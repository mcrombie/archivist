"""Pure contracts, validation, diagnostics, and rendering for evidence coverage.

This module deliberately has no model or retrieval dependencies.  A generation
adapter may construct :class:`EvidenceCoverageAnswer`, but only a
:class:`ValidatedEvidenceCoverage` can be rendered.
"""

from __future__ import annotations

import re
import unicodedata
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
    ValidationInfo,
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
    "INTERPRETIVE_EVIDENCE_COVERAGE_SCHEMA",
    "MAX_ANSWER_UNITS",
    "NO_SOURCES_MESSAGE",
    "AnswerUnit",
    "AnswerUnitRole",
    "CoverageContractError",
    "CoverageDiagnosticSummary",
    "CoverageOutcomeStatus",
    "CoverageValidationContext",
    "CoverageValidationErrorCode",
    "CitationLocalityFailure",
    "CitationLocalityFailureCode",
    "DiagnosticValidationResult",
    "EvidenceDimension",
    "EvidenceDimensionCoverage",
    "EvidenceObligationCoverage",
    "EvidenceObligationFocus",
    "EvidenceObligationScope",
    "EvidenceCoverageAnswer",
    "EvidenceCoverageResult",
    "GapReason",
    "InterpretiveEvidenceCoverageAnswer",
    "InterpretiveMove",
    "ObligationLink",
    "PremiseDecision",
    "PremiseSourceScope",
    "PremiseStatus",
    "RequirementCoverage",
    "RequirementStatus",
    "ValidatedEvidenceCoverage",
    "coverage_diagnostic_summary",
    "parse_citation_numbers",
    "process_evidence_coverage",
    "process_interpretive_evidence_coverage",
    "render_evidence_coverage",
    "validate_evidence_coverage",
]


EVIDENCE_COVERAGE_SCHEMA = "archivist.evidence_coverage/3"
INTERPRETIVE_EVIDENCE_COVERAGE_SCHEMA = (
    "archivist.interpretive_evidence_coverage/2"
)
EVIDENCE_COVERAGE_DIAGNOSTIC_SCHEMA = "archivist.evidence_coverage_diagnostics/5"
EVIDENCE_COVERAGE_RENDERER_VERSION = "evidence-coverage-renderer/1"
EVIDENCE_COVERAGE_NORMALIZER_VERSION = "evidence-coverage-normalizer/5"

MAX_REQUIREMENTS = 8
MAX_PREMISES = 2
MAX_SOURCES = 8
MAX_ANSWER_UNITS = 32
MAX_EVIDENCE_OBLIGATIONS = 32
MAX_OBLIGATION_DIMENSIONS = 4
MAX_UNIT_TEXT_CHARACTERS = 2_000
MAX_TOTAL_UNIT_TEXT_CHARACTERS = 12_000
MAX_INTERPRETIVE_PREFACE_CHARACTERS = 1_200
MAX_INTERPRETIVE_CODA_CHARACTERS = 600
MAX_REQUIREMENT_LABEL_CHARACTERS = 240

CITATION_GRAMMAR = r"\[Source\s+\d+(?:\s*,\s*Source\s+\d+)*\]"
CITATION_PATTERN = re.compile(CITATION_GRAMMAR)
_BRACKETED_PATTERN = re.compile(r"\[[^\[\]]*\]")
_CITATION_NUMBER_PATTERN = re.compile(r"Source\s+(\d+)")
_TERMINAL_CITATION_PATTERN = re.compile(rf"{CITATION_GRAMMAR}[.!?]$")
_FIRST_PERSON_PATTERN = re.compile(
    r"(?<![\w])(?:"
    r"i|me|my|mine|myself|we|us|our|ours|ourselves|"
    r"i['’](?:m|ve|d|ll)|we['’](?:re|ve|d|ll)|let['’]s"
    r")(?![\w])",
    flags=re.IGNORECASE,
)
ATOMIC_CITATION_TEXT_PATTERN = (
    rf"^[^.!?;\r\n\[\]]*[^\s.!?;\r\n\[\]][^.!?;\r\n\[\]]*"
    rf"{CITATION_GRAMMAR}[.!?]$"
)

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
InterpretivePrefaceText = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=MAX_INTERPRETIVE_PREFACE_CHARACTERS,
    ),
]
InterpretiveCodaText = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=MAX_INTERPRETIVE_CODA_CHARACTERS,
    ),
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


class InterpretiveMove(StrEnum):
    ACHIEVEMENT_AND_DURABLE_CAPACITY = "achievement_and_durable_capacity"
    TRAGIC_TENSION_AND_CONTINGENCY = "tragic_tension_and_contingency"
    FAITH_DUTY_AND_MORAL_CONSEQUENCE = "faith_duty_and_moral_consequence"
    HUMAN_DIGNITY_AND_LIVED_CONSEQUENCE = "human_dignity_and_lived_consequence"
    INQUIRY_REFORM_AND_SCRUTINY = "inquiry_reform_and_scrutiny"


class CoverageOutcomeStatus(StrEnum):
    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    GENERATION_CONTRACT_FAILED = "generation_contract_failed"


class DiagnosticValidationResult(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    NOT_RUN = "not_run"


class CitationLocalityFailureCode(StrEnum):
    MULTIPLE_CITATION_GROUPS = "multiple_citation_groups"
    MISSING_TERMINAL_PUNCTUATION = "missing_terminal_punctuation"
    TRAILING_CONTENT_AFTER_CITATION = "trailing_content_after_citation"
    EMPTY_CLAIM = "empty_claim"
    MULTILINE_CLAIM = "multiline_claim"
    SEMICOLON_IN_CLAIM = "semicolon_in_claim"
    PRE_CITATION_TERMINAL_PUNCTUATION = "pre_citation_terminal_punctuation"
    INTERNAL_SENTENCE_TERMINATOR = "internal_sentence_terminator"


class EvidenceObligationFocus(StrEnum):
    ORIGIN = "origin"
    TRANSITION = "transition"
    MECHANISM = "mechanism"
    ENDPOINT = "endpoint"
    CROSS_CUTTING = "cross_cutting"


class EvidenceDimension(StrEnum):
    STAGE_DEVELOPMENT = "stage_development"
    CAUSE_OR_ENABLER = "cause_or_enabler"
    MECHANISM = "mechanism"
    CONSEQUENCE = "consequence"
    CONTINUITY_OR_CHANGE = "continuity_or_change"
    QUALIFICATION = "qualification"


_DIMENSION_COMPATIBLE_ROLES = {
    EvidenceDimension.STAGE_DEVELOPMENT: frozenset(
        {
            AnswerUnitRole.DEFINITION,
            AnswerUnitRole.IDENTITY,
            AnswerUnitRole.EVENT,
            AnswerUnitRole.CHRONOLOGY,
        }
    ),
    EvidenceDimension.CAUSE_OR_ENABLER: frozenset(
        {
            AnswerUnitRole.CAUSE,
            AnswerUnitRole.MECHANISM,
        }
    ),
    EvidenceDimension.MECHANISM: frozenset(
        {
            AnswerUnitRole.CAUSE,
            AnswerUnitRole.MECHANISM,
        }
    ),
    EvidenceDimension.CONSEQUENCE: frozenset(
        {
            AnswerUnitRole.EVENT,
            AnswerUnitRole.MECHANISM,
            AnswerUnitRole.CONSEQUENCE,
            AnswerUnitRole.CHRONOLOGY,
        }
    ),
    EvidenceDimension.CONTINUITY_OR_CHANGE: frozenset(
        {
            AnswerUnitRole.MECHANISM,
            AnswerUnitRole.CONSEQUENCE,
            AnswerUnitRole.CHRONOLOGY,
            AnswerUnitRole.QUALIFICATION,
        }
    ),
    EvidenceDimension.QUALIFICATION: frozenset(
        {
            AnswerUnitRole.COUNTERARGUMENT,
            AnswerUnitRole.QUALIFICATION,
        }
    ),
}


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
    MISSING_OBLIGATION_ID = "missing_obligation_id"
    DUPLICATE_OBLIGATION_ID = "duplicate_obligation_id"
    UNKNOWN_OBLIGATION_ID = "unknown_obligation_id"
    OUT_OF_ORDER_OBLIGATION_ID = "out_of_order_obligation_id"
    MISSING_OBLIGATION_DIMENSION = "missing_obligation_dimension"
    DUPLICATE_OBLIGATION_DIMENSION = "duplicate_obligation_dimension"
    UNKNOWN_OBLIGATION_DIMENSION = "unknown_obligation_dimension"
    OUT_OF_ORDER_OBLIGATION_DIMENSION = "out_of_order_obligation_dimension"
    MISSING_UNIT_OBLIGATION_LINK = "missing_unit_obligation_link"
    DUPLICATE_UNIT_OBLIGATION_LINK = "duplicate_unit_obligation_link"
    UNKNOWN_UNIT_OBLIGATION_LINK = "unknown_unit_obligation_link"
    OUT_OF_ORDER_UNIT_OBLIGATION_LINK = "out_of_order_unit_obligation_link"
    OBLIGATION_SOURCE_MISMATCH = "obligation_source_mismatch"
    OBLIGATION_REQUIREMENT_MISMATCH = "obligation_requirement_mismatch"
    OBLIGATION_UNIT_MAPPING_MISMATCH = "obligation_unit_mapping_mismatch"
    OBLIGATION_SOURCE_MAPPING_MISMATCH = "obligation_source_mapping_mismatch"
    UNSUPPORTED_OBLIGATION_HAS_UNIT = "unsupported_obligation_has_unit"
    OBLIGATION_ROLE_MISMATCH = "obligation_role_mismatch"
    OBLIGATION_REQUIREMENT_STATUS_MISMATCH = "obligation_requirement_status_mismatch"
    OBLIGATION_DIMENSION_CAPACITY_EXCEEDED = (
        "obligation_dimension_capacity_exceeded"
    )
    MISSING_INTERPRETIVE_PARAGRAPH = "missing_interpretive_paragraph"
    INTERPRETIVE_MOVE_MISMATCH = "interpretive_move_mismatch"
    INTERPRETIVE_CITATION_FORBIDDEN = "interpretive_citation_forbidden"
    INTERPRETIVE_SENTENCE_COUNT_INVALID = "interpretive_sentence_count_invalid"
    INTERPRETIVE_FIRST_PERSON_FORBIDDEN = "interpretive_first_person_forbidden"
    INTERPRETIVE_SUBJECT_MISSING = "interpretive_subject_missing"
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


class ObligationLink(_ContractModel):
    obligation_id: Identifier
    dimension: EvidenceDimension


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
        ),
        json_schema_extra={"pattern": ATOMIC_CITATION_TEXT_PATTERN},
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
    obligation_links: tuple[ObligationLink, ...] = Field(
        default=(),
        max_length=MAX_EVIDENCE_OBLIGATIONS,
        description=(
            "Exact paragraph-level evidence obligations and dimensions realized by "
            "this unit. Premise corrections use an empty list."
        ),
    )

    @field_validator("text")
    @classmethod
    def reject_blank_or_padded_text(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("answer unit text must be nonblank and have no outer whitespace")
        return value


class EvidenceDimensionCoverage(_ContractModel):
    dimension: EvidenceDimension
    status: RequirementStatus
    unit_ids: tuple[Identifier, ...] = Field(max_length=MAX_ANSWER_UNITS)
    source_numbers: tuple[SourceNumber, ...] = Field(max_length=MAX_SOURCES)
    gap_reason: GapReason


class EvidenceObligationCoverage(_ContractModel):
    obligation_id: Identifier
    dimensions: tuple[EvidenceDimensionCoverage, ...] = Field(
        min_length=1,
        max_length=MAX_OBLIGATION_DIMENSIONS,
    )


class EvidenceCoverageAnswer(_ContractModel):
    schema_version: Literal["archivist.evidence_coverage/3"] = Field(alias="schema")
    premise_decisions: tuple[PremiseDecision, ...] = Field(max_length=MAX_PREMISES)
    coverage: tuple[RequirementCoverage, ...] = Field(
        min_length=1,
        max_length=MAX_REQUIREMENTS,
    )
    obligation_coverage: tuple[EvidenceObligationCoverage, ...] = Field(
        default=(),
        max_length=MAX_EVIDENCE_OBLIGATIONS,
    )
    answer_units: tuple[AnswerUnit, ...] = Field(max_length=MAX_ANSWER_UNITS)

    @property
    def schema(self) -> str:
        return self.schema_version


class InterpretiveEvidenceCoverageAnswer(EvidenceCoverageAnswer):
    """Evidence coverage framed by explicitly subjective, uncited prose."""

    schema_version: Literal["archivist.interpretive_evidence_coverage/2"] = (
        Field(alias="schema")
    )
    interpretive_moves: tuple[InterpretiveMove, ...] = Field(
        min_length=1,
        max_length=2,
        description=(
            "The exact ordered rhetorical moves requested in the input contract."
        ),
    )
    interpretive_preface: InterpretivePrefaceText = Field(
        description=(
            "An impersonal, uncited two- or three-sentence opening paragraph that "
            "directly names the question's subject, makes value judgments through "
            "the selected settings, and introduces no new historical facts."
        ),
    )
    interpretive_coda: InterpretiveCodaText = Field(
        description=(
            "An impersonal, uncited one-sentence closing judgment that directly "
            "returns to the question's subject, embodies the selected settings, "
            "and introduces no new historical facts."
        ),
    )

    @field_validator("interpretive_preface", "interpretive_coda")
    @classmethod
    def reject_blank_padded_or_multiline_framing(cls, value: str) -> str:
        if (
            not value.strip()
            or value != value.strip()
            or "\n" in value
            or "\r" in value
        ):
            raise ValueError(
                "interpretive framing must be one nonblank paragraph with no outer whitespace"
            )
        return value


class PremiseSourceScope(_ContractModel):
    """Trusted post-gate source provenance for one premise hypothesis."""

    premise_id: Identifier
    support_source_numbers: tuple[SourceNumber, ...] = Field(max_length=MAX_SOURCES)
    counter_source_numbers: tuple[SourceNumber, ...] = Field(max_length=MAX_SOURCES)
    framing_source_numbers: tuple[SourceNumber, ...] = Field(max_length=MAX_SOURCES)


class EvidenceObligationScope(_ContractModel):
    """Trusted paragraph-level source provenance for a broad-answer obligation."""

    obligation_id: Identifier
    source_number: SourceNumber
    paragraph_start: Annotated[int, Field(strict=True, ge=1)]
    paragraph_end: Annotated[int, Field(strict=True, ge=1)]
    allowed_requirement_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=MAX_REQUIREMENTS,
    )
    focus: EvidenceObligationFocus
    dimension_ids: tuple[EvidenceDimension, ...] = Field(
        min_length=1,
        max_length=MAX_OBLIGATION_DIMENSIONS,
    )
    required_for_requirement_status: bool

    @field_validator("paragraph_end")
    @classmethod
    def paragraph_range_is_forward(
        cls,
        value: int,
        info: ValidationInfo,
    ) -> int:
        start = info.data.get("paragraph_start")
        if isinstance(start, int) and value < start:
            raise ValueError("obligation paragraph range must be forward")
        return value

    @field_validator("allowed_requirement_ids", "dimension_ids")
    @classmethod
    def obligation_values_are_unique(cls, values: tuple[Any, ...]) -> tuple[Any, ...]:
        if len(values) != len(set(values)):
            raise ValueError("obligation scope values must be unique")
        return values


class CoverageValidationContext(_ContractModel):
    requirement_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=MAX_REQUIREMENTS,
    )
    premise_ids: tuple[Identifier, ...] = Field(max_length=MAX_PREMISES)
    premise_source_scopes: tuple[PremiseSourceScope, ...] = Field(
        max_length=MAX_PREMISES
    )
    obligation_scopes: tuple[EvidenceObligationScope, ...] = Field(
        max_length=MAX_EVIDENCE_OBLIGATIONS,
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
    obligation_links: tuple[ObligationLink, ...]


class CitationLocalityFailure(_ContractModel):
    unit_id: Identifier
    unit_ordinal: Annotated[int, Field(strict=True, ge=1, le=MAX_ANSWER_UNITS)]
    code: CitationLocalityFailureCode


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
    schema_version: Literal["archivist.evidence_coverage_diagnostics/5"] = Field(alias="schema")
    renderer_version: Literal["evidence-coverage-renderer/1"]
    validation_result: DiagnosticValidationResult
    error_code: CoverageValidationErrorCode | None
    citation_locality_failure: CitationLocalityFailure | None
    repair_applied: bool
    repair_codes: tuple[CoverageValidationErrorCode, ...]
    requirement_ids: tuple[Identifier, ...]
    premise_ids: tuple[Identifier, ...]
    premise_source_scopes: tuple[PremiseSourceScope, ...]
    obligation_scopes: tuple[EvidenceObligationScope, ...]
    requirement_count: int = Field(ge=0, le=MAX_REQUIREMENTS)
    premise_count: int = Field(ge=0, le=MAX_PREMISES)
    obligation_count: int = Field(ge=0, le=MAX_EVIDENCE_OBLIGATIONS)
    source_count: int = Field(ge=0, le=MAX_SOURCES)
    coverage_status_counts: RequirementStatusCounts
    premise_status_counts: PremiseStatusCounts
    answer_unit_count: int = Field(ge=0, le=MAX_ANSWER_UNITS)
    citation_count: int = Field(ge=0)
    coverage: tuple[RequirementCoverageDiagnostic, ...]
    obligation_coverage: tuple[EvidenceObligationCoverage, ...]
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
        citation_locality_failure: CitationLocalityFailure | None = None,
    ):
        self.code = code
        self.repair_codes = tuple(dict.fromkeys(repair_codes))
        self.citation_locality_failure = citation_locality_failure
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
    obligation_scopes: Sequence[EvidenceObligationScope | Mapping[str, Any]] = (),
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
        obligation_scopes,
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
    _validate_exact_ids(
        actual=tuple(record.obligation_id for record in answer.obligation_coverage),
        expected=tuple(scope.obligation_id for scope in context.obligation_scopes),
        missing=CoverageValidationErrorCode.MISSING_OBLIGATION_ID,
        duplicate=CoverageValidationErrorCode.DUPLICATE_OBLIGATION_ID,
        unknown=CoverageValidationErrorCode.UNKNOWN_OBLIGATION_ID,
        out_of_order=CoverageValidationErrorCode.OUT_OF_ORDER_OBLIGATION_ID,
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
    obligation_scopes_by_id = {
        scope.obligation_id: scope for scope in context.obligation_scopes
    }
    obligation_order = {
        scope.obligation_id: index
        for index, scope in enumerate(context.obligation_scopes)
    }
    obligation_dimension_order = {
        (scope.obligation_id, dimension): index
        for scope in context.obligation_scopes
        for index, dimension in enumerate(scope.dimension_ids)
    }

    total_text_characters = sum(len(unit.text) for unit in answer.answer_units)
    if total_text_characters > MAX_TOTAL_UNIT_TEXT_CHARACTERS:
        raise CoverageContractError(CoverageValidationErrorCode.TEXT_LIMIT_EXCEEDED)

    citation_count = 0
    for unit_ordinal, unit in enumerate(answer.answer_units, start=1):
        if unit.role is AnswerUnitRole.PREMISE_CORRECTION:
            if unit.requirement_ids or unit.obligation_links:
                raise CoverageContractError(
                    CoverageValidationErrorCode.PREMISE_CORRECTION_REQUIREMENT_MISMATCH
                )
        elif not unit.requirement_ids:
            raise CoverageContractError(
                CoverageValidationErrorCode.MISSING_UNIT_REQUIREMENT_ID
            )
        if (
            context.obligation_scopes
            and unit.role is not AnswerUnitRole.PREMISE_CORRECTION
            and not unit.obligation_links
        ):
            raise CoverageContractError(
                CoverageValidationErrorCode.MISSING_UNIT_OBLIGATION_LINK
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
        locality_failure = _citation_locality_failure(
            unit.text,
            cited_numbers,
            unit_id=unit.unit_id,
            unit_ordinal=unit_ordinal,
        )
        if locality_failure is not None:
            raise CoverageContractError(
                CoverageValidationErrorCode.CITATION_LOCALITY_INVALID,
                citation_locality_failure=locality_failure,
            )
        if any(number > context.source_count for number in cited_numbers):
            raise CoverageContractError(CoverageValidationErrorCode.UNRESOLVABLE_CITATION)
        if _ordered_unique(cited_numbers) != unit.source_numbers:
            raise CoverageContractError(CoverageValidationErrorCode.CITATION_SOURCE_MISMATCH)

        link_keys = tuple(
            (link.obligation_id, link.dimension)
            for link in unit.obligation_links
        )
        if len(link_keys) != len(set(link_keys)):
            raise CoverageContractError(
                CoverageValidationErrorCode.DUPLICATE_UNIT_OBLIGATION_LINK
            )
        if any(
            obligation_id not in obligation_scopes_by_id
            or (obligation_id, dimension) not in obligation_dimension_order
            for obligation_id, dimension in link_keys
        ):
            raise CoverageContractError(
                CoverageValidationErrorCode.UNKNOWN_UNIT_OBLIGATION_LINK
            )
        canonical_link_order = tuple(
            sorted(
                link_keys,
                key=lambda value: (
                    obligation_order[value[0]],
                    obligation_dimension_order[value],
                ),
            )
        )
        if link_keys != canonical_link_order:
            raise CoverageContractError(
                CoverageValidationErrorCode.OUT_OF_ORDER_UNIT_OBLIGATION_LINK
            )
        if unit.obligation_links:
            linked_source_numbers = _ordered_unique(
                obligation_scopes_by_id[link.obligation_id].source_number
                for link in unit.obligation_links
            )
            if set(linked_source_numbers) != set(unit.source_numbers):
                raise CoverageContractError(
                    CoverageValidationErrorCode.OBLIGATION_SOURCE_MISMATCH
                )
            if any(
                not set(unit.requirement_ids)
                <= set(
                    obligation_scopes_by_id[
                        link.obligation_id
                    ].allowed_requirement_ids
                )
                for link in unit.obligation_links
            ):
                raise CoverageContractError(
                    CoverageValidationErrorCode.OBLIGATION_REQUIREMENT_MISMATCH
                )
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

    obligation_coverage_by_id = {
        record.obligation_id: record for record in answer.obligation_coverage
    }
    for record in answer.obligation_coverage:
        scope = obligation_scopes_by_id[record.obligation_id]
        _validate_exact_ids(
            actual=tuple(dimension.dimension.value for dimension in record.dimensions),
            expected=tuple(dimension.value for dimension in scope.dimension_ids),
            missing=CoverageValidationErrorCode.MISSING_OBLIGATION_DIMENSION,
            duplicate=CoverageValidationErrorCode.DUPLICATE_OBLIGATION_DIMENSION,
            unknown=CoverageValidationErrorCode.UNKNOWN_OBLIGATION_DIMENSION,
            out_of_order=CoverageValidationErrorCode.OUT_OF_ORDER_OBLIGATION_DIMENSION,
        )
        for dimension_record in record.dimensions:
            _validate_source_numbers(
                dimension_record.source_numbers,
                context.source_count,
            )
            _validate_status_shape(dimension_record)
            mapped_units = tuple(
                unit
                for unit in answer.answer_units
                if any(
                    link.obligation_id == record.obligation_id
                    and link.dimension is dimension_record.dimension
                    for link in unit.obligation_links
                )
            )
            mapped_unit_ids = tuple(unit.unit_id for unit in mapped_units)
            mapped_source_numbers = _ordered_unique(
                number for unit in mapped_units for number in unit.source_numbers
            )
            if (
                dimension_record.status is RequirementStatus.UNSUPPORTED
                and mapped_units
            ):
                raise CoverageContractError(
                    CoverageValidationErrorCode.UNSUPPORTED_OBLIGATION_HAS_UNIT
                )
            if dimension_record.unit_ids != mapped_unit_ids:
                raise CoverageContractError(
                    CoverageValidationErrorCode.OBLIGATION_UNIT_MAPPING_MISMATCH
                )
            if dimension_record.source_numbers != mapped_source_numbers:
                raise CoverageContractError(
                    CoverageValidationErrorCode.OBLIGATION_SOURCE_MAPPING_MISMATCH
                )
            if mapped_units and mapped_source_numbers != (scope.source_number,):
                raise CoverageContractError(
                    CoverageValidationErrorCode.OBLIGATION_SOURCE_MISMATCH
                )
            if any(
                unit.role not in _DIMENSION_COMPATIBLE_ROLES[
                    dimension_record.dimension
                ]
                for unit in mapped_units
            ):
                raise CoverageContractError(
                    CoverageValidationErrorCode.OBLIGATION_ROLE_MISMATCH
                )

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
        required_obligation_dimensions = {
            (scope.obligation_id, dimension)
            for scope in context.obligation_scopes
            if scope.required_for_requirement_status
            and record.requirement_id in scope.allowed_requirement_ids
            for dimension in scope.dimension_ids
        }
        supported_obligation_dimensions = {
            (scope.obligation_id, dimension_record.dimension)
            for scope in context.obligation_scopes
            if scope.required_for_requirement_status
            and record.requirement_id in scope.allowed_requirement_ids
            for dimension_record in obligation_coverage_by_id[
                scope.obligation_id
            ].dimensions
            if dimension_record.status is RequirementStatus.SUPPORTED
        }
        if (
            record.status is RequirementStatus.SUPPORTED
            and required_obligation_dimensions
            and not required_obligation_dimensions
            <= supported_obligation_dimensions
        ):
            raise CoverageContractError(
                CoverageValidationErrorCode.OBLIGATION_REQUIREMENT_STATUS_MISMATCH
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
        citation_locality_failure=None,
        repair_applied=bool(normalized_repair_codes),
        repair_codes=normalized_repair_codes,
        requirement_ids=validated.context.requirement_ids,
        premise_ids=validated.context.premise_ids,
        premise_source_scopes=validated.context.premise_source_scopes,
        obligation_scopes=validated.context.obligation_scopes,
        requirement_count=len(validated.context.requirement_ids),
        premise_count=len(validated.context.premise_ids),
        obligation_count=len(validated.context.obligation_scopes),
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
        obligation_coverage=answer.obligation_coverage,
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
                obligation_links=unit.obligation_links,
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
    obligation_scopes: Sequence[EvidenceObligationScope | Mapping[str, Any]] = (),
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
            obligation_scopes,
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
            obligation_scopes=context.obligation_scopes,
            source_count=context.source_count,
        )
    except CoverageContractError as error:
        return _contract_failure_result(
            context=context,
            error_code=error.code,
            repair_codes=error.repair_codes or repair_codes,
            citation_locality_failure=error.citation_locality_failure,
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


def process_interpretive_evidence_coverage(
    payload: InterpretiveEvidenceCoverageAnswer | Mapping[str, Any] | None,
    *,
    required_moves: Sequence[InterpretiveMove],
    question_anchors: Sequence[str] = (),
    requirement_ids: Sequence[str],
    premise_ids: Sequence[str] = (),
    premise_source_scopes: Sequence[PremiseSourceScope | Mapping[str, Any]] = (),
    obligation_scopes: Sequence[EvidenceObligationScope | Mapping[str, Any]] = (),
    source_count: int,
    requirement_labels: Mapping[str, str] | None = None,
    refused: bool = False,
) -> EvidenceCoverageResult:
    """Frame validated factual coverage with explicitly subjective prose.

    The ordinary evidence-coverage validator remains the authority for requested
    facts, premise handling, completeness, and citations. The uncited preface and
    coda are validated separately and never satisfy a requirement or obligation.
    """

    try:
        context = _validation_context(
            requirement_ids,
            premise_ids,
            premise_source_scopes,
            obligation_scopes,
            source_count,
        )
        expected_moves = _validate_required_interpretive_moves(required_moves)
        expected_question_anchors = _validate_interpretive_question_anchors(
            question_anchors
        )
    except CoverageContractError as error:
        return _contract_failure_result(
            context=None,
            error_code=error.code,
        )

    if context.source_count == 0 or refused or payload is None:
        return process_evidence_coverage(
            None,
            requirement_ids=context.requirement_ids,
            premise_ids=context.premise_ids,
            premise_source_scopes=context.premise_source_scopes,
            obligation_scopes=context.obligation_scopes,
            source_count=context.source_count,
            requirement_labels=requirement_labels,
            refused=refused,
        )

    try:
        answer = _parse_interpretive_payload(payload)
    except CoverageContractError as error:
        return _contract_failure_result(
            context=context,
            error_code=error.code,
        )

    factual_answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=answer.premise_decisions,
        coverage=answer.coverage,
        obligation_coverage=answer.obligation_coverage,
        answer_units=answer.answer_units,
    )
    factual_result = process_evidence_coverage(
        factual_answer,
        requirement_ids=context.requirement_ids,
        premise_ids=context.premise_ids,
        premise_source_scopes=context.premise_source_scopes,
        obligation_scopes=context.obligation_scopes,
        source_count=context.source_count,
        requirement_labels=requirement_labels,
    )
    if factual_result.status is not CoverageOutcomeStatus.ANSWERED:
        return factual_result

    try:
        _validate_interpretive_frame(
            answer,
            required_moves=expected_moves,
            question_anchors=expected_question_anchors,
        )
    except CoverageContractError as error:
        return _contract_failure_result(
            context=context,
            error_code=error.code,
            citation_locality_failure=error.citation_locality_failure,
            repair_codes=factual_result.diagnostics.repair_codes,
        )

    return factual_result.model_copy(
        update={
            "answer": (
                f"{answer.interpretive_preface}\n\n"
                f"{factual_result.answer}\n\n"
                f"{answer.interpretive_coda}"
            ),
        }
    )


def _validation_context(
    requirement_ids: Sequence[str],
    premise_ids: Sequence[str],
    premise_source_scopes: Sequence[PremiseSourceScope | Mapping[str, Any]],
    obligation_scopes: Sequence[EvidenceObligationScope | Mapping[str, Any]],
    source_count: int,
) -> CoverageValidationContext:
    if (
        isinstance(requirement_ids, (str, bytes))
        or isinstance(premise_ids, (str, bytes))
        or isinstance(premise_source_scopes, (str, bytes, Mapping))
        or isinstance(obligation_scopes, (str, bytes, Mapping))
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
        parsed_obligation_scopes = tuple(
            (
                value
                if isinstance(value, EvidenceObligationScope)
                else EvidenceObligationScope.model_validate(value)
            )
            for value in obligation_scopes
        )
        context = CoverageValidationContext(
            requirement_ids=tuple(requirement_ids),
            premise_ids=tuple(premise_ids),
            premise_source_scopes=scopes,
            obligation_scopes=parsed_obligation_scopes,
            source_count=source_count,
        )
    except (TypeError, ValidationError):
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_CONTEXT) from None
    obligation_dimension_count = sum(
        len(scope.dimension_ids) for scope in context.obligation_scopes
    )
    if obligation_dimension_count + len(context.premise_ids) > MAX_ANSWER_UNITS:
        raise CoverageContractError(
            CoverageValidationErrorCode.OBLIGATION_DIMENSION_CAPACITY_EXCEEDED
        )
    scope_ids = tuple(scope.premise_id for scope in context.premise_source_scopes)
    obligation_ids = tuple(
        scope.obligation_id for scope in context.obligation_scopes
    )
    if (
        _has_duplicates(context.requirement_ids)
        or _has_duplicates(context.premise_ids)
        or scope_ids != context.premise_ids
        or _has_duplicates(obligation_ids)
        or any(
            not set(scope.allowed_requirement_ids) <= set(context.requirement_ids)
            or scope.source_number > context.source_count
            for scope in context.obligation_scopes
        )
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


def _parse_interpretive_payload(
    payload: InterpretiveEvidenceCoverageAnswer | Mapping[str, Any],
) -> InterpretiveEvidenceCoverageAnswer:
    if isinstance(payload, InterpretiveEvidenceCoverageAnswer):
        return payload
    if not isinstance(payload, Mapping):
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_PAYLOAD)
    try:
        return InterpretiveEvidenceCoverageAnswer.model_validate(payload)
    except ValidationError:
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_PAYLOAD) from None


def _validate_required_interpretive_moves(
    required_moves: Sequence[InterpretiveMove],
) -> tuple[InterpretiveMove, ...]:
    if (
        isinstance(required_moves, (str, bytes, Mapping))
        or not required_moves
        or len(required_moves) > 2
    ):
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_CONTEXT)
    try:
        normalized = tuple(InterpretiveMove(move) for move in required_moves)
    except (TypeError, ValueError):
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_CONTEXT) from None
    if _has_duplicates(normalized):
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_CONTEXT)
    return normalized


def _validate_interpretive_question_anchors(
    question_anchors: Sequence[str],
) -> tuple[str, ...]:
    if isinstance(question_anchors, (str, bytes, Mapping)):
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_CONTEXT)
    try:
        normalized = tuple(anchor.strip() for anchor in question_anchors)
    except (AttributeError, TypeError):
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_CONTEXT) from None
    if (
        len(normalized) > MAX_REQUIREMENTS
        or any(
            not anchor or len(anchor) > MAX_REQUIREMENT_LABEL_CHARACTERS
            for anchor in normalized
        )
        or _has_duplicates(
            tuple(_normalize_interpretive_text(anchor) for anchor in normalized)
        )
    ):
        raise CoverageContractError(CoverageValidationErrorCode.INVALID_CONTEXT)
    return normalized


def _validate_interpretive_frame(
    answer: InterpretiveEvidenceCoverageAnswer,
    *,
    required_moves: Sequence[InterpretiveMove],
    question_anchors: Sequence[str],
) -> None:
    if not answer.interpretive_preface or not answer.interpretive_coda:
        raise CoverageContractError(
            CoverageValidationErrorCode.MISSING_INTERPRETIVE_PARAGRAPH
        )
    if answer.interpretive_moves != tuple(required_moves):
        raise CoverageContractError(
            CoverageValidationErrorCode.INTERPRETIVE_MOVE_MISMATCH
        )
    if any(
        "[" in text or "]" in text
        for text in (
            answer.interpretive_preface,
            answer.interpretive_coda,
        )
    ):
        raise CoverageContractError(
            CoverageValidationErrorCode.INTERPRETIVE_CITATION_FORBIDDEN
        )
    if (
        _sentence_count(answer.interpretive_preface) not in {2, 3}
        or _sentence_count(answer.interpretive_coda) != 1
    ):
        raise CoverageContractError(
            CoverageValidationErrorCode.INTERPRETIVE_SENTENCE_COUNT_INVALID
        )
    if any(
        _FIRST_PERSON_PATTERN.search(text)
        for text in (
            answer.interpretive_preface,
            answer.interpretive_coda,
        )
    ):
        raise CoverageContractError(
            CoverageValidationErrorCode.INTERPRETIVE_FIRST_PERSON_FORBIDDEN
        )
    if question_anchors and any(
        not _contains_every_interpretive_anchor(text, question_anchors)
        for text in (
            answer.interpretive_preface,
            answer.interpretive_coda,
        )
    ):
        raise CoverageContractError(
            CoverageValidationErrorCode.INTERPRETIVE_SUBJECT_MISSING
        )


def _normalize_interpretive_text(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"\w+", folded, flags=re.UNICODE))


def _contains_every_interpretive_anchor(
    text: str,
    question_anchors: Sequence[str],
) -> bool:
    normalized_text = f" {_normalize_interpretive_text(text)} "
    return all(
        f" {_normalize_interpretive_text(anchor)} " in normalized_text
        for anchor in question_anchors
    )


def _sentence_count(text: str) -> int:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if not sentences or any(
        not sentence or sentence[-1] not in ".!?" for sentence in sentences
    ):
        return 0
    return len(sentences)


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
    obligation_order = {
        scope.obligation_id: index
        for index, scope in enumerate(context.obligation_scopes)
    }
    dimension_order = {
        (scope.obligation_id, dimension): index
        for scope in context.obligation_scopes
        for index, dimension in enumerate(scope.dimension_ids)
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

        text, citation_repaired = _normalize_pre_citation_terminal(unit.text)
        if citation_repaired:
            repair_codes.append(CoverageValidationErrorCode.CITATION_LOCALITY_INVALID)

        source_numbers = unit.source_numbers
        try:
            cited_numbers = parse_citation_numbers(text)
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

        obligation_links = unit.obligation_links
        link_keys = tuple(
            (link.obligation_id, link.dimension)
            for link in obligation_links
        )
        if (
            len(link_keys) == len(set(link_keys))
            and all(key[0] in obligation_order and key in dimension_order for key in link_keys)
        ):
            canonical_links = tuple(
                sorted(
                    obligation_links,
                    key=lambda link: (
                        obligation_order[link.obligation_id],
                        dimension_order[(link.obligation_id, link.dimension)],
                    ),
                )
            )
            if canonical_links != obligation_links:
                repair_codes.append(
                    CoverageValidationErrorCode.OUT_OF_ORDER_UNIT_OBLIGATION_LINK
                )
                obligation_links = canonical_links

        normalized_units.append(
            unit.model_copy(
                update={
                    "requirement_ids": requirement_ids,
                    "text": text,
                    "source_numbers": source_numbers,
                    "obligation_links": obligation_links,
                }
            )
        )

    answer_units = tuple(normalized_units)
    known_unit_ids = {unit.unit_id for unit in answer_units}

    obligation_coverage = _reorder_exact_records(
        answer.obligation_coverage,
        expected_ids=tuple(
            scope.obligation_id for scope in context.obligation_scopes
        ),
        id_attribute="obligation_id",
    )
    if obligation_coverage != answer.obligation_coverage:
        repair_codes.append(
            CoverageValidationErrorCode.OUT_OF_ORDER_OBLIGATION_ID
        )
    scopes_by_id = {
        scope.obligation_id: scope for scope in context.obligation_scopes
    }
    normalized_obligation_coverage: list[EvidenceObligationCoverage] = []
    for record in obligation_coverage:
        scope = scopes_by_id.get(record.obligation_id)
        if scope is None:
            normalized_obligation_coverage.append(record)
            continue
        dimensions = _reorder_exact_records(
            record.dimensions,
            expected_ids=scope.dimension_ids,
            id_attribute="dimension",
        )
        if dimensions != record.dimensions:
            repair_codes.append(
                CoverageValidationErrorCode.OUT_OF_ORDER_OBLIGATION_DIMENSION
            )
        normalized_dimensions: list[EvidenceDimensionCoverage] = []
        for dimension_record in dimensions:
            expected_gap = _STATUS_GAP_REASON[dimension_record.status]
            if dimension_record.gap_reason is not expected_gap:
                repair_codes.append(CoverageValidationErrorCode.STATUS_GAP_MISMATCH)
                dimension_record = dimension_record.model_copy(
                    update={"gap_reason": expected_gap}
                )
            if dimension_record.status is RequirementStatus.UNSUPPORTED:
                normalized_dimensions.append(dimension_record)
                continue
            mappings_are_safe_to_derive = (
                not _has_duplicates(dimension_record.unit_ids)
                and all(
                    unit_id in known_unit_ids
                    for unit_id in dimension_record.unit_ids
                )
                and not _has_duplicates(dimension_record.source_numbers)
                and all(
                    1 <= source_number <= context.source_count
                    for source_number in dimension_record.source_numbers
                )
            )
            if not mappings_are_safe_to_derive:
                normalized_dimensions.append(dimension_record)
                continue
            mapped_units = tuple(
                unit
                for unit in answer_units
                if any(
                    link.obligation_id == record.obligation_id
                    and link.dimension is dimension_record.dimension
                    for link in unit.obligation_links
                )
            )
            mapped_unit_ids = tuple(unit.unit_id for unit in mapped_units)
            mapped_source_numbers = _ordered_unique(
                source_number
                for unit in mapped_units
                for source_number in unit.source_numbers
            )
            if dimension_record.unit_ids != mapped_unit_ids:
                repair_codes.append(
                    CoverageValidationErrorCode.OBLIGATION_UNIT_MAPPING_MISMATCH
                )
            if dimension_record.source_numbers != mapped_source_numbers:
                repair_codes.append(
                    CoverageValidationErrorCode.OBLIGATION_SOURCE_MAPPING_MISMATCH
                )
            normalized_dimensions.append(
                dimension_record.model_copy(
                    update={
                        "unit_ids": mapped_unit_ids,
                        "source_numbers": mapped_source_numbers,
                    }
                )
            )
        normalized_obligation_coverage.append(
            record.model_copy(
                update={"dimensions": tuple(normalized_dimensions)}
            )
        )
    obligation_coverage_by_id = {
        record.obligation_id: record
        for record in normalized_obligation_coverage
    }

    coverage = _reorder_exact_records(
        answer.coverage,
        expected_ids=context.requirement_ids,
        id_attribute="requirement_id",
    )
    if coverage != answer.coverage:
        repair_codes.append(CoverageValidationErrorCode.OUT_OF_ORDER_REQUIREMENT_ID)
    normalized_coverage: list[RequirementCoverage] = []
    for record in coverage:
        required_obligation_dimensions = {
            (scope.obligation_id, dimension)
            for scope in context.obligation_scopes
            if scope.required_for_requirement_status
            and record.requirement_id in scope.allowed_requirement_ids
            for dimension in scope.dimension_ids
        }
        supported_obligation_dimensions = {
            (scope.obligation_id, dimension_record.dimension)
            for scope in context.obligation_scopes
            if scope.required_for_requirement_status
            and record.requirement_id in scope.allowed_requirement_ids
            and scope.obligation_id in obligation_coverage_by_id
            for dimension_record in obligation_coverage_by_id[
                scope.obligation_id
            ].dimensions
            if dimension_record.status is RequirementStatus.SUPPORTED
        }
        if (
            record.status is RequirementStatus.SUPPORTED
            and required_obligation_dimensions
            and not required_obligation_dimensions
            <= supported_obligation_dimensions
        ):
            repair_codes.append(
                CoverageValidationErrorCode.OBLIGATION_REQUIREMENT_STATUS_MISMATCH
            )
            record = record.model_copy(
                update={
                    "status": RequirementStatus.PARTIAL,
                    "gap_reason": GapReason.PARTIAL_SUPPORT,
                }
            )
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
            "obligation_coverage": tuple(normalized_obligation_coverage),
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


def _normalize_pre_citation_terminal(text: str) -> tuple[str, bool]:
    """Remove only a duplicated sentence terminator immediately before a citation.

    The v11 failures used ``claim.[Source N].`` for every otherwise atomic unit.
    This repair changes no words, sources, claim boundaries, or citation set. Any
    other locality shape remains untouched for strict validation.
    """

    citations = tuple(CITATION_PATTERN.finditer(text))
    if len(citations) != 1:
        return text, False
    citation = citations[0]
    if _TERMINAL_CITATION_PATTERN.fullmatch(text[citation.start() :]) is None:
        return text, False
    claim = text[: citation.start()].rstrip()
    if (
        not claim
        or claim[-1] not in ".!?"
        or "\n" in claim
        or "\r" in claim
        or ";" in claim
        or sum(claim.count(mark) for mark in ".!?") != 1
    ):
        return text, False
    normalized_claim = claim[:-1].rstrip()
    if not normalized_claim:
        return text, False
    return f"{normalized_claim} {text[citation.start():]}", True


def _citation_locality_failure(
    text: str,
    _cited_numbers: Sequence[int],
    *,
    unit_id: str,
    unit_ordinal: int,
) -> CitationLocalityFailure | None:
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
        return CitationLocalityFailure(
            unit_id=unit_id,
            unit_ordinal=unit_ordinal,
            code=CitationLocalityFailureCode.MULTIPLE_CITATION_GROUPS,
        )
    citation = citations[0]
    suffix = text[citation.start() :]
    if not suffix or suffix[-1] not in ".!?":
        code = CitationLocalityFailureCode.MISSING_TERMINAL_PUNCTUATION
        return CitationLocalityFailure(
            unit_id=unit_id,
            unit_ordinal=unit_ordinal,
            code=code,
        )
    if _TERMINAL_CITATION_PATTERN.fullmatch(suffix) is None:
        return CitationLocalityFailure(
            unit_id=unit_id,
            unit_ordinal=unit_ordinal,
            code=CitationLocalityFailureCode.TRAILING_CONTENT_AFTER_CITATION,
        )

    claim = text[: citation.start()].rstrip()
    if not claim:
        code = CitationLocalityFailureCode.EMPTY_CLAIM
    elif "\n" in claim or "\r" in claim:
        code = CitationLocalityFailureCode.MULTILINE_CLAIM
    elif ";" in claim:
        code = CitationLocalityFailureCode.SEMICOLON_IN_CLAIM
    else:
        terminators = tuple(
            index for index, character in enumerate(claim) if character in ".!?"
        )
        if len(terminators) == 1 and terminators[0] == len(claim) - 1:
            code = CitationLocalityFailureCode.PRE_CITATION_TERMINAL_PUNCTUATION
        elif terminators:
            code = CitationLocalityFailureCode.INTERNAL_SENTENCE_TERMINATOR
        else:
            return None
    return CitationLocalityFailure(
        unit_id=unit_id,
        unit_ordinal=unit_ordinal,
        code=code,
    )


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
    citation_locality_failure: CitationLocalityFailure | None = None,
    repair_codes: Sequence[CoverageValidationErrorCode] = (),
) -> CoverageDiagnosticSummary:
    normalized_repair_codes = tuple(dict.fromkeys(repair_codes))
    return CoverageDiagnosticSummary(
        schema=EVIDENCE_COVERAGE_DIAGNOSTIC_SCHEMA,
        renderer_version=EVIDENCE_COVERAGE_RENDERER_VERSION,
        validation_result=validation_result,
        error_code=error_code,
        citation_locality_failure=citation_locality_failure,
        repair_applied=bool(normalized_repair_codes),
        repair_codes=normalized_repair_codes,
        requirement_ids=context.requirement_ids,
        premise_ids=context.premise_ids,
        premise_source_scopes=context.premise_source_scopes,
        obligation_scopes=context.obligation_scopes,
        requirement_count=len(context.requirement_ids),
        premise_count=len(context.premise_ids),
        obligation_count=len(context.obligation_scopes),
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
        obligation_coverage=(),
        premise_decisions=(),
        answer_units=(),
    )


def _contract_failure_result(
    *,
    context: CoverageValidationContext | None,
    error_code: CoverageValidationErrorCode,
    citation_locality_failure: CitationLocalityFailure | None = None,
    repair_codes: Sequence[CoverageValidationErrorCode] = (),
) -> EvidenceCoverageResult:
    normalized_repair_codes = tuple(dict.fromkeys(repair_codes))
    if context is None:
        diagnostics = CoverageDiagnosticSummary(
            schema=EVIDENCE_COVERAGE_DIAGNOSTIC_SCHEMA,
            renderer_version=EVIDENCE_COVERAGE_RENDERER_VERSION,
            validation_result=DiagnosticValidationResult.INVALID,
            error_code=error_code,
            citation_locality_failure=citation_locality_failure,
            repair_applied=bool(normalized_repair_codes),
            repair_codes=normalized_repair_codes,
            requirement_ids=(),
            premise_ids=(),
            premise_source_scopes=(),
            obligation_scopes=(),
            requirement_count=0,
            premise_count=0,
            obligation_count=0,
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
            obligation_coverage=(),
            premise_decisions=(),
            answer_units=(),
        )
    else:
        diagnostics = _empty_diagnostic_summary(
            context,
            validation_result=DiagnosticValidationResult.INVALID,
            error_code=error_code,
            citation_locality_failure=citation_locality_failure,
            repair_codes=normalized_repair_codes,
        )
    return EvidenceCoverageResult(
        status=CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED,
        answer=GENERATION_CONTRACT_FAILED_MESSAGE,
        error_code=CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED.value,
        diagnostics=diagnostics,
    )
