"""Deterministic, text-free edition locators for private manuscript chunks."""

from __future__ import annotations

import bisect
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


LOCATOR_SCHEMA = "archivist.edition_locators/1"
TYPESET_PDF_EDITION_ID = "typeset_pdf_0706"
TYPESET_PDF_DISPLAY_NAME = "Typeset PDF (July 6, 2026)"
TYPESET_PDF_SHA256 = "89d68cdc186432d4d4804fbaff6aac0deb599d351dd016fe250b25f2a4771b3f"
TYPESET_PDF_PAGE_COUNT = 594
TYPESET_PDF_MANIFEST_SHA256 = (
    "b7ff94315a3f1f28c831e2c3ca62c385567d2b1447c19ff45139d175c3ff3c17"
)
MAPPING_VERSION = "1.0.0"
ANCHOR_TOKEN_COUNT = 12
ANCHOR_SAMPLE_COUNT = 6
MIN_MATCHED_ANCHORS = 2
MAX_EXPECTED_PAGE_SPAN = 4
BOUNDARY_ANCHOR_TOKEN_COUNT = 8
BOUNDARY_ANCHOR_STRIDE = 8

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


class EditionLocatorError(ValueError):
    """Raised when private inputs cannot produce a trustworthy locator artifact."""


@dataclass(frozen=True, slots=True)
class Anchor:
    token_start: int
    text: str


@dataclass(frozen=True, slots=True)
class AnchorMatch:
    anchor: Anchor
    physical_page: int


@dataclass(frozen=True, slots=True)
class LocatorMatch:
    physical_page_start: int
    physical_page_end: int
    matched_anchor_count: int
    sampled_anchor_count: int
    repeated_anchor_count: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_tokens(text: str) -> list[str]:
    """Normalize DOCX/PDF prose to stable word-and-number tokens."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    return _TOKEN_RE.findall(normalized)


def sampled_anchors(
    text: str,
    *,
    token_count: int = ANCHOR_TOKEN_COUNT,
    sample_count: int = ANCHOR_SAMPLE_COUNT,
) -> tuple[Anchor, ...]:
    """Return evenly spaced, deduplicated exact-token anchors including both ends."""

    tokens = normalize_tokens(text)
    if len(tokens) < token_count:
        raise EditionLocatorError(
            f"chunk has {len(tokens)} normalized tokens; at least {token_count} are required"
        )
    last_start = len(tokens) - token_count
    if sample_count == 1:
        starts = [0]
    else:
        starts = [
            round(index * last_start / (sample_count - 1))
            for index in range(sample_count)
        ]
    anchors: list[Anchor] = []
    seen: set[str] = set()
    for start in starts:
        value = " ".join(tokens[start : start + token_count])
        if value not in seen:
            anchors.append(Anchor(token_start=start, text=value))
            seen.add(value)
    return tuple(anchors)


class NormalizedPdf:
    """Normalized PDF text plus enough offsets to recover physical pages."""

    def __init__(self, page_texts: Sequence[str]):
        if not page_texts:
            raise EditionLocatorError("PDF contains no pages")
        joined_pages: list[str] = []
        self._page_starts: list[int] = []
        offset = 0
        for page_text in page_texts:
            self._page_starts.append(offset)
            normalized = " ".join(normalize_tokens(page_text))
            joined_pages.append(normalized)
            offset += len(normalized) + 1
        self.text = " ".join(joined_pages)
        self._normalized_pages = tuple(joined_pages)

    @property
    def page_count(self) -> int:
        return len(self._page_starts)

    def physical_page_at(self, character_offset: int) -> int:
        return bisect.bisect_right(self._page_starts, character_offset)

    def find_anchor_pages(self, anchor: str) -> tuple[int, ...]:
        """Find exact, token-boundary-safe occurrences, including page boundaries."""

        needle = f" {anchor} "
        haystack = f" {self.text} "
        pages: list[int] = []
        start = 0
        while True:
            found = haystack.find(needle, start)
            if found < 0:
                break
            # The leading padding adds one character to both strings, so `found`
            # is already the corresponding offset in self.text.
            pages.append(self.physical_page_at(found))
            start = found + 1
        return tuple(pages)

    def find_anchor_pages_in_range(
        self,
        anchor: str,
        *,
        physical_page_start: int,
        physical_page_end: int,
    ) -> tuple[int, ...]:
        """Find page-local anchor matches inside a small candidate range."""

        needle = f" {anchor} "
        pages: list[int] = []
        for physical_page in range(physical_page_start, physical_page_end + 1):
            page_text = self._normalized_pages[physical_page - 1]
            if needle in f" {page_text} ":
                pages.append(physical_page)
        return tuple(pages)


def _dense_boundary_anchors(text: str) -> tuple[Anchor, ...]:
    tokens = normalize_tokens(text)
    if len(tokens) < BOUNDARY_ANCHOR_TOKEN_COUNT:
        return ()
    last_start = len(tokens) - BOUNDARY_ANCHOR_TOKEN_COUNT
    starts = list(range(0, last_start + 1, BOUNDARY_ANCHOR_STRIDE))
    if starts[-1] != last_start:
        starts.append(last_start)
    anchors: list[Anchor] = []
    seen: set[str] = set()
    for start in starts:
        value = " ".join(tokens[start : start + BOUNDARY_ANCHOR_TOKEN_COUNT])
        if value not in seen:
            anchors.append(Anchor(token_start=start, text=value))
            seen.add(value)
    return tuple(anchors)


def _refine_page_boundaries(
    chunk_text: str,
    pdf: NormalizedPdf,
    coarse: LocatorMatch,
    *,
    minimum_physical_page: int,
    max_page_span: int,
) -> LocatorMatch:
    """Use dense local anchors to recover endpoints missed by six coarse anchors."""

    search_start = max(minimum_physical_page, coarse.physical_page_start - 2)
    search_end = min(pdf.page_count, coarse.physical_page_end + 2)
    matches: list[tuple[Anchor, tuple[int, ...]]] = []
    for anchor in _dense_boundary_anchors(chunk_text):
        pages = pdf.find_anchor_pages_in_range(
            anchor.text,
            physical_page_start=search_start,
            physical_page_end=search_end,
        )
        if pages:
            matches.append((anchor, pages))
    if not matches:
        return coarse

    candidates: list[tuple[tuple[int, int, int], int, int]] = []
    first_possible = max(
        search_start,
        coarse.physical_page_end - max_page_span + 1,
    )
    last_possible = min(coarse.physical_page_start, search_end - max_page_span + 1)
    for window_start in range(first_possible, last_possible + 1):
        window_end = window_start + max_page_span - 1
        selected_pages = [
            page
            for _, pages in matches
            for page in pages
            if window_start <= page <= window_end
        ]
        selected_anchors = sum(
            any(window_start <= page <= window_end for page in pages)
            for _, pages in matches
        )
        if not selected_pages:
            continue
        start = min(selected_pages)
        end = max(selected_pages)
        rank = (-selected_anchors, start, end)
        candidates.append((rank, start, end))
    if not candidates:
        return coarse
    _, start, end = min(candidates, key=lambda item: item[0])
    return LocatorMatch(
        physical_page_start=start,
        physical_page_end=end,
        matched_anchor_count=coarse.matched_anchor_count,
        sampled_anchor_count=coarse.sampled_anchor_count,
        repeated_anchor_count=coarse.repeated_anchor_count,
    )


def locate_chunk(
    chunk_text: str,
    pdf: NormalizedPdf,
    *,
    minimum_physical_page: int,
    token_count: int = ANCHOR_TOKEN_COUNT,
    sample_count: int = ANCHOR_SAMPLE_COUNT,
    min_matched_anchors: int = MIN_MATCHED_ANCHORS,
    max_page_span: int = MAX_EXPECTED_PAGE_SPAN,
) -> LocatorMatch:
    """Map one chunk by selecting the strongest monotonic exact-anchor cluster."""

    anchors = sampled_anchors(
        chunk_text,
        token_count=token_count,
        sample_count=sample_count,
    )
    matches_by_anchor: list[tuple[Anchor, tuple[int, ...]]] = []
    repeated_anchor_count = 0
    for anchor in anchors:
        all_pages = pdf.find_anchor_pages(anchor.text)
        if len(all_pages) > 1:
            repeated_anchor_count += 1
        pages = tuple(
            page
            for page in all_pages
            if page >= minimum_physical_page
        )
        if pages:
            matches_by_anchor.append((anchor, pages))

    candidates = sorted({page for _, pages in matches_by_anchor for page in pages})
    ranked: list[tuple[tuple[int, int, int, int], LocatorMatch]] = []
    for candidate_start in candidates:
        candidate_end_limit = candidate_start + max_page_span - 1
        selected: list[AnchorMatch] = []
        for anchor, pages in matches_by_anchor:
            in_window = [page for page in pages if candidate_start <= page <= candidate_end_limit]
            if not in_window:
                continue
            # The earlier page is deterministic and preserves the most inclusive span.
            selected.append(AnchorMatch(anchor=anchor, physical_page=min(in_window)))
        if not selected:
            continue
        physical_start = min(item.physical_page for item in selected)
        physical_end = max(item.physical_page for item in selected)
        result = LocatorMatch(
            physical_page_start=physical_start,
            physical_page_end=physical_end,
            matched_anchor_count=len(selected),
            sampled_anchor_count=len(anchors),
            repeated_anchor_count=repeated_anchor_count,
        )
        rank = (
            -result.matched_anchor_count,
            result.physical_page_end - result.physical_page_start,
            result.physical_page_start,
            result.physical_page_end,
        )
        ranked.append((rank, result))

    if not ranked:
        raise EditionLocatorError("no exact anchor cluster found")
    result = min(ranked, key=lambda item: item[0])[1]
    if result.matched_anchor_count < min_matched_anchors:
        raise EditionLocatorError(
            f"only {result.matched_anchor_count} exact anchors matched; "
            f"{min_matched_anchors} required"
        )
    return _refine_page_boundaries(
        chunk_text,
        pdf,
        result,
        minimum_physical_page=minimum_physical_page,
        max_page_span=max_page_span,
    )


def roman_numeral(value: int) -> str:
    if not 1 <= value <= 3999:
        raise EditionLocatorError(f"Roman page value out of range: {value}")
    numerals = (
        (1000, "m"),
        (900, "cm"),
        (500, "d"),
        (400, "cd"),
        (100, "c"),
        (90, "xc"),
        (50, "l"),
        (40, "xl"),
        (10, "x"),
        (9, "ix"),
        (5, "v"),
        (4, "iv"),
        (1, "i"),
    )
    result: list[str] = []
    remainder = value
    for magnitude, numeral in numerals:
        count, remainder = divmod(remainder, magnitude)
        result.append(numeral * count)
    return "".join(result)


def typeset_page_label(physical_page: int) -> str:
    """Map a physical PDF page to the July 6 typeset edition's printed label."""

    if not 1 <= physical_page <= TYPESET_PDF_PAGE_COUNT:
        raise EditionLocatorError(f"physical page out of range: {physical_page}")
    if physical_page < 19:
        return roman_numeral(physical_page)
    return str(physical_page - 18)


def eligible_chunks(
    chunks: Sequence[Mapping[str, object]],
    manifest: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """Validate private chunks against the manifest and return corpus-eligible records."""

    manifest_chunks = manifest.get("chunks")
    ingest = manifest.get("ingest")
    extraction = manifest.get("extraction")
    if not isinstance(manifest_chunks, list) or not isinstance(ingest, dict):
        raise EditionLocatorError("invalid corpus manifest structure")
    raw_skip_files = ingest.get("skip_files")
    if not isinstance(raw_skip_files, list) or not all(
        isinstance(value, str) and value for value in raw_skip_files
    ):
        raise EditionLocatorError("manifest skip_files are invalid")
    manifest_index = {
        str(item["chunk_id"]): item
        for item in manifest_chunks
        if isinstance(item, dict) and isinstance(item.get("chunk_id"), str)
    }
    if len(manifest_index) != len(manifest_chunks):
        raise EditionLocatorError("manifest chunk IDs are missing or duplicated")

    result: list[Mapping[str, object]] = []
    seen: set[str] = set()
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        document = chunk.get("document")
        text = chunk.get("text")
        if not isinstance(chunk_id, str) or chunk_id in seen:
            raise EditionLocatorError(f"private chunk ID is invalid or duplicated: {chunk_id!r}")
        seen.add(chunk_id)
        manifest_chunk = manifest_index.get(chunk_id)
        if manifest_chunk is None:
            raise EditionLocatorError(f"private chunk is absent from manifest: {chunk_id!r}")
        if not isinstance(document, str) or not isinstance(text, str):
            raise EditionLocatorError(f"private chunk {chunk_id!r} has invalid fields")
        expected_text_hash = manifest_chunk.get("text_sha256")
        actual_text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if actual_text_hash != expected_text_hash:
            raise EditionLocatorError(f"private chunk text hash mismatch: {chunk_id!r}")
        if str(manifest_chunk.get("document")) != document:
            raise EditionLocatorError(f"private chunk document mismatch: {chunk_id!r}")
        if not any(skip.casefold() in document.casefold() for skip in raw_skip_files):
            result.append(chunk)

    expected_count = extraction.get("searchable_chunk_count") if isinstance(extraction, dict) else None
    if len(result) != expected_count:
        raise EditionLocatorError(
            f"eligible chunk count mismatch: expected {expected_count}, found {len(result)}"
        )
    return result


def build_typeset_pdf_artifact(
    *,
    pdf_path: Path,
    chunks_path: Path,
    manifest_path: Path,
    extract_pdf_pages: Callable[[Path], Sequence[str]],
) -> dict[str, object]:
    """Build the production locator payload while keeping private text out of it."""

    pdf_hash = sha256_file(pdf_path)
    if pdf_hash != TYPESET_PDF_SHA256:
        raise EditionLocatorError(
            f"PDF SHA-256 mismatch: expected {TYPESET_PDF_SHA256}, found {pdf_hash}"
        )
    manifest_hash = sha256_file(manifest_path)
    if manifest_hash != TYPESET_PDF_MANIFEST_SHA256:
        raise EditionLocatorError(
            "corpus manifest SHA-256 mismatch: "
            f"expected {TYPESET_PDF_MANIFEST_SHA256}, found {manifest_hash}"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks_bytes = chunks_path.read_bytes()
    chunks_hash = hashlib.sha256(chunks_bytes).hexdigest()
    if chunks_hash != manifest.get("chunks_sha256"):
        raise EditionLocatorError(
            f"private chunks SHA-256 mismatch: expected {manifest.get('chunks_sha256')}, "
            f"found {chunks_hash}"
        )
    chunks = json.loads(chunks_bytes)
    if not isinstance(chunks, list) or not isinstance(manifest, dict):
        raise EditionLocatorError("private chunks or manifest have invalid JSON structure")
    corpus_chunks = eligible_chunks(chunks, manifest)

    page_texts = list(extract_pdf_pages(pdf_path))
    pdf = NormalizedPdf(page_texts)
    if pdf.page_count != TYPESET_PDF_PAGE_COUNT:
        raise EditionLocatorError(
            f"PDF page count mismatch: expected {TYPESET_PDF_PAGE_COUNT}, found {pdf.page_count}"
        )

    records: list[dict[str, object]] = []
    minimum_page_by_document: dict[str, int] = {}
    previous_end_by_document: dict[str, int] = {}
    for chunk in corpus_chunks:
        chunk_id = str(chunk["chunk_id"])
        document = str(chunk["document"])
        minimum_page = minimum_page_by_document.get(document, 1)
        try:
            match = locate_chunk(
                str(chunk["text"]),
                pdf,
                minimum_physical_page=minimum_page,
            )
        except EditionLocatorError as exc:
            raise EditionLocatorError(f"{chunk_id}: {exc}") from exc

        previous_end = previous_end_by_document.get(document)
        if previous_end is not None and match.physical_page_end < previous_end:
            raise EditionLocatorError(
                f"{chunk_id}: mapped end page {match.physical_page_end} regresses "
                f"behind {previous_end}"
            )
        minimum_page_by_document[document] = match.physical_page_start
        previous_end_by_document[document] = match.physical_page_end
        if match.matched_anchor_count == match.sampled_anchor_count:
            confidence = "high"
        elif match.matched_anchor_count >= 4:
            confidence = "medium"
        else:
            confidence = "review_required"
        records.append(
            {
                "chunk_id": chunk_id,
                "edition_id": TYPESET_PDF_EDITION_ID,
                "label_start": typeset_page_label(match.physical_page_start),
                "label_end": typeset_page_label(match.physical_page_end),
                "physical_page_start": match.physical_page_start,
                "physical_page_end": match.physical_page_end,
                "confidence": confidence,
                "method": "six_exact_12_token_anchors_dense_boundaries_monotonic_v1",
                "matched_anchor_count": match.matched_anchor_count,
                "sampled_anchor_count": match.sampled_anchor_count,
                "repeated_anchor_count": match.repeated_anchor_count,
            }
        )

    artifact: dict[str, object] = {
        "schema": LOCATOR_SCHEMA,
        "edition": {
            "edition_id": TYPESET_PDF_EDITION_ID,
            "display_name": TYPESET_PDF_DISPLAY_NAME,
            "locator_kind": "page",
            "source_asset_sha256": TYPESET_PDF_SHA256,
            "corpus_manifest_sha256": TYPESET_PDF_MANIFEST_SHA256,
            "mapping_version": MAPPING_VERSION,
            "status": "verified",
            "physical_page_count": TYPESET_PDF_PAGE_COUNT,
        },
        "locators": records,
    }
    validate_text_free_artifact(artifact, expected_chunk_ids=[str(c["chunk_id"]) for c in corpus_chunks])
    return artifact


def validate_text_free_artifact(
    artifact: Mapping[str, object],
    *,
    expected_chunk_ids: Sequence[str],
) -> None:
    """Reject accidental prose-bearing fields and mechanically invalid locators."""

    if artifact.get("schema") != LOCATOR_SCHEMA:
        raise EditionLocatorError("locator artifact schema is invalid")
    edition = artifact.get("edition")
    locators = artifact.get("locators")
    if not isinstance(edition, dict) or not isinstance(locators, list):
        raise EditionLocatorError("locator artifact structure is invalid")
    allowed_edition_fields = {
        "edition_id",
        "display_name",
        "locator_kind",
        "source_asset_sha256",
        "corpus_manifest_sha256",
        "mapping_version",
        "status",
        "physical_page_count",
    }
    allowed_locator_fields = {
        "chunk_id",
        "edition_id",
        "label_start",
        "label_end",
        "physical_page_start",
        "physical_page_end",
        "confidence",
        "method",
        "matched_anchor_count",
        "sampled_anchor_count",
        "repeated_anchor_count",
    }
    if set(edition) != allowed_edition_fields:
        raise EditionLocatorError("locator edition metadata fields are not allowlisted")
    found_ids: list[str] = []
    last_start_by_document: dict[str, int] = {}
    for index, locator in enumerate(locators):
        if not isinstance(locator, dict) or set(locator) != allowed_locator_fields:
            raise EditionLocatorError(f"locator {index} fields are not allowlisted")
        chunk_id = locator.get("chunk_id")
        start = locator.get("physical_page_start")
        end = locator.get("physical_page_end")
        if not isinstance(chunk_id, str) or not isinstance(start, int) or not isinstance(end, int):
            raise EditionLocatorError(f"locator {index} has invalid identity or page values")
        if not 1 <= start <= end <= TYPESET_PDF_PAGE_COUNT:
            raise EditionLocatorError(f"locator {chunk_id!r} has an invalid page span")
        if locator.get("label_start") != typeset_page_label(start):
            raise EditionLocatorError(f"locator {chunk_id!r} has an invalid start label")
        if locator.get("label_end") != typeset_page_label(end):
            raise EditionLocatorError(f"locator {chunk_id!r} has an invalid end label")
        document = chunk_id.rsplit("_", 1)[0]
        previous = last_start_by_document.get(document)
        if previous is not None and start < previous:
            raise EditionLocatorError(f"locator {chunk_id!r} is not monotonic")
        last_start_by_document[document] = start
        found_ids.append(chunk_id)
    if found_ids != list(expected_chunk_ids):
        raise EditionLocatorError("locator chunk IDs do not exactly match eligible corpus order")
