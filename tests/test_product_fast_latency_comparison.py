from __future__ import annotations

import json
import os
import shutil
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import product_fast_latency_comparison as comparison
from costs import TokenUsage, UsageLedger, current_usage_context
from query_planning import RouteTrait, route_question


@pytest.fixture
def workspace_dir() -> Path:
    root = Path("runtime") / "test-product-fast-latency-comparison" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _identity() -> dict[str, str]:
    return {"commit": "a" * 40, "working_tree": "clean"}


def _record_operation(
    *,
    operation: str,
    output_tokens: int = 0,
    actual_tier: str | None | object = ...,
) -> None:
    context = current_usage_context()
    assert context.request_id is not None
    if operation == "query_embedding":
        model = "text-embedding-3-small"
        usage = TokenUsage(input_tokens=24, total_tokens=24)
        requested_tier = None
        returned_tier = None
    else:
        model = comparison.AUTHORED_RESPONSE_SETTINGS.model
        usage = TokenUsage(
            input_tokens=900,
            cached_tokens=100,
            output_tokens=output_tokens,
            reasoning_tokens=50,
            total_tokens=900 + output_tokens,
        )
        requested_tier = context.answer_generation_service_tier
        returned_tier = requested_tier if actual_tier is ... else actual_tier
    UsageLedger().record(
        response_id=f"synthetic-{operation}-{uuid4().hex}",
        operation=operation,
        requested_model=model,
        actual_model=model,
        requested_service_tier=requested_tier,
        actual_service_tier=returned_tier,
        usage=usage,
        project_id=context.project_id,
        conversation_id=context.conversation_id,
        turn_id=context.turn_id,
        request_id=context.request_id,
    )


def _successful_runner(
    calls: list[dict[str, object]],
    *,
    actual_tier: str | None | object = ...,
):
    def run(question: str, **kwargs):
        context = current_usage_context()
        tier = context.answer_generation_service_tier
        calls.append({"question": question, "tier": tier, **kwargs})
        profile = (
            "broad"
            if RouteTrait.BROAD_SYNTHESIS in route_question(question)
            else "ordinary"
        )
        _record_operation(operation="query_embedding")
        _record_operation(
            operation="answer_generation",
            output_tokens=950 if profile == "broad" else 600,
            actual_tier=actual_tier,
        )
        generation_ms = 60.0 if tier == "priority" else 100.0
        return SimpleNamespace(
            answer="Synthetic factual answer [Source 1].",
            final_chunks=[{"chunk_id": "private-source"}],
            status="retrieval_authored",
            diagnostics={
                "generation": {
                    "status": "generated",
                    "validation_result": "valid",
                    "content_outcome": "valid_complete",
                    "answer_length_profile": profile,
                    "fallback_code": None,
                },
                "stage_timings_ms": {
                    "retrieval": 5.0,
                    "answer_generation": generation_ms,
                    "total": generation_ms + 8.0,
                },
            },
        )

    return run


def _run(workspace_dir: Path, *, runner, name: str = "run-001"):
    comparison_root = workspace_dir / "product-fast-latency-comparison-v1"
    run_root = comparison_root / name
    report = comparison.execute_fast_latency_comparison(
        run_root=run_root,
        maximum_usd=Decimal("12.00"),
        authorized=True,
        comparison_root=comparison_root,
        identity_provider=_identity,
        answer_runner=runner,
    )
    return run_root, report


def test_schedule_is_exactly_counterbalanced_and_fixture_bound():
    questions = comparison.load_latency_questions()
    schedule = comparison.frozen_schedule(questions)

    assert [(item.question.item_id, item.arm) for item in schedule] == [
        ("DEV-OPENING-001", "standard"),
        ("DEV-OPENING-001", "fast"),
        ("DEV-OPENING-002", "fast"),
        ("DEV-OPENING-002", "standard"),
        ("DEV-PRACTICAL-G006", "standard"),
        ("DEV-PRACTICAL-G006", "fast"),
    ]
    assert [item.requested_service_tier for item in schedule] == [
        "default",
        "priority",
        "priority",
        "default",
        "default",
        "priority",
    ]


def test_complete_comparison_is_six_fresh_calls_and_text_free(workspace_dir):
    calls: list[dict[str, object]] = []
    previous_usage_db = os.environ.get("ARCHIVIST_USAGE_DB")

    run_root, report = _run(
        workspace_dir,
        runner=_successful_runner(calls),
    )

    assert len(calls) == 6
    assert [call["tier"] for call in calls] == [
        "default",
        "priority",
        "priority",
        "default",
        "default",
        "priority",
    ]
    assert all(call["archivist_mode"].value == "professional" for call in calls)
    assert all(call["history"] == () for call in calls)
    assert all(call["application_compiled"] is True for call in calls)
    assert report["attempt_count"] == 6
    assert report["automatic_retries"] == 0
    assert report["provider_operation_event_counts"] == {
        "answer_generation": 6,
        "query_embedding": 6,
    }
    assert report["answer_generation_actual_service_tier_counts"] == {
        "default": 3,
        "priority": 3,
    }
    assert report["primary_median_fast_to_standard_ratio"] == 0.6
    assert report["primary_faster_pair_count"] == 3
    assert report["latency_gate_passed"] is True
    assert report["mechanical_gate"]["passed"] is True
    assert report["comparison_gate_passed"] is True
    assert report["promotion_decision"] == "owner_pending"
    assert report["fast_to_standard_recorded_cost_ratio"] > 1
    assert all(
        pair["fast_recorded_cost_nano_usd"]
        > pair["standard_recorded_cost_nano_usd"]
        and pair["fast_to_standard_recorded_cost_ratio"] > 1
        and pair["fast_minus_standard_cost_nano_usd"] > 0
        and pair["fast_output_tokens"] == pair["standard_output_tokens"]
        for pair in report["paired_answer_generation"]
    )
    assert "p95" not in json.dumps(report).casefold()
    assert (run_root / "usage.sqlite3").is_file()
    assert len(list((run_root / "attempts").glob("*/intent.json"))) == 6
    assert len(list((run_root / "attempts").glob("*/outcome.json"))) == 6
    assert (run_root / "prepared.json").is_file()
    assert (run_root / "report.json").is_file()
    assert (run_root / "report.md").is_file()
    assert os.environ.get("ARCHIVIST_USAGE_DB") == previous_usage_db

    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in run_root.rglob("*")
        if path.suffix in {".json", ".md"}
    )
    assert "Synthetic factual answer" not in persisted
    assert "private-source" not in persisted
    assert all(call["question"] not in persisted for call in calls)
    prepared = json.loads((run_root / "prepared.json").read_text(encoding="utf-8"))
    tier_contract = prepared["execution_contract"]["service_tier_contract"]
    assert tier_contract == {
        "arm_requested_and_required_returned_tiers": {
            "fast": "priority",
            "standard": "default",
        },
        "embedding_requested_service_tier": None,
        "embedding_required_returned_service_tier": None,
        "pricing_version": comparison.PRICING_VERSION,
    }


def test_missing_authorization_and_inexact_cap_do_nothing(workspace_dir):
    touched: list[str] = []
    comparison_root = workspace_dir / "product-fast-latency-comparison-v1"

    with pytest.raises(
        comparison.ProductFastLatencyComparisonError,
        match="requires --authorize",
    ):
        comparison.execute_fast_latency_comparison(
            run_root=comparison_root / "unauthorized",
            maximum_usd=Decimal("12.00"),
            authorized=False,
            comparison_root=comparison_root,
            identity_provider=lambda: touched.append("identity") or _identity(),
            answer_runner=lambda *_args, **_kwargs: touched.append("runner"),
        )
    for value in (Decimal("11.999999999"), Decimal("12.000000001")):
        with pytest.raises(comparison.ProductFastLatencyComparisonError):
            comparison.execute_fast_latency_comparison(
                run_root=comparison_root / f"bad-{value}",
                maximum_usd=value,
                authorized=True,
                comparison_root=comparison_root,
                identity_provider=lambda: touched.append("identity") or _identity(),
                answer_runner=lambda *_args, **_kwargs: touched.append("runner"),
            )

    assert touched == []
    assert not comparison_root.exists()


def test_changed_product_cost_ceiling_requires_a_new_protocol(
    workspace_dir,
    monkeypatch,
):
    touched: list[str] = []
    comparison_root = workspace_dir / "product-fast-latency-comparison-v1"
    monkeypatch.setattr(
        comparison,
        "PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD",
        2_000_000_001,
    )

    with pytest.raises(
        comparison.ProductFastLatencyComparisonError,
        match="open a new comparison protocol",
    ):
        comparison.execute_fast_latency_comparison(
            run_root=comparison_root / "changed-product-cap",
            maximum_usd=Decimal("12.00"),
            authorized=True,
            comparison_root=comparison_root,
            identity_provider=lambda: touched.append("identity") or _identity(),
            answer_runner=lambda *_args, **_kwargs: touched.append("runner"),
        )

    assert touched == []
    assert not comparison_root.exists()


def test_returned_tier_mismatch_seals_first_outcome_and_stops(workspace_dir):
    calls: list[dict[str, object]] = []
    runner = _successful_runner(calls, actual_tier="priority")
    comparison_root = workspace_dir / "product-fast-latency-comparison-v1"
    run_root = comparison_root / "tier-mismatch"

    with pytest.raises(
        comparison.ProductFastLatencyComparisonError,
        match="returned_service_tier_mismatch",
    ):
        comparison.execute_fast_latency_comparison(
            run_root=run_root,
            maximum_usd=Decimal("12.00"),
            authorized=True,
            comparison_root=comparison_root,
            identity_provider=_identity,
            answer_runner=runner,
        )

    assert len(calls) == 1
    outcome_path = next((run_root / "attempts").glob("*/outcome.json"))
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["measurement_status"] == "returned_service_tier_mismatch"
    assert outcome["error_class"] == "UsageContractError"
    assert not (run_root / "report.json").exists()


def test_missing_returned_tier_seals_unpriced_outcome_and_stops(workspace_dir):
    calls: list[dict[str, object]] = []
    runner = _successful_runner(calls, actual_tier=None)
    comparison_root = workspace_dir / "product-fast-latency-comparison-v1"
    run_root = comparison_root / "missing-tier"

    with pytest.raises(
        comparison.ProductFastLatencyComparisonError,
        match="unpriced_provider_event",
    ):
        comparison.execute_fast_latency_comparison(
            run_root=run_root,
            maximum_usd=Decimal("12.00"),
            authorized=True,
            comparison_root=comparison_root,
            identity_provider=_identity,
            answer_runner=runner,
        )

    assert len(calls) == 1
    outcome_path = next((run_root / "attempts").glob("*/outcome.json"))
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["measurement_status"] == "unpriced_provider_event"
    generation_event = next(
        event
        for event in outcome["usage"]["events"]
        if event["operation"] == "answer_generation"
    )
    assert generation_event["actual_service_tier"] is None
    assert generation_event["estimated_cost_nano_usd"] is None


def test_missing_operation_is_ambiguous_and_never_continues(workspace_dir):
    calls: list[str] = []

    def incomplete_runner(question: str, **_kwargs):
        calls.append(question)
        _record_operation(operation="query_embedding")
        return SimpleNamespace(
            answer="Synthetic fallback [Source 1].",
            final_chunks=[{"chunk_id": "private-source"}],
            status="retrieval_authored_fallback",
            diagnostics={
                "generation": {
                    "status": "fallback_to_direct_evidence",
                    "validation_result": "invalid",
                    "content_outcome": None,
                    "answer_length_profile": "ordinary",
                    "fallback_code": "provider_failure",
                },
                "stage_timings_ms": {"answer_generation": 10.0},
            },
        )

    comparison_root = workspace_dir / "product-fast-latency-comparison-v1"
    run_root = comparison_root / "missing-operation"
    with pytest.raises(
        comparison.ProductFastLatencyComparisonError,
        match="provider_event_count_mismatch",
    ):
        comparison.execute_fast_latency_comparison(
            run_root=run_root,
            maximum_usd=Decimal("12.00"),
            authorized=True,
            comparison_root=comparison_root,
            identity_provider=_identity,
            answer_runner=incomplete_runner,
        )

    assert len(calls) == 1
    outcome_path = next((run_root / "attempts").glob("*/outcome.json"))
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["measurement_status"] == "provider_event_count_mismatch"


def test_accounted_fallback_continues_but_fails_mechanical_gate(workspace_dir):
    calls: list[dict[str, object]] = []
    generated_runner = _successful_runner(calls)

    def fallback_runner(question: str, **kwargs):
        result = generated_runner(question, **kwargs)
        if len(calls) == 1:
            result.status = "retrieval_authored_fallback"
            result.diagnostics["generation"].update(
                {
                    "status": "fallback_to_direct_evidence",
                    "validation_result": "invalid",
                    "content_outcome": None,
                    "fallback_code": "response_refusal",
                }
            )
        return result

    _run_root, report = _run(
        workspace_dir,
        runner=fallback_runner,
        name="accounted-fallback",
    )

    assert len(calls) == 6
    assert report["fallback_count"] == 1
    assert report["fallback_code_counts"] == {"response_refusal": 1}
    assert report["mechanical_gate"]["passed"] is False
    assert report["mechanical_gate"]["passing_attempt_count"] == 5
    assert report["comparison_gate_passed"] is False
    assert report["promotion_decision"] == "owner_pending"


def test_malformed_or_unresolvable_citation_fails_mechanical_gate(workspace_dir):
    calls: list[dict[str, object]] = []
    generated_runner = _successful_runner(calls)

    def malformed_runner(question: str, **kwargs):
        result = generated_runner(question, **kwargs)
        if len(calls) == 2:
            result.answer = "Synthetic factual answer [Source 2]."
        return result

    _run_root, report = _run(
        workspace_dir,
        runner=malformed_runner,
        name="citation-failure",
    )

    assert len(calls) == 6
    assert report["mechanical_gate"]["passed"] is False
    failed = [item for item in report["items"] if not item["mechanical_gate_passed"]]
    assert len(failed) == 1
    assert failed[0]["citation_audit"]["out_of_range_reference_count"] == 1


def test_latency_gate_uses_unrounded_pair_ratios(workspace_dir):
    calls: list[dict[str, object]] = []
    generated_runner = _successful_runner(calls)

    def boundary_runner(question: str, **kwargs):
        result = generated_runner(question, **kwargs)
        tier = current_usage_context().answer_generation_service_tier
        result.diagnostics["stage_timings_ms"]["answer_generation"] = (
            700_000.4 if tier == "priority" else 1_000_000.0
        )
        return result

    _run_root, report = _run(
        workspace_dir,
        runner=boundary_runner,
        name="unrounded-boundary",
    )

    assert report["primary_median_fast_to_standard_ratio"] == 0.7
    assert report["primary_faster_pair_count"] == 3
    assert report["latency_gate_passed"] is False
    assert report["comparison_gate_passed"] is False


def test_existing_root_is_never_resumed(workspace_dir):
    comparison_root = workspace_dir / "product-fast-latency-comparison-v1"
    run_root = comparison_root / "existing"
    run_root.mkdir(parents=True)

    with pytest.raises(
        comparison.ProductFastLatencyComparisonError,
        match="never resumed",
    ):
        comparison.execute_fast_latency_comparison(
            run_root=run_root,
            maximum_usd=Decimal("12.00"),
            authorized=True,
            comparison_root=comparison_root,
            identity_provider=lambda: pytest.fail("existing root reached identity"),
            answer_runner=lambda *_args, **_kwargs: pytest.fail(
                "existing root ran product"
            ),
        )
