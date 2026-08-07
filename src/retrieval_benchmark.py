"""Text-free, retrieval-only evaluation for the locked Archivist gold set.

The module deliberately separates the one paid query-embedding operation from
local scoring.  A cache created once can be reused by both retrieval arms and
every noise-floor repetition without another provider request.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from costs import tracked_embeddings_create
from filters import should_skip_document
from gold_provenance import gold_question_set_sha256, normalized_question_sha256
from retrieval import (
    MAX_FINAL_SOURCES,
    MAX_PRIMARY_DISTANCE,
    SEMANTIC_CANDIDATE_LIMIT,
    build_hybrid_results,
    finalize_context_chunks,
)


EMBEDDING_CACHE_SCHEMA = "archivist.retrieval_query_embeddings/1"
BENCHMARK_SCHEMA = "archivist.retrieval_benchmark/1"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_PRICE_PER_MILLION_TOKENS_USD = 0.02
PROVIDER_BATCH_TOKEN_LIMIT = 300_000
PROVIDER_BATCH_WORST_CASE_USD = (
    PROVIDER_BATCH_TOKEN_LIMIT / 1_000_000 * EMBEDDING_PRICE_PER_MILLION_TOKENS_USD
)

K_VALUES = (1, 3, 5, 8, 10, 20)
CONTEXT_N_RESULTS = 5
NOISE_REPEATS = 5
PRIMARY_COMPARISON_METRIC = "macro_recall_at_5"
NOISE_SUBSET_STRATUM_COUNTS = {
    "focused_biographical": 2,
    "focused_analytical": 2,
    "conceptual": 1,
    "broad_thematic": 2,
    "out_of_corpus": 2,
    "adversarial_premise": 1,
}

_FORBIDDEN_PERSISTED_KEYS = frozenset(
    {
        "answer",
        "chunk",
        "document_text",
        "manuscript_text",
        "prompt",
        "question",
        "source_text",
        "text",
    }
)


class RetrievalBenchmarkError(ValueError):
    """Raised when a benchmark input or artifact violates the locked protocol."""


@dataclass(frozen=True, slots=True)
class LockedGold:
    raw: Mapping[str, object]
    items: tuple[Mapping[str, object], ...]
    gold_set_sha256: str
    question_set_sha256: str
    candidate_commit: str
    candidate_rag_policy: str
    corpus_manifest_sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RetrievalBenchmarkError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RetrievalBenchmarkError(f"{label} must be a JSON object")
    return value


def load_locked_gold(gold_path: Path, provenance_path: Path) -> LockedGold:
    """Load the already-validated gold/provenance pair without exposing its text."""

    gold = _load_json_object(gold_path, label="gold set")
    provenance = _load_json_object(provenance_path, label="gold provenance")
    raw_items = gold.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise RetrievalBenchmarkError("gold set must contain a non-empty items array")
    if not all(isinstance(item, Mapping) for item in raw_items):
        raise RetrievalBenchmarkError("every gold item must be an object")

    gold_hash = sha256_file(gold_path)
    question_hash = gold_question_set_sha256(gold)
    bindings = {
        "gold_set_sha256": gold_hash,
        "question_set_sha256": question_hash,
    }
    for field, expected in bindings.items():
        if provenance.get(field) != expected:
            raise RetrievalBenchmarkError(
                f"gold provenance {field} does not match the locked artifact"
            )

    required = {
        "candidate_commit": provenance.get("candidate_commit"),
        "candidate_rag_policy": provenance.get("candidate_rag_policy"),
        "corpus_manifest_sha256": provenance.get("corpus_manifest_sha256"),
    }
    if any(not isinstance(value, str) or not value for value in required.values()):
        raise RetrievalBenchmarkError("gold provenance is missing frozen run bindings")

    return LockedGold(
        raw=gold,
        items=tuple(raw_items),
        gold_set_sha256=gold_hash,
        question_set_sha256=question_hash,
        candidate_commit=str(required["candidate_commit"]),
        candidate_rag_policy=str(required["candidate_rag_policy"]),
        corpus_manifest_sha256=str(required["corpus_manifest_sha256"]),
    )


def embedding_preflight_summary(gold: LockedGold) -> dict[str, object]:
    questions = [_required_string(item, "question") for item in gold.items]
    return {
        "provider": "OpenAI",
        "model": EMBEDDING_MODEL,
        "operation_count": 1,
        "question_count": len(questions),
        "total_question_characters": sum(len(question) for question in questions),
        "maximum_question_characters": max(len(question) for question in questions),
        "provider_batch_token_limit": PROVIDER_BATCH_TOKEN_LIMIT,
        "provider_batch_worst_case_usd": PROVIDER_BATCH_WORST_CASE_USD,
        "gold_set_sha256": gold.gold_set_sha256,
        "question_set_sha256": gold.question_set_sha256,
    }


def request_query_embedding_cache(
    gold: LockedGold,
    *,
    embedding_client: object,
    request: Callable[..., object] = tracked_embeddings_create,
) -> dict[str, object]:
    """Send exactly the locked questions in one non-retried embedding operation."""

    questions = [_required_string(item, "question") for item in gold.items]
    response = request(
        embedding_client,
        operation="held_out_retrieval_query_embedding",
        model=EMBEDDING_MODEL,
        input=questions,
    )
    raw_data = getattr(response, "data", None)
    if not isinstance(raw_data, Sequence) or len(raw_data) != len(questions):
        raise RetrievalBenchmarkError(
            "embedding response count does not match the locked question count"
        )

    indexed_response: dict[int, object] = {}
    for response_item in raw_data:
        index = getattr(response_item, "index", None)
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or index < 0
            or index >= len(questions)
            or index in indexed_response
        ):
            raise RetrievalBenchmarkError(
                "embedding response contains invalid or duplicate input indices"
            )
        indexed_response[index] = response_item
    if set(indexed_response) != set(range(len(questions))):
        raise RetrievalBenchmarkError(
            "embedding response indices do not cover every locked question"
        )

    entries: list[dict[str, object]] = []
    dimensions: set[int] = set()
    for index, item in enumerate(gold.items):
        response_item = indexed_response[index]
        raw_embedding = getattr(response_item, "embedding", None)
        if not isinstance(raw_embedding, Sequence) or isinstance(raw_embedding, (str, bytes)):
            raise RetrievalBenchmarkError("embedding response item is missing its vector")
        embedding = [float(value) for value in raw_embedding]
        if not embedding or any(not math.isfinite(value) for value in embedding):
            raise RetrievalBenchmarkError("embedding response contains an invalid vector")
        dimensions.add(len(embedding))
        entries.append(
            {
                "id": _required_string(item, "id"),
                "question_sha256": normalized_question_sha256(
                    _required_string(item, "question")
                ),
                "embedding": embedding,
            }
        )
    if len(dimensions) != 1:
        raise RetrievalBenchmarkError("embedding response dimensions are inconsistent")

    usage = getattr(response, "usage", None)
    prompt_tokens = _optional_nonnegative_int(getattr(usage, "prompt_tokens", None))
    total_tokens = _optional_nonnegative_int(getattr(usage, "total_tokens", None))
    billed_tokens = prompt_tokens if prompt_tokens is not None else total_tokens
    estimated_cost = (
        billed_tokens / 1_000_000 * EMBEDDING_PRICE_PER_MILLION_TOKENS_USD
        if billed_tokens is not None
        else None
    )
    cache = {
        "schema": EMBEDDING_CACHE_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "provider": "OpenAI",
        "model": EMBEDDING_MODEL,
        "operation_count": 1,
        "automatic_retries": 0,
        "gold_set_sha256": gold.gold_set_sha256,
        "question_set_sha256": gold.question_set_sha256,
        "question_count": len(entries),
        "embedding_dimensions": dimensions.pop(),
        "usage": {
            "prompt_tokens": prompt_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": estimated_cost,
            "price_per_million_tokens_usd": EMBEDDING_PRICE_PER_MILLION_TOKENS_USD,
        },
        "items": entries,
    }
    validate_embedding_cache(cache, gold)
    return cache


def validate_embedding_cache(
    cache: Mapping[str, object],
    gold: LockedGold,
) -> dict[str, list[float]]:
    if cache.get("schema") != EMBEDDING_CACHE_SCHEMA:
        raise RetrievalBenchmarkError("embedding cache schema is missing or unsupported")
    for field, expected in (
        ("provider", "OpenAI"),
        ("model", EMBEDDING_MODEL),
        ("gold_set_sha256", gold.gold_set_sha256),
        ("question_set_sha256", gold.question_set_sha256),
        ("question_count", len(gold.items)),
        ("operation_count", 1),
        ("automatic_retries", 0),
    ):
        if cache.get(field) != expected:
            raise RetrievalBenchmarkError(f"embedding cache {field} does not match")

    raw_items = cache.get("items")
    if not isinstance(raw_items, list) or len(raw_items) != len(gold.items):
        raise RetrievalBenchmarkError("embedding cache items do not match the gold set")
    expected_dimensions = cache.get("embedding_dimensions")
    if not isinstance(expected_dimensions, int) or expected_dimensions <= 0:
        raise RetrievalBenchmarkError("embedding cache has invalid dimensions")

    embeddings: dict[str, list[float]] = {}
    for gold_item, cache_item in zip(gold.items, raw_items, strict=True):
        if not isinstance(cache_item, Mapping):
            raise RetrievalBenchmarkError("embedding cache item must be an object")
        item_id = _required_string(gold_item, "id")
        question = _required_string(gold_item, "question")
        if cache_item.get("id") != item_id:
            raise RetrievalBenchmarkError("embedding cache item order or ID changed")
        if cache_item.get("question_sha256") != normalized_question_sha256(question):
            raise RetrievalBenchmarkError(
                f"embedding cache question binding changed for {item_id}"
            )
        raw_embedding = cache_item.get("embedding")
        if not isinstance(raw_embedding, list) or len(raw_embedding) != expected_dimensions:
            raise RetrievalBenchmarkError(
                f"embedding cache vector dimensions changed for {item_id}"
            )
        embedding = [float(value) for value in raw_embedding]
        if any(not math.isfinite(value) for value in embedding):
            raise RetrievalBenchmarkError(
                f"embedding cache vector contains an invalid value for {item_id}"
            )
        embeddings[item_id] = embedding
    return embeddings


def write_json_atomic(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _first_batch(results: Mapping[str, object], key: str) -> list[object]:
    raw = results.get(key)
    if not isinstance(raw, list) or not raw:
        return []
    first = raw[0]
    return list(first) if isinstance(first, list) else []


def _slice_semantic_results(
    semantic_results: Mapping[str, object],
    limit: int,
) -> dict[str, object]:
    result = deepcopy(dict(semantic_results))
    for key in ("ids", "metadatas", "distances"):
        result[key] = [_first_batch(semantic_results, key)[:limit]]
    result.pop("hybrid", None)
    return result


def _hybrid_primary_ids(results: Mapping[str, object]) -> list[str]:
    hybrid = results.get("hybrid")
    if not isinstance(hybrid, Mapping):
        raise RetrievalBenchmarkError("hybrid retrieval result is missing")
    raw_ids = hybrid.get("primary_chunk_ids")
    if not isinstance(raw_ids, list):
        raise RetrievalBenchmarkError("hybrid primary IDs are malformed")
    return [str(value) for value in raw_ids]


def _chunk_ids(chunks: Sequence[Mapping[str, object]]) -> list[str]:
    return [_required_string(chunk, "chunk_id") for chunk in chunks]


def _score_set(item: Mapping[str, object], retrieved_ids: Sequence[str]) -> dict[str, object]:
    relevant = _string_set(item.get("relevant_chunk_ids"), field="relevant_chunk_ids")
    retrieved = set(retrieved_ids)
    intersection_count = len(relevant & retrieved)
    recall = intersection_count / len(relevant) if relevant else None
    hit = bool(intersection_count) if relevant else None

    raw_claims = item.get("claims")
    if not isinstance(raw_claims, list):
        raise RetrievalBenchmarkError("gold item claims must be an array")
    essential_claims = [
        claim
        for claim in raw_claims
        if isinstance(claim, Mapping) and claim.get("essential") is True
    ]
    covered = 0
    for claim in essential_claims:
        supporting = _string_set(
            claim.get("supporting_chunk_ids"),
            field="supporting_chunk_ids",
        )
        covered += int(bool(supporting & retrieved))
    essential_coverage = (
        covered / len(essential_claims) if relevant and essential_claims else None
    )
    return {
        "recall": recall,
        "hit": hit,
        "relevant_count": len(relevant),
        "retrieved_relevant_count": intersection_count,
        "essential_coverage": essential_coverage,
        "essential_claim_count": len(essential_claims),
        "covered_essential_claim_count": covered,
    }


def _dense_fallback_used(results: Mapping[str, object]) -> bool:
    metadatas = _first_batch(results, "metadatas")
    distances = _first_batch(results, "distances")
    eligible_distances = [
        float(distance)
        for metadata, distance in zip(metadatas, distances, strict=True)
        if isinstance(metadata, Mapping)
        and not should_skip_document(str(metadata.get("document") or ""))
    ]
    return bool(
        eligible_distances
        and not any(distance <= MAX_PRIMARY_DISTANCE for distance in eligible_distances)
    )


def _dense_displacement(
    results: Mapping[str, object],
    context_ids: Sequence[str],
) -> dict[str, int]:
    context = set(context_ids)
    metadatas = _first_batch(results, "metadatas")
    distances = _first_batch(results, "distances")
    eligible_within = any(
        isinstance(metadata, Mapping)
        and not should_skip_document(str(metadata.get("document") or ""))
        and float(distance) <= MAX_PRIMARY_DISTANCE
        for metadata, distance in zip(metadatas, distances, strict=True)
    )
    causes = Counter(
        {
            "distance_filtering": 0,
            "document_filtering": 0,
            "truncation": 0,
        }
    )
    for metadata, distance in zip(metadatas, distances, strict=True):
        if not isinstance(metadata, Mapping):
            continue
        chunk_id = str(metadata.get("chunk_id") or "")
        if not chunk_id or chunk_id in context:
            continue
        if should_skip_document(str(metadata.get("document") or "")):
            causes["document_filtering"] += 1
        elif eligible_within and float(distance) > MAX_PRIMARY_DISTANCE:
            causes["distance_filtering"] += 1
        else:
            causes["truncation"] += 1
    return dict(causes)


def _hybrid_fallback_used(results: Mapping[str, object]) -> bool:
    hybrid = results.get("hybrid")
    trace = hybrid.get("trace") if isinstance(hybrid, Mapping) else None
    selection = trace.get("selection") if isinstance(trace, Mapping) else None
    return bool(
        selection.get("raw_primary_fallback_used")
        if isinstance(selection, Mapping)
        else False
    )


def _hybrid_displacement(
    primary_ids: Sequence[str],
    context_ids: Sequence[str],
) -> dict[str, int]:
    context = set(context_ids)
    return {
        "distance_filtering": 0,
        "document_filtering": 0,
        "truncation": sum(1 for chunk_id in primary_ids if chunk_id not in context),
    }


def evaluate_item(
    item: Mapping[str, object],
    embedding: Sequence[float],
    *,
    collection: object,
    chunks: list[dict[str, Any]],
    corpus_trace: Mapping[str, object],
) -> dict[str, object]:
    """Query the local index once and score dense and hybrid arms text-free."""

    query_method = getattr(collection, "query", None)
    count_method = getattr(collection, "count", None)
    if not callable(query_method) or not callable(count_method):
        raise RetrievalBenchmarkError("collection must expose count() and query()")
    candidate_count = min(int(count_method()), max(K_VALUES, default=1))
    if candidate_count <= 0:
        raise RetrievalBenchmarkError("retrieval collection is empty")
    semantic_results = query_method(
        query_embeddings=[list(embedding)],
        n_results=candidate_count,
        include=["metadatas", "distances"],
    )
    if not isinstance(semantic_results, Mapping):
        raise RetrievalBenchmarkError("collection query returned a malformed result")

    query = _required_string(item, "question")
    dense_primary: dict[str, list[str]] = {}
    hybrid_primary: dict[str, list[str]] = {}
    hybrid_results_by_k: dict[int, Mapping[str, object]] = {}
    raw_dense_ids = [str(value) for value in _first_batch(semantic_results, "ids")]
    for k in K_VALUES:
        bounded = min(k, candidate_count)
        dense_primary[str(k)] = raw_dense_ids[:bounded]
        hybrid_results = build_hybrid_results(
            query,
            semantic_results,
            chunks,
            n_results=bounded,
            corpus=corpus_trace,
        )
        hybrid_results_by_k[k] = hybrid_results
        hybrid_primary[str(k)] = _hybrid_primary_ids(hybrid_results)

    dense_context_input = _slice_semantic_results(
        semantic_results,
        min(CONTEXT_N_RESULTS, candidate_count),
    )
    dense_context = finalize_context_chunks(
        dense_context_input,
        chunks=chunks,
        max_primary_distance=MAX_PRIMARY_DISTANCE,
        max_final_sources=MAX_FINAL_SOURCES,
    )
    hybrid_context_input = hybrid_results_by_k[CONTEXT_N_RESULTS]
    hybrid_context = finalize_context_chunks(
        hybrid_context_input,
        chunks=chunks,
        max_primary_distance=MAX_PRIMARY_DISTANCE,
        max_final_sources=MAX_FINAL_SOURCES,
    )
    dense_context_ids = _chunk_ids(dense_context)
    hybrid_context_ids = _chunk_ids(hybrid_context)

    return {
        "id": _required_string(item, "id"),
        "question_sha256": normalized_question_sha256(query),
        "stratum": _required_string(item, "stratum"),
        "expected_behavior": _required_string(item, "expected_behavior"),
        "arms": {
            "dense": {
                "primary_ids_by_k": dense_primary,
                "context_ids": dense_context_ids,
                "metrics_by_k": {
                    str(k): _score_set(item, dense_primary[str(k)]) for k in K_VALUES
                },
                "context_metrics": _score_set(item, dense_context_ids),
                "fallback_used": _dense_fallback_used(dense_context_input),
                "expansion_displacement": _dense_displacement(
                    dense_context_input,
                    dense_context_ids,
                ),
            },
            "hybrid": {
                "primary_ids_by_k": hybrid_primary,
                "context_ids": hybrid_context_ids,
                "metrics_by_k": {
                    str(k): _score_set(item, hybrid_primary[str(k)]) for k in K_VALUES
                },
                "context_metrics": _score_set(item, hybrid_context_ids),
                "fallback_used": _hybrid_fallback_used(hybrid_context_input),
                "expansion_displacement": _hybrid_displacement(
                    hybrid_primary[str(CONTEXT_N_RESULTS)],
                    hybrid_context_ids,
                ),
            },
        },
    }


def aggregate_results(
    item_results: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    strata = sorted({_required_string(item, "stratum") for item in item_results})
    return {
        "aggregate": _aggregate_group(item_results),
        "by_stratum": {
            stratum: _aggregate_group(
                [item for item in item_results if item.get("stratum") == stratum]
            )
            for stratum in strata
        },
    }


def _aggregate_group(item_results: Sequence[Mapping[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {"item_count": len(item_results), "arms": {}}
    arms = result["arms"]
    assert isinstance(arms, dict)
    for arm in ("dense", "hybrid"):
        arm_results = [_arm_result(item, arm) for item in item_results]
        recall_at_k: dict[str, object] = {}
        hit_rate_at_k: dict[str, object] = {}
        denominators_at_k: dict[str, int] = {}
        for k in K_VALUES:
            metric_records = [
                _metric_record(value, "metrics_by_k", str(k)) for value in arm_results
            ]
            recalls = _nonnull_numbers(metric_records, "recall")
            hits = _nonnull_numbers(metric_records, "hit")
            recall_at_k[str(k)] = _mean_or_none(recalls)
            hit_rate_at_k[str(k)] = _mean_or_none(hits)
            denominators_at_k[str(k)] = len(recalls)

        context_records = [
            _mapping_field(value, "context_metrics") for value in arm_results
        ]
        context_recalls = _nonnull_numbers(context_records, "recall")
        context_hits = _nonnull_numbers(context_records, "hit")
        essential = _nonnull_numbers(context_records, "essential_coverage")
        fallback = [float(bool(value.get("fallback_used"))) for value in arm_results]
        displacements = [
            _mapping_field(value, "expansion_displacement") for value in arm_results
        ]
        arms[arm] = {
            "recall_at_k": recall_at_k,
            "hit_rate_at_k": hit_rate_at_k,
            "primary_metric_denominators": denominators_at_k,
            "recall_context": _mean_or_none(context_recalls),
            "hit_rate_context": _mean_or_none(context_hits),
            "context_recall_denominator": len(context_recalls),
            "essential_coverage_context": _mean_or_none(essential),
            "essential_coverage_denominator": len(essential),
            "fallback_rate": _mean_or_none(fallback),
            "fallback_denominator": len(fallback),
            "expansion_displacement": {
                cause: {
                    "total": sum(int(value.get(cause, 0)) for value in displacements),
                    "mean_per_question": _mean_or_none(
                        [float(int(value.get(cause, 0))) for value in displacements]
                    ),
                }
                for cause in (
                    "distance_filtering",
                    "document_filtering",
                    "truncation",
                )
            },
        }
    return result


def select_noise_subset(items: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    """Select the prospectively declared 10-item stratified subset by ID order."""

    selected: list[str] = []
    for stratum, count in NOISE_SUBSET_STRATUM_COUNTS.items():
        ids = sorted(
            _required_string(item, "id")
            for item in items
            if item.get("stratum") == stratum
        )
        if len(ids) < count:
            raise RetrievalBenchmarkError(
                f"noise subset requires {count} {stratum} items, found {len(ids)}"
            )
        selected.extend(ids[:count])
    if len(selected) != 10 or len(set(selected)) != 10:
        raise RetrievalBenchmarkError("noise subset rule did not select 10 unique items")
    return tuple(selected)


def _flatten_published_metrics(aggregate: Mapping[str, object]) -> dict[str, float]:
    result: dict[str, float] = {}
    arms = _mapping_field(aggregate, "arms")
    for arm in ("dense", "hybrid"):
        values = _mapping_field(arms, arm)
        for family in ("recall_at_k", "hit_rate_at_k"):
            family_values = _mapping_field(values, family)
            for k in K_VALUES:
                value = family_values.get(str(k))
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    result[f"{arm}.{family}.{k}"] = float(value)
        for name in (
            "recall_context",
            "hit_rate_context",
            "essential_coverage_context",
            "fallback_rate",
        ):
            value = values.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                result[f"{arm}.{name}"] = float(value)
        displacement = _mapping_field(values, "expansion_displacement")
        for cause in ("distance_filtering", "document_filtering", "truncation"):
            cause_values = _mapping_field(displacement, cause)
            mean_value = cause_values.get("mean_per_question")
            if isinstance(mean_value, (int, float)) and not isinstance(mean_value, bool):
                result[f"{arm}.expansion_displacement.{cause}"] = float(mean_value)
    dense = _mapping_field(arms, "dense")
    hybrid = _mapping_field(arms, "hybrid")
    dense_recall = _mapping_field(dense, "recall_at_k").get("5")
    hybrid_recall = _mapping_field(hybrid, "recall_at_k").get("5")
    if (
        isinstance(dense_recall, (int, float))
        and not isinstance(dense_recall, bool)
        and isinstance(hybrid_recall, (int, float))
        and not isinstance(hybrid_recall, bool)
    ):
        result["comparison.macro_recall_at_5.hybrid_minus_dense"] = (
            float(hybrid_recall) - float(dense_recall)
        )
    return result


def build_noise_floor(
    repeated_item_results: Sequence[Sequence[Mapping[str, object]]],
) -> dict[str, object]:
    if len(repeated_item_results) != NOISE_REPEATS:
        raise RetrievalBenchmarkError(
            f"noise floor requires exactly {NOISE_REPEATS} repetitions"
        )
    expected_ids = sorted(
        _required_string(item, "id") for item in repeated_item_results[0]
    )
    for repetition in repeated_item_results:
        actual_ids = sorted(_required_string(item, "id") for item in repetition)
        if actual_ids != expected_ids:
            raise RetrievalBenchmarkError(
                "noise-floor repetitions must contain the same fixed item IDs"
            )

    summaries = [aggregate_results(items) for items in repeated_item_results]
    aggregate_profiles = [
        _flatten_published_metrics(_mapping_field(summary, "aggregate"))
        for summary in summaries
    ]
    strata = sorted(
        _mapping_field(summaries[0], "by_stratum")
    )
    for summary in summaries[1:]:
        if sorted(_mapping_field(summary, "by_stratum")) != strata:
            raise RetrievalBenchmarkError(
                "noise-floor repetitions changed their stratum composition"
            )
    return {
        "repetitions": NOISE_REPEATS,
        "subset_size": len(repeated_item_results[0]),
        "subset_rule": {
            "ordering": "lexicographic_item_id_within_stratum",
            "stratum_counts": dict(NOISE_SUBSET_STRATUM_COUNTS),
        },
        "aggregate": {
            "metrics": _metric_spreads(aggregate_profiles),
        },
        "by_stratum": {
            stratum: {
                "metrics": _metric_spreads(
                    [
                        _flatten_published_metrics(
                            _mapping_field(
                                _mapping_field(summary, "by_stratum"),
                                stratum,
                            )
                        )
                        for summary in summaries
                    ]
                ),
            }
            for stratum in strata
        },
    }


def _metric_spreads(
    repeated_metrics: Sequence[Mapping[str, float]],
) -> dict[str, dict[str, float]]:
    if not repeated_metrics:
        raise RetrievalBenchmarkError("noise-floor metric repetitions are empty")
    expected_names = set(repeated_metrics[0])
    if any(set(metrics) != expected_names for metrics in repeated_metrics[1:]):
        raise RetrievalBenchmarkError(
            "noise-floor repetitions changed their published metric set"
        )
    spreads: dict[str, dict[str, float]] = {}
    for name in sorted(expected_names):
        values = [float(metrics[name]) for metrics in repeated_metrics]
        spreads[name] = {
            "min": min(values),
            "max": max(values),
            "standard_deviation": statistics.pstdev(values),
        }
    return spreads


def build_benchmark_artifact(
    *,
    gold: LockedGold,
    embedding_cache: Mapping[str, object],
    item_results: Sequence[Mapping[str, object]],
    noise_repetitions: Sequence[Sequence[Mapping[str, object]]],
    run_identity: Mapping[str, object],
    corpus_identity: Mapping[str, object],
    embedding_cache_sha256: str,
) -> dict[str, object]:
    if len(item_results) != len(gold.items):
        raise RetrievalBenchmarkError("benchmark result count does not match locked gold")
    summary = aggregate_results(item_results)
    aggregate = _mapping_field(summary, "aggregate")
    aggregate_arms = _mapping_field(aggregate, "arms")
    dense = _mapping_field(aggregate_arms, "dense")
    hybrid = _mapping_field(aggregate_arms, "hybrid")
    dense_recall = _mapping_field(dense, "recall_at_k").get("5")
    hybrid_recall = _mapping_field(hybrid, "recall_at_k").get("5")
    delta = (
        float(hybrid_recall) - float(dense_recall)
        if isinstance(dense_recall, (int, float))
        and not isinstance(dense_recall, bool)
        and isinstance(hybrid_recall, (int, float))
        and not isinstance(hybrid_recall, bool)
        else None
    )
    cache_usage = embedding_cache.get("usage")
    artifact = {
        "schema": BENCHMARK_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "identity": {
            **dict(run_identity),
            "candidate_commit": gold.candidate_commit,
            "candidate_rag_policy": gold.candidate_rag_policy,
            "gold_set_sha256": gold.gold_set_sha256,
            "question_set_sha256": gold.question_set_sha256,
            "corpus_manifest_sha256": gold.corpus_manifest_sha256,
            "embedding_cache_sha256": embedding_cache_sha256,
            "embedding_model": EMBEDDING_MODEL,
        },
        "configuration": {
            "k_values": list(K_VALUES),
            "context_n_results": CONTEXT_N_RESULTS,
            "max_primary_distance": MAX_PRIMARY_DISTANCE,
            "max_final_sources": MAX_FINAL_SOURCES,
            "semantic_candidate_limit": SEMANTIC_CANDIDATE_LIMIT,
            "primary_comparison_metric": PRIMARY_COMPARISON_METRIC,
            "dense_arm": "raw_chroma_vector_ranking",
            "hybrid_arm": "existing_bm25_dense_rrf_primary_selection",
            "query_embedding_reuse": "one_locked_vector_per_item_for_both_arms_and_all_repeats",
        },
        "embedding_operation": {
            "operation_count": embedding_cache.get("operation_count"),
            "automatic_retries": embedding_cache.get("automatic_retries"),
            "usage": dict(cache_usage) if isinstance(cache_usage, Mapping) else None,
        },
        "comparison": {
            "metric": PRIMARY_COMPARISON_METRIC,
            "dense": dense_recall,
            "hybrid": hybrid_recall,
            "hybrid_minus_dense": delta,
        },
        "summary": summary,
        "noise_floor": build_noise_floor(noise_repetitions),
        "items": [dict(item) for item in item_results],
    }
    validate_text_free_artifact(artifact)
    return artifact


def validate_text_free_artifact(value: object, path: str = "$artifact") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).casefold()
            if normalized in _FORBIDDEN_PERSISTED_KEYS:
                raise RetrievalBenchmarkError(
                    f"{path}.{key}: forbidden text-bearing artifact field"
                )
            validate_text_free_artifact(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_text_free_artifact(child, f"{path}[{index}]")


def _required_string(value: Mapping[str, object], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise RetrievalBenchmarkError(f"{field} must be a non-empty string")
    return result


def _string_set(value: object, *, field: str) -> set[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise RetrievalBenchmarkError(f"{field} must be an array of non-empty strings")
    return set(value)


def _optional_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RetrievalBenchmarkError("embedding usage token count is invalid")
    return value


def _mapping_field(value: Mapping[str, object], field: str) -> Mapping[str, object]:
    result = value.get(field)
    if not isinstance(result, Mapping):
        raise RetrievalBenchmarkError(f"{field} must be an object")
    return result


def _arm_result(item: Mapping[str, object], arm: str) -> Mapping[str, object]:
    return _mapping_field(_mapping_field(item, "arms"), arm)


def _metric_record(
    arm: Mapping[str, object],
    field: str,
    key: str,
) -> Mapping[str, object]:
    return _mapping_field(_mapping_field(arm, field), key)


def _nonnull_numbers(
    values: Sequence[Mapping[str, object]],
    field: str,
) -> list[float]:
    result = []
    for value in values:
        candidate = value.get(field)
        if isinstance(candidate, bool):
            result.append(float(candidate))
        elif isinstance(candidate, (int, float)):
            result.append(float(candidate))
    return result


def _mean_or_none(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None
