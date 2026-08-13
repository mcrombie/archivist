#!/usr/bin/env python3
"""Prepare, run, or read the non-gold generated-mode persona evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from persona_evaluation import (  # noqa: E402
    DEFAULT_RUN_ROOT,
    DEFAULT_USAGE_DB,
    PersonaEvaluationError,
    load_diagnostics_report,
    prepare_evaluation,
    run_evaluation,
)
from web_project import openai_client  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Separate non-gold persona evaluation. Prepare/report are offline; run requires "
            "explicit authorization and makes at most one no-retry Sol call per untouched item."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Seal the provider-free fixed manifest.")
    _common_paths(prepare)

    run = subparsers.add_parser("run", help="Run only untouched fixed persona items.")
    _common_paths(run)
    run.add_argument(
        "--authorize-live-persona-evaluation",
        action="store_true",
        help=(
            "Acknowledge four fixed no-retry Sol calls sharing the retrieval-authored-v3 "
            "$7 master ledger cap."
        ),
    )
    run.add_argument(
        "--max-cost-usd",
        type=Decimal,
        required=True,
        help="Must be exactly 7.00; this is the shared master cap, not a new allowance.",
    )

    report = subparsers.add_parser(
        "report",
        help="Validate and print the already sealed diagnostics report without provider calls.",
    )
    _common_paths(report)
    return parser


def _common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--usage-db", type=Path, default=DEFAULT_USAGE_DB)


def _live_client() -> object:
    # Match the application character route: twelve-second request timeout and
    # no SDK retries. generate_character_conversation repeats max_retries=0 at
    # its own boundary so a future caller cannot silently weaken this contract.
    return openai_client().with_options(timeout=12.0, max_retries=0)


def _print_report(report: dict[str, object]) -> None:
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "prepare":
        manifest = prepare_evaluation(run_root=args.run_root, usage_db=args.usage_db)
        print(f"Prepared non-gold persona evaluation: {args.run_root / 'prepared-manifest.json'}")
        print(f"Fixed items: {manifest['expected_provider_calls']}; provider calls made: 0")
        return 0
    if args.command == "run":
        report = run_evaluation(
            authorized=args.authorize_live_persona_evaluation,
            maximum_usd=args.max_cost_usd,
            client_factory=_live_client,
            run_root=args.run_root,
            usage_db=args.usage_db,
        )
        _print_report(report)
        return 0
    report = load_diagnostics_report(run_root=args.run_root, usage_db=args.usage_db)
    _print_report(report)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PersonaEvaluationError as exc:
        print(f"persona evaluation stopped: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
