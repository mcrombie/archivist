from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from archivist_modes import ArchivistMode, supported_generated_modes
from character_conversation import (
    CharacterConversationResponse,
    validate_and_render_character_conversation,
)
from costs import TokenUsage, UsageLedger, current_usage_context
from persona_evaluation import (
    AMBIGUITY_RESERVE_NANO_USD,
    DEFAULT_RUN_ROOT,
    DEFAULT_USAGE_DB,
    MASTER_COST_CEILING_NANO_USD,
    MASTER_COST_CEILING_USD,
    MASTER_PROJECT_ID,
    MASTER_REQUEST_ID,
    OWNER_AUTHORIZED_COST_CAP_NANO_USD,
    OWNER_AUTHORIZED_COST_CAP_USD,
    PERSONA_CONVERSATION_ID,
    PERSONA_EVALUATION_CASES,
    PersonaEvaluationError,
    build_prepared_manifest,
    load_diagnostics_report,
    prepare_evaluation,
    run_evaluation,
)
from retrieval_authored_v3_evaluation import (
    AMBIGUOUS_H002_RESERVED_NANO_USD,
    EVALUATION_ID,
    MASTER_COST_CAP_NANO_USD,
    MASTER_COST_CAP_USD,
    MASTER_REQUEST_ID as V3_MASTER_REQUEST_ID,
    RECOVERY_EFFECTIVE_TRACKED_CAP_NANO_USD,
    default_paths,
)


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    evaluation_root = tmp_path / "runtime" / "evaluations" / "v3-shared"
    return (
        evaluation_root,
        evaluation_root / "conversational-persona",
        evaluation_root / "usage.sqlite3",
    )


class _Client:
    def __init__(self) -> None:
        self.retry_values: list[int] = []

    def with_options(self, *, max_retries: int):
        self.retry_values.append(max_retries)
        return self


_REPLIES = {
    ArchivistMode.PROFESSIONAL: (
        "I am a curious public historian, most content when attentive research becomes a clear "
        "conversation."
    ),
    ArchivistMode.PRETTY_PINK_PRINCESS: (
        "My princess life is sparkling: palace ribbons, tiny songs, and one terribly charming "
        "prince."
    ),
    ArchivistMode.BALEFUL_BLACK_BARON: (
        "Miserable, as a proper Baron should be; the ravens circle my bleak keep while one candle "
        "surrenders."
    ),
    ArchivistMode.EMBER_AND_INK: (
        "Fun is operational: I test strategy, preserve leverage, and negotiate alliances when the "
        "timing is favorable."
    ),
}


def _recorded_generator(calls: list[tuple[str, str]]):
    def generate(client, *, question, mode):
        context = current_usage_context()
        assert context.request_id == MASTER_REQUEST_ID
        assert context.project_id == MASTER_PROJECT_ID
        assert context.conversation_id == PERSONA_CONVERSATION_ID
        assert context.request_cost_ceiling_nano_usd == MASTER_COST_CEILING_NANO_USD
        assert context.enforce_budget is True
        assert context.allow_over_budget is False
        assert "manuscript" not in question.casefold()
        calls.append((mode.value, question))
        client.with_options(max_retries=0)
        UsageLedger().record(
            response_id=f"synthetic-persona-{mode.value}",
            operation="answer_generation",
            requested_model="gpt-5.6-sol",
            actual_model="gpt-5.6-sol",
            usage=TokenUsage(input_tokens=120, output_tokens=24, total_tokens=144),
            project_id=context.project_id,
            conversation_id=context.conversation_id,
            turn_id=context.turn_id,
            request_id=context.request_id,
        )
        return validate_and_render_character_conversation(
            CharacterConversationResponse(
                persona_reply=_REPLIES[mode],
                manuscript_follow_up_questions=(
                    "Which character in the manuscript should we discuss next?",
                ),
            ),
            mode=mode,
        )

    return generate


def test_manifest_is_provider_free_and_covers_current_generated_registry(tmp_path):
    evaluation_root, run_root, usage_db = _paths(tmp_path)
    manifest = build_prepared_manifest(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )

    assert [item["mode"] for item in manifest["items"]] == [
        "professional",
        "pretty_pink_princess",
        "baleful_black_baron",
        "ember_and_ink",
    ]
    assert {item["mode"] for item in manifest["items"]} == {
        mode.value for mode in supported_generated_modes()
    }
    assert {item["question"] for item in manifest["items"]} == {"How are you?"}
    assert all(case.question == "How are you?" for case in PERSONA_EVALUATION_CASES)
    assert all(item["route_classifier_eligible"] is True for item in manifest["items"])
    assert manifest["expected_provider_calls"] == 4
    assert manifest["automatic_retry_count"] == 0
    assert manifest["model"] == "gpt-5.6-sol"
    assert manifest["reasoning_effort"] == "low"
    assert manifest["verbosity"] == "low"
    assert manifest["max_output_tokens"] == 576
    assert manifest["master_request_id"] == MASTER_REQUEST_ID
    assert manifest["owner_authorized_cap_nano_usd"] == 7_000_000_000
    assert manifest["ambiguity_reserve_nano_usd"] == 399_575_000
    assert manifest["effective_tracked_ceiling_nano_usd"] == 6_600_425_000
    assert manifest["effective_tracked_ceiling_usd_exact"] == "6.600425000"
    assert manifest["projected_cohort_cost_nano_usd"] == sum(
        item["projected_cost_nano_usd"] for item in manifest["items"]
    )
    assert manifest["input_boundary"] == {
        "question_and_character_instructions_only": True,
        "history": False,
        "embedding": False,
        "retrieval": False,
        "manuscript": False,
        "evidence_dossier": False,
        "sources": False,
    }
    serialized = json.dumps(manifest)
    assert "chunk" not in serialized
    assert "retrieved passage" not in serialized
    assert all(item["projected_cost_nano_usd"] > 0 for item in manifest["items"])


def test_defaults_share_adapter_root_ledger_request_and_cap():
    shared = default_paths(Path(__file__).resolve().parent.parent)
    assert DEFAULT_RUN_ROOT == shared.root / "conversational-persona"
    assert DEFAULT_USAGE_DB == shared.ledger
    assert MASTER_REQUEST_ID == V3_MASTER_REQUEST_ID
    assert MASTER_REQUEST_ID == f"{EVALUATION_ID}-master"
    assert OWNER_AUTHORIZED_COST_CAP_NANO_USD == MASTER_COST_CAP_NANO_USD
    assert OWNER_AUTHORIZED_COST_CAP_USD == MASTER_COST_CAP_USD
    assert AMBIGUITY_RESERVE_NANO_USD == AMBIGUOUS_H002_RESERVED_NANO_USD
    assert MASTER_COST_CEILING_NANO_USD == RECOVERY_EFFECTIVE_TRACKED_CAP_NANO_USD
    assert MASTER_COST_CEILING_USD == Decimal("6.600425")
    assert MASTER_COST_CAP_USD == Decimal("7.00")


def test_prepare_is_offline_idempotent_and_does_not_create_ledger(tmp_path):
    evaluation_root, run_root, usage_db = _paths(tmp_path)
    first = prepare_evaluation(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    second = prepare_evaluation(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )

    assert first == second
    assert (run_root / "prepared-manifest.json").is_file()
    assert not usage_db.exists()
    assert not (run_root / "authorization.json").exists()
    assert not (run_root / "attempts").exists()


def test_run_makes_four_scoped_no_retry_calls_and_reports_diagnostics(tmp_path):
    evaluation_root, run_root, usage_db = _paths(tmp_path)
    prepare_evaluation(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    original_usage_db = os.environ.get("ARCHIVIST_USAGE_DB")
    ledger = UsageLedger(usage_db)
    ledger.update_settings(
        monthly_budget_usd=None,
        warning_threshold_percent=73,
        hard_limit_enabled=False,
    )
    calls: list[tuple[str, str]] = []
    client = _Client()

    report = run_evaluation(
        authorized=True,
        maximum_usd=Decimal("7.00"),
        client_factory=lambda: client,
        generator=_recorded_generator(calls),
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )

    assert calls == [(case.mode.value, case.question) for case in PERSONA_EVALUATION_CASES]
    assert client.retry_values == [0, 0, 0, 0]
    assert report["attempt_count"] == 4
    assert report["automatic_retry_count"] == 0
    assert report["status_counts"] == {"generated": 4}
    assert report["follow_up_to_manuscript_pass_count"] == 4
    assert report["character_distinctness_pass_count"] == 4
    assert report["all_persona_replies_unique"] is True
    assert report["cohort_cost_nano_usd"] > 0
    assert report["cohort_cost_nano_usd"] < MASTER_COST_CEILING_NANO_USD
    assert report["owner_authorized_cap_nano_usd"] == 7_000_000_000
    assert report["owner_authorized_cap_usd_exact"] == "7.000000000"
    assert report["ambiguity_reserve_nano_usd"] == 399_575_000
    assert report["ambiguity_reserve_usd_exact"] == "0.399575000"
    assert report["effective_tracked_ceiling_nano_usd"] == 6_600_425_000
    assert report["effective_tracked_ceiling_usd_exact"] == "6.600425000"
    assert report["effective_remaining_nano_usd_at_report"] == (
        MASTER_COST_CEILING_NANO_USD
        - report["master_ledger_cost_nano_usd_at_report"]
    )
    assert Decimal(report["effective_remaining_usd_exact_at_report"]) == (
        Decimal(report["effective_remaining_nano_usd_at_report"])
        / Decimal(1_000_000_000)
    )
    assert len(report["pairwise_token_jaccard"]) == 6
    assert all(mode["own_signature_hits"] for mode in report["modes"])
    assert all(mode["follow_up_to_manuscript"] for mode in report["modes"])
    assert ledger.request_usage_cost_state(MASTER_REQUEST_ID)["event_count"] == 4
    assert ledger.get_settings() == {
        "monthly_budget_usd": 6.600425,
        "warning_threshold_percent": 80,
        "hard_limit_enabled": True,
    }
    assert os.environ.get("ARCHIVIST_USAGE_DB") == original_usage_db
    assert len(list((run_root / "attempts").glob("*/intent.json"))) == 4
    assert len(list((run_root / "attempts").glob("*/outcome.json"))) == 4
    assert load_diagnostics_report(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    ) == report


def test_completed_run_resumes_without_client_or_provider_calls(tmp_path):
    evaluation_root, run_root, usage_db = _paths(tmp_path)
    prepare_evaluation(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    calls: list[tuple[str, str]] = []
    first = run_evaluation(
        authorized=True,
        maximum_usd=Decimal("7.00"),
        client_factory=_Client,
        generator=_recorded_generator(calls),
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    calls.clear()
    second = run_evaluation(
        authorized=True,
        maximum_usd=Decimal("7.00"),
        client_factory=lambda: pytest.fail("resume constructed a provider client"),
        generator=lambda *_args, **_kwargs: pytest.fail("resume replayed an item"),
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )

    assert second == first
    assert calls == []
    assert UsageLedger(usage_db).request_usage_cost_state(MASTER_REQUEST_ID)[
        "event_count"
    ] == 4


def test_unresolved_intent_blocks_resume_before_client_construction(tmp_path):
    evaluation_root, run_root, usage_db = _paths(tmp_path)
    manifest = prepare_evaluation(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    item = manifest["items"][0]
    # Drive one deliberately untracked call. The harness seals intent first,
    # records the ambiguous state, and forbids all automatic replay.
    with pytest.raises(PersonaEvaluationError, match="exactly one priced"):
        run_evaluation(
            authorized=True,
            maximum_usd=Decimal("7.00"),
            client_factory=_Client,
            generator=lambda *_args, **_kwargs: validate_and_render_character_conversation(
                CharacterConversationResponse(
                    persona_reply=_REPLIES[ArchivistMode.PROFESSIONAL],
                    manuscript_follow_up_questions=(
                        "Which person in the manuscript should we discuss?",
                    ),
                ),
                mode=ArchivistMode.PROFESSIONAL,
            ),
            run_root=run_root,
            usage_db=usage_db,
            evaluation_root=evaluation_root,
        )
    outcome_path = (
        run_root / "attempts" / f"01-{item['mode']}" / "outcome.json"
    )
    assert json.loads(outcome_path.read_text(encoding="utf-8"))["status"] == (
        "ambiguous_usage"
    )
    with pytest.raises(PersonaEvaluationError, match="unresolved usage"):
        run_evaluation(
            authorized=True,
            maximum_usd=Decimal("7.00"),
            client_factory=lambda: pytest.fail("ambiguous resume built a client"),
            run_root=run_root,
            usage_db=usage_db,
            evaluation_root=evaluation_root,
        )
    assert not (run_root / "diagnostics-report.json").exists()


def test_shared_master_cap_blocks_before_intent_or_client(tmp_path):
    evaluation_root, run_root, usage_db = _paths(tmp_path)
    prepare_evaluation(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    UsageLedger(usage_db).record(
        response_id="synthetic-prior-master-spend",
        operation="answer_generation",
        requested_model="gpt-5.6-sol",
        actual_model="gpt-5.6-sol",
        usage=TokenUsage(output_tokens=466_666, total_tokens=466_666),
        project_id=MASTER_PROJECT_ID,
        conversation_id="retrieval-authored-v3-other-evaluation",
        turn_id="prior-item",
        request_id=MASTER_REQUEST_ID,
    )

    with pytest.raises(PersonaEvaluationError, match="recovery effective ceiling"):
        run_evaluation(
            authorized=True,
            maximum_usd=Decimal("7.00"),
            client_factory=lambda: pytest.fail("cap failure constructed a client"),
            run_root=run_root,
            usage_db=usage_db,
            evaluation_root=evaluation_root,
        )
    assert not (run_root / "attempts").exists()


def test_h002_reserve_blocks_projection_that_would_fit_under_owner_cap(tmp_path):
    evaluation_root, run_root, usage_db = _paths(tmp_path)
    manifest = prepare_evaluation(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    projected = int(manifest["projected_cohort_cost_nano_usd"])
    # Sol output is 30,000 nano-USD/token. Choose prior spend so all four
    # projections fit beneath $7, but not beneath the H002-reserved ceiling.
    output_tokens = (MASTER_COST_CEILING_NANO_USD - projected) // 30_000 + 1
    UsageLedger(usage_db).record(
        response_id="synthetic-prior-reserve-edge",
        operation="answer_generation",
        requested_model="gpt-5.6-sol",
        actual_model="gpt-5.6-sol",
        usage=TokenUsage(output_tokens=output_tokens, total_tokens=output_tokens),
        project_id=MASTER_PROJECT_ID,
        conversation_id="retrieval-authored-v3-other-evaluation",
        turn_id="prior-reserve-edge",
        request_id=MASTER_REQUEST_ID,
    )
    state = UsageLedger(usage_db).request_usage_cost_state(MASTER_REQUEST_ID)
    assert int(state["estimated_cost_nano_usd"]) + projected > (
        MASTER_COST_CEILING_NANO_USD
    )
    assert int(state["estimated_cost_nano_usd"]) + projected < (
        OWNER_AUTHORIZED_COST_CAP_NANO_USD
    )

    with pytest.raises(PersonaEvaluationError, match="effective tracked ceiling"):
        run_evaluation(
            authorized=True,
            maximum_usd=Decimal("7.00"),
            client_factory=lambda: pytest.fail("reserve failure constructed a client"),
            run_root=run_root,
            usage_db=usage_db,
            evaluation_root=evaluation_root,
        )
    assert not (run_root / "attempts").exists()


@pytest.mark.parametrize("failure_kind", ("foreign", "unpriced"))
def test_master_ledger_rejects_foreign_or_unpriced_state_before_client(
    tmp_path,
    failure_kind,
):
    evaluation_root, run_root, usage_db = _paths(tmp_path)
    prepare_evaluation(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    UsageLedger(usage_db).record(
        response_id=f"synthetic-{failure_kind}",
        operation="answer_generation",
        requested_model=("unknown-persona-model" if failure_kind == "unpriced" else "gpt-5.6-sol"),
        actual_model=("unknown-persona-model" if failure_kind == "unpriced" else "gpt-5.6-sol"),
        usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        project_id=MASTER_PROJECT_ID,
        conversation_id=PERSONA_CONVERSATION_ID,
        turn_id=f"prior-{failure_kind}",
        request_id=("another-request" if failure_kind == "foreign" else MASTER_REQUEST_ID),
    )

    message = "another request scope" if failure_kind == "foreign" else "unpriced usage"
    with pytest.raises(PersonaEvaluationError, match=message):
        run_evaluation(
            authorized=True,
            maximum_usd=Decimal("7.00"),
            client_factory=lambda: pytest.fail("invalid ledger built a client"),
            run_root=run_root,
            usage_db=usage_db,
            evaluation_root=evaluation_root,
        )
    assert not (run_root / "attempts").exists()


@pytest.mark.parametrize(
    ("authorized", "maximum", "message"),
    (
        (False, Decimal("7.00"), "requires --authorize"),
        (True, Decimal("6.99"), r"exactly the shared \$7.00"),
        (True, Decimal("7.01"), r"exactly the shared \$7.00"),
    ),
)
def test_live_run_requires_exact_authorization_without_constructing_client(
    tmp_path,
    authorized,
    maximum,
    message,
):
    evaluation_root, run_root, usage_db = _paths(tmp_path)
    prepare_evaluation(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    with pytest.raises(PersonaEvaluationError, match=message):
        run_evaluation(
            authorized=authorized,
            maximum_usd=maximum,
            client_factory=lambda: pytest.fail("invalid authorization built a client"),
            run_root=run_root,
            usage_db=usage_db,
            evaluation_root=evaluation_root,
        )
    assert not (run_root / "attempts").exists()


def test_manifest_tamper_is_rejected_without_provider_work(tmp_path):
    evaluation_root, run_root, usage_db = _paths(tmp_path)
    prepare_evaluation(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    path = run_root / "prepared-manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["expected_provider_calls"] = 5
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PersonaEvaluationError, match="hash no longer binds"):
        run_evaluation(
            authorized=True,
            maximum_usd=Decimal("7.00"),
            client_factory=lambda: pytest.fail("tampered manifest built a client"),
            run_root=run_root,
            usage_db=usage_db,
            evaluation_root=evaluation_root,
        )


def test_shared_usage_database_path_cannot_be_replaced_with_independent_allowance(tmp_path):
    evaluation_root, run_root, usage_db = _paths(tmp_path)
    with pytest.raises(PersonaEvaluationError, match="must use the shared"):
        build_prepared_manifest(
            run_root=run_root,
            usage_db=usage_db.with_name("persona-only.sqlite3"),
            evaluation_root=evaluation_root,
        )
