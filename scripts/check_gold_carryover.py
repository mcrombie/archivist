"""Mechanically verify gold locations across corpus re-ingests.

Implements EVAL_CONTRACT.md section 2.5. Any invalid location quarantines the
entire owner-authored item until its locations are re-established by hand.
Reports contain identifiers and hashes only, never manuscript text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import TextIO


class CarryoverError(ValueError):
    """Raised when inputs cannot support a mechanical carry-over check."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CarryoverError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CarryoverError(f"{label} must be a JSON object")
    return value


def _manifest_index(
    manifest: dict[str, object],
) -> tuple[dict[str, dict[str, object]], list[str]]:
    if manifest.get("manifest_schema") != "archivist.corpus_manifest/1":
        raise CarryoverError("manifest schema must be archivist.corpus_manifest/1")
    ingest = manifest.get("ingest")
    chunks = manifest.get("chunks")
    if not isinstance(ingest, dict) or not isinstance(chunks, list):
        raise CarryoverError("manifest requires object ingest and array chunks fields")
    skip_values = ingest.get("skip_files")
    if not isinstance(skip_values, list) or any(
        not isinstance(value, str) for value in skip_values
    ):
        raise CarryoverError("manifest ingest.skip_files must be an array of strings")

    result: dict[str, dict[str, object]] = {}
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise CarryoverError("manifest chunk entries must be objects")
        chunk_id = chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise CarryoverError("manifest chunk IDs must be non-empty strings")
        if chunk_id in result:
            raise CarryoverError(f"duplicate manifest chunk ID {chunk_id!r}")
        result[chunk_id] = chunk
    return result, skip_values


def _is_skipped(chunk: dict[str, object], skip_files: list[str]) -> bool:
    document = chunk.get("document")
    if not isinstance(document, str):
        raise CarryoverError("manifest chunk document must be a string")
    normalized = document.casefold()
    return any(sentinel.casefold() in normalized for sentinel in skip_files)


def _item_locations(item: dict[str, object]) -> list[str]:
    locations: list[str] = []
    relevant = item.get("relevant_chunk_ids")
    claims = item.get("claims")
    if not isinstance(relevant, list) or not isinstance(claims, list):
        raise CarryoverError("gold items require claims and relevant_chunk_ids arrays")
    locations.extend(value for value in relevant if isinstance(value, str))
    for claim in claims:
        if not isinstance(claim, dict):
            raise CarryoverError("gold claims must be objects")
        supporting = claim.get("supporting_chunk_ids")
        if not isinstance(supporting, list):
            raise CarryoverError("gold claims require supporting_chunk_ids arrays")
        locations.extend(value for value in supporting if isinstance(value, str))
    return list(dict.fromkeys(locations))


def check_carryover(
    *,
    gold_set: dict[str, object],
    old_manifest: dict[str, object],
    new_manifest: dict[str, object],
    old_manifest_sha256: str,
    new_manifest_sha256: str,
    gold_set_sha256: str | None = None,
) -> dict[str, object]:
    """Return a text-free location verification and item quarantine report."""

    if gold_set.get("schema") != "archivist.gold/1":
        raise CarryoverError("gold schema must be archivist.gold/1")
    authored_against = gold_set.get("authored_against_corpus")
    if authored_against != old_manifest_sha256:
        raise CarryoverError(
            "gold authored_against_corpus does not match the supplied old manifest"
        )
    items = gold_set.get("items")
    if not isinstance(items, list):
        raise CarryoverError("gold items field must be an array")

    old_chunks, old_skip_files = _manifest_index(old_manifest)
    new_chunks, new_skip_files = _manifest_index(new_manifest)
    item_reports: list[dict[str, object]] = []
    quarantined_ids: list[str] = []
    verified_ids: list[str] = []

    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise CarryoverError("gold item entries require string IDs")
        item_id = str(item["id"])
        location_reports: list[dict[str, str]] = []
        quarantined = False
        for chunk_id in _item_locations(item):
            old_chunk = old_chunks.get(chunk_id)
            new_chunk = new_chunks.get(chunk_id)
            if old_chunk is None or _is_skipped(old_chunk, old_skip_files):
                status = "invalid_old_location"
            elif new_chunk is None:
                status = "missing"
            elif _is_skipped(new_chunk, new_skip_files):
                status = "newly_skipped"
            elif old_chunk.get("text_sha256") != new_chunk.get("text_sha256"):
                status = "changed_hash"
            else:
                status = "unchanged"
            if status != "unchanged":
                quarantined = True
            location_reports.append({"chunk_id": chunk_id, "status": status})

        item_status = "quarantined" if quarantined else "verified"
        if quarantined:
            quarantined_ids.append(item_id)
        else:
            verified_ids.append(item_id)
        item_reports.append(
            {
                "item_id": item_id,
                "status": item_status,
                "locations": location_reports,
            }
        )

    return {
        "schema": "archivist.gold_carryover/1",
        "gold_set_version": gold_set.get("version"),
        "gold_set_sha256": gold_set_sha256,
        "old_manifest_sha256": old_manifest_sha256,
        "new_manifest_sha256": new_manifest_sha256,
        "verified_item_ids": verified_ids,
        "quarantined_item_ids": quarantined_ids,
        "items": item_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify gold locations across manifests without reading manuscript text."
    )
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--old-manifest", type=Path, required=True)
    parser.add_argument("--new-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None, *, output: TextIO = sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    try:
        gold = _load_object(args.gold, label="gold set")
        old_manifest = _load_object(args.old_manifest, label="old manifest")
        new_manifest = _load_object(args.new_manifest, label="new manifest")
        report = check_carryover(
            gold_set=gold,
            old_manifest=old_manifest,
            new_manifest=new_manifest,
            old_manifest_sha256=sha256_file(args.old_manifest),
            new_manifest_sha256=sha256_file(args.new_manifest),
            gold_set_sha256=sha256_file(args.gold),
        )
    except CarryoverError as exc:
        print(f"ERROR: {exc}", file=output)
        return 2

    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output is None:
        print(serialized, end="", file=output)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        print(f"Wrote carry-over report: {args.output}", file=output)
    return 1 if report["quarantined_item_ids"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
