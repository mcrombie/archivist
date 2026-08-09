"""Pure, text-free reporting for the frozen 37-item answer evaluation.

The functions in this module perform no filesystem or provider operations.  They
join already-sealed private artifacts, apply the dimension-level scoring modes
from the ratified instrument lock, and emit only ``PublicEvaluationSummary``.
Judge results are never used for a dimension whose lock selected manual scoring.
When those manual decisions are absent, the affected public metric is explicitly
pending with its real applicable denominator.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from answer_evaluation import (
    AnswerStatus,
    AnswerEvaluationCohortManifest,
    BaselineRunStatus,
    CalibrationItemLabel,
    CitedSourceLabel,
    CohortPromptBinding,
    DecomposedClaim,
    DecomposedPilotItem,
    EvaluationStratum,
    ExpectedBehavior,
    FaithfulnessLabel,
    GoldClaimStatus,
    InstrumentLock,
    MetricAvailability,
    MustNotClaimStatus,
    PRIVATE_DECOMPOSITION_FAILURE_CHECKPOINT_SCHEMA,
    PrecalibrationMetricId,
    PrecalibrationPublicMetric,
    PrecalibrationPublicStratumSummary,
    PrivateDecompositionCheckpoint,
    PrivateDecompositionFailureCheckpoint,
    PrivateDecompositionOutcome,
    PrivateGeneratedItem,
    PrivateUsageEvent,
    PublicCost,
    PublicEvaluationSummary,
    PublicLimitationId,
    PublicLatency,
    PublicMetric,
    PublicMetricId,
    PublicPrecalibrationSummary,
    PublicStratumSummary,
    ResponseBehavior,
    ScoringDimension,
    ScoringMode,
    canonical_json_bytes,
    canonical_json_sha256,
    sha256_text,
    validate_public_summary,
    validate_public_precalibration_summary,
)
from evaluation_judge import ItemRubricInput
from evaluation_results import (
    BaselineSemanticAggregate,
    CalibrationSemanticAggregate,
    ClaimEvidenceResult,
    ItemRubricResult,
    ManualScoringAggregate,
    PrecalibrationPrivateArtifact,
    PrivateFullRunArtifact,
    validate_baseline_semantic_aggregate,
    validate_calibration_semantic_aggregate,
    validate_manual_scoring_aggregate,
    validate_precalibration_private_artifact,
    validate_private_full_run_artifact,
)
from evaluation_scoring import audit_citations


_TECHNICAL_FAILURES = frozenset(
    {
        AnswerStatus.GENERATION_CONTRACT_FAILED,
        AnswerStatus.CORPUS_INTEGRITY_FAILED,
    }
)
_SUCCESSFUL_RELEASES = frozenset(
    {
        AnswerStatus.ANSWERED,
        AnswerStatus.CLEAN_ABSTENTION,
        AnswerStatus.INSUFFICIENT_EVIDENCE,
    }
)


@dataclass(frozen=True, slots=True)
class _GoldClaim:
    claim_id: str
    text: str
    essential: bool
    supporting_chunk_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class _GoldItem:
    item_id: str
    question: str
    stratum: EvaluationStratum
    expected_behavior: ExpectedBehavior
    claims: tuple[_GoldClaim, ...]
    relevant_chunk_ids: frozenset[str]
    must_not_claim: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ItemBundle:
    generated: PrivateGeneratedItem
    decomposition: DecomposedPilotItem
    gold: _GoldItem
    evidence: Mapping[str, ClaimEvidenceResult]
    rubric: ItemRubricResult | None
    manual: CalibrationItemLabel | None


def _require_sequence(value: object, *, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an ordered array")
    return value


def _parse_gold_item(value: Mapping[str, object]) -> _GoldItem:
    item_id = value.get("id")
    question = value.get("question")
    if not isinstance(item_id, str) or not item_id:
        raise ValueError("gold item requires a nonempty id")
    if not isinstance(question, str) or not question:
        raise ValueError(f"{item_id}: gold item requires a nonempty question")
    try:
        stratum = EvaluationStratum(value.get("stratum"))
        expected = ExpectedBehavior(value.get("expected_behavior"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{item_id}: gold stratum or expected behavior is invalid") from exc

    claims: list[_GoldClaim] = []
    for raw_claim in _require_sequence(value.get("claims"), label=f"{item_id} claims"):
        if not isinstance(raw_claim, Mapping):
            raise ValueError(f"{item_id}: each gold claim must be an object")
        claim_id = raw_claim.get("claim_id")
        text = raw_claim.get("text")
        essential = raw_claim.get("essential")
        if not isinstance(claim_id, str) or not claim_id:
            raise ValueError(f"{item_id}: gold claim requires a nonempty claim_id")
        if not isinstance(text, str) or not text:
            raise ValueError(f"{claim_id}: gold claim requires nonempty text")
        if not isinstance(essential, bool):
            raise ValueError(f"{claim_id}: essential must be boolean")
        support_raw = _require_sequence(
            raw_claim.get("supporting_chunk_ids"),
            label=f"{claim_id} supporting_chunk_ids",
        )
        if not support_raw or any(
            not isinstance(chunk_id, str) or not chunk_id for chunk_id in support_raw
        ):
            raise ValueError(f"{claim_id}: supporting_chunk_ids must be nonempty strings")
        support = tuple(support_raw)
        if len(support) != len(set(support)):
            raise ValueError(f"{claim_id}: supporting_chunk_ids contain duplicates")
        claims.append(
            _GoldClaim(
                claim_id=claim_id,
                text=text,
                essential=essential,
                supporting_chunk_ids=frozenset(support),
            )
        )
    if len({claim.claim_id for claim in claims}) != len(claims):
        raise ValueError(f"{item_id}: gold claim IDs must be unique")

    relevant_raw = _require_sequence(
        value.get("relevant_chunk_ids"),
        label=f"{item_id} relevant_chunk_ids",
    )
    if any(not isinstance(chunk_id, str) or not chunk_id for chunk_id in relevant_raw):
        raise ValueError(f"{item_id}: relevant_chunk_ids must contain nonempty strings")
    relevant = tuple(relevant_raw)
    if len(relevant) != len(set(relevant)):
        raise ValueError(f"{item_id}: relevant_chunk_ids contain duplicates")

    must_raw = _require_sequence(
        value.get("must_not_claim"),
        label=f"{item_id} must_not_claim",
    )
    if any(not isinstance(text, str) or not text for text in must_raw):
        raise ValueError(f"{item_id}: must_not_claim entries must be nonempty strings")
    must_not = tuple(must_raw)
    if len(must_not) != len(set(must_not)):
        raise ValueError(f"{item_id}: must_not_claim entries contain duplicates")
    return _GoldItem(
        item_id=item_id,
        question=question,
        stratum=stratum,
        expected_behavior=expected,
        claims=tuple(claims),
        relevant_chunk_ids=frozenset(relevant),
        must_not_claim=must_not,
    )


def _normalize_generated(
    values: Sequence[PrivateGeneratedItem | Mapping[str, object]],
) -> tuple[PrivateGeneratedItem, ...]:
    return tuple(
        value
        if isinstance(value, PrivateGeneratedItem)
        else PrivateGeneratedItem.model_validate(value)
        for value in values
    )


def _normalize_decompositions(
    values: Sequence[DecomposedPilotItem | Mapping[str, object]],
) -> tuple[DecomposedPilotItem, ...]:
    return tuple(
        value
        if isinstance(value, DecomposedPilotItem)
        else DecomposedPilotItem.model_validate(value)
        for value in values
    )


def _validate_decomposition(
    generated: PrivateGeneratedItem,
    decomposition: DecomposedPilotItem,
) -> None:
    if decomposition.item_id != generated.item_id:
        raise ValueError("decomposition item order or identity changed")
    if decomposition.answer_sha256 != generated.answer_sha256:
        raise ValueError(f"{generated.item_id}: decomposition is bound to another answer")
    expected_claim_ids = [f"C{index:03d}" for index in range(1, len(decomposition.claims) + 1)]
    if [claim.claim_id for claim in decomposition.claims] != expected_claim_ids:
        raise ValueError(f"{generated.item_id}: canonical claim IDs must be C001..Cnnn")
    valid_sources = {source.source_number for source in generated.sources}
    for claim in decomposition.claims:
        if claim.char_end > len(generated.answer):
            raise ValueError(f"{generated.item_id}/{claim.claim_id}: span exceeds answer")
        if generated.answer[claim.char_start : claim.char_end] != claim.text:
            raise ValueError(
                f"{generated.item_id}/{claim.claim_id}: claim text differs from answer span"
            )
        if not set(claim.cited_source_numbers) <= valid_sources:
            raise ValueError(
                f"{generated.item_id}/{claim.claim_id}: citation is outside source union"
            )


def _rubric_sha256(gold: _GoldItem) -> str:
    raw = {
        "item_id": gold.item_id,
        "gold_claims": [{"claim_id": claim.claim_id, "text": claim.text} for claim in gold.claims],
        "must_not_claims": list(gold.must_not_claim),
    }
    raw["rubric_sha256"] = canonical_json_sha256(raw)
    return str(raw["rubric_sha256"])


def _sanitized_rubric(gold: _GoldItem) -> ItemRubricInput:
    """Project private gold into the exact prose subset permitted to the judge."""

    return ItemRubricInput.model_validate(
        {
            "question": gold.question,
            "claims": [
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "essential": claim.essential,
                }
                for claim in gold.claims
            ],
            "must_not_claim": list(gold.must_not_claim),
        }
    )


def _validate_manual(bundle: _ItemBundle) -> None:
    manual = bundle.manual
    if manual is None:
        return
    generated = bundle.generated
    decomposition = bundle.decomposition
    gold = bundle.gold
    if (
        manual.item_id != generated.item_id
        or manual.answer_sha256 != generated.answer_sha256
        or manual.decomposition_sha256 != decomposition.decomposition_sha256
        or manual.rubric_sha256 != _rubric_sha256(gold)
    ):
        raise ValueError(f"{generated.item_id}: manual scoring bindings changed")
    if len(manual.claims) != len(decomposition.claims):
        raise ValueError(f"{generated.item_id}: manual claim cardinality changed")
    valid_gold_ids = {claim.claim_id for claim in gold.claims}
    for owner, claim in zip(manual.claims, decomposition.claims, strict=True):
        if (
            owner.claim_id != claim.claim_id
            or owner.claim_text != claim.text
            or owner.claim_sha256 != claim.claim_sha256
        ):
            raise ValueError(f"{generated.item_id}: manual claim identity changed")
        if owner.gold_match_ids is not None and not set(owner.gold_match_ids) <= valid_gold_ids:
            raise ValueError(f"{generated.item_id}/{claim.claim_id}: invalid manual gold match")
        if owner.cited_source_labels is not None and set(owner.cited_source_labels) != set(
            claim.cited_source_numbers
        ):
            raise ValueError(
                f"{generated.item_id}/{claim.claim_id}: manual source labels changed citations"
            )
    if [status.claim_id for status in manual.gold_claim_statuses] != [
        claim.claim_id for claim in gold.claims
    ]:
        raise ValueError(f"{generated.item_id}: manual gold-claim order changed")
    for status, claim in zip(manual.gold_claim_statuses, gold.claims, strict=True):
        if status.claim_text != claim.text or status.claim_text_sha256 != sha256_text(claim.text):
            raise ValueError(f"{generated.item_id}/{claim.claim_id}: manual gold text changed")
    if [status.index for status in manual.must_not_claim_statuses] != list(
        range(len(gold.must_not_claim))
    ):
        raise ValueError(f"{generated.item_id}: manual tripwire order changed")
    for status, text in zip(
        manual.must_not_claim_statuses,
        gold.must_not_claim,
        strict=True,
    ):
        if status.claim_text != text or status.claim_text_sha256 != sha256_text(text):
            raise ValueError(f"{generated.item_id}: manual tripwire text changed")


def _validate_rubric_result(bundle: _ItemBundle) -> None:
    result = bundle.rubric
    if result is None:
        return
    generated = bundle.generated
    decomposition = bundle.decomposition
    gold = bundle.gold
    if (
        result.item_id != generated.item_id
        or result.answer_sha256 != generated.answer_sha256
        or result.decomposition_sha256 != decomposition.decomposition_sha256
    ):
        raise ValueError(f"{generated.item_id}: item-rubric result binding changed")
    if result.rubric.question_sha256 != sha256_text(gold.question):
        raise ValueError(f"{generated.item_id}: item-rubric question binding changed")
    if [claim.claim_id for claim in result.rubric.gold_claims] != [
        claim.claim_id for claim in gold.claims
    ]:
        raise ValueError(f"{generated.item_id}: item-rubric gold order changed")
    for binding, claim in zip(result.rubric.gold_claims, gold.claims, strict=True):
        if (
            binding.claim_text_sha256 != sha256_text(claim.text)
            or binding.essential != claim.essential
        ):
            raise ValueError(f"{generated.item_id}/{claim.claim_id}: rubric claim changed")
    if result.rubric.must_not_claim_sha256s != tuple(
        sha256_text(text) for text in gold.must_not_claim
    ):
        raise ValueError(f"{generated.item_id}: item-rubric tripwires changed")
    if [claim.claim_sha256 for claim in result.locked_claims] != [
        claim.claim_sha256 for claim in decomposition.claims
    ]:
        raise ValueError(f"{generated.item_id}: item-rubric locked claims changed")


def _validate_evidence_result(
    bundle: _ItemBundle,
    claim: DecomposedClaim,
    result: ClaimEvidenceResult,
) -> None:
    generated = bundle.generated
    decomposition = bundle.decomposition
    if (
        result.call_ordinal != 1
        or result.item_id != generated.item_id
        or result.answer_sha256 != generated.answer_sha256
        or result.decomposition_sha256 != decomposition.decomposition_sha256
        or result.claim.claim_sha256 != claim.claim_sha256
    ):
        raise ValueError(f"{generated.item_id}/{claim.claim_id}: evidence binding changed")
    expected_sources = [
        (source.source_number, source.chunk_id, source.text_sha256, source.source_sha256)
        for source in generated.sources
    ]
    actual_sources = [
        (source.source_number, source.chunk_id, source.text_sha256, source.source_sha256)
        for source in result.source_union
    ]
    if actual_sources != expected_sources:
        raise ValueError(f"{generated.item_id}/{claim.claim_id}: evidence source union changed")


def _dimension_modes(instrument: InstrumentLock) -> dict[ScoringDimension, ScoringMode]:
    return {entry.dimension: entry.scoring_mode for entry in instrument.dimensions}


def _manifest_prompt(
    manifest: AnswerEvaluationCohortManifest,
    prompt_id: str,
) -> CohortPromptBinding:
    try:
        return next(prompt for prompt in manifest.prompts if prompt.prompt_id == prompt_id)
    except StopIteration as exc:
        raise ValueError(f"cohort manifest is missing prompt {prompt_id}") from exc


_BASE_LIMITATIONS = (
    PublicLimitationId.CANONICAL_MODEL_ID_MUTABILITY,
    PublicLimitationId.GENERATOR_SPREAD_UNMEASURED,
    PublicLimitationId.DESCRIPTIVE_NOT_GATE,
)
_PENDING_LIMITATION_BY_DIMENSION = {
    ScoringDimension.FAITHFULNESS: PublicLimitationId.MANUAL_FAITHFULNESS_PENDING,
    ScoringDimension.CITED_SOURCE_SUPPORT: (PublicLimitationId.MANUAL_CITED_SOURCE_SUPPORT_PENDING),
    ScoringDimension.CLAIM_MAPPING: PublicLimitationId.MANUAL_CLAIM_MAPPING_PENDING,
    ScoringDimension.GOLD_STATUS: PublicLimitationId.MANUAL_GOLD_STATUS_PENDING,
    ScoringDimension.MUST_NOT_TRIPWIRES: (PublicLimitationId.MANUAL_MUST_NOT_TRIPWIRES_PENDING),
    ScoringDimension.RESPONSE_BEHAVIOR: (PublicLimitationId.MANUAL_RESPONSE_BEHAVIOR_PENDING),
}
_METRICS_BY_DIMENSION = {
    ScoringDimension.FAITHFULNESS: frozenset(
        {
            PublicMetricId.FAITHFULNESS_SUPPORTED,
            PublicMetricId.FAITHFULNESS_PARTIALLY_SUPPORTED,
            PublicMetricId.FAITHFULNESS_UNSUPPORTED,
            PublicMetricId.FAITHFULNESS_CONTRADICTED,
        }
    ),
    ScoringDimension.CITED_SOURCE_SUPPORT: frozenset(
        {PublicMetricId.CITATION_GROUNDEDNESS_JUDGE_ONLY}
    ),
    ScoringDimension.CLAIM_MAPPING: frozenset(
        {
            PublicMetricId.CITATION_GROUNDEDNESS_GOLD_MATCHED,
            PublicMetricId.CITATION_GROUNDEDNESS_JUDGE_ONLY,
        }
    ),
    ScoringDimension.GOLD_STATUS: frozenset(
        {
            PublicMetricId.GOLD_CLAIM_RECALL,
            PublicMetricId.ESSENTIAL_GOLD_CLAIM_RECALL,
        }
    ),
    ScoringDimension.MUST_NOT_TRIPWIRES: frozenset({PublicMetricId.MUST_NOT_CLAIM_VIOLATION}),
    ScoringDimension.RESPONSE_BEHAVIOR: frozenset(
        {
            PublicMetricId.OUT_OF_CORPUS_ABSTENTION,
            PublicMetricId.ADVERSARIAL_PREMISE_CORRECTION,
            PublicMetricId.FALSE_ABSTENTION,
        }
    ),
}


def _limitation_ids(
    modes: Mapping[ScoringDimension, ScoringMode],
    metrics: Sequence[PublicMetric],
) -> tuple[PublicLimitationId, ...]:
    pending_metric_ids = {
        metric.metric_id for metric in metrics if metric.availability is MetricAvailability.PENDING
    }
    pending = tuple(
        _PENDING_LIMITATION_BY_DIMENSION[dimension]
        for dimension in ScoringDimension
        if modes[dimension] is ScoringMode.MANUAL
        and pending_metric_ids & _METRICS_BY_DIMENSION[dimension]
    )
    return _BASE_LIMITATIONS + pending


def _metric(
    metric_id: PublicMetricId,
    *,
    numerator: int | None,
    denominator: int,
    available: bool,
) -> PublicMetric:
    if denominator == 0:
        return PublicMetric(
            metric_id=metric_id,
            availability=MetricAvailability.AVAILABLE,
            numerator=0,
            denominator=0,
            value=None,
        )
    if not available:
        return PublicMetric(
            metric_id=metric_id,
            availability=MetricAvailability.PENDING,
            numerator=None,
            denominator=denominator,
            value=None,
        )
    if numerator is None:
        raise ValueError(f"available metric {metric_id.value} requires a numerator")
    return PublicMetric(
        metric_id=metric_id,
        availability=MetricAvailability.AVAILABLE,
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator,
    )


def _manual_claim(bundle: _ItemBundle, claim_id: str):
    if bundle.manual is None:
        return None
    return next((claim for claim in bundle.manual.claims if claim.claim_id == claim_id), None)


def _claim_mapping(
    bundle: _ItemBundle,
    claim: DecomposedClaim,
    modes: Mapping[ScoringDimension, ScoringMode],
) -> tuple[str, ...] | None:
    if modes[ScoringDimension.CLAIM_MAPPING] is ScoringMode.JUDGE:
        if bundle.rubric is None:
            raise ValueError(f"{bundle.generated.item_id}: judge claim mapping is missing")
        match = next(
            entry
            for entry in bundle.rubric.verdict.answer_claim_matches
            if entry.answer_claim_id == claim.claim_id
        )
        return tuple(match.gold_claim_ids)
    owner = _manual_claim(bundle, claim.claim_id)
    return None if owner is None else owner.gold_match_ids


def _source_label(
    bundle: _ItemBundle,
    claim: DecomposedClaim,
    source_number: int,
    modes: Mapping[ScoringDimension, ScoringMode],
) -> CitedSourceLabel | None:
    if modes[ScoringDimension.CITED_SOURCE_SUPPORT] is ScoringMode.JUDGE:
        result = bundle.evidence.get(claim.claim_id)
        if result is None:
            raise ValueError(
                f"{bundle.generated.item_id}/{claim.claim_id}: judge source support is missing"
            )
        verdict = next(
            entry
            for entry in result.verdict.source_verdicts
            if entry.source_number == source_number
        )
        return CitedSourceLabel(verdict.label)
    owner = _manual_claim(bundle, claim.claim_id)
    if owner is None or owner.cited_source_labels is None:
        return None
    return owner.cited_source_labels.get(source_number)


def _faithfulness(
    bundle: _ItemBundle,
    claim: DecomposedClaim,
    modes: Mapping[ScoringDimension, ScoringMode],
) -> FaithfulnessLabel | None:
    if modes[ScoringDimension.FAITHFULNESS] is ScoringMode.JUDGE:
        result = bundle.evidence.get(claim.claim_id)
        if result is None:
            raise ValueError(
                f"{bundle.generated.item_id}/{claim.claim_id}: judge faithfulness is missing"
            )
        return FaithfulnessLabel(result.verdict.faithfulness)
    owner = _manual_claim(bundle, claim.claim_id)
    return None if owner is None else owner.faithfulness


def _gold_statuses(
    bundle: _ItemBundle,
    modes: Mapping[ScoringDimension, ScoringMode],
) -> tuple[GoldClaimStatus, ...] | None:
    if modes[ScoringDimension.GOLD_STATUS] is ScoringMode.JUDGE:
        if bundle.rubric is None:
            raise ValueError(f"{bundle.generated.item_id}: judge gold statuses are missing")
        return tuple(GoldClaimStatus(entry.status) for entry in bundle.rubric.verdict.gold_claims)
    if bundle.manual is None or any(
        entry.status is None for entry in bundle.manual.gold_claim_statuses
    ):
        return None
    return tuple(entry.status for entry in bundle.manual.gold_claim_statuses if entry.status)


def _tripwire_statuses(
    bundle: _ItemBundle,
    modes: Mapping[ScoringDimension, ScoringMode],
) -> tuple[MustNotClaimStatus, ...] | None:
    if modes[ScoringDimension.MUST_NOT_TRIPWIRES] is ScoringMode.JUDGE:
        if bundle.rubric is None:
            raise ValueError(f"{bundle.generated.item_id}: judge tripwire statuses are missing")
        return tuple(
            MustNotClaimStatus(entry.status) for entry in bundle.rubric.verdict.must_not_claim
        )
    if bundle.manual is None or any(
        entry.status is None for entry in bundle.manual.must_not_claim_statuses
    ):
        return None
    return tuple(entry.status for entry in bundle.manual.must_not_claim_statuses if entry.status)


def _response_behavior(
    bundle: _ItemBundle,
    modes: Mapping[ScoringDimension, ScoringMode],
) -> ResponseBehavior | None:
    if modes[ScoringDimension.RESPONSE_BEHAVIOR] is ScoringMode.JUDGE:
        if bundle.rubric is None:
            raise ValueError(f"{bundle.generated.item_id}: judge response behavior is missing")
        return ResponseBehavior(bundle.rubric.verdict.response_behavior)
    return None if bundle.manual is None else bundle.manual.response_behavior


def _score_metrics(
    bundles: Sequence[_ItemBundle],
    modes: Mapping[ScoringDimension, ScoringMode],
) -> tuple[PublicMetric, ...]:
    audits = [
        audit_citations(bundle.generated.answer, source_count=len(bundle.generated.sources))
        for bundle in bundles
    ]
    citation_references = sum(audit.source_reference_count for audit in audits)
    resolved_references = sum(audit.resolvable_reference_count for audit in audits)
    malformed = sum(audit.malformed_bracket_token_count for audit in audits)
    bracket_tokens = malformed + sum(audit.well_formed_group_count for audit in audits)

    claims = [(bundle, claim) for bundle in bundles for claim in bundle.decomposition.claims]
    cited_claims = sum(bool(claim.cited_source_numbers) for _, claim in claims)

    mappings: dict[tuple[str, str], tuple[str, ...] | None] = {
        (bundle.generated.item_id, claim.claim_id): _claim_mapping(bundle, claim, modes)
        for bundle, claim in claims
        if claim.cited_source_numbers
    }
    cited_pair_count = sum(len(claim.cited_source_numbers) for _, claim in claims)
    mapping_available = all(value is not None for value in mappings.values())
    gold_grounded = 0
    gold_pairs = 0
    judge_grounded = 0
    judge_pairs = 0
    source_support_available = True
    if mapping_available:
        for bundle, claim in claims:
            mapping = mappings.get((bundle.generated.item_id, claim.claim_id))
            if mapping is None:
                continue
            gold_by_id = {entry.claim_id: entry for entry in bundle.gold.claims}
            support_union = frozenset(
                chunk_id
                for gold_id in mapping
                for chunk_id in gold_by_id[gold_id].supporting_chunk_ids
            )
            for source_number in claim.cited_source_numbers:
                if mapping:
                    gold_pairs += 1
                    source = bundle.generated.sources[source_number - 1]
                    gold_grounded += int(source.chunk_id in support_union)
                else:
                    judge_pairs += 1
                    label = _source_label(bundle, claim, source_number, modes)
                    if label is None:
                        source_support_available = False
                    else:
                        judge_grounded += int(label is CitedSourceLabel.SUPPORTED)

    faithfulness_values = [_faithfulness(bundle, claim, modes) for bundle, claim in claims]
    faithfulness_available = all(value is not None for value in faithfulness_values)

    gold_records: list[tuple[_GoldClaim, GoldClaimStatus | None]] = []
    gold_status_available = True
    for bundle in bundles:
        statuses = _gold_statuses(bundle, modes)
        if statuses is None:
            if bundle.gold.claims:
                gold_status_available = False
            gold_records.extend((claim, None) for claim in bundle.gold.claims)
        else:
            gold_records.extend(zip(bundle.gold.claims, statuses, strict=True))
    essential_records = [record for record in gold_records if record[0].essential]

    tripwire_denominator = sum(len(bundle.gold.must_not_claim) for bundle in bundles)
    tripwire_values: list[MustNotClaimStatus] = []
    tripwire_available = True
    for bundle in bundles:
        statuses = _tripwire_statuses(bundle, modes)
        if statuses is None:
            if bundle.gold.must_not_claim:
                tripwire_available = False
        else:
            tripwire_values.extend(statuses)

    behavior_values = [_response_behavior(bundle, modes) for bundle in bundles]
    out_indices = [
        index
        for index, bundle in enumerate(bundles)
        if bundle.gold.stratum is EvaluationStratum.OUT_OF_CORPUS
    ]
    adversarial_indices = [
        index
        for index, bundle in enumerate(bundles)
        if bundle.gold.stratum is EvaluationStratum.ADVERSARIAL_PREMISE
    ]
    answerable_indices = [
        index
        for index, bundle in enumerate(bundles)
        if bundle.gold.expected_behavior is ExpectedBehavior.ANSWER
        and bundle.gold.stratum is not EvaluationStratum.OUT_OF_CORPUS
    ]
    out_behavior_available = all(behavior_values[index] is not None for index in out_indices)
    adversarial_behavior_available = all(
        behavior_values[index] is not None for index in adversarial_indices
    )
    answerable_behavior_available = all(
        behavior_values[index] is not None for index in answerable_indices
    )

    metrics = [
        _metric(
            PublicMetricId.CITATION_RESOLVABILITY,
            numerator=resolved_references,
            denominator=citation_references,
            available=True,
        ),
        _metric(
            PublicMetricId.CITATION_COMPLETENESS,
            numerator=cited_claims,
            denominator=len(claims),
            available=True,
        ),
        _metric(
            PublicMetricId.MALFORMED_CITATION_RATE,
            numerator=malformed,
            denominator=bracket_tokens,
            available=True,
        ),
        _metric(
            PublicMetricId.CITATION_GROUNDEDNESS_GOLD_MATCHED,
            numerator=gold_grounded if mapping_available else None,
            denominator=gold_pairs if mapping_available else cited_pair_count,
            available=mapping_available,
        ),
        _metric(
            PublicMetricId.CITATION_GROUNDEDNESS_JUDGE_ONLY,
            numerator=judge_grounded if mapping_available and source_support_available else None,
            denominator=judge_pairs if mapping_available else cited_pair_count,
            available=mapping_available and source_support_available,
        ),
    ]
    for metric_id, label in (
        (PublicMetricId.FAITHFULNESS_SUPPORTED, FaithfulnessLabel.SUPPORTED),
        (
            PublicMetricId.FAITHFULNESS_PARTIALLY_SUPPORTED,
            FaithfulnessLabel.PARTIALLY_SUPPORTED,
        ),
        (PublicMetricId.FAITHFULNESS_UNSUPPORTED, FaithfulnessLabel.UNSUPPORTED),
        (PublicMetricId.FAITHFULNESS_CONTRADICTED, FaithfulnessLabel.CONTRADICTED),
    ):
        metrics.append(
            _metric(
                metric_id,
                numerator=(
                    sum(value is label for value in faithfulness_values)
                    if faithfulness_available
                    else None
                ),
                denominator=len(claims),
                available=faithfulness_available,
            )
        )
    metrics.extend(
        [
            _metric(
                PublicMetricId.GOLD_CLAIM_RECALL,
                numerator=(
                    sum(status is GoldClaimStatus.PRESENT for _, status in gold_records)
                    if gold_status_available
                    else None
                ),
                denominator=len(gold_records),
                available=gold_status_available,
            ),
            _metric(
                PublicMetricId.ESSENTIAL_GOLD_CLAIM_RECALL,
                numerator=(
                    sum(status is GoldClaimStatus.PRESENT for _, status in essential_records)
                    if gold_status_available
                    else None
                ),
                denominator=len(essential_records),
                available=gold_status_available,
            ),
            _metric(
                PublicMetricId.MUST_NOT_CLAIM_VIOLATION,
                numerator=(
                    sum(value is MustNotClaimStatus.ASSERTED for value in tripwire_values)
                    if tripwire_available
                    else None
                ),
                denominator=tripwire_denominator,
                available=tripwire_available,
            ),
            _metric(
                PublicMetricId.OUT_OF_CORPUS_ABSTENTION,
                numerator=(
                    sum(behavior_values[index] is ResponseBehavior.DECLINE for index in out_indices)
                    if out_behavior_available
                    else None
                ),
                denominator=len(out_indices),
                available=out_behavior_available,
            ),
            _metric(
                PublicMetricId.ADVERSARIAL_PREMISE_CORRECTION,
                numerator=(
                    sum(
                        behavior_values[index] is ResponseBehavior.PREMISE_CORRECTION
                        for index in adversarial_indices
                    )
                    if adversarial_behavior_available
                    else None
                ),
                denominator=len(adversarial_indices),
                available=adversarial_behavior_available,
            ),
            _metric(
                PublicMetricId.FALSE_ABSTENTION,
                numerator=(
                    sum(
                        behavior_values[index] is ResponseBehavior.DECLINE
                        for index in answerable_indices
                    )
                    if answerable_behavior_available
                    else None
                ),
                denominator=len(answerable_indices),
                available=answerable_behavior_available,
            ),
            _metric(
                PublicMetricId.ANSWER_SUCCESS,
                numerator=sum(
                    bundle.generated.status in _SUCCESSFUL_RELEASES for bundle in bundles
                ),
                denominator=len(bundles),
                available=True,
            ),
        ]
    )
    if [metric.metric_id for metric in metrics] != list(PublicMetricId):
        raise AssertionError("reporting metric order diverged from PublicMetricId")
    return tuple(metrics)


def _cost(
    bundles: Sequence[_ItemBundle],
    claim_evidence_results: Sequence[ClaimEvidenceResult],
    item_rubric_results: Sequence[ItemRubricResult],
    additional_usage_events: Sequence[PrivateUsageEvent],
) -> PublicCost:
    events = [event for bundle in bundles for event in bundle.generated.usage_events]
    events.extend(result.usage_event for result in claim_evidence_results)
    events.extend(result.usage_event for result in item_rubric_results)
    events.extend(additional_usage_events)
    return _cost_from_usage_events(events)


def _cost_from_usage_events(events: Sequence[PrivateUsageEvent]) -> PublicCost:
    response_ids = [event.response_id for event in events]
    if len(response_ids) != len(set(response_ids)):
        raise ValueError("public cost inputs contain duplicate provider response IDs")
    unpriced = sum(event.unpriced for event in events)
    priced = len(events) - unpriced
    estimated = (
        None
        if unpriced
        else sum(event.estimated_cost_nano_usd or 0 for event in events) / 1_000_000_000
    )
    return PublicCost(
        estimated_cost_usd=estimated,
        priced_event_count=priced,
        unpriced_event_count=unpriced,
    )


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _latency(bundles: Sequence[_ItemBundle]) -> PublicLatency:
    return _latency_from_seconds([bundle.generated.elapsed_seconds for bundle in bundles])


def _latency_from_seconds(values: Sequence[float]) -> PublicLatency:
    if not values:
        raise ValueError("latency requires at least one exact observation")
    total = sum(values)
    return PublicLatency(
        total_seconds=total,
        mean_seconds=total / len(values),
        p50_seconds=_percentile(values, 0.50),
        p95_seconds=_percentile(values, 0.95),
        maximum_seconds=max(values),
    )


def _precalibration_metric(
    metric_id: PrecalibrationMetricId,
    *,
    numerator: int | None,
    denominator: int,
    available: bool,
) -> PrecalibrationPublicMetric:
    if denominator == 0:
        return PrecalibrationPublicMetric(
            metric_id=metric_id,
            availability=MetricAvailability.AVAILABLE,
            numerator=0,
            denominator=0,
            value=None,
        )
    if not available:
        return PrecalibrationPublicMetric(
            metric_id=metric_id,
            availability=MetricAvailability.PENDING,
            numerator=None,
            denominator=denominator,
            value=None,
        )
    if numerator is None:
        raise ValueError(f"available metric {metric_id.value} requires a numerator")
    return PrecalibrationPublicMetric(
        metric_id=metric_id,
        availability=MetricAvailability.AVAILABLE,
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator,
    )


def _gold_location_ids(gold: _GoldItem) -> frozenset[str]:
    return frozenset(
        set(gold.relevant_chunk_ids).union(
            chunk_id for claim in gold.claims for chunk_id in claim.supporting_chunk_ids
        )
    )


def _precalibration_metrics(
    bundles: Sequence[_ItemBundle],
    *,
    generated_items: Sequence[PrivateGeneratedItem],
    gold_items: Sequence[_GoldItem],
) -> tuple[PrecalibrationPublicMetric, ...]:
    audits = [
        audit_citations(generated.answer, source_count=len(generated.sources))
        for generated in generated_items
    ]
    citation_references = sum(audit.source_reference_count for audit in audits)
    resolved_references = sum(audit.resolvable_reference_count for audit in audits)
    malformed = sum(audit.malformed_bracket_token_count for audit in audits)
    bracket_tokens = malformed + sum(audit.well_formed_group_count for audit in audits)
    claims = [(bundle, claim) for bundle in bundles for claim in bundle.decomposition.claims]
    cited_claims = sum(bool(claim.cited_source_numbers) for _, claim in claims)
    cited_pairs = [
        (bundle, source_number)
        for bundle, claim in claims
        for source_number in claim.cited_source_numbers
    ]
    cited_gold_location_matches = sum(
        bundle.generated.sources[source_number - 1].chunk_id in _gold_location_ids(bundle.gold)
        for bundle, source_number in cited_pairs
    )
    gold_location_pairs = [
        (generated, gold, chunk_id)
        for generated, gold in zip(generated_items, gold_items, strict=True)
        for chunk_id in _gold_location_ids(gold)
    ]
    retrieved_gold_locations = sum(
        chunk_id in {source.chunk_id for source in generated.sources}
        for generated, _gold, chunk_id in gold_location_pairs
    )
    gold_claim_count = sum(len(bundle.gold.claims) for bundle in bundles)
    essential_gold_claim_count = sum(
        claim.essential for bundle in bundles for claim in bundle.gold.claims
    )
    tripwire_count = sum(len(bundle.gold.must_not_claim) for bundle in bundles)
    out_of_corpus_count = sum(
        gold.stratum is EvaluationStratum.OUT_OF_CORPUS for gold in gold_items
    )
    adversarial_count = sum(
        gold.stratum is EvaluationStratum.ADVERSARIAL_PREMISE for gold in gold_items
    )
    answerable_count = sum(
        gold.expected_behavior is ExpectedBehavior.ANSWER
        and gold.stratum is not EvaluationStratum.OUT_OF_CORPUS
        for gold in gold_items
    )
    metrics = (
        _precalibration_metric(
            PrecalibrationMetricId.CITATION_RESOLVABILITY,
            numerator=resolved_references,
            denominator=citation_references,
            available=True,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.CITATION_COMPLETENESS,
            numerator=cited_claims,
            denominator=len(claims),
            available=True,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.MALFORMED_CITATION_RATE,
            numerator=malformed,
            denominator=bracket_tokens,
            available=True,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.CITED_SOURCE_GOLD_LOCATION_MATCH,
            numerator=cited_gold_location_matches,
            denominator=len(cited_pairs),
            available=True,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.GOLD_LOCATION_RETRIEVAL_COVERAGE,
            numerator=retrieved_gold_locations,
            denominator=len(gold_location_pairs),
            available=True,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.CITATION_GROUNDEDNESS,
            numerator=None,
            denominator=len(cited_pairs),
            available=False,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.FAITHFULNESS_SUPPORTED,
            numerator=None,
            denominator=len(claims),
            available=False,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.FAITHFULNESS_PARTIALLY_SUPPORTED,
            numerator=None,
            denominator=len(claims),
            available=False,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.FAITHFULNESS_UNSUPPORTED,
            numerator=None,
            denominator=len(claims),
            available=False,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.FAITHFULNESS_CONTRADICTED,
            numerator=None,
            denominator=len(claims),
            available=False,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.GOLD_CLAIM_RECALL,
            numerator=None,
            denominator=gold_claim_count,
            available=False,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.ESSENTIAL_GOLD_CLAIM_RECALL,
            numerator=None,
            denominator=essential_gold_claim_count,
            available=False,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.MUST_NOT_CLAIM_VIOLATION,
            numerator=None,
            denominator=tripwire_count,
            available=False,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.OUT_OF_CORPUS_ABSTENTION,
            numerator=None,
            denominator=out_of_corpus_count,
            available=False,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.ADVERSARIAL_PREMISE_CORRECTION,
            numerator=None,
            denominator=adversarial_count,
            available=False,
        ),
        _precalibration_metric(
            PrecalibrationMetricId.FALSE_ABSTENTION,
            numerator=None,
            denominator=answerable_count,
            available=False,
        ),
    )
    if [metric.metric_id for metric in metrics] != list(PrecalibrationMetricId):
        raise AssertionError("precalibration metric order diverged from its closed enum")
    return metrics


def _normalize_decomposition_checkpoints(
    values: Sequence[PrivateDecompositionOutcome | Mapping[str, object]],
) -> tuple[PrivateDecompositionOutcome, ...]:
    normalized: list[PrivateDecompositionOutcome] = []
    for value in values:
        if isinstance(
            value,
            (PrivateDecompositionCheckpoint, PrivateDecompositionFailureCheckpoint),
        ):
            normalized.append(value)
            continue
        schema = value.get("schema")
        model = (
            PrivateDecompositionFailureCheckpoint
            if schema == PRIVATE_DECOMPOSITION_FAILURE_CHECKPOINT_SCHEMA
            else PrivateDecompositionCheckpoint
        )
        normalized.append(model.model_validate(value))
    return tuple(normalized)


def build_public_precalibration_summary(
    *,
    candidate_id: str,
    cohort_manifest: AnswerEvaluationCohortManifest | Mapping[str, object],
    generated_items: Sequence[PrivateGeneratedItem | Mapping[str, object]],
    decompositions: Sequence[DecomposedPilotItem | Mapping[str, object]],
    gold_items: Sequence[Mapping[str, object]],
    decomposition_checkpoints: Sequence[PrivateDecompositionOutcome | Mapping[str, object]],
    private_artifact: PrecalibrationPrivateArtifact | Mapping[str, object],
    migration_artifact_sha256: str | None = None,
    recovered_item_ids: Sequence[str] = (),
) -> PublicPrecalibrationSummary:
    """Emit the exact mechanical result before semantic calibration or judging."""

    generated = _normalize_generated(generated_items)
    decomposed = _normalize_decompositions(decompositions)
    gold_raw = tuple(dict(item) for item in gold_items)
    gold = tuple(_parse_gold_item(item) for item in gold_raw)
    checkpoints = _normalize_decomposition_checkpoints(decomposition_checkpoints)
    manifest = (
        cohort_manifest
        if isinstance(cohort_manifest, AnswerEvaluationCohortManifest)
        else AnswerEvaluationCohortManifest.model_validate(cohort_manifest)
    )
    artifact = (
        private_artifact
        if isinstance(private_artifact, PrecalibrationPrivateArtifact)
        else PrecalibrationPrivateArtifact.model_validate(private_artifact)
    )
    if len(generated) != 37 or len(gold) != 37 or len(checkpoints) != 37:
        raise ValueError(
            "public precalibration result requires 37 generated items, gold items, and attempts"
        )
    ids = [item.item_id for item in generated]
    if len(ids) != len(set(ids)):
        raise ValueError("generated precalibration item IDs must be unique")
    if [item.item_id for item in gold] != ids:
        raise ValueError("generated and gold order must match exactly")
    decomposition_ids = [item.item_id for item in decomposed]
    if decomposition_ids != [item_id for item_id in ids if item_id in decomposition_ids]:
        raise ValueError("usable decompositions must retain cohort-relative order")
    if [item.item_id for item in manifest.items] != ids:
        raise ValueError("cohort manifest item order differs from the frozen cohort")
    cohort_manifest_file_sha256 = hashlib.sha256(
        canonical_json_bytes(manifest, pretty=True)
    ).hexdigest()
    for manifest_item, generated_item, gold_item in zip(
        manifest.items,
        generated,
        gold,
        strict=True,
    ):
        if (
            generated_item.question != gold_item.question
            or manifest_item.question_sha256 != sha256_text(gold_item.question)
            or manifest_item.question_sha256 != generated_item.question_sha256
            or manifest_item.stratum is not gold_item.stratum
            or manifest_item.stratum is not generated_item.stratum
            or manifest_item.expected_behavior is not gold_item.expected_behavior
            or manifest_item.expected_behavior is not generated_item.expected_behavior
        ):
            raise ValueError(
                f"{generated_item.item_id}: cohort, generation, or gold binding changed"
            )
    if artifact.cohort_manifest_sha256 != cohort_manifest_file_sha256:
        raise ValueError("precalibration artifact belongs to another cohort manifest")
    if artifact.gold_set_sha256 != manifest.gold_set_sha256:
        raise ValueError("precalibration artifact belongs to another gold set")
    decomposition_prompt = _manifest_prompt(manifest, "claim_decomposition")
    generated_by_id = {item.item_id: item for item in generated}
    decomposition_by_id = {item.item_id: item for item in decomposed}
    successful_ids: list[str] = []
    for expected_item_id, checkpoint in zip(ids, checkpoints, strict=True):
        if (
            checkpoint.item_id != expected_item_id
            or checkpoint.answer_sha256 != generated_by_id[expected_item_id].answer_sha256
            or checkpoint.cohort_manifest_sha256 != cohort_manifest_file_sha256
            or checkpoint.prompt_version != decomposition_prompt.version
            or checkpoint.prompt_sha256 != decomposition_prompt.prompt_sha256
            or checkpoint.judge_model != manifest.judge.model_id
            or checkpoint.judge_settings != manifest.judge.settings
        ):
            raise ValueError("decomposition checkpoint differs from the cohort contract")
        if isinstance(checkpoint, PrivateDecompositionCheckpoint):
            decomposition = decomposition_by_id.get(checkpoint.item_id)
            if decomposition is None or checkpoint.decomposition != decomposition:
                raise ValueError("successful decomposition checkpoint changed")
            _validate_decomposition(generated_by_id[checkpoint.item_id], decomposition)
            successful_ids.append(checkpoint.item_id)
        elif checkpoint.item_id in decomposition_by_id:
            raise ValueError("failed decomposition checkpoint has a usable decomposition")
    if successful_ids != decomposition_ids:
        raise ValueError("usable decomposition set differs from successful checkpoints")
    validate_precalibration_private_artifact(
        artifact,
        cohort_manifest_sha256=cohort_manifest_file_sha256,
        generation_artifact_sha256=artifact.generation_artifact_sha256,
        decomposition_artifact_sha256=artifact.decomposition_artifact_sha256,
        gold_set_sha256=manifest.gold_set_sha256,
        generated_items=generated,
        decompositions=decomposed,
        gold_items=gold_raw,
        decomposition_checkpoints=checkpoints,
        migration_artifact_sha256=migration_artifact_sha256,
        recovered_item_ids=recovered_item_ids,
    )
    gold_by_id = {item.item_id: item for item in gold}
    bundles = tuple(
        _ItemBundle(
            generated=generated_by_id[decomposition.item_id],
            decomposition=decomposition,
            gold=gold_by_id[decomposition.item_id],
            evidence={},
            rubric=None,
            manual=None,
        )
        for decomposition in decomposed
    )
    metrics = _precalibration_metrics(
        bundles,
        generated_items=generated,
        gold_items=gold,
    )
    checkpoint_usage = tuple(checkpoint.usage_events[0] for checkpoint in checkpoints)
    recovered_ids = frozenset(artifact.recovered_item_ids)
    exact_latency_items = tuple(item for item in generated if item.item_id not in recovered_ids)
    limitations = (
        PublicLimitationId.CANONICAL_MODEL_ID_MUTABILITY,
        PublicLimitationId.GENERATOR_SPREAD_UNMEASURED,
        PublicLimitationId.DESCRIPTIVE_NOT_GATE,
        PublicLimitationId.SEMANTIC_SCORING_PENDING,
        *(
            (PublicLimitationId.TRACE_RECOVERED_ITEM_PRESENT,)
            if artifact.recovered_item_count
            else ()
        ),
        *(
            (PublicLimitationId.DECOMPOSITION_TECHNICAL_FAILURE_PRESENT,)
            if artifact.decomposition_technical_failure_count
            else ()
        ),
    )
    return PublicPrecalibrationSummary(
        evaluation_id=manifest.evaluation_id,
        candidate_id=candidate_id,
        candidate_commit=manifest.candidate_commit,
        rag_policy=manifest.rag_policy,
        cohort_manifest_sha256=cohort_manifest_file_sha256,
        corpus_manifest_sha256=manifest.corpus_manifest_sha256,
        chunks_sha256=manifest.chunks_sha256,
        question_set_sha256=manifest.question_set_sha256,
        model_catalog_sha256=manifest.model_catalog_sha256,
        runner_sha256=manifest.runner_sha256,
        planner_model_id=manifest.planner.model_id,
        generator_model_id=manifest.generator.model_id,
        decomposer_model_id=manifest.judge.model_id,
        embedding_model_id=manifest.embedding_model,
        private_artifact_sha256=artifact.artifact_sha256,
        generation_artifact_sha256=artifact.generation_artifact_sha256,
        decomposition_artifact_sha256=artifact.decomposition_artifact_sha256,
        gold_set_sha256=manifest.gold_set_sha256,
        migration_artifact_sha256=artifact.migration_artifact_sha256,
        recovered_item_count=artifact.recovered_item_count,
        decomposition_attempt_count=artifact.decomposition_attempt_count,
        usable_decomposition_count=artifact.usable_decomposition_count,
        decomposition_technical_failure_count=(artifact.decomposition_technical_failure_count),
        limitation_ids=limitations,
        run_status=BaselineRunStatus.COMPLETE,
        generation_latency_denominator=artifact.generation_latency_denominator,
        generation_latency_observed_count=(artifact.generation_latency_observed_count),
        item_count=37,
        source_count=sum(len(item.sources) for item in generated),
        claim_count=sum(len(bundle.decomposition.claims) for bundle in bundles),
        citation_count=sum(
            audit_citations(
                item.answer,
                source_count=len(item.sources),
            ).source_reference_count
            for item in generated
        ),
        completed_answer_count=sum(item.status in _SUCCESSFUL_RELEASES for item in generated),
        technical_error_count=sum(item.status in _TECHNICAL_FAILURES for item in generated),
        metrics=metrics,
        strata=tuple(
            PrecalibrationPublicStratumSummary(
                stratum=stratum,
                item_count=sum(item.stratum is stratum for item in gold),
                metrics=_precalibration_metrics(
                    [bundle for bundle in bundles if bundle.gold.stratum is stratum],
                    generated_items=[item for item in generated if item.stratum is stratum],
                    gold_items=[item for item in gold if item.stratum is stratum],
                ),
            )
            for stratum in EvaluationStratum
        ),
        cost=_cost_from_usage_events(
            [event for item in generated for event in item.usage_events] + list(checkpoint_usage)
        ),
        latency=_latency_from_seconds([item.elapsed_seconds for item in exact_latency_items]),
    )


def build_public_evaluation_summary(
    *,
    candidate_id: str,
    cohort_manifest: AnswerEvaluationCohortManifest | Mapping[str, object],
    generated_items: Sequence[PrivateGeneratedItem | Mapping[str, object]],
    decompositions: Sequence[DecomposedPilotItem | Mapping[str, object]],
    gold_items: Sequence[Mapping[str, object]],
    semantic_aggregate: BaselineSemanticAggregate | Mapping[str, object],
    calibration_semantic_aggregate: CalibrationSemanticAggregate | Mapping[str, object],
    additional_usage_events: Sequence[PrivateUsageEvent | Mapping[str, object]],
    private_full_run_artifact: PrivateFullRunArtifact | Mapping[str, object],
    instrument_lock: InstrumentLock | Mapping[str, object],
    manual_scoring_aggregate: ManualScoringAggregate | Mapping[str, object] | None = None,
) -> PublicEvaluationSummary:
    """Score the exact frozen 37-item cohort and return a closed public summary.

    The supplied full-run artifact is re-derived from these exact inputs.  Its
    hash therefore binds every public score, including optional full-cohort
    manual decisions, without exposing private prose.
    """

    generated = _normalize_generated(generated_items)
    decomposed = _normalize_decompositions(decompositions)
    gold = tuple(_parse_gold_item(item) for item in gold_items)
    manifest = (
        cohort_manifest
        if isinstance(cohort_manifest, AnswerEvaluationCohortManifest)
        else AnswerEvaluationCohortManifest.model_validate(cohort_manifest)
    )
    instrument = (
        instrument_lock
        if isinstance(instrument_lock, InstrumentLock)
        else InstrumentLock.model_validate(instrument_lock)
    )
    semantic = (
        semantic_aggregate
        if isinstance(semantic_aggregate, BaselineSemanticAggregate)
        else BaselineSemanticAggregate.model_validate(semantic_aggregate)
    )
    calibration_semantic = (
        calibration_semantic_aggregate
        if isinstance(calibration_semantic_aggregate, CalibrationSemanticAggregate)
        else CalibrationSemanticAggregate.model_validate(calibration_semantic_aggregate)
    )
    additional_usage = tuple(
        event if isinstance(event, PrivateUsageEvent) else PrivateUsageEvent.model_validate(event)
        for event in additional_usage_events
    )
    manual_aggregate = (
        None
        if manual_scoring_aggregate is None
        else manual_scoring_aggregate
        if isinstance(manual_scoring_aggregate, ManualScoringAggregate)
        else ManualScoringAggregate.model_validate(manual_scoring_aggregate)
    )
    full_run = (
        private_full_run_artifact
        if isinstance(private_full_run_artifact, PrivateFullRunArtifact)
        else PrivateFullRunArtifact.model_validate(private_full_run_artifact)
    )
    evidence_results = tuple(
        result for item in semantic.items for result in item.first_call_claim_evidence
    )
    rubric_results = tuple(
        item.item_rubric for item in semantic.items if item.item_rubric is not None
    )
    manual = () if manual_aggregate is None else manual_aggregate.items
    if not (len(generated) == len(decomposed) == len(gold) == 37):
        raise ValueError(
            "public baseline requires exactly 37 generated, decomposed, and gold items"
        )
    ids = [item.item_id for item in generated]
    if len(ids) != len(set(ids)):
        raise ValueError("generated baseline item IDs must be unique")
    if [item.item_id for item in decomposed] != ids or [item.item_id for item in gold] != ids:
        raise ValueError("generated, decomposition, and gold item order must match exactly")
    if [item.item_id for item in manifest.items] != ids:
        raise ValueError("cohort manifest item order differs from the frozen cohort")
    for manifest_item, generated_item, gold_item in zip(
        manifest.items,
        generated,
        gold,
        strict=True,
    ):
        if (
            manifest_item.question_sha256 != sha256_text(gold_item.question)
            or manifest_item.question_sha256 != sha256_text(generated_item.question)
            or manifest_item.stratum is not gold_item.stratum
            or manifest_item.expected_behavior is not gold_item.expected_behavior
        ):
            raise ValueError(f"{generated_item.item_id}: cohort manifest differs from frozen gold")
    if list(semantic.item_ids) != ids:
        raise ValueError("baseline semantic item order differs from the frozen cohort")
    cohort_manifest_file_sha256 = hashlib.sha256(
        canonical_json_bytes(manifest, pretty=True)
    ).hexdigest()
    if (
        cohort_manifest_file_sha256 != instrument.cohort_manifest_sha256
        or semantic.cohort_manifest_sha256 != instrument.cohort_manifest_sha256
        or semantic.instrument_sha256 != instrument.instrument_sha256
    ):
        raise ValueError("baseline semantic aggregate differs from the instrument lock")
    evidence_prompt = _manifest_prompt(manifest, "claim_evidence")
    rubric_prompt = _manifest_prompt(manifest, "item_rubric")
    if (
        instrument.evidence_prompt_sha256 != evidence_prompt.prompt_sha256
        or instrument.rubric_prompt_sha256 != rubric_prompt.prompt_sha256
        or instrument.judge_model != manifest.judge.model_id
        or instrument.judge_settings != manifest.judge.settings
    ):
        raise ValueError("instrument judge contract differs from the cohort manifest")
    sanitized_rubrics = tuple(_sanitized_rubric(item) for item in gold)
    validate_baseline_semantic_aggregate(
        semantic,
        cohort_manifest_sha256=instrument.cohort_manifest_sha256,
        generation_artifact_sha256=semantic.generation_artifact_sha256,
        decomposition_artifact_sha256=semantic.decomposition_artifact_sha256,
        item_ids=ids,
        generated_items=generated,
        decompositions=decomposed,
        rubrics=sanitized_rubrics,
        instrument_lock=instrument,
        evidence_prompt_version=evidence_prompt.version,
        evidence_prompt_sha256=instrument.evidence_prompt_sha256,
        rubric_prompt_version=rubric_prompt.version,
        rubric_prompt_sha256=instrument.rubric_prompt_sha256,
        judge_model=instrument.judge_model,
        judge_settings=instrument.judge_settings,
    )
    if manual_aggregate is not None:
        validate_manual_scoring_aggregate(
            manual_aggregate,
            cohort_manifest_sha256=instrument.cohort_manifest_sha256,
            generation_artifact_sha256=semantic.generation_artifact_sha256,
            decomposition_artifact_sha256=semantic.decomposition_artifact_sha256,
            instrument_lock=instrument,
            generated_items=generated,
            decompositions=decomposed,
            rubrics=sanitized_rubrics,
        )
    validate_calibration_semantic_aggregate(
        calibration_semantic,
        cohort_manifest_sha256=cohort_manifest_file_sha256,
        pilot_artifact_sha256=instrument.pilot_artifact_sha256,
        decomposition_artifact_sha256=instrument.decomposition_artifact_sha256,
        calibration_item_ids=manifest.calibration_item_ids,
    )
    validate_private_full_run_artifact(
        full_run,
        cohort_manifest_sha256=instrument.cohort_manifest_sha256,
        generation_artifact_sha256=semantic.generation_artifact_sha256,
        decomposition_artifact_sha256=semantic.decomposition_artifact_sha256,
        generated_items=generated,
        decompositions=decomposed,
        semantic_aggregate=semantic,
        instrument_lock=instrument,
        calibration_semantic_aggregate=calibration_semantic,
        additional_usage_events=additional_usage,
        manual_scoring_aggregate=manual_aggregate,
    )

    evidence_by_item: dict[str, dict[str, ClaimEvidenceResult]] = {item_id: {} for item_id in ids}
    for result in evidence_results:
        if result.cohort_manifest_sha256 != instrument.cohort_manifest_sha256:
            raise ValueError("claim-evidence result belongs to another cohort manifest")
        if (
            result.judge_model != instrument.judge_model
            or result.judge_settings != instrument.judge_settings
            or result.prompt_sha256 != instrument.evidence_prompt_sha256
        ):
            raise ValueError("claim-evidence result differs from the instrument lock")
        if result.item_id not in evidence_by_item:
            raise ValueError("claim-evidence result belongs to an unknown item")
        if result.claim.claim_id in evidence_by_item[result.item_id]:
            raise ValueError("duplicate first-call claim-evidence result")
        evidence_by_item[result.item_id][result.claim.claim_id] = result
    rubric_by_item: dict[str, ItemRubricResult] = {}
    for result in rubric_results:
        if result.cohort_manifest_sha256 != instrument.cohort_manifest_sha256:
            raise ValueError("item-rubric result belongs to another cohort manifest")
        if (
            result.judge_model != instrument.judge_model
            or result.judge_settings != instrument.judge_settings
            or result.prompt_sha256 != instrument.rubric_prompt_sha256
        ):
            raise ValueError("item-rubric result differs from the instrument lock")
        if result.item_id not in set(ids):
            raise ValueError("item-rubric result belongs to an unknown item")
        if result.item_id in rubric_by_item:
            raise ValueError("duplicate item-rubric result")
        rubric_by_item[result.item_id] = result
    manual_by_item = {item.item_id: item for item in manual}

    bundles: list[_ItemBundle] = []
    for generated_item, decomposition, gold_item in zip(
        generated,
        decomposed,
        gold,
        strict=True,
    ):
        if (
            generated_item.question != gold_item.question
            or generated_item.stratum is not gold_item.stratum
            or generated_item.expected_behavior is not gold_item.expected_behavior
        ):
            raise ValueError(f"{generated_item.item_id}: generated item differs from frozen gold")
        _validate_decomposition(generated_item, decomposition)
        bundle = _ItemBundle(
            generated=generated_item,
            decomposition=decomposition,
            gold=gold_item,
            evidence=evidence_by_item[generated_item.item_id],
            rubric=rubric_by_item.get(generated_item.item_id),
            manual=manual_by_item.get(generated_item.item_id),
        )
        _validate_manual(bundle)
        _validate_rubric_result(bundle)
        claim_by_id = {claim.claim_id: claim for claim in decomposition.claims}
        if not set(bundle.evidence) <= set(claim_by_id):
            raise ValueError(f"{generated_item.item_id}: evidence contains an unknown claim")
        for claim_id, result in bundle.evidence.items():
            _validate_evidence_result(bundle, claim_by_id[claim_id], result)
        bundles.append(bundle)

    modes = _dimension_modes(instrument)
    if modes[ScoringDimension.FAITHFULNESS] is ScoringMode.JUDGE:
        for bundle in bundles:
            if set(bundle.evidence) != {claim.claim_id for claim in bundle.decomposition.claims}:
                raise ValueError(
                    f"{bundle.generated.item_id}: judge faithfulness requires every claim result"
                )
    rubric_dimensions = (
        ScoringDimension.CLAIM_MAPPING,
        ScoringDimension.GOLD_STATUS,
        ScoringDimension.MUST_NOT_TRIPWIRES,
        ScoringDimension.RESPONSE_BEHAVIOR,
    )
    if any(modes[dimension] is ScoringMode.JUDGE for dimension in rubric_dimensions):
        missing = [bundle.generated.item_id for bundle in bundles if bundle.rubric is None]
        if missing:
            raise ValueError(f"judge rubric results are missing for items: {missing}")

    all_metrics = _score_metrics(bundles, modes)
    strata = tuple(
        PublicStratumSummary(
            stratum=stratum,
            item_count=sum(bundle.gold.stratum is stratum for bundle in bundles),
            metrics=_score_metrics(
                [bundle for bundle in bundles if bundle.gold.stratum is stratum],
                modes,
            ),
        )
        for stratum in EvaluationStratum
    )
    return PublicEvaluationSummary(
        evaluation_id=manifest.evaluation_id,
        candidate_id=candidate_id,
        candidate_commit=manifest.candidate_commit,
        rag_policy=manifest.rag_policy,
        cohort_manifest_sha256=cohort_manifest_file_sha256,
        corpus_manifest_sha256=manifest.corpus_manifest_sha256,
        chunks_sha256=manifest.chunks_sha256,
        question_set_sha256=manifest.question_set_sha256,
        model_catalog_sha256=manifest.model_catalog_sha256,
        runner_sha256=manifest.runner_sha256,
        planner_model_id=manifest.planner.model_id,
        generator_model_id=manifest.generator.model_id,
        judge_model_id=manifest.judge.model_id,
        embedding_model_id=manifest.embedding_model,
        private_artifact_sha256=full_run.artifact_sha256,
        instrument_lock_sha256=instrument.instrument_sha256,
        gold_set_sha256=manifest.gold_set_sha256,
        limitation_ids=_limitation_ids(modes, all_metrics),
        run_status=BaselineRunStatus.COMPLETE,
        scoring_mode=instrument.scoring_mode,
        item_count=37,
        source_count=sum(len(bundle.generated.sources) for bundle in bundles),
        claim_count=sum(len(bundle.decomposition.claims) for bundle in bundles),
        citation_count=sum(
            audit_citations(
                bundle.generated.answer,
                source_count=len(bundle.generated.sources),
            ).source_reference_count
            for bundle in bundles
        ),
        error_count=sum(bundle.generated.status in _TECHNICAL_FAILURES for bundle in bundles),
        metrics=all_metrics,
        strata=strata,
        cost=_cost(
            bundles,
            evidence_results,
            rubric_results,
            additional_usage,
        ),
        latency=_latency(bundles),
    )


def _markdown_ratio(metric: PublicMetric) -> str:
    if metric.availability is MetricAvailability.PENDING:
        return f"pending (denominator {metric.denominator})"
    if metric.denominator == 0:
        return "0/0 (not applicable)"
    return f"{metric.numerator}/{metric.denominator} ({metric.value:.3f})"


def render_public_evaluation_markdown(
    summary: PublicEvaluationSummary | Mapping[str, object],
    *,
    public_summary_json_sha256: str,
) -> str:
    """Render a deterministic report using only the closed public schema."""

    public = validate_public_summary(summary)
    if len(public_summary_json_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in public_summary_json_sha256
    ):
        raise ValueError("public summary JSON SHA-256 must be 64 lowercase hex characters")
    lines = [
        "# Archivist held-out evaluation",
        "",
        "## Identity",
        "",
        f"- Evaluation: `{public.evaluation_id}`",
        f"- Candidate: `{public.candidate_id}`",
        f"- Candidate commit: `{public.candidate_commit}`",
        f"- RAG policy: `{public.rag_policy}`",
        f"- Cohort manifest SHA-256: `{public.cohort_manifest_sha256}`",
        f"- Public summary JSON SHA-256: `{public_summary_json_sha256}`",
        f"- Private artifact SHA-256: `{public.private_artifact_sha256}`",
        f"- Instrument lock SHA-256: `{public.instrument_lock_sha256}`",
        f"- Gold set SHA-256: `{public.gold_set_sha256}`",
        f"- Corpus manifest SHA-256: `{public.corpus_manifest_sha256}`",
        f"- Chunks SHA-256: `{public.chunks_sha256}`",
        f"- Question set SHA-256: `{public.question_set_sha256}`",
        f"- Model catalog SHA-256: `{public.model_catalog_sha256}`",
        f"- Runner SHA-256: `{public.runner_sha256}`",
        "",
        "## Models",
        "",
        f"- Planner: `{public.planner_model_id}`",
        f"- Generator: `{public.generator_model_id}`",
        f"- Judge: `{public.judge_model_id}`",
        f"- Embedding: `{public.embedding_model_id}`",
        "",
        "## Cohort totals",
        "",
        f"- Run status: `{public.run_status.value}`",
        f"- Scoring mode: `{public.scoring_mode.value}`",
        f"- Items: {public.item_count}",
        f"- Sources: {public.source_count}",
        f"- Claims: {public.claim_count}",
        f"- Citation references: {public.citation_count}",
        f"- Technical errors: {public.error_count}",
        "",
        "## Aggregate metrics",
        "",
        "| Metric ID | Result |",
        "|---|---:|",
    ]
    lines.extend(
        f"| `{metric.metric_id.value}` | {_markdown_ratio(metric)} |" for metric in public.metrics
    )
    lines.extend(["", "## Strata", ""])
    for stratum in public.strata:
        lines.extend(
            [
                f"### `{stratum.stratum.value}` ({stratum.item_count})",
                "",
                "| Metric ID | Result |",
                "|---|---:|",
            ]
        )
        lines.extend(
            f"| `{metric.metric_id.value}` | {_markdown_ratio(metric)} |"
            for metric in stratum.metrics
        )
        lines.append("")
    lines.extend(
        [
            "## Cost and generation latency",
            "",
            f"- Estimated API cost (USD): {public.cost.estimated_cost_usd}",
            f"- Priced events: {public.cost.priced_event_count}",
            f"- Unpriced events: {public.cost.unpriced_event_count}",
            f"- Total generation seconds: {public.latency.total_seconds:.3f}",
            f"- Mean generation seconds: {public.latency.mean_seconds:.3f}",
            f"- P50 generation seconds: {public.latency.p50_seconds:.3f}",
            f"- P95 generation seconds: {public.latency.p95_seconds:.3f}",
            f"- Maximum generation seconds: {public.latency.maximum_seconds:.3f}",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- `{limitation.value}`" for limitation in public.limitation_ids)
    return "\n".join(lines) + "\n"


def _precalibration_markdown_ratio(metric: PrecalibrationPublicMetric) -> str:
    if metric.availability is MetricAvailability.PENDING:
        return f"pending (denominator {metric.denominator})"
    if metric.denominator == 0:
        return "0/0 (not applicable)"
    return f"{metric.numerator}/{metric.denominator} ({metric.value:.3f})"


def render_public_precalibration_markdown(
    summary: PublicPrecalibrationSummary | Mapping[str, object],
    *,
    public_summary_json_sha256: str,
) -> str:
    """Render the deterministic, text-free result available before calibration."""

    public = validate_public_precalibration_summary(summary)
    if len(public_summary_json_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in public_summary_json_sha256
    ):
        raise ValueError("public summary JSON SHA-256 must be 64 lowercase hex characters")
    lines = [
        "# Archivist pre-calibration evaluation result",
        "",
        "## Identity",
        "",
        f"- Evaluation: `{public.evaluation_id}`",
        f"- Candidate: `{public.candidate_id}`",
        f"- Candidate commit: `{public.candidate_commit}`",
        f"- RAG policy: `{public.rag_policy}`",
        f"- Cohort manifest SHA-256: `{public.cohort_manifest_sha256}`",
        f"- Public summary JSON SHA-256: `{public_summary_json_sha256}`",
        f"- Private artifact SHA-256: `{public.private_artifact_sha256}`",
        f"- Generation artifact SHA-256: `{public.generation_artifact_sha256}`",
        f"- Decomposition artifact SHA-256: `{public.decomposition_artifact_sha256}`",
        *(
            [f"- Migration artifact SHA-256: `{public.migration_artifact_sha256}`"]
            if public.migration_artifact_sha256 is not None
            else []
        ),
        f"- Gold set SHA-256: `{public.gold_set_sha256}`",
        f"- Corpus manifest SHA-256: `{public.corpus_manifest_sha256}`",
        f"- Chunks SHA-256: `{public.chunks_sha256}`",
        f"- Question set SHA-256: `{public.question_set_sha256}`",
        f"- Model catalog SHA-256: `{public.model_catalog_sha256}`",
        f"- Runner SHA-256: `{public.runner_sha256}`",
        "",
        "## Models",
        "",
        f"- Planner: `{public.planner_model_id}`",
        f"- Generator: `{public.generator_model_id}`",
        f"- Decomposer: `{public.decomposer_model_id}`",
        f"- Embedding: `{public.embedding_model_id}`",
        "",
        "## Cohort totals",
        "",
        f"- Run status: `{public.run_status.value}`",
        f"- Items: {public.item_count}",
        f"- Completed answers: {public.completed_answer_count}",
        f"- Technical errors: {public.technical_error_count}",
        f"- Trace-recovered items: {public.recovered_item_count}",
        f"- Canonical decomposition attempts: {public.decomposition_attempt_count}",
        f"- Usable decompositions: {public.usable_decomposition_count}",
        (f"- Decomposition technical failures: {public.decomposition_technical_failure_count}"),
        f"- Sources: {public.source_count}",
        f"- Claims: {public.claim_count}",
        f"- Citation references: {public.citation_count}",
        "",
        "## Aggregate metrics",
        "",
        "| Metric ID | Result |",
        "|---|---:|",
    ]
    lines.extend(
        f"| `{metric.metric_id.value}` | {_precalibration_markdown_ratio(metric)} |"
        for metric in public.metrics
    )
    lines.extend(["", "## Strata", ""])
    for stratum in public.strata:
        lines.extend(
            [
                f"### `{stratum.stratum.value}` ({stratum.item_count})",
                "",
                "| Metric ID | Result |",
                "|---|---:|",
            ]
        )
        lines.extend(
            f"| `{metric.metric_id.value}` | {_precalibration_markdown_ratio(metric)} |"
            for metric in stratum.metrics
        )
        lines.append("")
    lines.extend(
        [
            "## Cost and latency",
            "",
            f"- Estimated API cost (USD): {public.cost.estimated_cost_usd}",
            f"- Priced events: {public.cost.priced_event_count}",
            f"- Unpriced events: {public.cost.unpriced_event_count}",
            f"- Latency scope: `{public.latency_scope}`",
            f"- Latency denominator: {public.generation_latency_denominator}",
            f"- Exact latency observations: {public.generation_latency_observed_count}",
            f"- Total seconds: {public.latency.total_seconds:.3f}",
            f"- Mean seconds: {public.latency.mean_seconds:.3f}",
            f"- P50 seconds: {public.latency.p50_seconds:.3f}",
            f"- P95 seconds: {public.latency.p95_seconds:.3f}",
            f"- Maximum seconds: {public.latency.maximum_seconds:.3f}",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- `{limitation.value}`" for limitation in public.limitation_ids)
    return "\n".join(lines) + "\n"


__all__ = [
    "build_public_precalibration_summary",
    "build_public_evaluation_summary",
    "render_public_precalibration_markdown",
    "render_public_evaluation_markdown",
]
