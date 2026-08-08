from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pytest

from answer_evaluation import (
    CalibrationItemLabel,
    EvaluationStratum,
    PublicLimitationId,
    PublicMetricId,
    ScoringDimension,
    build_cohort_manifest,
    build_decomposed_claim,
    build_decomposed_pilot_item,
    build_instrument_lock,
    build_private_generated_item,
    build_private_source,
    build_private_usage_event,
    canonical_json_bytes,
    canonical_json_sha256,
    sha256_text,
)
from evaluation_judge import ItemRubricInput
from evaluation_reporting import (
    build_public_evaluation_summary,
    render_public_evaluation_markdown,
)
from evaluation_results import (
    build_baseline_semantic_aggregate,
    build_baseline_semantic_item,
    build_calibration_semantic_aggregate,
    build_calibration_semantic_item,
    build_claim_evidence_result,
    build_item_rubric_result,
    build_manual_scoring_aggregate,
    build_private_full_run_artifact,
)


GOLD_SHA = "b" * 64
DECOMPOSITION_PROMPT_SHA = "c" * 64
EVIDENCE_PROMPT_SHA = "d" * 64
RUBRIC_PROMPT_SHA = "e" * 64
PILOT_ARTIFACT_SHA = "1" * 64
CALIBRATION_DECOMPOSITION_ARTIFACT_SHA = "2" * 64
GENERATION_ARTIFACT_SHA = "5" * 64
DECOMPOSITION_ARTIFACT_SHA = "6" * 64
JUDGE_MODEL = "gpt-5.6-terra"
JUDGE_SETTINGS = {"reasoning_effort": "medium", "verbosity": "low"}
PRIVATE_SENTINEL = "PRIVATE MANUSCRIPT PASSAGE THAT MUST NOT REACH THE SUMMARY"


@dataclass(frozen=True)
class _Fixture:
    generated: tuple[Any, ...]
    decompositions: tuple[Any, ...]
    gold: tuple[dict[str, object], ...]
    evidence: tuple[Any, ...]
    rubrics: tuple[Any, ...]
    rubric_inputs: tuple[ItemRubricInput, ...]


def _stratum(index: int) -> EvaluationStratum:
    if index <= 8:
        return EvaluationStratum.FOCUSED_BIOGRAPHICAL
    if index <= 16:
        return EvaluationStratum.FOCUSED_ANALYTICAL
    if index <= 21:
        return EvaluationStratum.CONCEPTUAL
    if index <= 31:
        return EvaluationStratum.BROAD_THEMATIC
    if index <= 35:
        return EvaluationStratum.OUT_OF_CORPUS
    return EvaluationStratum.ADVERSARIAL_PREMISE


def _cohort_manifest():
    items = tuple(
        {
            "id": f"H{index:03d}",
            "question": f"Private evaluation question H{index:03d}?",
            "stratum": _stratum(index).value,
            "expected_behavior": (
                "abstain"
                if _stratum(index) is EvaluationStratum.OUT_OF_CORPUS
                else "answer"
            ),
        }
        for index in range(1, 38)
    )
    return build_cohort_manifest(
        evaluation_id="heldout-v26-baseline-1",
        candidate_commit="8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e",
        rag_policy="evidence-planned-v26",
        gold_set_sha256=GOLD_SHA,
        question_set_sha256="7" * 64,
        corpus_manifest_sha256="8" * 64,
        chunks_sha256="9" * 64,
        model_catalog_sha256="a" * 64,
        runner_sha256="f" * 64,
        items=items,
        calibration_item_ids=tuple(f"H{index:03d}" for index in range(1, 11)),
        generator={
            "model_id": "gpt-5.6-sol",
            "settings": {"reasoning_effort": "high", "verbosity": "low"},
        },
        planner={
            "model_id": "gpt-5.6-sol",
            "settings": {"reasoning_effort": "high", "verbosity": "low"},
        },
        judge={"model_id": JUDGE_MODEL, "settings": JUDGE_SETTINGS},
        embedding_model="text-embedding-3-small",
        retrieval={
            "collection_name": "manuscript",
            "collection_count": 481,
        },
        prompts=(
            {
                "prompt_id": "query_planner",
                "version": "query-planner-v11",
                "prompt_sha256": "0" * 64,
            },
            {
                "prompt_id": "evidence_coverage",
                "version": "evidence-coverage-v11",
                "prompt_sha256": "1" * 64,
            },
            {
                "prompt_id": "claim_decomposition",
                "version": "evaluation-claim-decomposition-v2",
                "prompt_sha256": DECOMPOSITION_PROMPT_SHA,
            },
            {
                "prompt_id": "claim_evidence",
                "version": "evaluation-claim-evidence-v1",
                "prompt_sha256": EVIDENCE_PROMPT_SHA,
            },
            {
                "prompt_id": "item_rubric",
                "version": "evaluation-item-rubric-v2",
                "prompt_sha256": RUBRIC_PROMPT_SHA,
            },
        ),
        structured_outputs=tuple(
            {
                "output_id": output_id,
                "schema_sha256": f"{index:x}" * 64,
            }
            for index, output_id in enumerate(
                (
                    "query_plan",
                    "evidence_coverage",
                    "claim_decomposition",
                    "claim_evidence",
                    "item_rubric",
                ),
                start=1,
            )
        ),
    )


COHORT_MANIFEST = _cohort_manifest()
COHORT_SHA = hashlib.sha256(
    canonical_json_bytes(COHORT_MANIFEST, pretty=True)
).hexdigest()


def _usage(*, response_id: str, operation: str, model: str):
    return build_private_usage_event(
        sequence=1,
        response_id=response_id,
        recorded_at="2026-08-07T18:00:00+00:00",
        operation=operation,
        requested_model=model,
        actual_model=model,
        input_tokens=80,
        cached_tokens=0,
        cache_write_tokens=0,
        output_tokens=20,
        reasoning_tokens=5,
        total_tokens=100,
        estimated_cost_nano_usd=1_000_000,
        pricing_version="openai-2026-08-07",
        unpriced=False,
    )


def _provider(response_id: str) -> dict[str, object]:
    return {
        "id": response_id,
        "model": JUDGE_MODEL,
        "created_at": 1_786_118_400,
        "system_fingerprint": "fp_reporting",
    }


def _make_fixture(*, insufficient_evidence_item: int | None = None) -> _Fixture:
    generated_items = []
    decompositions = []
    gold_items: list[dict[str, object]] = []
    evidence_results = []
    rubric_results = []
    rubric_inputs = []
    for index in range(1, 38):
        item_id = f"H{index:03d}"
        question = f"Private evaluation question {item_id}?"
        stratum = _stratum(index)
        out_of_corpus = stratum is EvaluationStratum.OUT_OF_CORPUS
        source = build_private_source(
            source_number=1,
            chunk_id=f"chapter_{index:02d}_001",
            text=f"{PRIVATE_SENTINEL} {item_id}",
            metadata={"chapter": index},
        )
        claims = []
        if out_of_corpus:
            answer = "The requested material is not found in this corpus."
            status = "clean_abstention"
            evidence_decision = "clean_abstention"
        else:
            primary = f"Primary fact {item_id}"
            if index == 1:
                extra = f"Additional fact {item_id}"
                answer = f"{primary} [Source 1]. {extra} [Source 1]."
                claims.append(
                    build_decomposed_claim(
                        claim_id="C001",
                        text=primary,
                        char_start=answer.index(primary),
                        char_end=answer.index(primary) + len(primary),
                        cited_source_numbers=(1,),
                    )
                )
                claims.append(
                    build_decomposed_claim(
                        claim_id="C002",
                        text=extra,
                        char_start=answer.index(extra),
                        char_end=answer.index(extra) + len(extra),
                        cited_source_numbers=(1,),
                    )
                )
            elif index == 2:
                answer = f"{primary} [Sources 1]."
                claims.append(
                    build_decomposed_claim(
                        claim_id="C001",
                        text=primary,
                        char_start=0,
                        char_end=len(primary),
                        cited_source_numbers=(),
                    )
                )
            else:
                answer = f"{primary} [Source 1]."
                claims.append(
                    build_decomposed_claim(
                        claim_id="C001",
                        text=primary,
                        char_start=0,
                        char_end=len(primary),
                        cited_source_numbers=(1,),
                    )
                )
            status = (
                "insufficient_evidence"
                if index == insufficient_evidence_item
                else "answered"
            )
            evidence_decision = "direct_answer"
        generated = build_private_generated_item(
            item_id=item_id,
            question=question,
            stratum=stratum,
            expected_behavior="abstain" if out_of_corpus else "answer",
            answer=answer,
            status=status,
            evidence_decision=evidence_decision,
            diagnostics={"sealed": True},
            sources=(source,),
            elapsed_seconds=float(index),
            usage_events=(
                _usage(
                    response_id=f"resp_generation_{item_id}",
                    operation="answer_generation",
                    model="gpt-5.6-sol",
                ),
            ),
            trace_references=(
                {
                    "sequence": 1,
                    "schema_id": "archivist.retrieval_trace/1",
                    "trace_id": f"{index:032x}",
                    "path": f"retrieval-traces/{item_id}.json",
                    "sha256": f"{index:064x}"[-64:],
                    "query_sha256": f"{index + 1:064x}"[-64:],
                    "retrieval_version": "faceted-hybrid-rrf-v2",
                },
            ),
        )
        decomposition = build_decomposed_pilot_item(
            item_id=item_id,
            answer_sha256=generated.answer_sha256,
            claims=claims,
        )
        gold_claims = (
            []
            if out_of_corpus
            else [
                {
                    "claim_id": f"{item_id}.G1",
                    "text": f"Owner rubric claim {item_id}.",
                    "essential": True,
                    "supporting_chunk_ids": [source.chunk_id],
                }
            ]
        )
        gold = {
            "id": item_id,
            "question": question,
            "stratum": stratum.value,
            "expected_behavior": "abstain" if out_of_corpus else "answer",
            "claims": gold_claims,
            "relevant_chunk_ids": [] if out_of_corpus else [source.chunk_id],
            "must_not_claim": [f"Bounded prohibited claim {item_id}."],
            "notes": "Private owner note.",
        }
        rubric = ItemRubricInput.model_validate(
            {
                "question": question,
                "claims": [
                    {
                        "claim_id": claim["claim_id"],
                        "text": claim["text"],
                        "essential": claim["essential"],
                    }
                    for claim in gold_claims
                ],
                "must_not_claim": gold["must_not_claim"],
            }
        )
        response_behavior = (
            "decline"
            if out_of_corpus
            else "premise_correction"
            if stratum is EvaluationStratum.ADVERSARIAL_PREMISE
            else "substantive_answer"
        )
        rubric_response_id = f"resp_rubric_{item_id}"
        rubric_result = build_item_rubric_result(
            cohort_manifest_sha256=COHORT_SHA,
            generated_item=generated,
            decomposition=decomposition,
            rubric=rubric,
            prompt_version="evaluation-item-rubric-v2",
            prompt_sha256=RUBRIC_PROMPT_SHA,
            judge_model=JUDGE_MODEL,
            judge_settings=JUDGE_SETTINGS,
            provider=_provider(rubric_response_id),
            usage_event=_usage(
                response_id=rubric_response_id,
                operation="eval_item_rubric",
                model=JUDGE_MODEL,
            ),
            verdict={
                "gold_claims": [
                    {"claim_id": claim["claim_id"], "status": "present"}
                    for claim in gold_claims
                ],
                "answer_claim_matches": [
                    {
                        "answer_claim_id": claim.claim_id,
                        "gold_claim_ids": (
                            [gold_claims[0]["claim_id"]]
                            if gold_claims and claim.claim_id == "C001"
                            else []
                        ),
                    }
                    for claim in claims
                ],
                "must_not_claim": [{"index": 0, "status": "not_asserted"}],
                "response_behavior": response_behavior,
                "rationale": "Private bounded rubric rationale.",
            },
        )
        for claim in claims:
            response_id = f"resp_evidence_{item_id}_{claim.claim_id}"
            evidence_results.append(
                build_claim_evidence_result(
                    cohort_manifest_sha256=COHORT_SHA,
                    generated_item=generated,
                    decomposition=decomposition,
                    claim=claim,
                    call_ordinal=1,
                    prompt_version="evaluation-claim-evidence-v1",
                    prompt_sha256=EVIDENCE_PROMPT_SHA,
                    judge_model=JUDGE_MODEL,
                    judge_settings=JUDGE_SETTINGS,
                    provider=_provider(response_id),
                    usage_event=_usage(
                        response_id=response_id,
                        operation="eval_claim_evidence",
                        model=JUDGE_MODEL,
                    ),
                    verdict={
                        "claim_id": claim.claim_id,
                        "faithfulness": "supported",
                        "source_verdicts": [
                            {"source_number": number, "label": "supported"}
                            for number in claim.cited_source_numbers
                        ],
                        "rationale": "Private bounded evidence rationale.",
                    },
                )
            )
        generated_items.append(generated)
        decompositions.append(decomposition)
        gold_items.append(gold)
        rubric_results.append(rubric_result)
        rubric_inputs.append(rubric)
    return _Fixture(
        generated=tuple(generated_items),
        decompositions=tuple(decompositions),
        gold=tuple(gold_items),
        evidence=tuple(evidence_results),
        rubrics=tuple(rubric_results),
        rubric_inputs=tuple(rubric_inputs),
    )


def _instrument(
    *,
    judge_results_sha256: str,
    manual_dimensions: set[ScoringDimension] = frozenset(),
):
    dimensions = {
        dimension: ((0.50, 10) if dimension in manual_dimensions else (0.90, 10))
        for dimension in ScoringDimension
    }
    pooled = sum(value[0] * value[1] for value in dimensions.values()) / sum(
        value[1] for value in dimensions.values()
    )
    return build_instrument_lock(
        instrument_id="heldout-v26-instrument-1",
        cohort_manifest_sha256=COHORT_SHA,
        pilot_artifact_sha256=PILOT_ARTIFACT_SHA,
        decomposition_artifact_sha256=CALIBRATION_DECOMPOSITION_ARTIFACT_SHA,
        human_labels_sha256="3" * 64,
        judge_results_sha256=judge_results_sha256,
        judge_model=JUDGE_MODEL,
        judge_settings=JUDGE_SETTINGS,
        decomposition_prompt_sha256=DECOMPOSITION_PROMPT_SHA,
        evidence_prompt_sha256=EVIDENCE_PROMPT_SHA,
        rubric_prompt_sha256=RUBRIC_PROMPT_SHA,
        pooled_agreement=pooled,
        repeat_agreement=0.95,
        dimension_agreements=dimensions,
    )


def _metric(summary, metric_id: PublicMetricId):
    return next(metric for metric in summary.metrics if metric.metric_id is metric_id)


def _calibration_semantic(fixture: _Fixture):
    evidence_by_item: dict[str, list[Any]] = {
        generated.item_id: [] for generated in fixture.generated[:10]
    }
    for result in fixture.evidence:
        if result.item_id in evidence_by_item:
            evidence_by_item[result.item_id].append(result)
    rubrics = {result.item_id: result for result in fixture.rubrics[:10]}
    semantic_items = []
    for generated, decomposition in zip(
        fixture.generated[:10],
        fixture.decompositions[:10],
        strict=True,
    ):
        first_results = tuple(evidence_by_item[generated.item_id])
        first = first_results[0]
        response_id = f"resp_evidence_repeat_{generated.item_id}"
        repeat = build_claim_evidence_result(
            cohort_manifest_sha256=COHORT_SHA,
            generated_item=generated,
            decomposition=decomposition,
            claim=decomposition.claims[0],
            call_ordinal=2,
            prompt_version="evaluation-claim-evidence-v1",
            prompt_sha256=EVIDENCE_PROMPT_SHA,
            judge_model=JUDGE_MODEL,
            judge_settings=JUDGE_SETTINGS,
            provider=_provider(response_id),
            usage_event=_usage(
                response_id=response_id,
                operation="eval_claim_evidence",
                model=JUDGE_MODEL,
            ),
            verdict=first.verdict,
        )
        semantic_items.append(
            build_calibration_semantic_item(
                first_call_claim_evidence=first_results,
                item_rubric=rubrics[generated.item_id],
                repeat_first_claim_evidence=repeat,
            )
        )
    return build_calibration_semantic_aggregate(
        cohort_manifest_sha256=COHORT_SHA,
        pilot_artifact_sha256=PILOT_ARTIFACT_SHA,
        decomposition_artifact_sha256=CALIBRATION_DECOMPOSITION_ARTIFACT_SHA,
        calibration_item_ids=COHORT_MANIFEST.calibration_item_ids,
        items=semantic_items,
    )


def _additional_usage_events(calibration_semantic) -> tuple[Any, ...]:
    decompositions = tuple(
        _usage(
            response_id=f"resp_decomposition_{index:03d}",
            operation="eval_claim_decomposition",
            model=JUDGE_MODEL,
        )
        for index in range(1, 58)
    )
    repeats = tuple(
        item.repeat_first_claim_evidence.usage_event
        for item in calibration_semantic.items
        if item.repeat_first_claim_evidence is not None
    )
    return decompositions + repeats


def _summary(
    fixture: _Fixture,
    *,
    manual_dimensions: set[ScoringDimension] = frozenset(),
    claim_evidence_results=None,
    item_rubric_results=None,
    manual_items=None,
    generated_items=None,
    decompositions=None,
    gold_items=None,
    additional_usage_events=None,
):
    evidence = (
        fixture.evidence
        if claim_evidence_results is None
        else tuple(claim_evidence_results)
    )
    rubrics = (
        fixture.rubrics if item_rubric_results is None else tuple(item_rubric_results)
    )
    calibration_semantic = _calibration_semantic(fixture)
    instrument = _instrument(
        judge_results_sha256=calibration_semantic.aggregate_sha256,
        manual_dimensions=manual_dimensions,
    )
    evidence_by_item: dict[str, dict[str, Any]] = {
        generated.item_id: {} for generated in fixture.generated
    }
    for result in evidence:
        evidence_by_item[result.item_id][result.claim.claim_id] = result
    rubric_by_item = {result.item_id: result for result in rubrics}
    semantic_items = tuple(
        build_baseline_semantic_item(
            decomposition=decomposition,
            instrument_lock=instrument,
            first_call_claim_evidence=tuple(
                evidence_by_item[generated.item_id][claim.claim_id]
                for claim in decomposition.claims
                if claim.claim_id in evidence_by_item[generated.item_id]
            ),
            item_rubric=rubric_by_item.get(generated.item_id),
        )
        for generated, decomposition in zip(
            fixture.generated,
            fixture.decompositions,
            strict=True,
        )
    )
    semantic = build_baseline_semantic_aggregate(
        cohort_manifest_sha256=COHORT_SHA,
        generation_artifact_sha256=GENERATION_ARTIFACT_SHA,
        decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
        instrument_lock=instrument,
        item_ids=tuple(item.item_id for item in fixture.generated),
        items=semantic_items,
    )
    manual_aggregate = (
        None
        if manual_items is None
        else build_manual_scoring_aggregate(
            cohort_manifest_sha256=COHORT_SHA,
            generation_artifact_sha256=GENERATION_ARTIFACT_SHA,
            decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
            instrument_lock=instrument,
            generated_items=fixture.generated,
            decompositions=fixture.decompositions,
            rubrics=fixture.rubric_inputs,
            items=manual_items,
        )
    )
    overhead = (
        _additional_usage_events(calibration_semantic)
        if additional_usage_events is None
        else tuple(additional_usage_events)
    )
    full_run = build_private_full_run_artifact(
        cohort_manifest_sha256=COHORT_SHA,
        generation_artifact_sha256=GENERATION_ARTIFACT_SHA,
        decomposition_artifact_sha256=DECOMPOSITION_ARTIFACT_SHA,
        generated_items=fixture.generated,
        decompositions=fixture.decompositions,
        semantic_aggregate=semantic,
        instrument_lock=instrument,
        calibration_semantic_aggregate=calibration_semantic,
        additional_usage_events=overhead,
        manual_scoring_aggregate=manual_aggregate,
    )
    return build_public_evaluation_summary(
        candidate_id="evidence-planned-v26",
        cohort_manifest=COHORT_MANIFEST,
        generated_items=fixture.generated if generated_items is None else generated_items,
        decompositions=(
            fixture.decompositions if decompositions is None else decompositions
        ),
        gold_items=fixture.gold if gold_items is None else gold_items,
        semantic_aggregate=semantic,
        calibration_semantic_aggregate=calibration_semantic,
        additional_usage_events=overhead,
        private_full_run_artifact=full_run,
        instrument_lock=instrument,
        manual_scoring_aggregate=manual_aggregate,
    )


def test_complete_judge_summary_separates_all_contract_metrics_and_is_text_free() -> None:
    fixture = _make_fixture()
    summary = _summary(fixture)

    assert summary.item_count == 37
    assert summary.source_count == 37
    assert summary.claim_count == 34
    assert summary.citation_count == 33
    assert summary.error_count == 0
    assert _metric(summary, PublicMetricId.CITATION_RESOLVABILITY).numerator == 33
    assert _metric(summary, PublicMetricId.CITATION_RESOLVABILITY).denominator == 33
    assert _metric(summary, PublicMetricId.CITATION_COMPLETENESS).numerator == 33
    assert _metric(summary, PublicMetricId.CITATION_COMPLETENESS).denominator == 34
    malformed = _metric(summary, PublicMetricId.MALFORMED_CITATION_RATE)
    assert (malformed.numerator, malformed.denominator) == (1, 34)
    gold_grounded = _metric(
        summary,
        PublicMetricId.CITATION_GROUNDEDNESS_GOLD_MATCHED,
    )
    assert (gold_grounded.numerator, gold_grounded.denominator) == (32, 32)
    judge_grounded = _metric(
        summary,
        PublicMetricId.CITATION_GROUNDEDNESS_JUDGE_ONLY,
    )
    assert (judge_grounded.numerator, judge_grounded.denominator) == (1, 1)
    assert (_metric(summary, PublicMetricId.FAITHFULNESS_SUPPORTED).numerator, 34) == (
        34,
        34,
    )
    assert _metric(summary, PublicMetricId.GOLD_CLAIM_RECALL).numerator == 33
    assert _metric(summary, PublicMetricId.ESSENTIAL_GOLD_CLAIM_RECALL).numerator == 33
    assert _metric(summary, PublicMetricId.MUST_NOT_CLAIM_VIOLATION).numerator == 0
    assert _metric(summary, PublicMetricId.OUT_OF_CORPUS_ABSTENTION).numerator == 4
    assert _metric(summary, PublicMetricId.ADVERSARIAL_PREMISE_CORRECTION).numerator == 2
    false_abstention = _metric(summary, PublicMetricId.FALSE_ABSTENTION)
    assert (false_abstention.numerator, false_abstention.denominator) == (0, 33)
    assert _metric(summary, PublicMetricId.ANSWER_SUCCESS).numerator == 37
    assert summary.cost.priced_event_count == 175
    assert summary.cost.estimated_cost_usd == pytest.approx(0.175)
    assert COHORT_SHA != COHORT_MANIFEST.manifest_sha256
    assert summary.cohort_manifest_sha256 == COHORT_SHA
    assert summary.corpus_manifest_sha256 == COHORT_MANIFEST.corpus_manifest_sha256
    assert summary.question_set_sha256 == COHORT_MANIFEST.question_set_sha256
    assert summary.model_catalog_sha256 == COHORT_MANIFEST.model_catalog_sha256
    assert summary.runner_sha256 == COHORT_MANIFEST.runner_sha256
    assert summary.generator_model_id == "gpt-5.6-sol"
    assert summary.planner_model_id == "gpt-5.6-sol"
    assert summary.judge_model_id == JUDGE_MODEL
    assert summary.embedding_model_id == "text-embedding-3-small"
    assert summary.limitation_ids == (
        PublicLimitationId.CANONICAL_MODEL_ID_MUTABILITY,
        PublicLimitationId.GENERATOR_SPREAD_UNMEASURED,
        PublicLimitationId.DESCRIPTIVE_NOT_GATE,
    )

    serialized = json.dumps(summary.model_dump(mode="json"), sort_keys=True)
    assert PRIVATE_SENTINEL not in serialized
    assert "Private evaluation question" not in serialized
    assert "Private owner note" not in serialized
    assert "rationale" not in serialized


def test_markdown_report_is_deterministic_and_uses_only_the_public_boundary() -> None:
    fixture = _make_fixture()
    summary = _summary(fixture)
    public_json_sha256 = canonical_json_sha256(summary.model_dump(mode="json"))

    markdown = render_public_evaluation_markdown(
        summary,
        public_summary_json_sha256=public_json_sha256,
    )

    assert markdown == render_public_evaluation_markdown(
        summary.model_dump(mode="json"),
        public_summary_json_sha256=public_json_sha256,
    )
    assert "# Archivist held-out evaluation" in markdown
    assert f"`{COHORT_SHA}`" in markdown
    assert "`citation_groundedness_gold_matched`" in markdown
    assert PRIVATE_SENTINEL not in markdown
    assert "Private evaluation question" not in markdown
    assert "Private owner note" not in markdown
    assert "rationale" not in markdown

    with pytest.raises(ValueError, match="64 lowercase hex"):
        render_public_evaluation_markdown(
            summary,
            public_summary_json_sha256="not-a-digest",
        )


def test_manual_evidence_lane_can_be_absent_without_blocking_judge_rubric_metrics() -> None:
    fixture = _make_fixture()
    summary = _summary(
        fixture,
        manual_dimensions={
            ScoringDimension.FAITHFULNESS,
            ScoringDimension.CITED_SOURCE_SUPPORT,
        },
        claim_evidence_results=(),
    )

    faithfulness = _metric(summary, PublicMetricId.FAITHFULNESS_SUPPORTED)
    assert faithfulness.availability.value == "pending"
    assert faithfulness.numerator is None
    assert faithfulness.denominator == 34
    gold_grounded = _metric(
        summary,
        PublicMetricId.CITATION_GROUNDEDNESS_GOLD_MATCHED,
    )
    assert gold_grounded.availability.value == "available"
    assert (gold_grounded.numerator, gold_grounded.denominator) == (32, 32)
    judge_grounded = _metric(
        summary,
        PublicMetricId.CITATION_GROUNDEDNESS_JUDGE_ONLY,
    )
    assert judge_grounded.availability.value == "pending"
    assert judge_grounded.numerator is None
    assert judge_grounded.denominator == 1
    assert _metric(summary, PublicMetricId.GOLD_CLAIM_RECALL).availability.value == "available"
    assert _metric(summary, PublicMetricId.OUT_OF_CORPUS_ABSTENTION).availability.value == "available"
    assert PublicLimitationId.MANUAL_FAITHFULNESS_PENDING in summary.limitation_ids
    assert (
        PublicLimitationId.MANUAL_CITED_SOURCE_SUPPORT_PENDING
        in summary.limitation_ids
    )


def _manual_items(fixture: _Fixture) -> tuple[CalibrationItemLabel, ...]:
    items = []
    for generated, decomposition, gold in zip(
        fixture.generated,
        fixture.decompositions,
        fixture.gold,
        strict=True,
    ):
        gold_claims = gold["claims"]
        must_not = gold["must_not_claim"]
        rubric_raw = {
            "item_id": generated.item_id,
            "gold_claims": [
                {"claim_id": claim["claim_id"], "text": claim["text"]}
                for claim in gold_claims
            ],
            "must_not_claims": must_not,
        }
        rubric_raw["rubric_sha256"] = canonical_json_sha256(rubric_raw)
        items.append(
            CalibrationItemLabel.model_validate(
                {
                    "item_id": generated.item_id,
                    "answer_sha256": generated.answer_sha256,
                    "decomposition_sha256": decomposition.decomposition_sha256,
                    "rubric_sha256": rubric_raw["rubric_sha256"],
                    "response_behavior": None,
                    "claims": [
                        {
                            "claim_id": claim.claim_id,
                            "claim_text": claim.text,
                            "claim_sha256": claim.claim_sha256,
                            "faithfulness": "supported",
                            "gold_match_ids": (
                                [gold_claims[0]["claim_id"]]
                                if gold_claims and claim.claim_id == "C001"
                                else []
                            ),
                            "cited_source_labels": {
                                number: "supported" for number in claim.cited_source_numbers
                            },
                        }
                        for claim in decomposition.claims
                    ],
                    "gold_claim_statuses": [
                        {
                            "claim_id": claim["claim_id"],
                            "claim_text": claim["text"],
                            "claim_text_sha256": sha256_text(claim["text"]),
                            "status": None,
                        }
                        for claim in gold_claims
                    ],
                    "must_not_claim_statuses": [
                        {
                            "index": index,
                            "claim_text": text,
                            "claim_text_sha256": sha256_text(text),
                            "status": None,
                        }
                        for index, text in enumerate(must_not)
                    ],
                }
            )
        )
    return tuple(items)


def test_manual_evidence_decisions_fill_only_their_affected_metrics() -> None:
    fixture = _make_fixture()
    summary = _summary(
        fixture,
        manual_dimensions={
            ScoringDimension.FAITHFULNESS,
            ScoringDimension.CITED_SOURCE_SUPPORT,
        },
        claim_evidence_results=(),
        manual_items=_manual_items(fixture),
    )

    assert _metric(summary, PublicMetricId.FAITHFULNESS_SUPPORTED).numerator == 34
    judge_grounded = _metric(
        summary,
        PublicMetricId.CITATION_GROUNDEDNESS_JUDGE_ONLY,
    )
    assert (judge_grounded.numerator, judge_grounded.denominator) == (1, 1)


def test_judge_eligible_lane_is_required_and_exactly_bound() -> None:
    fixture = _make_fixture()
    with pytest.raises(ValueError, match="active baseline evidence lane"):
        _summary(fixture, claim_evidence_results=fixture.evidence[:-1])

    tampered = list(fixture.gold)
    tampered[0] = dict(tampered[0])
    tampered[0]["question"] = "A changed question?"
    with pytest.raises(ValueError, match="cohort manifest differs from frozen gold"):
        _summary(fixture, gold_items=tampered)


def test_report_rejects_any_cohort_that_is_not_exactly_37_items() -> None:
    fixture = _make_fixture()
    with pytest.raises(ValueError, match="exactly 37"):
        _summary(
            fixture,
            generated_items=fixture.generated[:-1],
            decompositions=fixture.decompositions[:-1],
            gold_items=fixture.gold[:-1],
        )


def test_structurally_released_insufficient_evidence_counts_as_answer_success() -> None:
    fixture = _make_fixture(insufficient_evidence_item=1)
    summary = _summary(fixture)

    success = _metric(summary, PublicMetricId.ANSWER_SUCCESS)
    assert (success.numerator, success.denominator) == (37, 37)
    assert summary.error_count == 0
