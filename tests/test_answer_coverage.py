from __future__ import annotations

import json
from collections.abc import Iterable

import pytest
from pydantic import ValidationError

from answer_coverage import (
    ALL_UNSUPPORTED_MESSAGE,
    CITATION_GRAMMAR,
    COMPACT_EVIDENCE_COVERAGE_SCHEMA,
    COMPACT_EVIDENCE_EXPANDER_VERSION,
    COMPACT_INTERPRETIVE_EVIDENCE_COVERAGE_SCHEMA,
    EVIDENCE_COVERAGE_SCHEMA,
    GENERATION_CONTRACT_FAILED_MESSAGE,
    INTERPRETIVE_EVIDENCE_COVERAGE_SCHEMA,
    NO_SOURCES_MESSAGE,
    AnswerUnit,
    AnswerUnitRole,
    CompactEvidenceCoverageAnswer,
    CitationLocalityFailureCode,
    ContentCompletenessContext,
    ContentCompletenessProfile,
    ContentOutcome,
    CoverageContractError,
    CoverageOutcomeStatus,
    CoverageValidationErrorCode,
    DiagnosticValidationResult,
    EvidenceDimension,
    EvidenceDimensionCoverage,
    EvidenceCoverageAnswer,
    EvidenceObligationCoverage,
    EvidenceObligationFocus,
    EvidenceObligationKind,
    EvidenceObligationScope,
    ExpectedStageTransition,
    GapReason,
    InterpretiveEvidenceCoverageAnswer,
    InterpretiveMove,
    ObligationLink,
    PremiseDecision,
    PremiseSourceScope,
    PremiseStatus,
    RequirementCoverage,
    RequirementStatus,
    coverage_diagnostic_summary,
    expand_compact_evidence_coverage,
    expand_compact_interpretive_evidence_coverage,
    parse_citation_numbers,
    process_compact_evidence_coverage,
    process_evidence_coverage,
    process_interpretive_evidence_coverage,
    render_evidence_coverage,
    validate_evidence_coverage,
    validate_evidence_coverage_context,
    validate_streamable_compact_answer_unit,
    validate_streamable_answer_unit,
)


def _unit(
    unit_id: str,
    requirement_ids: tuple[str, ...],
    text: str,
    source_numbers: tuple[int, ...],
    *,
    paragraph: int = 1,
    role: AnswerUnitRole = AnswerUnitRole.EVENT,
) -> AnswerUnit:
    return AnswerUnit(
        unit_id=unit_id,
        requirement_ids=requirement_ids,
        role=role,
        text=text,
        source_numbers=source_numbers,
        paragraph=paragraph,
    )


def _coverage(
    requirement_id: str,
    status: RequirementStatus,
    unit_ids: tuple[str, ...],
    source_numbers: tuple[int, ...],
    gap_reason: GapReason,
) -> RequirementCoverage:
    return RequirementCoverage(
        requirement_id=requirement_id,
        status=status,
        unit_ids=unit_ids,
        source_numbers=source_numbers,
        gap_reason=gap_reason,
    )


def _premise_scopes(
    premise_ids: tuple[str, ...],
    source_count: int,
    *,
    framing_source_numbers: tuple[int, ...] = (),
) -> tuple[PremiseSourceScope, ...]:
    all_sources = tuple(range(1, source_count + 1))
    return tuple(
        PremiseSourceScope(
            premise_id=premise_id,
            support_source_numbers=all_sources,
            counter_source_numbers=all_sources,
            framing_source_numbers=framing_source_numbers,
        )
        for premise_id in premise_ids
    )


def _obligation_scope(
    *,
    dimensions: tuple[EvidenceDimension, ...] = (EvidenceDimension.MECHANISM,),
) -> EvidenceObligationScope:
    return EvidenceObligationScope(
        obligation_id="O1",
        source_number=1,
        paragraph_start=1,
        paragraph_end=1,
        allowed_requirement_ids=("R1",),
        focus=EvidenceObligationFocus.MECHANISM,
        dimension_ids=dimensions,
        required_for_requirement_status=True,
    )


def _adjacent_link_scopes(
    *,
    transition_source_number: int = 2,
) -> tuple[EvidenceObligationScope, ...]:
    return (
        EvidenceObligationScope(
            obligation_id="O1",
            source_number=1,
            paragraph_start=1,
            paragraph_end=1,
            allowed_requirement_ids=("R1",),
            focus=EvidenceObligationFocus.ORIGIN,
            dimension_ids=(EvidenceDimension.STAGE_DEVELOPMENT,),
            required_for_requirement_status=False,
        ),
        EvidenceObligationScope(
            obligation_id="O2",
            source_number=2,
            paragraph_start=1,
            paragraph_end=1,
            allowed_requirement_ids=("R2",),
            focus=EvidenceObligationFocus.TRANSITION,
            dimension_ids=(EvidenceDimension.STAGE_DEVELOPMENT,),
            required_for_requirement_status=False,
        ),
        EvidenceObligationScope(
            obligation_id="O3",
            kind=EvidenceObligationKind.ADJACENT_STAGE_LINK,
            source_number=transition_source_number,
            predecessor_source_number=1,
            paragraph_start=1,
            paragraph_end=1,
            allowed_requirement_ids=("R1", "R2"),
            focus=EvidenceObligationFocus.TRANSITION,
            dimension_ids=(EvidenceDimension.ADJACENT_STAGE_LINK,),
            required_for_requirement_status=True,
        ),
    )


def _adjacent_link_answer(
    *,
    transition_source_number: int = 2,
) -> EvidenceCoverageAnswer:
    unit = AnswerUnit(
        unit_id="U1",
        requirement_ids=("R1", "R2"),
        role=AnswerUnitRole.CAUSE,
        text=(
            "The later institution explicitly continued the earlier one "
            f"[Source {transition_source_number}]."
        ),
        source_numbers=(transition_source_number,),
        paragraph=1,
        obligation_links=(
            ObligationLink(
                obligation_id="O3",
                dimension=EvidenceDimension.ADJACENT_STAGE_LINK,
            ),
        ),
    )
    return EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (transition_source_number,),
                GapReason.NONE,
            ),
            _coverage(
                "R2",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (transition_source_number,),
                GapReason.NONE,
            ),
        ),
        obligation_coverage=(
            EvidenceObligationCoverage(
                obligation_id="O1",
                dimensions=(
                    EvidenceDimensionCoverage(
                        dimension=EvidenceDimension.STAGE_DEVELOPMENT,
                        status=RequirementStatus.UNSUPPORTED,
                        unit_ids=(),
                        source_numbers=(),
                        gap_reason=GapReason.NO_DIRECT_SUPPORT,
                    ),
                ),
            ),
            EvidenceObligationCoverage(
                obligation_id="O2",
                dimensions=(
                    EvidenceDimensionCoverage(
                        dimension=EvidenceDimension.STAGE_DEVELOPMENT,
                        status=RequirementStatus.UNSUPPORTED,
                        unit_ids=(),
                        source_numbers=(),
                        gap_reason=GapReason.NO_DIRECT_SUPPORT,
                    ),
                ),
            ),
            EvidenceObligationCoverage(
                obligation_id="O3",
                dimensions=(
                    EvidenceDimensionCoverage(
                        dimension=EvidenceDimension.ADJACENT_STAGE_LINK,
                        status=RequirementStatus.SUPPORTED,
                        unit_ids=("U1",),
                        source_numbers=(transition_source_number,),
                        gap_reason=GapReason.NONE,
                    ),
                ),
            ),
        ),
        answer_units=(unit,),
    )


def _valid_answer() -> EvidenceCoverageAnswer:
    return EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(
            PremiseDecision(
                premise_id="P1",
                status=PremiseStatus.SUPPORTED,
                source_numbers=(1,),
            ),
        ),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
            _coverage(
                "R2",
                RequirementStatus.PARTIAL,
                ("U2",),
                (2, 3),
                GapReason.PARTIAL_SUPPORT,
            ),
        ),
        answer_units=(
            _unit(
                "U1",
                ("R1",),
                "A synthetic first point is supported [Source 1].",
                (1,),
                paragraph=2,
                role=AnswerUnitRole.DEFINITION,
            ),
            _unit(
                "U2",
                ("R2",),
                "A synthetic later point is bounded [Source 2, Source 3].",
                (2, 3),
                paragraph=1,
                role=AnswerUnitRole.QUALIFICATION,
            ),
        ),
    )


def _interpretive_answer(
    *,
    interpretive_moves: tuple[InterpretiveMove, ...] = (
        InterpretiveMove.ACHIEVEMENT_AND_DURABLE_CAPACITY,
    ),
    preface: str = (
        "Project Lumen deserves recognition as a meaningful achievement. "
        "Project Lumen turns pressure into a proving ground of durable capacity."
    ),
    coda: str = "Project Lumen therefore stands as a meaningful accomplishment.",
) -> InterpretiveEvidenceCoverageAnswer:
    factual = _valid_answer()
    return InterpretiveEvidenceCoverageAnswer(
        schema=INTERPRETIVE_EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=factual.premise_decisions,
        coverage=factual.coverage,
        obligation_coverage=factual.obligation_coverage,
        answer_units=factual.answer_units,
        interpretive_moves=interpretive_moves,
        interpretive_preface=preface,
        interpretive_coda=coda,
    )


def _validate(answer: EvidenceCoverageAnswer):
    return validate_evidence_coverage(
        answer,
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )


def _assert_error(
    answer: EvidenceCoverageAnswer,
    code: CoverageValidationErrorCode,
    *,
    requirement_ids: tuple[str, ...] = ("R1", "R2"),
    premise_ids: tuple[str, ...] = ("P1",),
    source_count: int = 3,
) -> None:
    with pytest.raises(CoverageContractError) as captured:
        validate_evidence_coverage(
            answer,
            requirement_ids=requirement_ids,
            premise_ids=premise_ids,
            premise_source_scopes=_premise_scopes(premise_ids, source_count),
            source_count=source_count,
        )
    assert captured.value.code is code
    assert str(captured.value) == code.value


def test_contract_models_are_frozen_strict_and_forbid_extra_fields():
    payload = _valid_answer().model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        EvidenceCoverageAnswer.model_validate(payload)

    payload = _valid_answer().model_dump(mode="json")
    payload["answer_units"][0]["paragraph"] = "2"
    with pytest.raises(ValidationError):
        EvidenceCoverageAnswer.model_validate(payload)

    with pytest.raises(ValidationError):
        EvidenceCoverageAnswer.model_validate(
            {**_valid_answer().model_dump(mode="json"), "schema": "other/1"}
        )


def test_json_shaped_payload_is_accepted_and_validated_against_trusted_inputs():
    validated = validate_evidence_coverage(
        _valid_answer().model_dump(mode="json"),
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )

    assert validated.answer == _valid_answer()
    assert validated.citation_count == 3
    assert CITATION_GRAMMAR == r"\[Source\s+\d+(?:\s*,\s*Source\s+\d+)*\]"


def test_compact_contract_expands_exact_canonical_ledgers_from_units():
    expanded = _expand_compact(_compact_payload())

    assert expanded == _valid_answer()
    assert COMPACT_EVIDENCE_EXPANDER_VERSION == "compact-evidence-expander/1"
    assert (
        validate_evidence_coverage(
            expanded,
            requirement_ids=("R1", "R2"),
            premise_ids=("P1",),
            premise_source_scopes=_premise_scopes(("P1",), 3),
            source_count=3,
        ).answer
        == _valid_answer()
    )


def test_compact_unsupported_requirement_with_unit_remains_strictly_rejected():
    payload = _compact_payload()
    payload["coverage"][0]["status"] = RequirementStatus.UNSUPPORTED
    expanded = _expand_compact(payload)

    assert expanded.coverage[0].unit_ids == ()
    with pytest.raises(CoverageContractError) as captured:
        validate_evidence_coverage(
            expanded,
            requirement_ids=("R1", "R2"),
            premise_ids=("P1",),
            premise_source_scopes=_premise_scopes(("P1",), 3),
            source_count=3,
        )
    assert captured.value.code is CoverageValidationErrorCode.UNSUPPORTED_REQUIREMENT_HAS_UNIT


@pytest.mark.parametrize(
    ("coverage", "expected_code"),
    [
        (
            [{"requirement_id": "R1", "status": "supported"}],
            CoverageValidationErrorCode.MISSING_REQUIREMENT_ID,
        ),
        (
            [
                {"requirement_id": "R1", "status": "supported"},
                {"requirement_id": "RX", "status": "partial"},
            ],
            CoverageValidationErrorCode.UNKNOWN_REQUIREMENT_ID,
        ),
        (
            [
                {"requirement_id": "R2", "status": "partial"},
                {"requirement_id": "R1", "status": "supported"},
            ],
            CoverageValidationErrorCode.OUT_OF_ORDER_REQUIREMENT_ID,
        ),
    ],
)
def test_compact_expansion_fails_closed_on_requirement_identity_errors(
    coverage: list[dict[str, str]],
    expected_code: CoverageValidationErrorCode,
):
    payload = _compact_payload()
    payload["coverage"] = coverage
    with pytest.raises(CoverageContractError) as captured:
        _expand_compact(payload)
    assert captured.value.code is expected_code


def test_compact_expansion_fails_closed_on_premise_identity_order():
    payload = _compact_payload()
    payload["premise_decisions"] = []
    with pytest.raises(CoverageContractError) as captured:
        _expand_compact(payload)
    assert captured.value.code is CoverageValidationErrorCode.MISSING_PREMISE_ID


def test_compact_expansion_fails_closed_on_schema_version():
    payload = _compact_payload()
    payload["schema"] = "archivist.compact_evidence_coverage/999"
    with pytest.raises(CoverageContractError) as captured:
        _expand_compact(payload)
    assert captured.value.code is CoverageValidationErrorCode.INVALID_PAYLOAD


def test_compact_interpretive_expansion_preserves_framing_and_premise_fields():
    canonical = _interpretive_answer()
    payload = _compact_payload(canonical)
    payload.update(
        {
            "schema": COMPACT_INTERPRETIVE_EVIDENCE_COVERAGE_SCHEMA,
            "interpretive_moves": list(canonical.interpretive_moves),
            "interpretive_preface": canonical.interpretive_preface,
            "interpretive_coda": canonical.interpretive_coda,
        }
    )

    expanded = expand_compact_interpretive_evidence_coverage(
        payload,
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )

    assert expanded == canonical


def test_compact_broad_obligation_mappings_expand_but_role_contract_still_rejects():
    scope = _obligation_scope()
    payload = {
        "schema": COMPACT_EVIDENCE_COVERAGE_SCHEMA,
        "answer_units": [
            {
                "unit_id": "U1",
                "requirement_ids": ["R1"],
                "role": AnswerUnitRole.QUALIFICATION,
                "text": "A synthetic mechanism is asserted [Source 1].",
                "paragraph": 1,
                "obligation_links": [
                    {
                        "obligation_id": "O1",
                        "dimension": EvidenceDimension.MECHANISM,
                    }
                ],
            }
        ],
        "premise_decisions": [],
        "coverage": [{"requirement_id": "R1", "status": "supported"}],
        "obligation_coverage": [
            {
                "obligation_id": "O1",
                "dimensions": [{"dimension": "mechanism", "status": "supported"}],
            }
        ],
    }
    expanded = expand_compact_evidence_coverage(
        payload,
        requirement_ids=("R1",),
        obligation_scopes=(scope,),
        source_count=1,
    )
    assert expanded.obligation_coverage[0].dimensions[0].unit_ids == ("U1",)
    with pytest.raises(CoverageContractError) as captured:
        validate_evidence_coverage(
            expanded,
            requirement_ids=("R1",),
            obligation_scopes=(scope,),
            source_count=1,
        )
    assert captured.value.code is CoverageValidationErrorCode.OBLIGATION_ROLE_MISMATCH


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda records: [],
            CoverageValidationErrorCode.MISSING_OBLIGATION_ID,
        ),
        (
            lambda records: [
                {**records[0], "obligation_id": "OX"},
            ],
            CoverageValidationErrorCode.UNKNOWN_OBLIGATION_ID,
        ),
        (
            lambda records: [
                {
                    **records[0],
                    "dimensions": [
                        {"dimension": "cause_or_enabler", "status": "supported"},
                        {"dimension": "mechanism", "status": "supported"},
                    ],
                }
            ],
            CoverageValidationErrorCode.OUT_OF_ORDER_OBLIGATION_DIMENSION,
        ),
    ],
)
def test_compact_expansion_fails_closed_on_obligation_identity_and_order(
    mutate,
    expected_code: CoverageValidationErrorCode,
):
    scope = _obligation_scope(
        dimensions=(EvidenceDimension.MECHANISM, EvidenceDimension.CAUSE_OR_ENABLER)
    )
    payload = {
        "schema": COMPACT_EVIDENCE_COVERAGE_SCHEMA,
        "answer_units": [],
        "premise_decisions": [],
        "coverage": [{"requirement_id": "R1", "status": "unsupported"}],
        "obligation_coverage": [
            {
                "obligation_id": "O1",
                "dimensions": [
                    {"dimension": "mechanism", "status": "unsupported"},
                    {"dimension": "cause_or_enabler", "status": "unsupported"},
                ],
            }
        ],
    }
    payload["obligation_coverage"] = mutate(payload["obligation_coverage"])
    with pytest.raises(CoverageContractError) as captured:
        expand_compact_evidence_coverage(
            payload,
            requirement_ids=("R1",),
            obligation_scopes=(scope,),
            source_count=1,
        )
    assert captured.value.code is expected_code


def test_compact_stream_adapter_derives_sources_before_existing_unit_validation():
    context = validate_evidence_coverage_context(("R1",), source_count=2)
    validated = validate_streamable_compact_answer_unit(
        {
            "unit_id": "U1",
            "requirement_ids": ["R1"],
            "role": "event",
            "text": "A compact unit cites its support [Source 2].",
            "paragraph": 1,
            "obligation_links": [],
        },
        context=context,
        unit_ordinal=1,
    )
    assert validated.source_numbers == (2,)


def test_compact_stream_adapter_preserves_duplicate_citations_for_strict_rejection():
    context = validate_evidence_coverage_context(("R1",), source_count=2)
    with pytest.raises(CoverageContractError) as captured:
        validate_streamable_compact_answer_unit(
            {
                "unit_id": "U1",
                "requirement_ids": ["R1"],
                "role": "event",
                "text": "A compact unit repeats a source [Source 2, Source 2].",
                "paragraph": 1,
                "obligation_links": [],
            },
            context=context,
            unit_ordinal=1,
        )
    assert captured.value.code is CoverageValidationErrorCode.DUPLICATE_SOURCE_NUMBER


def test_compact_processor_preserves_expansion_error_code():
    payload = _compact_payload()
    payload["coverage"] = [{"requirement_id": "R1", "status": "supported"}]
    result = process_compact_evidence_coverage(
        payload,
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )
    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.diagnostics.error_code is CoverageValidationErrorCode.MISSING_REQUIREMENT_ID


def test_compact_conflicting_status_derives_the_canonical_gap_and_source_ledgers():
    payload = {
        "schema": COMPACT_EVIDENCE_COVERAGE_SCHEMA,
        "answer_units": [
            {
                "unit_id": "U1",
                "requirement_ids": ["R1"],
                "role": "qualification",
                "text": "The supplied accounts conflict on the synthetic point [Source 1, Source 2].",
                "paragraph": 1,
                "obligation_links": [],
            }
        ],
        "premise_decisions": [],
        "coverage": [{"requirement_id": "R1", "status": "conflicting"}],
        "obligation_coverage": [],
    }

    result = process_compact_evidence_coverage(
        payload,
        requirement_ids=("R1",),
        source_count=2,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.diagnostics.coverage[0].status is RequirementStatus.CONFLICTING
    assert result.diagnostics.coverage[0].unit_ids == ("U1",)
    assert result.diagnostics.coverage[0].source_numbers == (1, 2)


def test_compact_partial_requirement_remains_a_valid_partial_answer():
    result = process_compact_evidence_coverage(
        _compact_payload(),
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.diagnostics.content_outcome is ContentOutcome.VALID_PARTIAL
    assert result.diagnostics.coverage[1].status is RequirementStatus.PARTIAL
    assert result.answer.endswith(
        "The retrieved passages establish only part of the requested answer."
    )


def test_compact_requirement_component_expands_through_the_unchanged_validator():
    scope = EvidenceObligationScope(
        obligation_id="O1",
        kind=EvidenceObligationKind.REQUIREMENT_COMPONENT,
        source_number=1,
        paragraph_start=1,
        paragraph_end=1,
        allowed_requirement_ids=("R1",),
        focus=EvidenceObligationFocus.CROSS_CUTTING,
        dimension_ids=(EvidenceDimension.SIGNIFICANCE_OR_CONSEQUENCE,),
        required_for_requirement_status=True,
    )
    payload = {
        "schema": COMPACT_EVIDENCE_COVERAGE_SCHEMA,
        "answer_units": [
            {
                "unit_id": "U1",
                "requirement_ids": ["R1"],
                "role": "consequence",
                "text": "The synthetic reform expanded civic capacity [Source 1].",
                "paragraph": 1,
                "obligation_links": [
                    {
                        "obligation_id": "O1",
                        "dimension": "significance_or_consequence",
                    }
                ],
            }
        ],
        "premise_decisions": [],
        "coverage": [{"requirement_id": "R1", "status": "supported"}],
        "obligation_coverage": [
            {
                "obligation_id": "O1",
                "dimensions": [
                    {
                        "dimension": "significance_or_consequence",
                        "status": "supported",
                    }
                ],
            }
        ],
    }

    result = process_compact_evidence_coverage(
        payload,
        requirement_ids=("R1",),
        obligation_scopes=(scope,),
        source_count=1,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.diagnostics.validation_result is DiagnosticValidationResult.VALID
    assert result.diagnostics.obligation_coverage[0].dimensions[0].unit_ids == ("U1",)
    assert result.diagnostics.obligation_coverage[0].dimensions[0].source_numbers == (1,)


def test_compact_stage_and_adjacent_link_chain_is_content_complete():
    canonical, scopes = _two_stage_supported_answer(include_transition=True)

    result = process_compact_evidence_coverage(
        _compact_payload(canonical),
        requirement_ids=("R1", "R2"),
        obligation_scopes=scopes,
        source_count=2,
        completeness_context=_two_stage_completeness_context(),
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.diagnostics.validation_result is DiagnosticValidationResult.VALID
    assert result.diagnostics.content_outcome is ContentOutcome.VALID_COMPLETE
    assert result.diagnostics.realized_stage_count == 2
    assert result.diagnostics.realized_transition_count == 1
    assert result.diagnostics.required_obligation_dimension_count == 3


def test_compact_institutional_handoff_realizes_a_lineage_stage():
    scope = EvidenceObligationScope(
        obligation_id="O1",
        source_number=1,
        paragraph_start=1,
        paragraph_end=1,
        allowed_requirement_ids=("R1",),
        focus=EvidenceObligationFocus.ORIGIN,
        dimension_ids=(
            EvidenceDimension.STAGE_DEVELOPMENT,
            EvidenceDimension.INSTITUTIONAL_HANDOFF,
        ),
        required_for_requirement_status=True,
    )
    payload = {
        "schema": COMPACT_EVIDENCE_COVERAGE_SCHEMA,
        "answer_units": [
            {
                "unit_id": "U1",
                "requirement_ids": ["R1"],
                "role": "event",
                "text": "The institution transferred its civic capacity to its successor [Source 1].",
                "paragraph": 1,
                "obligation_links": [
                    {"obligation_id": "O1", "dimension": "stage_development"},
                    {"obligation_id": "O1", "dimension": "institutional_handoff"},
                ],
            }
        ],
        "premise_decisions": [],
        "coverage": [{"requirement_id": "R1", "status": "supported"}],
        "obligation_coverage": [
            {
                "obligation_id": "O1",
                "dimensions": [
                    {"dimension": "stage_development", "status": "supported"},
                    {"dimension": "institutional_handoff", "status": "supported"},
                ],
            }
        ],
    }
    completeness = ContentCompletenessContext(
        profile=ContentCompletenessProfile.LONG_INSTITUTIONAL_LINEAGE,
        required_requirement_ids=("R1",),
        expected_stage_requirement_ids=("R1",),
        expected_stage_transitions=(),
        minimum_supported_obligation_ratio=1.0,
        require_institutional_handoffs=True,
    )

    result = process_compact_evidence_coverage(
        payload,
        requirement_ids=("R1",),
        obligation_scopes=(scope,),
        source_count=1,
        completeness_context=completeness,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.diagnostics.validation_result is DiagnosticValidationResult.VALID
    assert result.diagnostics.content_outcome is ContentOutcome.VALID_COMPLETE
    assert result.diagnostics.realized_stage_count == 1
    assert result.diagnostics.supported_required_obligation_dimension_count == 2


def test_compact_contradicted_premise_preserves_the_correction_contract():
    payload = {
        "schema": COMPACT_EVIDENCE_COVERAGE_SCHEMA,
        "answer_units": [
            {
                "unit_id": "U1",
                "requirement_ids": [],
                "role": "premise_correction",
                "text": "The assumed premise is contradicted [Source 1].",
                "paragraph": 1,
                "obligation_links": [],
            },
            {
                "unit_id": "U2",
                "requirement_ids": ["R1"],
                "role": "event",
                "text": "The requested point is separately supported [Source 2].",
                "paragraph": 2,
                "obligation_links": [],
            },
        ],
        "premise_decisions": [
            {
                "premise_id": "P1",
                "status": "contradicted",
                "source_numbers": [1],
                "correction_unit_id": "U1",
            }
        ],
        "coverage": [{"requirement_id": "R1", "status": "supported"}],
        "obligation_coverage": [],
    }

    result = process_compact_evidence_coverage(
        payload,
        requirement_ids=("R1",),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 2),
        source_count=2,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.answer.startswith("The assumed premise is contradicted")
    assert result.diagnostics.premise_decisions[0].status is PremiseStatus.CONTRADICTED
    assert result.diagnostics.premise_decisions[0].source_numbers == (1,)
    assert result.diagnostics.answer_units[0].source_numbers == (1,)


def test_compact_unresolved_premise_stays_uncited_and_has_no_correction():
    payload = {
        "schema": COMPACT_EVIDENCE_COVERAGE_SCHEMA,
        "answer_units": [
            {
                "unit_id": "U1",
                "requirement_ids": ["R1"],
                "role": "event",
                "text": "The requested point is supported independently [Source 1].",
                "paragraph": 1,
                "obligation_links": [],
            }
        ],
        "premise_decisions": [
            {
                "premise_id": "P1",
                "status": "unresolved",
                "source_numbers": [],
                "correction_unit_id": None,
            }
        ],
        "coverage": [{"requirement_id": "R1", "status": "supported"}],
        "obligation_coverage": [],
    }

    result = process_compact_evidence_coverage(
        payload,
        requirement_ids=("R1",),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 1),
        source_count=1,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.diagnostics.premise_decisions[0].status is PremiseStatus.UNRESOLVED
    assert result.diagnostics.premise_decisions[0].source_numbers == ()
    assert result.diagnostics.premise_decisions[0].correction_unit_id is None


def test_compact_progressive_unit_expands_identically_to_terminal_expansion():
    payload = _compact_payload()
    context = validate_evidence_coverage_context(
        ("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )

    streamed_unit = validate_streamable_compact_answer_unit(
        payload["answer_units"][0],
        context=context,
        unit_ordinal=1,
    )
    terminal_unit = _expand_compact(payload).answer_units[0]

    assert streamed_unit == terminal_unit


def test_compact_all_unsupported_and_no_sources_preserve_abstention_outcomes():
    unsupported = {
        "schema": COMPACT_EVIDENCE_COVERAGE_SCHEMA,
        "answer_units": [],
        "premise_decisions": [],
        "coverage": [{"requirement_id": "R1", "status": "unsupported"}],
        "obligation_coverage": [],
    }

    result = process_compact_evidence_coverage(
        unsupported,
        requirement_ids=("R1",),
        source_count=1,
    )
    no_sources = process_compact_evidence_coverage(
        unsupported,
        requirement_ids=("R1",),
        source_count=0,
    )

    assert result.status is CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE
    assert result.answer == ALL_UNSUPPORTED_MESSAGE
    assert result.diagnostics.content_outcome is ContentOutcome.INSUFFICIENT_EVIDENCE
    assert no_sources.status is CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE
    assert no_sources.answer == NO_SOURCES_MESSAGE
    assert no_sources.diagnostics.validation_result is DiagnosticValidationResult.NOT_RUN


def test_compact_json_schema_is_smaller_and_omits_redundant_mapping_fields():
    canonical = json.dumps(EvidenceCoverageAnswer.model_json_schema(), sort_keys=True)
    compact_schema = CompactEvidenceCoverageAnswer.model_json_schema()
    compact = json.dumps(compact_schema, sort_keys=True)

    assert len(compact) < len(canonical)
    assert "source_numbers" not in compact_schema["$defs"]["CompactAnswerUnit"]["properties"]
    compact_requirement = compact_schema["$defs"]["CompactRequirementCoverage"]["properties"]
    assert set(compact_requirement) == {"requirement_id", "status"}
    compact_dimension = compact_schema["$defs"]["CompactEvidenceDimensionCoverage"]["properties"]
    assert set(compact_dimension) == {"dimension", "status"}


def test_representative_compact_payload_is_materially_smaller_than_canonical_payload():
    canonical, _scopes = _two_stage_supported_answer(include_transition=True)
    canonical_json = json.dumps(
        canonical.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
    )
    compact_json = json.dumps(
        _compact_payload(canonical),
        sort_keys=True,
        separators=(",", ":"),
    )

    assert len(canonical_json) - len(compact_json) >= 300
    assert len(compact_json) / len(canonical_json) <= 0.8


def test_interpretive_coverage_frames_the_factual_answer_with_subjective_prose():
    move = InterpretiveMove.ACHIEVEMENT_AND_DURABLE_CAPACITY
    result = process_interpretive_evidence_coverage(
        _interpretive_answer(),
        required_moves=(move,),
        question_anchors=("Project Lumen",),
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    paragraphs = result.answer.split("\n\n")
    assert paragraphs[0] == (
        "Project Lumen deserves recognition as a meaningful achievement. "
        "Project Lumen turns pressure into a proving ground of durable capacity."
    )
    assert paragraphs[-1] == ("Project Lumen therefore stands as a meaningful accomplishment.")
    assert "A synthetic later point is bounded [Source 2, Source 3]." in result.answer
    assert result.diagnostics.validation_result is DiagnosticValidationResult.VALID


def test_answered_interpretive_coverage_fails_without_the_required_coda():
    answer = _interpretive_answer().model_copy(
        update={"interpretive_coda": ""},
    )
    result = process_interpretive_evidence_coverage(
        answer,
        required_moves=(InterpretiveMove.ACHIEVEMENT_AND_DURABLE_CAPACITY,),
        question_anchors=("Project Lumen",),
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert (
        result.diagnostics.error_code is CoverageValidationErrorCode.MISSING_INTERPRETIVE_PARAGRAPH
    )


def test_interpretive_frame_rejects_citations_and_wrong_sentence_counts():
    cited = process_interpretive_evidence_coverage(
        _interpretive_answer(
            coda="This achievement deserves admiration [Source 1].",
        ),
        required_moves=(InterpretiveMove.ACHIEVEMENT_AND_DURABLE_CAPACITY,),
        question_anchors=("Project Lumen",),
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )
    too_short = process_interpretive_evidence_coverage(
        _interpretive_answer(preface="Achievement should define this account."),
        required_moves=(InterpretiveMove.ACHIEVEMENT_AND_DURABLE_CAPACITY,),
        question_anchors=("Project Lumen",),
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )

    assert (
        cited.diagnostics.error_code is CoverageValidationErrorCode.INTERPRETIVE_CITATION_FORBIDDEN
    )
    assert (
        too_short.diagnostics.error_code
        is CoverageValidationErrorCode.INTERPRETIVE_SENTENCE_COUNT_INVALID
    )


def test_interpretive_frame_rejects_first_person_and_generic_subjectless_prose():
    first_person = process_interpretive_evidence_coverage(
        _interpretive_answer(
            preface=(
                "I regard Project Lumen as a meaningful achievement. "
                "Project Lumen turns pressure into durable capacity."
            ),
        ),
        required_moves=(InterpretiveMove.ACHIEVEMENT_AND_DURABLE_CAPACITY,),
        question_anchors=("Project Lumen",),
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )
    generic = process_interpretive_evidence_coverage(
        _interpretive_answer(
            preface=(
                "Achievement deserves to stand at the center of this account. "
                "Pressure becomes the proving ground of durable capacity."
            ),
            coda="The result therefore stands as a meaningful accomplishment.",
        ),
        required_moves=(InterpretiveMove.ACHIEVEMENT_AND_DURABLE_CAPACITY,),
        question_anchors=("Project Lumen",),
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )

    assert (
        first_person.diagnostics.error_code
        is CoverageValidationErrorCode.INTERPRETIVE_FIRST_PERSON_FORBIDDEN
    )
    assert (
        generic.diagnostics.error_code is CoverageValidationErrorCode.INTERPRETIVE_SUBJECT_MISSING
    )


def test_entirely_unsupported_coverage_does_not_invent_interpretation():
    answer = _interpretive_answer().model_copy(
        update={
            "coverage": (
                _coverage(
                    "R1",
                    RequirementStatus.UNSUPPORTED,
                    (),
                    (),
                    GapReason.NO_DIRECT_SUPPORT,
                ),
                _coverage(
                    "R2",
                    RequirementStatus.UNSUPPORTED,
                    (),
                    (),
                    GapReason.NO_DIRECT_SUPPORT,
                ),
            ),
            "answer_units": (),
        }
    )

    result = process_interpretive_evidence_coverage(
        answer,
        required_moves=(InterpretiveMove.ACHIEVEMENT_AND_DURABLE_CAPACITY,),
        question_anchors=("Project Lumen",),
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )

    assert result.status is CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE
    assert result.answer == ALL_UNSUPPORTED_MESSAGE


@pytest.mark.parametrize(
    ("records", "code"),
    [
        (
            lambda answer: (answer.coverage[0],),
            CoverageValidationErrorCode.MISSING_REQUIREMENT_ID,
        ),
        (
            lambda answer: (answer.coverage[0], answer.coverage[0]),
            CoverageValidationErrorCode.DUPLICATE_REQUIREMENT_ID,
        ),
        (
            lambda answer: (
                answer.coverage[0],
                answer.coverage[1].model_copy(update={"requirement_id": "RX"}),
            ),
            CoverageValidationErrorCode.UNKNOWN_REQUIREMENT_ID,
        ),
        (
            lambda answer: tuple(reversed(answer.coverage)),
            CoverageValidationErrorCode.OUT_OF_ORDER_REQUIREMENT_ID,
        ),
    ],
)
def test_requirement_ids_must_be_exactly_once_and_in_input_order(records, code):
    answer = _valid_answer()
    changed = answer.model_copy(update={"coverage": records(answer)})
    _assert_error(changed, code)


@pytest.mark.parametrize(
    ("decisions", "code"),
    [
        ((), CoverageValidationErrorCode.MISSING_PREMISE_ID),
        (
            (
                PremiseDecision(
                    premise_id="P1",
                    status=PremiseStatus.SUPPORTED,
                    source_numbers=(1,),
                ),
                PremiseDecision(
                    premise_id="P1",
                    status=PremiseStatus.SUPPORTED,
                    source_numbers=(1,),
                ),
            ),
            CoverageValidationErrorCode.DUPLICATE_PREMISE_ID,
        ),
        (
            (
                PremiseDecision(
                    premise_id="PX",
                    status=PremiseStatus.SUPPORTED,
                    source_numbers=(1,),
                ),
            ),
            CoverageValidationErrorCode.UNKNOWN_PREMISE_ID,
        ),
    ],
)
def test_premise_ids_must_be_exactly_once(decisions, code):
    answer = _valid_answer().model_copy(update={"premise_decisions": decisions})
    _assert_error(answer, code)


def test_premise_ids_must_remain_in_input_order():
    decisions = (
        PremiseDecision(
            premise_id="P2",
            status=PremiseStatus.CONTRADICTED,
            source_numbers=(2,),
        ),
        PremiseDecision(
            premise_id="P1",
            status=PremiseStatus.SUPPORTED,
            source_numbers=(1,),
        ),
    )
    answer = _valid_answer().model_copy(update={"premise_decisions": decisions})
    _assert_error(
        answer,
        CoverageValidationErrorCode.OUT_OF_ORDER_PREMISE_ID,
        premise_ids=("P1", "P2"),
    )


@pytest.mark.parametrize(
    "status",
    [PremiseStatus.SUPPORTED, PremiseStatus.CONTRADICTED],
)
def test_evidentiary_premise_decisions_require_sources(status):
    answer = _valid_answer()
    decision = PremiseDecision(
        premise_id="P1",
        status=status,
        source_numbers=(),
    )
    changed = answer.model_copy(update={"premise_decisions": (decision,)})
    _assert_error(changed, CoverageValidationErrorCode.PREMISE_SOURCE_MISMATCH)


@pytest.mark.parametrize(
    "status",
    [PremiseStatus.UNRESOLVED, PremiseStatus.NOT_APPLICABLE],
)
def test_non_evidentiary_premise_decisions_forbid_sources(status):
    answer = _valid_answer()
    decision = PremiseDecision(
        premise_id="P1",
        status=status,
        source_numbers=(1,),
    )
    changed = answer.model_copy(update={"premise_decisions": (decision,)})
    _assert_error(changed, CoverageValidationErrorCode.PREMISE_SOURCE_MISMATCH)


def test_contradicted_premise_requires_a_source_bound_leading_correction():
    correction = _unit(
        "U1",
        (),
        "The assumed premise is contradicted [Source 1].",
        (1,),
        role=AnswerUnitRole.PREMISE_CORRECTION,
    )
    substantive = _unit(
        "U2",
        ("R1",),
        "The requested point is separately supported [Source 1].",
        (1,),
        paragraph=2,
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(
            PremiseDecision(
                premise_id="P1",
                status=PremiseStatus.CONTRADICTED,
                source_numbers=(1,),
                correction_unit_id="U1",
            ),
        ),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U2",),
                (1,),
                GapReason.NONE,
            ),
        ),
        answer_units=(correction, substantive),
    )

    validated = validate_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 1),
        source_count=1,
    )
    assert render_evidence_coverage(validated).startswith("The assumed premise is contradicted")

    missing = answer.premise_decisions[0].model_copy(update={"correction_unit_id": None})
    _assert_error(
        answer.model_copy(update={"premise_decisions": (missing,)}),
        CoverageValidationErrorCode.PREMISE_CORRECTION_MISSING,
        requirement_ids=("R1",),
        premise_ids=("P1",),
        source_count=1,
    )

    wrong_role = correction.model_copy(
        update={
            "role": AnswerUnitRole.EVENT,
            "requirement_ids": ("R1",),
        }
    )
    _assert_error(
        answer.model_copy(update={"answer_units": (wrong_role, substantive)}),
        CoverageValidationErrorCode.PREMISE_CORRECTION_INVALID,
        requirement_ids=("R1",),
        premise_ids=("P1",),
        source_count=1,
    )


def test_contradicted_premise_correction_must_render_first():
    first = _unit(
        "U2",
        ("R1",),
        "Context appears before the correction [Source 1].",
        (1,),
        paragraph=1,
    )
    correction = _unit(
        "U1",
        (),
        "The premise is corrected later [Source 1].",
        (1,),
        paragraph=2,
        role=AnswerUnitRole.PREMISE_CORRECTION,
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(
            PremiseDecision(
                premise_id="P1",
                status=PremiseStatus.CONTRADICTED,
                source_numbers=(1,),
                correction_unit_id="U1",
            ),
        ),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U2",),
                (1,),
                GapReason.NONE,
            ),
        ),
        answer_units=(correction, first),
    )

    _assert_error(
        answer,
        CoverageValidationErrorCode.PREMISE_CORRECTION_NOT_FIRST,
        requirement_ids=("R1",),
        premise_ids=("P1",),
        source_count=1,
    )


def test_listed_premise_cannot_be_marked_not_applicable():
    decision = PremiseDecision(
        premise_id="P1",
        status=PremiseStatus.NOT_APPLICABLE,
        source_numbers=(),
    )
    changed = _valid_answer().model_copy(update={"premise_decisions": (decision,)})
    _assert_error(
        changed,
        CoverageValidationErrorCode.PREMISE_STATUS_INVALID,
    )


def test_duplicate_and_unknown_unit_ids_fail_closed():
    answer = _valid_answer()
    duplicate = answer.answer_units[1].model_copy(update={"unit_id": "U1"})
    _assert_error(
        answer.model_copy(update={"answer_units": (answer.answer_units[0], duplicate)}),
        CoverageValidationErrorCode.DUPLICATE_UNIT_ID,
    )

    unknown_reference = answer.coverage[0].model_copy(update={"unit_ids": ("UX",)})
    _assert_error(
        answer.model_copy(update={"coverage": (unknown_reference, answer.coverage[1])}),
        CoverageValidationErrorCode.UNKNOWN_UNIT_ID,
    )


def test_unit_requirement_ids_must_be_known_and_in_requirement_order():
    answer = _valid_answer()
    unknown = answer.answer_units[0].model_copy(update={"requirement_ids": ("RX",)})
    _assert_error(
        answer.model_copy(update={"answer_units": (unknown, answer.answer_units[1])}),
        CoverageValidationErrorCode.UNKNOWN_UNIT_REQUIREMENT_ID,
    )

    shared = answer.answer_units[0].model_copy(update={"requirement_ids": ("R2", "R1")})
    _assert_error(
        answer.model_copy(update={"answer_units": (shared, answer.answer_units[1])}),
        CoverageValidationErrorCode.OUT_OF_ORDER_UNIT_REQUIREMENT_ID,
    )


@pytest.mark.parametrize(
    "text",
    [
        "Malformed [Source 1, 2].",
        "Malformed [Sources 1].",
        "Malformed [source 1].",
        "Malformed [3].",
        "Malformed [[Source 1]].",
        "Malformed [Source 1.",
        "Malformed [note] plus [Source 1].",
    ],
)
def test_locked_citation_grammar_rejects_every_malformed_bracket(text):
    answer = _valid_answer()
    unit = answer.answer_units[0].model_copy(update={"text": text})
    changed = answer.model_copy(update={"answer_units": (unit, answer.answer_units[1])})
    _assert_error(changed, CoverageValidationErrorCode.MALFORMED_CITATION)


def test_citation_parser_accepts_only_locked_single_and_group_forms():
    assert parse_citation_numbers("One [Source 1] and another [Source 2, Source 3].") == (1, 2, 3)


@pytest.mark.parametrize(
    "text",
    [
        "One factual sentence. A second factual sentence [Source 1].",
        "One factual clause; a second factual clause [Source 1].",
        "One factual line\nA second factual line [Source 1].",
        "One claim [Source 1]. Another claim [Source 1].",
        "One cited claim [Source 1] followed by uncited prose.",
        "One claim without ending punctuation [Source 1]",
        "One claim about Example Co. A second claim followed [Source 1].",
        "One claim in the U.S. The next claim followed [Source 1].",
        "The company was based in the U.S. Markets then fell [Source 1].",
        "The first category was A. Markets then fell [Source 1].",
        "U.S. policy changed [Source 1].",
    ],
)
def test_answer_units_reject_mechanically_nonlocal_citations(text):
    answer = _valid_answer()
    unit = answer.answer_units[0].model_copy(
        update={
            "text": text,
            "source_numbers": tuple(dict.fromkeys(parse_citation_numbers(text))),
        }
    )
    changed = answer.model_copy(update={"answer_units": (unit, answer.answer_units[1])})

    _assert_error(
        changed,
        CoverageValidationErrorCode.CITATION_LOCALITY_INVALID,
    )


def test_atomic_answer_unit_accepts_one_terminal_single_or_grouped_citation():
    answer = _valid_answer()
    terminal_single_citation = answer.answer_units[0].model_copy(
        update={"text": "One synthetic atomic claim [Source 1]."}
    )
    validated = _validate(
        answer.model_copy(
            update={
                "answer_units": (
                    terminal_single_citation,
                    answer.answer_units[1],
                )
            }
        )
    )

    assert validated.answer.answer_units[0].text == terminal_single_citation.text

    conflicting = _unit(
        "U1",
        ("R1",),
        "The synthetic sources disagree [Source 1, Source 2].",
        (1, 2),
    )
    conflicting_answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.CONFLICTING,
                ("U1",),
                (1, 2),
                GapReason.SOURCE_CONFLICT,
            ),
        ),
        answer_units=(conflicting,),
    )
    assert (
        validate_evidence_coverage(
            conflicting_answer,
            requirement_ids=("R1",),
            source_count=2,
        )
        .answer.answer_units[0]
        .text
        == conflicting.text
    )


def test_locality_failure_keeps_its_precise_diagnostic_and_never_renders_prose():
    bundled_text = "One factual sentence. A second factual sentence [Source 1]."
    answer = _valid_answer()
    unit = answer.answer_units[0].model_copy(update={"text": bundled_text})

    result = process_evidence_coverage(
        answer.model_copy(update={"answer_units": (unit, answer.answer_units[1])}),
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.diagnostics.error_code is CoverageValidationErrorCode.CITATION_LOCALITY_INVALID
    assert result.diagnostics.citation_locality_failure is not None
    assert (
        result.diagnostics.citation_locality_failure.code
        is CitationLocalityFailureCode.INTERNAL_SENTENCE_TERMINATOR
    )
    assert result.diagnostics.citation_locality_failure.unit_id == "U1"
    assert result.diagnostics.citation_locality_failure.unit_ordinal == 1
    assert bundled_text not in result.answer


def test_one_duplicate_pre_citation_terminator_is_repaired_without_changing_claim():
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
        ),
        answer_units=(
            _unit(
                "U1",
                ("R1",),
                "One synthetic atomic claim.[Source 1].",
                (1,),
            ),
        ),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        source_count=1,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.answer == "One synthetic atomic claim [Source 1]."
    assert result.diagnostics.citation_locality_failure is None
    assert result.diagnostics.repair_codes == (
        CoverageValidationErrorCode.CITATION_LOCALITY_INVALID,
    )


@pytest.mark.parametrize(
    "text,expected_code",
    [
        (
            "First synthetic claim. Second synthetic claim.[Source 1].",
            CitationLocalityFailureCode.INTERNAL_SENTENCE_TERMINATOR,
        ),
        (
            "One synthetic claim; another synthetic claim.[Source 1].",
            CitationLocalityFailureCode.SEMICOLON_IN_CLAIM,
        ),
        (
            "One synthetic claim\ncontinued.[Source 1].",
            CitationLocalityFailureCode.MULTILINE_CLAIM,
        ),
    ],
)
def test_duplicate_terminator_repair_rejects_every_nonexact_shape(
    text,
    expected_code,
):
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
        ),
        answer_units=(_unit("U1", ("R1",), text, (1,)),),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        source_count=1,
    )

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.diagnostics.citation_locality_failure is not None
    assert result.diagnostics.citation_locality_failure.code is expected_code
    assert result.diagnostics.repair_applied is False


@pytest.mark.parametrize(
    "text,source_numbers",
    [
        ("United States policy changed [Source 1].", (1,)),
        ("The United States Army acted [Source 1].", (1,)),
        ("Doctor Example acted [Source 1].", (1,)),
        ("Example Company operated locally [Source 1].", (1,)),
        ("In 1700, policy changed [Source 1, Source 2].", (1, 2)),
        ("The compact joined Alpha and Beta [Source 1, Source 2].", (1, 2)),
        ("The ratio was 2:1 [Source 1].", (1,)),
    ],
)
def test_locality_validation_does_not_guess_semantics_from_safe_punctuation(
    text,
    source_numbers,
):
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                source_numbers,
                GapReason.NONE,
            ),
        ),
        answer_units=(_unit("U1", ("R1",), text, source_numbers),),
    )

    validated = validate_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        source_count=3,
    )

    assert validated.answer.answer_units[0].text == text


def test_answer_unit_schema_explicitly_requires_one_independently_checkable_claim():
    text_schema = EvidenceCoverageAnswer.model_json_schema()["$defs"]["AnswerUnit"]["properties"][
        "text"
    ]
    description = text_schema["description"]

    assert "one independently checkable factual claim" in description
    assert "one terminal citation group" in description
    assert "period-containing abbreviations" in description
    assert text_schema["pattern"].endswith(r"\][.!?]$")


def test_openai_strict_response_schema_preserves_atomic_citation_pattern():
    from openai.lib._parsing._responses import type_to_text_format_param

    response_format = type_to_text_format_param(EvidenceCoverageAnswer)
    text_schema = response_format["schema"]["$defs"]["AnswerUnit"]["properties"]["text"]

    assert response_format["strict"] is True
    assert text_schema["pattern"].endswith(r"\][.!?]$")


def test_broad_obligation_ledger_validates_exact_source_dimension_and_role():
    scope = _obligation_scope()
    unit = AnswerUnit(
        unit_id="U1",
        requirement_ids=("R1",),
        role=AnswerUnitRole.MECHANISM,
        text="A synthetic process connected the stages [Source 1].",
        source_numbers=(1,),
        paragraph=1,
        obligation_links=(
            ObligationLink(
                obligation_id="O1",
                dimension=EvidenceDimension.MECHANISM,
            ),
        ),
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
        ),
        obligation_coverage=(
            EvidenceObligationCoverage(
                obligation_id="O1",
                dimensions=(
                    EvidenceDimensionCoverage(
                        dimension=EvidenceDimension.MECHANISM,
                        status=RequirementStatus.SUPPORTED,
                        unit_ids=("U1",),
                        source_numbers=(1,),
                        gap_reason=GapReason.NONE,
                    ),
                ),
            ),
        ),
        answer_units=(unit,),
    )

    validated = validate_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        obligation_scopes=(scope,),
        source_count=1,
    )

    assert validated.answer.obligation_coverage[0].dimensions[0].unit_ids == ("U1",)
    assert validated.answer.answer_units[0].obligation_links[0].obligation_id == "O1"


def test_streamable_unit_rejects_role_incompatible_with_linked_dimension():
    scope = _obligation_scope(dimensions=(EvidenceDimension.QUALIFICATION_OR_COUNTERARGUMENT,))
    context = validate_evidence_coverage_context(
        requirement_ids=("R1",),
        premise_ids=(),
        premise_source_scopes=(),
        obligation_scopes=(scope,),
        source_count=1,
    )
    unit = AnswerUnit(
        unit_id="U1",
        requirement_ids=("R1",),
        role=AnswerUnitRole.MECHANISM,
        text="A synthetic process connected the stages [Source 1].",
        source_numbers=(1,),
        paragraph=1,
        obligation_links=(
            ObligationLink(
                obligation_id="O1",
                dimension=EvidenceDimension.QUALIFICATION_OR_COUNTERARGUMENT,
            ),
        ),
    )

    with pytest.raises(CoverageContractError) as captured:
        validate_streamable_answer_unit(
            unit,
            context=context,
            unit_ordinal=1,
        )

    assert captured.value.code is CoverageValidationErrorCode.OBLIGATION_ROLE_MISMATCH


def _compact_payload(
    answer: EvidenceCoverageAnswer | None = None,
) -> dict[str, object]:
    canonical = answer or _valid_answer()
    return {
        "schema": COMPACT_EVIDENCE_COVERAGE_SCHEMA,
        "answer_units": [
            {
                "unit_id": unit.unit_id,
                "requirement_ids": list(unit.requirement_ids),
                "role": unit.role,
                "text": unit.text,
                "paragraph": unit.paragraph,
                "obligation_links": [
                    link.model_dump(mode="json") for link in unit.obligation_links
                ],
            }
            for unit in canonical.answer_units
        ],
        "premise_decisions": [
            record.model_dump(mode="json") for record in canonical.premise_decisions
        ],
        "coverage": [
            {
                "requirement_id": record.requirement_id,
                "status": record.status,
            }
            for record in canonical.coverage
        ],
        "obligation_coverage": [
            {
                "obligation_id": record.obligation_id,
                "dimensions": [
                    {
                        "dimension": dimension.dimension,
                        "status": dimension.status,
                    }
                    for dimension in record.dimensions
                ],
            }
            for record in canonical.obligation_coverage
        ],
    }


def _expand_compact(payload: dict[str, object]) -> EvidenceCoverageAnswer:
    return expand_compact_evidence_coverage(
        payload,
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )


def test_generation_schemas_put_streamable_units_before_terminal_ledgers():
    neutral_properties = list(EvidenceCoverageAnswer.model_json_schema()["properties"])
    interpretive_properties = list(
        InterpretiveEvidenceCoverageAnswer.model_json_schema()["properties"]
    )

    assert neutral_properties[:2] == ["schema", "answer_units"]
    assert interpretive_properties[:2] == ["schema", "answer_units"]
    assert neutral_properties[2:] == [
        "premise_decisions",
        "coverage",
        "obligation_coverage",
    ]


def test_adjacent_stage_link_requires_a_later_source_bounded_causal_unit():
    validated = validate_evidence_coverage(
        _adjacent_link_answer(),
        requirement_ids=("R1", "R2"),
        obligation_scopes=_adjacent_link_scopes(),
        source_count=2,
    )

    link_unit = validated.answer.answer_units[0]
    assert link_unit.requirement_ids == ("R1", "R2")
    assert link_unit.source_numbers == (2,)
    assert link_unit.role is AnswerUnitRole.CAUSE


def test_adjacent_stage_link_accepts_a_distinct_transition_passage():
    validated = validate_evidence_coverage(
        _adjacent_link_answer(transition_source_number=3),
        requirement_ids=("R1", "R2"),
        obligation_scopes=_adjacent_link_scopes(
            transition_source_number=3,
        ),
        source_count=3,
    )

    link_unit = validated.answer.answer_units[0]
    assert link_unit.source_numbers == (3,)
    assert link_unit.requirement_ids == ("R1", "R2")


def test_adjacent_stage_link_context_rejects_a_missing_successor_stage():
    scopes = _adjacent_link_scopes(transition_source_number=3)

    with pytest.raises(CoverageContractError) as captured:
        validate_evidence_coverage_context(
            requirement_ids=("R1", "R2"),
            obligation_scopes=(scopes[0], scopes[2]),
            source_count=3,
        )

    assert captured.value.code is CoverageValidationErrorCode.INVALID_CONTEXT


def test_adjacent_stage_link_context_preserves_the_predecessor_anchor():
    scopes = _adjacent_link_scopes(transition_source_number=3)
    wrong_predecessor = scopes[2].model_copy(
        update={"predecessor_source_number": 2},
    )

    with pytest.raises(CoverageContractError) as captured:
        validate_evidence_coverage_context(
            requirement_ids=("R1", "R2"),
            obligation_scopes=(*scopes[:2], wrong_predecessor),
            source_count=3,
        )

    assert captured.value.code is CoverageValidationErrorCode.INVALID_CONTEXT


def test_requirement_component_requires_its_source_bounded_material_layer():
    scope = EvidenceObligationScope(
        obligation_id="O1",
        kind=EvidenceObligationKind.REQUIREMENT_COMPONENT,
        source_number=1,
        paragraph_start=1,
        paragraph_end=1,
        allowed_requirement_ids=("R1",),
        focus=EvidenceObligationFocus.CROSS_CUTTING,
        dimension_ids=(EvidenceDimension.SIGNIFICANCE_OR_CONSEQUENCE,),
        required_for_requirement_status=True,
    )
    unit = AnswerUnit(
        unit_id="U1",
        requirement_ids=("R1",),
        role=AnswerUnitRole.CONSEQUENCE,
        text="The synthetic reform expanded civic capacity [Source 1].",
        source_numbers=(1,),
        paragraph=1,
        obligation_links=(
            ObligationLink(
                obligation_id="O1",
                dimension=EvidenceDimension.SIGNIFICANCE_OR_CONSEQUENCE,
            ),
        ),
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
        ),
        obligation_coverage=(
            EvidenceObligationCoverage(
                obligation_id="O1",
                dimensions=(
                    EvidenceDimensionCoverage(
                        dimension=(EvidenceDimension.SIGNIFICANCE_OR_CONSEQUENCE),
                        status=RequirementStatus.SUPPORTED,
                        unit_ids=("U1",),
                        source_numbers=(1,),
                        gap_reason=GapReason.NONE,
                    ),
                ),
            ),
        ),
        answer_units=(unit,),
    )

    validated = validate_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        obligation_scopes=(scope,),
        source_count=1,
    )

    assert validated.answer.answer_units[0].role is AnswerUnitRole.CONSEQUENCE


def test_requirement_component_rejects_multiple_requirements():
    with pytest.raises(ValidationError):
        EvidenceObligationScope(
            obligation_id="O1",
            kind=EvidenceObligationKind.REQUIREMENT_COMPONENT,
            source_number=1,
            paragraph_start=1,
            paragraph_end=1,
            allowed_requirement_ids=("R1", "R2"),
            focus=EvidenceObligationFocus.CROSS_CUTTING,
            dimension_ids=(EvidenceDimension.ACTION_OR_MECHANISM,),
            required_for_requirement_status=True,
        )


def test_adjacent_stage_link_rejects_a_single_stage_requirement_mapping():
    answer = _adjacent_link_answer()
    bad_unit = answer.answer_units[0].model_copy(update={"requirement_ids": ("R2",)})
    answer = answer.model_copy(update={"answer_units": (bad_unit,)})

    with pytest.raises(CoverageContractError) as captured:
        validate_evidence_coverage(
            answer,
            requirement_ids=("R1", "R2"),
            obligation_scopes=_adjacent_link_scopes(),
            source_count=2,
        )

    assert captured.value.code is CoverageValidationErrorCode.OBLIGATION_REQUIREMENT_MISMATCH


@pytest.mark.parametrize(
    ("update", "expected_code"),
    (
        (
            {"role": AnswerUnitRole.EVENT},
            CoverageValidationErrorCode.OBLIGATION_ROLE_MISMATCH,
        ),
        (
            {
                "text": "The later institution continued the earlier one [Source 1].",
                "source_numbers": (1,),
            },
            CoverageValidationErrorCode.OBLIGATION_SOURCE_MISMATCH,
        ),
    ),
)
def test_adjacent_stage_link_rejects_wrong_role_or_source(update, expected_code):
    answer = _adjacent_link_answer()
    bad_unit = answer.answer_units[0].model_copy(update=update)
    link_dimension = (
        answer.obligation_coverage[2]
        .dimensions[0]
        .model_copy(
            update={
                "source_numbers": bad_unit.source_numbers,
            }
        )
    )
    link_record = answer.obligation_coverage[2].model_copy(update={"dimensions": (link_dimension,)})
    answer = answer.model_copy(
        update={
            "answer_units": (bad_unit,),
            "obligation_coverage": (
                *answer.obligation_coverage[:2],
                link_record,
            ),
            "coverage": tuple(
                record.model_copy(update={"source_numbers": bad_unit.source_numbers})
                for record in answer.coverage
            ),
        }
    )

    with pytest.raises(CoverageContractError) as captured:
        validate_evidence_coverage(
            answer,
            requirement_ids=("R1", "R2"),
            obligation_scopes=_adjacent_link_scopes(),
            source_count=2,
        )

    assert captured.value.code is expected_code


def test_broad_obligation_role_mismatch_fails_closed():
    scope = _obligation_scope()
    unit = AnswerUnit(
        unit_id="U1",
        requirement_ids=("R1",),
        role=AnswerUnitRole.QUALIFICATION,
        text="A synthetic process connected the stages [Source 1].",
        source_numbers=(1,),
        paragraph=1,
        obligation_links=(
            ObligationLink(
                obligation_id="O1",
                dimension=EvidenceDimension.MECHANISM,
            ),
        ),
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
        ),
        obligation_coverage=(
            EvidenceObligationCoverage(
                obligation_id="O1",
                dimensions=(
                    EvidenceDimensionCoverage(
                        dimension=EvidenceDimension.MECHANISM,
                        status=RequirementStatus.SUPPORTED,
                        unit_ids=("U1",),
                        source_numbers=(1,),
                        gap_reason=GapReason.NONE,
                    ),
                ),
            ),
        ),
        answer_units=(unit,),
    )

    with pytest.raises(CoverageContractError) as captured:
        validate_evidence_coverage(
            answer,
            requirement_ids=("R1",),
            obligation_scopes=(scope,),
            source_count=1,
        )

    assert captured.value.code is CoverageValidationErrorCode.OBLIGATION_ROLE_MISMATCH


def test_each_obligation_link_must_individually_allow_every_unit_requirement():
    scopes = (
        _obligation_scope(),
        EvidenceObligationScope(
            obligation_id="O2",
            source_number=1,
            paragraph_start=2,
            paragraph_end=2,
            allowed_requirement_ids=("R2",),
            focus=EvidenceObligationFocus.MECHANISM,
            dimension_ids=(EvidenceDimension.MECHANISM,),
            required_for_requirement_status=True,
        ),
    )
    unit = AnswerUnit(
        unit_id="U1",
        requirement_ids=("R1",),
        role=AnswerUnitRole.MECHANISM,
        text="A synthetic process connected the stages [Source 1].",
        source_numbers=(1,),
        paragraph=1,
        obligation_links=(
            ObligationLink(
                obligation_id="O1",
                dimension=EvidenceDimension.MECHANISM,
            ),
            ObligationLink(
                obligation_id="O2",
                dimension=EvidenceDimension.MECHANISM,
            ),
        ),
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
            _coverage(
                "R2",
                RequirementStatus.UNSUPPORTED,
                (),
                (),
                GapReason.NO_DIRECT_SUPPORT,
            ),
        ),
        obligation_coverage=(
            *(
                EvidenceObligationCoverage(
                    obligation_id=scope.obligation_id,
                    dimensions=(
                        EvidenceDimensionCoverage(
                            dimension=EvidenceDimension.MECHANISM,
                            status=RequirementStatus.SUPPORTED,
                            unit_ids=("U1",),
                            source_numbers=(1,),
                            gap_reason=GapReason.NONE,
                        ),
                    ),
                )
                for scope in scopes
            ),
        ),
        answer_units=(unit,),
    )

    with pytest.raises(CoverageContractError) as captured:
        validate_evidence_coverage(
            answer,
            requirement_ids=("R1", "R2"),
            obligation_scopes=scopes,
            source_count=1,
        )

    assert captured.value.code is CoverageValidationErrorCode.OBLIGATION_REQUIREMENT_MISMATCH


def test_incomplete_required_obligation_dimensions_downgrade_supported_to_partial():
    scope = _obligation_scope(
        dimensions=(
            EvidenceDimension.MECHANISM,
            EvidenceDimension.CONSEQUENCE,
        )
    )
    unit = AnswerUnit(
        unit_id="U1",
        requirement_ids=("R1",),
        role=AnswerUnitRole.MECHANISM,
        text="A synthetic process connected the stages [Source 1].",
        source_numbers=(1,),
        paragraph=1,
        obligation_links=(
            ObligationLink(
                obligation_id="O1",
                dimension=EvidenceDimension.MECHANISM,
            ),
        ),
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
        ),
        obligation_coverage=(
            EvidenceObligationCoverage(
                obligation_id="O1",
                dimensions=(
                    EvidenceDimensionCoverage(
                        dimension=EvidenceDimension.MECHANISM,
                        status=RequirementStatus.SUPPORTED,
                        unit_ids=("U1",),
                        source_numbers=(1,),
                        gap_reason=GapReason.NONE,
                    ),
                    EvidenceDimensionCoverage(
                        dimension=EvidenceDimension.CONSEQUENCE,
                        status=RequirementStatus.UNSUPPORTED,
                        unit_ids=(),
                        source_numbers=(),
                        gap_reason=GapReason.NO_DIRECT_SUPPORT,
                    ),
                ),
            ),
        ),
        answer_units=(unit,),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        obligation_scopes=(scope,),
        source_count=1,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.diagnostics.coverage[0].status is RequirementStatus.PARTIAL
    assert (
        CoverageValidationErrorCode.OBLIGATION_REQUIREMENT_STATUS_MISMATCH
        in result.diagnostics.repair_codes
    )
    assert result.diagnostics.obligation_count == 1
    assert result.diagnostics.obligation_scopes == (scope,)


def test_unsupported_adjacent_link_downgrades_both_stage_requirements():
    scopes = _adjacent_link_scopes()
    units = (
        _unit("U1", ("R1",), "The first stage is supported [Source 1].", (1,)),
        _unit("U2", ("R2",), "The second stage is supported [Source 2].", (2,)),
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
            _coverage(
                "R2",
                RequirementStatus.SUPPORTED,
                ("U2",),
                (2,),
                GapReason.NONE,
            ),
        ),
        obligation_coverage=tuple(
            EvidenceObligationCoverage(
                obligation_id=scope.obligation_id,
                dimensions=tuple(
                    EvidenceDimensionCoverage(
                        dimension=dimension,
                        status=RequirementStatus.UNSUPPORTED,
                        unit_ids=(),
                        source_numbers=(),
                        gap_reason=GapReason.NO_DIRECT_SUPPORT,
                    )
                    for dimension in scope.dimension_ids
                ),
            )
            for scope in scopes
        ),
        answer_units=units,
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1", "R2"),
        obligation_scopes=scopes,
        source_count=2,
    )

    assert tuple(record.status for record in result.diagnostics.coverage) == (
        RequirementStatus.PARTIAL,
        RequirementStatus.PARTIAL,
    )


def test_broad_supplemental_unit_may_be_cited_without_synthesis_link():
    scope = _obligation_scope()
    linked = AnswerUnit(
        unit_id="U1",
        requirement_ids=("R1",),
        role=AnswerUnitRole.MECHANISM,
        text="A synthetic process connected the stages [Source 1].",
        source_numbers=(1,),
        paragraph=1,
        obligation_links=(
            ObligationLink(
                obligation_id="O1",
                dimension=EvidenceDimension.MECHANISM,
            ),
        ),
    )
    supplemental = AnswerUnit(
        unit_id="U2",
        requirement_ids=("R1",),
        role=AnswerUnitRole.CONSEQUENCE,
        text="A separate relevant result followed [Source 2].",
        source_numbers=(2,),
        paragraph=2,
        obligation_links=(),
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1", "U2"),
                (1, 2),
                GapReason.NONE,
            ),
        ),
        obligation_coverage=(
            EvidenceObligationCoverage(
                obligation_id="O1",
                dimensions=(
                    EvidenceDimensionCoverage(
                        dimension=EvidenceDimension.MECHANISM,
                        status=RequirementStatus.SUPPORTED,
                        unit_ids=("U1",),
                        source_numbers=(1,),
                        gap_reason=GapReason.NONE,
                    ),
                ),
            ),
        ),
        answer_units=(linked, supplemental),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        obligation_scopes=(scope,),
        source_count=2,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.diagnostics.validation_result is DiagnosticValidationResult.VALID
    assert result.diagnostics.answer_unit_count == 2


def test_missing_unresolvable_and_mismatched_citations_are_distinct_errors():
    answer = _valid_answer()

    missing = answer.answer_units[0].model_copy(update={"text": "No citation here."})
    _assert_error(
        answer.model_copy(update={"answer_units": (missing, answer.answer_units[1])}),
        CoverageValidationErrorCode.MISSING_CITATION,
    )

    unresolvable = answer.answer_units[0].model_copy(
        update={"text": "Outside the supplied list [Source 4]."}
    )
    _assert_error(
        answer.model_copy(update={"answer_units": (unresolvable, answer.answer_units[1])}),
        CoverageValidationErrorCode.UNRESOLVABLE_CITATION,
    )

    mismatch = answer.answer_units[0].model_copy(
        update={"text": "The declaration differs [Source 2]."}
    )
    _assert_error(
        answer.model_copy(update={"answer_units": (mismatch, answer.answer_units[1])}),
        CoverageValidationErrorCode.CITATION_SOURCE_MISMATCH,
    )


def test_declared_source_numbers_must_be_unique_and_resolvable():
    answer = _valid_answer()
    duplicate = answer.answer_units[0].model_copy(update={"source_numbers": (1, 1)})
    _assert_error(
        answer.model_copy(update={"answer_units": (duplicate, answer.answer_units[1])}),
        CoverageValidationErrorCode.DUPLICATE_SOURCE_NUMBER,
    )

    out_of_range = answer.answer_units[0].model_copy(
        update={
            "text": "The declared source is outside the list [Source 4].",
            "source_numbers": (4,),
        }
    )
    _assert_error(
        answer.model_copy(update={"answer_units": (out_of_range, answer.answer_units[1])}),
        CoverageValidationErrorCode.SOURCE_NUMBER_OUT_OF_RANGE,
    )


def test_coverage_unit_and_source_mappings_must_equal_the_units():
    answer = _valid_answer()
    missing_unit = answer.coverage[0].model_copy(update={"unit_ids": ()})
    _assert_error(
        answer.model_copy(update={"coverage": (missing_unit, answer.coverage[1])}),
        CoverageValidationErrorCode.STATUS_UNIT_MISMATCH,
    )

    wrong_source = answer.coverage[0].model_copy(update={"source_numbers": (2,)})
    _assert_error(
        answer.model_copy(update={"coverage": (wrong_source, answer.coverage[1])}),
        CoverageValidationErrorCode.SOURCE_MAPPING_MISMATCH,
    )


def test_unsupported_requirements_cannot_have_factual_units():
    answer = _valid_answer()
    unsupported = answer.coverage[0].model_copy(
        update={
            "status": RequirementStatus.UNSUPPORTED,
            "gap_reason": GapReason.NO_DIRECT_SUPPORT,
        }
    )
    _assert_error(
        answer.model_copy(update={"coverage": (unsupported, answer.coverage[1])}),
        CoverageValidationErrorCode.UNSUPPORTED_REQUIREMENT_HAS_UNIT,
    )


def test_status_and_gap_reason_are_a_closed_mapping():
    answer = _valid_answer()
    wrong_gap = answer.coverage[1].model_copy(update={"gap_reason": GapReason.NONE})
    _assert_error(
        answer.model_copy(update={"coverage": (answer.coverage[0], wrong_gap)}),
        CoverageValidationErrorCode.STATUS_GAP_MISMATCH,
    )


def test_conflicting_coverage_requires_at_least_two_sources_and_cites_both():
    unit = _unit(
        "U1",
        ("R1",),
        "The synthetic sources disagree [Source 1, Source 2].",
        (1, 2),
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.CONFLICTING,
                ("U1",),
                (1, 2),
                GapReason.SOURCE_CONFLICT,
            ),
        ),
        answer_units=(unit,),
    )
    validated = validate_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        source_count=2,
    )
    rendered = render_evidence_coverage(
        validated,
        requirement_labels={"R1": "which account applies"},
    )
    assert rendered.count(unit.text) == 1
    assert rendered.endswith("The retrieved passages conflict on part of the requested answer.")

    one_source_unit = unit.model_copy(
        update={
            "text": "Only one source is declared [Source 1].",
            "source_numbers": (1,),
        }
    )
    one_source_record = answer.coverage[0].model_copy(update={"source_numbers": (1,)})
    _assert_error(
        answer.model_copy(
            update={
                "coverage": (one_source_record,),
                "answer_units": (one_source_unit,),
            }
        ),
        CoverageValidationErrorCode.CONFLICT_REQUIRES_MULTIPLE_SOURCES,
        requirement_ids=("R1",),
        premise_ids=(),
        source_count=2,
    )


def test_renderer_orders_paragraphs_and_realizes_each_unit_once_before_gaps():
    answer = _valid_answer()
    validated = _validate(answer)
    rendered = render_evidence_coverage(
        validated,
        requirement_labels={"R2": "the unresolved synthetic relationship"},
    )

    assert rendered.index("synthetic later point") < rendered.index("synthetic first point")
    assert rendered.count(answer.answer_units[0].text) == 1
    assert rendered.count(answer.answer_units[1].text) == 1
    assert rendered.endswith("The retrieved passages establish only part of the requested answer.")


def test_gap_labels_cannot_inject_an_unvalidated_citation():
    rendered = render_evidence_coverage(
        _validate(_valid_answer()),
        requirement_labels={"R2": "a label [Source 99]\nwith a line break"},
    )

    assert "Source 99" not in rendered
    assert "\nwith a line break" not in rendered


def _two_stage_completeness_context() -> ContentCompletenessContext:
    return ContentCompletenessContext(
        profile=ContentCompletenessProfile.BROAD_SYNTHESIS,
        required_requirement_ids=("R1", "R2"),
        expected_stage_requirement_ids=("R1", "R2"),
        expected_stage_transitions=(
            ExpectedStageTransition(
                predecessor_requirement_id="R1",
                successor_requirement_id="R2",
            ),
        ),
        minimum_supported_obligation_ratio=1.0,
        require_institutional_handoffs=False,
    )


@pytest.mark.parametrize(
    ("expected_stages", "transitions"),
    (
        (
            ("R2", "R1", "R3"),
            (
                ExpectedStageTransition(
                    predecessor_requirement_id="R2",
                    successor_requirement_id="R1",
                ),
                ExpectedStageTransition(
                    predecessor_requirement_id="R1",
                    successor_requirement_id="R3",
                ),
            ),
        ),
        (("R1", "R2", "R3"), ()),
        (
            ("R1", "R2", "R3"),
            (
                ExpectedStageTransition(
                    predecessor_requirement_id="R1",
                    successor_requirement_id="R3",
                ),
                ExpectedStageTransition(
                    predecessor_requirement_id="R3",
                    successor_requirement_id="R2",
                ),
            ),
        ),
    ),
)
def test_broad_completeness_requires_the_exact_ordered_stage_chain(
    expected_stages,
    transitions,
):
    with pytest.raises(ValidationError):
        ContentCompletenessContext(
            profile=ContentCompletenessProfile.BROAD_SYNTHESIS,
            required_requirement_ids=("R1", "R2", "R3"),
            expected_stage_requirement_ids=expected_stages,
            expected_stage_transitions=transitions,
            minimum_supported_obligation_ratio=1.0,
            require_institutional_handoffs=False,
        )


def _two_stage_supported_answer(
    *,
    include_transition: bool,
) -> tuple[EvidenceCoverageAnswer, tuple[EvidenceObligationScope, ...]]:
    stage_scopes = (
        EvidenceObligationScope(
            obligation_id="O1",
            source_number=1,
            paragraph_start=1,
            paragraph_end=1,
            allowed_requirement_ids=("R1",),
            focus=EvidenceObligationFocus.ORIGIN,
            dimension_ids=(EvidenceDimension.STAGE_DEVELOPMENT,),
            required_for_requirement_status=True,
        ),
        EvidenceObligationScope(
            obligation_id="O2",
            source_number=2,
            paragraph_start=1,
            paragraph_end=1,
            allowed_requirement_ids=("R2",),
            focus=EvidenceObligationFocus.ENDPOINT,
            dimension_ids=(EvidenceDimension.STAGE_DEVELOPMENT,),
            required_for_requirement_status=True,
        ),
    )
    transition_scope = EvidenceObligationScope(
        obligation_id="O3",
        kind=EvidenceObligationKind.ADJACENT_STAGE_LINK,
        source_number=2,
        predecessor_source_number=1,
        paragraph_start=1,
        paragraph_end=1,
        allowed_requirement_ids=("R1", "R2"),
        focus=EvidenceObligationFocus.TRANSITION,
        dimension_ids=(EvidenceDimension.ADJACENT_STAGE_LINK,),
        required_for_requirement_status=True,
    )
    scopes = (*stage_scopes, *((transition_scope,) if include_transition else ()))
    units = (
        AnswerUnit(
            unit_id="U1",
            requirement_ids=("R1",),
            role=AnswerUnitRole.EVENT,
            text="The synthetic origin established the first stage [Source 1].",
            source_numbers=(1,),
            paragraph=1,
            obligation_links=(
                ObligationLink(
                    obligation_id="O1",
                    dimension=EvidenceDimension.STAGE_DEVELOPMENT,
                ),
            ),
        ),
        AnswerUnit(
            unit_id="U2",
            requirement_ids=("R2",),
            role=AnswerUnitRole.EVENT,
            text="The synthetic endpoint established the second stage [Source 2].",
            source_numbers=(2,),
            paragraph=2,
            obligation_links=(
                ObligationLink(
                    obligation_id="O2",
                    dimension=EvidenceDimension.STAGE_DEVELOPMENT,
                ),
            ),
        ),
        *(
            (
                AnswerUnit(
                    unit_id="U3",
                    requirement_ids=("R1", "R2"),
                    role=AnswerUnitRole.CAUSE,
                    text="The second stage inherited capacity from the first [Source 2].",
                    source_numbers=(2,),
                    paragraph=2,
                    obligation_links=(
                        ObligationLink(
                            obligation_id="O3",
                            dimension=EvidenceDimension.ADJACENT_STAGE_LINK,
                        ),
                    ),
                ),
            )
            if include_transition
            else ()
        ),
    )
    coverage = (
        _coverage(
            "R1",
            RequirementStatus.SUPPORTED,
            ("U1", "U3") if include_transition else ("U1",),
            (1, 2) if include_transition else (1,),
            GapReason.NONE,
        ),
        _coverage(
            "R2",
            RequirementStatus.SUPPORTED,
            ("U2", "U3") if include_transition else ("U2",),
            (2,),
            GapReason.NONE,
        ),
    )
    obligation_coverage = tuple(
        EvidenceObligationCoverage(
            obligation_id=scope.obligation_id,
            dimensions=tuple(
                EvidenceDimensionCoverage(
                    dimension=dimension,
                    status=RequirementStatus.SUPPORTED,
                    unit_ids=(
                        ("U1",)
                        if scope.obligation_id == "O1"
                        else ("U2",)
                        if scope.obligation_id == "O2"
                        else ("U3",)
                    ),
                    source_numbers=(scope.source_number,),
                    gap_reason=GapReason.NONE,
                )
                for dimension in scope.dimension_ids
            ),
        )
        for scope in scopes
    )
    return (
        EvidenceCoverageAnswer(
            schema=EVIDENCE_COVERAGE_SCHEMA,
            premise_decisions=(),
            coverage=coverage,
            obligation_coverage=obligation_coverage,
            answer_units=units,
        ),
        scopes,
    )


def test_content_outcome_keeps_structural_validity_separate_from_completeness():
    answer, scopes = _two_stage_supported_answer(include_transition=False)

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1", "R2"),
        obligation_scopes=scopes,
        source_count=2,
        completeness_context=_two_stage_completeness_context(),
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.diagnostics.validation_result is DiagnosticValidationResult.VALID
    assert result.diagnostics.content_outcome is ContentOutcome.VALID_PARTIAL
    assert result.diagnostics.expected_stage_count == 2
    assert result.diagnostics.realized_stage_count == 2
    assert result.diagnostics.expected_transition_count == 1
    assert result.diagnostics.realized_transition_count == 0
    assert result.answer.count("establish only part") == 1
    assert "required stages or connections" in result.answer


def test_broad_content_is_complete_only_when_every_expected_link_is_realized():
    answer, scopes = _two_stage_supported_answer(include_transition=True)

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1", "R2"),
        obligation_scopes=scopes,
        source_count=2,
        completeness_context=_two_stage_completeness_context(),
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.diagnostics.content_outcome is ContentOutcome.VALID_COMPLETE
    assert result.diagnostics.required_obligation_dimension_count == 3
    assert result.diagnostics.supported_required_obligation_dimension_count == 3
    assert result.diagnostics.realized_transition_count == 1
    assert "establish only part" not in result.answer


def test_broad_content_reports_a_missing_stage_even_when_the_link_is_supported():
    answer, scopes = _two_stage_supported_answer(include_transition=True)
    without_stage_two = answer.model_copy(
        update={
            "answer_units": tuple(
                unit.model_copy(update={"obligation_links": ()}) if unit.unit_id == "U2" else unit
                for unit in answer.answer_units
            ),
            "obligation_coverage": tuple(
                record.model_copy(
                    update={
                        "dimensions": tuple(
                            dimension.model_copy(
                                update={
                                    "status": RequirementStatus.UNSUPPORTED,
                                    "unit_ids": (),
                                    "source_numbers": (),
                                    "gap_reason": GapReason.NO_DIRECT_SUPPORT,
                                }
                            )
                            for dimension in record.dimensions
                        )
                    }
                )
                if record.obligation_id == "O2"
                else record
                for record in answer.obligation_coverage
            ),
        }
    )

    result = process_evidence_coverage(
        without_stage_two,
        requirement_ids=("R1", "R2"),
        obligation_scopes=scopes,
        source_count=2,
        completeness_context=_two_stage_completeness_context(),
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED, result.diagnostics.error_code
    assert result.diagnostics.content_outcome is ContentOutcome.VALID_PARTIAL
    assert result.diagnostics.realized_stage_count == 1
    assert result.diagnostics.realized_transition_count == 1
    assert result.answer.count("establish only part") == 1


def test_lineage_stages_require_supported_institutional_handoffs():
    answer, scopes = _two_stage_supported_answer(include_transition=True)
    lineage_context = _two_stage_completeness_context().model_copy(
        update={
            "profile": ContentCompletenessProfile.LONG_INSTITUTIONAL_LINEAGE,
            "require_institutional_handoffs": True,
        }
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1", "R2"),
        obligation_scopes=scopes,
        source_count=2,
        completeness_context=lineage_context,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.diagnostics.content_outcome is ContentOutcome.VALID_PARTIAL
    assert result.diagnostics.realized_stage_count == 0
    assert result.diagnostics.realized_transition_count == 1
    assert "required stages or handoffs" in result.answer


def test_all_unsupported_and_no_sources_have_deterministic_messages():
    unsupported_answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.UNSUPPORTED,
                (),
                (),
                GapReason.NO_DIRECT_SUPPORT,
            ),
        ),
        answer_units=(),
    )
    result = process_evidence_coverage(
        unsupported_answer,
        requirement_ids=("R1",),
        source_count=2,
    )
    assert result.status is CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE
    assert result.answer == ALL_UNSUPPORTED_MESSAGE
    assert result.diagnostics.content_outcome is ContentOutcome.INSUFFICIENT_EVIDENCE

    no_sources = process_evidence_coverage(
        {"unvalidated": "prose that must never be shown"},
        requirement_ids=("R1",),
        source_count=0,
    )
    assert no_sources.status is CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE
    assert no_sources.answer == NO_SOURCES_MESSAGE
    assert no_sources.diagnostics.validation_result is DiagnosticValidationResult.NOT_RUN
    assert no_sources.diagnostics.content_outcome is ContentOutcome.INSUFFICIENT_EVIDENCE


def test_refusal_and_invalid_payload_fail_closed_with_stable_codes():
    refusal = process_evidence_coverage(
        None,
        requirement_ids=("R1",),
        source_count=1,
        refused=True,
    )
    assert refusal.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert refusal.error_code == "generation_contract_failed"
    assert refusal.answer == GENERATION_CONTRACT_FAILED_MESSAGE
    assert refusal.diagnostics.error_code is CoverageValidationErrorCode.GENERATION_REFUSED

    invalid = process_evidence_coverage(
        {"schema": EVIDENCE_COVERAGE_SCHEMA, "raw_answer": "never display this"},
        requirement_ids=("R1",),
        source_count=1,
    )
    assert invalid.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert invalid.answer == GENERATION_CONTRACT_FAILED_MESSAGE
    assert "never display this" not in invalid.model_dump_json()
    assert invalid.diagnostics.error_code is CoverageValidationErrorCode.INVALID_PAYLOAD


def test_process_normalizes_only_order_and_redundant_derived_mappings():
    factual_text = "One synthetic unit answers both requests [Source 2, Source 1]."
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(
            PremiseDecision(
                premise_id="P2",
                status=PremiseStatus.SUPPORTED,
                source_numbers=(2,),
            ),
            PremiseDecision(
                premise_id="P1",
                status=PremiseStatus.SUPPORTED,
                source_numbers=(1,),
            ),
        ),
        coverage=(
            _coverage(
                "R2",
                RequirementStatus.SUPPORTED,
                (),
                (),
                GapReason.NONE,
            ),
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
        ),
        answer_units=(
            _unit(
                "U1",
                ("R2", "R1"),
                factual_text,
                (1, 2),
            ),
        ),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1", "R2"),
        premise_ids=("P1", "P2"),
        premise_source_scopes=_premise_scopes(("P1", "P2"), 2),
        source_count=2,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.diagnostics.content_outcome is ContentOutcome.VALID_COMPLETE
    assert result.answer == factual_text
    assert result.diagnostics.repair_applied is True
    assert result.diagnostics.repair_codes == (
        CoverageValidationErrorCode.OUT_OF_ORDER_UNIT_REQUIREMENT_ID,
        CoverageValidationErrorCode.CITATION_SOURCE_MISMATCH,
        CoverageValidationErrorCode.OUT_OF_ORDER_REQUIREMENT_ID,
        CoverageValidationErrorCode.SOURCE_MAPPING_MISMATCH,
        CoverageValidationErrorCode.STATUS_UNIT_MISMATCH,
        CoverageValidationErrorCode.OUT_OF_ORDER_PREMISE_ID,
    )
    assert tuple(record.requirement_id for record in result.diagnostics.coverage) == ("R1", "R2")
    assert all(
        record.unit_ids == ("U1",) and record.source_numbers == (2, 1)
        for record in result.diagnostics.coverage
    )
    assert result.diagnostics.answer_units[0].requirement_ids == ("R1", "R2")
    assert result.diagnostics.answer_units[0].source_numbers == (2, 1)
    assert tuple(decision.premise_id for decision in result.diagnostics.premise_decisions) == (
        "P1",
        "P2",
    )


def test_process_normalizes_gap_reason_from_unchanged_partial_status():
    unit = _unit(
        "U1",
        ("R1",),
        "The bounded synthetic material supports part of the request [Source 1].",
        (1,),
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.PARTIAL,
                ("U1",),
                (1,),
                GapReason.NO_DIRECT_SUPPORT,
            ),
        ),
        answer_units=(unit,),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        source_count=1,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert unit.text in result.answer
    assert result.diagnostics.repair_codes == (CoverageValidationErrorCode.STATUS_GAP_MISMATCH,)
    assert result.diagnostics.coverage[0].status is RequirementStatus.PARTIAL
    assert result.diagnostics.coverage[0].gap_reason is GapReason.PARTIAL_SUPPORT
    assert result.diagnostics.coverage[0].unit_ids == ("U1",)
    assert result.diagnostics.coverage[0].source_numbers == (1,)


def test_empty_ungrounded_requirement_mapping_downgrades_to_unsupported():
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.PARTIAL,
                (),
                (),
                GapReason.NO_DIRECT_SUPPORT,
            ),
        ),
        answer_units=(),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        source_count=1,
    )

    assert result.status is CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE
    assert result.answer == ALL_UNSUPPORTED_MESSAGE
    assert result.diagnostics.validation_result is DiagnosticValidationResult.VALID
    assert result.diagnostics.repair_codes == (CoverageValidationErrorCode.STATUS_UNIT_MISMATCH,)
    record = result.diagnostics.coverage[0]
    assert record.status is RequirementStatus.UNSUPPORTED
    assert record.gap_reason is GapReason.NO_DIRECT_SUPPORT
    assert record.unit_ids == ()
    assert record.source_numbers == ()


def test_empty_ungrounded_obligation_mapping_downgrades_without_inventing_support():
    scope = _obligation_scope()
    unit = _unit(
        "U1",
        ("R1",),
        "A separate grounded unit remains available [Source 1].",
        (1,),
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
        ),
        obligation_coverage=(
            EvidenceObligationCoverage(
                obligation_id="O1",
                dimensions=(
                    EvidenceDimensionCoverage(
                        dimension=EvidenceDimension.MECHANISM,
                        status=RequirementStatus.PARTIAL,
                        unit_ids=(),
                        source_numbers=(),
                        gap_reason=GapReason.PARTIAL_SUPPORT,
                    ),
                ),
            ),
        ),
        answer_units=(unit,),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        obligation_scopes=(scope,),
        source_count=1,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    dimension = result.diagnostics.obligation_coverage[0].dimensions[0]
    assert dimension.status is RequirementStatus.UNSUPPORTED
    assert dimension.gap_reason is GapReason.NO_DIRECT_SUPPORT
    assert dimension.unit_ids == ()
    assert dimension.source_numbers == ()
    assert result.diagnostics.coverage[0].status is RequirementStatus.PARTIAL
    assert CoverageValidationErrorCode.STATUS_UNIT_MISMATCH in (result.diagnostics.repair_codes)


def test_nonempty_invalid_mapping_still_fails_closed():
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.PARTIAL,
                ("UX",),
                (1,),
                GapReason.PARTIAL_SUPPORT,
            ),
        ),
        answer_units=(),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        source_count=1,
    )

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.diagnostics.error_code is CoverageValidationErrorCode.UNKNOWN_UNIT_ID
    assert result.diagnostics.repair_codes == ()


def test_gap_normalization_never_admits_an_unsupported_factual_unit():
    unit = _unit(
        "U1",
        ("R1",),
        "A factual unit remains forbidden for unsupported coverage [Source 1].",
        (1,),
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.UNSUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
        ),
        answer_units=(unit,),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        source_count=1,
    )

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert (
        result.diagnostics.error_code
        is CoverageValidationErrorCode.UNSUPPORTED_REQUIREMENT_HAS_UNIT
    )
    assert result.diagnostics.repair_codes == (CoverageValidationErrorCode.STATUS_GAP_MISMATCH,)
    assert unit.text not in result.answer


def test_process_derives_contradicted_premise_sources_from_its_correction_unit():
    correction = _unit(
        "U1",
        (),
        "The synthetic premise began earlier [Source 1].",
        (1,),
        role=AnswerUnitRole.PREMISE_CORRECTION,
    )
    substantive = _unit(
        "U2",
        ("R1",),
        "The supported answer remains separate [Source 2].",
        (2,),
        paragraph=2,
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(
            PremiseDecision(
                premise_id="P1",
                status=PremiseStatus.CONTRADICTED,
                source_numbers=(1, 2),
                correction_unit_id="U1",
            ),
        ),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U2",),
                (2,),
                GapReason.NONE,
            ),
        ),
        answer_units=(correction, substantive),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 2),
        source_count=2,
    )

    assert result.status is CoverageOutcomeStatus.ANSWERED
    assert result.answer == f"{correction.text}\n\n{substantive.text}"
    assert result.diagnostics.repair_codes == (CoverageValidationErrorCode.PREMISE_SOURCE_MISMATCH,)
    assert result.diagnostics.premise_decisions[0].source_numbers == (1,)
    assert result.diagnostics.coverage[0].source_numbers == (2,)


@pytest.mark.parametrize(
    ("decision_update", "unit_update", "error_code"),
    [
        (
            {"source_numbers": ()},
            {},
            CoverageValidationErrorCode.PREMISE_SOURCE_MISMATCH,
        ),
        (
            {"source_numbers": (2,)},
            {},
            CoverageValidationErrorCode.PREMISE_CORRECTION_INVALID,
        ),
        (
            {"source_numbers": (1, 1)},
            {},
            CoverageValidationErrorCode.DUPLICATE_SOURCE_NUMBER,
        ),
        (
            {"source_numbers": (3,)},
            {},
            CoverageValidationErrorCode.SOURCE_NUMBER_OUT_OF_RANGE,
        ),
        (
            {},
            {
                "role": AnswerUnitRole.EVENT,
                "requirement_ids": ("R1",),
            },
            CoverageValidationErrorCode.PREMISE_CORRECTION_INVALID,
        ),
    ],
)
def test_premise_source_normalization_never_repairs_malformed_or_semantic_fields(
    decision_update,
    unit_update,
    error_code,
):
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(
            PremiseDecision(
                premise_id="P1",
                status=PremiseStatus.CONTRADICTED,
                source_numbers=(2,),
                correction_unit_id="U1",
            ).model_copy(update=decision_update),
        ),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U2",),
                (2,),
                GapReason.NONE,
            ),
        ),
        answer_units=(
            _unit(
                "U1",
                (),
                "The synthetic premise began earlier [Source 1].",
                (1,),
                role=AnswerUnitRole.PREMISE_CORRECTION,
            ).model_copy(update=unit_update),
            _unit(
                "U2",
                ("R1",),
                "The supported answer remains separate [Source 2].",
                (2,),
                paragraph=2,
            ),
        ),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 2),
        source_count=2,
    )

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.diagnostics.error_code is error_code
    assert (
        CoverageValidationErrorCode.PREMISE_SOURCE_MISMATCH not in result.diagnostics.repair_codes
    )


def test_premise_decision_sources_must_equal_its_correction_sources():
    correction = _unit(
        "U1",
        (),
        "The synthetic premise began earlier [Source 1, Source 2].",
        (1, 2),
        role=AnswerUnitRole.PREMISE_CORRECTION,
    )
    substantive = _unit(
        "U2",
        ("R1",),
        "The supported answer remains separate [Source 2].",
        (2,),
        paragraph=2,
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(
            PremiseDecision(
                premise_id="P1",
                status=PremiseStatus.CONTRADICTED,
                source_numbers=(1,),
                correction_unit_id="U1",
            ),
        ),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U2",),
                (2,),
                GapReason.NONE,
            ),
        ),
        answer_units=(correction, substantive),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 2),
        source_count=2,
    )

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.diagnostics.error_code is CoverageValidationErrorCode.PREMISE_CORRECTION_INVALID


@pytest.mark.parametrize(
    ("unit", "error_code"),
    [
        (
            _unit(
                "U1",
                ("R1",),
                "A correction cannot double as requirement evidence [Source 1].",
                (1,),
                role=AnswerUnitRole.PREMISE_CORRECTION,
            ),
            CoverageValidationErrorCode.PREMISE_CORRECTION_REQUIREMENT_MISMATCH,
        ),
        (
            _unit(
                "U1",
                (),
                "An ordinary answer unit must map to a requirement [Source 1].",
                (1,),
            ),
            CoverageValidationErrorCode.MISSING_UNIT_REQUIREMENT_ID,
        ),
    ],
)
def test_answer_unit_roles_enforce_separate_correction_and_requirement_evidence(
    unit,
    error_code,
):
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U1",),
                (1,),
                GapReason.NONE,
            ),
        ),
        answer_units=(unit,),
    )

    _assert_error(
        answer,
        error_code,
        requirement_ids=("R1",),
        premise_ids=(),
        source_count=1,
    )


def test_contradicted_premise_requires_a_retained_framing_source():
    correction = _unit(
        "U1",
        (),
        "The proposed origin is too late [Source 2].",
        (2,),
        role=AnswerUnitRole.PREMISE_CORRECTION,
    )
    substantive = _unit(
        "U2",
        ("R1",),
        "The later development is supported separately [Source 1].",
        (1,),
        paragraph=2,
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(
            PremiseDecision(
                premise_id="P1",
                status=PremiseStatus.CONTRADICTED,
                source_numbers=(2,),
                correction_unit_id="U1",
            ),
        ),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U2",),
                (1,),
                GapReason.NONE,
            ),
        ),
        answer_units=(correction, substantive),
    )
    scopes = (
        PremiseSourceScope(
            premise_id="P1",
            support_source_numbers=(1,),
            counter_source_numbers=(2,),
            framing_source_numbers=(3,),
        ),
    )

    with pytest.raises(CoverageContractError) as captured:
        validate_evidence_coverage(
            answer,
            requirement_ids=("R1",),
            premise_ids=("P1",),
            premise_source_scopes=scopes,
            source_count=3,
        )

    assert captured.value.code is CoverageValidationErrorCode.PREMISE_PROVENANCE_MISMATCH


def test_contradicted_premise_accepts_framing_plus_counter_provenance():
    correction = _unit(
        "U1",
        (),
        "The proposed origin is too late and the manuscript begins earlier [Source 2, Source 3].",
        (2, 3),
        role=AnswerUnitRole.PREMISE_CORRECTION,
    )
    substantive = _unit(
        "U2",
        ("R1",),
        "The later development is supported separately [Source 1].",
        (1,),
        paragraph=2,
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(
            PremiseDecision(
                premise_id="P1",
                status=PremiseStatus.CONTRADICTED,
                source_numbers=(2, 3),
                correction_unit_id="U1",
            ),
        ),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                ("U2",),
                (1,),
                GapReason.NONE,
            ),
        ),
        answer_units=(correction, substantive),
    )
    scopes = (
        PremiseSourceScope(
            premise_id="P1",
            support_source_numbers=(1,),
            counter_source_numbers=(2,),
            framing_source_numbers=(3,),
        ),
    )

    validated = validate_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        premise_ids=("P1",),
        premise_source_scopes=scopes,
        source_count=3,
    )

    assert validated.answer == answer


def test_supported_premise_must_use_its_support_lane():
    answer = _valid_answer().model_copy(
        update={
            "premise_decisions": (
                PremiseDecision(
                    premise_id="P1",
                    status=PremiseStatus.SUPPORTED,
                    source_numbers=(2,),
                ),
            )
        }
    )
    scopes = (
        PremiseSourceScope(
            premise_id="P1",
            support_source_numbers=(1,),
            counter_source_numbers=(2,),
            framing_source_numbers=(3,),
        ),
    )

    with pytest.raises(CoverageContractError) as captured:
        validate_evidence_coverage(
            answer,
            requirement_ids=("R1", "R2"),
            premise_ids=("P1",),
            premise_source_scopes=scopes,
            source_count=3,
        )

    assert captured.value.code is CoverageValidationErrorCode.PREMISE_PROVENANCE_MISMATCH


def test_missing_premise_source_scope_fails_closed_as_invalid_context():
    result = process_evidence_coverage(
        _valid_answer(),
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=(),
        source_count=3,
    )

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.diagnostics.error_code is CoverageValidationErrorCode.INVALID_CONTEXT
    assert result.diagnostics.premise_source_scopes == ()


def test_obligation_dimensions_cannot_exceed_answer_unit_capacity():
    scopes = tuple(
        EvidenceObligationScope(
            obligation_id=f"O{index}",
            source_number=1,
            paragraph_start=index,
            paragraph_end=index,
            allowed_requirement_ids=("R1",),
            focus=EvidenceObligationFocus.MECHANISM,
            dimension_ids=(
                EvidenceDimension.CAUSE_OR_ENABLER,
                EvidenceDimension.MECHANISM,
            ),
            required_for_requirement_status=True,
        )
        for index in range(1, 18)
    )

    result = process_evidence_coverage(
        None,
        requirement_ids=("R1",),
        obligation_scopes=scopes,
        source_count=1,
        refused=True,
    )

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert (
        result.diagnostics.error_code
        is CoverageValidationErrorCode.OBLIGATION_DIMENSION_CAPACITY_EXCEEDED
    )


def test_process_never_repairs_an_unsupported_requirement_with_a_factual_unit():
    unit = _unit(
        "U1",
        ("R1",),
        "A factual unit remains forbidden for unsupported coverage [Source 1].",
        (1,),
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.UNSUPPORTED,
                (),
                (),
                GapReason.NO_DIRECT_SUPPORT,
            ),
        ),
        answer_units=(unit,),
    )

    result = process_evidence_coverage(
        answer,
        requirement_ids=("R1",),
        source_count=1,
    )

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert (
        result.diagnostics.error_code
        is CoverageValidationErrorCode.UNSUPPORTED_REQUIREMENT_HAS_UNIT
    )
    assert result.diagnostics.repair_applied is False
    assert result.diagnostics.repair_codes == ()
    assert unit.text not in result.answer


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda answer: answer.model_copy(
                update={
                    "answer_units": (
                        answer.answer_units[0].model_copy(
                            update={
                                "text": "The citation set changed [Source 2].",
                            }
                        ),
                        answer.answer_units[1],
                    )
                }
            ),
            CoverageValidationErrorCode.CITATION_SOURCE_MISMATCH,
        ),
        (
            lambda answer: answer.model_copy(
                update={
                    "coverage": (
                        answer.coverage[0].model_copy(update={"unit_ids": ("UX",)}),
                        answer.coverage[1],
                    )
                }
            ),
            CoverageValidationErrorCode.UNKNOWN_UNIT_ID,
        ),
        (
            lambda answer: answer.model_copy(
                update={
                    "answer_units": (
                        answer.answer_units[0].model_copy(
                            update={"text": "Malformed [Sources 1]."}
                        ),
                        answer.answer_units[1],
                    )
                }
            ),
            CoverageValidationErrorCode.MALFORMED_CITATION,
        ),
    ],
)
def test_process_retains_precise_nonrepairable_error_codes_in_diagnostics(
    mutate,
    code,
):
    result = process_evidence_coverage(
        mutate(_valid_answer()),
        requirement_ids=("R1", "R2"),
        premise_ids=("P1",),
        premise_source_scopes=_premise_scopes(("P1",), 3),
        source_count=3,
    )

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.diagnostics.error_code is code


def test_total_unit_text_is_bounded_even_when_individual_units_fit():
    units = tuple(
        _unit(
            f"U{index}",
            ("R1",),
            ("x" * 1_780) + " [Source 1]",
            (1,),
        )
        for index in range(1, 8)
    )
    answer = EvidenceCoverageAnswer(
        schema=EVIDENCE_COVERAGE_SCHEMA,
        premise_decisions=(),
        coverage=(
            _coverage(
                "R1",
                RequirementStatus.SUPPORTED,
                tuple(unit.unit_id for unit in units),
                (1,),
                GapReason.NONE,
            ),
        ),
        answer_units=units,
    )
    _assert_error(
        answer,
        CoverageValidationErrorCode.TEXT_LIMIT_EXCEEDED,
        requirement_ids=("R1",),
        premise_ids=(),
        source_count=1,
    )


def _all_mapping_keys(value: object) -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _all_mapping_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_mapping_keys(nested)


def test_diagnostic_summary_is_text_free_but_keeps_safe_mappings_and_counts():
    answer = _valid_answer()
    summary = coverage_diagnostic_summary(_validate(answer))
    dumped = summary.model_dump(mode="json")
    serialized = json.dumps(dumped, sort_keys=True)

    assert answer.answer_units[0].text not in serialized
    assert answer.answer_units[1].text not in serialized
    assert "the unresolved synthetic relationship" not in serialized
    assert "text" not in set(_all_mapping_keys(dumped))
    assert summary.answer_unit_count == 2
    assert summary.citation_count == 3
    assert summary.coverage_status_counts.supported == 1
    assert summary.coverage_status_counts.partial == 1
    assert summary.answer_units[0].unit_id == "U1"
    assert summary.answer_units[0].source_numbers == (1,)
