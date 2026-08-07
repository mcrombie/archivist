import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from gold_provenance import (
    NEAR_MIN_SHARED_TOKENS,
    NEAR_SEQUENCE_RATIO_THRESHOLD,
    NEAR_TOKEN_JACCARD_THRESHOLD,
    QUESTION_NORMALIZATION,
    GoldProvenanceValidationError,
    find_question_overlap,
    gold_question_set_sha256,
    normalize_question,
    normalized_question_sha256,
    validate_development_registry,
    validate_gold_provenance,
    validate_gold_provenance_file,
)
from gold_set import sha256_file


CANDIDATE_COMMIT = "a" * 40
RAG_POLICY = "evidence-planned-v26"
GOLD_SHA256 = "b" * 64
MANIFEST_SHA256 = "c" * 64
REGISTRY_SHA256 = "d" * 64
AUTO_QUESTION_SHA256 = "<computed by _validate>"
NEAR_DEVELOPMENT_QUESTION = (
    "How did the Alpha Company influence central government policy during the crisis?"
)
NEAR_GOLD_QUESTION = (
    "How did the Alpha Company influence central government policy amid the crisis?"
)


def _registry(*questions):
    return {
        "schema": "archivist.development_question_registry/1",
        "version": "1.0.0",
        "normalization": QUESTION_NORMALIZATION,
        "questions": [
            {
                "id": f"DEV-{index:03d}",
                "question": question,
                "normalized_sha256": normalized_question_sha256(question),
            }
            for index, question in enumerate(questions, start=1)
        ],
    }


def _gold(*questions):
    return {
        "items": [
            {
                "id": f"H{index:03d}",
                "question": question,
                "stratum": "focused_analytical",
                "expected_behavior": "answer",
            }
            for index, question in enumerate(questions, start=1)
        ]
    }


def _question_commitment(gold):
    return {
        "schema": "archivist.gold_question_commitment/1",
        "question_count": len(gold["items"]),
        "stratum_counts": dict(
            sorted(Counter(item["stratum"] for item in gold["items"]).items())
        ),
        "question_set_sha256": gold_question_set_sha256(gold),
    }


def _provenance(*, reviews=None):
    return {
        "schema": "archivist.gold_provenance/4",
        "gold_set_path": "fixtures/gold_set.json",
        "gold_set_sha256": GOLD_SHA256,
        "question_set_sha256": AUTO_QUESTION_SHA256,
        "candidate_commit": CANDIDATE_COMMIT,
        "candidate_rag_policy": RAG_POLICY,
        "corpus_manifest_sha256": MANIFEST_SHA256,
        "development_registry_sha256": REGISTRY_SHA256,
        "authoring_started_at": "2026-07-29T09:00:00-04:00",
        "authoring_completed_at": "2026-07-29T17:00:00-04:00",
        "annotation_assistance": {
            "method": "owner_adjudication_with_historical_ai_drafting/1",
            "provider": "Anthropic (Claude)",
            "model": "not recorded",
            "surface": "not recorded",
            "raw_draft_record_available": False,
            "prospective_blinding_record_available": False,
            "limitation": (
                "Historical drafting assistance preceded the formal commitment and prospective "
                "provenance protocol; the owner later verified and adjudicated every annotation."
            ),
        },
        "owner_attestations": {
            "questions_behaviors_and_strata_owner_authored_without_candidate_outputs": True,
            "historical_ai_drafting_disclosed_without_prospective_blinding_claim": True,
            "claims_and_essentiality_owner_adjudicated": True,
            "supporting_and_relevant_chunk_ids_owner_verified": True,
            "must_not_claim_and_notes_owner_adjudicated": True,
            "accepted_annotation_prose_source_verified_and_owner_adopted_or_revised": True,
            "held_out_items_not_run_before_lock": True,
            "near_match_flags_reviewed": True,
        },
        "near_match_reviews": reviews or [],
    }


def _validate(provenance, gold, registry, *, question_commitment=None):
    provenance = deepcopy(provenance)
    if provenance.get("question_set_sha256") == AUTO_QUESTION_SHA256:
        provenance["question_set_sha256"] = gold_question_set_sha256(gold)
    return validate_gold_provenance(
        provenance,
        gold,
        registry,
        question_commitment or _question_commitment(gold),
        gold_set_sha256=GOLD_SHA256,
        corpus_manifest_sha256=MANIFEST_SHA256,
        development_registry_sha256=REGISTRY_SHA256,
        expected_gold_set_path="fixtures/gold_set.json",
        expected_candidate_commit=CANDIDATE_COMMIT,
        expected_rag_policy=RAG_POLICY,
    )


def _near_review():
    return {
        "gold_item_id": "H001",
        "development_question_id": "DEV-001",
        "disposition": "approved_distinct",
        "note": "The owner confirms that the changed temporal relationship is intentional.",
    }


def test_question_normalization_is_nfkc_casefold_and_whitespace_stable():
    composed = "  STRASSE\u3000\u212aey?  "

    assert normalize_question(composed) == "strasse key?"
    assert normalized_question_sha256(composed) == normalized_question_sha256("strasse key?")


def test_development_registry_validates_stored_normalized_hashes():
    registry = _registry("What happened to the Alpha Company?")

    summary = validate_development_registry(registry)

    assert summary.version == "1.0.0"
    assert summary.questions[0].question_id == "DEV-001"
    assert summary.questions[0].normalized == "what happened to the alpha company?"


def test_committed_development_registry_is_valid_and_records_known_development_questions():
    registry = json.loads(
        Path("fixtures/development_question_registry.json").read_text(encoding="utf-8")
    )

    summary = validate_development_registry(registry)

    assert summary.version == "1.1.0"
    assert len(summary.questions) == 31
    assert summary.questions[0].question_id == "DEV-PRACTICAL-G001"
    assert summary.questions[-1].question_id == "DEV-MANUAL-008"


def test_provenance_template_binds_candidate_manifest_and_registry_but_is_not_attested():
    fixtures = Path("fixtures")
    template = json.loads(
        (fixtures / "gold_set.provenance.template.json").read_text(encoding="utf-8")
    )

    assert template["schema"] == "archivist.gold_provenance/4"
    assert template["candidate_commit"] == "<replace with the next clean frozen candidate commit>"
    assert template["candidate_rag_policy"] == "evidence-planned-v26"
    assert template["corpus_manifest_sha256"] == sha256_file(fixtures / "corpus_manifest.json")
    assert template["development_registry_sha256"] == sha256_file(
        fixtures / "development_question_registry.json"
    )
    assert template["annotation_assistance"]["raw_draft_record_available"] is False
    assert template["annotation_assistance"]["prospective_blinding_record_available"] is False
    assert set(template["owner_attestations"].values()) == {False}
    assert template["near_match_reviews"] == []


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            lambda registry: registry["questions"][0].update(normalized_sha256="0" * 64),
            "must equal the normalized question hash",
        ),
        (
            lambda registry: registry.update(normalization="lowercase-only"),
            "$registry.normalization",
        ),
        (
            lambda registry: registry["questions"][0].update(extra="not allowed"),
            "unexpected fields ['extra']",
        ),
    ],
)
def test_development_registry_rejects_invalid_contract(mutation, expected_error):
    registry = _registry("What happened to the Alpha Company?")
    mutation(registry)

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        validate_development_registry(registry)

    assert expected_error in "\n".join(exc_info.value.errors)


def test_development_registry_rejects_duplicate_ids_and_normalized_questions():
    registry = _registry(
        "What happened to the Alpha Company?",
        "  WHAT HAPPENED TO THE ALPHA COMPANY?  ",
    )
    registry["questions"][1]["id"] = "DEV-001"

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        validate_development_registry(registry)

    errors = "\n".join(exc_info.value.errors)
    assert "duplicate ID 'DEV-001'" in errors
    assert "duplicates normalized development question 'DEV-001'" in errors


def test_exact_development_question_reuse_is_a_non_overridable_failure():
    registry = validate_development_registry(_registry("What happened to the Alpha Company?"))
    gold = _gold("  WHAT HAPPENED TO THE ALPHA COMPANY? ")

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        find_question_overlap(gold, registry)

    errors = "\n".join(exc_info.value.errors)
    assert "exact normalized duplicate" in errors
    assert "cannot be approved" in errors


def test_near_match_rules_report_transparent_metrics_and_reasons():
    registry = validate_development_registry(_registry(NEAR_DEVELOPMENT_QUESTION))

    matches = find_question_overlap(_gold(NEAR_GOLD_QUESTION), registry)

    assert len(matches) == 1
    match = matches[0]
    assert match.key == ("H001", "DEV-001")
    assert match.shared_token_count >= NEAR_MIN_SHARED_TOKENS
    assert match.token_jaccard >= NEAR_TOKEN_JACCARD_THRESHOLD
    assert match.sequence_ratio >= NEAR_SEQUENCE_RATIO_THRESHOLD
    assert "token_jaccard>=0.72+shared_tokens>=5" in match.reasons
    assert "sequence_ratio>=0.86+min_chars>=24" in match.reasons


def test_unrelated_question_produces_no_near_match():
    registry = validate_development_registry(_registry(NEAR_DEVELOPMENT_QUESTION))

    assert (
        find_question_overlap(
            _gold("Which musical instruments appear in the final appendix?"),
            registry,
        )
        == ()
    )


def test_complete_provenance_accepts_every_exact_binding_and_owner_review():
    summary = _validate(
        _provenance(reviews=[_near_review()]),
        _gold(NEAR_GOLD_QUESTION),
        _registry(NEAR_DEVELOPMENT_QUESTION),
    )

    assert summary.candidate_commit == CANDIDATE_COMMIT
    assert summary.candidate_rag_policy == RAG_POLICY
    assert summary.annotation_provider == "Anthropic (Claude)"
    assert summary.annotation_model == "not recorded"
    assert summary.near_match_count == 1


def test_provenance_rejects_changed_owner_question_projection():
    provenance = _provenance()
    provenance["question_set_sha256"] = "0" * 64

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            provenance,
            _gold("Which musical instruments appear in the final appendix?"),
            _registry(NEAR_DEVELOPMENT_QUESTION),
        )

    assert "canonical ordered ID/question/stratum/behavior projection" in "\n".join(
        exc_info.value.errors
    )


def test_provenance_rejects_question_commitment_that_does_not_match_final_projection():
    gold = _gold("Which musical instruments appear in the final appendix?")
    commitment = _question_commitment(gold)
    commitment["question_set_sha256"] = "0" * 64

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            _provenance(),
            gold,
            _registry(NEAR_DEVELOPMENT_QUESTION),
            question_commitment=commitment,
        )

    errors = "\n".join(exc_info.value.errors)
    assert "$question_commitment.question_set_sha256" in errors
    assert "final canonical owner-field projection" in errors


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("method", "unblinded/1", ".method: must be exactly"),
        ("provider", "", ".provider: must be a non-empty string"),
        (
            "raw_draft_record_available",
            True,
            "must be false for retrospectively disclosed historical assistance",
        ),
        ("limitation", "too short", "must substantively disclose"),
    ],
)
def test_provenance_rejects_invalid_annotation_assistance(
    field,
    value,
    expected_error,
):
    provenance = _provenance()
    provenance["annotation_assistance"][field] = value

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            provenance,
            _gold("Which musical instruments appear in the final appendix?"),
            _registry(NEAR_DEVELOPMENT_QUESTION),
        )

    assert expected_error in "\n".join(exc_info.value.errors)


def test_historical_annotation_assistance_may_not_claim_prospective_blinding_record():
    provenance = _provenance()
    provenance["annotation_assistance"]["prospective_blinding_record_available"] = True

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            provenance,
            _gold("Which musical instruments appear in the final appendix?"),
            _registry(NEAR_DEVELOPMENT_QUESTION),
        )

    assert "must be false for retrospectively disclosed historical assistance" in "\n".join(
        exc_info.value.errors
    )


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("gold_set_sha256", "0" * 64, "does not match the exact file hash"),
        ("corpus_manifest_sha256", "0" * 64, "does not match the exact file hash"),
        (
            "development_registry_sha256",
            "0" * 64,
            "does not match the exact file hash",
        ),
        ("candidate_commit", "f" * 40, "does not match the frozen candidate"),
        ("candidate_commit", "abc123", "full lowercase 40-character Git commit"),
        ("candidate_rag_policy", "evidence-planned-v20", "does not match the frozen policy"),
        ("gold_set_path", "../gold_set.json", "normalized relative POSIX path"),
        ("gold_set_path", "fixtures\\gold_set.json", "normalized relative POSIX path"),
    ],
)
def test_provenance_rejects_wrong_or_malformed_bindings(field, value, expected_error):
    provenance = _provenance()
    provenance[field] = value

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            provenance,
            _gold("Which musical instruments appear in the final appendix?"),
            _registry(NEAR_DEVELOPMENT_QUESTION),
        )

    assert expected_error in "\n".join(exc_info.value.errors)


@pytest.mark.parametrize(
    ("started", "completed", "expected_error"),
    [
        (
            "2026-07-29T09:00:00",
            "2026-07-29T17:00:00-04:00",
            "must include a timezone offset",
        ),
        (
            "not-a-time",
            "2026-07-29T17:00:00-04:00",
            "must be a valid ISO-8601 timestamp",
        ),
        (
            "2026-07-29T18:00:00-04:00",
            "2026-07-29T17:00:00-04:00",
            "must not precede authoring_started_at",
        ),
    ],
)
def test_provenance_requires_ordered_timezone_aware_timestamps(
    started,
    completed,
    expected_error,
):
    provenance = _provenance()
    provenance["authoring_started_at"] = started
    provenance["authoring_completed_at"] = completed

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            provenance,
            _gold("Which musical instruments appear in the final appendix?"),
            _registry(NEAR_DEVELOPMENT_QUESTION),
        )

    assert expected_error in "\n".join(exc_info.value.errors)


def test_every_owner_attestation_must_be_explicitly_true():
    provenance = _provenance()
    provenance["owner_attestations"]["claims_and_essentiality_owner_adjudicated"] = False

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            provenance,
            _gold("Which musical instruments appear in the final appendix?"),
            _registry(NEAR_DEVELOPMENT_QUESTION),
        )

    assert "$provenance.owner_attestations.claims_and_essentiality_owner_adjudicated" in "\n".join(
        exc_info.value.errors
    )


def test_every_flagged_near_match_requires_exactly_one_substantive_owner_review():
    provenance = _provenance()

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            provenance,
            _gold(NEAR_GOLD_QUESTION),
            _registry(NEAR_DEVELOPMENT_QUESTION),
        )

    assert "missing owner reviews for [('H001', 'DEV-001')]" in "\n".join(exc_info.value.errors)

    duplicate_reviews = [_near_review(), _near_review()]
    duplicate_reviews[0]["note"] = ""
    duplicate_reviews[1]["disposition"] = "same_question"
    provenance = _provenance(reviews=duplicate_reviews)
    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            provenance,
            _gold(NEAR_GOLD_QUESTION),
            _registry(NEAR_DEVELOPMENT_QUESTION),
        )

    errors = "\n".join(exc_info.value.errors)
    assert "duplicate near-match review" in errors
    assert "non-empty distinction note" in errors
    assert "must be exactly 'approved_distinct'" in errors


def test_review_for_unflagged_pair_is_rejected():
    provenance = _provenance(reviews=[_near_review()])

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            provenance,
            _gold("Which musical instruments appear in the final appendix?"),
            _registry(NEAR_DEVELOPMENT_QUESTION),
        )

    assert "reviews for unflagged pairs" in "\n".join(exc_info.value.errors)


def test_near_review_cannot_override_an_exact_duplicate():
    exact_question = "What happened to the Alpha Company?"
    provenance = _provenance(
        reviews=[
            {
                "gold_item_id": "H001",
                "development_question_id": "DEV-001",
                "disposition": "approved_distinct",
                "note": "This attempted override must not be accepted.",
            }
        ]
    )

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(provenance, _gold(exact_question), _registry(exact_question))

    errors = "\n".join(exc_info.value.errors)
    assert "exact normalized duplicate" in errors
    assert "reviews for unflagged pairs" in errors


def test_file_validator_hashes_exact_bytes(tmp_path):
    gold_path = tmp_path / "gold.json"
    manifest_path = tmp_path / "manifest.json"
    registry_path = tmp_path / "registry.json"
    provenance_path = tmp_path / "provenance.json"
    commitment_path = tmp_path / "commitment.json"

    gold = _gold("Which musical instruments appear in the final appendix?")
    registry = _registry(NEAR_DEVELOPMENT_QUESTION)
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    manifest_path.write_text(json.dumps({"manifest": "synthetic"}), encoding="utf-8")
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    provenance = _provenance()
    provenance["gold_set_sha256"] = sha256_file(gold_path)
    provenance["question_set_sha256"] = gold_question_set_sha256(gold)
    provenance["corpus_manifest_sha256"] = sha256_file(manifest_path)
    provenance["development_registry_sha256"] = sha256_file(registry_path)
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    commitment_path.write_text(json.dumps(_question_commitment(gold)), encoding="utf-8")

    summary = validate_gold_provenance_file(
        provenance_path,
        gold_path,
        manifest_path,
        registry_path,
        commitment_path,
        expected_gold_set_path="fixtures/gold_set.json",
        expected_candidate_commit=CANDIDATE_COMMIT,
        expected_rag_policy=RAG_POLICY,
        repository_root=tmp_path,
    )

    assert summary.gold_set_sha256 == sha256_file(gold_path)
    assert summary.corpus_manifest_sha256 == sha256_file(manifest_path)


def test_provenance_rejects_unexpected_fields():
    provenance = deepcopy(_provenance())
    provenance["owner_attestations"]["owner_name"] = "not part of the contract"
    provenance["extra"] = True

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            provenance,
            _gold("Which musical instruments appear in the final appendix?"),
            _registry(NEAR_DEVELOPMENT_QUESTION),
        )

    errors = "\n".join(exc_info.value.errors)
    assert "$provenance: unexpected fields ['extra']" in errors
    assert "$provenance.owner_attestations: unexpected fields ['owner_name']" in errors
