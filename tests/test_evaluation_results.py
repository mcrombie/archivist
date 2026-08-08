from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from answer_evaluation import (
    CalibrationLabelFile,
    PrivateTraceReference,
    ScoringDimension,
    build_decomposed_claim,
    build_decomposed_pilot_item,
    build_private_generated_item,
    build_private_source,
    build_private_usage_event,
    build_instrument_lock,
    canonical_json_sha256,
    sha256_text,
)
from evaluation_judge import ItemRubricInput
from evaluation_results import (
    AGREEMENT_PROJECTION_SCHEMA,
    BASELINE_SEMANTIC_AGGREGATE_SCHEMA,
    BASELINE_SEMANTIC_ITEM_SCHEMA,
    CALIBRATION_SEMANTIC_AGGREGATE_SCHEMA,
    CLAIM_EVIDENCE_RESULT_SCHEMA,
    DECOMPOSITION_STABILITY_SCHEMA,
    ITEM_RUBRIC_RESULT_SCHEMA,
    MANUAL_SCORING_AGGREGATE_SCHEMA,
    PRIVATE_FULL_RUN_ARTIFACT_SCHEMA,
    BaselineSemanticAggregate,
    DecompositionStability,
    ManualScoringAggregate,
    CalibrationSemanticAggregate,
    ClaimEvidenceResult,
    ItemRubricResult,
    build_calibration_semantic_aggregate,
    build_calibration_semantic_item,
    build_baseline_semantic_aggregate,
    build_baseline_semantic_item,
    build_baseline_semantic_item_from_calibration,
    build_claim_evidence_result,
    build_decomposition_stability,
    build_item_rubric_result,
    build_manual_scoring_aggregate,
    build_private_full_run_artifact,
    project_calibration_agreement,
    validate_calibration_semantic_aggregate,
    validate_baseline_semantic_aggregate,
    validate_baseline_semantic_item,
    validate_claim_evidence_result,
    validate_decomposition_stability,
    validate_item_rubric_result,
    validate_manual_scoring_aggregate,
    validate_private_full_run_artifact,
)


COHORT_SHA = "a" * 64
PILOT_SHA = "b" * 64
DECOMPOSITION_ARTIFACT_SHA = "c" * 64
EVIDENCE_PROMPT_SHA = "d" * 64
RUBRIC_PROMPT_SHA = "e" * 64
JUDGE_MODEL = "gpt-5.6-terra"
JUDGE_SETTINGS = {"reasoning_effort": "medium", "verbosity": "low"}
PRIVATE_SOURCE_SENTINEL = "PRIVATE SOURCE: the exact manuscript passage"


def _usage_event(*, response_id: str, operation: str):
    return build_private_usage_event(
        sequence=1,
        response_id=response_id,
        recorded_at="2026-08-07T16:00:00+00:00",
        operation=operation,
        requested_model=JUDGE_MODEL,
        actual_model=JUDGE_MODEL,
        input_tokens=40,
        cached_tokens=0,
        cache_write_tokens=0,
        output_tokens=10,
        reasoning_tokens=2,
        total_tokens=50,
        estimated_cost_nano_usd=100_000,
        pricing_version="openai-2026-08-07",
        unpriced=False,
    )


def _provider(response_id: str) -> dict[str, object]:
    return {
        "id": response_id,
        "model": JUDGE_MODEL,
        "created_at": 1_786_118_400,
        "system_fingerprint": "fp_eval",
    }


def _bundle(index: int) -> dict[str, Any]:
    item_id = f"H{index:03d}"
    question = f"What happened in item {item_id}?"
    claim_text = f"Fact {item_id}"
    answer = f"{claim_text} [Source 1]."
    source = build_private_source(
        source_number=1,
        chunk_id=f"chapter_{index:02d}_001",
        text=f"{PRIVATE_SOURCE_SENTINEL} {item_id}",
        metadata={"chapter": index},
    )
    generation_usage = build_private_usage_event(
        sequence=1,
        response_id=f"resp_generation_{item_id}",
        recorded_at="2026-08-07T15:59:00+00:00",
        operation="answer_generation",
        requested_model="gpt-5.6-sol",
        actual_model="gpt-5.6-sol",
        input_tokens=100,
        cached_tokens=0,
        cache_write_tokens=0,
        output_tokens=20,
        reasoning_tokens=5,
        total_tokens=120,
        estimated_cost_nano_usd=500_000,
        pricing_version="openai-2026-08-07",
        unpriced=False,
    )
    trace = PrivateTraceReference(
        sequence=1,
        schema_id="archivist.retrieval_trace/1",
        trace_id=f"{index:032x}",
        path=f"retrieval-traces/{item_id}.json",
        sha256=f"{index % 16:x}" * 64,
        query_sha256=f"{(index + 1) % 16:x}" * 64,
        retrieval_version="faceted-hybrid-rrf-v2",
    )
    generated = build_private_generated_item(
        item_id=item_id,
        question=question,
        stratum="focused_analytical",
        expected_behavior="answer",
        answer=answer,
        status="answered",
        evidence_decision="direct_answer",
        diagnostics={"validation_result": "valid"},
        sources=(source,),
        elapsed_seconds=1.0,
        usage_events=(generation_usage,),
        trace_references=(trace,),
    )
    claim = build_decomposed_claim(
        claim_id="C001",
        text=claim_text,
        char_start=0,
        char_end=len(claim_text),
        cited_source_numbers=(1,),
    )
    decomposition = build_decomposed_pilot_item(
        item_id=item_id,
        answer_sha256=generated.answer_sha256,
        claims=(claim,),
    )
    gold_id = f"{item_id}.G1"
    gold_text = f"Gold claim for {item_id}."
    tripwire = f"Forbidden claim for {item_id}."
    rubric = ItemRubricInput.model_validate(
        {
            "question": question,
            "claims": [
                {
                    "claim_id": gold_id,
                    "text": gold_text,
                    "essential": True,
                }
            ],
            "must_not_claim": [tripwire],
        }
    )
    return {
        "item_id": item_id,
        "generated": generated,
        "decomposition": decomposition,
        "claim": claim,
        "rubric": rubric,
        "gold_id": gold_id,
        "gold_text": gold_text,
        "tripwire": tripwire,
    }


def _evidence(
    bundle: dict[str, Any],
    *,
    ordinal: int,
    faithfulness: str = "supported",
    source_label: str = "supported",
):
    item_id = bundle["item_id"]
    response_id = f"resp_evidence_{item_id}_{ordinal}"
    return build_claim_evidence_result(
        cohort_manifest_sha256=COHORT_SHA,
        generated_item=bundle["generated"],
        decomposition=bundle["decomposition"],
        claim=bundle["claim"],
        call_ordinal=ordinal,
        prompt_version="evaluation-claim-evidence-v1",
        prompt_sha256=EVIDENCE_PROMPT_SHA,
        judge_model=JUDGE_MODEL,
        judge_settings=JUDGE_SETTINGS,
        provider=_provider(response_id),
        usage_event=_usage_event(
            response_id=response_id,
            operation="eval_claim_evidence",
        ),
        verdict={
            "claim_id": "C001",
            "faithfulness": faithfulness,
            "source_verdicts": [{"source_number": 1, "label": source_label}],
            "rationale": "A bounded evidence rationale.",
        },
    )


def _rubric_result(
    bundle: dict[str, Any],
    *,
    mapped: bool = True,
    gold_status: str = "present",
    tripwire_status: str = "not_asserted",
    response_behavior: str = "substantive_answer",
):
    item_id = bundle["item_id"]
    response_id = f"resp_rubric_{item_id}"
    return build_item_rubric_result(
        cohort_manifest_sha256=COHORT_SHA,
        generated_item=bundle["generated"],
        decomposition=bundle["decomposition"],
        rubric=bundle["rubric"],
        prompt_version="evaluation-item-rubric-v2",
        prompt_sha256=RUBRIC_PROMPT_SHA,
        judge_model=JUDGE_MODEL,
        judge_settings=JUDGE_SETTINGS,
        provider=_provider(response_id),
        usage_event=_usage_event(response_id=response_id, operation="eval_item_rubric"),
        verdict={
            "gold_claims": [
                {"claim_id": bundle["gold_id"], "status": gold_status}
            ],
            "answer_claim_matches": [
                {
                    "answer_claim_id": "C001",
                    "gold_claim_ids": [bundle["gold_id"]] if mapped else [],
                }
            ],
            "must_not_claim": [{"index": 0, "status": tripwire_status}],
            "response_behavior": response_behavior,
            "rationale": "A bounded rubric rationale.",
        },
    )


def _semantic_fixture():
    bundles = [_bundle(index) for index in range(1, 11)]
    semantic_items = []
    label_items = []
    for index, bundle in enumerate(bundles, start=1):
        first = _evidence(
            bundle,
            ordinal=1,
            faithfulness="unsupported" if index == 1 else "supported",
            source_label="unsupported" if index == 2 else "supported",
        )
        repeat = _evidence(bundle, ordinal=2)
        rubric_result = _rubric_result(
            bundle,
            mapped=index != 3,
            gold_status="absent" if index == 4 else "present",
            tripwire_status="asserted" if index == 5 else "not_asserted",
            response_behavior="decline" if index == 6 else "substantive_answer",
        )
        semantic_items.append(
            build_calibration_semantic_item(
                first_call_claim_evidence=(first,),
                item_rubric=rubric_result,
                repeat_first_claim_evidence=repeat,
            )
        )
        label_items.append(
            {
                "item_id": bundle["item_id"],
                "answer_sha256": bundle["generated"].answer_sha256,
                "decomposition_sha256": bundle["decomposition"].decomposition_sha256,
                "rubric_sha256": rubric_result.rubric.calibration_rubric_sha256,
                "response_behavior": "substantive_answer",
                "claims": [
                    {
                        "claim_id": "C001",
                        "claim_text": bundle["claim"].text,
                        "claim_sha256": bundle["claim"].claim_sha256,
                        "faithfulness": "supported",
                        "gold_match_ids": [bundle["gold_id"]],
                        "cited_source_labels": {1: "supported"},
                    }
                ],
                "gold_claim_statuses": [
                    {
                        "claim_id": bundle["gold_id"],
                        "claim_text": bundle["gold_text"],
                        "claim_text_sha256": sha256_text(bundle["gold_text"]),
                        "status": "present",
                    }
                ],
                "must_not_claim_statuses": [
                    {
                        "index": 0,
                        "claim_text": bundle["tripwire"],
                        "claim_text_sha256": sha256_text(bundle["tripwire"]),
                        "status": "not_asserted",
                    }
                ],
            }
        )
    aggregate = build_calibration_semantic_aggregate(
        cohort_manifest_sha256=COHORT_SHA,
        pilot_artifact_sha256=PILOT_SHA,
        decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
        calibration_item_ids=[bundle["item_id"] for bundle in bundles],
        items=semantic_items,
    )
    labels = CalibrationLabelFile.model_validate(
        {
            "schema": "archivist.answer_evaluation.calibration_labels/1",
            "pilot_artifact_sha256": PILOT_SHA,
            "decomposition_artifact_sha256": DECOMPOSITION_ARTIFACT_SHA,
            "items": label_items,
        }
    )
    return aggregate, labels, bundles


def _instrument_lock(
    *,
    manual_dimensions: frozenset[ScoringDimension] = frozenset(),
    judge_results_sha256: str = "2" * 64,
):
    dimension_values = {
        dimension: (0.0 if dimension in manual_dimensions else 1.0)
        for dimension in ScoringDimension
    }
    return build_instrument_lock(
        instrument_id="held-out-v26-scoring-v1",
        cohort_manifest_sha256=COHORT_SHA,
        pilot_artifact_sha256=PILOT_SHA,
        decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
        human_labels_sha256="1" * 64,
        judge_results_sha256=judge_results_sha256,
        judge_model=JUDGE_MODEL,
        judge_settings=JUDGE_SETTINGS,
        decomposition_prompt_sha256="3" * 64,
        evidence_prompt_sha256=EVIDENCE_PROMPT_SHA,
        rubric_prompt_sha256=RUBRIC_PROMPT_SHA,
        pooled_agreement=sum(dimension_values.values()) / len(ScoringDimension),
        repeat_agreement=1.0,
        dimension_agreements={
            dimension: (dimension_values[dimension], 10)
            for dimension in ScoringDimension
        },
    )


def _baseline_fixture():
    calibration, _, calibration_bundles = _semantic_fixture()
    instrument = _instrument_lock(
        judge_results_sha256=calibration.aggregate_sha256,
    )
    bundles = list(calibration_bundles)
    items = [
        build_baseline_semantic_item_from_calibration(
            item,
            decomposition=bundle["decomposition"],
            instrument_lock=instrument,
        )
        for item, bundle in zip(
            calibration.items,
            calibration_bundles,
            strict=True,
        )
    ]
    for index in range(11, 38):
        bundle = _bundle(index)
        bundles.append(bundle)
        items.append(
            build_baseline_semantic_item(
                decomposition=bundle["decomposition"],
                instrument_lock=instrument,
                first_call_claim_evidence=(_evidence(bundle, ordinal=1),),
                item_rubric=_rubric_result(bundle),
            )
        )
    aggregate = build_baseline_semantic_aggregate(
        cohort_manifest_sha256=COHORT_SHA,
        generation_artifact_sha256=PILOT_SHA,
        decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
        instrument_lock=instrument,
        item_ids=[bundle["item_id"] for bundle in bundles],
        items=items,
    )
    return aggregate, bundles, calibration, instrument


def _additional_usage_events(calibration):
    decomposition_events = tuple(
        _usage_event(
            response_id=f"resp_decomposition_{index:03d}",
            operation="eval_claim_decomposition",
        )
        for index in range(1, 58)
    )
    repeat_events = tuple(
        item.repeat_first_claim_evidence.usage_event
        for item in calibration.items
        if item.repeat_first_claim_evidence is not None
    )
    return decomposition_events + repeat_events


def _manual_label(bundle: dict[str, Any]) -> dict[str, object]:
    rubric_binding = bundle["rubric"]
    calibration_rubric = {
        "item_id": bundle["item_id"],
        "gold_claims": [
            {"claim_id": claim.claim_id, "text": claim.text}
            for claim in rubric_binding.claims
        ],
        "must_not_claims": list(rubric_binding.must_not_claim),
    }
    return {
        "item_id": bundle["item_id"],
        "answer_sha256": bundle["generated"].answer_sha256,
        "decomposition_sha256": bundle["decomposition"].decomposition_sha256,
        "rubric_sha256": canonical_json_sha256(calibration_rubric),
        "response_behavior": None,
        "claims": [
            {
                "claim_id": claim.claim_id,
                "claim_text": claim.text,
                "claim_sha256": claim.claim_sha256,
                "faithfulness": None,
                "gold_match_ids": None,
                "cited_source_labels": None,
            }
            for claim in bundle["decomposition"].claims
        ],
        "gold_claim_statuses": [
            {
                "claim_id": claim.claim_id,
                "claim_text": claim.text,
                "claim_text_sha256": sha256_text(claim.text),
                "status": None,
            }
            for claim in rubric_binding.claims
        ],
        "must_not_claim_statuses": [
            {
                "index": index,
                "claim_text": text,
                "claim_text_sha256": sha256_text(text),
                "status": None,
            }
            for index, text in enumerate(rubric_binding.must_not_claim)
        ],
    }


def _decomposition_with_claim_count(bundle: dict[str, Any], count: int):
    answer = bundle["generated"].answer
    claims = [
        build_decomposed_claim(
            claim_id=f"C{index + 1:03d}",
            text=answer[index : index + 1],
            char_start=index,
            char_end=index + 1,
            cited_source_numbers=(1,),
        )
        for index in range(count)
    ]
    return build_decomposed_pilot_item(
        item_id=bundle["item_id"],
        answer_sha256=bundle["generated"].answer_sha256,
        claims=claims,
    )


def test_claim_evidence_result_is_self_hashed_text_free_and_externally_bound() -> None:
    bundle = _bundle(1)
    result = _evidence(bundle, ordinal=1)

    assert result.schema == CLAIM_EVIDENCE_RESULT_SCHEMA
    assert result.result_sha256 == canonical_json_sha256(
        result.model_dump(mode="json", exclude={"result_sha256"})
    )
    serialized = json.dumps(result.model_dump(mode="json"), sort_keys=True)
    assert PRIVATE_SOURCE_SENTINEL not in serialized
    assert "gold_rubric" not in serialized
    assert (
        validate_claim_evidence_result(
            result,
            cohort_manifest_sha256=COHORT_SHA,
            generated_item=bundle["generated"],
            decomposition=bundle["decomposition"],
            claim=bundle["claim"],
            call_ordinal=1,
            prompt_version="evaluation-claim-evidence-v1",
            prompt_sha256=EVIDENCE_PROMPT_SHA,
            judge_model=JUDGE_MODEL,
            judge_settings=JUDGE_SETTINGS,
        )
        is result
    )

    with pytest.raises(ValueError, match="cohort_manifest_sha256 changed"):
        validate_claim_evidence_result(
            result,
            cohort_manifest_sha256="f" * 64,
            generated_item=bundle["generated"],
            decomposition=bundle["decomposition"],
            claim=bundle["claim"],
            call_ordinal=1,
            prompt_version="evaluation-claim-evidence-v1",
            prompt_sha256=EVIDENCE_PROMPT_SHA,
            judge_model=JUDGE_MODEL,
            judge_settings=JUDGE_SETTINGS,
        )

    leaked = result.model_dump(mode="json")
    leaked["gold_rubric"] = {"private": "gold"}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ClaimEvidenceResult.model_validate(leaked)


def test_claim_evidence_rejects_provider_usage_and_source_cardinality_tampering() -> None:
    result = _evidence(_bundle(1), ordinal=1)

    wrong_provider = result.model_dump(mode="json")
    wrong_provider["provider"]["id"] = "resp_other"
    wrong_provider["result_sha256"] = canonical_json_sha256(
        {key: value for key, value in wrong_provider.items() if key != "result_sha256"}
    )
    with pytest.raises(ValidationError, match="provider and usage response IDs differ"):
        ClaimEvidenceResult.model_validate(wrong_provider)

    missing_source_verdict = result.model_dump(mode="json")
    missing_source_verdict["verdict"]["source_verdicts"] = []
    missing_source_verdict["result_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in missing_source_verdict.items()
            if key != "result_sha256"
        }
    )
    with pytest.raises(ValidationError, match="cited source order or cardinality"):
        ClaimEvidenceResult.model_validate(missing_source_verdict)


def test_item_rubric_result_is_sanitized_text_free_and_exactly_joined() -> None:
    bundle = _bundle(1)
    result = _rubric_result(bundle)

    assert result.schema == ITEM_RUBRIC_RESULT_SCHEMA
    serialized = json.dumps(result.model_dump(mode="json"), sort_keys=True)
    assert PRIVATE_SOURCE_SENTINEL not in serialized
    assert bundle["generated"].sources[0].chunk_id not in serialized
    assert "source_union" not in serialized
    assert bundle["gold_text"] not in serialized
    assert (
        validate_item_rubric_result(
            result,
            cohort_manifest_sha256=COHORT_SHA,
            generated_item=bundle["generated"],
            decomposition=bundle["decomposition"],
            rubric=bundle["rubric"],
            prompt_version="evaluation-item-rubric-v2",
            prompt_sha256=RUBRIC_PROMPT_SHA,
            judge_model=JUDGE_MODEL,
            judge_settings=JUDGE_SETTINGS,
        )
        is result
    )

    leaked = result.model_dump(mode="json")
    leaked["source_union"] = [{"text": PRIVATE_SOURCE_SENTINEL}]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ItemRubricResult.model_validate(leaked)

    changed_join = result.model_dump(mode="json")
    changed_join["verdict"]["answer_claim_matches"][0]["answer_claim_id"] = "C999"
    changed_join["result_sha256"] = canonical_json_sha256(
        {key: value for key, value in changed_join.items() if key != "result_sha256"}
    )
    with pytest.raises(ValidationError, match="locked answer claim order"):
        ItemRubricResult.model_validate(changed_join)


def test_semantic_aggregate_requires_exact_ten_order_and_distinct_repeat() -> None:
    aggregate, _, bundles = _semantic_fixture()

    assert aggregate.schema == CALIBRATION_SEMANTIC_AGGREGATE_SCHEMA
    assert len(aggregate.items) == 10
    assert (
        validate_calibration_semantic_aggregate(
            aggregate,
            cohort_manifest_sha256=COHORT_SHA,
            pilot_artifact_sha256=PILOT_SHA,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            calibration_item_ids=[bundle["item_id"] for bundle in bundles],
        )
        is aggregate
    )

    reordered = aggregate.model_dump(mode="json")
    reordered["items"][0], reordered["items"][1] = (
        reordered["items"][1],
        reordered["items"][0],
    )
    reordered["aggregate_sha256"] = canonical_json_sha256(
        {key: value for key, value in reordered.items() if key != "aggregate_sha256"}
    )
    with pytest.raises(ValidationError, match="every calibration item in order"):
        CalibrationSemanticAggregate.model_validate(reordered)

    missing = aggregate.model_dump(mode="json")
    missing["items"].pop()
    missing["calibration_item_ids"].pop()
    missing["aggregate_sha256"] = canonical_json_sha256(
        {key: value for key, value in missing.items() if key != "aggregate_sha256"}
    )
    with pytest.raises(ValidationError, match="at least 10 items"):
        CalibrationSemanticAggregate.model_validate(missing)

    first_item = aggregate.items[0]
    copied_repeat_payload = first_item.first_call_claim_evidence[0].model_dump(
        mode="json"
    )
    copied_repeat_payload["call_ordinal"] = 2
    copied_repeat_payload["result_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in copied_repeat_payload.items()
            if key != "result_sha256"
        }
    )
    copied_repeat = ClaimEvidenceResult.model_validate(copied_repeat_payload)
    with pytest.raises(ValidationError, match="distinct provider response"):
        build_calibration_semantic_item(
            first_call_claim_evidence=first_item.first_call_claim_evidence,
            item_rubric=first_item.item_rubric,
            repeat_first_claim_evidence=copied_repeat,
        )


def test_agreement_projection_reports_pooled_repeat_and_all_dimensions() -> None:
    aggregate, labels, _ = _semantic_fixture()

    projection = project_calibration_agreement(aggregate, labels)

    assert projection.schema == AGREEMENT_PROJECTION_SCHEMA
    assert projection.pooled_exact_agreement.agreement_count == 54
    assert projection.pooled_exact_agreement.denominator == 60
    assert projection.pooled_exact_agreement.agreement_rate == 0.9
    assert projection.repeat_agreement.agreement_count == 18
    assert projection.repeat_agreement.denominator == 20
    assert projection.repeat_agreement.agreement_rate == 0.9
    assert [entry.dimension for entry in projection.dimensions] == list(ScoringDimension)
    assert all(entry.agreement_count == 9 for entry in projection.dimensions)
    assert all(entry.denominator == 10 for entry in projection.dimensions)
    assert all(entry.agreement_rate == 0.9 for entry in projection.dimensions)
    assert projection.projection_sha256 == canonical_json_sha256(
        projection.model_dump(mode="json", exclude={"projection_sha256"})
    )


def test_agreement_projection_rejects_incomplete_or_rebound_owner_labels() -> None:
    aggregate, labels, _ = _semantic_fixture()

    incomplete = labels.model_dump(mode="json")
    incomplete["items"][0]["claims"][0]["faithfulness"] = None
    with pytest.raises(ValueError, match="faithfulness is not labelled"):
        project_calibration_agreement(aggregate, incomplete)

    rebound = labels.model_dump(mode="json")
    rebound["pilot_artifact_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="another pilot artifact"):
        project_calibration_agreement(aggregate, rebound)


def test_baseline_item_reuses_calibration_first_calls_without_repeat_lane() -> None:
    calibration, _, bundles = _semantic_fixture()
    source = calibration.items[0]
    instrument = _instrument_lock()

    item = build_baseline_semantic_item_from_calibration(
        source,
        decomposition=bundles[0]["decomposition"],
        instrument_lock=instrument,
    )

    assert item.schema == BASELINE_SEMANTIC_ITEM_SCHEMA
    assert item.first_call_claim_evidence == source.first_call_claim_evidence
    assert (
        item.first_call_claim_evidence[0].result_sha256
        == source.first_call_claim_evidence[0].result_sha256
    )
    assert item.item_rubric == source.item_rubric
    assert "repeat_first_claim_evidence" not in item.model_dump(mode="json")
    assert (
        validate_baseline_semantic_item(
            item,
            cohort_manifest_sha256=COHORT_SHA,
            generated_item=bundles[0]["generated"],
            decomposition=bundles[0]["decomposition"],
            rubric=bundles[0]["rubric"],
            instrument_lock=instrument,
            evidence_prompt_version="evaluation-claim-evidence-v1",
            evidence_prompt_sha256=EVIDENCE_PROMPT_SHA,
            rubric_prompt_version="evaluation-item-rubric-v2",
            rubric_prompt_sha256=RUBRIC_PROMPT_SHA,
            judge_model=JUDGE_MODEL,
            judge_settings=JUDGE_SETTINGS,
        )
        is item
    )

    with pytest.raises(ValidationError, match="cover every locked claim"):
        build_baseline_semantic_item(
            decomposition=bundles[0]["decomposition"],
            instrument_lock=instrument,
            first_call_claim_evidence=(),
            item_rubric=source.item_rubric,
        )
    with pytest.raises(ValidationError, match="call_ordinal 1"):
        build_baseline_semantic_item(
            decomposition=bundles[0]["decomposition"],
            instrument_lock=instrument,
            first_call_claim_evidence=(_evidence(bundles[0], ordinal=2),),
            item_rubric=source.item_rubric,
        )


def test_baseline_manual_fallback_omits_only_inactive_judge_lanes() -> None:
    bundle = _bundle(1)
    evidence_manual = _instrument_lock(
        manual_dimensions=frozenset(
            {
                ScoringDimension.FAITHFULNESS,
                ScoringDimension.CITED_SOURCE_SUPPORT,
            }
        )
    )
    rubric_manual = _instrument_lock(
        manual_dimensions=frozenset(
            {
                ScoringDimension.CLAIM_MAPPING,
                ScoringDimension.GOLD_STATUS,
                ScoringDimension.MUST_NOT_TRIPWIRES,
                ScoringDimension.RESPONSE_BEHAVIOR,
            }
        )
    )
    all_manual = _instrument_lock(
        manual_dimensions=frozenset(ScoringDimension)
    )

    no_evidence = build_baseline_semantic_item(
        decomposition=bundle["decomposition"],
        instrument_lock=evidence_manual,
        first_call_claim_evidence=(),
        item_rubric=_rubric_result(bundle),
    )
    assert not no_evidence.evidence_lane_active
    assert no_evidence.rubric_lane_active
    assert no_evidence.first_call_claim_evidence == ()

    no_rubric = build_baseline_semantic_item(
        decomposition=bundle["decomposition"],
        instrument_lock=rubric_manual,
        first_call_claim_evidence=(_evidence(bundle, ordinal=1),),
        item_rubric=None,
    )
    assert no_rubric.evidence_lane_active
    assert not no_rubric.rubric_lane_active
    assert no_rubric.item_rubric is None

    neither = build_baseline_semantic_item(
        decomposition=bundle["decomposition"],
        instrument_lock=all_manual,
        first_call_claim_evidence=(),
        item_rubric=None,
    )
    assert not neither.evidence_lane_active
    assert not neither.rubric_lane_active
    assert (
        validate_baseline_semantic_item(
            neither,
            cohort_manifest_sha256=COHORT_SHA,
            generated_item=bundle["generated"],
            decomposition=bundle["decomposition"],
            rubric=bundle["rubric"],
            instrument_lock=all_manual,
            evidence_prompt_version="evaluation-claim-evidence-v1",
            evidence_prompt_sha256=EVIDENCE_PROMPT_SHA,
            rubric_prompt_version="evaluation-item-rubric-v2",
            rubric_prompt_sha256=RUBRIC_PROMPT_SHA,
            judge_model=JUDGE_MODEL,
            judge_settings=JUDGE_SETTINGS,
        )
        is neither
    )

    with pytest.raises(ValidationError, match="active baseline evidence lane"):
        build_baseline_semantic_item(
            decomposition=bundle["decomposition"],
            instrument_lock=_instrument_lock(),
            first_call_claim_evidence=(),
            item_rubric=_rubric_result(bundle),
        )
    with pytest.raises(ValidationError, match="active baseline rubric lane"):
        build_baseline_semantic_item(
            decomposition=bundle["decomposition"],
            instrument_lock=_instrument_lock(),
            first_call_claim_evidence=(_evidence(bundle, ordinal=1),),
            item_rubric=None,
        )


def test_calibration_projection_preserves_existing_results_for_manual_lanes() -> None:
    calibration, _, bundles = _semantic_fixture()
    all_manual = _instrument_lock(
        manual_dimensions=frozenset(ScoringDimension)
    )

    projected = build_baseline_semantic_item_from_calibration(
        calibration.items[0],
        decomposition=bundles[0]["decomposition"],
        instrument_lock=all_manual,
    )

    assert not projected.evidence_lane_active
    assert not projected.rubric_lane_active
    assert projected.first_call_claim_evidence == (
        calibration.items[0].first_call_claim_evidence
    )
    assert projected.item_rubric == calibration.items[0].item_rubric


def test_baseline_aggregate_requires_and_validates_exact_37_ordered_items() -> None:
    aggregate, bundles, _, instrument = _baseline_fixture()

    assert aggregate.schema == BASELINE_SEMANTIC_AGGREGATE_SCHEMA
    assert len(aggregate.items) == 37
    assert aggregate.aggregate_sha256 == canonical_json_sha256(
        aggregate.model_dump(mode="json", exclude={"aggregate_sha256"})
    )
    assert (
        validate_baseline_semantic_aggregate(
            aggregate,
            cohort_manifest_sha256=COHORT_SHA,
            generation_artifact_sha256=PILOT_SHA,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            item_ids=[bundle["item_id"] for bundle in bundles],
            generated_items=[bundle["generated"] for bundle in bundles],
            decompositions=[bundle["decomposition"] for bundle in bundles],
            rubrics=[bundle["rubric"] for bundle in bundles],
            instrument_lock=instrument,
            evidence_prompt_version="evaluation-claim-evidence-v1",
            evidence_prompt_sha256=EVIDENCE_PROMPT_SHA,
            rubric_prompt_version="evaluation-item-rubric-v2",
            rubric_prompt_sha256=RUBRIC_PROMPT_SHA,
            judge_model=JUDGE_MODEL,
            judge_settings=JUDGE_SETTINGS,
        )
        is aggregate
    )

    reordered = aggregate.model_dump(mode="json")
    reordered["items"][0], reordered["items"][1] = (
        reordered["items"][1],
        reordered["items"][0],
    )
    reordered["aggregate_sha256"] = canonical_json_sha256(
        {key: value for key, value in reordered.items() if key != "aggregate_sha256"}
    )
    with pytest.raises(ValidationError, match="all 37 items in exact order"):
        BaselineSemanticAggregate.model_validate(reordered)

    with pytest.raises(ValidationError, match="at least 37 items"):
        build_baseline_semantic_aggregate(
            cohort_manifest_sha256=COHORT_SHA,
            generation_artifact_sha256=PILOT_SHA,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            instrument_lock=instrument,
            item_ids=aggregate.item_ids[:-1],
            items=aggregate.items[:-1],
        )


def test_baseline_external_validation_rejects_judge_config_drift() -> None:
    aggregate, bundles, _, instrument = _baseline_fixture()

    with pytest.raises(ValueError, match="judge settings differ"):
        validate_baseline_semantic_aggregate(
            aggregate,
            cohort_manifest_sha256=COHORT_SHA,
            generation_artifact_sha256=PILOT_SHA,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            item_ids=[bundle["item_id"] for bundle in bundles],
            generated_items=[bundle["generated"] for bundle in bundles],
            decompositions=[bundle["decomposition"] for bundle in bundles],
            rubrics=[bundle["rubric"] for bundle in bundles],
            instrument_lock=instrument,
            evidence_prompt_version="evaluation-claim-evidence-v1",
            evidence_prompt_sha256=EVIDENCE_PROMPT_SHA,
            rubric_prompt_version="evaluation-item-rubric-v2",
            rubric_prompt_sha256=RUBRIC_PROMPT_SHA,
            judge_model=JUDGE_MODEL,
            judge_settings={"reasoning_effort": "high", "verbosity": "low"},
        )


def test_private_full_run_artifact_is_exact_hash_only_reporting_boundary() -> None:
    semantic, bundles, calibration, instrument = _baseline_fixture()
    additional_usage = _additional_usage_events(calibration)

    artifact = build_private_full_run_artifact(
        cohort_manifest_sha256=COHORT_SHA,
        generation_artifact_sha256=PILOT_SHA,
        decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
        generated_items=[bundle["generated"] for bundle in bundles],
        decompositions=[bundle["decomposition"] for bundle in bundles],
        semantic_aggregate=semantic,
        instrument_lock=instrument,
        calibration_semantic_aggregate=calibration,
        additional_usage_events=additional_usage,
    )

    assert artifact.schema == PRIVATE_FULL_RUN_ARTIFACT_SCHEMA
    assert len(artifact.items) == 37
    assert artifact.additional_usage_event_count == len(additional_usage)
    assert artifact.additional_usage_events_sha256 == canonical_json_sha256(
        [event.model_dump(mode="json") for event in additional_usage]
    )
    assert artifact.artifact_sha256 == canonical_json_sha256(
        artifact.model_dump(mode="json", exclude={"artifact_sha256"})
    )
    serialized = json.dumps(artifact.model_dump(mode="json"), sort_keys=True)
    assert PRIVATE_SOURCE_SENTINEL not in serialized
    assert bundles[0]["generated"].answer not in serialized
    assert bundles[0]["gold_text"] not in serialized
    assert (
        validate_private_full_run_artifact(
            artifact,
            cohort_manifest_sha256=COHORT_SHA,
            generation_artifact_sha256=PILOT_SHA,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            generated_items=[bundle["generated"] for bundle in bundles],
            decompositions=[bundle["decomposition"] for bundle in bundles],
            semantic_aggregate=semantic,
            instrument_lock=instrument,
            calibration_semantic_aggregate=calibration,
            additional_usage_events=additional_usage,
        )
        is artifact
    )

    reordered_usage = list(additional_usage)
    reordered_usage[0], reordered_usage[1] = reordered_usage[1], reordered_usage[0]
    with pytest.raises(ValueError, match="private full-run artifact changed"):
        validate_private_full_run_artifact(
            artifact,
            cohort_manifest_sha256=COHORT_SHA,
            generation_artifact_sha256=PILOT_SHA,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            generated_items=[bundle["generated"] for bundle in bundles],
            decompositions=[bundle["decomposition"] for bundle in bundles],
            semantic_aggregate=semantic,
            instrument_lock=instrument,
            calibration_semantic_aggregate=calibration,
            additional_usage_events=reordered_usage,
        )

    with pytest.raises(ValueError, match="omits or changes calibration repeat"):
        build_private_full_run_artifact(
            cohort_manifest_sha256=COHORT_SHA,
            generation_artifact_sha256=PILOT_SHA,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            generated_items=[bundle["generated"] for bundle in bundles],
            decompositions=[bundle["decomposition"] for bundle in bundles],
            semantic_aggregate=semantic,
            instrument_lock=instrument,
            calibration_semantic_aggregate=calibration,
            additional_usage_events=additional_usage[:-1],
        )

    duplicate_represented = list(additional_usage)
    duplicate_represented[-1] = bundles[0]["generated"].usage_events[0]
    with pytest.raises(ValueError, match="duplicate represented provider calls"):
        build_private_full_run_artifact(
            cohort_manifest_sha256=COHORT_SHA,
            generation_artifact_sha256=PILOT_SHA,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            generated_items=[bundle["generated"] for bundle in bundles],
            decompositions=[bundle["decomposition"] for bundle in bundles],
            semantic_aggregate=semantic,
            instrument_lock=instrument,
            calibration_semantic_aggregate=calibration,
            additional_usage_events=duplicate_represented,
        )

    tampered = artifact.model_dump(mode="json")
    tampered["items"][0]["answer_sha256"] = "f" * 64
    tampered["artifact_sha256"] = canonical_json_sha256(
        {key: value for key, value in tampered.items() if key != "artifact_sha256"}
    )
    with pytest.raises(ValidationError, match="does not bind the full-run item"):
        type(artifact).model_validate(tampered)

    wrong_instrument = instrument.model_copy(
        update={"cohort_manifest_sha256": "f" * 64}
    )
    with pytest.raises(ValueError, match="instrument lock belongs to another cohort"):
        build_private_full_run_artifact(
            cohort_manifest_sha256=COHORT_SHA,
            generation_artifact_sha256=PILOT_SHA,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            generated_items=[bundle["generated"] for bundle in bundles],
            decompositions=[bundle["decomposition"] for bundle in bundles],
            semantic_aggregate=semantic,
            instrument_lock=wrong_instrument,
            calibration_semantic_aggregate=calibration,
            additional_usage_events=additional_usage,
        )


def test_manual_scoring_aggregate_is_closed_and_bound_into_full_run() -> None:
    semantic, bundles, calibration, instrument = _baseline_fixture()
    additional_usage = _additional_usage_events(calibration)
    manual = build_manual_scoring_aggregate(
        cohort_manifest_sha256=COHORT_SHA,
        generation_artifact_sha256=PILOT_SHA,
        decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
        instrument_lock=instrument,
        generated_items=[bundle["generated"] for bundle in bundles],
        decompositions=[bundle["decomposition"] for bundle in bundles],
        rubrics=[bundle["rubric"] for bundle in bundles],
        items=[_manual_label(bundle) for bundle in bundles],
    )

    assert manual.schema == MANUAL_SCORING_AGGREGATE_SCHEMA
    assert len(manual.items) == 37
    assert (
        validate_manual_scoring_aggregate(
            manual,
            cohort_manifest_sha256=COHORT_SHA,
            generation_artifact_sha256=PILOT_SHA,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            instrument_lock=instrument,
            generated_items=[bundle["generated"] for bundle in bundles],
            decompositions=[bundle["decomposition"] for bundle in bundles],
            rubrics=[bundle["rubric"] for bundle in bundles],
        )
        is manual
    )
    artifact = build_private_full_run_artifact(
        cohort_manifest_sha256=COHORT_SHA,
        generation_artifact_sha256=PILOT_SHA,
        decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
        generated_items=[bundle["generated"] for bundle in bundles],
        decompositions=[bundle["decomposition"] for bundle in bundles],
        semantic_aggregate=semantic,
        instrument_lock=instrument,
        calibration_semantic_aggregate=calibration,
        additional_usage_events=additional_usage,
        manual_scoring_aggregate=manual,
    )
    assert artifact.manual_scoring_aggregate_sha256 == manual.aggregate_sha256
    assert (
        validate_private_full_run_artifact(
            artifact,
            cohort_manifest_sha256=COHORT_SHA,
            generation_artifact_sha256=PILOT_SHA,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            generated_items=[bundle["generated"] for bundle in bundles],
            decompositions=[bundle["decomposition"] for bundle in bundles],
            semantic_aggregate=semantic,
            instrument_lock=instrument,
            calibration_semantic_aggregate=calibration,
            additional_usage_events=additional_usage,
            manual_scoring_aggregate=manual,
        )
        is artifact
    )

    leaked = manual.model_dump(mode="json")
    leaked["notes"] = "not permitted"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ManualScoringAggregate.model_validate(leaked)


def test_decomposition_stability_reports_exact_triplets_and_population_variance() -> None:
    bundles = [_bundle(index) for index in range(1, 11)]
    repetitions = [
        tuple(
            _decomposition_with_claim_count(bundle, count)
            for count in ((1, 2, 3) if index == 1 else (1, 1, 1))
        )
        for index, bundle in enumerate(bundles, start=1)
    ]

    stability = build_decomposition_stability(
        decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
        calibration_item_ids=[bundle["item_id"] for bundle in bundles],
        repetitions=repetitions,
    )

    assert stability.schema == DECOMPOSITION_STABILITY_SCHEMA
    assert stability.items[0].claim_counts == (1, 2, 3)
    assert stability.items[0].population_variance == pytest.approx(2 / 3)
    assert stability.items[1].population_variance == 0.0
    assert stability.total_claim_count == 33
    assert stability.mean_claim_count == pytest.approx(1.1)
    assert (
        validate_decomposition_stability(
            stability,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            calibration_item_ids=[bundle["item_id"] for bundle in bundles],
            repetitions=repetitions,
        )
        is stability
    )

    tampered = stability.model_dump(mode="json")
    tampered["items"][0]["population_variance"] = 0.0
    tampered["items"][0]["item_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in tampered["items"][0].items()
            if key != "item_sha256"
        }
    )
    tampered["stability_sha256"] = canonical_json_sha256(
        {key: value for key, value in tampered.items() if key != "stability_sha256"}
    )
    with pytest.raises(ValidationError, match="population_variance"):
        DecompositionStability.model_validate(tampered)
