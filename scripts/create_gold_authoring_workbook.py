"""Create an ignored, owner-fillable workbook for the held-out gold set.

The generated file contains identifiers, the required stratum allocation, and
blank schema fields. It deliberately contains no questions, claims, answers, or
source judgments. Only the manuscript owner may fill those fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPOSITORY_ROOT / "fixtures" / "corpus_manifest.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "runtime" / "gold-authoring" / "gold_set.draft.json"
GOLD_SCHEMA = "archivist.gold/1"
GOLD_VERSION = "1.0.0"

SLOT_COUNTS = (
    ("focused_biographical", 8),
    ("focused_analytical", 8),
    ("conceptual", 6),
    ("broad_thematic", 10),
    ("out_of_corpus", 5),
    ("adversarial_premise", 3),
)


class WorkbookCreationError(ValueError):
    """Raised when a gold-authoring workbook cannot be created safely."""


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest over the file's exact bytes."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_blank_workbook(corpus_manifest_sha256: str) -> dict[str, object]:
    """Return forty empty owner-authoring slots in the contract's target balance."""

    items: list[dict[str, object]] = []
    slot_number = 1
    for stratum, count in SLOT_COUNTS:
        for _ in range(count):
            item_id = f"H{slot_number:03d}"
            items.append(
                {
                    "id": item_id,
                    "question": "",
                    "stratum": stratum,
                    "expected_behavior": "",
                    "claims": [],
                    "relevant_chunk_ids": [],
                    "must_not_claim": [],
                    "notes": "",
                }
            )
            slot_number += 1

    return {
        "schema": GOLD_SCHEMA,
        "version": GOLD_VERSION,
        "authored_against_corpus": corpus_manifest_sha256,
        "items": items,
    }


def create_workbook(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    output_path: Path = DEFAULT_OUTPUT,
    force: bool = False,
) -> Path:
    """Write a blank workbook, refusing to replace an existing draft by default."""

    if output_path.exists() and not force:
        raise WorkbookCreationError(
            f"refusing to overwrite existing authoring draft: {output_path}; "
            "pass --force only after preserving any owner-authored work"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkbookCreationError(
            f"cannot read corpus manifest {manifest_path}: {exc}"
        ) from exc
    if not isinstance(manifest, dict) or manifest.get("manifest_schema") != (
        "archivist.corpus_manifest/1"
    ):
        raise WorkbookCreationError(
            f"{manifest_path} is not an archivist.corpus_manifest/1 manifest"
        )

    workbook = build_blank_workbook(sha256_file(manifest_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(workbook, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an owner-fillable, deliberately incomplete held-out gold workbook."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing draft (owner-authored content may be lost)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output_path = create_workbook(
            manifest_path=args.manifest,
            output_path=args.output,
            force=args.force,
        )
    except WorkbookCreationError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"Created blank held-out gold authoring workbook: {output_path}")
    print("It is intentionally invalid until the manuscript owner fills every slot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
