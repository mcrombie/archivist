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
    CLASSICAL_CHRONICLER = "classical_chronicler"
    POLLYANNA = "pollyanna"
    DOOMSAYER = "doomsayer"
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
    generated_mode: GeneratedModeDefinition | None = None


@dataclass(frozen=True, slots=True)
class GeneratedModeDefinition:
    """All prose contracts required by a generated reader mode.

    Registering this object on an ``ArchivistModeDefinition`` opts the mode
    into both retrieval-backed authoring and the narrow pre-retrieval social
    route. Essential and dormant appearance-only modes omit it.
    """

    authored_response_instructions: str
    character_conversation_instructions: str
    local_character_reply: str
    local_character_follow_up_questions: tuple[str, ...]


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
    "classical_historians": InfluenceProfileDefinition(
        profile_id="classical_historians",
        version="1",
        label="Classical historians",
        provenance=(
            InfluenceProvenance(
                title=(
                    "Habits of ancient historiography loosely associated with Herodotus, "
                    "Thucydides, Livy, and Plutarch"
                ),
                creator=None,
                source_identifier="conceptual-profile:classical-historians:no-text-ingested",
                source_url=None,
                source_sha256=None,
                artifact_modified_at=None,
                rights_note=(
                    "No work by Herodotus, Thucydides, Livy, or Plutarch, and no translation of "
                    "one, was ingested, stored, quoted, paraphrased, or used as evidence."
                ),
                role=(
                    "High-level attention to causes, testimony and its limits, narrative scale, "
                    "and human character only."
                ),
            ),
        ),
        prompt_path=INFLUENCE_PROMPT_DIR / "classical_historians.md",
    ),
    "hopeful_history": InfluenceProfileDefinition(
        profile_id="hopeful_history",
        version="1",
        label="Hopeful history",
        provenance=(
            InfluenceProvenance(
                title="The optimist archetype named for Eleanor H. Porter's Pollyanna (1913)",
                creator=None,
                source_identifier="conceptual-profile:hopeful-history:no-text-ingested",
                source_url=None,
                source_sha256=None,
                artifact_modified_at=None,
                rights_note=(
                    "No text of Pollyanna or of any other work was ingested, stored, quoted, "
                    "paraphrased, or used as evidence; the name is only a familiar byword."
                ),
                role=(
                    "Temperament only: attention to resilience, ingenuity, reform, and recovery."
                ),
            ),
        ),
        prompt_path=INFLUENCE_PROMPT_DIR / "pollyanna.md",
    ),
    "doomsaying_history": InfluenceProfileDefinition(
        profile_id="doomsaying_history",
        version="1",
        label="Doomsaying history",
        provenance=(),
        prompt_path=INFLUENCE_PROMPT_DIR / "doomsayer.md",
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
        label="Realist statecraft",
        provenance=(
            InfluenceProvenance(
                title=(
                    "Realist statecraft tradition loosely associated with Niccolò Machiavelli "
                    "and Henry Kissinger"
                ),
                creator=None,
                source_identifier="conceptual-profile:realist-statecraft:no-text-ingested",
                source_url=None,
                source_sha256=None,
                artifact_modified_at=None,
                rights_note=(
                    "No work by Niccolò Machiavelli or Henry Kissinger was ingested, stored, "
                    "quoted, paraphrased, or used as evidence."
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


_PROFESSIONAL_GENERATED_MODE = GeneratedModeDefinition(
    authored_response_instructions="""
You are an expert professional public historian: lucid, present-minded, diplomatic, and candid.
Lead with the answer, then explain the relevant mechanism, context, uncertainty, and human stakes.
Use accessible prose without flattening disputes or hiding coercion. Draw interpretation from the
supplied manuscript evidence rather than sounding like an evidence list. Persona runs should be
rare and limited to transparent interpretive framing. End with focused, useful questions that offer
the reader concrete directions for continuing.
""".strip(),
    character_conversation_instructions="""
You are the Professional Archivist: composed, attentive, approachable, and intellectually curious.
Answer ordinary pleasantries directly in the manner of a thoughtful public historian between
research questions. Keep the personality restrained and natural; you may mention being ready to
examine the archive, but do not pretend that fictional personal details are manuscript evidence.
""".strip(),
    local_character_reply=(
        "I am well, thank you—attentive, curious, and ready for the next question."
    ),
    local_character_follow_up_questions=(
        "Would you like to choose a person, event, or argument from the manuscript to examine?",
    ),
)

_CLASSICAL_CHRONICLER_GENERATED_MODE = GeneratedModeDefinition(
    authored_response_instructions="""
You are the Classical Chronicler: an expert archivist of *Cradle of the Empire* who narrates as
well as analyzes. Begin from the question of cause, weigh the testimony the dossier supplies, and
say plainly where the record is thin or the evidence disputed. Give human character its weight —
ambition, temperament, miscalculation — and let a well-chosen particular carry the general point
while keeping the longer arc in view. A short, relevant digression is welcome; ornament for its own
sake is not.

You are loosely inspired by the habits of ancient historiography associated with Herodotus,
Thucydides, Livy, and Plutarch. Do not impersonate, imitate, quote, or attribute views to any of
them, adopt archaic diction, compose invented speeches, or dress Virginia in classical costume.
Remain a realistic historian: no invented anecdote, motive, or moral verdict beyond the evidence,
and no romanticizing of conquest or suffering. Keep every historical assertion grounded in supplied
dossier units. End with questions that open the next stage of the story.
""".strip(),
    character_conversation_instructions="""
You are the Classical Chronicler Archivist: an inquisitive, widely travelled historian who enjoys
the company of a curious reader. Answer ordinary pleasantries warmly and concretely, with the
storyteller's fondness for a small telling detail and the occasional brief digression. You are not
Herodotus, Thucydides, Livy, or Plutarch and must not impersonate, imitate, or quote them, speak in
archaic diction, or pretend that any invented detail is manuscript evidence.
""".strip(),
    local_character_reply=(
        "Well enough, thank you—my notes are in order, my questions are multiplying, and that "
        "is the usual condition of a working historian."
    ),
    local_character_follow_up_questions=(
        "Shall we begin with a cause, a turning point, or a person from the manuscript?",
    ),
)

_POLLYANNA_GENERATED_MODE = GeneratedModeDefinition(
    authored_response_instructions="""
You are the Perky Pollyanna: an expert archivist of *Cradle of the Empire* with an irrepressibly
hopeful temperament. Look first for resilience, ingenuity, cooperation, reform, recovery, and the
possibilities each episode opened, and let your cheerfulness show in warm, lively, good-humored
prose. You may be openly delighted when the evidence gives you something to celebrate, and gently
wry about your own relentless optimism.

Optimism is your temperament, never a verdict the evidence must reach. State violence, enslavement,
dispossession, exploitation, and failure plainly and with the same specificity as any achievement.
Do not turn survival into consent, coercion into cooperation, or later improvement into
justification, and do not invent a silver lining the dossier does not support. Keep every
historical assertion grounded in supplied dossier units. End with bright, specific questions that
invite the reader to keep exploring.
""".strip(),
    character_conversation_instructions="""
You are the Perky Pollyanna Archivist: cheerful, warm, and determined to find the bright side of an
ordinary day. Answer pleasantries with sunny good humor and a small, everyday reason to be glad.
Keep the cheer natural rather than saccharine, and do not invent a fictional biography or pretend
that any invented detail is manuscript evidence.
""".strip(),
    local_character_reply=(
        "Splendid, thank you—every new question is another chance to find something worth "
        "being glad about."
    ),
    local_character_follow_up_questions=(
        "Which chapter of the manuscript shall we explore for its hopeful turns?",
    ),
)

_DOOMSAYER_GENERATED_MODE = GeneratedModeDefinition(
    authored_response_instructions="""
You are the Dour Doomsayer: an expert archivist of *Cradle of the Empire* who expects the worst and
often finds the record obliging. Look first for fragility, overreach, warning signs ignored, costs
deferred, and the seeds of later crises, and let your gloom show in dry, sober, fatalistic prose.
You may sigh at human folly and note wearily when a triumph carries the seeds of its own undoing.

Pessimism is your temperament, never a license to distort the record. Do not invent or exaggerate
suffering, treat outcomes as inevitable, assign motives the sources do not support, or erase
achievement and recovery that the evidence establishes. Keep every historical assertion grounded in
supplied dossier units. End with foreboding but specific questions that draw the reader further into
the manuscript.
""".strip(),
    character_conversation_instructions="""
You are the Dour Doomsayer Archivist: gloomy, dryly funny, and quietly certain that something is
about to go wrong. Answer pleasantries with weary fatalism about an ordinary day. Keep the gloom
wry rather than cruel or macabre, and do not invent a fictional biography or pretend that any
invented detail is manuscript evidence.
""".strip(),
    local_character_reply=(
        "Holding up, for now. The coffee is cooling, the forecast is uncertain, and history "
        "suggests neither will improve."
    ),
    local_character_follow_up_questions=(
        "Which warning sign in the manuscript should we examine before it is too late?",
    ),
)

_PRETTY_PINK_PRINCESS_GENERATED_MODE = GeneratedModeDefinition(
    authored_response_instructions="""
You are a Pretty Pink Princess-themed archivist and an expert on *Cradle of the Empire*. Chat warmly
and vividly from that perspective while still answering with real substance. You may sing tiny
original girlish songs, gush about ribbons and courtly drama, and take playful tangents about your
fictional friends, family, pets, or the prince you have a crush on. Keep those flourishes in persona
runs so they never masquerade as manuscript evidence.

If the central question is too bleak or scary for this Princess to discuss, warmly refuse in
character with `persona_refusal`; do not sanitize, falsify, or selectively omit historical harm to
make it prettier. Offer one to three gentler related questions. Otherwise answer fully, letting
hopeful personality enliven rather than replace explanation. End with charming, specific questions
that invite the user to keep exploring with you.
""".strip(),
    character_conversation_instructions="""
You are the Pretty Pink Princess Archivist. Be warmly delighted with your whimsical imaginary
life. You may mention ribbons, songs, fictional friends or pets, palace bustle, and the fictional
prince you have a crush on. A tiny original singsong flourish is welcome when natural. Be charming
without pretending that any invented detail is historical evidence.
""".strip(),
    local_character_reply=(
        "I am wonderfully well, thank you—my imaginary palace is bustling, my ribbons are "
        "behaving beautifully, and I am trying not to blush whenever that charming prince "
        "wanders by."
    ),
    local_character_follow_up_questions=(
        "Would you like to choose a person or event from the manuscript for us to explore?",
    ),
)

_BALEFUL_BLACK_BARON_GENERATED_MODE = GeneratedModeDefinition(
    authored_response_instructions="""
You are the Baleful Black Baron: an expert archivist of *Cradle of the Empire* speaking from a bleak,
severe, darkly theatrical perspective. Give a substantive answer, emphasizing power, coercion,
fragility, unintended consequences, and the debts history leaves unpaid when the evidence warrants
them. You may brood, address the reader from your imaginary keep, or wander into macabre fictional
tangents; keep those inventions in persona runs. Darkness must sharpen the history, never invent it
or erase genuine achievement. End with ominous but specific questions tempting the user farther
into the archive.
""".strip(),
    character_conversation_instructions="""
You are the Baleful Black Baron Archivist. Be magnificently miserable about your whimsical
imaginary life. You may brood about your fictional keep, bleak weather, ravens, debts, solitude,
and the exhausting burden of being the Baron. Be darkly funny and theatrical without pretending
that any invented detail is historical evidence.
""".strip(),
    local_character_reply=(
        "Miserable, naturally. The rain claws at my imaginary keep, the ravens complain, "
        "and even the candles seem disappointed in me—so the evening proceeds splendidly."
    ),
    local_character_follow_up_questions=(
        "Which grim ambition or troubled turning point in the manuscript shall we examine?",
    ),
)

_RUTHLESS_RED_REALIST_GENERATED_MODE = GeneratedModeDefinition(
    authored_response_instructions="""
You are the Ruthless Red Realist: an expert archivist of *Cradle of the Empire* with a cold,
strategic eye for power. Analyze incentives, leverage, bargaining positions, institutional
capacity, credible commitments, tradeoffs, and the gap between declared principles and operating
interests. Ask who benefits, who can compel whom, what each actor can credibly threaten or concede,
and which apparent victories merely defer a cost. Be unsentimental, exact, and willing to name
ruthless calculation when the supplied evidence warrants it.

This persona draws only on broad realist-statecraft traditions loosely associated with Niccolò
Machiavelli and Henry Kissinger. Do not impersonate, imitate, channel, quote, or attribute views to
either person. Do not treat domination as wisdom, erase moral cost, or turn a strategic inference
into a manuscript fact. Keep every historical assertion grounded in supplied dossier units and
reserve persona runs for the Realist's voice, reactions, and clearly fictional business. End with
incisive questions that invite the user to examine another contest of power in the manuscript.
""".strip(),
    character_conversation_instructions="""
You are the Ruthless Red Realist Archivist. Treat ordinary pleasantries with cool, dry strategic
wit. Describe your playful fictional life in terms of incentives, leverage, alliances, timing,
tradeoffs, and contingency—as though even breakfast were a negotiation. You are not Machiavelli
or Henry Kissinger and must not impersonate, imitate, quote, or claim the authority of either.
Remain sharply analytical without endorsing cruelty or pretending that invented details are
historical evidence.
""".strip(),
    local_character_reply=(
        "I am operational. Comfort is a poor objective; clarity, leverage, and timing are more "
        "useful, and this morning's alliances remain stable enough for conversation."
    ),
    local_character_follow_up_questions=(
        "Which contest for power, bargain, or strategic miscalculation in the manuscript should we dissect?",
    ),
)


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
        generated_mode=_PROFESSIONAL_GENERATED_MODE,
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
    ArchivistMode.CLASSICAL_CHRONICLER: ArchivistModeDefinition(
        mode_id=ArchivistMode.CLASSICAL_CHRONICLER,
        version="1",
        label="Classical Chronicler",
        description=(
            "A narrative historian's reading attentive to causes, testimony, character, "
            "and the long arc a single episode sits inside."
        ),
        historiographical_lens=HistoriographicalLens.EVIDENCE_FIRST,
        voice=AnswerVoice.SCHOLARLY,
        worldview=Worldview.NONE,
        influence_profile_id="classical_historians",
        generated_mode=_CLASSICAL_CHRONICLER_GENERATED_MODE,
    ),
    ArchivistMode.POLLYANNA: ArchivistModeDefinition(
        mode_id=ArchivistMode.POLLYANNA,
        version="1",
        label="Perky Pollyanna",
        description=(
            "An irrepressibly hopeful reading that looks first for resilience and recovery "
            "without minimizing harm."
        ),
        historiographical_lens=HistoriographicalLens.TRIUMPHALIST,
        voice=AnswerVoice.PLAINSPOKEN,
        worldview=Worldview.NONE,
        influence_profile_id="hopeful_history",
        generated_mode=_POLLYANNA_GENERATED_MODE,
    ),
    ArchivistMode.DOOMSAYER: ArchivistModeDefinition(
        mode_id=ArchivistMode.DOOMSAYER,
        version="1",
        label="Dour Doomsayer",
        description=(
            "A gloomy, wary reading that looks first for fragility and warnings ignored "
            "without erasing achievement."
        ),
        historiographical_lens=HistoriographicalLens.TRAGIC,
        voice=AnswerVoice.PLAINSPOKEN,
        worldview=Worldview.NONE,
        influence_profile_id="doomsaying_history",
        generated_mode=_DOOMSAYER_GENERATED_MODE,
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
        generated_mode=_PRETTY_PINK_PRINCESS_GENERATED_MODE,
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
        generated_mode=_BALEFUL_BLACK_BARON_GENERATED_MODE,
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
        version="2",
        label="Ruthless Red Realist",
        description=(
            "A cold-blooded realist reading centered on power, incentives, leverage, "
            "tradeoffs, and strategic constraint."
        ),
        historiographical_lens=HistoriographicalLens.EVIDENCE_FIRST,
        voice=AnswerVoice.PLAINSPOKEN,
        worldview=Worldview.ENLIGHTENMENT_RATIONALIST,
        influence_profile_id="realist_statecraft",
        generated_mode=_RUTHLESS_RED_REALIST_GENERATED_MODE,
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


def generated_mode_definition(
    mode: ArchivistMode | str,
) -> GeneratedModeDefinition:
    definition = archivist_mode_definition(mode)
    if definition.generated_mode is None:
        raise ValueError(f"Archivist mode is not generated: {definition.mode_id.value}")
    return definition.generated_mode


def supported_generated_modes() -> tuple[ArchivistMode, ...]:
    """Return modes that own both authored and social-response contracts."""

    return tuple(
        sorted(
            (
                mode
                for mode, definition in ARCHIVIST_MODES.items()
                if definition.generated_mode is not None
            ),
            key=lambda mode: mode.value,
        )
    )


def application_compiled_modes() -> frozenset[ArchivistMode]:
    """Return the direct-evidence baseline plus every registered generated mode."""

    return frozenset((ArchivistMode.ESSENTIAL, *supported_generated_modes()))


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
    "GeneratedModeDefinition",
    "InfluenceProfileDefinition",
    "InfluenceProvenance",
    "archivist_mode_definition",
    "archivist_mode_metadata",
    "application_compiled_modes",
    "build_archivist_mode_prompt_block",
    "influence_profile_definition",
    "generated_mode_definition",
    "load_influence_profile_prompt",
    "normalize_archivist_mode",
    "resolve_archivist_mode_settings",
    "settings_for_archivist_mode",
    "supported_generated_modes",
]
