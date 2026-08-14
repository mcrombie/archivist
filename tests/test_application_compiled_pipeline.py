from dataclasses import replace
from types import SimpleNamespace

import pytest

import web_project
from answer_progress import AnswerProgressStage
from archivist_modes import ArchivistMode
from authored_response import (
    AUTHORED_RESPONSE_POLICY_VERSION,
    AuthoredAnswerScope,
    AuthoredDisposition,
    AuthoredFailureCode,
    AuthoredResponseResult,
    AuthoredResponseStatus,
)
from character_conversation import (
    CHARACTER_CONVERSATION_POLICY_VERSION,
    CharacterConversationFailureCode,
    CharacterConversationResult,
    CharacterConversationStatus,
)
from rag_pipeline import answer_run_diagnostics
from query_planning import RouteTrait


CHUNKS = [
    {
        "document": "Chapter 4.md",
        "chapter_title": "Representative Government",
        "chunk_id": "chapter_4_001",
        "paragraph_start": 1,
        "paragraph_end": 2,
        "text": (
            "Sir Edwin Sandys (1561-1629) served as treasurer of the Virginia Company. "
            "He was an English politician and company leader whose administration changed "
            "the direction of the colony. Under Sandys, the company repealed harsh laws and "
            "permitted Virginia settlers to organize their own legislature. This fuller "
            "passage gives the answer model room to explain his identity, office, and policy "
            "without reducing the evidence to one locally selected sentence."
        ),
    },
    {
        "document": "Chapter 4.md",
        "chapter_title": "Representative Government",
        "chunk_id": "chapter_4_002",
        "paragraph_start": 3,
        "paragraph_end": 4,
        "text": (
            "Sandys instructed Governor George Yeardley to convene the General Assembly in "
            "Virginia. The assembly allowed colonists to participate in local government, "
            "although authority remained divided among colonial institutions and the company "
            "in London. The arrangement therefore represented both an institutional innovation "
            "and a limited experiment within an imperial corporation."
        ),
    },
    {
        "document": "Chapter 5.md",
        "chapter_title": "Company and Colony",
        "chunk_id": "chapter_5_001",
        "paragraph_start": 10,
        "paragraph_end": 11,
        "text": (
            "English separatists found an ally in Edwin Sandys of the Virginia Company. "
            "Sandys helped arrange for them to settle in Virginia, showing that his company "
            "work extended beyond the assembly itself. His sponsorship joined religious, "
            "commercial, and colonial questions that the company had to negotiate at the same "
            "time."
        ),
    },
    {
        "document": "Chapter 5.md",
        "chapter_title": "Company and Colony",
        "chunk_id": "chapter_5_002",
        "paragraph_start": 12,
        "paragraph_end": 13,
        "text": (
            "Sandys later stood trial in London after questioning the limits of royal authority. "
            "Meanwhile, the General Assembly he had enabled in Virginia became accustomed to "
            "governing itself. These developments connected his career in the company to a "
            "longer institutional story, while the manuscript still distinguishes his immediate "
            "actions from their later consequences."
        ),
    },
]

RETRIEVAL_RESULTS = object()


class RecordingClient:
    def __init__(self) -> None:
        self.option_calls: list[dict[str, object]] = []

    def with_options(self, **kwargs):
        self.option_calls.append(dict(kwargs))
        return self


def _install_pipeline(monkeypatch, *, client=None, retrieval_error=None):
    client = client or RecordingClient()
    collection = SimpleNamespace(configuration={"hnsw": {"space": "l2"}})
    factory_calls = []
    retrieval_calls = []
    planning_calls = []

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

    def client_factory():
        factory_calls.append(client)
        return client

    def fake_retrieve(
        question,
        collection_handle,
        chunks,
        *,
        n_results,
        embedding_client,
        corpus,
    ):
        retrieval_calls.append(
            {
                "question": question,
                "collection": collection_handle,
                "chunks": chunks,
                "n_results": n_results,
                "embedding_client": embedding_client,
                "corpus": corpus,
            }
        )
        if retrieval_error is not None:
            raise retrieval_error
        return RETRIEVAL_RESULTS

    def fake_plan(retrieval_results, *, chunks):
        planning_calls.append((retrieval_results, chunks))
        return SimpleNamespace(final_chunks=list(CHUNKS), trace={})

    monkeypatch.setattr(web_project, "openai_client", client_factory)
    monkeypatch.setattr(web_project, "retrieve_from_collection", fake_retrieve)
    monkeypatch.setattr(web_project, "plan_context_chunks", fake_plan)
    return SimpleNamespace(
        client=client,
        collection=collection,
        factory_calls=factory_calls,
        retrieval_calls=retrieval_calls,
        planning_calls=planning_calls,
    )


def _generated_result(mode, dossier, *, answer=None):
    first_unit = dossier.units[0]
    follow_up = "Would you like to trace how Sandys's policies shaped the assembly?"
    return AuthoredResponseResult(
        status=AuthoredResponseStatus.GENERATED,
        mode=mode,
        answer=answer
        or (
            "Sandys led the Virginia Company toward representative government "
            f"[Source {first_unit.source_numbers[0]}].\n\n{follow_up}"
        ),
        disposition=AuthoredDisposition.ANSWERED,
        paragraphs=(),
        follow_up_questions=(follow_up,),
        used_unit_ids=(first_unit.unit_id,),
        used_source_numbers=first_unit.source_numbers,
        failure_code=None,
    )


def test_v5_authoring_timeout_policy_preserves_one_shared_deadline():
    assert AUTHORED_RESPONSE_POLICY_VERSION == "retrieval-authored-v5"
    assert web_project.AUTHORED_TOTAL_PROVIDER_DEADLINE_SECONDS == 35.0
    assert web_project.AUTHORED_EMBEDDING_TIMEOUT_SECONDS == 8.0
    assert web_project.AUTHORED_AUTHORING_TIMEOUT_SECONDS == 30.0


def test_essential_uses_one_no_retry_client_for_hybrid_retrieval_only(monkeypatch):
    harness = _install_pipeline(monkeypatch)
    checked_claims = []
    stages = []
    monkeypatch.setattr(
        web_project,
        "generate_authored_response",
        lambda *_args, **_kwargs: pytest.fail("Essential must not make an authoring call"),
    )

    result = web_project.answer_project_question_result(
        "current",
        "Who was Edwin Sandys, and what did he do?",
        archivist_mode=ArchivistMode.ESSENTIAL,
        application_compiled=True,
        progress_callback=stages.append,
        checked_claim_callback=checked_claims.append,
    )

    assert result.status == "retrieval_authored_direct"
    assert result.answer_strategy_version == AUTHORED_RESPONSE_POLICY_VERSION
    assert result.answer.startswith("Direct evidence from the manuscript:")
    assert result.final_chunks
    assert len(harness.factory_calls) == 1
    assert len(harness.retrieval_calls) == 1
    assert harness.retrieval_calls[0]["embedding_client"] is harness.client
    assert harness.retrieval_calls[0]["question"] == (
        "Who was Edwin Sandys, and what did he do?"
    )
    assert len(harness.planning_calls) == 1
    assert harness.planning_calls[0][0] is RETRIEVAL_RESULTS
    assert harness.client.option_calls
    assert all(call["max_retries"] == 0 for call in harness.client.option_calls)
    timeout_calls = [
        call["timeout"]
        for call in harness.client.option_calls
        if "timeout" in call
    ]
    assert timeout_calls == [web_project.AUTHORED_EMBEDDING_TIMEOUT_SECONDS]
    assert result.diagnostics["generation"]["structured_generation_called"] is False
    assert result.diagnostics["generation"]["answer_length_profile"] == "not-applicable"
    assert result.diagnostics["generation"]["requested_max_output_tokens"] is None
    assert checked_claims
    assert AnswerProgressStage.GENERATING_ANSWER in stages

    diagnostics = answer_run_diagnostics(result)
    assert diagnostics["cohort"]["rag_policy_version"] == AUTHORED_RESPONSE_POLICY_VERSION
    assert diagnostics["planner"]["status"] == "not_called"


@pytest.mark.parametrize(
    ("mode", "expected_phrase"),
    (
        (ArchivistMode.PROFESSIONAL, "thoughtful professional life"),
        (ArchivistMode.PRETTY_PINK_PRINCESS, "wonderful imaginary life"),
        (ArchivistMode.BALEFUL_BLACK_BARON, "magnificently miserable"),
        (ArchivistMode.EMBER_AND_INK, "strategically stable morning"),
    ),
)
def test_character_social_turn_bypasses_retrieval_and_answers_once(
    monkeypatch,
    mode,
    expected_phrase,
):
    harness = _install_pipeline(monkeypatch)
    author_calls = []
    stages = []

    def fake_character(client, *, question, mode):
        author_calls.append((client, question, mode))
        followup = "Which story in the manuscript shall we explore?"
        return CharacterConversationResult(
            status=CharacterConversationStatus.GENERATED,
            mode=mode,
            answer=f"My {expected_phrase} is proceeding exactly as expected.\n\n{followup}",
            persona_reply=f"My {expected_phrase} is proceeding exactly as expected.",
            follow_up_questions=(followup,),
            failure_code=None,
        )

    monkeypatch.setattr(web_project, "generate_character_conversation", fake_character)
    monkeypatch.setattr(
        web_project,
        "generate_authored_response",
        lambda *_args, **_kwargs: pytest.fail("dossier authoring must not run for social chat"),
    )

    result = web_project.answer_project_question_result(
        "current",
        "How are you?",
        archivist_mode=mode,
        application_compiled=True,
        progress_callback=stages.append,
    )

    assert result.status == "character_conversation"
    assert result.final_chunks == []
    assert result.evidence_decision == "indeterminate"
    assert result.answer_strategy_version == AUTHORED_RESPONSE_POLICY_VERSION
    assert result.answer.endswith("Which story in the manuscript shall we explore?")
    assert len(harness.factory_calls) == 1
    assert harness.retrieval_calls == []
    assert harness.planning_calls == []
    assert len(author_calls) == 1
    assert author_calls[0][1:] == ("How are you?", mode)
    assert AnswerProgressStage.GENERATING_ANSWER in stages
    assert AnswerProgressStage.VALIDATING_ANSWER in stages
    assert AnswerProgressStage.RETRIEVING_SOURCES not in stages
    assert AnswerProgressStage.CHECKING_EVIDENCE not in stages
    assert AnswerProgressStage.PREPARING_CONTEXT not in stages
    generation = result.diagnostics["generation"]
    assert generation["structured_generation_called"] is True
    assert generation["validation_result"] == "valid"
    assert result.diagnostics["response_route"] == CHARACTER_CONVERSATION_POLICY_VERSION
    timeout_calls = [
        call["timeout"] for call in harness.client.option_calls if "timeout" in call
    ]
    assert timeout_calls == [web_project.CHARACTER_CONVERSATION_TIMEOUT_SECONDS]


def test_character_social_provider_failure_keeps_character_reply_without_sources(monkeypatch):
    harness = _install_pipeline(monkeypatch)
    fallback_question = "Which shadow in the manuscript shall we follow?"
    fallback = CharacterConversationResult(
        status=CharacterConversationStatus.LOCAL_FALLBACK,
        mode=ArchivistMode.BALEFUL_BLACK_BARON,
        answer=f"Miserable, naturally.\n\n{fallback_question}",
        persona_reply="Miserable, naturally.",
        follow_up_questions=(fallback_question,),
        failure_code=CharacterConversationFailureCode.PROVIDER_FAILURE,
    )
    monkeypatch.setattr(
        web_project,
        "generate_character_conversation",
        lambda *_args, **_kwargs: fallback,
    )

    result = web_project.answer_project_question_result(
        "current",
        "How are you?",
        archivist_mode=ArchivistMode.BALEFUL_BLACK_BARON,
        application_compiled=True,
    )

    assert result.status == "character_conversation_fallback"
    assert result.answer == fallback.answer
    assert result.final_chunks == []
    assert harness.retrieval_calls == []
    assert result.diagnostics["generation"]["fallback_code"] == "provider_failure"
    assert result.diagnostics["generation"]["validation_result"] == "valid"
    assert result.diagnostics["generation"]["content_outcome"] == "valid_complete"
    assert result.diagnostics["generation"]["structured_generation_called"] is True
    diagnostics = answer_run_diagnostics(result)
    assert diagnostics["validation_result"] == "valid"
    assert diagnostics["validation_error_code"] is None


@pytest.mark.parametrize(
    "mode",
    (
        ArchivistMode.PROFESSIONAL,
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ArchivistMode.BALEFUL_BLACK_BARON,
        ArchivistMode.EMBER_AND_INK,
    ),
)
def test_generated_modes_author_once_from_rich_dossier_and_preserve_followup(
    monkeypatch, mode
):
    harness = _install_pipeline(monkeypatch)
    author_calls = []
    checked_claims = []

    def fake_author(received_client, **kwargs):
        author_calls.append((received_client, kwargs))
        return _generated_result(mode, kwargs["dossier"])

    monkeypatch.setattr(web_project, "generate_authored_response", fake_author)

    result = web_project.answer_project_question_result(
        "current",
        "When did he live?",
        history=[
            {
                "question": "Who was Edwin Sandys, and what did he do?",
                "answer": "UNTRUSTED ASSISTANT TEXT THAT MUST NOT ENTER RETRIEVAL",
            }
        ],
        archivist_mode=mode,
        application_compiled=True,
        checked_claim_callback=checked_claims.append,
    )

    assert result.status == "retrieval_authored"
    assert len(harness.factory_calls) == 1
    assert len(harness.retrieval_calls) == 1
    assert len(author_calls) == 1
    received_client, kwargs = author_calls[0]
    assert received_client is harness.client
    assert kwargs["question"] == "When did he live?"
    assert kwargs["resolved_turn"].standalone_question == "When did Edwin Sandys live?"
    assert kwargs["dossier"].question == "When did Edwin Sandys live?"
    assert kwargs["mode"] is mode
    assert kwargs["answer_length_target"].scope is AuthoredAnswerScope.ORDINARY
    assert kwargs["answer_length_target"].target_output_token_minimum == 500
    assert kwargs["answer_length_target"].target_output_token_maximum == 700
    assert kwargs["answer_length_target"].max_output_tokens == 1_800
    assert len(kwargs["dossier"].units) == 4
    assert all(unit.text_scope == "full_chunk" for unit in kwargs["dossier"].units)
    assert sum(len(unit.text.split()) for unit in kwargs["dossier"].units) > 150
    assert harness.retrieval_calls[0]["question"] == "When did Edwin Sandys live?"
    assert checked_claims == []
    assert result.final_chunks == CHUNKS
    assert result.answer.endswith(
        "Would you like to trace how Sandys's policies shaped the assembly?"
    )
    assert result.diagnostics["generation"]["structured_generation_called"] is True
    assert result.diagnostics["generation"]["answer_length_profile"] == "ordinary"
    assert result.diagnostics["generation"]["target_answer_tokens_minimum"] == 500
    assert result.diagnostics["generation"]["target_answer_tokens_maximum"] == 700
    assert result.diagnostics["generation"]["requested_max_output_tokens"] == 1_800
    assert result.evidence_decision == "direct_answer"
    timeout_calls = [
        call["timeout"]
        for call in harness.client.option_calls
        if "timeout" in call
    ]
    assert timeout_calls == [
        web_project.AUTHORED_EMBEDDING_TIMEOUT_SECONDS,
        web_project.AUTHORED_AUTHORING_TIMEOUT_SECONDS,
    ]
    assert all(call["max_retries"] == 0 for call in harness.client.option_calls)


def test_broad_synthesis_trait_selects_and_forwards_longer_answer_profile(monkeypatch):
    _install_pipeline(monkeypatch)
    broad_plan = SimpleNamespace(traits=(RouteTrait.BROAD_SYNTHESIS,))
    monkeypatch.setattr(web_project, "build_question_plan", lambda _turn: broad_plan)
    captured = {}

    def fake_author(_client, **kwargs):
        captured.update(kwargs)
        return _generated_result(kwargs["mode"], kwargs["dossier"])

    monkeypatch.setattr(web_project, "generate_authored_response", fake_author)
    result = web_project.answer_project_question_result(
        "current",
        "How did Virginia's institutions change across the manuscript?",
        archivist_mode=ArchivistMode.PROFESSIONAL,
        application_compiled=True,
    )

    target = captured["answer_length_target"]
    assert target.scope is AuthoredAnswerScope.BROAD
    assert target.rationale_code == "question_plan_broad_synthesis"
    assert target.target_output_token_minimum == 900
    assert target.target_output_token_maximum == 1_100
    assert target.max_output_tokens == 2_400
    assert result.plan is broad_plan
    assert result.diagnostics["generation"]["answer_length_profile"] == "broad"
    assert result.diagnostics["generation"]["target_answer_tokens_minimum"] == 900
    assert result.diagnostics["generation"]["target_answer_tokens_maximum"] == 1_100
    assert result.diagnostics["generation"]["requested_max_output_tokens"] == 2_400


def test_generated_mode_skips_author_when_provider_deadline_is_exhausted(monkeypatch):
    _install_pipeline(monkeypatch)
    author_calls = []
    monkeypatch.setattr(
        web_project,
        "generate_authored_response",
        lambda *_args, **_kwargs: author_calls.append((_args, _kwargs)),
    )

    essential = web_project.answer_project_question_result(
        "current",
        "Who was Edwin Sandys?",
        archivist_mode=ArchivistMode.ESSENTIAL,
        application_compiled=True,
    )
    monkeypatch.setattr(
        web_project,
        "_remaining_provider_deadline_seconds",
        lambda _deadline_ns: 0.0,
    )
    fallback = web_project.answer_project_question_result(
        "current",
        "Who was Edwin Sandys?",
        archivist_mode=ArchivistMode.PROFESSIONAL,
        application_compiled=True,
    )

    assert author_calls == []
    assert fallback.status == "retrieval_authored_fallback"
    assert fallback.answer == essential.answer
    assert fallback.final_chunks == essential.final_chunks
    assert fallback.diagnostics["generation"]["structured_generation_called"] is False
    assert fallback.diagnostics["generation"]["fallback_code"] == "request_timeout"
    assert fallback.diagnostics["generation"]["answer_length_profile"] == "ordinary"
    assert fallback.diagnostics["generation"]["requested_max_output_tokens"] == 1_800
    assert answer_run_diagnostics(fallback)["validation_error_code"] == "request_timeout"


def test_generated_mode_forwards_advanced_interpretive_overrides(monkeypatch):
    _install_pipeline(monkeypatch)
    captured = {}

    def fake_author(_client, **kwargs):
        captured.update(kwargs)
        return _generated_result(kwargs["mode"], kwargs["dossier"])

    monkeypatch.setattr(web_project, "generate_authored_response", fake_author)
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


@pytest.mark.parametrize(
    ("disposition", "expected_decision"),
    (
        (AuthoredDisposition.PARTIAL, "partial_answer"),
        (AuthoredDisposition.INSUFFICIENT, "indeterminate"),
        (AuthoredDisposition.PERSONA_REFUSAL, "indeterminate"),
    ),
)
def test_authored_disposition_does_not_impersonate_an_evidence_gate(
    monkeypatch,
    disposition,
    expected_decision,
):
    _install_pipeline(monkeypatch)

    def fake_author(_client, **kwargs):
        result = _generated_result(kwargs["mode"], kwargs["dossier"])
        return replace(result, disposition=disposition)

    monkeypatch.setattr(web_project, "generate_authored_response", fake_author)
    result = web_project.answer_project_question_result(
        "current",
        "Who was Edwin Sandys?",
        archivist_mode=ArchivistMode.PRETTY_PINK_PRINCESS,
        application_compiled=True,
    )

    assert result.status == "retrieval_authored"
    assert result.evidence_decision == expected_decision


def test_author_failure_falls_back_to_exact_essential_answer_over_same_dossier(
    monkeypatch,
):
    _install_pipeline(monkeypatch)
    author_calls = []

    def failed_author(_client, **kwargs):
        author_calls.append(kwargs)
        return AuthoredResponseResult(
            status=AuthoredResponseStatus.FALLBACK_REQUIRED,
            mode=kwargs["mode"],
            answer=None,
            disposition=None,
            paragraphs=(),
            follow_up_questions=(),
            used_unit_ids=(),
            used_source_numbers=(),
            failure_code=AuthoredFailureCode.PROVIDER_EXCEPTION,
        )

    monkeypatch.setattr(web_project, "generate_authored_response", failed_author)
    essential = web_project.answer_project_question_result(
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

    assert len(author_calls) == 1
    assert len(author_calls[0]["dossier"].units) == 4
    assert fallback.status == "retrieval_authored_fallback"
    assert fallback.answer == essential.answer
    assert fallback.final_chunks == essential.final_chunks
    assert fallback.diagnostics["generation"]["fallback_code"] == (
        "provider_exception"
    )
    diagnostics = answer_run_diagnostics(fallback)
    assert diagnostics["cohort"]["rag_policy_version"] == AUTHORED_RESPONSE_POLICY_VERSION
    assert diagnostics["validation_error_code"] == (
        "provider_exception"
    )
    assert diagnostics["planner"]["status"] == "not_called"


def test_retrieval_failure_never_attempts_authored_response(monkeypatch):
    harness = _install_pipeline(
        monkeypatch,
        retrieval_error=RuntimeError("synthetic embedding failure"),
    )
    monkeypatch.setattr(
        web_project,
        "generate_authored_response",
        lambda *_args, **_kwargs: pytest.fail(
            "authoring must not run without completed hybrid retrieval"
        ),
    )

    result = web_project.answer_project_question_result(
        "current",
        "Who was Edwin Sandys?",
        archivist_mode=ArchivistMode.PROFESSIONAL,
        application_compiled=True,
    )

    assert len(harness.retrieval_calls) == 1
    assert harness.planning_calls == []
    assert result.status == "retrieval_unavailable"
    assert result.final_chunks == []
    assert result.answer_strategy_version == AUTHORED_RESPONSE_POLICY_VERSION
    assert result.diagnostics["generation"]["fallback_code"] == "retrieval_failure"
    assert result.diagnostics["generation"]["status"] == "retrieval_failed"
    diagnostics = answer_run_diagnostics(result)
    assert diagnostics["validation_result"] == "invalid"
    assert diagnostics["validation_error_code"] == "retrieval_failure"


def test_local_followup_resolution_uses_prior_user_question_not_assistant_text():
    turn = web_project.resolve_application_compiled_turn(
        "When did he live?",
        [
            {
                "question": "Who was Edwin Sandys, and what did he do?",
                "answer": "UNTRUSTED ASSISTANT CLAIM ABOUT A DIFFERENT PERSON",
            }
        ],
    )

    assert turn.standalone_question == "When did Edwin Sandys live?"
    assert "UNTRUSTED" not in turn.standalone_question
    assert turn.trusted_user_texts == (
        "Who was Edwin Sandys, and what did he do?",
        "When did he live?",
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
