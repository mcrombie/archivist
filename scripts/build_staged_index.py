"""Build and verify a new Chroma index without modifying the live index.

The builder deliberately requires a fresh target directory.  A completed build
updates only the supplied corpus manifest, and only after the persisted
collection has been read back and verified against the chunks file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import struct
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from costs import UsageLedger, tracked_embeddings_create, usage_scope  # noqa: E402
from filters import SKIP_FILES, should_skip_document  # noqa: E402


MANIFEST_SCHEMA = "archivist.corpus_manifest/1"
EMBEDDING_MODEL = "text-embedding-3-small"
HNSW_SPACE = "l2"
DEFAULT_COLLECTION = "manuscript"
DEFAULT_BATCH_SIZE = 50
LIVE_CHROMA_DIR = (ROOT / "chroma_db").resolve()
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")

ChromaClientFactory = Callable[..., object]


class StagedIndexError(ValueError):
    """Raised before or after a build when a safety invariant does not hold."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_json(path: Path, expected_type: type) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StagedIndexError(f"Could not read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, expected_type):
        raise StagedIndexError(
            f"{path} must contain a JSON {expected_type.__name__}, "
            f"not {type(value).__name__}"
        )
    return value


def _resolved_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def validate_fresh_target(target_dir: Path) -> None:
    """Reject the live store, its descendants, and any target with existing content."""
    target = target_dir.resolve()
    live = LIVE_CHROMA_DIR
    target_key = _resolved_key(target)
    live_key = _resolved_key(live)
    if (
        target_key == live_key
        or live_key.startswith(target_key + os.sep)
        or target_key.startswith(live_key + os.sep)
    ):
        raise StagedIndexError(
            f"Refusing target {target}: it overlaps the live Chroma directory {live}"
        )
    if target.exists():
        if not target.is_dir():
            raise StagedIndexError(f"Target already exists and is not a directory: {target}")
        if any(target.iterdir()):
            raise StagedIndexError(f"Target directory must be empty: {target}")


def _chunk_by_id(chunks: Sequence[object], *, source: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for position, raw_chunk in enumerate(chunks):
        if not isinstance(raw_chunk, dict):
            raise StagedIndexError(f"{source} entry {position} must be an object")
        chunk = raw_chunk
        chunk_id = chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise StagedIndexError(f"{source} entry {position} has no valid chunk_id")
        if chunk_id in indexed:
            raise StagedIndexError(f"{source} contains duplicate chunk_id {chunk_id!r}")
        indexed[chunk_id] = chunk
    return indexed


def _required_mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StagedIndexError(f"Manifest {field} must be an object")
    return value


def _require_fields(value: Mapping[str, Any], fields: set[str], *, label: str) -> None:
    missing = fields.difference(value)
    if missing:
        raise StagedIndexError(
            f"{label} is missing required fields: {', '.join(sorted(missing))}"
        )


def _is_int(value: object, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _validate_manifest_documents(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw_documents = manifest.get("documents")
    if not isinstance(raw_documents, list) or not raw_documents:
        raise StagedIndexError("Manifest documents must be a non-empty list")

    required_fields = {
        "filename",
        "sha256",
        "paragraph_count",
        "chunk_count",
        "chapter_title",
    }
    documents: dict[str, dict[str, Any]] = {}
    for position, raw_document in enumerate(raw_documents):
        if not isinstance(raw_document, dict):
            raise StagedIndexError(f"Manifest document {position} must be an object")
        _require_fields(raw_document, required_fields, label=f"Manifest document {position}")
        filename = raw_document["filename"]
        if not isinstance(filename, str) or not filename:
            raise StagedIndexError(f"Manifest document {position} has an invalid filename")
        if filename in documents:
            raise StagedIndexError(f"Manifest contains duplicate document {filename!r}")
        if not _valid_sha256(raw_document["sha256"]):
            raise StagedIndexError(f"Manifest document {filename!r} has an invalid SHA-256")
        if not _is_int(raw_document["paragraph_count"]):
            raise StagedIndexError(
                f"Manifest document {filename!r} has an invalid paragraph_count"
            )
        if not _is_int(raw_document["chunk_count"]):
            raise StagedIndexError(
                f"Manifest document {filename!r} has an invalid chunk_count"
            )
        if not isinstance(raw_document["chapter_title"], str):
            raise StagedIndexError(
                f"Manifest document {filename!r} has an invalid chapter_title"
            )
        documents[filename] = raw_document
    return documents


def _validate_manifest_ingest(manifest: Mapping[str, Any]) -> None:
    ingest = _required_mapping(manifest.get("ingest"), field="ingest")
    _require_fields(
        ingest,
        {
            "paragraphs_per_chunk",
            "paragraph_overlap",
            "ingest_commit",
            "skip_files",
        },
        label="Manifest ingest",
    )
    paragraphs_per_chunk = ingest["paragraphs_per_chunk"]
    paragraph_overlap = ingest["paragraph_overlap"]
    if not _is_int(paragraphs_per_chunk, minimum=1):
        raise StagedIndexError("Manifest ingest paragraphs_per_chunk must be positive")
    if (
        not _is_int(paragraph_overlap)
        or int(paragraph_overlap) >= int(paragraphs_per_chunk)
    ):
        raise StagedIndexError(
            "Manifest ingest paragraph_overlap must be non-negative and smaller "
            "than paragraphs_per_chunk"
        )
    if not isinstance(ingest["ingest_commit"], str) or not ingest["ingest_commit"]:
        raise StagedIndexError("Manifest ingest ingest_commit must be a non-empty string")
    skip_files = ingest["skip_files"]
    if (
        not isinstance(skip_files, list)
        or any(not isinstance(filename, str) or not filename for filename in skip_files)
        or len(skip_files) != len(set(skip_files))
        or set(skip_files) != set(SKIP_FILES)
    ):
        raise StagedIndexError(
            "Manifest ingest skip_files must exactly match the current SKIP_FILES"
        )


def _validate_manifest_store(
    manifest: Mapping[str, Any],
    *,
    collection_name: str,
) -> dict[str, Any]:
    store = _required_mapping(manifest.get("store"), field="store")
    _require_fields(
        store,
        {
            "hnsw_space",
            "embedding_model",
            "collection_name",
            "embedded_chunk_count",
        },
        label="Manifest store",
    )
    for field in ("hnsw_space", "embedding_model", "collection_name"):
        if not isinstance(store[field], str) or not store[field]:
            raise StagedIndexError(f"Manifest store {field} must be a non-empty string")
    if not _is_int(store["embedded_chunk_count"]):
        raise StagedIndexError(
            "Manifest store embedded_chunk_count must be a non-negative integer"
        )
    if store["hnsw_space"] != HNSW_SPACE:
        raise StagedIndexError(f"Manifest store hnsw_space must be {HNSW_SPACE!r}")
    if store["embedding_model"] != EMBEDDING_MODEL:
        raise StagedIndexError(
            f"Manifest store embedding_model must be {EMBEDDING_MODEL!r}"
        )
    if store["collection_name"] != collection_name:
        raise StagedIndexError(
            "Manifest store collection_name does not match the requested collection"
        )
    return store


def _validate_extraction_counts(
    manifest: Mapping[str, Any],
    documents: Mapping[str, Mapping[str, Any]],
    chunks: Sequence[Mapping[str, Any]],
) -> None:
    extraction = _required_mapping(manifest.get("extraction"), field="extraction")
    required = {
        "document_count",
        "paragraph_count",
        "chunk_count",
        "searchable_chunk_count",
        "skipped_document_count",
    }
    _require_fields(extraction, required, label="Manifest extraction")
    for field in required:
        if not _is_int(extraction[field]):
            raise StagedIndexError(
                f"Manifest extraction {field} must be a non-negative integer"
            )
    expected = {
        "document_count": len(documents),
        "paragraph_count": sum(int(item["paragraph_count"]) for item in documents.values()),
        "chunk_count": len(chunks),
        "searchable_chunk_count": sum(
            not should_skip_document(str(chunk["document"])) for chunk in chunks
        ),
        "skipped_document_count": len(
            {
                str(chunk["document"])
                for chunk in chunks
                if should_skip_document(str(chunk["document"]))
            }
        ),
    }
    for field, expected_value in expected.items():
        if extraction[field] != expected_value:
            raise StagedIndexError(
                f"Manifest extraction {field} mismatch: "
                f"expected {expected_value}, got {extraction[field]}"
            )


def validate_manifest(
    chunks_path: Path,
    chunks: list[object],
    manifest: dict[str, Any],
    *,
    collection_name: str,
) -> tuple[list[dict[str, Any]], str]:
    """Validate the manifest schema, relationships, and every chunk digest."""
    if manifest.get("manifest_schema") != MANIFEST_SCHEMA:
        raise StagedIndexError(
            f"Manifest manifest_schema must be exactly {MANIFEST_SCHEMA!r}"
        )
    documents = _validate_manifest_documents(manifest)
    _validate_manifest_ingest(manifest)
    store = _validate_manifest_store(manifest, collection_name=collection_name)

    actual_chunks_sha = sha256_file(chunks_path)
    expected_chunks_sha = manifest.get("chunks_sha256")
    if not _valid_sha256(expected_chunks_sha):
        raise StagedIndexError("Manifest is missing a valid chunks_sha256")
    assert isinstance(expected_chunks_sha, str)
    if expected_chunks_sha.casefold() != actual_chunks_sha:
        raise StagedIndexError(
            "Manifest/chunks SHA mismatch: "
            f"manifest={expected_chunks_sha}, actual={actual_chunks_sha}"
        )

    manifest_chunks = manifest.get("chunks")
    if not isinstance(manifest_chunks, list):
        raise StagedIndexError("Manifest is missing its chunks list")

    chunk_index = _chunk_by_id(chunks, source="Chunks file")
    manifest_index = _chunk_by_id(manifest_chunks, source="Manifest chunks")
    chunk_ids = set(chunk_index)
    manifest_ids = set(manifest_index)
    if manifest_ids != chunk_ids:
        missing = sorted(chunk_ids - manifest_ids)
        unexpected = sorted(manifest_ids - chunk_ids)
        raise StagedIndexError(
            "Manifest/chunks ID mismatch "
            f"(missing from manifest={missing[:5]}, unexpected={unexpected[:5]})"
        )

    chunk_counts = {filename: 0 for filename in documents}
    comparison_fields = (
        "document",
        "paragraph_start",
        "paragraph_end",
        "char_count",
    )
    for chunk_id, chunk in chunk_index.items():
        _require_fields(
            chunk,
            {
                "document",
                "chapter_title",
                "chunk_id",
                "paragraph_start",
                "paragraph_end",
                "text",
            },
            label=f"Chunk {chunk_id!r}",
        )
        document_name = chunk["document"]
        if not isinstance(document_name, str) or document_name not in documents:
            raise StagedIndexError(
                f"Chunk {chunk_id!r} references unknown document {document_name!r}"
            )
        document = documents[document_name]
        chunk_counts[document_name] += 1
        expected_chunk_id = (
            f"{Path(document_name).stem}_{chunk_counts[document_name]:03}"
        )
        if chunk_id != expected_chunk_id:
            raise StagedIndexError(
                f"Chunk ID contract mismatch: expected {expected_chunk_id!r}, "
                f"got {chunk_id!r}"
            )
        if (
            not isinstance(chunk["chapter_title"], str)
            or chunk["chapter_title"] != document["chapter_title"]
        ):
            raise StagedIndexError(
                f"Chunk {chunk_id!r} chapter title does not match its document"
            )
        start = chunk["paragraph_start"]
        end = chunk["paragraph_end"]
        if (
            not _is_int(start, minimum=1)
            or not _is_int(end, minimum=1)
            or int(end) < int(start)
            or int(end) > int(document["paragraph_count"])
        ):
            raise StagedIndexError(f"Chunk {chunk_id!r} has invalid paragraph bounds")

        text = chunk.get("text")
        if not isinstance(text, str):
            raise StagedIndexError(f"Chunk {chunk_id!r} has no string text")
        manifest_chunk = manifest_index[chunk_id]
        _require_fields(
            manifest_chunk,
            {
                "chunk_id",
                "document",
                "paragraph_start",
                "paragraph_end",
                "text_sha256",
                "char_count",
            },
            label=f"Manifest chunk {chunk_id!r}",
        )
        if (
            not isinstance(manifest_chunk["document"], str)
            or not _is_int(manifest_chunk["paragraph_start"], minimum=1)
            or not _is_int(manifest_chunk["paragraph_end"], minimum=1)
            or not _is_int(manifest_chunk["char_count"])
        ):
            raise StagedIndexError(
                f"Manifest chunk {chunk_id!r} has invalid field types"
            )
        expected_text_sha = manifest_chunk.get("text_sha256")
        actual_text_sha = sha256_text(text)
        if (
            not _valid_sha256(expected_text_sha)
            or str(expected_text_sha).casefold() != actual_text_sha
        ):
            raise StagedIndexError(
                f"Manifest/chunks text SHA mismatch for chunk {chunk_id!r}"
            )
        expected_values = {
            "document": chunk.get("document"),
            "paragraph_start": chunk.get("paragraph_start"),
            "paragraph_end": chunk.get("paragraph_end"),
            "char_count": len(text),
        }
        for field in comparison_fields:
            if manifest_chunk.get(field) != expected_values[field]:
                raise StagedIndexError(
                    f"Manifest/chunks {field} mismatch for chunk {chunk_id!r}"
                )

    for filename, document in documents.items():
        if chunk_counts[filename] != document["chunk_count"]:
            raise StagedIndexError(
                f"Manifest document {filename!r} chunk_count mismatch: "
                f"expected {chunk_counts[filename]}, got {document['chunk_count']}"
            )

    _validate_extraction_counts(
        manifest,
        documents,
        [chunk for chunk in chunk_index.values()],
    )
    filtered = [
        chunk
        for chunk in chunk_index.values()
        if not should_skip_document(str(chunk.get("document", "")))
    ]
    if not filtered:
        raise StagedIndexError("No retrieval-eligible chunks remain after filtering")
    if int(store["embedded_chunk_count"]) > len(filtered):
        raise StagedIndexError(
            "Manifest store embedded_chunk_count exceeds retrieval-eligible chunks"
        )
    return filtered, actual_chunks_sha


def metadata_for_chunk(chunk: Mapping[str, Any]) -> dict[str, str | int | float | bool]:
    """Return metadata that Chroma can round-trip without changing its meaning."""
    metadata: dict[str, str | int | float | bool] = {}
    for key, value in chunk.items():
        if not isinstance(key, str):
            raise StagedIndexError("Chunk metadata keys must be strings")
        if not isinstance(value, (str, int, float, bool)) or value is None:
            raise StagedIndexError(
                f"Chunk {chunk.get('chunk_id')!r} has unsupported metadata value for {key!r}"
            )
        if isinstance(value, float) and not math.isfinite(value):
            raise StagedIndexError(
                f"Chunk {chunk.get('chunk_id')!r} has non-finite metadata for {key!r}"
            )
        metadata[key] = value
    return metadata


def _object_value(value: object, field: str) -> object:
    return value.get(field) if isinstance(value, Mapping) else getattr(value, field, None)


def _sequence_values(value: object, *, label: str) -> list[object]:
    if value is None or isinstance(value, (str, bytes, Mapping)):
        raise StagedIndexError(f"{label} is not a sequence")
    try:
        return list(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise StagedIndexError(f"{label} is not a sequence") from exc


def _float32_vector(vector: Sequence[float]) -> tuple[float, ...]:
    try:
        return tuple(
            struct.unpack("<f", struct.pack("<f", float(value)))[0] for value in vector
        )
    except (OverflowError, struct.error, TypeError, ValueError) as exc:
        raise StagedIndexError("Embedding vector cannot be represented as finite float32") from exc


def _embedding_vectors(
    response: object,
    expected_count: int,
    *,
    expected_dimension: int | None,
) -> tuple[list[list[float]], int]:
    data = _object_value(response, "data")
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes)):
        raise StagedIndexError("Embedding response did not contain a data sequence")
    if len(data) != expected_count:
        raise StagedIndexError(
            f"Embedding response count mismatch: expected {expected_count}, got {len(data)}"
        )

    vectors: list[list[float]] = []
    dimensions: set[int] = set()
    for position, item in enumerate(data):
        index = _object_value(item, "index")
        if not isinstance(index, int) or isinstance(index, bool) or index != position:
            raise StagedIndexError(
                "Embedding response indices are missing, duplicated, or out of request order"
            )
        raw_vector = _object_value(item, "embedding")
        values = _sequence_values(
            raw_vector,
            label=f"Embedding response vector {position}",
        )
        try:
            vector = [float(value) for value in values]
        except (TypeError, ValueError) as exc:
            raise StagedIndexError(
                f"Embedding response vector {position} contains a non-number"
            ) from exc
        if not vector or any(not math.isfinite(value) for value in vector):
            raise StagedIndexError(
                f"Embedding response vector {position} must be non-empty and finite"
            )
        _float32_vector(vector)
        vectors.append(vector)
        dimensions.add(len(vector))
    if len(dimensions) != 1:
        raise StagedIndexError("Embedding response vectors have inconsistent dimensions")
    dimension = dimensions.pop()
    if expected_dimension is not None and dimension != expected_dimension:
        raise StagedIndexError(
            "Embedding vector dimension changed between batches: "
            f"expected {expected_dimension}, got {dimension}"
        )
    return vectors, dimension


def _verify_collection(
    collection: object,
    expected_metadata: Mapping[str, dict[str, str | int | float | bool]],
    expected_embeddings: Mapping[str, tuple[float, ...]],
    collection_metadata: Mapping[str, str],
) -> None:
    count = collection.count()
    if not isinstance(count, int) or isinstance(count, bool) or count != len(
        expected_metadata
    ):
        raise StagedIndexError(
            "Persisted collection count mismatch: "
            f"expected {len(expected_metadata)}, got {count}"
        )
    records = collection.get(include=["embeddings", "documents", "metadatas"])
    if not isinstance(records, Mapping):
        raise StagedIndexError("Persisted collection returned an invalid result")
    ids = _sequence_values(records.get("ids"), label="Persisted collection IDs")
    metadatas = _sequence_values(
        records.get("metadatas"),
        label="Persisted collection metadata",
    )
    embeddings = _sequence_values(
        records.get("embeddings"),
        label="Persisted collection embeddings",
    )
    raw_documents = records.get("documents")
    documents = (
        [None] * count
        if raw_documents is None
        else _sequence_values(raw_documents, label="Persisted collection documents")
    )
    if not all(isinstance(chunk_id, str) and chunk_id for chunk_id in ids):
        raise StagedIndexError("Persisted collection contains an invalid ID")
    if len(ids) != len(set(ids)):
        raise StagedIndexError("Persisted collection contains duplicate IDs")
    if set(ids) != set(expected_metadata):
        raise StagedIndexError("Persisted collection ID set does not match filtered chunks")
    for label, values in (
        ("metadata", metadatas),
        ("embeddings", embeddings),
        ("documents", documents),
    ):
        if len(values) != len(ids):
            raise StagedIndexError(
                f"Persisted collection {label} count does not match its IDs"
            )

    actual_dimensions: set[int] = set()
    for chunk_id, stored_metadata, raw_embedding, document in zip(
        ids,
        metadatas,
        embeddings,
        documents,
        strict=True,
    ):
        assert isinstance(chunk_id, str)
        if not isinstance(stored_metadata, Mapping):
            raise StagedIndexError(f"Persisted metadata is missing for chunk {chunk_id!r}")
        actual = dict(stored_metadata)
        wanted = expected_metadata[chunk_id]
        if actual != wanted:
            raise StagedIndexError(
                f"Persisted metadata does not match source chunk {chunk_id!r}"
            )
        if sha256_text(str(actual["text"])) != sha256_text(str(wanted["text"])):
            raise StagedIndexError(f"Persisted text hash mismatch for chunk {chunk_id!r}")
        if document is not None:
            raise StagedIndexError(
                f"Persisted document payload was unexpectedly set for chunk {chunk_id!r}"
            )
        raw_vector = _sequence_values(
            raw_embedding,
            label=f"Persisted embedding for chunk {chunk_id!r}",
        )
        try:
            vector = [float(value) for value in raw_vector]
        except (TypeError, ValueError) as exc:
            raise StagedIndexError(
                f"Persisted embedding is invalid for chunk {chunk_id!r}"
            ) from exc
        if not vector or any(not math.isfinite(value) for value in vector):
            raise StagedIndexError(
                f"Persisted embedding is invalid for chunk {chunk_id!r}"
            )
        normalized_vector = _float32_vector(vector)
        actual_dimensions.add(len(normalized_vector))
        if normalized_vector != expected_embeddings[chunk_id]:
            raise StagedIndexError(
                f"Persisted embedding does not match source response for chunk {chunk_id!r}"
            )
    if len(actual_dimensions) != 1:
        raise StagedIndexError("Persisted embeddings have inconsistent dimensions")

    actual_collection_metadata = getattr(collection, "metadata", None)
    if (
        not isinstance(actual_collection_metadata, Mapping)
        or dict(actual_collection_metadata) != dict(collection_metadata)
    ):
        raise StagedIndexError("Persisted collection metadata is unavailable")

    configuration = getattr(collection, "configuration", None)
    hnsw_configuration = (
        configuration.get("hnsw") if isinstance(configuration, Mapping) else None
    )
    if (
        not isinstance(hnsw_configuration, Mapping)
        or hnsw_configuration.get("space") != HNSW_SPACE
    ):
        raise StagedIndexError(
            f"Persisted collection HNSW configuration is not {HNSW_SPACE!r}"
        )


def _write_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _close_client(client: object | None) -> None:
    if client is None:
        return
    close = getattr(client, "close", None)
    if callable(close):
        close()


def _budget_state(ledger: object) -> Mapping[str, Any]:
    try:
        state = ledger.budget_state()
    except Exception as exc:
        raise StagedIndexError(
            f"Could not read the local API cost budget before embedding: {exc}"
        ) from exc
    if not isinstance(state, Mapping):
        raise StagedIndexError("Local API cost budget returned an invalid state")
    return state


def _enforce_hard_budget(ledger: object, *, allow_over_budget: bool) -> None:
    state = _budget_state(ledger)
    if (
        bool(state.get("hard_limit_enabled"))
        and bool(state.get("exceeded"))
        and not allow_over_budget
    ):
        raise StagedIndexError(
            "The local hard monthly API cost limit has been reached. "
            "No embedding request was sent. Re-run with --allow-over-budget "
            "only if you intentionally approve this index build."
        )


def _preflight_usage_ledger(ledger: object, *, allow_over_budget: bool) -> None:
    """Prove the ledger is writable, then enforce its current hard limit."""
    try:
        settings = ledger.get_settings()
        if not isinstance(settings, Mapping):
            raise TypeError("settings response is not an object")
        ledger.update_settings(
            monthly_budget_usd=settings.get("monthly_budget_usd"),
            warning_threshold_percent=settings.get("warning_threshold_percent"),
            hard_limit_enabled=settings.get("hard_limit_enabled"),
        )
    except Exception as exc:
        raise StagedIndexError(
            f"Could not preflight the writable local API usage ledger: {exc}"
        ) from exc
    _enforce_hard_budget(ledger, allow_over_budget=allow_over_budget)


def build_staged_index(
    chunks_path: str | Path,
    manifest_path: str | Path,
    target_dir: str | Path,
    *,
    collection_name: str = DEFAULT_COLLECTION,
    batch_size: int = DEFAULT_BATCH_SIZE,
    allow_over_budget: bool = False,
    openai_client: object | None = None,
    chroma_client_factory: ChromaClientFactory | None = None,
    usage_ledger: object | None = None,
) -> int:
    """Build, read back, verify, and then record a fresh staged index."""
    chunks_file = Path(chunks_path).resolve()
    manifest_file = Path(manifest_path).resolve()
    target = Path(target_dir).resolve()
    if batch_size <= 0:
        raise StagedIndexError("batch_size must be greater than zero")
    if not collection_name.strip():
        raise StagedIndexError("collection_name must not be empty")

    validate_fresh_target(target)
    chunks = _load_json(chunks_file, list)
    manifest = _load_json(manifest_file, dict)
    filtered_chunks, chunks_sha = validate_manifest(
        chunks_file,
        chunks,
        manifest,
        collection_name=collection_name,
    )
    store_manifest = manifest["store"]
    assert isinstance(store_manifest, dict)
    expected_metadata = {
        str(chunk["chunk_id"]): metadata_for_chunk(chunk) for chunk in filtered_chunks
    }

    load_dotenv(dotenv_path=ROOT / ".env", override=False)
    ledger = usage_ledger or UsageLedger()
    _preflight_usage_ledger(ledger, allow_over_budget=allow_over_budget)

    if openai_client is None:
        from openai import OpenAI

        openai_client = OpenAI()
    if chroma_client_factory is None:
        import chromadb

        chroma_client_factory = chromadb.PersistentClient

    collection_metadata = {
        "hnsw:space": HNSW_SPACE,
        "embedding_model": EMBEDDING_MODEL,
        "chunks_sha256": chunks_sha,
    }
    expected_embeddings: dict[str, tuple[float, ...]] = {}
    embedding_dimension: int | None = None
    write_store: object | None = None
    try:
        write_store = chroma_client_factory(path=str(target))
        collection = write_store.create_collection(
            name=collection_name,
            metadata=collection_metadata,
            embedding_function=None,
        )

        with usage_scope(project_id="current"):
            for start in range(0, len(filtered_chunks), batch_size):
                _enforce_hard_budget(
                    ledger,
                    allow_over_budget=allow_over_budget,
                )
                batch = filtered_chunks[start : start + batch_size]
                texts = [str(chunk["text"]) for chunk in batch]
                response = tracked_embeddings_create(
                    openai_client,
                    operation="corpus_embedding",
                    model=EMBEDDING_MODEL,
                    input=texts,
                )
                embeddings, embedding_dimension = _embedding_vectors(
                    response,
                    len(batch),
                    expected_dimension=embedding_dimension,
                )
                batch_ids = [str(chunk["chunk_id"]) for chunk in batch]
                for chunk_id, embedding in zip(batch_ids, embeddings, strict=True):
                    expected_embeddings[chunk_id] = _float32_vector(embedding)
                collection.add(
                    ids=batch_ids,
                    embeddings=embeddings,
                    metadatas=[
                        expected_metadata[str(chunk["chunk_id"])] for chunk in batch
                    ],
                )
    finally:
        _close_client(write_store)

    read_store: object | None = None
    try:
        read_store = chroma_client_factory(path=str(target))
        persisted_collection = read_store.get_collection(
            name=collection_name,
            embedding_function=None,
        )
        _verify_collection(
            persisted_collection,
            expected_metadata,
            expected_embeddings,
            collection_metadata,
        )
    finally:
        _close_client(read_store)

    store_manifest.update(
        {
            "hnsw_space": HNSW_SPACE,
            "embedding_model": EMBEDDING_MODEL,
            "collection_name": collection_name,
            "embedded_chunk_count": len(filtered_chunks),
        }
    )
    _write_manifest(manifest_file, manifest)
    return len(filtered_chunks)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and verify a fresh, staged Chroma corpus index."
    )
    parser.add_argument("chunks_json", type=Path)
    parser.add_argument("manifest_json", type=Path)
    parser.add_argument("target_chroma_dir", type=Path)
    parser.add_argument(
        "--collection-name",
        default=DEFAULT_COLLECTION,
        help=f"Chroma collection name (default: {DEFAULT_COLLECTION})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Embedding request batch size (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--allow-over-budget",
        action="store_true",
        help=(
            "Explicitly override Archivist's local hard monthly cost limit for "
            "this build."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    embedded_count = build_staged_index(
        args.chunks_json,
        args.manifest_json,
        args.target_chroma_dir,
        collection_name=args.collection_name,
        batch_size=args.batch_size,
        allow_over_budget=args.allow_over_budget,
    )
    print(f"Built and verified {embedded_count} chunks in {args.target_chroma_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
