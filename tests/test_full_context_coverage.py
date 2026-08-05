import pytest
from pydantic import ValidationError

from answer_coverage import AnswerUnitRole, ContentOutcome, CoverageOutcomeStatus, PremiseStatus
from full_context_coverage import (
    FULL_CONTEXT_COVERAGE_SCHEMA,
    FULL_CONTEXT_RUN_DIAGNOSTICS_SCHEMA,
    AbsenceFinding,
    AbsenceStatus,
    FullContextClaim,
    FullContextCoverageAnswer,
    FullContextValidationErrorCode,
    TrustedTargetAudit,
    process_full_context_coverage,
)


def chunk(chunk_id: str, text: str = "Synthetic manuscript prose.") -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document": "10_Synthetic Chapter 1_ Title.md",
        "chapter_title": "Synthetic Chapter 1",
        "paragraph_start": 1,
        "paragraph_end": 4,
        "text": text,
    }


CORPUS = [chunk(f"10_Synthetic Chapter 1_ Title_{index:03d}") for index in range(1, 6)]


def target_audit(
    target_id: str = "T1",
    *,
    surface: str = "Synthetic Subject",
    direct: tuple[str, ...] = (),
    absence_checkable: bool = True,
    certified_absent: bool = False,
) -> TrustedTargetAudit:
    return TrustedTargetAudit(
        target_id=target_id,
        query_surface_span=surface,
        direct_chunk_ids=direct,
        absence_checkable=absence_checkable,
        certified_direct_absence=certified_absent,
    )


def claim(
    claim_id: str,
    cited: tuple[str, ...],
    *,
    text: str | None = None,
    role: AnswerUnitRole = AnswerUnitRole.MECHANISM,
    paragraph_group: int = 1,
) -> FullContextClaim:
    return FullContextClaim(
        claim_id=claim_id,
        role=role,
        text=text or f"A synthetic process occurred in stage {claim_id}.",
        cited_chunk_ids=cited,
        paragraph_group=paragraph_group,
    )


def answer(
    claims: tuple[FullContextClaim, ...],
    *,
    premise_finding=None,
    absence_findings: tuple[AbsenceFinding, ...] = (),
    self_reported: ContentOutcome = ContentOutcome.VALID_COMPLETE,
) -> FullContextCoverageAnswer:
    return FullContextCoverageAnswer(
        schema=FULL_CONTEXT_COVERAGE_SCHEMA,
        premise_finding=premise_finding,
        claims=claims,
        absence_findings=absence_findings,
        self_reported_content_outcome=self_reported,
    )


def test_generation_schema_puts_streamable_claims_before_terminal_ledgers():
    properties = list(FullContextCoverageAnswer.model_json_schema()["properties"])

    assert properties == [
        "schema",
        "claims",
        "premise_finding",
        "absence_findings",
        "self_reported_content_outcome",
    ]


def test_claim_text_may_not_contain_a_citation_bracket_or_extra_sentence():
    # The renderer owns the bracket, so a model-written one is rejected outright
    # rather than normalized into an ambiguous second citation group.
    for invalid in (
        "A synthetic process occurred [Source 1].",
        "A synthetic process occurred. It then continued.",
        "A synthetic process occurred; it then continued.",
        "A synthetic process occurred",
        "A synthetic process occurred.\nAnother line.",
    ):
        with pytest.raises(ValidationError):
            claim("C1", ("10_Synthetic Chapter 1_ Title_001",), text=invalid)


def test_chunk_id_shape_is_constrained_by_the_schema():
    with pytest.raises(ValidationError):
        claim("C1", ("not-a-chunk-id",))


def test_duplicate_claim_ids_are_rejected_by_the_schema():
    with pytest.raises(ValidationError):
        answer(
            (
                claim("C1", ("10_Synthetic Chapter 1_ Title_001",)),
                claim("C1", ("10_Synthetic Chapter 1_ Title_002",)),
            )
        )


def test_well_formed_but_ineligible_chunk_id_fails_the_whole_answer_closed():
    payload = answer(
        (
            claim("C1", ("10_Synthetic Chapter 1_ Title_001",)),
            claim("C2", ("10_Synthetic Chapter 9_ Invented_412",)),
        )
    )

    result = process_full_context_coverage(payload, eligible_chunks=CORPUS)

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.error_code is FullContextValidationErrorCode.UNRESOLVABLE_CHUNK_ID
    # No partial answer survives an invented citation.
    assert result.final_chunks == []
    assert result.content_outcome is None


def test_duplicate_cited_chunk_ids_within_one_claim_fail_closed():
    payload = answer(
        (
            claim(
                "C1",
                (
                    "10_Synthetic Chapter 1_ Title_001",
                    "10_Synthetic Chapter 1_ Title_001",
                ),
            ),
        )
    )

    result = process_full_context_coverage(payload, eligible_chunks=CORPUS)

    assert result.error_code is FullContextValidationErrorCode.DUPLICATE_CITED_CHUNK_ID


def test_cited_chunks_remap_to_compact_source_numbers_in_first_cited_order():
    payload = answer(
        (
            claim("C1", ("10_Synthetic Chapter 1_ Title_004",)),
            claim(
                "C2",
                (
                    "10_Synthetic Chapter 1_ Title_002",
                    "10_Synthetic Chapter 1_ Title_004",
                ),
                paragraph_group=1,
            ),
            claim("C3", ("10_Synthetic Chapter 1_ Title_002",), paragraph_group=2),
        )
    )

    result = process_full_context_coverage(payload, eligible_chunks=CORPUS)

    assert result.status is CoverageOutcomeStatus.ANSWERED
    # Five chunks were supplied; only the two actually cited may be returned.
    assert [item["chunk_id"] for item in result.final_chunks] == [
        "10_Synthetic Chapter 1_ Title_004",
        "10_Synthetic Chapter 1_ Title_002",
    ]
    assert "[Source 1]." in result.answer
    assert "[Source 2, Source 1]." in result.answer
    # paragraph_group drives paragraph breaks, so C3 starts a new paragraph.
    assert len(result.answer.split("\n\n")) == 2


def test_rendered_citations_are_well_formed_by_construction():
    payload = answer((claim("C1", ("10_Synthetic Chapter 1_ Title_003",)),))

    result = process_full_context_coverage(payload, eligible_chunks=CORPUS)

    assert result.answer == "A synthetic process occurred in stage C1 [Source 1]."


def test_no_claims_is_a_clean_insufficient_evidence_outcome():
    payload = answer(
        (),
        absence_findings=(
            AbsenceFinding(
                target_id="T1",
                status=AbsenceStatus.NOT_ADDRESSED_IN_CORPUS,
            ),
        ),
        self_reported=ContentOutcome.INSUFFICIENT_EVIDENCE,
    )

    result = process_full_context_coverage(
        payload,
        eligible_chunks=CORPUS,
        trusted_target_audits=(
            target_audit(surface="Hudson's Bay Company", certified_absent=True),
        ),
    )

    assert result.status is CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE
    assert result.content_outcome is ContentOutcome.INSUFFICIENT_EVIDENCE
    assert result.final_chunks == []
    assert result.answer == "The manuscript does not directly address Hudson's Bay Company."


def test_indirect_model_status_cannot_create_an_uncited_positive_assertion():
    payload = answer(
        (),
        absence_findings=(
            AbsenceFinding(target_id="T1", status=AbsenceStatus.ADDRESSED_INDIRECTLY),
        ),
        self_reported=ContentOutcome.INSUFFICIENT_EVIDENCE,
    )
    result = process_full_context_coverage(
        payload,
        eligible_chunks=CORPUS,
        trusted_target_audits=(
            target_audit(surface="Hudson's Bay Company", certified_absent=True),
        ),
    )
    assert result.answer == "The manuscript does not directly address Hudson's Bay Company."


def test_contradicted_premise_requires_a_first_position_correction():
    correction = claim(
        "C1",
        ("10_Synthetic Chapter 1_ Title_001",),
        role=AnswerUnitRole.PREMISE_CORRECTION,
    )
    ordinary = claim("C2", ("10_Synthetic Chapter 1_ Title_002",))

    ordered = process_full_context_coverage(
        answer(
            (correction, ordinary),
            premise_finding={"status": PremiseStatus.CONTRADICTED, "correction_claim_id": "C1"},
        ),
        eligible_chunks=CORPUS,
    )
    assert ordered.status is CoverageOutcomeStatus.ANSWERED

    misordered = process_full_context_coverage(
        answer(
            (ordinary, correction),
            premise_finding={"status": PremiseStatus.CONTRADICTED, "correction_claim_id": "C1"},
        ),
        eligible_chunks=CORPUS,
    )
    assert misordered.error_code is FullContextValidationErrorCode.PREMISE_CORRECTION_NOT_FIRST


def test_correction_claim_without_a_contradicted_premise_fails_closed():
    payload = answer(
        (
            claim(
                "C1",
                ("10_Synthetic Chapter 1_ Title_001",),
                role=AnswerUnitRole.PREMISE_CORRECTION,
            ),
        ),
        premise_finding={"status": PremiseStatus.SUPPORTED, "correction_claim_id": None},
    )

    result = process_full_context_coverage(payload, eligible_chunks=CORPUS)

    assert result.error_code is FullContextValidationErrorCode.PREMISE_CORRECTION_UNEXPECTED


@pytest.mark.parametrize("with_claim", [False, True])
def test_a_scan_contradicting_a_reported_absence_fails_closed(with_claim):
    claims = (claim("C1", ("10_Synthetic Chapter 1_ Title_001",)),) if with_claim else ()
    payload = answer(
        claims,
        absence_findings=(
            AbsenceFinding(
                target_id="T1",
                status=AbsenceStatus.NOT_ADDRESSED_IN_CORPUS,
            ),
        ),
        self_reported=(
            ContentOutcome.VALID_COMPLETE if with_claim else ContentOutcome.INSUFFICIENT_EVIDENCE
        ),
    )

    result = process_full_context_coverage(
        payload,
        eligible_chunks=CORPUS,
        trusted_target_audits=(
            target_audit(
                surface="Ohio Company",
                direct=("10_Synthetic Chapter 1_ Title_001",),
            ),
        ),
    )

    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.error_code is FullContextValidationErrorCode.ABSENCE_TARGET_MISMATCH
    assert "Ohio Company" not in result.answer
    assert result.final_chunks == []


def test_unknown_or_paraphrased_absence_targets_cannot_cross_the_binding_boundary():
    unknown = answer(
        (),
        absence_findings=(
            AbsenceFinding(
                target_id="T99",
                status=AbsenceStatus.NOT_ADDRESSED_IN_CORPUS,
            ),
        ),
        self_reported=ContentOutcome.INSUFFICIENT_EVIDENCE,
    )
    result = process_full_context_coverage(
        unknown,
        eligible_chunks=CORPUS,
        trusted_target_audits=(target_audit(certified_absent=True),),
    )
    assert result.error_code is FullContextValidationErrorCode.UNKNOWN_ABSENCE_TARGET_ID

    # Version 1's model-authored subject/note form cannot smuggle a paraphrase
    # or uncited prose through the version 2 response schema.
    with pytest.raises(ValidationError):
        AbsenceFinding.model_validate(
            {
                "target_id": "T1",
                "subject": "A paraphrased subject",
                "status": AbsenceStatus.NOT_ADDRESSED_IN_CORPUS,
                "note": "Model-authored absence prose.",
            }
        )


def test_g008_style_near_match_cannot_pass_with_an_unrelated_valid_chunk():
    payload = answer((claim("C1", ("10_Synthetic Chapter 1_ Title_002",)),))
    result = process_full_context_coverage(
        payload,
        eligible_chunks=CORPUS,
        trusted_target_audits=(
            target_audit(
                surface="Ohio Company",
                direct=("10_Synthetic Chapter 1_ Title_001",),
            ),
        ),
    )
    assert result.error_code is FullContextValidationErrorCode.TRUSTED_TARGET_EVIDENCE_MISSING
    assert result.final_chunks == []


def test_all_certified_absent_targets_reject_unsolicited_analogue_claims():
    payload = answer(
        (claim("C1", ("10_Synthetic Chapter 1_ Title_002",)),),
        absence_findings=(
            AbsenceFinding(
                target_id="T1",
                status=AbsenceStatus.NOT_ADDRESSED_IN_CORPUS,
            ),
        ),
        self_reported=ContentOutcome.VALID_PARTIAL,
    )
    result = process_full_context_coverage(
        payload,
        eligible_chunks=CORPUS,
        trusted_target_audits=(
            target_audit(surface="Ohio Company", certified_absent=True),
        ),
    )
    assert result.error_code is FullContextValidationErrorCode.TRUSTED_TARGET_CLAIMS_UNSUPPORTED
    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.final_chunks == []


def test_uncheckable_target_without_direct_evidence_cannot_license_analogue_claims():
    payload = answer(
        (claim("C1", ("10_Synthetic Chapter 1_ Title_002",)),),
        self_reported=ContentOutcome.VALID_PARTIAL,
    )
    result = process_full_context_coverage(
        payload,
        eligible_chunks=CORPUS,
        trusted_target_audits=(
            target_audit(
                surface="Resolver-restored subject",
                absence_checkable=False,
                certified_absent=False,
            ),
        ),
    )
    assert result.error_code is FullContextValidationErrorCode.TRUSTED_TARGET_CLAIMS_UNSUPPORTED
    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED
    assert result.final_chunks == []


def test_certified_absent_target_requires_a_bound_absence_finding():
    payload = answer((), self_reported=ContentOutcome.INSUFFICIENT_EVIDENCE)
    result = process_full_context_coverage(
        payload,
        eligible_chunks=CORPUS,
        trusted_target_audits=(target_audit(certified_absent=True),),
    )
    assert result.error_code is FullContextValidationErrorCode.TRUSTED_TARGET_ABSENCE_MISSING


@pytest.mark.parametrize(
    "audits",
    [
        (),
        (
            target_audit(
                absence_checkable=False,
                certified_absent=False,
            ),
        ),
    ],
)
def test_zero_claims_cannot_turn_a_model_self_report_into_an_absence_certificate(audits):
    payload = answer((), self_reported=ContentOutcome.INSUFFICIENT_EVIDENCE)
    result = process_full_context_coverage(
        payload,
        eligible_chunks=CORPUS,
        trusted_target_audits=audits,
    )
    assert result.error_code is FullContextValidationErrorCode.INSUFFICIENT_EVIDENCE_UNCERTIFIED
    assert result.status is CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED


def test_model_complete_is_capped_at_partial_and_self_report_remains_diagnostic():
    result = process_full_context_coverage(
        answer((claim("C1", ("10_Synthetic Chapter 1_ Title_001",)),)),
        eligible_chunks=CORPUS,
    )
    assert result.content_outcome is ContentOutcome.VALID_PARTIAL
    assert result.diagnostics["self_reported_content_outcome"] == "valid_complete"


@pytest.mark.parametrize(
    ("claims", "self_reported"),
    [
        (
            (claim("C1", ("10_Synthetic Chapter 1_ Title_001",)),),
            ContentOutcome.INSUFFICIENT_EVIDENCE,
        ),
        ((), ContentOutcome.VALID_PARTIAL),
    ],
)
def test_claim_presence_and_content_outcome_must_be_consistent(claims, self_reported):
    result = process_full_context_coverage(
        answer(claims, self_reported=self_reported),
        eligible_chunks=CORPUS,
    )
    assert result.error_code is FullContextValidationErrorCode.CONTENT_OUTCOME_INCONSISTENT


def test_premise_correction_must_be_exactly_one_bound_first_role():
    correction_1 = claim(
        "C1",
        ("10_Synthetic Chapter 1_ Title_001",),
        role=AnswerUnitRole.PREMISE_CORRECTION,
    )
    correction_2 = claim(
        "C2",
        ("10_Synthetic Chapter 1_ Title_002",),
        role=AnswerUnitRole.PREMISE_CORRECTION,
    )
    multiple = process_full_context_coverage(
        answer(
            (correction_1, correction_2),
            premise_finding={"status": PremiseStatus.CONTRADICTED, "correction_claim_id": "C1"},
        ),
        eligible_chunks=CORPUS,
    )
    assert multiple.error_code is FullContextValidationErrorCode.PREMISE_CORRECTION_COUNT_INVALID

    ordinary = claim("C1", ("10_Synthetic Chapter 1_ Title_001",))
    actual_correction = claim(
        "C2",
        ("10_Synthetic Chapter 1_ Title_002",),
        role=AnswerUnitRole.PREMISE_CORRECTION,
    )
    mismatched = process_full_context_coverage(
        answer(
            (ordinary, actual_correction),
            premise_finding={"status": PremiseStatus.CONTRADICTED, "correction_claim_id": "C1"},
        ),
        eligible_chunks=CORPUS,
    )
    assert mismatched.error_code is FullContextValidationErrorCode.PREMISE_CORRECTION_ID_MISMATCH

    unexpected_id = process_full_context_coverage(
        answer(
            (ordinary,),
            premise_finding={"status": PremiseStatus.SUPPORTED, "correction_claim_id": "C1"},
        ),
        eligible_chunks=CORPUS,
    )
    assert unexpected_id.error_code is FullContextValidationErrorCode.PREMISE_CORRECTION_UNEXPECTED


def test_refusal_and_missing_payload_fail_closed_without_sources():
    refused = process_full_context_coverage(None, eligible_chunks=CORPUS, refused=True)
    assert refused.error_code is FullContextValidationErrorCode.GENERATION_REFUSED
    assert refused.final_chunks == []

    missing = process_full_context_coverage(None, eligible_chunks=CORPUS)
    assert missing.error_code is FullContextValidationErrorCode.INVALID_PAYLOAD
    assert missing.final_chunks == []


def test_diagnostics_carry_counts_only_and_no_manuscript_or_identifier_text():
    payload = answer((claim("C1", ("10_Synthetic Chapter 1_ Title_001",)),))

    diagnostics = process_full_context_coverage(payload, eligible_chunks=CORPUS).diagnostics

    serialized = str(diagnostics)
    assert "Synthetic manuscript prose" not in serialized
    assert "10_Synthetic Chapter 1_ Title_001" not in serialized
    assert "A synthetic process" not in serialized
    assert diagnostics["supplied_chunk_count"] == 5
    assert diagnostics["cited_chunk_count"] == 1
    assert diagnostics["claim_count"] == 1
    assert diagnostics["schema"] == FULL_CONTEXT_RUN_DIAGNOSTICS_SCHEMA
    assert diagnostics["response_schema"] == FULL_CONTEXT_COVERAGE_SCHEMA


def test_openai_strict_schema_conversion_preserves_the_chunk_id_constraint():
    from openai.lib._parsing._responses import type_to_text_format_param

    response_format = type_to_text_format_param(FullContextCoverageAnswer)
    claim_schema = response_format["schema"]["$defs"]["FullContextClaim"]["properties"]

    assert response_format["strict"] is True
    assert claim_schema["cited_chunk_ids"]["items"]["pattern"].endswith("_[0-9]{3,}$")
    # Rules out a model-authored bracket at the schema level, not just in review.
    assert r"\[" in claim_schema["text"]["pattern"]
