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
from answer_progress import ProviderStreamMilestone
from costs import (
    CostLimitExceeded,
    MODEL_PRICING,
    PRICING_VERSION,
    PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD,
    TokenUsage,
    UsageLedger,
    calculate_cost_nano_usd,
    current_usage_context,
    extract_token_usage,
    projected_provider_operation_cost_nano_usd,
    record_openai_response,
    tracked_embeddings_create,
    tracked_responses_create,
    tracked_responses_parse,
    tracked_responses_stream,
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
        "schema": "archivist.answer_run_diagnostics/3",
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
        "content_outcome": None,
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
        request_id="a" * 32,
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
    assert stored["request_id"] == "a" * 32
    assert ledger.get_answer_run_diagnostics_by_request_id("a" * 32) == stored
    assert stored["cohort"]["rag_policy_version"] == "evidence-planned-v4"
    assert stored["planner"]["status"] == "not_called"
    assert stored["stage_timings_ms"]["answer_generation"] == 240.125
    assert "question" not in str(stored).casefold()
    first_run_id = stored["run_id"]

    repaired = answer_run_diagnostics_payload(
        answer_status="answered",
        validation_result="valid",
        content_outcome="valid_partial",
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
        request_id="b" * 32,
        diagnostics=repaired,
    )
    updated = ledger.get_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
    )
    assert updated is not None
    assert updated["run_id"] != first_run_id
    assert updated["request_id"] == "b" * 32
    assert ledger.get_answer_run_diagnostics_by_request_id("a" * 32) is None
    assert updated["answer_status"] == "answered"
    assert updated["content_outcome"] == "valid_partial"
    assert updated["repair_codes"] == ["source_mapping_mismatch"]
    assert updated["planner"]["exception_class"] == "SyntheticPlannerFailure"
    assert updated["planner"]["exception_code"] == "rate-limit/429"


def test_public_request_observation_round_trip_recovery_and_privacy(ledger_path):
    ledger = UsageLedger(ledger_path)
    fields = {
        "request_id": "c" * 32,
        "recorded_at": "2026-08-10T12:00:00+00:00",
        "deployment_commit": "d" * 40,
        "process_epoch": "e" * 32,
        "render_instance_id": "srv-opaque-1",
        "route": "question",
        "delivery": "complete",
        "conversation_id": "cohort-01",
        "turn_id": "turn-01",
        "archivist_mode": "essential",
        "answer_strategy": "rag",
        "http_status": 200,
        "duration_ms": 1234.5678,
    }

    assert ledger.record_public_request_observation(**fields)
    assert not ledger.record_public_request_observation(**fields)
    stored = ledger.get_public_request_observation("c" * 32)

    assert stored == {
        "schema": "archivist.public_request_observation/1",
        **fields,
        "duration_ms": 1234.568,
    }
    assert ledger.find_public_request_observation(
        conversation_id="cohort-01",
        turn_id="turn-01",
    ) == stored
    assert (
        ledger.find_public_request_observation(
            conversation_id="cohort-01",
            turn_id="turn-01",
            recorded_at_gte="2026-08-10T12:00:01+00:00",
        )
        is None
    )
    assert not {
        "question",
        "answer",
        "source",
        "history",
        "ip",
    }.intersection(stored)


def test_request_id_correlates_usage_totals_without_changing_legacy_scope(ledger_path):
    ledger = UsageLedger(ledger_path)
    request_id = "f" * 32
    assert ledger.record(
        response_id="response-request-correlated",
        operation="answer",
        requested_model="gpt-5.6-sol",
        actual_model="gpt-5.6-sol",
        usage=TokenUsage(input_tokens=10, output_tokens=4, total_tokens=14),
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
        request_id=request_id,
    )

    totals = ledger.request_usage_totals(request_id)
    assert totals["event_count"] == 1
    assert totals["total_tokens"] == 14
    assert ledger.request_usage_totals("0" * 32)["event_count"] == 0


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
    assert stored["schema"] == "archivist.answer_run_diagnostics/3"
    assert stored["content_outcome"] is None
    assert stored["cohort"] == costs.HISTORICAL_UNKNOWN_COHORT
    assert stored["planner"] == {
        "schema": "archivist.planner_call_diagnostics/1",
        "status": "unknown",
        "failure_code": None,
        "exception_class": None,
        "exception_code": None,
    }


def test_historical_unknown_diagnostics_are_valid_v3_write_contract(ledger_path):
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
    with usage_scope(
        project_id="p1",
        conversation_id="c1",
        turn_id="t1",
        request_id="1" * 32,
    ):
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
                   request_id, requested_model, actual_model
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
            "1" * 32,
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


def test_structured_stream_tracks_terminal_usage_then_parses(monkeypatch):
    class StructuredPayload(BaseModel):
        result: str

    output_text = json.dumps({"result": "ok"})
    response_body = {
        "id": "structured-stream-response",
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
                        "text": output_text,
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
    events = [
        {
            "type": "response.output_text.delta",
            "item_id": "message-1",
            "output_index": 0,
            "content_index": 0,
            "delta": output_text[:8],
            "logprobs": [],
            "sequence_number": 1,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "message-1",
            "output_index": 0,
            "content_index": 0,
            "delta": output_text[8:],
            "logprobs": [],
            "sequence_number": 2,
        },
        {
            "type": "response.completed",
            "response": response_body,
            "sequence_number": 3,
        },
    ]
    sse = "".join(
        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
    )
    requests = []
    tracked = []
    milestones = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            content=sse.encode(),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    monkeypatch.setattr(
        costs,
        "record_openai_response",
        lambda response, **metadata: tracked.append((response, metadata)),
    )
    client = OpenAI(
        api_key="local-test-key",
        base_url="https://example.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    deltas = []
    try:
        response = tracked_responses_stream(
            client,
            operation="answer_generation",
            model="gpt-5.6-sol",
            input="structured prompt",
            text_format=StructuredPayload,
            on_text_delta=deltas.append,
            stream_milestone_callback=milestones.append,
        )
    finally:
        client.close()

    assert response.output_parsed == StructuredPayload(result="ok")
    assert deltas == [output_text[:8], output_text[8:]]
    assert milestones == [
        ProviderStreamMilestone.FIRST_DELTA,
        ProviderStreamMilestone.TERMINAL,
    ]
    assert len(requests) == 1
    assert json.loads(requests[0].content)["stream"] is True
    assert len(tracked) == 1
    assert tracked[0][0].id == "structured-stream-response"
    assert tracked[0][1] == {
        "operation": "answer_generation",
        "requested_model": "gpt-5.6-sol",
    }


def test_structured_stream_tracks_usage_before_local_validation_error(monkeypatch):
    class StructuredPayload(BaseModel):
        result: str

    output_text = json.dumps({"wrong": "shape"})
    response_body = {
        "id": "invalid-structured-stream-response",
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
                        "text": output_text,
                    }
                ],
            }
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "status": "completed",
        "usage": {
            "input_tokens": 2,
            "input_tokens_details": {
                "cached_tokens": 0,
                "cache_write_tokens": 0,
            },
            "output_tokens": 2,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 4,
        },
    }
    completed = {
        "type": "response.completed",
        "response": response_body,
        "sequence_number": 1,
    }
    sse = (
        "event: response.completed\n"
        f"data: {json.dumps(completed)}\n\n"
    )
    tracked = []

    def handler(request):
        return httpx.Response(
            200,
            content=sse.encode(),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    monkeypatch.setattr(
        costs,
        "record_openai_response",
        lambda response, **metadata: tracked.append((response, metadata)),
    )
    client = OpenAI(
        api_key="local-test-key",
        base_url="https://example.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(ValidationError):
            tracked_responses_stream(
                client,
                operation="answer_generation",
                model="gpt-5.6-sol",
                input="structured prompt",
                text_format=StructuredPayload,
            )
    finally:
        client.close()

    assert len(tracked) == 1
    assert tracked[0][0].id == "invalid-structured-stream-response"


class _ScriptedResponseStream:
    def __init__(
        self,
        *events,
        iteration_error: BaseException | None = None,
        close_error: BaseException | None = None,
    ):
        self._events = iter(events)
        self._iteration_error = iteration_error
        self._close_error = close_error
        self.close_calls = 0

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._events)
        except StopIteration:
            if self._iteration_error is not None:
                error = self._iteration_error
                self._iteration_error = None
                raise error
            raise

    def close(self):
        self.close_calls += 1
        if self._close_error is not None:
            raise self._close_error


def _scripted_stream_client(stream, requests):
    def create(**request):
        requests.append(request)
        return stream

    return SimpleNamespace(responses=SimpleNamespace(create=create))


def test_structured_stream_accounts_for_terminal_before_later_iterator_error(
    monkeypatch,
):
    class StructuredPayload(BaseModel):
        result: str

    terminal = SimpleNamespace(id="terminal-before-iterator-error")
    stream = _ScriptedResponseStream(
        SimpleNamespace(type="response.completed", response=terminal),
        iteration_error=RuntimeError("iterator failed after terminal"),
    )
    requests = []
    tracked = []
    monkeypatch.setattr(
        costs,
        "record_openai_response",
        lambda response, **metadata: tracked.append((response, metadata)),
    )
    monkeypatch.setattr(
        costs,
        "_parse_streamed_response",
        lambda **_kwargs: pytest.fail("terminal parsing must not hide an iterator error"),
    )

    with pytest.raises(RuntimeError, match="iterator failed after terminal"):
        tracked_responses_stream(
            _scripted_stream_client(stream, requests),
            operation="answer_generation",
            model="gpt-5.6-sol",
            input="structured prompt",
            text_format=StructuredPayload,
        )

    assert len(requests) == 1
    assert stream.close_calls == 1
    assert tracked == [
        (
            terminal,
            {
                "operation": "answer_generation",
                "requested_model": "gpt-5.6-sol",
            },
        )
    ]


def test_structured_stream_accounts_for_terminal_before_close_error(monkeypatch):
    class StructuredPayload(BaseModel):
        result: str

    terminal = SimpleNamespace(id="terminal-before-close-error")
    stream = _ScriptedResponseStream(
        SimpleNamespace(type="response.completed", response=terminal),
        close_error=OSError("stream close failed"),
    )
    requests = []
    tracked = []
    monkeypatch.setattr(
        costs,
        "record_openai_response",
        lambda response, **metadata: tracked.append((response, metadata)),
    )
    monkeypatch.setattr(
        costs,
        "_parse_streamed_response",
        lambda **_kwargs: pytest.fail("terminal parsing must not hide a close error"),
    )

    with pytest.raises(OSError, match="stream close failed"):
        tracked_responses_stream(
            _scripted_stream_client(stream, requests),
            operation="answer_generation",
            model="gpt-5.6-sol",
            input="structured prompt",
            text_format=StructuredPayload,
        )

    assert len(requests) == 1
    assert stream.close_calls == 1
    assert tracked == [
        (
            terminal,
            {
                "operation": "answer_generation",
                "requested_model": "gpt-5.6-sol",
            },
        )
    ]


def test_structured_stream_success_accounts_once_and_parses_terminal(monkeypatch):
    class StructuredPayload(BaseModel):
        result: str

    terminal = SimpleNamespace(id="successful-terminal")
    parsed = SimpleNamespace(output_parsed=StructuredPayload(result="ok"))
    stream = _ScriptedResponseStream(
        SimpleNamespace(type="response.completed", response=terminal)
    )
    requests = []
    tracked = []
    parsed_terminals = []
    monkeypatch.setattr(
        costs,
        "record_openai_response",
        lambda response, **metadata: tracked.append((response, metadata)),
    )

    def parse_terminal(**kwargs):
        parsed_terminals.append(kwargs["response"])
        return parsed

    monkeypatch.setattr(costs, "_parse_streamed_response", parse_terminal)

    result = tracked_responses_stream(
        _scripted_stream_client(stream, requests),
        operation="answer_generation",
        model="gpt-5.6-sol",
        input="structured prompt",
        text_format=StructuredPayload,
    )

    assert result is parsed
    assert len(requests) == 1
    assert stream.close_calls == 1
    assert parsed_terminals == [terminal]
    assert len(tracked) == 1
    assert tracked[0][0] is terminal


def test_structured_stream_without_terminal_closes_and_does_not_account(monkeypatch):
    class StructuredPayload(BaseModel):
        result: str

    stream = _ScriptedResponseStream()
    requests = []
    tracked = []
    monkeypatch.setattr(
        costs,
        "record_openai_response",
        lambda response, **metadata: tracked.append((response, metadata)),
    )
    monkeypatch.setattr(
        costs,
        "_parse_streamed_response",
        lambda **_kwargs: pytest.fail("a missing terminal response cannot be parsed"),
    )

    with pytest.raises(
        RuntimeError,
        match="OpenAI response stream ended without a terminal response",
    ):
        tracked_responses_stream(
            _scripted_stream_client(stream, requests),
            operation="answer_generation",
            model="gpt-5.6-sol",
            input="structured prompt",
            text_format=StructuredPayload,
        )

    assert len(requests) == 1
    assert stream.close_calls == 1
    assert tracked == []


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
        archivist_mode,
        answer_strategy="rag",
        application_compiled=False,
    ):
        captured.append(
            (
                "answer",
                project_id,
                question,
                history,
                current_usage_context(),
                archivist_mode,
                application_compiled,
            )
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
            answer_strategy=answer_strategy,
            answer_strategy_version="application-compiled-v1",
            diagnostics={
                "generation": {
                    "validation_result": "valid",
                    "prompt_version": "evidence-prose-renderer-v3",
                    "normalizer_version": "application-compiled-v1",
                    "instructions_sha256": "a" * 64,
                    "schema_sha256": "b" * 64,
                    "generator_model": "gpt-5.6-sol",
                    "generator_reasoning_effort": "low",
                    "generator_verbosity": "low",
                }
            },
        )

    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    request = web_api.QuestionRequest(
        question="What happened next?",
        history=[{"question": "Who?", "answer": "A prior answer."}],
        archivist_mode="professional",
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
    assert captured[0][5] is web_api.ArchivistMode.PROFESSIONAL
    assert captured[0][6] is True
    assert response["conversation_id"] == "conversation-1"
    assert response["turn_id"] == "turn-1"
    assert response["resolved_query"] == "Standalone question?"
    run_diagnostics = dict(response["run_diagnostics"])
    cohort = run_diagnostics.pop("cohort")
    assert cohort["rag_policy_version"] == "application-compiled-v1"
    assert cohort["query_planner_prompt_version"] == "not-applicable"
    assert cohort["coverage_prompt_version"] == "evidence-prose-renderer-v3"
    assert cohort["normalizer_version"] == "application-compiled-v1"
    assert len(cohort["coverage_instructions_sha256"]) == 64
    assert run_diagnostics == {
        "schema": "archivist.answer_run_diagnostics/3",
        "answer_status": "answered",
        "evidence_decision": "direct_answer",
        "validation_result": "valid",
        "content_outcome": None,
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
        "answer_generation",
    }
    persisted = UsageLedger().get_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
    )
    assert persisted is not None
    assert persisted["answer_status"] == "answered"
    assert persisted["validation_result"] == "valid"


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


def test_question_api_essential_bypasses_budget_but_professional_hard_stops(
    monkeypatch,
    ledger_path,
):
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

    contexts = []

    def fake_answer(*_args, **_kwargs):
        contexts.append(current_usage_context())
        return SimpleNamespace(
            answer="Allowed answer.",
            final_chunks=[],
            status="answered",
            evidence_decision="direct_answer",
            resolved_question="Question?",
            answer_strategy_version="application-compiled-v1",
            diagnostics={},
        )

    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)

    essential = web_api.QuestionRequest(question="Question?")
    assert web_api.question("current", essential)["answer"] == "Allowed answer."
    assert contexts[-1].enforce_budget is False

    blocked = web_api.QuestionRequest(
        question="Question?",
        archivist_mode="professional",
    )
    with pytest.raises(HTTPException) as exc_info:
        web_api.question("current", blocked)
    assert exc_info.value.status_code == 402
    assert exc_info.value.detail["code"] == "cost_limit_exceeded"
    assert exc_info.value.detail["budget"]["exceeded"] is True

    allowed = web_api.QuestionRequest(
        question="Question?",
        archivist_mode="professional",
        allow_over_budget=True,
    )
    assert web_api.question("current", allowed)["answer"] == "Allowed answer."
    assert contexts[-1].enforce_budget is True
    assert contexts[-1].allow_over_budget is True


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


def test_projected_budget_blocks_a_long_request_before_it_crosses_the_limit():
    from costs import enforce_projected_usage_budget

    class NearlySpentLedger:
        def budget_state(self):
            return {
                "hard_limit_enabled": True,
                "exceeded": False,
                "remaining_usd": 0.5,
            }

    with usage_scope(enforce_budget=True):
        with pytest.raises(CostLimitExceeded) as exc_info:
            enforce_projected_usage_budget(500_000_001, NearlySpentLedger())

    assert exc_info.value.budget["projected_request_usd"] == 0.500000001
    assert exc_info.value.budget["projected_exceeds_remaining"] is True


def test_projected_budget_allows_exact_remaining_cost_and_explicit_override():
    from costs import enforce_projected_usage_budget

    class ExactLedger:
        def __init__(self):
            self.checks = 0

        def budget_state(self):
            self.checks += 1
            return {
                "hard_limit_enabled": True,
                "exceeded": False,
                "remaining_usd": 0.5,
            }

    ledger = ExactLedger()
    with usage_scope(enforce_budget=True):
        enforce_projected_usage_budget(500_000_000, ledger)
    with usage_scope(enforce_budget=True, allow_over_budget=True):
        enforce_projected_usage_budget(900_000_000, ledger)

    assert ledger.checks == 1


def test_projected_budget_rejects_negative_estimates():
    from costs import enforce_projected_usage_budget

    with pytest.raises(ValueError, match="must be non-negative"):
        enforce_projected_usage_budget(-1)


def test_public_rag_operation_projection_includes_input_output_and_schema():
    class StructuredPayload(BaseModel):
        result: str

    small = projected_provider_operation_cost_nano_usd(
        provider_kind="responses",
        request={
            "model": "gpt-5.6-sol",
            "input": "short",
            "text_format": StructuredPayload,
            "max_output_tokens": 100,
        },
    )
    larger = projected_provider_operation_cost_nano_usd(
        provider_kind="responses",
        request={
            "model": "gpt-5.6-sol",
            "input": "x" * 10_000,
            "text_format": StructuredPayload,
            "max_output_tokens": 1_000,
        },
    )

    assert 0 < small < larger < PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD


def test_public_rag_operation_projection_uses_worst_case_cache_write_rate():
    request = {
        "model": "gpt-5.6-sol",
        "input": "bounded request",
        "max_output_tokens": 1_000,
    }
    projected = projected_provider_operation_cost_nano_usd(
        provider_kind="responses",
        request=request,
    )
    serialized_bytes = len(
        json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    input_upper_bound = (
        serialized_bytes + costs.PROVIDER_REQUEST_TOKEN_OVERHEAD_UPPER_BOUND
    )
    expected = calculate_cost_nano_usd(
        "gpt-5.6-sol",
        TokenUsage(
            input_tokens=input_upper_bound,
            cache_write_tokens=input_upper_bound,
            output_tokens=1_000,
            total_tokens=input_upper_bound + 1_000,
        ),
    )

    assert projected == expected


def test_request_operation_ceiling_blocks_before_provider_client_operation(monkeypatch):
    class NearlySpentLedger:
        def request_usage_cost_state(self, _request_id):
            return {
                "estimated_cost_nano_usd": 1_900_000_000,
                "event_count": 1,
                "unpriced_count": 0,
            }

    class FakeResponses:
        def __init__(self):
            self.calls = 0

        def create(self, **_request):
            self.calls += 1
            raise AssertionError("provider operation must not begin")

    responses = FakeResponses()
    monkeypatch.setattr(costs, "UsageLedger", NearlySpentLedger)
    with usage_scope(
        request_id="a" * 32,
        request_cost_ceiling_nano_usd=PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD,
    ):
        with pytest.raises(CostLimitExceeded) as exc_info:
            tracked_responses_create(
                SimpleNamespace(responses=responses),
                operation="answer_generation",
                model="gpt-5.6-sol",
                input="bounded prompt",
                max_output_tokens=12_000,
            )

    assert responses.calls == 0
    assert (
        exc_info.value.budget["request_cost_failure"]
        == "request_cost_ceiling_would_be_exceeded"
    )


def test_unknown_request_value_fails_closed_before_provider_client_operation(monkeypatch):
    class EmptyLedger:
        def request_usage_cost_state(self, _request_id):
            return {
                "estimated_cost_nano_usd": 0,
                "event_count": 0,
                "unpriced_count": 0,
            }

    class UnknownRequestValue:
        pass

    class FakeResponses:
        def __init__(self):
            self.calls = 0

        def create(self, **_request):
            self.calls += 1
            raise AssertionError("provider operation must not begin")

    responses = FakeResponses()
    monkeypatch.setattr(costs, "UsageLedger", EmptyLedger)
    with usage_scope(
        request_id="c" * 32,
        request_cost_ceiling_nano_usd=PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD,
    ):
        with pytest.raises(CostLimitExceeded) as exc_info:
            tracked_responses_create(
                SimpleNamespace(responses=responses),
                operation="answer_generation",
                model="gpt-5.6-sol",
                input=UnknownRequestValue(),
                max_output_tokens=12_000,
            )

    assert responses.calls == 0
    assert (
        exc_info.value.budget["request_cost_failure"]
        == "request_cost_projection_failed"
    )


def test_strict_request_scope_rejects_missing_usage_after_paid_operation(monkeypatch):
    class EmptyLedger:
        def request_usage_cost_state(self, _request_id):
            return {
                "estimated_cost_nano_usd": 0,
                "event_count": 0,
                "unpriced_count": 0,
            }

    class FakeResponses:
        def __init__(self):
            self.calls = 0

        def create(self, **_request):
            self.calls += 1
            return SimpleNamespace(id="paid-without-usage", model="gpt-5.6-sol")

    responses = FakeResponses()
    monkeypatch.setattr(costs, "UsageLedger", EmptyLedger)
    monkeypatch.setattr(costs, "record_openai_response", lambda *_args, **_kwargs: False)
    with usage_scope(
        request_id="b" * 32,
        request_cost_ceiling_nano_usd=PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD,
    ):
        with pytest.raises(CostLimitExceeded) as exc_info:
            tracked_responses_create(
                SimpleNamespace(responses=responses),
                operation="query_planning",
                model="gpt-5.6-sol",
                input="bounded prompt",
                max_output_tokens=4_000,
            )

    assert responses.calls == 1
    assert (
        exc_info.value.budget["request_cost_failure"]
        == "usage_tracking_missing_or_duplicate"
    )


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


def test_long_context_surcharge_applies_only_above_the_documented_threshold():
    from costs import LONG_CONTEXT_INPUT_TOKEN_THRESHOLD

    below = TokenUsage(
        input_tokens=LONG_CONTEXT_INPUT_TOKEN_THRESHOLD,
        output_tokens=1_000,
        total_tokens=LONG_CONTEXT_INPUT_TOKEN_THRESHOLD + 1_000,
    )
    above = TokenUsage(
        input_tokens=LONG_CONTEXT_INPUT_TOKEN_THRESHOLD + 1,
        output_tokens=1_000,
        total_tokens=LONG_CONTEXT_INPUT_TOKEN_THRESHOLD + 1_001,
    )

    below_cost = calculate_cost_nano_usd("gpt-5.6-sol", below)
    above_cost = calculate_cost_nano_usd("gpt-5.6-sol", above)

    # $5/M input, $30/M output, unsurcharged.
    assert below_cost == 272_000 * 5_000 + 1_000 * 30_000
    # 2x input and 1.5x output, for the whole request.
    assert above_cost == 272_001 * 5_000 * 2 + 1_000 * 30_000 * 3 // 2


def test_existing_retrieval_sized_requests_keep_their_previous_estimate():
    # The surcharge must not silently move any number in an existing cohort, so
    # a RAG-sized request is priced exactly as it was before the branch existed.
    usage = TokenUsage(input_tokens=20_000, output_tokens=4_000, total_tokens=24_000)

    assert calculate_cost_nano_usd("gpt-5.6-sol", usage) == 20_000 * 5_000 + 4_000 * 30_000


def test_models_without_a_documented_long_context_tier_are_never_surcharged():
    huge = TokenUsage(input_tokens=1_000_000, total_tokens=1_000_000)

    assert calculate_cost_nano_usd("text-embedding-3-small", huge) == 20_000_000
    assert calculate_cost_nano_usd("gpt-5", huge) == 1_250_000_000


def test_cache_detail_is_read_from_either_responses_or_chat_completions_shape():
    responses_shape = extract_token_usage(
        SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=1_000,
                output_tokens=10,
                total_tokens=1_010,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=400,
                    cache_write_tokens=200,
                ),
            )
        )
    )
    completions_shape = extract_token_usage(
        SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=1_000,
                output_tokens=10,
                total_tokens=1_010,
                prompt_tokens_details=SimpleNamespace(
                    cached_tokens=400,
                    cache_write_tokens=200,
                ),
            )
        )
    )

    assert responses_shape == completions_shape
    assert responses_shape.cached_tokens == 400
    assert responses_shape.cache_write_tokens == 200


def test_answer_strategy_is_optional_in_the_cohort_and_nullable_in_the_ledger(ledger_path):
    ledger = UsageLedger(ledger_path)

    # A payload written before answer strategies existed still validates.
    assert ledger.record_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-legacy",
        turn_id="turn-1",
        diagnostics=answer_run_diagnostics_payload(),
    )
    legacy = ledger.get_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-legacy",
        turn_id="turn-1",
    )
    assert legacy is not None
    # Never backfilled to "rag": the row genuinely did not record a strategy.
    assert legacy["answer_strategy"] is None

    strategy_payload = answer_run_diagnostics_payload()
    strategy_payload["cohort"] = {
        **strategy_payload["cohort"],
        "answer_strategy": "full_context",
        "answer_strategy_version": "full-context-v1",
    }
    assert ledger.record_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-full-context",
        turn_id="turn-1",
        diagnostics=strategy_payload,
    )
    stored = ledger.get_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-full-context",
        turn_id="turn-1",
    )
    assert stored is not None
    assert stored["answer_strategy"] == "full_context"
    assert stored["cohort"]["answer_strategy_version"] == "full-context-v1"
