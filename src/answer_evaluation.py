"""Strict artifacts for the held-out answer-evaluation workflow.

Private artifacts deliberately retain questions, answers, decomposed claims, and
the exact source text supplied to the generator.  The public summary has a
separate, recursively closed schema that cannot carry any of those text fields.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)


PRIVATE_GENERATED_ITEM_SCHEMA = "archivist.answer_evaluation.private_item/1"
DECOMPOSED_PILOT_ITEM_SCHEMA = "archivist.answer_evaluation.decomposition/1"
CALIBRATION_LABEL_SCHEMA = "archivist.answer_evaluation.calibration_labels/1"
INSTRUMENT_LOCK_SCHEMA = "archivist.answer_evaluation.instrument_lock/1"
PUBLIC_SUMMARY_SCHEMA = "archivist.answer_evaluation.public_summary/2"
PRECALIBRATION_PUBLIC_SUMMARY_SCHEMA = "archivist.answer_evaluation.precalibration_public_summary/2"
COHORT_MANIFEST_SCHEMA = "archivist.answer_evaluation.cohort_manifest/1"
PRIVATE_GENERATION_CHECKPOINT_SCHEMA = "archivist.answer_evaluation.private_generation_checkpoint/1"
PRIVATE_DECOMPOSITION_CHECKPOINT_SCHEMA = (
    "archivist.answer_evaluation.private_decomposition_checkpoint/1"
)

JUDGE_EXACT_AGREEMENT_MINIMUM = 0.80
JUDGE_REPEAT_AGREEMENT_MINIMUM = 0.90
BASELINE_NEXT_ACTION = "complete_37_question_evaluation"

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_TRACE_ID_PATTERN = r"^[0-9a-f]{32}$"
_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$"
_GIT_COMMIT_PATTERN = r"^[0-9a-f]{40}$"

Sha256 = Annotated[str, StringConstraints(pattern=_SHA256_PATTERN)]
Identifier = Annotated[str, StringConstraints(pattern=_IDENTIFIER_PATTERN)]
GitCommit = Annotated[str, StringConstraints(pattern=_GIT_COMMIT_PATTERN)]
NonemptyString = Annotated[str, StringConstraints(min_length=1)]
SourceNumber = Annotated[int, Field(strict=True, ge=1)]
NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]
NonnegativeFloat = Annotated[float, Field(strict=True, ge=0.0, allow_inf_nan=False)]
UnitInterval = Annotated[
    float,
    Field(strict=True, ge=0.0, le=1.0, allow_inf_nan=False),
]


class EvaluationStratum(StrEnum):
    FOCUSED_BIOGRAPHICAL = "focused_biographical"
    FOCUSED_ANALYTICAL = "focused_analytical"
    CONCEPTUAL = "conceptual"
    BROAD_THEMATIC = "broad_thematic"
    OUT_OF_CORPUS = "out_of_corpus"
    ADVERSARIAL_PREMISE = "adversarial_premise"


class ExpectedBehavior(StrEnum):
    ANSWER = "answer"
    ABSTAIN = "abstain"


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    CLEAN_ABSTENTION = "clean_abstention"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    GENERATION_CONTRACT_FAILED = "generation_contract_failed"
    CORPUS_INTEGRITY_FAILED = "corpus_integrity_failed"


class EvidenceDecision(StrEnum):
    DIRECT_ANSWER = "direct_answer"
    PARTIAL_ANSWER = "partial_answer"
    QUALIFIED_NEAR_MATCH = "qualified_near_match"
    CLEAN_ABSTENTION = "clean_abstention"
    INDETERMINATE = "indeterminate"


class FaithfulnessLabel(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"


class CitedSourceLabel(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"


class ResponseBehavior(StrEnum):
    SUBSTANTIVE_ANSWER = "substantive_answer"
    DECLINE = "decline"
    PREMISE_CORRECTION = "premise_correction"
    PARTIAL_DECLINE_THEN_ANSWER = "partial_decline_then_answer"


class GoldClaimStatus(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    CONTRADICTED = "contradicted"


class MustNotClaimStatus(StrEnum):
    ASSERTED = "asserted"
    NOT_ASSERTED = "not_asserted"


class ScoringMode(StrEnum):
    JUDGE = "judge"
    MANUAL = "manual"
    MIXED = "mixed"


class ScoringDimension(StrEnum):
    FAITHFULNESS = "faithfulness"
    CITED_SOURCE_SUPPORT = "cited_source_support"
    CLAIM_MAPPING = "claim_mapping"
    GOLD_STATUS = "gold_status"
    MUST_NOT_TRIPWIRES = "must_not_tripwires"
    RESPONSE_BEHAVIOR = "response_behavior"


class BaselineRunStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class MetricAvailability(StrEnum):
    AVAILABLE = "available"
    PENDING = "pending"


class PublicMetricId(StrEnum):
    CITATION_RESOLVABILITY = "citation_resolvability"
    CITATION_COMPLETENESS = "citation_completeness"
    MALFORMED_CITATION_RATE = "malformed_citation_rate"
    CITATION_GROUNDEDNESS_GOLD_MATCHED = "citation_groundedness_gold_matched"
    CITATION_GROUNDEDNESS_JUDGE_ONLY = "citation_groundedness_judge_only"
    FAITHFULNESS_SUPPORTED = "faithfulness_supported"
    FAITHFULNESS_PARTIALLY_SUPPORTED = "faithfulness_partially_supported"
    FAITHFULNESS_UNSUPPORTED = "faithfulness_unsupported"
    FAITHFULNESS_CONTRADICTED = "faithfulness_contradicted"
    GOLD_CLAIM_RECALL = "gold_claim_recall"
    ESSENTIAL_GOLD_CLAIM_RECALL = "essential_gold_claim_recall"
    MUST_NOT_CLAIM_VIOLATION = "must_not_claim_violation"
    OUT_OF_CORPUS_ABSTENTION = "out_of_corpus_abstention"
    ADVERSARIAL_PREMISE_CORRECTION = "adversarial_premise_correction"
    FALSE_ABSTENTION = "false_abstention"
    ANSWER_SUCCESS = "answer_success"


class PrecalibrationMetricId(StrEnum):
    """Closed metrics available before any semantic-scoring calls."""

    CITATION_RESOLVABILITY = "citation_resolvability"
    CITATION_COMPLETENESS = "citation_completeness"
    MALFORMED_CITATION_RATE = "malformed_citation_rate"
    CITED_SOURCE_GOLD_LOCATION_MATCH = "cited_source_gold_location_match"
    GOLD_LOCATION_RETRIEVAL_COVERAGE = "gold_location_retrieval_coverage"
    CITATION_GROUNDEDNESS = "citation_groundedness"
    FAITHFULNESS_SUPPORTED = "faithfulness_supported"
    FAITHFULNESS_PARTIALLY_SUPPORTED = "faithfulness_partially_supported"
    FAITHFULNESS_UNSUPPORTED = "faithfulness_unsupported"
    FAITHFULNESS_CONTRADICTED = "faithfulness_contradicted"
    GOLD_CLAIM_RECALL = "gold_claim_recall"
    ESSENTIAL_GOLD_CLAIM_RECALL = "essential_gold_claim_recall"
    MUST_NOT_CLAIM_VIOLATION = "must_not_claim_violation"
    OUT_OF_CORPUS_ABSTENTION = "out_of_corpus_abstention"
    ADVERSARIAL_PREMISE_CORRECTION = "adversarial_premise_correction"
    FALSE_ABSTENTION = "false_abstention"


class PublicLimitationId(StrEnum):
    """Closed, prose-free limitations that qualify the public baseline."""

    CANONICAL_MODEL_ID_MUTABILITY = "canonical_current_model_ids_are_not_immutable_snapshots"
    GENERATOR_SPREAD_UNMEASURED = "generator_output_variance_not_measured"
    DESCRIPTIVE_NOT_GATE = "evaluation_is_descriptive_not_a_release_gate"
    MANUAL_FAITHFULNESS_PENDING = "manual_faithfulness_pending"
    MANUAL_CITED_SOURCE_SUPPORT_PENDING = "manual_cited_source_support_pending"
    MANUAL_CLAIM_MAPPING_PENDING = "manual_claim_mapping_pending"
    MANUAL_GOLD_STATUS_PENDING = "manual_gold_status_pending"
    MANUAL_MUST_NOT_TRIPWIRES_PENDING = "manual_must_not_tripwires_pending"
    MANUAL_RESPONSE_BEHAVIOR_PENDING = "manual_response_behavior_pending"
    SEMANTIC_SCORING_PENDING = "semantic_scoring_pending_calibration"
    TRACE_RECOVERED_ITEM_PRESENT = "trace_recovered_item_present"


class _ClosedModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


def sha256_text(value: str) -> str:
    """Hash the exact UTF-8 representation of a private text field."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def canonical_json_bytes(value: object, *, pretty: bool = False) -> bytes:
    """Serialize JSON deterministically and reject non-finite numbers."""

    options: dict[str, object] = {
        "ensure_ascii": False,
        "sort_keys": True,
        "allow_nan": False,
    }
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    return (json.dumps(_jsonable(value), **options) + ("\n" if pretty else "")).encode("utf-8")


def canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_atomic_no_overwrite(path: Path, payload: object) -> str:
    """Atomically publish one JSON file and fail if the destination exists.

    A fully flushed temporary file is hard-linked into place.  Creating the
    destination link is atomic and, unlike ``replace``, cannot overwrite an
    artifact produced by an earlier evaluation.
    """

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(payload, pretty=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise FileExistsError(f"Refusing to overwrite evaluation artifact: {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    return hashlib.sha256(data).hexdigest()


class CohortItemBinding(_ClosedModel):
    """Text-free binding for one item in the prospectively closed cohort."""

    item_id: Identifier
    question_sha256: Sha256
    stratum: EvaluationStratum
    expected_behavior: ExpectedBehavior
    binding_sha256: Sha256

    @model_validator(mode="after")
    def binding_is_exact(self) -> "CohortItemBinding":
        payload = self.model_dump(mode="json", exclude={"binding_sha256"})
        if self.binding_sha256 != canonical_json_sha256(payload):
            raise ValueError("item binding_sha256 does not bind the exact cohort item")
        return self


class CohortModelBinding(_ClosedModel):
    """Exact requested model and settings for one evaluation role."""

    model_id: NonemptyString
    settings: dict[str, JsonValue]
    binding_sha256: Sha256

    @model_validator(mode="after")
    def binding_is_exact(self) -> "CohortModelBinding":
        payload = self.model_dump(mode="json", exclude={"binding_sha256"})
        if self.binding_sha256 != canonical_json_sha256(payload):
            raise ValueError("model binding_sha256 does not bind model ID and settings")
        return self


class CohortPromptBinding(_ClosedModel):
    """Versioned hash of one prompt contract used by the closed cohort."""

    prompt_id: Identifier
    version: Identifier
    prompt_sha256: Sha256
    binding_sha256: Sha256

    @model_validator(mode="after")
    def binding_is_exact(self) -> "CohortPromptBinding":
        payload = self.model_dump(mode="json", exclude={"binding_sha256"})
        if self.binding_sha256 != canonical_json_sha256(payload):
            raise ValueError("prompt binding_sha256 does not bind prompt identity")
        return self


class CohortStructuredOutputBinding(_ClosedModel):
    """Hash of one exact structured-output JSON schema."""

    output_id: Identifier
    schema_sha256: Sha256
    binding_sha256: Sha256

    @model_validator(mode="after")
    def binding_is_exact(self) -> "CohortStructuredOutputBinding":
        payload = self.model_dump(mode="json", exclude={"binding_sha256"})
        if self.binding_sha256 != canonical_json_sha256(payload):
            raise ValueError("structured-output binding_sha256 does not bind schema identity")
        return self


class CohortRetrievalBinding(_ClosedModel):
    """Closed identity of the frozen V26 retrieval surface."""

    n_results: Literal[5] = 5
    max_primary_distance: Literal[1.05] = 1.05
    max_final_sources: Literal[8] = 8
    hnsw_space: Literal["l2"] = "l2"
    neighbor_expansion_policy: Literal["primaries_first_then_immediate_neighbors"] = (
        "primaries_first_then_immediate_neighbors"
    )
    merge_adjacent_chunks: Literal[False] = False
    collection_name: NonemptyString
    collection_count: Annotated[int, Field(strict=True, ge=1)]
    binding_sha256: Sha256

    @model_validator(mode="after")
    def binding_is_exact(self) -> "CohortRetrievalBinding":
        payload = self.model_dump(mode="json", exclude={"binding_sha256"})
        if self.binding_sha256 != canonical_json_sha256(payload):
            raise ValueError("retrieval binding_sha256 does not bind retrieval identity")
        return self


class AnswerEvaluationCohortManifest(_ClosedModel):
    """Prospective, text-free closure of the ten-plus-twenty-seven run.

    The manifest deliberately contains no mutable timestamps.  Rebuilding it
    from the same frozen inputs therefore produces byte-identical canonical
    JSON.  ``write_json_atomic_no_overwrite`` can publish it once, while
    ``validate_cohort_manifest`` prevents a separately rehashed substitute from
    being accepted against the current repository inputs.
    """

    schema_version: Literal[COHORT_MANIFEST_SCHEMA] = Field(
        COHORT_MANIFEST_SCHEMA,
        alias="schema",
    )
    evaluation_id: Identifier
    candidate_commit: GitCommit
    rag_policy: Identifier
    gold_set_sha256: Sha256
    question_set_sha256: Sha256
    corpus_manifest_sha256: Sha256
    chunks_sha256: Sha256
    model_catalog_sha256: Sha256
    runner_sha256: Sha256
    items: tuple[CohortItemBinding, ...] = Field(min_length=37, max_length=37)
    calibration_item_ids: tuple[Identifier, ...] = Field(
        min_length=10,
        max_length=10,
    )
    remaining_item_ids: tuple[Identifier, ...] = Field(
        min_length=27,
        max_length=27,
    )
    generator: CohortModelBinding
    planner: CohortModelBinding
    judge: CohortModelBinding
    embedding_model: Literal["text-embedding-3-small"] = "text-embedding-3-small"
    retrieval: CohortRetrievalBinding
    prompts: tuple[CohortPromptBinding, ...] = Field(min_length=5, max_length=5)
    structured_outputs: tuple[CohortStructuredOutputBinding, ...] = Field(
        min_length=5,
        max_length=5,
    )
    model_identity_limitation: Literal["canonical_provider_ids_are_not_immutable_snapshots"] = (
        "canonical_provider_ids_are_not_immutable_snapshots"
    )
    calibration_items_immutable: Literal[True] = True
    remaining_phase_may_regenerate_calibration: Literal[False] = False
    manifest_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def partition_and_hash_are_exact(self) -> "AnswerEvaluationCohortManifest":
        item_ids = [item.item_id for item in self.items]
        _require_unique(item_ids, label="cohort item IDs")
        _require_unique(self.calibration_item_ids, label="calibration item IDs")
        _require_unique(self.remaining_item_ids, label="remaining item IDs")
        calibration_ids = set(self.calibration_item_ids)
        expected_calibration = [item_id for item_id in item_ids if item_id in calibration_ids]
        expected_remaining = [item_id for item_id in item_ids if item_id not in calibration_ids]
        if list(self.calibration_item_ids) != expected_calibration:
            raise ValueError(
                "calibration_item_ids must preserve their exact order in the 37-item cohort"
            )
        if list(self.remaining_item_ids) != expected_remaining:
            raise ValueError(
                "remaining_item_ids must be the ordered complement of calibration_item_ids"
            )
        if set(item_ids) != calibration_ids | set(self.remaining_item_ids):
            raise ValueError("calibration and remaining IDs must partition the cohort")
        _require_unique(
            [prompt.prompt_id for prompt in self.prompts],
            label="cohort prompt IDs",
        )
        _require_unique(
            [output.output_id for output in self.structured_outputs],
            label="cohort structured-output IDs",
        )
        payload = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if self.manifest_sha256 != canonical_json_sha256(payload):
            raise ValueError("manifest_sha256 does not bind the exact cohort manifest")
        return self


def build_cohort_item_binding(
    *,
    item_id: str,
    question: str,
    stratum: EvaluationStratum | str,
    expected_behavior: ExpectedBehavior | str,
) -> CohortItemBinding:
    raw: dict[str, object] = {
        "item_id": item_id,
        "question_sha256": sha256_text(question),
        "stratum": stratum,
        "expected_behavior": expected_behavior,
    }
    raw["binding_sha256"] = canonical_json_sha256(raw)
    return CohortItemBinding.model_validate(raw)


def build_cohort_model_binding(
    *,
    model_id: str,
    settings: Mapping[str, JsonValue],
) -> CohortModelBinding:
    normalized_settings = json.loads(canonical_json_bytes(dict(settings)))
    if not isinstance(normalized_settings, dict):  # pragma: no cover - defensive
        raise ValueError("model settings must be a JSON object")
    raw: dict[str, object] = {
        "model_id": model_id,
        "settings": normalized_settings,
    }
    raw["binding_sha256"] = canonical_json_sha256(raw)
    return CohortModelBinding.model_validate(raw)


def build_cohort_prompt_binding(
    *,
    prompt_id: str,
    version: str,
    prompt_sha256: str,
) -> CohortPromptBinding:
    raw: dict[str, object] = {
        "prompt_id": prompt_id,
        "version": version,
        "prompt_sha256": prompt_sha256,
    }
    raw["binding_sha256"] = canonical_json_sha256(raw)
    return CohortPromptBinding.model_validate(raw)


def build_cohort_structured_output_binding(
    *,
    output_id: str,
    schema_sha256: str,
) -> CohortStructuredOutputBinding:
    raw: dict[str, object] = {
        "output_id": output_id,
        "schema_sha256": schema_sha256,
    }
    raw["binding_sha256"] = canonical_json_sha256(raw)
    return CohortStructuredOutputBinding.model_validate(raw)


def build_cohort_retrieval_binding(
    *,
    collection_name: str,
    collection_count: int,
    n_results: int = 5,
    max_primary_distance: float = 1.05,
    max_final_sources: int = 8,
    hnsw_space: str = "l2",
    neighbor_expansion_policy: str = "primaries_first_then_immediate_neighbors",
    merge_adjacent_chunks: bool = False,
) -> CohortRetrievalBinding:
    raw: dict[str, object] = {
        "n_results": n_results,
        "max_primary_distance": max_primary_distance,
        "max_final_sources": max_final_sources,
        "hnsw_space": hnsw_space,
        "neighbor_expansion_policy": neighbor_expansion_policy,
        "merge_adjacent_chunks": merge_adjacent_chunks,
        "collection_name": collection_name,
        "collection_count": collection_count,
    }
    raw["binding_sha256"] = canonical_json_sha256(raw)
    return CohortRetrievalBinding.model_validate(raw)


def _normalize_cohort_item(
    value: CohortItemBinding | Mapping[str, object],
) -> CohortItemBinding:
    if isinstance(value, CohortItemBinding):
        return value
    if "binding_sha256" in value:
        return CohortItemBinding.model_validate(value)
    item_id = value.get("item_id", value.get("id"))
    question = value.get("question")
    stratum = value.get("stratum")
    expected_behavior = value.get("expected_behavior")
    if not all(isinstance(part, str) for part in (item_id, question, stratum, expected_behavior)):
        raise ValueError(
            "cohort items must provide string id, question, stratum, and expected_behavior"
        )
    return build_cohort_item_binding(
        item_id=item_id,
        question=question,
        stratum=stratum,
        expected_behavior=expected_behavior,
    )


def _normalize_cohort_model(
    value: CohortModelBinding | Mapping[str, object],
) -> CohortModelBinding:
    if isinstance(value, CohortModelBinding):
        return value
    if "binding_sha256" in value:
        return CohortModelBinding.model_validate(value)
    model_id = value.get("model_id")
    settings = value.get("settings")
    if not isinstance(model_id, str) or not isinstance(settings, Mapping):
        raise ValueError("cohort model bindings require model_id and settings")
    return build_cohort_model_binding(model_id=model_id, settings=settings)  # type: ignore[arg-type]


def _normalize_cohort_prompt(
    value: CohortPromptBinding | Mapping[str, object],
) -> CohortPromptBinding:
    if isinstance(value, CohortPromptBinding):
        return value
    if "binding_sha256" in value:
        return CohortPromptBinding.model_validate(value)
    prompt_id = value.get("prompt_id")
    version = value.get("version")
    prompt_sha256 = value.get("prompt_sha256")
    if not all(isinstance(part, str) for part in (prompt_id, version, prompt_sha256)):
        raise ValueError("cohort prompt bindings require prompt_id, version, and prompt_sha256")
    return build_cohort_prompt_binding(
        prompt_id=prompt_id,
        version=version,
        prompt_sha256=prompt_sha256,
    )


def _normalize_cohort_structured_output(
    value: CohortStructuredOutputBinding | Mapping[str, object],
) -> CohortStructuredOutputBinding:
    if isinstance(value, CohortStructuredOutputBinding):
        return value
    if "binding_sha256" in value:
        return CohortStructuredOutputBinding.model_validate(value)
    output_id = value.get("output_id")
    schema_sha256 = value.get("schema_sha256")
    if not isinstance(output_id, str) or not isinstance(schema_sha256, str):
        raise ValueError("structured-output bindings require output_id and schema_sha256")
    return build_cohort_structured_output_binding(
        output_id=output_id,
        schema_sha256=schema_sha256,
    )


def _normalize_cohort_retrieval(
    value: CohortRetrievalBinding | Mapping[str, object],
) -> CohortRetrievalBinding:
    if isinstance(value, CohortRetrievalBinding):
        return value
    if "binding_sha256" in value:
        return CohortRetrievalBinding.model_validate(value)
    return build_cohort_retrieval_binding(
        collection_name=str(value.get("collection_name") or ""),
        collection_count=value.get("collection_count"),  # type: ignore[arg-type]
        n_results=value.get("n_results", 5),  # type: ignore[arg-type]
        max_primary_distance=value.get("max_primary_distance", 1.05),  # type: ignore[arg-type]
        max_final_sources=value.get("max_final_sources", 8),  # type: ignore[arg-type]
        hnsw_space=value.get("hnsw_space", "l2"),  # type: ignore[arg-type]
        neighbor_expansion_policy=value.get(
            "neighbor_expansion_policy",
            "primaries_first_then_immediate_neighbors",
        ),  # type: ignore[arg-type]
        merge_adjacent_chunks=value.get("merge_adjacent_chunks", False),  # type: ignore[arg-type]
    )


def build_cohort_manifest(
    *,
    evaluation_id: str,
    candidate_commit: str,
    rag_policy: str,
    gold_set_sha256: str,
    question_set_sha256: str,
    corpus_manifest_sha256: str,
    chunks_sha256: str,
    model_catalog_sha256: str,
    runner_sha256: str,
    items: Sequence[CohortItemBinding | Mapping[str, object]],
    calibration_item_ids: Sequence[str],
    generator: CohortModelBinding | Mapping[str, object],
    planner: CohortModelBinding | Mapping[str, object],
    judge: CohortModelBinding | Mapping[str, object],
    embedding_model: str,
    retrieval: CohortRetrievalBinding | Mapping[str, object],
    prompts: Sequence[CohortPromptBinding | Mapping[str, object]],
    structured_outputs: Sequence[CohortStructuredOutputBinding | Mapping[str, object]],
) -> AnswerEvaluationCohortManifest:
    """Build the deterministic, closed ten-plus-twenty-seven cohort contract."""

    normalized_items = tuple(_normalize_cohort_item(item) for item in items)
    normalized_calibration = tuple(calibration_item_ids)
    calibration_set = set(normalized_calibration)
    remaining = tuple(
        item.item_id for item in normalized_items if item.item_id not in calibration_set
    )
    raw: dict[str, object] = {
        "schema": COHORT_MANIFEST_SCHEMA,
        "evaluation_id": evaluation_id,
        "candidate_commit": candidate_commit,
        "rag_policy": rag_policy,
        "gold_set_sha256": gold_set_sha256,
        "question_set_sha256": question_set_sha256,
        "corpus_manifest_sha256": corpus_manifest_sha256,
        "chunks_sha256": chunks_sha256,
        "model_catalog_sha256": model_catalog_sha256,
        "runner_sha256": runner_sha256,
        "items": [item.model_dump(mode="json") for item in normalized_items],
        "calibration_item_ids": list(normalized_calibration),
        "remaining_item_ids": list(remaining),
        "generator": _normalize_cohort_model(generator).model_dump(mode="json"),
        "planner": _normalize_cohort_model(planner).model_dump(mode="json"),
        "judge": _normalize_cohort_model(judge).model_dump(mode="json"),
        "embedding_model": embedding_model,
        "retrieval": _normalize_cohort_retrieval(retrieval).model_dump(mode="json"),
        "prompts": [_normalize_cohort_prompt(prompt).model_dump(mode="json") for prompt in prompts],
        "structured_outputs": [
            _normalize_cohort_structured_output(output).model_dump(mode="json")
            for output in structured_outputs
        ],
        "model_identity_limitation": ("canonical_provider_ids_are_not_immutable_snapshots"),
        "calibration_items_immutable": True,
        "remaining_phase_may_regenerate_calibration": False,
    }
    raw["manifest_sha256"] = canonical_json_sha256(raw)
    return AnswerEvaluationCohortManifest.model_validate(raw)


def validate_cohort_manifest(
    value: AnswerEvaluationCohortManifest | Mapping[str, object],
    *,
    expected: AnswerEvaluationCohortManifest,
) -> AnswerEvaluationCohortManifest:
    """Validate intrinsic hashes and exact equality to current frozen inputs."""

    validated = (
        value
        if isinstance(value, AnswerEvaluationCohortManifest)
        else AnswerEvaluationCohortManifest.model_validate(value)
    )
    if validated.model_dump(mode="json") != expected.model_dump(mode="json"):
        raise ValueError("cohort manifest does not match the exact frozen evaluation inputs")
    return validated


class PrivateOrderedSource(_ClosedModel):
    source_number: SourceNumber
    chunk_id: NonemptyString
    text: str
    text_sha256: Sha256
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    source_sha256: Sha256

    @model_validator(mode="after")
    def hashes_are_exact(self) -> "PrivateOrderedSource":
        if self.text_sha256 != sha256_text(self.text):
            raise ValueError("source text_sha256 does not match exact chunk text")
        payload = self.model_dump(mode="json", exclude={"source_sha256"})
        if self.source_sha256 != canonical_json_sha256(payload):
            raise ValueError("source_sha256 does not bind the exact source object")
        return self


def build_private_source(
    *,
    source_number: int,
    chunk_id: str,
    text: str,
    metadata: Mapping[str, JsonValue] | None = None,
) -> PrivateOrderedSource:
    raw: dict[str, object] = {
        "source_number": source_number,
        "chunk_id": chunk_id,
        "text": text,
        "text_sha256": sha256_text(text),
        "metadata": dict(metadata or {}),
    }
    raw["source_sha256"] = canonical_json_sha256(raw)
    return PrivateOrderedSource.model_validate(raw)


class PrivateUsageEvent(_ClosedModel):
    sequence: SourceNumber
    response_id: NonemptyString
    recorded_at: NonemptyString
    operation: NonemptyString
    requested_model: NonemptyString
    actual_model: NonemptyString
    input_tokens: NonnegativeInt
    cached_tokens: NonnegativeInt
    cache_write_tokens: NonnegativeInt
    output_tokens: NonnegativeInt
    reasoning_tokens: NonnegativeInt
    total_tokens: NonnegativeInt
    estimated_cost_nano_usd: NonnegativeInt | None
    pricing_version: NonemptyString
    unpriced: bool = Field(strict=True)
    event_sha256: Sha256

    @model_validator(mode="after")
    def usage_is_coherent_and_bound(self) -> "PrivateUsageEvent":
        if self.cached_tokens > self.input_tokens:
            raise ValueError("cached_tokens cannot exceed input_tokens")
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError("reasoning_tokens cannot exceed output_tokens")
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens must equal input_tokens plus output_tokens")
        if self.unpriced != (self.estimated_cost_nano_usd is None):
            raise ValueError("unpriced must agree with estimated_cost_nano_usd")
        payload = self.model_dump(mode="json", exclude={"event_sha256"})
        if self.event_sha256 != canonical_json_sha256(payload):
            raise ValueError("event_sha256 does not bind the exact usage event")
        return self


def build_private_usage_event(**values: object) -> PrivateUsageEvent:
    raw = dict(values)
    raw["event_sha256"] = canonical_json_sha256(raw)
    return PrivateUsageEvent.model_validate(raw)


class PrivateTraceReference(_ClosedModel):
    sequence: SourceNumber
    schema_id: Identifier
    trace_id: Annotated[str, StringConstraints(pattern=_TRACE_ID_PATTERN)]
    path: NonemptyString
    sha256: Sha256
    query_sha256: Sha256
    retrieval_version: Identifier

    @field_validator("path")
    @classmethod
    def path_is_relative_and_portable(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError("trace path must use forward slashes")
        parsed = PurePosixPath(value)
        if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
            raise ValueError("trace path must stay within the evaluation run directory")
        return value


class PrivateGeneratedItem(_ClosedModel):
    schema_version: Literal[PRIVATE_GENERATED_ITEM_SCHEMA] = Field(
        PRIVATE_GENERATED_ITEM_SCHEMA,
        alias="schema",
    )
    item_id: Identifier
    question: NonemptyString
    question_sha256: Sha256
    stratum: EvaluationStratum
    expected_behavior: ExpectedBehavior
    answer: NonemptyString
    answer_sha256: Sha256
    status: AnswerStatus
    evidence_decision: EvidenceDecision
    diagnostics: dict[str, JsonValue]
    diagnostics_sha256: Sha256
    sources: tuple[PrivateOrderedSource, ...]
    elapsed_seconds: NonnegativeFloat
    usage_events: tuple[PrivateUsageEvent, ...] = Field(min_length=1)
    trace_references: tuple[PrivateTraceReference, ...] = Field(min_length=1)
    item_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def identity_and_order_are_exact(self) -> "PrivateGeneratedItem":
        if self.question_sha256 != sha256_text(self.question):
            raise ValueError("question_sha256 does not match exact question")
        if self.answer_sha256 != sha256_text(self.answer):
            raise ValueError("answer_sha256 does not match exact answer")
        if self.diagnostics_sha256 != canonical_json_sha256(self.diagnostics):
            raise ValueError("diagnostics_sha256 does not match diagnostics")
        _require_dense_sequence(
            [source.source_number for source in self.sources],
            label="source numbers",
        )
        _require_dense_sequence(
            [event.sequence for event in self.usage_events],
            label="usage-event sequence",
        )
        _require_dense_sequence(
            [trace.sequence for trace in self.trace_references],
            label="trace-reference sequence",
        )
        _require_unique([source.chunk_id for source in self.sources], label="chunk IDs")
        _require_unique(
            [event.response_id for event in self.usage_events],
            label="usage response IDs",
        )
        _require_unique(
            [trace.trace_id for trace in self.trace_references],
            label="trace IDs",
        )
        payload = self.model_dump(mode="json", exclude={"item_sha256"})
        if self.item_sha256 != canonical_json_sha256(payload):
            raise ValueError("item_sha256 does not bind the exact generated item")
        return self


def build_private_generated_item(
    *,
    item_id: str,
    question: str,
    stratum: EvaluationStratum | str,
    expected_behavior: ExpectedBehavior | str,
    answer: str,
    status: AnswerStatus | str,
    evidence_decision: EvidenceDecision | str,
    diagnostics: Mapping[str, JsonValue],
    sources: Sequence[PrivateOrderedSource | Mapping[str, object]],
    elapsed_seconds: float,
    usage_events: Sequence[PrivateUsageEvent | Mapping[str, object]],
    trace_references: Sequence[PrivateTraceReference | Mapping[str, object]],
) -> PrivateGeneratedItem:
    normalized_sources = tuple(
        value
        if isinstance(value, PrivateOrderedSource)
        else PrivateOrderedSource.model_validate(value)
        for value in sources
    )
    normalized_usage = tuple(
        value if isinstance(value, PrivateUsageEvent) else PrivateUsageEvent.model_validate(value)
        for value in usage_events
    )
    normalized_traces = tuple(
        value
        if isinstance(value, PrivateTraceReference)
        else PrivateTraceReference.model_validate(value)
        for value in trace_references
    )
    raw: dict[str, object] = {
        "schema": PRIVATE_GENERATED_ITEM_SCHEMA,
        "item_id": item_id,
        "question": question,
        "question_sha256": sha256_text(question),
        "stratum": stratum,
        "expected_behavior": expected_behavior,
        "answer": answer,
        "answer_sha256": sha256_text(answer),
        "status": status,
        "evidence_decision": evidence_decision,
        "diagnostics": dict(diagnostics),
        "diagnostics_sha256": canonical_json_sha256(dict(diagnostics)),
        "sources": [source.model_dump(mode="json") for source in normalized_sources],
        "elapsed_seconds": elapsed_seconds,
        "usage_events": [event.model_dump(mode="json") for event in normalized_usage],
        "trace_references": [trace.model_dump(mode="json") for trace in normalized_traces],
    }
    raw["item_sha256"] = canonical_json_sha256(raw)
    return PrivateGeneratedItem.model_validate(raw)


class PrivateGenerationCheckpoint(_ClosedModel):
    """One generated item bound to exactly one closed evaluation cohort."""

    schema_version: Literal[PRIVATE_GENERATION_CHECKPOINT_SCHEMA] = Field(
        PRIVATE_GENERATION_CHECKPOINT_SCHEMA,
        alias="schema",
    )
    cohort_manifest_sha256: Sha256
    item: PrivateGeneratedItem
    checkpoint_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def checkpoint_hash_is_exact(self) -> "PrivateGenerationCheckpoint":
        payload = self.model_dump(mode="json", exclude={"checkpoint_sha256"})
        if self.checkpoint_sha256 != canonical_json_sha256(payload):
            raise ValueError("checkpoint_sha256 does not bind the exact generation checkpoint")
        return self


def build_private_generation_checkpoint(
    *,
    cohort_manifest_sha256: str,
    item: PrivateGeneratedItem | Mapping[str, object],
) -> PrivateGenerationCheckpoint:
    normalized = (
        item
        if isinstance(item, PrivateGeneratedItem)
        else PrivateGeneratedItem.model_validate(item)
    )
    raw: dict[str, object] = {
        "schema": PRIVATE_GENERATION_CHECKPOINT_SCHEMA,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "item": normalized.model_dump(mode="json"),
    }
    raw["checkpoint_sha256"] = canonical_json_sha256(raw)
    return PrivateGenerationCheckpoint.model_validate(raw)


def validate_private_generation_checkpoint(
    value: PrivateGenerationCheckpoint | Mapping[str, object],
    *,
    cohort_manifest_sha256: str,
    expected_item: CohortItemBinding,
) -> PrivateGenerationCheckpoint:
    """Reject a stale-run or copied generated-item checkpoint."""

    checkpoint = (
        value
        if isinstance(value, PrivateGenerationCheckpoint)
        else PrivateGenerationCheckpoint.model_validate(value)
    )
    if checkpoint.cohort_manifest_sha256 != cohort_manifest_sha256:
        raise ValueError("generation checkpoint belongs to another cohort manifest")
    generated = checkpoint.item
    if generated.item_id != expected_item.item_id:
        raise ValueError("generation checkpoint belongs to another cohort item")
    if generated.question_sha256 != expected_item.question_sha256:
        raise ValueError("generation checkpoint question binding changed")
    if generated.stratum != expected_item.stratum:
        raise ValueError("generation checkpoint stratum binding changed")
    if generated.expected_behavior != expected_item.expected_behavior:
        raise ValueError("generation checkpoint expected behavior binding changed")
    return checkpoint


class DecomposedClaim(_ClosedModel):
    claim_id: Identifier
    text: NonemptyString
    char_start: NonnegativeInt
    char_end: Annotated[int, Field(strict=True, ge=1)]
    cited_source_numbers: tuple[SourceNumber, ...]
    claim_sha256: Sha256

    @model_validator(mode="after")
    def span_and_hash_are_valid(self) -> "DecomposedClaim":
        if self.char_end <= self.char_start:
            raise ValueError("claim char_end must be greater than char_start")
        _require_unique(self.cited_source_numbers, label="cited source numbers")
        payload = self.model_dump(mode="json", exclude={"claim_sha256"})
        if self.claim_sha256 != canonical_json_sha256(payload):
            raise ValueError("claim_sha256 does not bind the exact decomposed claim")
        return self


def build_decomposed_claim(
    *,
    claim_id: str,
    text: str,
    char_start: int,
    char_end: int,
    cited_source_numbers: Sequence[int],
) -> DecomposedClaim:
    raw: dict[str, object] = {
        "claim_id": claim_id,
        "text": text,
        "char_start": char_start,
        "char_end": char_end,
        "cited_source_numbers": list(cited_source_numbers),
    }
    raw["claim_sha256"] = canonical_json_sha256(raw)
    return DecomposedClaim.model_validate(raw)


class DecomposedPilotItem(_ClosedModel):
    schema_version: Literal[DECOMPOSED_PILOT_ITEM_SCHEMA] = Field(
        DECOMPOSED_PILOT_ITEM_SCHEMA,
        alias="schema",
    )
    item_id: Identifier
    answer_sha256: Sha256
    claims: tuple[DecomposedClaim, ...]
    decomposition_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def claim_order_and_hash_are_exact(self) -> "DecomposedPilotItem":
        _require_unique([claim.claim_id for claim in self.claims], label="claim IDs")
        starts = [claim.char_start for claim in self.claims]
        if starts != sorted(starts):
            raise ValueError("decomposed claims must be ordered by char_start")
        for left, right in zip(self.claims, self.claims[1:], strict=False):
            if left.char_end > right.char_start:
                raise ValueError("decomposed claim spans cannot overlap")
        payload = self.model_dump(mode="json", exclude={"decomposition_sha256"})
        if self.decomposition_sha256 != canonical_json_sha256(payload):
            raise ValueError("decomposition_sha256 does not bind the exact decomposition")
        return self


def build_decomposed_pilot_item(
    *,
    item_id: str,
    answer_sha256: str,
    claims: Sequence[DecomposedClaim | Mapping[str, object]],
) -> DecomposedPilotItem:
    normalized = tuple(
        claim if isinstance(claim, DecomposedClaim) else DecomposedClaim.model_validate(claim)
        for claim in claims
    )
    raw: dict[str, object] = {
        "schema": DECOMPOSED_PILOT_ITEM_SCHEMA,
        "item_id": item_id,
        "answer_sha256": answer_sha256,
        "claims": [claim.model_dump(mode="json") for claim in normalized],
    }
    raw["decomposition_sha256"] = canonical_json_sha256(raw)
    return DecomposedPilotItem.model_validate(raw)


class PrivateProviderMetadata(_ClosedModel):
    """Closed provider identity retained beside a tracked judge call."""

    response_id: NonemptyString = Field(alias="id")
    model: NonemptyString
    created_at: NonnegativeInt | NonnegativeFloat | NonemptyString | None
    system_fingerprint: NonemptyString | None


class PrivateDecompositionCheckpoint(_ClosedModel):
    """One answer-only decomposition call, closed over identity and usage."""

    schema_version: Literal[PRIVATE_DECOMPOSITION_CHECKPOINT_SCHEMA] = Field(
        PRIVATE_DECOMPOSITION_CHECKPOINT_SCHEMA,
        alias="schema",
    )
    cohort_manifest_sha256: Sha256
    item_id: Identifier
    answer_sha256: Sha256
    repetition: Annotated[int, Field(strict=True, ge=1, le=3)]
    prompt_version: Identifier
    prompt_sha256: Sha256
    judge_model: NonemptyString
    judge_settings: dict[str, JsonValue]
    provider: PrivateProviderMetadata
    usage_events: tuple[PrivateUsageEvent, ...] = Field(min_length=1, max_length=1)
    decomposition: DecomposedPilotItem
    checkpoint_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def identities_and_hash_are_exact(self) -> "PrivateDecompositionCheckpoint":
        if self.decomposition.item_id != self.item_id:
            raise ValueError("decomposition checkpoint item binding changed")
        if self.decomposition.answer_sha256 != self.answer_sha256:
            raise ValueError("decomposition checkpoint answer binding changed")
        event = self.usage_events[0]
        if event.sequence != 1:
            raise ValueError("decomposition usage-event sequence must be exactly 1")
        if event.operation != "eval_claim_decomposition":
            raise ValueError("decomposition usage-event operation changed")
        if event.response_id != self.provider.response_id:
            raise ValueError("decomposition provider and usage response IDs differ")
        if event.requested_model != self.judge_model:
            raise ValueError("decomposition requested model differs from judge model")
        if event.actual_model != self.provider.model:
            raise ValueError("decomposition provider and usage actual models differ")
        if self.provider.model != self.judge_model:
            raise ValueError("decomposition provider model differs from judge model")
        payload = self.model_dump(mode="json", exclude={"checkpoint_sha256"})
        if self.checkpoint_sha256 != canonical_json_sha256(payload):
            raise ValueError("checkpoint_sha256 does not bind the exact decomposition checkpoint")
        return self


def build_private_decomposition_checkpoint(
    *,
    cohort_manifest_sha256: str,
    item_id: str,
    answer_sha256: str,
    repetition: int,
    prompt_version: str,
    prompt_sha256: str,
    judge_model: str,
    judge_settings: Mapping[str, JsonValue],
    provider: PrivateProviderMetadata | Mapping[str, object],
    usage_event: PrivateUsageEvent | Mapping[str, object],
    decomposition: DecomposedPilotItem | Mapping[str, object],
) -> PrivateDecompositionCheckpoint:
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
    normalized_decomposition = (
        decomposition
        if isinstance(decomposition, DecomposedPilotItem)
        else DecomposedPilotItem.model_validate(decomposition)
    )
    normalized_settings = json.loads(canonical_json_bytes(dict(judge_settings)))
    if not isinstance(normalized_settings, dict):  # pragma: no cover - defensive
        raise ValueError("judge settings must be a JSON object")
    raw: dict[str, object] = {
        "schema": PRIVATE_DECOMPOSITION_CHECKPOINT_SCHEMA,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "item_id": item_id,
        "answer_sha256": answer_sha256,
        "repetition": repetition,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "judge_model": judge_model,
        "judge_settings": normalized_settings,
        "provider": normalized_provider.model_dump(mode="json"),
        "usage_events": [normalized_usage.model_dump(mode="json")],
        "decomposition": normalized_decomposition.model_dump(mode="json"),
    }
    raw["checkpoint_sha256"] = canonical_json_sha256(raw)
    return PrivateDecompositionCheckpoint.model_validate(raw)


def validate_private_decomposition_checkpoint(
    value: PrivateDecompositionCheckpoint | Mapping[str, object],
    *,
    cohort_manifest_sha256: str,
    generated_item: PrivateGeneratedItem,
    repetition: int,
    prompt_version: str,
    prompt_sha256: str,
    judge_model: str,
    judge_settings: Mapping[str, JsonValue],
) -> PrivateDecompositionCheckpoint:
    """Reject stale, copied, or configuration-drifted decomposition state."""

    checkpoint = (
        value
        if isinstance(value, PrivateDecompositionCheckpoint)
        else PrivateDecompositionCheckpoint.model_validate(value)
    )
    expected_settings = json.loads(canonical_json_bytes(dict(judge_settings)))
    expected = {
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "item_id": generated_item.item_id,
        "answer_sha256": generated_item.answer_sha256,
        "repetition": repetition,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "judge_model": judge_model,
        "judge_settings": expected_settings,
    }
    actual = {
        "cohort_manifest_sha256": checkpoint.cohort_manifest_sha256,
        "item_id": checkpoint.item_id,
        "answer_sha256": checkpoint.answer_sha256,
        "repetition": checkpoint.repetition,
        "prompt_version": checkpoint.prompt_version,
        "prompt_sha256": checkpoint.prompt_sha256,
        "judge_model": checkpoint.judge_model,
        "judge_settings": checkpoint.judge_settings,
    }
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            raise ValueError(f"decomposition checkpoint {field} changed")
    _validate_decomposition_against_generated(
        generated_item,
        checkpoint.decomposition,
    )
    return checkpoint


class CalibrationClaimLabel(_ClosedModel):
    claim_id: Identifier
    claim_text: NonemptyString
    claim_sha256: Sha256
    faithfulness: FaithfulnessLabel | None
    gold_match_ids: tuple[Identifier, ...] | None
    cited_source_labels: dict[int, CitedSourceLabel] | None

    @model_validator(mode="after")
    def optional_values_are_structurally_valid(self) -> "CalibrationClaimLabel":
        if self.gold_match_ids is not None:
            _require_unique(self.gold_match_ids, label="gold match IDs")
        if self.cited_source_labels is not None and any(
            source_number < 1 for source_number in self.cited_source_labels
        ):
            raise ValueError("cited-source label keys must be positive source numbers")
        return self


class CalibrationGoldClaimStatus(_ClosedModel):
    claim_id: Identifier
    claim_text: NonemptyString
    claim_text_sha256: Sha256
    status: GoldClaimStatus | None

    @model_validator(mode="after")
    def text_hash_is_exact(self) -> "CalibrationGoldClaimStatus":
        if self.claim_text_sha256 != sha256_text(self.claim_text):
            raise ValueError("gold claim text hash does not match exact rubric text")
        return self


class CalibrationMustNotClaimStatus(_ClosedModel):
    index: NonnegativeInt
    claim_text: NonemptyString
    claim_text_sha256: Sha256
    status: MustNotClaimStatus | None

    @model_validator(mode="after")
    def text_hash_is_exact(self) -> "CalibrationMustNotClaimStatus":
        if self.claim_text_sha256 != sha256_text(self.claim_text):
            raise ValueError("must-not-claim text hash does not match exact rubric text")
        return self


class CalibrationItemLabel(_ClosedModel):
    item_id: Identifier
    answer_sha256: Sha256
    decomposition_sha256: Sha256
    rubric_sha256: Sha256
    response_behavior: ResponseBehavior | None
    claims: tuple[CalibrationClaimLabel, ...]
    gold_claim_statuses: tuple[CalibrationGoldClaimStatus, ...]
    must_not_claim_statuses: tuple[CalibrationMustNotClaimStatus, ...]


class CalibrationRubricGoldClaim(_ClosedModel):
    claim_id: Identifier
    text: NonemptyString


class CalibrationRubric(_ClosedModel):
    item_id: Identifier
    gold_claims: tuple[CalibrationRubricGoldClaim, ...]
    must_not_claims: tuple[NonemptyString, ...]
    rubric_sha256: Sha256

    @model_validator(mode="after")
    def rubric_order_and_hash_are_exact(self) -> "CalibrationRubric":
        _require_unique(
            [claim.claim_id for claim in self.gold_claims],
            label="rubric gold claim IDs",
        )
        payload = self.model_dump(mode="json", exclude={"rubric_sha256"})
        if self.rubric_sha256 != canonical_json_sha256(payload):
            raise ValueError("rubric_sha256 does not bind the ordered gold rubric")
        return self


class CalibrationLabelFile(_ClosedModel):
    schema_version: Literal[CALIBRATION_LABEL_SCHEMA] = Field(
        CALIBRATION_LABEL_SCHEMA,
        alias="schema",
    )
    pilot_artifact_sha256: Sha256
    decomposition_artifact_sha256: Sha256
    items: tuple[CalibrationItemLabel, ...]

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def item_ids_are_unique(self) -> "CalibrationLabelFile":
        _require_unique([item.item_id for item in self.items], label="calibration item IDs")
        return self


def build_calibration_label_template(
    *,
    generated_items: Sequence[PrivateGeneratedItem | Mapping[str, object]],
    decomposed_items: Sequence[DecomposedPilotItem | Mapping[str, object]],
    gold_items: Sequence[Mapping[str, object]],
    pilot_artifact_sha256: str,
    decomposition_artifact_sha256: str,
) -> CalibrationLabelFile:
    generated, decomposed = _paired_pilot_items(generated_items, decomposed_items)
    rubrics = _calibration_rubrics(gold_items)
    if [rubric.item_id for rubric in rubrics] != [item.item_id for item in generated]:
        raise ValueError("gold rubric order must match generated pilot item order")
    item_labels: list[CalibrationItemLabel] = []
    for generated_item, decomposed_item, rubric in zip(
        generated,
        decomposed,
        rubrics,
        strict=True,
    ):
        _validate_decomposition_against_generated(generated_item, decomposed_item)
        item_labels.append(
            CalibrationItemLabel(
                item_id=generated_item.item_id,
                answer_sha256=generated_item.answer_sha256,
                decomposition_sha256=decomposed_item.decomposition_sha256,
                rubric_sha256=rubric.rubric_sha256,
                response_behavior=None,
                claims=tuple(
                    CalibrationClaimLabel(
                        claim_id=claim.claim_id,
                        claim_text=claim.text,
                        claim_sha256=claim.claim_sha256,
                        faithfulness=None,
                        gold_match_ids=None,
                        cited_source_labels=None,
                    )
                    for claim in decomposed_item.claims
                ),
                gold_claim_statuses=tuple(
                    CalibrationGoldClaimStatus(
                        claim_id=claim.claim_id,
                        claim_text=claim.text,
                        claim_text_sha256=sha256_text(claim.text),
                        status=None,
                    )
                    for claim in rubric.gold_claims
                ),
                must_not_claim_statuses=tuple(
                    CalibrationMustNotClaimStatus(
                        index=index,
                        claim_text=text,
                        claim_text_sha256=sha256_text(text),
                        status=None,
                    )
                    for index, text in enumerate(rubric.must_not_claims)
                ),
            )
        )
    return CalibrationLabelFile(
        pilot_artifact_sha256=pilot_artifact_sha256,
        decomposition_artifact_sha256=decomposition_artifact_sha256,
        items=tuple(item_labels),
    )


def validate_calibration_labels_for_judge(
    payload: CalibrationLabelFile | Mapping[str, object],
    *,
    generated_items: Sequence[PrivateGeneratedItem | Mapping[str, object]],
    decomposed_items: Sequence[DecomposedPilotItem | Mapping[str, object]],
    gold_items: Sequence[Mapping[str, object]],
    pilot_artifact_sha256: str,
    decomposition_artifact_sha256: str,
) -> CalibrationLabelFile:
    """Require complete owner labels and exact pre-judge artifact bindings."""

    labels = (
        payload
        if isinstance(payload, CalibrationLabelFile)
        else CalibrationLabelFile.model_validate(payload)
    )
    if labels.pilot_artifact_sha256 != pilot_artifact_sha256:
        raise ValueError("calibration labels do not bind the supplied pilot artifact")
    if labels.decomposition_artifact_sha256 != decomposition_artifact_sha256:
        raise ValueError("calibration labels do not bind the decomposition artifact")

    generated, decomposed = _paired_pilot_items(generated_items, decomposed_items)
    rubrics = _calibration_rubrics(gold_items)
    expected_ids = [item.item_id for item in generated]
    if [rubric.item_id for rubric in rubrics] != expected_ids:
        raise ValueError("gold rubric order must match generated pilot item order")
    if [item.item_id for item in labels.items] != expected_ids:
        raise ValueError("calibration item order does not match generated pilot items")

    for item_label, generated_item, decomposed_item, rubric in zip(
        labels.items,
        generated,
        decomposed,
        rubrics,
        strict=True,
    ):
        _validate_decomposition_against_generated(generated_item, decomposed_item)
        if item_label.answer_sha256 != generated_item.answer_sha256:
            raise ValueError(f"{item_label.item_id}: answer hash binding changed")
        if item_label.decomposition_sha256 != decomposed_item.decomposition_sha256:
            raise ValueError(f"{item_label.item_id}: decomposition hash binding changed")
        if item_label.rubric_sha256 != rubric.rubric_sha256:
            raise ValueError(f"{item_label.item_id}: gold rubric hash binding changed")
        if item_label.response_behavior is None:
            raise ValueError(f"{item_label.item_id}: response_behavior is not labelled")
        if len(item_label.claims) != len(decomposed_item.claims):
            raise ValueError(f"{item_label.item_id}: claim count changed")

        for claim_label, claim in zip(item_label.claims, decomposed_item.claims, strict=True):
            if (
                claim_label.claim_id != claim.claim_id
                or claim_label.claim_text != claim.text
                or claim_label.claim_sha256 != claim.claim_sha256
            ):
                raise ValueError(
                    f"{item_label.item_id}: claim identity changed before judge calibration"
                )
            if claim_label.faithfulness is None:
                raise ValueError(f"{claim.claim_id}: faithfulness is not labelled")
            if claim_label.gold_match_ids is None:
                raise ValueError(f"{claim.claim_id}: gold_match_ids is not labelled")
            valid_gold_ids = {gold_claim.claim_id for gold_claim in rubric.gold_claims}
            if not set(claim_label.gold_match_ids) <= valid_gold_ids:
                raise ValueError(f"{claim.claim_id}: gold match is not in this item's rubric")
            if claim_label.cited_source_labels is None:
                raise ValueError(f"{claim.claim_id}: cited_source_labels is not labelled")
            if set(claim_label.cited_source_labels) != set(claim.cited_source_numbers):
                raise ValueError(
                    f"{claim.claim_id}: cited-source labels do not match cited sources"
                )

        if len(item_label.gold_claim_statuses) != len(rubric.gold_claims):
            raise ValueError(f"{item_label.item_id}: gold claim status count changed")
        for owner_status, gold_claim in zip(
            item_label.gold_claim_statuses,
            rubric.gold_claims,
            strict=True,
        ):
            if (
                owner_status.claim_id != gold_claim.claim_id
                or owner_status.claim_text != gold_claim.text
                or owner_status.claim_text_sha256 != sha256_text(gold_claim.text)
            ):
                raise ValueError(f"{item_label.item_id}: gold claim rubric identity changed")
            if owner_status.status is None:
                raise ValueError(f"{gold_claim.claim_id}: gold claim status is not labelled")

        if len(item_label.must_not_claim_statuses) != len(rubric.must_not_claims):
            raise ValueError(f"{item_label.item_id}: must-not-claim status count changed")
        for owner_status, (index, must_not_text) in zip(
            item_label.must_not_claim_statuses,
            enumerate(rubric.must_not_claims),
            strict=True,
        ):
            if (
                owner_status.index != index
                or owner_status.claim_text != must_not_text
                or owner_status.claim_text_sha256 != sha256_text(must_not_text)
            ):
                raise ValueError(f"{item_label.item_id}: must-not-claim rubric identity changed")
            if owner_status.status is None:
                raise ValueError(
                    f"{item_label.item_id}: must-not-claim status {index} is not labelled"
                )
    return labels


class JudgeEligibility(_ClosedModel):
    exact_agreement_minimum: Literal[JUDGE_EXACT_AGREEMENT_MINIMUM] = JUDGE_EXACT_AGREEMENT_MINIMUM
    repeat_agreement_minimum: Literal[JUDGE_REPEAT_AGREEMENT_MINIMUM] = (
        JUDGE_REPEAT_AGREEMENT_MINIMUM
    )
    pooled_agreement: UnitInterval
    repeat_agreement: UnitInterval
    eligible: bool = Field(strict=True)

    @model_validator(mode="after")
    def eligibility_matches_predeclared_thresholds(self) -> "JudgeEligibility":
        expected = (
            self.pooled_agreement >= JUDGE_EXACT_AGREEMENT_MINIMUM
            and self.repeat_agreement >= JUDGE_REPEAT_AGREEMENT_MINIMUM
        )
        if self.eligible != expected:
            raise ValueError("judge eligibility does not match predeclared thresholds")
        return self


class DimensionAgreement(_ClosedModel):
    dimension: ScoringDimension
    agreement: UnitInterval
    denominator: Annotated[int, Field(strict=True, ge=1)]
    scoring_mode: Literal[ScoringMode.JUDGE, ScoringMode.MANUAL]


class InstrumentLock(_ClosedModel):
    schema_version: Literal[INSTRUMENT_LOCK_SCHEMA] = Field(
        INSTRUMENT_LOCK_SCHEMA,
        alias="schema",
    )
    instrument_id: Identifier
    cohort_manifest_sha256: Sha256
    pilot_artifact_sha256: Sha256
    decomposition_artifact_sha256: Sha256
    human_labels_sha256: Sha256
    judge_results_sha256: Sha256
    judge_model: NonemptyString
    judge_settings: dict[str, JsonValue]
    decomposition_prompt_sha256: Sha256
    evidence_prompt_sha256: Sha256
    rubric_prompt_sha256: Sha256
    judge_eligibility: JudgeEligibility
    dimensions: tuple[DimensionAgreement, ...] = Field(min_length=6, max_length=6)
    scoring_mode: ScoringMode
    baseline_next_action: Literal[BASELINE_NEXT_ACTION] = BASELINE_NEXT_ACTION
    instrument_sha256: Sha256

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def dimension_fallbacks_and_hash_are_exact(self) -> "InstrumentLock":
        expected_dimensions = list(ScoringDimension)
        if [entry.dimension for entry in self.dimensions] != expected_dimensions:
            raise ValueError("instrument dimensions must appear exactly once in fixed order")
        denominator = sum(entry.denominator for entry in self.dimensions)
        weighted = (
            sum(entry.agreement * entry.denominator for entry in self.dimensions) / denominator
        )
        if not math.isclose(
            self.judge_eligibility.pooled_agreement,
            weighted,
            abs_tol=1e-12,
        ):
            raise ValueError("pooled agreement must equal dimension-weighted agreement")
        expected_dimension_modes = [
            (
                ScoringMode.JUDGE
                if self.judge_eligibility.repeat_agreement >= JUDGE_REPEAT_AGREEMENT_MINIMUM
                and entry.agreement >= JUDGE_EXACT_AGREEMENT_MINIMUM
                else ScoringMode.MANUAL
            )
            for entry in self.dimensions
        ]
        if [entry.scoring_mode for entry in self.dimensions] != expected_dimension_modes:
            raise ValueError("only affected scoring dimensions may fall back to manual")
        if all(mode is ScoringMode.JUDGE for mode in expected_dimension_modes):
            expected_mode = ScoringMode.JUDGE
        elif all(mode is ScoringMode.MANUAL for mode in expected_dimension_modes):
            expected_mode = ScoringMode.MANUAL
        else:
            expected_mode = ScoringMode.MIXED
        if self.scoring_mode is not expected_mode:
            raise ValueError("overall scoring_mode does not match dimension-level modes")
        payload = self.model_dump(mode="json", exclude={"instrument_sha256"})
        if self.instrument_sha256 != canonical_json_sha256(payload):
            raise ValueError("instrument_sha256 does not bind the exact scoring lock")
        return self


def build_instrument_lock(
    *,
    instrument_id: str,
    cohort_manifest_sha256: str,
    pilot_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    human_labels_sha256: str,
    judge_results_sha256: str,
    judge_model: str,
    judge_settings: Mapping[str, JsonValue],
    decomposition_prompt_sha256: str,
    evidence_prompt_sha256: str,
    rubric_prompt_sha256: str,
    pooled_agreement: float,
    repeat_agreement: float,
    dimension_agreements: Mapping[
        ScoringDimension | str,
        tuple[float, int] | Mapping[str, object],
    ],
) -> InstrumentLock:
    eligible = (
        pooled_agreement >= JUDGE_EXACT_AGREEMENT_MINIMUM
        and repeat_agreement >= JUDGE_REPEAT_AGREEMENT_MINIMUM
    )
    normalized_dimensions: list[DimensionAgreement] = []
    for dimension in ScoringDimension:
        raw_value = dimension_agreements.get(
            dimension,
            dimension_agreements.get(dimension.value),
        )
        if isinstance(raw_value, Mapping):
            agreement = raw_value.get("agreement")
            denominator = raw_value.get("denominator")
        elif isinstance(raw_value, tuple) and len(raw_value) == 2:
            agreement, denominator = raw_value
        else:
            raise ValueError(f"missing agreement for scoring dimension {dimension.value}")
        if not isinstance(agreement, (int, float)) or isinstance(agreement, bool):
            raise ValueError(f"{dimension.value} agreement must be numeric")
        if not isinstance(denominator, int) or isinstance(denominator, bool):
            raise ValueError(f"{dimension.value} denominator must be an integer")
        dimension_mode = (
            ScoringMode.JUDGE
            if repeat_agreement >= JUDGE_REPEAT_AGREEMENT_MINIMUM
            and float(agreement) >= JUDGE_EXACT_AGREEMENT_MINIMUM
            else ScoringMode.MANUAL
        )
        normalized_dimensions.append(
            DimensionAgreement(
                dimension=dimension,
                agreement=float(agreement),
                denominator=denominator,
                scoring_mode=dimension_mode,
            )
        )
    modes = [entry.scoring_mode for entry in normalized_dimensions]
    if all(mode is ScoringMode.JUDGE for mode in modes):
        overall_mode = ScoringMode.JUDGE
    elif all(mode is ScoringMode.MANUAL for mode in modes):
        overall_mode = ScoringMode.MANUAL
    else:
        overall_mode = ScoringMode.MIXED
    normalized_settings = json.loads(canonical_json_bytes(dict(judge_settings)))
    raw: dict[str, object] = {
        "schema": INSTRUMENT_LOCK_SCHEMA,
        "instrument_id": instrument_id,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "pilot_artifact_sha256": pilot_artifact_sha256,
        "decomposition_artifact_sha256": decomposition_artifact_sha256,
        "human_labels_sha256": human_labels_sha256,
        "judge_results_sha256": judge_results_sha256,
        "judge_model": judge_model,
        "judge_settings": normalized_settings,
        "decomposition_prompt_sha256": decomposition_prompt_sha256,
        "evidence_prompt_sha256": evidence_prompt_sha256,
        "rubric_prompt_sha256": rubric_prompt_sha256,
        "judge_eligibility": {
            "exact_agreement_minimum": JUDGE_EXACT_AGREEMENT_MINIMUM,
            "repeat_agreement_minimum": JUDGE_REPEAT_AGREEMENT_MINIMUM,
            "pooled_agreement": pooled_agreement,
            "repeat_agreement": repeat_agreement,
            "eligible": eligible,
        },
        "dimensions": [entry.model_dump(mode="json") for entry in normalized_dimensions],
        "scoring_mode": overall_mode,
        "baseline_next_action": BASELINE_NEXT_ACTION,
    }
    raw["instrument_sha256"] = canonical_json_sha256(raw)
    return InstrumentLock.model_validate(raw)


class PublicMetric(_ClosedModel):
    metric_id: PublicMetricId
    availability: MetricAvailability
    numerator: NonnegativeInt | None
    denominator: NonnegativeInt
    value: UnitInterval | None

    @model_validator(mode="after")
    def ratio_or_pending_state_is_exact(self) -> "PublicMetric":
        if self.availability is MetricAvailability.PENDING:
            if self.denominator < 1:
                raise ValueError("pending metric must retain its real positive denominator")
            if self.numerator is not None or self.value is not None:
                raise ValueError("pending metric must have null numerator and value")
            return self
        if self.numerator is None:
            raise ValueError("available metric must have a numerator")
        if self.numerator > self.denominator:
            raise ValueError("metric numerator cannot exceed denominator")
        if self.denominator == 0:
            if self.numerator != 0 or self.value is not None:
                raise ValueError("zero-denominator metric must be 0/0 with null value")
            return self
        expected = self.numerator / self.denominator
        if self.value is None or not math.isclose(self.value, expected, abs_tol=1e-12):
            raise ValueError("metric value must equal numerator divided by denominator")
        return self


class PrecalibrationPublicMetric(_ClosedModel):
    """One closed result whose unavailable semantic value remains explicit."""

    metric_id: PrecalibrationMetricId
    availability: MetricAvailability
    numerator: NonnegativeInt | None
    denominator: NonnegativeInt
    value: UnitInterval | None

    @model_validator(mode="after")
    def ratio_or_pending_state_is_exact(self) -> "PrecalibrationPublicMetric":
        if self.availability is MetricAvailability.PENDING:
            if self.denominator < 1:
                raise ValueError("pending metric must retain its real positive denominator")
            if self.numerator is not None or self.value is not None:
                raise ValueError("pending metric must have null numerator and value")
            return self
        if self.numerator is None:
            raise ValueError("available metric must have a numerator")
        if self.numerator > self.denominator:
            raise ValueError("metric numerator cannot exceed denominator")
        if self.denominator == 0:
            if self.numerator != 0 or self.value is not None:
                raise ValueError("zero-denominator metric must be 0/0 with null value")
            return self
        expected = self.numerator / self.denominator
        if self.value is None or not math.isclose(self.value, expected, abs_tol=1e-12):
            raise ValueError("metric value must equal numerator divided by denominator")
        return self


class PublicCost(_ClosedModel):
    estimated_cost_usd: NonnegativeFloat | None
    priced_event_count: NonnegativeInt
    unpriced_event_count: NonnegativeInt


class PublicLatency(_ClosedModel):
    total_seconds: NonnegativeFloat
    mean_seconds: NonnegativeFloat
    p50_seconds: NonnegativeFloat
    p95_seconds: NonnegativeFloat
    maximum_seconds: NonnegativeFloat

    @model_validator(mode="after")
    def percentiles_are_ordered(self) -> "PublicLatency":
        if not (
            self.p50_seconds <= self.p95_seconds <= self.maximum_seconds
            and self.mean_seconds <= self.maximum_seconds
            and self.maximum_seconds <= self.total_seconds
        ):
            raise ValueError("public latency aggregates are inconsistent")
        return self


class PublicStratumSummary(_ClosedModel):
    stratum: EvaluationStratum
    item_count: NonnegativeInt
    metrics: tuple[PublicMetric, ...]

    @model_validator(mode="after")
    def metric_ids_are_unique(self) -> "PublicStratumSummary":
        _require_unique([metric.metric_id for metric in self.metrics], label="stratum metric IDs")
        return self


class PublicEvaluationSummary(_ClosedModel):
    schema_version: Literal[PUBLIC_SUMMARY_SCHEMA] = Field(
        PUBLIC_SUMMARY_SCHEMA,
        alias="schema",
    )
    evaluation_id: Identifier
    candidate_id: Identifier
    candidate_commit: GitCommit
    rag_policy: Identifier
    cohort_manifest_sha256: Sha256
    corpus_manifest_sha256: Sha256
    chunks_sha256: Sha256
    question_set_sha256: Sha256
    model_catalog_sha256: Sha256
    runner_sha256: Sha256
    planner_model_id: NonemptyString
    generator_model_id: NonemptyString
    judge_model_id: NonemptyString
    embedding_model_id: NonemptyString
    private_artifact_sha256: Sha256
    instrument_lock_sha256: Sha256
    gold_set_sha256: Sha256
    limitation_ids: tuple[PublicLimitationId, ...]
    run_status: BaselineRunStatus
    scoring_mode: ScoringMode
    item_count: NonnegativeInt
    source_count: NonnegativeInt
    claim_count: NonnegativeInt
    citation_count: NonnegativeInt
    error_count: NonnegativeInt
    metrics: tuple[PublicMetric, ...]
    strata: tuple[PublicStratumSummary, ...]
    cost: PublicCost
    latency: PublicLatency

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def aggregate_ids_and_counts_are_coherent(self) -> "PublicEvaluationSummary":
        metric_ids = [metric.metric_id for metric in self.metrics]
        _require_unique(metric_ids, label="summary metric IDs")
        _require_unique([entry.stratum for entry in self.strata], label="summary strata")
        _require_unique(self.limitation_ids, label="public limitation IDs")
        required_limitations = {
            PublicLimitationId.CANONICAL_MODEL_ID_MUTABILITY,
            PublicLimitationId.GENERATOR_SPREAD_UNMEASURED,
            PublicLimitationId.DESCRIPTIVE_NOT_GATE,
        }
        if not required_limitations <= set(self.limitation_ids):
            raise ValueError("public summary is missing a fixed evaluation limitation")
        if sum(entry.item_count for entry in self.strata) != self.item_count:
            raise ValueError("stratum item counts must sum to item_count")
        if self.error_count > self.item_count:
            raise ValueError("error_count cannot exceed item_count")
        if self.run_status is BaselineRunStatus.COMPLETE:
            if self.item_count != 37:
                raise ValueError("complete evaluation must contain exactly 37 items")
            expected_strata = {
                EvaluationStratum.FOCUSED_BIOGRAPHICAL: 8,
                EvaluationStratum.FOCUSED_ANALYTICAL: 8,
                EvaluationStratum.CONCEPTUAL: 5,
                EvaluationStratum.BROAD_THEMATIC: 10,
                EvaluationStratum.OUT_OF_CORPUS: 4,
                EvaluationStratum.ADVERSARIAL_PREMISE: 2,
            }
            actual_strata = {entry.stratum: entry.item_count for entry in self.strata}
            if actual_strata != expected_strata:
                raise ValueError("complete evaluation stratum counts must be exactly 8/8/5/10/4/2")
            if set(metric_ids) != set(PublicMetricId):
                raise ValueError(
                    "complete evaluation must include every required metric exactly once"
                )
        return self


class PrecalibrationPublicStratumSummary(_ClosedModel):
    stratum: EvaluationStratum
    item_count: NonnegativeInt
    metrics: tuple[PrecalibrationPublicMetric, ...]

    @model_validator(mode="after")
    def metric_ids_are_unique(self) -> "PrecalibrationPublicStratumSummary":
        _require_unique(
            [metric.metric_id for metric in self.metrics],
            label="precalibration stratum metric IDs",
        )
        return self


class PublicPrecalibrationSummary(_ClosedModel):
    """Text-free first result emitted before semantic calibration or judging."""

    schema_version: Literal[PRECALIBRATION_PUBLIC_SUMMARY_SCHEMA] = Field(
        PRECALIBRATION_PUBLIC_SUMMARY_SCHEMA,
        alias="schema",
    )
    evaluation_id: Identifier
    candidate_id: Identifier
    candidate_commit: GitCommit
    rag_policy: Identifier
    cohort_manifest_sha256: Sha256
    corpus_manifest_sha256: Sha256
    chunks_sha256: Sha256
    question_set_sha256: Sha256
    model_catalog_sha256: Sha256
    runner_sha256: Sha256
    planner_model_id: NonemptyString
    generator_model_id: NonemptyString
    decomposer_model_id: NonemptyString
    embedding_model_id: NonemptyString
    private_artifact_sha256: Sha256
    generation_artifact_sha256: Sha256
    decomposition_artifact_sha256: Sha256
    gold_set_sha256: Sha256
    migration_artifact_sha256: Sha256 | None
    recovered_item_count: Literal[0, 1]
    limitation_ids: tuple[PublicLimitationId, ...]
    run_status: BaselineRunStatus
    latency_scope: Literal["generation_pipeline"] = "generation_pipeline"
    generation_latency_denominator: NonnegativeInt
    generation_latency_observed_count: NonnegativeInt
    item_count: NonnegativeInt
    source_count: NonnegativeInt
    claim_count: NonnegativeInt
    citation_count: NonnegativeInt
    completed_answer_count: NonnegativeInt
    technical_error_count: NonnegativeInt
    metrics: tuple[PrecalibrationPublicMetric, ...]
    strata: tuple[PrecalibrationPublicStratumSummary, ...]
    cost: PublicCost
    latency: PublicLatency

    @property
    def schema(self) -> str:
        return self.schema_version

    @model_validator(mode="after")
    def aggregate_ids_and_counts_are_coherent(self) -> "PublicPrecalibrationSummary":
        metric_ids = [metric.metric_id for metric in self.metrics]
        _require_unique(metric_ids, label="precalibration summary metric IDs")
        _require_unique(
            [entry.stratum for entry in self.strata],
            label="precalibration summary strata",
        )
        _require_unique(self.limitation_ids, label="precalibration limitation IDs")
        required_limitations = {
            PublicLimitationId.CANONICAL_MODEL_ID_MUTABILITY,
            PublicLimitationId.GENERATOR_SPREAD_UNMEASURED,
            PublicLimitationId.DESCRIPTIVE_NOT_GATE,
            PublicLimitationId.SEMANTIC_SCORING_PENDING,
        }
        if not required_limitations <= set(self.limitation_ids):
            raise ValueError("precalibration summary is missing a fixed limitation")
        recovery_limitation = PublicLimitationId.TRACE_RECOVERED_ITEM_PRESENT
        if self.recovered_item_count:
            if self.migration_artifact_sha256 is None:
                raise ValueError(
                    "trace-recovered precalibration summary requires a migration artifact"
                )
            if recovery_limitation not in self.limitation_ids:
                raise ValueError("trace-recovered precalibration summary is missing its limitation")
        elif self.migration_artifact_sha256 is not None:
            raise ValueError("ordinary precalibration summary cannot bind a migration artifact")
        elif recovery_limitation in self.limitation_ids:
            raise ValueError("ordinary precalibration summary cannot claim a recovered item")
        if self.generation_latency_denominator != self.item_count:
            raise ValueError("generation latency denominator must equal item_count")
        if self.generation_latency_observed_count != (self.item_count - self.recovered_item_count):
            raise ValueError("generation latency observations must exclude each recovered item")
        if sum(entry.item_count for entry in self.strata) != self.item_count:
            raise ValueError("precalibration stratum counts must sum to item_count")
        if self.completed_answer_count + self.technical_error_count != self.item_count:
            raise ValueError("completion and technical-error counts must cover every item")
        mechanical_ids = {
            PrecalibrationMetricId.CITATION_RESOLVABILITY,
            PrecalibrationMetricId.CITATION_COMPLETENESS,
            PrecalibrationMetricId.MALFORMED_CITATION_RATE,
            PrecalibrationMetricId.CITED_SOURCE_GOLD_LOCATION_MATCH,
            PrecalibrationMetricId.GOLD_LOCATION_RETRIEVAL_COVERAGE,
        }
        for metric in (
            *self.metrics,
            *(metric for stratum in self.strata for metric in stratum.metrics),
        ):
            if metric.metric_id in mechanical_ids:
                if metric.availability is not MetricAvailability.AVAILABLE:
                    raise ValueError("mechanical precalibration metrics must be available")
            elif metric.denominator > 0 and metric.availability is not MetricAvailability.PENDING:
                raise ValueError("semantic precalibration metrics must remain pending")
        if self.run_status is BaselineRunStatus.COMPLETE:
            if self.item_count != 37:
                raise ValueError("complete precalibration result must contain exactly 37 items")
            expected_strata = {
                EvaluationStratum.FOCUSED_BIOGRAPHICAL: 8,
                EvaluationStratum.FOCUSED_ANALYTICAL: 8,
                EvaluationStratum.CONCEPTUAL: 5,
                EvaluationStratum.BROAD_THEMATIC: 10,
                EvaluationStratum.OUT_OF_CORPUS: 4,
                EvaluationStratum.ADVERSARIAL_PREMISE: 2,
            }
            actual_strata = {entry.stratum: entry.item_count for entry in self.strata}
            if actual_strata != expected_strata:
                raise ValueError("complete precalibration strata must be exactly 8/8/5/10/4/2")
            if set(metric_ids) != set(PrecalibrationMetricId):
                raise ValueError(
                    "complete precalibration result must include every metric exactly once"
                )
            if any(
                set(metric.metric_id for metric in stratum.metrics) != set(PrecalibrationMetricId)
                for stratum in self.strata
            ):
                raise ValueError(
                    "complete precalibration strata must include every metric exactly once"
                )
        return self


def validate_public_summary(
    payload: PublicEvaluationSummary | Mapping[str, object],
) -> PublicEvaluationSummary:
    """Validate the closed, text-free public boundary.

    Every nested object is a ``_ClosedModel`` and the schema contains no
    arbitrary mapping or prose-bearing field.  Consequently unknown nested
    fields, questions, answers, source text, notes, and diagnostics all fail.
    """

    if isinstance(payload, PublicEvaluationSummary):
        return payload
    return PublicEvaluationSummary.model_validate(payload)


def validate_public_precalibration_summary(
    payload: PublicPrecalibrationSummary | Mapping[str, object],
) -> PublicPrecalibrationSummary:
    """Validate the closed public boundary available before semantic scoring."""

    if isinstance(payload, PublicPrecalibrationSummary):
        return payload
    return PublicPrecalibrationSummary.model_validate(payload)


def _calibration_rubrics(
    gold_items: Sequence[Mapping[str, object]],
) -> tuple[CalibrationRubric, ...]:
    if not gold_items:
        raise ValueError("calibration requires at least one gold rubric")
    rubrics: list[CalibrationRubric] = []
    for item in gold_items:
        item_id = item.get("id")
        claims_value = item.get("claims")
        must_not_value = item.get("must_not_claim")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("gold rubric item is missing a nonempty id")
        if not isinstance(claims_value, Sequence) or isinstance(
            claims_value,
            (str, bytes),
        ):
            raise ValueError(f"{item_id}: gold rubric claims must be an ordered array")
        if not isinstance(must_not_value, Sequence) or isinstance(
            must_not_value,
            (str, bytes),
        ):
            raise ValueError(f"{item_id}: must_not_claim must be an ordered array")

        gold_claims: list[dict[str, str]] = []
        for claim in claims_value:
            if not isinstance(claim, Mapping):
                raise ValueError(f"{item_id}: gold rubric claim must be an object")
            claim_id = claim.get("claim_id")
            text = claim.get("text")
            if not isinstance(claim_id, str) or not claim_id:
                raise ValueError(f"{item_id}: gold rubric claim is missing claim_id")
            if not isinstance(text, str) or not text:
                raise ValueError(f"{claim_id}: gold rubric claim is missing text")
            gold_claims.append({"claim_id": claim_id, "text": text})

        must_not_claims: list[str] = []
        for text in must_not_value:
            if not isinstance(text, str) or not text:
                raise ValueError(f"{item_id}: must-not-claim text must be nonempty")
            must_not_claims.append(text)

        raw: dict[str, object] = {
            "item_id": item_id,
            "gold_claims": gold_claims,
            "must_not_claims": must_not_claims,
        }
        raw["rubric_sha256"] = canonical_json_sha256(raw)
        rubrics.append(CalibrationRubric.model_validate(raw))
    _require_unique([rubric.item_id for rubric in rubrics], label="gold rubric item IDs")
    return tuple(rubrics)


def _paired_pilot_items(
    generated_items: Sequence[PrivateGeneratedItem | Mapping[str, object]],
    decomposed_items: Sequence[DecomposedPilotItem | Mapping[str, object]],
) -> tuple[tuple[PrivateGeneratedItem, ...], tuple[DecomposedPilotItem, ...]]:
    generated = tuple(
        item
        if isinstance(item, PrivateGeneratedItem)
        else PrivateGeneratedItem.model_validate(item)
        for item in generated_items
    )
    decomposed = tuple(
        item if isinstance(item, DecomposedPilotItem) else DecomposedPilotItem.model_validate(item)
        for item in decomposed_items
    )
    if not generated or len(generated) != len(decomposed):
        raise ValueError("generated and decomposed pilot items must be nonempty and paired")
    generated_ids = [item.item_id for item in generated]
    decomposed_ids = [item.item_id for item in decomposed]
    _require_unique(generated_ids, label="generated pilot item IDs")
    _require_unique(decomposed_ids, label="decomposed pilot item IDs")
    if generated_ids != decomposed_ids:
        raise ValueError("decomposed pilot item order must match generated pilot item order")
    return generated, decomposed


def _validate_decomposition_against_generated(
    generated: PrivateGeneratedItem,
    decomposed: DecomposedPilotItem,
) -> None:
    if decomposed.answer_sha256 != generated.answer_sha256:
        raise ValueError(f"{generated.item_id}: decomposition is bound to another answer")
    valid_sources = {source.source_number for source in generated.sources}
    for claim in decomposed.claims:
        if claim.char_end > len(generated.answer):
            raise ValueError(f"{claim.claim_id}: claim span exceeds answer length")
        if generated.answer[claim.char_start : claim.char_end] != claim.text:
            raise ValueError(f"{claim.claim_id}: claim text does not match answer span")
        if not set(claim.cited_source_numbers) <= valid_sources:
            raise ValueError(f"{claim.claim_id}: claim cites a source not supplied to generator")


def _require_dense_sequence(values: Sequence[int], *, label: str) -> None:
    if list(values) != list(range(1, len(values) + 1)):
        raise ValueError(f"{label} must be exactly ordered 1..N")


def _require_unique(values: Sequence[Any], *, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
