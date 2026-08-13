#!/usr/bin/env python3
"""Run one tightly capped live prose smoke for each generated reader mode."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from time import perf_counter_ns
from typing import Any
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from archivist_modes import ArchivistMode, resolve_archivist_mode_settings  # noqa: E402
from costs import (  # noqa: E402
    UsageLedger,
    projected_provider_operation_cost_nano_usd,
    usage_scope,
)
from evidence_compiler import (  # noqa: E402
    EvidencePacket,
    MAX_EVIDENCE_CARDS,
    compile_evidence_packet,
    render_direct_evidence_answer,
)
from filters import should_skip_document  # noqa: E402
from prose_renderer import (  # noqa: E402
    EVIDENCE_PROSE_RENDERER_VERSION,
    MAX_READER_PROSE_OUTPUT_TOKENS,
    READER_PROSE_SETTINGS,
    EvidenceProseResponse,
    EvidenceProseRenderResult,
    build_evidence_prose_input,
    build_evidence_prose_instructions,
    generate_evidence_prose,
)
from retrieval import lexical_candidates  # noqa: E402
from web_project import load_project_chunks, openai_client  # noqa: E402


SMOKE_SCHEMA = "archivist.reader_mode_smoke/1"
SMOKE_QUESTION = "Who was Edwin Sandys, and what did he do?"
SMOKE_ROOT = BASE_DIR / "runtime" / "paid-smokes"
MAX_AUTHORIZED_COST_NANO_USD = 2_000_000_000
PER_CALL_COST_CEILING_NANO_USD = 350_000_000
MODE_ORDER = (
    ArchivistMode.PROFESSIONAL,
    ArchivistMode.PRETTY_PINK_PRINCESS,
    ArchivistMode.BALEFUL_BLACK_BARON,
)
EXPECTED_CALL_COUNT = len(MODE_ORDER)
AGGREGATE_HARD_CEILING_NANO_USD = (
    EXPECTED_CALL_COUNT * PER_CALL_COST_CEILING_NANO_USD
)


class ReaderModeSmokeError(RuntimeError):
    """The smoke could no longer prove its one-call or cost contract."""


@dataclass(frozen=True, slots=True)
class ModePlan:
    mode: ArchivistMode
    lens: object
    voice: object
    worldview: object
    projected_cost_nano_usd: int


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Exactly three no-retry live prose calls over one locally compiled Edwin Sandys "
            "evidence packet. Private outcomes stay below runtime/paid-smokes."
        )
    )
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument(
        "--max-cost-usd",
        type=Decimal,
        required=True,
        help="Explicit aggregate authorization; must be at least $1.05 and no more than $2.00.",
    )
    parser.add_argument(
        "--authorize-live-prose-smoke",
        action="store_true",
        help=(
            "Acknowledge exactly one no-retry OpenAI prose call for each of the three modes, "
            "using the locally selected private manuscript excerpts."
        ),
    )
    return parser


def _nano_from_usd(value: Decimal) -> int:
    return int((value * Decimal("1000000000")).to_integral_exact())


def _usd_string(nano_usd: int) -> str:
    return f"{Decimal(nano_usd) / Decimal('1000000000'):.9f}"


def _validate_authorization(*, authorized: bool, maximum_usd: Decimal) -> int:
    if not authorized:
        raise ReaderModeSmokeError(
            "live smoke requires --authorize-live-prose-smoke; no run root or client was created"
        )
    if not maximum_usd.is_finite() or maximum_usd.as_tuple().exponent < -9:
        raise ReaderModeSmokeError("--max-cost-usd must be a finite value with at most 9 decimals")
    maximum_nano = _nano_from_usd(maximum_usd)
    if maximum_nano > MAX_AUTHORIZED_COST_NANO_USD:
        raise ReaderModeSmokeError("--max-cost-usd cannot exceed the authorized $2.00")
    if maximum_nano < AGGREGATE_HARD_CEILING_NANO_USD:
        raise ReaderModeSmokeError(
            "--max-cost-usd must cover the three fixed $0.35 per-call ceilings ($1.05)"
        )
    return maximum_nano


def _validated_run_root(path: Path, *, smoke_root: Path) -> Path:
    resolved = path.resolve()
    allowed = smoke_root.resolve()
    if resolved == allowed or allowed not in resolved.parents:
        raise ReaderModeSmokeError("--run-root must be a child of runtime/paid-smokes")
    if resolved.exists():
        raise ReaderModeSmokeError("--run-root must not already exist")
    return resolved


def _write_json_no_overwrite(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
    except FileExistsError as exc:
        raise ReaderModeSmokeError(f"refusing to overwrite smoke checkpoint: {path.name}") from exc


@contextmanager
def _isolated_usage_database(path: Path):
    previous = os.environ.get("ARCHIVIST_USAGE_DB")
    os.environ["ARCHIVIST_USAGE_DB"] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("ARCHIVIST_USAGE_DB", None)
        else:
            os.environ["ARCHIVIST_USAGE_DB"] = previous


def compile_smoke_packet(
    *,
    chunks_loader: Callable[[str], list[dict[str, Any]]] = load_project_chunks,
) -> EvidencePacket:
    """Use only local BM25 and the application compiler; no planner or embedding call."""

    chunks = [
        chunk
        for chunk in chunks_loader("current")
        if not should_skip_document(str(chunk.get("document") or ""))
    ]
    ranked, _diagnostics = lexical_candidates(SMOKE_QUESTION, chunks, limit=15)
    packet = compile_evidence_packet(
        SMOKE_QUESTION,
        [dict(candidate["chunk"]) for candidate in ranked],
    )
    if len(packet.cards) != MAX_EVIDENCE_CARDS:
        raise ReaderModeSmokeError(
            f"local compiler produced {len(packet.cards)} cards; expected {MAX_EVIDENCE_CARDS}"
        )
    return packet


def _exact_provider_request(packet: EvidencePacket, mode: ArchivistMode) -> tuple[dict[str, object], tuple[object, object, object]]:
    selected, lens, voice, worldview = resolve_archivist_mode_settings(mode, None, None, None)
    if selected is not mode:
        raise ReaderModeSmokeError("reader-mode defaults resolved to a different mode")
    request = {
        "instructions": build_evidence_prose_instructions(
            mode,
            historiographical_lens=lens,
            voice=voice,
            worldview=worldview,
        ),
        "input": build_evidence_prose_input(SMOKE_QUESTION, packet.cards, mode),
        "text_format": EvidenceProseResponse,
        "max_output_tokens": MAX_READER_PROSE_OUTPUT_TOKENS,
        **READER_PROSE_SETTINGS.responses_create_kwargs(),
    }
    return request, (lens, voice, worldview)


def build_mode_plans(packet: EvidencePacket) -> tuple[ModePlan, ...]:
    """Project all three exact requests before any client can be constructed."""

    plans: list[ModePlan] = []
    for mode in MODE_ORDER:
        request, (lens, voice, worldview) = _exact_provider_request(packet, mode)
        projection = projected_provider_operation_cost_nano_usd(
            provider_kind="responses",
            request=request,
        )
        if projection > PER_CALL_COST_CEILING_NANO_USD:
            raise ReaderModeSmokeError(
                f"{mode.value} projects above its fixed $0.35 per-call ceiling"
            )
        plans.append(
            ModePlan(
                mode=mode,
                lens=lens,
                voice=voice,
                worldview=worldview,
                projected_cost_nano_usd=projection,
            )
        )
    if tuple(plan.mode for plan in plans) != MODE_ORDER:
        raise ReaderModeSmokeError("smoke mode order changed")
    if sum(plan.projected_cost_nano_usd for plan in plans) > AGGREGATE_HARD_CEILING_NANO_USD:
        raise ReaderModeSmokeError("projected aggregate exceeds the fixed $1.05 hard ceiling")
    return tuple(plans)


def _prepared_record(
    *,
    packet: EvidencePacket,
    plans: Sequence[ModePlan],
    maximum_nano: int,
) -> dict[str, object]:
    card_fingerprints = [
        hashlib.sha256(
            f"{card.card_id}\0{card.chunk_id}\0{card.text}".encode("utf-8")
        ).hexdigest()
        for card in packet.cards
    ]
    return {
        "schema": SMOKE_SCHEMA,
        "phase": "prepared",
        "question_sha256": hashlib.sha256(SMOKE_QUESTION.encode("utf-8")).hexdigest(),
        "evidence_card_count": len(packet.cards),
        "evidence_card_sha256": card_fingerprints,
        "renderer_version": EVIDENCE_PROSE_RENDERER_VERSION,
        "requested_model": READER_PROSE_SETTINGS.model,
        "reasoning_effort": READER_PROSE_SETTINGS.reasoning_effort,
        "verbosity": READER_PROSE_SETTINGS.verbosity,
        "automatic_retries": 0,
        "authorized_cost_nano_usd": maximum_nano,
        "authorized_cost_usd": _usd_string(maximum_nano),
        "per_call_cost_ceiling_nano_usd": PER_CALL_COST_CEILING_NANO_USD,
        "aggregate_hard_ceiling_nano_usd": AGGREGATE_HARD_CEILING_NANO_USD,
        "modes": [
            {
                "mode": plan.mode.value,
                "ordinal": ordinal,
                "projected_cost_nano_usd": plan.projected_cost_nano_usd,
            }
            for ordinal, plan in enumerate(plans, start=1)
        ],
    }


def _safe_outcome(
    *,
    plan: ModePlan,
    ordinal: int,
    request_id: str,
    latency_ms: float,
    status: str,
    usage: Mapping[str, object],
    answer: str | None = None,
    failure_code: str | None = None,
    error_class: str | None = None,
) -> dict[str, object]:
    return {
        "schema": SMOKE_SCHEMA,
        "phase": "outcome",
        "ordinal": ordinal,
        "mode": plan.mode.value,
        "request_id": request_id,
        "status": status,
        "failure_code": failure_code,
        "error_class": error_class,
        "latency_ms": round(latency_ms, 3),
        "usage": dict(usage),
        "displayed_answer": answer,
        "automatic_retry_count": 0,
    }


def _usage_snapshot(
    ledger: UsageLedger,
    request_id: str,
) -> tuple[dict[str, object], dict[str, int] | None, str | None]:
    """Read both accounting views or return a text-safe ledger failure marker."""

    try:
        usage = ledger.request_usage_totals(request_id)
        state = ledger.request_usage_cost_state(request_id)
    except Exception as exc:
        return {"measurement_status": "unavailable"}, None, type(exc).__name__
    return dict(usage), dict(state), None


def execute_smoke(
    *,
    run_root: Path,
    maximum_usd: Decimal,
    authorized: bool,
    smoke_root: Path = SMOKE_ROOT,
    chunks_loader: Callable[[str], list[dict[str, Any]]] = load_project_chunks,
    client_factory: Callable[[], object] = openai_client,
    prose_generator: Callable[..., EvidenceProseRenderResult] = generate_evidence_prose,
) -> dict[str, object]:
    maximum_nano = _validate_authorization(authorized=authorized, maximum_usd=maximum_usd)
    target = _validated_run_root(run_root, smoke_root=smoke_root)
    packet = compile_smoke_packet(chunks_loader=chunks_loader)
    plans = build_mode_plans(packet)

    # This is a second, deliberately blunt aggregate gate independent of request projection.
    if AGGREGATE_HARD_CEILING_NANO_USD > maximum_nano:
        raise ReaderModeSmokeError("fixed aggregate ceiling exceeds owner authorization")

    target.mkdir(parents=True, exist_ok=False)
    usage_db = target / "usage.sqlite3"
    prepared = _prepared_record(packet=packet, plans=plans, maximum_nano=maximum_nano)
    _write_json_no_overwrite(target / "prepared.json", prepared)

    outcomes: list[dict[str, object]] = []
    cumulative_cost_nano = 0
    direct_answer = render_direct_evidence_answer(packet).answer

    with _isolated_usage_database(usage_db):
        ledger = UsageLedger()
        ledger.update_settings(
            monthly_budget_usd=maximum_usd,
            warning_threshold_percent=80,
            hard_limit_enabled=True,
        )
        # Client construction happens only after authorization, local evidence, all
        # projections, and the immutable prepared checkpoint have succeeded.
        base_client = client_factory()
        with_options = getattr(base_client, "with_options", None)
        client = with_options(max_retries=0) if callable(with_options) else base_client

        for ordinal, plan in enumerate(plans, start=1):
            request_id = uuid4().hex
            intent = {
                "schema": SMOKE_SCHEMA,
                "phase": "intent",
                "ordinal": ordinal,
                "mode": plan.mode.value,
                "request_id": request_id,
                "projected_cost_nano_usd": plan.projected_cost_nano_usd,
                "request_cost_ceiling_nano_usd": PER_CALL_COST_CEILING_NANO_USD,
                "automatic_retry_allowed": False,
            }
            mode_root = target / "attempts" / f"{ordinal:02d}-{plan.mode.value}"
            _write_json_no_overwrite(mode_root / "intent.json", intent)

            started_ns = perf_counter_ns()
            try:
                with usage_scope(
                    project_id="current",
                    conversation_id=target.name,
                    turn_id=plan.mode.value,
                    request_id=request_id,
                    enforce_budget=True,
                    allow_over_budget=False,
                    request_cost_ceiling_nano_usd=PER_CALL_COST_CEILING_NANO_USD,
                ):
                    result = prose_generator(
                        client,
                        question=SMOKE_QUESTION,
                        cards=packet.cards,
                        mode=plan.mode,
                        historiographical_lens=plan.lens,
                        voice=plan.voice,
                        worldview=plan.worldview,
                    )
            except Exception as exc:
                latency_ms = max(0, perf_counter_ns() - started_ns) / 1_000_000
                usage, _cost_state, ledger_error = _usage_snapshot(ledger, request_id)
                failed = _safe_outcome(
                    plan=plan,
                    ordinal=ordinal,
                    request_id=request_id,
                    latency_ms=latency_ms,
                    status="ledger_failure" if ledger_error is not None else "aborted",
                    usage=usage,
                    error_class=ledger_error or type(exc).__name__,
                )
                _write_json_no_overwrite(mode_root / "outcome.json", failed)
                raise ReaderModeSmokeError(
                    f"{plan.mode.value} ended ambiguously; no retry or later call was made"
                ) from exc

            latency_ms = max(0, perf_counter_ns() - started_ns) / 1_000_000
            usage, cost_state, ledger_error = _usage_snapshot(ledger, request_id)
            if cost_state is None:
                failed = _safe_outcome(
                    plan=plan,
                    ordinal=ordinal,
                    request_id=request_id,
                    latency_ms=latency_ms,
                    status="ledger_failure",
                    usage=usage,
                    error_class=ledger_error or "UsageLedgerError",
                )
                _write_json_no_overwrite(mode_root / "outcome.json", failed)
                raise ReaderModeSmokeError(
                    f"{plan.mode.value} usage ledger failed; no retry or later call was made"
                )
            if (
                cost_state["event_count"] != 1
                or cost_state["unpriced_count"] != 0
                or cost_state["estimated_cost_nano_usd"] > PER_CALL_COST_CEILING_NANO_USD
            ):
                failed = _safe_outcome(
                    plan=plan,
                    ordinal=ordinal,
                    request_id=request_id,
                    latency_ms=latency_ms,
                    status="ambiguous_usage",
                    usage=usage,
                    error_class="UsageContractError",
                )
                _write_json_no_overwrite(mode_root / "outcome.json", failed)
                raise ReaderModeSmokeError(
                    f"{plan.mode.value} lacks exactly one priced usage event; "
                    "no retry or later call was made"
                )

            cumulative_cost_nano += cost_state["estimated_cost_nano_usd"]
            if cumulative_cost_nano > AGGREGATE_HARD_CEILING_NANO_USD:
                raise ReaderModeSmokeError("recorded cumulative cost exceeds the fixed hard ceiling")

            failure_code = (
                result.failure_code.value if result.failure_code is not None else None
            )
            displayed_answer = result.answer or direct_answer
            outcome = _safe_outcome(
                plan=plan,
                ordinal=ordinal,
                request_id=request_id,
                latency_ms=latency_ms,
                status=result.status.value,
                usage={
                    **usage,
                    "estimated_cost_nano_usd": cost_state["estimated_cost_nano_usd"],
                    "estimated_cost_usd_exact": _usd_string(
                        cost_state["estimated_cost_nano_usd"]
                    ),
                },
                answer=displayed_answer,
                failure_code=failure_code,
            )
            _write_json_no_overwrite(mode_root / "outcome.json", outcome)
            outcomes.append(outcome)

    summary = {
        "schema": SMOKE_SCHEMA,
        "phase": "complete",
        "question": SMOKE_QUESTION,
        "renderer_version": EVIDENCE_PROSE_RENDERER_VERSION,
        "attempt_count": len(outcomes),
        "automatic_retries": 0,
        "aggregate_hard_ceiling_nano_usd": AGGREGATE_HARD_CEILING_NANO_USD,
        "recorded_cost_nano_usd": cumulative_cost_nano,
        "recorded_cost_usd_exact": _usd_string(cumulative_cost_nano),
        "outcomes": outcomes,
    }
    _write_json_no_overwrite(target / "private-summary.json", summary)
    return summary


def _print_summary(summary: Mapping[str, object], *, run_root: Path) -> None:
    outcomes = summary.get("outcomes")
    if not isinstance(outcomes, list):
        raise ReaderModeSmokeError("completed summary has no outcomes")
    for outcome in outcomes:
        if not isinstance(outcome, Mapping):
            continue
        usage = outcome.get("usage")
        usage = usage if isinstance(usage, Mapping) else {}
        print(
            f"{outcome['mode']}: {outcome['status']}; "
            f"{float(outcome['latency_ms']) / 1000:.3f}s; "
            f"{usage.get('total_tokens', 0)} tokens; "
            f"${usage.get('estimated_cost_usd_exact', 'unknown')}"
        )
        print(str(outcome.get("displayed_answer") or "[no displayed answer]"))
    print(f"Total estimated cost: ${summary['recorded_cost_usd_exact']}")
    print(f"Private ignored results: {run_root / 'private-summary.json'}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = execute_smoke(
        run_root=args.run_root,
        maximum_usd=args.max_cost_usd,
        authorized=args.authorize_live_prose_smoke,
    )
    _print_summary(summary, run_root=args.run_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
