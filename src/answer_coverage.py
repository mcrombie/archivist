"""Pure contracts, validation, diagnostics, and rendering for evidence coverage.

This module deliberately has no model or retrieval dependencies.  A generation
adapter may construct :class:`EvidenceCoverageAnswer`, but only a
:class:`ValidatedEvidenceCoverage` can be rendered.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import groupby
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

__all__ = [
    "ALL_UNSUPPORTED_MESSAGE",
    "CITATION_GRAMMAR",
    "EVIDENCE_COVERAGE_DIAGNOSTIC_SCHEMA",
    "EVIDENCE_COVERAGE_NORMALIZER_VERSION",
    "EVIDENCE_COVERAGE_RENDERER_VERSION",
    "EVIDENCE_COVERAGE_SCHEMA",
    "GENERATION_CONTRACT_FAILED_MESSAGE",
    "NO_SOURCES_MESSAGE",
    "AnswerUnit",
    "AnswerUnitRole",
    "CoverageContractError",
    "CoverageDiagnosticSummary",
    "CoverageOutcomeStatus",
    "CoverageValidationContext",
    "CoverageValidationErrorCode",
    "DiagnosticValidationResult",
    "EvidenceCoverageAnswer",
    "EvidenceCoverageResult",
    "GapReason",
    "PremiseDecision",
    "PremiseSourceScope",
    "PremiseStatus",
    "RequirementCoverage",
    "RequirementStatus",
    "ValidatedEvidenceCoverage",
    "coverage_diagnostic_summary",
    "parse_citation_numbers",
    "process_evidence_coverage",
    "render_evidence_coverage",
    "validate_evidence_coverage",
]


EVIDENCE_COVERAGE_SCHEMA = "archivist.evidence_coverage/2"
EVIDENCE_COVERAGE_DIAGNOSTIC_SCHEMA = "archivist.evidence_coverage_diagnostics/4"
EVIDENCE_COVERAGE_RENDERER_VERSION = "evidence-coverage-renderer/1"
EVIDENCE_COVERAGE_NORMALIZER_VERSION = "evidence-coverage-normalizer/4"

MAX_REQUIREMENTS = 8
MAX_PREMISES = 2
MAX_SOURCES = 8
MAX_ANSWER_UNITS = 32
MAX_UNIT_TEXT_CHARACTERS = 2_000
MAX_TOTAL_UNIT_TEXT_CHARACTERS = 12_000
MAX_REQUIREMENT_LABEL_CHARACTERS = 240

CITATION_GRAMMAR = r"\[Source\s+\d+(?:\s*,\s*Source\s+\d+)*\]"
CITATION_PATTERN = re.compile(CITATION_GRAMMAR)
_BRACKETED_PATTERN = re.compile(r"\[[^\[\]]*\]")
_CITATION_NUMBER_PATTERN = re.compile(r"Source\s+(\d+)")
_TERMINAL_CITATION_PATTERN = re.compile(rf"{CITATION_GRAMMAR}[.!?]$")

NO_SOURCES_MESSAGE = (
    "The retrieved passages do not provide enough evidence to answer this question."
)
ALL_UNSUPPORTED_MESSAGE = (
    "The retrieved passages do not provide enough evidence to answer the requested question."
)
GENERATION_CONTRACT_FAILED_MESSAGE = (
    "I could not produce a validated source-grounded answer from the retrieved passages."
)

Identifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
]
SourceNumber = Annotated[int, Field(strict=True, ge=1)]
UnitText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=MAX_UNIT_TEXT_CHARACTERS),
]


class PremiseStatus(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


class RequirementStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"


class GapReason(StrEnum):
    NONE = "none"
    NO_DIRECT_SUPPORT = "no_direct_support"
    PARTIAL_SUPPORT = "partial_support"
    SOURCE_CONFLICT = "source_conflict"


_STATUS_GAP_REASON = {
    RequirementStatus.SUPPORTED: GapReason.NONE,
    RequirementStatus.PARTIAL: GapReason.PARTIAL_SUPPORT,
    RequirementStatus.UNSUPPORTED: GapReason.NO_DIRECT_SUPPORT,
    RequirementStatus.CONFLICTING: GapReason.SOURCE_CONFLICT,
}


class AnswerUnitRole(StrEnum):
    PREMISE_CORRECTION = "premise_correction"
    DEFINITION = "definition"
    IDENTITY = "identity"
    CAUSE = "cause"
    MECHANISM = "mechanism"
    EVENT = "event"
    CONSEQUENCE = "consequence"
    QUANTITY = "quantity"
    COUNTERARGUMENT = "counterargument"
    QUALIFICATION = "qualification"
    CHRONOLOGY = "chronology"


class CoverageOutcomeStatus(StrEnum):
    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    GENERATION_CONTRACT_FAILED = "generation_contract_failed"


class DiagnosticValidationResult(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    NOT_RUN = "not_run"


class CoverageValidationErrorCode(StrEnum):
    INVALID_CONTEXT = "invalid_context"
    INVALID_PAYLOAD = "invalid_payload"
    GENERATION_REFUSED = "generation_refused"
    MISSING_REQUIREMENT_ID = "missing_requirement_id"
    DUPLICATE_REQUIREMENT_ID = "duplicate_requirement_id"
    UNKNOWN_REQUIREMENT_ID = "unknown_requirement_id"
    OUT_OF_ORDER_REQUIREMENT_ID = "out_of_order_requirement_id"
    MISSING_PREMISE_ID = "missing_premise_id"
    DUPLICATE_PREMISE_ID = "duplicate_premise_id"
    UNKNOWN_PREMISE_ID = "unknown_premise_id"
    OUT_OF_ORDER_PREMISE_ID = "out_of_order_premise_id"
    DUPLICATE_UNIT_ID = "duplicate_unit_id"
    UNKNOWN_UNIT_ID = "unknown_unit_id"
    DUPLICATE_UNIT_REFERENCE = "duplicate_unit_reference"
    UNKNOWN_UNIT_REQUIREMENT_ID = "unknown_unit_requirement_id"
    OUT_OF_ORDER_UNIT_REQUIREMENT_ID = "out_of_order_unit_requirement_id"
    UNIT_MAPPING_MISMATCH = "unit_mapping_mismatch"
    UNSUPPORTED_REQUIREMENT_HAS_UNIT = "unsupported_requirement_has_unit"
    STATUS_UNIT_MISMATCH = "status_unit_mismatch"
    STATUS_GAP_MISMATCH = "status_gap_mismatch"
    PREMISE_SOURCE_MISMATCH = "premise_source_mismatch"
    PREMISE_PROVENANCE_MISMATCH = "premise_provenance_mismatch"
    PREMISE_STATUS_INVALID = "premise_status_invalid"
    PREMISE_CORRECTION_MISSING = "premise_correction_missing"
    PREMISE_CORRECTION_INVALID = "premise_correction_invalid"
    PREMISE_CORRECTION_NOT_FIRST = "premise_correction_not_first"
    PREMISE_CORRECTION_REQUIREMENT_MISMATCH = (
        "premise_correction_requirement_mismatch"
    )
    MISSING_UNIT_REQUIREMENT_ID = "missing_unit_requirement_id"
    DUPLICATE_SOURCE_NUMBER = "duplicate_source_number"
    SOURCE_NUMBER_OUT_OF_RANGE = "source_number_out_of_range"
    SOURCE_MAPPING_MISMATCH = "source_mapping_mismatch"
    CONFLICT_REQUIRES_MULTIPLE_SOURCES = "conflict_requires_multiple_sources"
    MISSING_CITATION = "missing_citation"
    MALFORMED_CITATION = "malformed_citation"
    UNRESOLVABLE_CITATION = "unresolvable_citation"
    CITATION_SOURCE_MISMATCH = "citation_source_mismatch"
    CITATION_LOCALITY_INVALID = "citation_locality_invalid"
    TEXT_LIMIT_EXCEEDED = "text_limit_exceeded"


class _ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class PremiseDecision(_ContractModel):
    premise_id: Identifier
    status: PremiseStatus
    source_numbers: tuple[SourceNumber, ...] = Field(max_length=MAX_SOURCES)
    correction_unit_id: Identifier | None = None


class RequirementCoverage(_ContractModel):
    requirement_id: Identifier
    status: RequirementStatus
    unit_ids: tuple[Identifier, ...] = Field(max_length=MAX_ANSWER_UNITS)
    source_numbers: tuple[SourceNumber, ...] = Field(max_length=MAX_SOURCES)
    gap_reason: GapReason


class AnswerUnit(_ContractModel):
    unit_id: Identifier
    requirement_ids: tuple[Identifier, ...] = Field(
        max_length=MAX_REQUIREMENTS,
    )
    role: AnswerUnitRole
    text: UnitText = Field(
        description=(
            "Exactly one complete sentence asserting one independently checkable "
            "factual claim, followed by exactly one terminal citation group and "
            "its only ending punctuation. The claim must spell out or rephrase "
            "period-containing abbreviations, titles, and initials."
        )
    )
    source_numbers: tuple[SourceNumber, ...] = Field(
        min_length=1,
        max_length=MAX_SOURCES,
        description=(
            "The exact sources in the terminal citation group; every listed source "
            "must independently support the same single claim."
        ),
    )
    paragraph: Annotated[int, Field(strict=True, ge=1, le=MAX_ANSWER_UNITS)]

    @field_validator("text")
    @classmethod
    def reject_blank_or_padded_text(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("answer unit text must be nonblank and have no outer whitespace")
        return value


class EvidenceCoverageAnswer(_ContractModel):
    schema_version: Literal["archivist.evidence_coverage/2"] = Field(alias="schema")
    premise_decisions: tuple[PremiseDecision, ...] = Field(max_length=MAX_PREMISES)
    coverage: tuple[RequirementCoverage, ...] = Field(
        min_length=1,
        max_length=MAX_REQUIREMENTS,
    )
    answer_units: tuple[AnswerUnit, ...] = Field(max_length=MAX_ANSWER_UNITS)

    @property
    def schema(self) -> str:
        return self.schema_version


class PremiseSourceScope(_ContractModel):
    """Trusted post-gate source provenance for one premise hypothesis."""

    premise_id: Identifier
    support_source_numbers: tuple[SourceNumber, ...] = Field(max_length=MAX_SOURCES)
    counter_source_numbers: tuple[SourceNumber, ...] = Field(max_length=MAX_SOURCES)
    framing_source_numbers: tuple[SourceNumber, ...] = Field(max_length=MAX_SOURCES)


class CoverageValidationContext(_ContractModel):
    requirement_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=MAX_REQUIREMENTS,
    )
    premise_ids: tuple[Identifier, ...] = Field(max_length=MAX_PREMISES)
    premise_source_scopes: tuple[PremiseSourceScope, ...] = Field(
        max_length=MAX_PREMISES
    )
    source_count: Annotated[int, Field(strict=True, ge=0, le=MAX_SOURCES)]


class RequirementCoverageDiagnostic(_ContractModel):
    requirement_id: Identifier
    status: RequirementStatus
    unit_ids: tuple[Identifier, ...]
    source_numbers: tuple[SourceNumber, ...]
    gap_reason: GapReason


class PremiseDecisionDiagnostic(_ContractModel):
    premise_id: Identifier
    status: PremiseStatus
    source_numbers: tuple[SourceNumber, ...]
    correction_unit_id: Identifier | None


class AnswerUnitDiagnostic(_ContractModel):
    unit_id: Identifier
    requirement_ids: tuple[Identifier, ...]
    role: AnswerUnitRole
    source_numbers: tuple[SourceNumber, ...]
    paragraph: int


class RequirementStatusCounts(_ContractModel):
    supported: int = Field(ge=0)
    partial: int = Field(ge=0)
    unsupported: int = Field(ge=0)
    conflicting: int = Field(ge=0)


class PremiseStatusCounts(_ContractModel):
    supported: int = Field(ge=0)
    contradicted: int = Field(ge=0)
    unresolved: int = Field(ge=0)
    not_applicable: int = Field(ge=0)


class CoverageDiagnosticSummary(_ContractModel):
    schema_version: Literal["archivist.evidence_coverage_diagnostics/4"] = Field(alias="schema")
    renderer_version: Literal["evidence-coverage-renderer/1"]
    validation_result: DiagnosticValidationResult
    error_code: CoverageValidationErrorCode | None
    repair_applied: bool
    repair_codes: tuple[CoverageValidationErrorCode, ...]
    requirement_ids: tuple[Identifier, ...]
    premise_ids: tuple[Identifier, ...]
    premise_source_scopes: tuple[PremiseSourceScope, ...]
    requirement_count: int = Field(ge=0, le=MAX_REQUIREMENTS)
    premise_count: int = Field(ge=0, le=MAX_PREMISES)
    source_count: int = Field(ge=0, le=MAX_SOURCES)
    coverage_status_counts: RequirementStatusCounts
    premise_status_counts: PremiseStatusCounts
    answer_unit_count: int = Field(ge=0, le=MAX_ANSWER_UNITS)
    citation_count: int = Field(ge=0)
    coverage: tuple[RequirementCoverageDiagnostic, ...]
    premise_decisions: tuple[PremiseDecisionDiagnostic, ...]
    answer_units: tuple[AnswerUnitDiagnostic, ...]

    @property
    def schema(self) -> str:
        return self.schema_version


class EvidenceCoverageResult(_ContractModel):
    status: CoverageOutcomeStatus
    answer: str
    error_code: Literal["generation_contract_failed"] | None
    diagnostics: CoverageDiagnosticSummary


class CoverageContractError(ValueError):
    """A fail-closed semantic contract error with a stable, text-free code."""

    def __init__(
        self,
        code: CoverageValidationErrorCode,
        *,
        repair_codes: Sequence[CoverageValidationErrorCode] = (),
    ):
        self.code = code
        self.repair_codes = tuple(dict.fromkeys(repair_codes))
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class ValidatedEvidenceCoverage:
    """Opaque proof that an evidence-coverage payload passed local validation."""

    answer: EvidenceCoverageAnswer
    context: CoverageValidationContext
    citation_count: int


def parse_citation_numbers(text: str) -> tuple[int, ...]:
    """Parse only the citation grammar locked by ``EVAL_CONTRACT.md``.

    Every square-bracketed token in an answer unit must be a citation.  Nested,
    unmatched, or differently shaped brackets are rejected instead of repaired.
    """

    bracketed = list(_BRACKETED_PATTERN.finditer(text))
    outside_brackets = _BRACKETED_PATTERN.sub("", text)
    if "[" in outside_brackets or "]" in outside_brackets:
        raise CoverageContractError(CoverageValidationErrorCode.MALFORMED_CITATION)

    numbers: list[int] = []
    for match in bracketed:
        citation = match.group(0)
        if CITATION_PATTERN.fullmatch(citation) is None:
            raise CoverageContractError(CoverageValidationErrorCode.MALFORMED_CITATION)
        numbers.extend(int(value) for value in _CITATION_NUMBER_PATTERN.findall(citation))
    return tuple(numbers)


def validate_evidence_coverage(
    payload: EvidenceCoverageAnswer | Mapping[str, Any],
    *,
    requirement_ids: Sequence[str],
    premise_ids: Sequence[str] = (),
    premise_source_scopes: Sequence[PremiseSourceScope | Mapping[str, Any]] = (),
    source_count: int,
) -> ValidatedEvidenceCoverage:
    """Validate a structured answer against its trusted call inputs.

    The function never returns a partially validated payload.  Callers should
    catch :class:`CoverageContractError` or use
    :func:`process_evidence_coverage` for a stable fail-closed result.
    """

    context = _validation_context(
        requirement_ids,
        premise_ids,
        premise_source_scopes,
        source_count,
    )
    answer = _parse_payload(payload)

    _validate_exact_ids(
        actual=tuple(record.requirement_id for record in answer.coverage),
        expected=context.requirement_ids,
        missing=CoverageValidationErrorCode.MISSING_REQUIREMENT_ID,
        duplicate=CoverageValidationErrorCode.DUPLICATE_REQUIREMENT_ID,
        unknown=CoverageValidationErrorCode.UNKNOWN_REQUIREMENT_ID,
        out_of_order=CoverageValidationErrorCode.OUT_OF_ORDER_REQUIREMENT_ID,
    )
    _validate_exact_ids(
        actual=tuple(record.premise_id for record in answer.premise_decisions),
        expected=context.premise_ids,
        missing=CoverageValidationErrorCode.MISSING_PREMISE_ID,
        duplicate=CoverageValidationErrorCode.DUPLICATE_PREMISE_ID,
        unknown=CoverageValidationErrorCode.UNKNOWN_PREMISE_ID,
        out_of_order=CoverageValidationErrorCode.OUT_OF_ORDER_PREMISE_ID,
    )

    unit_ids = tuple(unit.unit_id for unit in answer.answer_units)
    if _has_duplicates(unit_ids):
        raise CoverageContractError(CoverageValidationErrorCode.DUPLICATE_UNIT_ID)
    known_unit_ids = set(unit_ids)
    units_by_id = {unit.unit_id: unit for unit in answer.answer_units}
    first_rendered_unit_id = next(
        (
            unit.unit_id
            for _index, unit in sorted(
                enumerate(answer.answer_units),
                key=lambda item: (item[1].paragraph, item[0]),
            )
        ),
        None,
    )
    requirement_order = {
        requirement_id: index for index, requirement_id in enumerate(context.requirement_ids)
    }

    total_text_characters = sum(len(unit.text) for unit in answer.answer_units)
    if total_text_characters > MAX_TOTAL_UNIT_TEXT_CHARACTERS:
        raise CoverageContractError(CoverageValidationErrorCode.TEXT_LIMIT_EXCEEDED)

    citation_count = 0
    for unit in answer.answer_units:
        if unit.role is AnswerUnitRole.PREMISE_CORRECTION:
            if unit.requirement_ids:
                raise CoverageContractError(
                    CoverageValidationErrorCode.PREMISE_CORRECTION_REQUIREMENT_MISMATCH
                )
        elif not unit.requirement_ids:
            raise CoverageContractError(
                CoverageValidationErrorCode.MISSING_UNIT_REQUIREMENT_ID
            )
        if _has_duplicates(unit.requirement_ids):
            raise CoverageContractError(CoverageValidationErrorCode.DUPLICATE_REQUIREMENT_ID)
        if any(requirement_id not in requirement_order for requirement_id in unit.requirement_ids):
            raise CoverageContractError(CoverageValidationErrorCode.UNKNOWN_UNIT_REQUIREMENT_ID)
        order = tuple(requirement_order[value] for value in unit.requirement_ids)
        if order != tuple(sorted(order)):
            raise CoverageContractError(
                CoverageValidationErrorCode.OUT_OF_ORDER_UNIT_REQUIREMENT_ID
            )

        _validate_source_numbers(unit.source_numbers, context.source_count)
        cited_numbers = parse_citation_numbers(unit.text)
        if not cited_numbers:
            raise CoverageContractError(CoverageValidationErrorCode.MISSING_CITATION)
        _validate_citation_locality(unit.text, cited_numbers)
        if any(number > context.source_count for number in cited_numbers):
            raise CoverageContractError(CoverageValidationErrorCode.UNRESOLVABLE_CITATION)
        if _ordered_unique(cited_numbers) != unit.source_numbers:
            raise CoverageContractError(CoverageValidationErrorCode.CITATION_SOURCE_MISMATCH)
        citation_count += len(cited_numbers)

    premise_scopes = {
        scope.premise_id: scope for scope in context.premise_source_scopes
    }
    correction_reference_counts: Counter[str] = Counter()
    for decision in answer.premise_decisions:
        _validate_source_numbers(decision.source_numbers, context.source_count)
        scope = premise_scopes[decision.premise_id]
        if decision.status in {PremiseStatus.SUPPORTED, PremiseStatus.CONTRADICTED}:
            if not decision.source_numbers:
                raise CoverageContractError(CoverageValidationErrorCode.PREMISE_SOURCE_MISMATCH)
        elif decision.source_numbers:
            raise CoverageContractError(CoverageValidationErrorCode.PREMISE_SOURCE_MISMATCH)
        if decision.status is PremiseStatus.NOT_APPLICABLE:
            raise CoverageContractError(CoverageValidationErrorCode.PREMISE_STATUS_INVALID)
        if decision.status is PremiseStatus.SUPPORTED:
            if not set(decision.source_numbers) <= set(scope.support_source_numbers):
                raise CoverageContractError(
                    CoverageValidationErrorCode.PREMISE_PROVENANCE_MISMATCH
                )
        if decision.status is PremiseStatus.CONTRADICTED:
            if decision.correction_unit_id is None:
                raise CoverageContractError(CoverageValidationErrorCode.PREMISE_CORRECTION_MISSING)
            correction = units_by_id.get(decision.correction_unit_id)
            if (
                correction is None
                or correction.role is not AnswerUnitRole.PREMISE_CORRECTION
                or decision.source_numbers != correction.source_numbers
            ):
                raise CoverageContractError(CoverageValidationErrorCode.PREMISE_CORRECTION_INVALID)
            allowed_correction_sources = set(scope.counter_source_numbers) | set(
                scope.framing_source_numbers
            )
            if (
                not set(decision.source_numbers) <= allowed_correction_sources
                or (
                    scope.framing_source_numbers
                    and not set(decision.source_numbers)
                    & set(scope.framing_source_numbers)
                )
            ):
                raise CoverageContractError(
                    CoverageValidationErrorCode.PREMISE_PROVENANCE_MISMATCH
                )
            if decision.correction_unit_id != first_rendered_unit_id:
                raise CoverageContractError(
                    CoverageValidationErrorCode.PREMISE_CORRECTION_NOT_FIRST
                )
            correction_reference_counts[decision.correction_unit_id] += 1
        elif decision.correction_unit_id is not None:
            raise CoverageContractError(CoverageValidationErrorCode.PREMISE_CORRECTION_INVALID)

    correction_unit_ids = {
        unit.unit_id
        for unit in answer.answer_units
        if unit.role is AnswerUnitRole.PREMISE_CORRECTION
    }
    if (
        set(correction_reference_counts) != correction_unit_ids
        or any(count != 1 for count in correction_reference_counts.values())
    ):
        raise CoverageContractError(CoverageValidationErrorCode.PREMISE_CORRECTION_INVALID)

    coverage_by_requirement = {record.requirement_id: record for record in answer.coverage}
    for record in answer.coverage:
        if _has_duplicates(record.unit_ids):
            raise CoverageContractError(CoverageValidationErrorCode.DUPLICATE_UNIT_REFERENCE)
        if any(unit_id not in known_unit_ids for unit_id in record.unit_ids):
            raise CoverageContractError(CoverageValidationErrorCode.UNKNOWN_UNIT_ID)
        _validate_source_numbers(record.source_numbers, context.source_count)
        _validate_status_shape(record)

        mapped_units = tuple(
            unit for unit in answer.answer_units if record.requirement_id in unit.requirement_ids
        )
        mapped_unit_ids = tuple(unit.unit_id for unit in mapped_units)
        if record.status is RequirementStatus.UNSUPPORTED and mapped_units:
            raise CoverageContractError(
                CoverageValidationErrorCode.UNSUPPORTED_REQUIREMENT_HAS_UNIT
            )
        if record.unit_ids != mapped_unit_ids:
            raise CoverageContractError(CoverageValidationErrorCode.UNIT_MAPPING_MISMATCH)

        mapped_source_numbers = _ordered_unique(
            number for unit in mapped_units for number in unit.source_numbers
        )
        if record.source_numbers != mapped_source_numbers:
            raise CoverageContractError(CoverageValidationErrorCode.SOURCE_MAPPING_MISMATCH)
        if record.status is RequirementStatus.CONFLICTING and len(record.source_numbers) < 2:
            raise CoverageContractError(
                CoverageValidationErrorCode.CONFLICT_REQUIRES_MULTIPLE_SOURCES
            )

    for unit in answer.answer_units:
        for requirement_id in unit.requirement_ids:
            if requirement_id not in coverage_by_requirement:
                raise CoverageContractError(CoverageValidationErrorCode.UNKNOWN_UNIT_REQUIREMENT_ID)

    return ValidatedEvidenceCoverage(
        answer=answer,
        context=context,
        citation_count=citation_count,
    )


def render_evidence_coverage(
    validated: ValidatedEvidenceCoverage,
    *,
    requirement_labels: Mapping[str, str] | None = None,
) -> str:
    """Render every validated unit once, followed by deterministic gap text."""

    answer = validated.answer
    if validated.context.source_count == 0:
        return NO_SOURCES_MESSAGE
    if all(record.status is RequirementStatus.UNSUPPORTED for record in answer.coverage):
        return ALL_UNSUPPORTED_MESSAGE

    indexed_units = tuple(enumerate(answer.answer_units))
    ordered_units = tuple(
        unit
        for _, unit in sorted(
            indexed_units,
            key=lambda item: (item[1].paragraph, item[0]),
        )
    )
    paragraphs = [
        " ".join(unit.text for unit in grouped_units)
        for _, grouped_units in groupby(ordered_units, key=lambda unit: unit.paragraph)
    ]

    labels = requirement_labels or {}
    for record in answer.coverage:
        label = _reader_safe_label(labels.get(record.requirement_id))
        if record.status is RequirementStatus.PARTIAL:
            paragraphs.append(
                f"The retrieved passages only partially establish this requested point ({label})."
            )
        elif record.status is RequirementStatus.UNSUPPORTED:
            paragraphs.append(
                f"The retrieved passages do not establish this requested point ({label})."
            )
        elif record.status is RequirementStatus.CONFLICTING:
            citation = _format_citation(record.source_numbers)
            paragraphs.append(
                f"The retrieved sources conflict about this requested point ({label}) {citation}."
            )

    return "\n\n".join(paragraphs)


def coverage_diagnostic_summary(
    validated: ValidatedEvidenceCoverage,
    *,
    repair_codes: Sequence[CoverageValidationErrorCode] = (),
) -> CoverageDiagnosticSummary:
    """Return a trace-safe summary with no generated or question-derived prose."""

    answer = validated.answer
    normalized_repair_codes = tuple(dict.fromkeys(repair_codes))
    coverage_counts = Counter(record.status for record in answer.coverage)
    premise_counts = Counter(record.status for record in answer.premise_decisions)
    return CoverageDiagnosticSummary(
        schema=EVIDENCE_COVERAGE_DIAGNOSTIC_SCHEMA,
        renderer_version=EVIDENCE_COVERAGE_RENDERER_VERSION,
        validation_result=DiagnosticValidationResult.VALID,
        error_code=None,
        repair_applied=bool(normalized_repair_codes),
        repair_codes=normalized_repair_codes,
        requirement_ids=validated.context.requirement_ids,
        premise_ids=validated.context.premise_ids,
        premise_source_scopes=validated.context.premise_source_scopes,
        requirement_count=len(validated.context.requirement_ids),
        premise_count=len(validated.context.premise_ids),
        source_count=validated.context.source_count,
        coverage_status_counts=RequirementStatusCounts(
            supported=coverage_counts[RequirementStatus.SUPPORTED],
            partial=coverage_counts[RequirementStatus.PARTIAL],
            unsupported=coverage_counts[RequirementStatus.UNSUPPORTED],
            conflicting=coverage_counts[RequirementStatus.CONFLICTING],
        ),
        premise_status_counts=PremiseStatusCounts(
            supported=premise_counts[PremiseStatus.SUPPORTED],
            contradicted=premise_counts[PremiseStatus.CONTRADICTED],
            unresolved=premise_counts[PremiseStatus.UNRESOLVED],
            not_applicable=premise_counts[PremiseStatus.NOT_APPLICABLE],
        ),
        answer_unit_count=len(answer.answer_units),
        citation_count=validated.citation_count,
        coverage=tuple(
            RequirementCoverageDiagnostic(
                requirement_id=record.requirement_id,
                status=record.status,
                unit_ids=record.unit_ids,
                source_numbers=record.source_numbers,
                gap_reason=record.gap_reason,
            )
            for record in answer.coverage
        ),
        premise_decisions=tuple(
            PremiseDecisionDiagnostic(
                premise_id=record.premise_id,
                status=record.status,
                source_numbers=record.source_numbers,
                correction_unit_id=record.correction_unit_id,
            )
            for record in answer.premise_decisions
        ),
        answer_units=tuple(
            AnswerUnitDiagnostic(
                unit_id=unit.unit_id,
                requirement_ids=unit.requirement_ids,
                role=unit.role,
                source_numbers=unit.source_numbers,
                paragraph=unit.paragraph,
            )
            for unit in answer.answer_units
        ),
    )


def process_evidence_coverage(
    payload: EvidenceCoverageAnswer | Mapping[str, Any] | None,
    *,
    requirement_ids: Sequence[str],
    premise_ids: Sequence[str] = (),
    premise_source_scopes: Sequence[PremiseSourceScope | Mapping[str, Any]] = (),
    source_count: int,
    requirement_labels: Mapping[str, str] | None = None,
    refused: bool = False,
) -> EvidenceCoverageResult:
    """Validate and render, or return one stable fail-closed result.

    ``payload`` may never be raw prose.  ``None`` or ``refused=True`` represents
    a refusal/no parsed output and is not retried here.
    """

    try:
        context = _validation_context(
            requirement_ids,
            premise_ids,
            premise_source_scopes,
            source_count,
        )
    except CoverageContractError as error:
        return _contract_failure_result(
            context=None,
            error_code=error.code,
        )

    if context.source_count == 0:
        return EvidenceCoverageResult(
            status=CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE,
            answer=NO_SOURCES_MESSAGE,
            error_code=None,
            diagnostics=_empty_diagnostic_summary(
                context,
                validation_result=DiagnosticValidationResult.NOT_RUN,
                error_code=None,
            ),
        )

    if refused or payload is None:
        return _contract_failure_result(
            context=context,
            error_code=CoverageValidationErrorCode.GENERATION_REFUSED,
        )

    repair_codes: tuple[CoverageValidationErrorCode, ...] = ()
    try:
        normalized_payload, repair_codes = _normalize_mechanical_contract(
            payload,
            context=context,
        )
        validated = validate_evidence_coverage(
            normalized_payload,
            requirement_ids=context.requirement_ids,
            premise_ids=context.premise_ids,
            premise_source_scopes=context.premise_source_scopes,
            source_count=context.source_count,
        )
    except CoverageContractError as error:
        return _contract_failure_result(
            context=context,
            error_code=error.code,
            repair_codes=error.repair_codes or repair_codes,
        )

    rendered = render_evidence_coverage(
        validated,
        requirement_labels=requirement_labels,
    )
    all_unsupported = all(
        record.status is RequirementStatus.UNSUPPORTED for record in validated.answer.coverage
    )
    return EvidenceCoverageResult(
        status=(
            CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE
            if all_unsupported
            else CoverageOutcomeStatus.ANSWERED
        ),
        answer=rendered,
        error_code=None,
        diagnostics=coverage_diagnostic_summary(
            validated,
            repair_codes=repair_codes,
        ),
    )


def _validation_context(
    requirement_ids: Sequence[str],
    premise_ids: Sequence[str],
    premise_source_scopes: Sequence[PremiseSourceScope | Mapping[str, Any]],
    source_count: int,
) -> CoverageValidationContext:
    if (
        isinstance(requirement_ids, (str, bytes))
        or isinstance(premise_ids, (str, bytes))
        or isinstance(premise_source_scopes, (str, bytes, Mapping))
    ):
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_CONTEXT)
    try:
        scopes = tuple(
            (
                value
                if isinstance(value, PremiseSourceScope)
                else PremiseSourceScope.model_validate(value)
            )
            for value in premise_source_scopes
        )
        context = CoverageValidationContext(
            requirement_ids=tuple(requirement_ids),
            premise_ids=tuple(premise_ids),
            premise_source_scopes=scopes,
            source_count=source_count,
        )
    except (TypeError, ValidationError):
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_CONTEXT) from None
    scope_ids = tuple(scope.premise_id for scope in context.premise_source_scopes)
    if (
        _has_duplicates(context.requirement_ids)
        or _has_duplicates(context.premise_ids)
        or scope_ids != context.premise_ids
        or any(
            _has_duplicates(source_numbers)
            or any(
                source_number < 1 or source_number > context.source_count
                for source_number in source_numbers
            )
            for scope in context.premise_source_scopes
            for source_numbers in (
                scope.support_source_numbers,
                scope.counter_source_numbers,
                scope.framing_source_numbers,
            )
        )
    ):
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_CONTEXT)
    return context


def _parse_payload(
    payload: EvidenceCoverageAnswer | Mapping[str, Any],
) -> EvidenceCoverageAnswer:
    if isinstance(payload, EvidenceCoverageAnswer):
        return payload
    if not isinstance(payload, Mapping):
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_PAYLOAD)
    try:
        return EvidenceCoverageAnswer.model_validate(payload)
    except ValidationError:
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_PAYLOAD) from None


def _normalize_mechanical_contract(
    payload: EvidenceCoverageAnswer | Mapping[str, Any],
    *,
    context: CoverageValidationContext,
) -> tuple[EvidenceCoverageAnswer, tuple[CoverageValidationErrorCode, ...]]:
    """Canonicalize only redundant ordering and derived coverage mappings.

    Model output occasionally contains the right factual units and citation
    sets but serializes redundant bookkeeping in a different order or with a
    stale derived mapping.  Repairing those fields cannot add a claim or a
    source.  Every semantic field remains untouched, and malformed/unknown
    identifiers, invalid source numbers, unsupported claims, and citation-set
    disagreements are deliberately left for the strict validator to reject
    with their precise contract code.
    """

    answer = _parse_payload(payload)
    repair_codes: list[CoverageValidationErrorCode] = []
    requirement_order = {
        requirement_id: index for index, requirement_id in enumerate(context.requirement_ids)
    }

    normalized_units: list[AnswerUnit] = []
    for unit in answer.answer_units:
        requirement_ids = unit.requirement_ids
        if not _has_duplicates(requirement_ids) and all(
            requirement_id in requirement_order for requirement_id in requirement_ids
        ):
            canonical_requirement_ids = tuple(
                sorted(requirement_ids, key=requirement_order.__getitem__)
            )
            if canonical_requirement_ids != requirement_ids:
                repair_codes.append(CoverageValidationErrorCode.OUT_OF_ORDER_UNIT_REQUIREMENT_ID)
                requirement_ids = canonical_requirement_ids

        source_numbers = unit.source_numbers
        try:
            cited_numbers = parse_citation_numbers(unit.text)
        except CoverageContractError as error:
            raise CoverageContractError(
                error.code,
                repair_codes=repair_codes,
            ) from None
        canonical_citations = _ordered_unique(cited_numbers)
        if not _has_duplicates(source_numbers) and set(source_numbers) == set(canonical_citations):
            if canonical_citations != source_numbers:
                repair_codes.append(CoverageValidationErrorCode.CITATION_SOURCE_MISMATCH)
            source_numbers = canonical_citations

        normalized_units.append(
            unit.model_copy(
                update={
                    "requirement_ids": requirement_ids,
                    "source_numbers": source_numbers,
                }
            )
        )

    answer_units = tuple(normalized_units)
    known_unit_ids = {unit.unit_id for unit in answer_units}

    coverage = _reorder_exact_records(
        answer.coverage,
        expected_ids=context.requirement_ids,
        id_attribute="requirement_id",
    )
    if coverage != answer.coverage:
        repair_codes.append(CoverageValidationErrorCode.OUT_OF_ORDER_REQUIREMENT_ID)
    normalized_coverage: list[RequirementCoverage] = []
    for record in coverage:
        expected_gap = _STATUS_GAP_REASON[record.status]
        if record.gap_reason is not expected_gap:
            repair_codes.append(CoverageValidationErrorCode.STATUS_GAP_MISMATCH)
            record = record.model_copy(update={"gap_reason": expected_gap})

        # An unsupported record with any claim/source association is never
        # repairable: the strict validator must reject it.
        if record.status is RequirementStatus.UNSUPPORTED:
            normalized_coverage.append(record)
            continue

        mappings_are_safe_to_derive = (
            not _has_duplicates(record.unit_ids)
            and all(unit_id in known_unit_ids for unit_id in record.unit_ids)
            and not _has_duplicates(record.source_numbers)
            and all(
                1 <= source_number <= context.source_count
                for source_number in record.source_numbers
            )
        )
        if not mappings_are_safe_to_derive:
            normalized_coverage.append(record)
            continue

        mapped_units = tuple(
            unit for unit in answer_units if record.requirement_id in unit.requirement_ids
        )
        mapped_unit_ids = tuple(unit.unit_id for unit in mapped_units)
        mapped_source_numbers = _ordered_unique(
            source_number for unit in mapped_units for source_number in unit.source_numbers
        )
        if not record.unit_ids or not record.source_numbers:
            if record.unit_ids != mapped_unit_ids or record.source_numbers != mapped_source_numbers:
                repair_codes.append(CoverageValidationErrorCode.STATUS_UNIT_MISMATCH)
        else:
            if record.unit_ids != mapped_unit_ids:
                repair_codes.append(CoverageValidationErrorCode.UNIT_MAPPING_MISMATCH)
            if record.source_numbers != mapped_source_numbers:
                repair_codes.append(CoverageValidationErrorCode.SOURCE_MAPPING_MISMATCH)
        normalized_coverage.append(
            record.model_copy(
                update={
                    "unit_ids": mapped_unit_ids,
                    "source_numbers": mapped_source_numbers,
                }
            )
        )

    premise_decisions = _reorder_exact_records(
        answer.premise_decisions,
        expected_ids=context.premise_ids,
        id_attribute="premise_id",
    )
    if premise_decisions != answer.premise_decisions:
        repair_codes.append(CoverageValidationErrorCode.OUT_OF_ORDER_PREMISE_ID)
    normalized_premise_decisions: list[PremiseDecision] = []
    units_by_id = {unit.unit_id: unit for unit in answer_units}
    for decision in premise_decisions:
        source_numbers = decision.source_numbers
        correction = (
            units_by_id.get(decision.correction_unit_id)
            if decision.correction_unit_id is not None
            else None
        )
        mappings_are_safe_to_derive = (
            decision.status is PremiseStatus.CONTRADICTED
            and correction is not None
            and correction.role is AnswerUnitRole.PREMISE_CORRECTION
            and bool(source_numbers)
            and not _has_duplicates(source_numbers)
            and all(1 <= source_number <= context.source_count for source_number in source_numbers)
            and not _has_duplicates(correction.source_numbers)
            and all(
                1 <= source_number <= context.source_count
                for source_number in correction.source_numbers
            )
        )
        if mappings_are_safe_to_derive and set(correction.source_numbers) < set(source_numbers):
            repair_codes.append(CoverageValidationErrorCode.PREMISE_SOURCE_MISMATCH)
            source_numbers = correction.source_numbers
        normalized_premise_decisions.append(
            decision.model_copy(update={"source_numbers": source_numbers})
        )
    normalized_answer = answer.model_copy(
        update={
            "premise_decisions": tuple(normalized_premise_decisions),
            "coverage": tuple(normalized_coverage),
            "answer_units": answer_units,
        }
    )
    return normalized_answer, tuple(dict.fromkeys(repair_codes))


def _reorder_exact_records(
    records: Sequence[Any],
    *,
    expected_ids: tuple[str, ...],
    id_attribute: str,
) -> tuple[Any, ...]:
    """Return trusted-input order only when the record identity set is exact."""

    actual_ids = tuple(getattr(record, id_attribute) for record in records)
    if _has_duplicates(actual_ids) or set(actual_ids) != set(expected_ids):
        return tuple(records)
    by_id = {getattr(record, id_attribute): record for record in records}
    return tuple(by_id[record_id] for record_id in expected_ids)


def _validate_exact_ids(
    *,
    actual: tuple[str, ...],
    expected: tuple[str, ...],
    missing: CoverageValidationErrorCode,
    duplicate: CoverageValidationErrorCode,
    unknown: CoverageValidationErrorCode,
    out_of_order: CoverageValidationErrorCode,
) -> None:
    if _has_duplicates(actual):
        raise CoverageContractError(duplicate)
    expected_set = set(expected)
    actual_set = set(actual)
    if not actual_set <= expected_set:
        raise CoverageContractError(unknown)
    if not expected_set <= actual_set:
        raise CoverageContractError(missing)
    if actual != expected:
        raise CoverageContractError(out_of_order)


def _validate_source_numbers(
    source_numbers: tuple[int, ...],
    source_count: int,
) -> None:
    if _has_duplicates(source_numbers):
        raise CoverageContractError(CoverageValidationErrorCode.DUPLICATE_SOURCE_NUMBER)
    if any(number < 1 or number > source_count for number in source_numbers):
        raise CoverageContractError(CoverageValidationErrorCode.SOURCE_NUMBER_OUT_OF_RANGE)


def _validate_citation_locality(
    text: str,
    _cited_numbers: Sequence[int],
) -> None:
    """Require one terminally cited sentence-shaped unit.

    Local code cannot decide whether a passage entails prose or whether one
    grammatical sentence contains more than one factual claim. It can reliably
    reserve all sentence-ending punctuation for the terminal citation, which
    prevents a trailing citation bundle from covering several punctuated
    sentences. Generated claims must spell out or rephrase period-containing
    abbreviations, titles, initials, and decimals.
    """

    citations = tuple(CITATION_PATTERN.finditer(text))
    if len(citations) != 1:
        raise CoverageContractError(CoverageValidationErrorCode.CITATION_LOCALITY_INVALID)
    citation = citations[0]
    if _TERMINAL_CITATION_PATTERN.fullmatch(text[citation.start() :]) is None:
        raise CoverageContractError(CoverageValidationErrorCode.CITATION_LOCALITY_INVALID)

    claim = text[: citation.start()].rstrip()
    if (
        not claim
        or "\n" in claim
        or "\r" in claim
        or ";" in claim
        or any(mark in claim for mark in ".!?")
    ):
        raise CoverageContractError(CoverageValidationErrorCode.CITATION_LOCALITY_INVALID)


def _validate_status_shape(record: RequirementCoverage) -> None:
    expected_gap = _STATUS_GAP_REASON[record.status]
    if record.gap_reason is not expected_gap:
        raise CoverageContractError(CoverageValidationErrorCode.STATUS_GAP_MISMATCH)

    if record.status is RequirementStatus.UNSUPPORTED:
        if record.unit_ids or record.source_numbers:
            raise CoverageContractError(
                CoverageValidationErrorCode.UNSUPPORTED_REQUIREMENT_HAS_UNIT
            )
    elif not record.unit_ids or not record.source_numbers:
        raise CoverageContractError(CoverageValidationErrorCode.STATUS_UNIT_MISMATCH)


def _reader_safe_label(label: str | None) -> str:
    if not isinstance(label, str) or not label.strip():
        return "a requested part"
    normalized = " ".join(label.split())
    normalized = normalized.replace("[", "(").replace("]", ")")
    if len(normalized) > MAX_REQUIREMENT_LABEL_CHARACTERS:
        normalized = normalized[:MAX_REQUIREMENT_LABEL_CHARACTERS].rstrip()
    return normalized or "a requested part"


def _format_citation(source_numbers: tuple[int, ...]) -> str:
    return "[" + ", ".join(f"Source {number}" for number in source_numbers) + "]"


def _ordered_unique(values: Iterable[int]) -> tuple[int, ...]:
    return tuple(dict.fromkeys(values))


def _has_duplicates(values: Sequence[Any]) -> bool:
    return len(values) != len(set(values))


def _empty_diagnostic_summary(
    context: CoverageValidationContext,
    *,
    validation_result: DiagnosticValidationResult,
    error_code: CoverageValidationErrorCode | None,
    repair_codes: Sequence[CoverageValidationErrorCode] = (),
) -> CoverageDiagnosticSummary:
    normalized_repair_codes = tuple(dict.fromkeys(repair_codes))
    return CoverageDiagnosticSummary(
        schema=EVIDENCE_COVERAGE_DIAGNOSTIC_SCHEMA,
        renderer_version=EVIDENCE_COVERAGE_RENDERER_VERSION,
        validation_result=validation_result,
        error_code=error_code,
        repair_applied=bool(normalized_repair_codes),
        repair_codes=normalized_repair_codes,
        requirement_ids=context.requirement_ids,
        premise_ids=context.premise_ids,
        premise_source_scopes=context.premise_source_scopes,
        requirement_count=len(context.requirement_ids),
        premise_count=len(context.premise_ids),
        source_count=context.source_count,
        coverage_status_counts=RequirementStatusCounts(
            supported=0,
            partial=0,
            unsupported=0,
            conflicting=0,
        ),
        premise_status_counts=PremiseStatusCounts(
            supported=0,
            contradicted=0,
            unresolved=0,
            not_applicable=0,
        ),
        answer_unit_count=0,
        citation_count=0,
        coverage=(),
        premise_decisions=(),
        answer_units=(),
    )


def _contract_failure_result(
    *,
    context: CoverageValidationContext | None,
    error_code: CoverageValidationErrorCode,
    repair_codes: Sequence[CoverageValidationErrorCode] = (),
) -> EvidenceCoverageResult:
    normalized_repair_codes = tuple(dict.fromkeys(repair_codes))
    if context is None:
        diagnostics = CoverageDiagnosticSummary(
            schema=EVIDENCE_COVERAGE_DIAGNOSTIC_SCHEMA,
            renderer_version=EVIDENCE_COVERAGE_RENDERER_VERSION,
            validation_result=DiagnosticValidationResult.INVALID,
            error_code=error_code,
            repair_applied=bool(normalized_repair_codes),
            repair_codes=normalized_repair_codes,
            requirement_ids=(),
            premise_ids=(),
            premise_source_scopes=(),
            requirement_count=0,
            premise_count=0,
            source_count=0,
            coverage_status_counts=RequirementStatusCounts(
                supported=0,
                partial=0,
                unsupported=0,
                conflicting=0,
            ),
            premise_status_counts=PremiseStatusCounts(
                supported=0,
                contradicted=0,
                unresolved=0,
                not_applicable=0,
            ),
            answer_unit_count=0,
            citation_count=0,
            coverage=(),
            premise_decisions=(),
            answer_units=(),
        )
    else:
        diagnostics = _empty_diagnostic_summary(
            context,
            validation_result=DiagnosticValidationResult.INVALID,
            error_code=error_code,
            repair_codes=normalized_repair_codes,
        )
    return EvidenceCoverageResult(
        status=CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED,
        answer=GENERATION_CONTRACT_FAILED_MESSAGE,
        error_code=CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED.value,
        diagnostics=diagnostics,
    )
