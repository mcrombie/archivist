from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import web_api
import web_project
from archivist_modes import (
    ARCHIVIST_MODES,
    INFLUENCE_PROFILES,
    ArchivistMode,
    archivist_mode_metadata,
    build_archivist_mode_prompt_block,
)
from perspectives import AnswerVoice, HistoriographicalLens, Worldview
from prompts import build_answer_prompt, build_interpretive_answer_prompt


CHUNKS = [
    {
        "document": "chapter.md",
        "chapter_title": "A chapter",
        "chunk_id": "chapter_001",
        "paragraph_start": 1,
        "paragraph_end": 2,
        "text": "A synthetic manuscript claim.",
    }
]


def test_mode_registry_is_allowlisted_and_versioned():
    assert set(ARCHIVIST_MODES) == {
        ArchivistMode.PROFESSIONAL,
        ArchivistMode.ESSENTIAL,
        ArchivistMode.FOREST,
    }
    assert set(INFLUENCE_PROFILES) == {
        "none",
        "professional_public_history",
        "dunsany_elfland",
    }
    assert all(definition.version for definition in ARCHIVIST_MODES.values())
    assert all(profile.version for profile in INFLUENCE_PROFILES.values())


def test_omitted_mode_is_essential_and_preserves_the_prompt_byte_for_byte():
    request = web_api.QuestionRequest(question="What happened?")
    expected = build_answer_prompt("What happened?", CHUNKS)

    assert request.archivist_mode is ArchivistMode.ESSENTIAL
    assert "archivist_mode" not in request.model_fields_set
    assert build_archivist_mode_prompt_block() == ""
    assert build_interpretive_answer_prompt("What happened?", CHUNKS) == expected
    assert (
        build_interpretive_answer_prompt(
            "What happened?",
            CHUNKS,
            archivist_mode=ArchivistMode.ESSENTIAL,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("mode", "lens", "voice", "worldview"),
    [
        (
            "professional",
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.PLAINSPOKEN,
            Worldview.SECULAR_HUMANIST,
        ),
        (
            "essential",
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.SCHOLARLY,
            Worldview.NONE,
        ),
        (
            "forest",
            HistoriographicalLens.TRAGIC,
            AnswerVoice.ROMANTIC,
            Worldview.NONE,
        ),
    ],
)
def test_explicit_mode_resolves_defaults(mode, lens, voice, worldview):
    request = web_api.QuestionRequest(
        question="What happened?",
        archivist_mode=mode,
    )

    assert request.historiographical_lens is lens
    assert request.voice is voice
    assert request.worldview is worldview


def test_advanced_facets_override_mode_defaults():
    request = web_api.QuestionRequest(
        question="What happened?",
        archivist_mode="forest",
        historiographical_lens="evidence_first",
        voice="plainspoken",
        worldview="enlightenment_rationalist",
    )

    assert request.historiographical_lens is HistoriographicalLens.EVIDENCE_FIRST
    assert request.voice is AnswerVoice.PLAINSPOKEN
    assert request.worldview is Worldview.ENLIGHTENMENT_RATIONALIST


def test_unknown_mode_is_rejected_before_generation():
    with pytest.raises(ValidationError):
        web_api.QuestionRequest(
            question="What happened?",
            archivist_mode="../../unknown",
        )


def test_forest_profile_is_generation_only_and_forbids_fictional_leakage():
    block = build_archivist_mode_prompt_block(archivist_mode="forest")
    normalized = " ".join(block.split())

    assert "Dunsany" not in block
    assert "King of Elfland" not in block
    assert "never historical evidence" in normalized
    assert "Do not import, allude to, paraphrase, or quote" in normalized
    assert "characters, places, events, lore, images, phrases, or claims" in normalized
    assert "all historical content and every citation" in normalized


def test_professional_profile_is_multicausal_without_becoming_evidence():
    block = build_archivist_mode_prompt_block(archivist_mode="professional")
    normalized = " ".join(block.split())

    assert all(name not in block for name in ("Craven", "Beard", "Du Bois"))
    assert "institutions, material interests, racialized power, and enforcement" in normalized
    assert "intended design from actual operation" in normalized
    assert (
        "must never supply a name, event, date, quotation, motive, causal link, or fact"
        in normalized
    )


def test_exact_provenance_stays_in_metadata_not_the_generation_prompt():
    metadata = archivist_mode_metadata("forest")
    prompt = build_archivist_mode_prompt_block(archivist_mode="forest")
    provenance = metadata["influence_provenance"][0]

    assert provenance["source_url"] == ("https://www.gutenberg.org/ebooks/61077.epub3.images")
    assert provenance["artifact_modified_at"] == "2026-07-30T00:38:46Z"
    assert provenance["source_sha256"] not in prompt
    assert provenance["source_url"] not in prompt
    assert provenance["artifact_modified_at"] not in prompt
    assert provenance["rights_note"] not in prompt
    assert provenance["title"] not in prompt
    assert provenance["creator"] not in prompt


def test_professional_profile_freezes_the_three_reviewed_artifacts():
    metadata = archivist_mode_metadata("professional")
    prompt = build_archivist_mode_prompt_block(archivist_mode="professional")
    provenance = metadata["influence_provenance"]

    assert [item["source_identifier"] for item in provenance] == [
        "project-gutenberg:28555",
        "project-gutenberg:70677",
        "project-gutenberg:17700",
    ]
    assert [item["artifact_modified_at"] for item in provenance] == [
        "2026-07-11T18:03:12Z",
        "2026-07-28T15:16:10Z",
        "2026-07-07T20:37:24Z",
    ]
    assert [item["source_sha256"] for item in provenance] == [
        "7b6475993d63a640a8fae1044d342dbcb9d71321649357c52a0424e484d2596c",
        "3359e7ef549af9281ffca2656aec82588ae1dc04017f05fdced4a5765e3ab16e",
        "08e428081e076e724cb91ba10229ed95ec66f53ef2e1d4e9c6875d3fda7a3b9b",
    ]
    for item in provenance:
        assert item["source_url"] not in prompt
        assert item["source_sha256"] not in prompt
        assert item["artifact_modified_at"] not in prompt
        assert item["rights_note"] not in prompt


def test_modes_do_not_change_retrieval_inputs(monkeypatch):
    calls = []
    monkeypatch.setattr(web_project, "load_project_chunks", lambda _project_id: CHUNKS)
    monkeypatch.setattr(
        web_project,
        "chroma_client",
        lambda: SimpleNamespace(get_collection=lambda **_kwargs: SimpleNamespace(configuration={})),
    )
    monkeypatch.setattr(web_project, "openai_client", lambda: object())
    monkeypatch.setattr(
        web_project,
        "preflight_answer_corpus",
        lambda **_kwargs: SimpleNamespace(passed=True),
    )

    def fake_pipeline(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            answer="Synthetic answer [Source 1].",
            final_chunks=CHUNKS,
            status="answered",
            evidence_decision="direct_answer",
            diagnostics={},
        )

    monkeypatch.setattr(web_project, "run_evidence_planned_answer", fake_pipeline)

    for mode in (ArchivistMode.ESSENTIAL, ArchivistMode.FOREST):
        web_project.answer_project_question_result(
            "current",
            "What happened?",
            n_results=5,
            archivist_mode=mode,
        )

    assert len(calls) == 2
    for call in calls:
        assert call["chunks"] == CHUNKS
        assert call["n_results"] == 5
        assert call["resolved_turn"].standalone_question == "What happened?"
    assert calls[0]["archivist_mode"] is ArchivistMode.ESSENTIAL
    assert calls[1]["archivist_mode"] is ArchivistMode.FOREST


def test_question_api_forwards_and_echoes_mode_metadata(monkeypatch):
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
        archivist_mode,
        answer_strategy="rag",
    ):
        captured.update(
            project_id=project_id,
            question=question,
            n_results=n_results,
            archivist_mode=archivist_mode,
            historiographical_lens=historiographical_lens,
            voice=voice,
            worldview=worldview,
            history=history,
        )
        return SimpleNamespace(
            answer="Synthetic answer [Source 1].",
            final_chunks=CHUNKS,
            status="answered",
            evidence_decision="direct_answer",
            diagnostics={},
            resolved_question=question,
        )

    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    request = web_api.QuestionRequest(
        question="What happened?",
        archivist_mode="forest",
    )

    response = web_api.question("current", request)

    assert captured["archivist_mode"] is ArchivistMode.FOREST
    assert captured["historiographical_lens"] is HistoriographicalLens.TRAGIC
    assert captured["voice"] is AnswerVoice.ROMANTIC
    assert captured["worldview"] is Worldview.NONE
    assert response["archivist_mode"] == "forest"
    assert response["archivist_mode_version"] == "1"
    assert response["influence_profile_id"] == "dunsany_elfland"
    assert response["influence_profile_version"] == "1"
    assert len(response["influence_prompt_sha256"]) == 64
    assert response["influence_provenance"][0]["source_identifier"] == ("project-gutenberg:61077")
