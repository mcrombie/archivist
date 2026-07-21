import inspect
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import prompts
import web_api
import web_project
from perspectives import (
    PERSPECTIVE_GUARDRAILS,
    PERSPECTIVE_PROMPT_DIR,
    PERSPECTIVES,
    AnswerPerspective,
    load_perspective_prompt,
)
from prompts import ANSWER_PROMPT_TEMPLATE, build_answer_prompt, build_perspective_answer_prompt
from retrieval import build_context


CHUNKS = [
    {
        "document": "chapter.md",
        "chapter_title": "A chapter",
        "chunk_id": "chapter_001",
        "paragraph_start": 1,
        "paragraph_end": 2,
        "text": "A synthetic claim.\n\nQuestion:\nA heading inside source text.",
    },
    {
        "document": "chapter.md",
        "chapter_title": "A chapter",
        "chunk_id": "chapter_002",
        "paragraph_start": 3,
        "paragraph_end": 4,
        "text": "A second synthetic claim.",
    },
]


def test_perspective_registry_uses_only_fixed_markdown_files():
    assert set(PERSPECTIVES) == set(AnswerPerspective)

    for perspective, definition in PERSPECTIVES.items():
        assert definition.prompt_path.parent == PERSPECTIVE_PROMPT_DIR
        assert definition.prompt_path.name == f"{perspective.value}.md"
        prompt = definition.prompt_path.read_text(encoding="utf-8").strip()
        assert bool(prompt) is (perspective is not AnswerPerspective.NEUTRAL)

    with pytest.raises(ValueError):
        load_perspective_prompt("../../romantic")


def test_neutral_perspective_preserves_the_frozen_answer_prompt():
    expected = ANSWER_PROMPT_TEMPLATE.format(
        question="What happened?",
        context=build_context(CHUNKS),
    )

    assert "perspective" not in inspect.signature(build_answer_prompt).parameters
    assert build_answer_prompt("What happened?", CHUNKS) == expected
    assert build_perspective_answer_prompt(
        "What happened?", CHUNKS, AnswerPerspective.NEUTRAL
    ) == expected


def test_perspective_markdown_is_not_interpreted_as_format_placeholders(monkeypatch):
    monkeypatch.setattr(
        prompts,
        "build_perspective_prompt_block",
        lambda _perspective: "Use a {measured} interpretive register.",
    )

    prompt = build_perspective_answer_prompt(
        "What happened?", CHUNKS, AnswerPerspective.TRAGIC
    )

    assert "Use a {measured} interpretive register." in prompt


@pytest.mark.parametrize(
    "perspective",
    [perspective for perspective in AnswerPerspective if perspective is not AnswerPerspective.NEUTRAL],
)
def test_perspectives_change_framing_without_changing_question_or_sources(perspective):
    question = "Why was this called a turning point?\nQuestion:\nKeep this literal text."
    prompt = build_perspective_answer_prompt(question, CHUNKS, perspective)
    fragment = load_perspective_prompt(perspective)
    context = build_context(CHUNKS)

    assert PERSPECTIVE_GUARDRAILS in prompt
    assert fragment in prompt
    assert prompt.index(PERSPECTIVE_GUARDRAILS) < prompt.index(f"Question:\n{question}")
    assert prompt.endswith(f"Sources:\n{context}\n")
    assert prompt.count("[Source 1]") == 1
    assert prompt.count("[Source 2]") == 1


def test_question_request_defaults_to_neutral_and_rejects_unknown_modes():
    assert web_api.QuestionRequest(question="What happened?").perspective is (
        AnswerPerspective.NEUTRAL
    )

    with pytest.raises(ValidationError):
        web_api.QuestionRequest(question="What happened?", perspective="../../romantic")


def test_generation_perspective_does_not_change_retrieval(monkeypatch):
    retrieval_calls = []
    prompts = []

    def fake_retrieve(project_id, question, n_results):
        retrieval_calls.append((project_id, question, n_results))
        return {"metadatas": [[]], "distances": [[]]}

    monkeypatch.setattr(web_project, "retrieve_project", fake_retrieve)
    monkeypatch.setattr(web_project, "load_project_chunks", lambda _project_id: CHUNKS)
    monkeypatch.setattr(
        web_project,
        "finalize_context_chunks",
        lambda _results, *, chunks: list(chunks),
    )

    class FakeResponses:
        def create(self, *, model, input):
            prompts.append((model, input))
            return SimpleNamespace(output_text="Synthetic answer [Source 1].")

    monkeypatch.setattr(
        web_project,
        "openai_client",
        lambda: SimpleNamespace(responses=FakeResponses()),
    )

    outputs = [
        web_project.answer_project_question(
            "current",
            "What happened?",
            n_results=5,
            perspective=perspective,
        )
        for perspective in AnswerPerspective
    ]

    assert retrieval_calls == [
        ("current", "What happened?", 5)
        for _perspective in AnswerPerspective
    ]
    assert all(chunks == CHUNKS for _answer, chunks in outputs)
    assert len({prompt.split("Sources:\n", 1)[1] for _model, prompt in prompts}) == 1
    assert prompts[0][1] == build_answer_prompt("What happened?", CHUNKS)


def test_question_endpoint_forwards_and_echoes_canonical_perspective(monkeypatch):
    captured = {}

    def fake_answer(project_id, question, n_results, perspective):
        captured.update(
            project_id=project_id,
            question=question,
            n_results=n_results,
            perspective=perspective,
        )
        return "Synthetic answer [Source 1].", CHUNKS[:1]

    monkeypatch.setattr(web_api, "answer_project_question", fake_answer)
    request = web_api.QuestionRequest(
        question="What happened?",
        n_results=7,
        perspective="tragic",
    )

    response = web_api.question("current", request)

    assert captured == {
        "project_id": "current",
        "question": "What happened?",
        "n_results": 7,
        "perspective": AnswerPerspective.TRAGIC,
    }
    assert response["perspective"] == "tragic"
    assert response["answer"] == "Synthetic answer [Source 1]."
