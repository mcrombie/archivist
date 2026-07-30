from types import SimpleNamespace

import pytest

import full_context_pipeline
import web_project
from answer_coverage import AnswerUnitRole, ContentOutcome, CoverageOutcomeStatus
from evidence_policy import assess_corpus_integrity
from full_context_coverage import (
    FULL_CONTEXT_COVERAGE_SCHEMA,
    AbsenceFinding,
    AbsenceStatus,
    FullContextClaim,
    FullContextCoverageAnswer,
    FullContextValidationErrorCode,
)
from full_context_pipeline import (
    FULL_CONTEXT_POLICY_VERSION,
    FullContextEvidenceDecision,
    build_full_context_input,
    eligible_full_context_chunks,
    run_full_context_answer,
    serialize_full_context_corpus,
)
from query_planning import ResolvedTurn
from rag_pipeline import AnswerStrategy, answer_run_diagnostics


MANIFEST_SHA256 = "a" * 64


def chunk(index: int, text: str = "Synthetic manuscript prose.") -> dict[str, object]:
    return {
        "chunk_id": f"10_Synthetic Chapter 1_ Title_{index:03d}",
        "document": "10_Synthetic Chapter 1_ Title.md",
        "chapter_title": "Synthetic Chapter 1",
        "paragraph_start": index,
        "paragraph_end": index + 3,
        "text": text,
    }


CORPUS = [chunk(index) for index in range(1, 4)]


def matching_integrity(chunks):
    chunk_ids = [str(item["chunk_id"]) for item in chunks]
    return assess_corpus_integrity(
        chunks,
        manifest_eligible_chunk_ids=chunk_ids,
        expected_manifest_sha256=MANIFEST_SHA256,
        loaded_manifest_sha256=MANIFEST_SHA256,
        expected_collection_count=len(chunks),
        collection_count=len(chunks),
    )


def failing_integrity(chunks):
    chunk_ids = [str(item["chunk_id"]) for item in chunks]
    return assess_corpus_integrity(
        chunks,
        manifest_eligible_chunk_ids=chunk_ids,
        expected_manifest_sha256=MANIFEST_SHA256,
        loaded_manifest_sha256="b" * 64,
        expected_collection_count=len(chunks),
        collection_count=len(chunks),
    )


def coverage_answer(
    claims: tuple[FullContextClaim, ...],
    *,
    absence_findings: tuple[AbsenceFinding, ...] = (),
    self_reported: ContentOutcome = ContentOutcome.VALID_COMPLETE,
) -> FullContextCoverageAnswer:
    return FullContextCoverageAnswer(
        schema=FULL_CONTEXT_COVERAGE_SCHEMA,
        premise_finding=None,
        claims=claims,
        absence_findings=absence_findings,
        self_reported_content_outcome=self_reported,
    )


def stub_response(parsed):
    return SimpleNamespace(output_parsed=parsed, output=())


class RecordingClient:
    """Captures the one structured call full context is permitted to make."""

    def __init__(self, parsed):
        self.parsed = parsed
        self.calls: list[dict[str, object]] = []

    def with_options(self, **_kwargs):
        return self


@pytest.fixture
def patched_generation(monkeypatch):
    def install(parsed):
        client = RecordingClient(parsed)

        def fake_parse(_client, *, operation, **request):
            client.calls.append({"operation": operation, **request})
            return stub_response(client.parsed)

        monkeypatch.setattr(full_context_pipeline, "tracked_responses_parse", fake_parse)
        return client

    return install


def test_eligible_chunks_keep_corpus_order_and_drop_skipped_documents():
    chunks = [
        chunk(1),
        {**chunk(2), "document": "02_Table of Contents.md"},
        chunk(3),
    ]

    eligible = eligible_full_context_chunks(chunks)

    assert [item["chunk_id"] for item in eligible] == [
        "10_Synthetic Chapter 1_ Title_001",
        "10_Synthetic Chapter 1_ Title_003",
    ]


def test_serialized_corpus_is_keyed_by_chunk_id_in_canonical_order():
    serialized = serialize_full_context_corpus(CORPUS)

    assert serialized.index("Title_001") < serialized.index("Title_002")
    assert serialized.count("Chunk ID:") == 3
    # Positional source labels would compete with the identifier the model must
    # cite back, so the serializer must not emit them.
    assert "[Source" not in serialized


def test_prompt_places_the_stable_corpus_before_the_variable_question():
    turn = ResolvedTurn(standalone_question="What happened?", trusted_user_texts=("What happened?",))

    prompt = build_full_context_input(
        corpus_block=serialize_full_context_corpus(CORPUS),
        resolved_turn=turn,
    )

    assert prompt.index("Chunk ID:") < prompt.index("Question: What happened?")


def test_interpretive_settings_stay_after_the_cacheable_corpus_prefix():
    turn = ResolvedTurn(standalone_question="What happened?", trusted_user_texts=("What happened?",))

    prompt = build_full_context_input(
        corpus_block=serialize_full_context_corpus(CORPUS),
        resolved_turn=turn,
        historiographical_lens="tragic",
        worldview="pious",
    )

    # Placing a style block inside the prefix would fragment the shared cache
    # into one entry per lens/voice/worldview combination.
    assert prompt.index("Chunk ID:") < prompt.index("Interpretive presentation")


def test_corpus_integrity_failure_short_circuits_before_any_model_call(patched_generation):
    client = patched_generation(None)
    turn = ResolvedTurn(standalone_question="What happened?", trusted_user_texts=("What happened?",))

    result = run_full_context_answer(
        resolved_turn=turn,
        chunks=CORPUS,
        client=client,
        corpus_integrity=failing_integrity(CORPUS),
    )

    assert client.calls == []
    assert result.status == "corpus_integrity_failed"
    assert result.evidence_decision == FullContextEvidenceDecision.INDETERMINATE
    assert result.final_chunks == []


def test_oversized_corpus_fails_closed_before_any_model_call(monkeypatch, patched_generation):
    client = patched_generation(None)
    monkeypatch.setattr(full_context_pipeline, "DOCUMENTED_MAX_INPUT_TOKENS", 10)
    turn = ResolvedTurn(standalone_question="What happened?", trusted_user_texts=("What happened?",))

    result = run_full_context_answer(
        resolved_turn=turn,
        chunks=CORPUS,
        client=client,
        corpus_integrity=matching_integrity(CORPUS),
    )

    assert client.calls == []
    assert result.status == CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED.value
    generation = result.diagnostics["generation"]
    assert generation["structured_generation_called"] is False
    assert generation["error_code"] == FullContextValidationErrorCode.CONTEXT_BUDGET_EXCEEDED.value
    # A truncated corpus would make every absence judgment unsound while still
    # looking complete, so no answer is produced at all.
    assert result.final_chunks == []


def test_one_generation_call_with_no_retry_produces_cited_only_sources(patched_generation):
    parsed = coverage_answer(
        (
            FullContextClaim(
                claim_id="C1",
                role=AnswerUnitRole.MECHANISM,
                text="A synthetic process occurred.",
                cited_chunk_ids=("10_Synthetic Chapter 1_ Title_002",),
                paragraph_group=1,
            ),
        )
    )
    client = patched_generation(parsed)
    turn = ResolvedTurn(standalone_question="What happened?", trusted_user_texts=("What happened?",))

    result = run_full_context_answer(
        resolved_turn=turn,
        chunks=CORPUS,
        client=client,
        corpus_integrity=matching_integrity(CORPUS),
    )

    assert len(client.calls) == 1
    assert client.calls[0]["operation"] == "answer_generation"
    assert result.status == CoverageOutcomeStatus.ANSWERED.value
    assert result.evidence_decision == FullContextEvidenceDecision.ANSWERED
    assert result.answer == "A synthetic process occurred [Source 1]."
    # Three chunks were supplied to the model; one was cited and one is returned.
    assert [item["chunk_id"] for item in result.final_chunks] == [
        "10_Synthetic Chapter 1_ Title_002"
    ]
    assert result.answer_strategy == AnswerStrategy.FULL_CONTEXT.value
    assert result.answer_strategy_version == FULL_CONTEXT_POLICY_VERSION
    assert result.plan is None
    assert result.resolved_question == "What happened?"


def test_the_full_corpus_never_reaches_the_result_or_its_diagnostics(patched_generation):
    parsed = coverage_answer(
        (
            FullContextClaim(
                claim_id="C1",
                role=AnswerUnitRole.MECHANISM,
                text="A synthetic process occurred.",
                cited_chunk_ids=("10_Synthetic Chapter 1_ Title_001",),
                paragraph_group=1,
            ),
        )
    )
    client = patched_generation(parsed)
    turn = ResolvedTurn(standalone_question="What happened?", trusted_user_texts=("What happened?",))

    result = run_full_context_answer(
        resolved_turn=turn,
        chunks=CORPUS,
        client=client,
        corpus_integrity=matching_integrity(CORPUS),
    )

    serialized_diagnostics = str(result.diagnostics)
    assert "Synthetic manuscript prose" not in serialized_diagnostics
    assert "Chunk ID:" not in serialized_diagnostics
    assert len(result.final_chunks) < len(CORPUS)


def test_a_reported_absence_the_corpus_contradicts_downgrades_the_outcome(patched_generation):
    corpus = [
        chunk(1, "The Ohio Company petitioned for a grant of land."),
        chunk(2, "A synthetic later development followed."),
    ]
    parsed = coverage_answer(
        (
            FullContextClaim(
                claim_id="C1",
                role=AnswerUnitRole.MECHANISM,
                text="A synthetic later development followed.",
                cited_chunk_ids=("10_Synthetic Chapter 1_ Title_002",),
                paragraph_group=1,
            ),
        ),
        absence_findings=(
            AbsenceFinding(
                subject="Ohio Company",
                status=AbsenceStatus.NOT_ADDRESSED_IN_CORPUS,
                note="The manuscript does not treat the Ohio Company.",
            ),
        ),
        self_reported=ContentOutcome.VALID_COMPLETE,
    )
    client = patched_generation(parsed)
    turn = ResolvedTurn(
        standalone_question="How does the book treat the Ohio Company?",
        trusted_user_texts=("How does the book treat the Ohio Company?",),
    )

    result = run_full_context_answer(
        resolved_turn=turn,
        chunks=corpus,
        client=client,
        corpus_integrity=matching_integrity(corpus),
    )

    assert result.diagnostics["generation"]["content_outcome"] == ContentOutcome.VALID_PARTIAL.value
    assert result.diagnostics["generation"]["contradicted_absence_count"] == 1


def test_run_diagnostics_report_the_strategy_and_no_rag_cohort_values(patched_generation):
    parsed = coverage_answer(
        (
            FullContextClaim(
                claim_id="C1",
                role=AnswerUnitRole.MECHANISM,
                text="A synthetic process occurred.",
                cited_chunk_ids=("10_Synthetic Chapter 1_ Title_001",),
                paragraph_group=1,
            ),
        )
    )
    client = patched_generation(parsed)
    turn = ResolvedTurn(standalone_question="What happened?", trusted_user_texts=("What happened?",))

    result = run_full_context_answer(
        resolved_turn=turn,
        chunks=CORPUS,
        client=client,
        corpus_integrity=matching_integrity(CORPUS),
    )
    diagnostics = answer_run_diagnostics(result)

    cohort = diagnostics["cohort"]
    assert cohort["answer_strategy"] == AnswerStrategy.FULL_CONTEXT.value
    assert cohort["answer_strategy_version"] == FULL_CONTEXT_POLICY_VERSION
    # Reporting RAG's planner or normalizer version here would misattribute the
    # cohort of a run that never had either.
    assert cohort["rag_policy_version"] == "not-applicable"
    assert cohort["query_planner_prompt_version"] == "not-applicable"
    assert cohort["normalizer_version"] == "not-applicable"
    assert diagnostics["planner"]["status"] == "not_called"


def test_full_context_run_diagnostics_are_accepted_by_the_usage_ledger(
    tmp_path,
    patched_generation,
):
    from costs import UsageLedger

    parsed = coverage_answer(
        (
            FullContextClaim(
                claim_id="C1",
                role=AnswerUnitRole.MECHANISM,
                text="A synthetic process occurred.",
                cited_chunk_ids=("10_Synthetic Chapter 1_ Title_001",),
                paragraph_group=1,
            ),
        )
    )
    client = patched_generation(parsed)
    turn = ResolvedTurn(standalone_question="What happened?", trusted_user_texts=("What happened?",))
    result = run_full_context_answer(
        resolved_turn=turn,
        chunks=CORPUS,
        client=client,
        corpus_integrity=matching_integrity(CORPUS),
    )

    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    assert ledger.record_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
        diagnostics=answer_run_diagnostics(result),
    )
    stored = ledger.get_answer_run_diagnostics(
        project_id="current",
        conversation_id="conversation-1",
        turn_id="turn-1",
    )

    assert stored is not None
    assert stored["answer_strategy"] == AnswerStrategy.FULL_CONTEXT.value


def test_an_unresolvable_chunk_id_from_a_live_response_fails_the_turn_closed(patched_generation):
    parsed = coverage_answer(
        (
            FullContextClaim(
                claim_id="C1",
                role=AnswerUnitRole.MECHANISM,
                text="A synthetic process occurred.",
                cited_chunk_ids=("10_Synthetic Chapter 9_ Invented_999",),
                paragraph_group=1,
            ),
        )
    )
    client = patched_generation(parsed)
    turn = ResolvedTurn(standalone_question="What happened?", trusted_user_texts=("What happened?",))

    result = run_full_context_answer(
        resolved_turn=turn,
        chunks=CORPUS,
        client=client,
        corpus_integrity=matching_integrity(CORPUS),
    )

    assert result.status == CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED.value
    assert result.final_chunks == []
    assert (
        result.diagnostics["generation"]["error_code"]
        == FullContextValidationErrorCode.UNRESOLVABLE_CHUNK_ID.value
    )


def test_dispatch_defaults_to_retrieval_and_routes_full_context_when_asked(monkeypatch):
    calls: list[str] = []

    def fake_preflight(**_kwargs):
        return matching_integrity(CORPUS)

    def fake_rag(**_kwargs):
        calls.append("rag")
        return SimpleNamespace(diagnostics={})

    def fake_full_context(**_kwargs):
        calls.append("full_context")
        return SimpleNamespace(diagnostics={})

    monkeypatch.setattr(web_project, "preflight_answer_corpus", fake_preflight)
    monkeypatch.setattr(web_project, "run_evidence_planned_answer", fake_rag)
    monkeypatch.setattr(web_project, "run_full_context_answer", fake_full_context)
    monkeypatch.setattr(web_project, "load_project_chunks", lambda _project_id: CORPUS)
    monkeypatch.setattr(web_project, "openai_client", lambda: object())
    monkeypatch.setattr(
        web_project,
        "chroma_client",
        lambda: SimpleNamespace(get_collection=lambda name: SimpleNamespace(configuration={})),
    )
    monkeypatch.setattr(
        web_project,
        "resolve_conversation_turn",
        lambda question, _history: ResolvedTurn(
            standalone_question=question,
            trusted_user_texts=(question,),
        ),
    )

    web_project.answer_project_question_result("current", "What happened?")
    assert calls == ["rag"]

    web_project.answer_project_question_result(
        "current",
        "What happened?",
        answer_strategy=AnswerStrategy.FULL_CONTEXT,
    )
    assert calls == ["rag", "full_context"]


def test_full_context_modules_do_not_import_the_retrieval_machinery():
    import ast
    from pathlib import Path

    forbidden = {
        # Planner, routing, and facet construction.
        "plan_question",
        "route_question",
        "requires_planning",
        "build_question_plan",
        "QuestionPlan",
        "FacetRole",
        # Ranking, fusion, and neighbor expansion.
        "retrieve_plan_from_collection",
        "retrieve_from_collection",
        "build_hybrid_results",
        "build_context",
        "MAX_FINAL_SOURCES",
        # Evidence gating and stage/obligation contracts.
        "apply_evidence_gate",
        "decide_evidence",
        "classify_evidence_lanes",
        "EvidenceObligationScope",
        "ExpectedStageTransition",
    }
    source_dir = Path(__file__).resolve().parents[1] / "src"

    for module in ("full_context_pipeline.py", "full_context_coverage.py"):
        tree = ast.parse((source_dir / module).read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        leaked = imported & forbidden
        assert not leaked, f"{module} imports retrieval-shaped names: {sorted(leaked)}"
