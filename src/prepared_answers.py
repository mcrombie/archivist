"""Application-owned, cited answers to a few stable questions about the book itself.

A prepared answer is written once from specific manuscript passages and served without
retrieval, embeddings, or an authoring call. Only the default Professional perspective uses one,
and only without interpretive overrides: any other perspective takes the live pipeline so the
answer's voice matches the reader's choice.
"""

from __future__ import annotations

from dataclasses import dataclass

from archivist_modes import ArchivistMode, settings_for_archivist_mode
from perspectives import AnswerVoice, HistoriographicalLens, Worldview
from product_help import matches_approved_question, normalize_bounded_question

PREPARED_ANSWER_POLICY_VERSION = "prepared-answer-v1"
PREPARED_ANSWER_STATUS = "prepared_answer"
PREPARED_ANSWER_MODES = frozenset({ArchivistMode.PROFESSIONAL})


@dataclass(frozen=True, slots=True)
class PreparedAnswer:
    answer_id: str
    approved_questions: tuple[str, ...]
    # "[Source N]" in the answer cites source_chunk_ids[N - 1].
    source_chunk_ids: tuple[str, ...]
    answer: str


BOOK_OVERVIEW = PreparedAnswer(
    answer_id="book_overview",
    approved_questions=(
        "what is cradle of the empire about",
        "what's cradle of the empire about",
        "what is the book about",
        "what's the book about",
        "what is this book about",
        "what's this book about",
        "what is the manuscript about",
        "what is this manuscript about",
    ),
    source_chunk_ids=("05_Introduction_001", "05_Introduction_002"),
    answer=(
        "Cradle of the Empire traces how the American imperial system was made, told through "
        "the history of Virginia. It is a “Big History”: it begins with the formation of the "
        "land itself—the tectonic collisions that raised the Appalachians and the shifts in "
        "climate that shaped its forests and waterways—then follows the first peoples, the "
        "fragmentary record of Indigenous nations, English conquest, the tobacco-plantation "
        "economy, expansion across the continent, industrialization, mobilization for world "
        "war, and the administration of a global empire up to the present day. [Source 1]\n\n"
        "Geography anchors the story. Virginia sits on a strategic corridor between the "
        "Atlantic world and the North American interior: the deep Chesapeake Bay offers "
        "anchorage for oceangoing trade, the James, York, Rappahannock, and Potomac reach inland "
        "toward the Appalachians, and the Fall Line divides the Tidewater from the Piedmont. "
        "Command of those waterways shaped power in the region long before Europeans arrived, "
        "and Virginia became a geopolitical staging ground again and again. Within a few "
        "centuries it changed from a sparsely populated land of farming, hunting, and gathering "
        "peoples into a modern industrial state home to major corporations, federal agencies, "
        "and war contractors. [Source 1, Source 2]\n\n"
        "The book is built to show change over long spans of time. The Introduction and "
        "Afterword frame its interpretation, the Prologue and Epilogue widen the view to "
        "geologic and even cosmic timescales, and twenty chapters in between move through the "
        "documented political and economic record roughly a quarter century at a time. Dates "
        "are kept to chapter titles and footnotes so the narrative can follow patterns of "
        "systemic change rather than a list of events to memorize. [Source 2]\n\n"
        "Where would you like to begin? You might ask how Virginia's geography shaped its "
        "history, who Powhatan was, or how the manuscript connects tobacco to labor."
    ),
)

PREPARED_ANSWERS: tuple[PreparedAnswer, ...] = (BOOK_OVERVIEW,)


def prepared_answer_for(
    question: str,
    *,
    archivist_mode: ArchivistMode | str,
    historiographical_lens: HistoriographicalLens | str,
    voice: AnswerVoice | str,
    worldview: Worldview | str,
) -> PreparedAnswer | None:
    """Return the prepared answer for this exact request, if one applies."""

    mode = ArchivistMode(archivist_mode)
    if mode not in PREPARED_ANSWER_MODES:
        return None
    requested_settings = (
        HistoriographicalLens(historiographical_lens),
        AnswerVoice(voice),
        Worldview(worldview),
    )
    if requested_settings != settings_for_archivist_mode(mode):
        return None
    normalized = normalize_bounded_question(question)
    if normalized is None:
        return None
    for prepared in PREPARED_ANSWERS:
        if matches_approved_question(normalized, prepared.approved_questions):
            return prepared
    return None


__all__ = [
    "BOOK_OVERVIEW",
    "PREPARED_ANSWERS",
    "PREPARED_ANSWER_MODES",
    "PREPARED_ANSWER_POLICY_VERSION",
    "PREPARED_ANSWER_STATUS",
    "PreparedAnswer",
    "prepared_answer_for",
]
