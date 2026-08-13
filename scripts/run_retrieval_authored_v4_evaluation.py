from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from retrieval_authored_v4_evaluation import (  # noqa: E402
    EVALUATION_ID,
    MAXIMUM_DESIGN_CAP_USD,
    V4EvaluationError,
    default_paths,
    preflight,
    prepare_v4_cohort,
    run_decomposition,
    run_professional_remaining,
    run_professional_sentinel,
    run_rubric,
    run_social_suite,
    write_text_free_report,
)


DEFAULT_ROOT = BASE_DIR / "runtime" / "evaluations" / EVALUATION_ID
PAID_COMMANDS = frozenset({"sentinel", "generate-rest", "decompose", "rubric", "social"})

load_dotenv(BASE_DIR / ".env")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the separate retrieval-authored-v4 cohort. The terminal v3 "
            "timeout-diagnostic cohort is never opened or modified."
        )
    )
    parser.add_argument(
        "command",
        choices=(
            "preflight",
            "prepare",
            "sentinel",
            "generate-rest",
            "decompose",
            "rubric",
            "social",
            "report",
        ),
    )
    parser.add_argument("--run-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--product-commit",
        required=True,
        help="Clean committed retrieval-authored-v4 product identity (must be a HEAD ancestor).",
    )
    parser.add_argument(
        "--authorize-openai",
        action="store_true",
        help=(
            "Required for each paid command only after the owner gives fresh, "
            "v4-cohort-specific authorization."
        ),
    )
    parser.add_argument(
        "--max-total-cost-usd",
        required=True,
        help=(
            "Exact cumulative cap shared by generation, decomposition, rubric, "
            "social calls, and ambiguity reserves (at most 7.00)."
        ),
    )
    return parser


def _cap(args: argparse.Namespace) -> Decimal:
    try:
        cap = Decimal(args.max_total_cost_usd)
    except InvalidOperation as exc:
        raise V4EvaluationError("--max-total-cost-usd must be numeric") from exc
    if not cap.is_finite() or cap <= 0 or cap > MAXIMUM_DESIGN_CAP_USD:
        raise V4EvaluationError("cap must be positive and no greater than $7.00")
    return cap


def _client() -> object:
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        max_retries=0,
        timeout=30.0,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cap = _cap(args)
        paid = args.command in PAID_COMMANDS
        if paid and not args.authorize_openai:
            raise V4EvaluationError(
                "paid v4 commands require fresh explicit --authorize-openai"
            )
        if paid and not os.getenv("OPENAI_API_KEY", "").strip():
            raise V4EvaluationError("OPENAI_API_KEY is unavailable")
        if args.run_root.resolve() != DEFAULT_ROOT.resolve():
            raise V4EvaluationError(
                "run-of-record CLI requires the declared private v4 root"
            )
        paths = default_paths(BASE_DIR, root=args.run_root)
        cohort = prepare_v4_cohort(
            base_dir=BASE_DIR,
            paths=paths,
            maximum_usd=cap,
            product_commit=args.product_commit,
            require_clean=True,
            persist_manifest=args.command != "preflight",
        )
        if args.command == "preflight":
            result = preflight(cohort)
            print("VALID RETRIEVAL-AUTHORED-V4 PREFLIGHT")
            print(
                f"Cached-vector readiness: {result['items_ready_for_one_authoring_call']}/"
                f"{result['item_count']}; new embedding calls: 0"
            )
            print("Sentinel: H001-H010, report-only quality and latency observations")
            print("Fresh paid authorization remains required; no call was made.")
            return 0
        if args.command == "prepare":
            print("SEALED RETRIEVAL-AUTHORED-V4 COHORT MANIFEST")
            print(f"Exact cumulative cap: ${cap:.9f}")
            print("No provider call was made.")
            return 0
        if args.command == "sentinel":
            run_professional_sentinel(cohort, client=_client(), maximum_usd=cap)
            print("SEALED FIRST TEN ONCE-ONLY PROFESSIONAL OUTCOMES")
            print("Quality, success rate, latency, and cost are observations, not vetoes.")
            return 0
        if args.command == "generate-rest":
            run_professional_remaining(cohort, client=_client(), maximum_usd=cap)
            print("SEALED REMAINING 27 ONCE-ONLY PROFESSIONAL OUTCOMES")
            return 0
        if args.command == "decompose":
            run_decomposition(cohort, client=_client(), maximum_usd=cap)
            print("SEALED 37 HELD-OUT DECOMPOSITION OUTCOMES")
            return 0
        if args.command == "rubric":
            run_rubric(cohort, client=_client(), maximum_usd=cap)
            print("SEALED 37 EXPLORATORY RUBRIC DISPOSITIONS")
            return 0
        if args.command == "social":
            run_social_suite(cohort, client=_client(), maximum_usd=cap)
            print("SEALED SEPARATE FOUR-MODE SOCIAL SUITE")
            return 0
        report = write_text_free_report(cohort, maximum_usd=cap)
        print("WROTE TEXT-FREE RETRIEVAL-AUTHORED-V4 REPORT")
        print(f"Professional outcomes: {report['generation']['sealed_count']}/37")
        print(f"Accounted cost: ${report['cost']['accounted_usd_exact']}")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"V4 EVALUATION FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
