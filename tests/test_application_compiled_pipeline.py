from types import SimpleNamespace

import pytest

import web_project
from archivist_modes import ArchivistMode, settings_for_archivist_mode
from evidence_compiler import render_evidence_card_claim
from prose_renderer import (
    EvidenceProseRenderResult,
    ProseFailureCode,
    ProseRenderStatus,
)
from rag_pipeline import answer_run_diagnostics


CHUNKS = [
    {
        "document": "Chapter 4.md",
        "chapter_title": "Representative Government",
        "chunk_id": "chapter_4_001",
        "paragraph_start": 1,
        "paragraph_end": 2,
        "text": (
            "Sir Edwin Sandys served as treasurer of the Virginia Company. "
            "Under Sandys, the company permitted Virginia settlers to organize "
            "their own legislature."
        ),
    },
    {
        "document": "Chapter 4.md",
        "chapter_title": "Representative Government",
        "chunk_id": "chapter_4_002",
        "paragraph_start": 3,
        "paragraph_end": 4,
        "text": ("Sandys instructed Governor Yeardley to convene the General Assembly."),
    },
]


def _install_corpus(monkeypatch):
    collection = SimpleNamespace(configuration={"hnsw": {"space": "l2"}})
    monkeypatch.setattr(
        web_project,
        "chroma_client",
        lambda: SimpleNamespace(get_collection=lambda **_kwargs: collection),
    )
    monkeypatch.setattr(web_project, "load_project_chunks", lambda _project_id: CHUNKS)
    monkeypatch.setattr(
        web_project,
        "preflight_answer_corpus",
        lambda **_kwargs: SimpleNamespace(passed=True),
    )


def test_essential_compiles_direct_evidence_without_any_openai_client(monkeypatch):
    _install_corpus(monkeypatch)
    checked_claims = []
    monkeypatch.setattr(
        web_project,
        "openai_client",
        lambda: (_ for _ in ()).throw(AssertionError("Essential must not construct a client")),
    )

    result = web_project.answer_project_question_result(
        "current",
        "Who was Edwin Sandys, and what did he do?",
        archivist_mode=ArchivistMode.ESSENTIAL,
        application_compiled=True,
        checked_claim_callback=checked_claims.append,
    )

    assert result.status == "application_compiled"
    assert result.answer_strategy_version == "application-compiled-v1"
    assert "Direct evidence from the manuscript" in result.answer
    assert "[Source 1]" in result.answer
    assert result.final_chunks
    assert result.diagnostics["generation"]["structured_generation_called"] is False
    assert checked_claims
    assert all(result.answer.count(claim.text) == 1 for claim in checked_claims)
    public_diagnostics = answer_run_diagnostics(result)
    assert public_diagnostics["cohort"]["rag_policy_version"] == "application-compiled-v1"
    assert public_diagnostics["planner"]["status"] == "not_called"


@pytest.mark.parametrize(
    "mode",
    (
        ArchivistMode.PROFESSIONAL,
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ArchivistMode.BALEFUL_BLACK_BARON,
    ),
)
def test_generated_modes_make_one_prose_call_over_the_same_local_cards(monkeypatch, mode):
    _install_corpus(monkeypatch)
    client = object()
    calls = []
    checked_claims = []
    monkeypatch.setattr(web_project, "openai_client", lambda: client)

    def fake_generate(
        received_client,
        *,
        question,
        cards,
        mode,
        historiographical_lens,
        voice,
        worldview,
    ):
        calls.append(
            (
                received_client,
                question,
                tuple(cards),
                mode,
                historiographical_lens,
                voice,
                worldview,
            )
        )
        rendered_claims = [render_evidence_card_claim(card) for card in cards]
        return EvidenceProseRenderResult(
            status=ProseRenderStatus.GENERATED,
            mode=mode,
            answer="\n\nEditorial interpretation - a measured reflection.\n\n".join(
                reversed(rendered_claims)
            ),
            segments=(),
            used_card_ids=tuple(card.card_id for card in cards),
            used_source_numbers=tuple(card.source_number for card in cards),
            failure_code=None,
        )

    monkeypatch.setattr(web_project, "generate_evidence_prose", fake_generate)

    result = web_project.answer_project_question_result(
        "current",
        "Who was Edwin Sandys, and what did he do?",
        archivist_mode=mode,
        application_compiled=True,
        checked_claim_callback=checked_claims.append,
    )

    assert result.status == "application_compiled_prose"
    assert len(calls) == 1
    assert calls[0][0] is client
    assert calls[0][2]
    assert calls[0][3] is mode
    assert calls[0][4:] == settings_for_archivist_mode(mode)
    assert result.final_chunks[0]["chunk_id"] == calls[0][2][0].chunk_id
    assert result.diagnostics["generation"]["structured_generation_called"] is True
    assert [claim.text for claim in checked_claims] == [
        render_evidence_card_claim(card) for card in calls[0][2]
    ]
    assert all(result.answer.count(claim.text) == 1 for claim in checked_claims)
    assert result.answer.index(checked_claims[-1].text) < result.answer.index(
        checked_claims[0].text
    )


def test_generated_mode_forwards_advanced_interpretive_overrides(monkeypatch):
    _install_corpus(monkeypatch)
    captured = {}
    monkeypatch.setattr(web_project, "openai_client", lambda: object())

    def fake_generate(_client, **kwargs):
        captured.update(kwargs)
        return EvidenceProseRenderResult(
            status=ProseRenderStatus.GENERATED,
            mode=kwargs["mode"],
            answer="A locally cited generated answer [Source 1].",
            segments=(),
            used_card_ids=(kwargs["cards"][0].card_id,),
            used_source_numbers=(1,),
            failure_code=None,
        )

    monkeypatch.setattr(web_project, "generate_evidence_prose", fake_generate)
    web_project.answer_project_question_result(
        "current",
        "Who was Edwin Sandys?",
        archivist_mode=ArchivistMode.PROFESSIONAL,
        historiographical_lens="tragic",
        voice="romantic",
        worldview="pious",
        application_compiled=True,
    )

    assert captured["historiographical_lens"].value == "tragic"
    assert captured["voice"].value == "romantic"
    assert captured["worldview"].value == "pious"


def test_failed_prose_call_falls_back_to_already_compiled_direct_evidence(monkeypatch):
    _install_corpus(monkeypatch)
    monkeypatch.setattr(web_project, "openai_client", lambda: object())
    monkeypatch.setattr(
        web_project,
        "generate_evidence_prose",
        lambda *_args, mode, **_kwargs: EvidenceProseRenderResult(
            status=ProseRenderStatus.FALLBACK_REQUIRED,
            mode=mode,
            answer=None,
            segments=(),
            used_card_ids=(),
            used_source_numbers=(),
            failure_code=ProseFailureCode.PROVIDER_FAILURE,
        ),
    )

    result = web_project.answer_project_question_result(
        "current",
        "Who was Edwin Sandys, and what did he do?",
        archivist_mode=ArchivistMode.PROFESSIONAL,
        application_compiled=True,
    )

    assert result.status == "application_compiled_fallback"
    assert result.answer.startswith("Direct evidence from the manuscript:")
    assert result.diagnostics["generation"]["fallback_code"] == "provider_failure"
    public_diagnostics = answer_run_diagnostics(result)
    assert public_diagnostics["validation_result"] == "invalid"
    assert public_diagnostics["validation_error_code"] == "provider_failure"
    assert public_diagnostics["cohort"]["query_planner_prompt_version"] == "not-applicable"


def test_client_construction_failure_falls_back_without_a_prose_attempt(monkeypatch):
    _install_corpus(monkeypatch)
    factory_calls = 0

    def missing_client():
        nonlocal factory_calls
        factory_calls += 1
        raise RuntimeError("synthetic missing API client")

    monkeypatch.setattr(web_project, "openai_client", missing_client)
    monkeypatch.setattr(
        web_project,
        "generate_evidence_prose",
        lambda *_args, **_kwargs: pytest.fail("client failure must not reach prose generation"),
    )

    direct = web_project.answer_project_question_result(
        "current",
        "Who was Edwin Sandys, and what did he do?",
        archivist_mode=ArchivistMode.ESSENTIAL,
        application_compiled=True,
    )
    fallback = web_project.answer_project_question_result(
        "current",
        "Who was Edwin Sandys, and what did he do?",
        archivist_mode=ArchivistMode.PROFESSIONAL,
        application_compiled=True,
    )

    assert factory_calls == 1
    assert fallback.status == "application_compiled_fallback"
    assert fallback.answer == direct.answer
    assert fallback.final_chunks == direct.final_chunks
    assert fallback.diagnostics["generation"] == {
        "status": "fallback_to_direct_evidence",
        "validation_result": "invalid",
        "error_code": "provider_failure",
        "content_outcome": None,
        "repair_applied": False,
        "repair_codes": [],
        "prompt_version": "not-applicable",
        "normalizer_version": "application-compiled-v1",
        "instructions_sha256": "not-applicable",
        "schema_sha256": "not-applicable",
        "generator_model": "not-applicable",
        "generator_reasoning_effort": "not-applicable",
        "generator_verbosity": "not-applicable",
        "structured_generation_called": False,
        "fallback_code": "provider_failure",
    }
    public_diagnostics = answer_run_diagnostics(fallback)
    assert public_diagnostics["validation_result"] == "invalid"
    assert public_diagnostics["validation_error_code"] == "provider_failure"


def test_compiled_followup_uses_only_user_questions_and_never_calls_resolver(monkeypatch):
    monkeypatch.setattr(
        web_project,
        "openai_client",
        lambda: (_ for _ in ()).throw(AssertionError("local follow-up must not use a client")),
    )
    turn = web_project.resolve_application_compiled_turn(
        "What else did he do?",
        [
            {
                "question": "Who was Edwin Sandys?",
                "answer": "UNTRUSTED ASSISTANT PROSE",
            }
        ],
    )

    assert "Who was Edwin Sandys?" in turn.standalone_question
    assert "What else did he do?" in turn.standalone_question
    assert "UNTRUSTED" not in turn.standalone_question
    assert turn.trusted_user_texts == (
        "Who was Edwin Sandys?",
        "What else did he do?",
    )


def test_application_compiler_rejects_hidden_or_full_context_routes():
    with pytest.raises(ValueError, match="application-compiled answers require"):
        web_project.answer_project_question_result(
            "current",
            "What happened?",
            archivist_mode=ArchivistMode.FOREST,
            application_compiled=True,
        )
    with pytest.raises(ValueError, match="application-compiled answers require"):
        web_project.answer_project_question_result(
            "current",
            "What happened?",
            answer_strategy="full_context",
            application_compiled=True,
        )
