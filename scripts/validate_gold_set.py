from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gold_set import (  # noqa: E402
    STRATUM_RANGES,
    GoldSetValidationError,
    validate_gold_set_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Mechanically validate an owner-authored archivist.gold/1 file "
            "without reading manuscript text or calling an API."
        )
    )
    parser.add_argument("gold_set", type=Path, help="Gold-set JSON file to validate.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=BASE_DIR / "fixtures" / "corpus_manifest.json",
        help="Exact text-free corpus manifest the gold set was authored against.",
    )
    parser.add_argument(
        "--mode",
        choices=("pilot", "run-of-record"),
        default="pilot",
        help=(
            "Use ten-item pilot checks by default. Full 34-46 item composition "
            "checks require an explicit run-of-record mode."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = validate_gold_set_file(
            args.gold_set,
            args.manifest,
            mode=args.mode,
        )
    except GoldSetValidationError as exc:
        print(f"INVALID {args.mode} gold set ({len(exc.errors)} error(s)):", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    represented = ", ".join(
        f"{name}={summary.stratum_counts[name]}"
        for name in STRATUM_RANGES
        if summary.stratum_counts[name]
    )
    print(
        f"VALID {summary.mode} gold set: {summary.item_count} items, "
        f"version {summary.version}."
    )
    print(f"Strata: {represented}")
    print(f"Corpus manifest SHA-256: {summary.corpus_manifest_sha256}")
    if summary.mode == "pilot":
        print(
            "PILOT ONLY: this file is not eligible for a run of record. "
            "Use explicit --mode run-of-record after completing the locked "
            "34-46 item composition."
        )
    else:
        print(
            "Gold-set schema and composition pass run-of-record checks. "
            "Run identity, clean-tree, and evaluation requirements still apply."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
