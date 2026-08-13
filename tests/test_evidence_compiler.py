from __future__ import annotations

from evidence_compiler import (
    APPLICATION_COMPILED_POLICY_VERSION,
    MAX_EVIDENCE_CARD_WORDS,
    compile_evidence_answer,
    compile_evidence_packet,
    render_evidence_card_claim,
    render_direct_evidence_answer,
)
from public_sources import answer_has_extended_verbatim_overlap


def _chunk(chunk_id: str, text: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document": "Chapter.md",
        "chapter_title": "Chapter",
        "paragraph_start": 1,
        "paragraph_end": 4,
        "text": text,
    }


def test_compiles_question_local_evidence_without_generation() -> None:
    chunks = [
        _chunk(
            "c1",
            (
                "Under a new treasurer, Sir Edwin Sandys, the company shifted course, "
                "ordering the repeal of the harsh laws and allowing the settlers to "
                "organize their own legislature."
            ),
        ),
        _chunk("c2", "Ships carried tobacco across the Atlantic."),
    ]

    result = compile_evidence_answer(
        "Who was Edwin Sandys, and what did he do?",
        chunks,
    )

    assert result.status == "application_compiled"
    assert result.final_chunks == (chunks[0],)
    assert len(result.cards) == 1
    assert result.cards[0].source_number == 1
    assert "Sir Edwin Sandys" in result.answer
    assert "[Source 1]" in result.answer
    assert result.diagnostics["compiler_version"] == APPLICATION_COMPILED_POLICY_VERSION
    assert result.diagnostics["generation_called"] is False


def test_packet_is_renderer_independent_and_keeps_numbering_bound() -> None:
    chunks = [
        _chunk("c1", "Edwin Sandys was treasurer of the Virginia Company."),
        _chunk("c2", "Sandys supported a new legislature in Virginia."),
    ]

    packet = compile_evidence_packet("Who was Edwin Sandys?", chunks)
    rendered = render_direct_evidence_answer(packet)

    assert [card.source_number for card in packet.cards] == [1, 2]
    assert [chunk["chunk_id"] for chunk in packet.source_chunks] == ["c1", "c2"]
    assert rendered.final_chunks == packet.source_chunks
    assert rendered.cards == packet.cards


def test_direct_answer_contains_each_progressive_checked_claim_verbatim_once() -> None:
    chunks = [
        _chunk("c1", "Edwin Sandys was treasurer of the Virginia Company."),
        _chunk("c2", "Sandys supported a new legislature in Virginia."),
    ]

    packet = compile_evidence_packet("Who was Edwin Sandys?", chunks)
    rendered = render_direct_evidence_answer(packet)

    checked_claims = tuple(render_evidence_card_claim(card) for card in packet.cards)
    assert checked_claims
    assert all(rendered.answer.count(claim) == 1 for claim in checked_claims)
    assert not answer_has_extended_verbatim_overlap(rendered.answer, chunks)


def test_selects_no_more_than_one_excerpt_per_source_and_numbers_contiguously() -> None:
    chunks = [
        _chunk(
            "c1",
            "Sandys was treasurer. Sandys repealed laws. Sandys supported an assembly.",
        ),
        _chunk("c2", "The assembly represented Virginia's boroughs."),
        _chunk("c3", "Virginia exported tobacco."),
        _chunk("c4", "A fourth Virginia passage should exceed the card limit."),
    ]

    result = compile_evidence_answer("What did Sandys do in Virginia?", chunks)

    assert len(result.cards) == 3
    assert [card.source_number for card in result.cards] == [1, 2, 3]
    assert len({card.chunk_id for card in result.cards}) == len(result.cards)
    assert result.answer.count("[Source 1]") == 1


def test_preserves_retrieval_order_after_relevance_selection() -> None:
    chunks = [
        _chunk("first", "Sandys appears briefly in this earlier retrieved source."),
        _chunk(
            "second",
            "Edwin Sandys was the Virginia Company treasurer and changed its policies.",
        ),
    ]

    result = compile_evidence_answer("Who was Edwin Sandys?", chunks)

    assert [chunk["chunk_id"] for chunk in result.final_chunks] == ["first", "second"]
    assert [card.chunk_id for card in result.cards] == ["first", "second"]


def test_long_sentence_is_windowed_below_public_verbatim_threshold() -> None:
    prefix = " ".join(f"prefix{index}" for index in range(30))
    suffix = " ".join(f"suffix{index}" for index in range(30))
    chunks = [
        _chunk(
            "c1",
            f"{prefix} Edwin Sandys served as treasurer and supported reform {suffix}.",
        )
    ]

    result = compile_evidence_answer("Who was Edwin Sandys?", chunks)

    assert len(result.cards[0].excerpt.split()) <= MAX_EVIDENCE_CARD_WORDS
    assert "Edwin Sandys" in result.cards[0].excerpt
    assert not answer_has_extended_verbatim_overlap(result.answer, chunks)


def test_footnote_tail_is_not_exposed_as_direct_evidence() -> None:
    chunks = [
        _chunk(
            "c1",
            "Sandys supported reform. [Footnote 48: A private bibliographic note.]",
        )
    ]

    result = compile_evidence_answer("What reform did Sandys support?", chunks)

    assert "Footnote" not in result.answer
    assert "private bibliographic note" not in result.answer


def test_unmatched_passages_fail_closed_without_sources() -> None:
    result = compile_evidence_answer(
        "Who was Edwin Sandys?",
        [_chunk("c1", "A passage solely about maritime weather.")],
    )

    assert result.status == "insufficient_evidence"
    assert result.final_chunks == ()
    assert result.cards == ()
    assert "did not contain" in result.answer
    assert result.diagnostics["generation_called"] is False


def test_compilation_is_deterministic() -> None:
    chunks = [
        _chunk("c1", "Edwin Sandys was treasurer of the Virginia Company."),
        _chunk("c2", "Sandys changed the company's policies."),
    ]

    first = compile_evidence_answer("Who was Edwin Sandys?", chunks)
    second = compile_evidence_answer("Who was Edwin Sandys?", chunks)

    assert first == second
