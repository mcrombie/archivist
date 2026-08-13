from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import retrieval
import retrieval_authored_v3_evaluation as v3

from archivist_modes import ArchivistMode
from authored_response import (
    AuthoredDisposition,
    AuthoredResponseResult,
    AuthoredResponseStatus,
)
from costs import TokenUsage, UsageLedger, current_usage_context
from retrieval_authored_v3_evaluation import (
    MASTER_COST_CAP_USD,
    MASTER_REQUEST_ID,
    ProviderCapturingClient,
    V3EvaluationError,
    V3Paths,
    _generation_intent,
    _intent_or_resume,
    _require_operation_evidence,
    default_paths,
    generate_professional_item,
    master_usage_scope,
    master_budget_state,
    reconcile_generation_ambiguity,
    retrieve_with_cached_embedding,
)


def _final_ids(outcome) -> list[str]:
    return [str(chunk["chunk_id"]) for chunk in outcome.final_chunks]


class _Collection:
    metadata = {
        "chunks_sha256": "synthetic",
        "embedding_model": "text-embedding-3-small",
        "hnsw:space": "l2",
    }
    configuration = {"hnsw": {"space": "l2"}}

    def __init__(self) -> None:
        self.query_calls: list[dict[str, object]] = []

    def count(self) -> int:
        return 4

    def query(self, **kwargs: object) -> dict[str, object]:
        self.query_calls.append(kwargs)
        return {
            "ids": [["c1", "c2", "c3", "c4"]],
            "metadatas": [[
                {"chunk_id": "c1", "document": "one.md"},
                {"chunk_id": "c2", "document": "two.md"},
                {"chunk_id": "c3", "document": "three.md"},
                {"chunk_id": "c4", "document": "four.md"},
            ]],
            "distances": [[0.1, 0.2, 0.3, 0.4]],
        }


def _chunks() -> list[dict[str, object]]:
    return [
        {
            "chunk_id": f"c{index}",
            "document": f"{label}.md",
            "chapter_title": f"Synthetic {label}",
            "paragraph_start": index,
            "paragraph_end": index,
            "text": (
                f"The synthetic subject acted in a documented way during episode {index}. "
                "This sentence supplies another bounded detail."
            ),
        }
        for index, label in enumerate(("one", "two", "three", "four"), start=1)
    ]


def _paths(root: Path) -> V3Paths:
    placeholder = root / "placeholder"
    return V3Paths(
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


def test_cached_retrieval_uses_supplied_vector_and_never_an_embedding_client():
    collection = _Collection()
    hybrid, outcome, primary_by_k = retrieve_with_cached_embedding(
        question="What did the synthetic subject do?",
        embedding=[0.1, 0.2, 0.3],
        collection=collection,
        chunks=_chunks(),
        corpus_trace={"collection_count": 4, "hnsw_space": "l2"},
    )

    assert collection.query_calls == [
        {
            "query_embeddings": [[0.1, 0.2, 0.3]],
            "n_results": 4,
            "include": ["metadatas", "distances"],
        }
    ]
    assert hybrid["hybrid"]["primary_chunk_ids"]
    assert outcome.final_chunks
    assert primary_by_k["1"]


def test_cached_adapter_matches_current_product_retrieval_primitives(monkeypatch):
    question = "What did the synthetic subject do?"
    vector = [0.1, 0.2, 0.3]
    corpus_trace = {"collection_count": 4, "hnsw_space": "l2"}
    adapter_collection = _Collection()
    product_collection = _Collection()
    monkeypatch.setattr(retrieval, "embed_query", lambda *_args, **_kwargs: vector)

    adapter_hybrid, adapter_outcome, _ = retrieve_with_cached_embedding(
        question=question,
        embedding=vector,
        collection=adapter_collection,
        chunks=_chunks(),
        corpus_trace=corpus_trace,
        profile_k=False,
    )
    product_hybrid = retrieval.retrieve_from_collection(
        question,
        product_collection,
        _chunks(),
        n_results=5,
        embedding_client=object(),
        corpus=corpus_trace,
    )
    product_outcome = retrieval.plan_context_chunks(product_hybrid, chunks=_chunks())

    assert adapter_hybrid["hybrid"]["primary_chunk_ids"] == product_hybrid["hybrid"][
        "primary_chunk_ids"
    ]
    assert _final_ids(adapter_outcome) == _final_ids(product_outcome)


def test_generation_calls_author_once_and_preserves_distinct_source_sets():
    collection = _Collection()
    item = {
        "id": "H001",
        "question": "What did the synthetic subject do?",
        "relevant_chunk_ids": ["c1", "c2"],
        "claims": [
            {"claim_id": "R1", "essential": True, "supporting_chunk_ids": ["c1"]}
        ],
    }
    cohort = SimpleNamespace(
        embeddings={"H001": [0.1, 0.2, 0.3]},
        collection=collection,
        chunks=_chunks(),
        corpus_trace={"collection_count": 4, "hnsw_space": "l2"},
    )
    calls: list[str] = []

    def author(_client, *, dossier, **_kwargs):
        calls.append(dossier.dossier_id)
        return AuthoredResponseResult(
            status=AuthoredResponseStatus.GENERATED,
            mode=ArchivistMode.PROFESSIONAL,
            answer="A synthetic grounded answer [Source 1].\n\nWhat should we examine next?",
            disposition=AuthoredDisposition.ANSWERED,
            paragraphs=(),
            follow_up_questions=("What should we examine next?",),
            used_unit_ids=(dossier.units[0].unit_id,),
            used_source_numbers=(1,),
            failure_code=None,
        )

    outcome = generate_professional_item(
        cohort,
        item=item,
        client=object(),
        author=author,
        require_provider_observation=False,
    )

    assert len(calls) == 1
    assert outcome["attempt_count"] == 1
    assert outcome["automatic_retries"] == 0
    assert outcome["query_embedding_provider_operations"] == 0
    assert outcome["finalized_retrieval_chunk_ids"]
    assert outcome["dossier"]["model_visible_units"]
    assert outcome["rendered_cited_source_numbers"] == [1]
    assert outcome["rendered_cited_chunk_ids"] == [
        outcome["dossier"]["model_visible_units"][0]["chunk_id"]
    ]
    assert outcome["displayed_source_chunk_ids"]


def test_intent_first_resume_rejects_ambiguous_attempt(tmp_path):
    intent_path = tmp_path / "intent.json"
    outcome_path = tmp_path / "outcome.json"
    intent = {"schema": "synthetic", "item_id": "H001"}

    assert not _intent_or_resume(
        intent_path=intent_path,
        outcome_path=outcome_path,
        intent=intent,
    )
    assert not intent_path.exists()
    intent_path.write_text(
        '{"item_id":"H001","schema":"synthetic"}\n',
        encoding="utf-8",
    )
    with pytest.raises(V3EvaluationError, match="ambiguous"):
        _intent_or_resume(
            intent_path=intent_path,
            outcome_path=outcome_path,
            intent=intent,
        )
    outcome_path.write_text("{}\n", encoding="utf-8")
    assert _intent_or_resume(
        intent_path=intent_path,
        outcome_path=outcome_path,
        intent=intent,
    )


def test_provider_capture_preserves_raw_response_metadata_before_parse_failure():
    payload = {
        "id": "response-raw",
        "model": "gpt-5.6-sol",
        "status": "completed",
        "created_at": 1,
    }
    attempts: list[str] = []

    class RawResponse:
        def json(self):
            return payload

        def parse(self):
            raise ValueError("structured validation failed")

    resource = SimpleNamespace(
        with_raw_response=SimpleNamespace(parse=lambda **_kwargs: RawResponse())
    )
    client = ProviderCapturingClient(
        SimpleNamespace(responses=resource),
        on_provider_attempt=lambda: attempts.append("started"),
    )

    raw = client.responses.with_raw_response.parse(model="gpt-5.6-sol")
    with pytest.raises(ValueError, match="structured validation"):
        raw.parse()

    assert attempts == ["started"]
    assert client.attempt_count == 1
    assert client.observations[0].response_id == "response-raw"
    assert client.observations[0].model == "gpt-5.6-sol"


def test_default_paths_rejects_non_private_run_root(tmp_path):
    base = tmp_path / "repo"
    with pytest.raises(V3EvaluationError, match="runtime/evaluations"):
        default_paths(base, root=tmp_path / "public-results")


def test_master_scope_reuses_one_request_id_and_one_ledger(tmp_path):
    paths = _paths(tmp_path / "run")
    with master_usage_scope(paths, maximum_usd=Decimal("7.00"), turn_id="G001:decomposition"):
        context = current_usage_context()
        assert context.request_id == MASTER_REQUEST_ID
        assert context.request_cost_ceiling_nano_usd == 7_000_000_000
        UsageLedger().record(
            response_id="response-one",
            operation="eval_claim_decomposition_v2",
            requested_model="gpt-5.6-terra",
            actual_model="gpt-5.6-terra",
            usage=TokenUsage(input_tokens=10, output_tokens=10, total_tokens=20),
            request_id=context.request_id,
            project_id=context.project_id,
            conversation_id=context.conversation_id,
            turn_id=context.turn_id,
        )
    with master_usage_scope(paths, maximum_usd=MASTER_COST_CAP_USD, turn_id="H001:generation"):
        assert current_usage_context().request_id == MASTER_REQUEST_ID

    totals = UsageLedger(paths.ledger).request_usage_totals(MASTER_REQUEST_ID)
    assert totals["event_count"] == 1
    assert totals["unpriced_count"] == 0


def test_generation_intent_binds_cached_embedding_and_exact_single_attempt():
    item = {"id": "H001", "question": "Question?"}
    manifest = {"schema": "manifest"}
    intent = _generation_intent(item, manifest)
    assert intent["attempt_count"] == 1
    assert intent["automatic_retries"] == 0
    assert intent["replacement"] is False
    assert intent["query_embedding_provider_operations"] == 0
    assert intent["master_request_id"] == MASTER_REQUEST_ID
    assert intent["question_sha256"]


def test_master_scope_rejects_more_than_seven_dollars(tmp_path):
    with pytest.raises(V3EvaluationError, match="no greater than"):
        with master_usage_scope(_paths(tmp_path), maximum_usd=Decimal("7.01")):
            pytest.fail("unsafe scope opened")


def test_started_provider_attempt_without_usage_is_ambiguous_and_stops():
    with pytest.raises(V3EvaluationError, match="billing state is ambiguous"):
        _require_operation_evidence(
            {
                "event_count": 0,
                "scope_valid": True,
                "operations_valid": True,
                "exactly_one_expected_event": False,
            },
            completed_response_required=False,
            label="H001 generation",
        )


def test_h021_recovery_declaration_is_externally_bound():
    declaration = v3.AMBIGUITY_RECOVERY_DECLARATIONS["H021"]

    assert declaration["sequence"] == 2
    assert declaration["previous_continuation_file_sha256"] == (
        "860dfc056e3b0889b2eb489e0e6fcdfd801a2bc4a7755e568afb3f82e4823330"
    )
    assert declaration["generation_intent_file_sha256"] == (
        "8ccac460a72f35657796c5f71bca0e4ae09e9ce0ad668dd1302f1831d03947e4"
    )
    assert declaration["generation_outcome_file_sha256"] == (
        "16c6e6d2cdcebc032abb23ecda51b15a5cfc1cb8f3a840b5561662cce4fd4cd9"
    )
    assert declaration["provider_request_shape_sha256"] == (
        "67b8150d9b69754d8650be9a548411ed53497276268cd65bf74bd13043cdf43b"
    )
    assert declaration["request_binding_sha256"] == (
        "5ec831a3895f1c47be49a0a00accdb50cd7c51be0d0ad72dcb78b9e84c1165c7"
    )
    assert declaration["projected_worst_case_reserved_nano_usd"] == 392_612_500
    assert declaration["next_item_id"] == "H022"


def test_h025_recovery_declaration_is_externally_bound():
    declaration = v3.AMBIGUITY_RECOVERY_DECLARATIONS["H025"]

    assert declaration["sequence"] == 3
    assert declaration["previous_recovery_harness_commit"] == (
        "ae6b579b34e23005302d274d9f2ff3d2be2d52e9"
    )
    assert declaration["previous_continuation_file_sha256"] == (
        "85ca14894d438da4e544d934a2b765ba4b615d934991210efd37525448260c7c"
    )
    assert declaration["generation_intent_file_sha256"] == (
        "7ed3889d3e73dd9b9057c2a0fc99a0570a998767f0f6dbc28a0b1b05b8a40e42"
    )
    assert declaration["generation_outcome_file_sha256"] == (
        "eea018822db00a3378a64dbd2fac79153ece7b876cbe60a2dfe2b2a406abb21b"
    )
    assert declaration["provider_request_shape_sha256"] == (
        "f57dedaba8fc55930d60b5b0718ed5a86d2fdd20f7f3c82031b60f517dd02336"
    )
    assert declaration["request_binding_sha256"] == (
        "de0060d3299973783267fd02d959b721ea12373eadf5e2497194852c7e5f9044"
    )
    assert declaration["projected_worst_case_reserved_nano_usd"] == 405_556_250
    assert declaration["next_item_id"] == "H026"


def test_recovery_budget_without_continuations_does_not_create_ledger(tmp_path):
    ledger = tmp_path / "absent.sqlite3"

    state = master_budget_state(ledger)

    assert not ledger.exists()
    assert state["ambiguity_reserve_nano_usd"] == 0
    assert state["ambiguity_reservation_count"] == 0
    assert state["effective_tracked_ceiling_nano_usd"] == 7_000_000_000
    assert state["effective_remaining_usd_exact"] == "7.000000000"


def _write_synthetic_reserved_h002(monkeypatch, paths: V3Paths) -> None:
    manifest = {"schema": "original-manifest", "sealed": True}
    intent = {
        "schema": "intent",
        "item_id": "H002",
        "attempt_count": 1,
    }
    outcome = {
        "schema": "outcome",
        "item_id": "H002",
        "provider_attempt_count": 1,
        "status": "technical_failure",
        "delivered_answer_status": "essential_fallback",
        "provider": {"response_id": None},
    }
    values = (
        (
            paths.cohort_manifest,
            manifest,
            "EXPECTED_ORIGINAL_COHORT_MANIFEST_FILE_SHA256",
            "EXPECTED_ORIGINAL_COHORT_MANIFEST_CANONICAL_SHA256",
        ),
        (
            paths.root / "items" / "H002" / "generation-intent.json",
            intent,
            "EXPECTED_H002_GENERATION_INTENT_FILE_SHA256",
            "EXPECTED_H002_GENERATION_INTENT_CANONICAL_SHA256",
        ),
        (
            paths.root / "items" / "H002" / "generation.json",
            outcome,
            "EXPECTED_H002_GENERATION_OUTCOME_FILE_SHA256",
            "EXPECTED_H002_GENERATION_OUTCOME_CANONICAL_SHA256",
        ),
    )
    for path, value, file_constant, canonical_constant in values:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        monkeypatch.setattr(v3, file_constant, hashlib.sha256(path.read_bytes()).hexdigest())
        monkeypatch.setattr(v3, canonical_constant, v3.canonical_json_sha256(value))
    legacy = v3._continuation_payload(recovery_commit=v3.H002_RECOVERY_HARNESS_COMMIT)
    paths.ambiguity_continuation.write_text(
        json.dumps(legacy, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        v3,
        "EXPECTED_H002_CONTINUATION_FILE_SHA256",
        hashlib.sha256(paths.ambiguity_continuation.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        v3,
        "EXPECTED_H002_CONTINUATION_CANONICAL_SHA256",
        v3.canonical_json_sha256(legacy),
    )


def _write_zero_event_generation(paths: V3Paths, item_id: str) -> None:
    root = paths.root / "items" / item_id
    root.mkdir(parents=True, exist_ok=True)
    intent = {"schema": "intent", "item_id": item_id, "attempt_count": 1}
    evidence = v3._turn_operation_evidence(
        paths,
        turn_id=f"{item_id}:generation",
        expected_operation="answer_generation",
    )
    outcome = {
        "schema": "outcome",
        "item_id": item_id,
        "provider_attempt_count": 1,
        "status": "technical_failure",
        "delivered_answer_status": "essential_fallback",
        "provider": {"response_id": None},
        "operation_evidence": evidence,
        "intent_sha256": v3.canonical_json_sha256(intent),
        "dossier": {},
    }
    (root / "generation-intent.json").write_text(
        json.dumps(intent, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "generation.json").write_text(
        json.dumps(outcome, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _synthetic_ambiguity_cohort(monkeypatch, tmp_path):
    paths = _paths(tmp_path / "run")
    _write_synthetic_reserved_h002(monkeypatch, paths)
    paths.instrument_freeze.write_text("{}\n", encoding="utf-8")
    _write_zero_event_generation(paths, "H003")
    cohort = SimpleNamespace(
        paths=paths,
        items=(
            {"id": "H003", "question": "Synthetic H003?"},
            {"id": "H004", "question": "Synthetic H004?"},
        ),
        manifest={"schema": "manifest"},
    )
    monkeypatch.setattr(
        v3,
        "_professional_request_projection",
        lambda *_args, **_kwargs: {
            "projected_worst_case_reserved_nano_usd": 100,
            "projection_method": "costs.projected_provider_operation_cost_nano_usd",
            "provider_kind": "responses",
            "request_binding": {"synthetic": True},
            "request_binding_sha256": v3.canonical_json_sha256({"synthetic": True}),
            "provider_request_shape_sha256": "a" * 64,
            "provider_request_serialized_bytes": 10,
            "provider_request_token_overhead_upper_bound": 20,
            "provider_input_token_upper_bound": 30,
            "max_output_tokens": 40,
        },
    )
    h003_intent = paths.root / "items" / "H003" / "generation-intent.json"
    h003_outcome = paths.root / "items" / "H003" / "generation.json"
    monkeypatch.setattr(
        v3,
        "AMBIGUITY_RECOVERY_DECLARATIONS",
        {
            "H003": {
                "sequence": 1,
                "turn_id": "H003:generation",
                "previous_recovery_harness_commit": v3.H002_RECOVERY_HARNESS_COMMIT,
                "previous_continuation_file": "ambiguity-continuation.json",
                "generation_intent_file_sha256": hashlib.sha256(
                    h003_intent.read_bytes()
                ).hexdigest(),
                "generation_intent_canonical_sha256": v3.canonical_json_sha256(
                    v3.read_json_object(h003_intent)
                ),
                "generation_outcome_file_sha256": hashlib.sha256(
                    h003_outcome.read_bytes()
                ).hexdigest(),
                "generation_outcome_canonical_sha256": v3.canonical_json_sha256(
                    v3.read_json_object(h003_outcome)
                ),
                "previous_continuation_file_sha256": v3.EXPECTED_H002_CONTINUATION_FILE_SHA256,
                "provider_request_shape_sha256": "a" * 64,
                "provider_request_serialized_bytes": 10,
                "provider_request_token_overhead_upper_bound": 20,
                "provider_input_token_upper_bound": 30,
                "max_output_tokens": 40,
                "projected_worst_case_reserved_nano_usd": 100,
                "request_binding_sha256": v3.canonical_json_sha256(
                    {"synthetic": True}
                ),
                "next_item_id": "H004",
                "later_generation_item_ids_sha256": v3.canonical_json_sha256(
                    ["H004"]
                ),
            }
        },
    )
    monkeypatch.setattr(v3, "_git_is_ancestor", lambda *_args, **_kwargs: True)
    return paths, cohort


def test_reconcile_appends_hash_chain_and_preserves_legacy_bytes(monkeypatch, tmp_path):
    paths, cohort = _synthetic_ambiguity_cohort(monkeypatch, tmp_path)
    recovery_commit = "1" * 40
    monkeypatch.setattr(v3, "_git_commit", lambda _base: recovery_commit)
    legacy_bytes = paths.ambiguity_continuation.read_bytes()

    continuation = reconcile_generation_ambiguity(cohort, base_dir=tmp_path)

    assert paths.ambiguity_continuation.read_bytes() == legacy_bytes
    assert continuation["sequence"] == 1
    assert continuation["item_id"] == "H003"
    assert continuation["retried"] is False
    assert continuation["projected_worst_case_reserved_nano_usd"] == 100
    assert continuation["cumulative_reserved_nano_usd"] == 399_575_100
    assert continuation["effective_tracked_ceiling_nano_usd"] == 6_600_424_900
    assert continuation["next_item_id"] == "H004"
    assert continuation["previous_continuation_file_sha256"] == hashlib.sha256(
        legacy_bytes
    ).hexdigest()
    assert (paths.ambiguity_entries / "0001-H003.json").is_file()


def test_reconcile_rejects_any_later_attempt_after_ambiguity(monkeypatch, tmp_path):
    paths, cohort = _synthetic_ambiguity_cohort(monkeypatch, tmp_path)
    monkeypatch.setattr(v3, "_git_commit", lambda _base: "2" * 40)
    h004_intent = paths.root / "items" / "H004" / "generation-intent.json"
    h004_intent.parent.mkdir(parents=True, exist_ok=True)
    h004_intent.write_text("{}\n", encoding="utf-8")

    with pytest.raises(V3EvaluationError, match="attempted after unreconciled H003"):
        reconcile_generation_ambiguity(cohort, base_dir=tmp_path)


def test_reserved_zero_event_exception_is_chain_derived(monkeypatch, tmp_path):
    paths, cohort = _synthetic_ambiguity_cohort(monkeypatch, tmp_path)
    recovery_commit = "3" * 40
    monkeypatch.setattr(v3, "_git_commit", lambda _base: recovery_commit)
    reconcile_generation_ambiguity(cohort, base_dir=tmp_path)

    assert v3._reserved_zero_event_is_valid(paths, item_id="H002") is True
    assert v3._reserved_zero_event_is_valid(paths, item_id="H003") is True
    assert v3._reserved_zero_event_is_valid(paths, item_id="H004") is False


def test_original_manifest_may_differ_only_by_bound_recovery_commit(monkeypatch):
    original = {
        "schema": "manifest",
        "system_under_test": {"harness_commit": v3.ORIGINAL_HARNESS_COMMIT},
        "working_tree": {
            "working_tree": "clean",
            "git_commit": v3.ORIGINAL_HARNESS_COMMIT,
            "dirty_fingerprint": None,
        },
        "sealed_identity": "unchanged",
    }
    current = json.loads(json.dumps(original))
    current["system_under_test"]["harness_commit"] = "4" * 40
    current["working_tree"]["git_commit"] = "4" * 40
    monkeypatch.setattr(
        v3,
        "EXPECTED_ORIGINAL_COHORT_MANIFEST_CANONICAL_SHA256",
        v3.canonical_json_sha256(original),
    )

    v3._validate_original_manifest_identity(original, current)

    current["sealed_identity"] = "changed"
    with pytest.raises(V3EvaluationError, match="changed more than"):
        v3._validate_original_manifest_identity(original, current)


def test_manifest_loader_requires_valid_continuation_when_head_differs(
    monkeypatch,
    tmp_path,
):
    paths = _paths(tmp_path / "run")
    original = {
        "schema": "manifest",
        "system_under_test": {"harness_commit": v3.ORIGINAL_HARNESS_COMMIT},
        "working_tree": {
            "working_tree": "clean",
            "git_commit": v3.ORIGINAL_HARNESS_COMMIT,
            "dirty_fingerprint": None,
        },
    }
    current = json.loads(json.dumps(original))
    current["system_under_test"]["harness_commit"] = "5" * 40
    current["working_tree"]["git_commit"] = "5" * 40
    paths.cohort_manifest.parent.mkdir(parents=True, exist_ok=True)
    paths.cohort_manifest.write_text(
        json.dumps(original, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        v3,
        "EXPECTED_ORIGINAL_COHORT_MANIFEST_CANONICAL_SHA256",
        v3.canonical_json_sha256(original),
    )
    monkeypatch.setattr(v3, "_git_commit", lambda _base: "5" * 40)
    monkeypatch.setattr(
        v3,
        "validate_ambiguity_continuation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            V3EvaluationError("invalid continuation")
        ),
    )

    with pytest.raises(V3EvaluationError, match="invalid continuation"):
        v3._select_cohort_manifest(
            paths=paths,
            built_manifest=current,
            base_dir=tmp_path,
            reconcile_ambiguity=False,
        )


def test_manifest_loader_accepts_original_after_continuation_validation(monkeypatch, tmp_path):
    paths = _paths(tmp_path / "run")
    original = {
        "schema": "manifest",
        "system_under_test": {"harness_commit": v3.ORIGINAL_HARNESS_COMMIT},
        "working_tree": {
            "working_tree": "clean",
            "git_commit": v3.ORIGINAL_HARNESS_COMMIT,
            "dirty_fingerprint": None,
        },
    }
    current = json.loads(json.dumps(original))
    current["system_under_test"]["harness_commit"] = "6" * 40
    current["working_tree"]["git_commit"] = "6" * 40
    paths.cohort_manifest.parent.mkdir(parents=True, exist_ok=True)
    paths.cohort_manifest.write_text(
        json.dumps(original, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        v3,
        "EXPECTED_ORIGINAL_COHORT_MANIFEST_CANONICAL_SHA256",
        v3.canonical_json_sha256(original),
    )
    monkeypatch.setattr(v3, "_git_commit", lambda _base: "6" * 40)
    observed: list[str] = []
    monkeypatch.setattr(
        v3,
        "validate_ambiguity_continuation",
        lambda _paths, *, recovery_commit: observed.append(recovery_commit),
    )

    selected = v3._select_cohort_manifest(
        paths=paths,
        built_manifest=current,
        base_dir=tmp_path,
        reconcile_ambiguity=False,
    )

    assert selected == original
    assert observed == ["6" * 40]
