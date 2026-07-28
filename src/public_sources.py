"""Reader-safe, edition-qualified source presentation for the public demo."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from edition_locators import (
    LOCATOR_SCHEMA,
    TYPESET_PDF_DISPLAY_NAME,
    TYPESET_PDF_EDITION_ID,
    TYPESET_PDF_MANIFEST_SHA256,
    TYPESET_PDF_SHA256,
    EditionLocatorError,
    validate_text_free_artifact,
)
from filters import should_skip_document


PUBLIC_SOURCE_SCHEMA = "archivist.public_sources/1"
MAX_EXCERPT_CHARACTERS = 280
MAX_EXCERPT_SENTENCES = 2
MAX_EXCERPT_SOURCES = 3
MAX_TOTAL_EXCERPT_CHARACTERS = 700
MAX_VERBATIM_ANSWER_WORDS = 45
EXPECTED_LOCATOR_COUNT = 481

_CITATION_PATTERN = re.compile(r"\[Source (\d+)(?:, Source \d+)*\]")
_SOURCE_NUMBER_PATTERN = re.compile(r"Source (\d+)")
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])(?:[\"'\N{RIGHT DOUBLE QUOTATION MARK}])?\s+|\n+")
_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "had",
        "has",
        "he",
        "her",
        "his",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "she",
        "that",
        "the",
        "their",
        "they",
        "this",
        "to",
        "was",
        "were",
        "with",
    }
)


class PublicSourceError(ValueError):
    """Raised when public source disclosure cannot be proven safe."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expected_locator_ids(manifest: Mapping[str, object]) -> list[str]:
    raw_chunks = manifest.get("chunks")
    if not isinstance(raw_chunks, list):
        raise PublicSourceError("corpus manifest does not contain chunk records")
    chunk_ids = [
        str(chunk.get("chunk_id"))
        for chunk in raw_chunks
        if isinstance(chunk, Mapping)
        and not should_skip_document(str(chunk.get("document") or ""))
    ]
    if len(chunk_ids) != EXPECTED_LOCATOR_COUNT or len(set(chunk_ids)) != len(chunk_ids):
        raise PublicSourceError("corpus manifest does not identify the expected public corpus")
    return chunk_ids


def load_locator_index(
    locator_path: Path,
    manifest_path: Path,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Load and fully verify a text-free locator artifact, failing closed."""

    try:
        if _sha256(manifest_path) != TYPESET_PDF_MANIFEST_SHA256:
            raise PublicSourceError("corpus manifest identity does not match the public edition")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact = json.loads(locator_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicSourceError("edition locator data are unavailable") from exc
    if not isinstance(manifest, dict) or not isinstance(artifact, dict):
        raise PublicSourceError("edition locator data are malformed")

    expected_ids = _expected_locator_ids(manifest)
    try:
        validate_text_free_artifact(artifact, expected_chunk_ids=expected_ids)
    except EditionLocatorError as exc:
        raise PublicSourceError("edition locator verification failed") from exc

    edition = artifact.get("edition")
    locators = artifact.get("locators")
    if (
        artifact.get("schema") != LOCATOR_SCHEMA
        or not isinstance(edition, dict)
        or not isinstance(locators, list)
        or edition.get("edition_id") != TYPESET_PDF_EDITION_ID
        or edition.get("display_name") != TYPESET_PDF_DISPLAY_NAME
        or edition.get("source_asset_sha256") != TYPESET_PDF_SHA256
        or edition.get("corpus_manifest_sha256") != TYPESET_PDF_MANIFEST_SHA256
        or edition.get("locator_kind") != "page"
        or edition.get("status") != "verified"
    ):
        raise PublicSourceError("edition locator profile identity is invalid")
    index = {
        str(locator["chunk_id"]): dict(locator)
        for locator in locators
        if isinstance(locator, Mapping)
    }
    if len(index) != EXPECTED_LOCATOR_COUNT:
        raise PublicSourceError("edition locator profile is incomplete")
    return dict(edition), index


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    return [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT_PATTERN.split(normalized)
        if sentence.strip()
    ]


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_PATTERN.findall(text.casefold())
        if len(token) > 2 and token not in _STOP_WORDS
    }


def _claims_by_source(answer: str) -> tuple[list[int], dict[int, str]]:
    ordered_sources: list[int] = []
    claims: dict[int, str] = {}
    for sentence in _sentences(answer):
        for marker in _CITATION_PATTERN.finditer(sentence):
            for match in _SOURCE_NUMBER_PATTERN.finditer(marker.group(0)):
                source_number = int(match.group(1))
                if source_number not in ordered_sources:
                    ordered_sources.append(source_number)
                claims.setdefault(
                    source_number,
                    _CITATION_PATTERN.sub("", sentence).strip(),
                )
    return ordered_sources, claims


def _truncate_at_word_boundary(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit < 2:
        return ""
    candidate = text[: limit - 1].rstrip()
    if " " in candidate:
        candidate = candidate.rsplit(" ", 1)[0].rstrip()
    return f"{candidate}\N{HORIZONTAL ELLIPSIS}" if candidate else ""


def claim_local_excerpt(
    source_text: str,
    claim: str,
    *,
    character_limit: int = MAX_EXCERPT_CHARACTERS,
) -> str:
    """Select at most two source sentences most relevant to one cited claim."""

    sentences = _sentences(source_text)
    if not sentences or character_limit < 1:
        return ""
    claim_tokens = _content_tokens(claim)
    scored = [
        (
            len(claim_tokens & _content_tokens(sentence)),
            len(claim_tokens & _content_tokens(sentence))
            / max(1, len(_content_tokens(sentence))),
            -index,
            index,
        )
        for index, sentence in enumerate(sentences)
    ]
    ranked = sorted(scored, reverse=True)
    selected_indices = sorted(
        item[3]
        for item in ranked[:MAX_EXCERPT_SENTENCES]
        if item[0] > 0
    )
    if not selected_indices:
        selected_indices = [0]
    excerpt = " ".join(sentences[index] for index in selected_indices)
    return _truncate_at_word_boundary(excerpt, character_limit)


def _locator_label(start: str, end: str) -> str:
    if start == end:
        return f"p. {start}"
    return f"pp. {start}\N{EN DASH}{end}"


def _display_title(chunk: Mapping[str, object]) -> str:
    chapter_title = re.sub(r"\s+", " ", str(chunk.get("chapter_title") or "")).strip()
    if chapter_title and chapter_title.casefold() not in {"n/a", "none"}:
        return chapter_title
    return "Manuscript passage"


def public_source_payload(
    answer: str,
    chunks: Sequence[Mapping[str, object]],
    *,
    locator_path: Path,
    manifest_path: Path,
) -> dict[str, object]:
    """Return every source in model order, with bounded excerpts for up to three."""

    edition, locator_index = load_locator_index(locator_path, manifest_path)
    cited_order, claims = _claims_by_source(answer)
    excerpt_candidates = cited_order[:MAX_EXCERPT_SOURCES]
    remaining_excerpt_characters = MAX_TOTAL_EXCERPT_CHARACTERS
    sources: list[dict[str, object]] = []

    for source_number, chunk in enumerate(chunks, start=1):
        chunk_id = str(chunk.get("chunk_id") or "")
        locator = locator_index.get(chunk_id)
        if locator is None:
            raise PublicSourceError("an answer source has no verified edition locator")
        start = str(locator["label_start"])
        end = str(locator["label_end"])
        location = _locator_label(start, end)
        title = _display_title(chunk)
        source: dict[str, object] = {
            "kind": "public_locator",
            "source_number": source_number,
            "citation_label": (
                f"{title}; {edition['display_name']}, {location}"
            ),
            "title": title,
            "edition": {
                "id": edition["edition_id"],
                "name": edition["display_name"],
                "locator_kind": edition["locator_kind"],
            },
            "locator": {
                "start": start,
                "end": end,
                "label": location,
            },
        }
        if (
            source_number in excerpt_candidates
            and remaining_excerpt_characters > 0
        ):
            excerpt = claim_local_excerpt(
                str(chunk.get("text") or ""),
                claims.get(source_number, ""),
                character_limit=min(
                    MAX_EXCERPT_CHARACTERS,
                    remaining_excerpt_characters,
                ),
            )
            if excerpt:
                source["excerpt"] = excerpt
                remaining_excerpt_characters -= len(excerpt)
        sources.append(source)

    return {
        "source_schema": PUBLIC_SOURCE_SCHEMA,
        "sources": sources,
    }


def answer_has_extended_verbatim_overlap(
    answer: str,
    chunks: Sequence[Mapping[str, object]],
    *,
    word_limit: int = MAX_VERBATIM_ANSWER_WORDS,
) -> bool:
    """Detect long contiguous manuscript reproduction in a generated answer."""

    without_citations = _CITATION_PATTERN.sub("", answer)
    answer_tokens = _TOKEN_PATTERN.findall(without_citations.casefold())
    if len(answer_tokens) < word_limit:
        return False
    source_token_strings = [
        " ".join(_TOKEN_PATTERN.findall(str(chunk.get("text") or "").casefold()))
        for chunk in chunks
    ]
    for start in range(0, len(answer_tokens) - word_limit + 1):
        window = " ".join(answer_tokens[start : start + word_limit])
        if any(window in source_tokens for source_tokens in source_token_strings):
            return True
    return False
