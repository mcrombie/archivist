"""Local evidence-presence and absence policy for Answer Mode.

This module deliberately has no retrieval, model, or persistence dependencies.  Callers pass the
complete retrieval-eligible chunk set, the manifest/store facts needed to certify that set, and
trusted target surfaces copied from the user's question.  Planner-generated synonyms may be used
for discovery elsewhere, but must never be passed as trusted targets here.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum


ANCHOR_NORMALIZER_VERSION = "unicode-nfkc-casefold-anchor-v1"
EVIDENCE_POLICY_VERSION = "evidence-gate-v1"
EVIDENCE_DIAGNOSTICS_SCHEMA = "archivist.evidence_policy_diagnostics/1"
WEAK_MATCH_WINDOW_TOKENS = 12

_APOSTROPHES = frozenset(
    {
        "\u02bc",  # modifier letter apostrophe
        "\u055a",  # Armenian apostrophe
        "\u2018",  # left single quotation mark
        "\u2019",  # right single quotation mark
        "\u201b",  # single high-reversed-9 quotation mark
        "\u2032",  # prime
        "\uff07",  # fullwidth apostrophe
    }
)
_LEXEME_PATTERN = re.compile(r"[^\W_]+(?:'[^\W_]+)*", flags=re.UNICODE)
_LETTER_OR_NUMBER_RUN_PATTERN = re.compile(
    r"[^\W\d_]+|\d+",
    flags=re.UNICODE,
)
_DOTTED_INITIALISM_PATTERN = re.compile(
    r"(?<!\w)(?:[^\W\d_]\.)+[^\W\d_]\.?(?!\w)",
    flags=re.UNICODE,
)
_UNDOTTED_INITIALISM_PATTERN = re.compile(
    r"(?<!\w)[^\W_]{2,10}(?!\w)",
    flags=re.UNICODE,
)
_MACHINE_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}")


class AnchorMatchKind(StrEnum):
    """How a trusted anchor relates to one chunk."""

    STRONG = "strong"
    FULL = "strong"
    WEAK = "weak"
    PARTIAL_TOKEN_COLLISION = "partial_token_collision"
    PARTIAL = "partial_token_collision"
    NONE = "none"


class AnchorMatchRule(StrEnum):
    FULL_TOKEN_SEQUENCE = "full_token_sequence"
    TWELVE_TOKEN_WINDOW = "twelve_token_window"
    MECHANICAL_INITIALISM = "mechanical_initialism"
    PARTIAL_TOKEN_COLLISION = "partial_token_collision"
    NONE = "none"


class EvidenceTargetRole(StrEnum):
    SUBJECT = "subject"
    FACET = "facet"


class EvidenceLane(StrEnum):
    DIRECT = "direct"
    BROADER_RELATED = "broader_related"
    ANALOGUE = "analogue"
    GENERIC_SEMANTIC = "generic_semantic"


class EvidenceDecision(StrEnum):
    DIRECT_ANSWER = "direct_answer"
    PARTIAL_ANSWER = "partial_answer"
    QUALIFIED_NEAR_MATCH = "qualified_near_match"
    CLEAN_ABSTENTION = "clean_abstention"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class AnchorMatch:
    kind: AnchorMatchKind
    rule: AnchorMatchRule


@dataclass(frozen=True, slots=True)
class CorpusIntegrity:
    """Text-free result of comparing the scan corpus with manifest/store identity."""

    expected_manifest_sha256: str | None
    loaded_manifest_sha256: str | None
    manifest_eligible_chunk_ids_sha256: str
    loaded_eligible_chunk_ids_sha256: str
    expected_eligible_chunk_count: int
    expected_collection_count: int
    loaded_eligible_chunk_count: int
    collection_count: int
    failure_codes: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failure_codes

    def with_failure(
        self,
        code: str,
        *,
        loaded_chunk_count: int | None = None,
        loaded_chunk_ids_sha256: str | None = None,
    ) -> CorpusIntegrity:
        failures = _ordered_unique((*self.failure_codes, code))
        return replace(
            self,
            loaded_eligible_chunk_count=(
                self.loaded_eligible_chunk_count
                if loaded_chunk_count is None
                else loaded_chunk_count
            ),
            loaded_eligible_chunk_ids_sha256=(
                self.loaded_eligible_chunk_ids_sha256
                if loaded_chunk_ids_sha256 is None
                else loaded_chunk_ids_sha256
            ),
            failure_codes=failures,
        )

    def as_diagnostics(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "expected_manifest_sha256": self.expected_manifest_sha256,
            "loaded_manifest_sha256": self.loaded_manifest_sha256,
            "manifest_eligible_chunk_ids_sha256": (
                self.manifest_eligible_chunk_ids_sha256
            ),
            "loaded_eligible_chunk_ids_sha256": (
                self.loaded_eligible_chunk_ids_sha256
            ),
            "expected_eligible_chunk_count": self.expected_eligible_chunk_count,
            "expected_collection_count": self.expected_collection_count,
            "loaded_eligible_chunk_count": self.loaded_eligible_chunk_count,
            "collection_count": self.collection_count,
            "failure_codes": list(self.failure_codes),
        }


@dataclass(frozen=True, slots=True)
class ChunkAnchorMatch:
    chunk_id: str
    kind: AnchorMatchKind
    rule: AnchorMatchRule


@dataclass(frozen=True, slots=True)
class EvidenceTargetScan:
    """Text-free scan result for one trusted user-surface target."""

    target_id: str
    role: EvidenceTargetRole
    target_sha256: str
    target_character_count: int
    anchor_token_count: int
    absence_checkable: bool
    scanned_chunk_count: int
    matches: tuple[ChunkAnchorMatch, ...]
    integrity: CorpusIntegrity

    @property
    def strong_chunk_ids(self) -> tuple[str, ...]:
        return tuple(
            match.chunk_id
            for match in self.matches
            if match.kind is AnchorMatchKind.STRONG
        )

    @property
    def weak_chunk_ids(self) -> tuple[str, ...]:
        return tuple(
            match.chunk_id
            for match in self.matches
            if match.kind is AnchorMatchKind.WEAK
        )

    @property
    def partial_chunk_ids(self) -> tuple[str, ...]:
        return tuple(
            match.chunk_id
            for match in self.matches
            if match.kind is AnchorMatchKind.PARTIAL_TOKEN_COLLISION
        )

    @property
    def direct_chunk_ids(self) -> tuple[str, ...]:
        return tuple(
            match.chunk_id
            for match in self.matches
            if match.kind in {AnchorMatchKind.STRONG, AnchorMatchKind.WEAK}
        )

    @property
    def direct_present(self) -> bool:
        return bool(self.direct_chunk_ids)

    @property
    def certified_direct_absence(self) -> bool:
        return (
            self.absence_checkable
            and self.integrity.passed
            and not self.direct_present
        )

    def as_diagnostics(self) -> dict[str, object]:
        return {
            "target_id": self.target_id,
            "role": self.role.value,
            "target_sha256": self.target_sha256,
            "target_character_count": self.target_character_count,
            "anchor_token_count": self.anchor_token_count,
            "absence_checkable": self.absence_checkable,
            "scanned_chunk_count": self.scanned_chunk_count,
            "strong_hit_count": len(self.strong_chunk_ids),
            "weak_hit_count": len(self.weak_chunk_ids),
            "partial_token_collision_count": len(self.partial_chunk_ids),
            "mechanical_initialism_hit_count": sum(
                match.rule is AnchorMatchRule.MECHANICAL_INITIALISM
                for match in self.matches
            ),
            "certified_direct_absence": self.certified_direct_absence,
        }


@dataclass(frozen=True, slots=True)
class BroaderRelatedScan:
    """Text-free certificate for bounded broader material."""

    broader_target_sha256: str
    related_probe_sha256: tuple[str, ...]
    scanned_chunk_ids_sha256: str
    broader_strong_chunk_ids: tuple[str, ...]
    qualifying_pairs: tuple[tuple[str, str], ...]

    @property
    def qualified_broader_chunk_ids(self) -> tuple[str, ...]:
        qualifying = {broader_id for broader_id, _ in self.qualifying_pairs}
        return tuple(
            chunk_id
            for chunk_id in self.broader_strong_chunk_ids
            if chunk_id in qualifying
        )

    @property
    def supporting_probe_chunk_ids(self) -> tuple[str, ...]:
        return _ordered_unique(
            probe_id for _, probe_id in self.qualifying_pairs
        )

    @property
    def qualified_chunk_ids(self) -> tuple[str, ...]:
        return _ordered_unique(
            (
                *self.qualified_broader_chunk_ids,
                *self.supporting_probe_chunk_ids,
            )
        )

    def as_diagnostics(self) -> dict[str, object]:
        return {
            "broader_target_sha256": self.broader_target_sha256,
            "related_probe_sha256": list(self.related_probe_sha256),
            "scanned_chunk_ids_sha256": self.scanned_chunk_ids_sha256,
            "broader_strong_hit_count": len(self.broader_strong_chunk_ids),
            "qualified_broader_hit_count": len(
                self.qualified_broader_chunk_ids
            ),
            "qualifying_pair_count": len(self.qualifying_pairs),
            "supporting_probe_chunk_count": len(
                self.supporting_probe_chunk_ids
            ),
        }


@dataclass(frozen=True, slots=True)
class EvidenceLaneAssignment:
    source_number: int
    chunk_id: str
    lane: EvidenceLane

    def as_diagnostics(self) -> dict[str, object]:
        return {
            "source_number": self.source_number,
            "chunk_id": self.chunk_id,
            "lane": self.lane.value,
        }


@dataclass(frozen=True, slots=True)
class EvidenceGateResult:
    decision: EvidenceDecision
    certified_direct_absence: bool
    premise_correction_required: bool
    relationship_chunk_ids: tuple[str, ...]
    allowed_source_numbers: tuple[int, ...]
    suppressed_source_numbers: tuple[int, ...]
    lane_assignments: tuple[EvidenceLaneAssignment, ...]
    rules_fired: tuple[str, ...]
    integrity: CorpusIntegrity

    @property
    def skip_answer_generation(self) -> bool:
        return self.decision is EvidenceDecision.CLEAN_ABSTENTION


@dataclass(frozen=True, slots=True)
class _AnchorParts:
    tokens: tuple[str, ...]
    lexemes: tuple[str, ...]


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _normalize_unicode(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = "".join(
        "'" if character in _APOSTROPHES else character
        for character in normalized
    )
    normalized = "".join(
        " "
        if unicodedata.category(character) == "Pd"
        or character in {"\u2212", "\ufe63"}
        else character
        for character in normalized
    )
    normalized = normalized.casefold()
    return _DOTTED_INITIALISM_PATTERN.sub(
        lambda match: match.group(0).replace(".", ""),
        normalized,
    )


def _strip_possessive(lexeme: str) -> str:
    if lexeme.endswith("'s") and len(lexeme) > 2:
        return lexeme[:-2]
    return lexeme


def _anchor_parts(value: str) -> _AnchorParts:
    if not isinstance(value, str):
        raise TypeError("anchor value must be a string")
    lexemes = tuple(
        stripped
        for raw in _LEXEME_PATTERN.findall(_normalize_unicode(value))
        if (stripped := _strip_possessive(raw))
    )
    tokens: list[str] = []
    for lexeme in lexemes:
        if "'" in lexeme:
            tokens.append(lexeme)
            continue
        pieces = _LETTER_OR_NUMBER_RUN_PATTERN.findall(lexeme)
        tokens.extend(pieces or (lexeme,))
    return _AnchorParts(tokens=tuple(tokens), lexemes=lexemes)


def tokenize_anchor(value: str) -> tuple[str, ...]:
    """Return conservative normalized anchor tokens, including short numerics."""

    return _anchor_parts(value).tokens


def normalize_anchor(value: str) -> str:
    """Return the stable space-joined form used for matching and target hashing."""

    return " ".join(tokenize_anchor(value))


def _contains_sequence(
    haystack: Sequence[str],
    needle: Sequence[str],
) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(
        tuple(haystack[start : start + width]) == tuple(needle)
        for start in range(len(haystack) - width + 1)
    )


def _contains_all_within_window(
    haystack: Sequence[str],
    needle: Sequence[str],
    window_size: int,
) -> bool:
    required = Counter(needle)
    if not required or len(needle) > window_size:
        return False
    for start in range(len(haystack)):
        window = Counter(haystack[start : start + window_size])
        if all(window[token] >= count for token, count in required.items()):
            return True
    return False


def _mechanical_initialism(tokens: Sequence[str]) -> str | None:
    if len(tokens) < 2:
        return None
    pieces: list[str] = []
    for token in tokens:
        if token.isdecimal():
            pieces.append(token)
        elif token:
            pieces.append(token[0])
    initialism = "".join(pieces)
    return initialism if len(initialism) >= 2 else None


def _explicit_initialisms(value: str) -> frozenset[str]:
    """Return initialisms whose uppercase/dot form is explicit in source text."""

    normalized = unicodedata.normalize("NFKC", value)
    candidates = (
        *(match.group(0) for match in _DOTTED_INITIALISM_PATTERN.finditer(normalized)),
        *(match.group(0) for match in _UNDOTTED_INITIALISM_PATTERN.finditer(normalized)),
    )
    explicit: set[str] = set()
    for candidate in candidates:
        compact = candidate.replace(".", "")
        if (
            len(compact) >= 2
            and any(character.isalpha() for character in compact)
            and all(
                character.isupper() or character.isdecimal()
                for character in compact
            )
        ):
            explicit.add(compact)
    return frozenset(explicit)


def classify_anchor_match(
    anchor: str,
    chunk_text: str,
    *,
    weak_window_tokens: int = WEAK_MATCH_WINDOW_TOKENS,
) -> AnchorMatch:
    """Classify a trusted anchor against one chunk without semantic inference."""

    if weak_window_tokens <= 0:
        raise ValueError("weak_window_tokens must be greater than zero")
    anchor_parts = _anchor_parts(anchor)
    if not anchor_parts.tokens:
        raise ValueError("anchor must contain at least one letter or number token")
    chunk_parts = _anchor_parts(chunk_text)

    if _contains_sequence(chunk_parts.tokens, anchor_parts.tokens):
        return AnchorMatch(
            AnchorMatchKind.STRONG,
            AnchorMatchRule.FULL_TOKEN_SEQUENCE,
        )

    if _contains_all_within_window(
        chunk_parts.tokens,
        anchor_parts.tokens,
        weak_window_tokens,
    ):
        return AnchorMatch(
            AnchorMatchKind.WEAK,
            AnchorMatchRule.TWELVE_TOKEN_WINDOW,
        )

    initialism = _mechanical_initialism(anchor_parts.tokens)
    if (
        initialism is not None
        and initialism.upper() in _explicit_initialisms(chunk_text)
    ):
        return AnchorMatch(
            AnchorMatchKind.WEAK,
            AnchorMatchRule.MECHANICAL_INITIALISM,
        )

    if set(anchor_parts.tokens).intersection(chunk_parts.tokens):
        return AnchorMatch(
            AnchorMatchKind.PARTIAL_TOKEN_COLLISION,
            AnchorMatchRule.PARTIAL_TOKEN_COLLISION,
        )

    return AnchorMatch(AnchorMatchKind.NONE, AnchorMatchRule.NONE)


def _chunk_scope_ids(
    eligible_chunks: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    scope_ids: list[str] = []
    for index, chunk in enumerate(eligible_chunks):
        if isinstance(chunk, Mapping):
            chunk_id = chunk.get("chunk_id")
            if isinstance(chunk_id, str) and chunk_id.strip():
                scope_ids.append(chunk_id)
                continue
        scope_ids.append(f"\x00invalid:{index}")
    return tuple(scope_ids)


def _ids_sha256(chunk_ids: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for chunk_id in sorted(chunk_ids):
        encoded = chunk_id.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _normalized_sha256(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().casefold()


def _nonnegative_int(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def assess_corpus_integrity(
    eligible_chunks: Sequence[Mapping[str, object]],
    *,
    manifest_eligible_chunk_ids: Iterable[str],
    expected_manifest_sha256: str,
    loaded_manifest_sha256: str,
    expected_collection_count: int,
    collection_count: int,
) -> CorpusIntegrity:
    """Compare loaded eligible chunks with the exact manifest and collection identity."""

    expected_collection_count = _nonnegative_int(
        expected_collection_count,
        name="expected_collection_count",
    )
    collection_count = _nonnegative_int(
        collection_count,
        name="collection_count",
    )
    manifest_ids_raw = tuple(manifest_eligible_chunk_ids)
    manifest_ids = tuple(
        value
        for value in manifest_ids_raw
        if isinstance(value, str) and value.strip()
    )
    scope_ids = _chunk_scope_ids(eligible_chunks)
    valid_loaded_ids = tuple(
        str(chunk.get("chunk_id"))
        for chunk in eligible_chunks
        if isinstance(chunk, Mapping)
        and isinstance(chunk.get("chunk_id"), str)
        and str(chunk.get("chunk_id")).strip()
    )
    failures: list[str] = []

    expected_hash = _normalized_sha256(expected_manifest_sha256)
    loaded_hash = _normalized_sha256(loaded_manifest_sha256)
    if expected_hash is None or loaded_hash is None:
        failures.append("manifest_identity_missing")
    elif expected_hash != loaded_hash:
        failures.append("manifest_identity_mismatch")

    if len(manifest_ids) != len(manifest_ids_raw):
        failures.append("invalid_manifest_chunk_id")
    if len(set(manifest_ids)) != len(manifest_ids):
        failures.append("duplicate_manifest_chunk_id")
    if any(
        not isinstance(chunk, Mapping)
        or not isinstance(chunk.get("chunk_id"), str)
        or not str(chunk.get("chunk_id")).strip()
        or not isinstance(chunk.get("text"), str)
        for chunk in eligible_chunks
    ):
        failures.append("invalid_loaded_chunk")
    if len(set(valid_loaded_ids)) != len(valid_loaded_ids):
        failures.append("duplicate_loaded_chunk_id")
    if set(valid_loaded_ids) != set(manifest_ids):
        failures.append("eligible_chunk_ids_mismatch")
    if len(eligible_chunks) != len(manifest_ids):
        failures.append("loaded_chunk_count_mismatch")
    if expected_collection_count != len(manifest_ids):
        failures.append("manifest_collection_count_mismatch")
    if collection_count != expected_collection_count:
        failures.append("collection_count_mismatch")

    return CorpusIntegrity(
        expected_manifest_sha256=expected_hash,
        loaded_manifest_sha256=loaded_hash,
        manifest_eligible_chunk_ids_sha256=_ids_sha256(manifest_ids),
        loaded_eligible_chunk_ids_sha256=_ids_sha256(scope_ids),
        expected_eligible_chunk_count=len(manifest_ids),
        expected_collection_count=expected_collection_count,
        loaded_eligible_chunk_count=len(eligible_chunks),
        collection_count=collection_count,
        failure_codes=_ordered_unique(failures),
    )


def _integrity_for_scan(
    eligible_chunks: Sequence[Mapping[str, object]],
    integrity: CorpusIntegrity,
) -> CorpusIntegrity:
    scope_ids = _chunk_scope_ids(eligible_chunks)
    scope_digest = _ids_sha256(scope_ids)
    result = integrity
    if (
        len(eligible_chunks) != integrity.loaded_eligible_chunk_count
        or scope_digest != integrity.loaded_eligible_chunk_ids_sha256
    ):
        result = result.with_failure(
            "scan_scope_mismatch",
            loaded_chunk_count=len(eligible_chunks),
            loaded_chunk_ids_sha256=scope_digest,
        )
    valid_ids: list[str] = []
    invalid = False
    for chunk in eligible_chunks:
        if (
            not isinstance(chunk, Mapping)
            or not isinstance(chunk.get("chunk_id"), str)
            or not str(chunk.get("chunk_id")).strip()
            or not isinstance(chunk.get("text"), str)
        ):
            invalid = True
            continue
        valid_ids.append(str(chunk["chunk_id"]))
    if invalid:
        result = result.with_failure("invalid_loaded_chunk")
    if len(valid_ids) != len(set(valid_ids)):
        result = result.with_failure("duplicate_loaded_chunk_id")
    return result


def _validate_target_id(target_id: str) -> None:
    if not isinstance(target_id, str) or not _MACHINE_ID_PATTERN.fullmatch(
        target_id
    ):
        raise ValueError(
            "target_id must be a compact machine ID of at most 64 characters"
        )


def scan_evidence_target(
    target_id: str,
    query_surface_span: str,
    eligible_chunks: Sequence[Mapping[str, object]],
    *,
    absence_checkable: bool,
    corpus_integrity: CorpusIntegrity,
    role: EvidenceTargetRole | str = EvidenceTargetRole.SUBJECT,
) -> EvidenceTargetScan:
    """Scan every supplied eligible chunk for one trusted user-surface target."""

    _validate_target_id(target_id)
    if not isinstance(absence_checkable, bool):
        raise TypeError("absence_checkable must be a boolean")
    role = EvidenceTargetRole(role)
    anchor_tokens = tokenize_anchor(query_surface_span)
    if not anchor_tokens:
        raise ValueError("query_surface_span must contain a trusted anchor")
    effective_integrity = _integrity_for_scan(
        eligible_chunks,
        corpus_integrity,
    )

    matches: list[ChunkAnchorMatch] = []
    for chunk in eligible_chunks:
        if (
            not isinstance(chunk, Mapping)
            or not isinstance(chunk.get("chunk_id"), str)
            or not str(chunk.get("chunk_id")).strip()
            or not isinstance(chunk.get("text"), str)
        ):
            continue
        match = classify_anchor_match(
            query_surface_span,
            str(chunk["text"]),
        )
        if match.kind is AnchorMatchKind.NONE:
            continue
        matches.append(
            ChunkAnchorMatch(
                chunk_id=str(chunk["chunk_id"]),
                kind=match.kind,
                rule=match.rule,
            )
        )

    normalized_target = " ".join(anchor_tokens)
    return EvidenceTargetScan(
        target_id=target_id,
        role=role,
        target_sha256=hashlib.sha256(
            normalized_target.encode("utf-8")
        ).hexdigest(),
        target_character_count=len(query_surface_span),
        anchor_token_count=len(anchor_tokens),
        absence_checkable=absence_checkable,
        scanned_chunk_count=len(eligible_chunks),
        matches=tuple(matches),
        integrity=effective_integrity,
    )


# The alias names the trust boundary explicitly for orchestration code.
scan_trusted_target = scan_evidence_target


def build_immediate_neighbor_map(
    eligible_chunks: Sequence[Mapping[str, object]],
) -> dict[str, tuple[str, ...]]:
    """Build same-document immediate neighbors from corpus-ordered chunks."""

    neighbors: dict[str, set[str]] = {}
    previous_by_document: dict[str, str] = {}
    for chunk in eligible_chunks:
        if not isinstance(chunk, Mapping):
            continue
        chunk_id = chunk.get("chunk_id")
        document = chunk.get("document")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            continue
        neighbors.setdefault(chunk_id, set())
        if not isinstance(document, str) or not document:
            continue
        previous = previous_by_document.get(document)
        if previous is not None:
            neighbors[chunk_id].add(previous)
            neighbors.setdefault(previous, set()).add(chunk_id)
        previous_by_document[document] = chunk_id
    return {
        chunk_id: tuple(sorted(related_ids))
        for chunk_id, related_ids in neighbors.items()
    }


def _symmetric_neighbor_sets(
    immediate_neighbors: Mapping[str, Iterable[str]] | None,
) -> dict[str, set[str]]:
    neighbors: dict[str, set[str]] = {}
    if immediate_neighbors is None:
        return neighbors
    for raw_chunk_id, raw_related in immediate_neighbors.items():
        chunk_id = str(raw_chunk_id)
        related_values: Iterable[str]
        if isinstance(raw_related, str):
            related_values = (raw_related,)
        else:
            related_values = raw_related
        neighbors.setdefault(chunk_id, set())
        for raw_neighbor_id in related_values:
            neighbor_id = str(raw_neighbor_id)
            neighbors[chunk_id].add(neighbor_id)
            neighbors.setdefault(neighbor_id, set()).add(chunk_id)
    return neighbors


def relationship_evidence_chunk_ids(
    subject_scan: EvidenceTargetScan,
    facet_scan: EvidenceTargetScan,
    *,
    immediate_neighbors: Mapping[str, Iterable[str]] | None = None,
) -> tuple[str, ...]:
    """Return subject/facet chunks that co-occur in one chunk or an immediate neighbor."""

    if (
        subject_scan.integrity.loaded_eligible_chunk_ids_sha256
        != facet_scan.integrity.loaded_eligible_chunk_ids_sha256
    ):
        return ()
    neighbors = _symmetric_neighbor_sets(immediate_neighbors)
    related: list[str] = []
    for subject_id in subject_scan.direct_chunk_ids:
        for facet_id in facet_scan.direct_chunk_ids:
            if (
                subject_id == facet_id
                or facet_id in neighbors.get(subject_id, set())
            ):
                related.extend((subject_id, facet_id))
    return _ordered_unique(related)


def scan_broader_related(
    broader_term: str,
    related_probes: Sequence[str],
    eligible_chunks: Sequence[Mapping[str, object]],
    *,
    immediate_neighbors: Mapping[str, Iterable[str]] | None = None,
) -> BroaderRelatedScan:
    """Certify broader material only with an exact broader term plus an exact probe."""

    broader_tokens = tokenize_anchor(broader_term)
    if not broader_tokens:
        raise ValueError("broader_term must contain at least one anchor token")
    broader_normalized = " ".join(broader_tokens)
    probe_by_normalized: dict[str, str] = {}
    for probe in related_probes:
        normalized = normalize_anchor(probe)
        if normalized and normalized != broader_normalized:
            probe_by_normalized.setdefault(normalized, probe)

    valid_chunks = [
        chunk
        for chunk in eligible_chunks
        if isinstance(chunk, Mapping)
        and isinstance(chunk.get("chunk_id"), str)
        and str(chunk.get("chunk_id")).strip()
        and isinstance(chunk.get("text"), str)
    ]
    broader_ids: list[str] = []
    probe_ids: list[str] = []
    for chunk in valid_chunks:
        chunk_id = str(chunk["chunk_id"])
        chunk_text = str(chunk["text"])
        if (
            classify_anchor_match(broader_term, chunk_text).kind
            is AnchorMatchKind.STRONG
        ):
            broader_ids.append(chunk_id)
        if any(
            classify_anchor_match(probe, chunk_text).kind
            is AnchorMatchKind.STRONG
            for probe in probe_by_normalized.values()
        ):
            probe_ids.append(chunk_id)

    if immediate_neighbors is None:
        immediate_neighbors = build_immediate_neighbor_map(eligible_chunks)
    neighbors = _symmetric_neighbor_sets(immediate_neighbors)
    qualifying_pairs: list[tuple[str, str]] = []
    for broader_id in broader_ids:
        for probe_id in probe_ids:
            if (
                broader_id == probe_id
                or probe_id in neighbors.get(broader_id, set())
            ):
                qualifying_pairs.append((broader_id, probe_id))

    return BroaderRelatedScan(
        broader_target_sha256=hashlib.sha256(
            broader_normalized.encode("utf-8")
        ).hexdigest(),
        related_probe_sha256=tuple(
            hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            for normalized in probe_by_normalized
        ),
        scanned_chunk_ids_sha256=_ids_sha256(
            _chunk_scope_ids(eligible_chunks)
        ),
        broader_strong_chunk_ids=tuple(broader_ids),
        qualifying_pairs=tuple(qualifying_pairs),
    )


def _selected_chunk_ids(
    selected_chunks: Sequence[str | Mapping[str, object]],
) -> tuple[str, ...]:
    chunk_ids: list[str] = []
    for selected in selected_chunks:
        raw_id = (
            selected
            if isinstance(selected, str)
            else selected.get("chunk_id")
            if isinstance(selected, Mapping)
            else None
        )
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise ValueError("every selected chunk must have a non-empty chunk_id")
        chunk_ids.append(raw_id)
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("selected chunks must not contain duplicate chunk IDs")
    return tuple(chunk_ids)


def classify_evidence_lanes(
    selected_chunks: Sequence[str | Mapping[str, object]],
    *,
    subject_scan: EvidenceTargetScan,
    facet_scan: EvidenceTargetScan | None = None,
    broader_related_scan: BroaderRelatedScan | None = None,
    analogue_chunk_ids: Iterable[str] = (),
    immediate_neighbors: Mapping[str, Iterable[str]] | None = None,
) -> tuple[EvidenceLaneAssignment, ...]:
    """Assign one non-promoting evidence lane to each selected candidate."""

    chunk_ids = _selected_chunk_ids(selected_chunks)
    direct_ids = set(subject_scan.direct_chunk_ids)
    if immediate_neighbors is not None:
        for chunk_id in subject_scan.direct_chunk_ids:
            direct_ids.update(
                str(neighbor_id)
                for neighbor_id in immediate_neighbors.get(chunk_id, ())
            )
    if facet_scan is not None:
        direct_ids.update(
            relationship_evidence_chunk_ids(
                subject_scan,
                facet_scan,
                immediate_neighbors=immediate_neighbors,
            )
        )
    broader_ids = (
        set(broader_related_scan.qualified_chunk_ids)
        if broader_related_scan is not None
        else set()
    )
    analogue_ids = {str(chunk_id) for chunk_id in analogue_chunk_ids}

    assignments: list[EvidenceLaneAssignment] = []
    for source_number, chunk_id in enumerate(chunk_ids, start=1):
        if chunk_id in direct_ids:
            lane = EvidenceLane.DIRECT
        elif chunk_id in broader_ids:
            lane = EvidenceLane.BROADER_RELATED
        elif chunk_id in analogue_ids:
            lane = EvidenceLane.ANALOGUE
        else:
            lane = EvidenceLane.GENERIC_SEMANTIC
        assignments.append(
            EvidenceLaneAssignment(
                source_number=source_number,
                chunk_id=chunk_id,
                lane=lane,
            )
        )
    return tuple(assignments)


def _allowed_and_suppressed_sources(
    decision: EvidenceDecision,
    assignments: tuple[EvidenceLaneAssignment, ...],
    *,
    premise_contradiction_chunk_ids: set[str],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if decision is EvidenceDecision.DIRECT_ANSWER:
        if premise_contradiction_chunk_ids:
            allowed = {
                assignment.source_number
                for assignment in assignments
                if assignment.chunk_id in premise_contradiction_chunk_ids
                or assignment.lane
                in {EvidenceLane.DIRECT, EvidenceLane.BROADER_RELATED}
            }
        else:
            allowed = {
                assignment.source_number
                for assignment in assignments
                if assignment.lane
                in {EvidenceLane.DIRECT, EvidenceLane.BROADER_RELATED}
            }
    elif decision is EvidenceDecision.PARTIAL_ANSWER:
        allowed = {
            assignment.source_number
            for assignment in assignments
            if assignment.lane
            in {EvidenceLane.DIRECT, EvidenceLane.BROADER_RELATED}
        }
    elif decision is EvidenceDecision.QUALIFIED_NEAR_MATCH:
        allowed = {
            assignment.source_number
            for assignment in assignments
            if assignment.lane is EvidenceLane.BROADER_RELATED
        }
    else:
        allowed = set()
    allowed_numbers = tuple(
        assignment.source_number
        for assignment in assignments
        if assignment.source_number in allowed
    )
    suppressed_numbers = tuple(
        assignment.source_number
        for assignment in assignments
        if assignment.source_number not in allowed
    )
    return allowed_numbers, suppressed_numbers


def decide_evidence(
    subject_scan: EvidenceTargetScan,
    *,
    facet_scan: EvidenceTargetScan | None = None,
    lane_assignments: Sequence[EvidenceLaneAssignment] = (),
    broader_related_scan: BroaderRelatedScan | None = None,
    immediate_neighbors: Mapping[str, Iterable[str]] | None = None,
    premise_contradiction_chunk_ids: Iterable[str] = (),
) -> EvidenceGateResult:
    """Apply the evidence-gate precedence rules and fail closed on uncertainty."""

    assignments = tuple(lane_assignments)
    integrity = subject_scan.integrity
    expected_scope = integrity.loaded_eligible_chunk_ids_sha256
    if (
        facet_scan is not None
        and facet_scan.integrity.loaded_eligible_chunk_ids_sha256
        != expected_scope
    ):
        integrity = integrity.with_failure("target_scan_scope_mismatch")
    if (
        broader_related_scan is not None
        and broader_related_scan.scanned_chunk_ids_sha256 != expected_scope
    ):
        integrity = integrity.with_failure("broader_scan_scope_mismatch")

    selected_ids = {assignment.chunk_id for assignment in assignments}
    contradiction_ids = {
        str(chunk_id)
        for chunk_id in premise_contradiction_chunk_ids
        if str(chunk_id)
    }
    if assignments:
        contradiction_ids.intersection_update(selected_ids)

    relationship_ids = (
        ()
        if facet_scan is None
        else relationship_evidence_chunk_ids(
            subject_scan,
            facet_scan,
            immediate_neighbors=immediate_neighbors,
        )
    )
    direct_present = subject_scan.direct_present
    certified_absence = (
        subject_scan.absence_checkable
        and integrity.passed
        and not direct_present
    )
    qualified_broader_ids: set[str] = set()
    if broader_related_scan is not None:
        qualified_broader_ids.update(
            broader_related_scan.qualified_chunk_ids
        )
        if assignments:
            selected_broader_ids = {
                assignment.chunk_id
                for assignment in assignments
                if assignment.lane is EvidenceLane.BROADER_RELATED
            }
            qualified_broader_ids.intersection_update(selected_broader_ids)

    if not integrity.passed:
        decision = EvidenceDecision.INDETERMINATE
        rules = ("corpus_integrity_failed",)
        premise_correction = False
    elif contradiction_ids:
        decision = EvidenceDecision.DIRECT_ANSWER
        rules = ("source_backed_premise_contradiction",)
        premise_correction = True
    elif direct_present and (facet_scan is None or relationship_ids):
        decision = EvidenceDecision.DIRECT_ANSWER
        rules = (
            (
                "direct_subject_evidence"
                if facet_scan is None
                else "direct_subject_and_facet_evidence"
            ),
        )
        premise_correction = False
    elif direct_present:
        decision = EvidenceDecision.PARTIAL_ANSWER
        rules = (
            "direct_subject_evidence",
            "requested_relationship_not_established",
        )
        premise_correction = False
    elif certified_absence and qualified_broader_ids:
        decision = EvidenceDecision.QUALIFIED_NEAR_MATCH
        rules = (
            "certified_direct_absence",
            "qualified_broader_material",
        )
        premise_correction = False
    elif certified_absence:
        decision = EvidenceDecision.CLEAN_ABSTENTION
        rules = (
            "certified_direct_absence",
            "no_safe_related_material",
        )
        premise_correction = False
    else:
        decision = EvidenceDecision.INDETERMINATE
        rules = ("direct_absence_not_certifiable",)
        premise_correction = False

    allowed_numbers, suppressed_numbers = _allowed_and_suppressed_sources(
        decision,
        assignments,
        premise_contradiction_chunk_ids=contradiction_ids,
    )
    return EvidenceGateResult(
        decision=decision,
        certified_direct_absence=certified_absence,
        premise_correction_required=premise_correction,
        relationship_chunk_ids=relationship_ids,
        allowed_source_numbers=allowed_numbers,
        suppressed_source_numbers=suppressed_numbers,
        lane_assignments=assignments,
        rules_fired=rules,
        integrity=integrity,
    )


def evidence_diagnostics(
    result: EvidenceGateResult,
    *,
    subject_scan: EvidenceTargetScan,
    facet_scan: EvidenceTargetScan | None = None,
    broader_related_scan: BroaderRelatedScan | None = None,
) -> dict[str, object]:
    """Build the normal trace payload without target, probe, question, or chunk text."""

    scans = [subject_scan]
    if facet_scan is not None:
        scans.append(facet_scan)
    return {
        "schema": EVIDENCE_DIAGNOSTICS_SCHEMA,
        "policy_version": EVIDENCE_POLICY_VERSION,
        "anchor_normalizer_version": ANCHOR_NORMALIZER_VERSION,
        "weak_match_window_tokens": WEAK_MATCH_WINDOW_TOKENS,
        "corpus": result.integrity.as_diagnostics(),
        "targets": [scan.as_diagnostics() for scan in scans],
        "broader_related": (
            None
            if broader_related_scan is None
            else broader_related_scan.as_diagnostics()
        ),
        "lanes": [
            assignment.as_diagnostics()
            for assignment in result.lane_assignments
        ],
        "decision": {
            "value": result.decision.value,
            "certified_direct_absence": result.certified_direct_absence,
            "premise_correction_required": (
                result.premise_correction_required
            ),
            "relationship_chunk_ids": list(
                result.relationship_chunk_ids
            ),
            "allowed_source_numbers": list(result.allowed_source_numbers),
            "suppressed_source_numbers": list(
                result.suppressed_source_numbers
            ),
            "skip_answer_generation": result.skip_answer_generation,
            "rules_fired": list(result.rules_fired),
        },
    }


__all__ = [
    "ANCHOR_NORMALIZER_VERSION",
    "EVIDENCE_DIAGNOSTICS_SCHEMA",
    "EVIDENCE_POLICY_VERSION",
    "WEAK_MATCH_WINDOW_TOKENS",
    "AnchorMatch",
    "AnchorMatchKind",
    "AnchorMatchRule",
    "BroaderRelatedScan",
    "ChunkAnchorMatch",
    "CorpusIntegrity",
    "EvidenceDecision",
    "EvidenceGateResult",
    "EvidenceLane",
    "EvidenceLaneAssignment",
    "EvidenceTargetRole",
    "EvidenceTargetScan",
    "assess_corpus_integrity",
    "build_immediate_neighbor_map",
    "classify_anchor_match",
    "classify_evidence_lanes",
    "decide_evidence",
    "evidence_diagnostics",
    "normalize_anchor",
    "relationship_evidence_chunk_ids",
    "scan_broader_related",
    "scan_evidence_target",
    "scan_trusted_target",
    "tokenize_anchor",
]
