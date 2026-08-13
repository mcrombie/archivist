import hashlib
from types import SimpleNamespace

import pytest

import prose_renderer
from archivist_modes import ArchivistMode, archivist_mode_metadata, load_influence_profile_prompt
from costs import CostLimitExceeded
from evidence_compiler import EvidenceCard
from prose_renderer import (
    EVIDENCE_PROSE_OUTPUT_SCHEMA,
    EDITORIAL_CUES,
    EditorialCueId,
    EvidenceProseContractError,
    EvidenceProseResponse,
    EvidenceProseSegment,
    ProseFailureCode,
    ProseRenderStatus,
    ProseSegmentKind,
    build_evidence_prose_input,
    build_evidence_prose_instructions,
    evidence_prose_prompt_metadata,
    generate_evidence_prose,
    validate_and_render_evidence_prose,
)


class Card:
    def __init__(self, card_id, text, source_numbers, requirement_ids=()):
        self.card_id = card_id
        self.text = text
        self.source_numbers = source_numbers
        self.requirement_ids = requirement_ids


CARDS = (
    Card("E1", "The treasurer supported repeal of the harsh laws.", (2,), ("identity",)),
    Card("E2", "The settlers were allowed to organize a legislature.", (3, 4), ("actions",)),
)


def response(*segments):
    return EvidenceProseResponse(schema=EVIDENCE_PROSE_OUTPUT_SCHEMA, segments=segments)


def evidence(text, *card_ids, paragraph=1):
    return EvidenceProseSegment(
        kind=ProseSegmentKind.EVIDENCE,
        paragraph=paragraph,
        text=prose_renderer.EVIDENCE_CARD_PLACEHOLDER,
        card_ids=card_ids,
    )


def aside(cue: EditorialCueId, paragraph=1):
    return EvidenceProseSegment(
        kind=ProseSegmentKind.CHARACTER_ASIDE,
        paragraph=paragraph,
        text=cue.value,
        card_ids=(),
    )


def interpretation(cue: EditorialCueId, paragraph=1):
    return EvidenceProseSegment(
        kind=ProseSegmentKind.INTERPRETATION,
        paragraph=paragraph,
        text=cue.value,
        card_ids=(),
    )


def test_input_contains_cards_but_not_application_owned_source_mapping():
    payload = build_evidence_prose_input("What changed?", CARDS, ArchivistMode.PROFESSIONAL)
    assert '"card_id":"E1"' in payload
    assert '"requirement_ids":["identity"]' in payload
    assert "source_numbers" not in payload
    assert "[Source" not in payload


def test_compiler_evidence_card_satisfies_renderer_protocol():
    card = EvidenceCard(
        source_number=1,
        chunk_id="synthetic-chunk",
        excerpt="Application-owned evidence.",
        score=1.0,
        matched_question_term_count=1,
    )
    payload = build_evidence_prose_input("What changed?", (card,), ArchivistMode.PROFESSIONAL)
    assert '"card_id":"card-1"' in payload
    assert '"text":"Application-owned evidence."' in payload
    assert "source_number" not in payload


def test_response_serializes_with_public_schema_alias():
    structured = response(evidence("Supported evidence.", "E1"))
    assert structured.schema == EVIDENCE_PROSE_OUTPUT_SCHEMA
    assert structured.model_dump()["schema"] == EVIDENCE_PROSE_OUTPUT_SCHEMA
    assert "schema_" not in structured.model_dump()


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (ArchivistMode.PROFESSIONAL, "present-minded professional-public-history"),
        (ArchivistMode.BALEFUL_BLACK_BARON, "Baleful Black Baron"),
        (ArchivistMode.PRETTY_PINK_PRINCESS, "Pretty Pink Princess"),
    ],
)
def test_mode_instructions_are_deliberately_distinct(mode, expected):
    prompt = build_evidence_prose_instructions(mode)
    assert expected in prompt
    assert "Factual freedom is zero" in prompt
    assert "Use every supplied card exactly once" in prompt
    assert "at most two" in prompt and "character_aside" in prompt
    assert "arrangement selector" in prompt
    assert "Allowed editorial cue IDs for this mode" in prompt


def test_advanced_facets_modify_prose_only_without_relaxing_evidence_rules():
    prompt = build_evidence_prose_instructions(
        ArchivistMode.PROFESSIONAL,
        historiographical_lens="tragic",
        voice="romantic",
        worldview="pious",
    )
    assert "Selected advanced historiographical lens" in prompt
    assert "Selected advanced voice" in prompt
    assert "Selected advanced worldview" in prompt
    assert "never relax" in prompt
    assert "Factual freedom is zero" in prompt


@pytest.mark.parametrize(
    "mode",
    (
        ArchivistMode.PROFESSIONAL,
        ArchivistMode.BALEFUL_BLACK_BARON,
        ArchivistMode.PRETTY_PINK_PRINCESS,
    ),
)
def test_active_renderer_embeds_and_hashes_the_registered_influence_profile(mode):
    prompt = build_evidence_prose_instructions(mode)
    influence_prompt = load_influence_profile_prompt(mode)
    metadata = evidence_prose_prompt_metadata(mode)
    registered_metadata = archivist_mode_metadata(mode)

    assert influence_prompt in prompt
    assert metadata["prose_renderer_prompt_sha256"] == hashlib.sha256(
        prompt.encode("utf-8")
    ).hexdigest()
    assert metadata["prose_renderer_influence_prompt_sha256"] == registered_metadata[
        "influence_prompt_sha256"
    ]


def test_renderer_maps_cards_to_citations_and_keeps_cohesive_paragraphs():
    structured = response(
        aside(EditorialCueId.BARON_FORGOTTEN_TURNINGS),
        evidence("unused", "E1"),
        evidence("unused", "E2", paragraph=2),
        interpretation(EditorialCueId.BARON_TRAGIC_LEDGER, 2),
    )
    result = validate_and_render_evidence_prose(
        structured, CARDS, mode=ArchivistMode.BALEFUL_BLACK_BARON
    )
    assert result.status is ProseRenderStatus.GENERATED
    assert result.used_card_ids == ("E1", "E2")
    assert result.used_source_numbers == (2, 3, 4)
    assert "[Source 2]." in result.answer
    assert "[Source 3, Source 4]." in result.answer
    assert "The Baron reflects" in result.answer
    assert EDITORIAL_CUES[EditorialCueId.BARON_FORGOTTEN_TURNINGS].text in result.answer
    assert EditorialCueId.BARON_FORGOTTEN_TURNINGS.value not in result.answer
    assert "\n\n" in result.answer


def test_unknown_or_omitted_cards_fail_closed():
    with pytest.raises(EvidenceProseContractError, match="unknown evidence card"):
        validate_and_render_evidence_prose(
            response(
                evidence("An unsupported claim.", "E9"),
                interpretation(EditorialCueId.PROFESSIONAL_POWER_AND_CONSEQUENCE),
            ),
            CARDS,
            mode=ArchivistMode.PROFESSIONAL,
        )
    with pytest.raises(EvidenceProseContractError, match="did not use every"):
        validate_and_render_evidence_prose(
            response(
                evidence("One supported fact.", "E1"),
                aside(EditorialCueId.PRINCESS_PATH_CATCHES_LIGHT),
            ),
            CARDS,
            mode=ArchivistMode.PRETTY_PINK_PRINCESS,
        )


def test_duplicate_evidence_card_fails_exactly_once_contract():
    structured = response(
        evidence("unused", "E1"),
        evidence("unused", "E1"),
        evidence("unused", "E2"),
        interpretation(EditorialCueId.PROFESSIONAL_POWER_AND_CONSEQUENCE),
    )
    with pytest.raises(EvidenceProseContractError, match="more than once"):
        validate_and_render_evidence_prose(
            structured,
            CARDS,
            mode=ArchivistMode.PROFESSIONAL,
        )


def test_typed_segments_separate_fact_from_interpretation_and_model_citations():
    with pytest.raises(ValueError):
        EvidenceProseSegment(
            kind=ProseSegmentKind.INTERPRETATION,
            paragraph=1,
            text=EditorialCueId.PROFESSIONAL_POWER_AND_CONSEQUENCE.value,
            card_ids=("E1",),
        )
    with pytest.raises(ValueError):
        EvidenceProseSegment(
            kind=ProseSegmentKind.EVIDENCE,
            paragraph=1,
            text="A fact [Source 1].",
            card_ids=("E1",),
        )


def test_evidence_segment_cannot_smuggle_factual_prose_under_a_valid_card():
    with pytest.raises(ValueError):
        EvidenceProseSegment(
            kind=ProseSegmentKind.EVIDENCE,
            paragraph=1,
            text="Napoleon secretly directed the settlement.",
            card_ids=("E1",),
        )


def test_renderer_uses_immutable_application_card_text_not_provider_text():
    result = validate_and_render_evidence_prose(
        response(
            evidence("unused", "E1"),
            evidence("unused", "E2"),
            interpretation(EditorialCueId.PROFESSIONAL_POWER_AND_CONSEQUENCE),
        ),
        CARDS,
        mode=ArchivistMode.PROFESSIONAL,
    )
    assert "The treasurer supported repeal of the harsh laws [Source 2]." in result.answer
    assert (
        "The settlers were allowed to organize a legislature [Source 3, Source 4]." in result.answer
    )


@pytest.mark.parametrize(
    "invented_text",
    (
        "Napoleon secretly directed the settlement.",
        "The year 1619 cast a shadow.",
        'The Baron calls this "inevitable."',
    ),
)
def test_editorial_segments_reject_every_model_authored_sentence(invented_text):
    with pytest.raises(ValueError):
        EvidenceProseSegment(
            kind=ProseSegmentKind.CHARACTER_ASIDE,
            paragraph=1,
            text=invented_text,
            card_ids=(),
        )


def test_character_asides_and_all_editorial_cues_are_bounded_per_response():
    response(
        aside(EditorialCueId.BARON_FORGOTTEN_TURNINGS),
        aside(EditorialCueId.BARON_QUIET_CLOSING_DOOR),
        evidence("unused", "E1"),
        evidence("unused", "E2"),
    )
    with pytest.raises(ValueError, match="at most 2 asides"):
        response(
            aside(EditorialCueId.BARON_FORGOTTEN_TURNINGS),
            aside(EditorialCueId.BARON_QUIET_CLOSING_DOOR),
            aside(EditorialCueId.BARON_ASH_AFTER_FIRE),
            evidence("unused", "E1"),
            evidence("unused", "E2"),
        )
    with pytest.raises(ValueError, match="at most 3 editorial cues"):
        response(
            interpretation(EditorialCueId.PROFESSIONAL_POWER_AND_CONSEQUENCE),
            interpretation(EditorialCueId.PROFESSIONAL_CONTEXT_AND_JUDGMENT),
            interpretation(EditorialCueId.PROFESSIONAL_COMPLEXITY_WITHOUT_EVASION),
            interpretation(EditorialCueId.PROFESSIONAL_INSTITUTIONS_AND_EXPERIENCE),
            evidence("unused", "E1"),
            evidence("unused", "E2"),
        )
    with pytest.raises(ValueError, match="must be unique"):
        response(
            aside(EditorialCueId.BARON_FORGOTTEN_TURNINGS),
            aside(EditorialCueId.BARON_FORGOTTEN_TURNINGS),
            evidence("unused", "E1"),
            evidence("unused", "E2"),
        )


def test_professional_mode_rejects_character_asides():
    structured = response(
        aside(EditorialCueId.BARON_FORGOTTEN_TURNINGS),
        evidence("unused", "E1"),
        evidence("unused", "E2"),
    )
    with pytest.raises(EvidenceProseContractError, match="Professional"):
        validate_and_render_evidence_prose(structured, CARDS, mode=ArchivistMode.PROFESSIONAL)


@pytest.mark.parametrize(
    ("cue", "mode"),
    (
        (
            EditorialCueId.PRINCESS_HOPE_WITHOUT_DISGUISE,
            ArchivistMode.BALEFUL_BLACK_BARON,
        ),
        (
            EditorialCueId.BARON_TRAGIC_LEDGER,
            ArchivistMode.PRETTY_PINK_PRINCESS,
        ),
        (
            EditorialCueId.BARON_TRAGIC_LEDGER,
            ArchivistMode.PROFESSIONAL,
        ),
    ),
)
def test_cross_mode_editorial_cues_fail_closed(cue, mode):
    structured = response(
        evidence("unused", "E1"),
        evidence("unused", "E2"),
        EvidenceProseSegment(
            kind=EDITORIAL_CUES[cue].kind,
            paragraph=1,
            text=cue.value,
            card_ids=(),
        ),
    )
    with pytest.raises(EvidenceProseContractError, match="does not belong"):
        validate_and_render_evidence_prose(structured, CARDS, mode=mode)


def test_cue_catalog_is_distinct_and_application_owned():
    by_mode = {
        mode: {
            cue
            for cue, definition in EDITORIAL_CUES.items()
            if definition.mode is mode
        }
        for mode in (
            ArchivistMode.PROFESSIONAL,
            ArchivistMode.BALEFUL_BLACK_BARON,
            ArchivistMode.PRETTY_PINK_PRINCESS,
        )
    }
    assert len(by_mode[ArchivistMode.PROFESSIONAL]) >= 6
    assert len(by_mode[ArchivistMode.BALEFUL_BLACK_BARON]) >= 8
    assert len(by_mode[ArchivistMode.PRETTY_PINK_PRINCESS]) >= 8
    assert all(
        by_mode[left].isdisjoint(by_mode[right])
        for left in by_mode
        for right in by_mode
        if left is not right
    )
    assert all(definition.text.strip() for definition in EDITORIAL_CUES.values())


class RecordingClient:
    def __init__(self):
        self.max_retries = None

    def with_options(self, *, max_retries):
        self.max_retries = max_retries
        return self


def test_generation_is_one_low_reasoning_call_without_retry(monkeypatch):
    client = RecordingClient()
    calls = []
    structured = response(
        evidence("unused", "E1"),
        evidence("unused", "E2"),
        interpretation(EditorialCueId.PROFESSIONAL_POWER_AND_CONSEQUENCE),
    )

    def fake_parse(request_client, *, operation, **request):
        calls.append((request_client, operation, request))
        return SimpleNamespace(output_parsed=structured, output=())

    monkeypatch.setattr(prose_renderer, "tracked_responses_parse", fake_parse)
    result = generate_evidence_prose(
        client,
        question="What changed?",
        cards=CARDS,
        mode=ArchivistMode.PROFESSIONAL,
    )
    assert result.status is ProseRenderStatus.GENERATED
    assert client.max_retries == 0
    assert len(calls) == 1
    assert calls[0][1] == "answer_generation"
    assert calls[0][2]["reasoning"] == {"effort": "low"}
    assert calls[0][2]["text"] == {"verbosity": "low"}
    assert calls[0][2]["max_output_tokens"] == 576
    assert calls[0][2]["text_format"] is EvidenceProseResponse


def test_provider_or_invalid_response_returns_fallback_signal(monkeypatch):
    client = RecordingClient()

    def provider_failure(*_args, **_kwargs):
        raise RuntimeError("offline synthetic failure")

    monkeypatch.setattr(prose_renderer, "tracked_responses_parse", provider_failure)
    failed = generate_evidence_prose(
        client,
        question="What changed?",
        cards=CARDS,
        mode=ArchivistMode.BALEFUL_BLACK_BARON,
    )
    assert failed.status is ProseRenderStatus.FALLBACK_REQUIRED
    assert failed.answer is None
    assert failed.failure_code is ProseFailureCode.PROVIDER_FAILURE

    monkeypatch.setattr(
        prose_renderer,
        "tracked_responses_parse",
        lambda *_args, **_kwargs: SimpleNamespace(output_parsed=None, output=()),
    )
    invalid = generate_evidence_prose(
        client,
        question="What changed?",
        cards=CARDS,
        mode=ArchivistMode.PRETTY_PINK_PRINCESS,
    )
    assert invalid.failure_code is ProseFailureCode.INVALID_RESPONSE


def test_refusal_is_a_distinct_fallback_and_cost_limit_passes_through(monkeypatch):
    client = RecordingClient()
    refusal = SimpleNamespace(
        output_parsed=None,
        output=(
            SimpleNamespace(
                type="message",
                content=(SimpleNamespace(type="refusal"),),
            ),
        ),
    )
    monkeypatch.setattr(
        prose_renderer,
        "tracked_responses_parse",
        lambda *_args, **_kwargs: refusal,
    )
    refused = generate_evidence_prose(
        client,
        question="What changed?",
        cards=CARDS,
        mode=ArchivistMode.BALEFUL_BLACK_BARON,
    )
    assert refused.failure_code is ProseFailureCode.REFUSAL

    budget_error = CostLimitExceeded({"limit": "synthetic"})

    def cost_limit(*_args, **_kwargs):
        raise budget_error

    monkeypatch.setattr(prose_renderer, "tracked_responses_parse", cost_limit)
    with pytest.raises(CostLimitExceeded) as exc_info:
        generate_evidence_prose(
            client,
            question="What changed?",
            cards=CARDS,
            mode=ArchivistMode.PRETTY_PINK_PRINCESS,
        )
    assert exc_info.value is budget_error


def test_post_call_card_mapping_violation_returns_invalid_fallback(monkeypatch):
    client = RecordingClient()
    calls = 0

    def fake_parse(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            output_parsed=response(
                evidence("Only one card was used.", "E1"),
                interpretation(EditorialCueId.PROFESSIONAL_POWER_AND_CONSEQUENCE),
            ),
            output=(),
        )

    monkeypatch.setattr(prose_renderer, "tracked_responses_parse", fake_parse)
    result = generate_evidence_prose(
        client,
        question="What changed?",
        cards=CARDS,
        mode=ArchivistMode.PROFESSIONAL,
    )
    assert calls == 1
    assert result.status is ProseRenderStatus.FALLBACK_REQUIRED
    assert result.failure_code is ProseFailureCode.INVALID_RESPONSE


@pytest.mark.parametrize(
    ("card", "expected"),
    [
        (Card("bad id", "Evidence.", (1,)), "valid card ID"),
        (
            Card("E1", "x" * (prose_renderer.MAX_CARD_TEXT_CHARACTERS + 1), (1,)),
            "card text",
        ),
        (Card("E1", "Evidence.", [1]), "source_numbers"),
        (Card("E1", "Evidence.", (True,)), "source_numbers"),
        (Card("E1", "Evidence.", (1,), ("bad id",)), "requirement_ids"),
        (Card("E1", "Evidence.", (1,), (["not", "hashable"],)), "requirement_ids"),
    ],
)
def test_application_owned_card_contract_is_validated_before_a_call(card, expected):
    with pytest.raises(EvidenceProseContractError, match=expected):
        build_evidence_prose_input("What changed?", (card,), ArchivistMode.PROFESSIONAL)


def test_essential_and_retired_modes_are_not_prose_renderer_modes():
    for mode in (ArchivistMode.ESSENTIAL, ArchivistMode.FOREST):
        with pytest.raises(EvidenceProseContractError, match="unsupported"):
            build_evidence_prose_input("What changed?", CARDS, mode)
