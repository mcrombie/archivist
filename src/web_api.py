from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from threading import Lock
from time import perf_counter_ns
from typing import Annotated
from uuid import uuid4

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from answer_progress import (
    ANSWER_STREAM_MEDIA_TYPE,
    ANSWER_STREAM_SCHEMA,
    PROGRESS_MESSAGES,
    AnswerProgressStage,
    CheckedClaimCallback,
    CheckedClaimCandidate,
    ProgressCallback,
    ProviderStreamMilestone,
    ProviderStreamMilestoneCallback,
    emit_progress,
)
from authored_response import authored_response_prompt_metadata
from character_conversation import character_conversation_prompt_metadata
from archivist_modes import (
    ArchivistMode,
    application_compiled_modes,
    archivist_mode_metadata,
    settings_for_archivist_mode,
)
from costs import (
    PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD,
    CostLimitExceeded,
    UsageLedger,
    enforce_projected_usage_budget,
    usage_scope,
)
from exposure_profile import ExposureProfile, ExposureSettings
from full_context_pipeline import eligible_full_context_chunks
from importers import chapter_title_from_text
from perspectives import (
    AnswerPerspective,
    AnswerVoice,
    HistoriographicalLens,
    Worldview,
    settings_for_legacy_perspective,
)
from rag_pipeline import (
    COMPACT_RAG_POLICY_VERSION,
    RAG_POLICY_VERSION,
    V27_COMPACT_CANDIDATE_POLICY,
    AnswerStrategy,
    RagPolicy,
    answer_run_diagnostics,
)
from public_telemetry import (
    PROCESS_EPOCH,
    PublicTelemetryIdentityError,
    new_public_request_observation,
    observation_log_payload,
    public_runtime_identity,
    validated_deployment_commit,
)
from public_request_gate import (
    DEFAULT_CATEGORY,
    FULL_CONTEXT_CATEGORY,
    PublicRequestGate,
)
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
_PUBLIC_REQUEST_ID: ContextVar[str | None] = ContextVar(
    "archivist_public_request_id",
    default=None,
)

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
    archivist_mode: ArchivistMode | None = None
    archivist_mode_version: str | None = Field(default=None, max_length=32)
    influence_profile_id: str | None = Field(default=None, max_length=128)
    influence_profile_version: str | None = Field(default=None, max_length=32)


class DevelopmentRagPolicyVersion(StrEnum):
    """Development-only choices; the public request contract omits this field."""

    V26 = RAG_POLICY_VERSION
    V27_COMPACT = COMPACT_RAG_POLICY_VERSION


_APPLICATION_COMPILED_MODES = application_compiled_modes()


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)
    n_results: int = Field(default=5, ge=1, le=12)
    archivist_mode: ArchivistMode = ArchivistMode.ESSENTIAL
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
    # Omitting this stays byte-identical to the retrieval behavior that predates
    # evidence scopes. n_results keeps its meaning for "rag" and has no effect
    # for "full_context", which has no retrieval depth to tune.
    answer_strategy: AnswerStrategy = AnswerStrategy.RAG
    # Omitted selects the current application-compiled product. Supplying V26
    # or V27 is an explicit local experiment that retains the frozen/development
    # evidence-planned pipelines without conflating their identity.
    rag_policy_version: DevelopmentRagPolicyVersion | None = None

    @field_validator("question")
    @classmethod
    def question_is_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question cannot be blank")
        return stripped

    @field_validator("archivist_mode")
    @classmethod
    def archivist_mode_is_selectable(cls, value: ArchivistMode) -> ArchivistMode:
        if value not in _APPLICATION_COMPILED_MODES:
            raise ValueError("this Archivist mode is temporarily unavailable")
        return value

    @model_validator(mode="before")
    @classmethod
    def resolve_interpretive_defaults(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            return data

        values = dict(data)
        if values.get("perspective") is not None:
            lens, voice, worldview = settings_for_legacy_perspective(values["perspective"])
            values.setdefault("historiographical_lens", lens)
            values.setdefault("voice", voice)
            values.setdefault("worldview", worldview)
        if "archivist_mode" in values:
            lens, voice, worldview = settings_for_archivist_mode(values["archivist_mode"])
            values.setdefault("historiographical_lens", lens)
            values.setdefault("voice", voice)
            values.setdefault("worldview", worldview)
        return values

    @model_validator(mode="after")
    def essential_has_no_prose_overrides(self) -> QuestionRequest:
        if (
            self.archivist_mode is ArchivistMode.ESSENTIAL
            and self.answer_strategy is AnswerStrategy.FULL_CONTEXT
        ):
            raise ValueError(
                "Essential is a direct-evidence RAG mode and requires Retrieved passages"
            )
        if (
            self.archivist_mode is ArchivistMode.ESSENTIAL
            and self.answer_strategy is AnswerStrategy.RAG
            and self.rag_policy_version is None
            and self.perspective is None
            and (
                self.historiographical_lens is not HistoriographicalLens.EVIDENCE_FIRST
                or self.voice is not AnswerVoice.SCHOLARLY
                or self.worldview is not Worldview.NONE
            )
        ):
            raise ValueError("Essential direct evidence does not use prose settings")
        return self


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
    archivist_mode: ArchivistMode | None = None
    archivist_mode_version: str | None = Field(default=None, max_length=32)
    influence_profile_id: str | None = Field(default=None, max_length=128)
    influence_profile_version: str | None = Field(default=None, max_length=32)


class PublicQuestionRequest(BaseModel):
    """The fixed public contract intentionally has no tuning or budget bypass."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1_500)
    archivist_mode: ArchivistMode = ArchivistMode.ESSENTIAL
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
    answer_strategy: AnswerStrategy = AnswerStrategy.RAG

    @field_validator("question")
    @classmethod
    def question_is_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question cannot be blank")
        return stripped

    @field_validator("archivist_mode")
    @classmethod
    def archivist_mode_is_selectable(cls, value: ArchivistMode) -> ArchivistMode:
        if value not in _APPLICATION_COMPILED_MODES:
            raise ValueError("this Archivist mode is temporarily unavailable")
        return value

    @model_validator(mode="before")
    @classmethod
    def resolve_mode_defaults(cls, data: object) -> object:
        if not isinstance(data, Mapping) or "archivist_mode" not in data:
            return data
        values = dict(data)
        lens, voice, worldview = settings_for_archivist_mode(values["archivist_mode"])
        values.setdefault("historiographical_lens", lens)
        values.setdefault("voice", voice)
        values.setdefault("worldview", worldview)
        return values

    @model_validator(mode="after")
    def essential_has_no_prose_overrides(self) -> PublicQuestionRequest:
        if (
            self.archivist_mode is ArchivistMode.ESSENTIAL
            and self.answer_strategy is AnswerStrategy.FULL_CONTEXT
        ):
            raise ValueError(
                "Essential is a direct-evidence RAG mode and requires Retrieved passages"
            )
        if self.archivist_mode is ArchivistMode.ESSENTIAL and (
            self.historiographical_lens is not HistoriographicalLens.EVIDENCE_FIRST
            or self.voice is not AnswerVoice.SCHOLARLY
            or self.worldview is not Worldview.NONE
        ):
            raise ValueError("Essential direct evidence does not use prose settings")
        return self


def _uses_application_compiled_answer(
    *,
    archivist_mode: ArchivistMode,
    answer_strategy: AnswerStrategy,
    legacy_perspective: bool = False,
    rag_policy_version: DevelopmentRagPolicyVersion | None = None,
) -> bool:
    """Select the product compiler without changing legacy or full-book routes."""

    return (
        answer_strategy is AnswerStrategy.RAG
        and archivist_mode in _APPLICATION_COMPILED_MODES
        and not legacy_perspective
        and rag_policy_version is None
    )


def _answer_mode_metadata(
    *,
    archivist_mode: ArchivistMode,
    historiographical_lens: HistoriographicalLens,
    voice: AnswerVoice,
    worldview: Worldview,
    application_compiled: bool,
    answer_status: str | None = None,
) -> dict[str, object]:
    """Bind compatibility metadata to the exact authored prompt in use."""

    metadata = dict(archivist_mode_metadata(archivist_mode))
    if application_compiled and answer_status in {
        "character_conversation",
        "character_conversation_fallback",
    }:
        character_metadata = character_conversation_prompt_metadata(archivist_mode)
        metadata.update(
            {
                "prose_renderer_version": character_metadata[
                    "character_conversation_renderer_version"
                ],
                "prose_renderer_prompt_sha256": character_metadata[
                    "character_conversation_prompt_sha256"
                ],
                "prose_renderer_mode_instruction_sha256": character_metadata[
                    "character_conversation_mode_instruction_sha256"
                ],
                # The compact social prompt uses its own fictional-character
                # brief and does not claim that the historical influence file
                # was included in this call.
                "prose_renderer_influence_prompt_sha256": None,
            }
        )
    elif application_compiled and archivist_mode is not ArchivistMode.ESSENTIAL:
        authored_metadata = authored_response_prompt_metadata(
            archivist_mode,
            historiographical_lens=historiographical_lens,
            voice=voice,
            worldview=worldview,
        )
        metadata.update(
            {
                # Preserve the established API field names while fingerprinting
                # the actual one-call authored-response prompt, not the retired
                # cue renderer.
                "prose_renderer_version": authored_metadata[
                    "authored_response_renderer_version"
                ],
                "prose_renderer_prompt_sha256": authored_metadata[
                    "authored_response_prompt_sha256"
                ],
                "prose_renderer_mode_instruction_sha256": authored_metadata[
                    "authored_response_mode_instruction_sha256"
                ],
                "prose_renderer_influence_prompt_sha256": authored_metadata[
                    "authored_response_influence_prompt_sha256"
                ],
            }
        )
    else:
        metadata.update(
            {
                "prose_renderer_version": None,
                "prose_renderer_prompt_sha256": None,
                "prose_renderer_mode_instruction_sha256": None,
                "prose_renderer_influence_prompt_sha256": None,
            }
        )
    return metadata


def _feature_flags(
    profile: ExposureProfile,
    settings: ExposureSettings | None = None,
) -> dict[str, bool]:
    public = profile is ExposureProfile.PUBLIC_DEMO
    return {
        "cost_ledger": not public,
        "full_source_text": not public,
        "local_tools": not public,
        "public_page_locators": public,
        "progressive_answers": True,
        # The compact-schema experiment remains callable by an explicit local
        # development request, but it is no longer a reader-facing product
        # option now that the application-owned evidence compiler is active.
        "experimental_compact_rag": False,
        # Lets a client hide an option it cannot use. This is presentation only:
        # the server still rejects an explicit request for a disabled strategy,
        # because a stale or modified client must not be able to spend on one.
        "full_context_answers": bool(settings is not None and settings.full_context_available),
    }


def _require_full_context_available(
    settings: ExposureSettings,
    answer_strategy: AnswerStrategy,
) -> None:
    """Reject a disabled strategy outright rather than quietly answering another way.

    A silent downgrade to retrieval would be indistinguishable from a successful
    full-context answer, hiding both the cost difference and any disagreement
    between the two strategies - which is the comparison this feature exists for.
    """

    if answer_strategy is not AnswerStrategy.FULL_CONTEXT:
        return
    if settings.full_context_available:
        return
    raise HTTPException(
        status_code=422,
        detail={
            "code": "full_context_disabled",
            "message": "Full-context answers are not enabled on this server.",
            "requested_strategy": answer_strategy.value,
        },
    )


def _development_rag_policy(
    project_id: str,
    request: QuestionRequest,
) -> RagPolicy | None:
    """Resolve the local experiment without widening the public API contract."""

    if request.rag_policy_version in {None, DevelopmentRagPolicyVersion.V26}:
        # Keep the established path's downstream call shape unchanged.
        return None
    if project_id != "current":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "experimental_rag_policy_unavailable",
                "message": "The compact RAG experiment is available only for the built-in manuscript.",
            },
        )
    if request.answer_strategy is not AnswerStrategy.RAG:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "experimental_rag_policy_requires_retrieval",
                "message": "The compact RAG experiment applies only to Retrieved passages.",
            },
        )
    return V27_COMPACT_CANDIDATE_POLICY


def _development_config() -> dict[str, object]:
    return {
        "exposure_profile": ExposureProfile.DEVELOPMENT.value,
        "project": load_manifest("current"),
        "features": _feature_flags(ExposureProfile.DEVELOPMENT, EXPOSURE_SETTINGS),
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


def _development_question_preflight(
    request: QuestionRequest,
    *,
    project_id: str = "current",
) -> UsageLedger:
    _require_full_context_available(EXPOSURE_SETTINGS, request.answer_strategy)
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
    return ledger


def _run_development_question(
    project_id: str,
    request: QuestionRequest,
    *,
    progress_callback: ProgressCallback | None = None,
    checked_claim_callback: CheckedClaimCallback | None = None,
    stream_milestone_callback: ProviderStreamMilestoneCallback | None = None,
) -> dict[str, object]:
    rag_policy = _development_rag_policy(project_id, request)
    application_compiled = project_id == "current" and _uses_application_compiled_answer(
        archivist_mode=request.archivist_mode,
        answer_strategy=request.answer_strategy,
        legacy_perspective=request.perspective is not None,
        rag_policy_version=request.rag_policy_version,
    )
    ledger = _development_question_preflight(request, project_id=project_id)

    try:
        with usage_scope(
            project_id=project_id,
            conversation_id=request.conversation_id,
            turn_id=request.turn_id,
            enforce_budget=True,
            allow_over_budget=request.allow_over_budget,
        ):
            answer_kwargs: dict[str, object] = {
                "n_results": request.n_results,
                "historiographical_lens": request.historiographical_lens,
                "voice": request.voice,
                "worldview": request.worldview,
                "history": [turn.model_dump(exclude_none=True) for turn in request.history],
                "answer_strategy": request.answer_strategy,
            }
            if "archivist_mode" in request.model_fields_set:
                answer_kwargs["archivist_mode"] = request.archivist_mode
            if progress_callback is not None:
                answer_kwargs["progress_callback"] = progress_callback
            if checked_claim_callback is not None:
                answer_kwargs["checked_claim_callback"] = checked_claim_callback
            if stream_milestone_callback is not None:
                answer_kwargs["stream_milestone_callback"] = stream_milestone_callback
            if rag_policy is not None:
                answer_kwargs["rag_policy"] = rag_policy
            if application_compiled:
                answer_kwargs["application_compiled"] = True
            answer_result = answer_project_question_result(
                project_id,
                request.question,
                **answer_kwargs,
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
        mode_metadata = _answer_mode_metadata(
            archivist_mode=request.archivist_mode,
            historiographical_lens=request.historiographical_lens,
            voice=request.voice,
            worldview=request.worldview,
            application_compiled=application_compiled,
            answer_status=answer_result.status,
        )
        return {
            "answer": answer,
            "answer_status": answer_result.status,
            "content_outcome": getattr(answer_result, "content_outcome", None),
            "answer_strategy": getattr(
                answer_result,
                "answer_strategy",
                AnswerStrategy.RAG.value,
            ),
            "answer_strategy_version": getattr(
                answer_result,
                "answer_strategy_version",
                None,
            ),
            "evidence_decision": answer_result.evidence_decision,
            "run_diagnostics": run_diagnostics,
            "resolved_query": resolved_query,
            "conversation_id": request.conversation_id,
            "turn_id": request.turn_id,
            "archivist_mode": request.archivist_mode.value,
            "archivist_mode_version": mode_metadata["archivist_mode_version"],
            "influence_profile_id": mode_metadata["influence_profile_id"],
            "influence_profile_version": mode_metadata["influence_profile_version"],
            "influence_prompt_sha256": mode_metadata["influence_prompt_sha256"],
            "influence_provenance": mode_metadata["influence_provenance"],
            "prose_renderer_version": mode_metadata["prose_renderer_version"],
            "prose_renderer_prompt_sha256": mode_metadata["prose_renderer_prompt_sha256"],
            "prose_renderer_mode_instruction_sha256": mode_metadata[
                "prose_renderer_mode_instruction_sha256"
            ],
            "prose_renderer_influence_prompt_sha256": mode_metadata[
                "prose_renderer_influence_prompt_sha256"
            ],
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


@app.post("/api/projects/{project_id}/question")
def question(project_id: str, request: QuestionRequest) -> dict[str, object]:
    """Return the established complete JSON answer contract."""

    return _run_development_question(project_id, request)


# Keep interactive progress visibly alive through proxies and provider stalls.
# Heartbeats are schema-only frames and contain no manuscript or diagnostic data.
_STREAM_HEARTBEAT_SECONDS = 3.0
_ANSWER_WORKER_TASKS: set[asyncio.Task[None]] = set()
_PROGRESSIVE_TIMING_SCHEMA = "archivist.progressive_delivery_timing/1"


class _ProgressiveDeliveryTiming:
    """Record text-free progressive milestones and log once both sides finish."""

    def __init__(
        self,
        *,
        public: bool,
        clock_ns: Callable[[], int] = perf_counter_ns,
        wall_clock: Callable[[], datetime] | None = None,
        trace_id: str | None = None,
    ) -> None:
        self._public = public
        self._clock_ns = clock_ns
        self._started_ns = clock_ns()
        now = (wall_clock or (lambda: datetime.now(timezone.utc)))()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        self._accepted_at_utc = now.astimezone(timezone.utc).isoformat(timespec="milliseconds")
        self._trace_id = trace_id or uuid4().hex
        self._milestones_ms: dict[str, float] = {"accepted": 0.0}
        self._worker_finished = False
        self._stream_finished = False
        self._outcome = "interrupted"
        self._logged = False
        self._lock = Lock()

    def mark_stage(self, stage: AnswerProgressStage) -> None:
        self._mark(f"stage_{AnswerProgressStage(stage).value}")

    def mark_provider(self, milestone: ProviderStreamMilestone) -> None:
        self._mark(ProviderStreamMilestone(milestone).value)

    def mark_first_checked_claim(self) -> None:
        self._mark("first_checked_claim")

    def mark_terminal(self, outcome: str) -> None:
        selected = "complete" if outcome == "complete" else "error"
        self._mark(f"terminal_{selected}")

    def worker_finished(self) -> None:
        self._mark("worker_finished")
        self._finish(worker=True)

    def stream_finished(self, outcome: str) -> None:
        self._mark("stream_finished")
        self._finish(worker=False, outcome=outcome)

    def snapshot(self) -> dict[str, object]:
        """Return the safe, text-free timing payload used by tests and logs."""

        with self._lock:
            return self._snapshot_locked()

    def _elapsed_ms(self) -> float:
        return round(max(0, self._clock_ns() - self._started_ns) / 1_000_000, 3)

    def _mark(self, name: str) -> None:
        with self._lock:
            self._milestones_ms.setdefault(name, self._elapsed_ms())

    def _snapshot_locked(self) -> dict[str, object]:
        return {
            "schema": _PROGRESSIVE_TIMING_SCHEMA,
            "trace_id": self._trace_id,
            "public": self._public,
            "accepted_at_utc": self._accepted_at_utc,
            "outcome": self._outcome,
            "milestones_ms": dict(self._milestones_ms),
            "total_ms": self._elapsed_ms(),
        }

    def _finish(self, *, worker: bool, outcome: str | None = None) -> None:
        payload: dict[str, object] | None = None
        with self._lock:
            if worker:
                self._worker_finished = True
            else:
                self._stream_finished = True
                if outcome in {"complete", "error", "interrupted"}:
                    self._outcome = outcome
            if self._worker_finished and self._stream_finished and not self._logged:
                self._logged = True
                payload = self._snapshot_locked()
        if payload is not None:
            logger.info(
                "progressive_delivery_timing %s",
                json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
            )


class _GateLease:
    """Release one public gate slot exactly once."""

    def __init__(self, release: Callable[[], None]):
        self._release = release
        self._released = False
        self._lock = Lock()

    @property
    def released(self) -> bool:
        with self._lock:
            return self._released

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        self._release()


class _StreamGateLifecycle:
    """Hold a public gate lease until both worker and response stream finish."""

    def __init__(self, lease: _GateLease | None):
        self._lease = lease
        self._worker_finished = False
        self._stream_finished = False
        self._lock = Lock()

    def worker_finished(self) -> None:
        self._finish(worker=True)

    def stream_finished(self) -> None:
        self._finish(worker=False)

    def _finish(self, *, worker: bool) -> None:
        release = False
        with self._lock:
            if worker:
                self._worker_finished = True
            else:
                self._stream_finished = True
            release = self._worker_finished and self._stream_finished
        if release and self._lease is not None:
            self._lease.release()


_STREAM_ERROR_MESSAGES = {
    "cost_limit_exceeded": "The local monthly OpenAI cost limit has been reached.",
    "full_context_disabled": "Full-book answers are not available on this server.",
    "public_usage_limit": (
        "The public demo has reached its current usage limit. Please try later."
    ),
    "public_answer_unavailable": (
        "Archivist could not safely present this answer. Please try again."
    ),
    "public_request_failed": "Archivist could not complete this request.",
    "question_unavailable": "Archivist could not complete this request.",
}


def _safe_stream_error(exc: Exception, *, public: bool) -> dict[str, object]:
    fallback_code = "public_request_failed" if public else "question_unavailable"
    code = fallback_code
    request_id: str | None = None
    if isinstance(exc, HTTPException) and isinstance(exc.detail, Mapping):
        candidate = exc.detail.get("code")
        if isinstance(candidate, str) and candidate in _STREAM_ERROR_MESSAGES:
            code = candidate
        candidate_request_id = exc.detail.get("request_id")
        if (
            isinstance(candidate_request_id, str)
            and 1 <= len(candidate_request_id) <= 128
            and all(
                character.isalnum() or character in "._:-" for character in candidate_request_id
            )
        ):
            request_id = candidate_request_id
    error: dict[str, object] = {
        "code": code,
        "message": _STREAM_ERROR_MESSAGES[code],
    }
    if request_id is not None:
        error["request_id"] = request_id
    return error


def _ndjson_line(frame: Mapping[str, object]) -> str:
    return (
        json.dumps(
            jsonable_encoder(frame),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )


def _progressive_answer_response(
    worker: Callable[
        [ProgressCallback, CheckedClaimCallback, ProviderStreamMilestoneCallback],
        dict[str, object],
    ],
    *,
    public: bool,
    lifecycle: _StreamGateLifecycle | None = None,
    trace_id: str | None = None,
) -> StreamingResponse:
    """Deliver checked claims while retaining an authoritative terminal result."""

    timing = _ProgressiveDeliveryTiming(public=public, trace_id=trace_id)

    async def body():
        loop = asyncio.get_running_loop()
        events: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        seen_stages = {AnswerProgressStage.ACCEPTED}
        stage_lock = Lock()
        sequence = 0
        claim_index = 0
        stream_outcome = "interrupted"

        def enqueue_from_worker(event: tuple[str, object]) -> None:
            """Synchronize worker callbacks with the terminal result enqueue.

            ``call_soon_threadsafe`` alone permits a very fast worker to return
            before its scheduled claim callback runs, letting the terminal
            result overtake that claim. Waiting only for the queue put (never
            for network delivery) preserves order without coupling provider
            work to a connected browser.
            """

            put = events.put(event)
            try:
                future = asyncio.run_coroutine_threadsafe(put, loop)
            except RuntimeError:
                put.close()
                return
            try:
                future.result(timeout=2.0)
            except Exception:
                future.cancel()
                return

        def progress_callback(stage: AnswerProgressStage) -> None:
            try:
                selected = AnswerProgressStage(stage)
            except (TypeError, ValueError):
                return
            with stage_lock:
                if selected in seen_stages:
                    return
                seen_stages.add(selected)
            timing.mark_stage(selected)
            enqueue_from_worker(("stage", selected))

        def checked_claim_callback(candidate: CheckedClaimCandidate) -> None:
            if not isinstance(candidate, CheckedClaimCandidate):
                return
            timing.mark_first_checked_claim()
            enqueue_from_worker(("checked_claim", candidate))

        def stream_milestone_callback(milestone: ProviderStreamMilestone) -> None:
            try:
                selected = ProviderStreamMilestone(milestone)
            except (TypeError, ValueError):
                return
            timing.mark_provider(selected)

        async def execute_worker() -> None:
            try:
                result = await asyncio.to_thread(
                    worker,
                    progress_callback,
                    checked_claim_callback,
                    stream_milestone_callback,
                )
            except Exception as exc:
                await events.put(("error", _safe_stream_error(exc, public=public)))
            else:
                await events.put(("result", result))
            finally:
                timing.worker_finished()
                if lifecycle is not None:
                    lifecycle.worker_finished()

        worker_task = asyncio.create_task(execute_worker())
        # asyncio keeps only weak references to tasks. Retain paid workers after
        # a client disconnects so provider usage and the local ledger finalize.
        _ANSWER_WORKER_TASKS.add(worker_task)

        def worker_task_finished(task: asyncio.Task[None]) -> None:
            _ANSWER_WORKER_TASKS.discard(task)
            try:
                task.result()
            except BaseException:
                # Exception paths handled by execute_worker become safe frames;
                # cancellation or process shutdown must not become an orphaned
                # task warning.
                pass

        worker_task.add_done_callback(worker_task_finished)

        def frame(frame_type: str, **fields: object) -> str:
            nonlocal sequence
            sequence += 1
            return _ndjson_line(
                {
                    "schema": ANSWER_STREAM_SCHEMA,
                    "type": frame_type,
                    "sequence": sequence,
                    **fields,
                }
            )

        try:
            yield frame(
                "stage",
                stage=AnswerProgressStage.ACCEPTED.value,
                message=PROGRESS_MESSAGES[AnswerProgressStage.ACCEPTED],
            )
            while True:
                try:
                    event_type, value = await asyncio.wait_for(
                        events.get(),
                        timeout=_STREAM_HEARTBEAT_SECONDS,
                    )
                except TimeoutError:
                    yield frame("heartbeat")
                    continue

                if event_type == "stage":
                    stage = AnswerProgressStage(value)
                    yield frame(
                        "stage",
                        stage=stage.value,
                        message=PROGRESS_MESSAGES[stage],
                    )
                    continue
                if event_type == "checked_claim":
                    if not isinstance(value, CheckedClaimCandidate):
                        continue
                    claim_index += 1
                    yield frame(
                        "checked_claim",
                        claim_index=claim_index,
                        paragraph=value.paragraph,
                        text=value.text,
                    )
                    continue
                if event_type == "error":
                    timing.mark_terminal("error")
                    stream_outcome = "error"
                    yield frame("error", error=value)
                    break

                result = value
                if not isinstance(result, Mapping):
                    timing.mark_terminal("error")
                    stream_outcome = "error"
                    yield frame(
                        "error",
                        error={
                            "code": ("public_request_failed" if public else "question_unavailable"),
                            "message": "Archivist could not complete this request.",
                        },
                    )
                    break
                if result.get("answer_status") in {
                    "generation_contract_failed",
                    "corpus_integrity_failed",
                    "retrieval_unavailable",
                }:
                    timing.mark_terminal("error")
                    stream_outcome = "error"
                    yield frame(
                        "error",
                        error={
                            "code": ("public_request_failed" if public else "question_unavailable"),
                            "message": "Archivist could not complete this request.",
                        },
                    )
                    break
                timing.mark_terminal("complete")
                stream_outcome = "complete"
                yield frame("complete", result=dict(result))
                break
        finally:
            # Do not cancel worker_task on disconnect: the OpenAI request and its
            # usage ledger must finish. The lifecycle releases only after this
            # stream *and* that worker have both ended.
            timing.stream_finished(stream_outcome)
            if lifecycle is not None:
                lifecycle.stream_finished()

    return StreamingResponse(
        body(),
        media_type=ANSWER_STREAM_MEDIA_TYPE,
        headers={
            "Cache-Control": "no-store, no-transform",
            "CDN-Cache-Control": "no-store",
            "Surrogate-Control": "no-store",
            "Vary": "Accept",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/projects/{project_id}/question/progressive")
async def progressive_question(
    project_id: str,
    request: QuestionRequest,
) -> StreamingResponse:
    # Preserve ordinary HTTP errors for feature and spend checks. The worker
    # repeats this preflight to close the race with another in-flight request.
    _development_rag_policy(project_id, request)
    _development_question_preflight(request, project_id=project_id)
    return _progressive_answer_response(
        lambda progress, checked_claim, stream_milestone: _run_development_question(
            project_id,
            request,
            progress_callback=progress,
            checked_claim_callback=checked_claim,
            stream_milestone_callback=stream_milestone,
        ),
        public=False,
    )


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
        "features": _feature_flags(ExposureProfile.PUBLIC_DEMO, settings),
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
    response.headers["X-Archivist-Commit"] = validated_deployment_commit() or "unknown"
    response.headers["X-Archivist-Process-Epoch"] = PROCESS_EPOCH
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


def _public_verbatim_audit_chunks(
    *,
    answer_strategy: AnswerStrategy,
    final_chunks: list[dict[str, object]],
) -> list[Mapping[str, object]]:
    """Return the private evidence scope used by the public quotation guard.

    Retrieval answers can reproduce manuscript prose only from their selected
    context, so their established audit scope remains ``final_chunks``. A
    full-context answer saw every eligible chunk even though its result exposes
    only cited chunks; audit that complete private scope so omitting a citation
    cannot bypass the public verbatim boundary.
    """

    if answer_strategy is not AnswerStrategy.FULL_CONTEXT:
        return final_chunks

    eligible_chunks = eligible_full_context_chunks(load_project_chunks("current"))
    if not eligible_chunks:
        raise PublicSourceError("private full-context corpus is not available")
    return eligible_chunks


def _preflight_public_progressive_question(
    request: PublicQuestionRequest,
    settings: ExposureSettings,
    *,
    request_id: str | None = None,
) -> None:
    """Keep cheap policy/spend failures as ordinary HTTP responses."""

    request_id = request_id or _PUBLIC_REQUEST_ID.get() or uuid4().hex
    if (
        request.answer_strategy is AnswerStrategy.FULL_CONTEXT
        and not settings.full_context_available
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "full_context_disabled",
                "message": "Full-book answers are not available on this deployment.",
                "request_id": request_id,
            },
        )
    try:
        ledger = UsageLedger()
        _configure_public_budget(ledger, settings)
        budget = ledger.budget_state()
        if budget["exceeded"]:
            raise CostLimitExceeded(budget)
    except CostLimitExceeded:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "public_usage_limit",
                "message": (
                    "The public demo has reached its current usage limit. Please try later."
                ),
                "request_id": request_id,
            },
        ) from None
    except Exception:
        logger.exception("Public progressive preflight failed request_id=%s", request_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "public_request_failed",
                "message": "Archivist could not complete this request.",
                "request_id": request_id,
            },
        ) from None


def _run_public_question(
    request: PublicQuestionRequest,
    settings: ExposureSettings,
    *,
    progress_callback: ProgressCallback | None = None,
    checked_claim_callback: CheckedClaimCallback | None = None,
    stream_milestone_callback: ProviderStreamMilestoneCallback | None = None,
    request_id: str | None = None,
) -> dict[str, object]:
    request_id = request_id or _PUBLIC_REQUEST_ID.get() or uuid4().hex
    ledger = UsageLedger()
    application_compiled = _uses_application_compiled_answer(
        archivist_mode=request.archivist_mode,
        answer_strategy=request.answer_strategy,
    )
    answer_result: object | None = None
    released_claims: list[CheckedClaimCandidate] = []
    claim_release_failed = False

    def release_checked_claim(candidate: CheckedClaimCandidate) -> None:
        """Apply public policy synchronously before the best-effort observer."""

        nonlocal claim_release_failed
        if claim_release_failed:
            return
        try:
            cumulative = " ".join(
                [existing.text for existing in released_claims] + [candidate.text]
            )
            if answer_has_extended_verbatim_overlap(cumulative, candidate.audit_chunks):
                raise PublicSourceError("provisional claims exceeded quotation boundary")
            public_source_payload(
                candidate.text,
                list(candidate.source_chunks),
                locator_path=settings.locator_artifact,
                manifest_path=BASE_DIR / "fixtures" / "corpus_manifest.json",
            )
        except Exception:
            # A broken locator loader or release checker is a deny condition,
            # not permission to continue without provisional disclosure checks.
            claim_release_failed = True
            logger.exception(
                "Public provisional-claim gate failed request_id=%s",
                request_id,
            )
            return
        released_claims.append(candidate)
        if checked_claim_callback is not None:
            try:
                checked_claim_callback(candidate)
            except Exception:
                # Delivery is presentation. The paid run and final release gate
                # must still finish after a client disconnects.
                logger.debug("Public checked-claim observer failed", exc_info=True)

    if (
        request.answer_strategy is AnswerStrategy.FULL_CONTEXT
        and not settings.full_context_available
    ):
        # 503 matches the existing public-safe family for "not currently
        # available" and, unlike 422/403, does not disclose whether the cause is
        # configuration, budget, or policy.
        raise HTTPException(
            status_code=503,
            detail={
                "code": "full_context_disabled",
                "message": "Full-book answers are not available on this deployment.",
                "request_id": request_id,
            },
        )
    try:
        _configure_public_budget(ledger, settings)
        budget = ledger.budget_state()
        if budget["exceeded"]:
            raise CostLimitExceeded(budget)

        with usage_scope(
            project_id="current",
            conversation_id=request.conversation_id,
            turn_id=request.turn_id,
            request_id=request_id,
            enforce_budget=True,
            allow_over_budget=False,
            request_cost_ceiling_nano_usd=(
                PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD
                if request.answer_strategy is AnswerStrategy.RAG
                else None
            ),
        ):
            if request.answer_strategy is AnswerStrategy.RAG:
                # Reserve a whole conservative request before Answer Mode can
                # construct a provider client or issue its first operation.
                enforce_projected_usage_budget(
                    PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD,
                    ledger,
                )
            answer_kwargs: dict[str, object] = {
                "n_results": settings.public_n_results,
                "historiographical_lens": request.historiographical_lens,
                "voice": request.voice,
                "worldview": request.worldview,
                "history": [turn.model_dump(exclude_none=True) for turn in request.history],
                "answer_strategy": request.answer_strategy,
            }
            if "archivist_mode" in request.model_fields_set:
                answer_kwargs["archivist_mode"] = request.archivist_mode
            if progress_callback is not None:
                answer_kwargs["progress_callback"] = progress_callback
            if checked_claim_callback is not None:
                answer_kwargs["checked_claim_callback"] = release_checked_claim
            if stream_milestone_callback is not None:
                answer_kwargs["stream_milestone_callback"] = stream_milestone_callback
            if application_compiled:
                answer_kwargs["application_compiled"] = True
            answer_result = answer_project_question_result(
                "current",
                request.question,
                **answer_kwargs,
            )
            emit_progress(progress_callback, AnswerProgressStage.CHECKING_RELEASE)
            if claim_release_failed:
                raise PublicSourceError("provisional claim did not pass release gate")
            if answer_result.status in {
                "generation_contract_failed",
                "corpus_integrity_failed",
                "retrieval_unavailable",
            }:
                raise PublicSourceError("answer did not pass the public release gate")
            audit_chunks = _public_verbatim_audit_chunks(
                answer_strategy=request.answer_strategy,
                final_chunks=answer_result.final_chunks,
            )
            if answer_has_extended_verbatim_overlap(
                answer_result.answer,
                audit_chunks,
            ):
                raise PublicSourceError("answer exceeded the public quotation boundary")
            sources = public_source_payload(
                answer_result.answer,
                answer_result.final_chunks,
                locator_path=settings.locator_artifact,
                manifest_path=BASE_DIR / "fixtures" / "corpus_manifest.json",
            )

        mode_metadata = _answer_mode_metadata(
            archivist_mode=request.archivist_mode,
            historiographical_lens=request.historiographical_lens,
            voice=request.voice,
            worldview=request.worldview,
            application_compiled=application_compiled,
            answer_status=answer_result.status,
        )
        return {
            "answer": answer_result.answer,
            "answer_status": answer_result.status,
            "content_outcome": getattr(answer_result, "content_outcome", None),
            "answer_strategy": getattr(
                answer_result,
                "answer_strategy",
                AnswerStrategy.RAG.value,
            ),
            "answer_strategy_version": getattr(
                answer_result,
                "answer_strategy_version",
                None,
            ),
            "archivist_mode": request.archivist_mode.value,
            "archivist_mode_version": mode_metadata["archivist_mode_version"],
            "influence_profile_id": mode_metadata["influence_profile_id"],
            "influence_profile_version": mode_metadata["influence_profile_version"],
            "influence_prompt_sha256": mode_metadata["influence_prompt_sha256"],
            "influence_provenance": mode_metadata["influence_provenance"],
            "prose_renderer_version": mode_metadata["prose_renderer_version"],
            "prose_renderer_prompt_sha256": mode_metadata["prose_renderer_prompt_sha256"],
            "prose_renderer_mode_instruction_sha256": mode_metadata[
                "prose_renderer_mode_instruction_sha256"
            ],
            "prose_renderer_influence_prompt_sha256": mode_metadata[
                "prose_renderer_influence_prompt_sha256"
            ],
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
    finally:
        if answer_result is not None:
            try:
                ledger.record_answer_run_diagnostics(
                    project_id="current",
                    conversation_id=request.conversation_id,
                    turn_id=request.turn_id,
                    request_id=request_id,
                    diagnostics=answer_run_diagnostics(answer_result),
                )
            except Exception:
                logger.exception(
                    "Could not persist public answer diagnostics request_id=%s",
                    request_id,
                )


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
        category_requests_per_minute={
            FULL_CONTEXT_CATEGORY: settings.public_full_context_requests_per_minute,
        },
        category_max_concurrent_requests={
            FULL_CONTEXT_CATEGORY: settings.public_full_context_max_concurrent_requests,
        },
    )

    def _request_category(body: bytes) -> str:
        """Classify a question by evidence scope before it reaches the route.

        A body that cannot be parsed is treated as an ordinary request: the
        route's own validation will reject it, and guessing the expensive
        category from malformed input would let a bad body exhaust the stricter
        ceiling for everyone.
        """

        if not body:
            return DEFAULT_CATEGORY
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return DEFAULT_CATEGORY
        if not isinstance(payload, Mapping):
            return DEFAULT_CATEGORY
        if payload.get("answer_strategy") == AnswerStrategy.FULL_CONTEXT.value:
            return FULL_CONTEXT_CATEGORY
        return DEFAULT_CATEGORY

    def _request_observation_metadata(body: bytes) -> dict[str, str | None]:
        """Read only allowlisted, text-free fields from a public request body."""

        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            payload = None
        if not isinstance(payload, Mapping):
            return {
                "conversation_id": None,
                "turn_id": None,
                "archivist_mode": None,
                "answer_strategy": None,
            }

        def safe_scope(name: str) -> str | None:
            value = payload.get(name)
            if not isinstance(value, str) or not value or len(value) > 128 or not value.isascii():
                return None
            if not all(character.isalnum() or character in "._:-" for character in value):
                return None
            return value

        try:
            mode = ArchivistMode(payload.get("archivist_mode", ArchivistMode.ESSENTIAL.value))
        except (TypeError, ValueError):
            mode = None
        try:
            strategy = AnswerStrategy(payload.get("answer_strategy", AnswerStrategy.RAG.value))
        except (TypeError, ValueError):
            strategy = None
        return {
            "conversation_id": safe_scope("conversation_id"),
            "turn_id": safe_scope("turn_id"),
            "archivist_mode": mode.value if mode is not None else None,
            "answer_strategy": strategy.value if strategy is not None else None,
        }

    @public_app.middleware("http")
    async def public_security_boundary(request: Request, call_next):
        is_question = request.method == "POST" and request.url.path in {
            "/api/projects/current/question",
            "/api/projects/current/question/progressive",
        }
        started_ns = perf_counter_ns()
        request_id = uuid4().hex if is_question else None
        if request_id is not None:
            request.state.public_request_id = request_id
        delivery = "progressive_header" if request.url.path.endswith("/progressive") else "complete"
        route = "question_progressive" if delivery == "progressive_header" else "question"
        observation_metadata: dict[str, str | None] = {
            "conversation_id": None,
            "turn_id": None,
            "archivist_mode": None,
            "answer_strategy": None,
        }

        def finalize(response: Response) -> Response:
            if request_id is None:
                return _with_public_security_headers(response)
            duration_ms = round(
                max(0, perf_counter_ns() - started_ns) / 1_000_000,
                3,
            )
            commit = validated_deployment_commit()
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Archivist-Commit"] = commit or "unknown"
            response.headers["X-Archivist-Process-Epoch"] = PROCESS_EPOCH
            if delivery == "complete":
                response.headers["Server-Timing"] = f"app;dur={duration_ms:.3f}"
            else:
                response.headers["Server-Timing"] = f"app_header;dur={duration_ms:.3f}"
            observation = new_public_request_observation(
                request_id=request_id,
                route=route,
                delivery=delivery,
                conversation_id=observation_metadata["conversation_id"],
                turn_id=observation_metadata["turn_id"],
                archivist_mode=observation_metadata["archivist_mode"],
                answer_strategy=observation_metadata["answer_strategy"],
                http_status=response.status_code,
                duration_ms=duration_ms,
            )
            try:
                persisted = observation.as_dict()
                persisted.pop("schema", None)
                UsageLedger().record_public_request_observation(**persisted)
            except Exception:
                logger.exception(
                    "Could not persist public request observation request_id=%s",
                    request_id,
                )
            logger.info(
                "public_request_observation %s",
                json.dumps(
                    observation_log_payload(observation),
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
            return _with_public_security_headers(response)

        client_id = request.client.host if request.client is not None else "unknown"
        entered_gate = False
        gate_lease: _GateLease | None = None
        category = DEFAULT_CATEGORY
        if is_question:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    too_large = int(content_length) > settings.public_max_request_bytes
                except ValueError:
                    too_large = True
                if too_large:
                    return finalize(
                        _public_safe_error(
                            status_code=413,
                            code="request_too_large",
                            message="This question is too large for the public demo.",
                            request_id=request_id,
                        )
                    )
            body = await request.body()
            observation_metadata = _request_observation_metadata(body)
            if len(body) > settings.public_max_request_bytes:
                return finalize(
                    _public_safe_error(
                        status_code=413,
                        code="request_too_large",
                        message="This question is too large for the public demo.",
                        request_id=request_id,
                    )
                )
            category = _request_category(body)
            decision = gate.try_enter(client_id, category=category)
            if not decision.allowed:
                full_context_limited = category == FULL_CONTEXT_CATEGORY and decision.reason in {
                    "category_rate_limit",
                    "category_concurrency_limit",
                }
                return finalize(
                    _public_safe_error(
                        status_code=429,
                        code=(
                            "full_context_rate_limit" if full_context_limited else "request_limit"
                        ),
                        message=(
                            "Full-book answers are temporarily limited. Try a "
                            "retrieved-passage answer, or try again in a moment."
                            if full_context_limited
                            else "Archivist is busy. Please wait before trying again."
                        ),
                        request_id=request_id,
                        retry_after=decision.retry_after_seconds,
                    )
                )
            entered_gate = True
            gate_lease = _GateLease(lambda: gate.leave(client_id, category=category))
            request.state.public_gate_lease = gate_lease
        try:
            response = await call_next(request)
        except Exception:
            if request_id is None:
                raise
            logger.exception("Unhandled public question failure request_id=%s", request_id)
            response = _public_safe_error(
                status_code=500,
                code="public_request_failed",
                message="Archivist could not complete this request.",
                request_id=request_id,
            )
        finally:
            if (
                entered_gate
                and gate_lease is not None
                and not getattr(request.state, "public_gate_release_deferred", False)
            ):
                gate_lease.release()
        return finalize(response)

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

    @public_app.get("/api/version")
    def public_version() -> dict[str, object]:
        """Expose only the closed, text-free identity of the running candidate."""

        try:
            return public_runtime_identity()
        except PublicTelemetryIdentityError:
            logger.exception("Public runtime identity check failed")
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
    def public_question(
        request: PublicQuestionRequest,
        http_request: Request,
    ) -> dict[str, object]:
        token = _PUBLIC_REQUEST_ID.set(getattr(http_request.state, "public_request_id", None))
        try:
            return _run_public_question(request, settings)
        finally:
            _PUBLIC_REQUEST_ID.reset(token)

    @public_app.post("/api/projects/current/question/progressive")
    async def public_progressive_question(
        request: PublicQuestionRequest,
        http_request: Request,
    ) -> StreamingResponse:
        request_id = getattr(http_request.state, "public_request_id", None)
        token = _PUBLIC_REQUEST_ID.set(request_id)
        try:
            _preflight_public_progressive_question(request, settings)
        finally:
            _PUBLIC_REQUEST_ID.reset(token)
        lease = getattr(http_request.state, "public_gate_lease", None)
        lifecycle = _StreamGateLifecycle(lease if isinstance(lease, _GateLease) else None)

        def run_progressive(
            progress: ProgressCallback,
            checked_claim: CheckedClaimCallback,
            stream_milestone: ProviderStreamMilestoneCallback,
        ) -> dict[str, object]:
            worker_token = _PUBLIC_REQUEST_ID.set(request_id)
            try:
                return _run_public_question(
                    request,
                    settings,
                    progress_callback=progress,
                    checked_claim_callback=checked_claim,
                    stream_milestone_callback=stream_milestone,
                )
            finally:
                _PUBLIC_REQUEST_ID.reset(worker_token)

        response = _progressive_answer_response(
            run_progressive,
            public=True,
            lifecycle=lifecycle,
            trace_id=request_id,
        )
        if isinstance(lease, _GateLease):
            # The worker and stream now jointly own this lease. Middleware must
            # not release it when the StreamingResponse headers are returned.
            http_request.state.public_gate_release_deferred = True
        return response

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
