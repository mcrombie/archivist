"""Offline-only semantic-evaluation artifacts and agreement projection.

This module performs no provider calls.  It seals the outputs of the two
semantic-judge lanes after those calls have completed:

* claim evidence sees locked answer claims and private source passages, never
  gold annotations;
* item rubric sees locked answer claims and a sanitized gold rubric, never
  private source passages.

The aggregate joins only the sealed outputs.  Source text and gold prose are
therefore absent from the result schemas, while exact input hashes remain
available for audit and replay validation.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

from answer_evaluation import (
    CalibrationItemLabel,
    CalibrationLabelFile,
    DecomposedClaim,
    DecomposedPilotItem,
    DecompositionOutcomeStatus,
    InstrumentLock,
    PRIVATE_DECOMPOSITION_FAILURE_CHECKPOINT_SCHEMA,
    PrivateDecompositionCheckpoint,
    PrivateDecompositionFailureCheckpoint,
    PrivateDecompositionOutcome,
    PrivateGeneratedItem,
    PrivateOrderedSource,
    PrivateProviderMetadata,
    PrivateUsageEvent,
    ScoringDimension,
    ScoringMode,
    canonical_json_bytes,
    canonical_json_sha256,
    sha256_text,
)
from evaluation_judge import ClaimEvidenceVerdict, ItemRubricInput, ItemRubricVerdict


CLAIM_EVIDENCE_RESULT_SCHEMA = "archivist.answer_evaluation.claim_evidence_result/1"
ITEM_RUBRIC_RESULT_SCHEMA = "archivist.answer_evaluation.item_rubric_result/1"
CALIBRATION_SEMANTIC_ITEM_SCHEMA = "archivist.answer_evaluation.calibration_semantic_item/1"
CALIBRATION_SEMANTIC_AGGREGATE_SCHEMA = (
    "archivist.answer_evaluation.calibration_semantic_aggregate/1"
)
AGREEMENT_PROJECTION_SCHEMA = "archivist.answer_evaluation.agreement_projection/1"
BASELINE_SEMANTIC_ITEM_SCHEMA = "archivist.answer_evaluation.baseline_semantic_item/1"
BASELINE_SEMANTIC_AGGREGATE_SCHEMA = "archivist.answer_evaluation.baseline_semantic_aggregate/1"
PRIVATE_FULL_RUN_ARTIFACT_SCHEMA = "archivist.answer_evaluation.private_full_run/1"
PRECALIBRATION_PRIVATE_ARTIFACT_SCHEMA = (
    "archivist.answer_evaluation.precalibration_private_artifact/3"
)
DECOMPOSITION_STABILITY_SCHEMA = "archivist.answer_evaluation.decomposition_stability/1"
MANUAL_SCORING_AGGREGATE_SCHEMA = "archivist.answer_evaluation.manual_scoring_aggregate/1"

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$"

Sha256 = Annotated[str, StringConstraints(pattern=_SHA256_PATTERN)]
Identifier = Annotated[str, StringConstraints(pattern=_IDENTIFIER_PATTERN)]
NonemptyString = Annotated[str, StringConstraints(min_length=1)]
SourceNumber = Annotated[int, Field(strict=True, ge=1)]
NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]
NonnegativeFloat = Annotated[
    float,
    Field(strict=True, ge=0.0, allow_inf_nan=False),
]
UnitInterval = Annotated[
    float,
    Field(strict=True, ge=0.0, le=1.0, allow_inf_nan=False),
]


class _ClosedModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


def _json_object(value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    normalized = json.loads(canonical_json_bytes(dict(value)))
    if not isinstance(normalized, dict):  # pragma: no cover - defensive
        raise ValueError("settings must be a JSON object")
    return normalized


def _require_unique(values: Sequence[object], *, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _require_dense_sources(values: Sequence[int], *, label: str) -> None:
    if list(values) != list(range(1, len(values) + 1)):
        raise ValueError(f"{label} must be exactly ordered 1..N")


def _validate_decomposition(
    generated_item: PrivateGeneratedItem,
    decomposition: DecomposedPilotItem,
) -> None:
    if decomposition.item_id != generated_item.item_id:
        raise ValueError("decomposition belongs to another generated item")
    if decomposition.answer_sha256 != generated_item.answer_sha256:
        raise ValueError("decomposition is bound to another answer")
    valid_sources = {source.source_number for source in generated_item.sources}
    for claim in decomposition.claims:
        if claim.char_end > len(generated_item.answer):
            raise ValueError(f"{claim.claim_id}: claim span exceeds answer length")
        if generated_item.answer[claim.char_start : claim.char_end] != claim.text:
            raise ValueError(f"{claim.claim_id}: claim text does not match answer span")
        if not set(claim.cited_source_numbers) <= valid_sources:
            raise ValueError(f"{claim.claim_id}: claim cites a source outside the source union")


class EvidenceSourceBinding(_ClosedModel):
    """Text-free identity for one source in the claim-evidence union."""

    source_number: SourceNumber
    chunk_id: NonemptyString
    text_sha256: Sha256
    source_sha256: Sha256
    binding_sha256: Sha256

    @model_validator(mode="after")
    def hash_is_exact(self) -> "EvidenceSourceBinding":
        payload = self.model_dump(mode="json", exclude={"binding_sha256"})
        if self.binding_sha256 != canonical_json_sha256(payload):
            raise ValueError("source binding_sha256 does not bind the source identity")
        return self


def _source_binding(source: PrivateOrderedSource) -> EvidenceSourceBinding:
    raw: dict[str, object] = {
        "source_number": source.source_number,
        "chunk_id": source.chunk_id,
        "text_sha256": source.text_sha256,
        "source_sha256": source.source_sha256,
    }
    raw["binding_sha256"] = canonical_json_sha256(raw)
    return EvidenceSourceBinding.model_validate(raw)


class LockedClaimBinding(_ClosedModel):
    """Text-free identity for one exact canonical answer claim."""

    claim_id: Identifier
    claim_text_sha256: Sha256
    claim_sha256: Sha256
    char_start: NonnegativeInt
    char_end: Annotated[int, Field(strict=True, ge=1)]
    cited_source_numbers: tuple[SourceNumber, ...]
    binding_sha256: Sha256

    @model_validator(mode="after")
    def span_sources_and_hash_are_exact(self) -> "LockedClaimBinding":
        if self.char_end <= self.char_start:
            raise ValueError("locked claim char_end must exceed char_start")
        _require_unique(self.cited_source_numbers, label="locked cited source numbers")
        payload = self.model_dump(mode="json", exclude={"binding_sha256"})
        if self.binding_sha256 != canonical_json_sha256(payload):
            raise ValueError("claim binding_sha256 does not bind the locked claim")
        return self


def _claim_binding(claim: DecomposedClaim) -> LockedClaimBinding:
    raw: dict[str, object] = {
        "claim_id": claim.claim_id,
        "claim_text_sha256": sha256_text(claim.text),
        "claim_sha256": claim.claim_sha256,
        "char_start": claim.char_start,
        "char_end": claim.char_end,
        "cited_source_numbers": list(claim.cited_source_numbers),
    }
    raw["binding_sha256"] = canonical_json_sha256(raw)
    return LockedClaimBinding.model_validate(raw)


class SanitizedGoldClaimBinding(_ClosedModel):
    claim_id: Identifier
    claim_text_sha256: Sha256
    essential: bool = Field(strict=True)
    binding_sha256: Sha256

    @model_validator(mode="after")
    def hash_is_exact(self) -> "SanitizedGoldClaimBinding":
        payload = self.model_dump(mode="json", exclude={"binding_sha256"})
        if self.binding_sha256 != canonical_json_sha256(payload):
            raise ValueError("gold claim binding_sha256 does not bind the sanitized claim")
        return self


class SanitizedRubricBinding(_ClosedModel):
    """Hashed projection of the only gold data permitted in the rubric lane."""

    question_sha256: Sha256
    gold_claims: tuple[SanitizedGoldClaimBinding, ...]
    must_not_claim_sha256s: tuple[Sha256, ...]
    sanitized_rubric_sha256: Sha256
    calibration_rubric_sha256: Sha256
    binding_sha256: Sha256

    @model_validator(mode="after")
    def order_and_hash_are_exact(self) -> "SanitizedRubricBinding":
        _require_unique(
            [claim.claim_id for claim in self.gold_claims],
            label="sanitized gold claim IDs",
        )
        payload = self.model_dump(mode="json", exclude={"binding_sha256"})
        if self.binding_sha256 != canonical_json_sha256(payload):
            raise ValueError("rubric binding_sha256 does not bind the sanitized rubric")
        return self


def build_sanitized_rubric_binding(
    *,
    item_id: str,
    rubric: ItemRubricInput,
) -> SanitizedRubricBinding:
    if not isinstance(rubric, ItemRubricInput):
        raise TypeError("rubric must be a sanitized ItemRubricInput")
    gold_claim_bindings: list[SanitizedGoldClaimBinding] = []
    for claim in rubric.claims:
        claim_raw: dict[str, object] = {
            "claim_id": claim.claim_id,
            "claim_text_sha256": sha256_text(claim.text),
            "essential": claim.essential,
        }
        claim_raw["binding_sha256"] = canonical_json_sha256(claim_raw)
        gold_claim_bindings.append(SanitizedGoldClaimBinding.model_validate(claim_raw))

    sanitized_payload = rubric.model_dump(mode="json")
    calibration_payload = {
        "item_id": item_id,
        "gold_claims": [
            {"claim_id": claim.claim_id, "text": claim.text} for claim in rubric.claims
        ],
        "must_not_claims": list(rubric.must_not_claim),
    }
    raw: dict[str, object] = {
        "question_sha256": sha256_text(rubric.question),
        "gold_claims": [claim.model_dump(mode="json") for claim in gold_claim_bindings],
        "must_not_claim_sha256s": [sha256_text(text) for text in rubric.must_not_claim],
        "sanitized_rubric_sha256": canonical_json_sha256(sanitized_payload),
        "calibration_rubric_sha256": canonical_json_sha256(calibration_payload),
    }
    raw["binding_sha256"] = canonical_json_sha256(raw)
    return SanitizedRubricBinding.model_validate(raw)


def _validate_provider_usage(
    *,
    provider: PrivateProviderMetadata,
    usage_event: PrivateUsageEvent,
    operation: str,
    judge_model: str,
) -> None:
    if usage_event.sequence != 1:
        raise ValueError("semantic judge usage-event sequence must be exactly 1")
    if usage_event.operation != operation:
        raise ValueError(f"semantic judge usage operation must be {operation}")
    if usage_event.response_id != provider.response_id:
        raise ValueError("semantic judge provider and usage response IDs differ")
    if usage_event.requested_model != judge_model:
        raise ValueError("semantic judge requested model differs from locked judge model")
    if usage_event.actual_model != provider.model:
        raise ValueError("semantic judge provider and usage actual models differ")
    if provider.model != judge_model:
        raise ValueError("semantic judge provider model differs from locked judge model")


class ClaimEvidenceResult(_ClosedModel):
    """One sealed claim-evidence call with no gold annotation fields."""

    schema_version: Literal[CLAIM_EVIDENCE_RESULT_SCHEMA] = Field(
        CLAIM_EVIDENCE_RESULT_SCHEMA,
        alias="schema",
    )
    cohort_manifest_sha256: Sha256
    item_id: Identifier
    answer_sha256: Sha256
    decomposition_sha256: Sha256
    claim: LockedClaimBinding
    call_ordinal: Annotated[int, Field(strict=True, ge=1, le=2)]
    source_union: tuple[EvidenceSourceBinding, ...] = Field(min_length=1)
    source_union_sha256: Sha256
    prompt_version: Identifier
    prompt_sha256: Sha256
    judge_model: NonemptyString
    judge_settings: dict[str, JsonValue]
    provider: PrivateProviderMetadata
    usage_event: PrivateUsageEvent
    verdict: ClaimEvidenceVerdict
    result_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def identities_and_hash_are_exact(self) -> "ClaimEvidenceResult":
        _require_dense_sources(
            [source.source_number for source in self.source_union],
            label="evidence source union",
        )
        _require_unique(
            [source.chunk_id for source in self.source_union],
            label="evidence source chunk IDs",
        )
        expected_union_hash = canonical_json_sha256(
            [source.model_dump(mode="json") for source in self.source_union]
        )
        if self.source_union_sha256 != expected_union_hash:
            raise ValueError("source_union_sha256 does not bind the ordered source union")
        if not set(self.claim.cited_source_numbers) <= {
            source.source_number for source in self.source_union
        }:
            raise ValueError("locked claim cites a source outside the evidence union")
        if self.verdict.claim_id != self.claim.claim_id:
            raise ValueError("claim evidence verdict changed the locked claim ID")
        if [entry.source_number for entry in self.verdict.source_verdicts] != sorted(
            self.claim.cited_source_numbers
        ):
            raise ValueError("claim evidence verdict changed cited source order or cardinality")
        _validate_provider_usage(
            provider=self.provider,
            usage_event=self.usage_event,
            operation="eval_claim_evidence",
            judge_model=self.judge_model,
        )
        payload = self.model_dump(mode="json", exclude={"result_sha256"})
        if self.result_sha256 != canonical_json_sha256(payload):
            raise ValueError("result_sha256 does not bind the claim evidence result")
        return self


def build_claim_evidence_result(
    *,
    cohort_manifest_sha256: str,
    generated_item: PrivateGeneratedItem,
    decomposition: DecomposedPilotItem,
    claim: DecomposedClaim,
    call_ordinal: int,
    prompt_version: str,
    prompt_sha256: str,
    judge_model: str,
    judge_settings: Mapping[str, JsonValue],
    provider: PrivateProviderMetadata | Mapping[str, object],
    usage_event: PrivateUsageEvent | Mapping[str, object],
    verdict: ClaimEvidenceVerdict | Mapping[str, object],
) -> ClaimEvidenceResult:
    _validate_decomposition(generated_item, decomposition)
    matching_claims = [
        candidate for candidate in decomposition.claims if candidate.claim_id == claim.claim_id
    ]
    if len(matching_claims) != 1 or matching_claims[0] != claim:
        raise ValueError("claim is not the exact locked claim in this decomposition")
    normalized_provider = (
        provider
        if isinstance(provider, PrivateProviderMetadata)
        else PrivateProviderMetadata.model_validate(provider)
    )
    normalized_usage = (
        usage_event
        if isinstance(usage_event, PrivateUsageEvent)
        else PrivateUsageEvent.model_validate(usage_event)
    )
    normalized_verdict = (
        verdict
        if isinstance(verdict, ClaimEvidenceVerdict)
        else ClaimEvidenceVerdict.model_validate(verdict)
    )
    sources = tuple(_source_binding(source) for source in generated_item.sources)
    raw: dict[str, object] = {
        "schema": CLAIM_EVIDENCE_RESULT_SCHEMA,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "item_id": generated_item.item_id,
        "answer_sha256": generated_item.answer_sha256,
        "decomposition_sha256": decomposition.decomposition_sha256,
        "claim": _claim_binding(claim).model_dump(mode="json"),
        "call_ordinal": call_ordinal,
        "source_union": [source.model_dump(mode="json") for source in sources],
        "source_union_sha256": canonical_json_sha256(
            [source.model_dump(mode="json") for source in sources]
        ),
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "judge_model": judge_model,
        "judge_settings": _json_object(judge_settings),
        "provider": normalized_provider.model_dump(mode="json"),
        "usage_event": normalized_usage.model_dump(mode="json"),
        "verdict": normalized_verdict.model_dump(mode="json"),
    }
    raw["result_sha256"] = canonical_json_sha256(raw)
    return ClaimEvidenceResult.model_validate(raw)


def validate_claim_evidence_result(
    value: ClaimEvidenceResult | Mapping[str, object],
    *,
    cohort_manifest_sha256: str,
    generated_item: PrivateGeneratedItem,
    decomposition: DecomposedPilotItem,
    claim: DecomposedClaim,
    call_ordinal: int,
    prompt_version: str,
    prompt_sha256: str,
    judge_model: str,
    judge_settings: Mapping[str, JsonValue],
) -> ClaimEvidenceResult:
    result = (
        value
        if isinstance(value, ClaimEvidenceResult)
        else ClaimEvidenceResult.model_validate(value)
    )
    _validate_decomposition(generated_item, decomposition)
    expected = {
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "item_id": generated_item.item_id,
        "answer_sha256": generated_item.answer_sha256,
        "decomposition_sha256": decomposition.decomposition_sha256,
        "claim": _claim_binding(claim),
        "call_ordinal": call_ordinal,
        "source_union": tuple(_source_binding(source) for source in generated_item.sources),
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "judge_model": judge_model,
        "judge_settings": _json_object(judge_settings),
    }
    for field, expected_value in expected.items():
        if getattr(result, field) != expected_value:
            raise ValueError(f"claim evidence result {field} changed")
    return result


class ItemRubricResult(_ClosedModel):
    """One sealed item-rubric call with no source fields or source hashes."""

    schema_version: Literal[ITEM_RUBRIC_RESULT_SCHEMA] = Field(
        ITEM_RUBRIC_RESULT_SCHEMA,
        alias="schema",
    )
    cohort_manifest_sha256: Sha256
    item_id: Identifier
    answer_sha256: Sha256
    decomposition_sha256: Sha256
    locked_claims: tuple[LockedClaimBinding, ...]
    locked_claims_sha256: Sha256
    rubric: SanitizedRubricBinding
    prompt_version: Identifier
    prompt_sha256: Sha256
    judge_model: NonemptyString
    judge_settings: dict[str, JsonValue]
    provider: PrivateProviderMetadata
    usage_event: PrivateUsageEvent
    verdict: ItemRubricVerdict
    result_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def identities_and_hash_are_exact(self) -> "ItemRubricResult":
        claim_ids = [claim.claim_id for claim in self.locked_claims]
        _require_unique(claim_ids, label="item-rubric locked claim IDs")
        expected_claim_hash = canonical_json_sha256(
            [claim.model_dump(mode="json") for claim in self.locked_claims]
        )
        if self.locked_claims_sha256 != expected_claim_hash:
            raise ValueError("locked_claims_sha256 does not bind the exact claims")
        if [entry.answer_claim_id for entry in self.verdict.answer_claim_matches] != claim_ids:
            raise ValueError("item rubric verdict changed locked answer claim order")
        gold_ids = [claim.claim_id for claim in self.rubric.gold_claims]
        if [entry.claim_id for entry in self.verdict.gold_claims] != gold_ids:
            raise ValueError("item rubric verdict changed sanitized gold claim order")
        valid_gold_ids = set(gold_ids)
        if any(
            not set(entry.gold_claim_ids) <= valid_gold_ids
            for entry in self.verdict.answer_claim_matches
        ):
            raise ValueError("item rubric verdict references a gold claim outside the rubric")
        if [entry.index for entry in self.verdict.must_not_claim] != list(
            range(len(self.rubric.must_not_claim_sha256s))
        ):
            raise ValueError("item rubric verdict changed must-not-claim order")
        _validate_provider_usage(
            provider=self.provider,
            usage_event=self.usage_event,
            operation="eval_item_rubric",
            judge_model=self.judge_model,
        )
        payload = self.model_dump(mode="json", exclude={"result_sha256"})
        if self.result_sha256 != canonical_json_sha256(payload):
            raise ValueError("result_sha256 does not bind the item rubric result")
        return self


def build_item_rubric_result(
    *,
    cohort_manifest_sha256: str,
    generated_item: PrivateGeneratedItem,
    decomposition: DecomposedPilotItem,
    rubric: ItemRubricInput,
    prompt_version: str,
    prompt_sha256: str,
    judge_model: str,
    judge_settings: Mapping[str, JsonValue],
    provider: PrivateProviderMetadata | Mapping[str, object],
    usage_event: PrivateUsageEvent | Mapping[str, object],
    verdict: ItemRubricVerdict | Mapping[str, object],
) -> ItemRubricResult:
    _validate_decomposition(generated_item, decomposition)
    if not isinstance(rubric, ItemRubricInput):
        raise TypeError("rubric must be a sanitized ItemRubricInput")
    if rubric.question != generated_item.question:
        raise ValueError("sanitized rubric question differs from the locked item question")
    normalized_provider = (
        provider
        if isinstance(provider, PrivateProviderMetadata)
        else PrivateProviderMetadata.model_validate(provider)
    )
    normalized_usage = (
        usage_event
        if isinstance(usage_event, PrivateUsageEvent)
        else PrivateUsageEvent.model_validate(usage_event)
    )
    normalized_verdict = (
        verdict
        if isinstance(verdict, ItemRubricVerdict)
        else ItemRubricVerdict.model_validate(verdict)
    )
    claims = tuple(_claim_binding(claim) for claim in decomposition.claims)
    raw: dict[str, object] = {
        "schema": ITEM_RUBRIC_RESULT_SCHEMA,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "item_id": generated_item.item_id,
        "answer_sha256": generated_item.answer_sha256,
        "decomposition_sha256": decomposition.decomposition_sha256,
        "locked_claims": [claim.model_dump(mode="json") for claim in claims],
        "locked_claims_sha256": canonical_json_sha256(
            [claim.model_dump(mode="json") for claim in claims]
        ),
        "rubric": build_sanitized_rubric_binding(
            item_id=generated_item.item_id,
            rubric=rubric,
        ).model_dump(mode="json"),
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "judge_model": judge_model,
        "judge_settings": _json_object(judge_settings),
        "provider": normalized_provider.model_dump(mode="json"),
        "usage_event": normalized_usage.model_dump(mode="json"),
        "verdict": normalized_verdict.model_dump(mode="json"),
    }
    raw["result_sha256"] = canonical_json_sha256(raw)
    return ItemRubricResult.model_validate(raw)


def validate_item_rubric_result(
    value: ItemRubricResult | Mapping[str, object],
    *,
    cohort_manifest_sha256: str,
    generated_item: PrivateGeneratedItem,
    decomposition: DecomposedPilotItem,
    rubric: ItemRubricInput,
    prompt_version: str,
    prompt_sha256: str,
    judge_model: str,
    judge_settings: Mapping[str, JsonValue],
) -> ItemRubricResult:
    result = (
        value if isinstance(value, ItemRubricResult) else ItemRubricResult.model_validate(value)
    )
    _validate_decomposition(generated_item, decomposition)
    if rubric.question != generated_item.question:
        raise ValueError("sanitized rubric question differs from the locked item question")
    expected = {
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "item_id": generated_item.item_id,
        "answer_sha256": generated_item.answer_sha256,
        "decomposition_sha256": decomposition.decomposition_sha256,
        "locked_claims": tuple(_claim_binding(claim) for claim in decomposition.claims),
        "rubric": build_sanitized_rubric_binding(
            item_id=generated_item.item_id,
            rubric=rubric,
        ),
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "judge_model": judge_model,
        "judge_settings": _json_object(judge_settings),
    }
    for field, expected_value in expected.items():
        if getattr(result, field) != expected_value:
            raise ValueError(f"item rubric result {field} changed")
    return result


def _evidence_input_identity(result: ClaimEvidenceResult) -> dict[str, object]:
    return {
        "cohort_manifest_sha256": result.cohort_manifest_sha256,
        "item_id": result.item_id,
        "answer_sha256": result.answer_sha256,
        "decomposition_sha256": result.decomposition_sha256,
        "claim": result.claim,
        "source_union": result.source_union,
        "source_union_sha256": result.source_union_sha256,
        "prompt_version": result.prompt_version,
        "prompt_sha256": result.prompt_sha256,
        "judge_model": result.judge_model,
        "judge_settings": result.judge_settings,
    }


class CalibrationSemanticItem(_ClosedModel):
    schema_version: Literal[CALIBRATION_SEMANTIC_ITEM_SCHEMA] = Field(
        CALIBRATION_SEMANTIC_ITEM_SCHEMA,
        alias="schema",
    )
    item_id: Identifier
    answer_sha256: Sha256
    decomposition_sha256: Sha256
    first_call_claim_evidence: tuple[ClaimEvidenceResult, ...]
    item_rubric: ItemRubricResult
    repeat_first_claim_evidence: ClaimEvidenceResult | None
    item_result_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def calls_are_complete_and_hash_is_exact(self) -> "CalibrationSemanticItem":
        if (
            self.item_rubric.item_id != self.item_id
            or self.item_rubric.answer_sha256 != self.answer_sha256
            or self.item_rubric.decomposition_sha256 != self.decomposition_sha256
        ):
            raise ValueError("semantic item rubric binding differs from the item identity")
        expected_claims = list(self.item_rubric.locked_claims)
        actual_claims = [result.claim for result in self.first_call_claim_evidence]
        if actual_claims != expected_claims:
            raise ValueError("first-call evidence must cover every locked claim in order")
        for result in self.first_call_claim_evidence:
            if result.call_ordinal != 1:
                raise ValueError("first-call evidence must have call_ordinal 1")
            if (
                result.item_id != self.item_id
                or result.answer_sha256 != self.answer_sha256
                or result.decomposition_sha256 != self.decomposition_sha256
                or result.cohort_manifest_sha256 != self.item_rubric.cohort_manifest_sha256
            ):
                raise ValueError("first-call evidence belongs to another semantic item")
            if (
                result.judge_model != self.item_rubric.judge_model
                or result.judge_settings != self.item_rubric.judge_settings
            ):
                raise ValueError("semantic item judge model or settings differ between lanes")

        if expected_claims:
            repeat = self.repeat_first_claim_evidence
            if repeat is None:
                raise ValueError("the first locked claim requires one repeat evidence result")
            first = self.first_call_claim_evidence[0]
            if repeat.call_ordinal != 2:
                raise ValueError("repeat evidence must have call_ordinal 2")
            if _evidence_input_identity(repeat) != _evidence_input_identity(first):
                raise ValueError("repeat evidence changed the fixed first-claim input")
            if repeat.provider.response_id == first.provider.response_id:
                raise ValueError("repeat evidence must be a distinct provider response")
        elif self.repeat_first_claim_evidence is not None:
            raise ValueError("an item without claims cannot contain repeat evidence")

        payload = self.model_dump(mode="json", exclude={"item_result_sha256"})
        if self.item_result_sha256 != canonical_json_sha256(payload):
            raise ValueError("item_result_sha256 does not bind the semantic item")
        return self


def build_calibration_semantic_item(
    *,
    first_call_claim_evidence: Sequence[ClaimEvidenceResult | Mapping[str, object]],
    item_rubric: ItemRubricResult | Mapping[str, object],
    repeat_first_claim_evidence: ClaimEvidenceResult | Mapping[str, object] | None,
) -> CalibrationSemanticItem:
    normalized_rubric = (
        item_rubric
        if isinstance(item_rubric, ItemRubricResult)
        else ItemRubricResult.model_validate(item_rubric)
    )
    normalized_first = tuple(
        value
        if isinstance(value, ClaimEvidenceResult)
        else ClaimEvidenceResult.model_validate(value)
        for value in first_call_claim_evidence
    )
    normalized_repeat = (
        None
        if repeat_first_claim_evidence is None
        else repeat_first_claim_evidence
        if isinstance(repeat_first_claim_evidence, ClaimEvidenceResult)
        else ClaimEvidenceResult.model_validate(repeat_first_claim_evidence)
    )
    raw: dict[str, object] = {
        "schema": CALIBRATION_SEMANTIC_ITEM_SCHEMA,
        "item_id": normalized_rubric.item_id,
        "answer_sha256": normalized_rubric.answer_sha256,
        "decomposition_sha256": normalized_rubric.decomposition_sha256,
        "first_call_claim_evidence": [value.model_dump(mode="json") for value in normalized_first],
        "item_rubric": normalized_rubric.model_dump(mode="json"),
        "repeat_first_claim_evidence": (
            None if normalized_repeat is None else normalized_repeat.model_dump(mode="json")
        ),
    }
    raw["item_result_sha256"] = canonical_json_sha256(raw)
    return CalibrationSemanticItem.model_validate(raw)


class CalibrationSemanticAggregate(_ClosedModel):
    schema_version: Literal[CALIBRATION_SEMANTIC_AGGREGATE_SCHEMA] = Field(
        CALIBRATION_SEMANTIC_AGGREGATE_SCHEMA,
        alias="schema",
    )
    cohort_manifest_sha256: Sha256
    pilot_artifact_sha256: Sha256
    decomposition_artifact_sha256: Sha256
    calibration_item_ids: tuple[Identifier, ...] = Field(min_length=10, max_length=10)
    items: tuple[CalibrationSemanticItem, ...] = Field(min_length=10, max_length=10)
    aggregate_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def cohort_is_complete_and_hash_is_exact(self) -> "CalibrationSemanticAggregate":
        _require_unique(self.calibration_item_ids, label="calibration semantic item IDs")
        if [item.item_id for item in self.items] != list(self.calibration_item_ids):
            raise ValueError("semantic aggregate must contain every calibration item in order")
        for item in self.items:
            if item.item_rubric.cohort_manifest_sha256 != self.cohort_manifest_sha256:
                raise ValueError("semantic aggregate contains an item from another cohort")
        payload = self.model_dump(mode="json", exclude={"aggregate_sha256"})
        if self.aggregate_sha256 != canonical_json_sha256(payload):
            raise ValueError("aggregate_sha256 does not bind the semantic aggregate")
        return self


def build_calibration_semantic_aggregate(
    *,
    cohort_manifest_sha256: str,
    pilot_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    calibration_item_ids: Sequence[str],
    items: Sequence[CalibrationSemanticItem | Mapping[str, object]],
) -> CalibrationSemanticAggregate:
    normalized = tuple(
        value
        if isinstance(value, CalibrationSemanticItem)
        else CalibrationSemanticItem.model_validate(value)
        for value in items
    )
    raw: dict[str, object] = {
        "schema": CALIBRATION_SEMANTIC_AGGREGATE_SCHEMA,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "pilot_artifact_sha256": pilot_artifact_sha256,
        "decomposition_artifact_sha256": decomposition_artifact_sha256,
        "calibration_item_ids": list(calibration_item_ids),
        "items": [item.model_dump(mode="json") for item in normalized],
    }
    raw["aggregate_sha256"] = canonical_json_sha256(raw)
    return CalibrationSemanticAggregate.model_validate(raw)


def validate_calibration_semantic_aggregate(
    value: CalibrationSemanticAggregate | Mapping[str, object],
    *,
    cohort_manifest_sha256: str,
    pilot_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    calibration_item_ids: Sequence[str],
) -> CalibrationSemanticAggregate:
    aggregate = (
        value
        if isinstance(value, CalibrationSemanticAggregate)
        else CalibrationSemanticAggregate.model_validate(value)
    )
    expected = {
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "pilot_artifact_sha256": pilot_artifact_sha256,
        "decomposition_artifact_sha256": decomposition_artifact_sha256,
        "calibration_item_ids": tuple(calibration_item_ids),
    }
    for field, expected_value in expected.items():
        if getattr(aggregate, field) != expected_value:
            raise ValueError(f"semantic aggregate {field} changed")
    return aggregate


_EVIDENCE_DIMENSIONS = (
    ScoringDimension.FAITHFULNESS,
    ScoringDimension.CITED_SOURCE_SUPPORT,
)
_RUBRIC_DIMENSIONS = (
    ScoringDimension.CLAIM_MAPPING,
    ScoringDimension.GOLD_STATUS,
    ScoringDimension.MUST_NOT_TRIPWIRES,
    ScoringDimension.RESPONSE_BEHAVIOR,
)


def _instrument_lane_activity(instrument_lock: InstrumentLock) -> tuple[bool, bool]:
    modes = {entry.dimension: entry.scoring_mode for entry in instrument_lock.dimensions}
    evidence_active = any(
        modes[dimension] is ScoringMode.JUDGE for dimension in _EVIDENCE_DIMENSIONS
    )
    rubric_active = any(modes[dimension] is ScoringMode.JUDGE for dimension in _RUBRIC_DIMENSIONS)
    return evidence_active, rubric_active


class BaselineSemanticItem(_ClosedModel):
    """The sealed first-call semantic results for one baseline item.

    Unlike :class:`CalibrationSemanticItem`, a baseline item deliberately has
    no repeat lane.  Judge-lane presence is fixed by the scoring instrument:
    an active evidence lane contains exactly one ordinal-one result per locked
    claim, while an active rubric lane contains exactly one rubric result.
    Manual-only lanes may be absent so the baseline does not make calls whose
    outputs cannot be scored automatically.
    """

    schema_version: Literal[BASELINE_SEMANTIC_ITEM_SCHEMA] = Field(
        BASELINE_SEMANTIC_ITEM_SCHEMA,
        alias="schema",
    )
    item_id: Identifier
    answer_sha256: Sha256
    decomposition_sha256: Sha256
    cohort_manifest_sha256: Sha256
    instrument_sha256: Sha256
    evidence_lane_active: bool = Field(strict=True)
    rubric_lane_active: bool = Field(strict=True)
    locked_claims: tuple[LockedClaimBinding, ...]
    locked_claims_sha256: Sha256
    first_call_claim_evidence: tuple[ClaimEvidenceResult, ...]
    item_rubric: ItemRubricResult | None
    item_result_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def calls_are_complete_and_hash_is_exact(self) -> "BaselineSemanticItem":
        rubric = self.item_rubric
        claim_ids = [claim.claim_id for claim in self.locked_claims]
        _require_unique(claim_ids, label="baseline locked claim IDs")
        expected_claim_hash = canonical_json_sha256(
            [claim.model_dump(mode="json") for claim in self.locked_claims]
        )
        if self.locked_claims_sha256 != expected_claim_hash:
            raise ValueError("locked_claims_sha256 does not bind baseline claims")
        if self.rubric_lane_active and rubric is None:
            raise ValueError("active baseline rubric lane requires exactly one result")
        if rubric is not None:
            if (
                rubric.item_id != self.item_id
                or rubric.answer_sha256 != self.answer_sha256
                or rubric.decomposition_sha256 != self.decomposition_sha256
                or rubric.cohort_manifest_sha256 != self.cohort_manifest_sha256
            ):
                raise ValueError("baseline item rubric binding differs from the item identity")
            if list(rubric.locked_claims) != list(self.locked_claims):
                raise ValueError("baseline item rubric changed the locked claims")
        if self.evidence_lane_active and len(self.first_call_claim_evidence) != len(
            self.locked_claims
        ):
            raise ValueError("active baseline evidence lane must cover every locked claim in order")
        expected_claims = list(self.locked_claims)
        actual_claims = [result.claim for result in self.first_call_claim_evidence]
        if actual_claims and actual_claims != expected_claims:
            raise ValueError("baseline first-call evidence must cover every locked claim in order")
        for result in self.first_call_claim_evidence:
            if result.call_ordinal != 1:
                raise ValueError("baseline evidence must have call_ordinal 1")
            if (
                result.item_id != self.item_id
                or result.answer_sha256 != self.answer_sha256
                or result.decomposition_sha256 != self.decomposition_sha256
                or result.cohort_manifest_sha256 != self.cohort_manifest_sha256
            ):
                raise ValueError("baseline evidence belongs to another semantic item")
            if rubric is not None and (
                result.judge_model != rubric.judge_model
                or result.judge_settings != rubric.judge_settings
            ):
                raise ValueError("baseline judge model or settings differ between semantic lanes")
        payload = self.model_dump(mode="json", exclude={"item_result_sha256"})
        if self.item_result_sha256 != canonical_json_sha256(payload):
            raise ValueError("item_result_sha256 does not bind the baseline semantic item")
        return self


def build_baseline_semantic_item(
    *,
    decomposition: DecomposedPilotItem,
    instrument_lock: InstrumentLock,
    first_call_claim_evidence: Sequence[ClaimEvidenceResult | Mapping[str, object]],
    item_rubric: ItemRubricResult | Mapping[str, object] | None,
) -> BaselineSemanticItem:
    """Seal one baseline item while preserving existing result objects exactly."""

    normalized_rubric = (
        None
        if item_rubric is None
        else item_rubric
        if isinstance(item_rubric, ItemRubricResult)
        else ItemRubricResult.model_validate(item_rubric)
    )
    normalized_evidence = tuple(
        value
        if isinstance(value, ClaimEvidenceResult)
        else ClaimEvidenceResult.model_validate(value)
        for value in first_call_claim_evidence
    )
    locked_claims = tuple(_claim_binding(claim) for claim in decomposition.claims)
    evidence_active, rubric_active = _instrument_lane_activity(instrument_lock)
    raw: dict[str, object] = {
        "schema": BASELINE_SEMANTIC_ITEM_SCHEMA,
        "item_id": decomposition.item_id,
        "answer_sha256": decomposition.answer_sha256,
        "decomposition_sha256": decomposition.decomposition_sha256,
        "cohort_manifest_sha256": instrument_lock.cohort_manifest_sha256,
        "instrument_sha256": instrument_lock.instrument_sha256,
        "evidence_lane_active": evidence_active,
        "rubric_lane_active": rubric_active,
        "locked_claims": [claim.model_dump(mode="json") for claim in locked_claims],
        "locked_claims_sha256": canonical_json_sha256(
            [claim.model_dump(mode="json") for claim in locked_claims]
        ),
        "first_call_claim_evidence": [
            result.model_dump(mode="json") for result in normalized_evidence
        ],
        "item_rubric": (
            None if normalized_rubric is None else normalized_rubric.model_dump(mode="json")
        ),
    }
    raw["item_result_sha256"] = canonical_json_sha256(raw)
    return BaselineSemanticItem.model_validate(raw)


def build_baseline_semantic_item_from_calibration(
    item: CalibrationSemanticItem | Mapping[str, object],
    *,
    decomposition: DecomposedPilotItem,
    instrument_lock: InstrumentLock,
) -> BaselineSemanticItem:
    """Project calibration first calls into the baseline without rerunning a judge."""

    normalized = (
        item
        if isinstance(item, CalibrationSemanticItem)
        else CalibrationSemanticItem.model_validate(item)
    )
    if (
        normalized.item_id != decomposition.item_id
        or normalized.answer_sha256 != decomposition.answer_sha256
        or normalized.decomposition_sha256 != decomposition.decomposition_sha256
    ):
        raise ValueError("calibration projection decomposition binding changed")
    return build_baseline_semantic_item(
        decomposition=decomposition,
        instrument_lock=instrument_lock,
        first_call_claim_evidence=normalized.first_call_claim_evidence,
        item_rubric=normalized.item_rubric,
    )


def validate_baseline_semantic_item(
    value: BaselineSemanticItem | Mapping[str, object],
    *,
    cohort_manifest_sha256: str,
    generated_item: PrivateGeneratedItem,
    decomposition: DecomposedPilotItem,
    rubric: ItemRubricInput,
    instrument_lock: InstrumentLock,
    evidence_prompt_version: str,
    evidence_prompt_sha256: str,
    rubric_prompt_version: str,
    rubric_prompt_sha256: str,
    judge_model: str,
    judge_settings: Mapping[str, JsonValue],
) -> BaselineSemanticItem:
    """Join a sealed item back to its private inputs and fixed judge config."""

    if instrument_lock.cohort_manifest_sha256 != cohort_manifest_sha256:
        raise ValueError("baseline instrument lock belongs to another cohort")
    if instrument_lock.judge_model != judge_model:
        raise ValueError("baseline judge model differs from the instrument lock")
    if instrument_lock.judge_settings != _json_object(judge_settings):
        raise ValueError("baseline judge settings differ from the instrument lock")
    if instrument_lock.evidence_prompt_sha256 != evidence_prompt_sha256:
        raise ValueError("baseline evidence prompt differs from the instrument lock")
    if instrument_lock.rubric_prompt_sha256 != rubric_prompt_sha256:
        raise ValueError("baseline rubric prompt differs from the instrument lock")
    item = (
        value
        if isinstance(value, BaselineSemanticItem)
        else BaselineSemanticItem.model_validate(value)
    )
    _validate_decomposition(generated_item, decomposition)
    if item.item_id != generated_item.item_id:
        raise ValueError("baseline semantic item_id changed")
    if item.answer_sha256 != generated_item.answer_sha256:
        raise ValueError("baseline semantic answer_sha256 changed")
    if item.decomposition_sha256 != decomposition.decomposition_sha256:
        raise ValueError("baseline semantic decomposition_sha256 changed")
    evidence_active, rubric_active = _instrument_lane_activity(instrument_lock)
    expected_identity = {
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "instrument_sha256": instrument_lock.instrument_sha256,
        "evidence_lane_active": evidence_active,
        "rubric_lane_active": rubric_active,
        "locked_claims": tuple(_claim_binding(claim) for claim in decomposition.claims),
    }
    for field, expected_value in expected_identity.items():
        if getattr(item, field) != expected_value:
            raise ValueError(f"baseline semantic {field} changed")
    if evidence_active and len(item.first_call_claim_evidence) != len(decomposition.claims):
        raise ValueError("active baseline evidence result count changed")
    if (
        not evidence_active
        and item.first_call_claim_evidence
        and len(item.first_call_claim_evidence) != len(decomposition.claims)
    ):
        raise ValueError("inactive baseline evidence lane is incomplete")
    if item.first_call_claim_evidence:
        for result, claim in zip(
            item.first_call_claim_evidence,
            decomposition.claims,
            strict=True,
        ):
            validate_claim_evidence_result(
                result,
                cohort_manifest_sha256=cohort_manifest_sha256,
                generated_item=generated_item,
                decomposition=decomposition,
                claim=claim,
                call_ordinal=1,
                prompt_version=evidence_prompt_version,
                prompt_sha256=evidence_prompt_sha256,
                judge_model=judge_model,
                judge_settings=judge_settings,
            )
    if rubric_active and item.item_rubric is None:
        raise ValueError("active baseline rubric result is absent")
    if item.item_rubric is not None:
        validate_item_rubric_result(
            item.item_rubric,
            cohort_manifest_sha256=cohort_manifest_sha256,
            generated_item=generated_item,
            decomposition=decomposition,
            rubric=rubric,
            prompt_version=rubric_prompt_version,
            prompt_sha256=rubric_prompt_sha256,
            judge_model=judge_model,
            judge_settings=judge_settings,
        )
    return item


class BaselineSemanticAggregate(_ClosedModel):
    """Exactly 37 ordered first-call semantic items for the held-out baseline."""

    schema_version: Literal[BASELINE_SEMANTIC_AGGREGATE_SCHEMA] = Field(
        BASELINE_SEMANTIC_AGGREGATE_SCHEMA,
        alias="schema",
    )
    cohort_manifest_sha256: Sha256
    generation_artifact_sha256: Sha256
    decomposition_artifact_sha256: Sha256
    instrument_sha256: Sha256
    evidence_lane_active: bool = Field(strict=True)
    rubric_lane_active: bool = Field(strict=True)
    item_ids: tuple[Identifier, ...] = Field(min_length=37, max_length=37)
    items: tuple[BaselineSemanticItem, ...] = Field(min_length=37, max_length=37)
    aggregate_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def cohort_is_complete_and_hash_is_exact(self) -> "BaselineSemanticAggregate":
        _require_unique(self.item_ids, label="baseline semantic item IDs")
        if [item.item_id for item in self.items] != list(self.item_ids):
            raise ValueError("baseline aggregate must contain all 37 items in exact order")
        for item in self.items:
            if item.cohort_manifest_sha256 != self.cohort_manifest_sha256:
                raise ValueError("baseline aggregate contains an item from another cohort")
            if item.instrument_sha256 != self.instrument_sha256:
                raise ValueError("baseline aggregate contains another instrument")
            if (
                item.evidence_lane_active != self.evidence_lane_active
                or item.rubric_lane_active != self.rubric_lane_active
            ):
                raise ValueError("baseline aggregate lane activity changed between items")
        payload = self.model_dump(mode="json", exclude={"aggregate_sha256"})
        if self.aggregate_sha256 != canonical_json_sha256(payload):
            raise ValueError("aggregate_sha256 does not bind the baseline aggregate")
        return self


def build_baseline_semantic_aggregate(
    *,
    cohort_manifest_sha256: str,
    generation_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    instrument_lock: InstrumentLock,
    item_ids: Sequence[str],
    items: Sequence[BaselineSemanticItem | Mapping[str, object]],
) -> BaselineSemanticAggregate:
    normalized = tuple(
        value
        if isinstance(value, BaselineSemanticItem)
        else BaselineSemanticItem.model_validate(value)
        for value in items
    )
    if instrument_lock.cohort_manifest_sha256 != cohort_manifest_sha256:
        raise ValueError("baseline instrument lock belongs to another cohort")
    evidence_active, rubric_active = _instrument_lane_activity(instrument_lock)
    raw: dict[str, object] = {
        "schema": BASELINE_SEMANTIC_AGGREGATE_SCHEMA,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "generation_artifact_sha256": generation_artifact_sha256,
        "decomposition_artifact_sha256": decomposition_artifact_sha256,
        "instrument_sha256": instrument_lock.instrument_sha256,
        "evidence_lane_active": evidence_active,
        "rubric_lane_active": rubric_active,
        "item_ids": list(item_ids),
        "items": [item.model_dump(mode="json") for item in normalized],
    }
    raw["aggregate_sha256"] = canonical_json_sha256(raw)
    return BaselineSemanticAggregate.model_validate(raw)


def validate_baseline_semantic_aggregate(
    value: BaselineSemanticAggregate | Mapping[str, object],
    *,
    cohort_manifest_sha256: str,
    generation_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    item_ids: Sequence[str],
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    rubrics: Sequence[ItemRubricInput],
    instrument_lock: InstrumentLock,
    evidence_prompt_version: str,
    evidence_prompt_sha256: str,
    rubric_prompt_version: str,
    rubric_prompt_sha256: str,
    judge_model: str,
    judge_settings: Mapping[str, JsonValue],
) -> BaselineSemanticAggregate:
    aggregate = (
        value
        if isinstance(value, BaselineSemanticAggregate)
        else BaselineSemanticAggregate.model_validate(value)
    )
    if instrument_lock.cohort_manifest_sha256 != cohort_manifest_sha256:
        raise ValueError("baseline instrument lock belongs to another cohort")
    evidence_active, rubric_active = _instrument_lane_activity(instrument_lock)
    expected = {
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "generation_artifact_sha256": generation_artifact_sha256,
        "decomposition_artifact_sha256": decomposition_artifact_sha256,
        "instrument_sha256": instrument_lock.instrument_sha256,
        "evidence_lane_active": evidence_active,
        "rubric_lane_active": rubric_active,
        "item_ids": tuple(item_ids),
    }
    for field, expected_value in expected.items():
        if getattr(aggregate, field) != expected_value:
            raise ValueError(f"baseline semantic aggregate {field} changed")
    lengths = {
        len(aggregate.items),
        len(generated_items),
        len(decompositions),
        len(rubrics),
    }
    if lengths != {37}:
        raise ValueError("baseline external inputs must contain exactly 37 paired items")
    for item, generated, decomposition, rubric in zip(
        aggregate.items,
        generated_items,
        decompositions,
        rubrics,
        strict=True,
    ):
        validate_baseline_semantic_item(
            item,
            cohort_manifest_sha256=cohort_manifest_sha256,
            generated_item=generated,
            decomposition=decomposition,
            rubric=rubric,
            instrument_lock=instrument_lock,
            evidence_prompt_version=evidence_prompt_version,
            evidence_prompt_sha256=evidence_prompt_sha256,
            rubric_prompt_version=rubric_prompt_version,
            rubric_prompt_sha256=rubric_prompt_sha256,
            judge_model=judge_model,
            judge_settings=judge_settings,
        )
    return aggregate


class PrecalibrationItemBinding(_ClosedModel):
    """Prose-free exact join for generation, decomposition, and owner gold."""

    item_id: Identifier
    generated_item_sha256: Sha256
    answer_sha256: Sha256
    decomposition_status: DecompositionOutcomeStatus
    decomposition_sha256: Sha256 | None
    decomposition_checkpoint_sha256: Sha256
    gold_item_sha256: Sha256
    binding_sha256: Sha256

    @model_validator(mode="after")
    def hash_is_exact(self) -> "PrecalibrationItemBinding":
        if self.decomposition_status is DecompositionOutcomeStatus.SUCCESS:
            if self.decomposition_sha256 is None:
                raise ValueError("successful item binding requires a decomposition")
        elif self.decomposition_sha256 is not None:
            raise ValueError("failed item binding cannot carry a decomposition")
        payload = self.model_dump(mode="json", exclude={"binding_sha256"})
        if self.binding_sha256 != canonical_json_sha256(payload):
            raise ValueError("binding_sha256 does not bind the precalibration item")
        return self


class PrecalibrationPrivateArtifact(_ClosedModel):
    """Hash-only join emitted before any semantic-scoring calls."""

    schema_version: Literal[PRECALIBRATION_PRIVATE_ARTIFACT_SCHEMA] = Field(
        PRECALIBRATION_PRIVATE_ARTIFACT_SCHEMA,
        alias="schema",
    )
    cohort_manifest_sha256: Sha256
    generation_artifact_sha256: Sha256
    decomposition_artifact_sha256: Sha256
    gold_set_sha256: Sha256
    gold_items_sha256: Sha256
    migration_artifact_sha256: Sha256 | None
    recovered_item_count: Literal[0, 1]
    recovered_item_ids: tuple[Identifier, ...]
    generation_latency_denominator: NonnegativeInt
    generation_latency_observed_count: NonnegativeInt
    decomposition_attempt_count: Literal[37]
    usable_decomposition_count: NonnegativeInt
    decomposition_technical_failure_count: NonnegativeInt
    decomposition_technical_failure_item_ids: tuple[Identifier, ...]
    decomposition_checkpoints_sha256: Sha256
    decomposition_usage_events_sha256: Sha256
    item_ids: tuple[Identifier, ...] = Field(min_length=37, max_length=37)
    items: tuple[PrecalibrationItemBinding, ...] = Field(min_length=37, max_length=37)
    artifact_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def joins_and_hash_are_exact(self) -> "PrecalibrationPrivateArtifact":
        _require_unique(self.item_ids, label="precalibration item IDs")
        _require_unique(
            self.recovered_item_ids,
            label="precalibration recovered item IDs",
        )
        if [item.item_id for item in self.items] != list(self.item_ids):
            raise ValueError("precalibration artifact must bind all 37 items in exact order")
        if len(self.recovered_item_ids) != self.recovered_item_count:
            raise ValueError("recovered item count must match recovered item IDs")
        if not set(self.recovered_item_ids) <= set(self.item_ids):
            raise ValueError("recovered item IDs must belong to the precalibration cohort")
        if self.recovered_item_count:
            if self.migration_artifact_sha256 is None:
                raise ValueError("recovered item requires a migration artifact")
        elif self.migration_artifact_sha256 is not None:
            raise ValueError("migration artifact requires a recovered item")
        if self.generation_latency_denominator != len(self.item_ids):
            raise ValueError("generation latency denominator must cover all items")
        if self.generation_latency_observed_count != (
            self.generation_latency_denominator - self.recovered_item_count
        ):
            raise ValueError("generation latency observations must exclude recovered items")
        if self.decomposition_attempt_count != len(self.item_ids):
            raise ValueError("decomposition attempts must cover all 37 items")
        if (
            self.usable_decomposition_count + self.decomposition_technical_failure_count
            != self.decomposition_attempt_count
        ):
            raise ValueError("usable and failed decompositions must cover every attempt")
        _require_unique(
            self.decomposition_technical_failure_item_ids,
            label="decomposition technical failure item IDs",
        )
        if (
            len(self.decomposition_technical_failure_item_ids)
            != self.decomposition_technical_failure_count
        ):
            raise ValueError("decomposition failure count must match failure item IDs")
        if not set(self.decomposition_technical_failure_item_ids) <= set(self.item_ids):
            raise ValueError("decomposition failure item IDs must belong to the cohort")
        failed_bindings = tuple(
            item.item_id
            for item in self.items
            if item.decomposition_status is DecompositionOutcomeStatus.TECHNICAL_FAILURE
        )
        if failed_bindings != self.decomposition_technical_failure_item_ids:
            raise ValueError("decomposition failure item bindings changed")
        payload = self.model_dump(mode="json", exclude={"artifact_sha256"})
        if self.artifact_sha256 != canonical_json_sha256(payload):
            raise ValueError("artifact_sha256 does not bind the precalibration artifact")
        return self


def _precalibration_item_binding(
    generated: PrivateGeneratedItem,
    outcome: PrivateDecompositionOutcome,
    decomposition: DecomposedPilotItem | None,
    gold_item: Mapping[str, object],
) -> PrecalibrationItemBinding:
    if gold_item.get("id") != generated.item_id:
        raise ValueError("precalibration gold item order or identity changed")
    if outcome.item_id != generated.item_id or outcome.answer_sha256 != generated.answer_sha256:
        raise ValueError("precalibration decomposition outcome binding changed")
    if isinstance(outcome, PrivateDecompositionCheckpoint):
        if decomposition is None or outcome.decomposition != decomposition:
            raise ValueError("successful decomposition outcome changed")
        _validate_decomposition(generated, decomposition)
        status = DecompositionOutcomeStatus.SUCCESS
        decomposition_sha256 = decomposition.decomposition_sha256
    else:
        if decomposition is not None:
            raise ValueError("failed decomposition outcome cannot bind a decomposition")
        status = DecompositionOutcomeStatus.TECHNICAL_FAILURE
        decomposition_sha256 = None
    raw: dict[str, object] = {
        "item_id": generated.item_id,
        "generated_item_sha256": generated.item_sha256,
        "answer_sha256": generated.answer_sha256,
        "decomposition_status": status,
        "decomposition_sha256": decomposition_sha256,
        "decomposition_checkpoint_sha256": outcome.checkpoint_sha256,
        "gold_item_sha256": canonical_json_sha256(dict(gold_item)),
    }
    raw["binding_sha256"] = canonical_json_sha256(raw)
    return PrecalibrationItemBinding.model_validate(raw)


def _validate_precalibration_checkpoints(
    *,
    cohort_manifest_sha256: str,
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    checkpoints: Sequence[PrivateDecompositionOutcome | Mapping[str, object]],
) -> tuple[PrivateDecompositionOutcome, ...]:
    normalized_list: list[PrivateDecompositionOutcome] = []
    for checkpoint in checkpoints:
        if isinstance(
            checkpoint,
            (PrivateDecompositionCheckpoint, PrivateDecompositionFailureCheckpoint),
        ):
            normalized_list.append(checkpoint)
            continue
        schema = checkpoint.get("schema")
        model = (
            PrivateDecompositionFailureCheckpoint
            if schema == PRIVATE_DECOMPOSITION_FAILURE_CHECKPOINT_SCHEMA
            else PrivateDecompositionCheckpoint
        )
        normalized_list.append(model.model_validate(checkpoint))
    normalized = tuple(normalized_list)
    if len(normalized) != 37:
        raise ValueError("precalibration cost closure requires exactly 37 decomposition calls")
    item_ids = tuple(item.item_id for item in generated_items)
    expected_layout = tuple((item_id, 1) for item_id in item_ids)
    actual_layout = tuple((checkpoint.item_id, checkpoint.repetition) for checkpoint in normalized)
    if actual_layout != expected_layout:
        raise ValueError(
            "decomposition checkpoints must be the 37 canonical repetition-1 calls in cohort order"
        )
    generated_by_id = {item.item_id: item for item in generated_items}
    decomposition_by_id = {item.item_id: item for item in decompositions}
    successful_ids: list[str] = []
    failed_ids: list[str] = []
    response_ids: list[str] = []
    for checkpoint in normalized:
        generated = generated_by_id[checkpoint.item_id]
        if checkpoint.cohort_manifest_sha256 != cohort_manifest_sha256:
            raise ValueError("decomposition checkpoint belongs to another cohort")
        if checkpoint.answer_sha256 != generated.answer_sha256:
            raise ValueError("decomposition checkpoint belongs to another answer")
        if isinstance(checkpoint, PrivateDecompositionCheckpoint):
            decomposition = decomposition_by_id.get(checkpoint.item_id)
            if decomposition is None or checkpoint.decomposition != decomposition:
                raise ValueError("canonical decomposition checkpoint changed")
            _validate_decomposition(generated, decomposition)
            successful_ids.append(checkpoint.item_id)
        else:
            if checkpoint.item_id in decomposition_by_id:
                raise ValueError("failed decomposition attempt cannot have a usable decomposition")
            failed_ids.append(checkpoint.item_id)
        response_ids.append(checkpoint.usage_events[0].response_id)
    if successful_ids != [item.item_id for item in decompositions]:
        raise ValueError("usable decompositions must follow successful outcomes in cohort order")
    if len(successful_ids) + len(failed_ids) != 37:
        raise ValueError("decomposition outcomes do not cover all 37 attempts")
    _require_unique(response_ids, label="precalibration decomposition response IDs")
    generated_response_ids = [
        event.response_id for generated in generated_items for event in generated.usage_events
    ]
    _require_unique(
        generated_response_ids,
        label="precalibration generation response IDs",
    )
    if set(generated_response_ids) & set(response_ids):
        raise ValueError("generation and decomposition response IDs overlap")
    return normalized


def build_precalibration_private_artifact(
    *,
    cohort_manifest_sha256: str,
    generation_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    gold_set_sha256: str,
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    gold_items: Sequence[Mapping[str, object]],
    decomposition_checkpoints: Sequence[PrivateDecompositionOutcome | Mapping[str, object]],
    migration_artifact_sha256: str | None = None,
    recovered_item_ids: Sequence[str] = (),
) -> PrecalibrationPrivateArtifact:
    if len(generated_items) != 37 or len(gold_items) != 37:
        raise ValueError("precalibration artifact requires exactly 37 generated and gold items")
    item_ids = tuple(item.item_id for item in generated_items)
    recovered_ids = tuple(recovered_item_ids)
    _require_unique(item_ids, label="precalibration generated item IDs")
    decomposition_ids = [item.item_id for item in decompositions]
    if decomposition_ids != [item_id for item_id in item_ids if item_id in decomposition_ids]:
        raise ValueError("usable decompositions must retain their cohort-relative order")
    _require_unique(decomposition_ids, label="precalibration usable decomposition IDs")
    normalized_checkpoints = _validate_precalibration_checkpoints(
        cohort_manifest_sha256=cohort_manifest_sha256,
        generated_items=generated_items,
        decompositions=decompositions,
        checkpoints=decomposition_checkpoints,
    )
    decomposition_by_id = {item.item_id: item for item in decompositions}
    bindings = tuple(
        _precalibration_item_binding(
            generated,
            outcome,
            decomposition_by_id.get(generated.item_id),
            gold_item,
        )
        for generated, outcome, gold_item in zip(
            generated_items,
            normalized_checkpoints,
            gold_items,
            strict=True,
        )
    )
    usage_events = tuple(checkpoint.usage_events[0] for checkpoint in normalized_checkpoints)
    failure_ids = tuple(
        checkpoint.item_id
        for checkpoint in normalized_checkpoints
        if isinstance(checkpoint, PrivateDecompositionFailureCheckpoint)
    )
    raw: dict[str, object] = {
        "schema": PRECALIBRATION_PRIVATE_ARTIFACT_SCHEMA,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "generation_artifact_sha256": generation_artifact_sha256,
        "decomposition_artifact_sha256": decomposition_artifact_sha256,
        "gold_set_sha256": gold_set_sha256,
        "gold_items_sha256": canonical_json_sha256([dict(item) for item in gold_items]),
        "migration_artifact_sha256": migration_artifact_sha256,
        "recovered_item_count": len(recovered_ids),
        "recovered_item_ids": list(recovered_ids),
        "generation_latency_denominator": len(item_ids),
        "generation_latency_observed_count": len(item_ids) - len(recovered_ids),
        "decomposition_attempt_count": len(normalized_checkpoints),
        "usable_decomposition_count": len(decompositions),
        "decomposition_technical_failure_count": len(failure_ids),
        "decomposition_technical_failure_item_ids": list(failure_ids),
        "decomposition_checkpoints_sha256": canonical_json_sha256(
            [checkpoint.model_dump(mode="json") for checkpoint in normalized_checkpoints]
        ),
        "decomposition_usage_events_sha256": canonical_json_sha256(
            [event.model_dump(mode="json") for event in usage_events]
        ),
        "item_ids": list(item_ids),
        "items": [binding.model_dump(mode="json") for binding in bindings],
    }
    raw["artifact_sha256"] = canonical_json_sha256(raw)
    return PrecalibrationPrivateArtifact.model_validate(raw)


def validate_precalibration_private_artifact(
    value: PrecalibrationPrivateArtifact | Mapping[str, object],
    *,
    cohort_manifest_sha256: str,
    generation_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    gold_set_sha256: str,
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    gold_items: Sequence[Mapping[str, object]],
    decomposition_checkpoints: Sequence[PrivateDecompositionOutcome | Mapping[str, object]],
    migration_artifact_sha256: str | None = None,
    recovered_item_ids: Sequence[str] = (),
) -> PrecalibrationPrivateArtifact:
    artifact = (
        value
        if isinstance(value, PrecalibrationPrivateArtifact)
        else PrecalibrationPrivateArtifact.model_validate(value)
    )
    expected = build_precalibration_private_artifact(
        cohort_manifest_sha256=cohort_manifest_sha256,
        generation_artifact_sha256=generation_artifact_sha256,
        decomposition_artifact_sha256=decomposition_artifact_sha256,
        gold_set_sha256=gold_set_sha256,
        generated_items=generated_items,
        decompositions=decompositions,
        gold_items=gold_items,
        decomposition_checkpoints=decomposition_checkpoints,
        migration_artifact_sha256=migration_artifact_sha256,
        recovered_item_ids=recovered_item_ids,
    )
    if artifact != expected:
        raise ValueError("precalibration artifact changed from its exact inputs")
    return artifact


class FullRunItemBinding(_ClosedModel):
    """Prose-free exact join for one generated/decomposed/semantic item."""

    item_id: Identifier
    generated_item_sha256: Sha256
    answer_sha256: Sha256
    decomposition_sha256: Sha256
    semantic_item_sha256: Sha256
    binding_sha256: Sha256

    @model_validator(mode="after")
    def hash_is_exact(self) -> "FullRunItemBinding":
        payload = self.model_dump(mode="json", exclude={"binding_sha256"})
        if self.binding_sha256 != canonical_json_sha256(payload):
            raise ValueError("binding_sha256 does not bind the full-run item")
        return self


class ManualScoringAggregate(_ClosedModel):
    """Optional full-cohort owner decisions for manual scoring dimensions."""

    schema_version: Literal[MANUAL_SCORING_AGGREGATE_SCHEMA] = Field(
        MANUAL_SCORING_AGGREGATE_SCHEMA,
        alias="schema",
    )
    cohort_manifest_sha256: Sha256
    generation_artifact_sha256: Sha256
    decomposition_artifact_sha256: Sha256
    instrument_sha256: Sha256
    item_ids: tuple[Identifier, ...] = Field(min_length=37, max_length=37)
    items: tuple[CalibrationItemLabel, ...] = Field(min_length=37, max_length=37)
    aggregate_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def cohort_and_hash_are_exact(self) -> "ManualScoringAggregate":
        _require_unique(self.item_ids, label="manual-scoring item IDs")
        if [item.item_id for item in self.items] != list(self.item_ids):
            raise ValueError("manual-scoring items must match all 37 IDs in exact order")
        payload = self.model_dump(mode="json", exclude={"aggregate_sha256"})
        if self.aggregate_sha256 != canonical_json_sha256(payload):
            raise ValueError("aggregate_sha256 does not bind manual scoring")
        return self


def _validate_manual_item_layout(
    *,
    label: CalibrationItemLabel,
    generated: PrivateGeneratedItem,
    decomposition: DecomposedPilotItem,
    rubric: ItemRubricInput,
) -> None:
    _validate_decomposition(generated, decomposition)
    if (
        label.item_id != generated.item_id
        or label.answer_sha256 != generated.answer_sha256
        or label.decomposition_sha256 != decomposition.decomposition_sha256
    ):
        raise ValueError(f"{generated.item_id}: manual-scoring item identity changed")
    expected_claims = [
        (claim.claim_id, claim.text, claim.claim_sha256) for claim in decomposition.claims
    ]
    actual_claims = [
        (claim.claim_id, claim.claim_text, claim.claim_sha256) for claim in label.claims
    ]
    if actual_claims != expected_claims:
        raise ValueError(f"{generated.item_id}: manual-scoring claim layout changed")
    rubric_binding = build_sanitized_rubric_binding(
        item_id=generated.item_id,
        rubric=rubric,
    )
    if label.rubric_sha256 != rubric_binding.calibration_rubric_sha256:
        raise ValueError(f"{generated.item_id}: manual-scoring rubric binding changed")
    expected_gold = [
        (claim.claim_id, claim.text, sha256_text(claim.text)) for claim in rubric.claims
    ]
    actual_gold = [
        (entry.claim_id, entry.claim_text, entry.claim_text_sha256)
        for entry in label.gold_claim_statuses
    ]
    if actual_gold != expected_gold:
        raise ValueError(f"{generated.item_id}: manual-scoring gold layout changed")
    expected_tripwires = [
        (index, text, sha256_text(text)) for index, text in enumerate(rubric.must_not_claim)
    ]
    actual_tripwires = [
        (entry.index, entry.claim_text, entry.claim_text_sha256)
        for entry in label.must_not_claim_statuses
    ]
    if actual_tripwires != expected_tripwires:
        raise ValueError(f"{generated.item_id}: manual-scoring tripwire layout changed")


def build_manual_scoring_aggregate(
    *,
    cohort_manifest_sha256: str,
    generation_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    instrument_lock: InstrumentLock,
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    rubrics: Sequence[ItemRubricInput],
    items: Sequence[CalibrationItemLabel | Mapping[str, object]],
) -> ManualScoringAggregate:
    if instrument_lock.cohort_manifest_sha256 != cohort_manifest_sha256:
        raise ValueError("manual-scoring instrument belongs to another cohort")
    if {len(generated_items), len(decompositions), len(rubrics), len(items)} != {37}:
        raise ValueError("manual scoring requires exactly 37 paired items")
    normalized_items = tuple(
        item
        if isinstance(item, CalibrationItemLabel)
        else CalibrationItemLabel.model_validate(item)
        for item in items
    )
    for label, generated, decomposition, rubric in zip(
        normalized_items,
        generated_items,
        decompositions,
        rubrics,
        strict=True,
    ):
        _validate_manual_item_layout(
            label=label,
            generated=generated,
            decomposition=decomposition,
            rubric=rubric,
        )
    raw: dict[str, object] = {
        "schema": MANUAL_SCORING_AGGREGATE_SCHEMA,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "generation_artifact_sha256": generation_artifact_sha256,
        "decomposition_artifact_sha256": decomposition_artifact_sha256,
        "instrument_sha256": instrument_lock.instrument_sha256,
        "item_ids": [item.item_id for item in generated_items],
        "items": [item.model_dump(mode="json") for item in normalized_items],
    }
    raw["aggregate_sha256"] = canonical_json_sha256(raw)
    return ManualScoringAggregate.model_validate(raw)


def validate_manual_scoring_aggregate(
    value: ManualScoringAggregate | Mapping[str, object],
    *,
    cohort_manifest_sha256: str,
    generation_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    instrument_lock: InstrumentLock,
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    rubrics: Sequence[ItemRubricInput],
) -> ManualScoringAggregate:
    aggregate = (
        value
        if isinstance(value, ManualScoringAggregate)
        else ManualScoringAggregate.model_validate(value)
    )
    expected = build_manual_scoring_aggregate(
        cohort_manifest_sha256=cohort_manifest_sha256,
        generation_artifact_sha256=generation_artifact_sha256,
        decomposition_artifact_sha256=decomposition_artifact_sha256,
        instrument_lock=instrument_lock,
        generated_items=generated_items,
        decompositions=decompositions,
        rubrics=rubrics,
        items=aggregate.items,
    )
    if aggregate != expected:
        raise ValueError("manual-scoring aggregate changed from its exact inputs")
    return aggregate


class PrivateFullRunArtifact(_ClosedModel):
    """Hash-only private join used as the reporting input boundary."""

    schema_version: Literal[PRIVATE_FULL_RUN_ARTIFACT_SCHEMA] = Field(
        PRIVATE_FULL_RUN_ARTIFACT_SCHEMA,
        alias="schema",
    )
    cohort_manifest_sha256: Sha256
    generation_artifact_sha256: Sha256
    decomposition_artifact_sha256: Sha256
    semantic_aggregate_sha256: Sha256
    instrument_id: Identifier
    instrument_sha256: Sha256
    manual_scoring_aggregate_sha256: Sha256 | None
    additional_usage_event_count: Annotated[int, Field(strict=True, ge=57)]
    additional_usage_events_sha256: Sha256
    item_ids: tuple[Identifier, ...] = Field(min_length=37, max_length=37)
    items: tuple[FullRunItemBinding, ...] = Field(min_length=37, max_length=37)
    artifact_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def joins_and_hash_are_exact(self) -> "PrivateFullRunArtifact":
        _require_unique(self.item_ids, label="private full-run item IDs")
        if [item.item_id for item in self.items] != list(self.item_ids):
            raise ValueError("private full-run artifact must bind all 37 items in exact order")
        payload = self.model_dump(mode="json", exclude={"artifact_sha256"})
        if self.artifact_sha256 != canonical_json_sha256(payload):
            raise ValueError("artifact_sha256 does not bind the private full-run artifact")
        return self


def _full_run_item_binding(
    generated: PrivateGeneratedItem,
    decomposition: DecomposedPilotItem,
    semantic: BaselineSemanticItem,
) -> FullRunItemBinding:
    _validate_decomposition(generated, decomposition)
    if (
        semantic.item_id != generated.item_id
        or semantic.answer_sha256 != generated.answer_sha256
        or semantic.decomposition_sha256 != decomposition.decomposition_sha256
    ):
        raise ValueError("full-run semantic item differs from generated/decomposed inputs")
    raw: dict[str, object] = {
        "item_id": generated.item_id,
        "generated_item_sha256": generated.item_sha256,
        "answer_sha256": generated.answer_sha256,
        "decomposition_sha256": decomposition.decomposition_sha256,
        "semantic_item_sha256": semantic.item_result_sha256,
    }
    raw["binding_sha256"] = canonical_json_sha256(raw)
    return FullRunItemBinding.model_validate(raw)


def _represented_usage_response_ids(
    *,
    generated_items: Sequence[PrivateGeneratedItem],
    semantic_aggregate: BaselineSemanticAggregate,
) -> set[str]:
    generated_ids = [
        event.response_id for generated in generated_items for event in generated.usage_events
    ]
    response_ids = set(generated_ids)
    if len(generated_ids) != len(response_ids):
        raise ValueError("generated-item usage response IDs must be globally unique")
    semantic_ids: list[str] = []
    for item in semantic_aggregate.items:
        semantic_ids.extend(
            result.usage_event.response_id for result in item.first_call_claim_evidence
        )
        if item.item_rubric is not None:
            semantic_ids.append(item.item_rubric.usage_event.response_id)
    if len(semantic_ids) != len(set(semantic_ids)):
        raise ValueError("baseline semantic usage response IDs must be unique")
    if response_ids & set(semantic_ids):
        raise ValueError("generated and semantic usage response IDs overlap")
    response_ids.update(semantic_ids)
    return response_ids


def _validate_additional_usage_events(
    *,
    events: Sequence[PrivateUsageEvent],
    represented_response_ids: set[str],
    calibration_semantic_aggregate: CalibrationSemanticAggregate,
) -> tuple[PrivateUsageEvent, ...]:
    normalized = tuple(
        PrivateUsageEvent.model_validate(event.model_dump(mode="json")) for event in events
    )
    response_ids = [event.response_id for event in normalized]
    _require_unique(response_ids, label="additional usage response IDs")
    overlap = represented_response_ids & set(response_ids)
    if overlap:
        raise ValueError("additional usage events duplicate represented provider calls")
    decomposition_count = sum(event.operation == "eval_claim_decomposition" for event in normalized)
    if decomposition_count != 57:
        raise ValueError("additional usage must contain exactly 57 decomposition calls")
    expected_repeats = tuple(
        item.repeat_first_claim_evidence.usage_event
        for item in calibration_semantic_aggregate.items
        if item.repeat_first_claim_evidence is not None
    )
    event_by_response = {event.response_id: event for event in normalized}
    for repeat in expected_repeats:
        if event_by_response.get(repeat.response_id) != repeat:
            raise ValueError("additional usage omits or changes calibration repeat evidence")
    return normalized


def build_private_full_run_artifact(
    *,
    cohort_manifest_sha256: str,
    generation_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    semantic_aggregate: BaselineSemanticAggregate,
    instrument_lock: InstrumentLock,
    calibration_semantic_aggregate: CalibrationSemanticAggregate,
    additional_usage_events: Sequence[PrivateUsageEvent],
    manual_scoring_aggregate: ManualScoringAggregate | None = None,
) -> PrivateFullRunArtifact:
    if instrument_lock.cohort_manifest_sha256 != cohort_manifest_sha256:
        raise ValueError("instrument lock belongs to another cohort")
    if semantic_aggregate.cohort_manifest_sha256 != cohort_manifest_sha256:
        raise ValueError("semantic aggregate belongs to another cohort")
    if semantic_aggregate.instrument_sha256 != instrument_lock.instrument_sha256:
        raise ValueError("semantic aggregate binds another scoring instrument")
    if calibration_semantic_aggregate.cohort_manifest_sha256 != cohort_manifest_sha256:
        raise ValueError("calibration semantic aggregate belongs to another cohort")
    if instrument_lock.judge_results_sha256 != calibration_semantic_aggregate.aggregate_sha256:
        raise ValueError("instrument lock does not bind the calibration semantic aggregate")
    if semantic_aggregate.generation_artifact_sha256 != generation_artifact_sha256:
        raise ValueError("semantic aggregate binds another generation artifact")
    if semantic_aggregate.decomposition_artifact_sha256 != decomposition_artifact_sha256:
        raise ValueError("semantic aggregate binds another decomposition artifact")
    if manual_scoring_aggregate is not None:
        expected_manual_identity = {
            "cohort_manifest_sha256": cohort_manifest_sha256,
            "generation_artifact_sha256": generation_artifact_sha256,
            "decomposition_artifact_sha256": decomposition_artifact_sha256,
            "instrument_sha256": instrument_lock.instrument_sha256,
            "item_ids": semantic_aggregate.item_ids,
        }
        for field, expected_value in expected_manual_identity.items():
            if getattr(manual_scoring_aggregate, field) != expected_value:
                raise ValueError(f"manual-scoring aggregate {field} changed")
    if {len(generated_items), len(decompositions), len(semantic_aggregate.items)} != {37}:
        raise ValueError("private full-run inputs must contain exactly 37 paired items")
    item_ids = [item.item_id for item in generated_items]
    if item_ids != list(semantic_aggregate.item_ids):
        raise ValueError("private full-run generated item order changed")
    bindings = tuple(
        _full_run_item_binding(generated, decomposition, semantic)
        for generated, decomposition, semantic in zip(
            generated_items,
            decompositions,
            semantic_aggregate.items,
            strict=True,
        )
    )
    normalized_additional_usage = _validate_additional_usage_events(
        events=additional_usage_events,
        represented_response_ids=_represented_usage_response_ids(
            generated_items=generated_items,
            semantic_aggregate=semantic_aggregate,
        ),
        calibration_semantic_aggregate=calibration_semantic_aggregate,
    )
    raw: dict[str, object] = {
        "schema": PRIVATE_FULL_RUN_ARTIFACT_SCHEMA,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "generation_artifact_sha256": generation_artifact_sha256,
        "decomposition_artifact_sha256": decomposition_artifact_sha256,
        "semantic_aggregate_sha256": semantic_aggregate.aggregate_sha256,
        "instrument_id": instrument_lock.instrument_id,
        "instrument_sha256": instrument_lock.instrument_sha256,
        "manual_scoring_aggregate_sha256": (
            None if manual_scoring_aggregate is None else manual_scoring_aggregate.aggregate_sha256
        ),
        "additional_usage_event_count": len(normalized_additional_usage),
        "additional_usage_events_sha256": canonical_json_sha256(
            [event.model_dump(mode="json") for event in normalized_additional_usage]
        ),
        "item_ids": item_ids,
        "items": [binding.model_dump(mode="json") for binding in bindings],
    }
    raw["artifact_sha256"] = canonical_json_sha256(raw)
    return PrivateFullRunArtifact.model_validate(raw)


def validate_private_full_run_artifact(
    value: PrivateFullRunArtifact | Mapping[str, object],
    *,
    cohort_manifest_sha256: str,
    generation_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    semantic_aggregate: BaselineSemanticAggregate,
    instrument_lock: InstrumentLock,
    calibration_semantic_aggregate: CalibrationSemanticAggregate,
    additional_usage_events: Sequence[PrivateUsageEvent],
    manual_scoring_aggregate: ManualScoringAggregate | None = None,
) -> PrivateFullRunArtifact:
    artifact = (
        value
        if isinstance(value, PrivateFullRunArtifact)
        else PrivateFullRunArtifact.model_validate(value)
    )
    expected = build_private_full_run_artifact(
        cohort_manifest_sha256=cohort_manifest_sha256,
        generation_artifact_sha256=generation_artifact_sha256,
        decomposition_artifact_sha256=decomposition_artifact_sha256,
        generated_items=generated_items,
        decompositions=decompositions,
        semantic_aggregate=semantic_aggregate,
        instrument_lock=instrument_lock,
        calibration_semantic_aggregate=calibration_semantic_aggregate,
        additional_usage_events=additional_usage_events,
        manual_scoring_aggregate=manual_scoring_aggregate,
    )
    if artifact != expected:
        raise ValueError("private full-run artifact changed from its exact inputs")
    return artifact


class DecompositionStabilityItem(_ClosedModel):
    """Claim-count stability for the three fixed decompositions of one answer."""

    item_id: Identifier
    answer_sha256: Sha256
    decomposition_sha256s: tuple[Sha256, Sha256, Sha256]
    claim_counts: tuple[NonnegativeInt, NonnegativeInt, NonnegativeInt]
    population_variance: NonnegativeFloat
    item_sha256: Sha256

    @model_validator(mode="after")
    def variance_and_hash_are_exact(self) -> "DecompositionStabilityItem":
        mean = sum(self.claim_counts) / 3
        expected_variance = sum((count - mean) ** 2 for count in self.claim_counts) / 3
        if not math.isclose(
            self.population_variance,
            expected_variance,
            abs_tol=1e-12,
        ):
            raise ValueError("population_variance does not match the claim-count triplet")
        payload = self.model_dump(mode="json", exclude={"item_sha256"})
        if self.item_sha256 != canonical_json_sha256(payload):
            raise ValueError("item_sha256 does not bind decomposition stability")
        return self


class DecompositionStability(_ClosedModel):
    """Offline descriptive stability artifact for the exact ten-item pilot."""

    schema_version: Literal[DECOMPOSITION_STABILITY_SCHEMA] = Field(
        DECOMPOSITION_STABILITY_SCHEMA,
        alias="schema",
    )
    decomposition_artifact_sha256: Sha256
    calibration_item_ids: tuple[Identifier, ...] = Field(min_length=10, max_length=10)
    repetitions_per_item: Literal[3] = 3
    items: tuple[DecompositionStabilityItem, ...] = Field(
        min_length=10,
        max_length=10,
    )
    total_claim_count: NonnegativeInt
    mean_claim_count: NonnegativeFloat
    stability_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def cohort_counts_and_hash_are_exact(self) -> "DecompositionStability":
        _require_unique(self.calibration_item_ids, label="stability calibration item IDs")
        if [item.item_id for item in self.items] != list(self.calibration_item_ids):
            raise ValueError("stability items must match the exact ten IDs in order")
        expected_total = sum(sum(item.claim_counts) for item in self.items)
        if self.total_claim_count != expected_total:
            raise ValueError("total_claim_count does not match the 30 decompositions")
        expected_mean = expected_total / 30
        if not math.isclose(self.mean_claim_count, expected_mean, abs_tol=1e-12):
            raise ValueError("mean_claim_count does not match the 30 decompositions")
        payload = self.model_dump(mode="json", exclude={"stability_sha256"})
        if self.stability_sha256 != canonical_json_sha256(payload):
            raise ValueError("stability_sha256 does not bind decomposition stability")
        return self


def _decomposition_stability_item(
    item_id: str,
    repetitions: Sequence[DecomposedPilotItem],
) -> DecompositionStabilityItem:
    if len(repetitions) != 3:
        raise ValueError(f"{item_id}: decomposition stability requires exactly 3 repeats")
    if [item.item_id for item in repetitions] != [item_id] * 3:
        raise ValueError(f"{item_id}: decomposition repetition item identity changed")
    answer_sha256s = {item.answer_sha256 for item in repetitions}
    if len(answer_sha256s) != 1:
        raise ValueError(f"{item_id}: decomposition repetitions bind different answers")
    claim_counts = tuple(len(item.claims) for item in repetitions)
    mean = sum(claim_counts) / 3
    population_variance = sum((count - mean) ** 2 for count in claim_counts) / 3
    raw: dict[str, object] = {
        "item_id": item_id,
        "answer_sha256": repetitions[0].answer_sha256,
        "decomposition_sha256s": [item.decomposition_sha256 for item in repetitions],
        "claim_counts": list(claim_counts),
        "population_variance": population_variance,
    }
    raw["item_sha256"] = canonical_json_sha256(raw)
    return DecompositionStabilityItem.model_validate(raw)


def build_decomposition_stability(
    *,
    decomposition_artifact_sha256: str,
    calibration_item_ids: Sequence[str],
    repetitions: Sequence[Sequence[DecomposedPilotItem | Mapping[str, object]]],
) -> DecompositionStability:
    """Report three-call claim-count variance without making provider calls."""

    if len(calibration_item_ids) != 10 or len(repetitions) != 10:
        raise ValueError("decomposition stability requires exactly 10 ordered items")
    normalized_repetitions = tuple(
        tuple(
            value
            if isinstance(value, DecomposedPilotItem)
            else DecomposedPilotItem.model_validate(value)
            for value in item_repetitions
        )
        for item_repetitions in repetitions
    )
    items = tuple(
        _decomposition_stability_item(item_id, item_repetitions)
        for item_id, item_repetitions in zip(
            calibration_item_ids,
            normalized_repetitions,
            strict=True,
        )
    )
    total_claim_count = sum(sum(item.claim_counts) for item in items)
    raw: dict[str, object] = {
        "schema": DECOMPOSITION_STABILITY_SCHEMA,
        "decomposition_artifact_sha256": decomposition_artifact_sha256,
        "calibration_item_ids": list(calibration_item_ids),
        "repetitions_per_item": 3,
        "items": [item.model_dump(mode="json") for item in items],
        "total_claim_count": total_claim_count,
        "mean_claim_count": total_claim_count / 30,
    }
    raw["stability_sha256"] = canonical_json_sha256(raw)
    return DecompositionStability.model_validate(raw)


def validate_decomposition_stability(
    value: DecompositionStability | Mapping[str, object],
    *,
    decomposition_artifact_sha256: str,
    calibration_item_ids: Sequence[str],
    repetitions: Sequence[Sequence[DecomposedPilotItem | Mapping[str, object]]],
) -> DecompositionStability:
    stability = (
        value
        if isinstance(value, DecompositionStability)
        else DecompositionStability.model_validate(value)
    )
    expected = build_decomposition_stability(
        decomposition_artifact_sha256=decomposition_artifact_sha256,
        calibration_item_ids=calibration_item_ids,
        repetitions=repetitions,
    )
    if stability != expected:
        raise ValueError("decomposition stability changed from its exact inputs")
    return stability


class AgreementCount(_ClosedModel):
    agreement_count: NonnegativeInt
    denominator: NonnegativeInt
    agreement_rate: UnitInterval | None

    @model_validator(mode="after")
    def rate_is_exact(self) -> "AgreementCount":
        if self.agreement_count > self.denominator:
            raise ValueError("agreement count cannot exceed denominator")
        if self.denominator == 0:
            if self.agreement_count != 0 or self.agreement_rate is not None:
                raise ValueError("zero-denominator agreement must be 0/0 with null rate")
            return self
        expected = self.agreement_count / self.denominator
        if self.agreement_rate is None or not math.isclose(
            self.agreement_rate,
            expected,
            abs_tol=1e-12,
        ):
            raise ValueError("agreement rate must equal count divided by denominator")
        return self


class DimensionAgreementProjection(AgreementCount):
    dimension: ScoringDimension


class CalibrationAgreementProjection(_ClosedModel):
    schema_version: Literal[AGREEMENT_PROJECTION_SCHEMA] = Field(
        AGREEMENT_PROJECTION_SCHEMA,
        alias="schema",
    )
    semantic_aggregate_sha256: Sha256
    pooled_exact_agreement: AgreementCount
    repeat_agreement: AgreementCount
    dimensions: tuple[DimensionAgreementProjection, ...] = Field(min_length=6, max_length=6)
    projection_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def dimensions_pool_and_hash_are_exact(self) -> "CalibrationAgreementProjection":
        if [entry.dimension for entry in self.dimensions] != list(ScoringDimension):
            raise ValueError("agreement dimensions must appear exactly once in fixed order")
        if self.pooled_exact_agreement.agreement_count != sum(
            entry.agreement_count for entry in self.dimensions
        ) or self.pooled_exact_agreement.denominator != sum(
            entry.denominator for entry in self.dimensions
        ):
            raise ValueError("pooled agreement must equal the exact dimension totals")
        payload = self.model_dump(mode="json", exclude={"projection_sha256"})
        if self.projection_sha256 != canonical_json_sha256(payload):
            raise ValueError("projection_sha256 does not bind the agreement projection")
        return self


def _agreement_count(matches: int, denominator: int) -> AgreementCount:
    return AgreementCount(
        agreement_count=matches,
        denominator=denominator,
        agreement_rate=(matches / denominator if denominator else None),
    )


def project_calibration_agreement(
    aggregate: CalibrationSemanticAggregate | Mapping[str, object],
    labels: CalibrationLabelFile | Mapping[str, object],
) -> CalibrationAgreementProjection:
    """Compare sealed semantic results with complete owner labels, without I/O."""

    semantic = (
        aggregate
        if isinstance(aggregate, CalibrationSemanticAggregate)
        else CalibrationSemanticAggregate.model_validate(aggregate)
    )
    owner = (
        labels
        if isinstance(labels, CalibrationLabelFile)
        else CalibrationLabelFile.model_validate(labels)
    )
    if owner.pilot_artifact_sha256 != semantic.pilot_artifact_sha256:
        raise ValueError("owner labels bind another pilot artifact")
    if owner.decomposition_artifact_sha256 != semantic.decomposition_artifact_sha256:
        raise ValueError("owner labels bind another decomposition artifact")
    if [item.item_id for item in owner.items] != list(semantic.calibration_item_ids):
        raise ValueError("owner labels do not cover calibration items in exact order")

    counts = {dimension: [0, 0] for dimension in ScoringDimension}
    repeat_matches = 0
    repeat_denominator = 0

    for result_item, owner_item in zip(semantic.items, owner.items, strict=True):
        rubric_result = result_item.item_rubric
        if owner_item.answer_sha256 != result_item.answer_sha256:
            raise ValueError(f"{owner_item.item_id}: owner answer binding changed")
        if owner_item.decomposition_sha256 != result_item.decomposition_sha256:
            raise ValueError(f"{owner_item.item_id}: owner decomposition binding changed")
        if owner_item.rubric_sha256 != rubric_result.rubric.calibration_rubric_sha256:
            raise ValueError(f"{owner_item.item_id}: owner rubric binding changed")
        if len(owner_item.claims) != len(rubric_result.locked_claims):
            raise ValueError(f"{owner_item.item_id}: owner claim count changed")

        match_entries = rubric_result.verdict.answer_claim_matches
        for owner_claim, locked_claim, evidence, mapping in zip(
            owner_item.claims,
            rubric_result.locked_claims,
            result_item.first_call_claim_evidence,
            match_entries,
            strict=True,
        ):
            if (
                owner_claim.claim_id != locked_claim.claim_id
                or owner_claim.claim_sha256 != locked_claim.claim_sha256
                or sha256_text(owner_claim.claim_text) != locked_claim.claim_text_sha256
            ):
                raise ValueError(f"{owner_item.item_id}: owner claim identity changed")
            if owner_claim.faithfulness is None:
                raise ValueError(f"{owner_claim.claim_id}: faithfulness is not labelled")
            if owner_claim.cited_source_labels is None:
                raise ValueError(f"{owner_claim.claim_id}: cited sources are not labelled")
            if owner_claim.gold_match_ids is None:
                raise ValueError(f"{owner_claim.claim_id}: gold matches are not labelled")

            counts[ScoringDimension.FAITHFULNESS][1] += 1
            counts[ScoringDimension.FAITHFULNESS][0] += int(
                owner_claim.faithfulness.value == evidence.verdict.faithfulness
            )

            source_verdicts = {
                entry.source_number: entry.label for entry in evidence.verdict.source_verdicts
            }
            if set(owner_claim.cited_source_labels) != set(locked_claim.cited_source_numbers):
                raise ValueError(f"{owner_claim.claim_id}: owner cited-source cardinality changed")
            for source_number in locked_claim.cited_source_numbers:
                counts[ScoringDimension.CITED_SOURCE_SUPPORT][1] += 1
                counts[ScoringDimension.CITED_SOURCE_SUPPORT][0] += int(
                    owner_claim.cited_source_labels[source_number].value
                    == source_verdicts[source_number]
                )

            counts[ScoringDimension.CLAIM_MAPPING][1] += 1
            counts[ScoringDimension.CLAIM_MAPPING][0] += int(
                set(owner_claim.gold_match_ids) == set(mapping.gold_claim_ids)
            )

        if len(owner_item.gold_claim_statuses) != len(rubric_result.verdict.gold_claims):
            raise ValueError(f"{owner_item.item_id}: owner gold-status count changed")
        for owner_status, binding, verdict in zip(
            owner_item.gold_claim_statuses,
            rubric_result.rubric.gold_claims,
            rubric_result.verdict.gold_claims,
            strict=True,
        ):
            if (
                owner_status.claim_id != binding.claim_id
                or owner_status.claim_text_sha256 != binding.claim_text_sha256
                or sha256_text(owner_status.claim_text) != binding.claim_text_sha256
            ):
                raise ValueError(f"{owner_item.item_id}: owner gold claim identity changed")
            if owner_status.status is None:
                raise ValueError(f"{owner_status.claim_id}: gold status is not labelled")
            counts[ScoringDimension.GOLD_STATUS][1] += 1
            counts[ScoringDimension.GOLD_STATUS][0] += int(
                owner_status.status.value == verdict.status
            )

        if len(owner_item.must_not_claim_statuses) != len(rubric_result.verdict.must_not_claim):
            raise ValueError(f"{owner_item.item_id}: owner tripwire count changed")
        for owner_status, text_hash, verdict in zip(
            owner_item.must_not_claim_statuses,
            rubric_result.rubric.must_not_claim_sha256s,
            rubric_result.verdict.must_not_claim,
            strict=True,
        ):
            if (
                owner_status.index != verdict.index
                or owner_status.claim_text_sha256 != text_hash
                or sha256_text(owner_status.claim_text) != text_hash
            ):
                raise ValueError(f"{owner_item.item_id}: owner tripwire identity changed")
            if owner_status.status is None:
                raise ValueError(
                    f"{owner_item.item_id}: tripwire {owner_status.index} is not labelled"
                )
            counts[ScoringDimension.MUST_NOT_TRIPWIRES][1] += 1
            counts[ScoringDimension.MUST_NOT_TRIPWIRES][0] += int(
                owner_status.status.value == verdict.status
            )

        if owner_item.response_behavior is None:
            raise ValueError(f"{owner_item.item_id}: response behavior is not labelled")
        counts[ScoringDimension.RESPONSE_BEHAVIOR][1] += 1
        counts[ScoringDimension.RESPONSE_BEHAVIOR][0] += int(
            owner_item.response_behavior.value == rubric_result.verdict.response_behavior
        )

        if result_item.first_call_claim_evidence:
            first = result_item.first_call_claim_evidence[0]
            repeat = result_item.repeat_first_claim_evidence
            if repeat is None:  # pragma: no cover - model validation already enforces this
                raise ValueError("fixed repeat evidence result is missing")
            repeat_denominator += 1
            repeat_matches += int(first.verdict.faithfulness == repeat.verdict.faithfulness)
            first_sources = {
                entry.source_number: entry.label for entry in first.verdict.source_verdicts
            }
            repeat_sources = {
                entry.source_number: entry.label for entry in repeat.verdict.source_verdicts
            }
            if list(first_sources) != list(repeat_sources):
                raise ValueError("repeat evidence source decision IDs changed")
            repeat_denominator += len(first_sources)
            repeat_matches += sum(
                first_sources[source_number] == repeat_sources[source_number]
                for source_number in first_sources
            )

    dimensions = tuple(
        DimensionAgreementProjection(
            dimension=dimension,
            agreement_count=counts[dimension][0],
            denominator=counts[dimension][1],
            agreement_rate=(
                counts[dimension][0] / counts[dimension][1] if counts[dimension][1] else None
            ),
        )
        for dimension in ScoringDimension
    )
    pooled_matches = sum(entry.agreement_count for entry in dimensions)
    pooled_denominator = sum(entry.denominator for entry in dimensions)
    raw: dict[str, object] = {
        "schema": AGREEMENT_PROJECTION_SCHEMA,
        "semantic_aggregate_sha256": semantic.aggregate_sha256,
        "pooled_exact_agreement": _agreement_count(
            pooled_matches,
            pooled_denominator,
        ).model_dump(mode="json"),
        "repeat_agreement": _agreement_count(
            repeat_matches,
            repeat_denominator,
        ).model_dump(mode="json"),
        "dimensions": [entry.model_dump(mode="json") for entry in dimensions],
    }
    raw["projection_sha256"] = canonical_json_sha256(raw)
    return CalibrationAgreementProjection.model_validate(raw)


__all__ = [
    "AGREEMENT_PROJECTION_SCHEMA",
    "BASELINE_SEMANTIC_AGGREGATE_SCHEMA",
    "BASELINE_SEMANTIC_ITEM_SCHEMA",
    "CALIBRATION_SEMANTIC_AGGREGATE_SCHEMA",
    "CALIBRATION_SEMANTIC_ITEM_SCHEMA",
    "CLAIM_EVIDENCE_RESULT_SCHEMA",
    "DECOMPOSITION_STABILITY_SCHEMA",
    "ITEM_RUBRIC_RESULT_SCHEMA",
    "MANUAL_SCORING_AGGREGATE_SCHEMA",
    "PRECALIBRATION_PRIVATE_ARTIFACT_SCHEMA",
    "PRIVATE_FULL_RUN_ARTIFACT_SCHEMA",
    "AgreementCount",
    "BaselineSemanticAggregate",
    "BaselineSemanticItem",
    "CalibrationAgreementProjection",
    "CalibrationSemanticAggregate",
    "CalibrationSemanticItem",
    "ClaimEvidenceResult",
    "DimensionAgreementProjection",
    "DecompositionStability",
    "DecompositionStabilityItem",
    "EvidenceSourceBinding",
    "FullRunItemBinding",
    "ItemRubricResult",
    "LockedClaimBinding",
    "ManualScoringAggregate",
    "PrecalibrationItemBinding",
    "PrecalibrationPrivateArtifact",
    "PrivateFullRunArtifact",
    "SanitizedGoldClaimBinding",
    "SanitizedRubricBinding",
    "build_calibration_semantic_aggregate",
    "build_calibration_semantic_item",
    "build_baseline_semantic_aggregate",
    "build_baseline_semantic_item",
    "build_baseline_semantic_item_from_calibration",
    "build_claim_evidence_result",
    "build_decomposition_stability",
    "build_item_rubric_result",
    "build_manual_scoring_aggregate",
    "build_precalibration_private_artifact",
    "build_private_full_run_artifact",
    "build_sanitized_rubric_binding",
    "project_calibration_agreement",
    "validate_calibration_semantic_aggregate",
    "validate_baseline_semantic_aggregate",
    "validate_baseline_semantic_item",
    "validate_claim_evidence_result",
    "validate_decomposition_stability",
    "validate_item_rubric_result",
    "validate_manual_scoring_aggregate",
    "validate_precalibration_private_artifact",
    "validate_private_full_run_artifact",
]
