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
_HEADING_RE = re.compile(r"^## (H\d{3})\s+(?:Â·|·)\s+([a-z_]+)$")
_QUESTION_PREFIX = "**Q:** "
_BEHAVIOR_PREFIX = "**Behavior:** "


class GoldQuestionFingerprintError(ValueError):
    """Raised when the private Markdown question form is incomplete or ambiguous."""


def _fingerprint_items(items: list[dict[str, str]]) -> dict[str, object]:
    """Validate and hash an ordered owner-controlled question projection."""

    if not items:
        raise GoldQuestionFingerprintError("no H### question blocks were found")
    actual_ids = [item.get("id", "") for item in items]
    if any(re.fullmatch(r"H\d{3}", item_id) is None for item_id in actual_ids):
        raise GoldQuestionFingerprintError("question IDs must use the H### form")
    if len(actual_ids) != len(set(actual_ids)):
        raise GoldQuestionFingerprintError("question IDs must be unique")
    if actual_ids != sorted(actual_ids, key=lambda value: int(value[1:])):
        raise GoldQuestionFingerprintError("question IDs must be strictly ascending")
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

    return _fingerprint_items(items)


def fingerprint_json(value: object) -> dict[str, object]:
    """Fingerprint owner-controlled fields from a private canonical gold object."""

    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise GoldQuestionFingerprintError("JSON question form must contain an items array")
    items: list[dict[str, str]] = []
    for index, raw_item in enumerate(value["items"]):
        if not isinstance(raw_item, dict):
            raise GoldQuestionFingerprintError(f"items[{index}] must be an object")
        projected: dict[str, str] = {}
        for field in ("id", "question", "stratum", "expected_behavior"):
            member = raw_item.get(field)
            if not isinstance(member, str):
                raise GoldQuestionFingerprintError(f"items[{index}].{field} must be a string")
            projected[field] = member
        items.append(projected)
    return _fingerprint_items(items)


def fingerprint_file(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.casefold() == ".json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GoldQuestionFingerprintError(f"invalid JSON: {exc}") from exc
        return fingerprint_json(value)
    return fingerprint_markdown(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a text-free hash commitment to IDs, questions, strata, and "
            "Behavior fields in a private canonical JSON or Markdown authoring form."
        )
    )
    parser.add_argument("question_form", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        commitment = fingerprint_file(args.question_form)
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
