from __future__ import annotations

import hashlib
from types import SimpleNamespace

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
