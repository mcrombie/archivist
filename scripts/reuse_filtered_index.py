"""Build a filtered staged Chroma index by reusing stored embeddings.

The source ``manuscript`` collection is opened for reading only. Records whose
metadata ``document`` is eligible under :func:`filters.should_skip_document`
are copied, with their stored embeddings, metadata, and document payloads
unchanged, into a fresh target store. The target is then reopened and verified
against the source values.

This path never imports an OpenAI client and never computes an embedding.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import shutil
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from filters import should_skip_document  # noqa: E402


LIVE_CHROMA_DIR = (ROOT / "chroma_db").resolve()
DEFAULT_COLLECTION = "manuscript"
DEFAULT_BATCH_SIZE = 100

ChromaClientFactory = Callable[..., object]


class ReusedIndexError(ValueError):
    """Raised when a source or staged-index invariant is not satisfied."""


class StoredRecord(NamedTuple):
    """One source record represented for deterministic value comparisons."""

    record_id: str
    embedding: tuple[float, ...]
    metadata: dict[str, Any]
    document: str | None

    @property
    def source_document(self) -> str:
        value = self.metadata["document"]
        assert isinstance(value, str)
        return value


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


def validate_paths(source_dir: Path, target_dir: Path) -> None:
    """Reject missing sources and every target that is not fresh and isolated."""
    source = source_dir.resolve()
    target = target_dir.resolve()
    if not source.is_dir():
        raise ReusedIndexError(f"Source Chroma directory does not exist: {source}")
    if not any(source.iterdir()):
        raise ReusedIndexError(f"Source Chroma directory is empty: {source}")
    if _paths_overlap(source, target):
        raise ReusedIndexError(
            f"Source and target Chroma directories must not overlap: {source}, {target}"
        )
    if _paths_overlap(target, LIVE_CHROMA_DIR):
        raise ReusedIndexError(
            f"Refusing target {target}: it overlaps the live Chroma directory "
            f"{LIVE_CHROMA_DIR}"
        )
    if target.exists():
        raise ReusedIndexError(f"Target must not already exist: {target}")


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
        name = (
            raw_collection
            if isinstance(raw_collection, str)
            else getattr(raw_collection, "name", None)
        )
        if not isinstance(name, str) or not name:
            raise ReusedIndexError("Chroma returned a collection without a valid name")
        names.append(name)
    if len(names) != len(set(names)):
        raise ReusedIndexError("Chroma returned duplicate collection names")
    return sorted(names)


def _get_collection(client: object, name: str) -> object:
    return client.get_collection(name=name, embedding_function=None)


def _as_list(value: object, *, field: str, expected_count: int) -> list[object]:
    if value is None or isinstance(value, (str, bytes, Mapping)):
        raise ReusedIndexError(f"Chroma returned invalid or missing {field}")
    try:
        converted = list(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ReusedIndexError(f"Chroma returned invalid {field}") from exc
    if len(converted) != expected_count:
        raise ReusedIndexError(
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
        raise ReusedIndexError(f"Record {record_id!r} has no valid embedding")
    try:
        vector = tuple(float(value) for value in raw_vector)  # type: ignore[union-attr]
    except (TypeError, ValueError) as exc:
        raise ReusedIndexError(
            f"Record {record_id!r} has no valid embedding"
        ) from exc
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ReusedIndexError(f"Record {record_id!r} has no valid embedding")
    return vector


def _read_records(collection: object) -> dict[str, StoredRecord]:
    expected_count = collection.count()
    if not isinstance(expected_count, int) or isinstance(expected_count, bool):
        raise ReusedIndexError("Source collection returned an invalid count")
    if expected_count <= 0:
        raise ReusedIndexError("Source manuscript collection must not be empty")

    result = collection.get(include=["embeddings", "documents", "metadatas"])
    if not isinstance(result, Mapping):
        raise ReusedIndexError("Chroma returned an invalid collection result")
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
    raw_metadatas = _as_list(
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
            raise ReusedIndexError("Source manuscript contains an invalid record ID")
        if raw_id in records:
            raise ReusedIndexError(
                f"Source manuscript contains duplicate record ID {raw_id!r}"
            )
        if not isinstance(raw_metadata, Mapping):
            raise ReusedIndexError(f"Record {raw_id!r} has no valid metadata")
        metadata = copy.deepcopy(dict(raw_metadata))
        source_document = metadata.get("document")
        if not isinstance(source_document, str) or not source_document.strip():
            raise ReusedIndexError(
                f"Record {raw_id!r} metadata has no valid document"
            )
        text = metadata.get("text")
        if not isinstance(text, str):
            raise ReusedIndexError(
                f"Record {raw_id!r} metadata has no string text"
            )
        if raw_document is not None and not isinstance(raw_document, str):
            raise ReusedIndexError(
                f"Record {raw_id!r} has an invalid stored document payload"
            )

        embedding = _embedding_vector(raw_embedding, record_id=raw_id)
        dimensions.add(len(embedding))
        records[raw_id] = StoredRecord(
            record_id=raw_id,
            embedding=embedding,
            metadata=metadata,
            document=raw_document,
        )

    if len(dimensions) != 1:
        raise ReusedIndexError("Source manuscript embeddings have mixed dimensions")
    return records


def _collection_metadata(collection: object) -> dict[str, Any] | None:
    raw_metadata = getattr(collection, "metadata", None)
    if raw_metadata is None:
        return None
    if not isinstance(raw_metadata, Mapping):
        raise ReusedIndexError("Source manuscript collection metadata is invalid")
    return copy.deepcopy(dict(raw_metadata))


def _hnsw_configuration(collection: object) -> dict[str, Any]:
    raw_configuration = getattr(collection, "configuration", None)
    if not isinstance(raw_configuration, Mapping):
        raise ReusedIndexError("Source manuscript collection configuration is unavailable")
    raw_hnsw = raw_configuration.get("hnsw")
    if not isinstance(raw_hnsw, Mapping):
        raise ReusedIndexError("Source manuscript collection has no HNSW configuration")
    hnsw = copy.deepcopy(dict(raw_hnsw))
    if hnsw.get("space") not in {"l2", "cosine", "ip"}:
        raise ReusedIndexError(
            "Source manuscript collection has an invalid HNSW distance space"
        )
    return hnsw


def _text_sha256(record: StoredRecord) -> str:
    text = record.metadata.get("text")
    if not isinstance(text, str):
        raise ReusedIndexError(
            f"Record {record.record_id!r} metadata has no string text"
        )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _add_records(
    collection: object,
    records: Mapping[str, StoredRecord],
    *,
    batch_size: int,
) -> None:
    grouped: dict[bool, list[StoredRecord]] = defaultdict(list)
    for record_id in sorted(records):
        record = records[record_id]
        grouped[record.document is not None].append(record)

    for has_document, group in sorted(grouped.items()):
        for start in range(0, len(group), batch_size):
            batch = group[start : start + batch_size]
            arguments: dict[str, Any] = {
                "ids": [record.record_id for record in batch],
                "embeddings": [list(record.embedding) for record in batch],
                "metadatas": [record.metadata for record in batch],
            }
            if has_document:
                arguments["documents"] = [record.document for record in batch]
            collection.add(**arguments)


def _verify_records(
    collection: object,
    expected_records: Mapping[str, StoredRecord],
    expected_collection_metadata: Mapping[str, Any] | None,
    expected_hnsw_configuration: Mapping[str, Any],
    *,
    label: str,
) -> None:
    actual_records = _read_records(collection)
    if set(actual_records) != set(expected_records):
        raise ReusedIndexError(f"{label} manuscript ID set does not match eligible source IDs")
    if len(actual_records) != len(expected_records):
        raise ReusedIndexError(f"{label} manuscript count does not match eligible source count")

    actual_metadata = _collection_metadata(collection)
    if actual_metadata != expected_collection_metadata:
        raise ReusedIndexError(
            f"{label} manuscript collection metadata does not match the source"
        )
    actual_hnsw = _hnsw_configuration(collection)
    if actual_hnsw != dict(expected_hnsw_configuration):
        raise ReusedIndexError(
            f"{label} manuscript HNSW configuration does not match the source"
        )

    for record_id, expected in expected_records.items():
        actual = actual_records[record_id]
        if actual.embedding != expected.embedding:
            raise ReusedIndexError(
                f"{label} embedding mismatch for record {record_id!r}"
            )
        if actual.metadata != expected.metadata:
            raise ReusedIndexError(
                f"{label} metadata mismatch for record {record_id!r}"
            )
        if _text_sha256(actual) != _text_sha256(expected):
            raise ReusedIndexError(
                f"{label} text mismatch for record {record_id!r}"
            )
        if actual.document != expected.document:
            raise ReusedIndexError(
                f"{label} stored document mismatch for record {record_id!r}"
            )


def reuse_filtered_index(
    source_dir: str | Path,
    target_dir: str | Path,
    *,
    collection_name: str = DEFAULT_COLLECTION,
    batch_size: int = DEFAULT_BATCH_SIZE,
    chroma_client_factory: ChromaClientFactory | None = None,
) -> dict[str, Any]:
    """Copy currently eligible records into a fresh, verified staged store."""
    source = Path(source_dir).resolve()
    target = Path(target_dir).resolve()
    if not collection_name.strip():
        raise ReusedIndexError("collection_name must not be empty")
    if batch_size <= 0:
        raise ReusedIndexError("batch_size must be greater than zero")
    validate_paths(source, target)

    if chroma_client_factory is None:
        import chromadb

        chroma_client_factory = chromadb.PersistentClient

    source_client: object | None = None
    write_client: object | None = None
    verify_client: object | None = None
    target_created = False
    succeeded = False
    try:
        source_client = chroma_client_factory(path=str(source))
        source_names = _collection_names(source_client)
        if collection_name not in source_names:
            raise ReusedIndexError(
                f"Source store does not contain collection {collection_name!r}"
            )
        source_collection = _get_collection(source_client, collection_name)
        source_records = _read_records(source_collection)
        source_metadata = _collection_metadata(source_collection)
        source_hnsw = _hnsw_configuration(source_collection)

        eligible_records = {
            record_id: record
            for record_id, record in source_records.items()
            if not should_skip_document(record.source_document)
        }
        if not eligible_records:
            raise ReusedIndexError(
                "No retrieval-eligible manuscript records remain after current filters"
            )
        excluded_documents = Counter(
            record.source_document
            for record in source_records.values()
            if record.record_id not in eligible_records
        )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.mkdir()
        target_created = True
        write_client = chroma_client_factory(path=str(target))
        if _collection_names(write_client):
            raise ReusedIndexError("Fresh target store unexpectedly contains collections")
        create_arguments: dict[str, Any] = {
            "name": collection_name,
            "configuration": {"hnsw": source_hnsw},
            "embedding_function": None,
        }
        if source_metadata is not None:
            create_arguments["metadata"] = source_metadata
        target_collection = write_client.create_collection(**create_arguments)
        _add_records(target_collection, eligible_records, batch_size=batch_size)
        _close_client(write_client)
        write_client = None

        verify_client = chroma_client_factory(path=str(target))
        if _collection_names(verify_client) != [collection_name]:
            raise ReusedIndexError(
                "Staged target must contain only the manuscript collection"
            )
        verified_collection = _get_collection(verify_client, collection_name)
        _verify_records(
            verified_collection,
            eligible_records,
            source_metadata,
            source_hnsw,
            label="Staged",
        )

        # Re-read the source so a source-side mutation cannot pass unnoticed.
        _verify_records(
            source_collection,
            source_records,
            source_metadata,
            source_hnsw,
            label="Source",
        )

        dimensions = {len(record.embedding) for record in eligible_records.values()}
        assert len(dimensions) == 1
        succeeded = True
        return {
            "source_collection": collection_name,
            "source_record_count": len(source_records),
            "retained_record_count": len(eligible_records),
            "excluded_record_count": len(source_records) - len(eligible_records),
            "excluded_document_counts": dict(sorted(excluded_documents.items())),
            "embedding_dimension": dimensions.pop(),
            "hnsw_space": source_hnsw["space"],
            "filter": "filters.should_skip_document",
            "api_calls": 0,
        }
    finally:
        _close_client(verify_client)
        _close_client(write_client)
        _close_client(source_client)
        if target_created and not succeeded and target.exists():
            shutil.rmtree(target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a fresh staged manuscript index from currently eligible "
            "records in an existing Chroma store, reusing stored embeddings."
        )
    )
    parser.add_argument("source_chroma_dir", type=Path)
    parser.add_argument("target_chroma_dir", type=Path)
    parser.add_argument(
        "--collection-name",
        default=DEFAULT_COLLECTION,
        help=f"Collection to filter and copy (default: {DEFAULT_COLLECTION})",
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
    report = reuse_filtered_index(
        args.source_chroma_dir,
        args.target_chroma_dir,
        collection_name=args.collection_name,
        batch_size=args.batch_size,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
