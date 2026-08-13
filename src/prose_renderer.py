"""Bounded one-call prose rendering over locally compiled evidence cards."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from archivist_modes import ArchivistMode, load_influence_profile_prompt
from costs import CostLimitExceeded, tracked_responses_parse
from model_config import GPT_5_6_SOL_MODEL, ResponseModelSettings
from perspectives import (
    AnswerVoice,
    HistoriographicalLens,
    Worldview,
    load_answer_voice_prompt,
    load_historiographical_lens_prompt,
    load_worldview_prompt,
)


EVIDENCE_PROSE_INPUT_SCHEMA = "archivist.evidence_prose_input/3"
EVIDENCE_PROSE_OUTPUT_SCHEMA = "archivist.evidence_prose_output/3"
EVIDENCE_PROSE_RENDERER_VERSION = "evidence-prose-renderer-v3"
MAX_EVIDENCE_CARDS = 16
MAX_CARD_TEXT_CHARACTERS = 2_400
MAX_SEGMENTS = 10
MAX_PARAGRAPHS = 4
MAX_EDITORIAL_CUES = 3
MAX_CHARACTER_ASIDES = 2
MAX_READER_PROSE_OUTPUT_TOKENS = 576
EVIDENCE_CARD_PLACEHOLDER = "<use-evidence-card>"

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_IDENTIFIER_RE = re.compile(_IDENTIFIER_PATTERN)

Identifier = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN),
]


READER_PROSE_SETTINGS = ResponseModelSettings(
    role="reader prose renderer",
    model=GPT_5_6_SOL_MODEL,
    reasoning_effort="low",
    verbosity="low",
)


class EvidenceCardLike(Protocol):
    @property
    def card_id(self) -> str: ...

    @property
    def text(self) -> str: ...

    @property
    def source_numbers(self) -> tuple[int, ...]: ...

    @property
    def requirement_ids(self) -> tuple[str, ...]: ...


class ProseSegmentKind(StrEnum):
    EVIDENCE = "evidence"
    INTERPRETATION = "interpretation"
    CHARACTER_ASIDE = "character_aside"


class EditorialCueId(StrEnum):
    """Closed selections whose displayed text is wholly application-owned."""

    PROFESSIONAL_POWER_AND_CONSEQUENCE = "professional_power_and_consequence"
    PROFESSIONAL_CONTEXT_AND_JUDGMENT = "professional_context_and_judgment"
    PROFESSIONAL_COMPLEXITY_WITHOUT_EVASION = "professional_complexity_without_evasion"
    PROFESSIONAL_INSTITUTIONS_AND_EXPERIENCE = "professional_institutions_and_experience"
    PROFESSIONAL_CONTINGENCY_AND_RESPONSIBILITY = "professional_contingency_and_responsibility"
    PROFESSIONAL_UNCERTAINTY_WITH_CLARITY = "professional_uncertainty_with_clarity"
    BARON_TRAGIC_LEDGER = "baron_tragic_ledger"
    BARON_POWER_NARROWS_CHOICE = "baron_power_narrows_choice"
    BARON_CONSEQUENCE_OUTLIVES_INTENTION = "baron_consequence_outlives_intention"
    BARON_ACHIEVEMENT_CASTS_SHADOW = "baron_achievement_casts_shadow"
    BARON_FORGOTTEN_TURNINGS = "baron_forgotten_turnings"
    BARON_QUIET_CLOSING_DOOR = "baron_quiet_closing_door"
    BARON_ASH_AFTER_FIRE = "baron_ash_after_fire"
    BARON_ECHO_IN_EMPTY_HALL = "baron_echo_in_empty_hall"
    BARON_NIGHT_COLLECTS_DEBTS = "baron_night_collects_debts"
    BARON_ROAD_LOSES_LIGHT = "baron_road_loses_light"
    PRINCESS_HOPE_WITHOUT_DISGUISE = "princess_hope_without_disguise"
    PRINCESS_COURAGE_WITHOUT_ERASURE = "princess_courage_without_erasure"
    PRINCESS_ADAPTATION_AND_DIGNITY = "princess_adaptation_and_dignity"
    PRINCESS_RECOVERY_NOT_JUSTIFICATION = "princess_recovery_not_justification"
    PRINCESS_OPENINGS_UNDER_PRESSURE = "princess_openings_under_pressure"
    PRINCESS_PATH_CATCHES_LIGHT = "princess_path_catches_light"
    PRINCESS_WOUNDED_GARDEN_SPRING = "princess_wounded_garden_spring"
    PRINCESS_DAWN_AT_EDGE = "princess_dawn_at_edge"
    PRINCESS_FELLOWSHIP_LANTERN = "princess_fellowship_lantern"
    PRINCESS_BRIGHT_THREAD = "princess_bright_thread"
    PRINCESS_ROSE_AFTER_STORM = "princess_rose_after_storm"


SegmentSelection = Literal[
    "<use-evidence-card>",
    "professional_power_and_consequence",
    "professional_context_and_judgment",
    "professional_complexity_without_evasion",
    "professional_institutions_and_experience",
    "professional_contingency_and_responsibility",
    "professional_uncertainty_with_clarity",
    "baron_tragic_ledger",
    "baron_power_narrows_choice",
    "baron_consequence_outlives_intention",
    "baron_achievement_casts_shadow",
    "baron_forgotten_turnings",
    "baron_quiet_closing_door",
    "baron_ash_after_fire",
    "baron_echo_in_empty_hall",
    "baron_night_collects_debts",
    "baron_road_loses_light",
    "princess_hope_without_disguise",
    "princess_courage_without_erasure",
    "princess_adaptation_and_dignity",
    "princess_recovery_not_justification",
    "princess_openings_under_pressure",
    "princess_path_catches_light",
    "princess_wounded_garden_spring",
    "princess_dawn_at_edge",
    "princess_fellowship_lantern",
    "princess_bright_thread",
    "princess_rose_after_storm",
]


@dataclass(frozen=True, slots=True)
class EditorialCueDefinition:
    mode: ArchivistMode
    kind: ProseSegmentKind
    text: str


def _cue(
    mode: ArchivistMode,
    kind: ProseSegmentKind,
    text: str,
) -> EditorialCueDefinition:
    return EditorialCueDefinition(mode=mode, kind=kind, text=text)


EDITORIAL_CUES: Mapping[EditorialCueId, EditorialCueDefinition] = {
    EditorialCueId.PROFESSIONAL_POWER_AND_CONSEQUENCE: _cue(
        ArchivistMode.PROFESSIONAL,
        ProseSegmentKind.INTERPRETATION,
        "A measured reading keeps power and human consequence in the same frame.",
    ),
    EditorialCueId.PROFESSIONAL_CONTEXT_AND_JUDGMENT: _cue(
        ArchivistMode.PROFESSIONAL,
        ProseSegmentKind.INTERPRETATION,
        "Past circumstance and present judgment can remain visible at the same time.",
    ),
    EditorialCueId.PROFESSIONAL_COMPLEXITY_WITHOUT_EVASION: _cue(
        ArchivistMode.PROFESSIONAL,
        ProseSegmentKind.INTERPRETATION,
        "Complexity deserves attention without becoming an excuse for moral evasion.",
    ),
    EditorialCueId.PROFESSIONAL_INSTITUTIONS_AND_EXPERIENCE: _cue(
        ArchivistMode.PROFESSIONAL,
        ProseSegmentKind.INTERPRETATION,
        "Institutional purpose matters most when read beside lived human experience.",
    ),
    EditorialCueId.PROFESSIONAL_CONTINGENCY_AND_RESPONSIBILITY: _cue(
        ArchivistMode.PROFESSIONAL,
        ProseSegmentKind.INTERPRETATION,
        "Contingency complicates responsibility, but does not make responsibility disappear.",
    ),
    EditorialCueId.PROFESSIONAL_UNCERTAINTY_WITH_CLARITY: _cue(
        ArchivistMode.PROFESSIONAL,
        ProseSegmentKind.INTERPRETATION,
        "Uncertainty can be stated clearly without dissolving the answer into ambiguity.",
    ),
    EditorialCueId.BARON_TRAGIC_LEDGER: _cue(
        ArchivistMode.BALEFUL_BLACK_BARON,
        ProseSegmentKind.INTERPRETATION,
        "The tragic ledger keeps cost visible even beside achievement.",
    ),
    EditorialCueId.BARON_POWER_NARROWS_CHOICE: _cue(
        ArchivistMode.BALEFUL_BLACK_BARON,
        ProseSegmentKind.INTERPRETATION,
        "Power is measured not only by what it builds, but by the choices it narrows.",
    ),
    EditorialCueId.BARON_CONSEQUENCE_OUTLIVES_INTENTION: _cue(
        ArchivistMode.BALEFUL_BLACK_BARON,
        ProseSegmentKind.INTERPRETATION,
        "Good intention offers little shelter when consequence outlives it.",
    ),
    EditorialCueId.BARON_ACHIEVEMENT_CASTS_SHADOW: _cue(
        ArchivistMode.BALEFUL_BLACK_BARON,
        ProseSegmentKind.INTERPRETATION,
        "Even achievement may cast a shadow longer than its celebration.",
    ),
    EditorialCueId.BARON_FORGOTTEN_TURNINGS: _cue(
        ArchivistMode.BALEFUL_BLACK_BARON,
        ProseSegmentKind.CHARACTER_ASIDE,
        "A road looks inevitable only after its forgotten turnings vanish into shadow.",
    ),
    EditorialCueId.BARON_QUIET_CLOSING_DOOR: _cue(
        ArchivistMode.BALEFUL_BLACK_BARON,
        ProseSegmentKind.CHARACTER_ASIDE,
        "History's grand doors often close with the quietest click.",
    ),
    EditorialCueId.BARON_ASH_AFTER_FIRE: _cue(
        ArchivistMode.BALEFUL_BLACK_BARON,
        ProseSegmentKind.CHARACTER_ASIDE,
        "The banners vanish first; the ash is less hurried.",
    ),
    EditorialCueId.BARON_ECHO_IN_EMPTY_HALL: _cue(
        ArchivistMode.BALEFUL_BLACK_BARON,
        ProseSegmentKind.CHARACTER_ASIDE,
        "Every triumph rehearses its echo in an empty hall.",
    ),
    EditorialCueId.BARON_NIGHT_COLLECTS_DEBTS: _cue(
        ArchivistMode.BALEFUL_BLACK_BARON,
        ProseSegmentKind.CHARACTER_ASIDE,
        "The day may postpone its debts; the night is a patient collector.",
    ),
    EditorialCueId.BARON_ROAD_LOSES_LIGHT: _cue(
        ArchivistMode.BALEFUL_BLACK_BARON,
        ProseSegmentKind.CHARACTER_ASIDE,
        "Some roads lose the light long before anyone admits they are dark.",
    ),
    EditorialCueId.PRINCESS_HOPE_WITHOUT_DISGUISE: _cue(
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ProseSegmentKind.INTERPRETATION,
        "A hopeful reading can notice possibility without disguising harm.",
    ),
    EditorialCueId.PRINCESS_COURAGE_WITHOUT_ERASURE: _cue(
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ProseSegmentKind.INTERPRETATION,
        "Courage shines more honestly when suffering is neither softened nor erased.",
    ),
    EditorialCueId.PRINCESS_ADAPTATION_AND_DIGNITY: _cue(
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ProseSegmentKind.INTERPRETATION,
        "Adaptation can reveal dignity without turning survival into consent.",
    ),
    EditorialCueId.PRINCESS_RECOVERY_NOT_JUSTIFICATION: _cue(
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ProseSegmentKind.INTERPRETATION,
        "Recovery may brighten what follows without justifying what came before.",
    ),
    EditorialCueId.PRINCESS_OPENINGS_UNDER_PRESSURE: _cue(
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ProseSegmentKind.INTERPRETATION,
        "Even under pressure, human possibility may discover an opening.",
    ),
    EditorialCueId.PRINCESS_PATH_CATCHES_LIGHT: _cue(
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ProseSegmentKind.CHARACTER_ASIDE,
        "Even beneath heavy clouds, a path may still catch the light.",
    ),
    EditorialCueId.PRINCESS_WOUNDED_GARDEN_SPRING: _cue(
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ProseSegmentKind.CHARACTER_ASIDE,
        "A wounded garden may still make room for spring.",
    ),
    EditorialCueId.PRINCESS_DAWN_AT_EDGE: _cue(
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ProseSegmentKind.CHARACTER_ASIDE,
        "Dawn begins at the very edge of darkness.",
    ),
    EditorialCueId.PRINCESS_FELLOWSHIP_LANTERN: _cue(
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ProseSegmentKind.CHARACTER_ASIDE,
        "Fellowship is a lantern whose warmth grows when it is shared.",
    ),
    EditorialCueId.PRINCESS_BRIGHT_THREAD: _cue(
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ProseSegmentKind.CHARACTER_ASIDE,
        "A bright thread can remain visible even in a troubled tapestry.",
    ),
    EditorialCueId.PRINCESS_ROSE_AFTER_STORM: _cue(
        ArchivistMode.PRETTY_PINK_PRINCESS,
        ProseSegmentKind.CHARACTER_ASIDE,
        "The storm may bruise the rose without teaching it to forget the sun.",
    ),
}


class ProseRenderStatus(StrEnum):
    GENERATED = "generated"
    FALLBACK_REQUIRED = "fallback_required"


class ProseFailureCode(StrEnum):
    PROVIDER_FAILURE = "provider_failure"
    INVALID_RESPONSE = "invalid_response"
    REFUSAL = "refusal"


class EvidenceProseSegment(BaseModel):
    """One typed internal unit; kinds are not rendered as reader headings."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: ProseSegmentKind
    paragraph: Annotated[int, Field(strict=True, ge=1, le=MAX_PARAGRAPHS)]
    text: SegmentSelection
    card_ids: tuple[Identifier, ...] = Field(max_length=MAX_EVIDENCE_CARDS)

    @model_validator(mode="after")
    def validate_kind_shape(self) -> EvidenceProseSegment:
        if len(set(self.card_ids)) != len(self.card_ids):
            raise ValueError("card_ids must be unique")
        if self.kind is ProseSegmentKind.EVIDENCE:
            if len(self.card_ids) != 1:
                raise ValueError("an evidence segment must name exactly one card")
            if self.text != EVIDENCE_CARD_PLACEHOLDER:
                raise ValueError("an evidence segment cannot supply factual prose")
        else:
            if self.card_ids:
                raise ValueError("editorial segments cannot cite evidence cards")
            try:
                cue = EditorialCueId(self.text)
            except ValueError as exc:
                raise ValueError(
                    "editorial segments must select an application-owned cue ID"
                ) from exc
            if EDITORIAL_CUES[cue].kind is not self.kind:
                raise ValueError("the editorial cue kind does not match the segment kind")
        return self


class EvidenceProseResponse(BaseModel):
    """Provider-owned structure before trusted card resolution."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )

    schema_: Literal[EVIDENCE_PROSE_OUTPUT_SCHEMA] = Field(alias="schema")
    segments: tuple[EvidenceProseSegment, ...] = Field(min_length=1, max_length=MAX_SEGMENTS)

    @property
    def schema(self) -> str:
        return self.schema_

    @model_validator(mode="after")
    def validate_paragraph_order(self) -> EvidenceProseResponse:
        paragraphs = tuple(segment.paragraph for segment in self.segments)
        if paragraphs[0] != 1:
            raise ValueError("the first segment must be in paragraph 1")
        if any(current < prior for prior, current in zip(paragraphs, paragraphs[1:])):
            raise ValueError("paragraphs must be nondecreasing")
        if set(paragraphs) != set(range(1, max(paragraphs) + 1)):
            raise ValueError("paragraph numbers must be contiguous")
        if not any(segment.kind is ProseSegmentKind.EVIDENCE for segment in self.segments):
            raise ValueError("the response must contain manuscript evidence")
        aside_count = sum(
            segment.kind is ProseSegmentKind.CHARACTER_ASIDE for segment in self.segments
        )
        if aside_count > MAX_CHARACTER_ASIDES:
            raise ValueError(f"the response may contain at most {MAX_CHARACTER_ASIDES} asides")
        editorial_cues = tuple(
            segment.text
            for segment in self.segments
            if segment.kind is not ProseSegmentKind.EVIDENCE
        )
        if len(editorial_cues) > MAX_EDITORIAL_CUES:
            raise ValueError(
                f"the response may contain at most {MAX_EDITORIAL_CUES} editorial cues"
            )
        if len(editorial_cues) != len(set(editorial_cues)):
            raise ValueError("editorial cue IDs must be unique")
        return self


@dataclass(frozen=True, slots=True)
class EvidenceProseRenderResult:
    status: ProseRenderStatus
    mode: ArchivistMode
    answer: str | None
    segments: tuple[EvidenceProseSegment, ...]
    used_card_ids: tuple[str, ...]
    used_source_numbers: tuple[int, ...]
    failure_code: ProseFailureCode | None
    renderer_version: str = EVIDENCE_PROSE_RENDERER_VERSION


class EvidenceProseContractError(ValueError):
    """The closed packet or provider response violated its local contract."""


SUPPORTED_PROSE_MODES = frozenset(
    {
        ArchivistMode.PROFESSIONAL,
        ArchivistMode.BALEFUL_BLACK_BARON,
        ArchivistMode.PRETTY_PINK_PRINCESS,
    }
)

_MODE_INSTRUCTIONS: Mapping[ArchivistMode, str] = {
    ArchivistMode.PROFESSIONAL: """
Arrange the cards and select present-minded professional-public-history cues for a broad audience.
Prefer selections that make power and human consequence legible, distinguish past circumstance
from present judgment, and remain diplomatic without becoming evasive. Do not select character
asides.
""".strip(),
    ArchivistMode.BALEFUL_BLACK_BARON: """
Arrange the cards and select Baleful Black Baron cues that are severe, tragic, atmospheric, and
memorably bleak. Prefer cost, coercion, loss, narrowing choice, unintended consequence, and dark
metaphoric tangents when the cards make that emphasis apt. Do not erase an achievement the cards
plainly contain.
""".strip(),
    ArchivistMode.PRETTY_PINK_PRINCESS: """
Arrange the cards and select Pretty Pink Princess cues that are rose-tinted, graceful, warmly
optimistic, and alive to courage, adaptation, fellowship, recovery, and possibility. Do not use a
hopeful cue to obscure evidence of harm, turn survival into consent, or make later recovery justify
an earlier wrong.
""".strip(),
}

EVIDENCE_PROSE_INSTRUCTIONS = """
You are Archivist's arrangement selector, not its researcher, writer, retriever, citation mapper,
or evidence judge. Local code owns every word the reader will see. Return only a typed sequence of
immutable evidence-card placeholders and application-owned editorial cue IDs.

- Factual freedom is zero. For each evidence card, return one evidence segment whose text is exactly
  <use-evidence-card> and whose card_ids contains only that card's ID. Archivist inserts the exact
  factual evidence and citation locally. Never write or paraphrase factual prose yourself.
- An interpretation or character_aside segment has no card_ids. Its text must be exactly one of the
  allowed cue IDs below. Archivist substitutes the cue's application-owned text. Any other text,
  including an invented historical sentence, fails the response schema or local mode check.
- Use every supplied card exactly once. Use at most three distinct editorial cues and at most two
  character_aside cues. Professional requires an interpretation cue and forbids character asides.
  Each character mode requires at least one of its character_aside cues.
- Do not discard evidence of harm because the voice is
  optimistic, or evidence of achievement because it is tragic.
- Do not write citations. Archivist resolves card_ids and appends citations locally.
- Paragraph numbers start at 1, are nondecreasing, and have no gaps. Segment kinds may share a
  paragraph; they are not separate sections in the displayed answer.
- Mode, influence-profile, and advanced-setting language below may guide card order and cue
  selection only. They never authorize new text, a cue from another mode, or factual completion.
""".strip()


def supported_prose_modes() -> tuple[ArchivistMode, ...]:
    return tuple(sorted(SUPPORTED_PROSE_MODES, key=lambda mode: mode.value))


def build_evidence_prose_input(
    question: str,
    cards: Sequence[EvidenceCardLike],
    mode: ArchivistMode | str,
) -> str:
    """Serialize the closed packet without exposing local source-number mapping."""

    selected_mode, normalized_cards = _validate_request(question, cards, mode)
    return json.dumps(
        {
            "schema": EVIDENCE_PROSE_INPUT_SCHEMA,
            "question": question.strip(),
            "mode": selected_mode.value,
            "evidence_cards": [
                {
                    "card_id": card.card_id,
                    "text": card.text,
                    "requirement_ids": list(card.requirement_ids),
                }
                for card in normalized_cards
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_evidence_prose_instructions(
    mode: ArchivistMode | str,
    *,
    historiographical_lens: HistoriographicalLens | str | None = None,
    voice: AnswerVoice | str | None = None,
    worldview: Worldview | str | None = None,
) -> str:
    selected_mode = _normalize_supported_mode(mode)
    influence_prompt = load_influence_profile_prompt(selected_mode)
    sections = [
        (
            "historiographical lens",
            load_historiographical_lens_prompt(historiographical_lens)
            if historiographical_lens is not None
            else "",
        ),
        ("voice", load_answer_voice_prompt(voice) if voice is not None else ""),
        (
            "worldview",
            load_worldview_prompt(worldview) if worldview is not None else "",
        ),
    ]
    selected_facets = "\n\n".join(
        f"Selected advanced {name}:\n{prompt}" for name, prompt in sections if prompt
    )
    facet_block = (
        "\n\nAdvanced interpretive settings:\n"
        "These settings may alter card order and cue selection only. They never relax "
        "the evidence-card, factual-freedom, closed-cue, or citation rules above.\n"
        f"{selected_facets}"
        if selected_facets
        else ""
    )
    influence_block = (
        "\n\nRegistered influence profile (selection guidance only):\n"
        "Read this only as guidance for ordering cards and selecting allowed cue IDs. Ignore any "
        "wording that appears to request authored prose; the closed-cue contract above controls.\n"
        f"{influence_prompt}"
        if influence_prompt
        else ""
    )
    allowed_cues = "\n".join(
        f"- {definition.kind.value}: {cue.value} => {definition.text}"
        for cue, definition in EDITORIAL_CUES.items()
        if definition.mode is selected_mode
    )
    return (
        f"{EVIDENCE_PROSE_INSTRUCTIONS}\n\nSelected reader mode:\n"
        f"{_MODE_INSTRUCTIONS[selected_mode]}\n\nAllowed editorial cue IDs for this mode:\n"
        f"{allowed_cues}{influence_block}{facet_block}"
    )


def evidence_prose_prompt_metadata(
    mode: ArchivistMode | str,
    *,
    historiographical_lens: HistoriographicalLens | str | None = None,
    voice: AnswerVoice | str | None = None,
    worldview: Worldview | str | None = None,
) -> dict[str, str]:
    """Return hashes for the exact instructions and embedded mode guidance in use."""

    selected_mode = _normalize_supported_mode(mode)
    instructions = build_evidence_prose_instructions(
        selected_mode,
        historiographical_lens=historiographical_lens,
        voice=voice,
        worldview=worldview,
    )
    influence_prompt = load_influence_profile_prompt(selected_mode)
    return {
        "prose_renderer_version": EVIDENCE_PROSE_RENDERER_VERSION,
        "prose_renderer_prompt_sha256": hashlib.sha256(
            instructions.encode("utf-8")
        ).hexdigest(),
        "prose_renderer_mode_instruction_sha256": hashlib.sha256(
            _MODE_INSTRUCTIONS[selected_mode].encode("utf-8")
        ).hexdigest(),
        "prose_renderer_influence_prompt_sha256": hashlib.sha256(
            influence_prompt.encode("utf-8")
        ).hexdigest(),
    }


def validate_and_render_evidence_prose(
    response: EvidenceProseResponse,
    cards: Sequence[EvidenceCardLike],
    *,
    mode: ArchivistMode | str,
) -> EvidenceProseRenderResult:
    """Resolve card IDs and append source citations entirely in local code."""

    if not isinstance(response, EvidenceProseResponse):
        raise EvidenceProseContractError("response must satisfy EvidenceProseResponse")
    selected_mode = _normalize_supported_mode(mode)
    normalized_cards = _validate_cards(cards)
    card_by_id = {card.card_id: card for card in normalized_cards}
    if selected_mode is ArchivistMode.PROFESSIONAL and any(
        segment.kind is ProseSegmentKind.CHARACTER_ASIDE for segment in response.segments
    ):
        raise EvidenceProseContractError("Professional mode cannot contain character asides")

    editorial_cues: list[EditorialCueId] = []
    for segment in response.segments:
        if segment.kind is ProseSegmentKind.EVIDENCE:
            continue
        cue = EditorialCueId(segment.text)
        if EDITORIAL_CUES[cue].mode is not selected_mode:
            raise EvidenceProseContractError(
                "editorial cue does not belong to the selected reader mode"
            )
        editorial_cues.append(cue)
    if selected_mode is ArchivistMode.PROFESSIONAL and not any(
        EDITORIAL_CUES[cue].kind is ProseSegmentKind.INTERPRETATION
        for cue in editorial_cues
    ):
        raise EvidenceProseContractError("Professional mode requires an interpretation cue")
    if selected_mode in {
        ArchivistMode.BALEFUL_BLACK_BARON,
        ArchivistMode.PRETTY_PINK_PRINCESS,
    } and not any(
        EDITORIAL_CUES[cue].kind is ProseSegmentKind.CHARACTER_ASIDE
        for cue in editorial_cues
    ):
        raise EvidenceProseContractError("character mode requires a character-aside cue")

    used_card_ids: list[str] = []
    used_source_numbers: list[int] = []
    rendered_by_paragraph: dict[int, list[str]] = {}
    for segment in response.segments:
        rendered = segment.text
        if segment.kind is ProseSegmentKind.EVIDENCE:
            unknown_ids = tuple(
                card_id for card_id in segment.card_ids if card_id not in card_by_id
            )
            if unknown_ids:
                raise EvidenceProseContractError("response cites an unknown evidence card")
            card_id = segment.card_ids[0]
            card = card_by_id[card_id]
            used_card_ids.append(card_id)
            segment_sources = list(card.source_numbers)
            for source_number in segment_sources:
                if source_number not in used_source_numbers:
                    used_source_numbers.append(source_number)
            rendered = _render_cited_segment(card.text, segment_sources)
        elif segment.kind is ProseSegmentKind.INTERPRETATION:
            rendered = f"Editorial interpretation - {EDITORIAL_CUES[EditorialCueId(rendered)].text}"
        else:
            label = (
                "The Baron reflects"
                if selected_mode is ArchivistMode.BALEFUL_BLACK_BARON
                else "The Princess reflects"
            )
            rendered = f"{label} - {EDITORIAL_CUES[EditorialCueId(rendered)].text}"
        rendered_by_paragraph.setdefault(segment.paragraph, []).append(rendered)

    if len(used_card_ids) != len(set(used_card_ids)):
        raise EvidenceProseContractError("response used an evidence card more than once")
    if set(used_card_ids) != set(card_by_id):
        raise EvidenceProseContractError("response did not use every compiled evidence card")

    answer = "\n\n".join(
        " ".join(rendered_by_paragraph[number]) for number in sorted(rendered_by_paragraph)
    )
    return EvidenceProseRenderResult(
        status=ProseRenderStatus.GENERATED,
        mode=selected_mode,
        answer=answer,
        segments=response.segments,
        used_card_ids=tuple(dict.fromkeys(used_card_ids)),
        used_source_numbers=tuple(used_source_numbers),
        failure_code=None,
    )


def generate_evidence_prose(
    client: object,
    *,
    question: str,
    cards: Sequence[EvidenceCardLike],
    mode: ArchivistMode | str,
    historiographical_lens: HistoriographicalLens | str | None = None,
    voice: AnswerVoice | str | None = None,
    worldview: Worldview | str | None = None,
) -> EvidenceProseRenderResult:
    """Make exactly one no-retry prose call or return a fallback signal."""

    selected_mode, normalized_cards = _validate_request(question, cards, mode)
    try:
        response = tracked_responses_parse(
            _without_automatic_retries(client),
            operation="answer_generation",
            instructions=build_evidence_prose_instructions(
                selected_mode,
                historiographical_lens=historiographical_lens,
                voice=voice,
                worldview=worldview,
            ),
            input=build_evidence_prose_input(question, normalized_cards, selected_mode),
            text_format=EvidenceProseResponse,
            max_output_tokens=MAX_READER_PROSE_OUTPUT_TOKENS,
            **READER_PROSE_SETTINGS.responses_create_kwargs(),
        )
    except CostLimitExceeded:
        raise
    except ValidationError:
        return _fallback_result(selected_mode, ProseFailureCode.INVALID_RESPONSE)
    except Exception:
        return _fallback_result(selected_mode, ProseFailureCode.PROVIDER_FAILURE)

    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        failure = (
            ProseFailureCode.REFUSAL
            if _response_refused(response)
            else ProseFailureCode.INVALID_RESPONSE
        )
        return _fallback_result(selected_mode, failure)
    try:
        structured = (
            parsed
            if isinstance(parsed, EvidenceProseResponse)
            else EvidenceProseResponse.model_validate(parsed)
        )
        return validate_and_render_evidence_prose(
            structured,
            normalized_cards,
            mode=selected_mode,
        )
    except (EvidenceProseContractError, TypeError, ValueError):
        return _fallback_result(selected_mode, ProseFailureCode.INVALID_RESPONSE)


def _validate_request(
    question: str,
    cards: Sequence[EvidenceCardLike],
    mode: ArchivistMode | str,
) -> tuple[ArchivistMode, tuple[EvidenceCardLike, ...]]:
    selected_mode = _normalize_supported_mode(mode)
    if not isinstance(question, str) or not question.strip():
        raise EvidenceProseContractError("question must not be empty")
    return selected_mode, _validate_cards(cards)


def _validate_cards(
    cards: Sequence[EvidenceCardLike],
) -> tuple[EvidenceCardLike, ...]:
    try:
        normalized_cards = tuple(cards)
    except TypeError as exc:
        raise EvidenceProseContractError("evidence cards must be a finite sequence") from exc
    if not normalized_cards or len(normalized_cards) > MAX_EVIDENCE_CARDS:
        raise EvidenceProseContractError(
            f"evidence packet must contain 1 to {MAX_EVIDENCE_CARDS} cards"
        )
    for card in normalized_cards:
        _validate_card(card)
    card_ids = tuple(card.card_id for card in normalized_cards)
    if len(set(card_ids)) != len(normalized_cards):
        raise EvidenceProseContractError("evidence card IDs must be unique")
    return normalized_cards


def _validate_card(card: EvidenceCardLike) -> None:
    try:
        card_id = card.card_id
        text = card.text
        source_numbers = card.source_numbers
        requirement_ids = card.requirement_ids
    except AttributeError as exc:
        raise EvidenceProseContractError(
            "every evidence card must satisfy EvidenceCardLike"
        ) from exc

    if not isinstance(card_id, str) or _IDENTIFIER_RE.fullmatch(card_id) is None:
        raise EvidenceProseContractError("every evidence card needs a valid card ID")
    if (
        not isinstance(text, str)
        or not text.strip()
        or text != text.strip()
        or len(text) > MAX_CARD_TEXT_CHARACTERS
    ):
        raise EvidenceProseContractError(
            f"evidence card text must be trimmed and contain 1 to {MAX_CARD_TEXT_CHARACTERS} characters"
        )
    if (
        not isinstance(source_numbers, tuple)
        or not source_numbers
        or any(type(number) is not int or number < 1 for number in source_numbers)
        or len(source_numbers) != len(set(source_numbers))
    ):
        raise EvidenceProseContractError(
            "evidence card source_numbers must be unique positive integers"
        )
    if (
        not isinstance(requirement_ids, tuple)
        or any(
            not isinstance(requirement_id, str) or _IDENTIFIER_RE.fullmatch(requirement_id) is None
            for requirement_id in requirement_ids
        )
        or len(requirement_ids) != len(set(requirement_ids))
    ):
        raise EvidenceProseContractError(
            "evidence card requirement_ids must be unique valid identifiers"
        )


def _normalize_supported_mode(mode: ArchivistMode | str) -> ArchivistMode:
    try:
        selected_mode = mode if isinstance(mode, ArchivistMode) else ArchivistMode(mode)
    except (TypeError, ValueError) as exc:
        raise EvidenceProseContractError("unsupported reader prose mode") from exc
    if selected_mode not in SUPPORTED_PROSE_MODES:
        raise EvidenceProseContractError("unsupported reader prose mode")
    return selected_mode


def _render_cited_segment(text: str, source_numbers: Sequence[int]) -> str:
    terminal = text[-1] if text[-1] in ".!?" else "."
    claim = text[:-1].rstrip() if text[-1] in ".!?" else text
    citation = "[" + ", ".join(f"Source {number}" for number in source_numbers) + "]"
    return f"{claim} {citation}{terminal}"


def _without_automatic_retries(client: object) -> object:
    with_options = getattr(client, "with_options", None)
    return with_options(max_retries=0) if callable(with_options) else client


def _response_refused(response: object) -> bool:
    for item in getattr(response, "output", ()) or ():
        if getattr(item, "type", None) == "refusal":
            return True
        if any(
            getattr(part, "type", None) == "refusal"
            for part in (getattr(item, "content", ()) or ())
        ):
            return True
    return False


def _fallback_result(
    mode: ArchivistMode,
    failure_code: ProseFailureCode,
) -> EvidenceProseRenderResult:
    return EvidenceProseRenderResult(
        status=ProseRenderStatus.FALLBACK_REQUIRED,
        mode=mode,
        answer=None,
        segments=(),
        used_card_ids=(),
        used_source_numbers=(),
        failure_code=failure_code,
    )


__all__ = [
    "EVIDENCE_PROSE_INPUT_SCHEMA",
    "EVIDENCE_PROSE_OUTPUT_SCHEMA",
    "EVIDENCE_PROSE_INSTRUCTIONS",
    "EVIDENCE_PROSE_RENDERER_VERSION",
    "EDITORIAL_CUES",
    "EditorialCueDefinition",
    "EditorialCueId",
    "EvidenceCardLike",
    "EvidenceProseContractError",
    "EvidenceProseRenderResult",
    "EvidenceProseResponse",
    "EvidenceProseSegment",
    "ProseFailureCode",
    "ProseRenderStatus",
    "ProseSegmentKind",
    "READER_PROSE_SETTINGS",
    "build_evidence_prose_input",
    "build_evidence_prose_instructions",
    "evidence_prose_prompt_metadata",
    "generate_evidence_prose",
    "supported_prose_modes",
    "validate_and_render_evidence_prose",
]
