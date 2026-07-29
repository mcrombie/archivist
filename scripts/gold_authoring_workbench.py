"""Offline, owner-directed corpus locator for held-out gold authoring.

This utility performs no retrieval, ranking, embeddings, or API calls. Listing
commands emit metadata only. Manuscript text is displayed solely for chunk IDs
the owner supplies explicitly, after each chunk's text hash is verified against
the frozen corpus manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import TextIO
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPOSITORY_ROOT / "fixtures" / "corpus_manifest.json"
DEFAULT_CHUNKS = REPOSITORY_ROOT / "output" / "chunks.json"


class WorkbenchError(ValueError):
    """Raised when local corpus data cannot be verified safely."""


def _load_json(path: Path, *, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkbenchError(f"cannot read {label} {path}: {exc}") from exc


def load_manifest(path: Path) -> dict[str, object]:
    value = _load_json(path, label="corpus manifest")
    if not isinstance(value, dict) or value.get("manifest_schema") != (
        "archivist.corpus_manifest/1"
    ):
        raise WorkbenchError(f"{path} is not an archivist.corpus_manifest/1 manifest")
    return value


def _skip_files(manifest: dict[str, object]) -> list[str]:
    ingest = manifest.get("ingest")
    if not isinstance(ingest, dict):
        raise WorkbenchError("manifest ingest field must be an object")
    values = ingest.get("skip_files")
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise WorkbenchError("manifest ingest.skip_files must be an array of strings")
    return values


def _is_skipped(document: str, skip_files: list[str]) -> bool:
    normalized = document.casefold()
    return any(sentinel.casefold() in normalized for sentinel in skip_files)


def document_rows(manifest: dict[str, object]) -> list[dict[str, object]]:
    """Return text-free document metadata in manifest order."""

    documents = manifest.get("documents")
    if not isinstance(documents, list):
        raise WorkbenchError("manifest documents field must be an array")
    skip_files = _skip_files(manifest)
    rows: list[dict[str, object]] = []
    for document in documents:
        if not isinstance(document, dict):
            raise WorkbenchError("manifest document entries must be objects")
        filename = document.get("filename")
        if not isinstance(filename, str):
            raise WorkbenchError("manifest document filename must be a string")
        rows.append(
            {
                "filename": filename,
                "chapter_title": document.get("chapter_title"),
                "paragraph_count": document.get("paragraph_count"),
                "chunk_count": document.get("chunk_count"),
                "retrieval_eligible": not _is_skipped(filename, skip_files),
            }
        )
    return rows


def chunk_rows(
    manifest: dict[str, object],
    *,
    document: str | None = None,
) -> list[dict[str, object]]:
    """Return text-free chunk metadata, optionally limited to one document."""

    chunks = manifest.get("chunks")
    if not isinstance(chunks, list):
        raise WorkbenchError("manifest chunks field must be an array")
    skip_files = _skip_files(manifest)
    rows: list[dict[str, object]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise WorkbenchError("manifest chunk entries must be objects")
        chunk_id = chunk.get("chunk_id")
        chunk_document = chunk.get("document")
        if not isinstance(chunk_id, str) or not isinstance(chunk_document, str):
            raise WorkbenchError("manifest chunks require string chunk_id and document")
        if document is not None and chunk_document != document:
            continue
        rows.append(
            {
                "chunk_id": chunk_id,
                "document": chunk_document,
                "paragraph_start": chunk.get("paragraph_start"),
                "paragraph_end": chunk.get("paragraph_end"),
                "char_count": chunk.get("char_count"),
                "text_sha256": chunk.get("text_sha256"),
                "retrieval_eligible": not _is_skipped(chunk_document, skip_files),
            }
        )
    return rows


def verified_requested_chunks(
    manifest: dict[str, object],
    chunk_payload: object,
    requested_chunk_ids: list[str],
) -> list[dict[str, object]]:
    """Return explicitly requested chunks only after identity and hash checks."""

    if not requested_chunk_ids:
        return []
    if len(requested_chunk_ids) != len(set(requested_chunk_ids)):
        raise WorkbenchError("requested chunk IDs must not contain duplicates")

    manifest_chunks = manifest.get("chunks")
    if not isinstance(manifest_chunks, list):
        raise WorkbenchError("manifest chunks field must be an array")
    manifest_by_id: dict[str, dict[str, object]] = {}
    for value in manifest_chunks:
        if not isinstance(value, dict) or not isinstance(value.get("chunk_id"), str):
            raise WorkbenchError("manifest chunks require string chunk_id fields")
        manifest_by_id[str(value["chunk_id"])] = value

    if not isinstance(chunk_payload, list):
        raise WorkbenchError("local chunks payload must be an array")
    payload_by_id: dict[str, dict[str, object]] = {}
    for value in chunk_payload:
        if not isinstance(value, dict) or not isinstance(value.get("chunk_id"), str):
            raise WorkbenchError("local chunk entries require string chunk_id fields")
        chunk_id = str(value["chunk_id"])
        if chunk_id in payload_by_id:
            raise WorkbenchError(f"duplicate local chunk ID {chunk_id!r}")
        payload_by_id[chunk_id] = value

    verified: list[dict[str, object]] = []
    for chunk_id in requested_chunk_ids:
        expected = manifest_by_id.get(chunk_id)
        actual = payload_by_id.get(chunk_id)
        if expected is None:
            raise WorkbenchError(f"requested chunk {chunk_id!r} is absent from the manifest")
        if actual is None:
            raise WorkbenchError(f"requested chunk {chunk_id!r} is absent from local chunks")
        text = actual.get("text")
        if not isinstance(text, str):
            raise WorkbenchError(f"local chunk {chunk_id!r} has no string text field")
        expected_hash = expected.get("text_sha256")
        actual_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if actual_hash != expected_hash:
            raise WorkbenchError(
                f"requested chunk {chunk_id!r} failed frozen-manifest text-hash verification"
            )
        if actual.get("document") != expected.get("document"):
            raise WorkbenchError(
                f"requested chunk {chunk_id!r} failed document identity verification"
            )
        verified.append(actual)
    return verified


def _print_json_lines(rows: list[dict[str, object]], output: TextIO) -> None:
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True), file=output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect frozen corpus metadata or explicitly requested chunks offline."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list-documents", action="store_true")
    action.add_argument(
        "--list-chunks",
        nargs="?",
        const="",
        metavar="DOCUMENT",
        help="list text-free chunk metadata, optionally for one exact document filename",
    )
    action.add_argument(
        "--show",
        action="append",
        default=[],
        metavar="CHUNK_ID",
        help="display one explicitly named local chunk after hash verification; repeatable",
    )
    return parser


def main(argv: list[str] | None = None, *, output: TextIO = sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.list_documents:
            _print_json_lines(document_rows(manifest), output)
        elif args.list_chunks is not None:
            document = args.list_chunks or None
            _print_json_lines(chunk_rows(manifest, document=document), output)
        else:
            payload = _load_json(args.chunks, label="local chunks")
            verified = verified_requested_chunks(manifest, payload, args.show)
            for chunk in verified:
                print(
                    f"===== {chunk['chunk_id']} | {chunk.get('document', '')} =====",
                    file=output,
                )
                print(chunk["text"], file=output)
    except WorkbenchError as exc:
        print(f"ERROR: {exc}", file=output)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
