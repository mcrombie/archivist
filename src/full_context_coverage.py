"""Contracts, validation, remap, and rendering for full-context answers.

Like :mod:`answer_coverage`, this module has no model or retrieval dependency.
It differs in one deliberate way: because full context supplies the complete
eligible corpus, the model cites **stable chunk IDs** rather than positional
source numbers, and only local code decides which of those IDs are real and
what compact ``[Source N]`` labels a reader eventually sees.

That remap is the reason this module exists. By the time a full-context result
leaves here it has exactly the shape a retrieval result has - prose with inline
``[Source N]`` citations plus a short ordered list of *cited* chunks - so every
downstream disclosure and presentation component keeps working unchanged and
never sees the whole corpus.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import groupby
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from answer_coverage import (
    AnswerUnitRole,
    ContentOutcome,
    CoverageOutcomeStatus,
    DiagnosticValidationResult,
    PremiseStatus,
)

__all__ = [
    "FULL_CONTEXT_COVERAGE_PROMPT_VERSION",
    "FULL_CONTEXT_COVERAGE_RENDERER_VERSION",
    "FULL_CONTEXT_COVERAGE_SCHEMA",
    "FULL_CONTEXT_RESPONSE_SCHEMA",
    "FULL_CONTEXT_RUN_DIAGNOSTICS_SCHEMA",
    "FULL_CONTEXT_GENERATION_FAILED_MESSAGE",
    "FULL_CONTEXT_NO_EVIDENCE_MESSAGE",
    "MAX_CITED_CHUNKS_PER_CLAIM",
    "MAX_FULL_CONTEXT_CLAIMS",
    "AbsenceFinding",
    "AbsenceStatus",
    "FullContextClaim",
    "FullContextCoverageAnswer",
    "FullContextCoverageResult",
    "FullContextValidationErrorCode",
    "PremiseFinding",
    "TrustedTargetAudit",
    "process_full_context_coverage",
    "render_full_context_answer",
]


FULL_CONTEXT_RESPONSE_SCHEMA = "archivist.full_context_coverage/2"
# Compatibility name for callers that already import the generation contract.
# Run diagnostics deliberately use a different identifier below.
FULL_CONTEXT_COVERAGE_SCHEMA = FULL_CONTEXT_RESPONSE_SCHEMA
FULL_CONTEXT_RUN_DIAGNOSTICS_SCHEMA = "archivist.full_context_run_diagnostics/1"
FULL_CONTEXT_COVERAGE_RENDERER_VERSION = "full-context-coverage-renderer/2"
FULL_CONTEXT_COVERAGE_PROMPT_VERSION = "full-context-coverage-v2"

MAX_FULL_CONTEXT_CLAIMS = 40
MAX_CITED_CHUNKS_PER_CLAIM = 6
MAX_ABSENCE_FINDINGS = 3
MAX_CLAIM_TEXT_CHARACTERS = 2_000
MAX_TOTAL_CLAIM_TEXT_CHARACTERS = 24_000

FULL_CONTEXT_NO_EVIDENCE_MESSAGE = (
    "The manuscript does not provide enough evidence to answer this question."
)
FULL_CONTEXT_GENERATION_FAILED_MESSAGE = (
    "I could not produce a validated source-grounded answer from the manuscript."
)

# A claim is one sentence with exactly one terminal mark and no bracket of its
# own. The renderer, not the model, writes the citation, which is what makes
# citation locality true by construction rather than something to police.
CLAIM_TEXT_PATTERN = r"^[^.!?;\r\n\[\]]*[^\s.!?;\r\n\[\]][^.!?;\r\n\[\]]*[.!?]$"
_CLAIM_TEXT_RE = re.compile(CLAIM_TEXT_PATTERN)
# Mirrors retrieval_trace_contract's chunk-ID shape. Duplicated as one literal
# rather than imported, because that module owns a diagnostics contract and this
# is a generation contract; coupling them would tie two unrelated versions.
CHUNK_ID_PATTERN = r"[^\r\n\x00-\x1f]{1,500}_[0-9]{3,}"

Identifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
]
ChunkIdStr = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=512,
        pattern=f"^{CHUNK_ID_PATTERN}$",
    ),
]
ClaimText = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=MAX_CLAIM_TEXT_CHARACTERS,
        pattern=CLAIM_TEXT_PATTERN,
    ),
]


class AbsenceStatus(StrEnum):
    NOT_ADDRESSED_IN_CORPUS = "not_addressed_in_corpus"
    ADDRESSED_INDIRECTLY = "addressed_indirectly"


class FullContextValidationErrorCode(StrEnum):
    INVALID_PAYLOAD = "invalid_payload"
    GENERATION_REFUSED = "generation_refused"
    UNRESOLVABLE_CHUNK_ID = "unresolvable_chunk_id"
    DUPLICATE_CLAIM_ID = "duplicate_claim_id"
    DUPLICATE_CITED_CHUNK_ID = "duplicate_cited_chunk_id"
    MALFORMED_CLAIM_TEXT = "malformed_claim_text"
    PREMISE_CORRECTION_MISSING = "premise_correction_missing"
    PREMISE_CORRECTION_NOT_FIRST = "premise_correction_not_first"
    PREMISE_CORRECTION_UNEXPECTED = "premise_correction_unexpected"
    UNKNOWN_CORRECTION_CLAIM_ID = "unknown_correction_claim_id"
    TEXT_LIMIT_EXCEEDED = "text_limit_exceeded"
    CONTEXT_BUDGET_EXCEEDED = "context_budget_exceeded"
    UNKNOWN_ABSENCE_TARGET_ID = "unknown_absence_target_id"
    DUPLICATE_ABSENCE_TARGET_ID = "duplicate_absence_target_id"
    ABSENCE_TARGET_MISMATCH = "absence_target_mismatch"
    TRUSTED_TARGET_EVIDENCE_MISSING = "trusted_target_evidence_missing"
    TRUSTED_TARGET_ABSENCE_MISSING = "trusted_target_absence_missing"
    TRUSTED_TARGET_CLAIMS_UNSUPPORTED = "trusted_target_claims_unsupported"
    CONTENT_OUTCOME_INCONSISTENT = "content_outcome_inconsistent"
    INSUFFICIENT_EVIDENCE_UNCERTIFIED = "insufficient_evidence_uncertified"
    PREMISE_CORRECTION_COUNT_INVALID = "premise_correction_count_invalid"
    PREMISE_CORRECTION_ID_MISMATCH = "premise_correction_id_mismatch"


class _ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class FullContextClaim(_ContractModel):
    claim_id: Identifier
    role: AnswerUnitRole
    text: ClaimText = Field(
        description=(
            "Exactly one complete sentence asserting one independently checkable "
            "factual claim, ending in its only terminal punctuation. Never write a "
            "citation, bracket, or source label; citations are attached "
            "automatically from cited_chunk_ids."
        ),
    )
    cited_chunk_ids: tuple[ChunkIdStr, ...] = Field(
        min_length=1,
        max_length=MAX_CITED_CHUNKS_PER_CLAIM,
        description=(
            "The exact Chunk ID values, copied verbatim from the supplied "
            "manuscript, that independently support this one claim. Every listed "
            "chunk must support the whole claim on its own."
        ),
    )
    paragraph_group: int = Field(
        ge=1,
        le=MAX_FULL_CONTEXT_CLAIMS,
        description="Claims sharing this number are rendered as one paragraph.",
    )


class PremiseFinding(_ContractModel):
    status: PremiseStatus
    correction_claim_id: Identifier | None = Field(
        description=(
            "The claim_id of the correcting claim when the question's premise is "
            "contradicted by the manuscript, otherwise null."
        ),
    )


class AbsenceFinding(_ContractModel):
    target_id: Identifier = Field(
        description=(
            "The exact application-issued Target ID for a requested subject whose "
            "direct absence the complete-corpus scan can certify. Never paraphrase "
            "or invent a target."
        ),
    )
    status: AbsenceStatus


@dataclass(frozen=True, slots=True)
class TrustedTargetAudit:
    """Application-owned evidence facts for one trusted user-surface target.

    The model may refer to ``target_id`` but cannot create or alter this record.
    ``direct_chunk_ids`` includes both strong and weak direct anchor matches from
    the exhaustive local scan.
    """

    target_id: str
    query_surface_span: str
    direct_chunk_ids: tuple[str, ...]
    absence_checkable: bool
    certified_direct_absence: bool


class FullContextCoverageAnswer(_ContractModel):
    schema_version: Literal["archivist.full_context_coverage/2"] = Field(alias="schema")
    premise_finding: PremiseFinding | None
    claims: tuple[FullContextClaim, ...] = Field(max_length=MAX_FULL_CONTEXT_CLAIMS)
    absence_findings: tuple[AbsenceFinding, ...] = Field(max_length=MAX_ABSENCE_FINDINGS)
    self_reported_content_outcome: ContentOutcome = Field(
        description=(
            "Your diagnostic judgment of whether the manuscript let you answer "
            "the whole question. Application validation owns the final outcome "
            "and currently caps every nonempty answer at valid_partial."
        ),
    )

    @property
    def schema(self) -> str:
        return self.schema_version

    @field_validator("claims")
    @classmethod
    def reject_duplicate_claim_ids(
        cls,
        value: tuple[FullContextClaim, ...],
    ) -> tuple[FullContextClaim, ...]:
        identifiers = [claim.claim_id for claim in value]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("claim_id values must be unique")
        return value


@dataclass(frozen=True, slots=True)
class FullContextCoverageResult:
    """A validated, rendered full-context answer in the shared result shape."""

    status: CoverageOutcomeStatus
    answer: str
    final_chunks: list[dict[str, Any]]
    content_outcome: ContentOutcome | None
    error_code: FullContextValidationErrorCode | None
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _diagnostics(
    *,
    validation_result: DiagnosticValidationResult,
    error_code: FullContextValidationErrorCode | None,
    content_outcome: ContentOutcome | None,
    self_reported_content_outcome: ContentOutcome | None = None,
    supplied_chunk_count: int = 0,
    cited_chunk_count: int = 0,
    claim_count: int = 0,
    citation_count: int = 0,
    absence_finding_count: int = 0,
    contradicted_absence_count: int = 0,
    trusted_target_count: int = 0,
    direct_target_count: int = 0,
    certified_absent_target_count: int = 0,
    premise_status: PremiseStatus | None = None,
) -> dict[str, Any]:
    """Build the text-free record of one full-context validation.

    Deliberately holds counts, enum values, and codes only: no question, answer,
    claim text, chunk ID, or manuscript prose ever enters durable diagnostics.
    """

    return {
        "schema": FULL_CONTEXT_RUN_DIAGNOSTICS_SCHEMA,
        "response_schema": FULL_CONTEXT_RESPONSE_SCHEMA,
        "renderer_version": FULL_CONTEXT_COVERAGE_RENDERER_VERSION,
        "validation_result": validation_result.value,
        "error_code": error_code.value if error_code is not None else None,
        "content_outcome": content_outcome.value if content_outcome is not None else None,
        "self_reported_content_outcome": (
            self_reported_content_outcome.value
            if self_reported_content_outcome is not None
            else None
        ),
        "supplied_chunk_count": supplied_chunk_count,
        "cited_chunk_count": cited_chunk_count,
        "claim_count": claim_count,
        "citation_count": citation_count,
        "absence_finding_count": absence_finding_count,
        "contradicted_absence_count": contradicted_absence_count,
        "trusted_target_count": trusted_target_count,
        "direct_target_count": direct_target_count,
        "certified_absent_target_count": certified_absent_target_count,
        "premise_status": premise_status.value if premise_status is not None else None,
    }


def _failure(
    code: FullContextValidationErrorCode,
    *,
    supplied_chunk_count: int,
    message: str = FULL_CONTEXT_GENERATION_FAILED_MESSAGE,
) -> FullContextCoverageResult:
    return FullContextCoverageResult(
        status=CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED,
        answer=message,
        final_chunks=[],
        content_outcome=None,
        error_code=code,
        diagnostics=_diagnostics(
            validation_result=DiagnosticValidationResult.INVALID,
            error_code=code,
            content_outcome=None,
            supplied_chunk_count=supplied_chunk_count,
        ),
    )


def _citation_token(source_numbers: Sequence[int]) -> str:
    return "[" + ", ".join(f"Source {number}" for number in source_numbers) + "]"


def render_full_context_answer(
    claims: Sequence[FullContextClaim],
    source_numbers_by_claim: Mapping[str, tuple[int, ...]],
    absence_statements: Sequence[str] = (),
) -> str:
    """Render validated claims as prose with mechanically attached citations.

    The model never writes a bracket, so a malformed, duplicated, or misplaced
    citation group is not reachable from any model output.
    """

    paragraphs: list[str] = []
    for _, grouped in groupby(claims, key=lambda claim: claim.paragraph_group):
        sentences: list[str] = []
        for claim in grouped:
            body = claim.text[:-1].rstrip()
            terminator = claim.text[-1]
            citation = _citation_token(source_numbers_by_claim[claim.claim_id])
            sentences.append(f"{body} {citation}{terminator}")
        paragraphs.append(" ".join(sentences))
    paragraphs.extend(statement.strip() for statement in absence_statements)
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def _application_absence_statement(
    target: TrustedTargetAudit,
    finding: AbsenceFinding,
) -> str:
    """Render an uncited evidence boundary without accepting model-authored prose."""

    surface = " ".join(target.query_surface_span.split()).strip()
    # The status is a model diagnostic, not evidence. Even when the model chose
    # ``addressed_indirectly``, the application can certify only that this exact
    # trusted target has no direct hit. Any positive analogue belongs in a cited
    # claim, not in an uncited boundary sentence.
    return f"The manuscript does not directly address {surface}."


def process_full_context_coverage(
    payload: FullContextCoverageAnswer | None,
    *,
    eligible_chunks: Sequence[Mapping[str, object]],
    trusted_target_audits: Sequence[TrustedTargetAudit] = (),
    refused: bool = False,
) -> FullContextCoverageResult:
    """Validate one structured full-context response and reduce it to cited sources.

    Trusted targets and their corpus-presence facts are application-owned. The
    model can bind an absence to one of their IDs, but cannot supply the target,
    the scan result, or reader-facing absence prose.
    """

    supplied = len(eligible_chunks)
    if refused:
        return _failure(
            FullContextValidationErrorCode.GENERATION_REFUSED,
            supplied_chunk_count=supplied,
        )
    if payload is None:
        return _failure(
            FullContextValidationErrorCode.INVALID_PAYLOAD,
            supplied_chunk_count=supplied,
        )

    chunks_by_id: dict[str, Mapping[str, object]] = {}
    for chunk in eligible_chunks:
        chunk_id = chunk.get("chunk_id")
        if isinstance(chunk_id, str) and chunk_id:
            chunks_by_id.setdefault(chunk_id, chunk)

    target_by_id: dict[str, TrustedTargetAudit] = {}
    for target in trusted_target_audits:
        if target.target_id in target_by_id:
            return _failure(
                FullContextValidationErrorCode.INVALID_PAYLOAD,
                supplied_chunk_count=supplied,
            )
        target_by_id[target.target_id] = target

    absence_by_target_id: dict[str, AbsenceFinding] = {}
    for finding in payload.absence_findings:
        if finding.target_id in absence_by_target_id:
            return _failure(
                FullContextValidationErrorCode.DUPLICATE_ABSENCE_TARGET_ID,
                supplied_chunk_count=supplied,
            )
        target = target_by_id.get(finding.target_id)
        if target is None:
            return _failure(
                FullContextValidationErrorCode.UNKNOWN_ABSENCE_TARGET_ID,
                supplied_chunk_count=supplied,
            )
        # A reported absence must agree with the exhaustive local scan. Strong
        # and weak matches are both direct evidence; neither may be erased by a
        # model-authored absence assertion.
        if target.direct_chunk_ids or not target.certified_direct_absence:
            return _failure(
                FullContextValidationErrorCode.ABSENCE_TARGET_MISMATCH,
                supplied_chunk_count=supplied,
            )
        absence_by_target_id[finding.target_id] = finding

    claims = payload.claims
    for claim in claims:
        # Pydantic already enforced the shape; this rejects a well-formed
        # sentence that smuggled a terminator past the pattern.
        if _CLAIM_TEXT_RE.fullmatch(claim.text) is None:
            return _failure(
                FullContextValidationErrorCode.MALFORMED_CLAIM_TEXT,
                supplied_chunk_count=supplied,
            )
        if len(set(claim.cited_chunk_ids)) != len(claim.cited_chunk_ids):
            return _failure(
                FullContextValidationErrorCode.DUPLICATE_CITED_CHUNK_ID,
                supplied_chunk_count=supplied,
            )
        # The one gate that stops an invented or stale chunk ID from ever
        # reaching a reader as a real citation. No partial repair: a single
        # unresolvable ID fails the whole answer closed.
        if any(chunk_id not in chunks_by_id for chunk_id in claim.cited_chunk_ids):
            return _failure(
                FullContextValidationErrorCode.UNRESOLVABLE_CHUNK_ID,
                supplied_chunk_count=supplied,
            )

    if sum(len(claim.text) for claim in claims) > MAX_TOTAL_CLAIM_TEXT_CHARACTERS:
        return _failure(
            FullContextValidationErrorCode.TEXT_LIMIT_EXCEEDED,
            supplied_chunk_count=supplied,
        )

    premise = payload.premise_finding
    claim_ids = {claim.claim_id for claim in claims}
    correction_claims = [
        claim for claim in claims if claim.role is AnswerUnitRole.PREMISE_CORRECTION
    ]
    contradicted = premise is not None and premise.status is PremiseStatus.CONTRADICTED
    if contradicted:
        correction_id = premise.correction_claim_id if premise is not None else None
        if correction_id is None or not correction_claims:
            return _failure(
                FullContextValidationErrorCode.PREMISE_CORRECTION_MISSING,
                supplied_chunk_count=supplied,
            )
        if len(correction_claims) != 1:
            return _failure(
                FullContextValidationErrorCode.PREMISE_CORRECTION_COUNT_INVALID,
                supplied_chunk_count=supplied,
            )
        if correction_id not in claim_ids:
            return _failure(
                FullContextValidationErrorCode.UNKNOWN_CORRECTION_CLAIM_ID,
                supplied_chunk_count=supplied,
            )
        if correction_claims[0].claim_id != correction_id:
            return _failure(
                FullContextValidationErrorCode.PREMISE_CORRECTION_ID_MISMATCH,
                supplied_chunk_count=supplied,
            )
        # A correction that arrives after the answer it corrects has already been
        # read is not a correction, so ordering is validated rather than repaired.
        if claims[0].claim_id != correction_id:
            return _failure(
                FullContextValidationErrorCode.PREMISE_CORRECTION_NOT_FIRST,
                supplied_chunk_count=supplied,
            )
    else:
        correction_id = premise.correction_claim_id if premise is not None else None
        if correction_claims or correction_id is not None:
            return _failure(
                FullContextValidationErrorCode.PREMISE_CORRECTION_UNEXPECTED,
                supplied_chunk_count=supplied,
            )

    cited_chunk_ids = {chunk_id for claim in claims for chunk_id in claim.cited_chunk_ids}
    for target in trusted_target_audits:
        if target.direct_chunk_ids and cited_chunk_ids.isdisjoint(target.direct_chunk_ids):
            return _failure(
                FullContextValidationErrorCode.TRUSTED_TARGET_EVIDENCE_MISSING,
                supplied_chunk_count=supplied,
            )
        if target.certified_direct_absence and target.target_id not in absence_by_target_id:
            return _failure(
                FullContextValidationErrorCode.TRUSTED_TARGET_ABSENCE_MISSING,
                supplied_chunk_count=supplied,
            )

    if (
        claims
        and trusted_target_audits
        and not any(target.direct_chunk_ids for target in trusted_target_audits)
    ):
        # Until the application owns an explicit analogue/qualification ledger,
        # a citable but merely related claim cannot answer a question whose every
        # trusted target lacks direct manuscript evidence. This also covers a
        # resolver-restored target whose absence is deliberately non-certifiable:
        # uncertainty cannot license substitution with another subject.
        return _failure(
            FullContextValidationErrorCode.TRUSTED_TARGET_CLAIMS_UNSUPPORTED,
            supplied_chunk_count=supplied,
        )

    if claims and payload.self_reported_content_outcome is ContentOutcome.INSUFFICIENT_EVIDENCE:
        return _failure(
            FullContextValidationErrorCode.CONTENT_OUTCOME_INCONSISTENT,
            supplied_chunk_count=supplied,
        )
    if (
        not claims
        and payload.self_reported_content_outcome is not ContentOutcome.INSUFFICIENT_EVIDENCE
    ):
        return _failure(
            FullContextValidationErrorCode.CONTENT_OUTCOME_INCONSISTENT,
            supplied_chunk_count=supplied,
        )
    if not claims and (
        not trusted_target_audits
        or any(not target.certified_direct_absence for target in trusted_target_audits)
    ):
        # A model's empty answer is not an absence certificate. With no trusted
        # target, or with any target the local scan cannot certify absent, the
        # application has no basis for telling a reader that the corpus lacks an
        # answer.
        return _failure(
            FullContextValidationErrorCode.INSUFFICIENT_EVIDENCE_UNCERTIFIED,
            supplied_chunk_count=supplied,
        )

    absence_statements = tuple(
        _application_absence_statement(target_by_id[finding.target_id], finding)
        for finding in payload.absence_findings
    )

    if not claims:
        outcome = ContentOutcome.INSUFFICIENT_EVIDENCE
        return FullContextCoverageResult(
            status=CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE,
            answer="\n\n".join(absence_statements) or FULL_CONTEXT_NO_EVIDENCE_MESSAGE,
            final_chunks=[],
            content_outcome=outcome,
            error_code=None,
            diagnostics=_diagnostics(
                validation_result=DiagnosticValidationResult.VALID,
                error_code=None,
                content_outcome=outcome,
                self_reported_content_outcome=payload.self_reported_content_outcome,
                supplied_chunk_count=supplied,
                absence_finding_count=len(payload.absence_findings),
                contradicted_absence_count=0,
                trusted_target_count=len(trusted_target_audits),
                direct_target_count=sum(
                    bool(target.direct_chunk_ids) for target in trusted_target_audits
                ),
                certified_absent_target_count=sum(
                    target.certified_direct_absence for target in trusted_target_audits
                ),
                premise_status=premise.status if premise is not None else None,
            ),
        )

    # The remap: distinct cited chunk IDs, in first-cited order, become 1-based
    # source numbers. This is the only place the corpus is reduced to what a
    # reader may see, and it runs before any result object is constructed.
    source_number_by_chunk_id: dict[str, int] = {}
    final_chunks: list[dict[str, Any]] = []
    for claim in claims:
        for chunk_id in claim.cited_chunk_ids:
            if chunk_id in source_number_by_chunk_id:
                continue
            source_number_by_chunk_id[chunk_id] = len(final_chunks) + 1
            final_chunks.append(dict(chunks_by_id[chunk_id]))

    source_numbers_by_claim = {
        claim.claim_id: tuple(
            source_number_by_chunk_id[chunk_id] for chunk_id in claim.cited_chunk_ids
        )
        for claim in claims
    }
    answer = render_full_context_answer(
        claims,
        source_numbers_by_claim,
        absence_statements,
    )

    # Until an application-owned requirement ledger exists, a model's report of
    # completeness is diagnostic only. Local validation establishes grounding
    # and target coverage, not that every requested requirement was satisfied.
    content_outcome = ContentOutcome.VALID_PARTIAL

    return FullContextCoverageResult(
        status=CoverageOutcomeStatus.ANSWERED,
        answer=answer,
        final_chunks=final_chunks,
        content_outcome=content_outcome,
        error_code=None,
        diagnostics=_diagnostics(
            validation_result=DiagnosticValidationResult.VALID,
            error_code=None,
            content_outcome=content_outcome,
            self_reported_content_outcome=payload.self_reported_content_outcome,
            supplied_chunk_count=supplied,
            cited_chunk_count=len(final_chunks),
            claim_count=len(claims),
            citation_count=sum(len(claim.cited_chunk_ids) for claim in claims),
            absence_finding_count=len(payload.absence_findings),
            contradicted_absence_count=0,
            trusted_target_count=len(trusted_target_audits),
            direct_target_count=sum(
                bool(target.direct_chunk_ids) for target in trusted_target_audits
            ),
            certified_absent_target_count=sum(
                target.certified_direct_absence for target in trusted_target_audits
            ),
            premise_status=premise.status if premise is not None else None,
        ),
    )
