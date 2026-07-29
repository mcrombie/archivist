from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gold_provenance import (  # noqa: E402
    GoldProvenanceValidationError,
    find_question_overlap,
    validate_development_registry,
)
from gold_set import GoldSetValidationError, load_json_object  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare draft gold questions with known development questions. "
            "Exact reuse fails; fuzzy matches are emitted for owner review."
        )
    )
    parser.add_argument("gold_set", type=Path)
    parser.add_argument(
        "--development-registry",
        type=Path,
        default=BASE_DIR / "fixtures" / "development_question_registry.json",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        gold_set = load_json_object(args.gold_set, label="gold set")
        registry_object = load_json_object(
            args.development_registry,
            label="development-question registry",
        )
        registry = validate_development_registry(registry_object)
        near_matches = find_question_overlap(gold_set, registry)
    except (GoldSetValidationError, GoldProvenanceValidationError) as exc:
        errors = getattr(exc, "errors", (str(exc),))
        print(f"INVALID HELD-OUT QUESTIONS ({len(errors)} error(s)):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 2

    report = {
        "schema": "archivist.gold_leakage_audit/1",
        "exact_duplicate_count": 0,
        "near_match_count": len(near_matches),
        "near_matches": [
            {
                "gold_item_id": match.gold_item_id,
                "development_question_id": match.development_question_id,
                "token_jaccard": round(match.token_jaccard, 6),
                "shared_token_count": match.shared_token_count,
                "sequence_ratio": round(match.sequence_ratio, 6),
                "reasons": list(match.reasons),
            }
            for match in near_matches
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if near_matches else 0


if __name__ == "__main__":
    raise SystemExit(main())
