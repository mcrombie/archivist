from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gold_provenance import gold_question_set_sha256  # noqa: E402


COMMITMENT_SCHEMA = "archivist.gold_question_commitment/1"
_HEADING_RE = re.compile(r"^## (H\d{3}) · ([a-z_]+)$")
_QUESTION_PREFIX = "**Q:** "
_BEHAVIOR_PREFIX = "**Behavior:** "


class GoldQuestionFingerprintError(ValueError):
    """Raised when the private Markdown question form is incomplete or ambiguous."""


def fingerprint_markdown(text: str) -> dict[str, object]:
    """Return a text-free commitment to ordered owner-controlled question fields."""

    items: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading = _HEADING_RE.fullmatch(line)
        if heading is not None:
            if current is not None:
                items.append(current)
            current = {"id": heading.group(1), "stratum": heading.group(2)}
            continue
        if current is None:
            continue
        if line.startswith(_QUESTION_PREFIX):
            current["question"] = line.removeprefix(_QUESTION_PREFIX).strip()
        elif line.startswith(_BEHAVIOR_PREFIX):
            current["expected_behavior"] = line.removeprefix(_BEHAVIOR_PREFIX).strip()
    if current is not None:
        items.append(current)

    if not items:
        raise GoldQuestionFingerprintError("no H### question blocks were found")
    expected_ids = [f"H{index:03d}" for index in range(1, len(items) + 1)]
    actual_ids = [item.get("id", "") for item in items]
    if actual_ids != expected_ids:
        raise GoldQuestionFingerprintError(
            "question IDs must be unique, ordered, and contiguous from H001"
        )
    for item in items:
        for field in ("question", "stratum", "expected_behavior"):
            if not item.get(field, "").strip():
                raise GoldQuestionFingerprintError(f"{item['id']} has an empty or missing {field}")
        if item["expected_behavior"] not in {"answer", "abstain"}:
            raise GoldQuestionFingerprintError(
                f"{item['id']} has invalid Behavior {item['expected_behavior']!r}"
            )

    projection = {"items": items}
    return {
        "schema": COMMITMENT_SCHEMA,
        "question_count": len(items),
        "stratum_counts": dict(sorted(Counter(item["stratum"] for item in items).items())),
        "question_set_sha256": gold_question_set_sha256(projection),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a text-free hash commitment to IDs, questions, strata, and "
            "Behavior fields in the private gold authoring form."
        )
    )
    parser.add_argument("question_form", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        commitment = fingerprint_markdown(args.question_form.read_text(encoding="utf-8"))
    except (OSError, GoldQuestionFingerprintError) as exc:
        print(f"Gold question fingerprint failed: {exc}", file=sys.stderr)
        return 1
    payload = json.dumps(commitment, indent=2, ensure_ascii=False) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="\n")
        print(f"Wrote text-free question commitment: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
