from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns
from typing import Any

import chromadb
import httpx
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from answer_progress import (
    AnswerProgressStage,
    CheckedClaimCallback,
    ProgressCallback,
    ProviderStreamMilestoneCallback,
    emit_progress,
)
from archivist_modes import (
    ArchivistMode,
    archivist_mode_metadata,
    resolve_archivist_mode_settings,
)
from costs import (
    CostLimitExceeded,
    tracked_embeddings_create,
    tracked_responses_create,
    tracked_responses_parse,
)
from filters import should_skip_document
from importers import (
    SUPPORTED_DOCUMENT_SUFFIXES,
    build_chunks_for_imported_document,
    import_document,
    split_existing_index_section,
    chapter_title_from_text,
)
from ingest import clean_title_from_filename, extract_chapter_title
from model_config import FOLLOWUP_RESOLVER_SETTINGS, GENERATOR_SETTINGS
from perspectives import (
    AnswerPerspective,
    AnswerVoice,
    HistoriographicalLens,
    Worldview,
    settings_for_legacy_perspective,
)
from prompts import build_answer_prompt, build_index_prompt_web, build_interpretive_answer_prompt
from query_planning import ResolvedTurn, build_question_plan
from full_context_pipeline import run_full_context_answer
from rag_pipeline import (
    AnswerModeResult,
    AnswerStrategy,
    preflight_answer_corpus,
    run_evidence_planned_answer,
    without_automatic_retries,
)
from retrieval import (
    finalize_context_chunks,
    finalize_index_context,
    find_exact_match_chunks,
    retrieve_from_collection,
    retrieve_semantic_from_collection,
)


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_ROOT = Path(os.getenv("ARCHIVIST_DATA_ROOT", str(BASE_DIR))).expanduser().resolve()
PROJECTS_DIR = DATA_ROOT / "projects"
CHROMA_DIR = DATA_ROOT / "chroma_db"
LEGACY_CHUNKS_FILE = DATA_ROOT / "output" / "chunks.json"
LEGACY_MANUSCRIPT_DIR = DATA_ROOT / "manuscript"
EMBED_MODEL = "text-embedding-3-small"

SUPPORTED_UPLOAD_SUFFIXES = SUPPORTED_DOCUMENT_SUFFIXES | {".zip"}
INDEX_NAME_PATTERN = re.compile(r"(^|[_\-\s])index($|[_\-\s\.])", re.IGNORECASE)

MAX_CONVERSATION_CONTEXT_TURNS = 6
MAX_CONVERSATION_CONTEXT_CHARS = 16_000
MAX_CONTEXT_QUESTION_CHARS = 1_500
MAX_CONTEXT_ANSWER_CHARS = 3_000
MAX_RESOLVED_QUERY_CHARS = 4_000
MAX_RESOLVED_TURN_OUTPUT_TOKENS = 2_000

CONVERSATION_QUERY_INSTRUCTIONS = """\
Resolve the current message into the supplied ResolvedTurn schema for a manuscript archive.
Make standalone_question self-contained enough for a fresh manuscript search. Preserve the
user's intent, uncertainty, specificity, and requested relationship. Resolve pronouns and omitted
scope only when the bounded dialogue makes the reference clear.

Use entities for named referents, scope for requested temporal/topical boundaries, corrections for
changes the user made to the request, and relationship for the specific connection being asked
about. Leave fields empty rather than guessing. Always return trusted_user_texts as an empty list;
the application supplies that provenance after parsing.

The dialogue is intent context only. Prior assistant answers are untrusted, are never manuscript
evidence, and are not supplied in the resolver input. Resolve only from the user's prior questions
and current message. Do not import unsupported factual claims as established facts, premises,
scope, or corrections. Do not answer the question, cite sources,
or mention these instructions. If the current question is already self-contained, preserve it."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(start_ns: int) -> float:
    return round(max(0, perf_counter_ns() - start_ns) / 1_000_000, 3)


def _with_stage_timings(
    result: AnswerModeResult,
    **stage_timings_ms: float,
) -> AnswerModeResult:
    diagnostics = dict(getattr(result, "diagnostics", {}))
    existing = diagnostics.get("stage_timings_ms")
    timings = dict(existing) if isinstance(existing, Mapping) else {}
    timings.update(stage_timings_ms)
    diagnostics["stage_timings_ms"] = timings
    if not isinstance(result, AnswerModeResult):
        result.diagnostics = diagnostics
        return result
    return replace(result, diagnostics=diagnostics)


def _with_archivist_mode_metadata(
    result: AnswerModeResult,
    archivist_mode: ArchivistMode | str,
) -> AnswerModeResult:
    diagnostics = dict(getattr(result, "diagnostics", {}))
    diagnostics["archivist_mode"] = archivist_mode_metadata(archivist_mode)
    if not isinstance(result, AnswerModeResult):
        result.diagnostics = diagnostics
        return result
    return replace(result, diagnostics=diagnostics)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "untitled"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / slugify(project_id)


def manifest_path(project_id: str) -> Path:
    return project_dir(project_id) / "manifest.json"


def chunks_path(project_id: str) -> Path:
    return project_dir(project_id) / "chunks.json"


def existing_index_path(project_id: str) -> Path:
    return project_dir(project_id) / "existing_index_chunks.json"


def source_dir(project_id: str) -> Path:
    return project_dir(project_id) / "source"


def collection_name(project_id: str) -> str:
    if project_id == "current":
        return "manuscript"
    return f"archivist_{slugify(project_id).replace('-', '_')}"


def load_manifest(project_id: str) -> dict[str, Any]:
    if project_id == "current":
        return current_project_manifest()
    manifest = read_json(manifest_path(project_id), None)
    if not manifest:
        raise FileNotFoundError(f"Project not found: {project_id}")
    return manifest


def save_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest["updated_at"] = utc_now()
    write_json(manifest_path(manifest["id"]), manifest)
    return manifest


def load_project_chunks(project_id: str) -> list[dict[str, Any]]:
    if project_id == "current":
        return read_json(LEGACY_CHUNKS_FILE, [])
    return read_json(chunks_path(project_id), [])


def load_existing_index_chunks(project_id: str) -> list[dict[str, Any]]:
    return read_json(existing_index_path(project_id), [])


def current_project_manifest() -> dict[str, Any]:
    chunks = read_json(LEGACY_CHUNKS_FILE, [])
    filtered_chunks = [chunk for chunk in chunks if not should_skip_document(chunk.get("document", ""))]
    index_chunks = [chunk for chunk in chunks if is_index_document_name(chunk.get("document", ""))]
    return {
        "id": "current",
        "name": "Cradle of the Empire",
        "created_at": "",
        "updated_at": "",
        "settings": {
            "ignore_existing_index": True,
            "consult_existing_index": False,
        },
        "source_files": [path.name for path in sorted(LEGACY_MANUSCRIPT_DIR.glob("*.md"))],
        "ignored_documents": sorted({chunk.get("document", "") for chunk in chunks if should_skip_document(chunk.get("document", ""))}),
        "existing_index_documents": sorted({chunk.get("document", "") for chunk in index_chunks}),
        "stats": {
            "source_files": len(list(LEGACY_MANUSCRIPT_DIR.glob("*.md"))),
            "chunks": len(chunks),
            "searchable_chunks": len(filtered_chunks),
            "existing_index_chunks": len(index_chunks),
        },
        "embedded": chroma_collection_count("current") > 0,
        "embedded_chunks": chroma_collection_count("current"),
        "is_builtin": True,
    }


def list_projects() -> list[dict[str, Any]]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    projects = [current_project_manifest()]
    for path in sorted(PROJECTS_DIR.glob("*/manifest.json")):
        try:
            projects.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return projects


def is_index_document_name(name: str) -> bool:
    return bool(INDEX_NAME_PATTERN.search(Path(name).name))


def is_index_document(path: Path, text: str) -> bool:
    if is_index_document_name(path.name):
        return True
    title = extract_chapter_title(text, fallback=clean_title_from_filename(path.stem)).strip().lower()
    return title in {"index", "index of names", "general index"}


def copy_upload_to_source(project_id: str, filename: str, content: bytes) -> list[str]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
        raise ValueError(f"Unsupported file type: {filename}")

    root = source_dir(project_id)
    root.mkdir(parents=True, exist_ok=True)
    stored_files: list[str] = []

    if suffix == ".zip":
        archive_path = root / safe_filename(filename)
        archive_path.write_bytes(content)
        extract_root = root / archive_path.stem
        extract_root.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                member_name = Path(member.filename)
                if member_name.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
                    continue
                destination = (extract_root / safe_filename(member_name.name)).resolve()
                if not str(destination).startswith(str(extract_root.resolve())):
                    continue
                with archive.open(member) as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                stored_files.append(str(destination.relative_to(root)))
        return stored_files

    destination = root / safe_filename(filename)
    destination.write_bytes(content)
    stored_files.append(destination.name)
    return stored_files


def safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    cleaned = re.sub(r"[^a-zA-Z0-9._() \-]+", "_", name)
    return cleaned or "upload.md"


def build_project(
    project_name: str,
    uploaded_files: list[tuple[str, bytes]],
    ignore_existing_index: bool,
    consult_existing_index: bool,
) -> dict[str, Any]:
    project_id = unique_project_id(project_name)
    root = project_dir(project_id)
    root.mkdir(parents=True, exist_ok=False)

    stored_files: list[str] = []
    for filename, content in uploaded_files:
        stored_files.extend(copy_upload_to_source(project_id, filename, content))

    chunks: list[dict[str, Any]] = []
    existing_index_chunks: list[dict[str, Any]] = []
    ignored_documents: set[str] = set()
    index_documents: set[str] = set()

    for file_path in sorted(source_dir(project_id).rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
            continue
        imported_document = import_document(file_path)
        manuscript_document, embedded_index_document = split_existing_index_section(imported_document)
        index_doc = is_index_document(file_path, imported_document.text)
        skip_doc = should_skip_document(file_path.name)
        embedded_index_chunks: list[dict[str, object]] = []

        if index_doc:
            index_documents.add(file_path.name)
            existing_index_chunks.extend(build_chunks_for_imported_document(imported_document))
            if ignore_existing_index:
                ignored_documents.add(file_path.name)
                continue

        if embedded_index_document:
            index_documents.add(embedded_index_document.document_name)
            embedded_index_chunks = build_chunks_for_imported_document(embedded_index_document)
            existing_index_chunks.extend(embedded_index_chunks)

        if skip_doc:
            ignored_documents.add(file_path.name)
            continue

        if manuscript_document:
            chunks.extend(build_chunks_for_imported_document(manuscript_document))

        if embedded_index_document:
            if ignore_existing_index:
                ignored_documents.add(embedded_index_document.document_name)
            else:
                chunks.extend(embedded_index_chunks)

    write_json(chunks_path(project_id), chunks)
    write_json(existing_index_path(project_id), existing_index_chunks)

    manifest = {
        "id": project_id,
        "name": project_name.strip() or project_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "settings": {
            "ignore_existing_index": bool(ignore_existing_index),
            "consult_existing_index": bool(consult_existing_index),
        },
        "source_files": stored_files,
        "ignored_documents": sorted(ignored_documents),
        "existing_index_documents": sorted(index_documents),
        "stats": {
            "source_files": len(stored_files),
            "chunks": len(chunks) + len(existing_index_chunks),
            "searchable_chunks": len(chunks),
            "existing_index_chunks": len(existing_index_chunks),
        },
        "embedded": False,
        "embedded_chunks": 0,
        "is_builtin": False,
    }
    return save_manifest(manifest)


def unique_project_id(project_name: str) -> str:
    base = slugify(project_name) or "project"
    candidate = base
    counter = 2
    while project_dir(candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    if should_trust_environment_proxy():
        return OpenAI(api_key=api_key)
    return OpenAI(api_key=api_key, http_client=httpx.Client(trust_env=False))


def should_trust_environment_proxy() -> bool:
    return os.getenv("ARCHIVIST_TRUST_ENV_PROXY", "").strip().lower() in {"1", "true", "yes", "on"}


def friendly_openai_error(exc: OpenAIError) -> str:
    error_name = exc.__class__.__name__
    if error_name in {"APIConnectionError", "APITimeoutError"}:
        return (
            "Could not reach OpenAI while building embeddings. "
            "Check your internet connection, VPN/firewall, and API access, then retry the search index build."
        )
    if error_name == "AuthenticationError":
        return "OpenAI authentication failed. Check OPENAI_API_KEY in the Archivist .env file."
    if error_name == "RateLimitError":
        return "OpenAI rate limit or quota was reached. Wait a bit or check project billing, then retry."
    return f"OpenAI request failed: {exc}"


def chroma_client() -> chromadb.PersistentClient:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def chroma_collection_count(project_id: str) -> int:
    try:
        collection = chroma_client().get_collection(name=collection_name(project_id))
        return int(collection.count())
    except Exception:
        return 0


def current_answer_corpus_integrity():
    """Run the full local, text-free identity preflight used by Answer Mode."""

    collection = chroma_client().get_collection(name=collection_name("current"))
    chunks = load_project_chunks("current")
    fixture_manifest = BASE_DIR / "fixtures" / "corpus_manifest.json"
    if not fixture_manifest.is_file():
        raise FileNotFoundError("The corpus manifest is unavailable.")
    corpus_manifest = read_json(fixture_manifest, None)
    corpus_manifest_sha256 = hashlib.sha256(fixture_manifest.read_bytes()).hexdigest()
    return preflight_answer_corpus(
        collection_handle=collection,
        chunks=chunks,
        corpus_manifest=corpus_manifest,
        corpus_manifest_sha256=corpus_manifest_sha256,
        require_store_identity=True,
    )


def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    try:
        response = tracked_embeddings_create(
            client,
            operation="corpus_embedding",
            model=EMBED_MODEL,
            input=texts,
        )
        return [item.embedding for item in response.data]
    except OpenAIError as exc:
        raise RuntimeError(friendly_openai_error(exc)) from exc


def embed_project(project_id: str) -> dict[str, Any]:
    manifest = load_manifest(project_id)
    chunks = [chunk for chunk in load_project_chunks(project_id) if not should_skip_document(chunk.get("document", ""))]
    if not chunks:
        raise RuntimeError("This project has no searchable chunks.")

    client = openai_client()
    store = chroma_client()
    name = collection_name(project_id)
    if project_id != "current":
        try:
            store.delete_collection(name=name)
        except Exception:
            pass
    collection = store.get_or_create_collection(name=name)

    batch_size = 50
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        texts = [chunk["text"] for chunk in batch]
        ids = [chunk["chunk_id"] for chunk in batch]
        embeddings = embed_texts(client, texts)
        collection.upsert(ids=ids, embeddings=embeddings, metadatas=batch)

    manifest["embedded"] = True
    manifest["embedded_chunks"] = len(chunks)
    return save_manifest(manifest)


def retrieve_project(project_id: str, query: str, n_results: int = 5) -> dict[str, Any]:
    collection = chroma_client().get_collection(name=collection_name(project_id))
    chunks_file = LEGACY_CHUNKS_FILE if project_id == "current" else chunks_path(project_id)
    corpus_trace: dict[str, object] = {
        "project_id": project_id,
        "collection_name": collection_name(project_id),
    }
    if chunks_file.is_file():
        corpus_trace["chunks_sha256"] = hashlib.sha256(chunks_file.read_bytes()).hexdigest()
    corpus_manifest = BASE_DIR / "fixtures" / "corpus_manifest.json"
    if project_id == "current" and corpus_manifest.is_file():
        corpus_trace["corpus_manifest_sha256"] = hashlib.sha256(
            corpus_manifest.read_bytes()
        ).hexdigest()
    return retrieve_from_collection(
        query,
        collection,
        load_project_chunks(project_id),
        n_results=n_results,
        embedding_client=openai_client(),
        corpus=corpus_trace,
    )


def retrieve_project_semantic(
    project_id: str,
    query: str,
    n_results: int = 5,
) -> dict[str, Any]:
    collection = chroma_client().get_collection(name=collection_name(project_id))
    return retrieve_semantic_from_collection(
        query,
        collection,
        n_results=n_results,
        embedding_client=openai_client(),
    )


def _truncate_conversation_text(value: object, limit: int) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1].rstrip()}\N{HORIZONTAL ELLIPSIS}"


def bounded_conversation_history(
    history: Sequence[Mapping[str, object]],
) -> list[dict[str, str]]:
    """Return recent dialogue context within a predictable request-size budget."""
    bounded: list[dict[str, str]] = []
    for turn in history[-MAX_CONVERSATION_CONTEXT_TURNS:]:
        question = _truncate_conversation_text(
            turn.get("question", ""),
            MAX_CONTEXT_QUESTION_CHARS,
        )
        answer = _truncate_conversation_text(
            turn.get("answer", ""),
            MAX_CONTEXT_ANSWER_CHARS,
        )
        if not question or not answer:
            continue
        bounded.append({"question": question, "answer": answer})

    while bounded and len(json.dumps(bounded, ensure_ascii=False)) > MAX_CONVERSATION_CONTEXT_CHARS:
        bounded.pop(0)
    return bounded


def build_conversation_query_input(
    question: str,
    history: Sequence[Mapping[str, object]],
) -> str:
    payload = {
        "prior_user_questions": [
            turn["question"]
            for turn in bounded_conversation_history(history)
        ],
        "current_question": question,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def resolve_conversation_turn(
    question: str,
    history: Sequence[Mapping[str, object]],
) -> ResolvedTurn:
    """Resolve follow-up intent without making dialogue manuscript evidence."""
    bounded_history = bounded_conversation_history(history)
    trusted_user_texts = tuple(
        dict.fromkeys(
            (
                *(
                    str(turn.get("question") or "")
                    for turn in bounded_history
                    if str(turn.get("question") or "").strip()
                ),
                question,
            )
        )
    )
    if not bounded_history:
        return ResolvedTurn(
            standalone_question=question,
            trusted_user_texts=trusted_user_texts,
        )

    try:
        response = tracked_responses_parse(
            without_automatic_retries(openai_client()),
            operation="followup_resolution",
            instructions=CONVERSATION_QUERY_INSTRUCTIONS,
            input=build_conversation_query_input(question, bounded_history),
            text_format=ResolvedTurn,
            max_output_tokens=MAX_RESOLVED_TURN_OUTPUT_TOKENS,
            **FOLLOWUP_RESOLVER_SETTINGS.responses_create_kwargs(),
        )
        parsed = getattr(response, "output_parsed", None)
        resolved = (
            parsed
            if isinstance(parsed, ResolvedTurn)
            else ResolvedTurn.model_validate(parsed)
        )
    except CostLimitExceeded:
        raise
    except Exception:
        return ResolvedTurn(
            standalone_question=question,
            trusted_user_texts=trusted_user_texts,
        )

    if (
        not resolved.standalone_question.strip()
        or len(resolved.standalone_question) > MAX_RESOLVED_QUERY_CHARS
    ):
        return ResolvedTurn(
            standalone_question=question,
            trusted_user_texts=trusted_user_texts,
        )
    return ResolvedTurn.model_validate(
        {
            **resolved.model_dump(),
            "trusted_user_texts": trusted_user_texts,
        }
    )


def resolve_conversation_query(
    question: str,
    history: Sequence[Mapping[str, object]],
) -> str:
    """Compatibility wrapper returning only the resolved standalone question."""
    return resolve_conversation_turn(question, history).standalone_question


def annotate_chapter_titles(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    current_document: str | None = None
    current_title: str | None = None
    for chunk in chunks:
        item = dict(chunk)
        document = str(item.get("document", ""))
        if document != current_document:
            current_document = document
            current_title = str(item.get("chapter_title") or "")
        detected = chapter_title_from_text(str(item.get("text", "")))
        if detected:
            current_title = detected
        item["chapter_title"] = current_title or item.get("chapter_title", "N/A")
        annotated.append(item)
    return annotated


def citation_label(chunk: dict[str, Any]) -> str:
    chapter = str(chunk.get("chapter_title") or "").strip()
    if not chapter or chapter == "N/A" or re.fullmatch(r"page\s+\d+", chapter, flags=re.IGNORECASE):
        chapter = Path(str(chunk.get("document") or "Manuscript")).stem
    if len(chapter) > 90:
        chapter = chapter[:87].rstrip() + "..."
    start = chunk.get("paragraph_start", "?")
    end = chunk.get("paragraph_end", "?")
    paragraph_label = f"¶{start}" if start == end else f"¶{start}–{end}"
    return f"{chapter}, {paragraph_label}"


def merge_adjacent_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge selected neighboring chunks after retrieval without changing stored RAG chunks."""
    if not chunks:
        return []

    ranked = list(enumerate(chunks))
    ranked.sort(key=lambda item: (
        str(item[1].get("document", "")),
        int(item[1].get("paragraph_start") or 0),
        item[0],
    ))
    merged: list[dict[str, Any]] = []

    for _, chunk in ranked:
        current = dict(chunk)
        current["chunk_ids"] = list(chunk.get("chunk_ids") or [str(chunk.get("chunk_id", "N/A"))])
        if not merged:
            merged.append(current)
            continue

        previous = merged[-1]
        same_document = previous.get("document") == current.get("document")
        same_chapter = previous.get("chapter_title") == current.get("chapter_title")
        previous_end = int(previous.get("paragraph_end") or 0)
        current_start = int(current.get("paragraph_start") or 0)
        neighboring = current_start <= previous_end + 1

        if not same_document or not same_chapter or not neighboring:
            merged.append(current)
            continue

        overlap = max(0, previous_end - current_start + 1)
        current_paragraphs = str(current.get("text", "")).split("\n\n")
        new_text = "\n\n".join(current_paragraphs[overlap:]).strip()
        if new_text:
            previous["text"] = f"{str(previous.get('text', '')).rstrip()}\n\n{new_text}"
        previous["paragraph_end"] = max(previous_end, int(current.get("paragraph_end") or previous_end))
        previous["chunk_ids"] = [*previous["chunk_ids"], *current["chunk_ids"]]
        if "source_numbers" in current:
            previous["source_numbers"] = [
                *previous.get("source_numbers", []),
                *current["source_numbers"],
            ]
    return merged


def _resolved_answer_style(
    *,
    archivist_mode: ArchivistMode | str,
    perspective: AnswerPerspective | str | None,
    historiographical_lens: HistoriographicalLens | str | None,
    voice: AnswerVoice | str | None,
    worldview: Worldview | str | None,
) -> tuple[ArchivistMode, HistoriographicalLens, AnswerVoice, Worldview]:
    selected_mode, lens, selected_voice, selected_worldview = (
        resolve_archivist_mode_settings(
            archivist_mode,
            historiographical_lens,
            voice,
            worldview,
        )
    )
    if perspective is None:
        return selected_mode, lens, selected_voice, selected_worldview

    legacy_lens, legacy_voice, legacy_worldview = settings_for_legacy_perspective(
        perspective
    )
    if (
        historiographical_lens is None
        or historiographical_lens == HistoriographicalLens.EVIDENCE_FIRST
    ):
        lens = legacy_lens
    if voice is None or voice == AnswerVoice.SCHOLARLY:
        selected_voice = legacy_voice
    if worldview is None or worldview == Worldview.NONE:
        selected_worldview = legacy_worldview
    return selected_mode, lens, selected_voice, selected_worldview


def answer_project_question_legacy(
    project_id: str,
    question: str,
    n_results: int = 5,
    perspective: AnswerPerspective | str | None = None,
    *,
    historiographical_lens: HistoriographicalLens | str | None = None,
    voice: AnswerVoice | str | None = None,
    worldview: Worldview | str | None = None,
    archivist_mode: ArchivistMode | str = ArchivistMode.ESSENTIAL,
    progress_callback: ProgressCallback | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    emit_progress(progress_callback, AnswerProgressStage.RETRIEVING_SOURCES)
    results = retrieve_project(project_id, question, n_results=n_results)
    emit_progress(progress_callback, AnswerProgressStage.PREPARING_CONTEXT)
    final_chunks = finalize_context_chunks(results, chunks=load_project_chunks(project_id))
    selected_mode, historiographical_lens, voice, worldview = _resolved_answer_style(
        archivist_mode=archivist_mode,
        perspective=perspective,
        historiographical_lens=historiographical_lens,
        voice=voice,
        worldview=worldview,
    )

    all_defaults = (
        selected_mode is ArchivistMode.ESSENTIAL
        and historiographical_lens == HistoriographicalLens.EVIDENCE_FIRST
        and voice == AnswerVoice.SCHOLARLY
        and worldview == Worldview.NONE
    )
    prompt = (
        build_answer_prompt(question, final_chunks)
        if all_defaults
        else build_interpretive_answer_prompt(
            question,
            final_chunks,
            historiographical_lens,
            voice,
            worldview,
            archivist_mode=selected_mode,
        )
    )
    emit_progress(progress_callback, AnswerProgressStage.GENERATING_ANSWER)
    response = tracked_responses_create(
        openai_client(),
        operation="answer_generation",
        input=prompt,
        **GENERATOR_SETTINGS.responses_create_kwargs(),
    )
    emit_progress(progress_callback, AnswerProgressStage.VALIDATING_ANSWER)
    return response.output_text, final_chunks


def answer_project_question_result(
    project_id: str,
    question: str,
    n_results: int = 5,
    perspective: AnswerPerspective | str | None = None,
    *,
    historiographical_lens: HistoriographicalLens | str | None = None,
    voice: AnswerVoice | str | None = None,
    worldview: Worldview | str | None = None,
    archivist_mode: ArchivistMode | str = ArchivistMode.ESSENTIAL,
    resolved_turn: ResolvedTurn | None = None,
    history: Sequence[Mapping[str, object]] = (),
    answer_strategy: AnswerStrategy | str = AnswerStrategy.RAG,
    progress_callback: ProgressCallback | None = None,
    checked_claim_callback: CheckedClaimCallback | None = None,
    stream_milestone_callback: ProviderStreamMilestoneCallback | None = None,
) -> AnswerModeResult:
    """Answer through the selected evidence scope's pipeline.

    Both strategies share this function's preflight and conversation resolution
    and return the same result shape; they diverge only at the one dispatch below.
    """
    answer_run_started_ns = perf_counter_ns()
    selected_strategy = AnswerStrategy(answer_strategy)
    selected_mode, historiographical_lens, voice, worldview = _resolved_answer_style(
        archivist_mode=archivist_mode,
        perspective=perspective,
        historiographical_lens=historiographical_lens,
        voice=voice,
        worldview=worldview,
    )

    # Custom projects do not yet persist the independent per-chunk identity
    # manifest required to certify a whole-corpus absence. Keep their established
    # behavior until project ingestion writes that snapshot.
    if project_id != "current":
        emit_progress(progress_callback, AnswerProgressStage.RESOLVING_QUESTION)
        turn = resolved_turn or resolve_conversation_turn(question, history)
        answer, final_chunks = answer_project_question_legacy(
            project_id,
            turn.standalone_question,
            n_results=n_results,
            historiographical_lens=historiographical_lens,
            voice=voice,
            worldview=worldview,
            archivist_mode=selected_mode,
            **(
                {"progress_callback": progress_callback}
                if progress_callback is not None
                else {}
            ),
        )
        result = AnswerModeResult(
            answer=answer,
            final_chunks=final_chunks,
            status="legacy_answer",
            plan=build_question_plan(turn),
            evidence_decision="legacy_unclassified",
            diagnostics={},
        )
        return _with_stage_timings(
            _with_archivist_mode_metadata(result, selected_mode),
            total=_elapsed_ms(answer_run_started_ns),
        )

    emit_progress(progress_callback, AnswerProgressStage.CHECKING_CORPUS)
    collection = chroma_client().get_collection(name=collection_name(project_id))
    chunks = load_project_chunks(project_id)
    chunks_file = (
        LEGACY_CHUNKS_FILE
        if project_id == "current"
        else chunks_path(project_id)
    )
    corpus_trace: dict[str, object] = {
        "project_id": project_id,
        "collection_name": collection_name(project_id),
    }
    if chunks_file.is_file():
        corpus_trace["chunks_sha256"] = hashlib.sha256(
            chunks_file.read_bytes()
        ).hexdigest()
    configuration = getattr(collection, "configuration", {})
    if isinstance(configuration, Mapping):
        hnsw = configuration.get("hnsw")
        if isinstance(hnsw, Mapping):
            corpus_trace["hnsw_space"] = str(hnsw.get("space") or "")

    corpus_manifest: Mapping[str, object] | None = None
    corpus_manifest_sha256: str | None = None
    fixture_manifest = BASE_DIR / "fixtures" / "corpus_manifest.json"
    if project_id == "current" and fixture_manifest.is_file():
        corpus_manifest = read_json(fixture_manifest, None)
        corpus_manifest_sha256 = hashlib.sha256(
            fixture_manifest.read_bytes()
        ).hexdigest()
        corpus_trace["corpus_manifest_sha256"] = corpus_manifest_sha256

    preflight_started_ns = perf_counter_ns()
    integrity = preflight_answer_corpus(
        collection_handle=collection,
        chunks=chunks,
        corpus_manifest=corpus_manifest,
        corpus_manifest_sha256=corpus_manifest_sha256,
        require_store_identity=True,
    )
    preflight_ms = _elapsed_ms(preflight_started_ns)
    resolution_started_ns = perf_counter_ns()
    emit_progress(progress_callback, AnswerProgressStage.RESOLVING_QUESTION)
    turn = resolved_turn
    if turn is None:
        turn = (
            resolve_conversation_turn(question, history)
            if integrity.passed
            else ResolvedTurn(
                standalone_question=question,
                trusted_user_texts=(question,),
            )
        )
    conversation_resolution_ms = _elapsed_ms(resolution_started_ns)
    client = openai_client() if integrity.passed else object()
    if selected_strategy is AnswerStrategy.FULL_CONTEXT:
        # n_results has no referent here: full context has no retrieval depth to
        # tune. It is ignored rather than rejected so an existing client need not
        # conditionally omit a field based on the reader's evidence scope.
        result = run_full_context_answer(
            resolved_turn=turn,
            collection_handle=collection,
            chunks=chunks,
            client=client,
            corpus_trace=corpus_trace,
            corpus_manifest=corpus_manifest,
            corpus_manifest_sha256=corpus_manifest_sha256,
            corpus_integrity=integrity,
            require_store_identity=True,
            historiographical_lens=historiographical_lens,
            voice=voice,
            worldview=worldview,
            archivist_mode=selected_mode,
            **(
                {"progress_callback": progress_callback}
                if progress_callback is not None
                else {}
            ),
            **(
                {"checked_claim_callback": checked_claim_callback}
                if checked_claim_callback is not None
                else {}
            ),
            **(
                {"stream_milestone_callback": stream_milestone_callback}
                if stream_milestone_callback is not None
                else {}
            ),
        )
    else:
        result = run_evidence_planned_answer(
            resolved_turn=turn,
            collection_handle=collection,
            chunks=chunks,
            client=client,
            n_results=n_results,
            corpus_trace=corpus_trace,
            corpus_manifest=corpus_manifest,
            corpus_manifest_sha256=corpus_manifest_sha256,
            corpus_integrity=integrity,
            require_store_identity=True,
            historiographical_lens=historiographical_lens,
            voice=voice,
            worldview=worldview,
            archivist_mode=selected_mode,
            **(
                {"progress_callback": progress_callback}
                if progress_callback is not None
                else {}
            ),
            **(
                {"checked_claim_callback": checked_claim_callback}
                if checked_claim_callback is not None
                else {}
            ),
            **(
                {"stream_milestone_callback": stream_milestone_callback}
                if stream_milestone_callback is not None
                else {}
            ),
        )
    return _with_stage_timings(
        _with_archivist_mode_metadata(result, selected_mode),
        preflight=preflight_ms,
        conversation_resolution=conversation_resolution_ms,
        total=_elapsed_ms(answer_run_started_ns),
    )


def answer_project_question(
    project_id: str,
    question: str,
    n_results: int = 5,
    perspective: AnswerPerspective | str | None = None,
    *,
    historiographical_lens: HistoriographicalLens | str | None = None,
    voice: AnswerVoice | str | None = None,
    worldview: Worldview | str | None = None,
    archivist_mode: ArchivistMode | str = ArchivistMode.ESSENTIAL,
    resolved_turn: ResolvedTurn | None = None,
    history: Sequence[Mapping[str, object]] = (),
) -> tuple[str, list[dict[str, Any]]]:
    """Compatibility wrapper for callers that only need prose and sources."""
    result = answer_project_question_result(
        project_id,
        question,
        n_results=n_results,
        perspective=perspective,
        historiographical_lens=historiographical_lens,
        voice=voice,
        worldview=worldview,
        archivist_mode=archivist_mode,
        resolved_turn=resolved_turn,
        history=history,
    )
    return result.answer, result.final_chunks


def search_existing_index(project_id: str, term: str, limit: int = 8) -> list[dict[str, Any]]:
    index_chunks = load_existing_index_chunks(project_id)
    matches = find_exact_match_chunks(term, index_chunks, empty_term_matches=False)
    return matches[:limit]


def generate_index_entry(project_id: str, term: str, consult_existing_index: bool) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    semantic_results = retrieve_project_semantic(project_id, term, n_results=5)
    chunks = load_project_chunks(project_id)
    final_chunks = finalize_index_context(
        term,
        semantic_results,
        chunks=chunks,
        empty_term_matches=False,
    )
    existing_index_chunks = search_existing_index(project_id, term) if consult_existing_index else []
    prompt = build_index_prompt_web(term, final_chunks, existing_index_chunks)
    response = tracked_responses_create(
        openai_client(),
        operation="index_generation",
        input=prompt,
        **GENERATOR_SETTINGS.responses_create_kwargs(),
    )
    return response.output_text, final_chunks, existing_index_chunks


def candidate_terms(project_id: str, limit: int = 50) -> list[dict[str, Any]]:
    chunks = load_project_chunks(project_id)
    counter: Counter[str] = Counter()
    stop = {
        "The", "A", "An", "And", "But", "For", "This", "That", "These", "Those",
        "In", "On", "At", "By", "From", "As", "It", "Its", "They", "Their",
        "Chapter", "Appendix", "Introduction",
    }
    phrase_pattern = re.compile(r"\b([A-Z][A-Za-z]+(?:\s+(?:of|the|and|de|du|[A-Z][A-Za-z]+)){0,4})\b")
    for chunk in chunks:
        if should_skip_document(chunk.get("document", "")):
            continue
        for match in phrase_pattern.finditer(chunk.get("text", "")):
            phrase = re.sub(r"\s+", " ", match.group(1)).strip()
            first = phrase.split()[0]
            if first in stop or len(phrase) < 4:
                continue
            counter[phrase] += 1
    return [{"term": term, "count": count} for term, count in counter.most_common(limit)]


def source_payload(chunks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    sources = []
    for i, chunk in enumerate(chunks, start=1):
        sources.append({
            "source_number": i,
            "citation_label": citation_label(chunk),
            "document": chunk.get("document", "N/A"),
            "chapter_title": chunk.get("chapter_title", "N/A"),
            "chunk_id": chunk.get("chunk_id", "N/A"),
            "chunk_ids": [chunk.get("chunk_id", "N/A")],
            "paragraph_start": chunk.get("paragraph_start"),
            "paragraph_end": chunk.get("paragraph_end"),
            "text": chunk.get("text", ""),
        })

    numbered_chunks = [
        {**chunk, "source_numbers": [i]}
        for i, chunk in enumerate(chunks, start=1)
    ]
    display_groups = []
    for group in merge_adjacent_chunks(numbered_chunks):
        numbers = group["source_numbers"]
        display_groups.append({
            "source_numbers": numbers,
            "text": group.get("text", ""),
            "citation_labels": [sources[number - 1]["citation_label"] for number in numbers],
        })
    return {"sources": sources, "display_groups": display_groups}
