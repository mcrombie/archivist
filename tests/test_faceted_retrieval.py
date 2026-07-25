from types import SimpleNamespace

import retrieval
from retrieval import retrieve_plan_from_collection
from retrieval_trace_contract import validate_text_free_retrieval_trace


def chunk(chunk_id: str, document: str, text: str, paragraph: int) -> dict:
    return {
        "chunk_id": chunk_id,
        "document": document,
        "chapter_title": document.removesuffix(".md"),
        "paragraph_start": paragraph,
        "paragraph_end": paragraph,
        "text": text,
    }


def semantic_results(chunks: list[dict], distances: list[float] | None = None) -> dict:
    return {
        "ids": [[item["chunk_id"] for item in chunks]],
        "metadatas": [[dict(item) for item in chunks]],
        "distances": [distances or [0.2 + index / 100 for index in range(len(chunks))]],
    }


def facet(
    facet_id: str,
    role: str,
    query: str,
    *,
    document_hints: tuple[str, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        facet_id=facet_id,
        role=role,
        search_query=query,
        document_hints=document_hints,
    )


def plan(*facets: SimpleNamespace, traits: tuple[str, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        schema="archivist.question_plan/1",
        traits=traits,
        facets=facets,
        requirements=(),
        planner_used=True,
        fallback_reason=None,
    )


def assert_text_free(value: object) -> None:
    forbidden = {"text", "question", "prompt", "answer", "raw_query"}

    def walk(item: object) -> None:
        if isinstance(item, dict):
            assert forbidden.isdisjoint(str(key).casefold() for key in item)
            for nested in item.values():
                walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)

    walk(value)


def test_facets_share_one_embedding_batch_and_receive_anchors_before_refill(monkeypatch):
    a1 = chunk("a_001", "a.md", "alpha direct evidence", 1)
    a2 = chunk("a_002", "a.md", "alpha additional evidence", 2)
    b1 = chunk("b_001", "b.md", "beta direct evidence", 1)
    b2 = chunk("b_002", "b.md", "beta additional evidence", 2)
    chunks = [a1, a2, b1, b2]
    embedded: list[list[str]] = []

    monkeypatch.setattr(
        retrieval,
        "embed_queries",
        lambda queries, embedding_client=None: (
            embedded.append(list(queries)) or [[0.0], [1.0]]
        ),
    )

    class Collection:
        configuration = {"hnsw": {"space": "l2"}}

        def count(self):
            return len(chunks)

        def query(self, **request):
            if request["query_embeddings"][0] == [0.0]:
                return semantic_results([a1, a2])
            return semantic_results([b1, b2])

    outcome = retrieve_plan_from_collection(
        plan(
            facet("F0", "original", "alpha"),
            facet("F1", "mechanism", "beta"),
        ),
        Collection(),
        chunks,
        n_results=2,
        embedding_client=object(),
        max_final_sources=3,
    )

    assert embedded == [["alpha", "beta"]]
    assert [item["chunk_id"] for item in outcome.final_chunks[:2]] == [
        "a_001",
        "b_001",
    ]
    assert len(outcome.final_chunks) == 3
    assert outcome.facet_source_numbers["F0"]
    assert outcome.facet_source_numbers["F1"]
    assert_text_free(outcome.trace)
    validate_text_free_retrieval_trace(outcome.trace)


def test_scoped_verification_lane_does_not_force_all_distant_semantic_results(
    monkeypatch,
):
    direct = chunk("direct_001", "direct.md", "alpha evidence", 1)
    distant = chunk("counter_001", "counter.md", "unrelated material", 1)
    chunks = [direct, distant]
    monkeypatch.setattr(
        retrieval,
        "embed_queries",
        lambda *_args, **_kwargs: [[0.0], [1.0]],
    )
    requests: list[dict] = []

    class Collection:
        def count(self):
            return len(chunks)

        def query(self, **request):
            requests.append(request)
            if request["query_embeddings"][0] == [0.0]:
                return semantic_results([direct], [0.2])
            return semantic_results([distant], [1.4])

    outcome = retrieve_plan_from_collection(
        plan(
            facet("F0", "original", "alpha"),
            facet(
                "F1",
                "premise_counter",
                "counter query",
                document_hints=("counter.md",),
            ),
        ),
        Collection(),
        chunks,
        max_final_sources=3,
    )

    assert requests[1]["where"] == {"document": "counter.md"}
    counter_lane = next(lane for lane in outcome.trace["lanes"] if lane["facet_id"] == "F1")
    assert counter_lane["raw_primary_fallback_detected"] is True
    assert counter_lane["semantic_fallback_used"] is False
    assert counter_lane["candidate_chunk_ids"] == []
    assert outcome.facet_source_numbers["F1"] == ()


def test_broad_context_is_reordered_by_corpus_ordinal_after_selection(monkeypatch):
    early = chunk("early_001", "early.md", "early stage", 1)
    late = chunk("late_001", "late.md", "late stage", 1)
    chunks = [early, late]
    monkeypatch.setattr(
        retrieval,
        "embed_queries",
        lambda *_args, **_kwargs: [[0.0], [1.0]],
    )

    class Collection:
        def count(self):
            return len(chunks)

        def query(self, **request):
            if request["query_embeddings"][0] == [0.0]:
                return semantic_results([late])
            return semantic_results([early])

    outcome = retrieve_plan_from_collection(
        plan(
            facet("F0", "original", "late stage"),
            facet("F1", "origin", "early stage"),
            traits=("broad_synthesis",),
        ),
        Collection(),
        chunks,
        max_final_sources=2,
    )

    assert [item["chunk_id"] for item in outcome.final_chunks] == [
        "early_001",
        "late_001",
    ]
    assert 2 in outcome.facet_source_numbers["F0"]
    assert 1 in outcome.facet_source_numbers["F1"]


def test_shared_candidate_is_mapped_to_each_facet_without_duplicate_source(
    monkeypatch,
):
    shared = chunk("shared_001", "shared.md", "shared synthetic evidence", 1)
    chunks = [shared]
    monkeypatch.setattr(
        retrieval,
        "embed_queries",
        lambda *_args, **_kwargs: [[0.0], [1.0]],
    )

    class Collection:
        def count(self):
            return 1

        def query(self, **_request):
            return semantic_results([shared])

    outcome = retrieve_plan_from_collection(
        plan(
            facet("F0", "original", "shared evidence"),
            facet("F1", "mechanism", "shared synthetic"),
        ),
        Collection(),
        chunks,
        max_final_sources=2,
    )

    assert [item["chunk_id"] for item in outcome.final_chunks] == [
        "shared_001"
    ]
    assert outcome.facet_source_numbers == {"F0": (1,), "F1": (1,)}


def test_late_high_value_primary_is_not_displaced_by_an_earlier_neighbor(
    monkeypatch,
):
    first = chunk("a_001", "a.md", "primary anchor evidence", 1)
    neighbor = chunk("a_002", "a.md", "continuity in the next passage", 2)
    second = chunk("b_001", "b.md", "primary second evidence", 1)
    late_high_value = chunk(
        "c_001",
        "c.md",
        "late high-value primary evidence",
        1,
    )
    chunks = [first, neighbor, second, late_high_value]
    monkeypatch.setattr(
        retrieval,
        "embed_queries",
        lambda *_args, **_kwargs: [[0.0]],
    )

    class Collection:
        def count(self):
            return len(chunks)

        def query(self, **_request):
            return semantic_results([first, second, late_high_value])

    outcome = retrieve_plan_from_collection(
        plan(facet("F0", "original", "quasar")),
        Collection(),
        chunks,
        n_results=3,
        max_final_sources=3,
    )

    assert [item["chunk_id"] for item in outcome.final_chunks] == [
        "a_001",
        "b_001",
        "c_001",
    ]
    assert outcome.facet_source_numbers == {"F0": (1, 2, 3)}
    assert [
        item["origin"]
        for item in outcome.trace["selection"]["context"]
    ] == ["primary", "primary", "primary"]


def test_immediate_neighbor_still_fills_a_slot_left_after_all_primaries(
    monkeypatch,
):
    first = chunk("a_001", "a.md", "first primary", 1)
    neighbor = chunk("a_002", "a.md", "continuity passage", 2)
    second = chunk("b_001", "b.md", "second primary", 1)
    chunks = [first, neighbor, second]
    monkeypatch.setattr(
        retrieval,
        "embed_queries",
        lambda *_args, **_kwargs: [[0.0]],
    )

    class Collection:
        def count(self):
            return len(chunks)

        def query(self, **_request):
            return semantic_results([first, second])

    outcome = retrieve_plan_from_collection(
        plan(facet("F0", "original", "quasar")),
        Collection(),
        chunks,
        n_results=2,
        max_final_sources=3,
    )

    assert [item["chunk_id"] for item in outcome.final_chunks] == [
        "a_001",
        "b_001",
        "a_002",
    ]
    assert [
        item["origin"]
        for item in outcome.trace["selection"]["context"]
    ] == ["primary", "primary", "neighbor"]
