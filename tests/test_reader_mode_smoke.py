from __future__ import annotations

import importlib.util
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from costs import TokenUsage, UsageLedger, current_usage_context
from prose_renderer import (
    EvidenceProseRenderResult,
    ProseFailureCode,
    ProseRenderStatus,
    READER_PROSE_SETTINGS,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_reader_mode_smoke.py"
SPEC = importlib.util.spec_from_file_location("run_reader_mode_smoke", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


def _chunks(_project_id: str) -> list[dict[str, object]]:
    return [
        {
            "chunk_id": f"synthetic-{index}",
            "document": "synthetic.txt",
            "chapter_title": "Synthetic evidence",
            "paragraph_start": index,
            "paragraph_end": index,
            "text": (
                f"Synthetic Edwin Sandys evidence item {label} describes a distinct action "
                "for an offline runner test."
            ),
        }
        for index, label in enumerate(("alpha", "beta", "gamma"), start=1)
    ]


class _NoRetryClient:
    def __init__(self) -> None:
        self.retry_options: list[int] = []

    def with_options(self, *, max_retries: int):
        self.retry_options.append(max_retries)
        return self


def _recorded_generator(calls: list[str]):
    def generate(_client, *, mode, **_kwargs):
        calls.append(mode.value)
        context = current_usage_context()
        assert context.request_id is not None
        UsageLedger().record(
            response_id=f"synthetic-response-{context.request_id}",
            operation="answer_generation",
            requested_model=READER_PROSE_SETTINGS.model,
            actual_model=READER_PROSE_SETTINGS.model,
            usage=TokenUsage(input_tokens=100, output_tokens=10, total_tokens=110),
            project_id=context.project_id,
            conversation_id=context.conversation_id,
            turn_id=context.turn_id,
            request_id=context.request_id,
        )
        return EvidenceProseRenderResult(
            status=ProseRenderStatus.GENERATED,
            mode=mode,
            answer=f"Synthetic {mode.value} answer.",
            segments=(),
            used_card_ids=(),
            used_source_numbers=(),
            failure_code=None,
        )

    return generate


def test_success_is_exactly_three_no_retry_calls_in_fresh_isolated_ledger(tmp_path):
    calls: list[str] = []
    client = _NoRetryClient()
    smoke_root = tmp_path / "paid-smokes"
    run_root = smoke_root / "run-001"
    previous_usage_db = os.environ.get("ARCHIVIST_USAGE_DB")

    summary = smoke.execute_smoke(
        run_root=run_root,
        maximum_usd=Decimal("2.00"),
        authorized=True,
        smoke_root=smoke_root,
        chunks_loader=_chunks,
        client_factory=lambda: client,
        prose_generator=_recorded_generator(calls),
    )

    assert calls == [mode.value for mode in smoke.MODE_ORDER]
    assert client.retry_options == [0]
    assert summary["attempt_count"] == 3
    assert summary["automatic_retries"] == 0
    assert summary["recorded_cost_nano_usd"] < smoke.AGGREGATE_HARD_CEILING_NANO_USD
    assert (run_root / "usage.sqlite3").is_file()
    assert (run_root / "private-summary.json").is_file()
    assert len(list((run_root / "attempts").glob("*/intent.json"))) == 3
    assert len(list((run_root / "attempts").glob("*/outcome.json"))) == 3
    assert os.environ.get("ARCHIVIST_USAGE_DB") == previous_usage_db

    prepared = json.loads((run_root / "prepared.json").read_text(encoding="utf-8"))
    assert prepared["evidence_card_count"] == 3
    assert "Synthetic Edwin Sandys evidence" not in json.dumps(prepared)
    assert prepared["aggregate_hard_ceiling_nano_usd"] == 1_050_000_000
    assert all(
        item["projected_cost_nano_usd"] <= smoke.PER_CALL_COST_CEILING_NANO_USD
        for item in prepared["modes"]
    )


def test_missing_authorization_does_not_read_corpus_create_root_or_client(tmp_path):
    touched: list[str] = []
    smoke_root = tmp_path / "paid-smokes"
    run_root = smoke_root / "unauthorized"

    with pytest.raises(smoke.ReaderModeSmokeError, match="requires --authorize"):
        smoke.execute_smoke(
            run_root=run_root,
            maximum_usd=Decimal("2.00"),
            authorized=False,
            smoke_root=smoke_root,
            chunks_loader=lambda _project: touched.append("corpus") or [],
            client_factory=lambda: touched.append("client") or object(),
        )

    assert touched == []
    assert not run_root.exists()


@pytest.mark.parametrize("maximum", (Decimal("1.049999999"), Decimal("2.000000001")))
def test_authorization_must_cover_fixed_aggregate_but_never_exceed_two_dollars(
    tmp_path,
    maximum,
):
    with pytest.raises(smoke.ReaderModeSmokeError):
        smoke.execute_smoke(
            run_root=tmp_path / "paid-smokes" / "invalid-cap",
            maximum_usd=maximum,
            authorized=True,
            smoke_root=tmp_path / "paid-smokes",
            chunks_loader=_chunks,
            client_factory=lambda: pytest.fail("unsafe cap constructed a client"),
        )


def test_all_projections_must_fit_before_root_or_client_creation(tmp_path, monkeypatch):
    smoke_root = tmp_path / "paid-smokes"
    run_root = smoke_root / "projection-failure"
    monkeypatch.setattr(
        smoke,
        "projected_provider_operation_cost_nano_usd",
        lambda **_kwargs: smoke.PER_CALL_COST_CEILING_NANO_USD + 1,
    )

    with pytest.raises(smoke.ReaderModeSmokeError, match="projects above"):
        smoke.execute_smoke(
            run_root=run_root,
            maximum_usd=Decimal("2.00"),
            authorized=True,
            smoke_root=smoke_root,
            chunks_loader=_chunks,
            client_factory=lambda: pytest.fail("failed preflight constructed a client"),
        )

    assert not run_root.exists()


def test_missing_usage_stops_after_first_call_without_retry_or_later_modes(tmp_path):
    calls: list[str] = []
    client = _NoRetryClient()
    smoke_root = tmp_path / "paid-smokes"
    run_root = smoke_root / "ambiguous"

    def untracked_generator(_client, *, mode, **_kwargs):
        calls.append(mode.value)
        return EvidenceProseRenderResult(
            status=ProseRenderStatus.FALLBACK_REQUIRED,
            mode=mode,
            answer=None,
            segments=(),
            used_card_ids=(),
            used_source_numbers=(),
            failure_code=ProseFailureCode.PROVIDER_FAILURE,
        )

    with pytest.raises(smoke.ReaderModeSmokeError, match="exactly one priced usage event"):
        smoke.execute_smoke(
            run_root=run_root,
            maximum_usd=Decimal("2.00"),
            authorized=True,
            smoke_root=smoke_root,
            chunks_loader=_chunks,
            client_factory=lambda: client,
            prose_generator=untracked_generator,
        )

    assert calls == [smoke.MODE_ORDER[0].value]
    assert client.retry_options == [0]
    assert len(list((run_root / "attempts").glob("*/intent.json"))) == 1
    outcomes = list((run_root / "attempts").glob("*/outcome.json"))
    assert len(outcomes) == 1
    assert json.loads(outcomes[0].read_text(encoding="utf-8"))["status"] == (
        "ambiguous_usage"
    )
    assert not (run_root / "private-summary.json").exists()


def test_ledger_read_failure_is_sealed_and_stops_after_first_call(tmp_path, monkeypatch):
    calls: list[str] = []
    smoke_root = tmp_path / "paid-smokes"
    run_root = smoke_root / "ledger-failure"

    class BrokenLedger:
        def update_settings(self, **_kwargs):
            return None

        def request_usage_totals(self, _request_id):
            raise OSError("synthetic ledger failure")

        def request_usage_cost_state(self, _request_id):
            pytest.fail("second ledger read must not follow the first failure")

    def generated_without_accounting(_client, *, mode, **_kwargs):
        calls.append(mode.value)
        return EvidenceProseRenderResult(
            status=ProseRenderStatus.GENERATED,
            mode=mode,
            answer="Synthetic answer.",
            segments=(),
            used_card_ids=(),
            used_source_numbers=(),
            failure_code=None,
        )

    monkeypatch.setattr(smoke, "UsageLedger", BrokenLedger)
    with pytest.raises(smoke.ReaderModeSmokeError, match="usage ledger failed"):
        smoke.execute_smoke(
            run_root=run_root,
            maximum_usd=Decimal("2.00"),
            authorized=True,
            smoke_root=smoke_root,
            chunks_loader=_chunks,
            client_factory=_NoRetryClient,
            prose_generator=generated_without_accounting,
        )

    assert calls == [smoke.MODE_ORDER[0].value]
    outcome_path = next((run_root / "attempts").glob("*/outcome.json"))
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["status"] == "ledger_failure"
    assert outcome["usage"] == {"measurement_status": "unavailable"}
    assert outcome["error_class"] == "OSError"
    assert "synthetic ledger failure" not in json.dumps(outcome)


def test_existing_or_out_of_scope_run_root_is_rejected_before_corpus_read(tmp_path):
    smoke_root = tmp_path / "paid-smokes"
    existing = smoke_root / "existing"
    existing.mkdir(parents=True)
    touched: list[str] = []

    for run_root in (existing, tmp_path / "outside"):
        with pytest.raises(smoke.ReaderModeSmokeError):
            smoke.execute_smoke(
                run_root=run_root,
                maximum_usd=Decimal("2.00"),
                authorized=True,
                smoke_root=smoke_root,
                chunks_loader=lambda _project: touched.append("corpus") or [],
                client_factory=lambda: touched.append("client") or object(),
            )

    assert touched == []
