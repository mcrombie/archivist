from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from evaluation_costs import (  # noqa: E402
    EvaluationCostError,
    build_development_cost_lineage,
    render_development_cost_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate text-free costs from isolated Archivist evaluation ledgers."
    )
    parser.add_argument(
        "--evaluations-root",
        type=Path,
        default=PROJECT_ROOT / "runtime" / "evaluations",
    )
    parser.add_argument("--min-version", type=int, required=True)
    parser.add_argument("--max-version", type=int, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser.parse_args()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    args = parse_args()
    try:
        report = build_development_cost_lineage(
            args.evaluations_root,
            min_version=args.min_version,
            max_version=args.max_version,
        )
        json_text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        markdown_text = render_development_cost_markdown(report)
    except (EvaluationCostError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json_output is not None:
        _write(args.json_output, json_text)
    if args.markdown_output is not None:
        _write(args.markdown_output, markdown_text)
    if args.json_output is None and args.markdown_output is None:
        print(json_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
