"""Paired Standard-versus-Fast latency comparison for the current product path.

This protocol is deliberately separate from the three-question latency smoke.
It sends the same three registered development questions through Professional
once per service tier in a frozen, counterbalanced order. Artifacts retain only
operational measurements, hashes, and mechanical citation counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from uuid import uuid4

from archivist_modes import ArchivistMode
from authored_response import (
    AUTHORED_ANSWER_LENGTH_POLICY_VERSION,
    AUTHORED_RESPONSE_INPUT_SCHEMA,
    AUTHORED_RESPONSE_OUTPUT_SCHEMA,
    AUTHORED_RESPONSE_POLICY_VERSION,
    AUTHORED_RESPONSE_SETTINGS,
    authored_response_prompt_metadata,
)
from costs import (
    PRICING_VERSION,
    PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD,
    PUBLIC_RAG_REQUEST_COST_CEILING_VERSION,
    UsageLedger,
    usage_scope,
)
from evaluation_scoring import CitationAudit, audit_citations
from evidence_dossier import (
    DEFAULT_HARD_EVIDENCE_TOKEN_LIMIT,
    DEFAULT_MAX_DOSSIER_UNITS,
    DEFAULT_MIN_DOSSIER_UNITS,
    DEFAULT_TARGET_EVIDENCE_TOKENS,
)
from product_latency_smoke import (
    CORPUS_MANIFEST,
    DEVELOPMENT_REGISTRY,
    QUESTION_FIXTURE,
    LatencyQuestion,
    clean_git_identity,
    load_latency_questions,
)
from public_telemetry import PUBLIC_EMBEDDING_MODEL, PUBLIC_EVIDENCE_RETRIEVAL_KIND


BASE_DIR = Path(__file__).resolve().parent.parent
COMPARISON_ROOT = (
    BASE_DIR / "runtime" / "evaluations" / "product-fast-latency-comparison-v1"
)

PROTOCOL_VERSION = "product-fast-latency-comparison-v1"
PREPARED_SCHEMA = "archivist.product_fast_latency_comparison_manifest/1"
ATTEMPT_INTENT_SCHEMA = (
    "archivist.product_fast_latency_comparison_attempt_intent/1"
)
ATTEMPT_OUTCOME_SCHEMA = (
    "archivist.product_fast_latency_comparison_attempt_outcome/1"
)
REPORT_SCHEMA = "archivist.product_fast_latency_comparison_report/1"

STANDARD_ARM = "standard"
FAST_ARM = "fast"
ARM_SERVICE_TIERS = {STANDARD_ARM: "default", FAST_ARM: "priority"}
EXPECTED_ATTEMPT_COUNT = 6
EXPECTED_PROVIDER_OPERATIONS = {"answer_generation": 1, "query_embedding": 1}
EXPECTED_PUBLIC_REQUEST_COST_CEILING_VERSION = "public-rag-request-ceiling-v1"
PER_ATTEMPT_COST_CEILING_NANO_USD = 2_000_000_000
AGGREGATE_HARD_CEILING_NANO_USD = (
    EXPECTED_ATTEMPT_COUNT * PER_ATTEMPT_COST_CEILING_NANO_USD
)
PRIMARY_MEDIAN_RATIO_MAXIMUM = 0.70
PRIMARY_MINIMUM_FASTER_PAIRS = 2
VALID_CONTENT_OUTCOMES = {"valid_complete", "valid_partial"}


class ProductFastLatencyComparisonError(RuntimeError):
    """The paired comparison could no longer prove its closed contract."""


@dataclass(frozen=True, slots=True)
class AttemptSpec:
    ordinal: int
    question: LatencyQuestion
    arm: str
    requested_service_tier: str

    def text_free_binding(self) -> dict[str, object]:
        return {
            **self.question.text_free_binding(),
            "question_ordinal": self.question.ordinal,
            "ordinal": self.ordinal,
            "arm": self.arm,
            "requested_answer_generation_service_tier": (
                self.requested_service_tier
            ),
        }


def frozen_schedule(
    questions: Sequence[LatencyQuestion],
) -> tuple[AttemptSpec, ...]:
    """Return the exact counterbalanced six-attempt order."""

    if len(questions) != 3:
        raise ProductFastLatencyComparisonError(
            "comparison schedule requires exactly three questions"
        )
    arm_order = (
        (STANDARD_ARM, FAST_ARM),
        (FAST_ARM, STANDARD_ARM),
        (STANDARD_ARM, FAST_ARM),
    )
    schedule: list[AttemptSpec] = []
    ordinal = 0
    for question, pair_order in zip(questions, arm_order, strict=True):
        for arm in pair_order:
            ordinal += 1
            schedule.append(
                AttemptSpec(
                    ordinal=ordinal,
                    question=question,
                    arm=arm,
                    requested_service_tier=ARM_SERVICE_TIERS[arm],
                )
            )
    return tuple(schedule)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _sealed(value: Mapping[str, object]) -> dict[str, object]:
    payload = dict(value)
    payload.pop("artifact_sha256", None)
    payload["artifact_sha256"] = hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()
    return payload


def _write_json_no_overwrite(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
    except FileExistsError as exc:
        raise ProductFastLatencyComparisonError(
            f"refusing to overwrite comparison artifact: {path.name}"
        ) from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _usd_string(nano_usd: int) -> str:
    return f"{Decimal(nano_usd) / Decimal('1000000000'):.9f}"


def _nano_from_usd(value: Decimal) -> int:
    return int((value * Decimal("1000000000")).to_integral_exact())


def validate_authorization(*, authorized: bool, maximum_usd: Decimal) -> int:
    """Require the exact twelve-dollar six-attempt defensive ceiling."""

    if not authorized:
        raise ProductFastLatencyComparisonError(
            "live comparison requires --authorize-openai-fast-latency-comparison"
        )
    if (
        PUBLIC_RAG_REQUEST_COST_CEILING_VERSION
        != EXPECTED_PUBLIC_REQUEST_COST_CEILING_VERSION
        or PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD
        != PER_ATTEMPT_COST_CEILING_NANO_USD
    ):
        raise ProductFastLatencyComparisonError(
            "the product request-cost ceiling changed; open a new comparison protocol"
        )
    if not maximum_usd.is_finite() or maximum_usd.as_tuple().exponent < -9:
        raise ProductFastLatencyComparisonError(
            "--max-total-cost-usd must be finite with at most 9 decimals"
        )
    try:
        maximum_nano = _nano_from_usd(maximum_usd)
    except (InvalidOperation, ValueError) as exc:
        raise ProductFastLatencyComparisonError(
            "invalid --max-total-cost-usd"
        ) from exc
    if maximum_nano != AGGREGATE_HARD_CEILING_NANO_USD:
        raise ProductFastLatencyComparisonError(
            "--max-total-cost-usd must equal the fixed six-attempt ceiling ($12.00)"
        )
    return maximum_nano


def _validated_run_root(path: Path, *, comparison_root: Path) -> Path:
    resolved = path.resolve()
    allowed = comparison_root.resolve()
    if resolved == allowed or allowed not in resolved.parents:
        raise ProductFastLatencyComparisonError(
            "--run-root must be a new child of "
            "runtime/evaluations/product-fast-latency-comparison-v1"
        )
    if resolved.exists():
        raise ProductFastLatencyComparisonError(
            "--run-root already exists; ambiguous attempts are never resumed"
        )
    return resolved


def _prepared_manifest(
    *,
    schedule: Sequence[AttemptSpec],
    maximum_nano: int,
    identity: Mapping[str, str],
    question_fixture: Path,
    development_registry: Path,
) -> dict[str, object]:
    return _sealed(
        {
            "schema": PREPARED_SCHEMA,
            "protocol_version": PROTOCOL_VERSION,
            "system_identity": {
                **dict(identity),
                "answer_policy_version": AUTHORED_RESPONSE_POLICY_VERSION,
                "authored_response_input_schema": AUTHORED_RESPONSE_INPUT_SCHEMA,
                "authored_response_output_schema": AUTHORED_RESPONSE_OUTPUT_SCHEMA,
                "answer_length_policy_version": (
                    AUTHORED_ANSWER_LENGTH_POLICY_VERSION
                ),
                "requested_model": AUTHORED_RESPONSE_SETTINGS.model,
                "reasoning_effort": (
                    AUTHORED_RESPONSE_SETTINGS.reasoning_effort
                ),
                "verbosity": AUTHORED_RESPONSE_SETTINGS.verbosity,
                "mode": ArchivistMode.PROFESSIONAL.value,
                "turn_context": "fresh_first_turn",
                "authored_response_prompt": authored_response_prompt_metadata(
                    ArchivistMode.PROFESSIONAL
                ),
                "evidence_retrieval_kind": PUBLIC_EVIDENCE_RETRIEVAL_KIND,
                "embedding_model": PUBLIC_EMBEDDING_MODEL,
                "retrieval_dossier": {
                    "minimum_units": DEFAULT_MIN_DOSSIER_UNITS,
                    "maximum_units": DEFAULT_MAX_DOSSIER_UNITS,
                    "target_evidence_tokens": DEFAULT_TARGET_EVIDENCE_TOKENS,
                    "hard_evidence_token_limit": DEFAULT_HARD_EVIDENCE_TOKEN_LIMIT,
                },
                "question_fixture_sha256": _sha256_file(question_fixture),
                "development_registry_sha256": _sha256_file(
                    development_registry
                ),
                "corpus_manifest_sha256": _sha256_file(CORPUS_MANIFEST),
                "dependency_lock_sha256": _sha256_file(BASE_DIR / "uv.lock"),
            },
            "execution_contract": {
                "attempt_count": EXPECTED_ATTEMPT_COUNT,
                "automatic_retries": 0,
                "resume_allowed": False,
                "expected_provider_operations_per_attempt": dict(
                    EXPECTED_PROVIDER_OPERATIONS
                ),
                "request_cost_ceiling_version": (
                    PUBLIC_RAG_REQUEST_COST_CEILING_VERSION
                ),
                "per_attempt_cost_ceiling_nano_usd": (
                    PER_ATTEMPT_COST_CEILING_NANO_USD
                ),
                "aggregate_hard_ceiling_nano_usd": (
                    AGGREGATE_HARD_CEILING_NANO_USD
                ),
                "authorized_cost_nano_usd": maximum_nano,
                "authorized_cost_usd": _usd_string(maximum_nano),
                "primary_median_answer_generation_ratio_maximum": (
                    PRIMARY_MEDIAN_RATIO_MAXIMUM
                ),
                "primary_minimum_faster_pairs": (
                    PRIMARY_MINIMUM_FASTER_PAIRS
                ),
                "promotion_decision_owner": "owner",
                "service_tier_contract": {
                    "arm_requested_and_required_returned_tiers": dict(
                        ARM_SERVICE_TIERS
                    ),
                    "embedding_requested_service_tier": None,
                    "embedding_required_returned_service_tier": None,
                    "pricing_version": PRICING_VERSION,
                },
            },
            "schedule": [attempt.text_free_binding() for attempt in schedule],
        }
    )


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


def _default_answer_runner(
    question: str,
    *,
    archivist_mode: ArchivistMode,
    history: Sequence[Mapping[str, object]],
    application_compiled: bool,
) -> object:
    from web_project import answer_project_question_result

    return answer_project_question_result(
        "current",
        question,
        archivist_mode=archivist_mode,
        history=history,
        application_compiled=application_compiled,
    )


def _safe_generation_trace(result: object | None) -> dict[str, object]:
    diagnostics = getattr(result, "diagnostics", None)
    if not isinstance(diagnostics, Mapping):
        return {}
    generation = diagnostics.get("generation")
    return dict(generation) if isinstance(generation, Mapping) else {}


def _safe_stage_timings(result: object | None) -> dict[str, float]:
    diagnostics = getattr(result, "diagnostics", None)
    raw = diagnostics.get("stage_timings_ms") if isinstance(diagnostics, Mapping) else None
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(key): round(float(value), 3)
        for key, value in raw.items()
        if isinstance(key, str)
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value >= 0
    }


def _usage_snapshot(
    ledger: UsageLedger,
    request_id: str,
) -> tuple[dict[str, object], dict[str, int], tuple[dict[str, object], ...]]:
    try:
        totals = dict(ledger.request_usage_totals(request_id))
        state = dict(ledger.request_usage_cost_state(request_id))
        events = tuple(dict(event) for event in ledger.request_usage_events(request_id))
    except Exception as exc:
        raise ProductFastLatencyComparisonError(
            "usage ledger could not be read"
        ) from exc
    return totals, state, events


def _event_projection(events: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "operation": event.get("operation"),
            "requested_model": event.get("requested_model"),
            "actual_model": event.get("actual_model"),
            "requested_service_tier": event.get("requested_service_tier"),
            "actual_service_tier": event.get("actual_service_tier"),
            "input_tokens": int(event.get("input_tokens", 0)),
            "cached_tokens": int(event.get("cached_tokens", 0)),
            "cache_write_tokens": int(event.get("cache_write_tokens", 0)),
            "output_tokens": int(event.get("output_tokens", 0)),
            "reasoning_tokens": int(event.get("reasoning_tokens", 0)),
            "total_tokens": int(event.get("total_tokens", 0)),
            "estimated_cost_nano_usd": (
                int(event["estimated_cost_nano_usd"])
                if event.get("estimated_cost_nano_usd") is not None
                else None
            ),
            "pricing_version": event.get("pricing_version"),
            "unpriced": int(event.get("unpriced", 0)),
        }
        for event in events
    ]


def _usage_contract_error(
    *,
    events: Sequence[Mapping[str, object]],
    totals: Mapping[str, object],
    state: Mapping[str, int],
    requested_service_tier: str,
) -> str | None:
    if len(events) != 2 or int(state.get("event_count", -1)) != 2:
        return "provider_event_count_mismatch"
    counts = Counter(str(event.get("operation")) for event in events)
    if dict(counts) != EXPECTED_PROVIDER_OPERATIONS:
        return "provider_operation_mismatch"
    if totals.get("operation_event_counts") != EXPECTED_PROVIDER_OPERATIONS:
        return "provider_operation_totals_mismatch"
    if int(state.get("unpriced_count", -1)) != 0:
        return "unpriced_provider_event"
    if int(state.get("estimated_cost_nano_usd", -1)) < 0:
        return "invalid_recorded_cost"
    if int(state.get("estimated_cost_nano_usd", 0)) > PER_ATTEMPT_COST_CEILING_NANO_USD:
        return "attempt_cost_ceiling_exceeded"

    by_operation = {str(event.get("operation")): event for event in events}
    embedding = by_operation["query_embedding"]
    generation = by_operation["answer_generation"]
    if (
        embedding.get("requested_model") != PUBLIC_EMBEDDING_MODEL
        or embedding.get("actual_model") != PUBLIC_EMBEDDING_MODEL
    ):
        return "embedding_model_mismatch"
    if (
        embedding.get("requested_service_tier") is not None
        or embedding.get("actual_service_tier") is not None
    ):
        return "embedding_service_tier_mismatch"
    if (
        generation.get("requested_model") != AUTHORED_RESPONSE_SETTINGS.model
        or generation.get("actual_model") != AUTHORED_RESPONSE_SETTINGS.model
    ):
        return "answer_generation_model_mismatch"
    if generation.get("requested_service_tier") != requested_service_tier:
        return "requested_service_tier_mismatch"
    if generation.get("actual_service_tier") != requested_service_tier:
        return "returned_service_tier_mismatch"
    if any(int(event.get("unpriced", 0)) != 0 for event in events):
        return "unpriced_provider_event"
    if any(event.get("pricing_version") != PRICING_VERSION for event in events):
        return "pricing_version_mismatch"
    event_cost = sum(int(event.get("estimated_cost_nano_usd", 0)) for event in events)
    if event_cost != int(state.get("estimated_cost_nano_usd", -1)):
        return "event_cost_total_mismatch"
    return None


def _citation_projection(answer: str, *, source_count: int) -> dict[str, int]:
    audit: CitationAudit = audit_citations(answer, source_count=source_count)
    return {
        "well_formed_group_count": audit.well_formed_group_count,
        "source_reference_count": audit.source_reference_count,
        "malformed_bracket_token_count": audit.malformed_bracket_token_count,
        "resolvable_group_count": audit.resolvable_group_count,
        "resolvable_reference_count": audit.resolvable_reference_count,
        "out_of_range_reference_count": audit.out_of_range_reference_count,
    }


def _outcome(
    *,
    attempt: AttemptSpec,
    request_id: str,
    measurement_status: str,
    wall_latency_ms: float,
    usage: Mapping[str, object],
    state: Mapping[str, int] | None,
    events: Sequence[Mapping[str, object]],
    result: object | None = None,
    error_class: str | None = None,
    citation: Mapping[str, int] | None = None,
) -> dict[str, object]:
    generation = _safe_generation_trace(result)
    timings = _safe_stage_timings(result)
    answer = getattr(result, "answer", None) if result is not None else None
    answer_text = answer if isinstance(answer, str) else ""
    final_chunks = getattr(result, "final_chunks", ()) if result is not None else ()
    source_count = len(final_chunks) if isinstance(final_chunks, Sequence) else 0
    cost_nano = int(state.get("estimated_cost_nano_usd", 0)) if state else 0
    return _sealed(
        {
            "schema": ATTEMPT_OUTCOME_SCHEMA,
            **attempt.text_free_binding(),
            "request_id": request_id,
            "measurement_status": measurement_status,
            "product_status": getattr(result, "status", None),
            "fallback_code": generation.get("fallback_code"),
            "generation_status": generation.get("status"),
            "generation_validation_result": generation.get("validation_result"),
            "content_outcome": generation.get("content_outcome"),
            "observed_answer_length_profile": generation.get(
                "answer_length_profile"
            ),
            "wall_latency_ms": round(max(0.0, wall_latency_ms), 3),
            "stage_timings_ms": timings,
            "source_count": source_count,
            "citation_audit": dict(citation or {}),
            "answer_sha256": (
                hashlib.sha256(answer_text.encode("utf-8")).hexdigest()
                if answer_text
                else None
            ),
            "answer_character_count": len(answer_text),
            "usage": {
                **dict(usage),
                "estimated_cost_nano_usd": cost_nano,
                "estimated_cost_usd_exact": _usd_string(cost_nano),
                "events": _event_projection(events),
            },
            "error_class": error_class,
            "automatic_retry_count": 0,
        }
    )


def _metric_summary(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "minimum_ms": None,
            "median_ms": None,
            "maximum_ms": None,
        }
    return {
        "count": len(values),
        "minimum_ms": round(min(values), 3),
        "median_ms": round(float(median(values)), 3),
        "maximum_ms": round(max(values), 3),
    }


def _arm_usage(outcomes: Sequence[Mapping[str, object]], arm: str) -> dict[str, object]:
    selected = [item for item in outcomes if item.get("arm") == arm]
    fields = (
        "input_tokens",
        "cached_tokens",
        "cache_write_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
    )
    token_totals = {
        field: sum(
            int(item.get("usage", {}).get(field, 0))
            for item in selected
            if isinstance(item.get("usage"), Mapping)
        )
        for field in fields
    }
    cost_nano = sum(
        int(item.get("usage", {}).get("estimated_cost_nano_usd", 0))
        for item in selected
        if isinstance(item.get("usage"), Mapping)
    )
    return {
        "attempt_count": len(selected),
        **token_totals,
        "recorded_cost_nano_usd": cost_nano,
        "recorded_cost_usd_exact": _usd_string(cost_nano),
    }


def _mechanical_item_passes(item: Mapping[str, object]) -> bool:
    citation = item.get("citation_audit")
    if not isinstance(citation, Mapping):
        return False
    references = int(citation.get("source_reference_count", 0))
    return (
        item.get("measurement_status") == "complete"
        and item.get("product_status") == "retrieval_authored"
        and item.get("fallback_code") is None
        and item.get("generation_status") == "generated"
        and item.get("generation_validation_result") == "valid"
        and item.get("content_outcome") in VALID_CONTENT_OUTCOMES
        and references >= 1
        and int(citation.get("resolvable_reference_count", 0)) == references
        and int(citation.get("out_of_range_reference_count", 0)) == 0
        and int(citation.get("malformed_bracket_token_count", 0)) == 0
    )


def build_report(outcomes: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Build the text-free paired report after six unambiguous attempts."""

    if len(outcomes) != EXPECTED_ATTEMPT_COUNT:
        raise ProductFastLatencyComparisonError(
            "report requires exactly six completed outcomes"
        )
    if [int(item.get("ordinal", -1)) for item in outcomes] != list(
        range(1, EXPECTED_ATTEMPT_COUNT + 1)
    ):
        raise ProductFastLatencyComparisonError("report attempt order changed")
    observed_schedule = [
        (int(item.get("question_ordinal", -1)), str(item.get("arm")))
        for item in outcomes
    ]
    expected_schedule = [
        (1, STANDARD_ARM),
        (1, FAST_ARM),
        (2, FAST_ARM),
        (2, STANDARD_ARM),
        (3, STANDARD_ARM),
        (3, FAST_ARM),
    ]
    if observed_schedule != expected_schedule:
        raise ProductFastLatencyComparisonError("report schedule changed")

    by_arm = {
        arm: [item for item in outcomes if item.get("arm") == arm]
        for arm in (STANDARD_ARM, FAST_ARM)
    }
    if any(len(items) != 3 for items in by_arm.values()):
        raise ProductFastLatencyComparisonError(
            "report requires three observations per arm"
        )
    paired: list[dict[str, object]] = []
    raw_ratios: list[float] = []
    for item_id in dict.fromkeys(str(item.get("item_id")) for item in outcomes):
        pair = [item for item in outcomes if item.get("item_id") == item_id]
        arms = {str(item.get("arm")): item for item in pair}
        if len(pair) != 2 or set(arms) != {STANDARD_ARM, FAST_ARM}:
            raise ProductFastLatencyComparisonError(
                f"report pair is incomplete for {item_id}"
            )
        standard_generation = float(
            arms[STANDARD_ARM]["stage_timings_ms"]["answer_generation"]
        )
        fast_generation = float(
            arms[FAST_ARM]["stage_timings_ms"]["answer_generation"]
        )
        if standard_generation <= 0 or fast_generation <= 0:
            raise ProductFastLatencyComparisonError(
                "paired generation latencies must be positive"
            )
        ratio = fast_generation / standard_generation
        standard_usage = arms[STANDARD_ARM].get("usage")
        fast_usage = arms[FAST_ARM].get("usage")
        if not isinstance(standard_usage, Mapping) or not isinstance(
            fast_usage, Mapping
        ):
            raise ProductFastLatencyComparisonError(
                f"report usage is missing for {item_id}"
            )
        standard_cost = int(standard_usage.get("estimated_cost_nano_usd", 0))
        fast_cost = int(fast_usage.get("estimated_cost_nano_usd", 0))
        pair_cost_ratio = None if standard_cost <= 0 else fast_cost / standard_cost
        raw_ratios.append(ratio)
        paired.append(
            {
                "item_id": item_id,
                "question_sha256": arms[STANDARD_ARM].get("question_sha256"),
                "answer_length_profile": arms[STANDARD_ARM].get(
                    "observed_answer_length_profile"
                ),
                "standard_answer_generation_ms": round(standard_generation, 3),
                "fast_answer_generation_ms": round(fast_generation, 3),
                "fast_to_standard_ratio": round(ratio, 6),
                "fast_reduction_fraction": round(1.0 - ratio, 6),
                "fast_was_faster": fast_generation < standard_generation,
                "standard_recorded_cost_nano_usd": standard_cost,
                "standard_recorded_cost_usd_exact": _usd_string(standard_cost),
                "fast_recorded_cost_nano_usd": fast_cost,
                "fast_recorded_cost_usd_exact": _usd_string(fast_cost),
                "fast_minus_standard_cost_nano_usd": fast_cost - standard_cost,
                "fast_to_standard_recorded_cost_ratio": (
                    None
                    if pair_cost_ratio is None
                    else round(pair_cost_ratio, 6)
                ),
                "standard_output_tokens": int(
                    standard_usage.get("output_tokens", 0)
                ),
                "fast_output_tokens": int(fast_usage.get("output_tokens", 0)),
            }
        )

    median_ratio = float(median(raw_ratios))
    faster_pairs = sum(bool(item["fast_was_faster"]) for item in paired)
    mechanical_pass_count = sum(_mechanical_item_passes(item) for item in outcomes)
    mechanical_gate_passed = mechanical_pass_count == EXPECTED_ATTEMPT_COUNT
    latency_gate_passed = (
        median_ratio <= PRIMARY_MEDIAN_RATIO_MAXIMUM
        and faster_pairs >= PRIMARY_MINIMUM_FASTER_PAIRS
    )

    arm_usage = {
        arm: _arm_usage(outcomes, arm) for arm in (STANDARD_ARM, FAST_ARM)
    }
    standard_cost = int(arm_usage[STANDARD_ARM]["recorded_cost_nano_usd"])
    fast_cost = int(arm_usage[FAST_ARM]["recorded_cost_nano_usd"])
    cost_ratio = None if standard_cost <= 0 else fast_cost / standard_cost

    operation_counts: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    fallback_codes: Counter[str] = Counter()
    total_cost = 0
    for item in outcomes:
        status_counts[str(item.get("product_status"))] += 1
        if item.get("fallback_code") is not None:
            fallback_codes[str(item.get("fallback_code"))] += 1
        usage = item.get("usage")
        if not isinstance(usage, Mapping):
            continue
        total_cost += int(usage.get("estimated_cost_nano_usd", 0))
        raw_counts = usage.get("operation_event_counts")
        if isinstance(raw_counts, Mapping):
            operation_counts.update(
                {str(key): int(value) for key, value in raw_counts.items()}
            )
        events = usage.get("events")
        if isinstance(events, Sequence):
            for event in events:
                if (
                    isinstance(event, Mapping)
                    and event.get("operation") == "answer_generation"
                ):
                    tier_counts[str(event.get("actual_service_tier"))] += 1

    fallback_count = sum(
        1
        for item in outcomes
        if "fallback" in str(item.get("product_status") or "")
    )

    report = {
        "schema": REPORT_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "attempt_count": len(outcomes),
        "automatic_retries": 0,
        "latency_ms_by_arm": {
            arm: _metric_summary(
                [float(item["wall_latency_ms"]) for item in items]
            )
            for arm, items in by_arm.items()
        },
        "answer_generation_latency_ms_by_arm": {
            arm: _metric_summary(
                [
                    float(item["stage_timings_ms"]["answer_generation"])
                    for item in items
                ]
            )
            for arm, items in by_arm.items()
        },
        "paired_answer_generation": paired,
        "primary_median_fast_to_standard_ratio": round(median_ratio, 6),
        "primary_median_fast_reduction_fraction": round(
            1.0 - median_ratio, 6
        ),
        "primary_faster_pair_count": faster_pairs,
        "primary_pair_count": len(paired),
        "primary_median_ratio_maximum": PRIMARY_MEDIAN_RATIO_MAXIMUM,
        "primary_minimum_faster_pairs": PRIMARY_MINIMUM_FASTER_PAIRS,
        "latency_gate_passed": latency_gate_passed,
        "mechanical_gate": {
            "passed": mechanical_gate_passed,
            "passing_attempt_count": mechanical_pass_count,
            "required_attempt_count": EXPECTED_ATTEMPT_COUNT,
            "requirements": {
                "retrieval_authored": True,
                "generation_valid_complete_or_partial": True,
                "fallback_count": 0,
                "minimum_citation_references_per_answer": 1,
                "all_citation_references_resolvable": True,
                "malformed_bracket_tokens": 0,
            },
        },
        "comparison_gate_passed": mechanical_gate_passed and latency_gate_passed,
        "promotion_decision": "owner_pending",
        "status_counts": dict(sorted(status_counts.items())),
        "fallback_count": fallback_count,
        "fallback_code_counts": dict(sorted(fallback_codes.items())),
        "provider_operation_event_counts": dict(sorted(operation_counts.items())),
        "answer_generation_actual_service_tier_counts": dict(
            sorted(tier_counts.items())
        ),
        "usage_by_arm": arm_usage,
        "fast_to_standard_recorded_cost_ratio": (
            None if cost_ratio is None else round(cost_ratio, 6)
        ),
        "recorded_cost_nano_usd": total_cost,
        "recorded_cost_usd_exact": _usd_string(total_cost),
        "aggregate_hard_ceiling_nano_usd": AGGREGATE_HARD_CEILING_NANO_USD,
        "items": [
            {
                "ordinal": item.get("ordinal"),
                "item_id": item.get("item_id"),
                "question_sha256": item.get("question_sha256"),
                "arm": item.get("arm"),
                "requested_answer_generation_service_tier": item.get(
                    "requested_answer_generation_service_tier"
                ),
                "product_status": item.get("product_status"),
                "fallback_code": item.get("fallback_code"),
                "generation_status": item.get("generation_status"),
                "generation_validation_result": item.get(
                    "generation_validation_result"
                ),
                "content_outcome": item.get("content_outcome"),
                "answer_length_profile": item.get(
                    "observed_answer_length_profile"
                ),
                "wall_latency_ms": item.get("wall_latency_ms"),
                "answer_generation_latency_ms": item.get(
                    "stage_timings_ms", {}
                ).get("answer_generation"),
                "source_count": item.get("source_count"),
                "citation_audit": item.get("citation_audit"),
                "mechanical_gate_passed": _mechanical_item_passes(item),
            }
            for item in outcomes
        ],
    }
    return _sealed(report)


def _render_report_markdown(report: Mapping[str, object]) -> str:
    wall = report["latency_ms_by_arm"]
    generation = report["answer_generation_latency_ms_by_arm"]
    assert isinstance(wall, Mapping) and isinstance(generation, Mapping)
    lines = [
        "# Product Fast latency comparison",
        "",
        f"- Protocol: `{report['protocol_version']}`",
        f"- Attempts: {report['attempt_count']} (automatic retries: 0)",
        (
            "- Primary median Fast/Standard answer-generation ratio: "
            f"{report['primary_median_fast_to_standard_ratio']}"
        ),
        (
            "- Fast was faster in "
            f"{report['primary_faster_pair_count']}/{report['primary_pair_count']} pairs"
        ),
        f"- Latency gate passed: {report['latency_gate_passed']}",
        f"- Mechanical gate passed: {report['mechanical_gate']['passed']}",
        f"- Comparison gate passed: {report['comparison_gate_passed']}",
        f"- Promotion decision: `{report['promotion_decision']}`",
        f"- Recorded cost: ${report['recorded_cost_usd_exact']}",
        "",
        "## Latency by arm",
        "",
    ]
    for arm in (STANDARD_ARM, FAST_ARM):
        arm_wall = wall[arm]
        arm_generation = generation[arm]
        lines.extend(
            [
                (
                    f"- {arm} wall: min {arm_wall['minimum_ms']} ms, "
                    f"median {arm_wall['median_ms']} ms, "
                    f"max {arm_wall['maximum_ms']} ms (n={arm_wall['count']})"
                ),
                (
                    f"- {arm} answer generation: "
                    f"min {arm_generation['minimum_ms']} ms, "
                    f"median {arm_generation['median_ms']} ms, "
                    f"max {arm_generation['maximum_ms']} ms "
                    f"(n={arm_generation['count']})"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "This six-attempt paired sample is a directional operational comparison, "
            "not an SLA or a general quality claim.",
            "No question, answer, source, manuscript, or provider-error text is stored here.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_fast_latency_comparison(
    *,
    run_root: Path,
    maximum_usd: Decimal,
    authorized: bool,
    comparison_root: Path = COMPARISON_ROOT,
    question_fixture: Path = QUESTION_FIXTURE,
    development_registry: Path = DEVELOPMENT_REGISTRY,
    identity_provider: Callable[[], Mapping[str, str]] = clean_git_identity,
    answer_runner: Callable[..., object] = _default_answer_runner,
    ledger_factory: Callable[[], UsageLedger] = UsageLedger,
) -> dict[str, object]:
    """Execute the exact six calls once, fail-closing on measurement ambiguity."""

    maximum_nano = validate_authorization(
        authorized=authorized,
        maximum_usd=maximum_usd,
    )
    target = _validated_run_root(run_root, comparison_root=comparison_root)
    questions = load_latency_questions(
        question_fixture=question_fixture,
        development_registry=development_registry,
    )
    schedule = frozen_schedule(questions)
    identity = dict(identity_provider())
    manifest = _prepared_manifest(
        schedule=schedule,
        maximum_nano=maximum_nano,
        identity=identity,
        question_fixture=question_fixture,
        development_registry=development_registry,
    )

    target.mkdir(parents=True, exist_ok=False)
    _write_json_no_overwrite(target / "prepared.json", manifest)
    usage_db = target / "usage.sqlite3"
    outcomes: list[dict[str, object]] = []
    cumulative_cost_nano = 0

    with _isolated_usage_database(usage_db):
        ledger = ledger_factory()
        ledger.update_settings(
            monthly_budget_usd=maximum_usd,
            warning_threshold_percent=80,
            hard_limit_enabled=True,
        )
        for attempt in schedule:
            remaining = EXPECTED_ATTEMPT_COUNT - attempt.ordinal + 1
            if (
                cumulative_cost_nano
                + remaining * PER_ATTEMPT_COST_CEILING_NANO_USD
                > maximum_nano
            ):
                raise ProductFastLatencyComparisonError(
                    "remaining worst-case requests exceed the aggregate cap"
                )
            request_id = uuid4().hex
            attempt_root = (
                target
                / "attempts"
                / f"{attempt.ordinal:02d}-{attempt.question.item_id}-{attempt.arm}"
            )
            _write_json_no_overwrite(
                attempt_root / "intent.json",
                _sealed(
                    {
                        "schema": ATTEMPT_INTENT_SCHEMA,
                        **attempt.text_free_binding(),
                        "request_id": request_id,
                        "mode": ArchivistMode.PROFESSIONAL.value,
                        "fresh_first_turn": True,
                        "automatic_retry_allowed": False,
                        "request_cost_ceiling_nano_usd": (
                            PER_ATTEMPT_COST_CEILING_NANO_USD
                        ),
                    }
                ),
            )

            started_ns = perf_counter_ns()
            try:
                with usage_scope(
                    project_id="current",
                    conversation_id=target.name,
                    turn_id=f"{attempt.question.item_id}-{attempt.arm}",
                    request_id=request_id,
                    enforce_budget=True,
                    allow_over_budget=False,
                    request_cost_ceiling_nano_usd=(
                        PER_ATTEMPT_COST_CEILING_NANO_USD
                    ),
                    answer_generation_service_tier=(
                        attempt.requested_service_tier
                    ),
                ):
                    result = answer_runner(
                        attempt.question.question,
                        archivist_mode=ArchivistMode.PROFESSIONAL,
                        history=(),
                        application_compiled=True,
                    )
            except Exception as exc:
                wall_ms = max(0, perf_counter_ns() - started_ns) / 1_000_000
                try:
                    usage, state, events = _usage_snapshot(ledger, request_id)
                except ProductFastLatencyComparisonError:
                    usage, state, events = {"measurement_status": "unavailable"}, None, ()
                sealed = _outcome(
                    attempt=attempt,
                    request_id=request_id,
                    measurement_status="ambiguous_exception",
                    wall_latency_ms=wall_ms,
                    usage=usage,
                    state=state,
                    events=events,
                    error_class=type(exc).__name__,
                )
                _write_json_no_overwrite(attempt_root / "outcome.json", sealed)
                raise ProductFastLatencyComparisonError(
                    f"attempt {attempt.ordinal} ended ambiguously; no later call was made"
                ) from exc

            wall_ms = max(0, perf_counter_ns() - started_ns) / 1_000_000
            try:
                usage, state, events = _usage_snapshot(ledger, request_id)
            except ProductFastLatencyComparisonError as exc:
                sealed = _outcome(
                    attempt=attempt,
                    request_id=request_id,
                    measurement_status="ambiguous_ledger",
                    wall_latency_ms=wall_ms,
                    usage={"measurement_status": "unavailable"},
                    state=None,
                    events=(),
                    result=result,
                    error_class=(
                        type(exc.__cause__).__name__
                        if exc.__cause__ is not None
                        else type(exc).__name__
                    ),
                )
                _write_json_no_overwrite(attempt_root / "outcome.json", sealed)
                raise ProductFastLatencyComparisonError(
                    f"attempt {attempt.ordinal} usage is ambiguous; no later call was made"
                ) from exc

            usage_error = _usage_contract_error(
                events=events,
                totals=usage,
                state=state,
                requested_service_tier=attempt.requested_service_tier,
            )
            generation = _safe_generation_trace(result)
            timings = _safe_stage_timings(result)
            profile_error = (
                generation.get("answer_length_profile")
                != attempt.question.expected_profile
            )
            product_status = getattr(result, "status", None)
            product_status_error = product_status not in {
                "retrieval_authored",
                "retrieval_authored_fallback",
            }
            generation_latency = timings.get("answer_generation")
            timing_error = not isinstance(generation_latency, (int, float)) or (
                generation_latency <= 0
            )
            answer = getattr(result, "answer", None)
            final_chunks = getattr(result, "final_chunks", ())
            answer_shape_error = not isinstance(answer, str) or not isinstance(
                final_chunks, Sequence
            )
            citation = (
                {}
                if answer_shape_error
                else _citation_projection(answer, source_count=len(final_chunks))
            )

            if usage_error is not None:
                measurement_status = usage_error
                error_class = "UsageContractError"
            elif profile_error:
                measurement_status = "profile_mismatch"
                error_class = "AnswerLengthProfileMismatch"
            elif product_status_error:
                measurement_status = "product_status_mismatch"
                error_class = "ProductStatusMismatch"
            elif timing_error:
                measurement_status = "generation_timing_missing"
                error_class = "GenerationTimingError"
            elif answer_shape_error:
                measurement_status = "answer_shape_mismatch"
                error_class = "AnswerShapeError"
            else:
                measurement_status = "complete"
                error_class = None

            sealed = _outcome(
                attempt=attempt,
                request_id=request_id,
                measurement_status=measurement_status,
                wall_latency_ms=wall_ms,
                usage=usage,
                state=state,
                events=events,
                result=result,
                error_class=error_class,
                citation=citation,
            )
            _write_json_no_overwrite(attempt_root / "outcome.json", sealed)
            if measurement_status != "complete":
                raise ProductFastLatencyComparisonError(
                    f"attempt {attempt.ordinal} measurement is {measurement_status}; "
                    "no later call was made"
                )
            cumulative_cost_nano += int(state["estimated_cost_nano_usd"])
            outcomes.append(sealed)

    report = build_report(outcomes)
    _write_json_no_overwrite(target / "report.json", report)
    try:
        with (target / "report.md").open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(_render_report_markdown(report))
    except FileExistsError as exc:
        raise ProductFastLatencyComparisonError(
            "refusing to overwrite comparison report"
        ) from exc
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the exact paired six-attempt Standard-versus-Fast product "
            "latency comparison and write text-free artifacts."
        )
    )
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--max-total-cost-usd", type=Decimal, required=True)
    parser.add_argument(
        "--authorize-openai-fast-latency-comparison",
        action="store_true",
        help=(
            "Authorize six embeddings and six authored-response attempts against "
            "private manuscript evidence, with no retries."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = execute_fast_latency_comparison(
        run_root=args.run_root,
        maximum_usd=args.max_total_cost_usd,
        authorized=args.authorize_openai_fast_latency_comparison,
    )
    print(
        "Product Fast latency comparison complete: "
        f"median ratio {report['primary_median_fast_to_standard_ratio']}; "
        f"faster pairs {report['primary_faster_pair_count']}/3; "
        f"mechanical gate {report['mechanical_gate']['passed']}; "
        f"cost ${report['recorded_cost_usd_exact']}"
    )
    print(f"Text-free report: {args.run_root / 'report.md'}")
    return 0


__all__ = [
    "AGGREGATE_HARD_CEILING_NANO_USD",
    "ARM_SERVICE_TIERS",
    "AttemptSpec",
    "EXPECTED_PROVIDER_OPERATIONS",
    "FAST_ARM",
    "ProductFastLatencyComparisonError",
    "STANDARD_ARM",
    "build_report",
    "execute_fast_latency_comparison",
    "frozen_schedule",
    "main",
    "validate_authorization",
]
