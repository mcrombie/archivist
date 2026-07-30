from types import SimpleNamespace

import retrieval
from query_planning import deterministic_fallback_plan
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
                (
                    "whole history charter foundation assembly reform legacy "
                    f"persistence evidence {index} began because finance "
                    "transformed institutions"
                ),
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
            facet("F1", "origin", "charter foundation"),
            facet("F2", "transition", "assembly reform"),
            facet("F3", "endpoint", "legacy persistence"),
            traits=("broad_synthesis",),
        ),
        Collection(),
        chunks,
        max_final_sources=6,
    )

    assert embedded[0][:4] == [
        "whole history",
        "charter foundation",
        "assembly reform",
        "legacy persistence",
    ]
    assert len(embedded[0]) == 9
    assert all(query.startswith("whole history ") for query in embedded[0][4:7])
    assert "charter foundation" in embedded[0][7]
    assert "assembly reform" in embedded[0][7]
    assert "assembly reform" in embedded[0][8]
    assert "legacy persistence" in embedded[0][8]
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


def test_adjacent_pair_lane_selects_only_an_explicit_two_stage_transition(
    monkeypatch,
):
    origin = chunk(
        "origin_001",
        "01_Chapter 1.md",
        "A charter foundation established the synthetic institution.",
        1,
    )
    disconnected = chunk(
        "disconnected_002",
        "02_Chapter 2.md",
        "The charter foundation and assembly government are both named.",
        1,
    )
    transition = chunk(
        "transition_003",
        "03_Chapter 3.md",
        "The charter foundation led to an assembly government.",
        2,
    )
    endpoint = chunk(
        "endpoint_004",
        "04_Epilogue.md",
        "The assembly government persisted as a legacy institution.",
        1,
    )
    chunks = [origin, disconnected, transition, endpoint]
    embedded: list[list[str]] = []
    monkeypatch.setattr(
        retrieval,
        "embed_queries",
        lambda queries, embedding_client=None: (
            embedded.append(list(queries))
            or [[float(index)] for index in range(len(queries))]
        ),
    )

    class Collection:
        configuration = {"hnsw": {"space": "l2"}}

        def count(self):
            return len(chunks)

        def query(self, **request):
            value = int(request["query_embeddings"][0][0])
            selected = (
                origin
                if value in {1, 3}
                else endpoint
                if value in {2, 4}
                else transition
            )
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
                        item
                        for item in chunks
                        if item["document"] in allowed
                    )
            return semantic_results([selected])

    requirements = (
        SimpleNamespace(
            requirement_id="R1",
            order=0,
            label="charter foundation",
        ),
        SimpleNamespace(
            requirement_id="R2",
            order=1,
            label="assembly government",
        ),
    )
    broad_plan = SimpleNamespace(
        schema="archivist.question_plan/1",
        traits=("broad_synthesis",),
        facets=(
            facet(
                "F0",
                "original",
                "synthetic institutional history",
                requirement_ids=("R1", "R2"),
            ),
            facet(
                "F1",
                "origin",
                "charter foundation",
                requirement_ids=("R1",),
            ),
            facet(
                "F2",
                "endpoint",
                "assembly government",
                requirement_ids=("R2",),
            ),
        ),
        requirements=requirements,
        planner_used=True,
        fallback_reason=None,
    )

    outcome = retrieve_plan_from_collection(
        broad_plan,
        Collection(),
        chunks,
        max_final_sources=3,
    )

    assert len(embedded[0]) == 6
    assert outcome.broad_transition_chunk_ids == {
        ("F1", "F2"): "transition_003"
    }
    assert outcome.trace["selection"]["transition_coverage_required_count"] == 1
    assert outcome.trace["selection"]["transition_coverage_satisfied_count"] == 1
    assert outcome.trace["selection"]["transition_coverage_shortfall_count"] == 0
    successor_lane = next(
        lane
        for lane in outcome.trace["lanes"]
        if lane["facet_id"] == "F2"
    )
    candidates = {
        item["chunk_id"]: item
        for item in successor_lane["transition_candidates"]
    }
    assert candidates["transition_003"]["eligible"] is True
    assert candidates["transition_003"]["transition_signal_score"] > 0
    assert candidates["disconnected_002"]["eligible"] is False
    assert candidates["disconnected_002"]["eligibility"] == "no_transition_signal"
    assert successor_lane["transition_selected_chunk_ids"] == [
        "transition_003"
    ]
    validate_text_free_retrieval_trace(outcome.trace)


def test_long_lineage_reserves_eight_stage_slots_and_reports_transition_capacity(
    monkeypatch,
):
    stage_terms = (
        "charter alpha",
        "council beta",
        "assembly gamma",
        "treasury delta",
        "bureau epsilon",
        "agency zeta",
        "contractor eta",
        "network theta",
    )
    stage_chunks = [
        chunk(
            f"stage_{index:03}",
            f"{index:02}_Chapter {index}.md",
            (
                f"{stage_terms[index - 1]} established authority and "
                "transformed the synthetic institution."
            ),
            1,
        )
        for index in range(1, 9)
    ]
    bridge_chunks = [
        chunk(
            f"bridge_{index:03}",
            stage_chunks[index]["document"],
            (
                f"{stage_terms[index - 1]} led to {stage_terms[index]} "
                "through an explicit institutional transfer."
            ),
            2,
        )
        for index in range(1, 8)
    ]
    chunks = [
        item
        for pair in zip(stage_chunks, [None, *bridge_chunks], strict=True)
        for item in pair
        if item is not None
    ]
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
            where = request.get("where")
            if where is None:
                selected = chunks
            else:
                document_filter = where["document"]
                allowed = (
                    set(document_filter["$in"])
                    if isinstance(document_filter, dict)
                    else {document_filter}
                )
                selected = [
                    item
                    for item in chunks
                    if item["document"] in allowed
                ]
            return semantic_results(selected)

    def fixed_stage_anchors(
        lane,
        *,
        document_ordinal_by_id,
        chunk_by_id,
        original_query,
        stage_intent_query,
        role,
    ):
        del (
            document_ordinal_by_id,
            chunk_by_id,
            original_query,
            stage_intent_query,
            role,
        )
        stage_index = int(str(lane["facet_id"]).removeprefix("F")) - 1
        selected = stage_chunks[stage_index]
        return [
            {
                "chunk_id": selected["chunk_id"],
                "document": selected["document"],
                "rrf_score": 1.0,
                "stage_anchor_eligible": True,
                "stage_anchor_eligibility": "eligible",
                "stage_intent_match_count": 2,
                "stage_distinctive_intent_match_count": 2,
                "stage_required_distinctive_intent_match_count": 2,
                "stage_role_signal_score": 1,
                "anchor_pool_names": ("canonical", "provider"),
                "anchor_pool_ranks": {"canonical": 1, "provider": 1},
                "anchor_pool_hit_count": 2,
            }
        ]

    def fixed_transition_candidates(
        candidates,
        *,
        chunk_by_id,
        original_query,
        predecessor_intent_query,
        successor_intent_query,
    ):
        del chunk_by_id, original_query, predecessor_intent_query
        successor_index = next(
            index
            for index, term in enumerate(stage_terms[1:], start=1)
            if term in successor_intent_query
        )
        selected = (
            stage_chunks[1]
            if successor_index == 1
            else bridge_chunks[successor_index - 1]
        )
        base = next(
            (
                dict(candidate)
                for candidate in candidates
                if candidate.get("chunk_id") == selected["chunk_id"]
            ),
            {
                "chunk_id": selected["chunk_id"],
                "document": selected["document"],
                "rrf_score": 1.0,
            },
        )
        return [
            {
                **base,
                "transition_eligible": True,
                "transition_eligibility": "eligible",
                "predecessor_intent_match_count": 1,
                "successor_intent_match_count": 1,
                "transition_signal_score": 1,
            }
        ]

    monkeypatch.setattr(
        retrieval,
        "_ranked_broad_stage_anchor_candidates",
        fixed_stage_anchors,
    )
    monkeypatch.setattr(
        retrieval,
        "_ranked_broad_transition_candidates",
        fixed_transition_candidates,
    )
    requirements = tuple(
        SimpleNamespace(
            requirement_id=f"R{index}",
            order=index - 1,
            label=stage_terms[index - 1],
        )
        for index in range(1, 9)
    )
    roles = (
        "origin",
        "transition",
        "mechanism",
        "transition",
        "mechanism",
        "transition",
        "mechanism",
        "endpoint",
    )
    lineage_plan = SimpleNamespace(
        schema="archivist.question_plan/3",
        traits=("broad_synthesis", "long_institutional_lineage"),
        facets=(
            facet(
                "F0",
                "original",
                "synthetic institutional lineage",
                requirement_ids=tuple(f"R{index}" for index in range(1, 9)),
            ),
            *(
                facet(
                    f"F{index}",
                    roles[index - 1],
                    stage_terms[index - 1],
                    document_hints=(stage_chunks[index - 1]["document"],),
                    requirement_ids=(f"R{index}",),
                )
                for index in range(1, 9)
            ),
        ),
        requirements=requirements,
        planner_used=True,
        fallback_reason=None,
    )

    outcome = retrieve_plan_from_collection(
        lineage_plan,
        Collection(),
        chunks,
        max_final_sources=8,
    )

    selection = outcome.trace["selection"]
    assert len(outcome.final_chunks) == 8
    assert set(outcome.broad_stage_anchor_chunk_ids) == {
        f"F{index}" for index in range(1, 9)
    }
    assert selection["stage_coverage_required_count"] == 8
    assert selection["stage_coverage_satisfied_count"] == 8
    assert selection["stage_capacity_shortfall_count"] == 0
    assert selection["transition_coverage_required_count"] == 7
    assert selection["transition_coverage_satisfied_count"] == 1
    assert selection["transition_coverage_shortfall_count"] == 6
    assert selection["transition_extra_source_capacity_count"] == 0
    assert selection["transition_reuse_satisfied_count"] == 1
    assert selection["transition_new_source_satisfied_count"] == 0
    assert selection["transition_capacity_limited_count"] == 6
    assert selection["transition_candidate_shortfall_count"] == 0
    assert selection["transition_selection_shortfall_count"] == 0
    assert outcome.trace["plan"][
        "lineage_stage_required_count"
    ] == 8
    assert outcome.trace["plan"][
        "lineage_stage_planned_count"
    ] == 8
    assert outcome.trace["plan"][
        "lineage_stage_source_capacity_count"
    ] == 8
    assert outcome.trace["parameters"][
        "lineage_stage_contract_version"
    ] == "long-institutional-lineage-v2"
    assert outcome.trace["parameters"][
        "lineage_transition_capacity_policy"
    ] == "reuse-selected-stage-source-before-extra-source"
    lanes = {
        lane["facet_id"]: lane for lane in outcome.trace["lanes"]
    }
    assert [
        (
            lanes[f"F{index}"]["chronology_min_document_ordinal"],
            lanes[f"F{index}"]["chronology_max_document_ordinal"],
        )
        for index in range(1, 9)
    ] == [(index - 1, index - 1) for index in range(1, 9)]
    validate_text_free_retrieval_trace(outcome.trace)


def test_five_noncausal_broad_stages_span_numbered_chapters_through_epilogue(
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
                    (
                        "central power war charter foundation assembly franchise "
                        "fiscal consolidation bureaucracy administration security "
                        "alliance legacy persistence began because finance transformed "
                        f"institutions and persisted stage {index}"
                    ),
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

    stage_labels = (
        "charter foundation",
        "assembly franchise",
        "fiscal consolidation",
        "bureaucracy administration",
        "security alliance legacy",
    )
    requirements = tuple(
        SimpleNamespace(
            requirement_id=f"R{index}",
            order=index - 1,
            label=stage_labels[index - 1],
        )
        for index in range(1, 6)
    )
    facets = (
        SimpleNamespace(
            facet_id="F0",
            role="original",
            search_query="trace central power across the whole history",
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
                search_query=stage_labels[index - 1],
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
        == "consensus_stage_anchor_then_transition_then_global_supplement"
    )
    assert (
        outcome.trace["parameters"]["broad_execution_version"]
        == "broad-stage-narrative-span-v7"
    )
    assert outcome.trace["retrieval_version"] == "faceted-hybrid-rrf-v14"
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
    assert set(outcome.broad_stage_anchor_chunk_ids) == {
        "F1",
        "F2",
        "F3",
        "F4",
        "F5",
    }
    assert all(
        chunk_id == lanes[facet_id]["stage_anchor_selected_chunk_ids"][0]
        for facet_id, chunk_id in (
            outcome.broad_stage_anchor_chunk_ids.items()
        )
    )
    assert all(
        lanes[facet_id]["stage_anchor_consensus_candidates"]
        for facet_id in ("F1", "F2", "F3", "F4", "F5")
    )
    validate_text_free_retrieval_trace(outcome.trace)


def test_six_stage_causal_span_protects_five_body_bands_and_terminal(
    monkeypatch,
):
    documents = [
        "05_Introduction.md",
        *(f"{index + 7:02}_Chapter {index}.md" for index in range(1, 21)),
        "28_Epilogue.md",
    ]
    text = (
        "conflict central power charter taxation mobilization procurement "
        "centralization terminal endpoint began because finance transformed "
        "institutions and persisted"
    )
    chunks = [
        chunk(f"span_{index:03}", document, text, 1)
        for index, document in enumerate(documents)
    ]
    embedding_batches: list[list[str]] = []
    monkeypatch.setattr(
        retrieval,
        "embed_queries",
        lambda queries, embedding_client=None: (
            embedding_batches.append(list(queries))
            or [[float(index)] for index in range(len(queries))]
        ),
    )

    class Collection:
        configuration = {"hnsw": {"space": "l2"}}

        def count(self):
            return len(chunks)

        def query(self, **request):
            where = request.get("where")
            if where is None:
                return semantic_results([chunks[0]])
            document_filter = where["document"]
            selected_documents = (
                set(document_filter["$in"])
                if isinstance(document_filter, dict)
                else {document_filter}
            )
            return semantic_results(
                [
                    item
                    for item in chunks
                    if item["document"] in selected_documents
                ]
            )

    labels = (
        "conflict charter",
        "conflict taxation",
        "conflict mobilization",
        "conflict procurement",
        "conflict centralization",
        "conflict terminal endpoint",
    )
    requirements = tuple(
        SimpleNamespace(
            requirement_id=f"R{index}",
            order=index - 1,
            label=label,
        )
        for index, label in enumerate(labels, start=1)
    )
    stage_roles = (
        "origin",
        "transition",
        "mechanism",
        "transition",
        "mechanism",
        "endpoint",
    )
    hints = (
        (
            "08_Chapter 1.md",
            "05_Introduction.md",
        ),
        ("12_Chapter 5.md",),
        ("16_Chapter 9.md",),
        ("20_Chapter 13.md",),
        ("24_Chapter 17.md",),
        ("28_Epilogue.md",),
    )
    facets = (
        facet(
            "F0",
            "original",
            "How does the book treat conflict as an engine of central power?",
            requirement_ids=tuple(
                requirement.requirement_id for requirement in requirements
            ),
        ),
        *(
            facet(
                f"F{index}",
                role,
                labels[index - 1],
                document_hints=hints[index - 1],
                requirement_ids=(f"R{index}",),
            )
            for index, role in enumerate(stage_roles, start=1)
        ),
    )
    causal_plan = SimpleNamespace(
        schema="archivist.question_plan/3",
        traits=("broad_synthesis",),
        facets=facets,
        requirements=requirements,
        planner_used=True,
        fallback_reason=None,
    )

    outcome = retrieve_plan_from_collection(
        causal_plan,
        Collection(),
        chunks,
        max_final_sources=8,
    )

    assert len(embedding_batches) == 1
    assert set(outcome.broad_stage_anchor_chunk_ids) == {
        "F1",
        "F2",
        "F3",
        "F4",
        "F5",
        "F6",
    }
    anchor_documents = {
        facet_id: next(
            item["document"]
            for item in chunks
            if item["chunk_id"] == chunk_id
        )
        for facet_id, chunk_id in outcome.broad_stage_anchor_chunk_ids.items()
    }
    assert "05_Introduction.md" not in anchor_documents.values()
    assert anchor_documents["F6"] == "28_Epilogue.md"
    assert len(set(anchor_documents.values())) == 6
    assert len(outcome.final_chunks) <= 8
    assert outcome.trace["selection"]["stage_coverage_required_count"] == 6
    assert outcome.trace["selection"]["stage_coverage_satisfied_count"] == 6
    assert (
        outcome.trace["selection"]["transition_extra_source_capacity_count"]
        == 2
    )
    validate_text_free_retrieval_trace(outcome.trace)


def test_six_stage_fallback_reserves_in_core_candidates_before_intent_gate(
    monkeypatch,
):
    documents = [
        "05_Introduction.md",
        *(f"{index + 7:02}_Chapter {index}.md" for index in range(1, 21)),
        "28_Epilogue.md",
    ]
    chunks = [
        chunk(
            f"fallback_{index:03}",
            document,
            (
                "Conflict changed public authority because institutions "
                "financed administration and persisted."
            ),
            1,
        )
        for index, document in enumerate(documents)
    ]
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
            where = request.get("where")
            if where is None:
                return semantic_results([chunks[0]])
            document_filter = where["document"]
            selected_documents = (
                set(document_filter["$in"])
                if isinstance(document_filter, dict)
                else {document_filter}
            )
            return semantic_results(
                [
                    item
                    for item in chunks
                    if item["document"] in selected_documents
                ]
            )

    question = (
        "How does the book treat conflict as an engine of central power?"
    )
    fallback_plan = deterministic_fallback_plan(
        question,
        fallback_reason="invalid_planner_output",
    )

    outcome = retrieve_plan_from_collection(
        fallback_plan,
        Collection(),
        chunks,
        max_final_sources=8,
    )

    lanes = {
        lane["facet_id"]: lane
        for lane in outcome.trace["lanes"]
        if lane["facet_id"] != "F0"
    }
    assert set(outcome.broad_stage_anchor_chunk_ids) == {
        f"F{index}" for index in range(1, 7)
    }
    assert all(
        lanes[facet_id]["stage_anchor_selected_chunk_ids"]
        for facet_id in lanes
    )
    assert any(
        not candidate["eligible"]
        for lane in lanes.values()
        for candidate in lane["stage_anchor_consensus_candidates"]
        if candidate["chunk_id"]
        in lane["stage_anchor_selected_chunk_ids"]
    )
    assert outcome.trace["selection"]["canonical_core_required_count"] == 6
    assert outcome.trace["selection"]["canonical_core_satisfied_count"] == 6
    assert outcome.trace["selection"]["canonical_core_shortfall_count"] == 0
    assert (
        outcome.trace["selection"]["transition_extra_source_capacity_count"]
        == 2
    )
    validate_text_free_retrieval_trace(outcome.trace)


def test_empty_fallback_structural_core_stops_optional_global_fill(
    monkeypatch,
):
    documents = [
        *(f"{index:02}_Chapter {index}.md" for index in range(1, 5)),
        "05_Epilogue.md",
    ]
    chunks = [
        chunk(
            f"sparse_{index:03}",
            document,
            (
                "Conflict changed public authority because institutions "
                "financed administration and persisted."
            ),
            1,
        )
        for index, document in enumerate(documents)
    ]
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
            where = request.get("where")
            if where is None:
                return semantic_results(chunks)
            document_filter = where["document"]
            selected_documents = (
                set(document_filter["$in"])
                if isinstance(document_filter, dict)
                else {document_filter}
            )
            return semantic_results(
                [
                    item
                    for item in chunks
                    if item["document"] in selected_documents
                ]
            )

    fallback_plan = deterministic_fallback_plan(
        "How does the book treat conflict as an engine of central power?",
        fallback_reason="invalid_planner_output",
    )

    outcome = retrieve_plan_from_collection(
        fallback_plan,
        Collection(),
        chunks,
        max_final_sources=8,
    )

    selection = outcome.trace["selection"]
    assert selection["canonical_core_required_count"] == 6
    assert selection["canonical_core_satisfied_count"] == 5
    assert selection["canonical_core_shortfall_count"] == 1
    assert selection["stage_coverage_shortfall_count"] == 1
    assert selection["transition_extra_source_capacity_count"] == 0
    assert len(outcome.broad_stage_anchor_chunk_ids) == 5
    assert len(outcome.final_chunks) == 5
    missing_lane = next(
        lane
        for lane in outcome.trace["lanes"]
        if not lane.get("stage_anchor_consensus_candidates")
        and lane["facet_id"] != "F0"
    )
    assert missing_lane["stage_anchor_selected_chunk_ids"] == []
    validate_text_free_retrieval_trace(outcome.trace)


def test_broad_stage_consensus_uses_provider_agreement_deterministically(
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

    stage_markers = tuple(core_by_position)
    requirements = tuple(
        SimpleNamespace(
            requirement_id=f"R{index}",
            order=index - 1,
            label=stage_markers[index - 1],
        )
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
    selected_anchor_ids = [
        tuple(
            lane_map[f"F{index}"]["stage_anchor_selected_chunk_ids"][0]
            for index in range(1, 6)
        )
        for lane_map in lane_maps
    ]

    for outcome, lane_map, selected_ids in zip(
        outcomes,
        lane_maps,
        selected_anchor_ids,
        strict=True,
    ):
        assert {
            item["chunk_id"] for item in outcome.final_chunks
        }.issuperset(selected_ids)
        for index, selected_id in enumerate(selected_ids, start=1):
            diagnostics = lane_map[f"F{index}"][
                "stage_anchor_consensus_candidates"
            ]
            assert diagnostics[0]["chunk_id"] == selected_id
            assert diagnostics[0]["pool_hit_count"] == max(
                candidate["pool_hit_count"] for candidate in diagnostics
            )
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


def test_origin_anchor_rejects_three_route_consensus_without_role_signal(
    monkeypatch,
):
    generic = chunk(
        "generic_001",
        "01_Chapter 1.md",
        "Charter compact conflict expanded authority across the region.",
        1,
    )
    mechanism = chunk(
        "mechanism_001",
        "01_Chapter 1.md",
        (
            "Conflict expanded authority because finance enabled an "
            "administrative institution, established a charter compact, "
            "and created a precedent."
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
                "charter compact conflict",
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

    assert origin_lane["stage_anchor_selected_chunk_ids"] == ["mechanism_001"]
    diagnostics = origin_lane["stage_anchor_consensus_candidates"]
    assert diagnostics[0]["chunk_id"] == "mechanism_001"
    assert diagnostics[0]["eligible"] is True
    assert diagnostics[0]["eligibility"] == "eligible"
    assert diagnostics[0]["distinctive_intent_match_count"] == 2
    assert diagnostics[0]["required_distinctive_intent_match_count"] == 2
    assert diagnostics[0]["pool_names"] == ["canonical", "mechanism"]
    assert diagnostics[0]["pool_hit_count"] == 2
    assert diagnostics[1]["chunk_id"] == "generic_001"
    assert diagnostics[1]["eligible"] is False
    assert diagnostics[1]["eligibility"] == "no_role_signal"
    assert diagnostics[1]["pool_hit_count"] == 3
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


def test_broad_stage_anchor_prefers_two_pool_consensus_over_canonical_singleton():
    canonical = {
        "chunk_id": "canonical_001",
        "document": "early.md",
        "rrf_score": 1.0,
    }
    consensus = {
        "chunk_id": "consensus_001",
        "document": "middle.md",
        "rrf_score": 0.01,
    }
    ranked = retrieval._ranked_broad_stage_anchor_candidates(
        {
            "canonical_core_candidates": [canonical],
            "mechanism_candidates": [consensus],
            "candidates": [consensus],
        },
        document_ordinal_by_id={"early.md": 1, "middle.md": 2},
        chunk_by_id={
            "canonical_001": {"text": "The stage was established as a precedent."},
            "consensus_001": {"text": "The stage was established as a precedent."},
        },
        original_query="stage",
        stage_intent_query="stage precedent",
        role="origin",
    )

    assert ranked[0]["chunk_id"] == "consensus_001"
    assert ranked[0]["anchor_pool_names"] == ("mechanism", "provider")
    assert ranked[0]["anchor_pool_hit_count"] == 2
    assert ranked[1]["chunk_id"] == "canonical_001"


def test_stage_intent_eligibility_beats_higher_consensus_for_wrong_subproblem():
    wrong_consensus = {
        "chunk_id": "wrong_001",
        "document": "middle.md",
        "rrf_score": 10.0,
    }
    intended_singleton = {
        "chunk_id": "intended_001",
        "document": "later.md",
        "rrf_score": 0.01,
    }

    ranked = retrieval._ranked_broad_stage_anchor_candidates(
        {
            "canonical_core_candidates": [
                wrong_consensus,
                intended_singleton,
            ],
            "mechanism_candidates": [wrong_consensus],
            "candidates": [wrong_consensus],
        },
        document_ordinal_by_id={"middle.md": 1, "later.md": 2},
        chunk_by_id={
            "wrong_001": {
                "text": (
                    "Colonial authority changed because trade financed "
                    "an administrative institution."
                )
            },
            "intended_001": {
                "text": (
                    "Federal corporate consolidation changed authority "
                    "because debt financed institutions."
                )
            },
        },
        original_query="war and central power",
        stage_intent_query="federal corporate consolidation",
        role="transition",
    )

    assert ranked[0]["chunk_id"] == "intended_001"
    assert ranked[0]["stage_anchor_eligible"] is True
    assert ranked[0]["anchor_pool_hit_count"] == 1
    assert ranked[1]["chunk_id"] == "wrong_001"
    assert ranked[1]["stage_anchor_eligible"] is False
    assert (
        ranked[1]["stage_anchor_eligibility"]
        == "insufficient_distinctive_stage_anchor_match"
    )
    assert ranked[1]["anchor_pool_hit_count"] == 3


def test_lineage_stage_anchor_must_support_bearer_and_handoff_role():
    correct = {
        "chunk_id": "correct_001",
        "document": "procurement.md",
        "rrf_score": 0.1,
    }
    generic = {
        "chunk_id": "generic_001",
        "document": "procurement.md",
        "rrf_score": 10.0,
    }
    handoff = SimpleNamespace(
        bearer="Federal Procurement Bureau",
        inherited_capacity="national fiscal capacity",
        transfer_mechanism="contracts transform fiscal power",
        outgoing_capacity="contractor command capacity",
    )

    ranked = retrieval._ranked_broad_stage_anchor_candidates(
        {
            "canonical_core_candidates": [generic, correct],
            "mechanism_candidates": [generic, correct],
            "candidates": [generic, correct],
            "institutional_handoff": handoff,
        },
        document_ordinal_by_id={"procurement.md": 1},
        chunk_by_id={
            "generic_001": {
                "text": (
                    "Authority changed through an administrative institution."
                )
            },
            "correct_001": {
                "text": (
                    "The Federal Procurement Bureau inherited national fiscal "
                    "capacity and transformed it through contracts into "
                    "contractor command capacity."
                )
            },
        },
        original_query="trace institutional lineage",
        stage_intent_query=(
            "Federal Procurement Bureau national fiscal capacity contracts "
            "contractor command capacity"
        ),
        role="mechanism",
    )

    assert ranked[0]["chunk_id"] == "correct_001"
    assert ranked[0]["stage_anchor_eligible"] is True
    assert ranked[1]["chunk_id"] == "generic_001"
    assert ranked[1]["stage_anchor_eligible"] is False
    assert ranked[1]["stage_anchor_eligibility"] in {
        "insufficient_distinctive_stage_anchor_match",
        "no_institutional_bearer_match",
    }


def test_lineage_transition_requires_both_bearers_and_shared_capacity():
    candidates = (
        {
            "chunk_id": "generic_001",
            "document": "handoff.md",
            "rrf_score": 10.0,
            "rank": 1,
        },
        {
            "chunk_id": "linked_002",
            "document": "handoff.md",
            "rrf_score": 0.1,
            "rank": 2,
        },
    )
    ranked = retrieval._ranked_broad_transition_candidates(
        candidates,
        chunk_by_id={
            "generic_001": {
                "text": (
                    "Federal procurement authority transformed into a later "
                    "administrative capacity."
                )
            },
            "linked_002": {
                "text": (
                    "The National Treasury transferred federal procurement "
                    "authority to the Federal Procurement Bureau, which thereby "
                    "converted it into contractor command capacity."
                )
            },
        },
        original_query="trace institutional lineage from Alpha to Omega",
        predecessor_intent_query=(
            "National Treasury national fiscal capacity transfers federal "
            "procurement authority"
        ),
        successor_intent_query=(
            "Federal Procurement Bureau inherits federal procurement authority "
            "through contracts into contractor command capacity"
        ),
    )

    assert ranked[0]["chunk_id"] == "linked_002"
    assert ranked[0]["transition_eligible"] is True
    assert ranked[1]["chunk_id"] == "generic_001"
    assert ranked[1]["transition_eligible"] is False


def test_no_role_eligible_stage_anchor_leaves_an_observable_shortfall(
    monkeypatch,
):
    wrong = chunk(
        "wrong_001",
        "middle.md",
        (
            "Colonial authority changed because trade financed an "
            "administrative institution."
        ),
        1,
    )
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
            return 1

        def query(self, **request):
            return semantic_results([wrong])

    outcome = retrieve_plan_from_collection(
        plan(
            facet("F0", "original", "war and central power"),
            facet(
                "F1",
                "transition",
                "federal corporate consolidation",
            ),
            traits=("broad_synthesis",),
        ),
        Collection(),
        [wrong],
        max_final_sources=1,
    )

    lane = next(
        item for item in outcome.trace["lanes"] if item["facet_id"] == "F1"
    )
    assert lane["stage_anchor_selected_chunk_ids"] == []
    assert lane["stage_anchor_consensus_candidates"][0]["eligible"] is False
    assert (
        lane["stage_anchor_consensus_candidates"][0]["eligibility"]
        == "insufficient_distinctive_stage_anchor_match"
    )
    assert outcome.broad_stage_anchor_chunk_ids == {}
    assert outcome.trace["selection"]["stage_coverage_satisfied_count"] == 0
    assert outcome.trace["selection"]["stage_coverage_shortfall_count"] == 1
    validate_text_free_retrieval_trace(outcome.trace)


def test_broad_stage_anchor_prefers_three_way_over_two_way_consensus():
    three_way = {
        "chunk_id": "three_way_001",
        "document": "later.md",
        "rrf_score": 0.01,
    }
    two_way = {
        "chunk_id": "two_way_001",
        "document": "earlier.md",
        "rrf_score": 1.0,
    }
    ranked = retrieval._ranked_broad_stage_anchor_candidates(
        {
            "canonical_core_candidates": [two_way, three_way],
            "mechanism_candidates": [three_way, two_way],
            "candidates": [three_way],
        },
        document_ordinal_by_id={"earlier.md": 1, "later.md": 2},
        chunk_by_id={
            "three_way_001": {"text": "The stage was established as a precedent."},
            "two_way_001": {"text": "The stage was established as a precedent."},
        },
        original_query="stage",
        stage_intent_query="stage precedent",
        role="origin",
    )

    assert ranked[0]["chunk_id"] == "three_way_001"
    assert ranked[0]["anchor_pool_names"] == (
        "canonical",
        "mechanism",
        "provider",
    )
    assert ranked[0]["anchor_pool_hit_count"] == 3
    assert ranked[1]["chunk_id"] == "two_way_001"


def test_broad_stage_anchor_uses_canonical_fallback_when_pools_disagree():
    canonical = {
        "chunk_id": "canonical_001",
        "document": "later.md",
        "rrf_score": 0.001,
    }
    mechanism = {
        "chunk_id": "mechanism_001",
        "document": "middle.md",
        "rrf_score": 10.0,
    }
    provider = {
        "chunk_id": "provider_001",
        "document": "early.md",
        "rrf_score": 100.0,
    }
    ranked = retrieval._ranked_broad_stage_anchor_candidates(
        {
            "canonical_core_candidates": [canonical],
            "mechanism_candidates": [mechanism],
            "candidates": [provider],
        },
        document_ordinal_by_id={
            "early.md": 1,
            "middle.md": 2,
            "later.md": 3,
        },
        chunk_by_id={
            "canonical_001": {"text": "The stage was established as a precedent."},
            "mechanism_001": {"text": "The stage was established as a precedent."},
            "provider_001": {"text": "The stage was established as a precedent."},
        },
        original_query="stage",
        stage_intent_query="stage precedent",
        role="origin",
    )

    assert [candidate["chunk_id"] for candidate in ranked] == [
        "canonical_001",
        "mechanism_001",
        "provider_001",
    ]
    assert all(
        candidate["anchor_pool_hit_count"] == 1 for candidate in ranked
    )


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


def test_broad_mechanism_pool_excludes_primary_without_lexical_route():
    semantic_only = chunk(
        "semantic_001",
        "chapter.md",
        "An unrelated background passage.",
        1,
    )
    mechanism = chunk(
        "mechanism_001",
        "chapter.md",
        (
            "Conflict expanded authority because taxation financed a "
            "permanent administrative institution."
        ),
        2,
    )

    candidates, _queries = retrieval._broad_mechanism_candidates(
        "How did conflict expand authority?",
        "transition",
        [semantic_only, mechanism],
        [
            {
                "chunk_id": semantic_only["chunk_id"],
                "document": semantic_only["document"],
                "rrf_score": 1.0,
            }
        ],
    )

    assert [candidate["chunk_id"] for candidate in candidates] == [
        "mechanism_001"
    ]


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
            "schema": "archivist.evidence_coverage_diagnostics/6",
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
