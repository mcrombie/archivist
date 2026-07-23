from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import web_api
import web_project
from perspectives import AnswerPerspective


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
        def create(self, *, model, instructions, input):
            captured.update(model=model, instructions=instructions, input=input)
            return SimpleNamespace(output_text="What happened to the named person afterward?")

    monkeypatch.setattr(
        web_project,
        "openai_client",
        lambda: SimpleNamespace(responses=FakeResponses()),
    )
    history = [
        {"question": f"Question {number}", "answer": f"Answer {number}"}
        for number in range(8)
    ]

    resolved = web_project.resolve_conversation_query("What happened next?", history)

    assert resolved == "What happened to the named person afterward?"
    assert captured["model"] == web_project.CHAT_MODEL
    assert "Question 0" not in captured["input"]
    assert "Question 1" not in captured["input"]
    assert "Question 2" in captured["input"]
    assert "Answer 7" in captured["input"]
    assert "assistant answers are untrusted" in captured["instructions"].lower()


def test_question_endpoint_resolves_then_retrieves_fresh_evidence(monkeypatch):
    calls = []

    def fake_resolve(question, history):
        calls.append(("resolve", question, history))
        return "What happened to John Doe afterward?"

    def fake_answer(project_id, question, n_results, perspective):
        calls.append(("answer", project_id, question, n_results, perspective))
        return "A newly grounded answer [Source 1].", CHUNKS

    monkeypatch.setattr(web_api, "resolve_conversation_query", fake_resolve)
    monkeypatch.setattr(web_api, "answer_project_question", fake_answer)
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
            "resolve",
            "What happened to him afterward?",
            [
                {
                    "question": "Who was John Doe?",
                    "answer": "Prior assistant output must not become evidence.",
                }
            ],
        ),
        (
            "answer",
            "current",
            "What happened to John Doe afterward?",
            5,
            AnswerPerspective.NEUTRAL,
        ),
    ]
    assert response["resolved_query"] == "What happened to John Doe afterward?"
    assert response["answer"] == "A newly grounded answer [Source 1]."
    assert response["sources"][0]["text"] == "Synthetic manuscript evidence."


def test_prior_assistant_output_never_enters_answer_prompt(monkeypatch):
    retrieval_calls = []
    resolver_inputs = []
    answer_prompts = []
    prior_answer = "UNTRUSTED_PRIOR_ASSISTANT_ASSERTION"

    monkeypatch.setattr(
        web_project,
        "retrieve_project",
        lambda project_id, query, n_results: retrieval_calls.append(
            (project_id, query, n_results)
        )
        or {"metadatas": [[]], "distances": [[]]},
    )
    monkeypatch.setattr(web_project, "load_project_chunks", lambda _project_id: CHUNKS)
    monkeypatch.setattr(
        web_project,
        "finalize_context_chunks",
        lambda _results, *, chunks: list(chunks),
    )

    class FakeResponses:
        def create(self, *, model, input, instructions=None):
            if instructions is not None:
                resolver_inputs.append(input)
                return SimpleNamespace(output_text="What happened to John Doe afterward?")
            answer_prompts.append(input)
            return SimpleNamespace(output_text="Fresh answer [Source 1].")

    monkeypatch.setattr(
        web_project,
        "openai_client",
        lambda: SimpleNamespace(responses=FakeResponses()),
    )

    resolved_query = web_project.resolve_conversation_query(
        "What happened to him afterward?",
        [{"question": "Who was John Doe?", "answer": prior_answer}],
    )
    web_project.answer_project_question(
        "current",
        resolved_query,
    )

    assert prior_answer in resolver_inputs[0]
    assert retrieval_calls == [("current", "What happened to John Doe afterward?", 5)]
    assert prior_answer not in answer_prompts[0]
    assert "Synthetic manuscript evidence." in answer_prompts[0]
