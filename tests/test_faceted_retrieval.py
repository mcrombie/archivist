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
    requirement_ids: tuple[str, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        facet_id=facet_id,
        role=role,
        search_query=query,
        document_hints=document_hints,
        requirement_ids=requirement_ids,
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
        lambda queries, **_kwargs: [
            [float(index)] for index in range(len(queries))
        ],
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
        lambda queries, **_kwargs: [
            [float(index)] for index in range(len(queries))
        ],
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


def test_broad_stage_lanes_use_document_terciles_and_fill_new_documents_first(
    monkeypatch,
):
    chunks = [
        chunk(
            f"stage_{index:03}",
            f"document-{index}.md",
            f"stage evidence {index}",
            1,
        )
        for index in range(9)
    ]
    embedded: list[list[str]] = []
    monkeypatch.setattr(
        retrieval,
        "embed_queries",
        lambda queries, embedding_client=None: (
            embedded.append(list(queries))
            or [[float(index)] for index in range(len(queries))]
        ),
    )
    requests: list[dict] = []

    class Collection:
        configuration = {"hnsw": {"space": "l2"}}

        def count(self):
            return len(chunks)

        def query(self, **request):
            requests.append(request)
            where = request.get("where")
            if where is None:
                return semantic_results([chunks[4]])
            documents = set(where["document"]["$in"])
            return semantic_results(
                [item for item in chunks if item["document"] in documents]
            )

    outcome = retrieve_plan_from_collection(
        plan(
            facet("F0", "original", "whole history"),
            facet("F1", "origin", "early history"),
            facet("F2", "transition", "middle history"),
            facet("F3", "endpoint", "late history"),
            traits=("broad_synthesis",),
        ),
        Collection(),
        chunks,
        max_final_sources=6,
    )

    assert embedded[0][:4] == [
        "whole history",
        "early history",
        "middle history",
        "late history",
    ]
    assert len(embedded[0]) == 7
    assert all(query.startswith("whole history ") for query in embedded[0][4:])
    assert requests[0].get("where") is None
    assert [
        set(request["where"]["document"]["$in"])
        for request in requests[1:7:2]
    ] == [
        {f"document-{index}.md" for index in range(0, 3)},
        {f"document-{index}.md" for index in range(3, 6)},
        {f"document-{index}.md" for index in range(6, 9)},
    ]
    assert len({item["document"] for item in outcome.final_chunks}) == 6
    assert outcome.trace["selection"]["stage_coverage_required_count"] == 3
    assert outcome.trace["selection"]["stage_coverage_satisfied_count"] == 3
    assert outcome.trace["selection"]["stage_coverage_shortfall_count"] == 0
    lanes = {lane["facet_id"]: lane for lane in outcome.trace["lanes"]}
    assert (
        lanes["F1"]["chronology_band"],
        lanes["F1"]["chronology_min_document_ordinal"],
        lanes["F1"]["chronology_max_document_ordinal"],
    ) == ("early", 0, 2)
    assert (
        lanes["F2"]["chronology_band"],
        lanes["F2"]["chronology_min_document_ordinal"],
        lanes["F2"]["chronology_max_document_ordinal"],
    ) == ("middle", 3, 5)
    assert (
        lanes["F3"]["chronology_band"],
        lanes["F3"]["chronology_min_document_ordinal"],
        lanes["F3"]["chronology_max_document_ordinal"],
    ) == ("late", 6, 8)
    assert [
        item["document_ordinal"]
        for item in outcome.trace["selection"]["context"]
    ] == sorted(
        item["document_ordinal"]
        for item in outcome.trace["selection"]["context"]
    )
    validate_text_free_retrieval_trace(outcome.trace)


def test_five_broad_stages_span_numbered_chapters_through_epilogue(
    monkeypatch,
):
    document_names = [
        "05_Introduction.md",
        "07_Prologue.md",
        *(f"{index + 7:02}_Chapter {index}.md" for index in range(1, 21)),
        "28_Epilogue.md",
        "29_Afterword.md",
        "30_Appendix A.md",
    ]
    chunks = [
        chunk(
            f"narrative_{index:03}",
            document,
            f"central power war stage {index}",
            1,
        )
        for index, document in enumerate(document_names)
    ]
    monkeypatch.setattr(
        retrieval,
        "embed_queries",
        lambda queries, embedding_client=None: [
            [float(index)] for index in range(len(queries))
        ],
    )
    requests: list[dict] = []

    class Collection:
        configuration = {"hnsw": {"space": "l2"}}

        def count(self):
            return len(chunks)

        def query(self, **request):
            requests.append(request)
            where = request.get("where")
            if where is None:
                return semantic_results([chunks[0]])
            document_filter = where["document"]
            documents = (
                set(document_filter["$in"])
                if isinstance(document_filter, dict)
                else {document_filter}
            )
            return semantic_results(
                [item for item in chunks if item["document"] in documents]
            )

    requirements = tuple(
        SimpleNamespace(requirement_id=f"R{index}", order=index - 1)
        for index in range(1, 6)
    )
    facets = (
        SimpleNamespace(
            facet_id="F0",
            role="original",
            search_query="war as an engine of central power",
            document_hints=(),
            requirement_ids=tuple(f"R{index}" for index in range(1, 6)),
        ),
        *(
            SimpleNamespace(
                facet_id=f"F{index}",
                role=(
                    "origin"
                    if index == 1
                    else "endpoint"
                    if index == 5
                    else "mechanism"
                ),
                search_query=f"war central power stage {index}",
                document_hints=(),
                requirement_ids=(f"R{index}",),
            )
            for index in range(1, 6)
        ),
    )
    broad_plan = SimpleNamespace(
        schema="archivist.question_plan/1",
        traits=("broad_synthesis",),
        facets=facets,
        requirements=requirements,
        planner_used=True,
        fallback_reason=None,
    )

    outcome = retrieve_plan_from_collection(
        broad_plan,
        Collection(),
        chunks,
        max_final_sources=8,
    )

    assert requests[0].get("where") is None
    assert [
        list(request["where"]["document"]["$in"])
        for request in requests[1:11:2]
    ] == [
        [f"{index + 7:02}_Chapter {index}.md" for index in range(1, 8)],
        [f"{index + 7:02}_Chapter {index}.md" for index in range(4, 12)],
        [f"{index + 7:02}_Chapter {index}.md" for index in range(8, 16)],
        [f"{index + 7:02}_Chapter {index}.md" for index in range(12, 20)],
        [
            *(f"{index + 7:02}_Chapter {index}.md" for index in range(16, 21)),
            "28_Epilogue.md",
        ],
    ]
    assert requests[11]["where"]["document"] == "28_Epilogue.md"
    lanes = {lane["facet_id"]: lane for lane in outcome.trace["lanes"]}
    assert [
        (
            lanes[f"F{index}"]["chronology_min_document_ordinal"],
            lanes[f"F{index}"]["chronology_max_document_ordinal"],
        )
        for index in range(1, 6)
    ] == [(2, 8), (5, 12), (9, 16), (13, 20), (17, 22)]
    assert outcome.trace["selection"]["stage_coverage_required_count"] == 5
    assert outcome.trace["selection"]["stage_coverage_satisfied_count"] == 5
    assert outcome.trace["selection"]["stage_coverage_shortfall_count"] == 0
    assert "28_Epilogue.md" in {
        item["document"] for item in outcome.final_chunks
    }
    assert (
        outcome.trace["parameters"]["lane_selection"]
        == "canonical_stage_core_then_global_supplement"
    )
    assert (
        outcome.trace["parameters"]["broad_execution_version"]
        == "broad-canonical-core-v1"
    )
    assert (
        outcome.trace["parameters"]["broad_mechanism_lexical_version"]
        == "role-scoped-mechanism-lexical-v1"
    )
    assert lanes["F2"]["mechanism_query_sha256s"]
    assert lanes["F2"]["mechanism_candidate_chunk_ids"]
    assert lanes["F2"]["provider_query_sha256"] == lanes["F2"]["query_sha256"]
    assert lanes["F2"]["canonical_query_sha256"]
    assert lanes["F2"]["canonical_candidate_chunk_ids"]
    assert lanes["F2"]["canonical_core_selected_chunk_ids"]
    assert outcome.trace["selection"]["canonical_core_required_count"] == 5
    assert outcome.trace["selection"]["canonical_core_satisfied_count"] == 5
    assert outcome.trace["selection"]["canonical_core_shortfall_count"] == 0
    validate_text_free_retrieval_trace(outcome.trace)


def test_canonical_broad_core_survives_provider_query_hint_and_order_variance(
    monkeypatch,
):
    documents = [
        *(f"{index:02}_Chapter {index}.md" for index in range(1, 21)),
        "21_Epilogue.md",
    ]
    chunks = [
        chunk(
            f"synthetic_{index:03}",
            document,
            "shared topic background",
            1,
        )
        for index, document in enumerate(documents, start=1)
    ]
    core_by_position = {
        "earliest origin emergence": chunks[1],
        "early development expansion": chunks[6],
        "middle mechanism consolidation": chunks[10],
        "later transformation normalization": chunks[14],
        "latest endpoint consequence": chunks[20],
    }
    for marker, item in core_by_position.items():
        item["text"] = f"shared topic {marker} cause finance institution persistence"

    def embed(queries, embedding_client=None):
        del embedding_client
        vectors = []
        for query in queries:
            if query == "shared topic":
                vectors.append([0.0])
                continue
            marker_index = next(
                (
                    index
                    for index, marker in enumerate(core_by_position, start=1)
                    if marker in query
                ),
                None,
            )
            if marker_index is not None:
                vectors.append([float(10 + marker_index)])
            elif query.startswith("provider-a"):
                vectors.append([101.0])
            else:
                vectors.append([201.0])
        return vectors

    monkeypatch.setattr(retrieval, "embed_queries", embed)

    class Collection:
        configuration = {"hnsw": {"space": "l2"}}

        def count(self):
            return len(chunks)

        def query(self, **request):
            value = int(request["query_embeddings"][0][0])
            if 11 <= value <= 15:
                selected = list(core_by_position.values())[value - 11]
            elif value == 101:
                selected = chunks[3]
            elif value == 201:
                selected = chunks[5]
            else:
                selected = chunks[16]
            where = request.get("where")
            if where is not None:
                document_filter = where["document"]
                allowed = (
                    set(document_filter["$in"])
                    if isinstance(document_filter, dict)
                    else {document_filter}
                )
                if selected["document"] not in allowed:
                    selected = next(
                        item for item in chunks if item["document"] in allowed
                    )
            return semantic_results([selected])

    original_mechanism_candidates = retrieval._broad_mechanism_candidates

    def deterministic_core_candidates(query, role, lane_chunks, primary_candidates):
        for marker, item in core_by_position.items():
            if marker in query:
                return (
                    [
                        {
                            "chunk_id": item["chunk_id"],
                            "document": item["document"],
                            "rrf_score": 1.0,
                        }
                    ],
                    (f"{query} fixed mechanism",),
                )
        return original_mechanism_candidates(
            query,
            role,
            lane_chunks,
            primary_candidates,
        )

    monkeypatch.setattr(
        retrieval,
        "_broad_mechanism_candidates",
        deterministic_core_candidates,
    )

    requirements = tuple(
        SimpleNamespace(requirement_id=f"R{index}", order=index - 1)
        for index in range(1, 6)
    )
    roles = ("origin", "transition", "mechanism", "transition", "endpoint")

    def variant_plan(variant: str, *, reverse: bool) -> SimpleNamespace:
        stage_facets = [
            facet(
                f"F{index}",
                role,
                f"provider-{variant} shared topic stage {index}",
                document_hints=(
                    documents[(index * 3 + (0 if variant == "a" else 1)) % 20],
                ),
                requirement_ids=(f"R{index}",),
            )
            for index, role in enumerate(roles, start=1)
        ]
        if reverse:
            stage_facets.reverse()
        return SimpleNamespace(
            schema="archivist.question_plan/1",
            traits=("broad_synthesis",),
            facets=(
                facet(
                    "F0",
                    "original",
                    "shared topic",
                    requirement_ids=tuple(f"R{index}" for index in range(1, 6)),
                ),
                *stage_facets,
            ),
            requirements=requirements,
            planner_used=True,
            fallback_reason=None,
        )

    outcomes = [
        retrieve_plan_from_collection(
            variant_plan("a", reverse=False),
            Collection(),
            chunks,
            max_final_sources=8,
        ),
        retrieve_plan_from_collection(
            variant_plan("b", reverse=True),
            Collection(),
            chunks,
            max_final_sources=8,
        ),
    ]
    lane_maps = [
        {lane["facet_id"]: lane for lane in outcome.trace["lanes"]}
        for outcome in outcomes
    ]
    expected_core_ids = tuple(
        item["chunk_id"] for item in core_by_position.values()
    )
    selected_core_ids = [
        tuple(
            lane_map[f"F{index}"]["canonical_core_selected_chunk_ids"][0]
            for index in range(1, 6)
        )
        for lane_map in lane_maps
    ]

    assert selected_core_ids == [expected_core_ids, expected_core_ids]
    assert {
        item["chunk_id"] for item in outcomes[0].final_chunks
    }.issuperset(expected_core_ids)
    assert {
        item["chunk_id"] for item in outcomes[1].final_chunks
    }.issuperset(expected_core_ids)
    assert [
        lane_maps[0][f"F{index}"]["canonical_query_sha256"]
        for index in range(1, 6)
    ] == [
        lane_maps[1][f"F{index}"]["canonical_query_sha256"]
        for index in range(1, 6)
    ]
    assert lane_maps[0]["F3"]["provider_query_sha256"] != (
        lane_maps[1]["F3"]["provider_query_sha256"]
    )
    assert all(
        outcome.trace["selection"]["canonical_core_satisfied_count"] == 5
        for outcome in outcomes
    )
    for outcome in outcomes:
        validate_text_free_retrieval_trace(outcome.trace)


def test_origin_uses_canonical_mechanism_core_instead_of_semantic_decoy(
    monkeypatch,
):
    generic = chunk(
        "generic_001",
        "01_Chapter 1.md",
        "Conflict expanded authority across the region.",
        1,
    )
    mechanism = chunk(
        "mechanism_001",
        "01_Chapter 1.md",
        (
            "Conflict expanded authority because finance enabled an "
            "administrative institution and established a precedent."
        ),
        2,
    )
    chunks = [generic, mechanism]
    monkeypatch.setattr(
        retrieval,
        "embed_queries",
        lambda queries, embedding_client=None: [
            [float(index)] for index in range(len(queries))
        ],
    )

    class Collection:
        configuration = {"hnsw": {"space": "l2"}}

        def count(self):
            return len(chunks)

        def query(self, **request):
            return semantic_results([generic])

    outcome = retrieve_plan_from_collection(
        plan(
            facet("F0", "original", "How did conflict expand authority?"),
            facet(
                "F1",
                "origin",
                "provider wording about conflict",
            ),
            traits=("broad_synthesis",),
        ),
        Collection(),
        chunks,
        max_final_sources=1,
    )
    origin_lane = next(
        lane for lane in outcome.trace["lanes"] if lane["facet_id"] == "F1"
    )

    assert origin_lane["canonical_core_selected_chunk_ids"] == [
        "mechanism_001"
    ]
    assert [item["chunk_id"] for item in outcome.final_chunks] == [
        "mechanism_001"
    ]


def test_broad_supplemental_utility_is_global_not_facet_ordered():
    early = {
        "chunk_id": "early_001",
        "document": "early.md",
        "rrf_score": 1.0,
    }
    consensus = {
        "chunk_id": "consensus_001",
        "document": "later.md",
        "rrf_score": 1.0,
    }
    lanes = [
        {
            "facet_id": "F1",
            "canonical_core_candidates": [early],
            "mechanism_candidates": [],
            "candidates": [],
        },
        {
            "facet_id": "F5",
            "canonical_core_candidates": [consensus],
            "mechanism_candidates": [consensus],
            "candidates": [consensus],
        },
    ]

    forward = retrieval._ranked_broad_supplemental_options(
        lanes,
        document_ordinal_by_id={"early.md": 1, "later.md": 5},
    )
    reverse = retrieval._ranked_broad_supplemental_options(
        list(reversed(lanes)),
        document_ordinal_by_id={"early.md": 1, "later.md": 5},
    )

    assert forward[0]["chunk_id"] == "consensus_001"
    assert reverse[0]["chunk_id"] == "consensus_001"


def test_broad_mechanism_rerank_prefers_explicit_financing_link():
    generic = chunk(
        "generic_001",
        "chapter.md",
        "The conflict expanded authority across the region.",
        1,
    )
    mechanism = chunk(
        "mechanism_001",
        "chapter.md",
        (
            "The conflict enabled central authority because debt and taxation "
            "financed a permanent administrative institution."
        ),
        2,
    )

    candidates, queries = retrieval._broad_mechanism_candidates(
        "How did conflict expand central authority?",
        "transition",
        [generic, mechanism],
        [
            {
                "chunk_id": generic["chunk_id"],
                "document": generic["document"],
                "rrf_score": 0.02,
            }
        ],
    )

    assert len(queries) == 2
    assert candidates[0]["chunk_id"] == "mechanism_001"
    assert candidates[0]["mechanism_utility_score"] > 0


def test_broad_endpoint_rerank_prefers_institutional_transformation():
    generic = chunk(
        "generic_001",
        "ending.md",
        "Central authority remained important after the conflict.",
        1,
    )
    transformed = chunk(
        "transformed_001",
        "ending.md",
        (
            "After the conflict, central authority preserved the alliance; it "
            "was not retired but transformed into a permanent institution that "
            "continued the earlier policy."
        ),
        2,
    )

    candidates, _queries = retrieval._broad_mechanism_candidates(
        "What happened to central authority after the conflict?",
        "endpoint",
        [generic, transformed],
        [],
    )

    assert candidates[0]["chunk_id"] == "transformed_001"


def test_hinted_absence_relation_lane_may_use_bounded_distant_fallback(
    monkeypatch,
):
    generic = chunk("generic_001", "generic.md", "generic material", 1)
    related = chunk("related_001", "related.md", "bounded related material", 1)
    chunks = [generic, related]
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
                return semantic_results([generic], [0.2])
            return semantic_results([related], [1.4])

    outcome = retrieve_plan_from_collection(
        plan(
            facet("F0", "original", "missing event and bounded relation"),
            facet(
                "F1",
                "mechanism",
                "missing event bounded relation",
                document_hints=("related.md",),
            ),
            traits=("absence_sensitive",),
        ),
        Collection(),
        chunks,
        max_final_sources=3,
    )

    related_lane = next(
        lane for lane in outcome.trace["lanes"] if lane["facet_id"] == "F1"
    )
    assert related_lane["raw_primary_fallback_detected"] is True
    assert related_lane["semantic_fallback_used"] is True
    assert related_lane["candidate_chunk_ids"] == ["related_001"]
    assert outcome.facet_source_numbers["F1"]
    validate_text_free_retrieval_trace(outcome.trace)


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


def test_trace_contract_accepts_text_free_evidence_obligation_diagnostics():
    trace = {
        "generation_contract": {
            "schema": "archivist.evidence_coverage_diagnostics/5",
            "normalizer_version": "evidence-coverage-normalizer/5",
            "prompt_version": "evidence-coverage-v4",
            "citation_locality_failure": {
                "unit_id": "U1",
                "unit_ordinal": 1,
                "code": "semicolon_in_claim",
            },
            "obligation_count": 1,
            "obligation_scopes": [
                {
                    "obligation_id": "O1",
                    "source_number": 1,
                    "paragraph_start": 3,
                    "paragraph_end": 4,
                    "allowed_requirement_ids": ["R1"],
                    "focus": "mechanism",
                    "dimension_ids": ["cause_or_enabler", "mechanism"],
                    "required_for_requirement_status": True,
                }
            ],
            "obligation_coverage": [
                {
                    "obligation_id": "O1",
                    "dimensions": [
                        {
                            "dimension": "mechanism",
                            "status": "supported",
                            "unit_ids": ["U1"],
                            "source_numbers": [1],
                            "gap_reason": "none",
                        }
                    ],
                }
            ],
            "answer_units": [
                {
                    "unit_id": "U1",
                    "requirement_ids": ["R1"],
                    "role": "mechanism",
                    "source_numbers": [1],
                    "paragraph": 1,
                    "obligation_links": [
                        {
                            "obligation_id": "O1",
                            "dimension": "mechanism",
                        }
                    ],
                }
            ],
        }
    }

    assert_text_free(trace)
    validate_text_free_retrieval_trace(trace)
