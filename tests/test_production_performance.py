from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

import production_performance as protocol
import web_api
from exposure_profile import ExposureSettings


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_production_performance.py"
SPEC = importlib.util.spec_from_file_location("run_production_performance", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)

GOLD = ROOT / "fixtures" / "gold_set.json"
PROVENANCE = ROOT / "fixtures" / "gold_set.provenance.json"
CORPUS_MANIFEST = ROOT / "fixtures" / "corpus_manifest.json"
LOCATORS = ROOT / "fixtures" / "edition_locators" / "typeset_pdf_0706.json"
COMMIT = "a" * 40
EPOCH = "b" * 32


@lru_cache(maxsize=1)
def _prepared() -> tuple[dict[str, object], tuple[protocol.SelectedItem, ...]]:
    with patch("production_performance.clean_wrapper_commit", return_value=COMMIT):
        return protocol.build_prepared_manifest(
            repository_root=ROOT,
            run_id="production-unit",
            base_url="https://testserver",
            gold_path=GOLD,
            provenance_path=PROVENANCE,
            corpus_manifest_path=CORPUS_MANIFEST,
        )


def _runtime_identity(manifest: dict[str, object], *, epoch: str = EPOCH) -> dict[str, object]:
    cost_contract = manifest["cost_contract"]
    assert isinstance(cost_contract, dict)
    return {
        "schema": protocol.PUBLIC_RUNTIME_IDENTITY_SCHEMA,
        "deployment_commit": COMMIT,
        "process_epoch": epoch,
        "answer_policy_version": manifest["answer_policy_version_expected"],
        "evidence_retrieval_kind": "hybrid_bm25_rrf",
        "embedding_model": manifest["embedding_model_expected"],
        "generated_prose_model": manifest["generated_prose_model_expected"],
        "corpus_manifest_sha256": manifest["corpus_manifest_sha256"],
        "frozen_candidate_commit": manifest["frozen_candidate_commit"],
        "frozen_candidate_rag_policy": manifest["frozen_candidate_rag_policy"],
        "public_rag_request_cost_ceiling_version": cost_contract[
            "public_rag_request_cost_ceiling_version"
        ],
        "public_rag_request_cost_ceiling_nano_usd": cost_contract[
            "public_rag_request_cost_ceiling_nano_usd"
        ],
    }


def _application_compiled_manifest() -> dict[str, object]:
    current, _items = _prepared()
    legacy = dict(current)
    legacy["schema"] = protocol.APPLICATION_COMPILED_PREPARED_MANIFEST_SCHEMA
    legacy["protocol_version"] = protocol.LEGACY_PROTOCOL_VERSION
    legacy["answer_policy_version_expected"] = "application-compiled-v1"
    legacy["evidence_retrieval_kind_expected"] = "local_bm25"
    legacy.pop("embedding_model_expected")
    legacy["answer_provider_model_expected"] = None
    cost_contract = dict(legacy["cost_contract"])
    cost_contract["answer_provider_contract"] = "providerless_essential_zero_calls"
    cost_contract.pop("expected_provider_operations_per_attempt")
    cost_contract["expected_provider_event_count_per_attempt"] = 0
    cost_contract["max_next_attempt_cost_usd"] = 0.0
    cost_contract["max_next_attempt_cost_nano_usd"] = 0
    cost_contract["ceiling_enforcement"] = (
        "essential_is_providerless_and_request_scoped_usage_must_remain_zero"
    )
    legacy["cost_contract"] = cost_contract
    return protocol.sealed_artifact(legacy)


def _legacy_manifest() -> dict[str, object]:
    legacy = dict(_application_compiled_manifest())
    legacy["schema"] = protocol.LEGACY_PREPARED_MANIFEST_SCHEMA
    legacy.pop("answer_policy_version_expected")
    legacy.pop("evidence_retrieval_kind_expected")
    legacy.pop("answer_provider_model_expected")
    legacy["generator_model_expected"] = legacy.pop("generated_prose_model_expected")
    cost_contract = dict(legacy["cost_contract"])
    cost_contract.pop("answer_provider_contract")
    cost_contract.pop("expected_provider_event_count_per_attempt")
    cost_contract.pop("max_next_attempt_cost_nano_usd")
    cost_contract["max_next_attempt_cost_usd"] = protocol.MAX_NEXT_ATTEMPT_COST_USD
    cost_contract["ceiling_enforcement"] = (
        "server_reserves_the_full_request_ceiling_before_RAG_and_projects_"
        "every_provider_operation_before_send"
    )
    legacy["cost_contract"] = cost_contract
    return protocol.sealed_artifact(legacy)


def _application_compiled_runtime_identity(
    manifest: dict[str, object], *, epoch: str = EPOCH
) -> dict[str, object]:
    cost_contract = manifest["cost_contract"]
    assert isinstance(cost_contract, dict)
    return {
        "schema": protocol.APPLICATION_COMPILED_PUBLIC_RUNTIME_IDENTITY_SCHEMA,
        "deployment_commit": COMMIT,
        "process_epoch": epoch,
        "answer_policy_version": manifest["answer_policy_version_expected"],
        "evidence_retrieval_kind": manifest["evidence_retrieval_kind_expected"],
        "generated_prose_model": manifest["generated_prose_model_expected"],
        "corpus_manifest_sha256": manifest["corpus_manifest_sha256"],
        "frozen_candidate_commit": manifest["frozen_candidate_commit"],
        "frozen_candidate_rag_policy": manifest["frozen_candidate_rag_policy"],
        "public_rag_request_cost_ceiling_version": cost_contract[
            "public_rag_request_cost_ceiling_version"
        ],
        "public_rag_request_cost_ceiling_nano_usd": cost_contract[
            "public_rag_request_cost_ceiling_nano_usd"
        ],
    }


def _legacy_runtime_identity(
    manifest: dict[str, object], *, epoch: str = EPOCH
) -> dict[str, object]:
    cost_contract = manifest["cost_contract"]
    assert isinstance(cost_contract, dict)
    return {
        "schema": protocol.LEGACY_PUBLIC_RUNTIME_IDENTITY_SCHEMA,
        "deployment_commit": COMMIT,
        "process_epoch": epoch,
        "rag_policy_version": manifest["frozen_candidate_rag_policy"],
        "generator_model": manifest["generator_model_expected"],
        "corpus_manifest_sha256": manifest["corpus_manifest_sha256"],
        "frozen_candidate_commit": manifest["frozen_candidate_commit"],
        "frozen_candidate_rag_policy": manifest["frozen_candidate_rag_policy"],
        "public_rag_request_cost_ceiling_version": cost_contract[
            "public_rag_request_cost_ceiling_version"
        ],
        "public_rag_request_cost_ceiling_nano_usd": cost_contract[
            "public_rag_request_cost_ceiling_nano_usd"
        ],
    }


def _session(manifest: dict[str, object], *, epoch: str = EPOCH) -> dict[str, object]:
    if protocol.manifest_is_query_embedding_essential(manifest):
        identity = _runtime_identity(manifest, epoch=epoch)
    elif protocol.manifest_is_providerless_essential(manifest):
        identity = _application_compiled_runtime_identity(manifest, epoch=epoch)
    else:
        identity = _legacy_runtime_identity(manifest, epoch=epoch)
    health = {
        "status": 200,
        "body_status": "ready",
        "deployment_commit": COMMIT,
        "process_epoch": epoch,
    }
    return protocol.build_runtime_session(
        manifest=manifest,
        identity=identity,
        health_observations=[health, health],
    )


def _usage(
    *,
    cost: float = 0.01,
    operation_event_counts: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "estimated_cost_usd": cost,
        "input_tokens": 10,
        "cached_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 5,
        "reasoning_tokens": 2,
        "total_tokens": 17,
        "event_count": 1,
        "unpriced_event_count": 0,
        "operation_event_counts": operation_event_counts or {"query_embedding": 1},
    }


def _zero_usage() -> dict[str, object]:
    return {
        "estimated_cost_usd": 0.0,
        "input_tokens": 0,
        "cached_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "event_count": 0,
        "unpriced_event_count": 0,
        "operation_event_counts": {},
    }


def _observation(
    item: protocol.SelectedItem,
    *,
    request_id: str,
    duration_ms: float,
    epoch: str = EPOCH,
) -> dict[str, object]:
    return {
        "schema": "archivist.public_request_observation/1",
        "request_id": request_id,
        "recorded_at": "2099-08-10T12:00:00+00:00",
        "deployment_commit": COMMIT,
        "process_epoch": epoch,
        "render_instance_id": "render-unit",
        "route": "question",
        "delivery": "complete",
        "conversation_id": item.conversation_id,
        "turn_id": item.turn_id,
        "archivist_mode": "essential",
        "answer_strategy": "rag",
        "http_status": 200,
        "duration_ms": duration_ms,
    }


def _outcome(
    manifest: dict[str, object],
    item: protocol.SelectedItem,
    *,
    duration_ms: float,
    diagnostics: dict[str, object] | None = None,
    epoch: str = EPOCH,
) -> tuple[dict[str, object], dict[str, object]]:
    intent = protocol.build_attempt_intent(
        manifest=manifest,
        item=item,
        started_at=f"2026-08-10T12:{item.ordinal:02d}:00+00:00",
    )
    request_id = f"{item.ordinal:032x}"
    outcome = protocol.build_attempt_outcome(
        manifest=manifest,
        intent=intent,
        request_id=request_id,
        http_status=200,
        response_contract_valid=True,
        response_error_code=None,
        answer_status="answered",
        response_payload_sha256="c" * 64,
        client_duration_ms=duration_ms + 4,
        header_duration_ms=duration_ms,
        header_commit=COMMIT,
        header_process_epoch=epoch,
        observation=_observation(
            item,
            request_id=request_id,
            duration_ms=duration_ms,
            epoch=epoch,
        ),
        diagnostics=diagnostics if diagnostics is not None else {"answer_status": "answered"},
        usage_totals=(
            _zero_usage()
            if protocol.manifest_is_providerless_essential(manifest)
            else _usage()
        ),
    )
    return intent, outcome


class _Ledger:
    def __init__(self, outcomes: list[dict[str, object]]):
        self.totals = {str(outcome["request_id"]): outcome["usage_totals"] for outcome in outcomes}

    def request_usage_totals(self, request_id: str):
        return self.totals[request_id]

    def get_public_request_observation(self, _request_id: str):
        raise AssertionError("completed resume/report must not query observations")

    def find_public_request_observation(self, **_kwargs):
        raise AssertionError("completed resume/report must not query observations")


def _authorization_record(
    manifest: dict[str, object],
    *,
    maximum: float | None = None,
) -> dict[str, object]:
    cost_contract = manifest["cost_contract"]
    assert isinstance(cost_contract, dict)
    providerless = protocol.manifest_is_providerless_essential(manifest)
    authorized_maximum = (0.0 if providerless else 40.0) if maximum is None else maximum
    return protocol.sealed_artifact(
        {
            "schema": runner.AUTHORIZATION_SCHEMA,
            "run_id": manifest["run_id"],
            "manifest_sha256": manifest["artifact_sha256"],
            "max_cost_usd": authorized_maximum,
            "max_next_attempt_cost_usd": cost_contract["max_next_attempt_cost_usd"],
            "max_next_attempt_cost_nano_usd": cost_contract.get(
                "max_next_attempt_cost_nano_usd",
                cost_contract["public_rag_request_cost_ceiling_nano_usd"],
            ),
            "request_cost_ceiling_version": cost_contract[
                "public_rag_request_cost_ceiling_version"
            ],
            "cost_ceiling_enforcement": cost_contract["ceiling_enforcement"],
            "operation_scope": (
                "exactly one Complete public POST for each still-untouched planned item; "
                "no retries or replacements"
            ),
        }
    )


def _materialize_complete_run(tmp_path: Path):
    manifest, items = _prepared()
    run_root = tmp_path / "cohort"
    protocol.write_json_no_overwrite(run_root / "prepared-manifest.json", manifest)
    session = _session(manifest)
    protocol.write_json_no_overwrite(run_root / "runtime-session.json", session)
    outcomes: list[dict[str, object]] = []
    for item in items:
        intent, outcome = _outcome(manifest, item, duration_ms=float(item.ordinal * 100))
        protocol.write_json_no_overwrite(
            run_root / "attempts" / f"{item.ordinal:02d}" / "intent.json",
            intent,
        )
        protocol.write_json_no_overwrite(
            run_root / "attempts" / f"{item.ordinal:02d}" / "outcome.json",
            outcome,
        )
        outcomes.append(outcome)
    usage_db = tmp_path / "usage.sqlite3"
    usage_db.write_bytes(b"SQLite format 3\0")
    runner._authorization(run_root=run_root, manifest=manifest, maximum=40.0)
    return run_root, usage_db, manifest, items, session, outcomes


def _args(run_root: Path, usage_db: Path) -> argparse.Namespace:
    return argparse.Namespace(
        run_root=run_root,
        usage_db=usage_db,
        authorize_production_performance=True,
        max_cost_usd=40.0,
        gold=GOLD,
        provenance=PROVENANCE,
        corpus_manifest=CORPUS_MANIFEST,
    )


def test_closed_selection_is_exact_answerable_file_order_and_text_free_on_disk():
    manifest, items = _prepared()
    raw = json.loads(GOLD.read_text(encoding="utf-8"))
    expected_ids = [item["id"] for item in raw["items"] if item["expected_behavior"] == "answer"]

    assert len(items) == protocol.PLANNED_ATTEMPT_COUNT == 33
    assert manifest["schema"] == "archivist.production_performance_manifest/3"
    assert manifest["protocol_version"] == "production-performance-v2"
    assert manifest["answer_policy_version_expected"] == "retrieval-authored-v5"
    assert manifest["evidence_retrieval_kind_expected"] == "hybrid_bm25_rrf"
    assert manifest["embedding_model_expected"] == "text-embedding-3-small"
    assert manifest["generated_prose_model_expected"] == "gpt-5.6-sol"
    assert manifest["cost_contract"] == {
        "answer_provider_contract": "essential_query_embedding_only",
        "expected_provider_operations_per_attempt": ["query_embedding"],
        "expected_provider_event_count_per_attempt": 1,
        "public_rag_request_cost_ceiling_version": "public-rag-request-ceiling-v1",
        "public_rag_request_cost_ceiling_nano_usd": 2_000_000_000,
        "max_next_attempt_cost_usd": 2.0,
        "max_next_attempt_cost_nano_usd": 2_000_000_000,
        "ceiling_enforcement": (
            "server_reserves_the_full_request_ceiling_before_RAG_and_projects_"
            "every_provider_operation_before_send"
        ),
        "unpriced_events_allowed": False,
        "scope": "exact_request_ids_in_this_cohort",
    }
    assert [item.item_id for item in items] == expected_ids
    assert [binding["ordinal"] for binding in manifest["item_bindings"]] == list(range(1, 34))
    assert all("question" not in binding for binding in manifest["item_bindings"])
    assert manifest["request_contract"] == {
        "delivery": "complete",
        "answer_strategy": "rag",
        "archivist_mode": "essential",
        "historiographical_lens": "evidence_first",
        "voice": "scholarly",
        "worldview": "none",
        "history": [],
        "first_turn": True,
        "sequential": True,
        "automatic_retries": 0,
        "replacement_attempts": 0,
        "minimum_start_interval_seconds": 12.0,
        "request_timeout_seconds": 240.0,
    }


def test_runtime_identity_requires_current_retrieval_authored_v5_contract():
    manifest, _items = _prepared()
    identity = _runtime_identity(manifest)

    assert protocol.validate_runtime_identity(identity, manifest=manifest) == identity

    obsolete_identity = {**identity, "schema": "archivist.public_runtime_identity/3"}
    with pytest.raises(
        protocol.ProductionPerformanceError,
        match="unsupported identity contract",
    ):
        protocol.validate_runtime_identity(obsolete_identity, manifest=manifest)


@pytest.mark.parametrize(
    "historical_policy",
    ("retrieval-authored-v3", "retrieval-authored-v4"),
)
def test_current_loader_preserves_a_self_bound_historical_manifest(
    tmp_path,
    historical_policy,
):
    current, _items = _prepared()
    historical = dict(current)
    historical["answer_policy_version_expected"] = historical_policy
    historical = protocol.sealed_artifact(historical)
    path = tmp_path / "prepared-manifest.json"
    protocol.write_json_no_overwrite(path, historical)

    loaded = protocol.load_prepared_manifest(path)
    identity = _runtime_identity(loaded)

    assert loaded == historical
    assert loaded["artifact_sha256"] == historical["artifact_sha256"]
    assert identity["answer_policy_version"] == historical_policy
    assert protocol.validate_runtime_identity(identity, manifest=loaded) == identity


def test_loader_and_runtime_validator_preserve_sealed_v2_contract(tmp_path):
    manifest = _application_compiled_manifest()
    path = tmp_path / "prepared-manifest.json"
    protocol.write_json_no_overwrite(path, manifest)

    loaded = protocol.load_prepared_manifest(path)

    assert loaded == manifest
    assert loaded["artifact_sha256"] == manifest["artifact_sha256"]
    assert loaded["protocol_version"] == "production-performance-v1"
    identity = _application_compiled_runtime_identity(manifest)
    assert protocol.validate_runtime_identity(identity, manifest=manifest) == identity
    with pytest.raises(protocol.ProductionPerformanceError, match="unsupported identity contract"):
        protocol.validate_runtime_identity(_runtime_identity(_prepared()[0]), manifest=manifest)


def test_loader_and_runtime_validator_preserve_sealed_v1_contract(tmp_path):
    manifest = _legacy_manifest()
    path = tmp_path / "prepared-manifest.json"
    protocol.write_json_no_overwrite(path, manifest)

    loaded = protocol.load_prepared_manifest(path)

    assert loaded == manifest
    assert loaded["artifact_sha256"] == manifest["artifact_sha256"]
    assert loaded["protocol_version"] == "production-performance-v1"
    identity = _legacy_runtime_identity(manifest)
    assert protocol.validate_runtime_identity(identity, manifest=manifest) == identity
    with pytest.raises(protocol.ProductionPerformanceError, match="unsupported identity contract"):
        protocol.validate_runtime_identity(_runtime_identity(_prepared()[0]), manifest=manifest)


def test_legacy_v1_summary_remains_reportable_without_contract_rewrite():
    manifest = _legacy_manifest()
    _current, items = _prepared()
    session = _session(manifest)
    outcomes = [
        _outcome(manifest, item, duration_ms=float(item.ordinal * 100))[1]
        for item in items
    ]

    _private, public = protocol.aggregate_summaries(
        manifest=manifest,
        session=session,
        authorization=_authorization_record(manifest),
        outcomes=outcomes,
    )

    assert public["protocol_version"] == "production-performance-v1"
    assert public["cost"]["recorded_estimated_cost_usd"] == 0.33
    assert public["authorization"]["max_next_attempt_cost_usd"] == 2.0
    assert "Enforced maximum accounted per next/unknown attempt: $2.000000" in (
        protocol.public_report_markdown(public)
    )


def test_retrieval_authored_artifacts_bind_production_performance_v2():
    manifest, items = _prepared()
    session = _session(manifest)
    intent, outcome = _outcome(manifest, items[0], duration_ms=100.0)

    assert manifest["protocol_version"] == protocol.PROTOCOL_VERSION
    assert session["protocol_version"] == protocol.PROTOCOL_VERSION
    assert intent["protocol_version"] == protocol.PROTOCOL_VERSION
    assert outcome["protocol_version"] == protocol.PROTOCOL_VERSION
    assert "operation_event_counts" in outcome["usage_totals"]
    assert protocol.PROTOCOL_VERSION == "production-performance-v2"


def test_historical_usage_replay_ignores_only_the_later_operation_breakdown():
    _current, items = _prepared()
    for manifest in (_legacy_manifest(), _application_compiled_manifest()):
        _intent, outcome = _outcome(manifest, items[0], duration_ms=100.0)
        sealed_usage = outcome["usage_totals"]
        assert isinstance(sealed_usage, dict)
        assert "operation_event_counts" not in sealed_usage

        current_ledger_usage = dict(sealed_usage)
        current_ledger_usage["operation_event_counts"] = (
            {"answer_generation": 1} if sealed_usage["event_count"] == 1 else {}
        )

        class CurrentLedger:
            def request_usage_totals(self, _request_id):
                return current_ledger_usage

        recorded, accounted, event_count, unavailable = (
            runner._authorization_accounted_usage(
                CurrentLedger(),
                [outcome],
                manifest=manifest,
                authorization=_authorization_record(manifest),
            )
        )

        assert recorded == float(sealed_usage["estimated_cost_usd"])
        assert accounted == recorded
        assert event_count == sealed_usage["event_count"]
        assert unavailable == 0


def test_prepare_is_offline_even_when_all_client_construction_is_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol, "clean_wrapper_commit", lambda _root: COMMIT)
    monkeypatch.setattr(
        runner.httpx,
        "Client",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("network client constructed")),
    )
    args = SimpleNamespace(
        run_root=tmp_path / "prepared",
        run_id="offline-prepare",
        base_url="https://testserver",
        gold=GOLD,
        provenance=PROVENANCE,
        corpus_manifest=CORPUS_MANIFEST,
    )

    assert runner.prepare(args) == 0
    assert (args.run_root / "prepared-manifest.json").is_file()


def test_prepare_rejects_noncanonical_gold_path_before_client_construction(
    tmp_path,
    monkeypatch,
):
    alternate = tmp_path / "gold_set.json"
    alternate.write_bytes(GOLD.read_bytes())
    monkeypatch.setattr(
        runner.httpx,
        "Client",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("network client constructed")),
    )
    args = SimpleNamespace(
        run_root=tmp_path / "prepared",
        run_id="alternate-gold",
        base_url="https://testserver",
        gold=alternate,
        provenance=PROVENANCE,
        corpus_manifest=CORPUS_MANIFEST,
    )

    with pytest.raises(protocol.ProductionPerformanceError, match="canonical committed gold set"):
        runner.prepare(args)


def test_session_preflight_uses_real_public_health_and_version_contract(tmp_path, monkeypatch):
    manifest, _items = _prepared()
    monkeypatch.setenv("ARCHIVIST_DEPLOY_COMMIT", COMMIT)
    monkeypatch.setenv("ARCHIVIST_USAGE_DB", str(tmp_path / "usage.sqlite3"))
    monkeypatch.setattr(
        web_api,
        "_public_project_config",
        lambda _settings: {
            "exposure_profile": "public_demo",
            "project": {"id": "current", "embedded": True, "embedded_chunks": 481},
            "features": {},
        },
    )
    settings = ExposureSettings.public_demo(
        monthly_budget_usd="5.00",
        locator_artifact=LOCATORS,
    )

    session = runner._establish_session(
        client=TestClient(web_api.create_app(settings)),
        manifest=manifest,
    )

    assert session["deployment_commit"] == COMMIT
    assert session["process_epoch"] == web_api.PROCESS_EPOCH
    assert len(session["health_observations"]) == 2
    assert session["paid_warmup_calls"] == 0


def test_completed_resume_constructs_no_client_and_makes_no_replacement(tmp_path, monkeypatch):
    run_root, usage_db, _manifest, _items, _session_value, outcomes = _materialize_complete_run(
        tmp_path
    )
    monkeypatch.setattr(runner, "UsageLedger", lambda _path: _Ledger(outcomes))

    def fatal_client(**_kwargs):
        raise AssertionError("completed resume constructed a network client")

    assert runner.run(_args(run_root, usage_db), client_factory=fatal_client) == 0
    assert len(list((run_root / "attempts").glob("*/intent.json"))) == 33
    assert len(list((run_root / "attempts").glob("*/outcome.json"))) == 33


def test_report_is_offline_and_public_artifacts_are_closed(tmp_path, monkeypatch):
    run_root, usage_db, _manifest, items, _session_value, outcomes = _materialize_complete_run(
        tmp_path
    )
    monkeypatch.setattr(runner, "UsageLedger", lambda _path: _Ledger(outcomes))
    monkeypatch.setattr(
        runner.httpx,
        "Client",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("report constructed client")),
    )

    assert runner.report(_args(run_root, usage_db)) == 0
    public_json = (run_root / "public-summary.json").read_text(encoding="utf-8")
    public_markdown = (run_root / "public-report.md").read_text(encoding="utf-8")
    combined = public_json + public_markdown
    assert not any(item.item_id in combined for item in items)
    assert not any(item.question in combined for item in items)
    assert "answer" not in json.loads(public_json)
    assert "passage" not in combined.casefold()
    assert "prompt" not in combined.casefold()
    assert "source" not in combined.casefold()


def test_ambiguous_persisted_intent_is_sealed_without_replay_or_zero_spend_claim(
    tmp_path,
    monkeypatch,
):
    manifest, items = _prepared()
    session = _session(manifest)
    intent = protocol.build_attempt_intent(manifest=manifest, item=items[0])
    monkeypatch.setattr(runner, "_wait_for_observation", lambda *_args, **_kwargs: None)

    ledger = SimpleNamespace(
        find_public_request_observation=lambda **_kwargs: None,
    )
    with pytest.raises(protocol.ProductionPerformanceError, match="was sealed"):
        runner._recover_intent(
            run_root=tmp_path,
            manifest=manifest,
            session=session,
            intent=intent,
            ledger=ledger,
        )
    outcome = protocol.validate_sealed_artifact(
        protocol.read_json(
            tmp_path / "attempts" / "01" / "outcome.json",
            label="ambiguous outcome",
        ),
        schema=protocol.ATTEMPT_OUTCOME_SCHEMA,
        label="ambiguous outcome",
    )
    assert outcome["request_id"] is None
    assert outcome["usage_totals"] is None
    assert outcome["usage_measurement_status"] == "unavailable_ambiguous_transport"
    assert outcome["automatic_retry_count"] == 0


def test_terminal_observation_recovers_without_replay_and_process_restart_stops(tmp_path):
    manifest, items = _prepared()
    session = _session(manifest)
    intent = protocol.build_attempt_intent(manifest=manifest, item=items[0])
    restarted_epoch = "d" * 32
    observation = _observation(
        items[0],
        request_id="e" * 32,
        duration_ms=900.0,
        epoch=restarted_epoch,
    )

    recovery_queries: list[dict[str, object]] = []

    class RecoveryLedger:
        def find_public_request_observation(self, **kwargs):
            recovery_queries.append(kwargs)
            return observation

        def get_answer_run_diagnostics_by_request_id(self, _request_id):
            return {"answer_status": "answered"}

        def request_usage_totals(self, _request_id):
            return _usage()

    recovered = runner._recover_intent(
        run_root=tmp_path,
        manifest=manifest,
        session=session,
        intent=intent,
        ledger=RecoveryLedger(),
    )
    assert recovered["recovered_without_replay"] is True
    assert recovered["automatic_retry_count"] == 0
    assert recovery_queries[0]["recorded_at_gte"] == intent["started_at"]
    assert (tmp_path / "attempts" / "01" / "outcome.json").is_file()
    with pytest.raises(protocol.ProductionPerformanceError, match="process/deploy boundary"):
        runner._assert_session_boundary([recovered], session=session)


def test_post_attempt_is_exactly_once_and_persists_intent_first(tmp_path, monkeypatch):
    manifest, items = _prepared()
    session = _session(manifest)
    item = items[0]
    response = httpx.Response(
        200,
        json={
            "answer": "Synthetic public answer.",
            "answer_status": "answered",
            "answer_strategy": "rag",
            "archivist_mode": "essential",
        },
        headers={
            "X-Request-ID": "f" * 32,
            "X-Archivist-Commit": COMMIT,
            "X-Archivist-Process-Epoch": EPOCH,
            "Server-Timing": "app;dur=123.000",
        },
    )
    calls = 0

    class OnePostClient:
        def post(self, _url, *, json):
            nonlocal calls
            calls += 1
            assert (tmp_path / "attempts" / "01" / "intent.json").is_file()
            assert json["history"] == []
            return response

    observation = _observation(
        item,
        request_id="f" * 32,
        duration_ms=123.0,
    )

    class OnePostLedger:
        def find_public_request_observation(self, **_kwargs):
            return None

        def get_public_request_observation(self, _request_id):
            return {**observation, "recorded_at": "2099-08-10T12:00:00+00:00"}

        def get_answer_run_diagnostics_by_request_id(self, _request_id):
            return {"answer_status": "answered"}

        def request_usage_totals(self, _request_id):
            return _usage()

    monkeypatch.setattr(runner, "_seconds_until_start_allowed", lambda _root: 0.0)
    outcome = runner._post_one(
        client=OnePostClient(),
        run_root=tmp_path,
        manifest=manifest,
        session=session,
        item=item,
        ledger=OnePostLedger(),
    )
    assert calls == 1
    assert outcome["automatic_retry_count"] == 0
    assert outcome["instrumentation_failures"] == []


def test_latency_requires_zero_instrumentation_failures_and_uses_closed_estimators():
    manifest, items = _prepared()
    session = _session(manifest)
    outcomes = []
    for item in items:
        _intent, outcome = _outcome(
            manifest,
            item,
            duration_ms=float(item.ordinal * 1000),
        )
        outcomes.append(outcome)
    # A valid 2xx response with an instrumentation defect remains a successful
    # completion, but is not allowed into either latency denominator.
    broken = dict(outcomes[-1])
    broken["instrumentation_failures"] = ["missing_server_timing_header"]
    broken = protocol.sealed_artifact(broken)
    outcomes[-1] = broken

    private, public = protocol.aggregate_summaries(
        manifest=manifest,
        session=session,
        authorization=_authorization_record(manifest),
        outcomes=outcomes,
    )
    assert private["protocol_version"] == "production-performance-v2"
    assert public["protocol_version"] == "production-performance-v2"
    assert public["successful_completion_count"] == 33
    assert public["instrumentation_failure_count"] == 1
    assert public["latency_eligible_completion_count"] == 32
    assert public["server_latency"] == {
        "observation_count": 32,
        "p50_seconds": 16.5,
        "p95_seconds": 31.0,
    }
    assert public["authorization"] == {
        "max_cost_usd": 40.0,
        "max_next_attempt_cost_usd": 2.0,
        "max_next_attempt_cost_nano_usd": 2_000_000_000,
        "request_cost_ceiling_version": "public-rag-request-ceiling-v1",
        "cost_ceiling_enforcement": manifest["cost_contract"]["ceiling_enforcement"],
    }


def test_zero_latency_eligible_rows_still_emit_honest_public_report():
    manifest, items = _prepared()
    session = _session(manifest)
    outcomes = []
    for item in items:
        _intent, outcome = _outcome(manifest, item, duration_ms=100.0)
        changed = dict(outcome)
        changed["instrumentation_failures"] = ["missing_server_timing_header"]
        outcomes.append(protocol.sealed_artifact(changed))

    _private, public = protocol.aggregate_summaries(
        manifest=manifest,
        session=session,
        authorization=_authorization_record(manifest),
        outcomes=outcomes,
    )
    report = protocol.public_report_markdown(public)
    assert public["latency_eligible_completion_count"] == 0
    assert public["server_latency"] is None
    assert public["operator_client_latency"] is None
    assert "unavailable (zero latency-eligible completions)" in report


def test_providerless_authorization_requires_an_exact_zero_cap(tmp_path):
    manifest = _application_compiled_manifest()
    with pytest.raises(protocol.ProductionPerformanceError, match="exactly zero"):
        runner._authorization(run_root=tmp_path, manifest=manifest, maximum=0.01)


def test_legacy_authorization_retains_full_server_enforced_reserve(tmp_path):
    manifest = _legacy_manifest()
    with pytest.raises(protocol.ProductionPerformanceError, match="server-enforced"):
        runner._authorization(run_root=tmp_path, manifest=manifest, maximum=1.99)


def test_valid_application_compiled_completion_with_zero_usage_is_latency_eligible():
    manifest = _application_compiled_manifest()
    _current, items = _prepared()
    intent = protocol.build_attempt_intent(manifest=manifest, item=items[0])
    usage = _zero_usage()
    outcome = protocol.build_attempt_outcome(
        manifest=manifest,
        intent=intent,
        request_id="1" * 32,
        http_status=200,
        response_contract_valid=True,
        response_error_code=None,
        answer_status="answered",
        response_payload_sha256="c" * 64,
        client_duration_ms=104.0,
        header_duration_ms=100.0,
        header_commit=COMMIT,
        header_process_epoch=EPOCH,
        observation=_observation(
            items[0],
            request_id="1" * 32,
            duration_ms=100.0,
        ),
        diagnostics={"answer_status": "answered"},
        usage_totals=usage,
    )

    assert outcome["instrumentation_failures"] == []


@pytest.mark.parametrize("event_count", [0, 2])
def test_retrieval_authored_essential_requires_exactly_one_provider_event(event_count):
    manifest, items = _prepared()
    intent = protocol.build_attempt_intent(manifest=manifest, item=items[0])
    usage = _usage()
    usage["event_count"] = event_count
    outcome = protocol.build_attempt_outcome(
        manifest=manifest,
        intent=intent,
        request_id="4" * 32,
        http_status=200,
        response_contract_valid=True,
        response_error_code=None,
        answer_status="answered",
        response_payload_sha256="c" * 64,
        client_duration_ms=104.0,
        header_duration_ms=100.0,
        header_commit=COMMIT,
        header_process_epoch=EPOCH,
        observation=_observation(items[0], request_id="4" * 32, duration_ms=100.0),
        diagnostics={"answer_status": "answered"},
        usage_totals=usage,
    )

    assert outcome["instrumentation_failures"] == ["unexpected_provider_event_count"]


def test_retrieval_authored_essential_rejects_the_wrong_provider_operation():
    manifest, items = _prepared()
    intent = protocol.build_attempt_intent(manifest=manifest, item=items[0])
    usage = _usage(operation_event_counts={"answer_generation": 1})
    outcome = protocol.build_attempt_outcome(
        manifest=manifest,
        intent=intent,
        request_id="5" * 32,
        http_status=200,
        response_contract_valid=True,
        response_error_code=None,
        answer_status="answered",
        response_payload_sha256="c" * 64,
        client_duration_ms=104.0,
        header_duration_ms=100.0,
        header_commit=COMMIT,
        header_process_epoch=EPOCH,
        observation=_observation(items[0], request_id="5" * 32, duration_ms=100.0),
        diagnostics={"answer_status": "answered"},
        usage_totals=usage,
    )

    assert outcome["instrumentation_failures"] == ["unexpected_provider_operation"]


def test_legacy_valid_completion_still_requires_a_usage_event():
    manifest = _legacy_manifest()
    _current, items = _prepared()
    intent = protocol.build_attempt_intent(manifest=manifest, item=items[0])
    outcome = protocol.build_attempt_outcome(
        manifest=manifest,
        intent=intent,
        request_id="2" * 32,
        http_status=200,
        response_contract_valid=True,
        response_error_code=None,
        answer_status="answered",
        response_payload_sha256="c" * 64,
        client_duration_ms=104.0,
        header_duration_ms=100.0,
        header_commit=COMMIT,
        header_process_epoch=EPOCH,
        observation=_observation(items[0], request_id="2" * 32, duration_ms=100.0),
        diagnostics={"answer_status": "answered"},
        usage_totals=_zero_usage(),
    )

    assert outcome["instrumentation_failures"] == ["zero_usage_events"]


def test_ambiguous_terminal_outcome_closes_fixed_denominator_with_reserved_cost():
    manifest, items = _prepared()
    session = _session(manifest)
    outcomes: list[dict[str, object]] = []
    for item in items[:-1]:
        _intent, outcome = _outcome(manifest, item, duration_ms=100.0)
        outcomes.append(outcome)
    last_intent = protocol.build_attempt_intent(manifest=manifest, item=items[-1])
    outcomes.append(
        protocol.build_ambiguous_transport_outcome(
            manifest=manifest,
            session=session,
            intent=last_intent,
            failure_code="client_timeout",
            client_duration_ms=240_000.0,
        )
    )

    _private, public = protocol.aggregate_summaries(
        manifest=manifest,
        session=session,
        authorization=_authorization_record(manifest),
        outcomes=outcomes,
    )
    report = protocol.public_report_markdown(public)
    assert public["attempted_count"] == 33
    assert public["successful_completion_count"] == 32
    assert public["failure_count"] == 1
    assert public["instrumentation_failure_count"] == 1
    assert public["latency_eligible_completion_count"] == 32
    assert public["cost"]["estimated_cost_usd"] is None
    assert public["cost"]["recorded_estimated_cost_usd"] == 0.32
    assert public["cost"]["authorization_accounted_cost_usd"] == 2.32
    assert "Attempts with unavailable usage: 1" in report


def test_transport_failure_posts_once_seals_ambiguity_and_stops_invocation(
    tmp_path,
    monkeypatch,
):
    manifest, items = _prepared()
    session = _session(manifest)
    calls = 0

    class FailedClient:
        def post(self, _url, *, json):
            nonlocal calls
            calls += 1
            assert json["history"] == []
            raise httpx.ReadTimeout("closed test timeout")

    class EmptyLedger:
        def find_public_request_observation(self, **_kwargs):
            return None

    monkeypatch.setattr(runner, "_seconds_until_start_allowed", lambda _root: 0.0)
    monkeypatch.setattr(runner, "_wait_for_observation", lambda *_args, **_kwargs: None)
    with pytest.raises(protocol.ProductionPerformanceError, match="was sealed"):
        runner._post_one(
            client=FailedClient(),
            run_root=tmp_path,
            manifest=manifest,
            session=session,
            item=items[0],
            ledger=EmptyLedger(),
        )
    assert calls == 1
    assert (tmp_path / "attempts" / "01" / "intent.json").is_file()
    assert (tmp_path / "attempts" / "01" / "outcome.json").is_file()


def test_preexisting_scope_observation_prevents_intent_and_post(tmp_path, monkeypatch):
    manifest, items = _prepared()
    session = _session(manifest)

    class FatalClient:
        def post(self, *_args, **_kwargs):
            raise AssertionError("stale scope must prevent POST")

    class StaleLedger:
        def find_public_request_observation(self, **_kwargs):
            return {"schema": "stale"}

    monkeypatch.setattr(runner, "_seconds_until_start_allowed", lambda _root: 0.0)
    with pytest.raises(protocol.ProductionPerformanceError, match="already exists"):
        runner._post_one(
            client=FatalClient(),
            run_root=tmp_path,
            manifest=manifest,
            session=session,
            item=items[0],
            ledger=StaleLedger(),
        )
    assert not (tmp_path / "attempts" / "01" / "intent.json").exists()


def test_observation_predating_intent_is_rejected():
    manifest, items = _prepared()
    intent = protocol.build_attempt_intent(
        manifest=manifest,
        item=items[0],
        started_at="2026-08-10T12:00:00+00:00",
    )
    observation = _observation(
        items[0],
        request_id="9" * 32,
        duration_ms=100.0,
    )
    observation["recorded_at"] = "2026-08-10T11:59:59+00:00"

    with pytest.raises(protocol.ProductionPerformanceError, match="predates"):
        runner._validate_observation(observation, intent=intent)


def test_recorded_request_cost_cannot_exceed_deployed_per_request_ceiling():
    manifest, items = _prepared()
    _intent, outcome = _outcome(manifest, items[0], duration_ms=100.0)
    changed = dict(outcome)
    changed["usage_totals"] = _usage(cost=2.01)
    outcome = protocol.sealed_artifact(changed)
    ledger = _Ledger([outcome])

    with pytest.raises(protocol.ProductionPerformanceError, match="per-request ceiling"):
        runner._authorization_accounted_usage(
            ledger,
            [outcome],
            manifest=manifest,
            authorization=_authorization_record(manifest),
        )


def test_providerless_outcome_marks_any_provider_event_as_instrumentation_failure():
    manifest = _application_compiled_manifest()
    _current, items = _prepared()
    intent = protocol.build_attempt_intent(manifest=manifest, item=items[0])
    outcome = protocol.build_attempt_outcome(
        manifest=manifest,
        intent=intent,
        request_id="3" * 32,
        http_status=200,
        response_contract_valid=True,
        response_error_code=None,
        answer_status="answered",
        response_payload_sha256="c" * 64,
        client_duration_ms=104.0,
        header_duration_ms=100.0,
        header_commit=COMMIT,
        header_process_epoch=EPOCH,
        observation=_observation(items[0], request_id="3" * 32, duration_ms=100.0),
        diagnostics={"answer_status": "answered"},
        usage_totals=_usage(),
    )

    assert outcome["instrumentation_failures"] == ["unexpected_provider_usage"]


def test_next_attempt_capacity_reserves_full_server_enforced_maximum():
    manifest = _legacy_manifest()
    authorization = _authorization_record(manifest, maximum=4.0)

    runner._require_next_attempt_capacity(
        recorded_cost_usd=0.0,
        accounted_cost_usd=2.0,
        unavailable_attempts=1,
        authorization=authorization,
    )
    with pytest.raises(protocol.ProductionPerformanceError, match="requires the server-enforced"):
        runner._require_next_attempt_capacity(
            recorded_cost_usd=0.01,
            accounted_cost_usd=2.01,
            unavailable_attempts=1,
            authorization=authorization,
        )


def test_multiple_unresolved_intents_are_rejected_before_observation_lookup(tmp_path):
    manifest, items = _prepared()
    session = _session(manifest)
    for item in items[:2]:
        protocol.write_json_no_overwrite(
            tmp_path / "attempts" / f"{item.ordinal:02d}" / "intent.json",
            protocol.build_attempt_intent(manifest=manifest, item=item),
        )
    ledger = SimpleNamespace(
        find_public_request_observation=lambda **_kwargs: pytest.fail(
            "observation lookup should not begin for an invalid state"
        )
    )
    with pytest.raises(protocol.ProductionPerformanceError, match="multiple unresolved"):
        runner._terminal_state(
            run_root=tmp_path,
            manifest=manifest,
            session=session,
            ledger=ledger,
        )
