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
                    standalone_question=(
                        "What happened to the named person afterward?"
                    ),
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
        {"question": f"Question {number}", "answer": f"Answer {number}"}
        for number in range(8)
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
    assert (
        captured["max_output_tokens"]
        == web_project.MAX_RESOLVED_TURN_OUTPUT_TOKENS
    )
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
        ),
    ]
    assert response["resolved_query"] == "What happened to John Doe afterward?"
    assert response["answer"] == "A newly grounded answer [Source 1]."
    assert response["answer_status"] == "answered"
    assert response["evidence_decision"] == "direct_answer"
    assert response["sources"][0]["text"] == "Synthetic manuscript evidence."


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
            assert (
                max_output_tokens
                == web_project.MAX_RESOLVED_TURN_OUTPUT_TOKENS
            )
            resolver_inputs.append(input)
            return SimpleNamespace(
                output_parsed=ResolvedTurn(
                    standalone_question=(
                        "What happened to John Doe afterward?"
                    ),
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
        lambda **_kwargs: (
            calls.append("preflight") or failed_integrity
        ),
    )
    monkeypatch.setattr(
        web_project,
        "resolve_conversation_turn",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("resolver must not run")
        ),
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
