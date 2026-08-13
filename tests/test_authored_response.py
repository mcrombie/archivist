import json
from types import SimpleNamespace

import pytest
from openai.lib._pydantic import to_strict_json_schema

import authored_response
from archivist_modes import ArchivistMode
from authored_response import (
    AUTHORED_RESPONSE_OUTPUT_SCHEMA,
    AuthoredDisposition,
    AuthoredFailureCode,
    AuthoredFollowUp,
    AuthoredParagraph,
    AuthoredResponse,
    AuthoredResponseContractError,
    AuthoredResponseStatus,
    AuthoredRunKind,
    GroundedAuthoredRun,
    PersonaAuthoredRun,
    build_authored_response_input,
    build_authored_response_instructions,
    generate_authored_response,
    validate_and_render_authored_response,
)
from costs import CostLimitExceeded
from evidence_dossier import (
    RETRIEVAL_DOSSIER_SCHEMA,
    DossierRequirement,
    DossierSource,
    DossierUnit,
    RetrievalDossier,
)
from query_planning import ResolvedTurn


def _source(rank, *, source_numbers=None, chapter="Synthetic Chapter"):
    return DossierSource(
        chunk_id=f"chunk-{rank}",
        chunk_ids=(f"chunk-{rank}",),
        source_numbers=source_numbers or (rank,),
        retrieval_rank=rank,
        document="Synthetic manuscript",
        chapter_title=chapter,
        paragraph_start=rank * 2,
        paragraph_end=rank * 2 + 1,
        physical_page_start=rank + 10,
        physical_page_end=rank + 11,
        edition_id="synthetic-edition",
        edition_name="Synthetic Edition",
    )


def _unit(unit_id, rank, text, *, requirement_ids=("requirement:what:1",)):
    return DossierUnit(
        unit_id=unit_id,
        source=_source(rank),
        text=text,
        text_scope="full_chunk",
        estimated_evidence_tokens=max(1, len(text) // 4),
        requirement_ids=requirement_ids,
        aspect_tags=("what",),
    )


def _dossier(*units):
    return RetrievalDossier(
        dossier_id="dossier:test",
        schema=RETRIEVAL_DOSSIER_SCHEMA,
        question="Who was Edwin Sandys, and what did he do?",
        retrieval_query="Edwin Sandys Virginia Company reforms",
        requirements=(
            DossierRequirement(
                requirement_id="requirement:what:1",
                aspect="what",
                question_fragment="what did Edwin Sandys do?",
            ),
        ),
        aspect_tags=("what",),
        units=units
        or (
            _unit(
                "unit:1",
                1,
                "Sandys became treasurer and supported changes to the company's government.",
            ),
            _unit(
                "unit:2",
                2,
                "Settlers gained a representative assembly during the company's reforms.",
            ),
        ),
        estimated_evidence_tokens=80,
        target_evidence_tokens=2_500,
        hard_evidence_token_limit=4_500,
        diagnostics={"synthetic": True},
    )


TURN = ResolvedTurn(
    standalone_question="Who was Edwin Sandys, and what did he do?",
    entities=("Edwin Sandys",),
    scope="Virginia Company",
    trusted_user_texts=("Who was Edwin Sandys, and what did he do?",),
)


def _response(*paragraphs, disposition=AuthoredDisposition.ANSWERED, followups=None):
    return AuthoredResponse(
        schema=AUTHORED_RESPONSE_OUTPUT_SCHEMA,
        disposition=disposition,
        paragraphs=paragraphs,
        follow_up_questions=followups
        or (
            AuthoredFollowUp(
                text="Would you like to trace what happened to those reforms next?",
                support_unit_ids=("unit:2",),
            ),
        ),
    )


def _grounded(text, *unit_ids):
    return GroundedAuthoredRun(
        kind=AuthoredRunKind.GROUNDED,
        text=text,
        support_unit_ids=unit_ids,
    )


def _persona(text):
    return PersonaAuthoredRun(kind=AuthoredRunKind.PERSONA, text=text)


def _resolve_schema_ref(schema, node):
    if "$ref" not in node:
        return node
    prefix = "#/$defs/"
    reference = node["$ref"]
    assert reference.startswith(prefix)
    return schema["$defs"][reference.removeprefix(prefix)]


def _literal_schema_value(schema, node):
    node = _resolve_schema_ref(schema, node)
    if "const" in node:
        return node["const"]
    assert len(node.get("enum", ())) == 1
    return node["enum"][0]


def test_provider_schema_exposes_mutually_exclusive_grounded_and_persona_runs():
    schema = to_strict_json_schema(AuthoredResponse)
    assert "anyOf" not in schema
    assert "oneOf" not in schema
    paragraph = _resolve_schema_ref(schema, schema["properties"]["paragraphs"]["items"])
    run_items = paragraph["properties"]["runs"]["items"]
    alternatives = run_items.get("oneOf") or run_items.get("anyOf")

    assert alternatives is not None
    assert len(alternatives) == 2
    variants = {
        _literal_schema_value(schema, variant["properties"]["kind"]): variant
        for raw_variant in alternatives
        for variant in (_resolve_schema_ref(schema, raw_variant),)
    }
    assert set(variants) == {"grounded", "persona"}

    grounded = variants["grounded"]
    grounded_support = grounded["properties"]["support_unit_ids"]
    assert "support_unit_ids" in grounded["required"]
    assert grounded_support["minItems"] == 1

    persona = variants["persona"]
    persona_support = persona["properties"].get("support_unit_ids")
    assert persona_support is None or persona_support["maxItems"] == 0


@pytest.mark.parametrize(
    "invalid_run",
    (
        {"kind": "grounded", "text": "An unsupported factual claim.", "support_unit_ids": []},
        {"kind": "persona", "text": "A theatrical aside.", "support_unit_ids": ["unit:1"]},
    ),
)
def test_model_validation_rejects_run_support_that_conflicts_with_kind(invalid_run):
    payload = {
        "schema": AUTHORED_RESPONSE_OUTPUT_SCHEMA,
        "disposition": "answered",
        "paragraphs": [
            {
                "runs": [
                    {
                        "kind": "grounded",
                        "text": "A supported factual claim.",
                        "support_unit_ids": ["unit:1"],
                    },
                    invalid_run,
                ]
            }
        ],
        "follow_up_questions": [
            {
                "text": "Would you like to continue?",
                "support_unit_ids": [],
            }
        ],
    }

    with pytest.raises(ValueError):
        AuthoredResponse.model_validate(payload)


def test_input_sends_rich_full_passages_but_not_local_source_numbers():
    long_text = " ".join(f"word{number}" for number in range(180))
    dossier = _dossier(_unit("unit:1", 1, long_text))
    serialized = build_authored_response_input(
        question="Who was he?",
        resolved_turn=TURN,
        dossier=dossier,
        mode=ArchivistMode.PROFESSIONAL,
    )
    payload = json.loads(serialized)
    assert payload["retrieval_dossier"]["units"][0]["text"] == long_text
    assert payload["retrieval_dossier"]["units"][0]["source"]["chapter_title"]
    assert payload["resolved_turn"]["entities"] == ["Edwin Sandys"]
    assert "source_numbers" not in serialized
    assert "[Source" not in serialized


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        (ArchivistMode.PROFESSIONAL, "professional public historian"),
        (ArchivistMode.PRETTY_PINK_PRINCESS, "prince you have a crush on"),
        (ArchivistMode.BALEFUL_BLACK_BARON, "imaginary keep"),
        (ArchivistMode.EMBER_AND_INK, "Ruthless Red Realist"),
    ),
)
def test_distinct_prompts_allow_real_authoring_and_require_engagement(mode, expected):
    instructions = build_authored_response_instructions(mode)
    assert expected in instructions
    assert "freely synthesize, paraphrase" in instructions
    assert "choose the useful\nlength" in instructions
    assert "one to three original follow-up questions" in instructions
    assert "sentence does not need to quote or exactly match" in instructions
    assert "Registered editorial influence profile" in instructions


def test_ruthless_red_realist_is_inspired_without_impersonating_or_adding_facts():
    instructions = build_authored_response_instructions(ArchivistMode.EMBER_AND_INK)
    normalized = " ".join(instructions.split())

    assert "Ruthless Red Realist" in normalized
    assert "Niccolò Machiavelli and Henry Kissinger" in normalized
    assert "Do not impersonate, imitate, channel, quote" in normalized
    assert "Keep every historical assertion grounded in supplied dossier units" in normalized


def test_advanced_facets_reach_the_authoring_prompt_without_relaxing_grounding():
    instructions = build_authored_response_instructions(
        ArchivistMode.PROFESSIONAL,
        historiographical_lens="tragic",
        voice="romantic",
        worldview="pious",
    )
    assert "Selected advanced historiographical lens" in instructions
    assert "Selected advanced voice" in instructions
    assert "Selected advanced worldview" in instructions
    assert "never override the grounding contract" in instructions
    assert "subjective preface and coda" not in instructions
    assert "factual middle" not in instructions


@pytest.mark.parametrize(
    ("mode", "lens", "voice", "worldview"),
    (
        (
            ArchivistMode.PROFESSIONAL,
            "evidence_first",
            "plainspoken",
            "secular_humanist",
        ),
        (
            ArchivistMode.PRETTY_PINK_PRINCESS,
            "triumphalist",
            "romantic",
            "secular_humanist",
        ),
        (
            ArchivistMode.BALEFUL_BLACK_BARON,
            "tragic",
            "romantic",
            "none",
        ),
        (
            ArchivistMode.EMBER_AND_INK,
            "evidence_first",
            "plainspoken",
            "enlightenment_rationalist",
        ),
    ),
)
def test_mode_defaults_do_not_reinject_legacy_advanced_structure(
    mode,
    lens,
    voice,
    worldview,
):
    base = build_authored_response_instructions(mode)
    with_defaults = build_authored_response_instructions(
        mode,
        historiographical_lens=lens,
        voice=voice,
        worldview=worldview,
    )

    assert with_defaults == base
    assert "Advanced interpretive settings" not in with_defaults
    assert "subjective preface and coda" not in with_defaults
    assert "factual middle" not in with_defaults


def test_renderer_keeps_original_prose_and_resolves_support_ids_to_citations():
    structured = _response(
        AuthoredParagraph(
            runs=(
                _persona("My archive doors swing open with a suitably ominous creak."),
                _grounded(
                    "Sandys helped redirect the company toward representative government",
                    "unit:1",
                    "unit:2",
                ),
            )
        ),
        followups=(
            AuthoredFollowUp(text="Shall we examine how the assembly developed?"),
            AuthoredFollowUp(
                text="Would you rather follow the company's political struggle?",
                support_unit_ids=("unit:1",),
            ),
        ),
    )
    result = validate_and_render_authored_response(
        structured,
        _dossier(),
        mode=ArchivistMode.BALEFUL_BLACK_BARON,
    )
    assert result.status is AuthoredResponseStatus.GENERATED
    assert (
        "Sandys helped redirect the company toward representative government [Source 1, Source 2]."
    ) in result.answer
    assert "My archive doors swing open" in result.answer
    assert result.used_unit_ids == ("unit:1", "unit:2")
    assert result.used_source_numbers == (1, 2)
    assert result.follow_up_questions == (
        "Shall we examine how the assembly developed?",
        "Would you rather follow the company's political struggle [Source 1]?",
    )
    assert result.answer.endswith(
        "Would you rather follow the company's political struggle [Source 1]?"
    )


def test_free_paraphrase_is_not_exact_matched_against_the_manuscript():
    prose = "He pushed the enterprise toward a more participatory political structure."
    result = validate_and_render_authored_response(
        _response(AuthoredParagraph(runs=(_grounded(prose, "unit:1"),))),
        _dossier(),
        mode=ArchivistMode.PROFESSIONAL,
    )
    assert prose.removesuffix(".") in result.answer


@pytest.mark.parametrize(
    ("run", "expected"),
    (
        (_grounded("A claim with [Source 9].", "unit:1"), "citation label"),
        (_grounded("A claim with <em>secret markup</em>.", "unit:1"), "HTML"),
        (_grounded("Read https://example.test for more.", "unit:1"), "link"),
        (_grounded("Read [this source](https://example.test).", "unit:1"), "link"),
    ),
)
def test_renderer_rejects_forged_citations_html_and_links(run, expected):
    with pytest.raises(AuthoredResponseContractError, match=expected):
        validate_and_render_authored_response(
            _response(AuthoredParagraph(runs=(run,))),
            _dossier(),
            mode=ArchivistMode.PROFESSIONAL,
        )


def test_unknown_support_unit_is_rejected_locally():
    with pytest.raises(AuthoredResponseContractError, match="unknown dossier unit"):
        validate_and_render_authored_response(
            _response(AuthoredParagraph(runs=(_grounded("A claim.", "unit:404"),))),
            _dossier(),
            mode=ArchivistMode.PROFESSIONAL,
        )


def test_extended_verbatim_manuscript_reproduction_is_rejected():
    source_text = " ".join(f"distinct{number}" for number in range(60))
    dossier = _dossier(_unit("unit:1", 1, source_text))
    copied = " ".join(source_text.split()[:50])
    structured = _response(
        AuthoredParagraph(runs=(_grounded(copied, "unit:1"),)),
        followups=(AuthoredFollowUp(text="Would you like to continue?"),),
    )
    with pytest.raises(AuthoredResponseContractError, match="extended manuscript"):
        validate_and_render_authored_response(
            structured,
            dossier,
            mode=ArchivistMode.PROFESSIONAL,
        )


def test_followups_are_mandatory_original_questions():
    with pytest.raises(ValueError):
        AuthoredResponse(
            disposition=AuthoredDisposition.ANSWERED,
            paragraphs=(AuthoredParagraph(runs=(_grounded("A claim.", "unit:1"),)),),
            follow_up_questions=(),
        )
    with pytest.raises(ValueError, match="question mark"):
        AuthoredFollowUp(text="Let us continue")


def test_persona_refusal_is_princess_only_and_may_be_entirely_persona():
    refusal = _response(
        AuthoredParagraph(
            runs=(
                _persona(
                    "Oh, that chamber is too frightening for me; let us choose a gentler door."
                ),
            )
        ),
        disposition=AuthoredDisposition.PERSONA_REFUSAL,
        followups=(AuthoredFollowUp(text="Would you like a gentler story about daily life?"),),
    )
    result = validate_and_render_authored_response(
        refusal,
        _dossier(),
        mode=ArchivistMode.PRETTY_PINK_PRINCESS,
    )
    assert result.disposition is AuthoredDisposition.PERSONA_REFUSAL
    with pytest.raises(AuthoredResponseContractError, match="only to Pretty Pink Princess"):
        validate_and_render_authored_response(
            refusal,
            _dossier(),
            mode=ArchivistMode.BALEFUL_BLACK_BARON,
        )


class RecordingClient:
    def __init__(self):
        self.max_retries = None

    def with_options(self, *, max_retries):
        self.max_retries = max_retries
        return self


def test_generation_is_exactly_one_low_reasoning_medium_verbosity_call(monkeypatch):
    calls = []
    client = RecordingClient()
    structured = _response(
        AuthoredParagraph(runs=(_grounded("Sandys helped reshape the company.", "unit:1"),))
    )

    def fake_parse(request_client, *, operation, **request):
        calls.append((request_client, operation, request))
        return SimpleNamespace(output_parsed=structured, output=())

    monkeypatch.setattr(authored_response, "tracked_responses_parse", fake_parse)
    result = generate_authored_response(
        client,
        question="Who was Edwin Sandys?",
        resolved_turn=TURN,
        dossier=_dossier(),
        mode=ArchivistMode.PROFESSIONAL,
        historiographical_lens="tragic",
        voice="romantic",
        worldview="pious",
    )
    assert result.status is AuthoredResponseStatus.GENERATED
    assert client.max_retries == 0
    assert len(calls) == 1
    assert calls[0][1] == "answer_generation"
    assert calls[0][2]["model"] == "gpt-5.6-sol"
    assert calls[0][2]["reasoning"] == {"effort": "low"}
    assert calls[0][2]["text"] == {"verbosity": "medium"}
    assert calls[0][2]["max_output_tokens"] == 1_800
    assert calls[0][2]["text_format"] is AuthoredResponse
    assert "Selected advanced voice" in calls[0][2]["instructions"]


def test_provider_and_invalid_output_return_typed_fallback_without_retry(monkeypatch):
    client = RecordingClient()
    calls = 0

    def fail(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("synthetic offline failure")

    monkeypatch.setattr(authored_response, "tracked_responses_parse", fail)
    failed = generate_authored_response(
        client,
        question="Who was Edwin Sandys?",
        resolved_turn=TURN,
        dossier=_dossier(),
        mode=ArchivistMode.PROFESSIONAL,
    )
    assert calls == 1
    assert failed.status is AuthoredResponseStatus.FALLBACK_REQUIRED
    assert failed.failure_code is AuthoredFailureCode.PROVIDER_FAILURE

    monkeypatch.setattr(
        authored_response,
        "tracked_responses_parse",
        lambda *_args, **_kwargs: SimpleNamespace(output_parsed=None, output=()),
    )
    invalid = generate_authored_response(
        client,
        question="Who was Edwin Sandys?",
        resolved_turn=TURN,
        dossier=_dossier(),
        mode=ArchivistMode.PROFESSIONAL,
    )
    assert invalid.failure_code is AuthoredFailureCode.INVALID_RESPONSE


def test_provider_refusal_is_distinct_and_cost_limit_passes_through(monkeypatch):
    client = RecordingClient()
    refusal = SimpleNamespace(
        output_parsed=None,
        output=(SimpleNamespace(type="message", content=(SimpleNamespace(type="refusal"),)),),
    )
    monkeypatch.setattr(
        authored_response,
        "tracked_responses_parse",
        lambda *_args, **_kwargs: refusal,
    )
    result = generate_authored_response(
        client,
        question="Who was Edwin Sandys?",
        resolved_turn=TURN,
        dossier=_dossier(),
        mode=ArchivistMode.PRETTY_PINK_PRINCESS,
    )
    assert result.failure_code is AuthoredFailureCode.REFUSAL

    error = CostLimitExceeded({"limit": "synthetic"})

    def cost_limit(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(authored_response, "tracked_responses_parse", cost_limit)
    with pytest.raises(CostLimitExceeded) as exc_info:
        generate_authored_response(
            client,
            question="Who was Edwin Sandys?",
            resolved_turn=TURN,
            dossier=_dossier(),
            mode=ArchivistMode.PRETTY_PINK_PRINCESS,
        )
    assert exc_info.value is error


def test_essential_and_dormant_modes_are_not_authored_modes():
    for mode in (ArchivistMode.ESSENTIAL, ArchivistMode.FOREST):
        with pytest.raises(AuthoredResponseContractError, match="unsupported"):
            build_authored_response_instructions(mode)
