from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import web_api
import web_project
from model_config import FOLLOWUP_RESOLVER_SETTINGS
from perspectives import AnswerVoice, HistoriographicalLens, Worldview
from query_planning import ResolvedTurn, extract_trusted_targets


CHUNKS = [
    {
        "document": "chapter.md",
        "chapter_title": "A chapter",
        "chunk_id": "chapter_001",
        "paragraph_start": 1,
        "paragraph_end": 2,
        "text": "Synthetic manuscript evidence.",
    }
]


def test_question_request_history_is_optional_and_bounded():
    request = web_api.QuestionRequest(question="Who was this person?")
    assert request.history == []
    assert request.rag_policy_version is None


@pytest.mark.parametrize("mode", ("forest", "cromb_coo_coo", "tidal_archivist"))
def test_hidden_modes_are_rejected_by_the_development_request(mode):
    with pytest.raises(ValueError, match="temporarily unavailable"):
        web_api.QuestionRequest(question="What happened?", archivist_mode=mode)


def test_essential_rejects_prose_only_overrides():
    with pytest.raises(ValueError, match="does not use prose settings"):
        web_api.QuestionRequest(
            question="What happened?",
            archivist_mode="essential",
            voice="romantic",
        )

    turn = {"question": "Who was the person?", "answer": "A synthetic answer."}
    request = web_api.QuestionRequest(question="What happened next?", history=[turn])
    assert request.history[0].question == turn["question"]
    assert request.history[0].answer == turn["answer"]

    with pytest.raises(ValidationError):
        web_api.QuestionRequest(question="Continue.", history=[turn] * 13)
    with pytest.raises(ValidationError):
        web_api.QuestionRequest(question="   ")
    with pytest.raises(ValidationError):
        web_api.QuestionRequest(question="x" * 4_001)


def test_no_history_preserves_question_without_a_resolver_call(monkeypatch):
    monkeypatch.setattr(
        web_project,
        "openai_client",
        lambda: (_ for _ in ()).throw(AssertionError("resolver should not run")),
    )

    assert web_project.resolve_conversation_query("What happened?", []) == "What happened?"


def test_context_resolver_receives_only_bounded_dialogue(monkeypatch):
    captured = {}

    class FakeResponses:
        def parse(
            self,
            *,
            model,
            reasoning,
            text,
            instructions,
            input,
            text_format,
            max_output_tokens,
        ):
            captured.update(
                model=model,
                reasoning=reasoning,
                text=text,
                instructions=instructions,
                input=input,
                text_format=text_format,
                max_output_tokens=max_output_tokens,
            )
            return SimpleNamespace(
                output_parsed=ResolvedTurn(
                    standalone_question=("What happened to the named person afterward?"),
                    entities=("Named Person",),
                    relationship="subsequent events",
                )
            )

    monkeypatch.setattr(
        web_project,
        "openai_client",
        lambda: SimpleNamespace(responses=FakeResponses()),
    )
    history = [
        {"question": f"Question {number}", "answer": f"Answer {number}"} for number in range(8)
    ]

    resolved_turn = web_project.resolve_conversation_turn(
        "What happened next?",
        history,
    )
    resolved = resolved_turn.standalone_question

    assert resolved == "What happened to the named person afterward?"
    assert {
        "model": captured["model"],
        "reasoning": captured["reasoning"],
        "text": captured["text"],
    } == FOLLOWUP_RESOLVER_SETTINGS.responses_create_kwargs()
    assert "Question 0" not in captured["input"]
    assert "Question 1" not in captured["input"]
    assert "Question 2" in captured["input"]
    assert "Answer 7" not in captured["input"]
    assert "prior_user_questions" in captured["input"]
    assert "not supplied" in captured["instructions"].lower()
    assert captured["text_format"] is ResolvedTurn
    assert captured["max_output_tokens"] == web_project.MAX_RESOLVED_TURN_OUTPUT_TOKENS
    assert extract_trusted_targets(resolved_turn)[0].absence_checkable is False


def test_question_endpoint_resolves_then_retrieves_fresh_evidence(monkeypatch):
    calls = []

    def fake_answer(
        project_id,
        question,
        n_results,
        *,
        historiographical_lens,
        voice,
        worldview,
        history,
        answer_strategy="rag",
        application_compiled=False,
    ):
        calls.append(
            (
                "answer",
                project_id,
                question,
                n_results,
                historiographical_lens,
                voice,
                worldview,
                history,
                application_compiled,
            )
        )
        return SimpleNamespace(
            answer="A newly grounded answer [Source 1].",
            final_chunks=CHUNKS,
            status="answered",
            evidence_decision="direct_answer",
            resolved_question="What happened to John Doe afterward?",
        )

    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    request = web_api.QuestionRequest(
        question="What happened to him afterward?",
        history=[
            {
                "question": "Who was John Doe?",
                "answer": "Prior assistant output must not become evidence.",
            }
        ],
    )

    response = web_api.question("current", request)

    assert calls == [
        (
            "answer",
            "current",
            "What happened to him afterward?",
            5,
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.SCHOLARLY,
            Worldview.NONE,
            [
                {
                    "question": "Who was John Doe?",
                    "answer": "Prior assistant output must not become evidence.",
                }
            ],
            True,
        ),
    ]
    assert response["resolved_query"] == "What happened to John Doe afterward?"
    assert response["answer"] == "A newly grounded answer [Source 1]."
    assert response["answer_status"] == "answered"
    assert response["evidence_decision"] == "direct_answer"
    assert response["sources"][0]["text"] == "Synthetic manuscript evidence."


@pytest.mark.parametrize(
    "mode",
    (
        "professional",
        "essential",
        "pretty_pink_princess",
        "baleful_black_baron",
    ),
)
def test_selectable_rag_modes_use_the_application_compiler(monkeypatch, mode):
    captured: dict[str, object] = {}

    class FakeLedger:
        def budget_state(self):
            return {"hard_limit_enabled": False, "exceeded": False}

        def record_answer_run_diagnostics(self, **_kwargs):
            return None

        def summary(self, **_kwargs):
            return None

    def fake_answer(*_args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            answer="A compiled answer [Source 1].",
            final_chunks=CHUNKS,
            status="application_compiled",
            evidence_decision="direct_answer",
            resolved_question="What happened?",
        )

    monkeypatch.setattr(web_api, "UsageLedger", FakeLedger)
    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    monkeypatch.setattr(web_api, "answer_run_diagnostics", lambda _result: {})

    web_api.question(
        "current",
        web_api.QuestionRequest(question="What happened?", archivist_mode=mode),
    )

    assert captured["application_compiled"] is True


@pytest.mark.parametrize(
    ("mode", "strategy", "legacy_perspective"),
    (("forest", "rag", False), ("essential", "full_context", False), ("essential", "rag", True)),
)
def test_hidden_legacy_and_full_context_modes_do_not_select_application_compiler(
    mode,
    strategy,
    legacy_perspective,
):
    assert not web_api._uses_application_compiled_answer(
        archivist_mode=web_api.ArchivistMode(mode),
        answer_strategy=web_api.AnswerStrategy(strategy),
        legacy_perspective=legacy_perspective,
    )


def test_essential_compiler_skips_local_budget_preflight(monkeypatch):
    class NoBudgetLedger:
        def budget_state(self):
            raise AssertionError("providerless compiler must not read the budget")

        def record_answer_run_diagnostics(self, **_kwargs):
            return None

        def summary(self, **_kwargs):
            return None

    captured: dict[str, object] = {}

    def fake_answer(*_args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            answer="A compiled answer [Source 1].",
            final_chunks=CHUNKS,
            status="application_compiled",
            evidence_decision="direct_answer",
            resolved_question="What happened?",
        )

    monkeypatch.setattr(web_api, "UsageLedger", NoBudgetLedger)
    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    monkeypatch.setattr(web_api, "answer_run_diagnostics", lambda _result: {})

    response = web_api.question("current", web_api.QuestionRequest(question="What happened?"))

    assert response["answer_status"] == "application_compiled"
    assert captured["application_compiled"] is True


def test_v27_current_rag_forwards_exact_candidate_policy(monkeypatch):
    captured: dict[str, object] = {}

    class FakeLedger:
        def budget_state(self):
            return {"hard_limit_enabled": False, "exceeded": False}

        def record_answer_run_diagnostics(self, **_kwargs):
            return None

        def summary(self, **_kwargs):
            return None

    def fake_answer(
        project_id,
        question,
        n_results,
        *,
        rag_policy,
        **_kwargs,
    ):
        captured.update(
            project_id=project_id,
            question=question,
            n_results=n_results,
            rag_policy=rag_policy,
        )
        return SimpleNamespace(
            answer="A compact-policy answer [Source 1].",
            final_chunks=CHUNKS,
            status="answered",
            evidence_decision="direct_answer",
            resolved_question=question,
            answer_strategy_version=rag_policy.version,
        )

    monkeypatch.setattr(web_api, "UsageLedger", FakeLedger)
    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    monkeypatch.setattr(
        web_api,
        "answer_run_diagnostics",
        lambda _result: {"schema": "archivist.answer_run_diagnostics/3"},
    )

    response = web_api.question(
        "current",
        web_api.QuestionRequest(
            question="Who was Edwin Sandys?",
            rag_policy_version=web_api.DevelopmentRagPolicyVersion.V27_COMPACT,
        ),
    )

    assert captured["rag_policy"] is web_api.V27_COMPACT_CANDIDATE_POLICY
    assert response["answer_strategy_version"] == web_api.COMPACT_RAG_POLICY_VERSION


def test_explicit_v26_uses_frozen_pipeline_not_application_compiler(monkeypatch):
    captured = {}

    class FakeLedger:
        def budget_state(self):
            return {"hard_limit_enabled": False, "exceeded": False}

        def record_answer_run_diagnostics(self, **_kwargs):
            return None

        def summary(self, **_kwargs):
            return None

    def fake_answer(*_args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            answer="A V26 answer [Source 1].",
            final_chunks=CHUNKS,
            status="answered",
            evidence_decision="direct_answer",
            resolved_question="What happened?",
            answer_strategy_version=web_api.RAG_POLICY_VERSION,
        )

    monkeypatch.setattr(web_api, "UsageLedger", FakeLedger)
    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    monkeypatch.setattr(web_api, "answer_run_diagnostics", lambda _result: {})
    web_api.question(
        "current",
        web_api.QuestionRequest(
            question="What happened?",
            rag_policy_version=web_api.DevelopmentRagPolicyVersion.V26,
        ),
    )
    assert "application_compiled" not in captured
    assert "rag_policy" not in captured


def test_custom_project_keeps_legacy_route_and_budget_semantics(monkeypatch):
    captured = {}

    class FakeLedger:
        def budget_state(self):
            return {"hard_limit_enabled": False, "exceeded": False}

        def record_answer_run_diagnostics(self, **_kwargs):
            return None

        def summary(self, **_kwargs):
            return None

    def fake_answer(*_args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            answer="A custom-project answer [Source 1].",
            final_chunks=CHUNKS,
            status="legacy_answer",
            evidence_decision="legacy_unclassified",
            resolved_question="What happened?",
        )

    monkeypatch.setattr(web_api, "UsageLedger", FakeLedger)
    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    monkeypatch.setattr(web_api, "answer_run_diagnostics", lambda _result: {})
    web_api.question("custom", web_api.QuestionRequest(question="What happened?"))
    assert "application_compiled" not in captured


@pytest.mark.parametrize(
    ("project_id", "answer_strategy", "expected_code"),
    [
        ("custom", "rag", "experimental_rag_policy_unavailable"),
        ("current", "full_context", "experimental_rag_policy_requires_retrieval"),
    ],
)
def test_v27_invalid_scope_fails_before_preflight_or_model_work(
    monkeypatch,
    project_id,
    answer_strategy,
    expected_code,
):
    monkeypatch.setattr(
        web_api,
        "_development_question_preflight",
        lambda _request: (_ for _ in ()).throw(AssertionError("spend preflight must not run")),
    )
    monkeypatch.setattr(
        web_api,
        "answer_project_question_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("model work must not run")),
    )
    request = web_api.QuestionRequest(
        question="What happened?",
        archivist_mode="professional",
        answer_strategy=answer_strategy,
        rag_policy_version=web_api.DevelopmentRagPolicyVersion.V27_COMPACT,
    )

    with pytest.raises(web_api.HTTPException) as exc_info:
        web_api.question(project_id, request)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == expected_code


def test_prior_assistant_output_never_enters_answer_prompt(monkeypatch):
    resolver_inputs = []
    pipeline_inputs = []
    prior_answer = "UNTRUSTED_PRIOR_ASSISTANT_ASSERTION"

    monkeypatch.setattr(web_project, "load_project_chunks", lambda _project_id: CHUNKS)
    monkeypatch.setattr(
        web_project,
        "chroma_client",
        lambda: SimpleNamespace(
            get_collection=lambda **_kwargs: SimpleNamespace(
                configuration={"hnsw": {"space": "l2"}}
            )
        ),
    )

    class FakeResponses:
        def parse(
            self,
            *,
            model,
            reasoning,
            text,
            input,
            instructions,
            text_format,
            max_output_tokens,
        ):
            assert {
                "model": model,
                "reasoning": reasoning,
                "text": text,
            } == FOLLOWUP_RESOLVER_SETTINGS.responses_create_kwargs()
            assert text_format is ResolvedTurn
            assert max_output_tokens == web_project.MAX_RESOLVED_TURN_OUTPUT_TOKENS
            resolver_inputs.append(input)
            return SimpleNamespace(
                output_parsed=ResolvedTurn(
                    standalone_question=("What happened to John Doe afterward?"),
                    entities=("John Doe",),
                    relationship="subsequent events",
                )
            )

    monkeypatch.setattr(
        web_project,
        "openai_client",
        lambda: SimpleNamespace(responses=FakeResponses()),
    )
    monkeypatch.setattr(
        web_project,
        "run_evidence_planned_answer",
        lambda **kwargs: (
            pipeline_inputs.append(kwargs)
            or SimpleNamespace(
                answer="Fresh answer [Source 1].",
                final_chunks=CHUNKS,
            )
        ),
    )
    monkeypatch.setattr(
        web_project,
        "preflight_answer_corpus",
        lambda **_kwargs: SimpleNamespace(passed=True),
    )

    resolved_turn = web_project.resolve_conversation_turn(
        "What happened to him afterward?",
        [{"question": "Who was John Doe?", "answer": prior_answer}],
    )
    web_project.answer_project_question(
        "current",
        resolved_turn.standalone_question,
        resolved_turn=resolved_turn,
    )

    assert prior_answer not in resolver_inputs[0]
    assert pipeline_inputs[0]["resolved_turn"] == resolved_turn
    assert prior_answer not in resolved_turn.model_dump_json()


def test_failed_preflight_skips_paid_followup_resolution(monkeypatch):
    calls = []
    failed_integrity = SimpleNamespace(passed=False)
    collection = SimpleNamespace()

    monkeypatch.setattr(
        web_project,
        "load_project_chunks",
        lambda _project_id: CHUNKS,
    )
    monkeypatch.setattr(
        web_project,
        "chroma_client",
        lambda: SimpleNamespace(
            get_collection=lambda **_kwargs: collection,
        ),
    )
    monkeypatch.setattr(
        web_project,
        "preflight_answer_corpus",
        lambda **_kwargs: calls.append("preflight") or failed_integrity,
    )
    monkeypatch.setattr(
        web_project,
        "resolve_conversation_turn",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("resolver must not run")),
    )
    monkeypatch.setattr(web_project, "openai_client", lambda: object())

    def fake_pipeline(**kwargs):
        calls.append("pipeline")
        assert kwargs["corpus_integrity"] is failed_integrity
        assert kwargs["resolved_turn"] == ResolvedTurn(
            standalone_question="What happened next?",
            trusted_user_texts=("What happened next?",),
        )
        return SimpleNamespace(
            answer="The local index is stale.",
            final_chunks=[],
            status="corpus_integrity_failed",
        )

    monkeypatch.setattr(
        web_project,
        "run_evidence_planned_answer",
        fake_pipeline,
    )

    result = web_project.answer_project_question_result(
        "current",
        "What happened next?",
        history=[{"question": "Who was the person?", "answer": "Prior answer."}],
    )

    assert calls == ["preflight", "pipeline"]
    assert result.status == "corpus_integrity_failed"
    assert {
        "preflight",
        "conversation_resolution",
        "total",
    }.issubset(result.diagnostics["stage_timings_ms"])
    assert all(value >= 0 for value in result.diagnostics["stage_timings_ms"].values())
