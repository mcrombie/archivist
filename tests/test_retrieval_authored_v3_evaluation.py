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


def test_h026_recovery_declaration_is_externally_bound():
    declaration = v3.AMBIGUITY_RECOVERY_DECLARATIONS["H026"]

    assert declaration["sequence"] == 4
    assert declaration["previous_recovery_harness_commit"] == (
        "7d8b50904d05e8bcd7b33f11ef1d2cf6943d79df"
    )
    assert declaration["previous_continuation_file_sha256"] == (
        "65a4d3b1dca437af280a4033826487a26882a36f96a3ff2da4130f77bd0eafda"
    )
    assert declaration["generation_intent_file_sha256"] == (
        "d96c7c10b4b54d90732a73d9d4907a3a93e28450c41a0d29c84f6159bb05f7c4"
    )
    assert declaration["generation_outcome_file_sha256"] == (
        "f14d8e0c6ca0844faf9a58271a48a5f479ed6ed9ad55601771b9cfb206189f47"
    )
    assert declaration["provider_request_shape_sha256"] == (
        "10a9d760d090a93d10b32ea906f2ed09f04e55d2fae30b46a1d6480858875aed"
    )
    assert declaration["request_binding_sha256"] == (
        "d86b1a5cd99c0f34b5962109b306aa110417ea7060460f5f9b913b890bf7159f"
    )
    assert declaration["projected_worst_case_reserved_nano_usd"] == 405_881_250
    assert declaration["next_item_id"] == "H027"


def test_h027_recovery_declaration_is_externally_bound():
    declaration = v3.AMBIGUITY_RECOVERY_DECLARATIONS["H027"]

    assert declaration["sequence"] == 5
    assert declaration["previous_recovery_harness_commit"] == (
        "b1a79f79b64b341be140a5d15fbbfe510099417b"
    )
    assert declaration["previous_continuation_file_sha256"] == (
        "f38ce09650f6f80efb62970f474887d422324c727e58bd9238cd15233752bfe1"
    )
    assert declaration["generation_intent_file_sha256"] == (
        "be28db6792991a1991802b77b77e3c10ea67562e5757d4db28c875395129f4db"
    )
    assert declaration["generation_outcome_file_sha256"] == (
        "c2118e787f48e6ab69bbdf7154bb272a8cddf56ff7f8b054f6390f68c3547cbf"
    )
    assert declaration["provider_request_shape_sha256"] == (
        "73c163241c8fbea48666bdad4176dcd054bdf69341db484ea7c18be3a12d57ad"
    )
    assert declaration["request_binding_sha256"] == (
        "154a73ccfff401c201b84fb5bfc169fd8b1ef571f1652ca0806fb818bc55d9b7"
    )
    assert declaration["projected_worst_case_reserved_nano_usd"] == 390_450_000
    assert declaration["next_item_id"] == "H028"


def test_h031_recovery_declaration_is_externally_bound():
    declaration = v3.AMBIGUITY_RECOVERY_DECLARATIONS["H031"]

    assert declaration["sequence"] == 6
    assert declaration["previous_recovery_harness_commit"] == (
        "71ba7984757b243c569df5a34b0ab1f549cab464"
    )
    assert declaration["previous_continuation_file_sha256"] == (
        "ec044853da4f1d1cc9f61af860b74fde17e65ca9ac00008239199499477faa7f"
    )
    assert declaration["generation_intent_file_sha256"] == (
        "7f1c039de5f989778680f0d8af4b2c76fabf490a0eaeaaeafbbe5cc915637ddb"
    )
    assert declaration["generation_outcome_file_sha256"] == (
        "9246559e008624984eacacbd607fc4c904e6046f3d2224cb4190e1a80f702366"
    )
    assert declaration["provider_request_shape_sha256"] == (
        "e98380bdca0e025b294cbd07b251701a041293b6e815e8d8742eeabcb17b05d6"
    )
    assert declaration["request_binding_sha256"] == (
        "48a22a71fe118b18aa0aae28b2255ef769865ea00180debf7d309addb79b9add"
    )
    assert declaration["projected_worst_case_reserved_nano_usd"] == 406_400_000
    assert declaration["next_item_id"] == "H032"


def test_h001_decomposition_recovery_declaration_is_externally_bound():
    declaration = v3.AMBIGUITY_RECOVERY_DECLARATIONS["H001:decomposition"]

    assert declaration["sequence"] == 7
    assert declaration["phase"] == "decomposition"
    assert declaration["operation"] == "eval_claim_decomposition_v2"
    assert declaration["previous_recovery_harness_commit"] == (
        "3f4cac4bb3a95e0aefcdbde9d6842ec45c96e1f1"
    )
    assert declaration["previous_continuation_file_sha256"] == (
        "cc33f875abe1f1fbcbacd21e3bd39921875693467ea045d6bf454df27edcf863"
    )
    assert declaration["intent_file_sha256"] == (
        "6b42361ffbf2cc548873d517ef8ba0363a8efef4cece0897cba575a18a1f33be"
    )
    assert declaration["outcome_file_sha256"] == (
        "7d1fdc89e7c0b7b6c24f1dc14b89b8db9f8e09b67624ad2405487c03cf56b2a9"
    )
    assert declaration["provider_request_shape_sha256"] == (
        "cf42cd51897a3e9602d94505bb423dbe3f883c00e7449506141e83b064c63e64"
    )
    assert declaration["request_binding_sha256"] == (
        "b958c251e09725081c5e590b58eeadbbfd9788d94a7d44a6f2046ffbdb579a97"
    )
    assert declaration["projected_worst_case_reserved_nano_usd"] == 175_984_375
    assert declaration["next_turn_id"] == "H002:decomposition"


def test_h012_decomposition_recovery_declaration_is_externally_bound():
    declaration = v3.AMBIGUITY_RECOVERY_DECLARATIONS["H012:decomposition"]

    assert declaration["sequence"] == 8
    assert declaration["phase"] == "decomposition"
    assert declaration["operation"] == "eval_claim_decomposition_v2"
    assert declaration["previous_recovery_harness_commit"] == (
        "bc2111b0b336764457b9539c402389142741e70b"
    )
    assert declaration["previous_continuation_file_sha256"] == (
        "0a63acd50508d4baef512fa2a4ac7db6e80952ece01e004333b40407026a7be5"
    )
    assert declaration["intent_file_sha256"] == (
        "d69d2739c9a24bd64cec53092e0e1b6351c86273d27e50314dcc0eae2dc46081"
    )
    assert declaration["outcome_file_sha256"] == (
        "40ae8b368da730e692334edf9a258832138e329a51256d1871113cd2b89d157b"
    )
    assert declaration["provider_request_shape_sha256"] == (
        "566fced7a1438b2d2e85ab2171f695e8571950d9e3ee37062db130250234f8aa"
    )
    assert declaration["request_binding_sha256"] == (
        "da423c679c205a10046a640d97399754e1a541e93aca1d95977c8d220e369d7a"
    )
    assert declaration["projected_worst_case_reserved_nano_usd"] == 180_178_125
    assert declaration["next_turn_id"] == "H013:decomposition"


def test_h013_decomposition_recovery_declaration_is_externally_bound():
    declaration = v3.AMBIGUITY_RECOVERY_DECLARATIONS["H013:decomposition"]

    assert declaration["sequence"] == 9
    assert declaration["phase"] == "decomposition"
    assert declaration["operation"] == "eval_claim_decomposition_v2"
    assert declaration["previous_recovery_harness_commit"] == (
        "a9d53e7e83586b6b6bc79e5702662ec4163dc98e"
    )
    assert declaration["previous_continuation_file_sha256"] == (
        "53e98db329dbe5eb2bcadbdcc52ccb0b5290768e6be04a99b0f94ed3ec56d210"
    )
    assert declaration["intent_file_sha256"] == (
        "2b3307ce477ac994e5910621d541a56a837c007a0b0107fb01eab63714b10c2a"
    )
    assert declaration["outcome_file_sha256"] == (
        "8ef5f44565f37468ca63146b415926405da5b823b211d7ec757391ad96ba8920"
    )
    assert declaration["provider_request_shape_sha256"] == (
        "3080f88bd82f4598eca77b66b645cbeaa0be9ae424fd157922bd2fa7ba02fa38"
    )
    assert declaration["request_binding_sha256"] == (
        "4a859757dfdc9d8d8343427be9ab5ce70f2d1a77dd1d6acaa12f1fa4f00610a1"
    )
    assert declaration["projected_worst_case_reserved_nano_usd"] == 179_390_625
    assert declaration["next_turn_id"] == "H014:decomposition"


def test_h014_decomposition_recovery_declaration_is_externally_bound():
    declaration = v3.AMBIGUITY_RECOVERY_DECLARATIONS["H014:decomposition"]

    assert declaration["sequence"] == 10
    assert declaration["phase"] == "decomposition"
    assert declaration["operation"] == "eval_claim_decomposition_v2"
    assert declaration["previous_recovery_harness_commit"] == (
        "e5f40d296fb58925d586bc54e8bd19d1e42725db"
    )
    assert declaration["previous_continuation_file_sha256"] == (
        "3b102a33b6de74e13a614ae782e88a41a5054ca80230bc34971bab13355f4656"
    )
    assert declaration["intent_file_sha256"] == (
        "35e053871fa024940b023a95ac348915aeff6579816f8bb6d4b1beb8a1b075eb"
    )
    assert declaration["outcome_file_sha256"] == (
        "008c18e4248298a3b1156331aabcc3e1330f4b10e0f6b8572fed71e6ff7c71b0"
    )
    assert declaration["provider_request_shape_sha256"] == (
        "8696b68731d37e45c7cf3fe70fe847a7958ec73d814224508e7d6e76aa7749cd"
    )
    assert declaration["request_binding_sha256"] == (
        "8957a11a89e812221c9413cb36a1a3f2d64c9393072fdffcffdeb9c0d34f69d0"
    )
    assert declaration["projected_worst_case_reserved_nano_usd"] == 176_209_375
    assert declaration["next_turn_id"] == "H015:decomposition"


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
        "attempt_count": 1,
        "provider_attempt_count": 1,
        "status": "technical_failure",
        "delivered_answer_status": "essential_fallback",
        "provider": {"response_id": None},
        "operation_evidence": evidence,
        "intent_sha256": v3.canonical_json_sha256(intent),
        "dossier": {},
        "automatic_retries": 0,
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
    monkeypatch.setattr(
        v3,
        "_phase_expected_intent",
        lambda *_args, item, **_kwargs: v3.read_json_object(
            paths.root / "items" / str(item["id"]) / "generation-intent.json"
        ),
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


def test_legacy_generation_entry_does_not_require_new_phase_boundary_field(
    monkeypatch,
    tmp_path,
):
    paths, cohort = _synthetic_ambiguity_cohort(monkeypatch, tmp_path)
    monkeypatch.setattr(v3, "_git_commit", lambda _base: "1" * 40)
    reconcile_generation_ambiguity(cohort, base_dir=tmp_path)
    entry_path = paths.ambiguity_entries / "0001-H003.json"
    entry = v3.read_json_object(entry_path)
    entry.pop("next_item_unattempted_at_reconciliation", None)
    entry_path.write_text(
        json.dumps(entry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    state = v3._ambiguity_chain_state(paths)

    assert state["reservations"][-1]["turn_id"] == "H003:generation"


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


def test_reserved_zero_event_terminal_closure_uses_descendant_validation_only(
    monkeypatch,
    tmp_path,
):
    paths = _paths(tmp_path / "run")
    observed: list[tuple[Path, str]] = []
    monkeypatch.setattr(
        v3,
        "validate_terminal_closure_continuation",
        lambda _paths, *, base_dir, closure_commit: observed.append(
            (base_dir, closure_commit)
        ),
    )
    monkeypatch.setattr(
        v3,
        "validate_ambiguity_continuation",
        lambda *_args, **_kwargs: pytest.fail("terminal closure used exact binding"),
    )
    monkeypatch.setattr(
        v3,
        "_ambiguity_chain_state",
        lambda _paths: {"reservations": [{"turn_id": "H014:decomposition"}]},
    )

    assert v3._reserved_zero_event_is_valid(
        paths,
        item_id="H014",
        phase="decomposition",
        terminal_closure_base_dir=tmp_path,
        terminal_closure_commit="c" * 40,
    )
    assert observed == [(tmp_path, "c" * 40)]


def test_decomposition_resume_skips_only_declared_zero_event(monkeypatch, tmp_path):
    paths = _paths(tmp_path / "run")
    item_id = "H001"
    intent = {
        "item_id": item_id,
        "answer_sha256": "a" * 64,
        "instrument": {"operation": "eval_claim_decomposition_v2"},
    }
    evidence = v3._turn_operation_evidence(
        paths,
        turn_id="H001:decomposition",
        expected_operation="eval_claim_decomposition_v2",
    )
    outcome = {
        "schema": v3.V3_DECOMPOSITION_OUTCOME_SCHEMA,
        "item_id": item_id,
        "status": "technical_failure",
        "answer_sha256": intent["answer_sha256"],
        "intent_sha256": v3.canonical_json_sha256(intent),
        "provider_attempt_count": 1,
        "provider": None,
        "operation_evidence": evidence,
        "attempt_count": 1,
        "automatic_retries": 0,
    }
    intent_path, outcome_path = v3._decomposition_paths(
        paths,
        item_id,
        development=False,
    )
    intent_path.parent.mkdir(parents=True, exist_ok=True)
    intent_path.write_text(json.dumps(intent), encoding="utf-8")
    outcome_path.write_text(json.dumps(outcome), encoding="utf-8")
    monkeypatch.setattr(
        v3,
        "_reserved_zero_event_is_valid",
        lambda *_args, **kwargs: kwargs.get("phase") == "decomposition",
    )

    validated = v3._validate_decomposition_pair(
        paths,
        item_id=item_id,
        intent=intent,
        development=False,
    )

    assert validated["status"] == "technical_failure"
    monkeypatch.setattr(v3, "_reserved_zero_event_is_valid", lambda *_args, **_kwargs: False)
    with pytest.raises(V3EvaluationError, match="billing state is ambiguous"):
        v3._validate_decomposition_pair(
            paths,
            item_id=item_id,
            intent=intent,
            development=False,
        )


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


def _write_diagnostic_inventory(paths: V3Paths) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    item_ids = [
        f"H{ordinal:03d}"
        for ordinal in range(1, 39)
        if ordinal != 20
    ]
    paths.cohort_manifest.write_text(
        json.dumps({"items": [{"id": item_id} for item_id in item_ids]}) + "\n",
        encoding="utf-8",
    )
    paths.instrument_freeze.write_text("{}\n", encoding="utf-8")
    paths.ledger.write_bytes(b"sealed-ledger")
    paths.ambiguity_continuation.write_text("{}\n", encoding="utf-8")
    for item_id in item_ids:
        root = paths.root / "items" / item_id
        root.mkdir(parents=True, exist_ok=True)
        (root / "generation-intent.json").write_text("{}\n", encoding="utf-8")
        (root / "generation.json").write_text("{}\n", encoding="utf-8")
    for ordinal in range(1, 11):
        root = paths.root / "development" / f"G{ordinal:03d}"
        root.mkdir(parents=True, exist_ok=True)
        (root / "decomposition-intent.json").write_text("{}\n", encoding="utf-8")
        (root / "decomposition.json").write_text("{}\n", encoding="utf-8")
    for ordinal in range(1, 15):
        root = paths.root / "items" / f"H{ordinal:03d}"
        (root / "decomposition-intent.json").write_text("{}\n", encoding="utf-8")
        (root / "decomposition.json").write_text("{}\n", encoding="utf-8")


def test_close_diagnostic_cohort_is_provider_free_idempotent_and_terminal(
    monkeypatch,
    tmp_path,
):
    paths = _paths(tmp_path / "run")
    _write_diagnostic_inventory(paths)
    cohort = SimpleNamespace(paths=paths)
    summary = {
        "schema": v3.V3_DIAGNOSTIC_PARTIAL_SUMMARY_SCHEMA,
        "evaluation_id": v3.EVALUATION_ID,
        "terminal_status": "closed_incomplete_timeout_diagnostic",
        "privacy": {
            "contains_questions": False,
            "contains_answers": False,
            "contains_manuscript_text": False,
            "contains_provider_response_metadata": False,
        },
    }
    monkeypatch.setattr(
        v3,
        "build_diagnostic_partial_summary",
        lambda *_args, **_kwargs: summary,
    )
    monkeypatch.setattr(v3, "_git_commit", lambda _base: "7" * 40)

    first = v3.close_diagnostic_cohort(cohort, base_dir=tmp_path)
    closure_bytes = paths.diagnostic_closure.read_bytes()
    second = v3.close_diagnostic_cohort(cohort, base_dir=tmp_path)

    assert first == second == summary
    assert paths.diagnostic_closure.read_bytes() == closure_bytes
    closure = v3.validate_diagnostic_closure(paths)
    assert closure["provider_operations_during_closure"] == 0
    assert closure["retries_during_closure"] == 0
    assert closure["resume_turn_id"] is None
    assert closure["paid_phases_permanently_disabled"] is True
    with pytest.raises(V3EvaluationError, match="closed as an incomplete diagnostic"):
        with v3.master_usage_scope(paths):
            pytest.fail("closed cohort opened a usage ledger scope")


def test_diagnostic_closure_detects_mutation_of_sealed_artifact(monkeypatch, tmp_path):
    paths = _paths(tmp_path / "run")
    _write_diagnostic_inventory(paths)
    cohort = SimpleNamespace(paths=paths)
    monkeypatch.setattr(
        v3,
        "build_diagnostic_partial_summary",
        lambda *_args, **_kwargs: {
            "schema": v3.V3_DIAGNOSTIC_PARTIAL_SUMMARY_SCHEMA,
            "evaluation_id": v3.EVALUATION_ID,
        },
    )
    monkeypatch.setattr(v3, "_git_commit", lambda _base: "8" * 40)
    v3.close_diagnostic_cohort(cohort, base_dir=tmp_path)
    generation = paths.root / "items" / "H038" / "generation.json"
    generation.write_text('{"changed":true}\n', encoding="utf-8")

    with pytest.raises(V3EvaluationError, match="diagnostic closure identity changed"):
        v3.validate_diagnostic_closure(paths)


def test_diagnostic_inventory_uses_sealed_noncontiguous_cohort_ids(tmp_path):
    paths = _paths(tmp_path / "run")
    _write_diagnostic_inventory(paths)

    inventory = v3._diagnostic_artifact_inventory(paths)

    assert inventory["generation"]["item_count"] == 37
    assert "H038" in inventory["generation"]["item_ids"]
    assert "H020" not in inventory["generation"]["item_ids"]


def test_diagnostic_terminal_state_requires_reconciled_h014(monkeypatch, tmp_path):
    paths = _paths(tmp_path / "run")
    cohort = SimpleNamespace(paths=paths)
    observed_generation_context: list[dict[str, object]] = []
    monkeypatch.setattr(
        v3,
        "require_complete_generation",
        lambda _cohort, **kwargs: observed_generation_context.append(kwargs),
    )
    monkeypatch.setattr(v3, "require_instrument_freeze", lambda _paths: None)
    monkeypatch.setattr(v3, "_git_commit", lambda _base: "9" * 40)
    monkeypatch.setattr(
        v3,
        "_ambiguity_chain_state",
        lambda _paths: {
            "reservations": [{"turn_id": "H013:decomposition"}],
            "cumulative_reserved_nano_usd": 3_334_184_375,
            "tail_recovery_harness_commit": "9" * 40,
        },
    )

    with pytest.raises(V3EvaluationError, match="requires the sealed H014"):
        v3._validate_diagnostic_terminal_state(cohort, base_dir=tmp_path)
    assert observed_generation_context == [
        {
            "terminal_closure_base_dir": tmp_path,
            "terminal_closure_commit": "9" * 40,
        }
    ]


def _manifest_pair_for_continuation_test(monkeypatch, paths: V3Paths):
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
    current["system_under_test"]["harness_commit"] = "c" * 40
    current["working_tree"]["git_commit"] = "c" * 40
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
    return original, current


def test_terminal_closure_accepts_clean_descendant_of_ambiguity_tail(
    monkeypatch,
    tmp_path,
):
    paths = _paths(tmp_path / "run")
    original, current = _manifest_pair_for_continuation_test(monkeypatch, paths)
    tail = "a" * 40
    closing = "c" * 40
    monkeypatch.setattr(v3, "_git_commit", lambda _base: closing)
    monkeypatch.setattr(
        v3,
        "_ambiguity_chain_state",
        lambda _paths: {
            "reservations": [{"turn_id": "H014:decomposition"}],
            "tail_recovery_harness_commit": tail,
        },
    )
    observed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        v3,
        "_git_is_ancestor",
        lambda _base, *, ancestor, descendant: (
            observed.append((ancestor, descendant)) or True
        ),
    )

    selected = v3._select_cohort_manifest(
        paths=paths,
        built_manifest=current,
        base_dir=tmp_path,
        reconcile_ambiguity=False,
        terminal_closure=True,
    )

    assert selected == original
    assert observed == [(tail, closing)]


def test_terminal_closure_rejects_non_descendant_harness(monkeypatch, tmp_path):
    paths = _paths(tmp_path / "run")
    _original, current = _manifest_pair_for_continuation_test(monkeypatch, paths)
    monkeypatch.setattr(v3, "_git_commit", lambda _base: "c" * 40)
    monkeypatch.setattr(
        v3,
        "_ambiguity_chain_state",
        lambda _paths: {
            "reservations": [{"turn_id": "H014:decomposition"}],
            "tail_recovery_harness_commit": "a" * 40,
        },
    )
    monkeypatch.setattr(v3, "_git_is_ancestor", lambda *_args, **_kwargs: False)

    with pytest.raises(V3EvaluationError, match="not a descendant"):
        v3._select_cohort_manifest(
            paths=paths,
            built_manifest=current,
            base_dir=tmp_path,
            reconcile_ambiguity=False,
            terminal_closure=True,
        )


def test_normal_route_keeps_exact_ambiguity_tail_binding(monkeypatch, tmp_path):
    paths = _paths(tmp_path / "run")
    _original, current = _manifest_pair_for_continuation_test(monkeypatch, paths)
    monkeypatch.setattr(v3, "_git_commit", lambda _base: "c" * 40)
    monkeypatch.setattr(
        v3,
        "_ambiguity_chain_state",
        lambda _paths: {
            "reservations": [{"turn_id": "H014:decomposition"}],
            "tail_recovery_harness_commit": "a" * 40,
        },
    )
    monkeypatch.setattr(
        v3,
        "_git_is_ancestor",
        lambda *_args, **_kwargs: pytest.fail(
            "normal route used terminal descendant allowance"
        ),
    )

    with pytest.raises(V3EvaluationError, match="not bound to the current harness"):
        v3._select_cohort_manifest(
            paths=paths,
            built_manifest=current,
            base_dir=tmp_path,
            reconcile_ambiguity=False,
        )


def test_terminal_closure_preparation_cannot_disable_clean_tree_requirement(tmp_path):
    paths = _paths(tmp_path / "run")

    with pytest.raises(V3EvaluationError, match="requires a clean working tree"):
        v3.prepare_v3_cohort(
            base_dir=tmp_path,
            paths=paths,
            require_clean=False,
            terminal_closure=True,
        )
