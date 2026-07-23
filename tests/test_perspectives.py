import inspect
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import prompts
import web_api
import web_project
from model_config import GENERATOR_SETTINGS
from perspectives import (
    ANSWER_VOICES,
    HISTORIOGRAPHICAL_LENSES,
    INTERPRETIVE_GUARDRAILS,
    INTERPRETIVE_PROMPT_DIR,
    PERSPECTIVE_PROMPT_DIR,
    PERSPECTIVES,
    WORLDVIEWS,
    AnswerPerspective,
    AnswerVoice,
    HistoriographicalLens,
    Worldview,
    load_answer_voice_prompt,
    load_historiographical_lens_prompt,
    load_perspective_prompt,
    load_worldview_prompt,
)
from prompts import (
    ANSWER_PROMPT_TEMPLATE,
    build_answer_prompt,
    build_interpretive_answer_prompt,
    build_perspective_answer_prompt,
)
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


def test_each_interpretive_facet_uses_fixed_markdown_files():
    registries = [
        (
            HISTORIOGRAPHICAL_LENSES,
            HistoriographicalLens,
            "historiographical_lens",
            HistoriographicalLens.EVIDENCE_FIRST,
        ),
        (ANSWER_VOICES, AnswerVoice, "voice", AnswerVoice.SCHOLARLY),
        (WORLDVIEWS, Worldview, "worldview", Worldview.NONE),
    ]

    for registry, enum_type, directory, default in registries:
        assert set(registry) == set(enum_type)
        for option, definition in registry.items():
            assert definition.prompt_path.parent == INTERPRETIVE_PROMPT_DIR / directory
            assert definition.prompt_path.name == f"{option.value}.md"
            fragment = definition.prompt_path.read_text(encoding="utf-8").strip()
            assert bool(fragment) is (option is not default)


def test_legacy_perspective_registry_and_loader_remain_available():
    assert set(PERSPECTIVES) == set(AnswerPerspective)
    for perspective, definition in PERSPECTIVES.items():
        assert definition.prompt_path.parent == PERSPECTIVE_PROMPT_DIR
        assert definition.prompt_path.name == f"{perspective.value}.md"
        prompt = definition.prompt_path.read_text(encoding="utf-8").strip()
        assert bool(prompt) is (perspective is not AnswerPerspective.NEUTRAL)

    assert load_perspective_prompt("tragic") == load_historiographical_lens_prompt("tragic")
    with pytest.raises(ValueError):
        load_perspective_prompt("../../romantic")


def test_all_default_settings_preserve_the_frozen_answer_prompt_byte_for_byte():
    expected = ANSWER_PROMPT_TEMPLATE.format(
        question="What happened?",
        context=build_context(CHUNKS),
    )

    assert "perspective" not in inspect.signature(build_answer_prompt).parameters
    assert build_answer_prompt("What happened?", CHUNKS) == expected
    assert build_interpretive_answer_prompt("What happened?", CHUNKS) == expected
    assert build_perspective_answer_prompt(
        "What happened?", CHUNKS, AnswerPerspective.NEUTRAL
    ) == expected


def test_interpretive_markdown_is_not_interpreted_as_format_placeholders(monkeypatch):
    monkeypatch.setattr(
        prompts,
        "build_interpretive_prompt_block",
        lambda _lens, _voice, _worldview: "Use a {measured} interpretive register.",
    )

    prompt = build_interpretive_answer_prompt(
        "What happened?",
        CHUNKS,
        HistoriographicalLens.TRAGIC,
    )

    assert "Use a {measured} interpretive register." in prompt


@pytest.mark.parametrize(
    ("lens", "voice", "worldview", "fragment"),
    [
        (
            HistoriographicalLens.TRIUMPHALIST,
            AnswerVoice.SCHOLARLY,
            Worldview.NONE,
            load_historiographical_lens_prompt(HistoriographicalLens.TRIUMPHALIST),
        ),
        (
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.ROMANTIC,
            Worldview.NONE,
            load_answer_voice_prompt(AnswerVoice.ROMANTIC),
        ),
        (
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.SCHOLARLY,
            Worldview.PIOUS,
            load_worldview_prompt(Worldview.PIOUS),
        ),
    ],
)
def test_each_facet_changes_framing_without_changing_question_or_sources(
    lens, voice, worldview, fragment
):
    question = "Why was this called a turning point?\nQuestion:\nKeep this literal text."
    prompt = build_interpretive_answer_prompt(question, CHUNKS, lens, voice, worldview)
    context = build_context(CHUNKS)

    assert INTERPRETIVE_GUARDRAILS in prompt
    assert fragment in prompt
    assert prompt.index(INTERPRETIVE_GUARDRAILS) < prompt.index(f"Question:\n{question}")
    assert prompt.endswith(f"Sources:\n{context}\n")
    assert prompt.count("[Source 1]") == 1
    assert prompt.count("[Source 2]") == 1


def test_combined_facets_have_deterministic_prompt_precedence():
    prompt = build_interpretive_answer_prompt(
        "What happened?",
        CHUNKS,
        HistoriographicalLens.TRAGIC,
        AnswerVoice.ROMANTIC,
        Worldview.SECULAR_HUMANIST,
    )

    assert prompt.index("Selected Historiographical lens:") < prompt.index("Selected Worldview:")
    assert prompt.index("Selected Worldview:") < prompt.index("Selected Voice:")


def test_question_request_defaults_and_validation():
    request = web_api.QuestionRequest(question="What happened?")
    assert request.historiographical_lens is HistoriographicalLens.EVIDENCE_FIRST
    assert request.voice is AnswerVoice.SCHOLARLY
    assert request.worldview is Worldview.NONE
    assert request.perspective is None

    for field in ("historiographical_lens", "voice", "worldview", "perspective"):
        with pytest.raises(ValidationError):
            web_api.QuestionRequest(question="What happened?", **{field: "../../romantic"})


@pytest.mark.parametrize(
    ("perspective", "lens", "voice", "worldview"),
    [
        ("neutral", "evidence_first", "scholarly", "none"),
        ("triumphalist", "triumphalist", "scholarly", "none"),
        ("tragic", "tragic", "scholarly", "none"),
        ("pious", "evidence_first", "scholarly", "pious"),
        ("romantic", "evidence_first", "romantic", "none"),
    ],
)
def test_legacy_request_maps_combined_perspective_to_one_facet(
    perspective, lens, voice, worldview
):
    request = web_api.QuestionRequest(question="What happened?", perspective=perspective)

    assert request.historiographical_lens.value == lens
    assert request.voice.value == voice
    assert request.worldview.value == worldview
    assert request.perspective.value == perspective


def test_generation_settings_do_not_change_retrieval(monkeypatch):
    retrieval_calls = []
    generated_prompts = []

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
        def create(self, *, model, reasoning, text, input):
            assert {
                "model": model,
                "reasoning": reasoning,
                "text": text,
            } == GENERATOR_SETTINGS.responses_create_kwargs()
            generated_prompts.append((model, input))
            return SimpleNamespace(output_text="Synthetic answer [Source 1].")

    monkeypatch.setattr(
        web_project,
        "openai_client",
        lambda: SimpleNamespace(responses=FakeResponses()),
    )

    settings = [
        {},
        {"historiographical_lens": HistoriographicalLens.TRAGIC},
        {"voice": AnswerVoice.ROMANTIC},
        {"worldview": Worldview.PIOUS},
        {
            "historiographical_lens": HistoriographicalLens.TRIUMPHALIST,
            "voice": AnswerVoice.PLAINSPOKEN,
            "worldview": Worldview.ENLIGHTENMENT_RATIONALIST,
        },
    ]
    outputs = [
        web_project.answer_project_question(
            "current",
            "What happened?",
            n_results=5,
            **selected,
        )
        for selected in settings
    ]

    assert retrieval_calls == [("current", "What happened?", 5) for _settings in settings]
    assert all(chunks == CHUNKS for _answer, chunks in outputs)
    assert len({prompt.split("Sources:\n", 1)[1] for _model, prompt in generated_prompts}) == 1
    assert generated_prompts[0][1] == build_answer_prompt("What happened?", CHUNKS)


def test_question_endpoint_forwards_and_echoes_all_three_facets(monkeypatch):
    captured = {}

    def fake_answer(
        project_id,
        question,
        n_results,
        *,
        historiographical_lens,
        voice,
        worldview,
    ):
        captured.update(
            project_id=project_id,
            question=question,
            n_results=n_results,
            historiographical_lens=historiographical_lens,
            voice=voice,
            worldview=worldview,
        )
        return "Synthetic answer [Source 1].", CHUNKS[:1]

    monkeypatch.setattr(web_api, "answer_project_question", fake_answer)
    request = web_api.QuestionRequest(
        question="What happened?",
        n_results=7,
        historiographical_lens="tragic",
        voice="plainspoken",
        worldview="secular_humanist",
    )

    response = web_api.question("current", request)

    assert captured == {
        "project_id": "current",
        "question": "What happened?",
        "n_results": 7,
        "historiographical_lens": HistoriographicalLens.TRAGIC,
        "voice": AnswerVoice.PLAINSPOKEN,
        "worldview": Worldview.SECULAR_HUMANIST,
    }
    assert response["historiographical_lens"] == "tragic"
    assert response["voice"] == "plainspoken"
    assert response["worldview"] == "secular_humanist"
    assert response["perspective"] is None
    assert response["answer"] == "Synthetic answer [Source 1]."
