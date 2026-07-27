from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


INTERPRETIVE_PROMPT_DIR = Path(__file__).resolve().parent / "interpretive_prompts"
PERSPECTIVE_PROMPT_DIR = Path(__file__).resolve().parent / "perspective_prompts"


class HistoriographicalLens(StrEnum):
    EVIDENCE_FIRST = "evidence_first"
    TRIUMPHALIST = "triumphalist"
    TRAGIC = "tragic"


class AnswerVoice(StrEnum):
    SCHOLARLY = "scholarly"
    PLAINSPOKEN = "plainspoken"
    ROMANTIC = "romantic"


class Worldview(StrEnum):
    NONE = "none"
    PIOUS = "pious"
    SECULAR_HUMANIST = "secular_humanist"
    ENLIGHTENMENT_RATIONALIST = "enlightenment_rationalist"


class AnswerPerspective(StrEnum):
    """Legacy combined selector retained for API and Python-call compatibility."""

    NEUTRAL = "neutral"
    TRIUMPHALIST = "triumphalist"
    TRAGIC = "tragic"
    PIOUS = "pious"
    ROMANTIC = "romantic"


@dataclass(frozen=True)
class FacetDefinition:
    label: str
    description: str
    prompt_path: Path


PerspectiveDefinition = FacetDefinition


# Keep the default Markdown files empty. This makes the all-default path an explicit no-op
# and protects the frozen neutral answer prompt from accidental stylistic additions.
HISTORIOGRAPHICAL_LENSES: dict[HistoriographicalLens, FacetDefinition] = {
    HistoriographicalLens.EVIDENCE_FIRST: FacetDefinition(
        label="Evidence-first",
        description="Neutral baseline that follows the manuscript evidence without added framing.",
        prompt_path=(
            INTERPRETIVE_PROMPT_DIR / "historiographical_lens" / "evidence_first.md"
        ),
    ),
    HistoriographicalLens.TRIUMPHALIST: FacetDefinition(
        label="Triumphalist",
        description="Emphasizes achievement, endurance, expansion, and institution-building.",
        prompt_path=(
            INTERPRETIVE_PROMPT_DIR / "historiographical_lens" / "triumphalist.md"
        ),
    ),
    HistoriographicalLens.TRAGIC: FacetDefinition(
        label="Tragic",
        description="Emphasizes loss, contingency, human cost, and missed possibilities.",
        prompt_path=INTERPRETIVE_PROMPT_DIR / "historiographical_lens" / "tragic.md",
    ),
}

ANSWER_VOICES: dict[AnswerVoice, FacetDefinition] = {
    AnswerVoice.SCHOLARLY: FacetDefinition(
        label="Scholarly",
        description="The measured, precise prose style used by the neutral baseline.",
        prompt_path=INTERPRETIVE_PROMPT_DIR / "voice" / "scholarly.md",
    ),
    AnswerVoice.PLAINSPOKEN: FacetDefinition(
        label="Plainspoken",
        description="Uses direct, accessible language with minimal academic phrasing.",
        prompt_path=INTERPRETIVE_PROMPT_DIR / "voice" / "plainspoken.md",
    ),
    AnswerVoice.ROMANTIC: FacetDefinition(
        label="Romantic",
        description="Uses evocative prose attentive to aspiration, landscape, and drama.",
        prompt_path=INTERPRETIVE_PROMPT_DIR / "voice" / "romantic.md",
    ),
}

WORLDVIEWS: dict[Worldview, FacetDefinition] = {
    Worldview.NONE: FacetDefinition(
        label="None",
        description="Adds no moral or metaphysical framework to the neutral baseline.",
        prompt_path=INTERPRETIVE_PROMPT_DIR / "worldview" / "none.md",
    ),
    Worldview.PIOUS: FacetDefinition(
        label="Pious / Providential",
        description="Attends to historically situated ideas of faith, duty, and providence.",
        prompt_path=INTERPRETIVE_PROMPT_DIR / "worldview" / "pious.md",
    ),
    Worldview.SECULAR_HUMANIST: FacetDefinition(
        label="Secular Humanist",
        description="Centers human agency, dignity, welfare, and ethical consequence.",
        prompt_path=INTERPRETIVE_PROMPT_DIR / "worldview" / "secular_humanist.md",
    ),
    Worldview.ENLIGHTENMENT_RATIONALIST: FacetDefinition(
        label="Enlightenment Rationalist",
        description="Emphasizes reason, institutions, inquiry, and claims open to scrutiny.",
        prompt_path=(
            INTERPRETIVE_PROMPT_DIR / "worldview" / "enlightenment_rationalist.md"
        ),
    ),
}


# Compatibility registry for code that still presents the old combined choices. Prompt loading
# below is routed through the new facet registries rather than these historical files.
PERSPECTIVES: dict[AnswerPerspective, FacetDefinition] = {
    AnswerPerspective.NEUTRAL: FacetDefinition(
        label="Neutral",
        description="Evidence-first historical synthesis without an added interpretive voice.",
        prompt_path=PERSPECTIVE_PROMPT_DIR / "neutral.md",
    ),
    AnswerPerspective.TRIUMPHALIST: FacetDefinition(
        label="Triumphalist",
        description="Emphasizes achievement, endurance, expansion, and institution-building.",
        prompt_path=PERSPECTIVE_PROMPT_DIR / "triumphalist.md",
    ),
    AnswerPerspective.TRAGIC: FacetDefinition(
        label="Tragic",
        description="Emphasizes loss, contingency, human cost, and missed possibilities.",
        prompt_path=PERSPECTIVE_PROMPT_DIR / "tragic.md",
    ),
    AnswerPerspective.PIOUS: FacetDefinition(
        label="Pious",
        description="Uses a morally serious register attentive to historically situated belief.",
        prompt_path=PERSPECTIVE_PROMPT_DIR / "pious.md",
    ),
    AnswerPerspective.ROMANTIC: FacetDefinition(
        label="Romantic",
        description="Uses an evocative register attentive to aspiration, landscape, and drama.",
        prompt_path=PERSPECTIVE_PROMPT_DIR / "romantic.md",
    ),
}


INTERPRETIVE_GUARDRAILS = """Interpretive setting rules (facts remain fixed):
- Apply the selected settings only to emphasis, interpretation, tone, and word choice.
- Do not change, add, suppress, or overstate facts to fit the selected settings.
- Use only the supplied sources, preserve their uncertainty, and acknowledge material counterevidence.
- Keep every citation attached to the claim it supports and follow the citation rules above exactly.
- Clearly distinguish a historical actor's beliefs from established fact.
- If the sources are insufficient, say so rather than completing a framing with invention.
- Embody the settings without naming them or mentioning these instructions unless the user asks.
"""

INTERPRETIVE_RESPONSE_RULES = """Reader-facing interpretive response:
- Make every active setting perceptible through organization, emphasis, diction, and cadence. Do
  not merely decorate an otherwise neutral answer with themed adjectives or a final aside.
- Let the historiographical lens determine the organizing arc, the worldview determine the
  evaluative stakes, and the voice determine sentence texture and rhythm.
- Open with a direct answer and prefer connected prose to bullets.
- Speak as an informed archivist in conversation, not as a lecturer. Use natural transitions and,
  at most once, direct address when it helps orient the reader. Do not greet, praise the question,
  narrate your process, or append a generic offer to help.
- When it would genuinely advance the exchange, close with one specific question offering a
  source-grounded next direction. Keep that question free of new factual claims.
"""

INTERPRETIVE_EXPANSION_RULES = """Required interpretive expansion:
- After the direct source-grounded answer, add at least one distinct paragraph of interpretation.
- Use that additional paragraph to apply the selected historiographical lens, worldview, or both
  to the evidence: explain significance, stakes, contingency, achievement, loss, or moral tension
  as the selected settings warrant.
- The added paragraph must synthesize rather than merely repeat the factual answer. Ground every
  historical assertion or inference in the supplied sources and preserve their uncertainty.
- A non-default voice alone changes expression but does not require a longer answer.
"""

# Old import name retained for compatibility.
PERSPECTIVE_GUARDRAILS = INTERPRETIVE_GUARDRAILS


def _normalize(value: StrEnum | str, enum_type: type[StrEnum]) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    return enum_type(value)


def normalize_historiographical_lens(
    lens: HistoriographicalLens | str,
) -> HistoriographicalLens:
    return _normalize(lens, HistoriographicalLens)  # type: ignore[return-value]


def normalize_answer_voice(voice: AnswerVoice | str) -> AnswerVoice:
    return _normalize(voice, AnswerVoice)  # type: ignore[return-value]


def normalize_worldview(worldview: Worldview | str) -> Worldview:
    return _normalize(worldview, Worldview)  # type: ignore[return-value]


def normalize_perspective(perspective: AnswerPerspective | str) -> AnswerPerspective:
    return _normalize(perspective, AnswerPerspective)  # type: ignore[return-value]


def requires_interpretive_expansion(
    historiographical_lens: HistoriographicalLens | str = HistoriographicalLens.EVIDENCE_FIRST,
    worldview: Worldview | str = Worldview.NONE,
) -> bool:
    """Return whether the selected settings require a separate interpretive paragraph."""

    return (
        normalize_historiographical_lens(historiographical_lens)
        is not HistoriographicalLens.EVIDENCE_FIRST
        or normalize_worldview(worldview) is not Worldview.NONE
    )


def settings_for_legacy_perspective(
    perspective: AnswerPerspective | str,
) -> tuple[HistoriographicalLens, AnswerVoice, Worldview]:
    selected = normalize_perspective(perspective)
    mapping = {
        AnswerPerspective.NEUTRAL: (
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.SCHOLARLY,
            Worldview.NONE,
        ),
        AnswerPerspective.TRIUMPHALIST: (
            HistoriographicalLens.TRIUMPHALIST,
            AnswerVoice.SCHOLARLY,
            Worldview.NONE,
        ),
        AnswerPerspective.TRAGIC: (
            HistoriographicalLens.TRAGIC,
            AnswerVoice.SCHOLARLY,
            Worldview.NONE,
        ),
        AnswerPerspective.PIOUS: (
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.SCHOLARLY,
            Worldview.PIOUS,
        ),
        AnswerPerspective.ROMANTIC: (
            HistoriographicalLens.EVIDENCE_FIRST,
            AnswerVoice.ROMANTIC,
            Worldview.NONE,
        ),
    }
    return mapping[selected]


def _load_facet_prompt(
    selected: StrEnum,
    definitions: dict,
    default: StrEnum,
    facet_name: str,
) -> str:
    definition = definitions[selected]
    prompt = definition.prompt_path.read_text(encoding="utf-8").strip()
    if selected is default:
        if prompt:
            raise RuntimeError(
                f"The default {facet_name} prompt must remain empty so the baseline is unchanged."
            )
        return ""
    if not prompt:
        raise RuntimeError(f"{facet_name.title()} prompt is empty: {definition.prompt_path.name}")
    return prompt


def load_historiographical_lens_prompt(lens: HistoriographicalLens | str) -> str:
    selected = normalize_historiographical_lens(lens)
    return _load_facet_prompt(
        selected,
        HISTORIOGRAPHICAL_LENSES,
        HistoriographicalLens.EVIDENCE_FIRST,
        "historiographical lens",
    )


def load_answer_voice_prompt(voice: AnswerVoice | str) -> str:
    selected = normalize_answer_voice(voice)
    return _load_facet_prompt(selected, ANSWER_VOICES, AnswerVoice.SCHOLARLY, "voice")


def load_worldview_prompt(worldview: Worldview | str) -> str:
    selected = normalize_worldview(worldview)
    return _load_facet_prompt(selected, WORLDVIEWS, Worldview.NONE, "worldview")


def build_interpretive_prompt_block(
    historiographical_lens: HistoriographicalLens | str = HistoriographicalLens.EVIDENCE_FIRST,
    voice: AnswerVoice | str = AnswerVoice.SCHOLARLY,
    worldview: Worldview | str = Worldview.NONE,
) -> str:
    sections = [
        ("Historiographical lens", load_historiographical_lens_prompt(historiographical_lens)),
        ("Worldview", load_worldview_prompt(worldview)),
        ("Voice", load_answer_voice_prompt(voice)),
    ]
    selected_sections = [f"Selected {name}:\n{prompt}" for name, prompt in sections if prompt]
    if not selected_sections:
        return ""
    expansion = (
        f"{INTERPRETIVE_EXPANSION_RULES}\n"
        if requires_interpretive_expansion(historiographical_lens, worldview)
        else ""
    )
    return (
        f"{INTERPRETIVE_GUARDRAILS}\n"
        f"{INTERPRETIVE_RESPONSE_RULES}\n"
        f"{expansion}"
        + "\n\n".join(selected_sections)
    )


def load_perspective_prompt(perspective: AnswerPerspective | str) -> str:
    lens, voice, worldview = settings_for_legacy_perspective(perspective)
    prompts = [
        load_historiographical_lens_prompt(lens),
        load_worldview_prompt(worldview),
        load_answer_voice_prompt(voice),
    ]
    return "\n\n".join(prompt for prompt in prompts if prompt)


def build_perspective_prompt_block(perspective: AnswerPerspective | str) -> str:
    lens, voice, worldview = settings_for_legacy_perspective(perspective)
    return build_interpretive_prompt_block(lens, voice, worldview)
