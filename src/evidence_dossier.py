"""Build a rich, provider-neutral evidence dossier from finalized retrieval.

The dossier boundary sits *after* Archivist's shared retrieval finalizer.  It
therefore accepts dense-only or hybrid results without knowing how they were
ranked, preserves their order, and performs no retrieval or provider calls of
its own.

Unlike :mod:`evidence_compiler`, this private model-facing representation keeps
whole chunks (or, only when the hard budget requires it, a range of complete
paragraphs).  It is not safe to return directly from a public endpoint.  The
reader-facing Essential answer must continue to use the bounded public excerpt
compiler rather than serializing this object.
"""

from __future__ import annotations

import json
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal


RETRIEVAL_DOSSIER_SCHEMA = "archivist.retrieval_dossier/1"
DEFAULT_MIN_DOSSIER_UNITS = 4
DEFAULT_MAX_DOSSIER_UNITS = 8
DEFAULT_TARGET_EVIDENCE_TOKENS = 2_500
DEFAULT_HARD_EVIDENCE_TOKEN_LIMIT = 4_500
CHARACTERS_PER_ESTIMATED_TOKEN = 4

Aspect = Literal["who", "what", "when", "why", "general"]

_SPACE_PATTERN = re.compile(r"\s+")
_PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n+")
_QUESTION_WORD_PATTERN = re.compile(r"\b(who|what|when|why)\b", re.IGNORECASE)
_WHAT_TIME_PATTERN = re.compile(
    r"\bwhat\s+(?:date|day|month|time|year|century|period|era)\b",
    re.IGNORECASE,
)
_MULTIPART_PATTERN = re.compile(
    r"(?:[;]|\?\s+|\b(?:and|also|as well as)\s+(?:who|what|when|why)\b)",
    re.IGNORECASE,
)
_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:['\N{RIGHT SINGLE QUOTATION MARK}][^\W_]+)?", re.UNICODE)
_DATE_PATTERN = re.compile(
    r"(?:\b(?:1[0-9]{3}|20[0-9]{2})\b|"
    r"\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|"
    r"eighteenth|nineteenth|twentieth|twenty-first)\s+centur(?:y|ies)\b|"
    r"\b(?:before|after|during|later|earlier|year|date|century|decade|era)\b)",
    re.IGNORECASE,
)
_CAUSAL_PATTERN = re.compile(
    r"\b(?:because|cause[ds]?|causing|consequen(?:ce|tly)|due to|led to|"
    r"result(?:ed|ing|s)? in|therefore|thus|so that|in order to|prompted|"
    r"produced|drove|driven|arose from|stemmed from)\b",
    re.IGNORECASE,
)
_FOLLOWUP_PRONOUN_PATTERN = re.compile(
    r"\b(?:he|him|his|she|her|hers|they|them|their|theirs|it|its)\b",
    re.IGNORECASE,
)
_TELL_ME_MORE_PATTERN = re.compile(r"^tell me more[?.!]*$", re.IGNORECASE)
_WHAT_HAPPENED_NEXT_PATTERN = re.compile(
    r"^what happened next[?.!]*$",
    re.IGNORECASE,
)
_PREVIOUS_SUBJECT_PATTERNS = (
    re.compile(
        r"^\s*who\s+(?:was|is|were|are)\s+(?P<subject>.+?)"
        r"(?:\s*,?\s+and\s+(?:who|what|when|why|how)\b|[?.!]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*what\s+(?:did|does|do)\s+(?P<subject>.+?)\s+"
        r"(?:do|make|create|establish|change|support|oppose|write|lead)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*when\s+(?:did|does)\s+(?P<subject>.+?)\s+"
        r"(?:live|die|serve|arrive|leave|begin|end|happen|occur)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:tell me about|describe|explain)\s+(?P<subject>.+?)[?.!]?$",
        re.IGNORECASE,
    ),
)
_QUESTION_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
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
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
    }
)


class EvidenceDossierError(ValueError):
    """Raised when finalized retrieval cannot form a valid dossier."""


@dataclass(frozen=True, slots=True)
class DossierRequirement:
    """One explicit question aspect the answer should address."""

    requirement_id: str
    aspect: Aspect
    question_fragment: str

    def to_payload(self) -> dict[str, str]:
        return {
            "requirement_id": self.requirement_id,
            "aspect": self.aspect,
            "question_fragment": self.question_fragment,
        }


@dataclass(frozen=True, slots=True)
class DossierSource:
    """Corpus-owned source identity and location for one evidence unit."""

    chunk_id: str
    chunk_ids: tuple[str, ...]
    source_numbers: tuple[int, ...]
    retrieval_rank: int
    document: str
    chapter_title: str
    paragraph_start: int | None
    paragraph_end: int | None
    physical_page_start: int | None = None
    physical_page_end: int | None = None
    edition_id: str | None = None
    edition_name: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_ids": list(self.chunk_ids),
            # Reader-facing source numbers are deliberately omitted.  They are
            # local rendering state, not something the model may write.
            "retrieval_rank": self.retrieval_rank,
            "document": self.document,
            "chapter_title": self.chapter_title,
            "paragraph_start": self.paragraph_start,
            "paragraph_end": self.paragraph_end,
            "physical_page_start": self.physical_page_start,
            "physical_page_end": self.physical_page_end,
            "edition_id": self.edition_id,
            "edition_name": self.edition_name,
        }


@dataclass(frozen=True, slots=True)
class DossierUnit:
    """One full retrieved chunk or hard-budgeted complete-paragraph range."""

    unit_id: str
    source: DossierSource
    text: str
    text_scope: Literal["full_chunk", "complete_paragraph_range"]
    estimated_evidence_tokens: int
    requirement_ids: tuple[str, ...]
    aspect_tags: tuple[str, ...]

    @property
    def source_numbers(self) -> tuple[int, ...]:
        """Return locally owned source numbers without exposing them to the model."""

        return self.source.source_numbers

    @property
    def chunk_id(self) -> str:
        return self.source.chunk_id

    @property
    def chapter_title(self) -> str:
        return self.source.chapter_title

    @property
    def locator(self) -> str:
        start = self.source.paragraph_start
        end = self.source.paragraph_end
        if start is None:
            paragraphs = "paragraphs unknown"
        elif end is None or end == start:
            paragraphs = f"paragraph {start}"
        else:
            paragraphs = f"paragraphs {start}-{end}"
        chapter = self.source.chapter_title or self.source.document or "Manuscript"
        return f"{chapter}, {paragraphs}"

    def to_payload(self) -> dict[str, object]:
        return {
            "unit_id": self.unit_id,
            "source": self.source.to_payload(),
            "text_scope": self.text_scope,
            "estimated_evidence_tokens": self.estimated_evidence_tokens,
            "requirement_ids": list(self.requirement_ids),
            "aspect_tags": list(self.aspect_tags),
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class RetrievalDossier:
    """Bounded evidence and question requirements for one answer call."""

    dossier_id: str
    schema: str
    question: str
    retrieval_query: str
    requirements: tuple[DossierRequirement, ...]
    aspect_tags: tuple[str, ...]
    units: tuple[DossierUnit, ...]
    estimated_evidence_tokens: int
    target_evidence_tokens: int
    hard_evidence_token_limit: int
    diagnostics: dict[str, Any]

    def to_payload(self) -> dict[str, object]:
        return {
            "dossier_id": self.dossier_id,
            "schema": self.schema,
            "question": self.question,
            "retrieval_query": self.retrieval_query,
            "requirements": [requirement.to_payload() for requirement in self.requirements],
            "aspect_tags": list(self.aspect_tags),
            "units": [unit.to_payload() for unit in self.units],
            "estimated_evidence_tokens": self.estimated_evidence_tokens,
            "target_evidence_tokens": self.target_evidence_tokens,
            "hard_evidence_token_limit": self.hard_evidence_token_limit,
            "tag_semantics": (
                "Requirement IDs and aspect tags are routing hints, not proof that a passage "
                "supports a claim; support must be checked against the passage text."
            ),
        }


def estimate_evidence_tokens(value: str) -> int:
    """Return the repository's conservative, dependency-free token estimate."""

    if not value:
        return 0
    return -(-len(value) // CHARACTERS_PER_ESTIMATED_TOKEN)


def _stable_unit_id(chunk_id: str, scope: str = "full") -> str:
    """Return a bounded opaque ID even when a document stem has spaces."""

    identity = f"{chunk_id}\0{scope}".encode("utf-8")
    return "evidence:" + hashlib.sha256(identity).hexdigest()[:24]


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(token.casefold() for token in _TOKEN_PATTERN.findall(value))


def _content_terms(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in _tokens(value)
        if len(token) > 2 and token not in _QUESTION_STOPWORDS
    )


def derive_question_requirements(question: str) -> tuple[DossierRequirement, ...]:
    """Derive transparent who/what/when/why requirements from user wording.

    These are deterministic coverage hints, not a claim that retrieval satisfied
    any aspect.  The prose model still has to inspect the supplied text.
    """

    normalized = _SPACE_PATTERN.sub(" ", question).strip()
    if not normalized:
        raise EvidenceDossierError("question must not be blank")

    requirement_source = _WHAT_TIME_PATTERN.sub("when", normalized)
    matches = tuple(_QUESTION_WORD_PATTERN.finditer(requirement_source))
    if not matches:
        return (
            DossierRequirement(
                requirement_id="requirement:general:1",
                aspect="general",
                question_fragment=normalized,
            ),
        )

    counts: dict[str, int] = {}
    requirements: list[DossierRequirement] = []
    for index, match in enumerate(matches):
        aspect = match.group(1).casefold()
        start = match.start()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(requirement_source)
        )
        fragment = requirement_source[start:end].strip(" ,;:-")
        fragment = re.sub(r"\s+(?:and|also)$", "", fragment, flags=re.IGNORECASE).strip()
        counts[aspect] = counts.get(aspect, 0) + 1
        requirements.append(
            DossierRequirement(
                requirement_id=f"requirement:{aspect}:{counts[aspect]}",
                aspect=aspect,  # type: ignore[arg-type]
                question_fragment=fragment or normalized,
            )
        )
    return tuple(requirements)


def _question_aspect_tags(
    question: str,
    requirements: Sequence[DossierRequirement],
) -> tuple[str, ...]:
    tags = list(dict.fromkeys(requirement.aspect for requirement in requirements))
    if len(requirements) > 1 or _MULTIPART_PATTERN.search(question):
        tags.append("multipart")
    return tuple(tags)


def _candidate_requirement_ids(
    text: str,
    requirements: Sequence[DossierRequirement],
    *,
    question_terms: frozenset[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    text_terms = _content_terms(text)
    requirement_ids: list[str] = []
    aspects: list[str] = []
    for requirement in requirements:
        fragment_terms = _content_terms(requirement.question_fragment)
        # A pronominal multipart clause such as "what did he do?" carries
        # no useful clause-local terms.  In that common case the whole
        # question's subject terms are the least surprising routing hint.
        if not fragment_terms:
            fragment_terms = question_terms
        has_overlap = bool(text_terms & fragment_terms)
        if requirement.aspect == "when":
            candidate = has_overlap and bool(_DATE_PATTERN.search(text))
        elif requirement.aspect == "why":
            candidate = has_overlap and bool(_CAUSAL_PATTERN.search(text))
        else:
            candidate = has_overlap
        if candidate:
            requirement_ids.append(requirement.requirement_id)
            aspects.append(requirement.aspect)
    if len(set(aspects)) > 1:
        aspects.append("multipart")
    return tuple(requirement_ids), tuple(dict.fromkeys(aspects))


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _edition_values(chunk: Mapping[str, object]) -> tuple[str | None, str | None]:
    edition = chunk.get("edition")
    if not isinstance(edition, Mapping):
        return None, None
    edition_id = str(edition.get("edition_id") or "").strip() or None
    edition_name = str(edition.get("name") or edition.get("edition_name") or "").strip() or None
    return edition_id, edition_name


def _source_from_chunk(
    chunk: Mapping[str, object],
    *,
    retrieval_rank: int,
    paragraph_start: int | None = None,
    paragraph_end: int | None = None,
) -> DossierSource:
    chunk_id = str(chunk.get("chunk_id") or "").strip()
    if not chunk_id:
        raise EvidenceDossierError("every finalized chunk must have a stable chunk_id")
    raw_chunk_ids = chunk.get("chunk_ids")
    if isinstance(raw_chunk_ids, Sequence) and not isinstance(raw_chunk_ids, (str, bytes)):
        chunk_ids = tuple(str(value).strip() for value in raw_chunk_ids if str(value).strip())
    else:
        chunk_ids = (chunk_id,)
    edition_id, edition_name = _edition_values(chunk)
    return DossierSource(
        chunk_id=chunk_id,
        chunk_ids=chunk_ids or (chunk_id,),
        # Reassigned contiguously after blank, duplicate, and budget skips.
        source_numbers=(),
        retrieval_rank=retrieval_rank,
        document=str(chunk.get("document") or ""),
        chapter_title=str(chunk.get("chapter_title") or ""),
        paragraph_start=(
            paragraph_start
            if paragraph_start is not None
            else _optional_int(chunk.get("paragraph_start"))
        ),
        paragraph_end=(
            paragraph_end if paragraph_end is not None else _optional_int(chunk.get("paragraph_end"))
        ),
        physical_page_start=_optional_int(chunk.get("physical_page_start")),
        physical_page_end=_optional_int(chunk.get("physical_page_end")),
        edition_id=edition_id,
        edition_name=edition_name,
    )


def _full_unit(
    chunk: Mapping[str, object],
    *,
    retrieval_rank: int,
    requirements: Sequence[DossierRequirement],
    question_terms: frozenset[str],
) -> DossierUnit:
    source = _source_from_chunk(chunk, retrieval_rank=retrieval_rank)
    text = str(chunk.get("text") or "").strip()
    requirement_ids, aspects = _candidate_requirement_ids(
        text,
        requirements,
        question_terms=question_terms,
    )
    return DossierUnit(
        unit_id=_stable_unit_id(source.chunk_id),
        source=source,
        text=text,
        text_scope="full_chunk",
        estimated_evidence_tokens=estimate_evidence_tokens(text),
        requirement_ids=requirement_ids,
        aspect_tags=aspects,
    )


def _paragraph_range_unit(
    chunk: Mapping[str, object],
    *,
    retrieval_rank: int,
    requirements: Sequence[DossierRequirement],
    question_terms: frozenset[str],
    available_tokens: int,
) -> DossierUnit | None:
    """Fit leading complete paragraphs when the full chunk breaches the cap."""

    paragraphs = [
        paragraph.strip()
        for paragraph in _PARAGRAPH_SPLIT_PATTERN.split(str(chunk.get("text") or ""))
        if paragraph.strip()
    ]
    selected: list[str] = []
    for paragraph in paragraphs:
        candidate_text = "\n\n".join((*selected, paragraph))
        if estimate_evidence_tokens(candidate_text) > available_tokens:
            break
        selected.append(paragraph)
    if not selected:
        return None

    raw_start = _optional_int(chunk.get("paragraph_start"))
    paragraph_start = raw_start
    paragraph_end = raw_start + len(selected) - 1 if raw_start is not None else None
    source = _source_from_chunk(
        chunk,
        retrieval_rank=retrieval_rank,
        paragraph_start=paragraph_start,
        paragraph_end=paragraph_end,
    )
    text = "\n\n".join(selected)
    requirement_ids, aspects = _candidate_requirement_ids(
        text,
        requirements,
        question_terms=question_terms,
    )
    range_label = (
        f"p{paragraph_start}-{paragraph_end}"
        if paragraph_start is not None and paragraph_end is not None
        else f"paragraphs-1-{len(selected)}"
    )
    return DossierUnit(
        unit_id=_stable_unit_id(source.chunk_id, range_label),
        source=source,
        text=text,
        text_scope="complete_paragraph_range",
        estimated_evidence_tokens=estimate_evidence_tokens(text),
        requirement_ids=requirement_ids,
        aspect_tags=aspects,
    )


def _minimum_complete_paragraph_tokens(chunk: Mapping[str, object]) -> int:
    """Return the smallest complete leading range selectable from a chunk."""

    paragraphs = [
        paragraph.strip()
        for paragraph in _PARAGRAPH_SPLIT_PATTERN.split(str(chunk.get("text") or ""))
        if paragraph.strip()
    ]
    return estimate_evidence_tokens(paragraphs[0]) if paragraphs else 0


def _validate_budget(
    *,
    target_tokens: int,
    hard_token_limit: int,
    min_units: int,
    max_units: int,
) -> None:
    if target_tokens <= 0 or hard_token_limit <= 0:
        raise EvidenceDossierError("token budgets must be positive")
    if target_tokens > hard_token_limit:
        raise EvidenceDossierError("target_tokens must not exceed hard_token_limit")
    if min_units <= 0 or max_units <= 0 or min_units > max_units:
        raise EvidenceDossierError("unit bounds must be positive and ordered")
    if max_units > DEFAULT_MAX_DOSSIER_UNITS:
        raise EvidenceDossierError(
            f"max_units must not exceed {DEFAULT_MAX_DOSSIER_UNITS}"
        )


def build_retrieval_dossier(
    question: str,
    finalized_chunks: Sequence[Mapping[str, object]],
    *,
    retrieval_query: str | None = None,
    target_tokens: int = DEFAULT_TARGET_EVIDENCE_TOKENS,
    hard_token_limit: int = DEFAULT_HARD_EVIDENCE_TOKEN_LIMIT,
    min_units: int = DEFAULT_MIN_DOSSIER_UNITS,
    max_units: int = DEFAULT_MAX_DOSSIER_UNITS,
) -> RetrievalDossier:
    """Package finalized retrieval into 4--8 rich, source-bound units.

    Retrieval order is preserved.  The builder includes at least ``min_units``
    when the finalized result and hard budget permit, then continues toward the
    target budget without exceeding ``max_units`` or the hard evidence cap.
    Whole chunk text is preferred.  If a chunk alone would cross the hard cap,
    the only permitted shortening is a leading range of complete paragraphs.
    """

    _validate_budget(
        target_tokens=target_tokens,
        hard_token_limit=hard_token_limit,
        min_units=min_units,
        max_units=max_units,
    )
    normalized_question = _SPACE_PATTERN.sub(" ", question).strip()
    normalized_retrieval_query = _SPACE_PATTERN.sub(
        " ", retrieval_query if retrieval_query is not None else normalized_question
    ).strip()
    if not normalized_retrieval_query:
        raise EvidenceDossierError("retrieval_query must not be blank")
    requirements = derive_question_requirements(normalized_question)
    question_tags = _question_aspect_tags(normalized_question, requirements)
    question_terms = _content_terms(normalized_question)

    candidates: list[tuple[int, Mapping[str, object], int]] = []
    seen_chunk_ids: set[str] = set()
    skipped_blank = 0
    skipped_duplicate = 0

    for retrieval_rank, chunk in enumerate(finalized_chunks, start=1):
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        if not chunk_id:
            raise EvidenceDossierError("every finalized chunk must have a stable chunk_id")
        if chunk_id in seen_chunk_ids:
            skipped_duplicate += 1
            continue
        seen_chunk_ids.add(chunk_id)
        if not str(chunk.get("text") or "").strip():
            skipped_blank += 1
            continue
        candidates.append(
            (retrieval_rank, chunk, _minimum_complete_paragraph_tokens(chunk))
        )

    units: list[DossierUnit] = []
    total_tokens = 0
    skipped_budget = 0
    paragraph_ranged = 0

    for candidate_index, (retrieval_rank, chunk, minimum_tokens) in enumerate(candidates):
        if len(units) >= max_units:
            break

        full_unit = _full_unit(
            chunk,
            retrieval_rank=retrieval_rank,
            requirements=requirements,
            question_terms=question_terms,
        )
        available_tokens = hard_token_limit - total_tokens

        # Until the dossier reaches its minimum breadth, reserve the cheapest
        # complete leading paragraph from enough later candidates.  This keeps
        # a very large high-ranked chunk from consuming a feasible hard budget
        # by itself while retaining retrieval order in the selected output.
        remaining_required = max(0, min_units - len(units) - 1)
        future_minimums = sorted(
            candidate[2] for candidate in candidates[candidate_index + 1 :]
        )
        if remaining_required > len(future_minimums):
            reserved_tokens = 0
        else:
            reserved_tokens = sum(future_minimums[:remaining_required])
        selection_tokens = available_tokens - reserved_tokens
        if minimum_tokens > selection_tokens:
            skipped_budget += 1
            continue

        if full_unit.estimated_evidence_tokens <= selection_tokens:
            unit = full_unit
        else:
            unit = _paragraph_range_unit(
                chunk,
                retrieval_rank=retrieval_rank,
                requirements=requirements,
                question_terms=question_terms,
                available_tokens=selection_tokens,
            )
            if unit is None:
                skipped_budget += 1
                continue
            paragraph_ranged += 1

        units.append(unit)
        total_tokens += unit.estimated_evidence_tokens
        if len(units) >= min_units and total_tokens >= target_tokens:
            break

    below_minimum = len(units) < min_units
    diagnostics: dict[str, Any] = {
        "schema": RETRIEVAL_DOSSIER_SCHEMA,
        "input_finalized_chunk_count": len(finalized_chunks),
        "selected_unit_count": len(units),
        "estimated_evidence_tokens": total_tokens,
        "target_reached": total_tokens >= target_tokens,
        "below_minimum_unit_count": below_minimum,
        "skipped_blank_chunk_count": skipped_blank,
        "skipped_duplicate_chunk_count": skipped_duplicate,
        "skipped_for_budget_count": skipped_budget,
        "paragraph_ranged_unit_count": paragraph_ranged,
        "retrieval_order_preserved": True,
        "provider_calls": 0,
        "publicly_renderable": False,
    }
    units = [
        replace(unit, source=replace(unit.source, source_numbers=(source_number,)))
        for source_number, unit in enumerate(units, start=1)
    ]
    identity_payload = json.dumps(
        {
            "question": normalized_question,
            "retrieval_query": normalized_retrieval_query,
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "text_sha256": hashlib.sha256(unit.text.encode("utf-8")).hexdigest(),
                }
                for unit in units
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    dossier_id = "dossier:" + hashlib.sha256(identity_payload.encode("utf-8")).hexdigest()[:20]
    return RetrievalDossier(
        dossier_id=dossier_id,
        schema=RETRIEVAL_DOSSIER_SCHEMA,
        question=normalized_question,
        retrieval_query=normalized_retrieval_query,
        requirements=requirements,
        aspect_tags=question_tags,
        units=tuple(units),
        estimated_evidence_tokens=total_tokens,
        target_evidence_tokens=target_tokens,
        hard_evidence_token_limit=hard_token_limit,
        diagnostics=diagnostics,
    )


def serialize_retrieval_dossier(dossier: RetrievalDossier) -> str:
    """Serialize a dossier deterministically for one model request."""

    return json.dumps(
        dossier.to_payload(),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _subject_from_question(question: str) -> str | None:
    for pattern in _PREVIOUS_SUBJECT_PATTERNS:
        match = pattern.search(question)
        if match:
            subject = _SPACE_PATTERN.sub(" ", match.group("subject")).strip(" ,;:-")
            if subject and len(subject) <= 160 and _content_terms(subject):
                return subject
    return None


def _latest_history_subject(
    history: Sequence[Mapping[str, object]],
) -> str | None:
    for turn in reversed(history):
        previous = str(turn.get("question") or "").strip()
        if not previous:
            continue
        subject = _subject_from_question(previous)
        if subject:
            return subject
    return None


def resolve_local_followup_question(
    question: str,
    history: Sequence[Mapping[str, object]],
) -> str:
    """Resolve a simple pronominal follow-up using prior user text only.

    The function intentionally handles only high-confidence grammatical forms.
    If it cannot identify one bounded subject, it returns the current question
    unchanged instead of concatenating an entire earlier question into search.
    """

    current = _SPACE_PATTERN.sub(" ", question).strip()
    if not current:
        return current
    is_tell_me_more = bool(_TELL_ME_MORE_PATTERN.fullmatch(current))
    is_what_happened_next = bool(_WHAT_HAPPENED_NEXT_PATTERN.fullmatch(current))
    has_pronoun = bool(_FOLLOWUP_PRONOUN_PATTERN.search(current))
    if not has_pronoun and not is_tell_me_more and not is_what_happened_next:
        return current

    subject = _latest_history_subject(history)
    if not subject:
        return current
    if is_tell_me_more:
        return f"Tell me more about {subject}."
    if is_what_happened_next:
        return f"What happened to {subject} next?"

    possessive = f"{subject}'" if subject.endswith("s") else f"{subject}'s"

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        lowered = token.casefold()
        if lowered in {"his", "hers", "their", "theirs", "its"}:
            replacement = possessive
        elif lowered == "her":
            following = current[match.end() :].lstrip()
            replacement = possessive if following and following[0].isalnum() else subject
        else:
            replacement = subject
        if token[:1].isupper():
            return replacement[:1].upper() + replacement[1:]
        return replacement

    return _FOLLOWUP_PRONOUN_PATTERN.sub(replace, current)


__all__ = [
    "CHARACTERS_PER_ESTIMATED_TOKEN",
    "DEFAULT_HARD_EVIDENCE_TOKEN_LIMIT",
    "DEFAULT_MAX_DOSSIER_UNITS",
    "DEFAULT_MIN_DOSSIER_UNITS",
    "DEFAULT_TARGET_EVIDENCE_TOKENS",
    "DossierRequirement",
    "DossierSource",
    "DossierUnit",
    "EvidenceDossierError",
    "RETRIEVAL_DOSSIER_SCHEMA",
    "RetrievalDossier",
    "build_retrieval_dossier",
    "derive_question_requirements",
    "estimate_evidence_tokens",
    "resolve_local_followup_question",
    "serialize_retrieval_dossier",
]
