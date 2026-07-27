import inspect
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import prompts
import web_api
import web_project
from perspectives import (
    ANSWER_VOICES,
    HISTORIOGRAPHICAL_LENSES,
    INTERPRETIVE_EXPANSION_RULES,
    INTERPRETIVE_GUARDRAILS,
    INTERPRETIVE_PROMPT_DIR,
    INTERPRETIVE_RESPONSE_RULES,
    PERSPECTIVE_PROMPT_DIR,
    PERSPECTIVES,
    WORLDVIEWS,
    AnswerPerspective,
    AnswerVoice,
    HistoriographicalLens,
    Worldview,
    build_interpretive_prompt_block,
    load_answer_voice_prompt,
    load_historiographical_lens_prompt,
    load_perspective_prompt,
    load_worldview_prompt,
    requires_interpretive_expansion,
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
    assert INTERPRETIVE_RESPONSE_RULES not in expected


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


@pytest.mark.parametrize(
    ("lens", "voice", "worldview"),
    [
        (
            HistoriographicalLens.TRIUMPHALIST,
            AnswerVoice.SCHOLARLY,
            Worldview.NONE,
        ),
        (
            HistoriographicalLens.TRAGIC,
            AnswerVoice.SCHOLARLY,
            Worldview.NONE,
        ),
        (
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.PLAINSPOKEN,
            Worldview.NONE,
        ),
        (
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.ROMANTIC,
            Worldview.NONE,
        ),
        (
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.SCHOLARLY,
            Worldview.PIOUS,
        ),
        (
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.SCHOLARLY,
            Worldview.SECULAR_HUMANIST,
        ),
        (
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.SCHOLARLY,
            Worldview.ENLIGHTENMENT_RATIONALIST,
        ),
    ],
)
def test_each_non_default_facet_enables_conversational_interpretive_rules(
    lens, voice, worldview
):
    prompt = build_interpretive_answer_prompt(
        "What happened?",
        CHUNKS,
        lens,
        voice,
        worldview,
    )

    assert prompt.count(INTERPRETIVE_RESPONSE_RULES) == 1


def test_single_active_facet_does_not_emit_default_facet_sections():
    block = build_interpretive_prompt_block(
        HistoriographicalLens.EVIDENCE_FIRST,
        AnswerVoice.ROMANTIC,
        Worldview.NONE,
    )

    assert block.count(INTERPRETIVE_RESPONSE_RULES) == 1
    assert "Selected Voice:" in block
    assert "Selected Historiographical lens:" not in block
    assert "Selected Worldview:" not in block


def test_lens_or_worldview_requires_a_subjective_frame_around_the_evidence():
    assert requires_interpretive_expansion(
        HistoriographicalLens.TRAGIC,
        Worldview.NONE,
    )
    assert requires_interpretive_expansion(
        HistoriographicalLens.EVIDENCE_FIRST,
        Worldview.PIOUS,
    )

    for block in (
        build_interpretive_prompt_block(
            HistoriographicalLens.TRAGIC,
            AnswerVoice.SCHOLARLY,
            Worldview.NONE,
        ),
        build_interpretive_prompt_block(
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.SCHOLARLY,
            Worldview.PIOUS,
        ),
    ):
        assert INTERPRETIVE_EXPANSION_RULES in block
        assert "two or three sentences" in block
        assert "ordinary source-grounded factual answer" in block
        assert "question's subject" in block
        assert "first-person" in block
        assert "one cohesive answer" in block
        assert "no headings, labels" in block


def test_triumphalist_prompt_requires_an_unmistakable_non_neutral_judgment():
    prompt = load_historiographical_lens_prompt(
        HistoriographicalLens.TRIUMPHALIST
    )
    normalized = " ".join(prompt.split())

    assert "deliberately and unmistakably triumphalist" in normalized
    assert "close on accomplishment" in normalized
    assert "canceling itself with a neutral qualification" in normalized


def test_tragic_prompt_conditions_the_judgment_on_concrete_factual_tension():
    prompt = load_historiographical_lens_prompt(HistoriographicalLens.TRAGIC)
    normalized = " ".join(prompt.split())

    assert "concrete tension already present in the factual middle" in normalized
    assert "Do not manufacture a tragedy" in normalized
    assert 'generic "human cost," "better possibilities," "moral burden,"' in normalized
    assert "Genuine achievement must remain genuine achievement" in normalized
    assert "state that tension proportionately" in normalized


def test_stacked_settings_form_one_judgment_instead_of_multiplying_themes():
    block = build_interpretive_prompt_block(
        HistoriographicalLens.TRAGIC,
        AnswerVoice.ROMANTIC,
        Worldview.PIOUS,
    )
    normalized = " ".join(block.split())

    assert "one coherent interpretive judgment" in normalized
    assert "do not stack independent moral themes" in normalized
    assert "smallest fitting moral frame" in normalized
    assert "adding a second thesis" in normalized


def test_voice_alone_changes_expression_without_forcing_a_longer_answer():
    block = build_interpretive_prompt_block(
        HistoriographicalLens.EVIDENCE_FIRST,
        AnswerVoice.ROMANTIC,
        Worldview.NONE,
    )

    assert not requires_interpretive_expansion(
        HistoriographicalLens.EVIDENCE_FIRST,
        Worldview.NONE,
    )
    assert INTERPRETIVE_RESPONSE_RULES in block
    assert INTERPRETIVE_EXPANSION_RULES not in block


@pytest.mark.parametrize(
    "perspective",
    [
        AnswerPerspective.TRIUMPHALIST,
        AnswerPerspective.TRAGIC,
        AnswerPerspective.PIOUS,
        AnswerPerspective.ROMANTIC,
    ],
)
def test_legacy_non_neutral_perspectives_enable_interpretive_rules_once(perspective):
    prompt = build_perspective_answer_prompt("What happened?", CHUNKS, perspective)

    assert prompt.count(INTERPRETIVE_RESPONSE_RULES) == 1


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
    pipeline_calls = []
    monkeypatch.setattr(web_project, "load_project_chunks", lambda _project_id: CHUNKS)
    monkeypatch.setattr(
        web_project,
        "chroma_client",
        lambda: SimpleNamespace(
            get_collection=lambda **_kwargs: SimpleNamespace(configuration={})
        ),
    )
    monkeypatch.setattr(
        web_project,
        "openai_client",
        lambda: object(),
    )
    monkeypatch.setattr(
        web_project,
        "preflight_answer_corpus",
        lambda **_kwargs: SimpleNamespace(passed=True),
    )
    monkeypatch.setattr(
        web_project,
        "run_evidence_planned_answer",
        lambda **kwargs: (
            pipeline_calls.append(kwargs)
            or SimpleNamespace(
                answer="Synthetic answer [Source 1].",
                final_chunks=CHUNKS,
            )
        ),
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

    assert len(pipeline_calls) == len(settings)
    assert all(call["chunks"] == CHUNKS for call in pipeline_calls)
    assert all(call["n_results"] == 5 for call in pipeline_calls)
    assert all(
        call["resolved_turn"].standalone_question == "What happened?"
        for call in pipeline_calls
    )
    assert all(chunks == CHUNKS for _answer, chunks in outputs)
    assert {
        (
            call["historiographical_lens"],
            call["voice"],
            call["worldview"],
        )
        for call in pipeline_calls
    } == {
        (
            selected.get(
                "historiographical_lens",
                HistoriographicalLens.EVIDENCE_FIRST,
            ),
            selected.get("voice", AnswerVoice.SCHOLARLY),
            selected.get("worldview", Worldview.NONE),
        )
        for selected in settings
    }


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
        history,
    ):
        captured.update(
            project_id=project_id,
            question=question,
            n_results=n_results,
            historiographical_lens=historiographical_lens,
            voice=voice,
            worldview=worldview,
        )
        return SimpleNamespace(
            answer="Synthetic answer [Source 1].",
            final_chunks=CHUNKS[:1],
            status="answered",
            evidence_decision="direct_answer",
            resolved_question=question,
        )

    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
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
