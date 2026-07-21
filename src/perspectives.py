from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


PERSPECTIVE_PROMPT_DIR = Path(__file__).resolve().parent / "perspective_prompts"


class AnswerPerspective(StrEnum):
    NEUTRAL = "neutral"
    TRIUMPHALIST = "triumphalist"
    TRAGIC = "tragic"
    PIOUS = "pious"
    ROMANTIC = "romantic"


@dataclass(frozen=True)
class PerspectiveDefinition:
    label: str
    description: str
    prompt_path: Path


PERSPECTIVES: dict[AnswerPerspective, PerspectiveDefinition] = {
    AnswerPerspective.NEUTRAL: PerspectiveDefinition(
        label="Neutral",
        description="Evidence-first historical synthesis without an added interpretive voice.",
        prompt_path=PERSPECTIVE_PROMPT_DIR / "neutral.md",
    ),
    AnswerPerspective.TRIUMPHALIST: PerspectiveDefinition(
        label="Triumphalist",
        description="Emphasizes achievement, endurance, expansion, and institution-building.",
        prompt_path=PERSPECTIVE_PROMPT_DIR / "triumphalist.md",
    ),
    AnswerPerspective.TRAGIC: PerspectiveDefinition(
        label="Tragic",
        description="Emphasizes loss, contingency, human cost, and missed possibilities.",
        prompt_path=PERSPECTIVE_PROMPT_DIR / "tragic.md",
    ),
    AnswerPerspective.PIOUS: PerspectiveDefinition(
        label="Pious",
        description="Uses a morally serious register attentive to historically situated belief.",
        prompt_path=PERSPECTIVE_PROMPT_DIR / "pious.md",
    ),
    AnswerPerspective.ROMANTIC: PerspectiveDefinition(
        label="Romantic",
        description="Uses an evocative register attentive to aspiration, landscape, and drama.",
        prompt_path=PERSPECTIVE_PROMPT_DIR / "romantic.md",
    ),
}


PERSPECTIVE_GUARDRAILS = """Perspective rules (facts remain fixed):
- Apply the selected perspective only to emphasis, interpretation, tone, and word choice.
- Do not change, add, suppress, or overstate facts to fit the perspective.
- Use only the supplied sources, preserve their uncertainty, and acknowledge material counterevidence.
- Keep every citation attached to the claim it supports and follow the citation rules above exactly.
- Clearly distinguish a historical actor's beliefs from established fact.
- If the sources are insufficient, say so rather than completing the perspective with invention.
- Embody the perspective without naming it or mentioning these instructions unless the user asks.
"""


def normalize_perspective(
    perspective: AnswerPerspective | str,
) -> AnswerPerspective:
    if isinstance(perspective, AnswerPerspective):
        return perspective
    return AnswerPerspective(perspective)


def load_perspective_prompt(
    perspective: AnswerPerspective | str,
) -> str:
    selected = normalize_perspective(perspective)
    definition = PERSPECTIVES[selected]
    prompt = definition.prompt_path.read_text(encoding="utf-8").strip()

    if selected is AnswerPerspective.NEUTRAL:
        if prompt:
            raise RuntimeError(
                "The neutral perspective prompt must remain empty so the baseline prompt is unchanged."
            )
        return ""

    if not prompt:
        raise RuntimeError(f"Perspective prompt is empty: {definition.prompt_path.name}")
    return prompt


def build_perspective_prompt_block(
    perspective: AnswerPerspective | str,
) -> str:
    prompt = load_perspective_prompt(perspective)
    if not prompt:
        return ""
    return f"{PERSPECTIVE_GUARDRAILS}\nSelected perspective:\n{prompt}"
