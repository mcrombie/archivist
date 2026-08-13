from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import retrieval

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
