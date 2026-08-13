from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import retrieval_authored_v4_evaluation as v4
from costs import TokenUsage, UsageLedger, current_usage_context


@pytest.fixture
def local_root() -> Iterator[Path]:
    path = (
        Path(__file__).resolve().parents[1]
        / "runtime"
        / "evaluations"
        / f"_v4_test_{uuid4().hex}"
    )
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path)


def _paths(root: Path) -> v4.V4Paths:
    placeholder = root / "placeholder"
    return v4.V4Paths(
        root=root,
        gold=placeholder,
        provenance=placeholder,
        question_commitment=placeholder,
        corpus_manifest=placeholder,
        chunks=placeholder,
        cache=placeholder,
        catalog=placeholder,
        uv_lock=placeholder,
        chroma=placeholder,
    )


def _projection(cost: int = 100) -> dict[str, object]:
    return {
        "operation": "answer_generation",
        "provider_kind": "responses",
        "request_binding": {"item_id": "H001"},
        "request_binding_sha256": v4.canonical_json_sha256({"item_id": "H001"}),
        "provider_request_shape_sha256": "a" * 64,
        "provider_request_serialized_bytes": 10,
        "provider_request_token_overhead_upper_bound": 10,
        "provider_input_token_upper_bound": 20,
        "max_output_tokens": 10,
        "projected_worst_case_nano_usd": cost,
        "projection_method": "test",
    }


def _intent(projection: dict[str, object] | None = None) -> dict[str, object]:
    return v4.build_attempt_intent(
        cohort_manifest_sha256="b" * 64,
        turn_id="generation:H001",
        item_id="H001",
        phase="generation",
        projection=projection or _projection(),
    )


def _settle_zero_event(
    paths: v4.V4Paths,
    *,
    phase: str = "generation",
    item_id: str = "H001",
    operation: str = "answer_generation",
    schema: str = v4.V4_GENERATION_OUTCOME_SCHEMA,
    cap_nano_usd: int = 1_000,
) -> dict[str, object]:
    turn_id = f"{phase}:{item_id}"
    projection = _projection()
    projection["operation"] = operation
    intent = v4.build_attempt_intent(
        cohort_manifest_sha256="b" * 64,
        turn_id=turn_id,
        item_id=item_id,
        phase=phase,
        projection=projection,
    )
    seal = v4.prepare_attempt(paths, intent=intent, cap_nano_usd=cap_nano_usd)
    seal()
    outcome = {
        "schema": schema,
        "evaluation_id": v4.EVALUATION_ID,
        "item_id": item_id,
        "status": "technical_failure",
        "failure_category": "usage_contract_failure",
        "intent_sha256": v4.canonical_json_sha256(intent),
        "provider_boundary_attempt_count": 1,
        "automatic_retries": 0,
        "operation_evidence": v4.operation_evidence(
            paths,
            turn_id=turn_id,
            operation=operation,
        ),
    }
    v4.settle_attempt(
        paths,
        intent=intent,
        outcome=outcome,
        cap_nano_usd=cap_nano_usd,
    )
    return outcome


def _seal_intentionally_unattempted_rubric(
    paths: v4.V4Paths,
    *,
    item_id: str = "H001",
) -> None:
    turn_id = f"rubric:{item_id}"
    intent = {
        "schema": v4.V4_INTENT_SCHEMA,
        "evaluation_id": v4.EVALUATION_ID,
        "cohort_manifest_sha256": "b" * 64,
        "turn_id": turn_id,
        "item_id": item_id,
        "phase": "rubric",
        "attempt_count": 0,
        "automatic_retries": 0,
        "replacement": False,
        "request_projection": None,
    }
    intent_path, marker_path, outcome_path = v4.attempt_paths(paths, turn_id=turn_id)
    v4.write_or_validate_json(intent_path, intent)
    v4.write_or_validate_json(
        marker_path,
        {
            "schema": v4.V4_ATTEMPT_STARTED_SCHEMA,
            "evaluation_id": v4.EVALUATION_ID,
            "turn_id": turn_id,
            "intent_sha256": v4.canonical_json_sha256(intent),
            "provider_boundary_not_crossed": True,
            "projected_worst_case_nano_usd": 0,
        },
    )
    v4.write_or_validate_json(
        outcome_path,
        v4._no_boundary_rubric_outcome(paths, intent=intent),
    )


def _record_usage(
    paths: v4.V4Paths,
    *,
    turn_id: str,
    operation: str,
    requested_model: str,
    actual_model: str,
) -> None:
    UsageLedger(paths.ledger).record(
        response_id=f"response-{uuid4().hex}",
        operation=operation,
        requested_model=requested_model,
        actual_model=actual_model,
        usage=TokenUsage(input_tokens=10, output_tokens=10, total_tokens=20),
        project_id=v4.MASTER_PROJECT_ID,
        conversation_id=v4.MASTER_CONVERSATION_ID,
        turn_id=turn_id,
        request_id=v4.MASTER_REQUEST_ID,
    )


def test_sentinel_is_first_ten_and_never_a_separate_repeat() -> None:
    items = tuple({"id": item_id} for item_id in v4.LOCKED_ITEM_IDS)
    cohort = SimpleNamespace(items=items)

    assert [value["id"] for value in v4._generation_items(cohort, sentinel=True)] == [
        f"H{index:03d}" for index in range(1, 11)
    ]
    assert [value["id"] for value in v4._generation_items(cohort, sentinel=False)] == [
        *[f"H{index:03d}" for index in range(11, 20)],
        *[f"H{index:03d}" for index in range(21, 39)],
    ]


def test_attempt_intent_and_boundary_are_atomic_and_no_retry(local_root: Path) -> None:
    paths = _paths(local_root)
    intent = _intent()
    seal = v4.prepare_attempt(paths, intent=intent, cap_nano_usd=1_000)
    intent_path, marker_path, _ = v4.attempt_paths(paths, turn_id="generation:H001")

    assert intent_path.is_file()
    assert not marker_path.exists()
    seal()
    assert marker_path.is_file()
    with pytest.raises(v4.V4EvaluationError, match="already crossed"):
        v4.prepare_attempt(paths, intent=intent, cap_nano_usd=1_000)


def test_zero_event_is_reserved_and_counts_against_exact_cap(local_root: Path) -> None:
    paths = _paths(local_root)
    _settle_zero_event(paths, cap_nano_usd=150)
    state = v4.budget_state(paths, cap_nano_usd=150)
    assert state["ambiguity_reserved_nano_usd"] == 100
    assert state["remaining_nano_usd"] == 50
    with pytest.raises(v4.V4EvaluationError, match="exceed"):
        v4.require_projection_headroom(
            paths,
            cap_nano_usd=150,
            projected_nano_usd=51,
        )


def test_master_scope_uses_effective_cap_not_remaining_balance(
    local_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(local_root)
    monkeypatch.setattr(
        v4,
        "budget_state",
        lambda _paths, *, cap_nano_usd: {
            "ambiguity_reserved_nano_usd": 100_000_000,
            "remaining_nano_usd": 400_000_000,
        },
    )

    with v4.master_usage_scope(
        paths,
        cap_nano_usd=1_000_000_000,
        turn_id="rubric:H036",
    ):
        context = current_usage_context()
        assert context.request_cost_ceiling_nano_usd == 900_000_000
        assert context.request_cost_ceiling_nano_usd != 400_000_000


def test_harness_scope_continuation_binds_unattempted_rubric_turn(
    local_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(local_root)
    v4.atomic_seal_json(
        paths.cohort_manifest,
        {
            "system_under_test": {
                "harness_commit": "a" * 40,
                "product_commit": "c" * 40,
            },
            "paid_scope": {"maximum_total_cost_nano_usd": 7_000_000_000},
        },
    )
    v4.atomic_seal_json(paths.trace_scope_continuation, {"sealed": "trace"})
    projection = _projection(cost=163_890_625)
    projection["operation"] = "eval_item_rubric"
    projection["request_binding"] = {"item_id": "H036"}
    projection["request_binding_sha256"] = v4.canonical_json_sha256(
        {"item_id": "H036"}
    )
    intent = v4.build_attempt_intent(
        cohort_manifest_sha256="b" * 64,
        turn_id="rubric:H036",
        item_id="H036",
        phase="rubric",
        projection=projection,
    )
    v4.atomic_seal_json(
        v4.attempt_paths(paths, turn_id="rubric:H036")[0],
        intent,
    )
    changed = (
        "docs/retrieval_authored_v4_evaluation.md",
        "scripts/run_retrieval_authored_v4_evaluation.py",
        "src/retrieval_authored_v4_evaluation.py",
        "tests/test_retrieval_authored_v4_evaluation.py",
    )
    monkeypatch.setattr(v4, "_git_changed_paths", lambda *args, **kwargs: changed)

    payload = v4._harness_scope_continuation_payload(
        base_dir=Path.cwd(),
        paths=paths,
        trace_recovery_commit="d" * 40,
        recovery_commit="e" * 40,
        cap_nano_usd=7_000_000_000,
        require_h036_unattempted=False,
    )
    v4.atomic_seal_json(paths.harness_scope_continuation, payload)
    v4._validate_harness_scope_continuation(
        base_dir=Path.cwd(),
        paths=paths,
        current_commit="e" * 40,
        trace_recovery_commit="d" * 40,
    )

    assert payload["provider_calls_made"] == 0
    assert payload["next_turn_id"] == "rubric:H036"
    assert payload["h036_intent_canonical_sha256"] == v4.canonical_json_sha256(intent)


def test_crash_after_boundary_seals_reserve_without_replay(local_root: Path) -> None:
    paths = _paths(local_root)
    intent = _intent()
    seal = v4.prepare_attempt(paths, intent=intent, cap_nano_usd=150)
    seal()
    cohort = SimpleNamespace(items=())
    # Use decomposition to exercise generic provider-free recovery without
    # needing retrieval data.
    intent_path, marker_path, _ = v4.attempt_paths(paths, turn_id="generation:H001")
    value = json.loads(intent_path.read_text(encoding="utf-8"))
    value["phase"] = "decomposition"
    value["turn_id"] = "decomposition:H001"
    value["request_projection"]["operation"] = "eval_claim_decomposition_v2"
    intent_path.unlink()
    marker_path.unlink()
    new_intent = local_root / "attempts" / "decomposition" / "H001" / "intent.json"
    new_marker = new_intent.with_name("attempt-started.json")
    v4.atomic_seal_json(new_intent, value)
    v4.atomic_seal_json(
        new_marker,
        {
            "schema": v4.V4_ATTEMPT_STARTED_SCHEMA,
            "evaluation_id": v4.EVALUATION_ID,
            "turn_id": "decomposition:H001",
            "intent_sha256": v4.canonical_json_sha256(value),
            "request_shape_sha256": "a" * 64,
            "projected_worst_case_nano_usd": 100,
        },
    )
    recovered = v4.recover_interrupted_attempts(
        paths,
        cap_nano_usd=150,
        cohort=cohort,
    )
    assert recovered == ["decomposition:H001"]
    assert v4.attempt_paths(paths, turn_id="decomposition:H001")[2].is_file()
    assert v4.budget_state(paths, cap_nano_usd=150)["reservation_count"] == 1


def test_failure_taxonomy_preserves_product_codes() -> None:
    assert v4.classify_failure(None, failure_code="request_timeout") == "timeout"
    assert v4.classify_failure(None, failure_code="transport_failure") == "transport"
    assert v4.classify_failure(None, failure_code="provider_exception") == "provider_exception"


def test_social_matrix_is_four_modes_by_three_cases() -> None:
    assert len(v4.SOCIAL_MODES) == 4
    assert len(v4.SOCIAL_QUESTIONS) == 3
    assert len(v4.SOCIAL_MODES) * len(v4.SOCIAL_QUESTIONS) == 12


def test_trace_scope_continuation_normalizes_only_sealed_sentinel_ids(
    local_root: Path,
) -> None:
    paths = _paths(local_root)
    manifest = {
        "system_under_test": {"harness_commit": "a" * 40},
        "paid_scope": {"maximum_total_cost_nano_usd": 7_000_000_000},
    }
    v4.atomic_seal_json(paths.cohort_manifest, manifest)
    original_traces: dict[str, dict[str, object]] = {}
    for item_id in v4.SENTINEL_ITEM_IDS:
        trace = {
            "scope": {
                "project_id": "archivist-v4-evaluation",
                "conversation_id": v4.EVALUATION_ID,
                "turn_id": f"generation:{item_id}",
            }
        }
        original_traces[item_id] = trace
        outcome = {
            "retrieval_trace": trace,
            "operation_evidence": {"turn_id": f"generation:{item_id}"},
        }
        v4.atomic_seal_json(
            v4.attempt_paths(paths, turn_id=f"generation:{item_id}")[2],
            outcome,
        )

    payload = v4._trace_scope_continuation_payload(
        paths,
        harness_commit="b" * 40,
    )
    v4.atomic_seal_json(paths.trace_scope_continuation, payload)

    assert len(payload["outcomes"]) == 10
    assert payload["provider_calls_made"] == 0
    assert payload["sentinel_outcomes_rewritten"] is False
    for item_id, trace in original_traces.items():
        normalized = v4._validated_trace_for_contract(
            paths,
            item_id=item_id,
            trace=trace,
        )
        assert normalized["scope"]["turn_id"] == f"generation-{item_id}"
        assert trace["scope"]["turn_id"] == f"generation:{item_id}"


def test_future_generation_trace_is_normalized_before_sealing() -> None:
    outcome: dict[str, object] = {
        "retrieval_trace": {
            "scope": {
                "project_id": "archivist-v4-evaluation",
                "conversation_id": v4.EVALUATION_ID,
                "turn_id": "generation:H011",
            }
        }
    }

    v4._normalize_generation_trace_scope(outcome, item_id="H011")

    assert outcome["retrieval_trace"]["scope"]["turn_id"] == "generation-H011"


def test_decomposition_timeout_is_longer_than_product_authoring_timeout() -> None:
    assert v4.DECOMPOSITION_TIMEOUT_SECONDS == 60.0
    assert v4.DECOMPOSITION_TIMEOUT_SECONDS > v4.AUTHORED_AUTHORING_TIMEOUT_SECONDS


def test_exact_request_mismatch_never_seals_boundary() -> None:
    calls: list[str] = []

    class Responses:
        def parse(self, **_kwargs):
            calls.append("provider")

    client = SimpleNamespace(responses=Responses())
    expected = v4.project_request(
        operation="answer_generation",
        request={"model": "gpt-5.6-sol", "input": "a", "max_output_tokens": 10},
        request_binding={"item_id": "H001"},
    )
    exact = v4.ExactRequestCapturingClient(
        client,
        expected_projection=expected,
        seal_boundary=lambda: calls.append("sealed"),
    )
    with pytest.raises(v4.V4EvaluationError, match="changed"):
        exact.responses.parse(model="gpt-5.6-sol", input="different", max_output_tokens=10)
    assert calls == []


def test_exact_request_retry_guard_is_shared_across_client_clones() -> None:
    calls: list[str] = []
    request = {"model": "gpt-5.6-sol", "input": "a", "max_output_tokens": 10}

    class Responses:
        def parse(self, **_kwargs: object) -> object:
            calls.append("provider")
            return object()

    class Client:
        responses = Responses()

        def with_options(self, **_kwargs: object) -> Client:
            return self

    exact = v4.ExactRequestCapturingClient(
        Client(),
        expected_projection=v4.project_request(
            operation="answer_generation",
            request=request,
            request_binding={"item_id": "H001"},
        ),
        seal_boundary=lambda: calls.append("sealed"),
    )
    first = exact.with_options(max_retries=0)
    second = exact.with_options(timeout=30.0)

    first.responses.parse(**request)
    with pytest.raises(v4.V4EvaluationError, match="repeated provider attempt"):
        second.responses.parse(**request)

    assert exact.attempt_count == 1
    assert calls == ["sealed", "provider"]


@pytest.mark.parametrize(
    ("field", "tampered"),
    (
        ("schema", "archivist.invalid/1"),
        ("operation", "wrong_operation"),
        ("reservation_method", "unbound_guess"),
        ("continuation_policy", "retry_it"),
        ("provider_boundary_attempt_count", 2),
        ("usage_event_count", 1),
        ("retried", True),
    ),
)
def test_budget_rejects_tampered_reservation_contract(
    local_root: Path,
    field: str,
    tampered: object,
) -> None:
    paths = _paths(local_root)
    _settle_zero_event(paths, cap_nano_usd=150)
    reservation = paths.reservation_root / "generation-H001.json"
    value = json.loads(reservation.read_text(encoding="utf-8"))
    value[field] = tampered
    reservation.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(v4.V4EvaluationError, match="identity|binding"):
        v4.budget_state(paths, cap_nano_usd=150)


def test_foreign_turn_under_master_request_is_rejected(local_root: Path) -> None:
    paths = _paths(local_root)
    _record_usage(
        paths,
        turn_id="generation:H999",
        operation="answer_generation",
        requested_model=v4.AUTHORED_RESPONSE_SETTINGS.model,
        actual_model=v4.AUTHORED_RESPONSE_SETTINGS.model,
    )

    with pytest.raises(v4.V4EvaluationError, match="foreign-scope"):
        v4.budget_state(paths, cap_nano_usd=1_000_000)


def test_foreign_attempt_directory_is_rejected(local_root: Path) -> None:
    paths = _paths(local_root)
    v4.atomic_seal_json(
        paths.root / "attempts" / "generation" / "H999" / "intent.json",
        {"turn_id": "generation:H999"},
    )

    with pytest.raises(v4.V4EvaluationError, match="foreign turn"):
        v4.budget_state(paths, cap_nano_usd=1_000)


def test_no_boundary_rubric_crash_is_settled_without_provider_call(
    local_root: Path,
) -> None:
    paths = _paths(local_root)
    _seal_intentionally_unattempted_rubric(paths)
    outcome_path = v4.attempt_paths(paths, turn_id="rubric:H001")[2]
    outcome_path.unlink()

    assert v4.recover_interrupted_attempts(paths, cap_nano_usd=1_000) == [
        "rubric:H001"
    ]
    assert v4._completed_turn(paths, turn_id="rubric:H001") is True
    assert not v4._reservation_path(paths, turn_id="rubric:H001").exists()


@pytest.mark.parametrize(
    ("missing_phase", "message"),
    (
        ("generation", "generation phase inventory changed"),
        ("decomposition", "decomposition phase inventory changed"),
        ("rubric", "rubric phase inventory changed"),
        ("social", "social phase inventory changed"),
    ),
)
def test_report_refuses_each_incomplete_phase(
    local_root: Path,
    missing_phase: str,
    message: str,
) -> None:
    paths = _paths(local_root)
    cohort = SimpleNamespace(paths=paths, items=({"id": "H001"},), manifest={})
    if missing_phase != "generation":
        _settle_zero_event(paths, cap_nano_usd=1_000)
    if missing_phase not in {"generation", "decomposition"}:
        _settle_zero_event(
            paths,
            phase="decomposition",
            operation="eval_claim_decomposition_v2",
            schema=v4.V4_DECOMPOSITION_OUTCOME_SCHEMA,
            cap_nano_usd=1_000,
        )
    if missing_phase == "social":
        _seal_intentionally_unattempted_rubric(paths)
    with pytest.raises(v4.V4EvaluationError, match=message):
        v4.build_text_free_report(cohort, maximum_usd=Decimal("1.00"))


def test_locked_gold_inventory_includes_h038_and_excludes_h020() -> None:
    gold_path = Path(__file__).resolve().parents[1] / "fixtures" / "gold_set.json"
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    ids = [value["id"] for value in gold["items"]]

    assert ids == [f"H{index:03d}" for index in range(1, 20)] + [
        f"H{index:03d}" for index in range(21, 39)
    ]
    assert "H020" not in ids
    assert "H038" in ids


def test_invalid_usage_is_rejected_before_outcome_is_sealed(local_root: Path) -> None:
    paths = _paths(local_root)
    intent = _intent()
    seal = v4.prepare_attempt(paths, intent=intent, cap_nano_usd=150)
    seal()
    invalid = {
        "turn_id": "generation:H001",
        "operation": "answer_generation",
        "event_count": 2,
        "exactly_one_priced_event": False,
        "scope_valid": True,
        "events": [{}, {}],
    }
    outcome = {
        "schema": v4.V4_GENERATION_OUTCOME_SCHEMA,
        "evaluation_id": v4.EVALUATION_ID,
        "item_id": "H001",
        "intent_sha256": v4.canonical_json_sha256(intent),
        "operation_evidence": invalid,
    }
    with pytest.raises(v4.V4EvaluationError, match="changed"):
        v4.settle_attempt(paths, intent=intent, outcome=outcome, cap_nano_usd=150)
    assert not v4.attempt_paths(paths, turn_id="generation:H001")[2].exists()


def test_wrong_provider_model_never_seals_outcome(local_root: Path) -> None:
    paths = _paths(local_root)
    intent = _intent()
    seal = v4.prepare_attempt(paths, intent=intent, cap_nano_usd=1_000_000)
    seal()
    _record_usage(
        paths,
        turn_id="generation:H001",
        operation="answer_generation",
        requested_model=v4.AUTHORED_RESPONSE_SETTINGS.model,
        actual_model="gpt-5.6-terra",
    )
    outcome = {
        "schema": v4.V4_GENERATION_OUTCOME_SCHEMA,
        "evaluation_id": v4.EVALUATION_ID,
        "item_id": "H001",
        "status": "generated",
        "intent_sha256": v4.canonical_json_sha256(intent),
        "provider_boundary_attempt_count": 1,
        "automatic_retries": 0,
        "operation_evidence": v4.operation_evidence(
            paths,
            turn_id="generation:H001",
            operation="answer_generation",
        ),
    }

    with pytest.raises(v4.V4EvaluationError, match="model or response identity"):
        v4.settle_attempt(
            paths,
            intent=intent,
            outcome=outcome,
            cap_nano_usd=1_000_000,
        )
    assert not v4.attempt_paths(paths, turn_id="generation:H001")[2].exists()


def test_recovery_with_wrong_provider_model_never_seals_outcome(local_root: Path) -> None:
    paths = _paths(local_root)
    intent = _intent()
    seal = v4.prepare_attempt(paths, intent=intent, cap_nano_usd=1_000_000)
    seal()
    _record_usage(
        paths,
        turn_id="generation:H001",
        operation="answer_generation",
        requested_model=v4.AUTHORED_RESPONSE_SETTINGS.model,
        actual_model="gpt-5.6-terra",
    )

    with pytest.raises(v4.V4EvaluationError, match="model or response identity"):
        v4.recover_interrupted_attempts(paths, cap_nano_usd=1_000_000)
    assert not v4.attempt_paths(paths, turn_id="generation:H001")[2].exists()


def test_intentionally_unattempted_rubric_is_skipped_without_reservation(
    local_root: Path,
) -> None:
    paths = _paths(local_root)
    _seal_intentionally_unattempted_rubric(paths)

    assert v4.recover_interrupted_attempts(paths, cap_nano_usd=1_000) == []
    assert v4._completed_turn(paths, turn_id="rubric:H001") is True
    assert not v4._reservation_path(paths, turn_id="rubric:H001").exists()
    assert v4.budget_state(paths, cap_nano_usd=1_000)["reservation_count"] == 0

    _record_usage(
        paths,
        turn_id="rubric:H001",
        operation="eval_item_rubric",
        requested_model="gpt-5.6-terra",
        actual_model="gpt-5.6-terra",
    )
    with pytest.raises(v4.V4EvaluationError, match="no-boundary usage state"):
        v4.recover_interrupted_attempts(paths, cap_nano_usd=1_000_000)
    assert not v4._reservation_path(paths, turn_id="rubric:H001").exists()


def test_no_boundary_rubric_refuses_usage_before_outcome_is_sealed(
    local_root: Path,
) -> None:
    paths = _paths(local_root)
    turn_id = "rubric:H001"
    intent = {
        "schema": v4.V4_INTENT_SCHEMA,
        "evaluation_id": v4.EVALUATION_ID,
        "cohort_manifest_sha256": "b" * 64,
        "turn_id": turn_id,
        "item_id": "H001",
        "phase": "rubric",
        "attempt_count": 0,
        "automatic_retries": 0,
        "replacement": False,
        "request_projection": None,
    }
    intent_path, marker_path, outcome_path = v4.attempt_paths(paths, turn_id=turn_id)
    v4.write_or_validate_json(intent_path, intent)
    v4.write_or_validate_json(
        marker_path,
        {
            "schema": v4.V4_ATTEMPT_STARTED_SCHEMA,
            "evaluation_id": v4.EVALUATION_ID,
            "turn_id": turn_id,
            "intent_sha256": v4.canonical_json_sha256(intent),
            "provider_boundary_not_crossed": True,
            "projected_worst_case_nano_usd": 0,
        },
    )
    _record_usage(
        paths,
        turn_id=turn_id,
        operation="eval_item_rubric",
        requested_model="gpt-5.6-terra",
        actual_model="gpt-5.6-terra",
    )

    with pytest.raises(v4.V4EvaluationError, match="no-boundary usage state"):
        v4._no_boundary_rubric_outcome(paths, intent=intent)

    assert not outcome_path.exists()


def test_zero_event_generation_delivers_deterministic_essential_fallback(
    local_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import retrieval_authored_v3_evaluation as v3

    paths = _paths(local_root)
    item = {"id": "H001"}
    maximum_usd = Decimal("1.00")
    cap_nano_usd = 1_000_000_000
    cohort = SimpleNamespace(
        paths=paths,
        items=(item,),
        manifest={"paid_scope": {"maximum_total_cost_nano_usd": cap_nano_usd}},
        as_v3_retrieval_adapter=lambda: object(),
    )
    provider_request = {
        "model": v4.AUTHORED_RESPONSE_SETTINGS.model,
        "input": "sealed-test-input",
        "max_output_tokens": 10,
    }
    projection = v4.project_request(
        operation="answer_generation",
        request=provider_request,
        request_binding={"item_id": "H001"},
    )
    hidden_answer = "hidden generated answer"
    fallback_answer = "deterministic Essential evidence"

    class Responses:
        def parse(self, **_kwargs: object) -> object:
            return SimpleNamespace()

    class Client:
        responses = Responses()

        def with_options(self, **_kwargs: object) -> Client:
            return self

    def fake_generate(
        _cohort: object,
        *,
        item: object,
        client: object,
        require_provider_observation: bool,
    ) -> dict[str, object]:
        assert require_provider_observation is False
        client.responses.parse(**provider_request)
        return {
            "item_id": "H001",
            "status": "generated",
            "answer": hidden_answer,
            "answer_sha256": hashlib.sha256(hidden_answer.encode()).hexdigest(),
            "provider": {
                "response_id": "untracked-provider-response",
                "model": v4.AUTHORED_RESPONSE_SETTINGS.model,
            },
        }

    def fake_fallback(
        _cohort: object,
        *,
        item: object,
        exc: Exception,
    ) -> dict[str, object]:
            return {
                "item_id": "H001",
                "status": "technical_failure",
                "answer": fallback_answer,
                "answer_sha256": hashlib.sha256(fallback_answer.encode()).hexdigest(),
                "retrieval_trace": {
                    "scope": {
                        "project_id": None,
                        "conversation_id": None,
                        "turn_id": None,
                    }
                },
            }

    monkeypatch.setattr(v4, "_generation_items", lambda *_args, **_kwargs: (item,))
    monkeypatch.setattr(v4, "generation_request_projection", lambda *_args, **_kwargs: projection)
    monkeypatch.setattr(v4, "generate_professional_item", fake_generate)
    monkeypatch.setattr(v3, "_local_technical_generation_outcome", fake_fallback)

    v4.run_professional_generation(
        cohort,
        client=Client(),
        maximum_usd=maximum_usd,
        sentinel=True,
    )

    outcome = v4.read_json_object(
        v4.attempt_paths(paths, turn_id="generation:H001")[2]
    )
    assert outcome["answer"] == fallback_answer
    assert hidden_answer not in json.dumps(outcome)
    assert outcome["delivered_answer_status"] == "essential_fallback"
    assert outcome["failure_category"] == "usage_contract_failure"
    assert v4._reservation_path(paths, turn_id="generation:H001").is_file()
