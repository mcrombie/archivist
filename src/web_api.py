from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from uuid import uuid4

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from costs import CostLimitExceeded, UsageLedger, usage_scope
from exposure_profile import ExposureProfile, ExposureSettings
from importers import chapter_title_from_text
from perspectives import (
    AnswerPerspective,
    AnswerVoice,
    HistoriographicalLens,
    Worldview,
    settings_for_legacy_perspective,
)
from rag_pipeline import answer_run_diagnostics
from public_request_gate import PublicRequestGate
from public_sources import (
    PublicSourceError,
    answer_has_extended_verbatim_overlap,
    load_locator_index,
    public_source_payload,
)

from web_project import (
    BASE_DIR,
    answer_project_question_result,
    build_project,
    candidate_terms,
    current_answer_corpus_integrity,
    embed_project,
    generate_index_entry,
    list_projects,
    load_manifest,
    load_project_chunks,
    search_existing_index,
    source_payload,
    source_dir,
)


FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
SAFE_USAGE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
logger = logging.getLogger(__name__)
EXPOSURE_SETTINGS = ExposureSettings.from_env()
_PUBLIC_RUNTIME_VERIFIED = False

app = FastAPI(
    title="Archivist API",
    version="0.1.0",
    description="Local-first manuscript RAG and indexing API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


class ConversationTurn(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)
    answer: str = Field(min_length=1, max_length=12_000)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)
    n_results: int = Field(default=5, ge=1, le=12)
    historiographical_lens: HistoriographicalLens = HistoriographicalLens.EVIDENCE_FIRST
    voice: AnswerVoice = AnswerVoice.SCHOLARLY
    worldview: Worldview = Worldview.NONE
    perspective: AnswerPerspective | None = None
    history: list[ConversationTurn] = Field(default_factory=list, max_length=12)
    conversation_id: str | None = Field(
        default=None,
        pattern=SAFE_USAGE_ID_PATTERN,
        max_length=128,
    )
    turn_id: str | None = Field(
        default=None,
        pattern=SAFE_USAGE_ID_PATTERN,
        max_length=128,
    )
    allow_over_budget: bool = False

    @field_validator("question")
    @classmethod
    def question_is_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question cannot be blank")
        return stripped

    @model_validator(mode="before")
    @classmethod
    def translate_legacy_perspective(cls, data: object) -> object:
        if not isinstance(data, Mapping) or data.get("perspective") is None:
            return data

        values = dict(data)
        lens, voice, worldview = settings_for_legacy_perspective(values["perspective"])
        values.setdefault("historiographical_lens", lens)
        values.setdefault("voice", voice)
        values.setdefault("worldview", worldview)
        return values


class IndexEntryRequest(BaseModel):
    term: str = Field(min_length=1)
    consult_existing_index: bool = False


class CostSettingsRequest(BaseModel):
    monthly_budget_usd: Decimal | None = Field(ge=Decimal("0.01"), le=Decimal("100000"))
    warning_threshold_percent: int = Field(ge=1, le=100)
    hard_limit_enabled: bool


class PublicConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1_500)
    answer: str = Field(min_length=1, max_length=6_000)


class PublicQuestionRequest(BaseModel):
    """The fixed public contract intentionally has no tuning or budget bypass."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1_500)
    historiographical_lens: HistoriographicalLens = HistoriographicalLens.EVIDENCE_FIRST
    voice: AnswerVoice = AnswerVoice.SCHOLARLY
    worldview: Worldview = Worldview.NONE
    history: list[PublicConversationTurn] = Field(default_factory=list, max_length=6)
    conversation_id: str | None = Field(
        default=None,
        pattern=SAFE_USAGE_ID_PATTERN,
        max_length=128,
    )
    turn_id: str | None = Field(
        default=None,
        pattern=SAFE_USAGE_ID_PATTERN,
        max_length=128,
    )

    @field_validator("question")
    @classmethod
    def question_is_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question cannot be blank")
        return stripped


def _feature_flags(profile: ExposureProfile) -> dict[str, bool]:
    public = profile is ExposureProfile.PUBLIC_DEMO
    return {
        "cost_ledger": not public,
        "full_source_text": not public,
        "local_tools": not public,
        "public_page_locators": public,
    }


def _development_config() -> dict[str, object]:
    return {
        "exposure_profile": ExposureProfile.DEVELOPMENT.value,
        "project": load_manifest("current"),
        "features": _feature_flags(ExposureProfile.DEVELOPMENT),
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def app_config() -> dict[str, object]:
    return _development_config()


@app.get("/api/costs/summary")
def cost_summary(
    project_id: Annotated[str | None, Query(max_length=128)] = None,
    conversation_id: Annotated[
        str | None,
        Query(pattern=SAFE_USAGE_ID_PATTERN, max_length=128),
    ] = None,
    turn_id: Annotated[
        str | None,
        Query(pattern=SAFE_USAGE_ID_PATTERN, max_length=128),
    ] = None,
) -> dict[str, object]:
    return UsageLedger().summary(
        project_id=project_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
    )


@app.get("/api/costs/settings")
def cost_settings() -> dict[str, object]:
    return UsageLedger().get_settings()


@app.put("/api/costs/settings")
def update_cost_settings(request: CostSettingsRequest) -> dict[str, object]:
    return UsageLedger().update_settings(
        monthly_budget_usd=request.monthly_budget_usd,
        warning_threshold_percent=request.warning_threshold_percent,
        hard_limit_enabled=request.hard_limit_enabled,
    )


@app.get("/api/projects")
def projects() -> dict[str, object]:
    return {"projects": list_projects()}


@app.get("/api/projects/{project_id}")
def project(project_id: str) -> dict[str, object]:
    try:
        return {"project": load_manifest(project_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects")
async def create_project(
    project_name: Annotated[str, Form()],
    ignore_existing_index: Annotated[bool, Form()] = True,
    consult_existing_index: Annotated[bool, Form()] = False,
    files: Annotated[list[UploadFile], File()] = [],
) -> dict[str, object]:
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one manuscript file.")

    uploaded_files: list[tuple[str, bytes]] = []
    for upload in files:
        uploaded_files.append((upload.filename or "upload.md", await upload.read()))

    try:
        manifest = build_project(
            project_name=project_name,
            uploaded_files=uploaded_files,
            ignore_existing_index=ignore_existing_index,
            consult_existing_index=consult_existing_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"project": manifest}


@app.post("/api/projects/{project_id}/embed")
def embed(project_id: str) -> dict[str, object]:
    try:
        with usage_scope(project_id=project_id):
            return {"project": embed_project(project_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {exc}") from exc


@app.post("/api/projects/{project_id}/question")
def question(project_id: str, request: QuestionRequest) -> dict[str, object]:
    ledger = UsageLedger()
    budget = ledger.budget_state()
    if budget["hard_limit_enabled"] and budget["exceeded"] and not request.allow_over_budget:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "cost_limit_exceeded",
                "message": (
                    "The local monthly OpenAI cost limit has been reached. "
                    "Set allow_over_budget to true to run this request anyway."
                ),
                "budget": budget,
            },
        )

    try:
        with usage_scope(
            project_id=project_id,
            conversation_id=request.conversation_id,
            turn_id=request.turn_id,
            enforce_budget=True,
            allow_over_budget=request.allow_over_budget,
        ):
            answer_result = answer_project_question_result(
                project_id,
                request.question,
                n_results=request.n_results,
                historiographical_lens=request.historiographical_lens,
                voice=request.voice,
                worldview=request.worldview,
                history=[turn.model_dump() for turn in request.history],
            )
            resolved_query = answer_result.resolved_question
            answer = answer_result.answer
            chunks = answer_result.final_chunks
            run_diagnostics = answer_run_diagnostics(answer_result)
        try:
            ledger.record_answer_run_diagnostics(
                project_id=project_id,
                conversation_id=request.conversation_id,
                turn_id=request.turn_id,
                diagnostics=run_diagnostics,
            )
        except Exception:
            logger.exception("Could not persist text-free answer-run diagnostics")
        try:
            costs = ledger.summary(
                project_id=project_id,
                conversation_id=request.conversation_id,
                turn_id=request.turn_id,
            )
        except Exception:
            logger.exception("Could not load the post-answer local cost summary")
            costs = None
        return {
            "answer": answer,
            "answer_status": answer_result.status,
            "content_outcome": getattr(answer_result, "content_outcome", None),
            "evidence_decision": answer_result.evidence_decision,
            "run_diagnostics": run_diagnostics,
            "resolved_query": resolved_query,
            "conversation_id": request.conversation_id,
            "turn_id": request.turn_id,
            "historiographical_lens": request.historiographical_lens.value,
            "voice": request.voice.value,
            "worldview": request.worldview.value,
            "perspective": request.perspective.value if request.perspective is not None else None,
            **source_payload(chunks),
            "costs": costs,
        }
    except CostLimitExceeded as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "cost_limit_exceeded",
                "message": (
                    "The local monthly OpenAI cost limit has been reached. "
                    "Set allow_over_budget to true to run this request anyway."
                ),
                "budget": exc.budget,
            },
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Question failed: {exc}") from exc


@app.post("/api/projects/{project_id}/index/entry")
def index_entry(project_id: str, request: IndexEntryRequest) -> dict[str, object]:
    try:
        with usage_scope(project_id=project_id):
            output, chunks, existing_index_chunks = generate_index_entry(
                project_id=project_id,
                term=request.term,
                consult_existing_index=request.consult_existing_index,
            )
        payload = source_payload(chunks)
        return {
            "entry": output,
            **payload,
            "existing_index_sources": source_payload(existing_index_chunks)["sources"],
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Index entry failed: {exc}") from exc


@app.get("/api/projects/{project_id}/index/search")
def existing_index_search(
    project_id: str,
    term: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> dict[str, object]:
    try:
        chunks = search_existing_index(project_id, term, limit=limit)
        return {"results": source_payload(chunks)["sources"]}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/index/candidates")
def index_candidates(
    project_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, object]:
    try:
        return {"terms": candidate_terms(project_id, limit=limit)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/sources")
def sources(
    project_id: str,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    search: Annotated[str | None, Query(max_length=200)] = None,
    document: Annotated[str | None, Query(max_length=300)] = None,
) -> dict[str, object]:
    chunks = load_project_chunks(project_id)
    reading_chunks: list[dict[str, object]] = []
    previous_document: str | None = None
    previous_end = 0
    current_chapter_title: str | None = None

    for chunk in chunks:
        reading_chunk = dict(chunk)
        document = str(chunk.get("document", ""))
        start = int(chunk.get("paragraph_start") or 1)
        end = int(chunk.get("paragraph_end") or start)

        if document != previous_document:
            current_chapter_title = str(chunk.get("chapter_title", "N/A"))
        detected_title = chapter_title_from_text(str(chunk.get("text", "")))
        if detected_title:
            current_chapter_title = detected_title
        reading_chunk["chapter_title"] = current_chapter_title or "N/A"

        if document == previous_document and start <= previous_end:
            overlap = previous_end - start + 1
            paragraphs = str(chunk.get("text", "")).split("\n\n")
            reading_chunk["text"] = "\n\n".join(paragraphs[overlap:])
            reading_chunk["paragraph_start"] = start + overlap

        if str(reading_chunk.get("text", "")).strip():
            reading_chunks.append(reading_chunk)

        previous_document = document
        previous_end = end

    documents = sorted({str(chunk.get("document", "N/A")) for chunk in reading_chunks})
    filtered_chunks = reading_chunks
    if document:
        filtered_chunks = [
            chunk for chunk in filtered_chunks if str(chunk.get("document", "")) == document
        ]
    if search and search.strip():
        needle = search.strip().casefold()
        filtered_chunks = [
            chunk
            for chunk in filtered_chunks
            if needle in str(chunk.get("text", "")).casefold()
            or needle in str(chunk.get("chapter_title", "")).casefold()
        ]

    selected = filtered_chunks[offset : offset + limit]
    return {
        "total": len(filtered_chunks),
        "sources": source_payload(selected)["sources"],
        "documents": documents,
    }


@app.get("/api/projects/{project_id}/source-file/{file_path:path}")
def source_file(project_id: str, file_path: str) -> FileResponse:
    root = source_dir(project_id).resolve()
    requested = (root / file_path).resolve()
    try:
        requested.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid source file path.") from exc
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="Source file not found.")
    return FileResponse(
        requested, media_type="application/pdf" if requested.suffix.lower() == ".pdf" else None
    )


@app.get("/{full_path:path}")
def app_shell(full_path: str) -> FileResponse:
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-store, max-age=0",
                "Pragma": "no-cache",
            },
        )
    raise HTTPException(status_code=404, detail="Frontend has not been built yet.")


_development_app = app


def _public_project_config(settings: ExposureSettings) -> dict[str, object]:
    global _PUBLIC_RUNTIME_VERIFIED
    if not _PUBLIC_RUNTIME_VERIFIED:
        integrity = current_answer_corpus_integrity()
        if not integrity.passed:
            raise PublicSourceError("private corpus identity verification failed")
        _PUBLIC_RUNTIME_VERIFIED = True
    manifest = load_manifest("current")
    stats = manifest.get("stats")
    searchable_chunks = (
        int(stats.get("searchable_chunks") or 0) if isinstance(stats, Mapping) else 0
    )
    embedded_chunks = int(manifest.get("embedded_chunks") or 0)
    load_locator_index(
        settings.locator_artifact,
        BASE_DIR / "fixtures" / "corpus_manifest.json",
    )
    return {
        "exposure_profile": ExposureProfile.PUBLIC_DEMO.value,
        "project": {
            "id": "current",
            "name": "Cradle of the Empire",
            "created_at": "",
            "updated_at": "",
            "settings": {
                "ignore_existing_index": True,
                "consult_existing_index": False,
            },
            "stats": {
                "source_files": 0,
                "chunks": searchable_chunks,
                "searchable_chunks": searchable_chunks,
                "existing_index_chunks": 0,
            },
            "source_files": [],
            "ignored_documents": [],
            "existing_index_documents": [],
            "embedded": bool(manifest.get("embedded")),
            "embedded_chunks": embedded_chunks,
            "is_builtin": True,
        },
        "features": _feature_flags(ExposureProfile.PUBLIC_DEMO),
    }


def _public_safe_error(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    retry_after: int | None = None,
) -> JSONResponse:
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "detail": {
                "code": code,
                "message": message,
                "request_id": request_id,
            }
        },
    )


def _with_public_security_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "base-uri 'none'; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data:; "
        "object-src 'none'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'"
    )
    return response


def _configure_public_budget(
    ledger: UsageLedger,
    settings: ExposureSettings,
) -> None:
    budget = settings.public_monthly_budget_usd
    if budget is None:
        raise RuntimeError("public budget is not configured")
    stored = ledger.get_settings()
    stored_budget = stored.get("monthly_budget_usd")
    if (
        stored_budget is None
        or Decimal(str(stored_budget)) != budget
        or stored.get("warning_threshold_percent") != 80
        or stored.get("hard_limit_enabled") is not True
    ):
        ledger.update_settings(
            monthly_budget_usd=budget,
            warning_threshold_percent=80,
            hard_limit_enabled=True,
        )


def _run_public_question(
    request: PublicQuestionRequest,
    settings: ExposureSettings,
) -> dict[str, object]:
    request_id = uuid4().hex
    ledger = UsageLedger()
    try:
        _configure_public_budget(ledger, settings)
        budget = ledger.budget_state()
        if budget["exceeded"]:
            raise CostLimitExceeded(budget)

        with usage_scope(
            project_id="current",
            conversation_id=request.conversation_id,
            turn_id=request.turn_id,
            enforce_budget=True,
            allow_over_budget=False,
        ):
            answer_result = answer_project_question_result(
                "current",
                request.question,
                n_results=settings.public_n_results,
                historiographical_lens=request.historiographical_lens,
                voice=request.voice,
                worldview=request.worldview,
                history=[turn.model_dump() for turn in request.history],
            )
            if answer_result.status in {
                "generation_contract_failed",
                "corpus_integrity_failed",
            }:
                raise PublicSourceError("answer did not pass the public release gate")
            if answer_has_extended_verbatim_overlap(
                answer_result.answer,
                answer_result.final_chunks,
            ):
                raise PublicSourceError("answer exceeded the public quotation boundary")
            sources = public_source_payload(
                answer_result.answer,
                answer_result.final_chunks,
                locator_path=settings.locator_artifact,
                manifest_path=BASE_DIR / "fixtures" / "corpus_manifest.json",
            )

        try:
            ledger.record_answer_run_diagnostics(
                project_id="current",
                conversation_id=request.conversation_id,
                turn_id=request.turn_id,
                diagnostics=answer_run_diagnostics(answer_result),
            )
        except Exception:
            logger.exception(
                "Could not persist public answer diagnostics request_id=%s",
                request_id,
            )
        return {
            "answer": answer_result.answer,
            "answer_status": answer_result.status,
            "content_outcome": getattr(answer_result, "content_outcome", None),
            "historiographical_lens": request.historiographical_lens.value,
            "voice": request.voice.value,
            "worldview": request.worldview.value,
            **sources,
        }
    except CostLimitExceeded:
        logger.warning("Public spend ceiling reached request_id=%s", request_id)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "public_usage_limit",
                "message": "The public demo has reached its current usage limit. Please try later.",
                "request_id": request_id,
            },
        ) from None
    except (FileNotFoundError, PublicSourceError):
        logger.exception("Public answer release gate failed request_id=%s", request_id)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "public_answer_unavailable",
                "message": "Archivist could not safely present this answer. Please try again.",
                "request_id": request_id,
            },
        ) from None
    except Exception:
        logger.exception("Public question failed request_id=%s", request_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "public_request_failed",
                "message": "Archivist could not complete this request.",
                "request_id": request_id,
            },
        ) from None


def _create_public_app(settings: ExposureSettings) -> FastAPI:
    public_app = FastAPI(
        title="Archivist",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    gate = PublicRequestGate(
        requests_per_minute=settings.public_requests_per_minute,
        global_requests_per_minute=settings.public_global_requests_per_minute,
        max_concurrent_requests=settings.public_max_concurrent_requests,
        max_concurrent_per_client=settings.public_max_concurrent_per_client,
    )

    @public_app.middleware("http")
    async def public_security_boundary(request: Request, call_next):
        is_question = (
            request.method == "POST" and request.url.path == "/api/projects/current/question"
        )
        client_id = request.client.host if request.client is not None else "unknown"
        entered_gate = False
        if is_question:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    too_large = int(content_length) > settings.public_max_request_bytes
                except ValueError:
                    too_large = True
                if too_large:
                    return _with_public_security_headers(
                        _public_safe_error(
                            status_code=413,
                            code="request_too_large",
                            message="This question is too large for the public demo.",
                            request_id=uuid4().hex,
                        )
                    )
            body = await request.body()
            if len(body) > settings.public_max_request_bytes:
                return _with_public_security_headers(
                    _public_safe_error(
                        status_code=413,
                        code="request_too_large",
                        message="This question is too large for the public demo.",
                        request_id=uuid4().hex,
                    )
                )
            decision = gate.try_enter(client_id)
            if not decision.allowed:
                return _with_public_security_headers(
                    _public_safe_error(
                        status_code=429,
                        code="request_limit",
                        message="Archivist is busy. Please wait before trying again.",
                        request_id=uuid4().hex,
                        retry_after=decision.retry_after_seconds,
                    )
                )
            entered_gate = True
        try:
            response = await call_next(request)
        finally:
            if entered_gate:
                gate.leave(client_id)
        return _with_public_security_headers(response)

    if FRONTEND_DIST.exists():
        public_app.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_DIST / "assets"),
            name="assets",
        )

    @public_app.get("/api/live")
    def public_liveness() -> dict[str, str]:
        """Process-only probe used while a new private disk is being seeded."""

        return {"status": "live"}

    @public_app.get("/api/health")
    def public_health() -> dict[str, str]:
        try:
            config = _public_project_config(settings)
            project = config["project"]
            if (
                not isinstance(project, Mapping)
                or project.get("embedded") is not True
                or project.get("embedded_chunks") != 481
            ):
                raise PublicSourceError("private corpus is not ready")
            return {"status": "ready"}
        except Exception:
            logger.exception("Public readiness check failed")
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "service_not_ready",
                    "message": "Archivist is not ready.",
                },
            ) from None

    @public_app.get("/api/config")
    def public_config() -> dict[str, object]:
        try:
            return _public_project_config(settings)
        except Exception:
            logger.exception("Public configuration check failed")
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "service_not_ready",
                    "message": "Archivist is not ready.",
                },
            ) from None

    @public_app.post("/api/projects/current/question")
    def public_question(request: PublicQuestionRequest) -> dict[str, object]:
        return _run_public_question(request, settings)

    @public_app.api_route(
        "/api",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    @public_app.api_route(
        "/api/{full_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    def public_api_not_found(full_path: str = "") -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": {"code": "not_found", "message": "Not found."}},
        )

    @public_app.get("/docs")
    @public_app.get("/redoc")
    @public_app.get("/openapi.json")
    def public_docs_not_found() -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": {"code": "not_found", "message": "Not found."}},
        )

    @public_app.get("/{full_path:path}")
    def public_app_shell(full_path: str) -> FileResponse:
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(
                index_file,
                headers={
                    "Cache-Control": "no-store, max-age=0",
                    "Pragma": "no-cache",
                },
            )
        raise HTTPException(status_code=404, detail="Frontend has not been built yet.")

    return public_app


def create_app(settings: ExposureSettings | None = None) -> FastAPI:
    selected = settings or ExposureSettings.from_env()
    if selected.profile is ExposureProfile.PUBLIC_DEMO:
        return _create_public_app(selected)
    return _development_app


app = create_app(EXPOSURE_SETTINGS)
