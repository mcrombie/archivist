from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from answer_evaluation import (
    BASELINE_NEXT_ACTION,
    CALIBRATION_LABEL_SCHEMA,
    COHORT_MANIFEST_SCHEMA,
    DECOMPOSED_PILOT_ITEM_SCHEMA,
    INSTRUMENT_LOCK_SCHEMA,
    PRIVATE_DECOMPOSITION_CHECKPOINT_SCHEMA,
    PRIVATE_GENERATION_CHECKPOINT_SCHEMA,
    PRIVATE_GENERATED_ITEM_SCHEMA,
    PUBLIC_SUMMARY_SCHEMA,
    AnswerEvaluationCohortManifest,
    CalibrationLabelFile,
    InstrumentLock,
    PrivateGeneratedItem,
    PrivateDecompositionCheckpoint,
    PrivateGenerationCheckpoint,
    PrivateTraceReference,
    PublicEvaluationSummary,
    PublicMetricId,
    build_calibration_label_template,
    build_cohort_manifest,
    build_cohort_item_binding,
    build_decomposed_claim,
    build_decomposed_pilot_item,
    build_instrument_lock,
    build_private_generated_item,
    build_private_decomposition_checkpoint,
    build_private_generation_checkpoint,
    build_private_source,
    build_private_usage_event,
    canonical_json_sha256,
    sha256_file,
    sha256_text,
    validate_calibration_labels_for_judge,
    validate_cohort_manifest,
    validate_private_decomposition_checkpoint,
    validate_private_generation_checkpoint,
    validate_public_summary,
    write_json_atomic_no_overwrite,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
PRIVATE_SENTINEL = "PRIVATE SENTINEL: Anthony Burns escaped Virginia"


def _cohort_items() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "id": f"H{index:03d}",
            "question": f"Exact held-out question {index}?",
            "stratum": "focused_biographical",
            "expected_behavior": "answer",
        }
        for index in range(1, 38)
    )


def _cohort_manifest(
    *,
    items: tuple[dict[str, object], ...] | None = None,
    calibration_ids: tuple[str, ...] | None = None,
    gold_set_sha256: str = SHA_A,
) -> AnswerEvaluationCohortManifest:
    return build_cohort_manifest(
        evaluation_id="v26-held-out-answer-quality-2026-08-07",
        candidate_commit="8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e",
        rag_policy="evidence-planned-v26",
        gold_set_sha256=gold_set_sha256,
        question_set_sha256=SHA_B,
        corpus_manifest_sha256=SHA_C,
        chunks_sha256="4" * 64,
        model_catalog_sha256="d" * 64,
        runner_sha256="e" * 64,
        items=items or _cohort_items(),
        calibration_item_ids=calibration_ids
        or tuple(f"H{index:03d}" for index in range(1, 11)),
        generator={
            "model_id": "gpt-5.6-sol",
            "settings": {"reasoning_effort": "high", "verbosity": "low"},
        },
        planner={
            "model_id": "gpt-5.6-sol",
            "settings": {"reasoning_effort": "high", "verbosity": "low"},
        },
        judge={
            "model_id": "gpt-5.6-terra",
            "settings": {"reasoning_effort": "high", "verbosity": "low"},
        },
        embedding_model="text-embedding-3-small",
        retrieval={
            "n_results": 5,
            "max_primary_distance": 1.05,
            "max_final_sources": 8,
            "hnsw_space": "l2",
            "neighbor_expansion_policy": "primaries_first_then_immediate_neighbors",
            "merge_adjacent_chunks": False,
            "collection_name": "manuscript",
            "collection_count": 481,
        },
        prompts=(
            {
                "prompt_id": "query_planner",
                "version": "query-planner-v11",
                "prompt_sha256": "f" * 64,
            },
            {
                "prompt_id": "evidence_coverage",
                "version": "evidence-coverage-v11",
                "prompt_sha256": "2" * 64,
            },
            {
                "prompt_id": "claim_decomposition",
                "version": "evaluation-claim-decomposition-v2",
                "prompt_sha256": "1" * 64,
            },
            {
                "prompt_id": "claim_evidence",
                "version": "evaluation-claim-evidence-v1",
                "prompt_sha256": "3" * 64,
            },
            {
                "prompt_id": "item_rubric",
                "version": "evaluation-item-rubric-v2",
                "prompt_sha256": "5" * 64,
            },
        ),
        structured_outputs=(
            {"output_id": "query_plan", "schema_sha256": "6" * 64},
            {"output_id": "evidence_coverage", "schema_sha256": "7" * 64},
            {"output_id": "claim_decomposition", "schema_sha256": "8" * 64},
            {"output_id": "claim_evidence", "schema_sha256": "9" * 64},
            {"output_id": "item_rubric", "schema_sha256": "0" * 64},
        ),
    )


def _generated_item() -> PrivateGeneratedItem:
    sources = (
        build_private_source(
            source_number=1,
            chunk_id="chapter_14_007",
            text=PRIVATE_SENTINEL,
            metadata={"chapter": 14, "page": 413},
        ),
        build_private_source(
            source_number=2,
            chunk_id="chapter_14_008",
            text="Federal troops enforced the Fugitive Slave Act.",
            metadata={"chapter": 14, "page": 414},
        ),
    )
    usage = build_private_usage_event(
        sequence=1,
        response_id="resp_heldout_001",
        recorded_at="2026-08-07T12:00:00+00:00",
        operation="responses.parse",
        requested_model="gpt-5.6-sol-2026-07-15",
        actual_model="gpt-5.6-sol-2026-07-15",
        input_tokens=100,
        cached_tokens=20,
        cache_write_tokens=0,
        output_tokens=40,
        reasoning_tokens=10,
        total_tokens=140,
        estimated_cost_nano_usd=1250000,
        pricing_version="openai-2026-07-15",
        unpriced=False,
    )
    trace = PrivateTraceReference(
        sequence=1,
        schema_id="archivist.retrieval_trace/1",
        trace_id="d" * 32,
        path="retrieval-traces/H001.json",
        sha256="e" * 64,
        query_sha256="f" * 64,
        retrieval_version="faceted-hybrid-rrf-v2",
    )
    return build_private_generated_item(
        item_id="H001",
        question="Who was Anthony Burns?",
        stratum="focused_biographical",
        expected_behavior="answer",
        answer="Burns escaped Virginia [Source 1].",
        status="answered",
        evidence_decision="direct_answer",
        diagnostics={"validation_result": "valid", "repair_applied": False},
        sources=sources,
        elapsed_seconds=12.5,
        usage_events=(usage,),
        trace_references=(trace,),
    )


def _decomposed_item(item: PrivateGeneratedItem):
    claim_text = "Burns escaped Virginia"
    start = item.answer.index(claim_text)
    claim = build_decomposed_claim(
        claim_id="claim.H001.1",
        text=claim_text,
        char_start=start,
        char_end=start + len(claim_text),
        cited_source_numbers=(1,),
    )
    return build_decomposed_pilot_item(
        item_id=item.item_id,
        answer_sha256=item.answer_sha256,
        claims=(claim,),
    )


def _decomposition_usage_event(*, response_id: str = "resp_decompose_001"):
    return build_private_usage_event(
        sequence=1,
        response_id=response_id,
        recorded_at="2026-08-07T12:01:00+00:00",
        operation="eval_claim_decomposition",
        requested_model="gpt-5.6-terra",
        actual_model="gpt-5.6-terra",
        input_tokens=50,
        cached_tokens=0,
        cache_write_tokens=0,
        output_tokens=20,
        reasoning_tokens=5,
        total_tokens=70,
        estimated_cost_nano_usd=250000,
        pricing_version="openai-2026-08-07",
        unpriced=False,
    )


def _decomposition_checkpoint(
    item: PrivateGeneratedItem,
    *,
    repetition: int = 1,
    cohort_manifest_sha256: str = SHA_A,
) -> PrivateDecompositionCheckpoint:
    return build_private_decomposition_checkpoint(
        cohort_manifest_sha256=cohort_manifest_sha256,
        item_id=item.item_id,
        answer_sha256=item.answer_sha256,
        repetition=repetition,
        prompt_version="evaluation-claim-decomposition-v2",
        prompt_sha256=SHA_B,
        judge_model="gpt-5.6-terra",
        judge_settings={"reasoning_effort": "medium", "verbosity": "low"},
        provider={
            "id": "resp_decompose_001",
            "model": "gpt-5.6-terra",
            "created_at": 1786118460,
            "system_fingerprint": None,
        },
        usage_event=_decomposition_usage_event(),
        decomposition=_decomposed_item(item),
    )


def _gold_item() -> dict[str, object]:
    return {
        "id": "H001",
        "claims": [
            {
                "claim_id": "H001.1",
                "text": "Anthony Burns escaped from Virginia.",
                "essential": True,
                "supporting_chunk_ids": ["chapter_14_007"],
            }
        ],
        "must_not_claim": [
            "Anthony Burns remained enslaved for the rest of his life."
        ],
    }


def _public_summary_payload() -> dict[str, object]:
    metric = {
        "metric_id": "citation_resolvability",
        "availability": "available",
        "numerator": 1,
        "denominator": 1,
        "value": 1.0,
    }
    return {
        "schema": PUBLIC_SUMMARY_SCHEMA,
        "evaluation_id": "heldout-v26-baseline-1",
        "candidate_id": "evidence-planned-v26",
        "candidate_commit": "8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e",
        "rag_policy": "evidence-planned-v26",
        "cohort_manifest_sha256": SHA_A,
        "corpus_manifest_sha256": SHA_B,
        "chunks_sha256": SHA_C,
        "question_set_sha256": SHA_A,
        "model_catalog_sha256": SHA_B,
        "runner_sha256": SHA_C,
        "planner_model_id": "gpt-5.6-sol",
        "generator_model_id": "gpt-5.6-sol",
        "judge_model_id": "gpt-5.6-terra",
        "embedding_model_id": "text-embedding-3-small",
        "private_artifact_sha256": SHA_A,
        "instrument_lock_sha256": SHA_B,
        "gold_set_sha256": SHA_C,
        "limitation_ids": [
            "canonical_current_model_ids_are_not_immutable_snapshots",
            "generator_output_variance_not_measured",
            "evaluation_is_descriptive_not_a_release_gate",
        ],
        "run_status": "partial",
        "scoring_mode": "manual",
        "item_count": 1,
        "source_count": 2,
        "claim_count": 1,
        "citation_count": 1,
        "error_count": 0,
        "metrics": [metric],
        "strata": [
            {
                "stratum": "focused_biographical",
                "item_count": 1,
                "metrics": [metric],
            }
        ],
        "cost": {
            "estimated_cost_usd": 0.125,
            "priced_event_count": 1,
            "unpriced_event_count": 0,
        },
        "latency": {
            "total_seconds": 12.5,
            "mean_seconds": 12.5,
            "p50_seconds": 12.5,
            "p95_seconds": 12.5,
            "maximum_seconds": 12.5,
        },
    }


def _complete_public_summary_payload() -> dict[str, object]:
    payload = _public_summary_payload()
    payload["run_status"] = "complete"
    payload["item_count"] = 37
    payload["error_count"] = 0
    payload["metrics"] = [
        {
            "metric_id": metric_id.value,
            "availability": "available",
            "numerator": 1,
            "denominator": 1,
            "value": 1.0,
        }
        for metric_id in PublicMetricId
    ]
    payload["strata"] = [
        {"stratum": "focused_biographical", "item_count": 8, "metrics": []},
        {"stratum": "focused_analytical", "item_count": 8, "metrics": []},
        {"stratum": "conceptual", "item_count": 5, "metrics": []},
        {"stratum": "broad_thematic", "item_count": 10, "metrics": []},
        {"stratum": "out_of_corpus", "item_count": 4, "metrics": []},
        {"stratum": "adversarial_premise", "item_count": 2, "metrics": []},
    ]
    return payload


def _instrument_lock(
    *,
    agreements: dict[str, tuple[float, int]] | None = None,
    repeat_agreement: float = 0.95,
    instrument_id: str = "heldout-v26-instrument-1",
) -> InstrumentLock:
    dimensions = agreements or {
        "faithfulness": (0.90, 10),
        "cited_source_support": (0.90, 10),
        "claim_mapping": (0.90, 10),
        "gold_status": (0.90, 10),
        "must_not_tripwires": (0.90, 10),
        "response_behavior": (0.90, 10),
    }
    denominator = sum(value[1] for value in dimensions.values())
    pooled = sum(value[0] * value[1] for value in dimensions.values()) / denominator
    return build_instrument_lock(
        instrument_id=instrument_id,
        cohort_manifest_sha256="1" * 64,
        pilot_artifact_sha256=SHA_A,
        decomposition_artifact_sha256="2" * 64,
        human_labels_sha256=SHA_B,
        judge_results_sha256=SHA_C,
        judge_model="gpt-5.6-terra",
        judge_settings={"reasoning_effort": "medium", "verbosity": "low"},
        decomposition_prompt_sha256="3" * 64,
        evidence_prompt_sha256="4" * 64,
        rubric_prompt_sha256="5" * 64,
        pooled_agreement=pooled,
        repeat_agreement=repeat_agreement,
        dimension_agreements=dimensions,
    )


def test_private_generated_item_binds_exact_text_sources_order_and_types() -> None:
    item = _generated_item()

    assert item.schema == PRIVATE_GENERATED_ITEM_SCHEMA
    assert item.question_sha256 == sha256_text(item.question)
    assert item.answer_sha256 == sha256_text(item.answer)
    assert [source.source_number for source in item.sources] == [1, 2]
    assert item.item_sha256 == canonical_json_sha256(
        item.model_dump(mode="json", exclude={"item_sha256"})
    )

    mutated_question = item.model_dump(mode="json")
    mutated_question["question"] = "A different question"
    with pytest.raises(ValidationError, match="question_sha256"):
        PrivateGeneratedItem.model_validate(mutated_question)

    mutated_answer = item.model_dump(mode="json")
    mutated_answer["answer"] = "A different answer"
    with pytest.raises(ValidationError, match="answer_sha256"):
        PrivateGeneratedItem.model_validate(mutated_answer)

    mutated_source = item.model_dump(mode="json")
    mutated_source["sources"][0]["text"] = "Changed private source text"
    with pytest.raises(ValidationError, match="text_sha256"):
        PrivateGeneratedItem.model_validate(mutated_source)

    reordered = item.model_dump(mode="json")
    reordered["sources"].reverse()
    with pytest.raises(ValidationError, match="ordered 1..N"):
        PrivateGeneratedItem.model_validate(reordered)

    wrong_type = item.model_dump(mode="json")
    wrong_type["sources"][0]["source_number"] = "1"
    with pytest.raises(ValidationError, match="source_number"):
        PrivateGeneratedItem.model_validate(wrong_type)


@pytest.mark.parametrize("status", ["clean_abstention", "corpus_integrity_failed"])
def test_private_generated_item_preserves_frozen_v26_status(status: str) -> None:
    item = _generated_item().model_dump(mode="json")
    item["status"] = status
    item["item_sha256"] = canonical_json_sha256(
        {key: value for key, value in item.items() if key != "item_sha256"}
    )

    validated = PrivateGeneratedItem.model_validate(item)

    assert validated.status.value == status
    assert validated.model_dump(mode="json")["status"] == status


def test_generation_checkpoint_is_closed_deterministic_and_externally_bound() -> None:
    item = _generated_item()
    expected_item = build_cohort_item_binding(
        item_id=item.item_id,
        question=item.question,
        stratum=item.stratum,
        expected_behavior=item.expected_behavior,
    )
    checkpoint = build_private_generation_checkpoint(
        cohort_manifest_sha256=SHA_A,
        item=item,
    )

    assert checkpoint.schema == PRIVATE_GENERATION_CHECKPOINT_SCHEMA
    assert checkpoint.item == item
    assert checkpoint == build_private_generation_checkpoint(
        cohort_manifest_sha256=SHA_A,
        item=item,
    )
    assert (
        validate_private_generation_checkpoint(
            checkpoint,
            cohort_manifest_sha256=SHA_A,
            expected_item=expected_item,
        )
        is checkpoint
    )

    copied_binding = build_cohort_item_binding(
        item_id="H002",
        question=item.question,
        stratum=item.stratum,
        expected_behavior=item.expected_behavior,
    )
    with pytest.raises(ValueError, match="another cohort item"):
        validate_private_generation_checkpoint(
            checkpoint,
            cohort_manifest_sha256=SHA_A,
            expected_item=copied_binding,
        )
    with pytest.raises(ValueError, match="another cohort manifest"):
        validate_private_generation_checkpoint(
            checkpoint,
            cohort_manifest_sha256=SHA_B,
            expected_item=expected_item,
        )

    unknown = checkpoint.model_dump(mode="json")
    unknown["item"]["unexpected"] = "copied state"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PrivateGenerationCheckpoint.model_validate(unknown)


def test_decomposition_checkpoint_binds_provider_usage_prompt_and_answer() -> None:
    generated = _generated_item()
    checkpoint = _decomposition_checkpoint(generated)

    assert checkpoint.schema == PRIVATE_DECOMPOSITION_CHECKPOINT_SCHEMA
    assert checkpoint.provider.response_id == "resp_decompose_001"
    assert len(checkpoint.usage_events) == 1
    assert checkpoint.decomposition.item_id == generated.item_id
    assert checkpoint == _decomposition_checkpoint(generated)
    assert (
        validate_private_decomposition_checkpoint(
            checkpoint,
            cohort_manifest_sha256=SHA_A,
            generated_item=generated,
            repetition=1,
            prompt_version="evaluation-claim-decomposition-v2",
            prompt_sha256=SHA_B,
            judge_model="gpt-5.6-terra",
            judge_settings={"reasoning_effort": "medium", "verbosity": "low"},
        )
        is checkpoint
    )

    with pytest.raises(ValueError, match="prompt_version changed"):
        validate_private_decomposition_checkpoint(
            checkpoint,
            cohort_manifest_sha256=SHA_A,
            generated_item=generated,
            repetition=1,
            prompt_version="evaluation-claim-decomposition-v3",
            prompt_sha256=SHA_B,
            judge_model="gpt-5.6-terra",
            judge_settings={"reasoning_effort": "medium", "verbosity": "low"},
        )

    with pytest.raises(ValueError, match="cohort_manifest_sha256 changed"):
        validate_private_decomposition_checkpoint(
            checkpoint,
            cohort_manifest_sha256=SHA_C,
            generated_item=generated,
            repetition=1,
            prompt_version="evaluation-claim-decomposition-v2",
            prompt_sha256=SHA_B,
            judge_model="gpt-5.6-terra",
            judge_settings={"reasoning_effort": "medium", "verbosity": "low"},
        )

    changed_answer = generated.model_dump(mode="json")
    changed_answer["answer"] = "A response copied from another item."
    changed_answer["answer_sha256"] = sha256_text(changed_answer["answer"])
    changed_answer["item_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in changed_answer.items()
            if key != "item_sha256"
        }
    )
    with pytest.raises(ValueError, match="answer_sha256 changed"):
        validate_private_decomposition_checkpoint(
            checkpoint,
            cohort_manifest_sha256=SHA_A,
            generated_item=PrivateGeneratedItem.model_validate(changed_answer),
            repetition=1,
            prompt_version="evaluation-claim-decomposition-v2",
            prompt_sha256=SHA_B,
            judge_model="gpt-5.6-terra",
            judge_settings={"reasoning_effort": "medium", "verbosity": "low"},
        )


def test_decomposition_checkpoint_rejects_copied_or_ambiguous_call_state() -> None:
    generated = _generated_item()
    checkpoint = _decomposition_checkpoint(generated)

    wrong_provider = checkpoint.model_dump(mode="json")
    wrong_provider["provider"]["id"] = "resp_from_another_call"
    wrong_provider["checkpoint_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in wrong_provider.items()
            if key != "checkpoint_sha256"
        }
    )
    with pytest.raises(ValidationError, match="provider and usage response IDs differ"):
        PrivateDecompositionCheckpoint.model_validate(wrong_provider)

    extra_usage = checkpoint.model_dump(mode="json")
    second_event = _decomposition_usage_event(response_id="resp_decompose_002").model_dump(
        mode="json"
    )
    second_event["sequence"] = 2
    second_event["event_sha256"] = canonical_json_sha256(
        {key: value for key, value in second_event.items() if key != "event_sha256"}
    )
    extra_usage["usage_events"].append(second_event)
    extra_usage["checkpoint_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in extra_usage.items()
            if key != "checkpoint_sha256"
        }
    )
    with pytest.raises(ValidationError, match="at most 1 item"):
        PrivateDecompositionCheckpoint.model_validate(extra_usage)

    unknown_provider = checkpoint.model_dump(mode="json")
    unknown_provider["provider"]["raw_response"] = PRIVATE_SENTINEL
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PrivateDecompositionCheckpoint.model_validate(unknown_provider)


@pytest.mark.parametrize("repetition", [0, 4])
def test_decomposition_checkpoint_repetition_is_limited_to_three(
    repetition: int,
) -> None:
    with pytest.raises(ValidationError, match="repetition"):
        _decomposition_checkpoint(_generated_item(), repetition=repetition)


def test_cohort_manifest_closes_exact_37_item_partition_and_runtime_identity() -> None:
    manifest = _cohort_manifest()

    assert manifest.schema == COHORT_MANIFEST_SCHEMA
    assert len(manifest.items) == 37
    assert manifest.calibration_item_ids == tuple(
        f"H{index:03d}" for index in range(1, 11)
    )
    assert manifest.remaining_item_ids == tuple(
        f"H{index:03d}" for index in range(11, 38)
    )
    assert manifest.calibration_items_immutable is True
    assert manifest.remaining_phase_may_regenerate_calibration is False
    assert manifest.generator.model_id == "gpt-5.6-sol"
    assert manifest.planner.settings["reasoning_effort"] == "high"
    assert manifest.judge.model_id == "gpt-5.6-terra"
    assert manifest.chunks_sha256 == "4" * 64
    assert manifest.embedding_model == "text-embedding-3-small"
    assert manifest.retrieval.n_results == 5
    assert manifest.retrieval.max_primary_distance == 1.05
    assert manifest.retrieval.max_final_sources == 8
    assert manifest.retrieval.collection_name == "manuscript"
    assert manifest.retrieval.collection_count == 481
    assert manifest.retrieval.hnsw_space == "l2"
    assert (
        manifest.retrieval.neighbor_expansion_policy
        == "primaries_first_then_immediate_neighbors"
    )
    assert manifest.retrieval.merge_adjacent_chunks is False
    assert {
        prompt.prompt_id: (prompt.version, prompt.prompt_sha256)
        for prompt in manifest.prompts
    } == {
        "query_planner": ("query-planner-v11", "f" * 64),
        "evidence_coverage": ("evidence-coverage-v11", "2" * 64),
        "claim_decomposition": (
            "evaluation-claim-decomposition-v2",
            "1" * 64,
        ),
        "claim_evidence": ("evaluation-claim-evidence-v1", "3" * 64),
        "item_rubric": ("evaluation-item-rubric-v2", "5" * 64),
    }
    assert {
        output.output_id: output.schema_sha256
        for output in manifest.structured_outputs
    } == {
        "query_plan": "6" * 64,
        "evidence_coverage": "7" * 64,
        "claim_decomposition": "8" * 64,
        "claim_evidence": "9" * 64,
        "item_rubric": "0" * 64,
    }
    assert (
        manifest.model_identity_limitation
        == "canonical_provider_ids_are_not_immutable_snapshots"
    )
    assert manifest.manifest_sha256 == canonical_json_sha256(
        manifest.model_dump(mode="json", exclude={"manifest_sha256"})
    )
    assert _cohort_manifest().model_dump(mode="json") == manifest.model_dump(
        mode="json"
    )


def test_cohort_manifest_rejects_intrinsic_question_hash_and_partition_mutation() -> None:
    manifest = _cohort_manifest()
    changed_question = manifest.model_dump(mode="json")
    changed_question["items"][0]["question_sha256"] = "2" * 64
    changed_question["manifest_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in changed_question.items()
            if key != "manifest_sha256"
        }
    )
    with pytest.raises(ValidationError, match="item binding_sha256"):
        AnswerEvaluationCohortManifest.model_validate(changed_question)

    changed_partition = manifest.model_dump(mode="json")
    changed_partition["calibration_item_ids"][-1] = "H011"
    changed_partition["manifest_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in changed_partition.items()
            if key != "manifest_sha256"
        }
    )
    with pytest.raises(ValidationError, match="remaining_item_ids"):
        AnswerEvaluationCohortManifest.model_validate(changed_partition)

    changed_retrieval = manifest.model_dump(mode="json")
    changed_retrieval["retrieval"]["n_results"] = 6
    changed_retrieval["retrieval"]["binding_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in changed_retrieval["retrieval"].items()
            if key != "binding_sha256"
        }
    )
    changed_retrieval["manifest_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in changed_retrieval.items()
            if key != "manifest_sha256"
        }
    )
    with pytest.raises(ValidationError, match="n_results"):
        AnswerEvaluationCohortManifest.model_validate(changed_retrieval)

    missing_schema = manifest.model_dump(mode="json")
    missing_schema["structured_outputs"].pop()
    with pytest.raises(ValidationError, match="at least 5 items"):
        AnswerEvaluationCohortManifest.model_validate(missing_schema)


def test_cohort_manifest_external_validation_rejects_rehashed_substitution() -> None:
    expected = _cohort_manifest()
    reversed_items = tuple(reversed(_cohort_items()))
    reversed_calibration = tuple(f"H{index:03d}" for index in range(10, 0, -1))
    reordered = _cohort_manifest(
        items=reversed_items,
        calibration_ids=reversed_calibration,
    )
    changed_partition = _cohort_manifest(
        calibration_ids=tuple(
            [*(f"H{index:03d}" for index in range(1, 10)), "H011"]
        )
    )
    changed_hash = _cohort_manifest(gold_set_sha256="3" * 64)

    changed_chunks = expected.model_dump(mode="json")
    changed_chunks["chunks_sha256"] = "7" * 64
    changed_chunks["manifest_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in changed_chunks.items()
            if key != "manifest_sha256"
        }
    )
    changed_chunks_manifest = AnswerEvaluationCohortManifest.model_validate(
        changed_chunks
    )

    changed_prompt = expected.model_dump(mode="json")
    changed_prompt["prompts"][0]["prompt_sha256"] = "8" * 64
    changed_prompt["prompts"][0]["binding_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in changed_prompt["prompts"][0].items()
            if key != "binding_sha256"
        }
    )
    changed_prompt["manifest_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in changed_prompt.items()
            if key != "manifest_sha256"
        }
    )
    changed_prompt_manifest = AnswerEvaluationCohortManifest.model_validate(
        changed_prompt
    )

    changed_output = expected.model_dump(mode="json")
    changed_output["structured_outputs"][0]["schema_sha256"] = "9" * 64
    changed_output["structured_outputs"][0]["binding_sha256"] = (
        canonical_json_sha256(
            {
                key: value
                for key, value in changed_output["structured_outputs"][0].items()
                if key != "binding_sha256"
            }
        )
    )
    changed_output["manifest_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in changed_output.items()
            if key != "manifest_sha256"
        }
    )
    changed_output_manifest = AnswerEvaluationCohortManifest.model_validate(
        changed_output
    )

    assert validate_cohort_manifest(expected, expected=expected) is expected
    for substitute in (
        reordered,
        changed_partition,
        changed_hash,
        changed_chunks_manifest,
        changed_prompt_manifest,
        changed_output_manifest,
    ):
        with pytest.raises(ValueError, match="exact frozen evaluation inputs"):
            validate_cohort_manifest(substitute, expected=expected)


def test_cohort_manifest_is_ready_for_atomic_no_overwrite_publication() -> None:
    test_root = Path("tmp") / f"cohort-manifest-{uuid4().hex}"
    path = test_root / "cohort-manifest.json"
    try:
        manifest = _cohort_manifest()
        artifact_sha256 = write_json_atomic_no_overwrite(path, manifest)
        assert artifact_sha256 == sha256_file(path)
        with pytest.raises(FileExistsError, match="Refusing to overwrite"):
            write_json_atomic_no_overwrite(path, manifest)
    finally:
        path.unlink(missing_ok=True)
        test_root.rmdir()


def test_private_nested_models_reject_unknown_fields_and_are_frozen() -> None:
    item = _generated_item()
    unknown = item.model_dump(mode="json")
    unknown["sources"][0]["unexpected"] = PRIVATE_SENTINEL
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PrivateGeneratedItem.model_validate(unknown)

    with pytest.raises(ValidationError, match="frozen"):
        item.answer = "mutation"  # type: ignore[misc]


def test_calibration_template_is_nullable_then_requires_complete_bound_labels() -> None:
    item = _generated_item()
    decomposition = _decomposed_item(item)
    template = build_calibration_label_template(
        generated_items=(item,),
        decomposed_items=(decomposition,),
        gold_items=(_gold_item(),),
        pilot_artifact_sha256=SHA_A,
        decomposition_artifact_sha256=SHA_B,
    )

    assert template.schema == CALIBRATION_LABEL_SCHEMA
    assert template.items[0].response_behavior is None
    assert template.items[0].claims[0].faithfulness is None
    with pytest.raises(ValueError, match="response_behavior"):
        validate_calibration_labels_for_judge(
            template,
            generated_items=(item,),
            decomposed_items=(decomposition,),
            gold_items=(_gold_item(),),
            pilot_artifact_sha256=SHA_A,
            decomposition_artifact_sha256=SHA_B,
        )

    completed = template.model_dump(mode="json")
    completed["items"][0]["response_behavior"] = "substantive_answer"
    claim_label = completed["items"][0]["claims"][0]
    claim_label["faithfulness"] = "supported"
    claim_label["gold_match_ids"] = ["H001.1"]
    claim_label["cited_source_labels"] = {"1": "supported"}
    completed["items"][0]["gold_claim_statuses"][0]["status"] = "present"
    completed["items"][0]["must_not_claim_statuses"][0]["status"] = "not_asserted"
    validated = validate_calibration_labels_for_judge(
        completed,
        generated_items=(item,),
        decomposed_items=(decomposition,),
        gold_items=(_gold_item(),),
        pilot_artifact_sha256=SHA_A,
        decomposition_artifact_sha256=SHA_B,
    )
    assert validated.items[0].claims[0].gold_match_ids == ("H001.1",)

    missing_gold_status = validated.model_dump(mode="json")
    missing_gold_status["items"][0]["gold_claim_statuses"][0]["status"] = None
    with pytest.raises(ValueError, match="gold claim status is not labelled"):
        validate_calibration_labels_for_judge(
            missing_gold_status,
            generated_items=(item,),
            decomposed_items=(decomposition,),
            gold_items=(_gold_item(),),
            pilot_artifact_sha256=SHA_A,
            decomposition_artifact_sha256=SHA_B,
        )

    missing_must_not_status = validated.model_dump(mode="json")
    missing_must_not_status["items"][0]["must_not_claim_statuses"][0]["status"] = None
    with pytest.raises(ValueError, match="must-not-claim status 0 is not labelled"):
        validate_calibration_labels_for_judge(
            missing_must_not_status,
            generated_items=(item,),
            decomposed_items=(decomposition,),
            gold_items=(_gold_item(),),
            pilot_artifact_sha256=SHA_A,
            decomposition_artifact_sha256=SHA_B,
        )

    wrong_binding = validated.model_dump(mode="json")
    wrong_binding["items"][0]["answer_sha256"] = SHA_C
    with pytest.raises(ValueError, match="answer hash binding changed"):
        validate_calibration_labels_for_judge(
            wrong_binding,
            generated_items=(item,),
            decomposed_items=(decomposition,),
            gold_items=(_gold_item(),),
            pilot_artifact_sha256=SHA_A,
            decomposition_artifact_sha256=SHA_B,
        )

    changed_rubric = _gold_item()
    changed_rubric["claims"][0]["text"] = "A changed owner rubric claim."
    with pytest.raises(ValueError, match="gold rubric hash binding changed"):
        validate_calibration_labels_for_judge(
            validated,
            generated_items=(item,),
            decomposed_items=(decomposition,),
            gold_items=(changed_rubric,),
            pilot_artifact_sha256=SHA_A,
            decomposition_artifact_sha256=SHA_B,
        )


def test_calibration_rejects_decomposition_or_claim_mutation() -> None:
    item = _generated_item()
    decomposition = _decomposed_item(item)
    mutated = decomposition.model_dump(mode="json")
    mutated["claims"][0]["text"] = "Burns remained in Virginia"
    with pytest.raises(ValidationError, match="claim_sha256"):
        build_calibration_label_template(
            generated_items=(item,),
            decomposed_items=(mutated,),
            gold_items=(_gold_item(),),
            pilot_artifact_sha256=SHA_A,
            decomposition_artifact_sha256=SHA_B,
        )


def test_instrument_lock_binds_identity_and_uses_dimension_level_fallbacks() -> None:
    eligible = _instrument_lock()
    assert eligible.schema == INSTRUMENT_LOCK_SCHEMA
    assert eligible.scoring_mode.value == "judge"
    assert eligible.baseline_next_action == BASELINE_NEXT_ACTION
    assert eligible.cohort_manifest_sha256 == "1" * 64
    assert eligible.decomposition_artifact_sha256 == "2" * 64
    assert eligible.judge_model == "gpt-5.6-terra"
    assert eligible.instrument_sha256 == canonical_json_sha256(
        eligible.model_dump(mode="json", exclude={"instrument_sha256"})
    )

    mixed = _instrument_lock(
        agreements={
            "faithfulness": (0.79, 10),
            "cited_source_support": (0.90, 10),
            "claim_mapping": (0.90, 10),
            "gold_status": (0.90, 10),
            "must_not_tripwires": (0.90, 10),
            "response_behavior": (0.90, 10),
        },
        instrument_id="heldout-v26-instrument-2",
    )
    assert mixed.scoring_mode.value == "mixed"
    modes = {entry.dimension.value: entry.scoring_mode.value for entry in mixed.dimensions}
    assert modes["faithfulness"] == "manual"
    assert all(mode == "judge" for key, mode in modes.items() if key != "faithfulness")
    assert mixed.baseline_next_action == "complete_37_question_evaluation"

    invalid = mixed.model_dump(mode="json")
    invalid["dimensions"][1]["scoring_mode"] = "manual"
    invalid["instrument_sha256"] = canonical_json_sha256(
        {key: value for key, value in invalid.items() if key != "instrument_sha256"}
    )
    with pytest.raises(ValidationError, match="only affected"):
        InstrumentLock.model_validate(invalid)

    invalid_action = mixed.model_dump(mode="json")
    invalid_action["baseline_next_action"] = "delay_baseline"
    with pytest.raises(ValidationError, match="complete_37_question_evaluation"):
        InstrumentLock.model_validate(invalid_action)


def test_instrument_lock_repeat_failure_falls_all_dimensions_back_to_manual() -> None:
    fallback = _instrument_lock(repeat_agreement=0.89)

    assert fallback.scoring_mode.value == "manual"
    assert fallback.judge_eligibility.eligible is False
    assert all(entry.scoring_mode.value == "manual" for entry in fallback.dimensions)


def test_instrument_lock_rejects_pooled_agreement_or_prompt_hash_mutation() -> None:
    lock = _instrument_lock()
    bad_pool = lock.model_dump(mode="json")
    bad_pool["judge_eligibility"]["pooled_agreement"] = 0.80
    bad_pool["judge_eligibility"]["eligible"] = True
    bad_pool["instrument_sha256"] = canonical_json_sha256(
        {key: value for key, value in bad_pool.items() if key != "instrument_sha256"}
    )
    with pytest.raises(ValidationError, match="dimension-weighted"):
        InstrumentLock.model_validate(bad_pool)

    bad_prompt = lock.model_dump(mode="json")
    bad_prompt["evidence_prompt_sha256"] = "6" * 64
    with pytest.raises(ValidationError, match="instrument_sha256"):
        InstrumentLock.model_validate(bad_prompt)


def test_public_summary_is_recursively_closed_and_text_free() -> None:
    summary = validate_public_summary(_public_summary_payload())
    serialized = json.dumps(summary.model_dump(mode="json"), sort_keys=True)
    assert summary.schema == PUBLIC_SUMMARY_SCHEMA
    assert PRIVATE_SENTINEL not in serialized

    leaked = _public_summary_payload()
    leaked["strata"][0]["answer"] = PRIVATE_SENTINEL
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_public_summary(leaked)

    unknown_nested = _public_summary_payload()
    unknown_nested["metrics"][0]["notes"] = "looks good"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_public_summary(unknown_nested)

    prose_in_identifier = _public_summary_payload()
    prose_in_identifier["candidate_id"] = PRIVATE_SENTINEL
    with pytest.raises(ValidationError, match="candidate_id"):
        PublicEvaluationSummary.model_validate(prose_in_identifier)


def test_public_summary_rejects_invalid_zero_denominator_and_nested_counts() -> None:
    invalid_ratio = _public_summary_payload()
    invalid_ratio["metrics"][0] = {
        "metric_id": "citation_resolvability",
        "availability": "available",
        "numerator": 0,
        "denominator": 0,
        "value": 0.0,
    }
    with pytest.raises(ValidationError, match="zero-denominator"):
        validate_public_summary(invalid_ratio)

    invalid_total = _public_summary_payload()
    invalid_total["strata"][0]["item_count"] = 2
    with pytest.raises(ValidationError, match="sum to item_count"):
        validate_public_summary(invalid_total)


def test_complete_public_summary_requires_exact_cohort_and_all_metrics() -> None:
    complete = validate_public_summary(_complete_public_summary_payload())
    assert complete.item_count == 37
    assert len(complete.metrics) == len(PublicMetricId)

    wrong_count = _complete_public_summary_payload()
    wrong_count["item_count"] = 36
    wrong_count["strata"][0]["item_count"] = 7
    with pytest.raises(ValidationError, match="exactly 37"):
        validate_public_summary(wrong_count)

    wrong_stratum = _complete_public_summary_payload()
    wrong_stratum["strata"][0]["item_count"] = 7
    wrong_stratum["strata"][1]["item_count"] = 9
    with pytest.raises(ValidationError, match="8/8/5/10/4/2"):
        validate_public_summary(wrong_stratum)

    missing_metric = _complete_public_summary_payload()
    missing_metric["metrics"].pop()
    with pytest.raises(ValidationError, match="every required metric"):
        validate_public_summary(missing_metric)


def test_public_semantic_metric_can_be_pending_with_real_denominator() -> None:
    payload = _complete_public_summary_payload()
    faithfulness = next(
        metric
        for metric in payload["metrics"]
        if metric["metric_id"] == "faithfulness_supported"
    )
    faithfulness.update(
        {
            "availability": "pending",
            "numerator": None,
            "denominator": 42,
            "value": None,
        }
    )
    summary = validate_public_summary(payload)
    pending = next(
        metric
        for metric in summary.metrics
        if metric.metric_id.value == "faithfulness_supported"
    )
    assert pending.availability.value == "pending"
    assert pending.denominator == 42

    zero_denominator = payload.copy()
    zero_denominator["metrics"] = [dict(metric) for metric in payload["metrics"]]
    pending_raw = next(
        metric
        for metric in zero_denominator["metrics"]
        if metric["metric_id"] == "faithfulness_supported"
    )
    pending_raw["denominator"] = 0
    with pytest.raises(ValidationError, match="real positive denominator"):
        validate_public_summary(zero_denominator)


def test_atomic_writer_refuses_overwrite_and_returns_file_hash() -> None:
    test_root = Path("tmp") / f"answer-evaluation-{uuid4().hex}"
    path = test_root / "private" / "H001.json"
    try:
        item = _generated_item()
        written_sha = write_json_atomic_no_overwrite(path, item)

        assert path.is_file()
        assert written_sha == sha256_file(path)
        original = path.read_bytes()
        with pytest.raises(FileExistsError, match="Refusing to overwrite"):
            write_json_atomic_no_overwrite(path, {"replacement": True})
        assert path.read_bytes() == original
    finally:
        path.unlink(missing_ok=True)
        path.parent.rmdir()
        test_root.rmdir()


def test_schema_constants_are_not_interchangeable() -> None:
    assert len(
        {
            PRIVATE_GENERATED_ITEM_SCHEMA,
            DECOMPOSED_PILOT_ITEM_SCHEMA,
            CALIBRATION_LABEL_SCHEMA,
            INSTRUMENT_LOCK_SCHEMA,
            PUBLIC_SUMMARY_SCHEMA,
            COHORT_MANIFEST_SCHEMA,
            PRIVATE_GENERATION_CHECKPOINT_SCHEMA,
            PRIVATE_DECOMPOSITION_CHECKPOINT_SCHEMA,
        }
    ) == 8
    invalid = _public_summary_payload()
    invalid["schema"] = PRIVATE_GENERATED_ITEM_SCHEMA
    with pytest.raises(ValidationError, match="public_summary"):
        validate_public_summary(invalid)

    label_payload = {
        "schema": CALIBRATION_LABEL_SCHEMA,
        "pilot_artifact_sha256": SHA_A,
        "decomposition_artifact_sha256": SHA_B,
        "items": [],
    }
    assert CalibrationLabelFile.model_validate(label_payload).schema == CALIBRATION_LABEL_SCHEMA
