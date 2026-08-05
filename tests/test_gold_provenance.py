import json
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
    normalize_question,
    normalized_question_sha256,
    validate_development_registry,
    validate_gold_provenance,
    validate_gold_provenance_file,
)
from gold_set import sha256_file


CANDIDATE_COMMIT = "a" * 40
RAG_POLICY = "evidence-planned-v21"
GOLD_SHA256 = "b" * 64
MANIFEST_SHA256 = "c" * 64
REGISTRY_SHA256 = "d" * 64
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
            {"id": f"H{index:03d}", "question": question}
            for index, question in enumerate(questions, start=1)
        ]
    }


def _provenance(*, reviews=None):
    return {
        "schema": "archivist.gold_provenance/1",
        "gold_set_path": "fixtures/gold_set.json",
        "gold_set_sha256": GOLD_SHA256,
        "candidate_commit": CANDIDATE_COMMIT,
        "candidate_rag_policy": RAG_POLICY,
        "corpus_manifest_sha256": MANIFEST_SHA256,
        "development_registry_sha256": REGISTRY_SHA256,
        "authoring_started_at": "2026-07-29T09:00:00-04:00",
        "authoring_completed_at": "2026-07-29T17:00:00-04:00",
        "owner_attestations": {
            "questions_authored_without_candidate_outputs": True,
            "claims_and_locations_owner_authored": True,
            "held_out_items_not_run_before_lock": True,
            "near_match_flags_reviewed": True,
        },
        "near_match_reviews": reviews or [],
    }


def _validate(provenance, gold, registry):
    return validate_gold_provenance(
        provenance,
        gold,
        registry,
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
    assert normalized_question_sha256(composed) == normalized_question_sha256(
        "strasse key?"
    )


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

    assert template["candidate_commit"] == (
        "bf424c880bca4728a8d13225f85978e27a8d8dcf"
    )
    assert template["candidate_rag_policy"] == "evidence-planned-v21"
    assert template["corpus_manifest_sha256"] == sha256_file(
        fixtures / "corpus_manifest.json"
    )
    assert template["development_registry_sha256"] == sha256_file(
        fixtures / "development_question_registry.json"
    )
    assert set(template["owner_attestations"].values()) == {False}
    assert template["near_match_reviews"] == []


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            lambda registry: registry["questions"][0].update(
                normalized_sha256="0" * 64
            ),
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
    registry = validate_development_registry(
        _registry("What happened to the Alpha Company?")
    )
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

    assert find_question_overlap(
        _gold("Which musical instruments appear in the final appendix?"),
        registry,
    ) == ()


def test_complete_provenance_accepts_every_exact_binding_and_owner_review():
    summary = _validate(
        _provenance(reviews=[_near_review()]),
        _gold(NEAR_GOLD_QUESTION),
        _registry(NEAR_DEVELOPMENT_QUESTION),
    )

    assert summary.candidate_commit == CANDIDATE_COMMIT
    assert summary.candidate_rag_policy == RAG_POLICY
    assert summary.near_match_count == 1


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
    provenance["owner_attestations"]["claims_and_locations_owner_authored"] = False

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            provenance,
            _gold("Which musical instruments appear in the final appendix?"),
            _registry(NEAR_DEVELOPMENT_QUESTION),
        )

    assert (
        "$provenance.owner_attestations.claims_and_locations_owner_authored"
        in "\n".join(exc_info.value.errors)
    )


def test_every_flagged_near_match_requires_exactly_one_substantive_owner_review():
    provenance = _provenance()

    with pytest.raises(GoldProvenanceValidationError) as exc_info:
        _validate(
            provenance,
            _gold(NEAR_GOLD_QUESTION),
            _registry(NEAR_DEVELOPMENT_QUESTION),
        )

    assert "missing owner reviews for [('H001', 'DEV-001')]" in "\n".join(
        exc_info.value.errors
    )

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

    gold = _gold("Which musical instruments appear in the final appendix?")
    registry = _registry(NEAR_DEVELOPMENT_QUESTION)
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    manifest_path.write_text(json.dumps({"manifest": "synthetic"}), encoding="utf-8")
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    provenance = _provenance()
    provenance["gold_set_sha256"] = sha256_file(gold_path)
    provenance["corpus_manifest_sha256"] = sha256_file(manifest_path)
    provenance["development_registry_sha256"] = sha256_file(registry_path)
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")

    summary = validate_gold_provenance_file(
        provenance_path,
        gold_path,
        manifest_path,
        registry_path,
        expected_gold_set_path="fixtures/gold_set.json",
        expected_candidate_commit=CANDIDATE_COMMIT,
        expected_rag_policy=RAG_POLICY,
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
