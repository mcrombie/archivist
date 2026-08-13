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

from retrieval_authored_v3_evaluation import (  # noqa: E402
    EVALUATION_ID,
    MASTER_COST_CAP_USD,
    V3EvaluationError,
    default_paths,
    freeze_decomposition_instrument,
    preflight_all_cached_items,
    prepare_v3_cohort,
    reconcile_provider_ambiguity,
    run_development_decomposition_phase,
    run_exploratory_rubric_phase,
    run_generation_phase,
    run_held_out_decomposition_phase,
    write_public_summary,
)


DEFAULT_ROOT = BASE_DIR / "runtime" / "evaluations" / EVALUATION_ID
DEFAULT_DEV_SOURCE = (
    BASE_DIR / "runtime" / "evaluations" / "evidence-planned-v24-clean-20260730-2"
)
PAID_COMMANDS = frozenset({"dev-decompose", "generate", "decompose", "rubric"})

load_dotenv(BASE_DIR / ".env")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the isolated retrieval-authored-v3 Professional evaluation. "
            "The frozen V26 runner and artifacts are never modified."
        )
    )
    parser.add_argument(
        "command",
        choices=(
            "preflight",
            "reconcile-ambiguity",
            "dev-decompose",
            "freeze",
            "generate",
            "decompose",
            "rubric",
            "report",
        ),
    )
    parser.add_argument("--run-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--development-source-root",
        type=Path,
        default=DEFAULT_DEV_SOURCE,
        help=(
            "Archived G001-G010 answer root used only to validate the decomposition "
            "instrument; these development answers are not v3 quality results."
        ),
    )
    parser.add_argument(
        "--authorize-openai",
        action="store_true",
        help="Required for a paid command after the owner authorizes its exact scope.",
    )
    parser.add_argument(
        "--max-total-cost-usd",
        type=str,
        help="Shared maximum across development, held-out, and persona calls (at most 7.00).",
    )
    return parser


def _paid_cap(args: argparse.Namespace) -> Decimal:
    if not args.authorize_openai:
        raise V3EvaluationError("paid commands require --authorize-openai")
    if args.max_total_cost_usd is None:
        raise V3EvaluationError("paid commands require --max-total-cost-usd")
    try:
        value = Decimal(args.max_total_cost_usd)
    except InvalidOperation as exc:
        raise V3EvaluationError("--max-total-cost-usd must be numeric") from exc
    if not value.is_finite() or value <= 0 or value > MASTER_COST_CAP_USD:
        raise V3EvaluationError("shared paid cap must be positive and no greater than $7.00")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise V3EvaluationError("OPENAI_API_KEY is unavailable")
    return value


def _client() -> object:
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        max_retries=0,
        timeout=20.0,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cap = _paid_cap(args) if args.command in PAID_COMMANDS else None
        if args.run_root.resolve() != DEFAULT_ROOT.resolve():
            raise V3EvaluationError(
                "the run-of-record CLI requires its declared private v3 evaluation root"
            )
        paths = default_paths(BASE_DIR, root=args.run_root)
        cohort = prepare_v3_cohort(
            base_dir=BASE_DIR,
            paths=paths,
            require_clean=True,
            persist_manifest=args.command != "preflight",
            reconcile_ambiguity=args.command == "reconcile-ambiguity",
        )
        if args.command == "preflight":
            readiness = preflight_all_cached_items(cohort)
            print("VALID RETRIEVAL-AUTHORED-V3 EVALUATION PREFLIGHT")
            print(f"Items: {len(cohort.items)}")
            print("Query embeddings: validated cache; zero new embedding calls")
            print(
                "Identity: product "
                f"{cohort.manifest['system_under_test']['product_commit']} / harness "
                f"{cohort.manifest['system_under_test']['harness_commit']}"
            )
            print("Classification: reused locked benchmark, not pristine held-out")
            print(
                "Decomposer development source: "
                f"{args.development_source_root} (G001-G010 instrument validation only; "
                "not v3 answer-quality evidence)"
            )
            print("Held-out generation is blocked until that instrument is frozen.")
            print(
                "One-call readiness: "
                f"{readiness['items_ready_for_one_authoring_call']}/"
                f"{readiness['item_count']} items; minimum dossier units "
                f"{readiness['minimum_dossier_units']}"
            )
            return 0
        if args.command == "reconcile-ambiguity":
            value = reconcile_provider_ambiguity(cohort, base_dir=BASE_DIR)
            print(f"SEALED {value['turn_id']} ZERO-EVENT AMBIGUITY CONTINUATION")
            print(
                f"{value['turn_id']} will not be retried; "
                f"continuation begins with {value.get('next_turn_id') or value['next_item_id']}."
            )
            print(
                "Reserved nano-USD: "
                f"{value['projected_worst_case_reserved_nano_usd']}"
            )
            print(
                "Cumulative reserved nano-USD: "
                f"{value['cumulative_reserved_nano_usd']}"
            )
            print(
                "Effective tracked ceiling nano-USD: "
                f"{value['effective_tracked_ceiling_nano_usd']}"
            )
            return 0
        if args.command == "dev-decompose":
            assert cap is not None
            run_development_decomposition_phase(
                paths,
                source_root=args.development_source_root,
                client=_client(),
                maximum_usd=cap,
            )
            print("SEALED G001-G010 DECOMPOSITION DEVELOPMENT OUTCOMES")
            return 0
        if args.command == "freeze":
            value = freeze_decomposition_instrument(paths)
            print(
                "FROZEN DECOMPOSITION INSTRUMENT: "
                f"{value['instrument']['instrument_version']}"
            )
            return 0
        if args.command == "generate":
            assert cap is not None
            run_generation_phase(cohort, client=_client(), maximum_usd=cap)
            print("SEALED 37 PROFESSIONAL GENERATION OUTCOMES")
            return 0
        if args.command == "decompose":
            assert cap is not None
            run_held_out_decomposition_phase(cohort, client=_client(), maximum_usd=cap)
            print("SEALED 37 HELD-OUT DECOMPOSITION OUTCOMES")
            return 0
        if args.command == "rubric":
            assert cap is not None
            run_exploratory_rubric_phase(cohort, client=_client(), maximum_usd=cap)
            print("SEALED EXPLORATORY UNCALIBRATED RUBRIC OUTCOMES")
            return 0
        summary = write_public_summary(cohort)
        print("WROTE RETRIEVAL-AUTHORED-V3 PUBLIC-SAFE SUMMARY")
        print(f"Items: {summary['item_count']}")
        print(f"Recorded total cost: ${summary['cost']['recorded_total_usd']:.8f}")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"V3 EVALUATION FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
