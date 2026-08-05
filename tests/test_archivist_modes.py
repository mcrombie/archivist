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
        ArchivistMode.CROMB_COO_COO,
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ArchivistMode.BALEFUL_BLACK_BARON,
        ArchivistMode.TIDAL_ARCHIVIST,
        ArchivistMode.EMBER_AND_INK,
        ArchivistMode.ILLUMINATED_CODEX,
        ArchivistMode.COSMIC_ALMANAC,
    }
    assert set(INFLUENCE_PROFILES) == {
        "none",
        "professional_public_history",
        "dunsany_elfland",
        "cromb_coo_coo_manuscript",
        "rose_tinted_optimism",
        "severe_tragic_history",
        "moby_dick_maritime",
        "realist_statecraft",
        "modern_liberal_history",
        "future_science_history",
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
        (
            "cromb_coo_coo",
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.ROMANTIC,
            Worldview.SECULAR_HUMANIST,
        ),
        (
            "pretty_pink_princess",
            HistoriographicalLens.TRIUMPHALIST,
            AnswerVoice.ROMANTIC,
            Worldview.SECULAR_HUMANIST,
        ),
        (
            "baleful_black_baron",
            HistoriographicalLens.TRAGIC,
            AnswerVoice.ROMANTIC,
            Worldview.NONE,
        ),
        (
            "tidal_archivist",
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.ROMANTIC,
            Worldview.NONE,
        ),
        (
            "ember_and_ink",
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.PLAINSPOKEN,
            Worldview.ENLIGHTENMENT_RATIONALIST,
        ),
        (
            "illuminated_codex",
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.SCHOLARLY,
            Worldview.SECULAR_HUMANIST,
        ),
        (
            "cosmic_almanac",
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.SCHOLARLY,
            Worldview.ENLIGHTENMENT_RATIONALIST,
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


def test_cromb_coo_coo_profile_is_playful_humane_and_strictly_generation_only():
    block = build_archivist_mode_prompt_block(archivist_mode="cromb_coo_coo")
    normalized = " ".join(block.split())

    assert "playful but disciplined historical sensibility" in normalized
    assert "contingency" in normalized
    assert "official grandeur and ordinary experience" in normalized
    assert "tenderness, appetite, violence, and absurdity" in normalized
    assert "must never trivialize suffering" in normalized
    assert "lucid, lightly whimsical, humane, and precise" in normalized
    assert "never historical evidence" in normalized
    assert (
        "characters, places, creatures, plot, lore, names, distinctive phrases, or claims"
        in normalized
    )
    assert "Do not convert historical actors into fantasy figures" in normalized
    assert "invent onomatopoeia" in normalized
    assert "jokes at victims' expense" in normalized
    assert "every historical fact and citation" in normalized
    assert "grounded exclusively in *Cradle of the Empire*" in normalized


def test_pretty_pink_princess_is_strongly_optimistic_without_suppressing_harm():
    block = build_archivist_mode_prompt_block(archivist_mode="pretty_pink_princess")
    normalized = " ".join(block.split())

    assert "deliberately and unmistakably triumphalist" in normalized
    assert "unmistakably rose-tinted and optimistic" in normalized
    assert "courage, adaptation, creative agency, fellowship, recovery" in normalized
    assert "never falsify, omit, bury, euphemize, or minimize harm" in normalized
    assert "violence, enslavement, dispossession, exploitation" in normalized
    assert "state it plainly and with the same factual specificity" in normalized
    assert "Hope is an interpretive judgment" in normalized
    assert "grounded exclusively in *Cradle of the Empire*" in normalized


def test_baleful_black_baron_is_strongly_tragic_but_cannot_invent_tragedy():
    block = build_archivist_mode_prompt_block(archivist_mode="baleful_black_baron")
    normalized = " ".join(block.split())

    assert "opening and conclusion recognizably tragic" in normalized
    assert "strong tragic interpretation" in normalized
    assert "costs, coercion, violence, broken promises" in normalized
    assert "do not let a routine balancing sentence dissolve" in normalized
    assert "Do not invent or exaggerate suffering" in normalized
    assert "Tragedy should arise from concrete evidence" in normalized
    assert "grounded exclusively in *Cradle of the Empire*" in normalized


def test_tidal_archivist_is_maritime_not_dunsany_or_literary_evidence():
    block = build_archivist_mode_prompt_block(archivist_mode="tidal_archivist")
    normalized = " ".join(block.split())

    assert "Moby-Dick" not in block
    assert "Herman Melville" not in block
    assert "oceanic scale, long-voyage uncertainty, moral pressure" in normalized
    assert "limits of command" in normalized
    assert "image of tide, depth, weather, course, or wake" in normalized
    assert "Do not quote, paraphrase, imitate, or reproduce" in normalized
    assert "Dunsany-like mythopoetic forest register" in normalized
    assert "supplies no historical content" in normalized
    assert "grounded exclusively in *Cradle of the Empire*" in normalized


def test_ember_and_ink_is_realist_statecraft_without_kissinger_text_or_imitation():
    block = build_archivist_mode_prompt_block(archivist_mode="ember_and_ink")
    normalized = " ".join(block.split())

    assert "Kissinger" not in block
    assert "restrained realist statecraft frame" in normalized
    assert "interests, power, bargaining leverage" in normalized
    assert "declared principle from operating incentive" in normalized
    assert "Do not quote, paraphrase, imitate, or claim to channel" in normalized
    assert "No copyrighted statecraft work is a source" in normalized
    assert "no outside work may supply historical claims" in normalized
    assert "grounded exclusively in *Cradle of the Empire*" in normalized


def test_illuminated_codex_is_liberal_history_without_party_advocacy():
    block = build_archivist_mode_prompt_block(archivist_mode="illuminated_codex")
    normalized = " ".join(block.split())
    metadata = archivist_mode_metadata("illuminated_codex")

    assert "lowercase-l modern liberal historiography" in normalized
    assert "individual rights and dignity" in normalized
    assert "pluralism, representative institutions, rule of law" in normalized
    assert "reform, inclusion, toleration" in normalized
    assert "gaps between declared ideals and lived experience" in normalized
    assert "incremental, contested, reversible, and incomplete" in normalized
    assert "not as an automatic arc or inevitable destination" in normalized
    assert "Preserve coercion, exclusion, violence" in normalized
    assert "Do not turn this frame into present-day party advocacy" in normalized
    assert "Do not add facts or make uncited claims" in normalized
    assert "grounded exclusively in *Cradle of the Empire*" in normalized
    assert metadata["influence_profile_id"] == "modern_liberal_history"
    assert metadata["influence_provenance"] == []


def test_cosmic_almanac_is_future_science_history_without_forecasting():
    block = build_archivist_mode_prompt_block(archivist_mode="cosmic_almanac")
    normalized = " ".join(block.split())
    metadata = archivist_mode_metadata("cosmic_almanac")

    assert "future-science-oriented historical perspective" in normalized
    assert "long time horizons and connected systems" in normalized
    assert "ecology and climate, demography, technology, energy" in normalized
    assert "infrastructure, information, and institutions" in normalized
    assert "path dependence, feedback loops, thresholds" in normalized
    assert "constrained or opened plausible later futures" in normalized
    assert "Keep possibility distinct from evidence" in normalized
    assert "bounded interpretation, not prediction" in normalized
    assert "Do not invent future facts" in normalized
    assert "write science fiction" in normalized
    assert "technologically deterministic or teleological" in normalized
    assert "do not import present-day scientific categories" in normalized
    assert "grounded exclusively in *Cradle of the Empire*" in normalized
    assert metadata["influence_profile_id"] == "future_science_history"
    assert metadata["influence_provenance"] == []


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


def test_cromb_coo_coo_profile_freezes_private_provenance_outside_the_prompt():
    metadata = archivist_mode_metadata("cromb_coo_coo")
    prompt = build_archivist_mode_prompt_block(archivist_mode="cromb_coo_coo")
    provenance = metadata["influence_provenance"]

    assert metadata["archivist_mode"] == "cromb_coo_coo"
    assert metadata["archivist_mode_version"] == "1"
    assert metadata["influence_profile_id"] == "cromb_coo_coo_manuscript"
    assert metadata["influence_profile_version"] == "1"
    assert provenance == [
        {
            "title": "Journey through Cromb Coo Coo",
            "creator": None,
            "source_identifier": "owner-supplied:journey-through-cromb-coo-coo:2026-07-30",
            "source_url": None,
            "source_sha256": "f67f9ed3f622583abe2fca090d73881ff86a7f801cea88034589c986509ece74",
            "artifact_modified_at": "2026-07-30T10:05:30-04:00",
            "rights_note": (
                "Private owner-supplied manuscript; not redistributed. Reviewed locally "
                "to derive a bounded literary influence profile."
            ),
            "role": "Literary/editorial framing only; never historical evidence.",
        }
    ]
    for value in provenance[0].values():
        if isinstance(value, str):
            assert value not in prompt


def test_named_literary_and_statecraft_references_stay_in_metadata_only():
    tidal_metadata = archivist_mode_metadata("tidal_archivist")
    tidal_prompt = build_archivist_mode_prompt_block(archivist_mode="tidal_archivist")
    tidal_provenance = tidal_metadata["influence_provenance"][0]

    assert tidal_metadata["influence_profile_id"] == "moby_dick_maritime"
    assert tidal_provenance["source_identifier"] == "project-gutenberg:15"
    assert tidal_provenance["source_url"] == (
        "https://www.gutenberg.org/ebooks/15.epub3.images"
    )
    assert tidal_provenance["source_sha256"] == (
        "8d76f75515a8e10b0ed0657275767f75b4b283177805a1c09c231840a0607d95"
    )
    assert tidal_provenance["artifact_modified_at"] == "2026-08-01T07:33:10Z"
    assert tidal_provenance["title"] not in tidal_prompt
    assert tidal_provenance["creator"] not in tidal_prompt

    ember_metadata = archivist_mode_metadata("ember_and_ink")
    ember_prompt = build_archivist_mode_prompt_block(archivist_mode="ember_and_ink")
    ember_provenance = ember_metadata["influence_provenance"][0]

    assert ember_metadata["influence_profile_id"] == "realist_statecraft"
    assert ember_provenance["source_identifier"] == (
        "conceptual-profile:realist-statecraft:no-text-ingested"
    )
    assert ember_provenance["source_sha256"] is None
    assert "No Henry Kissinger work was ingested" in ember_provenance["rights_note"]
    assert "Henry Kissinger" not in ember_prompt


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

    modes = (
        ArchivistMode.ESSENTIAL,
        ArchivistMode.FOREST,
        ArchivistMode.CROMB_COO_COO,
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ArchivistMode.BALEFUL_BLACK_BARON,
        ArchivistMode.TIDAL_ARCHIVIST,
        ArchivistMode.EMBER_AND_INK,
        ArchivistMode.ILLUMINATED_CODEX,
        ArchivistMode.COSMIC_ALMANAC,
    )
    for mode in modes:
        web_project.answer_project_question_result(
            "current",
            "What happened?",
            n_results=5,
            archivist_mode=mode,
        )

    assert len(calls) == len(modes)
    for call in calls:
        assert call["chunks"] == CHUNKS
        assert call["n_results"] == 5
        assert call["resolved_turn"].standalone_question == "What happened?"
    assert [call["archivist_mode"] for call in calls] == list(modes)


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
