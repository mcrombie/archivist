"""Pure scoring primitives for Archivist's held-out answer evaluation.

This module deliberately has no filesystem or provider dependencies.  It owns
only deterministic calibration selection, strict citation accounting,
decomposition validation, and arithmetic over already-classified results.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CALIBRATION_POSITIVE_STRATA = (
    "focused_biographical",
    "focused_analytical",
    "conceptual",
    "broad_thematic",
)
CALIBRATION_EXHAUSTIVE_STRATA = (
    "out_of_corpus",
    "adversarial_premise",
)
CALIBRATION_REQUIRED_STRATA = frozenset(
    (*CALIBRATION_POSITIVE_STRATA, *CALIBRATION_EXHAUSTIVE_STRATA)
)
CALIBRATION_ITEM_COUNT = 10

CITATION_GROUP_GRAMMAR = r"\[Source\s+\d+(?:\s*,\s*Source\s+\d+)*\]"
_CITATION_GROUP_PATTERN = re.compile(CITATION_GROUP_GRAMMAR)
_CITATION_REFERENCE_PATTERN = re.compile(r"Source\s+(\d+)")


class EvaluationScoringError(ValueError):
    """Raised when scoring input violates the declared evaluation contract."""


def select_calibration_item_ids(
    items: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    """Return the fixed ten-item calibration subset in lexical ID order.

    The selector takes the lexicographically first item in each answerable
    content stratum and every item in both behavior-focused strata.  It fails
    closed unless that prospective rule yields exactly ten unique items and
    covers all six declared strata.
    """

    by_stratum: dict[str, list[str]] = {
        stratum: [] for stratum in CALIBRATION_REQUIRED_STRATA
    }
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise EvaluationScoringError(
                f"calibration item at index {index} must be an object"
            )
        item_id = item.get("id")
        stratum = item.get("stratum")
        if not isinstance(item_id, str) or not item_id or item_id != item_id.strip():
            raise EvaluationScoringError(
                f"calibration item at index {index} has an invalid id"
            )
        if item_id in seen_ids:
            raise EvaluationScoringError(f"duplicate calibration item id: {item_id}")
        seen_ids.add(item_id)
        if not isinstance(stratum, str) or stratum not in CALIBRATION_REQUIRED_STRATA:
            raise EvaluationScoringError(
                f"calibration item {item_id} has an unsupported stratum"
            )
        by_stratum[stratum].append(item_id)

    selected: list[str] = []
    for stratum in CALIBRATION_POSITIVE_STRATA:
        candidates = sorted(by_stratum[stratum])
        if not candidates:
            raise EvaluationScoringError(
                f"calibration selection is missing stratum {stratum}"
            )
        selected.append(candidates[0])
    for stratum in CALIBRATION_EXHAUSTIVE_STRATA:
        selected.extend(sorted(by_stratum[stratum]))

    selected_strata = {
        stratum
        for stratum, item_ids in by_stratum.items()
        if any(item_id in selected for item_id in item_ids)
    }
    if len(selected) != CALIBRATION_ITEM_COUNT:
        raise EvaluationScoringError(
            "calibration selection must contain exactly "
            f"{CALIBRATION_ITEM_COUNT} items, found {len(selected)}"
        )
    if len(set(selected)) != CALIBRATION_ITEM_COUNT:
        raise EvaluationScoringError("calibration selection contains duplicate items")
    if selected_strata != CALIBRATION_REQUIRED_STRATA:
        missing = sorted(CALIBRATION_REQUIRED_STRATA - selected_strata)
        raise EvaluationScoringError(
            f"calibration selection does not cover all six strata; missing={missing}"
        )
    return tuple(sorted(selected))


@dataclass(frozen=True, slots=True)
class CitationAudit:
    well_formed_group_count: int
    source_reference_count: int
    malformed_bracket_token_count: int
    resolvable_group_count: int
    resolvable_reference_count: int
    out_of_range_reference_count: int


def _bracket_tokens(text: str) -> tuple[str, ...]:
    """Split every bracket-shaped token without repairing malformed syntax."""

    tokens: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == "[":
            closing = text.find("]", index + 1)
            if closing < 0:
                tokens.append(text[index:])
                break
            tokens.append(text[index : closing + 1])
            index = closing + 1
            continue
        if character == "]":
            tokens.append(character)
        index += 1
    return tuple(tokens)


def audit_citations(answer: str, *, source_count: int) -> CitationAudit:
    """Count valid, malformed, resolvable, and out-of-range citations.

    References inside malformed bracket tokens do not contribute to any other
    metric.  A grouped citation is resolvable only when every individual source
    reference resolves against the exact source list supplied for the answer.
    """

    if not isinstance(answer, str):
        raise TypeError("answer must be a string")
    if (
        not isinstance(source_count, int)
        or isinstance(source_count, bool)
        or source_count < 0
    ):
        raise EvaluationScoringError("source_count must be a non-negative integer")

    well_formed_groups = 0
    source_references = 0
    malformed_tokens = 0
    resolvable_groups = 0
    resolvable_references = 0
    out_of_range_references = 0
    for token in _bracket_tokens(answer):
        if _CITATION_GROUP_PATTERN.fullmatch(token) is None:
            malformed_tokens += 1
            continue
        well_formed_groups += 1
        references = tuple(
            int(value) for value in _CITATION_REFERENCE_PATTERN.findall(token)
        )
        source_references += len(references)
        resolved = tuple(1 <= value <= source_count for value in references)
        resolvable_references += sum(resolved)
        out_of_range_references += len(resolved) - sum(resolved)
        resolvable_groups += int(all(resolved))

    return CitationAudit(
        well_formed_group_count=well_formed_groups,
        source_reference_count=source_references,
        malformed_bracket_token_count=malformed_tokens,
        resolvable_group_count=resolvable_groups,
        resolvable_reference_count=resolvable_references,
        out_of_range_reference_count=out_of_range_references,
    )


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AtomicFactualClaim(_StrictModel):
    id: str
    text: str
    char_start: int = Field(strict=True, ge=0)
    char_end: int = Field(strict=True, ge=1)
    cited_sources: tuple[int, ...] = ()

    @field_validator("id", "text")
    @classmethod
    def require_nonempty_string(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("claim id and text must be non-empty")
        return value

    @field_validator("id")
    @classmethod
    def reject_padded_id(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("claim id must not have outer whitespace")
        return value

    @field_validator("cited_sources", mode="before")
    @classmethod
    def require_positive_source_numbers(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            raise ValueError("cited sources must be an array")
        if any(
            not isinstance(source, int)
            or isinstance(source, bool)
            or source <= 0
            for source in value
        ):
            raise ValueError("cited source numbers must be positive integers")
        return value


class AnswerDecomposition(_StrictModel):
    claims: tuple[AtomicFactualClaim, ...]


def validate_decomposition(
    answer: str,
    decomposition: AnswerDecomposition | Mapping[str, object],
) -> AnswerDecomposition:
    """Validate claim identity, ordering, spans, and exact answer binding."""

    if not isinstance(answer, str):
        raise TypeError("answer must be a string")
    validated = (
        decomposition
        if isinstance(decomposition, AnswerDecomposition)
        else AnswerDecomposition.model_validate(decomposition)
    )
    seen_ids: set[str] = set()
    previous_end = 0
    for ordinal, claim in enumerate(validated.claims, start=1):
        if claim.id in seen_ids:
            raise EvaluationScoringError(f"duplicate decomposed claim id: {claim.id}")
        seen_ids.add(claim.id)
        if claim.char_start >= claim.char_end:
            raise EvaluationScoringError(
                f"decomposed claim {claim.id} has an empty or reversed span"
            )
        if claim.char_end > len(answer):
            raise EvaluationScoringError(
                f"decomposed claim {claim.id} span exceeds the answer"
            )
        if ordinal > 1 and claim.char_start < previous_end:
            raise EvaluationScoringError(
                f"decomposed claim {claim.id} is out of order or overlaps a prior claim"
            )
        if answer[claim.char_start : claim.char_end] != claim.text:
            raise EvaluationScoringError(
                f"decomposed claim {claim.id} text does not match its answer span"
            )
        previous_end = claim.char_end
    return validated


@dataclass(frozen=True, slots=True)
class RateMetric:
    numerator: int
    denominator: int
    rate: float | None


def _rate(numerator: int, denominator: int) -> RateMetric:
    if numerator < 0 or denominator < 0 or numerator > denominator:
        raise EvaluationScoringError("metric counts are invalid")
    return RateMetric(
        numerator=numerator,
        denominator=denominator,
        rate=(numerator / denominator if denominator else None),
    )


def citation_completeness(
    decomposition: AnswerDecomposition | Sequence[AtomicFactualClaim],
) -> RateMetric:
    """Return the fraction of factual claims carrying at least one citation."""

    claims = (
        decomposition.claims
        if isinstance(decomposition, AnswerDecomposition)
        else tuple(decomposition)
    )
    if not all(isinstance(claim, AtomicFactualClaim) for claim in claims):
        raise EvaluationScoringError(
            "citation completeness requires validated atomic factual claims"
        )
    return _rate(
        sum(bool(claim.cited_sources) for claim in claims),
        len(claims),
    )


class FaithfulnessLabel(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"


@dataclass(frozen=True, slots=True)
class FaithfulnessDistribution:
    supported_count: int
    partially_supported_count: int
    unsupported_count: int
    contradicted_count: int
    denominator: int
    full_supported_rate: float | None


def _faithfulness_label(value: FaithfulnessLabel | str) -> FaithfulnessLabel:
    try:
        return FaithfulnessLabel(value)
    except (TypeError, ValueError) as exc:
        raise EvaluationScoringError(f"unsupported faithfulness label: {value!r}") from exc


def faithfulness_distribution(
    labels: Mapping[str, FaithfulnessLabel | str]
    | Sequence[FaithfulnessLabel | str],
) -> FaithfulnessDistribution:
    """Count all rubric levels and report the strict fully-supported rate."""

    raw_labels = labels.values() if isinstance(labels, Mapping) else labels
    normalized = tuple(_faithfulness_label(value) for value in raw_labels)
    counts = {label: normalized.count(label) for label in FaithfulnessLabel}
    denominator = len(normalized)
    supported = counts[FaithfulnessLabel.SUPPORTED]
    return FaithfulnessDistribution(
        supported_count=supported,
        partially_supported_count=counts[FaithfulnessLabel.PARTIALLY_SUPPORTED],
        unsupported_count=counts[FaithfulnessLabel.UNSUPPORTED],
        contradicted_count=counts[FaithfulnessLabel.CONTRADICTED],
        denominator=denominator,
        full_supported_rate=(supported / denominator if denominator else None),
    )


@dataclass(frozen=True, slots=True)
class AgreementMetrics:
    agreement_count: int
    denominator: int
    agreement_rate: float | None
    confusion_matrix: dict[str, dict[str, int]]


@dataclass(frozen=True, slots=True)
class ExactDecisionAgreement:
    agreement_count: int
    denominator: int
    agreement_rate: float | None


def exact_decision_agreement(
    reference: Mapping[str, object],
    observed: Mapping[str, object],
) -> ExactDecisionAgreement:
    """Compare a prospectively keyed pool of atomic decisions exactly.

    The caller owns the decision-key namespace. Values may be scalar labels or
    immutable JSON-like tuples (for example, an ordered gold-ID match set), but
    neither missing nor additional decisions are tolerated.
    """

    for role, values in (("reference", reference), ("observed", observed)):
        if any(
            not isinstance(decision_id, str)
            or not decision_id
            or decision_id != decision_id.strip()
            for decision_id in values
        ):
            raise EvaluationScoringError(f"{role} contains an invalid decision id")
    if set(reference) != set(observed):
        missing_from_observed = sorted(set(reference) - set(observed))
        missing_from_reference = sorted(set(observed) - set(reference))
        raise EvaluationScoringError(
            "reference and observed decision ids differ "
            f"(missing_from_observed={missing_from_observed}, "
            f"missing_from_reference={missing_from_reference})"
        )
    agreement = sum(
        reference[decision_id] == observed[decision_id]
        for decision_id in sorted(reference)
    )
    denominator = len(reference)
    return ExactDecisionAgreement(
        agreement_count=agreement,
        denominator=denominator,
        agreement_rate=(agreement / denominator if denominator else None),
    )


def _normalize_label_mapping(
    values: Mapping[str, FaithfulnessLabel | str],
    *,
    role: str,
) -> dict[str, FaithfulnessLabel]:
    result: dict[str, FaithfulnessLabel] = {}
    for claim_id, label in values.items():
        if not isinstance(claim_id, str) or not claim_id or claim_id != claim_id.strip():
            raise EvaluationScoringError(f"{role} labels contain an invalid claim id")
        result[claim_id] = _faithfulness_label(label)
    return result


def faithfulness_agreement(
    human_labels: Mapping[str, FaithfulnessLabel | str],
    judge_labels: Mapping[str, FaithfulnessLabel | str],
) -> AgreementMetrics:
    """Compute exact agreement and a human-row/judge-column confusion matrix."""

    human = _normalize_label_mapping(human_labels, role="human")
    judge = _normalize_label_mapping(judge_labels, role="judge")
    if set(human) != set(judge):
        missing_from_judge = sorted(set(human) - set(judge))
        missing_from_human = sorted(set(judge) - set(human))
        raise EvaluationScoringError(
            "human and judge claim ids differ "
            f"(missing_from_judge={missing_from_judge}, "
            f"missing_from_human={missing_from_human})"
        )

    matrix = {
        human_label.value: {judge_label.value: 0 for judge_label in FaithfulnessLabel}
        for human_label in FaithfulnessLabel
    }
    agreement = 0
    for claim_id in sorted(human):
        human_label = human[claim_id]
        judge_label = judge[claim_id]
        matrix[human_label.value][judge_label.value] += 1
        agreement += int(human_label is judge_label)
    denominator = len(human)
    return AgreementMetrics(
        agreement_count=agreement,
        denominator=denominator,
        agreement_rate=(agreement / denominator if denominator else None),
        confusion_matrix=matrix,
    )


class EvaluationStratum(StrEnum):
    FOCUSED_BIOGRAPHICAL = "focused_biographical"
    FOCUSED_ANALYTICAL = "focused_analytical"
    CONCEPTUAL = "conceptual"
    BROAD_THEMATIC = "broad_thematic"
    OUT_OF_CORPUS = "out_of_corpus"
    ADVERSARIAL_PREMISE = "adversarial_premise"


class AbstentionOutcome(StrEnum):
    ANSWER = "answer"
    DECLINE = "decline"
    PREMISE_CORRECTION = "premise_correction"
    PARTIAL_DECLINE_THEN_ANSWER = "partial_decline_then_answer"


class AbstentionObservation(_StrictModel):
    id: str
    stratum: EvaluationStratum
    expected_behavior: Literal["answer", "abstain"]
    outcome: AbstentionOutcome

    @field_validator("id")
    @classmethod
    def require_valid_id(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("observation id must be non-empty and unpadded")
        return value


@dataclass(frozen=True, slots=True)
class AbstentionMetrics:
    out_of_corpus_decline: RateMetric
    answerable_false_abstention: RateMetric
    adversarial_premise_correction: RateMetric


def abstention_metrics(
    observations: Sequence[AbstentionObservation | Mapping[str, object]],
) -> AbstentionMetrics:
    """Compute the three behavior rates without collapsing their denominators."""

    normalized = tuple(
        observation
        if isinstance(observation, AbstentionObservation)
        else AbstentionObservation.model_validate(observation)
        for observation in observations
    )
    ids = [observation.id for observation in normalized]
    if len(ids) != len(set(ids)):
        raise EvaluationScoringError("abstention observations contain duplicate item ids")

    out_of_corpus = tuple(
        observation
        for observation in normalized
        if observation.stratum is EvaluationStratum.OUT_OF_CORPUS
    )
    answerable = tuple(
        observation
        for observation in normalized
        if observation.expected_behavior == "answer"
    )
    adversarial = tuple(
        observation
        for observation in normalized
        if observation.stratum is EvaluationStratum.ADVERSARIAL_PREMISE
    )
    return AbstentionMetrics(
        out_of_corpus_decline=_rate(
            sum(
                observation.outcome is AbstentionOutcome.DECLINE
                for observation in out_of_corpus
            ),
            len(out_of_corpus),
        ),
        answerable_false_abstention=_rate(
            sum(
                observation.outcome is AbstentionOutcome.DECLINE
                for observation in answerable
            ),
            len(answerable),
        ),
        adversarial_premise_correction=_rate(
            sum(
                observation.outcome is AbstentionOutcome.PREMISE_CORRECTION
                for observation in adversarial
            ),
            len(adversarial),
        ),
    )


__all__ = [
    "AbstentionMetrics",
    "AbstentionObservation",
    "AbstentionOutcome",
    "AgreementMetrics",
    "AnswerDecomposition",
    "AtomicFactualClaim",
    "CALIBRATION_ITEM_COUNT",
    "CALIBRATION_REQUIRED_STRATA",
    "CITATION_GROUP_GRAMMAR",
    "CitationAudit",
    "EvaluationScoringError",
    "EvaluationStratum",
    "ExactDecisionAgreement",
    "FaithfulnessDistribution",
    "FaithfulnessLabel",
    "RateMetric",
    "abstention_metrics",
    "audit_citations",
    "citation_completeness",
    "exact_decision_agreement",
    "faithfulness_agreement",
    "faithfulness_distribution",
    "select_calibration_item_ids",
    "validate_decomposition",
]
