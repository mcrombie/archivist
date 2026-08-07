"""Mechanical provenance and leakage checks for a held-out gold set.

This module never judges historical correctness and never authors gold
content. It binds owner-authored questions and owner-adjudicated annotations
to a frozen candidate, corpus manifest, development-question registry, and
an honest disclosure of any historical drafting assistance. It then checks
that every fuzzy similarity flag received an explicit owner review.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath

from gold_set import load_json_object, sha256_file


DEVELOPMENT_REGISTRY_SCHEMA = "archivist.development_question_registry/1"
QUESTION_COMMITMENT_SCHEMA = "archivist.gold_question_commitment/1"
GOLD_PROVENANCE_SCHEMA = "archivist.gold_provenance/4"
ANNOTATION_METHOD = "owner_adjudication_with_historical_ai_drafting/1"
QUESTION_NORMALIZATION = "NFKC+casefold+collapse-whitespace/v1"

# A pair is flagged when either independently legible rule is satisfied.
NEAR_TOKEN_JACCARD_THRESHOLD = 0.72
NEAR_MIN_SHARED_TOKENS = 5
NEAR_SEQUENCE_RATIO_THRESHOLD = 0.86
NEAR_MIN_NORMALIZED_CHARACTERS = 24

OWNER_ATTESTATIONS = {
    "questions_behaviors_and_strata_owner_authored_without_candidate_outputs",
    "historical_ai_drafting_disclosed_without_prospective_blinding_claim",
    "claims_and_essentiality_owner_adjudicated",
    "supporting_and_relevant_chunk_ids_owner_verified",
    "must_not_claim_and_notes_owner_adjudicated",
    "accepted_annotation_prose_source_verified_and_owner_adopted_or_revised",
    "held_out_items_not_run_before_lock",
    "near_match_flags_reviewed",
}

_REGISTRY_FIELDS = {"schema", "version", "normalization", "questions"}
_REGISTRY_QUESTION_FIELDS = {"id", "question", "normalized_sha256"}
_QUESTION_COMMITMENT_FIELDS = {
    "schema",
    "question_count",
    "stratum_counts",
    "question_set_sha256",
}
_PROVENANCE_FIELDS = {
    "schema",
    "gold_set_path",
    "gold_set_sha256",
    "question_set_sha256",
    "candidate_commit",
    "candidate_rag_policy",
    "corpus_manifest_sha256",
    "development_registry_sha256",
    "authoring_started_at",
    "authoring_completed_at",
    "annotation_assistance",
    "owner_attestations",
    "near_match_reviews",
}
_ANNOTATION_ASSISTANCE_FIELDS = {
    "method",
    "provider",
    "model",
    "surface",
    "raw_draft_record_available",
    "prospective_blinding_record_available",
    "limitation",
}
_REVIEW_FIELDS = {
    "gold_item_id",
    "development_question_id",
    "disposition",
    "note",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class GoldProvenanceValidationError(ValueError):
    """Raised when held-out provenance or leakage checks fail."""

    def __init__(self, errors: list[str] | tuple[str, ...]):
        self.errors = tuple(errors)
        super().__init__("\n".join(self.errors))


@dataclass(frozen=True, slots=True)
class DevelopmentQuestion:
    """One mechanically validated question already used in development."""

    question_id: str
    question: str
    normalized: str
    normalized_sha256: str


@dataclass(frozen=True, slots=True)
class DevelopmentRegistrySummary:
    """Validated development registry content."""

    version: str
    questions: tuple[DevelopmentQuestion, ...]


@dataclass(frozen=True, slots=True)
class NearMatch:
    """A deterministic similarity flag requiring owner review."""

    gold_item_id: str
    development_question_id: str
    token_jaccard: float
    shared_token_count: int
    sequence_ratio: float
    reasons: tuple[str, ...]

    @property
    def key(self) -> tuple[str, str]:
        """Return the stable pair identifier used by provenance reviews."""

        return self.gold_item_id, self.development_question_id


@dataclass(frozen=True, slots=True)
class GoldProvenanceSummary:
    """Description of a completely bound and reviewed held-out artifact."""

    candidate_commit: str
    candidate_rag_policy: str
    gold_set_sha256: str
    corpus_manifest_sha256: str
    development_registry_sha256: str
    annotation_provider: str
    annotation_model: str
    near_match_count: int


def normalize_question(question: str) -> str:
    """Normalize a question with the committed, deterministic v1 contract."""

    normalized = unicodedata.normalize("NFKC", question).casefold()
    return " ".join(normalized.split())


def normalized_question_sha256(question: str) -> str:
    """Hash the normalized UTF-8 representation of a question."""

    return hashlib.sha256(normalize_question(question).encode("utf-8")).hexdigest()


def gold_question_set_sha256(gold_set: object) -> str:
    """Hash the ordered owner-controlled question projection of a gold set.

    Annotation fields are deliberately excluded. The resulting commitment can
    therefore prove that the owner-controlled exam was fixed before any
    candidate-system exposure and later be compared with the completed file.
    """

    if not isinstance(gold_set, dict) or not isinstance(gold_set.get("items"), list):
        raise GoldProvenanceValidationError(
            ["$gold.items: cannot fingerprint questions without an items array"]
        )

    projection: list[dict[str, str]] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for index, raw_item in enumerate(gold_set["items"]):
        path = f"$gold.items[{index}]"
        if not isinstance(raw_item, dict):
            errors.append(f"{path}: must be an object")
            continue
        projected: dict[str, str] = {}
        for field in ("id", "question", "stratum", "expected_behavior"):
            value = raw_item.get(field)
            if not _is_nonempty_string(value):
                errors.append(f"{path}.{field}: must be a non-empty string")
            else:
                projected[field] = value
        item_id = projected.get("id")
        if item_id in seen_ids:
            errors.append(f"{path}.id: duplicate gold item ID {item_id!r}")
        elif item_id is not None:
            seen_ids.add(item_id)
        if len(projected) == 4:
            projection.append(projected)

    if errors:
        raise GoldProvenanceValidationError(errors)
    canonical = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_development_registry(registry: object) -> DevelopmentRegistrySummary:
    """Validate a text-only registry of questions exposed during development."""

    errors: list[str] = []
    if not isinstance(registry, dict):
        raise GoldProvenanceValidationError(
            ["$registry: development-question registry must be an object"]
        )

    _validate_fields(registry, _REGISTRY_FIELDS, "$registry", errors)
    if registry.get("schema") != DEVELOPMENT_REGISTRY_SCHEMA:
        errors.append(f"$registry.schema: must be exactly {DEVELOPMENT_REGISTRY_SCHEMA!r}")

    version = registry.get("version")
    if not isinstance(version, str) or _SEMVER_RE.fullmatch(version) is None:
        errors.append("$registry.version: must be a semantic version")
        version_text = ""
    else:
        version_text = version

    if registry.get("normalization") != QUESTION_NORMALIZATION:
        errors.append(f"$registry.normalization: must be exactly {QUESTION_NORMALIZATION!r}")

    raw_questions = registry.get("questions")
    if not isinstance(raw_questions, list):
        errors.append("$registry.questions: must be an array")
        raw_questions = []
    elif not raw_questions:
        errors.append("$registry.questions: must contain at least one development question")

    question_ids: set[str] = set()
    normalized_questions: dict[str, str] = {}
    questions: list[DevelopmentQuestion] = []
    for index, raw_question in enumerate(raw_questions):
        path = f"$registry.questions[{index}]"
        if not isinstance(raw_question, dict):
            errors.append(f"{path}: must be an object")
            continue
        _validate_fields(raw_question, _REGISTRY_QUESTION_FIELDS, path, errors)

        question_id = raw_question.get("id")
        if not _is_nonempty_string(question_id):
            errors.append(f"{path}.id: must be a non-empty string")
            question_id_text = f"index {index}"
        else:
            question_id_text = question_id
            if question_id_text in question_ids:
                errors.append(f"{path}.id: duplicate ID {question_id_text!r}")
            question_ids.add(question_id_text)

        question = raw_question.get("question")
        if not _is_nonempty_string(question):
            errors.append(f"{path}.question: must be a non-empty string")
            continue
        normalized = normalize_question(question)
        previous_id = normalized_questions.get(normalized)
        if previous_id is not None:
            errors.append(
                f"{path}.question: duplicates normalized development question {previous_id!r}"
            )
        else:
            normalized_questions[normalized] = question_id_text

        recorded_digest = raw_question.get("normalized_sha256")
        expected_digest = normalized_question_sha256(question)
        if recorded_digest != expected_digest:
            errors.append(
                f"{path}.normalized_sha256: must equal the normalized question hash "
                f"{expected_digest}"
            )
        questions.append(
            DevelopmentQuestion(
                question_id=question_id_text,
                question=question,
                normalized=normalized,
                normalized_sha256=expected_digest,
            )
        )

    if errors:
        raise GoldProvenanceValidationError(errors)
    return DevelopmentRegistrySummary(
        version=version_text,
        questions=tuple(questions),
    )


def find_question_overlap(
    gold_set: object,
    registry: DevelopmentRegistrySummary,
) -> tuple[NearMatch, ...]:
    """Reject exact reuse and return every deterministic fuzzy-match flag."""

    gold_questions = _extract_gold_questions(gold_set)
    development_by_normalized = {question.normalized: question for question in registry.questions}
    exact_errors: list[str] = []
    near_matches: list[NearMatch] = []

    for gold_item_id, gold_question in gold_questions:
        normalized_gold = normalize_question(gold_question)
        exact = development_by_normalized.get(normalized_gold)
        if exact is not None:
            exact_errors.append(
                f"$gold.items[{gold_item_id!r}].question: exact normalized duplicate "
                f"of development question {exact.question_id!r}; exact reuse cannot "
                "be approved by a near-match review"
            )
            continue

        for development_question in registry.questions:
            match = _near_match(
                gold_item_id,
                normalized_gold,
                development_question,
            )
            if match is not None:
                near_matches.append(match)

    if exact_errors:
        raise GoldProvenanceValidationError(exact_errors)
    return tuple(near_matches)


def validate_gold_provenance_file(
    provenance_path: Path,
    gold_set_path: Path,
    corpus_manifest_path: Path,
    development_registry_path: Path,
    question_commitment_path: Path,
    *,
    expected_gold_set_path: str,
    expected_candidate_commit: str,
    expected_rag_policy: str,
    repository_root: Path | None = None,
) -> GoldProvenanceSummary:
    """Validate exact file bindings and held-out attestations."""

    provenance = load_json_object(provenance_path, label="gold provenance")
    gold_set = load_json_object(gold_set_path, label="gold set")
    registry = load_json_object(
        development_registry_path,
        label="development-question registry",
    )
    question_commitment = load_json_object(
        question_commitment_path,
        label="gold-question commitment",
    )
    # Kept for API compatibility with callers that already pass an explicit
    # repository root. Provenance v4 deliberately does not bind a private raw
    # draft that was not prospectively captured.
    _ = repository_root
    return validate_gold_provenance(
        provenance,
        gold_set,
        registry,
        question_commitment,
        gold_set_sha256=sha256_file(gold_set_path),
        corpus_manifest_sha256=sha256_file(corpus_manifest_path),
        development_registry_sha256=sha256_file(development_registry_path),
        expected_gold_set_path=expected_gold_set_path,
        expected_candidate_commit=expected_candidate_commit,
        expected_rag_policy=expected_rag_policy,
    )


def validate_gold_provenance(
    provenance: object,
    gold_set: object,
    development_registry: object,
    question_commitment: object,
    *,
    gold_set_sha256: str,
    corpus_manifest_sha256: str,
    development_registry_sha256: str,
    expected_gold_set_path: str,
    expected_candidate_commit: str,
    expected_rag_policy: str,
) -> GoldProvenanceSummary:
    """Validate provenance without inspecting manuscript text or model output."""

    errors: list[str] = []
    try:
        registry = validate_development_registry(development_registry)
    except GoldProvenanceValidationError as exc:
        errors.extend(exc.errors)
        registry = DevelopmentRegistrySummary(version="", questions=())

    try:
        near_matches = find_question_overlap(gold_set, registry)
    except GoldProvenanceValidationError as exc:
        errors.extend(exc.errors)
        near_matches = ()

    if not isinstance(provenance, dict):
        raise GoldProvenanceValidationError(
            [*errors, "$provenance: gold provenance must be an object"]
        )
    _validate_fields(provenance, _PROVENANCE_FIELDS, "$provenance", errors)
    if provenance.get("schema") != GOLD_PROVENANCE_SCHEMA:
        errors.append(f"$provenance.schema: must be exactly {GOLD_PROVENANCE_SCHEMA!r}")

    _validate_binding(
        provenance,
        field="gold_set_sha256",
        expected=gold_set_sha256,
        errors=errors,
    )

    try:
        expected_question_set_sha256 = gold_question_set_sha256(gold_set)
    except GoldProvenanceValidationError as exc:
        errors.extend(exc.errors)
        expected_question_set_sha256 = ""
    recorded_question_set_sha256 = provenance.get("question_set_sha256")
    if (
        not isinstance(recorded_question_set_sha256, str)
        or _SHA256_RE.fullmatch(recorded_question_set_sha256) is None
    ):
        errors.append("$provenance.question_set_sha256: must be a lowercase 64-character SHA-256")
    elif (
        expected_question_set_sha256
        and recorded_question_set_sha256 != expected_question_set_sha256
    ):
        errors.append(
            "$provenance.question_set_sha256: does not match the canonical ordered "
            "ID/question/stratum/behavior projection"
        )
    _validate_question_commitment(
        question_commitment,
        gold_set,
        expected_question_set_sha256=expected_question_set_sha256,
        recorded_question_set_sha256=recorded_question_set_sha256,
        errors=errors,
    )
    _validate_binding(
        provenance,
        field="corpus_manifest_sha256",
        expected=corpus_manifest_sha256,
        errors=errors,
    )
    _validate_binding(
        provenance,
        field="development_registry_sha256",
        expected=development_registry_sha256,
        errors=errors,
    )

    recorded_gold_path = provenance.get("gold_set_path")
    if not _is_safe_relative_posix_path(recorded_gold_path):
        errors.append(
            "$provenance.gold_set_path: must be a normalized relative POSIX path "
            "without '.' or '..' components"
        )
    elif recorded_gold_path != expected_gold_set_path:
        errors.append(
            "$provenance.gold_set_path: does not match the expected gold-set path "
            f"{expected_gold_set_path!r}"
        )

    candidate_commit = provenance.get("candidate_commit")
    if not isinstance(candidate_commit, str) or _COMMIT_RE.fullmatch(candidate_commit) is None:
        errors.append(
            "$provenance.candidate_commit: must be a full lowercase 40-character Git commit"
        )
        candidate_commit_text = ""
    else:
        candidate_commit_text = candidate_commit
        if candidate_commit != expected_candidate_commit:
            errors.append(
                "$provenance.candidate_commit: does not match the frozen candidate "
                f"{expected_candidate_commit!r}"
            )

    candidate_rag_policy = provenance.get("candidate_rag_policy")
    if not _is_nonempty_string(candidate_rag_policy):
        errors.append("$provenance.candidate_rag_policy: must be a non-empty string")
        candidate_rag_policy_text = ""
    else:
        candidate_rag_policy_text = candidate_rag_policy
        if candidate_rag_policy != expected_rag_policy:
            errors.append(
                "$provenance.candidate_rag_policy: does not match the frozen policy "
                f"{expected_rag_policy!r}"
            )

    started = _validate_timestamp(
        provenance.get("authoring_started_at"),
        "$provenance.authoring_started_at",
        errors,
    )
    completed = _validate_timestamp(
        provenance.get("authoring_completed_at"),
        "$provenance.authoring_completed_at",
        errors,
    )
    if started is not None and completed is not None and completed < started:
        errors.append("$provenance.authoring_completed_at: must not precede authoring_started_at")

    annotation_provider, annotation_model = _validate_annotation_assistance(
        provenance.get("annotation_assistance"),
        errors,
    )

    attestations = provenance.get("owner_attestations")
    if not isinstance(attestations, dict):
        errors.append("$provenance.owner_attestations: must be an object")
    else:
        _validate_fields(
            attestations,
            OWNER_ATTESTATIONS,
            "$provenance.owner_attestations",
            errors,
        )
        for attestation in sorted(OWNER_ATTESTATIONS):
            if attestations.get(attestation) is not True:
                errors.append(
                    f"$provenance.owner_attestations.{attestation}: "
                    "owner must explicitly attest true"
                )

    _validate_near_match_reviews(
        provenance.get("near_match_reviews"),
        near_matches,
        errors,
    )

    if errors:
        raise GoldProvenanceValidationError(errors)
    return GoldProvenanceSummary(
        candidate_commit=candidate_commit_text,
        candidate_rag_policy=candidate_rag_policy_text,
        gold_set_sha256=gold_set_sha256,
        corpus_manifest_sha256=corpus_manifest_sha256,
        development_registry_sha256=development_registry_sha256,
        annotation_provider=annotation_provider,
        annotation_model=annotation_model,
        near_match_count=len(near_matches),
    )


def _validate_question_commitment(
    raw_commitment: object,
    gold_set: object,
    *,
    expected_question_set_sha256: str,
    recorded_question_set_sha256: object,
    errors: list[str],
) -> None:
    """Bind the final owner fields to the previously frozen text-free commitment."""

    path = "$question_commitment"
    if not isinstance(raw_commitment, dict):
        errors.append(f"{path}: must be an object")
        return
    _validate_fields(raw_commitment, _QUESTION_COMMITMENT_FIELDS, path, errors)
    if raw_commitment.get("schema") != QUESTION_COMMITMENT_SCHEMA:
        errors.append(f"{path}.schema: must be exactly {QUESTION_COMMITMENT_SCHEMA!r}")

    raw_count = raw_commitment.get("question_count")
    if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count < 1:
        errors.append(f"{path}.question_count: must be a positive integer")

    raw_counts = raw_commitment.get("stratum_counts")
    counts_are_valid = isinstance(raw_counts, dict) and all(
        isinstance(name, str)
        and bool(name)
        and not isinstance(count, bool)
        and isinstance(count, int)
        and count >= 0
        for name, count in raw_counts.items()
    )
    if not counts_are_valid:
        errors.append(
            f"{path}.stratum_counts: must map non-empty stratum names to non-negative integers"
        )

    gold_items = gold_set.get("items") if isinstance(gold_set, dict) else None
    if isinstance(gold_items, list):
        expected_count = len(gold_items)
        if isinstance(raw_count, int) and not isinstance(raw_count, bool):
            if raw_count != expected_count:
                errors.append(
                    f"{path}.question_count: does not match the final gold item count "
                    f"{expected_count}"
                )
        expected_counts = Counter(
            item.get("stratum")
            for item in gold_items
            if isinstance(item, dict) and isinstance(item.get("stratum"), str)
        )
        if counts_are_valid and dict(raw_counts) != dict(sorted(expected_counts.items())):
            errors.append(
                f"{path}.stratum_counts: does not match the final gold stratum distribution"
            )

    commitment_sha256 = raw_commitment.get("question_set_sha256")
    if not isinstance(commitment_sha256, str) or _SHA256_RE.fullmatch(commitment_sha256) is None:
        errors.append(
            f"{path}.question_set_sha256: must be a lowercase 64-character SHA-256"
        )
        return
    if expected_question_set_sha256 and commitment_sha256 != expected_question_set_sha256:
        errors.append(
            f"{path}.question_set_sha256: does not match the final canonical owner-field projection"
        )
    if (
        isinstance(recorded_question_set_sha256, str)
        and _SHA256_RE.fullmatch(recorded_question_set_sha256) is not None
        and commitment_sha256 != recorded_question_set_sha256
    ):
        errors.append(
            f"{path}.question_set_sha256: does not match provenance.question_set_sha256"
        )


def _extract_gold_questions(gold_set: object) -> tuple[tuple[str, str], ...]:
    errors: list[str] = []
    if not isinstance(gold_set, dict):
        raise GoldProvenanceValidationError(["$gold: gold set must be an object"])
    raw_items = gold_set.get("items")
    if not isinstance(raw_items, list):
        raise GoldProvenanceValidationError(["$gold.items: must be an array"])

    result: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for index, raw_item in enumerate(raw_items):
        path = f"$gold.items[{index}]"
        if not isinstance(raw_item, dict):
            errors.append(f"{path}: must be an object")
            continue
        item_id = raw_item.get("id")
        question = raw_item.get("question")
        if not _is_nonempty_string(item_id):
            errors.append(f"{path}.id: must be a non-empty string")
            continue
        if item_id in seen_ids:
            errors.append(f"{path}.id: duplicate gold item ID {item_id!r}")
            continue
        seen_ids.add(item_id)
        if not _is_nonempty_string(question):
            errors.append(f"{path}.question: must be a non-empty string")
            continue
        result.append((item_id, question))
    if errors:
        raise GoldProvenanceValidationError(errors)
    return tuple(result)


def _near_match(
    gold_item_id: str,
    normalized_gold: str,
    development_question: DevelopmentQuestion,
) -> NearMatch | None:
    gold_tokens = set(_TOKEN_RE.findall(normalized_gold))
    development_tokens = set(_TOKEN_RE.findall(development_question.normalized))
    shared_token_count = len(gold_tokens & development_tokens)
    union_count = len(gold_tokens | development_tokens)
    token_jaccard = shared_token_count / union_count if union_count else 0.0
    sequence_ratio = SequenceMatcher(
        None,
        normalized_gold,
        development_question.normalized,
        autojunk=False,
    ).ratio()

    reasons: list[str] = []
    if (
        shared_token_count >= NEAR_MIN_SHARED_TOKENS
        and token_jaccard >= NEAR_TOKEN_JACCARD_THRESHOLD
    ):
        reasons.append(
            f"token_jaccard>={NEAR_TOKEN_JACCARD_THRESHOLD:.2f}"
            f"+shared_tokens>={NEAR_MIN_SHARED_TOKENS}"
        )
    if (
        min(len(normalized_gold), len(development_question.normalized))
        >= NEAR_MIN_NORMALIZED_CHARACTERS
        and sequence_ratio >= NEAR_SEQUENCE_RATIO_THRESHOLD
    ):
        reasons.append(
            f"sequence_ratio>={NEAR_SEQUENCE_RATIO_THRESHOLD:.2f}"
            f"+min_chars>={NEAR_MIN_NORMALIZED_CHARACTERS}"
        )
    if not reasons:
        return None
    return NearMatch(
        gold_item_id=gold_item_id,
        development_question_id=development_question.question_id,
        token_jaccard=token_jaccard,
        shared_token_count=shared_token_count,
        sequence_ratio=sequence_ratio,
        reasons=tuple(reasons),
    )


def _validate_annotation_assistance(
    raw_assistance: object,
    errors: list[str],
) -> tuple[str, str]:
    path = "$provenance.annotation_assistance"
    if not isinstance(raw_assistance, dict):
        errors.append(f"{path}: must be an object")
        return "", ""

    _validate_fields(raw_assistance, _ANNOTATION_ASSISTANCE_FIELDS, path, errors)
    if raw_assistance.get("method") != ANNOTATION_METHOD:
        errors.append(f"{path}.method: must be exactly {ANNOTATION_METHOD!r}")

    text_values: dict[str, str] = {}
    for field in ("provider", "model", "surface"):
        value = raw_assistance.get(field)
        if not _is_nonempty_string(value):
            errors.append(f"{path}.{field}: must be a non-empty string")
            text_values[field] = ""
        else:
            text_values[field] = value

    for field in ("raw_draft_record_available", "prospective_blinding_record_available"):
        if raw_assistance.get(field) is not False:
            errors.append(
                f"{path}.{field}: must be false for retrospectively disclosed historical assistance"
            )

    limitation = raw_assistance.get("limitation")
    if not _is_nonempty_string(limitation):
        errors.append(f"{path}.limitation: must be a non-empty disclosure")
    elif len(limitation.split()) < 12:
        errors.append(f"{path}.limitation: must substantively disclose the provenance limitation")

    return text_values.get("provider", ""), text_values.get("model", "")


def _validate_near_match_reviews(
    raw_reviews: object,
    near_matches: tuple[NearMatch, ...],
    errors: list[str],
) -> None:
    if not isinstance(raw_reviews, list):
        errors.append("$provenance.near_match_reviews: must be an array")
        raw_reviews = []

    expected = {match.key for match in near_matches}
    reviewed: set[tuple[str, str]] = set()
    for index, raw_review in enumerate(raw_reviews):
        path = f"$provenance.near_match_reviews[{index}]"
        if not isinstance(raw_review, dict):
            errors.append(f"{path}: must be an object")
            continue
        _validate_fields(raw_review, _REVIEW_FIELDS, path, errors)
        gold_item_id = raw_review.get("gold_item_id")
        development_question_id = raw_review.get("development_question_id")
        if not _is_nonempty_string(gold_item_id):
            errors.append(f"{path}.gold_item_id: must be a non-empty string")
        if not _is_nonempty_string(development_question_id):
            errors.append(f"{path}.development_question_id: must be a non-empty string")
        if not (_is_nonempty_string(gold_item_id) and _is_nonempty_string(development_question_id)):
            continue

        key = (gold_item_id, development_question_id)
        if key in reviewed:
            errors.append(f"{path}: duplicate near-match review for {key!r}")
        reviewed.add(key)
        if raw_review.get("disposition") != "approved_distinct":
            errors.append(
                f"{path}.disposition: must be exactly 'approved_distinct'; "
                "replace a non-distinct gold question instead of approving reuse"
            )
        if not _is_nonempty_string(raw_review.get("note")):
            errors.append(f"{path}.note: owner must record a non-empty distinction note")

    missing = sorted(expected - reviewed)
    extra = sorted(reviewed - expected)
    if missing:
        errors.append(f"$provenance.near_match_reviews: missing owner reviews for {missing!r}")
    if extra:
        errors.append(
            f"$provenance.near_match_reviews: contains reviews for unflagged pairs {extra!r}"
        )


def _validate_binding(
    provenance: dict[str, object],
    *,
    field: str,
    expected: str,
    errors: list[str],
) -> None:
    recorded = provenance.get(field)
    if not isinstance(recorded, str) or _SHA256_RE.fullmatch(recorded) is None:
        errors.append(f"$provenance.{field}: must be a lowercase 64-character SHA-256")
    elif recorded != expected:
        errors.append(f"$provenance.{field}: does not match the exact file hash {expected}")


def _validate_timestamp(
    raw_timestamp: object,
    path: str,
    errors: list[str],
) -> datetime | None:
    if not _is_nonempty_string(raw_timestamp):
        errors.append(f"{path}: must be a non-empty ISO-8601 timestamp with timezone")
        return None
    try:
        timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{path}: must be a valid ISO-8601 timestamp with timezone")
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        errors.append(f"{path}: must include a timezone offset")
        return None
    return timestamp


def _is_safe_relative_posix_path(value: object) -> bool:
    if not _is_nonempty_string(value) or "\\" in value:
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or ":" in path.parts[0]:
        return False
    if any(part in {"", ".", ".."} for part in path.parts):
        return False
    return path.as_posix() == value


def _validate_fields(
    value: dict[str, object],
    expected: set[str],
    path: str,
    errors: list[str],
) -> None:
    missing = sorted(expected - value.keys())
    extra = sorted(value.keys() - expected)
    if missing:
        errors.append(f"{path}: missing required fields {missing!r}")
    if extra:
        errors.append(f"{path}: unexpected fields {extra!r}")


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
