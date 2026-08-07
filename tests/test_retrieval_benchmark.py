from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_retrieval_benchmark as benchmark_cli  # noqa: E402

from retrieval_benchmark import (
    K_VALUES,
    LockedGold,
    RetrievalBenchmarkError,
    aggregate_results,
    build_noise_floor,
    evaluate_item,
    request_query_embedding_cache,
    select_noise_subset,
    validate_embedding_cache,
    validate_text_free_artifact,
)


def _gold(items):
    return LockedGold(
        raw={"items": items},
        items=tuple(items),
        gold_set_sha256="a" * 64,
        question_set_sha256="b" * 64,
        candidate_commit="c" * 40,
        candidate_rag_policy="evidence-planned-v26",
        corpus_manifest_sha256="d" * 64,
    )


def _item(
    item_id="H001",
    *,
    question="Which record matters?",
    stratum="focused_biographical",
    behavior="answer",
    relevant=None,
):
    relevant = ["Chapter_001"] if relevant is None else relevant
    return {
        "id": item_id,
        "question": question,
        "stratum": stratum,
        "expected_behavior": behavior,
        "claims": (
            [
                {
                    "claim_id": f"{item_id}.C1",
                    "text": "Private expected prose",
                    "essential": True,
                    "supporting_chunk_ids": ["Chapter_001"],
                }
            ]
            if behavior == "answer"
            else []
        ),
        "relevant_chunk_ids": relevant,
        "must_not_claim": [],
        "notes": "",
    }


def test_query_embedding_cache_uses_one_operation_and_persists_no_question_text():
    items = [_item(), _item("H002", question="What changed?")]
    gold = _gold(items)
    calls = []

    def request(client, **kwargs):
        calls.append((client, kwargs))
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.3, 0.4]),
                SimpleNamespace(index=0, embedding=[0.1, 0.2]),
            ],
            usage=SimpleNamespace(prompt_tokens=11, total_tokens=11),
        )

    cache = request_query_embedding_cache(
        gold,
        embedding_client="client",
        request=request,
    )

    assert len(calls) == 1
    assert calls[0][1]["input"] == [item["question"] for item in items]
    assert calls[0][1]["model"] == "text-embedding-3-small"
    assert cache["operation_count"] == 1
    assert cache["automatic_retries"] == 0
    assert all("question" not in entry for entry in cache["items"])
    assert validate_embedding_cache(cache, gold) == {
        "H001": [0.1, 0.2],
        "H002": [0.3, 0.4],
    }


def test_embedding_cache_rejects_question_binding_change():
    gold = _gold([_item()])
    cache = request_query_embedding_cache(
        gold,
        embedding_client="client",
        request=lambda *_args, **_kwargs: SimpleNamespace(
            data=[SimpleNamespace(index=0, embedding=[0.1])],
            usage=SimpleNamespace(prompt_tokens=1, total_tokens=1),
        ),
    )
    changed = _gold([_item(question="A changed question")])
    with pytest.raises(RetrievalBenchmarkError, match="question binding"):
        validate_embedding_cache(cache, changed)


def test_embedding_response_rejects_duplicate_input_indices():
    gold = _gold([_item(), _item("H002", question="What changed?")])
    with pytest.raises(RetrievalBenchmarkError, match="duplicate input indices"):
        request_query_embedding_cache(
            gold,
            embedding_client="client",
            request=lambda *_args, **_kwargs: SimpleNamespace(
                data=[
                    SimpleNamespace(index=0, embedding=[0.1]),
                    SimpleNamespace(index=0, embedding=[0.2]),
                ],
                usage=SimpleNamespace(prompt_tokens=1, total_tokens=1),
            ),
        )


class _Collection:
    def __init__(self, chunks):
        self.chunks = chunks
        self.query_count = 0

    def count(self):
        return len(self.chunks)

    def query(self, **kwargs):
        self.query_count += 1
        assert kwargs["query_embeddings"] == [[0.5, 0.25]]
        return {
            "ids": [[chunk["chunk_id"] for chunk in self.chunks]],
            "metadatas": [[dict(chunk) for chunk in self.chunks]],
            "distances": [[0.2, 0.3, 0.4]],
        }


def test_item_evaluation_reuses_one_vector_query_for_both_arms_and_every_k():
    chunks = [
        {
            "chunk_id": "Chapter_001",
            "document": "Chapter.md",
            "chapter_title": "Chapter",
            "paragraph_start": 1,
            "paragraph_end": 2,
            "text": "A general account of the record.",
        },
        {
            "chunk_id": "Chapter_002",
            "document": "Chapter.md",
            "chapter_title": "Chapter",
            "paragraph_start": 3,
            "paragraph_end": 4,
            "text": "A second general passage.",
        },
        {
            "chunk_id": "Chapter_003",
            "document": "Chapter.md",
            "chapter_title": "Chapter",
            "paragraph_start": 5,
            "paragraph_end": 6,
            "text": "The distinctive lantern compact changed the institution.",
        },
    ]
    item = _item(
        question="What did the distinctive lantern compact change?",
        relevant=["Chapter_003"],
    )
    item["claims"][0]["supporting_chunk_ids"] = ["Chapter_003"]
    collection = _Collection(chunks)

    result = evaluate_item(
        item,
        [0.5, 0.25],
        collection=collection,
        chunks=chunks,
        corpus_trace={"collection_count": 3},
    )

    assert collection.query_count == 1
    assert set(result["arms"]) == {"dense", "hybrid"}
    for arm in result["arms"].values():
        assert set(arm["primary_ids_by_k"]) == {str(k) for k in K_VALUES}
        assert "context_metrics" in arm
    assert result["arms"]["dense"]["metrics_by_k"]["1"]["recall"] == 0.0
    assert result["arms"]["hybrid"]["metrics_by_k"]["3"]["recall"] == 1.0
    validate_text_free_artifact(result)


def _item_result(item_id, stratum, recall, *, fallback=False):
    metric = {
        "recall": recall,
        "hit": None if recall is None else recall > 0,
        "relevant_count": 0 if recall is None else 1,
        "retrieved_relevant_count": 0 if not recall else 1,
        "essential_coverage": recall,
        "essential_claim_count": 0 if recall is None else 1,
        "covered_essential_claim_count": 0 if not recall else 1,
    }
    arm = {
        "metrics_by_k": {str(k): dict(metric) for k in K_VALUES},
        "context_metrics": dict(metric),
        "fallback_used": fallback,
        "expansion_displacement": {
            "distance_filtering": 0,
            "document_filtering": 0,
            "truncation": 0,
        },
    }
    return {
        "id": item_id,
        "question_sha256": "e" * 64,
        "stratum": stratum,
        "expected_behavior": "abstain" if recall is None else "answer",
        "arms": {"dense": dict(arm), "hybrid": dict(arm)},
    }


def test_aggregate_excludes_empty_relevance_from_recall_but_counts_fallback():
    summary = aggregate_results(
        [
            _item_result("H001", "focused_biographical", 1.0),
            _item_result("H002", "out_of_corpus", None, fallback=True),
        ]
    )
    dense = summary["aggregate"]["arms"]["dense"]
    assert dense["recall_at_k"]["5"] == 1.0
    assert dense["primary_metric_denominators"]["5"] == 1
    assert dense["fallback_rate"] == 0.5
    assert dense["fallback_denominator"] == 2
    assert (
        summary["by_stratum"]["out_of_corpus"]["arms"]["dense"]["recall_at_k"]["5"]
        is None
    )


def test_noise_subset_is_fixed_stratified_and_noise_spread_is_measured():
    counts = {
        "focused_biographical": 2,
        "focused_analytical": 2,
        "conceptual": 1,
        "broad_thematic": 2,
        "out_of_corpus": 2,
        "adversarial_premise": 1,
    }
    items = []
    number = 1
    for stratum, count in counts.items():
        for _ in range(count):
            behavior = "abstain" if stratum == "out_of_corpus" else "answer"
            relevant = [] if behavior == "abstain" else ["Chapter_001"]
            items.append(
                _item(
                    f"H{number:03}",
                    stratum=stratum,
                    behavior=behavior,
                    relevant=relevant,
                )
            )
            number += 1

    subset = select_noise_subset(items)
    assert len(subset) == 10
    results = [
        _item_result(
            item["id"],
            item["stratum"],
            None if item["expected_behavior"] == "abstain" else 1.0,
        )
        for item in items
    ]
    noise = build_noise_floor([results, results, results, results, results])
    assert noise["repetitions"] == 5
    assert noise["subset_size"] == 10
    assert set(noise["by_stratum"]) == set(counts)
    assert (
        noise["aggregate"]["metrics"][
            "comparison.macro_recall_at_5.hybrid_minus_dense"
        ]["standard_deviation"]
        == 0.0
    )
    assert all(
        value["standard_deviation"] == 0.0
        for value in noise["aggregate"]["metrics"].values()
    )


def test_noise_floor_rejects_changed_repetition_membership():
    first = [_item_result("H001", "focused_biographical", 1.0)]
    changed = [_item_result("H002", "focused_biographical", 1.0)]
    with pytest.raises(RetrievalBenchmarkError, match="same fixed item IDs"):
        build_noise_floor([first, first, changed, first, first])


def test_text_free_artifact_rejects_private_text_fields():
    with pytest.raises(RetrievalBenchmarkError, match="forbidden"):
        validate_text_free_artifact({"items": [{"question": "private"}]})


def test_cli_rejects_nonfinite_cost_ceiling_before_client_creation(tmp_path):
    args = SimpleNamespace(
        embedding_cache=tmp_path / "missing-cache.json",
        authorize_openai_query_embeddings=True,
        max_cost_usd=float("nan"),
    )
    with pytest.raises(RetrievalBenchmarkError, match="finite positive"):
        benchmark_cli._create_cache(args, _gold([_item()]))


def test_cli_run_rejects_existing_output_before_embedding_request(
    tmp_path,
    monkeypatch,
):
    output = tmp_path / "existing-result.json"
    output.write_text("{}", encoding="utf-8")
    cache_called = False

    def unexpected_cache(*_args, **_kwargs):
        nonlocal cache_called
        cache_called = True
        raise AssertionError("embedding cache creation must not be reached")

    monkeypatch.setattr(benchmark_cli, "_validated_gold", lambda _args: object())
    monkeypatch.setattr(benchmark_cli, "_require_clean_candidate", lambda _gold: {})
    monkeypatch.setattr(
        benchmark_cli,
        "_collection_and_corpus",
        lambda _args, _gold: (object(), [], {}, {}),
    )
    monkeypatch.setattr(benchmark_cli, "_create_cache", unexpected_cache)

    assert benchmark_cli.main(["run", "--output", str(output)]) == 1
    assert cache_called is False
