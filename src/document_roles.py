"""Deterministic, passage-free document role profiles for query planning.

The profile is search orientation, never evidence. It reduces each eligible
document to a bounded list of locally derived tokens so a planner can choose a
document that actually mentions the actor, institution, mechanism, or period
named by a proposed historical stage without receiving manuscript passages.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence


DOCUMENT_ROLE_PROFILE_VERSION = "document-role-profile-v1"
MAX_DOCUMENT_ROLE_TERMS = 48
MAX_DOCUMENT_PERIOD_TERMS = 4
MAX_DOCUMENT_TITLE_TERMS = 4
MAX_DOCUMENT_ACRONYM_TERMS = 6
MAX_DOCUMENT_NAMED_TERMS = 18
MAX_DOCUMENT_INSTITUTIONAL_TERMS = 16
MAX_ROLE_TERM_CHARACTERS = 48

_WORD_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)
_YEAR_PATTERN = re.compile(r"^(?:1[0-9]{3}|20[0-9]{2})$")
_ROLE_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "again",
        "against",
        "also",
        "among",
        "another",
        "because",
        "been",
        "before",
        "being",
        "between",
        "both",
        "chapter",
        "could",
        "did",
        "does",
        "during",
        "each",
        "even",
        "first",
        "footnote",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "into",
        "itself",
        "later",
        "made",
        "many",
        "more",
        "most",
        "much",
        "must",
        "other",
        "over",
        "same",
        "should",
        "since",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "under",
        "until",
        "upon",
        "very",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "will",
        "with",
        "would",
        "years",
    }
)
_HISTORICAL_ROLE_VOCABULARY = frozenset(
    {
        "administration",
        "administrative",
        "army",
        "authority",
        "bank",
        "bureaucracy",
        "capital",
        "central",
        "charter",
        "civic",
        "colonial",
        "colony",
        "commerce",
        "commission",
        "communications",
        "company",
        "confederacy",
        "conflict",
        "congress",
        "constitution",
        "contract",
        "contracting",
        "corporate",
        "corporation",
        "court",
        "credit",
        "crown",
        "data",
        "debt",
        "defense",
        "empire",
        "federal",
        "finance",
        "fiscal",
        "government",
        "imperial",
        "industry",
        "infrastructure",
        "institution",
        "intelligence",
        "law",
        "legislature",
        "market",
        "military",
        "mobilization",
        "navy",
        "network",
        "parliament",
        "policy",
        "power",
        "procurement",
        "public",
        "regulation",
        "reserve",
        "revolution",
        "royal",
        "security",
        "server",
        "state",
        "tax",
        "taxation",
        "technology",
        "trade",
        "treasury",
        "war",
        "warfare",
        "wartime",
    }
)


def _normalize_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    ).casefold()


def _role_token_occurrences(
    value: str,
) -> tuple[tuple[str, bool, bool], ...]:
    occurrences: list[tuple[str, bool, bool]] = []
    for raw_token in _WORD_PATTERN.findall(value):
        token = _normalize_token(raw_token)
        if (
            not token
            or len(token) > MAX_ROLE_TERM_CHARACTERS
            or token in _ROLE_STOPWORDS
            or (not _YEAR_PATTERN.fullmatch(token) and len(token) < 3)
            or (token.isdigit() and not _YEAR_PATTERN.fullmatch(token))
            or (
                any(character.isdigit() for character in token)
                and not token.isdigit()
            )
        ):
            continue
        is_acronym = (
            raw_token.isupper()
            and any(character.isalpha() for character in raw_token)
            and len(token) <= 12
        )
        occurrences.append((token, raw_token[:1].isupper(), is_acronym))
    return tuple(occurrences)


def _role_tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token, _is_named, _is_acronym in _role_token_occurrences(value)
    )


def _role_vocabulary_match(term: str) -> bool:
    if term in _HISTORICAL_ROLE_VOCABULARY:
        return True
    return any(
        min(len(term), len(role)) >= 5
        and (term.startswith(role) or role.startswith(term))
        for role in _HISTORICAL_ROLE_VOCABULARY
    )


def _extend_unique(
    selected: list[str],
    candidates: Sequence[str],
    *,
    limit: int,
    capacity: int,
) -> None:
    if limit <= 0 or capacity <= len(selected):
        return
    added = 0
    seen = set(selected)
    for term in candidates:
        if term in seen:
            continue
        selected.append(term)
        seen.add(term)
        added += 1
        if added >= limit or len(selected) >= capacity:
            break


def derive_document_role_terms(
    chunks: Sequence[Mapping[str, object]],
) -> dict[str, tuple[str, ...]]:
    """Return stable, bounded role terms keyed by document ID.

    The returned values contain normalized tokens only—never sentences,
    paragraphs, chunk IDs, or excerpts. Titles receive a small weighting boost;
    dates are capped separately, while acronyms, named actors, institutional
    mechanisms, and general salience each receive bounded representation.
    """

    term_counts: dict[str, Counter[str]] = defaultdict(Counter)
    named_counts: dict[str, Counter[str]] = defaultdict(Counter)
    acronym_counts: dict[str, Counter[str]] = defaultdict(Counter)
    title_terms: dict[str, set[str]] = defaultdict(set)
    document_order: list[str] = []
    seen_documents: set[str] = set()

    for chunk in chunks:
        document = str(chunk.get("document") or "").strip()
        if not document:
            continue
        if document not in seen_documents:
            seen_documents.add(document)
            document_order.append(document)
        text_occurrences = _role_token_occurrences(str(chunk.get("text") or ""))
        term_counts[document].update(
            token for token, _is_named, _is_acronym in text_occurrences
        )
        named_counts[document].update(
            token
            for token, is_named, _is_acronym in text_occurrences
            if is_named
        )
        acronym_counts[document].update(
            token
            for token, _is_named, is_acronym in text_occurrences
            if is_acronym
        )
        title_terms[document].update(
            _role_tokens(str(chunk.get("chapter_title") or ""))
        )

    document_frequency: Counter[str] = Counter()
    for document in document_order:
        document_frequency.update(term_counts[document].keys())

    document_count = max(len(document_order), 1)
    profiles: dict[str, tuple[str, ...]] = {}
    for document in document_order:
        counts = term_counts[document]
        scored_terms: list[tuple[float, int, str]] = []
        score_by_term: dict[str, float] = {}
        period_terms: list[tuple[int, str]] = []
        for term, frequency in counts.items():
            if _YEAR_PATTERN.fullmatch(term):
                period_terms.append((frequency, term))
                continue
            inverse_document_frequency = (
                math.log(
                    (document_count + 1)
                    / (document_frequency[term] + 1)
                )
                + 1.0
            )
            score = (1.0 + math.log(frequency)) * inverse_document_frequency
            if term in title_terms[document]:
                score += 1.5
            score_by_term[term] = score
            scored_terms.append((score, frequency, term))

        scored_terms.sort(key=lambda item: (-item[0], -item[1], item[2]))
        ranked_terms = [term for _score, _frequency, term in scored_terms]
        title_ranked = sorted(
            (
                term
                for term in title_terms[document]
                if not _YEAR_PATTERN.fullmatch(term)
            ),
            key=lambda term: (
                -score_by_term.get(term, 0.0),
                -counts[term],
                term,
            ),
        )
        acronym_ranked = sorted(
            acronym_counts[document],
            key=lambda term: (
                -score_by_term.get(term, 0.0),
                -acronym_counts[document][term],
                term,
            ),
        )
        named_ranked = sorted(
            named_counts[document],
            key=lambda term: (
                -score_by_term.get(term, 0.0),
                -named_counts[document][term],
                term,
            ),
        )
        institutional_ranked = sorted(
            (
                term
                for term in counts
                if not _YEAR_PATTERN.fullmatch(term)
                and _role_vocabulary_match(term)
            ),
            key=lambda term: (
                -score_by_term.get(term, 0.0),
                -counts[term],
                term,
            ),
        )
        period_terms.sort(key=lambda item: (-item[0], item[1]))
        selected_periods = [
            term
            for _frequency, term in period_terms[:MAX_DOCUMENT_PERIOD_TERMS]
        ]
        non_period_capacity = MAX_DOCUMENT_ROLE_TERMS - len(selected_periods)
        selected: list[str] = []
        _extend_unique(
            selected,
            title_ranked,
            limit=MAX_DOCUMENT_TITLE_TERMS,
            capacity=non_period_capacity,
        )
        _extend_unique(
            selected,
            acronym_ranked,
            limit=MAX_DOCUMENT_ACRONYM_TERMS,
            capacity=non_period_capacity,
        )
        _extend_unique(
            selected,
            named_ranked,
            limit=MAX_DOCUMENT_NAMED_TERMS,
            capacity=non_period_capacity,
        )
        _extend_unique(
            selected,
            institutional_ranked,
            limit=MAX_DOCUMENT_INSTITUTIONAL_TERMS,
            capacity=non_period_capacity,
        )
        _extend_unique(
            selected,
            ranked_terms,
            limit=MAX_DOCUMENT_ROLE_TERMS,
            capacity=non_period_capacity,
        )
        _extend_unique(
            selected,
            selected_periods,
            limit=MAX_DOCUMENT_PERIOD_TERMS,
            capacity=MAX_DOCUMENT_ROLE_TERMS,
        )
        profiles[document] = tuple(selected)
    return profiles


__all__ = [
    "DOCUMENT_ROLE_PROFILE_VERSION",
    "MAX_DOCUMENT_ROLE_TERMS",
    "derive_document_role_terms",
]
