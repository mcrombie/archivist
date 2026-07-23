"""Assemble a promotion-ready Chroma store without modifying either input store.

The live-sized source store is copied in full so project-specific collections
survive promotion.  Only the copied ``manuscript`` collection is replaced,
using already-computed vectors from a separately verified staged store.  This
script never imports or calls OpenAI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple


ROOT = Path(__file__).resolve().parents[1]
LIVE_CHROMA_DIR = (ROOT / "chroma_db").resolve()
DEFAULT_COLLECTION = "manuscript"
DEFAULT_BATCH_SIZE = 100

ChromaClientFactory = Callable[..., object]


class PromotionIndexError(ValueError):
    """Raised when an input, copy, or post-copy invariant is not satisfied."""


class StoredRecord(NamedTuple):
    """A Chroma record in a representation with deterministic comparisons."""

    record_id: str
    embedding: tuple[float, ...]
    metadata: dict[str, Any] | None
    document: str | None


def _resolved_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _paths_overlap(first: Path, second: Path) -> bool:
    first_key = _resolved_key(first)
    second_key = _resolved_key(second)
    return (
        first_key == second_key
        or first_key.startswith(second_key + os.sep)
        or second_key.startswith(first_key + os.sep)
    )


def validate_paths(source_dir: Path, staged_dir: Path, target_dir: Path) -> None:
    """Validate all filesystem paths before creating the target."""
    source = source_dir.resolve()
    staged = staged_dir.resolve()
    target = target_dir.resolve()

    for label, path in (("Source", source), ("Staged", staged)):
        if not path.is_dir():
            raise PromotionIndexError(f"{label} Chroma directory does not exist: {path}")
        if not any(path.iterdir()):
            raise PromotionIndexError(f"{label} Chroma directory is empty: {path}")

    if _paths_overlap(source, staged):
        raise PromotionIndexError(
            f"Source and staged Chroma directories must not overlap: {source}, {staged}"
        )
    if _paths_overlap(target, LIVE_CHROMA_DIR):
        raise PromotionIndexError(
            f"Refusing target {target}: it overlaps the live Chroma directory "
            f"{LIVE_CHROMA_DIR}"
        )
    if target.exists():
        raise PromotionIndexError(f"Target must not already exist: {target}")
    for label, path in (("source", source), ("staged", staged)):
        if _paths_overlap(target, path):
            raise PromotionIndexError(
                f"Refusing target {target}: it overlaps the {label} Chroma directory {path}"
            )


def _close_client(client: object | None) -> None:
    if client is None:
        return
    close = getattr(client, "close", None)
    if callable(close):
        close()


def _collection_names(client: object) -> list[str]:
    raw_collections = client.list_collections()
    names: list[str] = []
    for raw_collection in raw_collections:
        name = raw_collection if isinstance(raw_collection, str) else getattr(
            raw_collection, "name", None
        )
        if not isinstance(name, str) or not name:
            raise PromotionIndexError("Chroma returned a collection without a valid name")
        names.append(name)
    if len(names) != len(set(names)):
        raise PromotionIndexError("Chroma returned duplicate collection names")
    return sorted(names)


def _get_collection(client: object, name: str) -> object:
    return client.get_collection(name=name, embedding_function=None)


def _collection_counts(client: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in _collection_names(client):
        count = _get_collection(client, name).count()
        if not isinstance(count, int) or count < 0:
            raise PromotionIndexError(f"Collection {name!r} returned an invalid count")
        counts[name] = count
    return counts


def _as_list(value: object, *, field: str, expected_count: int) -> list[object]:
    if value is None:
        raise PromotionIndexError(f"Chroma omitted required {field}")
    if isinstance(value, (str, bytes, Mapping)):
        raise PromotionIndexError(f"Chroma returned invalid {field}")
    try:
        converted = list(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise PromotionIndexError(f"Chroma returned invalid {field}") from exc
    if len(converted) != expected_count:
        raise PromotionIndexError(
            f"Chroma {field} count mismatch: expected {expected_count}, "
            f"got {len(converted)}"
        )
    return converted


def _optional_list(
    value: object,
    *,
    field: str,
    expected_count: int,
) -> list[object | None]:
    if value is None:
        return [None] * expected_count
    return _as_list(value, field=field, expected_count=expected_count)


def _embedding_vector(raw_vector: object, *, record_id: str) -> tuple[float, ...]:
    if raw_vector is None or isinstance(raw_vector, (str, bytes, Mapping)):
        raise PromotionIndexError(f"Record {record_id!r} has no valid embedding")
    try:
        vector = tuple(float(value) for value in raw_vector)  # type: ignore[union-attr]
    except (TypeError, ValueError) as exc:
        raise PromotionIndexError(
            f"Record {record_id!r} has no valid embedding"
        ) from exc
    if not vector or any(not math.isfinite(value) for value in vector):
        raise PromotionIndexError(f"Record {record_id!r} has no valid embedding")
    return vector


def _read_records(collection: object) -> dict[str, StoredRecord]:
    expected_count = collection.count()
    if not isinstance(expected_count, int) or expected_count <= 0:
        raise PromotionIndexError("Staged manuscript collection must not be empty")

    result = collection.get(include=["embeddings", "documents", "metadatas"])
    if not isinstance(result, Mapping):
        raise PromotionIndexError("Chroma returned an invalid collection result")
    raw_ids = _as_list(result.get("ids"), field="IDs", expected_count=expected_count)
    raw_embeddings = _as_list(
        result.get("embeddings"),
        field="embeddings",
        expected_count=expected_count,
    )
    raw_documents = _optional_list(
        result.get("documents"),
        field="documents",
        expected_count=expected_count,
    )
    raw_metadatas = _optional_list(
        result.get("metadatas"),
        field="metadatas",
        expected_count=expected_count,
    )

    records: dict[str, StoredRecord] = {}
    dimensions: set[int] = set()
    for raw_id, raw_embedding, raw_metadata, raw_document in zip(
        raw_ids,
        raw_embeddings,
        raw_metadatas,
        raw_documents,
        strict=True,
    ):
        if not isinstance(raw_id, str) or not raw_id:
            raise PromotionIndexError("Staged manuscript contains an invalid record ID")
        if raw_id in records:
            raise PromotionIndexError(
                f"Staged manuscript contains duplicate record ID {raw_id!r}"
            )
        if raw_metadata is not None and not isinstance(raw_metadata, Mapping):
            raise PromotionIndexError(f"Record {raw_id!r} has invalid metadata")
        if raw_document is not None and not isinstance(raw_document, str):
            raise PromotionIndexError(f"Record {raw_id!r} has an invalid document")

        embedding = _embedding_vector(raw_embedding, record_id=raw_id)
        dimensions.add(len(embedding))
        metadata = dict(raw_metadata) if raw_metadata is not None else None
        records[raw_id] = StoredRecord(
            record_id=raw_id,
            embedding=embedding,
            metadata=metadata,
            document=raw_document,
        )

    if len(dimensions) != 1:
        raise PromotionIndexError("Staged manuscript embeddings have mixed dimensions")
    return records


def _collection_metadata(collection: object) -> dict[str, Any]:
    raw_metadata = getattr(collection, "metadata", None)
    if not isinstance(raw_metadata, Mapping):
        raise PromotionIndexError("Staged manuscript collection metadata is unavailable")
    metadata = dict(raw_metadata)
    if metadata.get("hnsw:space") != "l2":
        raise PromotionIndexError(
            "Staged manuscript collection must declare metadata hnsw:space='l2'"
        )
    for field in ("embedding_model", "chunks_sha256"):
        value = metadata.get(field)
        if not isinstance(value, str) or not value:
            raise PromotionIndexError(
                f"Staged manuscript collection metadata is missing {field!r}"
            )
    return metadata


def _metadata_text_hash(record: StoredRecord) -> str:
    metadata = record.metadata
    text = metadata.get("text") if metadata is not None else None
    if not isinstance(text, str):
        raise PromotionIndexError(
            f"Record {record.record_id!r} metadata does not contain string text"
        )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _add_records(
    collection: object,
    records: Mapping[str, StoredRecord],
    *,
    batch_size: int,
) -> None:
    grouped: dict[tuple[bool, bool], list[StoredRecord]] = defaultdict(list)
    for record_id in sorted(records):
        record = records[record_id]
        grouped[(record.metadata is not None, record.document is not None)].append(record)

    for (has_metadata, has_document), group in sorted(grouped.items()):
        for start in range(0, len(group), batch_size):
            batch = group[start : start + batch_size]
            arguments: dict[str, Any] = {
                "ids": [record.record_id for record in batch],
                "embeddings": [list(record.embedding) for record in batch],
            }
            if has_metadata:
                arguments["metadatas"] = [record.metadata for record in batch]
            if has_document:
                arguments["documents"] = [record.document for record in batch]
            collection.add(**arguments)


def _verify_records(
    collection: object,
    expected_records: Mapping[str, StoredRecord],
    expected_collection_metadata: Mapping[str, Any],
) -> None:
    actual_records = _read_records(collection)
    if set(actual_records) != set(expected_records):
        raise PromotionIndexError("Promoted manuscript ID set does not match staged IDs")
    if len(actual_records) != len(expected_records):
        raise PromotionIndexError("Promoted manuscript count does not match staged count")

    actual_metadata = getattr(collection, "metadata", None)
    if not isinstance(actual_metadata, Mapping) or dict(actual_metadata) != dict(
        expected_collection_metadata
    ):
        raise PromotionIndexError(
            "Promoted manuscript collection metadata does not match staged metadata"
        )

    for record_id, expected in expected_records.items():
        actual = actual_records[record_id]
        if actual.metadata != expected.metadata:
            raise PromotionIndexError(
                f"Promoted manuscript metadata mismatch for record {record_id!r}"
            )
        if _metadata_text_hash(actual) != _metadata_text_hash(expected):
            raise PromotionIndexError(
                f"Promoted manuscript text hash mismatch for record {record_id!r}"
            )
        if actual.document != expected.document:
            raise PromotionIndexError(
                f"Promoted manuscript document mismatch for record {record_id!r}"
            )
        if actual.embedding != expected.embedding:
            raise PromotionIndexError(
                f"Promoted manuscript embedding mismatch for record {record_id!r}"
            )


def assemble_promoted_index(
    source_dir: str | Path,
    staged_dir: str | Path,
    target_dir: str | Path,
    *,
    collection_name: str = DEFAULT_COLLECTION,
    batch_size: int = DEFAULT_BATCH_SIZE,
    chroma_client_factory: ChromaClientFactory | None = None,
) -> dict[str, Any]:
    """Copy a full store, replace its manuscript collection, and verify the result."""
    source = Path(source_dir).resolve()
    staged = Path(staged_dir).resolve()
    target = Path(target_dir).resolve()
    if not collection_name.strip():
        raise PromotionIndexError("collection_name must not be empty")
    if batch_size <= 0:
        raise PromotionIndexError("batch_size must be greater than zero")
    validate_paths(source, staged, target)

    if chroma_client_factory is None:
        import chromadb

        chroma_client_factory = chromadb.PersistentClient

    source_client: object | None = None
    staged_client: object | None = None
    target_client: object | None = None
    succeeded = False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)

        source_client = chroma_client_factory(path=str(source))
        staged_client = chroma_client_factory(path=str(staged))
        target_client = chroma_client_factory(path=str(target))

        source_counts = _collection_counts(source_client)
        copied_counts = _collection_counts(target_client)
        if source_counts != copied_counts:
            raise PromotionIndexError(
                "Copied Chroma collection names/counts do not match the source store"
            )
        if collection_name not in source_counts:
            raise PromotionIndexError(
                f"Source store does not contain collection {collection_name!r}"
            )

        staged_names = _collection_names(staged_client)
        if staged_names != [collection_name]:
            raise PromotionIndexError(
                "Staged store must contain only the verified manuscript collection"
            )
        staged_collection = _get_collection(staged_client, collection_name)
        staged_metadata = _collection_metadata(staged_collection)
        staged_records = _read_records(staged_collection)
        for record in staged_records.values():
            _metadata_text_hash(record)

        target_client.delete_collection(name=collection_name)
        promoted_collection = target_client.create_collection(
            name=collection_name,
            metadata=staged_metadata,
            embedding_function=None,
        )
        _add_records(promoted_collection, staged_records, batch_size=batch_size)
        _verify_records(promoted_collection, staged_records, staged_metadata)

        expected_preserved = {
            name: count for name, count in source_counts.items() if name != collection_name
        }
        promoted_counts = _collection_counts(target_client)
        actual_preserved = {
            name: count for name, count in promoted_counts.items() if name != collection_name
        }
        if actual_preserved != expected_preserved:
            raise PromotionIndexError(
                "A non-manuscript collection name or count changed during assembly"
            )
        if set(promoted_counts) != set(source_counts):
            raise PromotionIndexError(
                "Promoted store collection names do not match the source store"
            )
        if promoted_counts[collection_name] != len(staged_records):
            raise PromotionIndexError(
                "Promoted manuscript count does not match the staged manuscript"
            )
        if _collection_counts(source_client) != source_counts:
            raise PromotionIndexError(
                "Source collection names/counts changed while the copy was assembled"
            )

        succeeded = True
        return {
            "source_collection_counts": source_counts,
            "preserved_collection_counts": expected_preserved,
            "promoted_collection": collection_name,
            "promoted_manuscript_count": len(staged_records),
            "manuscript_metadata": staged_metadata,
        }
    finally:
        _close_client(target_client)
        _close_client(staged_client)
        _close_client(source_client)
        if not succeeded and target.exists():
            shutil.rmtree(target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Copy a complete Chroma store and replace only its manuscript "
            "collection from a staged, already-embedded store."
        )
    )
    parser.add_argument("source_chroma_dir", type=Path)
    parser.add_argument("staged_chroma_dir", type=Path)
    parser.add_argument("target_chroma_dir", type=Path)
    parser.add_argument(
        "--collection-name",
        default=DEFAULT_COLLECTION,
        help=f"Collection to replace (default: {DEFAULT_COLLECTION})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Record copy batch size (default: {DEFAULT_BATCH_SIZE})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = assemble_promoted_index(
        args.source_chroma_dir,
        args.staged_chroma_dir,
        args.target_chroma_dir,
        collection_name=args.collection_name,
        batch_size=args.batch_size,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
