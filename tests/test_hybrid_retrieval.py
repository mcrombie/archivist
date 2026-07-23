import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

import retrieval
from retrieval import (
    FileTraceSink,
    build_context,
    build_hybrid_results,
    finalize_context_chunks,
    lexical_candidates,
    plan_context_chunks,
    retrieve_from_collection,
    retrieve_semantic_from_collection,
)


def chunk(
    chunk_id: str,
    document: str,
    text: str,
    *,
    paragraph_start: int = 1,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "document": document,
        "chapter_title": document.removesuffix(".md"),
        "paragraph_start": paragraph_start,
        "paragraph_end": paragraph_start + 2,
        "text": text,
    }


def semantic_results(
    ranked_chunks: list[dict],
    distances: list[float] | None = None,
) -> dict:
    distances = distances or [
        round(0.1 + index / 100, 3)
        for index in range(len(ranked_chunks))
    ]
    return {
        "ids": [[item["chunk_id"] for item in ranked_chunks]],
        "metadatas": [[dict(item) for item in ranked_chunks]],
        "distances": [distances],
    }


def assert_trace_is_text_free(value: object) -> None:
    sensitive_keys = {"text", "raw_query", "question", "prompt", "manuscript_text"}

    def walk(item: object) -> None:
        if isinstance(item, dict):
            assert sensitive_keys.isdisjoint(
                str(key).casefold() for key in item
            )
            for nested in item.values():
                walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)

    walk(value)


def test_full_name_lexical_signal_can_promote_a_candidate_without_mutating_raw_top_k():
    corridor = chunk(
        "01_One_001",
        "one.md",
        "The Marlowe Technology Corridor became a regional nickname.",
    )
    unrelated = chunk(
        "02_Two_001",
        "two.md",
        "The assembly debated harbor duties.",
    )
    person = chunk(
        "03_Three_001",
        "three.md",
        "Ada Marlowe organized the expedition and later wrote its account.",
    )
    results = build_hybrid_results(
        "Who was Ada Marlowe?",
        semantic_results([corridor, unrelated, person]),
        [corridor, unrelated, person],
        n_results=2,
    )

    assert results["ids"][0] == ["01_One_001", "02_Two_001"]
    assert [item["chunk_id"] for item in results["metadatas"][0]] == [
        "01_One_001",
        "02_Two_001",
    ]
    assert results["distances"][0] == [0.1, 0.11]
    assert results["hybrid"]["primary_chunk_ids"] == [
        "01_One_001",
        "03_Three_001",
    ]
    assert results["hybrid"]["trace"]["candidates"]["semantic"][0]["rank"] == 1
    assert results["hybrid"]["trace"]["candidates"]["lexical"][0]["chunk_id"] == (
        "03_Three_001"
    )


def test_semantic_only_query_preserves_semantic_order():
    chunks = [
        chunk("01_One_001", "one.md", "harbor assembly"),
        chunk("02_Two_001", "two.md", "frontier settlement"),
        chunk("03_Three_001", "three.md", "constitutional debate"),
    ]
    results = build_hybrid_results(
        "quasar",
        semantic_results(chunks),
        chunks,
        n_results=3,
    )

    assert results["hybrid"]["primary_chunk_ids"] == [
        "01_One_001",
        "02_Two_001",
        "03_Three_001",
    ]
    assert results["hybrid"]["trace"]["candidates"]["lexical"] == []


def test_distance_filter_and_fallback_remain_visible_while_lexical_can_rescue():
    distant_exact = chunk(
        "01_One_001",
        "one.md",
        "Ada Marlowe organized the expedition.",
    )
    near_partial = chunk(
        "02_Two_001",
        "two.md",
        "Marlowe was also the name of a road.",
    )
    results = build_hybrid_results(
        "Ada Marlowe",
        semantic_results([near_partial, distant_exact], [0.2, 1.4]),
        [near_partial, distant_exact],
        n_results=2,
    )

    assert "01_One_001" in results["hybrid"]["primary_chunk_ids"]
    trace = results["hybrid"]["trace"]
    assert trace["selection"]["raw_primary_fallback_used"] is False
    assert trace["selection"]["fusion_pool_fallback_used"] is False
    assert any(
        item["chunk_id"] == "01_One_001"
        and item["reason"] == "distance_threshold"
        for item in trace["selection"]["discarded"]
    )
    rescued = next(
        item
        for item in trace["candidates"]["fused"]
        if item["chunk_id"] == "01_One_001"
    )
    assert rescued["semantic_rank"] == 2
    assert rescued["semantic_distance"] == 1.4
    assert rescued["semantic_contributed"] is False

    fallback = build_hybrid_results(
        "quasar",
        semantic_results([near_partial, distant_exact], [1.3, 1.4]),
        [near_partial, distant_exact],
        n_results=2,
    )
    assert fallback["hybrid"]["trace"]["selection"]["raw_primary_fallback_used"] is True
    assert fallback["hybrid"]["trace"]["selection"]["fusion_pool_fallback_used"] is True
    assert fallback["hybrid"]["primary_chunk_ids"] == [
        "02_Two_001",
        "01_One_001",
    ]


def test_raw_primary_and_fusion_pool_fallback_events_are_separate():
    chunks = [
        chunk(f"01_One_{index:03}", "one.md", f"entry {index}")
        for index in range(1, 7)
    ]
    results = build_hybrid_results(
        "quasar",
        semantic_results(
            chunks,
            [1.20, 1.21, 1.22, 1.23, 1.24, 0.20],
        ),
        chunks,
        n_results=5,
    )

    selection = results["hybrid"]["trace"]["selection"]
    assert selection["raw_primary_fallback_used"] is True
    assert selection["fusion_pool_fallback_used"] is False
    assert results["hybrid"]["primary_chunk_ids"] == [
        "01_One_001",
        "01_One_002",
        "01_One_003",
        "01_One_004",
        "01_One_005",
    ]


def test_every_displaced_raw_primary_has_one_contract_facing_cause():
    structural = chunk(
        "00_Front_001",
        "02_Table of Contents.md",
        "structural",
    )
    distant = chunk("01_One_001", "one.md", "distant")
    near = [
        chunk(f"02_Two_{index:03}", "two.md", f"near {index}")
        for index in range(1, 4)
    ]
    lexical = [
        chunk(f"03_Three_{index:03}", "three.md", f"quasar {index}")
        for index in range(1, 4)
    ]
    chunks = [structural, distant, *near, *lexical]
    results = build_hybrid_results(
        "quasar",
        semantic_results(
            [structural, distant, *near],
            [0.10, 1.40, 0.20, 0.30, 0.40],
        ),
        chunks,
        n_results=5,
    )
    outcome = plan_context_chunks(
        results,
        chunks=chunks,
        max_final_sources=5,
    )
    raw_ids = set(results["ids"][0])
    context_ids = {
        item["chunk_id"] for item in outcome.final_chunks
    }
    displaced = raw_ids - context_ids
    causes_by_id: dict[str, set[str]] = {}
    for item in outcome.trace["selection"]["discarded"]:
        if item.get("chunk_id") in displaced and item.get("displacement_cause"):
            causes_by_id.setdefault(item["chunk_id"], set()).add(
                item["displacement_cause"]
            )

    assert displaced == {
        "00_Front_001",
        "01_One_001",
        "02_Two_003",
    }
    assert causes_by_id == {
        "00_Front_001": {"document_filtering"},
        "01_One_001": {"distance_filtering"},
        "02_Two_003": {"truncation"},
    }


def test_diversity_cap_then_backfill_is_deterministic():
    dominant = [
        chunk(f"01_One_{index:03}", "one.md", f"entry {index}")
        for index in range(1, 7)
    ]
    alternatives = [
        chunk(f"02_Two_{index:03}", "two.md", f"alternative {index}")
        for index in range(1, 3)
    ]
    chunks = [*dominant, *alternatives]
    results = build_hybrid_results(
        "Trace the development of quasar policy across institutions",
        semantic_results(chunks),
        chunks,
        n_results=5,
    )

    assert results["hybrid"]["primary_chunk_ids"] == [
        "01_One_001",
        "01_One_002",
        "01_One_003",
        "02_Two_001",
        "02_Two_002",
    ]
    repeated = build_hybrid_results(
        "Trace the development of quasar policy across institutions",
        semantic_results(chunks),
        chunks,
        n_results=5,
    )
    assert repeated["hybrid"]["primary_chunk_ids"] == (
        results["hybrid"]["primary_chunk_ids"]
    )

    one_document = build_hybrid_results(
        "Trace the development of quasar policy across institutions",
        semantic_results(dominant),
        dominant,
        n_results=5,
    )
    assert len(one_document["hybrid"]["primary_chunk_ids"]) == 5


def test_standard_queries_do_not_trade_strong_evidence_for_weak_document_spread():
    dominant = [
        chunk(
            f"01_One_{index:03}",
            "one.md",
            f"Ada Marlowe expedition evidence {index}",
        )
        for index in range(1, 6)
    ]
    weak_alternatives = [
        chunk(f"02_Two_{index:03}", "two.md", f"unrelated {index}")
        for index in range(1, 3)
    ]
    ranked = [*dominant, *weak_alternatives]
    results = build_hybrid_results(
        "Ada Marlowe expedition",
        semantic_results(ranked),
        ranked,
        n_results=5,
    )

    assert results["hybrid"]["primary_chunk_ids"] == [
        item["chunk_id"] for item in dominant
    ]
    assert results["hybrid"]["trace"]["query"]["mode"] == "standard"
    assert results["hybrid"]["trace"]["selection"]["diversity_applied"] is False


def test_broad_diversity_rejects_alternatives_outside_the_relevance_band():
    dominant = [
        chunk(
            f"01_One_{index:03}",
            "one.md",
            f"Ada Marlowe expedition evidence {index}",
        )
        for index in range(1, 6)
    ]
    weak_alternatives = [
        chunk(f"02_Two_{index:03}", "two.md", f"unrelated {index}")
        for index in range(1, 3)
    ]
    ranked = [*dominant, *weak_alternatives]
    results = build_hybrid_results(
        "Trace Ada Marlowe expedition evidence across institutions",
        semantic_results(ranked),
        ranked,
        n_results=5,
    )

    assert results["hybrid"]["trace"]["query"]["mode"] == "broad_synthesis"
    assert results["hybrid"]["primary_chunk_ids"] == [
        item["chunk_id"] for item in dominant
    ]
    assert results["hybrid"]["trace"]["selection"]["diversity_applied"] is False


def test_lexical_tokenizer_normalizes_terminal_possessives():
    possessive = chunk(
        "01_One_001",
        "one.md",
        "Hudson's ships returned to the harbor.",
    )
    plain = chunk(
        "02_Two_001",
        "two.md",
        "Hudson ships returned to the harbor.",
    )

    possessive_ranked, _ = lexical_candidates("Hudson ships", [possessive])
    plain_ranked, _ = lexical_candidates("Hudson's ships", [plain])
    assert possessive_ranked[0]["chunk_id"] == "01_One_001"
    assert plain_ranked[0]["chunk_id"] == "02_Two_001"


def test_answer_context_reserves_all_primaries_before_optional_neighbors():
    chunks = [
        chunk(f"01_One_{index:03}", "one.md", f"one {index}")
        for index in range(1, 4)
    ] + [
        chunk(f"02_Two_{index:03}", "two.md", f"two {index}")
        for index in range(1, 4)
    ]
    results = build_hybrid_results(
        "quasar",
        semantic_results([chunks[1], chunks[4]]),
        chunks,
        n_results=2,
    )
    outcome = plan_context_chunks(
        results,
        chunks=chunks,
        max_final_sources=3,
    )

    assert [item["chunk_id"] for item in outcome.final_chunks] == [
        "01_One_002",
        "02_Two_002",
        "01_One_001",
    ]
    assert [
        item["origin"]
        for item in outcome.trace["selection"]["context"]
    ] == ["primary", "primary", "neighbor"]
    assert any(
        item["reason"] == "final_source_cap"
        for item in outcome.trace["selection"]["discarded"]
    )
    context = build_context(outcome.final_chunks)
    assert context.index("Chunk ID: 01_One_002") < context.index(
        "Chunk ID: 02_Two_002"
    ) < context.index("Chunk ID: 01_One_001")

    import web_project

    sources = web_project.source_payload(outcome.final_chunks)["sources"]
    assert [item["source_number"] for item in sources] == [1, 2, 3]
    assert [item["chunk_id"] for item in sources] == [
        "01_One_002",
        "02_Two_002",
        "01_One_001",
    ]


def test_trace_is_text_free_and_optional_persistence_is_nonfatal(caplog):
    evidence = "Synthetic private evidence that must never enter diagnostics."
    chunks = [chunk("01_One_001", "one.md", evidence)]
    results = build_hybrid_results(
        "What is the synthetic evidence?",
        semantic_results(chunks),
        chunks,
        n_results=1,
        corpus={
            "project_id": "synthetic",
            "text": "malicious manuscript leak attempt",
        },
    )
    trace_root = Path("runtime") / f"retrieval-test-{uuid4().hex}"
    try:
        sink = FileTraceSink(trace_root)
        final_chunks = finalize_context_chunks(results, chunks=chunks, trace_sink=sink)
        trace_path = next(trace_root.rglob("*.json"))
        saved = json.loads(trace_path.read_text(encoding="utf-8"))

        assert final_chunks == chunks
        assert_trace_is_text_free(saved)
        assert evidence not in trace_path.read_text(encoding="utf-8")
        assert "What is the synthetic evidence?" not in trace_path.read_text(
            encoding="utf-8"
        )
        assert saved["corpus"] == {"project_id": "synthetic"}
    finally:
        shutil.rmtree(trace_root, ignore_errors=True)

    def broken_sink(_trace: object) -> None:
        raise OSError("diagnostic disk unavailable")

    same_chunks = finalize_context_chunks(
        results,
        chunks=chunks,
        trace_sink=broken_sink,
    )
    assert same_chunks == final_chunks
    assert "Retrieval diagnostics could not be persisted" in caplog.text

    with pytest.raises(ValueError, match="forbidden field"):
        FileTraceSink(trace_root)(
            {"schema": retrieval.RETRIEVAL_TRACE_SCHEMA, "text": evidence}
        )
    with pytest.raises(ValueError, match="hashed diagnostics"):
        FileTraceSink(trace_root)(
            {
                "schema": retrieval.RETRIEVAL_TRACE_SCHEMA,
                "query": "raw private question",
            }
        )
    malicious_path_trace = dict(results["hybrid"]["trace"])
    malicious_path_trace["trace_id"] = "../escape"
    with pytest.raises(ValueError, match="trace ID"):
        FileTraceSink(trace_root)(malicious_path_trace)


def test_stale_hybrid_primary_ids_fail_instead_of_masking_corruption():
    chunks = [chunk("01_One_001", "one.md", "synthetic")]
    results = build_hybrid_results(
        "synthetic",
        semantic_results(chunks),
        chunks,
        n_results=1,
    )

    with pytest.raises(RuntimeError, match="unavailable corpus chunks"):
        finalize_context_chunks(results, chunks=[])


def test_collection_retrieval_uses_one_embedding_and_a_larger_semantic_pool(monkeypatch):
    chunks = [
        chunk(f"01_One_{index:03}", "one.md", f"entry {index}")
        for index in range(1, 26)
    ]
    calls: list[tuple] = []

    class FakeCollection:
        configuration = {"hnsw": {"space": "l2"}}

        def count(self) -> int:
            return len(chunks)

        def query(self, **kwargs):
            calls.append(("query", kwargs))
            limit = kwargs["n_results"]
            return semantic_results(chunks[:limit])

    def fake_embed(query: str, embedding_client=None) -> list[float]:
        calls.append(("embed", query, embedding_client))
        return [0.25, 0.75]

    monkeypatch.setattr(retrieval, "embed_query", fake_embed)
    results = retrieve_from_collection(
        "quasar",
        FakeCollection(),
        chunks,
        n_results=5,
        embedding_client=object(),
    )

    assert [call[0] for call in calls] == ["embed", "query"]
    assert calls[1][1]["n_results"] == retrieval.SEMANTIC_CANDIDATE_LIMIT
    assert len(results["ids"][0]) == 5
    assert len(results["hybrid"]["trace"]["candidates"]["semantic"]) == 20
    assert results["hybrid"]["trace"]["corpus"]["hnsw_space"] == "l2"


def test_semantic_only_collection_path_requests_exact_k_and_never_fuses(monkeypatch):
    chunks = [
        chunk(f"01_One_{index:03}", "one.md", f"entry {index}")
        for index in range(1, 9)
    ]
    calls: list[tuple] = []

    class FakeCollection:
        def count(self) -> int:
            return len(chunks)

        def query(self, **kwargs):
            calls.append(("query", kwargs))
            return semantic_results(chunks[:kwargs["n_results"]])

    def fake_embed(query: str, embedding_client=None) -> list[float]:
        calls.append(("embed", query, embedding_client))
        return [0.5]

    monkeypatch.setattr(retrieval, "embed_query", fake_embed)
    monkeypatch.setattr(
        retrieval,
        "build_hybrid_results",
        lambda *_args, **_kwargs: pytest.fail("semantic-only path invoked fusion"),
    )
    results = retrieve_semantic_from_collection(
        "index term",
        FakeCollection(),
        n_results=5,
        embedding_client=object(),
    )

    assert [call[0] for call in calls] == ["embed", "query"]
    assert calls[1][1]["n_results"] == 5
    assert len(results["ids"][0]) == 5
    assert "hybrid" not in results


def test_web_project_retrieval_delegates_to_the_shared_core(monkeypatch):
    import web_project

    chunks = [chunk("01_One_001", "one.md", "synthetic")]
    collection_handle = object()
    embedding_client = object()
    captured: dict[str, object] = {}
    sentinel = {"hybrid": {"primary_chunk_ids": ["01_One_001"]}}

    class FakeStore:
        def get_collection(self, *, name: str):
            captured["collection_name"] = name
            return collection_handle

    def fake_shared_retrieval(query, collection, corpus_chunks, **kwargs):
        captured.update(
            {
                "query": query,
                "collection": collection,
                "chunks": corpus_chunks,
                **kwargs,
            }
        )
        return sentinel

    monkeypatch.setattr(web_project, "chroma_client", lambda: FakeStore())
    monkeypatch.setattr(web_project, "load_project_chunks", lambda _project_id: chunks)
    monkeypatch.setattr(web_project, "openai_client", lambda: embedding_client)
    monkeypatch.setattr(
        web_project,
        "retrieve_from_collection",
        fake_shared_retrieval,
    )

    assert web_project.retrieve_project("current", "question", n_results=7) is sentinel
    assert captured["collection_name"] == web_project.collection_name("current")
    assert captured["query"] == "question"
    assert captured["collection"] is collection_handle
    assert captured["chunks"] == chunks
    assert captured["n_results"] == 7
    assert captured["embedding_client"] is embedding_client
    corpus = captured["corpus"]
    assert corpus["project_id"] == "current"
    assert corpus["collection_name"] == web_project.collection_name("current")
    assert len(corpus["chunks_sha256"]) == 64
    assert len(corpus["corpus_manifest_sha256"]) == 64


def test_cli_and_web_answer_wrappers_produce_the_same_synthetic_context(monkeypatch):
    import web_project

    chunks = [
        chunk(f"01_One_{index:03}", "one.md", f"entry {index}")
        for index in range(1, 7)
    ]

    class FakeCollection:
        configuration = {"hnsw": {"space": "l2"}}

        def count(self) -> int:
            return len(chunks)

        def query(self, **kwargs):
            return semantic_results(chunks[:kwargs["n_results"]])

    collection_handle = FakeCollection()

    class FakeStore:
        def get_collection(self, *, name: str):
            assert name == web_project.collection_name("current")
            return collection_handle

    monkeypatch.setattr(retrieval, "collection", collection_handle)
    monkeypatch.setattr(retrieval, "get_all_chunks", lambda: chunks)
    monkeypatch.setattr(retrieval, "embed_query", lambda *_args, **_kwargs: [0.5])
    monkeypatch.setattr(web_project, "chroma_client", lambda: FakeStore())
    monkeypatch.setattr(web_project, "load_project_chunks", lambda _project_id: chunks)
    monkeypatch.setattr(web_project, "openai_client", lambda: object())

    cli_results = retrieval.retrieve("quasar", n_results=5)
    web_results = web_project.retrieve_project("current", "quasar", n_results=5)
    assert cli_results["hybrid"]["primary_chunk_ids"] == (
        web_results["hybrid"]["primary_chunk_ids"]
    )
    assert [
        item["chunk_id"]
        for item in finalize_context_chunks(cli_results, chunks=chunks)
    ] == [
        item["chunk_id"]
        for item in finalize_context_chunks(web_results, chunks=chunks)
    ]


def test_web_index_generation_uses_semantic_only_retrieval(monkeypatch):
    import web_project

    chunks = [chunk("01_One_001", "one.md", "index evidence")]
    semantic = semantic_results(chunks)
    calls: list[tuple] = []

    monkeypatch.setattr(
        web_project,
        "retrieve_project",
        lambda *_args, **_kwargs: pytest.fail("Index Mode invoked hybrid retrieval"),
    )
    monkeypatch.setattr(
        web_project,
        "retrieve_project_semantic",
        lambda project_id, query, n_results=5: (
            calls.append(("semantic", project_id, query, n_results))
            or semantic
        ),
    )
    monkeypatch.setattr(web_project, "load_project_chunks", lambda _project_id: chunks)
    monkeypatch.setattr(
        web_project,
        "finalize_index_context",
        lambda *_args, **_kwargs: chunks,
    )
    monkeypatch.setattr(web_project, "openai_client", lambda: object())
    monkeypatch.setattr(
        web_project,
        "tracked_responses_create",
        lambda *_args, **_kwargs: type("Response", (), {"output_text": "entry"})(),
    )

    answer, final_chunks, existing = web_project.generate_index_entry(
        "current",
        "term",
        False,
    )
    assert calls == [("semantic", "current", "term", 5)]
    assert (answer, final_chunks, existing) == ("entry", chunks, [])
