from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

import rag_pipeline
from answer_coverage import (
    EVIDENCE_COVERAGE_SCHEMA,
    INTERPRETIVE_EVIDENCE_COVERAGE_SCHEMA,
    AnswerUnit,
    AnswerUnitRole,
    EvidenceDimension,
    EvidenceDimensionCoverage,
    EvidenceCoverageAnswer,
    EvidenceObligationCoverage,
    EvidenceObligationScope,
    GapReason,
    InterpretiveEvidenceCoverageAnswer,
    InterpretiveMove,
    ObligationLink,
    PremiseDecision,
    PremiseStatus,
    RequirementCoverage,
    RequirementStatus,
)
from perspectives import AnswerVoice, HistoriographicalLens, Worldview
from query_planning import (
    AnswerRequirement,
    DocumentCatalogEntry,
    FacetRole,
    InstitutionalHandoff,
    PlannerAnswerRequirement,
    PlannerQuestionPlan,
    PlannerSearchFacet,
    QuestionPlan,
    ResolvedTurn,
    RouteTrait,
    SearchFacet,
    build_question_plan,
)
from retrieval import PlannedContext, RETRIEVAL_TRACE_SCHEMA
from retrieval_trace_contract import validate_text_free_retrieval_trace
from model_config import GENERATOR_SETTINGS, QUERY_PLANNER_SETTINGS


CHUNK = {
    "chunk_id": "synthetic_001",
    "document": "chapter.md",
    "chapter_title": "Synthetic chapter",
    "paragraph_start": 1,
    "paragraph_end": 1,
    "text": "Project Lumen appears in this synthetic manuscript passage.",
}
MANIFEST_SHA256 = "a" * 64


class Collection:
    configuration = {"hnsw": {"space": "l2"}}

    def __init__(self, count: int = 1):
        self._count = count

    def count(self) -> int:
        return self._count


def corpus_manifest(*chunks: dict) -> dict:
    return {
        "chunks": [
            {
                "chunk_id": chunk["chunk_id"],
                "document": chunk["document"],
                "paragraph_start": chunk["paragraph_start"],
                "paragraph_end": chunk["paragraph_end"],
                "text_sha256": hashlib.sha256(str(chunk["text"]).encode("utf-8")).hexdigest(),
                "char_count": len(str(chunk["text"])),
            }
            for chunk in chunks
        ],
        "store": {"embedded_chunk_count": len(chunks)},
    }


def strict_corpus_manifest(*chunks: dict) -> dict:
    manifest = corpus_manifest(*chunks)
    manifest["chunks_sha256"] = "b" * 64
    manifest["store"] = {
        "embedded_chunk_count": len(chunks),
        "collection_name": "manuscript",
        "hnsw_space": "l2",
        "embedding_model": "text-embedding-3-small",
    }
    return manifest


class StrictCollection(Collection):
    name = "manuscript"
    metadata = {
        "chunks_sha256": "b" * 64,
        "embedding_model": "text-embedding-3-small",
        "hnsw:space": "l2",
    }

    def __init__(
        self,
        *,
        stored_id: str = "synthetic_001",
        stored_text: str = CHUNK["text"],
    ):
        super().__init__(count=1)
        self.stored_id = stored_id
        self.stored_text = stored_text

    def get(self, *, include):
        assert include == ["metadatas"]
        return {
            "ids": [self.stored_id],
            "metadatas": [
                {
                    **CHUNK,
                    "chunk_id": self.stored_id,
                    "text": self.stored_text,
                }
            ],
        }


def planned_context(
    plan: QuestionPlan,
    chunks: list[dict],
) -> PlannedContext:
    source_numbers = tuple(range(1, len(chunks) + 1))
    return PlannedContext(
        final_chunks=chunks,
        facet_source_numbers={facet.facet_id: source_numbers for facet in plan.facets},
        trace={
            "schema": RETRIEVAL_TRACE_SCHEMA,
            "plan": {},
            "evidence": {},
            "generation_contract": {},
        },
        lane_by_chunk_id={
            str(chunk["chunk_id"]): tuple(facet.facet_id for facet in plan.facets)
            for chunk in chunks
        },
        broad_stage_anchor_chunk_ids=(
            {
                facet.facet_id: str(chunks[0]["chunk_id"])
                for facet in plan.facets
                if facet.role
                in {
                    FacetRole.ORIGIN,
                    FacetRole.TRANSITION,
                    FacetRole.MECHANISM,
                    FacetRole.ENDPOINT,
                }
            }
            if chunks
            else {}
        ),
    )


def two_stage_transition_plan() -> QuestionPlan:
    return QuestionPlan(
        traits=(RouteTrait.BROAD_SYNTHESIS,),
        requirements=(
            AnswerRequirement(requirement_id="R1", label="Foundation", order=0),
            AnswerRequirement(requirement_id="R2", label="Successor", order=1),
        ),
        facets=(
            SearchFacet(
                facet_id="F0",
                requirement_ids=("R1", "R2"),
                role=FacetRole.ORIGINAL,
                search_query="Trace Project Lumen from foundation to successor.",
            ),
            SearchFacet(
                facet_id="F1",
                requirement_ids=("R1",),
                role=FacetRole.ORIGIN,
                search_query="Project Lumen charter foundation",
            ),
            SearchFacet(
                facet_id="F2",
                requirement_ids=("R2",),
                role=FacetRole.ENDPOINT,
                search_query="Project Lumen institutional successor",
            ),
        ),
        planner_used=True,
    )


def three_passage_transition_context() -> list[dict]:
    return [
        {
            **CHUNK,
            "chunk_id": "foundation_001",
            "paragraph_start": 1,
            "paragraph_end": 1,
            "text": "Project Lumen began with a synthetic charter foundation.",
        },
        {
            **CHUNK,
            "chunk_id": "successor_002",
            "paragraph_start": 2,
            "paragraph_end": 2,
            "text": "Project Lumen later had a synthetic institutional successor.",
        },
        {
            **CHUNK,
            "chunk_id": "transition_003",
            "paragraph_start": 3,
            "paragraph_end": 3,
            "text": (
                "Project Lumen's charter foundation explicitly enabled its "
                "institutional successor."
            ),
        },
    ]


def transition_planned_context(
    plan: QuestionPlan,
    chunks: list[dict],
) -> PlannedContext:
    return PlannedContext(
        final_chunks=chunks,
        facet_source_numbers={
            "F0": (1, 2, 3),
            "F1": (1,),
            "F2": (2,),
        },
        trace={
            "schema": RETRIEVAL_TRACE_SCHEMA,
            "plan": {},
            "evidence": {},
            "generation_contract": {},
        },
        lane_by_chunk_id={
            str(chunk["chunk_id"]): tuple(
                facet.facet_id for facet in plan.facets
            )
            for chunk in chunks
        },
        broad_stage_anchor_chunk_ids={
            "F1": str(chunks[0]["chunk_id"]),
            "F2": str(chunks[1]["chunk_id"]),
        },
        broad_transition_chunk_ids={
            ("F1", "F2"): str(chunks[2]["chunk_id"]),
        },
    )


def supported_answer(
    requirement_ids: tuple[str, ...],
    *,
    source_number: int = 1,
) -> EvidenceCoverageAnswer:
    unit_ids = tuple(f"U{index}" for index in range(1, len(requirement_ids) + 1))
    return EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=tuple(
            RequirementCoverage(
                requirement_id=requirement_id,
                status=RequirementStatus.SUPPORTED,
                unit_ids=(unit_id,),
                source_numbers=(source_number,),
                gap_reason=GapReason.NONE,
            )
            for requirement_id, unit_id in zip(
                requirement_ids,
                unit_ids,
                strict=True,
            )
        ),
        answer_units=tuple(
            AnswerUnit(
                unit_id=unit_id,
                requirement_ids=(requirement_id,),
                role=AnswerUnitRole.EVENT,
                text=f"Synthetic supported point {index} [Source {source_number}].",
                source_numbers=(source_number,),
                paragraph=index,
            )
            for index, (requirement_id, unit_id) in enumerate(
                zip(requirement_ids, unit_ids, strict=True),
                start=1,
            )
        ),
    )


def supported_interpretive_answer(
    requirement_ids: tuple[str, ...],
    *,
    moves: tuple[InterpretiveMove, ...],
    source_number: int = 1,
) -> InterpretiveEvidenceCoverageAnswer:
    factual = supported_answer(
        requirement_ids,
        source_number=source_number,
    )
    return InterpretiveEvidenceCoverageAnswer(
        schema=INTERPRETIVE_EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=factual.premise_decisions,
        coverage=factual.coverage,
        obligation_coverage=factual.obligation_coverage,
        answer_units=factual.answer_units,
        interpretive_moves=moves,
        interpretive_preface=(
            "Project Lumen deserves recognition as a meaningful achievement. "
            "Project Lumen turns pressure into a proving ground of durable capacity."
        ),
        interpretive_coda=(
            "Project Lumen therefore stands as a meaningful accomplishment."
        ),
    )


def supported_obligation_answer(
    requirement_ids: tuple[str, ...],
    obligation_scopes: tuple[EvidenceObligationScope, ...],
) -> EvidenceCoverageAnswer:
    role_by_dimension = {
        EvidenceDimension.STAGE_DEVELOPMENT: AnswerUnitRole.EVENT,
        EvidenceDimension.CAUSE_OR_ENABLER: AnswerUnitRole.CAUSE,
        EvidenceDimension.MECHANISM: AnswerUnitRole.MECHANISM,
        EvidenceDimension.CONSEQUENCE: AnswerUnitRole.CONSEQUENCE,
        EvidenceDimension.CONTINUITY_OR_CHANGE: AnswerUnitRole.CHRONOLOGY,
        EvidenceDimension.QUALIFICATION: AnswerUnitRole.QUALIFICATION,
        EvidenceDimension.ADJACENT_STAGE_LINK: AnswerUnitRole.CAUSE,
        EvidenceDimension.INSTITUTIONAL_HANDOFF: AnswerUnitRole.MECHANISM,
        EvidenceDimension.SUBJECT_OR_DEFINITION: AnswerUnitRole.IDENTITY,
        EvidenceDimension.ACTION_OR_MECHANISM: AnswerUnitRole.MECHANISM,
        EvidenceDimension.SIGNIFICANCE_OR_CONSEQUENCE: (
            AnswerUnitRole.CONSEQUENCE
        ),
        EvidenceDimension.QUALIFICATION_OR_COUNTERARGUMENT: (
            AnswerUnitRole.QUALIFICATION
        ),
    }
    units: list[AnswerUnit] = []
    obligation_coverage: list[EvidenceObligationCoverage] = []
    for scope in obligation_scopes:
        dimension_coverage: list[EvidenceDimensionCoverage] = []
        for dimension in scope.dimension_ids:
            unit_id = f"U{len(units) + 1}"
            units.append(
                AnswerUnit(
                    unit_id=unit_id,
                    requirement_ids=scope.allowed_requirement_ids,
                    role=role_by_dimension[dimension],
                    text=(
                        f"Synthetic obligation point {len(units) + 1} "
                        f"[Source {scope.source_number}]."
                    ),
                    source_numbers=(scope.source_number,),
                    paragraph=len(units) + 1,
                    obligation_links=(
                        ObligationLink(
                            obligation_id=scope.obligation_id,
                            dimension=dimension,
                        ),
                    ),
                )
            )
            dimension_coverage.append(
                EvidenceDimensionCoverage(
                    dimension=dimension,
                    status=RequirementStatus.SUPPORTED,
                    unit_ids=(unit_id,),
                    source_numbers=(scope.source_number,),
                    gap_reason=GapReason.NONE,
                )
            )
        obligation_coverage.append(
            EvidenceObligationCoverage(
                obligation_id=scope.obligation_id,
                dimensions=tuple(dimension_coverage),
            )
        )

    coverage = []
    for requirement_id in requirement_ids:
        mapped_units = tuple(
            unit for unit in units if requirement_id in unit.requirement_ids
        )
        coverage.append(
            RequirementCoverage(
                requirement_id=requirement_id,
                status=RequirementStatus.SUPPORTED,
                unit_ids=tuple(unit.unit_id for unit in mapped_units),
                source_numbers=tuple(
                    dict.fromkeys(
                        source_number
                        for unit in mapped_units
                        for source_number in unit.source_numbers
                    )
                ),
                gap_reason=GapReason.NONE,
            )
        )

    return EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=tuple(coverage),
        obligation_coverage=tuple(obligation_coverage),
        answer_units=tuple(units),
    )


def install_planned_retrieval(monkeypatch, chunks: list[dict]) -> None:
    def fake_retrieve(plan, *_args, **_kwargs):
        return planned_context(plan, chunks)

    monkeypatch.setattr(
        rag_pipeline,
        "retrieve_plan_from_collection",
        fake_retrieve,
    )
    monkeypatch.setattr(rag_pipeline, "emit_retrieval_trace", lambda _trace: None)


def test_evidence_coverage_prompt_requires_atomic_terminal_citations():
    instructions = " ".join(rag_pipeline.EVIDENCE_COVERAGE_INSTRUCTIONS.split())

    assert rag_pipeline.EVIDENCE_COVERAGE_PROMPT_VERSION == "evidence-coverage-v9"
    assert "exactly one independently checkable factual claim" in instructions
    assert "exactly one terminal citation group" in instructions
    assert "every listed source independently supports" in instructions
    assert "split them into separate answer" in instructions
    assert "spell them out or rephrase" in instructions
    assert "have no requirement IDs" in instructions
    assert "correction unit never satisfies an answer requirement" in instructions
    assert "framing candidate sources" in instructions
    assert "positive replacement chronology" in instructions
    assert "inspection_passages" in instructions
    assert "synthesis_obligations" in instructions
    assert "Inspect every inspection passage in order" in instructions
    assert "do not create an answer unit merely to prove" in instructions
    assert "cite only that obligation's single source" in instructions
    assert "do not infer a link merely because" in instructions
    assert "cite only source_number, never predecessor_source_number" in instructions
    assert "requirement_component" in instructions
    assert "dedicated transition passage" in instructions
    assert "orientation_only" in instructions
    assert "not manuscript evidence" in instructions
    assert "institutional_handoff" in instructions
    assert "required for that requirement is supported" in instructions


def test_broad_inspection_and_anchor_obligations_have_distinct_jobs():
    requirements = (
        AnswerRequirement(requirement_id="R1", label="Origin", order=0),
        AnswerRequirement(requirement_id="R2", label="Endpoint", order=1),
    )
    plan = QuestionPlan(
        traits=(RouteTrait.BROAD_SYNTHESIS,),
        requirements=requirements,
        facets=(
            SearchFacet(
                facet_id="F0",
                requirement_ids=("R1", "R2"),
                role=FacetRole.ORIGINAL,
                search_query="Trace a synthetic development.",
            ),
            SearchFacet(
                facet_id="F1",
                requirement_ids=("R1",),
                role=FacetRole.ORIGIN,
                search_query="synthetic origin",
            ),
            SearchFacet(
                facet_id="F2",
                requirement_ids=("R2",),
                role=FacetRole.ENDPOINT,
                search_query="synthetic endpoint",
            ),
        ),
    )
    chunks = [
        {
            **CHUNK,
            "chunk_id": "synthetic_origin",
            "paragraph_start": 10,
            "paragraph_end": 11,
            "text": "First synthetic paragraph.\n\nSecond synthetic paragraph.",
        },
        {
            **CHUNK,
            "chunk_id": "synthetic_endpoint",
            "paragraph_start": 20,
            "paragraph_end": 22,
            "text": "Metadata mismatch safely becomes one source-wide scope.",
        },
    ]

    inspection_scopes = rag_pipeline._evidence_inspection_scopes(
        plan,
        chunks,
        {
            "F0": (1, 2),
            "F1": (1,),
            "F2": (2,),
        },
    )

    assert [
        (
            scope.inspection_id,
            scope.source_number,
            scope.paragraph_start,
            scope.paragraph_end,
            scope.allowed_requirement_ids,
            scope.focus.value,
        )
        for scope in inspection_scopes
    ] == [
        (
            "I1",
            1,
            10,
            10,
            ("R1",),
            "origin",
        ),
        (
            "I2",
            1,
            11,
            11,
            ("R1",),
            "origin",
        ),
        (
            "I3",
            2,
            20,
            22,
            ("R2",),
            "endpoint",
        ),
    ]
    obligation_scopes = rag_pipeline._evidence_obligation_scopes(
        plan,
        chunks,
        {"F1": 1, "F2": 2},
        {("F1", "F2"): 2},
    )
    assert [
        (
            scope.obligation_id,
            scope.kind.value,
            scope.source_number,
            scope.predecessor_source_number,
            scope.paragraph_start,
            scope.paragraph_end,
            scope.allowed_requirement_ids,
            scope.focus.value,
            tuple(dimension.value for dimension in scope.dimension_ids),
        )
        for scope in obligation_scopes
    ] == [
        (
            "O1",
            "stage",
            1,
            None,
            10,
            11,
            ("R1",),
            "origin",
            ("cause_or_enabler", "stage_development"),
        ),
        (
            "O2",
            "stage",
            2,
            None,
            20,
            22,
            ("R2",),
            "endpoint",
            ("continuity_or_change", "consequence", "qualification"),
        ),
        (
            "O3",
            "adjacent_stage_link",
            2,
            1,
            20,
            22,
            ("R1", "R2"),
            "endpoint",
            ("adjacent_stage_link",),
        ),
    ]
    assert all(
        scope.required_for_requirement_status for scope in obligation_scopes
    )


def test_focused_material_components_bind_distinct_answer_layers_to_sources():
    plan = QuestionPlan(
        requirements=(
            AnswerRequirement(
                requirement_id="R1",
                label="Project Lumen",
                order=0,
            ),
        ),
        facets=(
            SearchFacet(
                facet_id="F0",
                requirement_ids=("R1",),
                role=FacetRole.ORIGINAL,
                search_query="What was Project Lumen and what did it do?",
            ),
        ),
    )
    chunks = [
        {
            **CHUNK,
            "chunk_id": "identity_001",
            "paragraph_start": 1,
            "paragraph_end": 1,
            "text": "Project Lumen was a synthetic civic network.",
        },
        {
            **CHUNK,
            "chunk_id": "action_002",
            "paragraph_start": 2,
            "paragraph_end": 2,
            "text": "Project Lumen organized local synthetic councils.",
        },
        {
            **CHUNK,
            "chunk_id": "significance_003",
            "paragraph_start": 3,
            "paragraph_end": 3,
            "text": "Project Lumen thereby expanded synthetic civic capacity.",
        },
        {
            **CHUNK,
            "chunk_id": "qualification_004",
            "paragraph_start": 4,
            "paragraph_end": 4,
            "text": "However, Project Lumen did not reach every district.",
        },
    ]

    scopes = rag_pipeline._focused_requirement_component_scopes(
        plan,
        chunks,
        {"F0": (1, 2, 3, 4)},
    )

    assert [
        (
            scope.kind.value,
            scope.source_number,
            scope.allowed_requirement_ids,
            tuple(dimension.value for dimension in scope.dimension_ids),
        )
        for scope in scopes
    ] == [
        ("requirement_component", 1, ("R1",), ("subject_or_definition",)),
        ("requirement_component", 2, ("R1",), ("action_or_mechanism",)),
        (
            "requirement_component",
            3,
            ("R1",),
            ("significance_or_consequence",),
        ),
        (
            "requirement_component",
            4,
            ("R1",),
            ("qualification_or_counterargument",),
        ),
    ]


def test_focused_component_pass_does_not_expand_a_single_detected_layer():
    plan = QuestionPlan(
        requirements=(
            AnswerRequirement(
                requirement_id="R1",
                label="Project Lumen",
                order=0,
            ),
        ),
        facets=(
            SearchFacet(
                facet_id="F0",
                requirement_ids=("R1",),
                role=FacetRole.ORIGINAL,
                search_query="What was Project Lumen?",
            ),
        ),
    )

    scopes = rag_pipeline._focused_requirement_component_scopes(
        plan,
        [
            {
                **CHUNK,
                "text": "Project Lumen was a synthetic civic network.",
            }
        ],
        {"F0": (1,)},
    )

    assert scopes == ()


def test_adjacent_obligation_uses_the_dedicated_transition_source():
    plan = QuestionPlan(
        traits=(RouteTrait.BROAD_SYNTHESIS,),
        requirements=(
            AnswerRequirement(requirement_id="R1", label="Origin", order=0),
            AnswerRequirement(requirement_id="R2", label="Endpoint", order=1),
        ),
        facets=(
            SearchFacet(
                facet_id="F0",
                requirement_ids=("R1", "R2"),
                role=FacetRole.ORIGINAL,
                search_query="Trace a synthetic development.",
            ),
            SearchFacet(
                facet_id="F1",
                requirement_ids=("R1",),
                role=FacetRole.ORIGIN,
                search_query="charter foundation",
            ),
            SearchFacet(
                facet_id="F2",
                requirement_ids=("R2",),
                role=FacetRole.ENDPOINT,
                search_query="assembly government",
            ),
        ),
    )
    chunks = [
        {
            **CHUNK,
            "chunk_id": "origin_001",
            "paragraph_start": 1,
            "paragraph_end": 1,
        },
        {
            **CHUNK,
            "chunk_id": "endpoint_002",
            "paragraph_start": 2,
            "paragraph_end": 2,
        },
        {
            **CHUNK,
            "chunk_id": "transition_003",
            "paragraph_start": 30,
            "paragraph_end": 31,
            "text": "Synthetic transition paragraph one.\n\nParagraph two.",
        },
    ]

    scopes = rag_pipeline._evidence_obligation_scopes(
        plan,
        chunks,
        {"F1": 1, "F2": 2},
        {("F1", "F2"): 3},
    )
    link = next(
        scope
        for scope in scopes
        if scope.kind.value == "adjacent_stage_link"
    )

    assert link.source_number == 3
    assert link.predecessor_source_number == 1
    assert (link.paragraph_start, link.paragraph_end) == (30, 31)
    assert link.allowed_requirement_ids == ("R1", "R2")


def test_broad_inspection_scope_cap_coalesces_without_omitting_any_source_range():
    requirements = (
        AnswerRequirement(requirement_id="R1", label="Development", order=0),
    )
    plan = QuestionPlan(
        traits=(RouteTrait.BROAD_SYNTHESIS,),
        requirements=requirements,
        facets=(
            SearchFacet(
                facet_id="F0",
                requirement_ids=("R1",),
                role=FacetRole.ORIGINAL,
                search_query="Trace a synthetic development.",
            ),
            SearchFacet(
                facet_id="F1",
                requirement_ids=("R1",),
                role=FacetRole.TRANSITION,
                search_query="synthetic transition",
            ),
        ),
    )
    chunks = [
        {
            **CHUNK,
            "chunk_id": f"synthetic_{source_number}",
            "paragraph_start": (source_number * 10) + 1,
            "paragraph_end": (source_number * 10) + 10,
            "text": "\n\n".join(
                f"Synthetic paragraph {paragraph_number}."
                for paragraph_number in range(1, 11)
            ),
        }
        for source_number in range(1, 9)
    ]

    scopes = rag_pipeline._evidence_inspection_scopes(
        plan,
        chunks,
        {
            "F0": tuple(range(1, 9)),
            "F1": tuple(range(1, 9)),
        },
    )

    assert len(scopes) == rag_pipeline.MAX_BROAD_INSPECTION_SCOPES
    for source_number, chunk in enumerate(chunks, start=1):
        source_scopes = [
            scope for scope in scopes if scope.source_number == source_number
        ]
        assert source_scopes[0].paragraph_start == chunk["paragraph_start"]
        assert source_scopes[-1].paragraph_end == chunk["paragraph_end"]
        assert all(
            left.paragraph_end + 1 == right.paragraph_start
            for left, right in zip(source_scopes, source_scopes[1:])
        )


def test_broad_obligation_range_cap_can_reserve_answer_units_for_premises():
    chunks = [
        {
            **CHUNK,
            "chunk_id": f"synthetic_{source_number}",
            "paragraph_start": (source_number * 10) + 1,
            "paragraph_end": (source_number * 10) + 10,
            "text": "\n\n".join(
                f"Synthetic paragraph {paragraph_number}."
                for paragraph_number in range(1, 11)
            ),
        }
        for source_number in range(1, 9)
    ]

    ranges = rag_pipeline._bounded_obligation_ranges(
        chunks,
        max_obligations=30,
    )

    assert sum(len(source_ranges) for source_ranges in ranges) == 30
    assert all(source_ranges for source_ranges in ranges)


def test_focused_question_uses_no_planner_and_one_structured_answer(monkeypatch):
    install_planned_retrieval(monkeypatch, [CHUNK])
    calls: list[dict] = []

    def fake_parse(_client, *, operation, **request):
        calls.append({"operation": operation, **request})
        return SimpleNamespace(
            output_parsed=supported_answer(("R1",)),
            output=(),
        )

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question="Who was Project Lumen?",
            entities=("Project Lumen",),
            trusted_user_texts=("Who was Project Lumen?",),
        ),
        collection_handle=Collection(),
        chunks=[CHUNK],
        client=object(),
        corpus_manifest=corpus_manifest(CHUNK),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert [call["operation"] for call in calls] == ["answer_generation"]
    assert result.status == "answered"
    assert result.answer == "Synthetic supported point 1 [Source 1]."
    assert result.final_chunks == [CHUNK]
    assert calls[0]["text_format"] is EvidenceCoverageAnswer
    assert "Project Lumen" in calls[0]["input"]
    assert {
        key: calls[0][key] for key in ("model", "reasoning", "text")
    } == GENERATOR_SETTINGS.responses_create_kwargs()
    run_diagnostics = rag_pipeline.answer_run_diagnostics(result)
    assert run_diagnostics["validation_result"] == "valid"
    assert run_diagnostics["validation_error_code"] is None
    assert run_diagnostics["planner"] == {
        "schema": "archivist.planner_call_diagnostics/2",
        "status": "not_called",
        "failure_code": None,
        "planner_validation_code": None,
        "exception_class": None,
        "exception_code": None,
    }
    assert {
        "corpus_integrity",
        "query_planning",
        "retrieval",
        "evidence_gate",
        "context_preparation",
        "answer_generation",
        "answer_validation",
        "pipeline_total",
    }.issubset(run_diagnostics["stage_timings_ms"])
    assert all(value >= 0 for value in run_diagnostics["stage_timings_ms"].values())


@pytest.mark.parametrize(
    ("lens", "worldview", "move"),
    [
        (
            HistoriographicalLens.TRAGIC,
            Worldview.NONE,
            InterpretiveMove.TRAGIC_TENSION_AND_CONTINGENCY,
        ),
        (
            HistoriographicalLens.EVIDENCE_FIRST,
            Worldview.PIOUS,
            InterpretiveMove.FAITH_DUTY_AND_MORAL_CONSEQUENCE,
        ),
    ],
)
def test_lens_or_worldview_frames_the_evidence_with_subjective_prose(
    monkeypatch,
    lens,
    worldview,
    move,
):
    install_planned_retrieval(monkeypatch, [CHUNK])
    calls: list[dict] = []

    def fake_parse(_client, *, operation, **request):
        calls.append({"operation": operation, **request})
        return SimpleNamespace(
            output_parsed=supported_interpretive_answer(
                ("R1",),
                moves=(move,),
            ),
            output=(),
        )

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question="Who was Project Lumen?",
            trusted_user_texts=("Who was Project Lumen?",),
        ),
        collection_handle=Collection(),
        chunks=[CHUNK],
        client=object(),
        corpus_manifest=corpus_manifest(CHUNK),
        corpus_manifest_sha256=MANIFEST_SHA256,
        historiographical_lens=lens,
        worldview=worldview,
    )

    assert result.status == "answered"
    assert result.answer == (
        "Project Lumen deserves recognition as a meaningful achievement. "
        "Project Lumen turns pressure into a proving ground of durable capacity.\n\n"
        "Synthetic supported point 1 [Source 1].\n\n"
        "Project Lumen therefore stands as a meaningful accomplishment."
    )
    assert calls[0]["text_format"] is InterpretiveEvidenceCoverageAnswer
    assert rag_pipeline.INTERPRETIVE_STRUCTURED_OUTPUT_RULES in calls[0]["input"]
    assert f'"required_moves": [\n      "{move.value}"' in calls[0]["input"]
    assert '"required_question_anchors": [\n      "Project Lumen"' in calls[0]["input"]
    assert '"first_person": "forbidden"' in calls[0]["input"]


def test_voice_alone_keeps_the_ordinary_compact_answer_contract(monkeypatch):
    install_planned_retrieval(monkeypatch, [CHUNK])
    calls: list[dict] = []

    def fake_parse(_client, *, operation, **request):
        calls.append({"operation": operation, **request})
        return SimpleNamespace(
            output_parsed=supported_answer(("R1",)),
            output=(),
        )

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question="Who was Project Lumen?",
            entities=("Project Lumen",),
            trusted_user_texts=("Who was Project Lumen?",),
        ),
        collection_handle=Collection(),
        chunks=[CHUNK],
        client=object(),
        corpus_manifest=corpus_manifest(CHUNK),
        corpus_manifest_sha256=MANIFEST_SHA256,
        voice=AnswerVoice.ROMANTIC,
    )

    assert result.status == "answered"
    assert result.answer == "Synthetic supported point 1 [Source 1]."
    assert calls[0]["text_format"] is EvidenceCoverageAnswer
    assert rag_pipeline.INTERPRETIVE_STRUCTURED_OUTPUT_RULES not in calls[0]["input"]


def test_homepage_relationship_question_decomposes_locally_and_reaches_answer(
    monkeypatch,
):
    install_planned_retrieval(monkeypatch, [CHUNK])
    calls: list[str] = []

    def fake_parse(_client, *, operation, **_request):
        calls.append(operation)
        return SimpleNamespace(
            output_parsed=supported_answer(("R1", "R2", "R3")),
            output=(),
        )

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question="How does the manuscript connect tobacco to labor?",
        ),
        collection_handle=Collection(),
        chunks=[CHUNK],
        client=object(),
        corpus_manifest=corpus_manifest(CHUNK),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert calls == ["answer_generation"]
    assert result.status == "answered"
    assert [facet.search_query for facet in result.plan.facets] == [
        "How does the manuscript connect tobacco to labor?",
        "tobacco context",
        "labor context",
        "tobacco labor connect",
    ]
    assert "Synthetic supported point 3" in result.answer


def test_resolved_between_relationship_context_does_not_call_the_planner(
    monkeypatch,
):
    relationship_chunk = {
        **CHUNK,
        "text": ("Project Lumen and Harbor Network shaped civic exchange in Port Delta."),
    }
    install_planned_retrieval(monkeypatch, [relationship_chunk])
    calls: list[str] = []

    def fake_parse(_client, *, operation, **_request):
        calls.append(operation)
        return SimpleNamespace(
            output_parsed=supported_answer(("R1", "R2", "R3")),
            output=(),
        )

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)
    question = (
        "How did the manuscript describe the relationship between Project Lumen "
        "and Harbor Network as shaping civic exchange in Port Delta?"
    )

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(standalone_question=question),
        collection_handle=Collection(),
        chunks=[relationship_chunk],
        client=object(),
        corpus_manifest=corpus_manifest(relationship_chunk),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert "query_planning" not in calls
    assert result.diagnostics["planner"]["status"] == "not_called"
    assert result.plan.facets[-1].search_query == (
        "Project Lumen Harbor Network relationship as shaping civic exchange in Port Delta"
    )


def test_directional_resolved_relationship_does_not_call_the_planner(
    monkeypatch,
):
    relationship_chunk = {
        **CHUNK,
        "text": ("Project Lumen and Harbor Network shaped civic exchange in Port Delta."),
    }
    install_planned_retrieval(monkeypatch, [relationship_chunk])
    calls: list[str] = []

    def fake_parse(_client, *, operation, **_request):
        calls.append(operation)
        return SimpleNamespace(
            output_parsed=supported_answer(("R1", "R2", "R3")),
            output=(),
        )

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)
    question = (
        "How did the relationship between Project Lumen and Harbor Network "
        "shape civic exchange in Port Delta?"
    )

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(standalone_question=question),
        collection_handle=Collection(),
        chunks=[relationship_chunk],
        client=object(),
        corpus_manifest=corpus_manifest(relationship_chunk),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert "query_planning" not in calls
    assert result.diagnostics["planner"]["status"] == "not_called"
    assert result.plan.facets[-1].search_query == (
        "Project Lumen Harbor Network relationship shape civic exchange in Port Delta"
    )


def test_document_catalog_uses_bounded_role_tokens_without_sending_passages():
    chunks = [
        {
            **CHUNK,
            "document": "01_Chapter 1.md",
            "chapter_title": "Chapter 1: Chartered Harbor",
            "text": (
                "The Harbor Council and the HCA used a corporate charter and "
                "taxation to administer Asterbridge in 1620."
            ),
        },
        {
            **CHUNK,
            "chunk_id": "synthetic_002",
            "document": "02_Chapter 2.md",
            "chapter_title": "Chapter 2: Naval Office",
            "text": (
                "The Naval Office used procurement and wartime finance "
                "to administer the fleet in 1942."
            ),
        },
    ]

    catalog = rag_pipeline.build_document_catalog(chunks)
    planner_input = rag_pipeline.build_planner_input(
        ResolvedTurn(
            standalone_question="Trace the Harbor administration over time."
        ),
        catalog,
    )
    payload = json.loads(planner_input)

    assert payload["document_role_profile_version"] == "document-role-profile-v1"
    assert "charter" in catalog[0].role_terms
    assert "taxation" in catalog[0].role_terms
    assert "hca" in catalog[0].role_terms
    assert "asterbridge" in catalog[0].role_terms
    assert "1620" in catalog[0].role_terms
    assert "procurement" in catalog[1].role_terms
    assert len(catalog[0].role_terms) <= 48
    assert chunks[0]["text"] not in planner_input
    assert chunks[1]["text"] not in planner_input
    assert payload["eligible_document_catalog"][0]["role_terms"]


def test_complex_question_has_one_planner_call_and_one_answer_call(monkeypatch):
    install_planned_retrieval(monkeypatch, [CHUNK])
    turn = ResolvedTurn(
        standalone_question=("Trace Project Lumen from its origin to its endpoint."),
        entities=("Project Lumen",),
    )
    raw_plan = PlannerQuestionPlan(
        requirements=(
            PlannerAnswerRequirement(
                requirement_id="R1",
                label="Project Lumen origin",
            ),
            PlannerAnswerRequirement(
                requirement_id="R2",
                label="Project Lumen transition",
            ),
            PlannerAnswerRequirement(
                requirement_id="R3",
                label="Project Lumen middle mechanism",
            ),
            PlannerAnswerRequirement(
                requirement_id="R4",
                label="Project Lumen later transition",
            ),
            PlannerAnswerRequirement(
                requirement_id="R5",
                label="Project Lumen endpoint",
            ),
        ),
        facets=(
            PlannerSearchFacet(
                facet_id="F1",
                requirement_ids=("R1",),
                role=FacetRole.ORIGIN,
                search_query="origin Project Lumen",
                document_hints=("chapter.md",),
            ),
            PlannerSearchFacet(
                facet_id="F2",
                requirement_ids=("R2",),
                role=FacetRole.TRANSITION,
                search_query="transition Project Lumen",
                document_hints=("chapter.md",),
            ),
            PlannerSearchFacet(
                facet_id="F3",
                requirement_ids=("R3",),
                role=FacetRole.MECHANISM,
                search_query="middle mechanism Project Lumen",
                document_hints=("chapter.md",),
            ),
            PlannerSearchFacet(
                facet_id="F4",
                requirement_ids=("R4",),
                role=FacetRole.TRANSITION,
                search_query="later transition Project Lumen",
                document_hints=("chapter.md",),
            ),
            PlannerSearchFacet(
                facet_id="F5",
                requirement_ids=("R5",),
                role=FacetRole.ENDPOINT,
                search_query="endpoint Project Lumen",
                document_hints=("chapter.md",),
            ),
        ),
    )
    finalized_plan = build_question_plan(turn, raw_plan)
    obligation_scopes = rag_pipeline._evidence_obligation_scopes(
        finalized_plan,
        [CHUNK],
        {
            facet.facet_id: 1
            for facet in finalized_plan.facets
            if facet.role
            in {
                FacetRole.ORIGIN,
                FacetRole.TRANSITION,
                FacetRole.MECHANISM,
                FacetRole.ENDPOINT,
            }
        },
    )
    requirement_ids = tuple(
        requirement.requirement_id for requirement in finalized_plan.requirements
    )
    calls: list[dict] = []

    def fake_parse(_client, *, operation, **request):
        calls.append({"operation": operation, **request})
        parsed = (
                raw_plan
                if operation == "query_planning"
                else supported_obligation_answer(
                    requirement_ids,
                    obligation_scopes,
                )
        )
        return SimpleNamespace(output_parsed=parsed, output=())

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=turn,
        collection_handle=Collection(),
        chunks=[CHUNK],
        client=object(),
        corpus_manifest=corpus_manifest(CHUNK),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert [call["operation"] for call in calls] == [
        "query_planning",
        "answer_generation",
    ]
    assert {
        key: calls[0][key] for key in ("model", "reasoning", "text")
    } == QUERY_PLANNER_SETTINGS.responses_create_kwargs()
    assert calls[0]["text_format"] is PlannerQuestionPlan
    assert calls[0]["max_output_tokens"] == 4_000
    assert '"schema": "archivist.answer_request/6"' in calls[1]["input"]
    assert '"inspection_passages"' in calls[1]["input"]
    assert '"synthesis_obligations"' in calls[1]["input"]
    assert '"evidence_obligations"' not in calls[1]["input"]
    assert result.plan.planner_used is True
    assert result.plan.facets[0].facet_id == "F0"
    assert result.status == "answered"
    assert result.diagnostics["generation"]["inspection_scope_count"] == 1
    assert result.diagnostics["generation"]["obligation_count"] == 5


def test_late_causal_origin_is_repaired_after_one_planner_call(monkeypatch):
    turn = ResolvedTurn(
        standalone_question=(
            "How does the book treat conflict as an engine of central power?"
        ),
    )
    catalog = tuple(
        DocumentCatalogEntry(
            document_id=f"{index:02}_Chapter {index}.md",
            chapter_title=f"Chapter {index}",
            corpus_ordinal=index,
            role_terms=(
                "conflict",
                (
                    "charter"
                    if index == 1
                    else "taxation"
                    if index == 2
                    else "mobilization"
                    if index == 3
                    else "procurement"
                    if index == 4
                    else "centralization"
                    if index == 5
                    else "endpoint"
                ),
            ),
        )
        for index in range(1, 7)
    )
    labels = (
        "Conflict and centralization",
        "Conflict taxation",
        "Conflict mobilization",
        "Conflict procurement",
        "Conflict endpoint",
    )
    roles = (
        FacetRole.ORIGIN,
        FacetRole.TRANSITION,
        FacetRole.MECHANISM,
        FacetRole.TRANSITION,
        FacetRole.ENDPOINT,
    )
    hints = (5, 2, 3, 4, 6)
    proposal = PlannerQuestionPlan(
        requirements=tuple(
            PlannerAnswerRequirement(
                requirement_id=f"R{index}",
                label=label,
            )
            for index, label in enumerate(labels, start=1)
        ),
        facets=tuple(
            PlannerSearchFacet(
                facet_id=f"F{index}",
                requirement_ids=(f"R{index}",),
                role=role,
                search_query=labels[index - 1],
                document_hints=(f"{hint:02}_Chapter {hint}.md",),
            )
            for index, (role, hint) in enumerate(
                zip(roles, hints, strict=True),
                start=1,
            )
        ),
    )
    calls: list[str] = []

    def fake_parse(_client, *, operation, **_request):
        calls.append(operation)
        return SimpleNamespace(output_parsed=proposal, output=())

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)
    diagnostics = {}

    plan = rag_pipeline.plan_question(
        object(),
        turn,
        catalog,
        planner_diagnostics=diagnostics,
    )

    assert calls == ["query_planning"]
    assert plan.planner_used is True
    assert plan.fallback_reason is None
    assert len(plan.requirements) == 5
    assert plan.facets[1].document_hints == (
        "01_Chapter 1.md",
        "05_Chapter 5.md",
    )
    assert tuple(facet.document_hints for facet in plan.facets[2:]) == (
        ("02_Chapter 2.md",),
        ("03_Chapter 3.md",),
        ("04_Chapter 4.md",),
        ("06_Chapter 6.md",),
    )
    assert diagnostics == {
        "schema": "archivist.planner_call_diagnostics/2",
        "status": "succeeded",
        "failure_code": None,
        "planner_validation_code": None,
        "exception_class": None,
        "exception_code": None,
    }


def test_long_institutional_lineage_keeps_all_eight_stage_roles_through_generation(
    monkeypatch,
):
    question = (
        "Trace the institutional lineage from Alpha Consortium to Omega Network."
    )
    stage_specs = (
        (
            "Chartered venture",
            FacetRole.ORIGIN,
            "chartered venture",
            "Alpha Consortium",
        ),
        (
            "Provincial council",
            FacetRole.TRANSITION,
            "provincial council",
            "Provincial Council",
        ),
        (
            "Assembly taxation",
            FacetRole.MECHANISM,
            "assembly taxation",
            "Assembly Tax Authority",
        ),
        (
            "Commonwealth office",
            FacetRole.TRANSITION,
            "commonwealth office",
            "Commonwealth Office",
        ),
        (
            "National treasury",
            FacetRole.MECHANISM,
            "national treasury",
            "National Treasury",
        ),
        (
            "Federal procurement",
            FacetRole.MECHANISM,
            "federal procurement",
            "Federal Procurement Bureau",
        ),
        (
            "Contractor command",
            FacetRole.TRANSITION,
            "contractor command",
            "Contractor Command",
        ),
        (
            "Data center",
            FacetRole.ENDPOINT,
            "data center",
            "Omega Network",
        ),
    )
    capacities = tuple(
        f"synthetic capacity {index}"
        for index in range(1, 10)
    )
    chunks = [
        {
            **CHUNK,
            "chunk_id": f"lineage_{index:03}",
            "document": f"lineage-{index}.md",
            "chapter_title": label,
            "paragraph_start": index,
            "paragraph_end": index,
            "text": (
                f"Alpha Consortium and Omega Network appear in the {query} "
                "stage, which established and transformed synthetic authority."
            ),
        }
        for index, (label, _role, query, _bearer) in enumerate(
            stage_specs,
            start=1,
        )
    ]
    proposal = PlannerQuestionPlan(
        requirements=tuple(
            PlannerAnswerRequirement(
                requirement_id=f"R{index}",
                label=label,
                institutional_handoff=InstitutionalHandoff(
                    bearer=bearer,
                    inherited_capacity=capacities[index - 1],
                    transfer_mechanism=(
                        f"{bearer} transforms synthetic capacity"
                    ),
                    outgoing_capacity=capacities[index],
                ),
            )
            for index, (label, _role, _query, bearer) in enumerate(
                stage_specs,
                start=1,
            )
        ),
        facets=tuple(
            PlannerSearchFacet(
                facet_id=f"F{index}",
                requirement_ids=(f"R{index}",),
                role=role,
                search_query=(
                    f"{'Alpha Consortium' if index <= 4 else 'Omega Network'} "
                    f"{query}"
                ),
                document_hints=(f"lineage-{index}.md",),
            )
            for index, (_label, role, query, _bearer) in enumerate(
                stage_specs,
                start=1,
            )
        ),
    )
    finalized = build_question_plan(
        question,
        proposal,
        rag_pipeline.build_document_catalog(chunks),
    )
    planned = PlannedContext(
        final_chunks=chunks,
        facet_source_numbers={
            "F0": tuple(range(1, 9)),
            **{
                f"F{index}": (index,)
                for index in range(1, 9)
            },
        },
        trace={
            "schema": RETRIEVAL_TRACE_SCHEMA,
            "plan": {},
            "evidence": {},
            "generation_contract": {},
        },
        lane_by_chunk_id={
            str(item["chunk_id"]): ("F0", f"F{index}")
            for index, item in enumerate(chunks, start=1)
        },
        broad_stage_anchor_chunk_ids={
            f"F{index}": str(item["chunk_id"])
            for index, item in enumerate(chunks, start=1)
        },
    )
    obligation_scopes = rag_pipeline._evidence_obligation_scopes(
        finalized,
        chunks,
        {
            f"F{index}": index
            for index in range(1, 9)
        },
    )
    calls: list[str] = []

    monkeypatch.setattr(
        rag_pipeline,
        "retrieve_plan_from_collection",
        lambda *_args, **_kwargs: planned,
    )

    def fake_parse(_client, *, operation, **_request):
        calls.append(operation)
        if operation == "answer_generation":
            assert '"orientation_only"' in _request["input"]
            assert '"bearer": "Alpha Consortium"' in _request["input"]
            assert (
                "planner search orientation only" in _request["input"]
            )
        parsed = (
            proposal
            if operation == "query_planning"
            else supported_obligation_answer(
                tuple(f"R{index}" for index in range(1, 9)),
                obligation_scopes,
            )
        )
        return SimpleNamespace(output_parsed=parsed, output=())

    monkeypatch.setattr(
        rag_pipeline,
        "tracked_responses_parse",
        fake_parse,
    )

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(standalone_question=question),
        collection_handle=Collection(count=8),
        chunks=chunks,
        client=object(),
        corpus_manifest=corpus_manifest(*chunks),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert calls == ["query_planning", "answer_generation"]
    assert result.status == "answered"
    assert result.plan.traits == (
        RouteTrait.BROAD_SYNTHESIS,
        RouteTrait.LONG_INSTITUTIONAL_LINEAGE,
    )
    assert len(result.plan.requirements) == 8
    assert len(result.plan.facets) == 9
    assert result.diagnostics["generation"]["obligation_count"] == 8
    assert {
        scope["allowed_requirement_ids"][0]
        for scope in result.diagnostics["generation"]["obligation_scopes"]
    } == {f"R{index}" for index in range(1, 9)}


def test_pipeline_accepts_a_dedicated_transition_passage(monkeypatch):
    plan = two_stage_transition_plan()
    chunks = three_passage_transition_context()
    planned = transition_planned_context(plan, chunks)
    obligation_scopes = rag_pipeline._evidence_obligation_scopes(
        plan,
        chunks,
        {"F1": 1, "F2": 2},
        {("F1", "F2"): 3},
    )
    calls: list[str] = []

    monkeypatch.setattr(
        rag_pipeline,
        "plan_question",
        lambda *_args, **_kwargs: plan,
    )
    monkeypatch.setattr(
        rag_pipeline,
        "retrieve_plan_from_collection",
        lambda *_args, **_kwargs: planned,
    )
    monkeypatch.setattr(rag_pipeline, "emit_retrieval_trace", lambda _trace: None)

    def fake_parse(_client, *, operation, **_request):
        calls.append(operation)
        return SimpleNamespace(
            output_parsed=supported_obligation_answer(
                ("R1", "R2"),
                obligation_scopes,
            ),
            output=(),
        )

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question=(
                "Trace Project Lumen from foundation to successor."
            ),
        ),
        collection_handle=Collection(count=3),
        chunks=chunks,
        client=object(),
        corpus_manifest=corpus_manifest(*chunks),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert calls == ["answer_generation"]
    assert result.status == "answered"
    link_scope = next(
        scope
        for scope in result.diagnostics["generation"]["obligation_scopes"]
        if scope["kind"] == "adjacent_stage_link"
    )
    assert link_scope["source_number"] == 3
    assert link_scope["predecessor_source_number"] == 1


def test_pipeline_rejects_a_stage_shortfall_before_answer_generation(
    monkeypatch,
):
    plan = two_stage_transition_plan()
    chunks = three_passage_transition_context()
    planned = transition_planned_context(plan, chunks)
    valid_scopes = rag_pipeline._evidence_obligation_scopes(
        plan,
        chunks,
        {"F1": 1, "F2": 2},
        {("F1", "F2"): 3},
    )
    invalid_scopes = (valid_scopes[0], valid_scopes[2])
    calls: list[str] = []
    emitted_trace: dict[str, object] = {}

    monkeypatch.setattr(
        rag_pipeline,
        "plan_question",
        lambda *_args, **_kwargs: plan,
    )
    monkeypatch.setattr(
        rag_pipeline,
        "retrieve_plan_from_collection",
        lambda *_args, **_kwargs: planned,
    )
    monkeypatch.setattr(
        rag_pipeline,
        "_evidence_obligation_scopes",
        lambda *_args, **_kwargs: invalid_scopes,
    )
    monkeypatch.setattr(
        rag_pipeline,
        "emit_retrieval_trace",
        lambda trace: emitted_trace.update(trace),
    )

    def unexpected_parse(_client, *, operation, **_request):
        calls.append(operation)
        raise AssertionError("invalid trusted context reached generation")

    monkeypatch.setattr(
        rag_pipeline,
        "tracked_responses_parse",
        unexpected_parse,
    )

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question=(
                "Trace Project Lumen from foundation to successor."
            ),
        ),
        collection_handle=Collection(count=3),
        chunks=chunks,
        client=object(),
        corpus_manifest=corpus_manifest(*chunks),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert calls == []
    assert result.status == "generation_contract_failed"
    assert (
        result.diagnostics["generation"]["error_code"]
        == "invalid_context"
    )
    assert (
        result.diagnostics["generation"]["structured_generation_called"]
        is False
    )
    assert "answer_generation" not in result.diagnostics["stage_timings_ms"]
    validate_text_free_retrieval_trace(emitted_trace)


def test_semantically_invalid_proposal_is_local_fallback_not_parse_failure(
    monkeypatch,
):
    install_planned_retrieval(monkeypatch, [CHUNK])
    turn = ResolvedTurn(
        standalone_question=("Trace Project Lumen from its origin to its endpoint."),
    )
    emitted_trace: dict[str, object] = {}
    monkeypatch.setattr(
        rag_pipeline,
        "emit_retrieval_trace",
        lambda trace: emitted_trace.update(trace),
    )
    proposal = PlannerQuestionPlan(
        requirements=(
            PlannerAnswerRequirement(
                requirement_id="R1",
                label="Project Lumen origin",
            ),
            PlannerAnswerRequirement(
                requirement_id="R2",
                label="Project Lumen endpoint",
            ),
        ),
        facets=(
            PlannerSearchFacet(
                facet_id="F1",
                requirement_ids=("R1",),
                role=FacetRole.ORIGIN,
                search_query="origin Project Lumen",
            ),
        ),
    )
    finalized_plan = build_question_plan(turn, proposal)
    obligation_scopes = rag_pipeline._evidence_obligation_scopes(
        finalized_plan,
        [CHUNK],
        {
            facet.facet_id: 1
            for facet in finalized_plan.facets
            if facet.role
            in {
                FacetRole.ORIGIN,
                FacetRole.TRANSITION,
                FacetRole.MECHANISM,
                FacetRole.ENDPOINT,
            }
        },
    )
    requirement_ids = tuple(
        requirement.requirement_id for requirement in finalized_plan.requirements
    )
    calls: list[str] = []

    def fake_parse(_client, *, operation, **_request):
        calls.append(operation)
        parsed = (
            proposal
            if operation == "query_planning"
            else supported_obligation_answer(
                requirement_ids,
                obligation_scopes,
            )
        )
        return SimpleNamespace(output_parsed=parsed, output=())

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=turn,
        collection_handle=Collection(),
        chunks=[CHUNK],
        client=object(),
        corpus_manifest=corpus_manifest(CHUNK),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert calls == ["query_planning", "answer_generation"]
    assert result.plan.planner_used is False
    assert result.plan.fallback_reason == "invalid_planner_output"
    assert result.diagnostics["planner"] == {
        "schema": "archivist.planner_call_diagnostics/2",
        "status": "failed",
        "failure_code": "invalid_planner_output",
        "planner_validation_code": "missing_requirement_mapping",
        "exception_class": None,
        "exception_code": None,
    }
    assert emitted_trace["plan"]["planner_call"] == {
        "schema": "archivist.planner_call_diagnostics/2",
        "status": "failed",
        "failure_code": "invalid_planner_output",
        "planner_validation_code": "missing_requirement_mapping",
        "exception_class_sha256": None,
        "exception_code": None,
    }
    validate_text_free_retrieval_trace(emitted_trace)
    assert rag_pipeline.answer_run_diagnostics(result)["planner"] == (result.diagnostics["planner"])


def test_planner_failure_preserves_only_exact_text_free_diagnostics(monkeypatch):
    install_planned_retrieval(monkeypatch, [CHUNK])
    turn = ResolvedTurn(
        standalone_question=("Trace Project Lumen from its origin to its endpoint."),
    )
    finalized_plan = build_question_plan(
        turn,
        None,
        fallback_reason="planner_call_failed",
    )
    obligation_scopes = rag_pipeline._evidence_obligation_scopes(
        finalized_plan,
        [CHUNK],
        {
            facet.facet_id: 1
            for facet in finalized_plan.facets
            if facet.role
            in {
                FacetRole.ORIGIN,
                FacetRole.TRANSITION,
                FacetRole.MECHANISM,
                FacetRole.ENDPOINT,
            }
        },
    )
    requirement_ids = tuple(
        requirement.requirement_id for requirement in finalized_plan.requirements
    )
    emitted_trace: dict[str, object] = {}
    monkeypatch.setattr(
        rag_pipeline,
        "emit_retrieval_trace",
        lambda trace: emitted_trace.update(trace),
    )
    calls: list[str] = []
    private_provider_message = "PRIVATE provider prose must never be recorded"

    class SyntheticPlannerFailure(RuntimeError):
        code = "rate-limit/429"

    def fake_parse(_client, *, operation, **_request):
        calls.append(operation)
        if operation == "query_planning":
            raise SyntheticPlannerFailure(private_provider_message)
        return SimpleNamespace(
            output_parsed=supported_obligation_answer(
                requirement_ids,
                obligation_scopes,
            ),
            output=(),
        )

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=turn,
        collection_handle=Collection(),
        chunks=[CHUNK],
        client=object(),
        corpus_manifest=corpus_manifest(CHUNK),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    expected = {
        "schema": "archivist.planner_call_diagnostics/2",
        "status": "failed",
        "failure_code": "planner_call_failed",
        "planner_validation_code": None,
        "exception_class": "SyntheticPlannerFailure",
        "exception_code": "rate-limit/429",
    }
    assert calls == ["query_planning", "answer_generation"]
    assert result.plan.fallback_reason == "planner_call_failed"
    assert result.diagnostics["planner"] == expected
    assert emitted_trace["plan"]["planner_call"] == {
        "schema": "archivist.planner_call_diagnostics/2",
        "status": "failed",
        "failure_code": "planner_call_failed",
        "planner_validation_code": None,
        "exception_class_sha256": hashlib.sha256(b"SyntheticPlannerFailure").hexdigest(),
        "exception_code": "rate-limit/429",
    }
    validate_text_free_retrieval_trace(emitted_trace)
    run_diagnostics = rag_pipeline.answer_run_diagnostics(result)
    assert run_diagnostics["schema"] == "archivist.answer_run_diagnostics/2"
    assert run_diagnostics["planner"] == expected
    assert private_provider_message not in str(result.diagnostics)
    assert private_provider_message not in str(emitted_trace)
    assert private_provider_message not in str(run_diagnostics)


@pytest.mark.parametrize(
    "private_code",
    [
        "PRIVATE-provider-prose-must-never-persist",
        "PRIVATE/provider/prose",
        "C:/Users/Michael/private",
        "private-provider-prose-must-persist",
        "c:users:michael:private",
    ],
)
def test_planner_diagnostics_reject_encoded_prose_and_paths(private_code):
    class SyntheticPlannerFailure(RuntimeError):
        code = private_code

    diagnostic = rag_pipeline._planner_call_diagnostic(
        "failed",
        failure_code="planner_call_failed",
        error=SyntheticPlannerFailure("private provider message"),
    )

    assert diagnostic["exception_code"] is None
    assert private_code not in str(diagnostic)


def test_planner_diagnostic_uses_safe_status_when_provider_code_is_unsafe():
    class SyntheticPlannerFailure(RuntimeError):
        code = "private-provider-prose-must-persist"
        status_code = 429

    diagnostic = rag_pipeline._planner_call_diagnostic(
        "failed",
        failure_code="planner_call_failed",
        error=SyntheticPlannerFailure("private provider message"),
    )

    assert diagnostic["exception_code"] == "429"
    assert SyntheticPlannerFailure.code not in str(diagnostic)


def test_certified_absence_skips_answer_generation(monkeypatch):
    absent_chunk = {
        **CHUNK,
        "text": "This synthetic passage discusses an unrelated subject.",
    }
    install_planned_retrieval(monkeypatch, [absent_chunk])
    calls: list[str] = []

    def fake_parse(_client, *, operation, **_request):
        calls.append(operation)
        raise AssertionError("clean abstention must not call answer generation")

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question="Who was Project Lumen?",
            entities=("Project Lumen",),
            trusted_user_texts=("Who was Project Lumen?",),
        ),
        collection_handle=Collection(),
        chunks=[absent_chunk],
        client=object(),
        corpus_manifest=corpus_manifest(absent_chunk),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert calls == []
    assert result.status == "clean_abstention"
    assert result.final_chunks == []
    assert "could not find a direct mention" in result.answer


def test_absence_gate_is_not_overridden_by_an_untrusted_premise_plan():
    absent_chunk = {
        **CHUNK,
        "text": "This synthetic passage discusses an unrelated subject.",
    }
    question = "Why did Project Lumen begin the signal change?"
    turn = ResolvedTurn(
        standalone_question=question,
        trusted_user_texts=(question,),
    )
    premise_plan = rag_pipeline.build_question_plan(turn)
    defensive_plan = premise_plan.model_copy(
        update={"traits": (RouteTrait.ABSENCE_SENSITIVE,)}
    )
    planned = planned_context(defensive_plan, [absent_chunk])

    gate, _diagnostics, _target_label = rag_pipeline.apply_evidence_gate(
        defensive_plan,
        planned,
        [absent_chunk],
        trusted_user_texts=turn.trusted_user_texts,
        collection_count=1,
        corpus_manifest=corpus_manifest(absent_chunk),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert premise_plan.premises
    assert RouteTrait.PREMISE_SENSITIVE not in defensive_plan.traits
    assert gate.decision.value == "clean_abstention"
    assert "premise_evaluation_pending" not in gate.rules_fired


def test_compound_named_subjects_are_scanned_independently_and_admit_context():
    first = {
        **CHUNK,
        "chunk_id": "synthetic_001",
        "text": "Avery North appears in this synthetic record.",
    }
    second = {
        **CHUNK,
        "chunk_id": "synthetic_002",
        "paragraph_start": 2,
        "paragraph_end": 2,
        "text": "Blake South appears in a separate synthetic record.",
    }
    contextual = {
        **CHUNK,
        "chunk_id": "synthetic_003",
        "paragraph_start": 3,
        "paragraph_end": 3,
        "text": "A contextual passage develops the synthetic argument.",
    }
    chunks = [first, second, contextual]
    question = "What role do Avery North and Blake South play in the argument?"
    turn = ResolvedTurn(
        standalone_question=question,
        trusted_user_texts=(question,),
    )
    plan = rag_pipeline.build_question_plan(turn)
    planned = planned_context(plan, chunks)

    gate, diagnostics, target_label = rag_pipeline.apply_evidence_gate(
        plan,
        planned,
        chunks,
        trusted_user_texts=turn.trusted_user_texts,
        collection_count=len(chunks),
        corpus_manifest=corpus_manifest(*chunks),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert gate.decision.value == "direct_answer"
    assert gate.allowed_source_numbers == (1, 2, 3)
    assert gate.suppressed_source_numbers == ()
    assert gate.rules_fired == (
        "all_subject_targets_direct",
        "compound_named_subject_split",
    )
    assert len(diagnostics["targets"]) == 2
    assert target_label is None


def test_multiple_subjects_plus_a_facet_remain_indeterminate():
    joint = {
        **CHUNK,
        "text": (
            "Avery North and Blake South appear alongside Casey East in this synthetic record."
        ),
    }
    question = "How did Avery North and Blake South affect Casey East?"
    turn = ResolvedTurn(
        standalone_question=question,
        trusted_user_texts=(question,),
    )
    plan = rag_pipeline.build_question_plan(turn)
    planned = planned_context(plan, [joint])

    gate, diagnostics, target_label = rag_pipeline.apply_evidence_gate(
        plan,
        planned,
        [joint],
        trusted_user_texts=turn.trusted_user_texts,
        collection_count=1,
        corpus_manifest=corpus_manifest(joint),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert gate.decision.value == "indeterminate"
    assert gate.allowed_source_numbers == ()
    assert gate.suppressed_source_numbers == (1,)
    assert gate.rules_fired == ("multiple_targets_require_disambiguation",)
    assert [target["role"] for target in diagnostics["targets"]] == [
        "subject",
        "subject",
        "facet",
    ]
    assert target_label is None


def test_trusted_related_tail_qualifies_bounded_near_match():
    related = {
        **CHUNK,
        "text": ("Federal programs changed while contracting expanded in the synthetic record."),
    }
    question = "What does the book say about XR-37 and its effect on federal contracting?"
    turn = ResolvedTurn(
        standalone_question=question,
        trusted_user_texts=(question,),
    )
    plan = rag_pipeline.build_question_plan(turn)
    planned = planned_context(plan, [related])

    gate, diagnostics, target_label = rag_pipeline.apply_evidence_gate(
        plan,
        planned,
        [related],
        trusted_user_texts=turn.trusted_user_texts,
        collection_count=1,
        corpus_manifest=corpus_manifest(related),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert gate.decision.value == "qualified_near_match"
    assert gate.allowed_source_numbers == (1,)
    assert gate.rules_fired == (
        "certified_direct_absence",
        "qualified_broader_material",
        "trusted_related_tail_material",
    )
    assert diagnostics["broader_related"]["qualifying_pair_count"] == 1
    assert target_label == "XR-37"


def test_hinted_planner_relation_outranks_exact_tail_keyword_fallback():
    keyword = {
        **CHUNK,
        "chunk_id": "keyword_001",
        "document": "keyword.md",
        "text": "Federal programs changed while contracting expanded in the record.",
    }
    hinted = {
        **CHUNK,
        "chunk_id": "hinted_001",
        "document": "hinted.md",
        "paragraph_start": 2,
        "paragraph_end": 2,
        "text": "A worldwide pandemic exposed supply-chain risk and prompted reshoring.",
    }
    question = "What does the book say about XR-37 and its effect on federal contracting?"
    turn = ResolvedTurn(
        standalone_question=question,
        trusted_user_texts=(question,),
    )
    local = rag_pipeline.build_question_plan(turn)
    plan = QuestionPlan(
        traits=local.traits,
        requirements=local.requirements,
        facets=(
            local.facets[0],
            SearchFacet(
                facet_id="F1",
                requirement_ids=(local.requirements[0].requirement_id,),
                role=FacetRole.MECHANISM,
                search_query="XR-37 federal contracting",
                document_hints=("hinted.md",),
            ),
        ),
        targets=local.targets,
        planner_used=True,
    )
    planned = PlannedContext(
        final_chunks=[keyword, hinted],
        facet_source_numbers={"F0": (1,), "F1": (2,)},
        trace={
            "schema": RETRIEVAL_TRACE_SCHEMA,
            "plan": {},
            "evidence": {},
            "generation_contract": {},
        },
        lane_by_chunk_id={"keyword_001": ("F0",), "hinted_001": ("F1",)},
    )

    gate, diagnostics, target_label = rag_pipeline.apply_evidence_gate(
        plan,
        planned,
        [keyword, hinted],
        trusted_user_texts=turn.trusted_user_texts,
        collection_count=2,
        corpus_manifest=corpus_manifest(keyword, hinted),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert gate.decision.value == "qualified_near_match"
    assert gate.allowed_source_numbers == (2,)
    assert gate.suppressed_source_numbers == (1,)
    assert gate.rules_fired == (
        "certified_direct_absence",
        "qualified_broader_material",
        "planner_bounded_related_material",
    )
    assert diagnostics["broader_related"]["qualifying_pair_count"] == 1
    assert target_label == "XR-37"


def test_related_looking_noncooccurring_material_preserves_clean_absence():
    broader = {
        **CHUNK,
        "document": "first.md",
        "text": "Canadian policy appears in this synthetic record.",
    }
    probe = {
        **CHUNK,
        "chunk_id": "synthetic_002",
        "document": "second.md",
        "paragraph_start": 2,
        "paragraph_end": 2,
        "text": "A fur trade appears in an unrelated synthetic record.",
    }
    chunks = [broader, probe]
    question = "How does the book treat the Briar Council and the Canadian fur trade?"
    turn = ResolvedTurn(
        standalone_question=question,
        trusted_user_texts=(question,),
    )
    plan = rag_pipeline.build_question_plan(turn)
    planned = planned_context(plan, chunks)

    gate, diagnostics, target_label = rag_pipeline.apply_evidence_gate(
        plan,
        planned,
        chunks,
        trusted_user_texts=turn.trusted_user_texts,
        collection_count=len(chunks),
        corpus_manifest=corpus_manifest(*chunks),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert gate.decision.value == "clean_abstention"
    assert gate.allowed_source_numbers == ()
    assert gate.suppressed_source_numbers == (1, 2)
    assert diagnostics["broader_related"]["qualifying_pair_count"] == 0
    assert target_label == "Briar Council"


def test_related_tail_derivation_never_uses_resolver_only_prose():
    related = {
        **CHUNK,
        "text": ("Federal programs changed while contracting expanded in the synthetic record."),
    }
    resolved_question = "What does the book say about XR-37 and its effect on federal contracting?"
    trusted_question = "What does the book say about XR-37?"
    turn = ResolvedTurn(
        standalone_question=resolved_question,
        trusted_user_texts=(trusted_question,),
    )
    plan = rag_pipeline.build_question_plan(turn)
    planned = planned_context(plan, [related])

    gate, diagnostics, _target_label = rag_pipeline.apply_evidence_gate(
        plan,
        planned,
        [related],
        trusted_user_texts=turn.trusted_user_texts,
        collection_count=1,
        corpus_manifest=corpus_manifest(related),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert gate.decision.value == "clean_abstention"
    assert diagnostics["broader_related"] is None


def test_invalid_structured_answer_fails_closed_without_retry(monkeypatch):
    install_planned_retrieval(monkeypatch, [CHUNK])
    invalid = supported_answer(("R1",), source_number=2)
    calls: list[str] = []

    def fake_parse(_client, *, operation, **_request):
        calls.append(operation)
        return SimpleNamespace(output_parsed=invalid, output=())

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question="Who was Project Lumen?",
        ),
        collection_handle=Collection(),
        chunks=[CHUNK],
        client=object(),
        corpus_manifest=corpus_manifest(CHUNK),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert calls == ["answer_generation"]
    assert result.status == "generation_contract_failed"
    assert "validated source-grounded answer" in result.answer
    run_diagnostics = rag_pipeline.answer_run_diagnostics(result)
    assert run_diagnostics["validation_result"] == "invalid"
    assert run_diagnostics["validation_error_code"] == "source_number_out_of_range"
    assert "validated source-grounded answer" not in str(run_diagnostics)


def test_answer_input_contains_resolved_structure_not_prior_assistant_prose(
    monkeypatch,
):
    install_planned_retrieval(monkeypatch, [CHUNK])
    captured: dict[str, object] = {}

    def fake_parse(_client, *, operation, **request):
        captured.update(request)
        assert operation == "answer_generation"
        return SimpleNamespace(
            output_parsed=supported_answer(("R1",)),
            output=(),
        )

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)
    prior_marker = "UNTRUSTED_PRIOR_ASSISTANT_ASSERTION"

    rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question="Who was Project Lumen?",
            entities=("Project Lumen",),
            scope="the requested period",
            relationship="identity",
        ),
        collection_handle=Collection(),
        chunks=[CHUNK],
        client=object(),
        corpus_manifest=corpus_manifest(CHUNK),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert "Project Lumen" in str(captured["input"])
    assert "the requested period" in str(captured["input"])
    assert prior_marker not in str(captured["input"])


def test_integrity_failure_stops_before_planning_embedding_or_generation(
    monkeypatch,
):
    original = dict(CHUNK)
    altered = {**CHUNK, "text": "Altered text with unchanged chunk identity."}
    calls: list[str] = []
    monkeypatch.setattr(
        rag_pipeline,
        "retrieve_plan_from_collection",
        lambda *_args, **_kwargs: calls.append("retrieval"),
    )
    monkeypatch.setattr(
        rag_pipeline,
        "tracked_responses_parse",
        lambda *_args, **_kwargs: calls.append("model"),
    )

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(standalone_question="Who was Project Lumen?"),
        collection_handle=Collection(),
        chunks=[altered],
        client=object(),
        corpus_manifest=corpus_manifest(original),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert calls == []
    assert result.status == "corpus_integrity_failed"
    assert result.final_chunks == []
    assert "index could not be verified" in result.answer
    assert (
        "chunk_text_identity_mismatch" in result.diagnostics["evidence"]["corpus"]["failure_codes"]
    )
    assert result.diagnostics["planner"] == {
        "schema": "archivist.planner_call_diagnostics/2",
        "status": "not_called",
        "failure_code": None,
        "planner_validation_code": None,
        "exception_class": None,
        "exception_code": None,
    }
    assert rag_pipeline.answer_run_diagnostics(result)["planner"] == (result.diagnostics["planner"])


def test_strict_preflight_checks_actual_collection_ids_and_metadata():
    manifest = strict_corpus_manifest(CHUNK)

    valid = rag_pipeline.preflight_answer_corpus(
        collection_handle=StrictCollection(),
        chunks=[CHUNK],
        corpus_manifest=manifest,
        corpus_manifest_sha256=MANIFEST_SHA256,
        require_store_identity=True,
    )
    stale_id = rag_pipeline.preflight_answer_corpus(
        collection_handle=StrictCollection(stored_id="stale_001"),
        chunks=[CHUNK],
        corpus_manifest=manifest,
        corpus_manifest_sha256=MANIFEST_SHA256,
        require_store_identity=True,
    )
    stale_metadata = rag_pipeline.preflight_answer_corpus(
        collection_handle=StrictCollection(stored_text="Stale stored text."),
        chunks=[CHUNK],
        corpus_manifest=manifest,
        corpus_manifest_sha256=MANIFEST_SHA256,
        require_store_identity=True,
    )

    assert valid.passed is True
    assert "collection_chunk_ids_mismatch" in stale_id.failure_codes
    assert "collection_chunk_metadata_mismatch" in stale_metadata.failure_codes


def test_same_count_stale_collection_stops_before_any_paid_stage(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        rag_pipeline,
        "retrieve_plan_from_collection",
        lambda *_args, **_kwargs: calls.append("retrieval"),
    )
    monkeypatch.setattr(
        rag_pipeline,
        "tracked_responses_parse",
        lambda *_args, **_kwargs: calls.append("model"),
    )

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(standalone_question="Who was Project Lumen?"),
        collection_handle=StrictCollection(stored_id="stale_001"),
        chunks=[CHUNK],
        client=object(),
        corpus_manifest=strict_corpus_manifest(CHUNK),
        corpus_manifest_sha256=MANIFEST_SHA256,
        require_store_identity=True,
    )

    assert calls == []
    assert result.status == "corpus_integrity_failed"
    assert (
        "collection_chunk_ids_mismatch" in result.diagnostics["evidence"]["corpus"]["failure_codes"]
    )


def test_global_anchor_hit_is_promoted_into_generation_context(monkeypatch):
    unrelated = {
        **CHUNK,
        "chunk_id": "synthetic_002",
        "paragraph_start": 2,
        "paragraph_end": 2,
        "text": "An unrelated synthetic passage.",
    }
    direct = dict(CHUNK)

    def fake_retrieve(plan, *_args, **_kwargs):
        return planned_context(plan, [unrelated])

    monkeypatch.setattr(
        rag_pipeline,
        "retrieve_plan_from_collection",
        fake_retrieve,
    )
    monkeypatch.setattr(rag_pipeline, "emit_retrieval_trace", lambda _trace: None)
    captured: dict[str, object] = {}

    def fake_parse(_client, *, operation, **request):
        assert operation == "answer_generation"
        captured.update(request)
        return SimpleNamespace(
            output_parsed=supported_answer(("R1",)),
            output=(),
        )

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)
    chunks = [direct, unrelated]

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(standalone_question="Who was Project Lumen?"),
        collection_handle=Collection(count=2),
        chunks=chunks,
        client=object(),
        corpus_manifest=corpus_manifest(*chunks),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert result.final_chunks[0]["chunk_id"] == direct["chunk_id"]
    assert direct["text"] in str(captured["input"])
    assert result.evidence_decision == "direct_answer"


def test_anchor_promotion_preserves_every_broad_requirement_lane():
    requirements = tuple(
        AnswerRequirement(
            requirement_id=f"R{index}",
            label=f"Broad requirement {index}",
            order=index - 1,
        )
        for index in range(1, 5)
    )
    plan = QuestionPlan(
        traits=(RouteTrait.BROAD_SYNTHESIS,),
        requirements=requirements,
        facets=(
            SearchFacet(
                facet_id="F0",
                requirement_ids=tuple(
                    requirement.requirement_id for requirement in requirements
                ),
                role=FacetRole.ORIGINAL,
                search_query="Trace four synthetic periods.",
            ),
            SearchFacet(
                facet_id="F1",
                requirement_ids=("R1",),
                role=FacetRole.ORIGIN,
                search_query="synthetic origin",
            ),
            SearchFacet(
                facet_id="F2",
                requirement_ids=("R2",),
                role=FacetRole.MECHANISM,
                search_query="synthetic mechanism",
            ),
            SearchFacet(
                facet_id="F3",
                requirement_ids=("R3",),
                role=FacetRole.TRANSITION,
                search_query="synthetic transition",
            ),
            SearchFacet(
                facet_id="F4",
                requirement_ids=("R4",),
                role=FacetRole.ENDPOINT,
                search_query="synthetic endpoint",
            ),
        ),
    )
    old_chunks = [
        {
            **CHUNK,
            "chunk_id": f"old_{index}",
            "paragraph_start": index,
            "paragraph_end": index,
            "text": f"Retrieved lane passage {index}.",
        }
        for index in range(1, 9)
    ]
    anchor_names = ("Atlas One", "Boreal Two", "Cedar Three", "Delta Four")
    anchor_chunks = [
        {
            **CHUNK,
            "chunk_id": f"anchor_{index}",
            "paragraph_start": 20 + index,
            "paragraph_end": 20 + index,
            "text": f"{anchor_name} appears in this synthetic passage.",
        }
        for index, anchor_name in enumerate(anchor_names, start=1)
    ]
    eligible_chunks = [*old_chunks, *anchor_chunks]
    planned = PlannedContext(
        final_chunks=old_chunks.copy(),
        facet_source_numbers={
            "F0": tuple(range(1, 9)),
            "F1": (1, 2),
            "F2": (3, 4),
            "F3": (5, 6),
            "F4": (7, 8),
        },
        trace={
            "schema": RETRIEVAL_TRACE_SCHEMA,
            "plan": {},
            "selection": {"context": []},
            "evidence": {},
            "generation_contract": {},
        },
        lane_by_chunk_id={
            str(chunk["chunk_id"]): (
                "F0",
                f"F{((index - 1) // 2) + 1}",
            )
            for index, chunk in enumerate(old_chunks, start=1)
        },
        broad_stage_anchor_chunk_ids={
            "F1": "old_1",
            "F2": "old_3",
            "F3": "old_5",
            "F4": "old_7",
        },
    )
    integrity = rag_pipeline.assess_corpus_integrity(
        eligible_chunks,
        manifest_eligible_chunk_ids=tuple(
            str(chunk["chunk_id"]) for chunk in eligible_chunks
        ),
        expected_manifest_sha256=MANIFEST_SHA256,
        loaded_manifest_sha256=MANIFEST_SHA256,
        expected_collection_count=len(eligible_chunks),
        collection_count=len(eligible_chunks),
    )
    scans = tuple(
        rag_pipeline.scan_evidence_target(
            f"T{index}",
            anchor_name,
            eligible_chunks,
            absence_checkable=True,
            corpus_integrity=integrity,
        )
        for index, anchor_name in enumerate(anchor_names, start=1)
    )

    rag_pipeline._promote_direct_anchor_chunks(
        plan,
        planned,
        scans,
        eligible_chunks,
        facet_scan=None,
        immediate_neighbors={},
    )

    assert [chunk["chunk_id"] for chunk in planned.final_chunks] == [
        "old_1",
        "old_3",
        "old_5",
        "old_7",
        "anchor_1",
        "anchor_2",
        "anchor_3",
        "anchor_4",
    ]
    assert planned.facet_source_numbers["F1"] == (1,)
    assert planned.facet_source_numbers["F2"] == (2,)
    assert planned.facet_source_numbers["F3"] == (3,)
    assert planned.facet_source_numbers["F4"] == (4,)
    assert planned.broad_stage_anchor_chunk_ids == {
        "F1": "old_1",
        "F2": "old_3",
        "F3": "old_5",
        "F4": "old_7",
    }
    (
        _filtered_chunks,
        _old_to_new,
        _remapped_facets,
        remapped_stage_anchors,
        remapped_transition_sources,
    ) = rag_pipeline._filter_context(planned, tuple(range(1, 9)))
    assert remapped_stage_anchors == {
        "F1": 1,
        "F2": 2,
        "F3": 3,
        "F4": 4,
    }
    assert remapped_transition_sources == {}
    assert planned.trace["selection"]["anchor_requested_count"] == 4
    assert planned.trace["selection"]["protected_source_count"] == 4
    assert planned.trace["selection"]["protected_source_shortfall_count"] == 0


def test_promoted_premise_anchor_keeps_correction_source_mapping_valid(monkeypatch):
    substantive = {
        **CHUNK,
        "chunk_id": "synthetic_002",
        "paragraph_start": 2,
        "paragraph_end": 2,
        "text": "The later synthetic signal change is described.",
    }
    framing = {
        **CHUNK,
        "chunk_id": "synthetic_003",
        "paragraph_start": 3,
        "paragraph_end": 3,
        "text": "The manuscript frames the synthetic chronology as beginning earlier.",
    }
    direct = dict(CHUNK)

    def fake_retrieve(plan, *_args, **_kwargs):
        return PlannedContext(
            final_chunks=[substantive, framing],
            facet_source_numbers={
                "F0": (1, 2),
                "F1": (1,),
                "F2": (2,),
                "F3": (2,),
            },
            trace={
                "schema": RETRIEVAL_TRACE_SCHEMA,
                "plan": {},
                "evidence": {},
                "generation_contract": {},
            },
            lane_by_chunk_id={
                "synthetic_002": ("F0", "F1"),
                "synthetic_003": ("F0", "F2", "F3"),
            },
        )

    monkeypatch.setattr(
        rag_pipeline,
        "retrieve_plan_from_collection",
        fake_retrieve,
    )
    monkeypatch.setattr(
        rag_pipeline,
        "plan_question",
        lambda _client, resolved_turn, _catalog, **_kwargs: rag_pipeline.build_question_plan(
            resolved_turn,
            fallback_reason="synthetic_test",
        ),
    )
    traces: list[dict] = []
    monkeypatch.setattr(
        rag_pipeline,
        "emit_retrieval_trace",
        lambda trace: traces.append(trace),
    )
    captured: dict[str, object] = {}
    correction = AnswerUnit(
        unit_id="U1",
        requirement_ids=(),
        role=AnswerUnitRole.PREMISE_CORRECTION,
        text="The manuscript frames the synthetic chronology as beginning earlier [Source 3].",
        source_numbers=(3,),
        paragraph=1,
    )
    substantive_unit = AnswerUnit(
        unit_id="U2",
        requirement_ids=("R1",),
        role=AnswerUnitRole.EVENT,
        text="The later synthetic signal change is described [Source 2].",
        source_numbers=(2,),
        paragraph=2,
    )

    def fake_parse(_client, *, operation, **request):
        assert operation == "answer_generation"
        captured.update(request)
        return SimpleNamespace(
            output_parsed=EvidenceCoverageAnswer(
                schema=EVIDENCE_COVERAGE_SCHEMA,
                premise_decisions=(
                    PremiseDecision(
                        premise_id="P1",
                        status=PremiseStatus.CONTRADICTED,
                        source_numbers=(3,),
                        correction_unit_id="U1",
                    ),
                ),
                coverage=(
                    RequirementCoverage(
                        requirement_id="R1",
                        status=RequirementStatus.SUPPORTED,
                        unit_ids=("U2",),
                        source_numbers=(2,),
                        gap_reason=GapReason.NONE,
                    ),
                ),
                answer_units=(correction, substantive_unit),
            ),
            output=(),
        )

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question="Why did Project Lumen begin the signal change?",
            entities=("Project Lumen",),
            trusted_user_texts=("Why did Project Lumen begin the signal change?",),
        ),
        collection_handle=Collection(count=3),
        chunks=[direct, substantive, framing],
        client=object(),
        corpus_manifest=corpus_manifest(direct, substantive, framing),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert result.status == "answered"
    assert result.answer == f"{correction.text}\n\n{substantive_unit.text}"
    assert [chunk["chunk_id"] for chunk in result.final_chunks] == [
        "synthetic_001",
        "synthetic_002",
        "synthetic_003",
    ]
    assert str(captured["input"]).index("[Source 1]") < str(captured["input"]).index("[Source 2]")
    assert str(captured["input"]).index("[Source 2]") < str(captured["input"]).index("[Source 3]")
    assert "inspect all supplied sources" in str(captured["instructions"])
    assert result.diagnostics["generation"]["repair_codes"] == []
    assert result.diagnostics["generation"]["premise_source_scopes"] == [
        {
            "premise_id": "P1",
            "support_source_numbers": [2],
            "counter_source_numbers": [3],
            "framing_source_numbers": [3],
        }
    ]
    assert traces[0]["selection"]["anchor_source_number_remap"] == [
        {
            "pre_anchor_source_number": None,
            "post_anchor_source_number": 1,
        },
        {
            "pre_anchor_source_number": 1,
            "post_anchor_source_number": 2,
        },
        {
            "pre_anchor_source_number": 2,
            "post_anchor_source_number": 3,
        },
    ]
    assert traces[0]["selection"]["generation_context"][0]["chunk_id"] == ("synthetic_001")


def test_trace_records_post_gate_source_number_remap(monkeypatch):
    first = dict(CHUNK)
    generic = {
        **CHUNK,
        "chunk_id": "synthetic_002",
        "document": "other.md",
        "chapter_title": "Other",
        "paragraph_start": 2,
        "paragraph_end": 2,
        "text": "A generic synthetic passage.",
    }
    third = {
        **CHUNK,
        "chunk_id": "synthetic_003",
        "paragraph_start": 3,
        "paragraph_end": 3,
        "text": "Project Lumen appears again in a later passage.",
    }
    chunks = [first, generic, third]
    install_planned_retrieval(monkeypatch, chunks)
    traces: list[dict] = []
    monkeypatch.setattr(
        rag_pipeline,
        "emit_retrieval_trace",
        lambda trace: traces.append(trace),
    )
    monkeypatch.setattr(
        rag_pipeline,
        "tracked_responses_parse",
        lambda _client, *, operation, **_request: SimpleNamespace(
            output_parsed=supported_answer(("R1",), source_number=2),
            output=(),
        ),
    )

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(standalone_question="Who was Project Lumen?"),
        collection_handle=Collection(count=3),
        chunks=chunks,
        client=object(),
        corpus_manifest=corpus_manifest(*chunks),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert [chunk["chunk_id"] for chunk in result.final_chunks] == [
        "synthetic_001",
        "synthetic_003",
    ]
    assert traces[0]["selection"]["source_number_remap"] == [
        {
            "retrieval_source_number": 1,
            "generation_source_number": 1,
        },
        {
            "retrieval_source_number": 3,
            "generation_source_number": 2,
        },
    ]
    assert traces[0]["selection"]["generation_context"][1]["chunk_id"] == ("synthetic_003")
