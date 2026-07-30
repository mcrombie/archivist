import pytest
from pydantic import ValidationError

from answer_coverage import AnswerUnitRole, ContentOutcome, CoverageOutcomeStatus, PremiseStatus
from full_context_coverage import (
    FULL_CONTEXT_COVERAGE_SCHEMA,
    AbsenceFinding,
    AbsenceStatus,
    FullContextClaim,
    FullContextCoverageAnswer,
    FullContextValidationErrorCode,
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
                subject="Hudson's Bay Company",
                status=AbsenceStatus.NOT_ADDRESSED_IN_CORPUS,
                note="The manuscript does not treat this company.",
            ),
        ),
        self_reported=ContentOutcome.INSUFFICIENT_EVIDENCE,
    )

    result = process_full_context_coverage(payload, eligible_chunks=CORPUS)

    assert result.status is CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE
    assert result.content_outcome is ContentOutcome.INSUFFICIENT_EVIDENCE
    assert result.final_chunks == []
    assert result.answer == "The manuscript does not treat this company."


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


def test_a_scan_contradicting_a_reported_absence_downgrades_a_complete_claim():
    payload = answer(
        (claim("C1", ("10_Synthetic Chapter 1_ Title_001",)),),
        absence_findings=(
            AbsenceFinding(
                subject="Ohio Company",
                status=AbsenceStatus.NOT_ADDRESSED_IN_CORPUS,
                note="The manuscript does not treat this company.",
            ),
        ),
        self_reported=ContentOutcome.VALID_COMPLETE,
    )

    trusted = process_full_context_coverage(payload, eligible_chunks=CORPUS)
    assert trusted.content_outcome is ContentOutcome.VALID_COMPLETE

    audited = process_full_context_coverage(
        payload,
        eligible_chunks=CORPUS,
        contradicted_absence_subjects=("ohio company",),
    )
    # Downgraded, not rewritten: the reader still sees the model's own prose.
    assert audited.content_outcome is ContentOutcome.VALID_PARTIAL
    assert audited.answer == trusted.answer
    assert audited.diagnostics["contradicted_absence_count"] == 1


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


def test_openai_strict_schema_conversion_preserves_the_chunk_id_constraint():
    from openai.lib._parsing._responses import type_to_text_format_param

    response_format = type_to_text_format_param(FullContextCoverageAnswer)
    claim_schema = response_format["schema"]["$defs"]["FullContextClaim"]["properties"]

    assert response_format["strict"] is True
    assert claim_schema["cited_chunk_ids"]["items"]["pattern"].endswith("_[0-9]{3,}$")
    # Rules out a model-authored bracket at the schema level, not just in review.
    assert r"\[" in claim_schema["text"]["pattern"]
