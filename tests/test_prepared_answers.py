import re
from pathlib import Path

import pytest

import web_project
from archivist_modes import ArchivistMode, settings_for_archivist_mode
from perspectives import AnswerVoice
from prepared_answers import BOOK_OVERVIEW, PREPARED_ANSWERS, prepared_answer_for
from product_help import is_product_help_question
from public_sources import answer_has_extended_verbatim_overlap

MANIFEST = Path(__file__).resolve().parent.parent / "fixtures" / "corpus_manifest.json"


def settings_for(mode):
    lens, voice, worldview = settings_for_archivist_mode(mode)
    return {"historiographical_lens": lens, "voice": voice, "worldview": worldview}


def prepared_in(mode, question, **overrides):
    return prepared_answer_for(
        question,
        archivist_mode=mode,
        **{**settings_for(mode), **overrides},
    )


@pytest.mark.parametrize(
    "question",
    (
        "What is Cradle of the Empire about?",
        "what's cradle of the empire about",
        "What is this book about?",
        "What is the manuscript about?",
        "Waht is Cradle of the Empire about?",
    ),
)
def test_book_overview_questions_use_the_prepared_answer(question):
    assert prepared_in(ArchivistMode.PROFESSIONAL, question) is BOOK_OVERVIEW


@pytest.mark.parametrize(
    "question",
    (
        "What is Chapter 4 about?",
        "Who was Powhatan?",
        "What is Cradle of the Empire about, and who wrote it?",
        "What is Cradle of the Empire about?\nAnd tobacco?",
        "What do you do?",
    ),
)
def test_other_questions_do_not_use_a_prepared_answer(question):
    assert prepared_in(ArchivistMode.PROFESSIONAL, question) is None


@pytest.mark.parametrize(
    "mode",
    (
        ArchivistMode.ESSENTIAL,
        ArchivistMode.CLASSICAL_CHRONICLER,
        ArchivistMode.POLLYANNA,
        ArchivistMode.DOOMSAYER,
    ),
)
def test_other_perspectives_answer_live(mode):
    assert prepared_in(mode, "What is Cradle of the Empire about?") is None


def test_interpretive_overrides_answer_live():
    assert (
        prepared_in(
            ArchivistMode.PROFESSIONAL,
            "What is Cradle of the Empire about?",
            voice=AnswerVoice.ROMANTIC,
        )
        is None
    )


def test_the_overview_question_is_not_product_help():
    assert is_product_help_question("What is Cradle of the Empire about?") is False


def test_prepared_answers_cite_every_source_and_only_real_corpus_passages():
    manifest = MANIFEST.read_text(encoding="utf-8")
    assert len({prepared.answer_id for prepared in PREPARED_ANSWERS}) == len(PREPARED_ANSWERS)
    for prepared in PREPARED_ANSWERS:
        # Answer prose renders as plain text, so markdown emphasis would show literally.
        assert "*" not in prepared.answer and "_" not in prepared.answer
        cited = {int(number) for number in re.findall(r"Source (\d+)", prepared.answer)}
        assert cited == set(range(1, len(prepared.source_chunk_ids) + 1))
        for chunk_id in prepared.source_chunk_ids:
            assert f'"{chunk_id}"' in manifest, f"{chunk_id} is not in the corpus manifest"


@pytest.mark.skipif(
    not web_project.LEGACY_CHUNKS_FILE.exists(),
    reason="the built-in manuscript chunks are not present in this checkout",
)
def test_prepared_answers_paraphrase_rather_than_reproduce_their_sources():
    chunks_by_id = {
        chunk["chunk_id"]: chunk for chunk in web_project.load_project_chunks("current")
    }
    for prepared in PREPARED_ANSWERS:
        sources = [chunks_by_id[chunk_id] for chunk_id in prepared.source_chunk_ids]
        assert not answer_has_extended_verbatim_overlap(prepared.answer, sources)
