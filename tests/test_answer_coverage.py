from __future__ import annotations

import json
from collections.abc import Iterable

import pytest
from pydantic import ValidationError

from answer_coverage import (
    ALL_UNSUPPORTED_MESSAGE,
    CITATION_GRAMMAR,
    EVIDENCE_COVERAGE_SCHEMA,
    GENERATION_CONTRACT_FAILED_MESSAGE,
    INTERPRETIVE_EVIDENCE_COVERAGE_SCHEMA,
    NO_SOURCES_MESSAGE,
    AnswerUnit,
    AnswerUnitRole,
    CitationLocalityFailureCode,
    CoverageContractError,
    CoverageOutcomeStatus,
    CoverageValidationErrorCode,
    DiagnosticValidationResult,
    EvidenceDimension,
    EvidenceDimensionCoverage,
    EvidenceCoverageAnswer,
    EvidenceObligationCoverage,
    EvidenceObligationFocus,
    EvidenceObligationScope,
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
    parse_citation_numbers,
    process_evidence_coverage,
    process_interpretive_evidence_coverage,
    render_evidence_coverage,
    validate_evidence_coverage,
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
    assert paragraphs[-1] == (
        "Project Lumen therefore stands as a meaningful accomplishment."
    )
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
        result.diagnostics.error_code
        is CoverageValidationErrorCode.MISSING_INTERPRETIVE_PARAGRAPH
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
        cited.diagnostics.error_code
        is CoverageValidationErrorCode.INTERPRETIVE_CITATION_FORBIDDEN
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
        generic.diagnostics.error_code
        is CoverageValidationErrorCode.INTERPRETIVE_SUBJECT_MISSING
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
    text_schema = EvidenceCoverageAnswer.model_json_schema()["$defs"]["AnswerUnit"][
        "properties"
    ]["text"]
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

    assert (
        captured.value.code
        is CoverageValidationErrorCode.OBLIGATION_REQUIREMENT_MISMATCH
    )


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
    assert rendered.endswith(
        "The retrieved sources conflict about this requested point "
        "(which account applies) [Source 1, Source 2]."
    )

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
    assert rendered.endswith(
        "The retrieved passages only partially establish this requested point "
        "(the unresolved synthetic relationship)."
    )


def test_gap_labels_cannot_inject_an_unvalidated_citation():
    rendered = render_evidence_coverage(
        _validate(_valid_answer()),
        requirement_labels={"R2": "a label [Source 99]\nwith a line break"},
    )

    assert "[Source 99]" not in rendered
    assert "(Source 99)" in rendered
    assert "\nwith a line break" not in rendered


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

    no_sources = process_evidence_coverage(
        {"unvalidated": "prose that must never be shown"},
        requirement_ids=("R1",),
        source_count=0,
    )
    assert no_sources.status is CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE
    assert no_sources.answer == NO_SOURCES_MESSAGE
    assert no_sources.diagnostics.validation_result is DiagnosticValidationResult.NOT_RUN


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


def test_gap_normalization_does_not_supply_missing_units_or_sources():
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

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.diagnostics.error_code is CoverageValidationErrorCode.STATUS_UNIT_MISMATCH
    assert result.diagnostics.repair_codes == (CoverageValidationErrorCode.STATUS_GAP_MISMATCH,)


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
    assert result.diagnostics.repair_codes == (
        CoverageValidationErrorCode.PREMISE_SOURCE_MISMATCH,
    )
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
    assert (
        result.diagnostics.error_code
        is CoverageValidationErrorCode.PREMISE_CORRECTION_INVALID
    )


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

    assert (
        captured.value.code
        is CoverageValidationErrorCode.PREMISE_PROVENANCE_MISMATCH
    )


def test_contradicted_premise_accepts_framing_plus_counter_provenance():
    correction = _unit(
        "U1",
        (),
        "The proposed origin is too late and the manuscript begins earlier "
        "[Source 2, Source 3].",
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

    assert (
        captured.value.code
        is CoverageValidationErrorCode.PREMISE_PROVENANCE_MISMATCH
    )


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
