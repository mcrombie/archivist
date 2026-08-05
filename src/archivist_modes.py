from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from perspectives import (
    INTERPRETIVE_EXPANSION_RULES,
    INTERPRETIVE_GUARDRAILS,
    INTERPRETIVE_RESPONSE_RULES,
    AnswerVoice,
    HistoriographicalLens,
    Worldview,
    build_interpretive_prompt_block,
    normalize_answer_voice,
    normalize_historiographical_lens,
    normalize_worldview,
    requires_interpretive_expansion,
)


INFLUENCE_PROMPT_DIR = (
    Path(__file__).resolve().parent / "interpretive_prompts" / "influence_profiles"
)


class ArchivistMode(StrEnum):
    """Allowlisted reader-facing combinations of interpretation and appearance."""

    PROFESSIONAL = "professional"
    ESSENTIAL = "essential"
    FOREST = "forest"
    CROMB_COO_COO = "cromb_coo_coo"
    PRETTY_PINK_PRINCESS = "pretty_pink_princess"
    BALEFUL_BLACK_BARON = "baleful_black_baron"
    TIDAL_ARCHIVIST = "tidal_archivist"
    EMBER_AND_INK = "ember_and_ink"
    ILLUMINATED_CODEX = "illuminated_codex"
    COSMIC_ALMANAC = "cosmic_almanac"


@dataclass(frozen=True, slots=True)
class InfluenceProvenance:
    title: str
    creator: str | None
    source_identifier: str
    source_url: str | None
    source_sha256: str | None
    artifact_modified_at: str | None
    rights_note: str
    role: str


@dataclass(frozen=True, slots=True)
class InfluenceProfileDefinition:
    profile_id: str
    version: str
    label: str
    provenance: tuple[InfluenceProvenance, ...]
    prompt_path: Path | None


@dataclass(frozen=True, slots=True)
class ArchivistModeDefinition:
    mode_id: ArchivistMode
    version: str
    label: str
    description: str
    historiographical_lens: HistoriographicalLens
    voice: AnswerVoice
    worldview: Worldview
    influence_profile_id: str


INFLUENCE_PROFILES: dict[str, InfluenceProfileDefinition] = {
    "none": InfluenceProfileDefinition(
        profile_id="none",
        version="1",
        label="No additional influence",
        provenance=(),
        prompt_path=None,
    ),
    "professional_public_history": InfluenceProfileDefinition(
        profile_id="professional_public_history",
        version="1",
        label="Professional public history",
        provenance=(
            InfluenceProvenance(
                title="The Virginia Company Of London, 1606-1624",
                creator="Wesley Frank Craven",
                source_identifier="project-gutenberg:28555",
                source_url="https://www.gutenberg.org/ebooks/28555.epub3.images",
                source_sha256=("7b6475993d63a640a8fae1044d342dbcb9d71321649357c52a0424e484d2596c"),
                artifact_modified_at="2026-07-11T18:03:12Z",
                rights_note=(
                    "Project Gutenberg records public-domain status in the USA after reporting "
                    "that extensive research found no copyright renewal. The author died in "
                    "1981, so status outside the USA requires a separate check."
                ),
                role=(
                    "Institutional development, competing purposes, and the practical operation "
                    "of the Virginia Company."
                ),
            ),
            InfluenceProvenance(
                title="An Economic Interpretation of the Constitution of the United States",
                creator="Charles A. Beard",
                source_identifier="project-gutenberg:70677",
                source_url="https://www.gutenberg.org/ebooks/70677.epub3.images",
                source_sha256=("3359e7ef549af9281ffca2656aec82588ae1dc04017f05fdced4a5765e3ab16e"),
                artifact_modified_at="2026-07-28T15:16:10Z",
                rights_note=(
                    "Project Gutenberg records public-domain status in the USA; status outside "
                    "the USA requires a separate check."
                ),
                role=(
                    "Institutional political economy, material interests, and the difference "
                    "between formal design and practical effects."
                ),
            ),
            InfluenceProvenance(
                title=(
                    "The Suppression of the African Slave Trade to the United States of "
                    "America, 1638-1870"
                ),
                creator="W. E. B. Du Bois",
                source_identifier="project-gutenberg:17700",
                source_url="https://www.gutenberg.org/ebooks/17700.epub3.images",
                source_sha256=("08e428081e076e724cb91ba10229ed95ec66f53ef2e1d4e9c6875d3fda7a3b9b"),
                artifact_modified_at="2026-07-07T20:37:24Z",
                rights_note=(
                    "Project Gutenberg records public-domain status in the USA; status outside "
                    "the USA requires a separate check."
                ),
                role=(
                    "Racialized power, enforcement, political economy, and the gap between "
                    "declared policy and historical operation. Public domain in the USA."
                ),
            ),
        ),
        prompt_path=INFLUENCE_PROMPT_DIR / "professional_public_history.md",
    ),
    "dunsany_elfland": InfluenceProfileDefinition(
        profile_id="dunsany_elfland",
        version="1",
        label="Dunsany mythopoetic influence",
        provenance=(
            InfluenceProvenance(
                title="The King of Elfland's Daughter",
                creator="Lord Dunsany",
                source_identifier="project-gutenberg:61077",
                source_url="https://www.gutenberg.org/ebooks/61077.epub3.images",
                source_sha256=("b8a8a8cad9385000ae4154b61d9c8d4be645a4b346f7fe8aa580f77486cb80b4"),
                artifact_modified_at="2026-07-30T00:38:46Z",
                rights_note=(
                    "Project Gutenberg records public-domain status in the USA; status outside "
                    "the USA requires a separate check. The exact underlying print base edition "
                    "is not yet attributed with certainty."
                ),
                role=(
                    "Literary influence on cadence, imagery, and framing only; never a "
                    "historical source."
                ),
            ),
        ),
        prompt_path=INFLUENCE_PROMPT_DIR / "dunsany_elfland.md",
    ),
    "cromb_coo_coo_manuscript": InfluenceProfileDefinition(
        profile_id="cromb_coo_coo_manuscript",
        version="1",
        label="Cromb Coo Coo literary influence",
        provenance=(
            InfluenceProvenance(
                title="Journey through Cromb Coo Coo",
                creator=None,
                source_identifier=("owner-supplied:journey-through-cromb-coo-coo:2026-07-30"),
                source_url=None,
                source_sha256=("f67f9ed3f622583abe2fca090d73881ff86a7f801cea88034589c986509ece74"),
                artifact_modified_at="2026-07-30T10:05:30-04:00",
                rights_note=(
                    "Private owner-supplied manuscript; not redistributed. Reviewed locally "
                    "to derive a bounded literary influence profile."
                ),
                role="Literary/editorial framing only; never historical evidence.",
            ),
        ),
        prompt_path=INFLUENCE_PROMPT_DIR / "cromb_coo_coo.md",
    ),
    "rose_tinted_optimism": InfluenceProfileDefinition(
        profile_id="rose_tinted_optimism",
        version="1",
        label="Rose-tinted optimism",
        provenance=(),
        prompt_path=INFLUENCE_PROMPT_DIR / "pretty_pink_princess.md",
    ),
    "severe_tragic_history": InfluenceProfileDefinition(
        profile_id="severe_tragic_history",
        version="1",
        label="Severe tragic history",
        provenance=(),
        prompt_path=INFLUENCE_PROMPT_DIR / "baleful_black_baron.md",
    ),
    "moby_dick_maritime": InfluenceProfileDefinition(
        profile_id="moby_dick_maritime",
        version="1",
        label="Moby-Dick-informed maritime framing",
        provenance=(
            InfluenceProvenance(
                title="Moby-Dick; or, The Whale",
                creator="Herman Melville",
                source_identifier="project-gutenberg:15",
                source_url="https://www.gutenberg.org/ebooks/15.epub3.images",
                source_sha256=(
                    "8d76f75515a8e10b0ed0657275767f75b4b283177805a1c09c231840a0607d95"
                ),
                artifact_modified_at="2026-08-01T07:33:10Z",
                rights_note=(
                    "Project Gutenberg identifies this artifact as public domain in the USA, "
                    "describes ebook #15 as its highest-quality Moby-Dick transcription, and "
                    "ties it to the 1851 first American edition. Archivist does not redistribute "
                    "the EPUB; status outside the USA requires a separate check."
                ),
                role=(
                    "Maritime scale, moral pressure, uncertainty, and cadence only; never "
                    "historical evidence."
                ),
            ),
        ),
        prompt_path=INFLUENCE_PROMPT_DIR / "moby_dick_maritime.md",
    ),
    "realist_statecraft": InfluenceProfileDefinition(
        profile_id="realist_statecraft",
        version="1",
        label="Kissinger-associated realist statecraft",
        provenance=(
            InfluenceProvenance(
                title="Realist statecraft tradition associated with Henry Kissinger",
                creator=None,
                source_identifier="conceptual-profile:realist-statecraft:no-text-ingested",
                source_url=None,
                source_sha256=None,
                artifact_modified_at=None,
                rights_note=(
                    "No Henry Kissinger work was ingested, stored, quoted, paraphrased, or "
                    "used as evidence."
                ),
                role=(
                    "High-level attention to power, interests, leverage, institutions, and "
                    "strategic constraint only."
                ),
            ),
        ),
        prompt_path=INFLUENCE_PROMPT_DIR / "realist_statecraft.md",
    ),
    "modern_liberal_history": InfluenceProfileDefinition(
        profile_id="modern_liberal_history",
        version="1",
        label="Project-authored modern liberal history",
        provenance=(),
        prompt_path=INFLUENCE_PROMPT_DIR / "modern_liberal_history.md",
    ),
    "future_science_history": InfluenceProfileDefinition(
        profile_id="future_science_history",
        version="1",
        label="Project-authored future-science history",
        provenance=(),
        prompt_path=INFLUENCE_PROMPT_DIR / "future_science_history.md",
    ),
}


ARCHIVIST_MODES: dict[ArchivistMode, ArchivistModeDefinition] = {
    ArchivistMode.PROFESSIONAL: ArchivistModeDefinition(
        mode_id=ArchivistMode.PROFESSIONAL,
        version="1",
        label="Professional",
        description="Accessible, restrained public history for the public prototype.",
        historiographical_lens=HistoriographicalLens.EVIDENCE_FIRST,
        voice=AnswerVoice.PLAINSPOKEN,
        worldview=Worldview.SECULAR_HUMANIST,
        influence_profile_id="professional_public_history",
    ),
    ArchivistMode.ESSENTIAL: ArchivistModeDefinition(
        mode_id=ArchivistMode.ESSENTIAL,
        version="1",
        label="Essential",
        description="The unchanged evidence-first Archivist baseline.",
        historiographical_lens=HistoriographicalLens.EVIDENCE_FIRST,
        voice=AnswerVoice.SCHOLARLY,
        worldview=Worldview.NONE,
        influence_profile_id="none",
    ),
    ArchivistMode.FOREST: ArchivistModeDefinition(
        mode_id=ArchivistMode.FOREST,
        version="1",
        label="Mythical Forest Folio",
        description="A tragic, romantic reading with a bounded Dunsany literary influence.",
        historiographical_lens=HistoriographicalLens.TRAGIC,
        voice=AnswerVoice.ROMANTIC,
        worldview=Worldview.NONE,
        influence_profile_id="dunsany_elfland",
    ),
    ArchivistMode.CROMB_COO_COO: ArchivistModeDefinition(
        mode_id=ArchivistMode.CROMB_COO_COO,
        version="1",
        label="Cromb Coo Coo",
        description=(
            "A humane, mischievous reading attentive to contingency, eccentric actors, "
            "and the collision of grandeur with ordinary experience."
        ),
        historiographical_lens=HistoriographicalLens.EVIDENCE_FIRST,
        voice=AnswerVoice.ROMANTIC,
        worldview=Worldview.SECULAR_HUMANIST,
        influence_profile_id="cromb_coo_coo_manuscript",
    ),
    ArchivistMode.PRETTY_PINK_PRINCESS: ArchivistModeDefinition(
        mode_id=ArchivistMode.PRETTY_PINK_PRINCESS,
        version="1",
        label="Pretty Pink Princess",
        description=(
            "A strongly optimistic, rose-tinted reading that never falsifies or omits harm."
        ),
        historiographical_lens=HistoriographicalLens.TRIUMPHALIST,
        voice=AnswerVoice.ROMANTIC,
        worldview=Worldview.SECULAR_HUMANIST,
        influence_profile_id="rose_tinted_optimism",
    ),
    ArchivistMode.BALEFUL_BLACK_BARON: ArchivistModeDefinition(
        mode_id=ArchivistMode.BALEFUL_BLACK_BARON,
        version="1",
        label="Baleful Black Baron",
        description="A severe tragic reading centered on costs, coercion, and loss.",
        historiographical_lens=HistoriographicalLens.TRAGIC,
        voice=AnswerVoice.ROMANTIC,
        worldview=Worldview.NONE,
        influence_profile_id="severe_tragic_history",
    ),
    ArchivistMode.TIDAL_ARCHIVIST: ArchivistModeDefinition(
        mode_id=ArchivistMode.TIDAL_ARCHIVIST,
        version="1",
        label="Tidal Archivist",
        description=(
            "A Moby-Dick-informed maritime reading of scale, pressure, command, and uncertainty."
        ),
        historiographical_lens=HistoriographicalLens.EVIDENCE_FIRST,
        voice=AnswerVoice.ROMANTIC,
        worldview=Worldview.NONE,
        influence_profile_id="moby_dick_maritime",
    ),
    ArchivistMode.EMBER_AND_INK: ArchivistModeDefinition(
        mode_id=ArchivistMode.EMBER_AND_INK,
        version="1",
        label="Ember & Ink",
        description=(
            "A realist statecraft reading associated with Henry Kissinger at the level of "
            "tradition, without using his works."
        ),
        historiographical_lens=HistoriographicalLens.EVIDENCE_FIRST,
        voice=AnswerVoice.PLAINSPOKEN,
        worldview=Worldview.ENLIGHTENMENT_RATIONALIST,
        influence_profile_id="realist_statecraft",
    ),
    ArchivistMode.ILLUMINATED_CODEX: ArchivistModeDefinition(
        mode_id=ArchivistMode.ILLUMINATED_CODEX,
        version="1",
        label="Illuminated Codex",
        description=(
            "A modern liberal-history reading of rights, pluralism, accountable institutions, "
            "and contested reform."
        ),
        historiographical_lens=HistoriographicalLens.EVIDENCE_FIRST,
        voice=AnswerVoice.SCHOLARLY,
        worldview=Worldview.SECULAR_HUMANIST,
        influence_profile_id="modern_liberal_history",
    ),
    ArchivistMode.COSMIC_ALMANAC: ArchivistModeDefinition(
        mode_id=ArchivistMode.COSMIC_ALMANAC,
        version="1",
        label="Cosmic Almanac",
        description=(
            "A future-science historical reading of systems, path dependence, uncertainty, "
            "and the futures opened or constrained by past choices."
        ),
        historiographical_lens=HistoriographicalLens.EVIDENCE_FIRST,
        voice=AnswerVoice.SCHOLARLY,
        worldview=Worldview.ENLIGHTENMENT_RATIONALIST,
        influence_profile_id="future_science_history",
    ),
}


def normalize_archivist_mode(mode: ArchivistMode | str) -> ArchivistMode:
    if isinstance(mode, ArchivistMode):
        return mode
    return ArchivistMode(mode)


def archivist_mode_definition(
    mode: ArchivistMode | str,
) -> ArchivistModeDefinition:
    return ARCHIVIST_MODES[normalize_archivist_mode(mode)]


def influence_profile_definition(
    mode: ArchivistMode | str,
) -> InfluenceProfileDefinition:
    definition = archivist_mode_definition(mode)
    return INFLUENCE_PROFILES[definition.influence_profile_id]


def settings_for_archivist_mode(
    mode: ArchivistMode | str,
) -> tuple[HistoriographicalLens, AnswerVoice, Worldview]:
    definition = archivist_mode_definition(mode)
    return (
        definition.historiographical_lens,
        definition.voice,
        definition.worldview,
    )


def resolve_archivist_mode_settings(
    mode: ArchivistMode | str = ArchivistMode.ESSENTIAL,
    historiographical_lens: HistoriographicalLens | str | None = None,
    voice: AnswerVoice | str | None = None,
    worldview: Worldview | str | None = None,
) -> tuple[ArchivistMode, HistoriographicalLens, AnswerVoice, Worldview]:
    selected_mode = normalize_archivist_mode(mode)
    default_lens, default_voice, default_worldview = settings_for_archivist_mode(selected_mode)
    return (
        selected_mode,
        (
            normalize_historiographical_lens(historiographical_lens)
            if historiographical_lens is not None
            else default_lens
        ),
        normalize_answer_voice(voice) if voice is not None else default_voice,
        normalize_worldview(worldview) if worldview is not None else default_worldview,
    )


def load_influence_profile_prompt(mode: ArchivistMode | str) -> str:
    profile = influence_profile_definition(mode)
    if profile.prompt_path is None:
        return ""
    prompt = profile.prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise RuntimeError(f"Influence profile prompt is empty: {profile.prompt_path.name}")
    return prompt


def build_archivist_mode_prompt_block(
    historiographical_lens: HistoriographicalLens | str | None = None,
    voice: AnswerVoice | str | None = None,
    worldview: Worldview | str | None = None,
    *,
    archivist_mode: ArchivistMode | str = ArchivistMode.ESSENTIAL,
) -> str:
    """Build generation-only framing while leaving Essential byte-identical.

    The returned block is inserted after retrieval has finished. Influence
    profiles therefore cannot affect query planning, ranking, or source admission.
    """

    selected_mode, lens, selected_voice, selected_worldview = resolve_archivist_mode_settings(
        archivist_mode,
        historiographical_lens,
        voice,
        worldview,
    )
    base = build_interpretive_prompt_block(lens, selected_voice, selected_worldview)
    influence = load_influence_profile_prompt(selected_mode)
    if not influence:
        return base

    influence_section = (
        "Selected literary/editorial influence profile "
        f"({influence_profile_definition(selected_mode).profile_id}):\n{influence}"
    )
    if base:
        return f"{base}\n\n{influence_section}"

    expansion = (
        f"{INTERPRETIVE_EXPANSION_RULES}\n"
        if requires_interpretive_expansion(lens, selected_worldview)
        else ""
    )
    return (
        f"{INTERPRETIVE_GUARDRAILS}\n{INTERPRETIVE_RESPONSE_RULES}\n{expansion}{influence_section}"
    )


def archivist_mode_metadata(mode: ArchivistMode | str) -> dict[str, object]:
    definition = archivist_mode_definition(mode)
    profile = influence_profile_definition(mode)
    prompt = load_influence_profile_prompt(mode)
    return {
        "archivist_mode": definition.mode_id.value,
        "archivist_mode_version": definition.version,
        "influence_profile_id": profile.profile_id,
        "influence_profile_version": profile.version,
        "influence_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "influence_provenance": [
            {
                "title": item.title,
                "creator": item.creator,
                "source_identifier": item.source_identifier,
                "source_url": item.source_url,
                "source_sha256": item.source_sha256,
                "artifact_modified_at": item.artifact_modified_at,
                "rights_note": item.rights_note,
                "role": item.role,
            }
            for item in profile.provenance
        ],
    }


__all__ = [
    "ARCHIVIST_MODES",
    "INFLUENCE_PROFILES",
    "ArchivistMode",
    "ArchivistModeDefinition",
    "InfluenceProfileDefinition",
    "InfluenceProvenance",
    "archivist_mode_definition",
    "archivist_mode_metadata",
    "build_archivist_mode_prompt_block",
    "influence_profile_definition",
    "load_influence_profile_prompt",
    "normalize_archivist_mode",
    "resolve_archivist_mode_settings",
    "settings_for_archivist_mode",
]
