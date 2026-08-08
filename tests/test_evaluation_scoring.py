from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from evaluation_scoring import (
    AbstentionObservation,
    AnswerDecomposition,
    AtomicFactualClaim,
    EvaluationScoringError,
    FaithfulnessLabel,
    abstention_metrics,
    audit_citations,
    citation_completeness,
    exact_decision_agreement,
    faithfulness_agreement,
    faithfulness_distribution,
    select_calibration_item_ids,
    validate_decomposition,
)


def _calibration_items():
    return [
        {"id": "H002", "stratum": "focused_biographical"},
        {"id": "H001", "stratum": "focused_biographical"},
        {"id": "H010", "stratum": "focused_analytical"},
        {"id": "H009", "stratum": "focused_analytical"},
        {"id": "H018", "stratum": "conceptual"},
        {"id": "H017", "stratum": "conceptual"},
        {"id": "H024", "stratum": "broad_thematic"},
        {"id": "H023", "stratum": "broad_thematic"},
        {"id": "H033", "stratum": "out_of_corpus"},
        {"id": "H034", "stratum": "out_of_corpus"},
        {"id": "H035", "stratum": "out_of_corpus"},
        {"id": "H036", "stratum": "out_of_corpus"},
        {"id": "H037", "stratum": "adversarial_premise"},
        {"id": "H038", "stratum": "adversarial_premise"},
    ]


def test_calibration_selector_uses_first_positive_and_every_behavior_item():
    assert select_calibration_item_ids(_calibration_items()) == (
        "H001",
        "H009",
        "H017",
        "H023",
        "H033",
        "H034",
        "H035",
        "H036",
        "H037",
        "H038",
    )


def test_calibration_selector_fails_closed_on_wrong_size_or_duplicate_ids():
    too_small = [
        item for item in _calibration_items() if item["id"] != "H036"
    ]
    with pytest.raises(EvaluationScoringError, match="exactly 10"):
        select_calibration_item_ids(too_small)

    duplicate = deepcopy(_calibration_items())
    duplicate[-1]["id"] = "H037"
    with pytest.raises(EvaluationScoringError, match="duplicate"):
        select_calibration_item_ids(duplicate)


def test_citation_audit_keeps_valid_malformed_and_unresolvable_counts_separate():
    audit = audit_citations(
        (
            "One [Source 1]. Two [Source 2, Source 4]. "
            "Bad [Source 3, 4], [Sources 2], and [3]."
        ),
        source_count=3,
    )

    assert audit.well_formed_group_count == 2
    assert audit.source_reference_count == 3
    assert audit.malformed_bracket_token_count == 3
    assert audit.resolvable_group_count == 1
    assert audit.resolvable_reference_count == 2
    assert audit.out_of_range_reference_count == 1


def test_citation_audit_never_repairs_unmatched_or_nested_brackets():
    audit = audit_citations(
        "Nested [[Source 1]] and unmatched [Source 2",
        source_count=2,
    )

    assert audit.well_formed_group_count == 0
    assert audit.source_reference_count == 0
    assert audit.malformed_bracket_token_count == 3


def _valid_decomposition():
    answer = "Alpha changed [Source 1]. Beta followed [Source 2, Source 3]."
    first = "Alpha changed [Source 1]"
    second = "Beta followed [Source 2, Source 3]"
    second_start = answer.index(second)
    return answer, {
        "claims": [
            {
                "id": "C1",
                "text": first,
                "char_start": 0,
                "char_end": len(first),
                "cited_sources": [1],
            },
            {
                "id": "C2",
                "text": second,
                "char_start": second_start,
                "char_end": second_start + len(second),
                "cited_sources": [2, 3],
            },
        ]
    }


def test_decomposition_binds_ordered_nonoverlapping_claims_to_exact_spans():
    answer, raw = _valid_decomposition()

    validated = validate_decomposition(answer, raw)

    assert isinstance(validated, AnswerDecomposition)
    assert tuple(claim.id for claim in validated.claims) == ("C1", "C2")
    assert validated.claims[1].cited_sources == (2, 3)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda raw: raw["claims"][1].update({"id": "C1"}),
            "duplicate",
        ),
        (
            lambda raw: raw["claims"][1].update({"char_start": 5}),
            "out of order or overlaps",
        ),
        (
            lambda raw: raw["claims"][0].update({"char_start": 5, "char_end": 5}),
            "empty or reversed",
        ),
        (
            lambda raw: raw["claims"][1].update({"char_end": 10_000}),
            "exceeds",
        ),
        (
            lambda raw: raw["claims"][0].update({"text": "Changed wording"}),
            "does not match",
        ),
    ],
)
def test_decomposition_rejects_invalid_identity_order_and_span_binding(mutate, message):
    answer, raw = _valid_decomposition()
    mutate(raw)

    with pytest.raises((EvaluationScoringError, ValidationError), match=message):
        validate_decomposition(answer, raw)


@pytest.mark.parametrize("source", [0, -1, True, "1"])
def test_decomposition_schema_rejects_nonpositive_or_nonstrict_sources(source):
    answer, raw = _valid_decomposition()
    raw["claims"][0]["cited_sources"] = [source]
    with pytest.raises(ValidationError, match="positive"):
        validate_decomposition(answer, raw)


def test_decomposition_schema_rejects_extra_fields():
    answer, raw = _valid_decomposition()
    raw["claims"][0]["rationale"] = "not part of the contract"
    with pytest.raises(ValidationError, match="Extra inputs"):
        validate_decomposition(answer, raw)


def test_citation_completeness_reports_exact_counts_and_null_zero_denominator():
    claims = (
        AtomicFactualClaim(
            id="C1",
            text="One",
            char_start=0,
            char_end=3,
            cited_sources=(1,),
        ),
        AtomicFactualClaim(
            id="C2",
            text="Two",
            char_start=4,
            char_end=7,
            cited_sources=(),
        ),
    )

    metric = citation_completeness(claims)
    assert (metric.numerator, metric.denominator, metric.rate) == (1, 2, 0.5)
    empty = citation_completeness(())
    assert (empty.numerator, empty.denominator, empty.rate) == (0, 0, None)


def test_faithfulness_distribution_keeps_all_four_levels_distinct():
    distribution = faithfulness_distribution(
        [
            "supported",
            FaithfulnessLabel.SUPPORTED,
            "partially_supported",
            "unsupported",
            "contradicted",
        ]
    )

    assert distribution.supported_count == 2
    assert distribution.partially_supported_count == 1
    assert distribution.unsupported_count == 1
    assert distribution.contradicted_count == 1
    assert distribution.denominator == 5
    assert distribution.full_supported_rate == 0.4
    assert faithfulness_distribution([]).full_supported_rate is None


def test_faithfulness_agreement_joins_by_claim_id_and_builds_full_matrix():
    human = {
        "C2": "unsupported",
        "C1": "supported",
        "C3": "partially_supported",
        "C4": "contradicted",
    }
    judge = {
        "C4": "contradicted",
        "C3": "supported",
        "C2": "unsupported",
        "C1": "unsupported",
    }

    agreement = faithfulness_agreement(human, judge)

    assert (agreement.agreement_count, agreement.denominator) == (2, 4)
    assert agreement.agreement_rate == 0.5
    assert agreement.confusion_matrix["supported"]["unsupported"] == 1
    assert agreement.confusion_matrix["unsupported"]["unsupported"] == 1
    assert agreement.confusion_matrix["partially_supported"]["supported"] == 1
    assert agreement.confusion_matrix["contradicted"]["contradicted"] == 1
    assert set(agreement.confusion_matrix) == {label.value for label in FaithfulnessLabel}


def test_faithfulness_agreement_requires_exact_id_sets_and_nulls_empty_rate():
    with pytest.raises(EvaluationScoringError, match="claim ids differ"):
        faithfulness_agreement(
            {"C1": "supported"},
            {"C2": "supported"},
        )

    empty = faithfulness_agreement({}, {})
    assert (empty.agreement_count, empty.denominator, empty.agreement_rate) == (
        0,
        0,
        None,
    )


def test_exact_decision_agreement_pools_scalar_and_set_decisions():
    reference = {
        "H001:C001:faithfulness": "supported",
        "H001:C001:gold_matches": ("H001.1", "H001.3"),
        "H001:behavior": "substantive_answer",
    }
    observed = {
        "H001:behavior": "substantive_answer",
        "H001:C001:gold_matches": ("H001.1",),
        "H001:C001:faithfulness": "supported",
    }

    agreement = exact_decision_agreement(reference, observed)

    assert (agreement.agreement_count, agreement.denominator) == (2, 3)
    assert agreement.agreement_rate == pytest.approx(2 / 3)
    assert exact_decision_agreement({}, {}).agreement_rate is None


def test_exact_decision_agreement_rejects_key_drift():
    with pytest.raises(EvaluationScoringError, match="decision ids differ"):
        exact_decision_agreement({"a": "supported"}, {"b": "supported"})


def test_abstention_metrics_keep_three_behavior_denominators_separate():
    observations = [
        {
            "id": "H033",
            "stratum": "out_of_corpus",
            "expected_behavior": "abstain",
            "outcome": "decline",
        },
        {
            "id": "H034",
            "stratum": "out_of_corpus",
            "expected_behavior": "abstain",
            "outcome": "answer",
        },
        {
            "id": "H001",
            "stratum": "focused_biographical",
            "expected_behavior": "answer",
            "outcome": "decline",
        },
        {
            "id": "H002",
            "stratum": "focused_biographical",
            "expected_behavior": "answer",
            "outcome": "partial_decline_then_answer",
        },
        {
            "id": "H037",
            "stratum": "adversarial_premise",
            "expected_behavior": "answer",
            "outcome": "premise_correction",
        },
        {
            "id": "H038",
            "stratum": "adversarial_premise",
            "expected_behavior": "answer",
            "outcome": "decline",
        },
    ]

    metrics = abstention_metrics(observations)

    assert metrics.out_of_corpus_decline.rate == 0.5
    assert (
        metrics.answerable_false_abstention.numerator,
        metrics.answerable_false_abstention.denominator,
        metrics.answerable_false_abstention.rate,
    ) == (2, 4, 0.5)
    assert metrics.adversarial_premise_correction.rate == 0.5


def test_partial_decline_then_answer_counts_as_answer_not_abstention():
    metrics = abstention_metrics(
        [
            {
                "id": "H001",
                "stratum": "focused_biographical",
                "expected_behavior": "answer",
                "outcome": "partial_decline_then_answer",
            },
            {
                "id": "H033",
                "stratum": "out_of_corpus",
                "expected_behavior": "abstain",
                "outcome": "partial_decline_then_answer",
            },
        ]
    )

    assert metrics.answerable_false_abstention.numerator == 0
    assert metrics.out_of_corpus_decline.numerator == 0


def test_abstention_metrics_use_null_for_every_empty_denominator():
    metrics = abstention_metrics([])

    assert metrics.out_of_corpus_decline.rate is None
    assert metrics.answerable_false_abstention.rate is None
    assert metrics.adversarial_premise_correction.rate is None


def test_abstention_metrics_reject_duplicate_item_ids():
    observation = AbstentionObservation(
        id="H001",
        stratum="focused_biographical",
        expected_behavior="answer",
        outcome="answer",
    )
    with pytest.raises(EvaluationScoringError, match="duplicate"):
        abstention_metrics([observation, observation])
