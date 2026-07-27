import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from openai import OpenAI
from pydantic import BaseModel, ValidationError

import web_api
import costs
from costs import (
    CostLimitExceeded,
    MODEL_PRICING,
    PRICING_VERSION,
    TokenUsage,
    UsageLedger,
    calculate_cost_nano_usd,
    current_usage_context,
    extract_token_usage,
    record_openai_response,
    tracked_embeddings_create,
    tracked_responses_create,
    tracked_responses_parse,
    usage_scope,
)


@pytest.fixture
def ledger_path(request):
    directory = Path("runtime") / "test-ledgers"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{request.node.name}.sqlite3"
    related_paths = [path, Path(f"{path}-wal"), Path(f"{path}-shm")]
    for related in related_paths:
        related.unlink(missing_ok=True)
    yield path
    for related in related_paths:
        related.unlink(missing_ok=True)
    try:
        directory.rmdir()
    except OSError:
        pass


def answer_run_diagnostics_payload(**overrides):
    payload = {
        "schema": "archivist.answer_run_diagnostics/2",
        "cohort": {
            "rag_policy_version": "evidence-planned-v4",
            "query_planner_prompt_version": "query-planner-v2",
            "coverage_prompt_version": "evidence-coverage-v3",
            "normalizer_version": "evidence-coverage-normalizer/1",
            "coverage_instructions_sha256": "a" * 64,
            "coverage_schema_sha256": "b" * 64,
            "generator_model": "gpt-5.6-sol",
            "generator_reasoning_effort": "high",
            "generator_verbosity": "low",
        },
        "answer_status": "generation_contract_failed",
        "evidence_decision": "direct_answer",
        "validation_result": "invalid",
        "validation_error_code": "citation_source_mismatch",
        "repair_applied": False,
        "repair_codes": [],
        "planner": {
            "schema": "archivist.planner_call_diagnostics/1",
            "status": "not_called",
            "failure_code": None,
            "exception_class": None,
            "exception_code": None,
        },
        "stage_timings_ms": {
            "retrieval": 12.5,
            "answer_generation": 240.125,
            "answer_validation": 0.75,
            "total": 260.0,
        },
    }
    payload.update(overrides)
    return payload


def test_answer_run_diagnostics_round_trip_is_text_free_and_upserted(ledger_path):
    ledger = UsageLedger(ledger_path)
    payload = answer_run_diagnostics_payload()

    assert ledger.record_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
        diagnostics=payload,
        recorded_at="2026-07-24T12:00:00+00:00",
    )
    stored = ledger.get_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
    )

    assert stored is not None
    assert stored["validation_error_code"] == "citation_source_mismatch"
    assert stored["cohort"]["rag_policy_version"] == "evidence-planned-v4"
    assert stored["planner"]["status"] == "not_called"
    assert stored["stage_timings_ms"]["answer_generation"] == 240.125
    assert "question" not in str(stored).casefold()
    first_run_id = stored["run_id"]

    repaired = answer_run_diagnostics_payload(
        answer_status="answered",
        validation_result="valid",
        validation_error_code=None,
        repair_applied=True,
        repair_codes=["source_mapping_mismatch"],
        planner={
            "schema": "archivist.planner_call_diagnostics/1",
            "status": "failed",
            "failure_code": "planner_call_failed",
            "exception_class": "SyntheticPlannerFailure",
            "exception_code": "rate-limit/429",
        },
    )
    assert ledger.record_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
        diagnostics=repaired,
    )
    updated = ledger.get_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
    )
    assert updated is not None
    assert updated["run_id"] != first_run_id
    assert updated["answer_status"] == "answered"
    assert updated["repair_codes"] == ["source_mapping_mismatch"]
    assert updated["planner"]["exception_class"] == "SyntheticPlannerFailure"
    assert updated["planner"]["exception_code"] == "rate-limit/429"


def test_answer_run_diagnostics_migration_marks_historical_planner_state_unknown(
    ledger_path,
):
    with closing(sqlite3.connect(ledger_path)) as connection, connection:
        connection.executescript(
            """
            CREATE TABLE answer_run_diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                recorded_at TEXT NOT NULL,
                project_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                answer_status TEXT NOT NULL,
                evidence_decision TEXT NOT NULL,
                validation_result TEXT NOT NULL,
                validation_error_code TEXT,
                repair_applied INTEGER NOT NULL,
                repair_codes_json TEXT NOT NULL,
                cohort_json TEXT NOT NULL,
                stage_timings_json TEXT NOT NULL,
                UNIQUE(project_id, conversation_id, turn_id)
            );
            """
        )
        connection.execute(
            """
            INSERT INTO answer_run_diagnostics (
                run_id, recorded_at, project_id, conversation_id, turn_id,
                answer_status, evidence_decision, validation_result,
                validation_error_code, repair_applied, repair_codes_json,
                cohort_json, stage_timings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "historical-run",
                "2026-07-24T12:00:00+00:00",
                "current",
                "historical-conversation",
                "historical-turn",
                "answered",
                "direct_answer",
                "valid",
                None,
                0,
                "[]",
                "{}",
                "{}",
            ),
        )

    stored = UsageLedger(ledger_path).get_answer_run_diagnostics(
        project_id="current",
        conversation_id="historical-conversation",
        turn_id="historical-turn",
    )

    assert stored is not None
    assert stored["schema"] == "archivist.answer_run_diagnostics/2"
    assert stored["cohort"] == costs.HISTORICAL_UNKNOWN_COHORT
    assert stored["planner"] == {
        "schema": "archivist.planner_call_diagnostics/1",
        "status": "unknown",
        "failure_code": None,
        "exception_class": None,
        "exception_code": None,
    }


def test_historical_unknown_diagnostics_are_valid_v2_write_contract(ledger_path):
    payload = answer_run_diagnostics_payload(
        cohort=costs.HISTORICAL_UNKNOWN_COHORT,
        planner=costs.HISTORICAL_UNKNOWN_PLANNER,
    )

    assert UsageLedger(ledger_path).record_answer_run_diagnostics(
        project_id="current",
        conversation_id="historical-conversation",
        turn_id="historical-turn",
        diagnostics=payload,
    )


def test_active_planner_validation_code_round_trips_without_private_payload(
    ledger_path,
):
    payload = answer_run_diagnostics_payload(
        planner={
            "schema": "archivist.planner_call_diagnostics/2",
            "status": "failed",
            "failure_code": "invalid_planner_output",
            "planner_validation_code": "missing_requirement_mapping",
            "exception_class": None,
            "exception_code": None,
        },
    )
    ledger = UsageLedger(ledger_path)

    assert ledger.record_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
        diagnostics=payload,
    )
    stored = ledger.get_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
    )

    assert stored is not None
    assert stored["planner"] == payload["planner"]
    assert "requirement text" not in str(stored).casefold()


def test_fresh_diagnostics_table_defaults_support_older_writer(ledger_path):
    ledger = UsageLedger(ledger_path)
    assert (
        ledger.get_answer_run_diagnostics(
            project_id="current",
            conversation_id="missing-conversation",
            turn_id="missing-turn",
        )
        is None
    )
    with closing(sqlite3.connect(ledger_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO answer_run_diagnostics (
                run_id, recorded_at, project_id, conversation_id, turn_id,
                answer_status, evidence_decision, validation_result,
                validation_error_code, repair_applied, repair_codes_json,
                stage_timings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "rollback-writer-run",
                "2026-07-24T12:00:00+00:00",
                "current",
                "rollback-conversation",
                "rollback-turn",
                "answered",
                "direct_answer",
                "valid",
                None,
                0,
                "[]",
                "{}",
            ),
        )

    stored = ledger.get_answer_run_diagnostics(
        project_id="current",
        conversation_id="rollback-conversation",
        turn_id="rollback-turn",
    )

    assert stored is not None
    assert stored["cohort"] == costs.HISTORICAL_UNKNOWN_COHORT
    assert stored["planner"] == costs.HISTORICAL_UNKNOWN_PLANNER


@pytest.mark.parametrize(
    "payload",
    [
        answer_run_diagnostics_payload(answer_text="must not persist"),
        answer_run_diagnostics_payload(stage_timings_ms={"retrieval": -1}),
        answer_run_diagnostics_payload(
            validation_result="valid",
            validation_error_code="citation_source_mismatch",
        ),
        answer_run_diagnostics_payload(
            planner={
                "schema": "archivist.planner_call_diagnostics/1",
                "status": "succeeded",
                "failure_code": "planner_call_failed",
                "exception_class": None,
                "exception_code": None,
            }
        ),
        answer_run_diagnostics_payload(
            planner={
                "schema": "archivist.planner_call_diagnostics/2",
                "status": "failed",
                "failure_code": "invalid_planner_output",
                "planner_validation_code": None,
                "exception_class": None,
                "exception_code": None,
            }
        ),
        answer_run_diagnostics_payload(
            planner={
                "schema": "archivist.planner_call_diagnostics/2",
                "status": "failed",
                "failure_code": "invalid_planner_output",
                "planner_validation_code": "PRIVATE-planner-prose",
                "exception_class": None,
                "exception_code": None,
            }
        ),
        answer_run_diagnostics_payload(
            planner={
                "schema": "archivist.planner_call_diagnostics/1",
                "status": "failed",
                "failure_code": None,
                "exception_class": "Private message must not persist",
                "exception_code": None,
            }
        ),
        *(
            answer_run_diagnostics_payload(
                planner={
                    "schema": "archivist.planner_call_diagnostics/1",
                    "status": "failed",
                    "failure_code": "planner_call_failed",
                    "exception_class": "SyntheticPlannerFailure",
                    "exception_code": private_code,
                }
            )
            for private_code in (
                "PRIVATE-provider-prose-must-never-persist",
                "PRIVATE/provider/prose",
                "C:/Users/Michael/private",
                "private-provider-prose-must-persist",
                "c:users:michael:private",
            )
        ),
    ],
)
def test_answer_run_diagnostics_reject_content_and_inconsistent_metadata(
    ledger_path,
    payload,
):
    with pytest.raises(ValueError):
        UsageLedger(ledger_path).record_answer_run_diagnostics(
            project_id="current",
            conversation_id="conversation-1",
            turn_id="turn-1",
            diagnostics=payload,
        )


def test_versioned_pricing_handles_cached_writes_and_reasoning_without_double_charge():
    usage = TokenUsage(
        input_tokens=1_000,
        cached_tokens=200,
        cache_write_tokens=100,
        output_tokens=50,
        reasoning_tokens=25,
        total_tokens=1_050,
    )

    # GPT-5 cache writes use its normal input rate; 5.6 variants use 1.25x.
    assert calculate_cost_nano_usd("gpt-5", usage) == 1_525_000
    assert calculate_cost_nano_usd("gpt-5-2025-08-07", usage) == 1_525_000
    assert calculate_cost_nano_usd("gpt-5.6-sol", usage) == 5_725_000
    assert (
        calculate_cost_nano_usd(
            "text-embedding-3-small",
            TokenUsage(input_tokens=1_000_000, total_tokens=1_000_000),
        )
        == 20_000_000
    )
    assert (
        calculate_cost_nano_usd(
            "text-embedding-3-large",
            TokenUsage(input_tokens=1_000_000, total_tokens=1_000_000),
        )
        == 130_000_000
    )
    assert calculate_cost_nano_usd("unknown-model", usage) is None
    assert PRICING_VERSION


@pytest.mark.parametrize(
    ("model", "input_rate", "cached_rate", "output_rate"),
    [
        ("gpt-5.6", "5", "0.50", "30"),
        ("gpt-5.6-sol", "5", "0.50", "30"),
        ("gpt-5.6-terra", "2.50", "0.25", "15"),
        ("gpt-5.6-luna", "1", "0.10", "6"),
    ],
)
def test_all_named_generation_models_have_centralized_rates(
    model, input_rate, cached_rate, output_rate
):
    pricing = MODEL_PRICING[model]
    assert pricing.input_usd_per_million == Decimal(input_rate)
    assert pricing.cached_input_usd_per_million == Decimal(cached_rate)
    assert pricing.output_usd_per_million == Decimal(output_rate)


def test_usage_extraction_supports_responses_and_embeddings_shapes():
    response_usage = SimpleNamespace(
        input_tokens=120,
        input_tokens_details=SimpleNamespace(cached_tokens=20, cache_write_tokens=10),
        output_tokens=30,
        output_tokens_details=SimpleNamespace(reasoning_tokens=7),
        total_tokens=150,
    )
    response = SimpleNamespace(usage=response_usage)
    assert extract_token_usage(response) == TokenUsage(
        input_tokens=120,
        cached_tokens=20,
        cache_write_tokens=10,
        output_tokens=30,
        reasoning_tokens=7,
        total_tokens=150,
    )

    embedding = {
        "usage": {"prompt_tokens": 44, "total_tokens": 44},
    }
    assert extract_token_usage(embedding) == TokenUsage(input_tokens=44, total_tokens=44)
    assert extract_token_usage(SimpleNamespace(output_text="no usage")) is None
    assert extract_token_usage(SimpleNamespace(usage=SimpleNamespace())) is None


def test_tracked_wrappers_record_context_and_are_idempotent(monkeypatch, ledger_path):
    database = ledger_path
    monkeypatch.setenv("ARCHIVIST_USAGE_DB", str(database))
    usage = SimpleNamespace(input_tokens=100, output_tokens=10, total_tokens=110)

    class FakeResponses:
        def create(self, **_request):
            return SimpleNamespace(
                id="resp-1",
                model="gpt-5-2025-08-07",
                output_text="answer",
                usage=usage,
            )

    client = SimpleNamespace(responses=FakeResponses())
    with usage_scope(project_id="p1", conversation_id="c1", turn_id="t1"):
        first = tracked_responses_create(
            client,
            operation="answer_generation",
            model="gpt-5",
            input="prompt",
        )
        second = tracked_responses_create(
            client,
            operation="answer_generation",
            model="gpt-5",
            input="prompt",
        )

    assert first.output_text == second.output_text == "answer"
    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute(
            """
            SELECT response_id, operation, project_id, conversation_id, turn_id,
                   requested_model, actual_model
            FROM usage_events
            """
        ).fetchall()
    assert rows == [
        (
            "resp-1",
            "answer_generation",
            "p1",
            "c1",
            "t1",
            "gpt-5",
            "gpt-5-2025-08-07",
        )
    ]


def test_embedding_wrapper_records_object_usage_and_no_usage_creates_nothing(
    monkeypatch, ledger_path
):
    database = ledger_path
    monkeypatch.setenv("ARCHIVIST_USAGE_DB", str(database))

    class NoUsageEmbeddings:
        def create(self, **_request):
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1])])

    tracked_embeddings_create(
        SimpleNamespace(embeddings=NoUsageEmbeddings()),
        operation="query_embedding",
        model="text-embedding-3-small",
        input="question",
    )
    assert not database.exists()

    class UsedEmbeddings:
        def create(self, **_request):
            return SimpleNamespace(
                _request_id="request-embedding-1",
                model="text-embedding-3-small",
                data=[SimpleNamespace(embedding=[0.1])],
                usage=SimpleNamespace(prompt_tokens=12, total_tokens=12),
            )

    tracked_embeddings_create(
        SimpleNamespace(embeddings=UsedEmbeddings()),
        operation="query_embedding",
        model="text-embedding-3-small",
        input="question",
    )
    assert UsageLedger(database).summary()["operations"] == [
        {
            "operation": "query_embedding",
            "calls": 1,
            "tokens": 12,
            "cost_usd": 2.4e-07,
        }
    ]


def test_post_response_tracking_failure_does_not_hide_success(monkeypatch):
    paid_response = SimpleNamespace(
        id="paid-response",
        model="gpt-5",
        output_text="paid answer",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2),
    )
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_request: paid_response))
    monkeypatch.setattr(
        costs,
        "record_openai_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("ledger offline")),
    )

    response = tracked_responses_create(
        client,
        operation="answer_generation",
        model="gpt-5",
        input="prompt",
    )

    assert response.output_text == "paid answer"


def test_structured_response_wrapper_uses_parse_and_tracks_usage(monkeypatch):
    paid_response = SimpleNamespace(
        id="structured-response",
        model="gpt-5.6-sol",
        output_parsed={"result": "ok"},
        usage=SimpleNamespace(input_tokens=2, output_tokens=1, total_tokens=3),
    )
    requests = []
    tracked = []
    client = SimpleNamespace(
        responses=SimpleNamespace(parse=lambda **request: requests.append(request) or paid_response)
    )
    monkeypatch.setattr(
        costs,
        "record_openai_response",
        lambda response, **metadata: tracked.append((response, metadata)),
    )

    response = tracked_responses_parse(
        client,
        operation="query_planning",
        model="gpt-5.6-sol",
        input="structured prompt",
        text_format=dict,
    )

    assert response is paid_response
    assert requests == [
        {
            "model": "gpt-5.6-sol",
            "input": "structured prompt",
            "text_format": dict,
        }
    ]
    assert tracked == [
        (
            paid_response,
            {
                "operation": "query_planning",
                "requested_model": "gpt-5.6-sol",
            },
        )
    ]


def test_structured_raw_response_path_preserves_output_parsed(monkeypatch):
    parsed_response = SimpleNamespace(output_parsed={"result": "ok"})
    raw_payload = {
        "id": "raw-structured-response",
        "model": "gpt-5.6-sol",
        "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
    }
    requests = []
    tracked = []

    class FakeRawResponse:
        def json(self):
            return raw_payload

        def parse(self):
            return parsed_response

    client = SimpleNamespace(
        responses=SimpleNamespace(
            with_raw_response=SimpleNamespace(
                parse=lambda **request: requests.append(request) or FakeRawResponse()
            )
        )
    )
    monkeypatch.setattr(
        costs,
        "record_openai_response",
        lambda response, **metadata: tracked.append((response, metadata)),
    )

    response = tracked_responses_parse(
        client,
        operation="query_planning",
        model="gpt-5.6-sol",
        input="structured prompt",
        text_format=dict,
    )

    assert response.output_parsed == {"result": "ok"}
    assert len(requests) == 1
    assert tracked == [
        (
            raw_payload,
            {
                "operation": "query_planning",
                "requested_model": "gpt-5.6-sol",
            },
        )
    ]


def test_structured_validation_error_still_tracks_completed_response_usage(
    monkeypatch, ledger_path
):
    class StructuredPayload(BaseModel):
        result: str

    database = ledger_path
    monkeypatch.setenv("ARCHIVIST_USAGE_DB", str(database))
    calls = []
    response_body = {
        "id": "structured-validation-error",
        "object": "response",
        "created_at": 1.0,
        "model": "gpt-5.6-sol",
        "output": [
            {
                "id": "message-1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "annotations": [],
                        "text": json.dumps({"wrong": "shape"}),
                    }
                ],
            }
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "status": "completed",
        "usage": {
            "input_tokens": 12,
            "input_tokens_details": {
                "cached_tokens": 2,
                "cache_write_tokens": 0,
            },
            "output_tokens": 3,
            "output_tokens_details": {"reasoning_tokens": 1},
            "total_tokens": 15,
        },
    }

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=response_body,
            headers={"content-type": "application/json"},
            request=request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAI(
        api_key="local-test-key",
        base_url="https://example.test/v1",
        http_client=http_client,
    )
    try:
        with usage_scope(project_id="p1", conversation_id="c1", turn_id="t1"):
            with pytest.raises(ValidationError):
                tracked_responses_parse(
                    client,
                    operation="query_planning",
                    model="gpt-5.6-sol",
                    input="structured prompt",
                    text_format=StructuredPayload,
                )
    finally:
        client.close()

    assert len(calls) == 1
    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute(
            """
            SELECT response_id, operation, project_id, conversation_id, turn_id,
                   requested_model, actual_model, input_tokens, cached_tokens,
                   output_tokens, reasoning_tokens, total_tokens
            FROM usage_events
            """
        ).fetchall()
    assert rows == [
        (
            "structured-validation-error",
            "query_planning",
            "p1",
            "c1",
            "t1",
            "gpt-5.6-sol",
            "gpt-5.6-sol",
            12,
            2,
            3,
            1,
            15,
        )
    ]


def test_summary_filters_scopes_and_utc_calendar_month(ledger_path):
    ledger = UsageLedger(ledger_path)
    usage = TokenUsage(input_tokens=1_000, total_tokens=1_000)
    records = [
        ("one", "p1", "c1", "t1", "2026-07-01T00:00:00+00:00"),
        ("two", "p1", "c1", "t2", "2026-07-20T00:00:00+00:00"),
        ("three", "p1", "c2", "t3", "2026-07-21T00:00:00+00:00"),
        ("old", "p1", "c1", "old", "2026-06-30T23:59:59+00:00"),
        ("other-project", "p2", "c1", "t1", "2026-07-21T00:00:00+00:00"),
    ]
    for response_id, project_id, conversation_id, turn_id, timestamp in records:
        ledger.record(
            response_id=response_id,
            operation="answer_generation",
            requested_model="gpt-5",
            actual_model="gpt-5",
            usage=usage,
            project_id=project_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            recorded_at=timestamp,
        )
    ledger.record(
        response_id="unknown",
        operation="followup_resolution",
        requested_model="future-model",
        actual_model="future-model",
        usage=usage,
        project_id="p1",
        conversation_id="c1",
        turn_id="t1",
        recorded_at="2026-07-22T00:00:00+00:00",
    )

    summary = ledger.summary(
        project_id="p1",
        conversation_id="c1",
        turn_id="t1",
        now=datetime(2026, 7, 22, tzinfo=timezone.utc),
    )

    assert summary["tracking_started_at"] == "2026-06-30T23:59:59+00:00"
    assert summary["turn_usd"] == 0.00125
    assert summary["conversation_usd"] == 0.00375
    assert summary["month_usd"] == 0.005
    assert summary["all_time_usd"] == 0.00625
    assert summary["unpriced_events"] == 1
    assert {item["operation"] for item in summary["operations"]} == {
        "answer_generation",
        "followup_resolution",
    }
    assert len(summary["recent_events"]) == 5
    assert all(event["timestamp"].startswith("2026-07") for event in summary["recent_events"])


def test_settings_and_hard_stop_use_global_utc_month(ledger_path):
    ledger = UsageLedger(ledger_path)
    assert ledger.get_settings() == {
        "monthly_budget_usd": None,
        "warning_threshold_percent": 80,
        "hard_limit_enabled": False,
    }
    assert (
        ledger.update_settings(
            monthly_budget_usd="0.01",
            warning_threshold_percent=50,
            hard_limit_enabled=True,
        )["monthly_budget_usd"]
        == 0.01
    )

    usage = TokenUsage(input_tokens=10_000, total_tokens=10_000)
    ledger.record(
        response_id="previous-month",
        operation="answer_generation",
        requested_model="gpt-5",
        actual_model="gpt-5",
        usage=usage,
        recorded_at="2026-06-30T23:59:59+00:00",
    )
    assert not ledger.budget_state(datetime(2026, 7, 1, tzinfo=timezone.utc))["exceeded"]
    ledger.record(
        response_id="current-month",
        operation="answer_generation",
        requested_model="gpt-5",
        actual_model="gpt-5",
        usage=usage,
        recorded_at="2026-07-01T00:00:00+00:00",
    )
    state = ledger.budget_state(datetime(2026, 7, 22, tzinfo=timezone.utc))
    assert state["percent_used"] == 125.0
    assert state["warning"] is True
    assert state["exceeded"] is True


def test_cost_settings_and_summary_api_functions_return_flat_shapes(monkeypatch, ledger_path):
    monkeypatch.setenv("ARCHIVIST_USAGE_DB", str(ledger_path))

    assert web_api.cost_settings() == {
        "monthly_budget_usd": None,
        "warning_threshold_percent": 80,
        "hard_limit_enabled": False,
    }
    updated = web_api.update_cost_settings(
        web_api.CostSettingsRequest(
            monthly_budget_usd="25.00",
            warning_threshold_percent=75,
            hard_limit_enabled=True,
        )
    )
    assert updated == {
        "monthly_budget_usd": 25.0,
        "warning_threshold_percent": 75,
        "hard_limit_enabled": True,
    }

    summary = web_api.cost_summary(
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
    )
    assert summary["currency"] == "USD"
    assert summary["accuracy"] == "estimated"
    assert summary["tracking_started_at"] is None
    assert summary["turn_usd"] == summary["conversation_usd"] == 0.0
    assert summary["month_usd"] == summary["all_time_usd"] == 0.0
    assert summary["operations"] == summary["recent_events"] == []


def test_question_api_scopes_calls_forwards_ids_and_returns_costs(monkeypatch, ledger_path):
    monkeypatch.setenv("ARCHIVIST_USAGE_DB", str(ledger_path))
    captured = []

    def fake_answer(
        project_id,
        question,
        n_results,
        *,
        historiographical_lens,
        voice,
        worldview,
        history,
    ):
        captured.append(("answer", project_id, question, history, current_usage_context()))
        record_openai_response(
            SimpleNamespace(
                id="resolver",
                model="gpt-5",
                usage=SimpleNamespace(input_tokens=100, output_tokens=10, total_tokens=110),
            ),
            operation="followup_resolution",
            requested_model="gpt-5",
        )
        record_openai_response(
            SimpleNamespace(
                id="answer",
                model="gpt-5",
                usage=SimpleNamespace(input_tokens=200, output_tokens=20, total_tokens=220),
            ),
            operation="answer_generation",
            requested_model="gpt-5",
        )
        return SimpleNamespace(
            answer="Grounded answer.",
            final_chunks=[],
            status="answered",
            evidence_decision="direct_answer",
            resolved_question="Standalone question?",
        )

    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    request = web_api.QuestionRequest(
        question="What happened next?",
        history=[{"question": "Who?", "answer": "A prior answer."}],
        conversation_id="conversation-1",
        turn_id="turn-1",
    )

    response = web_api.question("current", request)

    context = captured[0][4]
    assert (
        context.project_id,
        context.conversation_id,
        context.turn_id,
        context.enforce_budget,
        context.allow_over_budget,
    ) == ("current", "conversation-1", "turn-1", True, False)
    assert response["conversation_id"] == "conversation-1"
    assert response["turn_id"] == "turn-1"
    assert response["resolved_query"] == "Standalone question?"
    run_diagnostics = dict(response["run_diagnostics"])
    cohort = run_diagnostics.pop("cohort")
    assert cohort["rag_policy_version"] == "evidence-planned-v13"
    assert cohort["query_planner_prompt_version"] == "query-planner-v6"
    assert cohort["coverage_prompt_version"] == "evidence-coverage-v5"
    assert cohort["normalizer_version"] == "evidence-coverage-normalizer/5"
    assert len(cohort["coverage_instructions_sha256"]) == 64
    assert run_diagnostics == {
        "schema": "archivist.answer_run_diagnostics/2",
        "answer_status": "answered",
        "evidence_decision": "direct_answer",
        "validation_result": "not_run",
        "validation_error_code": None,
        "repair_applied": False,
        "repair_codes": [],
        "planner": {
            "schema": "archivist.planner_call_diagnostics/2",
            "status": "not_called",
            "failure_code": None,
            "planner_validation_code": None,
            "exception_class": None,
            "exception_code": None,
        },
        "stage_timings_ms": {},
    }
    assert response["costs"]["turn_usd"] > 0
    assert response["costs"]["turn_usd"] == response["costs"]["conversation_usd"]
    assert {item["operation"] for item in response["costs"]["operations"]} == {
        "followup_resolution",
        "answer_generation",
    }
    persisted = UsageLedger().get_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
    )
    assert persisted is not None
    assert persisted["answer_status"] == "answered"
    assert persisted["validation_result"] == "not_run"


def test_question_api_persists_explicit_legacy_cohort(monkeypatch, ledger_path):
    monkeypatch.setenv("ARCHIVIST_USAGE_DB", str(ledger_path))

    def fake_answer(*_args, **_kwargs):
        return SimpleNamespace(
            answer="Legacy answer.",
            final_chunks=[],
            status="legacy_answer",
            evidence_decision="legacy_unclassified",
            resolved_question="Legacy question?",
            diagnostics={},
        )

    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    request = web_api.QuestionRequest(
        question="Legacy question?",
        conversation_id="legacy-conversation",
        turn_id="legacy-turn",
    )

    response = web_api.question("custom-project", request)

    cohort = response["run_diagnostics"]["cohort"]
    assert cohort["rag_policy_version"] == "legacy-answer-v1"
    assert cohort["query_planner_prompt_version"] == "not-applicable"
    assert cohort["coverage_prompt_version"] == "not-applicable"
    assert cohort["normalizer_version"] == "not-applicable"
    assert cohort["coverage_instructions_sha256"] == "not-applicable"
    assert cohort["coverage_schema_sha256"] == "not-applicable"
    assert response["run_diagnostics"]["planner"]["status"] == "not_called"

    persisted = UsageLedger().get_answer_run_diagnostics(
        project_id="custom-project",
        conversation_id="legacy-conversation",
        turn_id="legacy-turn",
    )
    assert persisted is not None
    assert persisted["cohort"] == cohort


def test_question_api_hard_stop_and_explicit_override(monkeypatch, ledger_path):
    monkeypatch.setenv("ARCHIVIST_USAGE_DB", str(ledger_path))
    ledger = UsageLedger()
    ledger.update_settings(
        monthly_budget_usd="0.01",
        warning_threshold_percent=80,
        hard_limit_enabled=True,
    )
    ledger.record(
        response_id="already-spent",
        operation="answer_generation",
        requested_model="gpt-5",
        actual_model="gpt-5",
        usage=TokenUsage(input_tokens=10_000, total_tokens=10_000),
    )

    blocked = web_api.QuestionRequest(question="Question?")
    with pytest.raises(HTTPException) as exc_info:
        web_api.question("current", blocked)
    assert exc_info.value.status_code == 402
    assert exc_info.value.detail["code"] == "cost_limit_exceeded"
    assert exc_info.value.detail["budget"]["exceeded"] is True

    monkeypatch.setattr(
        web_api,
        "answer_project_question_result",
        lambda *_args, **_kwargs: SimpleNamespace(
            answer="Allowed answer.",
            final_chunks=[],
            status="answered",
            evidence_decision="direct_answer",
            resolved_question="Question?",
        ),
    )
    allowed = web_api.QuestionRequest(question="Question?", allow_over_budget=True)
    assert web_api.question("current", allowed)["answer"] == "Allowed answer."


def test_post_answer_summary_failure_does_not_discard_paid_answer(monkeypatch):
    class BrokenSummaryLedger:
        def budget_state(self):
            return {
                "monthly_budget_usd": None,
                "warning_threshold_percent": 80,
                "hard_limit_enabled": False,
                "percent_used": None,
                "remaining_usd": None,
                "warning": False,
                "exceeded": False,
            }

        def summary(self, **_filters):
            raise RuntimeError("ledger became unavailable")

    monkeypatch.setattr(web_api, "UsageLedger", BrokenSummaryLedger)
    monkeypatch.setattr(
        web_api,
        "answer_project_question_result",
        lambda *_args, **_kwargs: SimpleNamespace(
            answer="Paid answer.",
            final_chunks=[],
            status="answered",
            evidence_decision="direct_answer",
            resolved_question="Question?",
        ),
    )

    response = web_api.question("current", web_api.QuestionRequest(question="Question?"))

    assert response["answer"] == "Paid answer."
    assert response["costs"] is None


def test_tracked_calls_recheck_hard_limit_between_operations(monkeypatch):
    class SequencedLedger:
        def __init__(self):
            self.checks = 0

        def budget_state(self):
            self.checks += 1
            exceeded = self.checks > 1
            return {
                "hard_limit_enabled": True,
                "exceeded": exceeded,
            }

    class FakeResponses:
        def __init__(self):
            self.calls = 0

        def create(self, **_request):
            self.calls += 1
            return SimpleNamespace(id=f"response-{self.calls}")

    ledger = SequencedLedger()
    responses = FakeResponses()
    monkeypatch.setattr(costs, "UsageLedger", lambda: ledger)
    client = SimpleNamespace(responses=responses)

    with usage_scope(enforce_budget=True):
        tracked_responses_create(
            client,
            operation="first",
            model="gpt-5",
            input="Synthetic input.",
        )
        with pytest.raises(CostLimitExceeded):
            tracked_responses_create(
                client,
                operation="second",
                model="gpt-5",
                input="Synthetic input.",
            )

    assert ledger.checks == 2
    assert responses.calls == 1


def test_explicit_budget_override_applies_to_every_tracked_operation(monkeypatch):
    monkeypatch.setattr(
        costs,
        "UsageLedger",
        lambda: (_ for _ in ()).throw(AssertionError("override must skip budget reads")),
    )

    class FakeEmbeddings:
        def __init__(self):
            self.calls = 0

        def create(self, **_request):
            self.calls += 1
            return SimpleNamespace(id=f"embedding-{self.calls}")

    embeddings = FakeEmbeddings()
    with usage_scope(enforce_budget=True, allow_over_budget=True):
        tracked_embeddings_create(
            SimpleNamespace(embeddings=embeddings),
            operation="query_embedding",
            model="text-embedding-3-small",
            input=["Synthetic query."],
        )
        tracked_embeddings_create(
            SimpleNamespace(embeddings=embeddings),
            operation="query_embedding",
            model="text-embedding-3-small",
            input=["Another synthetic query."],
        )

    assert embeddings.calls == 2


def test_question_api_reports_a_mid_turn_cost_stop_as_payment_required(
    monkeypatch,
):
    available = {
        "hard_limit_enabled": True,
        "exceeded": False,
    }
    exceeded = {
        "hard_limit_enabled": True,
        "exceeded": True,
    }

    class InitiallyAvailableLedger:
        def budget_state(self):
            return available

    monkeypatch.setattr(web_api, "UsageLedger", InitiallyAvailableLedger)
    monkeypatch.setattr(
        web_api,
        "answer_project_question_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(CostLimitExceeded(exceeded)),
    )

    with pytest.raises(HTTPException) as exc_info:
        web_api.question(
            "current",
            web_api.QuestionRequest(question="Synthetic question?"),
        )

    assert exc_info.value.status_code == 402
    assert exc_info.value.detail["code"] == "cost_limit_exceeded"
    assert exc_info.value.detail["budget"] == exceeded


def test_request_and_settings_validation():
    request = web_api.QuestionRequest(question="Question?")
    assert request.conversation_id is None
    assert request.turn_id is None
    assert request.allow_over_budget is False
    for identifier in ("../escape", "has whitespace", "", "x" * 129):
        with pytest.raises(ValidationError):
            web_api.QuestionRequest(question="Question?", conversation_id=identifier)
    with pytest.raises(ValidationError):
        web_api.CostSettingsRequest(
            monthly_budget_usd="0.009",
            warning_threshold_percent=80,
            hard_limit_enabled=False,
        )
