from __future__ import annotations

import json
import os
import shutil
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import product_latency_smoke as smoke
from costs import TokenUsage, UsageLedger, current_usage_context
from query_planning import RouteTrait, route_question


@pytest.fixture
def workspace_dir() -> Path:
    root = Path("runtime") / "test-product-latency-smoke" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _identity() -> dict[str, str]:
    return {"commit": "a" * 40, "working_tree": "clean"}


def _record_operation(*, operation: str, output_tokens: int = 0) -> None:
    context = current_usage_context()
    assert context.request_id is not None
    if operation == "query_embedding":
        model = "text-embedding-3-small"
        usage = TokenUsage(input_tokens=24, output_tokens=0, total_tokens=24)
    else:
        model = smoke.AUTHORED_RESPONSE_SETTINGS.model
        usage = TokenUsage(
            input_tokens=900,
            output_tokens=output_tokens,
            reasoning_tokens=50,
            total_tokens=900 + output_tokens,
        )
    UsageLedger().record(
        response_id=f"synthetic-{operation}-{uuid4().hex}",
        operation=operation,
        requested_model=model,
        actual_model=model,
        usage=usage,
        project_id=context.project_id,
        conversation_id=context.conversation_id,
        turn_id=context.turn_id,
        request_id=context.request_id,
    )


def _successful_runner(calls: list[dict[str, object]]):
    def run(question: str, **kwargs):
        calls.append({"question": question, **kwargs})
        profile = (
            "broad"
            if RouteTrait.BROAD_SYNTHESIS in route_question(question)
            else "ordinary"
        )
        _record_operation(operation="query_embedding")
        _record_operation(
            operation="answer_generation",
            output_tokens=950 if profile == "broad" else 600,
        )
        return SimpleNamespace(
            answer="SYNTHETIC PRIVATE ANSWER TEXT",
            final_chunks=[{"chunk_id": "private-source"}],
            status="retrieval_authored",
            diagnostics={
                "generation": {
                    "answer_length_profile": profile,
                    "fallback_code": None,
                },
                "stage_timings_ms": {
                    "retrieval": 5.0,
                    "answer_generation": 12.0,
                    "total": 18.0,
                },
            },
        )

    return run


def _run(tmp_path: Path, *, runner, name: str = "run-001"):
    smoke_root = tmp_path / "product-latency-smoke-v1"
    run_root = smoke_root / name
    report = smoke.execute_latency_smoke(
        run_root=run_root,
        maximum_usd=Decimal("6.00"),
        authorized=True,
        smoke_root=smoke_root,
        identity_provider=_identity,
        answer_runner=runner,
    )
    return run_root, report


def test_fixture_is_registry_bound_two_ordinary_one_broad():
    questions = smoke.load_latency_questions()

    assert [question.item_id for question in questions] == [
        "DEV-OPENING-001",
        "DEV-OPENING-002",
        "DEV-PRACTICAL-G006",
    ]
    assert [question.expected_profile for question in questions] == [
        "ordinary",
        "ordinary",
        "broad",
    ]
    assert all(not question.item_id.startswith("H") for question in questions)


def test_complete_smoke_is_three_fresh_professional_calls_and_text_free(workspace_dir):
    calls: list[dict[str, object]] = []
    previous_usage_db = os.environ.get("ARCHIVIST_USAGE_DB")

    run_root, report = _run(workspace_dir, runner=_successful_runner(calls))

    assert len(calls) == 3
    assert all(call["archivist_mode"].value == "professional" for call in calls)
    assert all(call["history"] == () for call in calls)
    assert all(call["application_compiled"] is True for call in calls)
    assert report["attempt_count"] == 3
    assert report["automatic_retries"] == 0
    assert report["fallback_count"] == 0
    assert report["provider_operation_event_counts"] == {
        "answer_generation": 3,
        "query_embedding": 3,
    }
    assert report["total_output_tokens"] == 2_150
    assert report["latency_ms"]["count"] == 3
    assert "p95" not in json.dumps(report).casefold()
    assert report["recorded_cost_nano_usd"] < smoke.AGGREGATE_HARD_CEILING_NANO_USD
    assert (run_root / "usage.sqlite3").is_file()
    assert (run_root / "prepared.json").is_file()
    assert (run_root / "report.json").is_file()
    assert (run_root / "report.md").is_file()
    assert len(list((run_root / "attempts").glob("*/intent.json"))) == 3
    assert len(list((run_root / "attempts").glob("*/outcome.json"))) == 3
    assert os.environ.get("ARCHIVIST_USAGE_DB") == previous_usage_db

    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in run_root.rglob("*")
        if path.suffix in {".json", ".md"}
    )
    assert "SYNTHETIC PRIVATE ANSWER TEXT" not in persisted
    assert all(call["question"] not in persisted for call in calls)
    assert "private-source" not in persisted


def test_missing_authorization_does_not_create_root_or_touch_identity_or_runner(workspace_dir):
    touched: list[str] = []
    smoke_root = workspace_dir / "product-latency-smoke-v1"
    run_root = smoke_root / "unauthorized"

    with pytest.raises(smoke.ProductLatencySmokeError, match="requires --authorize"):
        smoke.execute_latency_smoke(
            run_root=run_root,
            maximum_usd=Decimal("6.00"),
            authorized=False,
            smoke_root=smoke_root,
            identity_provider=lambda: touched.append("identity") or _identity(),
            answer_runner=lambda *_args, **_kwargs: touched.append("runner"),
        )

    assert touched == []
    assert not run_root.exists()


@pytest.mark.parametrize("maximum", (Decimal("5.999999999"), Decimal("6.000000001")))
def test_cap_must_equal_fixed_six_dollar_worst_case(workspace_dir, maximum):
    with pytest.raises(smoke.ProductLatencySmokeError):
        smoke.execute_latency_smoke(
            run_root=workspace_dir / "product-latency-smoke-v1" / "bad-cap",
            maximum_usd=maximum,
            authorized=True,
            smoke_root=workspace_dir / "product-latency-smoke-v1",
            identity_provider=lambda: pytest.fail("bad cap reached identity"),
            answer_runner=lambda *_args, **_kwargs: pytest.fail("bad cap ran product"),
        )


def test_missing_provider_operation_seals_first_outcome_and_never_continues(
    workspace_dir,
):
    calls: list[str] = []

    def incomplete_runner(question: str, **_kwargs):
        calls.append(question)
        _record_operation(operation="query_embedding")
        return SimpleNamespace(
            answer="private fallback",
            final_chunks=[],
            status="retrieval_authored_fallback",
            diagnostics={
                "generation": {
                    "answer_length_profile": "ordinary",
                    "fallback_code": "provider_failure",
                }
            },
        )

    smoke_root = workspace_dir / "product-latency-smoke-v1"
    run_root = smoke_root / "ambiguous"
    with pytest.raises(smoke.ProductLatencySmokeError, match="ambiguous_usage"):
        smoke.execute_latency_smoke(
            run_root=run_root,
            maximum_usd=Decimal("6.00"),
            authorized=True,
            smoke_root=smoke_root,
            identity_provider=_identity,
            answer_runner=incomplete_runner,
        )

    assert len(calls) == 1
    outcome_path = next((run_root / "attempts").glob("*/outcome.json"))
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["measurement_status"] == "ambiguous_usage"
    assert outcome["fallback_code"] == "provider_failure"
    assert not (run_root / "report.json").exists()


def test_accounted_product_fallback_is_reported_without_becoming_ambiguous(
    workspace_dir,
):
    calls: list[dict[str, object]] = []
    generated_runner = _successful_runner(calls)

    def fallback_runner(question: str, **kwargs):
        result = generated_runner(question, **kwargs)
        if len(calls) == 1:
            result.status = "retrieval_authored_fallback"
            result.diagnostics["generation"]["fallback_code"] = "response_refusal"
        return result

    _run_root, report = _run(
        workspace_dir,
        runner=fallback_runner,
        name="accounted-fallback",
    )

    assert report["fallback_count"] == 1
    assert report["fallback_code_counts"] == {"response_refusal": 1}
    assert report["status_counts"] == {
        "retrieval_authored": 2,
        "retrieval_authored_fallback": 1,
    }


def test_changed_product_profile_stops_after_first_accounted_attempt(workspace_dir):
    calls: list[dict[str, object]] = []
    generated_runner = _successful_runner(calls)

    def wrong_profile_runner(question: str, **kwargs):
        result = generated_runner(question, **kwargs)
        result.diagnostics["generation"]["answer_length_profile"] = "broad"
        return result

    smoke_root = workspace_dir / "product-latency-smoke-v1"
    run_root = smoke_root / "wrong-profile"
    with pytest.raises(smoke.ProductLatencySmokeError, match="profile_mismatch"):
        smoke.execute_latency_smoke(
            run_root=run_root,
            maximum_usd=Decimal("6.00"),
            authorized=True,
            smoke_root=smoke_root,
            identity_provider=_identity,
            answer_runner=wrong_profile_runner,
        )

    assert len(calls) == 1
    outcome_path = next((run_root / "attempts").glob("*/outcome.json"))
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["measurement_status"] == "profile_mismatch"
    assert outcome["error_class"] == "AnswerLengthProfileMismatch"


def test_exception_persists_only_error_class_and_never_retries(workspace_dir):
    calls: list[str] = []

    def failing_runner(question: str, **_kwargs):
        calls.append(question)
        raise TimeoutError("PRIVATE PROVIDER ERROR DETAIL")

    smoke_root = workspace_dir / "product-latency-smoke-v1"
    run_root = smoke_root / "exception"
    with pytest.raises(smoke.ProductLatencySmokeError, match="ended ambiguously"):
        smoke.execute_latency_smoke(
            run_root=run_root,
            maximum_usd=Decimal("6.00"),
            authorized=True,
            smoke_root=smoke_root,
            identity_provider=_identity,
            answer_runner=failing_runner,
        )

    assert len(calls) == 1
    outcome_path = next((run_root / "attempts").glob("*/outcome.json"))
    raw = outcome_path.read_text(encoding="utf-8")
    outcome = json.loads(raw)
    assert outcome["measurement_status"] == "ambiguous_exception"
    assert outcome["error_class"] == "TimeoutError"
    assert "PRIVATE PROVIDER ERROR DETAIL" not in raw


def test_existing_root_is_never_resumed(workspace_dir):
    smoke_root = workspace_dir / "product-latency-smoke-v1"
    run_root = smoke_root / "existing"
    run_root.mkdir(parents=True)

    with pytest.raises(smoke.ProductLatencySmokeError, match="never resumed"):
        smoke.execute_latency_smoke(
            run_root=run_root,
            maximum_usd=Decimal("6.00"),
            authorized=True,
            smoke_root=smoke_root,
            identity_provider=lambda: pytest.fail("existing root reached identity"),
            answer_runner=lambda *_args, **_kwargs: pytest.fail("existing root ran product"),
        )
