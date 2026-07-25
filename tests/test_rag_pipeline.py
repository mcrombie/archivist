from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

import rag_pipeline
from answer_coverage import (
    AnswerUnit,
    AnswerUnitRole,
    EvidenceCoverageAnswer,
    GapReason,
    RequirementCoverage,
    RequirementStatus,
)
from query_planning import (
    AnswerRequirement,
    FacetRole,
    QuestionPlan,
    ResolvedTurn,
    SearchFacet,
)
from retrieval import PlannedContext
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
                "text_sha256": hashlib.sha256(
                    str(chunk["text"]).encode("utf-8")
                ).hexdigest(),
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
        facet_source_numbers={
            facet.facet_id: source_numbers for facet in plan.facets
        },
        trace={
            "schema": "archivist.retrieval_trace/2",
            "plan": {},
            "evidence": {},
            "generation_contract": {},
        },
        lane_by_chunk_id={
            str(chunk["chunk_id"]): tuple(facet.facet_id for facet in plan.facets)
            for chunk in chunks
        },
    )


def supported_answer(
    requirement_ids: tuple[str, ...],
    *,
    source_number: int = 1,
) -> EvidenceCoverageAnswer:
    unit_ids = tuple(f"U{index}" for index in range(1, len(requirement_ids) + 1))
    return EvidenceCoverageAnswer(
        schema="archivist.evidence_coverage/1",
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

    assert rag_pipeline.EVIDENCE_COVERAGE_PROMPT_VERSION == "evidence-coverage-v2"
    assert "exactly one independently checkable factual claim" in instructions
    assert "exactly one terminal citation group" in instructions
    assert "every listed source independently supports" in instructions
    assert "split them into separate answer" in instructions
    assert "spell them out or rephrase" in instructions


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
        "schema": "archivist.planner_call_diagnostics/1",
        "status": "not_called",
        "failure_code": None,
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
        "text": (
            "Project Lumen and Harbor Network shaped civic exchange "
            "in Port Delta."
        ),
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
        "Project Lumen Harbor Network relationship "
        "as shaping civic exchange in Port Delta"
    )


def test_complex_question_has_one_planner_call_and_one_answer_call(monkeypatch):
    install_planned_retrieval(monkeypatch, [CHUNK])
    raw_plan = QuestionPlan(
        requirements=(
            AnswerRequirement(
                requirement_id="R1",
                label="Project Lumen origin",
                order=0,
            ),
            AnswerRequirement(
                requirement_id="R2",
                label="Project Lumen endpoint",
                order=1,
            ),
        ),
        facets=(
            SearchFacet(
                facet_id="F1",
                requirement_ids=("R1",),
                role=FacetRole.ORIGIN,
                search_query="origin Project Lumen",
            ),
            SearchFacet(
                facet_id="F2",
                requirement_ids=("R2",),
                role=FacetRole.ENDPOINT,
                search_query="endpoint Project Lumen",
            ),
        ),
    )
    calls: list[dict] = []

    def fake_parse(_client, *, operation, **request):
        calls.append({"operation": operation, **request})
        parsed = (
            raw_plan
            if operation == "query_planning"
            else supported_answer(("R1", "R2"))
        )
        return SimpleNamespace(output_parsed=parsed, output=())

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question=(
                "Trace Project Lumen from its origin to its endpoint."
            ),
            entities=("Project Lumen",),
        ),
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
    assert result.plan.planner_used is True
    assert result.plan.facets[0].facet_id == "F0"
    assert result.status == "answered"


def test_planner_failure_preserves_only_exact_text_free_diagnostics(monkeypatch):
    install_planned_retrieval(monkeypatch, [CHUNK])
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
            output_parsed=supported_answer(("R1", "R2", "R3")),
            output=(),
        )

    monkeypatch.setattr(rag_pipeline, "tracked_responses_parse", fake_parse)

    result = rag_pipeline.run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question=(
                "Trace Project Lumen from its origin to its endpoint."
            ),
        ),
        collection_handle=Collection(),
        chunks=[CHUNK],
        client=object(),
        corpus_manifest=corpus_manifest(CHUNK),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    expected = {
        "schema": "archivist.planner_call_diagnostics/1",
        "status": "failed",
        "failure_code": "planner_call_failed",
        "exception_class": "SyntheticPlannerFailure",
        "exception_code": "rate-limit/429",
    }
    assert calls == ["query_planning", "answer_generation"]
    assert result.plan.fallback_reason == "planner_call_failed"
    assert result.diagnostics["planner"] == expected
    assert emitted_trace["plan"]["planner_call"] == expected
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
        resolved_turn=ResolvedTurn(
            standalone_question="Who was Project Lumen?"
        ),
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
        "chunk_text_identity_mismatch"
        in result.diagnostics["evidence"]["corpus"]["failure_codes"]
    )
    assert result.diagnostics["planner"] == {
        "schema": "archivist.planner_call_diagnostics/1",
        "status": "not_called",
        "failure_code": None,
        "exception_class": None,
        "exception_code": None,
    }
    assert rag_pipeline.answer_run_diagnostics(result)["planner"] == (
        result.diagnostics["planner"]
    )


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
        resolved_turn=ResolvedTurn(
            standalone_question="Who was Project Lumen?"
        ),
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
        "collection_chunk_ids_mismatch"
        in result.diagnostics["evidence"]["corpus"]["failure_codes"]
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
        resolved_turn=ResolvedTurn(
            standalone_question="Who was Project Lumen?"
        ),
        collection_handle=Collection(count=2),
        chunks=chunks,
        client=object(),
        corpus_manifest=corpus_manifest(*chunks),
        corpus_manifest_sha256=MANIFEST_SHA256,
    )

    assert result.final_chunks[0]["chunk_id"] == direct["chunk_id"]
    assert direct["text"] in str(captured["input"])
    assert result.evidence_decision == "direct_answer"


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
        resolved_turn=ResolvedTurn(
            standalone_question="Who was Project Lumen?"
        ),
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
            "retrieval_source_number": 2,
            "generation_source_number": 2,
        },
    ]
    assert traces[0]["selection"]["generation_context"][1]["chunk_id"] == (
        "synthetic_003"
    )
