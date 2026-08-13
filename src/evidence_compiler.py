"""Deterministic, application-owned evidence compilation for direct answers.

This module deliberately performs no model or network calls. It receives the
ordered chunks admitted by Archivist's retrieval layer, selects short excerpts
that overlap the resolved question, and owns citation numbering itself.

The compiler is a product path, not a replacement for the frozen V26 pipeline.
Callers that want generated synthesis continue to use ``rag_pipeline``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


APPLICATION_COMPILED_POLICY_VERSION = "application-compiled-v1"
APPLICATION_COMPILED_SCHEMA = "archivist.application_compiled_answer/1"
MAX_EVIDENCE_CARDS = 3
MAX_EVIDENCE_CARD_WORDS = 32

_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:['\N{RIGHT SINGLE QUOTATION MARK}][^\W_]+)?", re.UNICODE)
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])(?:[\"'\N{RIGHT DOUBLE QUOTATION MARK}])?\s+|\n+")
_FOOTNOTE_PATTERN = re.compile(r"\s*\[Footnote\b.*$", re.IGNORECASE | re.DOTALL)
_SPACE_PATTERN = re.compile(r"\s+")
_QUESTION_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "book",
        "by",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "him",
        "his",
        "how",
        "in",
        "is",
        "it",
        "its",
        "manuscript",
        "of",
        "on",
        "or",
        "she",
        "that",
        "the",
        "their",
        "them",
        "they",
        "this",
        "to",
        "us",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "would",
        "you",
    }
)


@dataclass(frozen=True, slots=True)
class EvidenceCard:
    """One bounded verbatim excerpt attached to one selected source."""

    source_number: int
    chunk_id: str
    excerpt: str
    score: float
    matched_question_term_count: int

    @property
    def card_id(self) -> str:
        """Return the renderer-facing identifier owned by local code."""

        return f"card-{self.source_number}"

    @property
    def text(self) -> str:
        """Expose the bounded excerpt through ``EvidenceCardLike``."""

        return self.excerpt

    @property
    def source_numbers(self) -> tuple[int, ...]:
        """Bind this card to exactly its mechanically assigned source."""

        return (self.source_number,)

    @property
    def requirement_ids(self) -> tuple[str, ...]:
        """Direct question-local compilation has no planner requirements."""

        return ()


@dataclass(frozen=True, slots=True)
class CompiledEvidenceAnswer:
    """The direct reader answer plus its mechanically numbered source subset."""

    answer: str
    final_chunks: tuple[dict[str, Any], ...]
    cards: tuple[EvidenceCard, ...]
    status: str
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EvidencePacket:
    """Application-selected evidence shared by direct and generated renderers.

    ``source_chunks`` and ``cards`` use the same contiguous numbering. A prose
    model may later receive this packet, but it cannot add or renumber evidence.
    """

    question: str
    source_chunks: tuple[dict[str, Any], ...]
    cards: tuple[EvidenceCard, ...]
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _Candidate:
    chunk_index: int
    chunk_id: str
    sentence_index: int
    sentence: str
    score: float
    matched_question_term_count: int


def _tokens(value: str) -> list[str]:
    return [token.casefold() for token in _TOKEN_PATTERN.findall(value)]


def _question_terms(question: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            token
            for token in _tokens(question)
            if len(token) > 2 and token not in _QUESTION_STOPWORDS
        )
    )


def _sentences(text: object) -> list[str]:
    # Footnotes are a private bibliographic tail in corpus chunks. Remove the
    # complete tail before sentence splitting so no fragment can become a card.
    cleaned = _FOOTNOTE_PATTERN.sub("", str(text or ""))
    return [
        normalized
        for raw in _SENTENCE_SPLIT_PATTERN.split(cleaned)
        if (normalized := _SPACE_PATTERN.sub(" ", raw).strip(" \t\r\n-"))
    ]


def _candidate_score(
    sentence: str,
    *,
    question_terms: Sequence[str],
    chunk_index: int,
    sentence_index: int,
) -> tuple[float, int]:
    sentence_tokens = _tokens(sentence)
    sentence_token_set = set(sentence_tokens)
    matched = tuple(term for term in question_terms if term in sentence_token_set)
    if not matched:
        return 0.0, 0

    coverage = len(matched) / max(1, len(question_terms))
    density = len(matched) / max(1, min(len(sentence_token_set), 24))
    normalized_sentence = " ".join(sentence_tokens)
    adjacency_bonus = sum(
        1
        for left, right in zip(question_terms, question_terms[1:])
        if f"{left} {right}" in normalized_sentence
    )

    # Retrieval and sentence position are deterministic tie-breaks small enough
    # not to displace a candidate with stronger lexical evidence.
    retrieval_tie_break = 1 / (100 + chunk_index)
    sentence_tie_break = 1 / (10_000 + sentence_index)
    return (
        round(
            coverage * 10
            + density * 2
            + adjacency_bonus * 3
            + retrieval_tie_break
            + sentence_tie_break,
            6,
        ),
        len(matched),
    )


def _bounded_excerpt(sentence: str, question_terms: Sequence[str]) -> str:
    """Return a question-local window that stays below public quotation limits."""

    raw_words = sentence.split()
    if len(raw_words) <= MAX_EVIDENCE_CARD_WORDS:
        return sentence

    normalized_words = [(_tokens(word) or [""])[0] for word in raw_words]
    match_indices = [index for index, word in enumerate(normalized_words) if word in question_terms]
    center = match_indices[0] if match_indices else 0
    start = max(0, center - MAX_EVIDENCE_CARD_WORDS // 3)
    start = min(start, len(raw_words) - MAX_EVIDENCE_CARD_WORDS)
    end = start + MAX_EVIDENCE_CARD_WORDS
    excerpt = " ".join(raw_words[start:end]).strip()
    if start:
        excerpt = f"\N{HORIZONTAL ELLIPSIS}{excerpt}"
    if end < len(raw_words):
        excerpt = f"{excerpt}\N{HORIZONTAL ELLIPSIS}"
    return excerpt


def _best_candidates(
    question: str,
    chunks: Sequence[Mapping[str, object]],
) -> tuple[_Candidate, ...]:
    question_terms = _question_terms(question)
    candidates: list[_Candidate] = []
    for chunk_index, chunk in enumerate(chunks):
        chunk_id = str(chunk.get("chunk_id") or "")
        for sentence_index, sentence in enumerate(_sentences(chunk.get("text"))):
            score, matched_count = _candidate_score(
                sentence,
                question_terms=question_terms,
                chunk_index=chunk_index,
                sentence_index=sentence_index,
            )
            if score <= 0:
                continue
            candidates.append(
                _Candidate(
                    chunk_index=chunk_index,
                    chunk_id=chunk_id,
                    sentence_index=sentence_index,
                    sentence=sentence,
                    score=score,
                    matched_question_term_count=matched_count,
                )
            )

    ranked = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.score,
            candidate.chunk_index,
            candidate.sentence_index,
            candidate.chunk_id,
        ),
    )
    selected: list[_Candidate] = []
    used_chunks: set[int] = set()
    normalized_excerpts: set[str] = set()
    for candidate in ranked:
        if candidate.chunk_index in used_chunks:
            continue
        excerpt = _bounded_excerpt(candidate.sentence, question_terms)
        normalized = " ".join(_tokens(excerpt))
        if not normalized or normalized in normalized_excerpts:
            continue
        selected.append(candidate)
        used_chunks.add(candidate.chunk_index)
        normalized_excerpts.add(normalized)
        if len(selected) == MAX_EVIDENCE_CARDS:
            break

    # Citation numbering follows retrieval order, never relevance rank.
    return tuple(sorted(selected, key=lambda candidate: candidate.chunk_index))


def compile_evidence_packet(
    question: str,
    chunks: Sequence[Mapping[str, object]],
) -> EvidencePacket:
    """Select and number bounded evidence cards without rendering an answer."""

    question_terms = _question_terms(question)
    selected = _best_candidates(question, chunks)
    if not selected:
        return EvidencePacket(
            question=question,
            source_chunks=(),
            cards=(),
            diagnostics={
                "schema": APPLICATION_COMPILED_SCHEMA,
                "compiler_version": APPLICATION_COMPILED_POLICY_VERSION,
                "candidate_source_count": len(chunks),
                "selected_source_count": 0,
                "selected_card_count": 0,
                "question_term_count": len(question_terms),
                "generation_called": False,
            },
        )

    source_chunks = tuple(dict(chunks[item.chunk_index]) for item in selected)
    cards = tuple(
        EvidenceCard(
            source_number=source_number,
            chunk_id=item.chunk_id,
            excerpt=_bounded_excerpt(item.sentence, question_terms),
            score=item.score,
            matched_question_term_count=item.matched_question_term_count,
        )
        for source_number, item in enumerate(selected, start=1)
    )
    return EvidencePacket(
        question=question,
        source_chunks=source_chunks,
        cards=cards,
        diagnostics={
            "schema": APPLICATION_COMPILED_SCHEMA,
            "compiler_version": APPLICATION_COMPILED_POLICY_VERSION,
            "candidate_source_count": len(chunks),
            "selected_source_count": len(source_chunks),
            "selected_card_count": len(cards),
            "question_term_count": len(question_terms),
            "matched_question_term_count": max(card.matched_question_term_count for card in cards),
            "generation_called": False,
        },
    )


def render_direct_evidence_answer(packet: EvidencePacket) -> CompiledEvidenceAnswer:
    """Render one packet verbatim with mechanical citations and no generation."""

    if not packet.cards:
        return CompiledEvidenceAnswer(
            answer=(
                "The retrieved passages did not contain a concise direct excerpt "
                "responsive to this question."
            ),
            final_chunks=(),
            cards=(),
            status="insufficient_evidence",
            diagnostics=dict(packet.diagnostics),
        )

    answer_lines = ["Direct evidence from the manuscript:", ""]
    answer_lines.extend(f"- {render_evidence_card_claim(card)}" for card in packet.cards)
    return CompiledEvidenceAnswer(
        answer="\n".join(answer_lines),
        final_chunks=packet.source_chunks,
        cards=packet.cards,
        status="application_compiled",
        diagnostics=dict(packet.diagnostics),
    )


def render_evidence_card_claim(card: EvidenceCard) -> str:
    """Render one immutable card exactly as progressive delivery releases it.

    Keeping this application-owned string shared by the direct renderer and
    the progressive callback guarantees that every provisional checked claim
    survives verbatim in the canonical Essential answer. Generated renderers
    use the same evidence-and-citation shape while remaining free to reorder
    cards or interleave explicitly labeled editorial prose.
    """

    excerpt = card.excerpt.strip()
    terminal = excerpt[-1] if excerpt and excerpt[-1] in ".!?" else "."
    body = excerpt[:-1].rstrip() if excerpt and excerpt[-1] in ".!?" else excerpt
    return f"{body} [Source {card.source_number}]{terminal}"


def compile_evidence_answer(
    question: str,
    chunks: Sequence[Mapping[str, object]],
) -> CompiledEvidenceAnswer:
    """Compile a cited direct-evidence answer without a prose-model call."""

    return render_direct_evidence_answer(compile_evidence_packet(question, chunks))


__all__ = [
    "APPLICATION_COMPILED_POLICY_VERSION",
    "APPLICATION_COMPILED_SCHEMA",
    "CompiledEvidenceAnswer",
    "EvidenceCard",
    "EvidencePacket",
    "MAX_EVIDENCE_CARDS",
    "MAX_EVIDENCE_CARD_WORDS",
    "compile_evidence_answer",
    "compile_evidence_packet",
    "render_evidence_card_claim",
    "render_direct_evidence_answer",
]
