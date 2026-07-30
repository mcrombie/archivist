import hashlib
import json
import logging
import math
import os
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

from corpus import (
    build_chunk_lookup,
    get_all_chunks,
    get_chunk_lookup,
    get_neighbor_chunk_ids,
)
from costs import current_usage_context, tracked_embeddings_create
from filters import should_skip_document
from query_planning import (
    BROAD_NARRATIVE_SPAN_STAGE_REQUIREMENTS,
    LONG_INSTITUTIONAL_LINEAGE_STAGE_REQUIREMENTS,
    narrative_span_document_bands,
    requires_broad_narrative_span,
)
from retrieval_trace_contract import (
    RETRIEVAL_TRACE_SCHEMA,
    document_identifier_sha256,
    validate_text_free_retrieval_trace,
)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "chroma_db"

MAX_PRIMARY_DISTANCE = 1.05
MAX_FINAL_SOURCES = 8
SEMANTIC_CANDIDATE_LIMIT = 20
LEXICAL_CANDIDATE_LIMIT = 20
LEXICAL_SCORING_VERSION = "bm25-nfkd-word-v1"
TOKENIZER_VERSION = "nfkd-unicode-word-possessive-v1"
BM25_K1 = 1.2
BM25_B = 0.75
LEXICAL_COVERAGE_MULTIPLIER = 0.2
QUOTED_PHRASE_BONUS = 2.0
QUERY_BIGRAM_BONUS = 0.5
RRF_K = 60
SEMANTIC_WEIGHT = 1.0
LEXICAL_WEIGHT = 1.0
MAX_PRIMARY_PER_DOCUMENT = 3
DIVERSITY_MIN_SCORE_RATIO = 0.75
HYBRID_RETRIEVAL_VERSION = "hybrid-bm25-rrf-v1"
FACETED_RETRIEVAL_VERSION = "faceted-hybrid-rrf-v13"
BROAD_MECHANISM_LEXICAL_VERSION = "role-scoped-mechanism-lexical-v1"
BROAD_MECHANISM_CANDIDATE_LIMIT = 20
BROAD_CANONICAL_EXECUTION_VERSION = "broad-stage-narrative-span-v6"
BROAD_TRANSITION_LANE_VERSION = "adjacent-pair-transition-v3"
LONG_LINEAGE_CONTRACT_VERSION = "long-institutional-lineage-v2"
LONG_LINEAGE_TRANSITION_CAPACITY_POLICY = (
    "reuse-selected-stage-source-before-extra-source"
)
RETRIEVAL_DIAGNOSTICS_ENV = "ARCHIVIST_RETRIEVAL_DIAGNOSTICS"
RETRIEVAL_DIAGNOSTICS_DIR_ENV = "ARCHIVIST_RETRIEVAL_DIAGNOSTICS_DIR"
RETRIEVAL_DIAGNOSTICS_DIR = BASE_DIR / "runtime" / "retrieval-diagnostics"
_TRACE_CORPUS_FIELDS = frozenset(
    {
        "collection_count",
        "collection_name",
        "corpus_manifest_sha256",
        "chunks_sha256",
        "hnsw_space",
        "project_id",
    }
)
_TRACE_TOP_LEVEL_FIELDS = frozenset(
    {
        "candidates",
        "corpus",
        "created_at",
        "parameters",
        "plan",
        "query",
        "evidence",
        "generation_contract",
        "lanes",
        "retrieval_version",
        "schema",
        "scope",
        "selection",
        "trace_id",
    }
)

_WORD_PATTERN = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", flags=re.UNICODE)
_QUOTED_PHRASE_PATTERN = re.compile(r'["“”]([^"“”]+)["“”]')
_BROAD_QUERY_PATTERNS = tuple(
    re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\btrace\b",
        r"\blineage\b",
        r"\bacross\b",
        r"\bthroughout\b",
        r"\bover\s+time\b",
        r"\b(?:evolution|development)\b",
        r"\bas\s+(?:an?\s+|the\s+)?(?:engine|force|driver|instrument)\b",
    )
)
_LEXICAL_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "after",
        "again",
        "against",
        "all",
        "also",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "became",
        "because",
        "been",
        "before",
        "being",
        "book",
        "but",
        "by",
        "can",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "him",
        "his",
        "how",
        "i",
        "in",
        "into",
        "is",
        "it",
        "its",
        "manuscript",
        "me",
        "more",
        "most",
        "not",
        "of",
        "on",
        "or",
        "our",
        "play",
        "role",
        "say",
        "says",
        "she",
        "should",
        "so",
        "some",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "us",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
)

logger = logging.getLogger(__name__)

chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
collection = chroma_client.get_or_create_collection(name="manuscript")


@dataclass(frozen=True)
class RetrievalOutcome:
    """Final model context paired with its text-free retrieval trace."""

    final_chunks: list[dict[str, Any]]
    trace: dict[str, Any]


@dataclass(frozen=True)
class PlannedContext:
    """Ordered multi-facet context and the source map consumed by generation."""

    final_chunks: list[dict[str, Any]]
    facet_source_numbers: dict[str, tuple[int, ...]]
    trace: dict[str, Any]
    lane_by_chunk_id: dict[str, tuple[str, ...]]
    broad_stage_anchor_chunk_ids: dict[str, str] = field(default_factory=dict)
    broad_transition_chunk_ids: dict[tuple[str, str], str] = field(
        default_factory=dict
    )


class FileTraceSink:
    """Persist one private, text-free retrieval trace per JSON file."""

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            configured_root = os.getenv(RETRIEVAL_DIAGNOSTICS_DIR_ENV, "").strip()
            root = (
                Path(configured_root)
                if configured_root
                else RETRIEVAL_DIAGNOSTICS_DIR
            )
        self.root = root

    def __call__(self, trace: Mapping[str, Any]) -> Path:
        if trace.get("schema") != RETRIEVAL_TRACE_SCHEMA:
            raise ValueError("retrieval trace schema is missing or unsupported")
        validate_text_free_retrieval_trace(trace)
        day = datetime.now(UTC).date().isoformat()
        directory = self.root / day
        directory.mkdir(parents=True, exist_ok=True)
        trace_id = str(trace.get("trace_id") or "")
        if not re.fullmatch(r"[0-9a-f]{32}", trace_id):
            raise ValueError("retrieval trace ID must be 32 lowercase hexadecimal characters")
        target = directory / f"{trace_id}.json"
        temporary = directory / f".{trace_id}.{uuid4().hex}.tmp"
        temporary.write_text(
            json.dumps(trace, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target


@lru_cache(maxsize=1)
def default_openai_client() -> OpenAI:
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def embed_query(query: str, embedding_client: OpenAI | None = None) -> list[float]:
    response = tracked_embeddings_create(
        embedding_client or default_openai_client(),
        operation="query_embedding",
        model="text-embedding-3-small",
        input=query,
    )
    return response.data[0].embedding


def embed_queries(
    queries: Sequence[str],
    embedding_client: OpenAI | None = None,
) -> list[list[float]]:
    """Embed a bounded facet set in one tracked API operation."""
    query_list = [str(query) for query in queries]
    if not query_list:
        return []
    response = tracked_embeddings_create(
        embedding_client or default_openai_client(),
        operation="query_embedding",
        model="text-embedding-3-small",
        input=query_list,
    )
    embeddings = [list(item.embedding) for item in response.data]
    if len(embeddings) != len(query_list):
        raise RuntimeError("embedding response count does not match query facet count")
    return embeddings


def retrieve_semantic_from_collection(
    query: str,
    collection_handle: Any,
    *,
    n_results: int = 5,
    embedding_client: OpenAI | None = None,
) -> dict[str, Any]:
    """Run the shared semantic-only query used by deferred Index Mode."""
    if n_results <= 0:
        raise ValueError("n_results must be greater than zero")
    collection_count = int(collection_handle.count())
    candidate_count = min(collection_count, n_results)
    if candidate_count <= 0:
        return {
            "ids": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
    query_embedding = embed_query(query, embedding_client=embedding_client)
    return collection_handle.query(
        query_embeddings=[query_embedding],
        n_results=candidate_count,
        include=["metadatas", "distances"],
    )


def retrieve_semantic(query: str, n_results: int = 5) -> dict[str, Any]:
    return retrieve_semantic_from_collection(
        query,
        collection,
        n_results=n_results,
    )


def _normalized_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.replace("’", "'"))
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _tokens(value: str) -> list[str]:
    normalized_tokens = []
    for raw_token in _WORD_PATTERN.findall(_normalized_text(value)):
        token = raw_token.casefold()
        if token.endswith("'s") and len(token) > 2:
            token = token[:-2]
        if token.isdigit() and len(token) <= 2:
            continue
        normalized_tokens.append(token)
    return normalized_tokens


def _query_terms(query: str) -> list[str]:
    terms = [
        token
        for token in _tokens(query)
        if token not in _LEXICAL_STOPWORDS and len(token) > 1
    ]
    return list(dict.fromkeys(terms))


def _quoted_phrases(query: str) -> list[str]:
    phrases = []
    for match in _QUOTED_PHRASE_PATTERN.finditer(query):
        normalized = " ".join(_tokens(match.group(1)))
        if normalized:
            phrases.append(normalized)
    return list(dict.fromkeys(phrases))


def classify_retrieval_mode(query: str) -> str:
    if any(pattern.search(query) for pattern in _BROAD_QUERY_PATTERNS):
        return "broad_synthesis"
    return "standard"


def _safe_chunk_fields(chunk: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.get("chunk_id") or ""),
        "document_sha256": document_identifier_sha256(
            chunk.get("document")
        ),
        "paragraph_start": chunk.get("paragraph_start"),
        "paragraph_end": chunk.get("paragraph_end"),
    }


def _document_distribution(items: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        document_sha256 = str(item.get("document_sha256") or "")
        document = str(item.get("document") or "")
        if not document_sha256 and document:
            document_sha256 = document_identifier_sha256(document)
        if document_sha256:
            counts[document_sha256] += 1
    return dict(sorted(counts.items()))


def _safe_corpus_trace(corpus: Mapping[str, Any] | None) -> dict[str, Any]:
    if not corpus:
        return {}
    return {
        str(key): value
        for key, value in corpus.items()
        if str(key) in _TRACE_CORPUS_FIELDS
        and isinstance(value, (str, int, float, bool, type(None)))
    }


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lexical_candidates(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    limit: int = LEXICAL_CANDIDATE_LIMIT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rank eligible chunks with deterministic dependency-free BM25."""
    if limit <= 0:
        raise ValueError("lexical candidate limit must be greater than zero")

    query_terms = _query_terms(query)
    quoted_phrases = _quoted_phrases(query)
    if not query_terms:
        return [], {
            "query_term_count": 0,
            "query_terms_with_zero_document_frequency": 0,
            "quoted_phrase_count": len(quoted_phrases),
        }

    eligible: list[tuple[int, dict[str, Any], list[str], Counter[str]]] = []
    for ordinal, chunk in enumerate(chunks):
        if should_skip_document(str(chunk.get("document") or "")):
            continue
        chunk_tokens = _tokens(str(chunk.get("text") or ""))
        eligible.append((ordinal, chunk, chunk_tokens, Counter(chunk_tokens)))

    if not eligible:
        return [], {
            "query_term_count": len(query_terms),
            "query_terms_with_zero_document_frequency": len(query_terms),
            "quoted_phrase_count": len(quoted_phrases),
        }

    document_frequency = {
        term: sum(1 for _, _, _, counts in eligible if counts.get(term, 0) > 0)
        for term in query_terms
    }
    average_length = sum(len(tokens) for _, _, tokens, _ in eligible) / len(eligible)
    average_length = max(average_length, 1.0)
    corpus_size = len(eligible)
    content_sequence = [
        token
        for token in _tokens(query)
        if token not in _LEXICAL_STOPWORDS and len(token) > 1
    ]
    query_bigrams = list(
        dict.fromkeys(
            " ".join(pair)
            for pair in zip(content_sequence, content_sequence[1:], strict=False)
        )
    )

    ranked: list[dict[str, Any]] = []
    for ordinal, chunk, chunk_tokens, counts in eligible:
        score = 0.0
        matched_term_count = 0
        length_normalization = (
            1.0
            - BM25_B
            + BM25_B * (len(chunk_tokens) / average_length)
        )
        for term in query_terms:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            matched_term_count += 1
            df = document_frequency[term]
            inverse_document_frequency = math.log(
                1.0 + (corpus_size - df + 0.5) / (df + 0.5)
            )
            score += inverse_document_frequency * (
                frequency * (BM25_K1 + 1.0)
                / (frequency + BM25_K1 * length_normalization)
            )

        normalized_chunk = " ".join(chunk_tokens)
        quoted_phrase_hits = sum(
            1 for phrase in quoted_phrases if phrase in normalized_chunk
        )
        bigram_hits = sum(1 for phrase in query_bigrams if phrase in normalized_chunk)
        if matched_term_count:
            coverage = matched_term_count / len(query_terms)
            score *= 1.0 + LEXICAL_COVERAGE_MULTIPLIER * coverage
        score += (
            quoted_phrase_hits * QUOTED_PHRASE_BONUS
            + bigram_hits * QUERY_BIGRAM_BONUS
        )
        if score <= 0:
            continue

        ranked.append(
            {
                "chunk": chunk,
                "chunk_id": str(chunk.get("chunk_id") or ""),
                "document": str(chunk.get("document") or ""),
                "score": score,
                "matched_term_count": matched_term_count,
                "quoted_phrase_hits": quoted_phrase_hits,
                "bigram_hits": bigram_hits,
                "ordinal": ordinal,
            }
        )

    ranked.sort(
        key=lambda candidate: (
            -float(candidate["score"]),
            int(candidate["ordinal"]),
            str(candidate["chunk_id"]),
        )
    )
    ranked = ranked[:limit]
    for rank, candidate in enumerate(ranked, start=1):
        candidate["rank"] = rank

    return ranked, {
        "query_term_count": len(query_terms),
        "query_terms_with_zero_document_frequency": sum(
            1 for frequency in document_frequency.values() if frequency == 0
        ),
        "quoted_phrase_count": len(quoted_phrases),
    }


def _first_batch(results: Mapping[str, Any], key: str) -> list[Any]:
    batches = results.get(key)
    if not batches:
        return []
    first = batches[0]
    if first is None:
        return []
    return list(first)


def _semantic_candidates(results: Mapping[str, Any]) -> list[dict[str, Any]]:
    metadatas = _first_batch(results, "metadatas")
    distances = _first_batch(results, "distances")
    ids = _first_batch(results, "ids")
    if len(metadatas) != len(distances):
        raise ValueError("semantic metadata and distance counts do not match")
    if ids and len(ids) != len(metadatas):
        raise ValueError("semantic ID and metadata counts do not match")

    candidates: list[dict[str, Any]] = []
    for index, (metadata, raw_distance) in enumerate(
        zip(metadatas, distances, strict=True),
        start=1,
    ):
        if not isinstance(metadata, Mapping):
            raise ValueError("semantic candidate metadata must be an object")
        chunk_id = str(metadata.get("chunk_id") or "")
        raw_id = str(ids[index - 1]) if ids else chunk_id
        if not chunk_id or raw_id != chunk_id:
            raise ValueError("semantic candidate ID does not match metadata chunk_id")
        try:
            distance = float(raw_distance)
        except (TypeError, ValueError) as exc:
            raise ValueError("semantic candidate distance must be numeric") from exc
        candidates.append(
            {
                "rank": index,
                "chunk_id": chunk_id,
                "document": str(metadata.get("document") or ""),
                "distance": distance,
                "metadata": dict(metadata),
            }
        )
    return candidates


def _raw_primary_fallback_used(
    semantic: list[dict[str, Any]],
    *,
    n_results: int,
) -> bool:
    eligible = [
        candidate
        for candidate in semantic[:n_results]
        if not should_skip_document(str(candidate.get("document") or ""))
    ]
    return bool(
        eligible
        and not any(
            float(candidate["distance"]) <= MAX_PRIMARY_DISTANCE
            for candidate in eligible
        )
    )


def _trace_candidate(
    candidate: Mapping[str, Any],
    *,
    include_lexical: bool = False,
) -> dict[str, Any]:
    source = candidate.get("chunk") or candidate.get("metadata") or candidate
    if not isinstance(source, Mapping):
        source = candidate
    trace = {
        **_safe_chunk_fields(source),
        "rank": candidate.get("rank"),
    }
    if "distance" in candidate:
        trace["distance"] = candidate.get("distance")
        trace["within_distance_threshold"] = (
            float(candidate["distance"]) <= MAX_PRIMARY_DISTANCE
        )
    if include_lexical:
        trace.update(
            {
                "bm25_score": round(float(candidate["score"]), 12),
                "matched_term_count": candidate.get("matched_term_count", 0),
                "quoted_phrase_hits": candidate.get("quoted_phrase_hits", 0),
                "bigram_hits": candidate.get("bigram_hits", 0),
            }
        )
    return trace


def _select_fused_candidates(
    fused: list[dict[str, Any]],
    *,
    limit: int,
    max_per_document: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if max_per_document is None:
        return fused[:limit], []

    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    document_counts: Counter[str] = Counter()

    for candidate in fused:
        document = str(candidate["document"])
        if document_counts[document] >= max_per_document:
            deferred.append(candidate)
            continue
        if deferred:
            strongest_deferred_score = float(deferred[0]["rrf_score"])
            if (
                float(candidate["rrf_score"])
                < strongest_deferred_score * DIVERSITY_MIN_SCORE_RATIO
            ):
                deferred.append(candidate)
                continue
        selected.append(candidate)
        document_counts[document] += 1
        if len(selected) == limit:
            return selected, deferred

    for candidate in deferred:
        selected.append(candidate)
        if len(selected) == limit:
            break
    return selected, deferred


def build_hybrid_results(
    query: str,
    semantic_results: Mapping[str, Any],
    chunks: list[dict[str, Any]],
    *,
    n_results: int = 5,
    corpus: Mapping[str, Any] | None = None,
    allow_semantic_fallback: bool = True,
    retrieval_mode_override: str | None = None,
    broad_max_per_document: int | None = None,
) -> dict[str, Any]:
    """Attach deterministic BM25/RRF primary anchors to raw semantic results."""
    if n_results <= 0:
        raise ValueError("n_results must be greater than zero")

    semantic = _semantic_candidates(semantic_results)
    lexical, lexical_query = lexical_candidates(query, chunks)
    if retrieval_mode_override not in {None, "standard", "broad_synthesis"}:
        raise ValueError("retrieval_mode_override must be standard or broad_synthesis")
    if broad_max_per_document is not None and broad_max_per_document <= 0:
        raise ValueError("broad_max_per_document must be greater than zero")
    retrieval_mode = retrieval_mode_override or classify_retrieval_mode(query)
    lookup = build_chunk_lookup(chunks)
    discarded: list[dict[str, Any]] = []
    semantic_reachable: list[dict[str, Any]] = []
    for candidate in semantic:
        if should_skip_document(candidate["document"]):
            discarded.append(
                {
                    **_safe_chunk_fields(candidate),
                    "stage": "semantic",
                    "reason": "structural_document",
                    "displacement_cause": "document_filtering",
                }
            )
        elif candidate["chunk_id"] not in lookup:
            raise RuntimeError(
                "semantic index returned a chunk absent from the active corpus: "
                + str(candidate["chunk_id"])
            )
        else:
            semantic_reachable.append(candidate)

    semantic_within_threshold = [
        candidate
        for candidate in semantic_reachable
        if float(candidate["distance"]) <= MAX_PRIMARY_DISTANCE
    ]
    raw_primary_fallback_detected = _raw_primary_fallback_used(
        semantic,
        n_results=n_results,
    )
    raw_primary_fallback = bool(
        allow_semantic_fallback and raw_primary_fallback_detected
    )
    semantic_fallback = bool(
        allow_semantic_fallback
        and semantic_reachable
        and not semantic_within_threshold
    )
    if semantic_fallback:
        semantic_for_fusion = semantic_reachable
    else:
        fusion_ids = {
            str(candidate["chunk_id"])
            for candidate in semantic_within_threshold
        }
        if raw_primary_fallback:
            fusion_ids.update(
                str(candidate["chunk_id"])
                for candidate in semantic_reachable
                if int(candidate["rank"]) <= n_results
            )
        semantic_for_fusion = [
            candidate
            for candidate in semantic_reachable
            if str(candidate["chunk_id"]) in fusion_ids
        ]
    semantic_for_fusion_ids = {
        str(candidate["chunk_id"]) for candidate in semantic_for_fusion
    }
    if not semantic_fallback:
        for candidate in semantic_reachable:
            if candidate["chunk_id"] not in semantic_for_fusion_ids:
                discarded.append(
                    {
                        **_safe_chunk_fields(candidate),
                        "stage": "semantic",
                        "reason": "distance_threshold",
                        "displacement_cause": "distance_filtering",
                    }
                )

    semantic_by_id = {
        candidate["chunk_id"]: candidate for candidate in semantic_for_fusion
    }
    all_semantic_by_id = {
        candidate["chunk_id"]: candidate for candidate in semantic_reachable
    }
    lexical_by_id = {candidate["chunk_id"]: candidate for candidate in lexical}
    eligible_ids = set(semantic_by_id)
    eligible_ids.update(lexical_by_id)

    fused: list[dict[str, Any]] = []
    for chunk_id in eligible_ids:
        semantic_candidate = semantic_by_id.get(chunk_id)
        raw_semantic_candidate = all_semantic_by_id.get(chunk_id)
        lexical_candidate = lexical_by_id.get(chunk_id)
        chunk = lookup[chunk_id]
        semantic_contribution = (
            SEMANTIC_WEIGHT / (RRF_K + int(semantic_candidate["rank"]))
            if semantic_candidate is not None
            else 0.0
        )
        lexical_contribution = (
            LEXICAL_WEIGHT / (RRF_K + int(lexical_candidate["rank"]))
            if lexical_candidate is not None
            else 0.0
        )
        fused.append(
            {
                "chunk_id": chunk_id,
                "document": str(chunk.get("document") or ""),
                "chunk": chunk,
                "semantic_rank": (
                    raw_semantic_candidate["rank"]
                    if raw_semantic_candidate
                    else None
                ),
                "semantic_distance": (
                    raw_semantic_candidate["distance"]
                    if raw_semantic_candidate
                    else None
                ),
                "semantic_contributed": semantic_candidate is not None,
                "lexical_rank": (
                    lexical_candidate["rank"] if lexical_candidate else None
                ),
                "bm25_score": (
                    lexical_candidate["score"] if lexical_candidate else None
                ),
                "semantic_rrf": semantic_contribution,
                "lexical_rrf": lexical_contribution,
                "rrf_score": semantic_contribution + lexical_contribution,
            }
        )

    fused.sort(
        key=lambda candidate: (
            -float(candidate["rrf_score"]),
            int(candidate["semantic_rank"] or 10**9),
            int(candidate["lexical_rank"] or 10**9),
            str(candidate["chunk_id"]),
        )
    )
    for rank, candidate in enumerate(fused, start=1):
        candidate["rank"] = rank

    selected, diversity_deferred = _select_fused_candidates(
        fused,
        limit=n_results,
        max_per_document=(
            (
                broad_max_per_document
                if broad_max_per_document is not None
                else MAX_PRIMARY_PER_DOCUMENT
            )
            if retrieval_mode == "broad_synthesis"
            else None
        ),
    )
    selected_ids = [str(candidate["chunk_id"]) for candidate in selected]
    selected_set = set(selected_ids)
    for candidate in fused:
        if candidate["chunk_id"] not in selected_set:
            discarded.append(
                {
                    **_safe_chunk_fields(candidate["chunk"]),
                    "stage": "fusion",
                    "reason": "fusion_primary_cap",
                    "displacement_cause": "truncation",
                }
            )

    semantic_trace = []
    for candidate in semantic:
        trace_candidate = _trace_candidate(candidate)
        trace_candidate["retrieval_eligible"] = (
            not should_skip_document(candidate["document"])
            and candidate["chunk_id"] in lookup
        )
        semantic_trace.append(trace_candidate)

    lexical_trace = [
        _trace_candidate(candidate, include_lexical=True)
        for candidate in lexical
    ]
    fused_trace = [
        {
            **_safe_chunk_fields(candidate["chunk"]),
            "rank": candidate["rank"],
            "rrf_score": round(float(candidate["rrf_score"]), 12),
            "semantic_rank": candidate["semantic_rank"],
            "semantic_distance": candidate["semantic_distance"],
            "semantic_contributed": candidate["semantic_contributed"],
            "semantic_rrf": round(float(candidate["semantic_rrf"]), 12),
            "lexical_rank": candidate["lexical_rank"],
            "bm25_score": (
                round(float(candidate["bm25_score"]), 12)
                if candidate["bm25_score"] is not None
                else None
            ),
            "lexical_rrf": round(float(candidate["lexical_rrf"]), 12),
            "selected_primary": candidate["chunk_id"] in selected_set,
        }
        for candidate in fused
    ]

    trace = {
        "schema": RETRIEVAL_TRACE_SCHEMA,
        "trace_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "retrieval_version": HYBRID_RETRIEVAL_VERSION,
        "query": {
            "sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
            "char_count": len(query),
            "mode": retrieval_mode,
            **lexical_query,
        },
        "corpus": _safe_corpus_trace(corpus),
        "parameters": {
            "lexical_scoring_version": LEXICAL_SCORING_VERSION,
            "tokenizer_version": TOKENIZER_VERSION,
            "stopword_sha256": hashlib.sha256(
                "\n".join(sorted(_LEXICAL_STOPWORDS)).encode("utf-8")
            ).hexdigest(),
            "bm25_k1": BM25_K1,
            "bm25_b": BM25_B,
            "lexical_coverage_multiplier": LEXICAL_COVERAGE_MULTIPLIER,
            "quoted_phrase_bonus": QUOTED_PHRASE_BONUS,
            "query_bigram_bonus": QUERY_BIGRAM_BONUS,
            "semantic_candidate_limit": SEMANTIC_CANDIDATE_LIMIT,
            "semantic_candidate_count": len(semantic),
            "lexical_candidate_limit": LEXICAL_CANDIDATE_LIMIT,
            "lexical_candidate_count": len(lexical),
            "primary_limit": n_results,
            "semantic_distance_threshold": MAX_PRIMARY_DISTANCE,
            "final_context_source_limit": MAX_FINAL_SOURCES,
            "rrf_k": RRF_K,
            "semantic_weight": SEMANTIC_WEIGHT,
            "lexical_weight": LEXICAL_WEIGHT,
            "max_primary_per_document": (
                (
                    broad_max_per_document
                    if broad_max_per_document is not None
                    else MAX_PRIMARY_PER_DOCUMENT
                )
                if retrieval_mode == "broad_synthesis"
                else None
            ),
            "diversity_min_score_ratio": DIVERSITY_MIN_SCORE_RATIO,
            "neighbor_expansion": "primaries_first_then_immediate_neighbors",
            "semantic_fallback_allowed": allow_semantic_fallback,
            "tie_break": "rrf_desc_semantic_rank_lexical_rank_chunk_id",
        },
        "candidates": {
            "semantic": semantic_trace,
            "lexical": lexical_trace,
            "fused": fused_trace,
        },
        "selection": {
            "primary_chunk_ids": selected_ids,
            "diversity_deferred_chunk_ids": [
                str(candidate["chunk_id"]) for candidate in diversity_deferred
            ],
            "diversity_applied": (
                selected_ids
                != [
                    str(candidate["chunk_id"])
                    for candidate in fused[:n_results]
                ]
            ),
            "discarded": discarded,
            "raw_primary_fallback_used": raw_primary_fallback,
            "raw_primary_fallback_detected": raw_primary_fallback_detected,
            "fusion_pool_fallback_used": semantic_fallback,
            "document_distribution": {
                "semantic": _document_distribution(semantic_trace),
                "lexical": _document_distribution(lexical_trace),
                "selected_primary": _document_distribution(
                    [_safe_chunk_fields(candidate["chunk"]) for candidate in selected]
                ),
                "context": {},
            },
            "context": [],
        },
    }

    raw = deepcopy(dict(semantic_results))
    for key in ("ids", "metadatas", "distances"):
        batch = _first_batch(semantic_results, key)
        if batch or key in semantic_results:
            raw[key] = [batch[:n_results]]
    raw["hybrid"] = {
        "primary_chunk_ids": selected_ids,
        "primary_candidates": [
            {
                "chunk_id": candidate["chunk_id"],
                "document": candidate["document"],
                "rrf_score": round(float(candidate["rrf_score"]), 12),
                "semantic_distance": candidate["semantic_distance"],
                "semantic_rank": candidate["semantic_rank"],
                "semantic_contributed": candidate["semantic_contributed"],
                "lexical_rank": candidate["lexical_rank"],
                "fused_rank": candidate["rank"],
            }
            for candidate in selected
        ],
        "trace": trace,
    }
    return raw


def _collection_hnsw_space(collection_handle: Any) -> str:
    configuration = getattr(collection_handle, "configuration", None)
    if isinstance(configuration, Mapping):
        hnsw = configuration.get("hnsw")
        if isinstance(hnsw, Mapping) and hnsw.get("space"):
            return str(hnsw["space"])
    metadata = getattr(collection_handle, "metadata", None)
    if isinstance(metadata, Mapping) and metadata.get("hnsw:space"):
        return str(metadata["hnsw:space"])
    return ""


def retrieve_from_collection(
    query: str,
    collection_handle: Any,
    chunks: list[dict[str, Any]],
    *,
    n_results: int = 5,
    embedding_client: OpenAI | None = None,
    corpus: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one embedding request, a local semantic pool, and deterministic fusion."""
    if n_results <= 0:
        raise ValueError("n_results must be greater than zero")
    collection_count = int(collection_handle.count())
    semantic_results = retrieve_semantic_from_collection(
        query,
        collection_handle,
        n_results=max(SEMANTIC_CANDIDATE_LIMIT, n_results),
        embedding_client=embedding_client,
    )
    corpus_trace = dict(corpus or {})
    corpus_trace.setdefault("collection_count", collection_count)
    hnsw_space = _collection_hnsw_space(collection_handle)
    if hnsw_space:
        corpus_trace.setdefault("hnsw_space", hnsw_space)
    return build_hybrid_results(
        query,
        semantic_results,
        chunks,
        n_results=n_results,
        corpus=corpus_trace,
    )


def _plan_value(item: object, field: str, default: object = None) -> object:
    if isinstance(item, Mapping):
        return item.get(field, default)
    return getattr(item, field, default)


def _facet_priority(facet: object) -> tuple[int, str]:
    role = str(_plan_value(facet, "role", ""))
    facet_id = str(_plan_value(facet, "facet_id", ""))
    priorities = {
        "original": 0,
        "premise_support": 1,
        "premise_counter": 1,
        "framing": 1,
    }
    return priorities.get(role, 2), facet_id


_BROAD_STAGE_BANDS = {
    "origin": ("early", 0),
    "transition": ("middle", 1),
    "mechanism": ("middle", 1),
    "endpoint": ("late", 2),
}
_BOUNDED_RELATED_FALLBACK_ROLES = frozenset(
    {"broader_related", "endpoint", "mechanism", "origin", "transition"}
)
_BROAD_STAGE_ROLES = frozenset(
    {"endpoint", "mechanism", "origin", "transition"}
)
BROAD_STAGE_OVERLAP_DOCUMENTS = 2
_BROAD_MECHANISM_QUERY_SUFFIXES = {
    "origin": (
        (
            "origin precedent emergence pattern recurrence expansion enforcement "
            "administration finance private interests"
        ),
    ),
    "transition": (
        "cause mechanism finance debt tax consolidation",
        (
            "policy doctrine strategy program budget deficit finance permanent "
            "military spending alliance bases"
        ),
    ),
    "mechanism": (
        "cause mechanism finance debt tax consolidation",
        (
            "policy doctrine strategy program budget deficit finance permanent "
            "military spending alliance bases"
        ),
    ),
    "endpoint": (
        (
            "persistence transformation continuation adaptation retirement replacement "
            "aftermath legacy"
        ),
        (
            "institution alliance authority finance budget spending employment "
            "industry security dilemma"
        ),
    ),
}
_BROAD_MECHANISM_SIGNAL_PATTERNS = {
    "causal": re.compile(
        r"\b(?:because|since|thereby|enable\w*|allow\w*|drive\w*|drove|"
        r"lead\w*|led|result\w*|consequen\w*|mechanism\w*|through|"
        r"require\w*)\b",
        flags=re.IGNORECASE,
    ),
    "institutional": re.compile(
        r"\b(?:law\w*|act\w*|institution\w*|agency|agencies|department\w*|"
        r"council\w*|government\w*|administration\w*|authorit\w*|"
        r"bureaucr\w*|congress\w*|bank\w*|alliance\w*|military)\b",
        flags=re.IGNORECASE,
    ),
    "fiscal": re.compile(
        r"\b(?:financ\w*|debt\w*|tax\w*|budget\w*|deficit\w*|spend\w*|"
        r"credit\w*|bond\w*|employ\w*|industr\w*|contract\w*|profit\w*)\b",
        flags=re.IGNORECASE,
    ),
    "persistence": re.compile(
        r"\b(?:permanent\w*|indefinite\w*|persist\w*|continu\w*|"
        r"transform\w*|retain\w*|retire\w*|remain\w*|maintain\w*|"
        r"normaliz\w*|establish\w*|adapt\w*|replace\w*)\b",
        flags=re.IGNORECASE,
    ),
}
_BROAD_CANONICAL_POSITION_VOCABULARY = {
    "origin": "earliest origin emergence precedent formation",
    "early": "early development expansion institution formation",
    "middle": "middle mechanism consolidation finance administration",
    "late": "later transformation normalization persistence institution",
    "endpoint": "latest endpoint consequence persistence transformation legacy",
}
_BROAD_CANONICAL_ROLE_VOCABULARY = {
    "origin": "origin precedent emergence",
    "transition": "transition development change",
    "mechanism": "mechanism cause finance institution administration",
    "endpoint": "endpoint persistence transformation legacy",
}
_BROAD_STAGE_INTENT_GENERIC_TERMS = frozenset(
    {
        "development",
        "developments",
        "distinct",
        "early",
        "endpoint",
        "function",
        "historical",
        "history",
        "late",
        "lineage",
        "mechanism",
        "middle",
        "narrative",
        "origin",
        "period",
        "provider",
        "role",
        "stage",
        "trace",
        "transition",
        "wording",
    }
)
_LINEAGE_HANDOFF_STRUCTURAL_TERMS = frozenset(
    {
        "capacity",
        "handoff",
        "inherited",
        "inherits",
        "institution",
        "institutional",
        "mechanism",
        "outgoing",
        "power",
        "powers",
        "authority",
        "stage",
        "transfer",
        "transfers",
    }
)
_BROAD_STAGE_ROLE_SIGNAL_PATTERNS = {
    "origin": re.compile(
        r"\b(?:begin\w*|began|creat\w*|emerg\w*|establish\w*|first|"
        r"form\w*|found\w*|initial\w*|origin\w*|precedent\w*|"
        r"because|thereby|enable\w*|allow\w*)\b",
        flags=re.IGNORECASE,
    ),
    "transition": re.compile(
        r"\b(?:became|chang\w*|consolidat\w*|expand\w*|reorganiz\w*|"
        r"replac\w*|shift\w*|transition\w*|transform\w*|because|"
        r"thereby|enable\w*|allow\w*|lead\w*|led|result\w*|"
        r"financ\w*|debt\w*|tax\w*|budget\w*|credit\w*)\b",
        flags=re.IGNORECASE,
    ),
    "mechanism": re.compile(
        r"\b(?:administ\w*|because|contract\w*|credit\w*|debt\w*|"
        r"enable\w*|allow\w*|enforc\w*|financ\w*|implement\w*|"
        r"institut\w*|require\w*|tax\w*|thereby|through|budget\w*)\b",
        flags=re.IGNORECASE,
    ),
    "endpoint": re.compile(
        r"\b(?:adapt\w*|aftermath\w*|consequen\w*|continu\w*|end\w*|"
        r"legacy|normaliz\w*|permanent\w*|persist\w*|remain\w*|"
        r"replac\w*|retain\w*|retire\w*|transform\w*|result\w*|led)\b",
        flags=re.IGNORECASE,
    ),
}
_BROAD_TRANSITION_SIGNAL_PATTERN = re.compile(
    r"\b(?:"
    r"because|thereby|therefore|thus|enable\w*|allow\w*|lead\w*\s+to|led\s+to|"
    r"result\w*\s+(?:in|from)|gave\s+rise\s+to|grew\s+into|evolv\w*\s+into|"
    r"became|chang\w*\s+into|consolidat\w*|continu\w*|depart\w*\s+from|"
    r"develop\w*\s+into|institutionali[sz]\w*|reorganiz\w*|replac\w*|"
    r"shift\w*\s+(?:into|toward|to)|transform\w*|absorb\w*|carry\w*\s+(?:on|forward)"
    r")\b",
    flags=re.IGNORECASE,
)
_BROAD_TRANSITION_QUERY_VOCABULARY = (
    "causal institutional connection transition continuity transformation "
    "replacement consolidation led resulted enabled"
)
_NUMBERED_CHAPTER_ONE_PATTERN = re.compile(r"\bchapter\s+1\b")
_NARRATIVE_ENDPOINT_PATTERN = re.compile(r"\b(?:conclusion|epilogue)\b")
_SUPPLEMENTAL_BACK_MATTER_PATTERN = re.compile(
    r"\b(?:acknowledg(?:e)?ments?|afterword|appendix|bibliograph(?:y|ies)|"
    r"credits?|index|notes?|works\s+consulted)\b"
)


def _eligible_document_ordinals(
    chunks: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, ...], dict[str, int]]:
    documents: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        document = str(chunk.get("document") or "")
        if not document or document in seen or should_skip_document(document):
            continue
        seen.add(document)
        documents.append(document)
    return tuple(documents), {
        document: ordinal for ordinal, document in enumerate(documents)
    }


def _document_structure_label(document: str) -> str:
    normalized = unicodedata.normalize("NFKD", document).casefold()
    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def _broad_narrative_documents(documents: Sequence[str]) -> tuple[str, ...]:
    """Prefer the numbered narrative body over front and supplemental matter."""

    if not documents:
        return ()
    labels = [_document_structure_label(document) for document in documents]
    chapter_one_indices = [
        index
        for index, label in enumerate(labels)
        if _NUMBERED_CHAPTER_ONE_PATTERN.search(label) is not None
    ]
    start = chapter_one_indices[0] if chapter_one_indices else 0
    supplemental_indices = [
        index
        for index, label in enumerate(labels[start:], start=start)
        if _SUPPLEMENTAL_BACK_MATTER_PATTERN.search(label) is not None
    ]
    supplemental_start = (
        supplemental_indices[0] if supplemental_indices else len(documents)
    )
    endpoint_indices = [
        index
        for index, label in enumerate(labels[start:supplemental_start], start=start)
        if _NARRATIVE_ENDPOINT_PATTERN.search(label) is not None
    ]
    end = (
        endpoint_indices[-1] + 1
        if endpoint_indices
        else supplemental_start
    )
    selected = tuple(documents[start:end])
    return selected or tuple(documents)


def _broad_stage_positions(
    facets: Sequence[object],
    requirements: Sequence[object],
) -> dict[str, tuple[int, int]]:
    requirement_order = {
        str(_plan_value(requirement, "requirement_id", "")): int(
            _plan_value(requirement, "order", 0)
        )
        for requirement in requirements
        if str(_plan_value(requirement, "requirement_id", ""))
    }
    dedicated = [
        facet
        for facet in facets
        if str(_plan_value(facet, "role", "")) in _BROAD_STAGE_ROLES
        and len(tuple(_plan_value(facet, "requirement_ids", ()) or ())) == 1
        and str(tuple(_plan_value(facet, "requirement_ids", ()) or ())[0])
        in requirement_order
    ]
    dedicated.sort(
        key=lambda facet: (
            requirement_order[
                str(tuple(_plan_value(facet, "requirement_ids", ()) or ())[0])
            ],
            str(_plan_value(facet, "facet_id", "")),
        )
    )
    count = len(dedicated)
    return {
        str(_plan_value(facet, "facet_id", "")): (index, count)
        for index, facet in enumerate(dedicated)
    }


def _broad_stage_scope(
    role: str,
    documents: Sequence[str],
    *,
    stage_index: int | None = None,
    stage_count: int | None = None,
    narrative_span: bool = False,
) -> tuple[tuple[str, ...], str, int | None, int | None]:
    if role not in _BROAD_STAGE_ROLES or not documents:
        return (), "none", None, None
    narrative_documents = _broad_narrative_documents(documents)
    if (
        narrative_span
        and stage_index is not None
        and stage_count == BROAD_NARRATIVE_SPAN_STAGE_REQUIREMENTS
        and 0 <= stage_index < stage_count
    ):
        structural_bands = narrative_span_document_bands(
            documents,
            structure_text=str,
            stage_count=stage_count,
        )
        if (
            len(structural_bands) == stage_count
            and structural_bands[stage_index]
        ):
            structural_documents = tuple(
                document
                for band in structural_bands
                for document in band
            )
            structural_ordinal = {
                document: ordinal
                for ordinal, document in enumerate(structural_documents)
            }
            core_ordinals = [
                structural_ordinal[document]
                for document in structural_bands[stage_index]
            ]
            selected_start = max(
                0,
                core_ordinals[0] - BROAD_STAGE_OVERLAP_DOCUMENTS,
            )
            selected_end = min(
                len(structural_documents) - 1,
                core_ordinals[-1] + BROAD_STAGE_OVERLAP_DOCUMENTS,
            )
            selected = structural_documents[selected_start : selected_end + 1]
            ordinal_by_document = {
                document: ordinal
                for ordinal, document in enumerate(documents)
            }
            label = (
                "early"
                if stage_index == 0
                else "late"
                if stage_index == stage_count - 1
                else "middle"
            )
            return (
                selected,
                label,
                ordinal_by_document[selected[0]],
                ordinal_by_document[selected[-1]],
            )
    if (
        stage_index is not None
        and stage_count is not None
        and stage_count >= 3
        and 0 <= stage_index < stage_count
    ):
        label = (
            "early"
            if stage_index == 0
            else "late"
            if stage_index == stage_count - 1
            else "middle"
        )
        target_band = stage_index
        band_count = stage_count
    else:
        stage = _BROAD_STAGE_BANDS.get(role)
        if stage is None:
            return (), "none", None, None
        label, target_band = stage
        band_count = 3
    count = len(narrative_documents)
    selected_ordinals = [
        ordinal
        for ordinal in range(count)
        if min(
            band_count - 1,
            (band_count * ordinal) // count,
        )
        == target_band
    ]
    if (
        stage_index is not None
        and stage_count is not None
        and selected_ordinals
    ):
        selected_start = max(
            0,
            selected_ordinals[0] - BROAD_STAGE_OVERLAP_DOCUMENTS,
        )
        selected_end = min(
            count - 1,
            selected_ordinals[-1] + BROAD_STAGE_OVERLAP_DOCUMENTS,
        )
        selected_ordinals = list(range(selected_start, selected_end + 1))
    selected = tuple(
        narrative_documents[ordinal] for ordinal in selected_ordinals
    )
    if not selected:
        return (), label, None, None
    ordinal_by_document = {
        document: ordinal for ordinal, document in enumerate(documents)
    }
    return (
        selected,
        label,
        ordinal_by_document[selected[0]],
        ordinal_by_document[selected[-1]],
    )


def _broad_structural_anchor_scope(
    documents: Sequence[str],
    *,
    stage_index: int | None,
    stage_count: int | None,
    narrative_span: bool,
) -> tuple[str, ...]:
    """Return the non-overlapping core eligible for a protected stage anchor."""

    if not narrative_span:
        return ()
    if (
        stage_index is None
        or stage_count != BROAD_NARRATIVE_SPAN_STAGE_REQUIREMENTS
        or not 0 <= stage_index < stage_count
    ):
        return ()
    bands = narrative_span_document_bands(
        documents,
        structure_text=str,
        stage_count=stage_count,
    )
    if len(bands) != stage_count:
        return ()
    return tuple(bands[stage_index])


def _broad_canonical_position_label(
    role: str,
    stage_position: tuple[int, int] | None,
) -> str:
    if stage_position is None:
        if role == "origin":
            return "origin"
        if role == "endpoint":
            return "endpoint"
        return "middle"

    stage_index, stage_count = stage_position
    if stage_index == 0:
        return "origin"
    if stage_index == stage_count - 1:
        return "endpoint"

    interior_count = max(stage_count - 2, 1)
    if interior_count == 1:
        return "middle"
    interior_index = stage_index - 1
    bucket = min(2, (3 * interior_index) // interior_count)
    return ("early", "middle", "late")[bucket]


def _broad_canonical_execution_query(
    original_query: str,
    role: str,
    stage_position: tuple[int, int] | None,
) -> str:
    """Build the application-owned query for one protected broad stage.

    Provider wording remains useful as a supplemental route, but it must not
    decide which source represents the stage's protected core.
    """

    position = _broad_canonical_position_label(role, stage_position)
    return " ".join(
        (
            original_query,
            _BROAD_CANONICAL_POSITION_VOCABULARY[position],
            _BROAD_CANONICAL_ROLE_VOCABULARY[role],
        )
    ).strip()


def _empty_semantic_results() -> dict[str, list[list[object]]]:
    return {"ids": [[]], "metadatas": [[]], "distances": [[]]}


def _semantic_lane_query(
    collection_handle: Any,
    embedding: list[float],
    *,
    candidate_count: int,
    document_hints: tuple[str, ...],
) -> dict[str, Any]:
    if candidate_count <= 0:
        return _empty_semantic_results()
    request: dict[str, Any] = {
        "query_embeddings": [embedding],
        "n_results": candidate_count,
        "include": ["metadatas", "distances"],
    }
    if document_hints:
        request["where"] = (
            {"document": document_hints[0]}
            if len(document_hints) == 1
            else {"document": {"$in": list(document_hints)}}
        )
    return collection_handle.query(**request)


def _pick_first_lane_candidate(
    candidates: list[dict[str, Any]],
    *,
    selected_ids: set[str],
    selected_documents: set[str],
    prefer_new_document: bool,
) -> dict[str, Any] | None:
    available = [
        candidate
        for candidate in candidates
        if str(candidate.get("chunk_id") or "") not in selected_ids
    ]
    if not available:
        return None
    if not prefer_new_document:
        return available[0]

    strongest = float(available[0].get("rrf_score") or 0.0)
    for candidate in available:
        document = str(candidate.get("document") or "")
        score = float(candidate.get("rrf_score") or 0.0)
        if (
            document not in selected_documents
            and (strongest <= 0.0 or score >= strongest * DIVERSITY_MIN_SCORE_RATIO)
        ):
            return candidate
    return available[0]


def _ranked_broad_supplemental_options(
    lanes: Sequence[Mapping[str, Any]],
    *,
    document_ordinal_by_id: Mapping[str, int],
) -> list[dict[str, Any]]:
    """Aggregate all non-anchor candidates without favoring an early lane.

    Rank aggregation makes canonical/provider agreement useful while keeping
    unlike semantic and lexical score scales out of the cross-lane comparison.
    """

    by_chunk_id: dict[str, dict[str, Any]] = {}
    for lane in lanes:
        facet_id = str(lane["facet_id"])
        candidate_pools = (
            lane.get("canonical_core_candidates", ()),
            lane.get("mechanism_candidates", ()),
            lane.get("candidates", ()),
        )
        for candidates in candidate_pools:
            for rank, candidate in enumerate(candidates, start=1):
                chunk_id = str(candidate.get("chunk_id") or "")
                if not chunk_id:
                    continue
                entry = by_chunk_id.setdefault(
                    chunk_id,
                    {
                        "candidate": candidate,
                        "facet_ids": set(),
                        "rank_utility": 0.0,
                        "pool_hit_count": 0,
                        "best_rank": rank,
                    },
                )
                entry["facet_ids"].add(facet_id)
                entry["rank_utility"] += 1.0 / (RRF_K + rank)
                entry["pool_hit_count"] += 1
                entry["best_rank"] = min(int(entry["best_rank"]), rank)

    options: list[dict[str, Any]] = []
    for chunk_id, entry in by_chunk_id.items():
        candidate = entry["candidate"]
        document = str(candidate.get("document") or "")
        options.append(
            {
                "candidate": candidate,
                "chunk_id": chunk_id,
                "document": document,
                "document_ordinal": document_ordinal_by_id.get(document, 10**9),
                "facet_ids": tuple(sorted(entry["facet_ids"])),
                "rank_utility": float(entry["rank_utility"]),
                "pool_hit_count": int(entry["pool_hit_count"]),
                "best_rank": int(entry["best_rank"]),
            }
        )
    options.sort(
        key=lambda option: (
            -float(option["rank_utility"]),
            -int(option["pool_hit_count"]),
            int(option["best_rank"]),
            int(option["document_ordinal"]),
            str(option["chunk_id"]),
        )
    )
    return options


def _broad_stage_intent_query(
    facet: object,
    requirement_by_id: Mapping[str, object],
) -> str:
    """Return the planned historical function used to qualify a stage anchor."""

    requirements = [
        requirement_by_id.get(requirement_id)
        for requirement_id in tuple(
            _plan_value(facet, "requirement_ids", ()) or ()
        )
    ]
    labels = [
        str(_plan_value(requirement, "label", "")).strip()
        for requirement in requirements
    ]
    handoff_parts: list[str] = []
    for requirement in requirements:
        handoff = _plan_value(
            requirement,
            "institutional_handoff",
            None,
        )
        if handoff is None:
            continue
        handoff_parts.extend(
            str(_plan_value(handoff, field, "")).strip()
            for field in (
                "bearer",
                "inherited_capacity",
                "transfer_mechanism",
                "outgoing_capacity",
            )
        )
    parts = [
        *[label for label in labels if label],
        *[part for part in handoff_parts if part],
        str(_plan_value(facet, "search_query", "")).strip(),
    ]
    return " ".join(dict.fromkeys(part for part in parts if part))


def _lineage_handoff_term_groups(
    handoff: object | None,
) -> tuple[frozenset[str], frozenset[str]]:
    if handoff is None:
        return frozenset(), frozenset()
    bearer_terms = frozenset(
        term
        for term in _query_terms(
            str(_plan_value(handoff, "bearer", ""))
        )
        if term not in _LINEAGE_HANDOFF_STRUCTURAL_TERMS
    )
    handoff_terms = frozenset(
        term
        for term in _query_terms(
            " ".join(
                str(_plan_value(handoff, field, ""))
                for field in (
                    "inherited_capacity",
                    "transfer_mechanism",
                    "outgoing_capacity",
                )
            )
        )
        if term not in _LINEAGE_HANDOFF_STRUCTURAL_TERMS
    )
    return bearer_terms, handoff_terms


def _broad_stage_anchor_eligibility(
    chunk: Mapping[str, Any] | None,
    *,
    original_query: str,
    stage_intent_query: str,
    role: str,
    institutional_handoff: object | None = None,
) -> dict[str, Any]:
    """Qualify an anchor by stage-specific intent before route consensus."""

    intent_terms, distinctive_terms = _broad_stage_intent_terms(
        original_query,
        stage_intent_query,
    )
    chunk_terms = (
        frozenset(_tokens(str(chunk.get("text") or "")))
        if chunk is not None
        else frozenset()
    )
    intent_match_count = len(intent_terms & chunk_terms)
    distinctive_match_count = len(distinctive_terms & chunk_terms)
    role_pattern = _BROAD_STAGE_ROLE_SIGNAL_PATTERNS.get(role)
    role_signal_score = (
        len(role_pattern.findall(str(chunk.get("text") or "")))
        if chunk is not None and role_pattern is not None
        else 0
    )
    required_distinctive_match_count = (
        min(2, len(distinctive_terms)) if distinctive_terms else 0
    )
    bearer_terms, handoff_terms = _lineage_handoff_term_groups(
        institutional_handoff
    )
    bearer_match_count = len(bearer_terms & chunk_terms)
    handoff_match_count = len(handoff_terms & chunk_terms)

    if chunk is None:
        eligibility = "missing_chunk"
    elif not distinctive_terms:
        eligibility = "no_distinctive_stage_anchor"
    elif distinctive_match_count < required_distinctive_match_count:
        eligibility = "insufficient_distinctive_stage_anchor_match"
    elif institutional_handoff is not None and bearer_match_count <= 0:
        eligibility = "no_institutional_bearer_match"
    elif institutional_handoff is not None and handoff_match_count <= 0:
        eligibility = "no_institutional_handoff_match"
    elif role_signal_score <= 0:
        eligibility = "no_role_signal"
    else:
        eligibility = "eligible"

    return {
        "stage_anchor_eligible": eligibility == "eligible",
        "stage_anchor_eligibility": eligibility,
        "stage_intent_match_count": intent_match_count,
        "stage_distinctive_intent_match_count": distinctive_match_count,
        "stage_role_signal_score": role_signal_score,
        "stage_intent_term_count": len(intent_terms),
        "stage_distinctive_intent_term_count": len(distinctive_terms),
        "stage_required_distinctive_intent_match_count": (
            required_distinctive_match_count
        ),
    }


def _broad_stage_intent_terms(
    original_query: str,
    stage_intent_query: str,
) -> tuple[frozenset[str], frozenset[str]]:
    intent_terms = frozenset(_query_terms(stage_intent_query))
    original_terms = frozenset(_query_terms(original_query))
    distinctive_terms = frozenset(
        term
        for term in intent_terms - original_terms
        if term not in _BROAD_STAGE_INTENT_GENERIC_TERMS
    )
    return intent_terms, distinctive_terms


def _broad_transition_query(
    predecessor_intent_query: str,
    successor_intent_query: str,
) -> str:
    """Build a neutral adjacent-stage query without asserting a connection."""

    return " ".join(
        part
        for part in (
            predecessor_intent_query.strip(),
            successor_intent_query.strip(),
            _BROAD_TRANSITION_QUERY_VOCABULARY,
        )
        if part
    )


def _ranked_broad_transition_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    chunk_by_id: Mapping[str, Mapping[str, Any]],
    original_query: str,
    predecessor_intent_query: str,
    successor_intent_query: str,
) -> list[dict[str, Any]]:
    """Require both adjacent stage intents and an explicit transition signal."""

    predecessor_intent, predecessor_distinctive = _broad_stage_intent_terms(
        original_query,
        predecessor_intent_query,
    )
    successor_intent, successor_distinctive = _broad_stage_intent_terms(
        original_query,
        successor_intent_query,
    )
    predecessor_base_terms = predecessor_distinctive or predecessor_intent
    successor_base_terms = successor_distinctive or successor_intent
    predecessor_exclusive_terms = (
        predecessor_base_terms - successor_base_terms
    )
    successor_exclusive_terms = (
        successor_base_terms - predecessor_base_terms
    )
    predecessor_terms = (
        predecessor_exclusive_terms or predecessor_base_terms
    )
    successor_terms = successor_exclusive_terms or successor_base_terms
    shared_handoff_terms = frozenset(
        term
        for term in predecessor_base_terms & successor_base_terms
        if term not in _LINEAGE_HANDOFF_STRUCTURAL_TERMS
    )
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        chunk_id = str(candidate.get("chunk_id") or "")
        chunk = chunk_by_id.get(chunk_id)
        chunk_text = str(chunk.get("text") or "") if chunk is not None else ""
        chunk_terms = frozenset(_tokens(chunk_text))
        predecessor_match_count = len(predecessor_terms & chunk_terms)
        successor_match_count = len(successor_terms & chunk_terms)
        shared_handoff_match_count = len(
            shared_handoff_terms & chunk_terms
        )
        transition_signal_score = len(
            _BROAD_TRANSITION_SIGNAL_PATTERN.findall(chunk_text)
        )
        if chunk is None:
            eligibility = "missing_chunk"
        elif not predecessor_terms:
            eligibility = "no_predecessor_stage_intent"
        elif not successor_terms:
            eligibility = "no_successor_stage_intent"
        elif predecessor_match_count <= 0:
            eligibility = "no_predecessor_stage_intent_match"
        elif successor_match_count <= 0:
            eligibility = "no_successor_stage_intent_match"
        elif shared_handoff_terms and shared_handoff_match_count <= 0:
            eligibility = "no_handoff_capacity_match"
        elif transition_signal_score <= 0:
            eligibility = "no_transition_signal"
        else:
            eligibility = "eligible"
        ranked.append(
            {
                **candidate,
                "chunk_id": chunk_id,
                "transition_eligible": eligibility == "eligible",
                "transition_eligibility": eligibility,
                "predecessor_intent_match_count": predecessor_match_count,
                "successor_intent_match_count": successor_match_count,
                "transition_signal_score": transition_signal_score,
            }
        )

    ranked.sort(
        key=lambda candidate: (
            0 if bool(candidate["transition_eligible"]) else 1,
            -min(
                int(candidate["predecessor_intent_match_count"]),
                int(candidate["successor_intent_match_count"]),
            ),
            -(
                int(candidate["predecessor_intent_match_count"])
                + int(candidate["successor_intent_match_count"])
            ),
            -int(candidate["transition_signal_score"]),
            -float(candidate.get("rrf_score") or 0.0),
            int(candidate.get("rank") or 10**9),
            str(candidate["chunk_id"]),
        )
    )
    return ranked


def _ranked_broad_stage_anchor_candidates(
    lane: Mapping[str, Any],
    *,
    document_ordinal_by_id: Mapping[str, int],
    chunk_by_id: Mapping[str, Mapping[str, Any]],
    original_query: str,
    stage_intent_query: str,
    role: str,
) -> list[dict[str, Any]]:
    """Rank eligible protected anchors by agreement across three routes.

    Canonical, mechanism, and provider-relevance ranks are deliberately kept
    as independent votes. Stage-intent and historical-role eligibility is an
    earlier hard boundary: consensus can rank candidates only inside it.
    """

    candidate_pools = (
        ("canonical", lane.get("canonical_core_candidates", ())),
        ("mechanism", lane.get("mechanism_candidates", ())),
        ("provider", lane.get("candidates", ())),
    )
    by_chunk_id: dict[str, dict[str, Any]] = {}
    for pool_name, candidates in candidate_pools:
        for rank, candidate in enumerate(candidates, start=1):
            chunk_id = str(candidate.get("chunk_id") or "")
            if not chunk_id:
                continue
            entry = by_chunk_id.setdefault(
                chunk_id,
                {
                    "candidate": candidate,
                    "pool_ranks": {},
                    "rank_utility": 0.0,
                    "best_rank": rank,
                },
            )
            pool_ranks = entry["pool_ranks"]
            if pool_name in pool_ranks:
                continue
            pool_ranks[pool_name] = rank
            entry["rank_utility"] += 1.0 / (RRF_K + rank)
            entry["best_rank"] = min(int(entry["best_rank"]), rank)

    ranked: list[dict[str, Any]] = []
    for chunk_id, entry in by_chunk_id.items():
        candidate = entry["candidate"]
        document = str(candidate.get("document") or "")
        pool_ranks = dict(entry["pool_ranks"])
        pool_names = tuple(
            pool_name
            for pool_name, _candidates in candidate_pools
            if pool_name in pool_ranks
        )
        fallback_pool_priority = min(
            (
                index
                for index, (pool_name, _candidates) in enumerate(
                    candidate_pools
                )
                if pool_name in pool_ranks
            ),
            default=len(candidate_pools),
        )
        fallback_pool_name = candidate_pools[fallback_pool_priority][0]
        fallback_rank = int(pool_ranks[fallback_pool_name])
        eligibility = _broad_stage_anchor_eligibility(
            chunk_by_id.get(chunk_id),
            original_query=original_query,
            stage_intent_query=stage_intent_query,
            role=role,
            institutional_handoff=lane.get("institutional_handoff"),
        )
        ranked.append(
            {
                **candidate,
                **eligibility,
                "chunk_id": chunk_id,
                "document": document,
                "rrf_score": float(entry["rank_utility"]),
                "anchor_pool_names": pool_names,
                "anchor_pool_ranks": pool_ranks,
                "anchor_pool_hit_count": len(pool_ranks),
                "anchor_best_rank": int(entry["best_rank"]),
                "anchor_fallback_pool_priority": fallback_pool_priority,
                "anchor_fallback_rank": fallback_rank,
                "anchor_document_ordinal": document_ordinal_by_id.get(
                    document,
                    10**9,
                ),
            }
        )

    ranked.sort(
        key=lambda candidate: (
            0 if bool(candidate["stage_anchor_eligible"]) else 1,
            0 if int(candidate["anchor_pool_hit_count"]) >= 2 else 1,
            (
                -int(candidate["anchor_pool_hit_count"])
                if int(candidate["anchor_pool_hit_count"]) >= 2
                else int(candidate["anchor_fallback_pool_priority"])
            ),
            (
                -float(candidate["rrf_score"])
                if int(candidate["anchor_pool_hit_count"]) >= 2
                else int(candidate["anchor_fallback_rank"])
            ),
            int(candidate["anchor_best_rank"]),
            int(candidate["anchor_document_ordinal"]),
            str(candidate["chunk_id"]),
        )
    )
    return ranked


def _broad_mechanism_queries(query: str, role: str) -> tuple[str, ...]:
    suffixes = _BROAD_MECHANISM_QUERY_SUFFIXES.get(role, ())
    return tuple(f"{query} {suffix}".strip() for suffix in suffixes)


def _broad_mechanism_signal_score(
    chunk: Mapping[str, Any],
    *,
    role: str,
) -> int:
    text = str(chunk.get("text") or "")
    counts = {
        name: len(pattern.findall(text))
        for name, pattern in _BROAD_MECHANISM_SIGNAL_PATTERNS.items()
    }
    causal = min(counts["causal"], 3)
    institutional = min(counts["institutional"], 2)
    fiscal = min(counts["fiscal"], 3)
    persistence = min(counts["persistence"], 3)
    if role == "origin":
        return causal * 2 + institutional + fiscal + persistence
    if role == "endpoint":
        return persistence * 2 + causal + institutional + fiscal
    return causal * 2 + fiscal * 2 + institutional + persistence


def _broad_mechanism_candidates(
    query: str,
    role: str,
    chunks: list[dict[str, Any]],
    primary_candidates: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """Rerank a bounded stage locally for explicit historical mechanisms.

    Semantic retrieval still establishes relevance. This pass adds a deterministic
    lexical route over planner-hinted documents and favors passages that state how
    power was financed, institutionalized, implemented, or preserved.
    """

    mechanism_queries = _broad_mechanism_queries(query, role)
    if not mechanism_queries or not chunks:
        return [], ()

    lookup = build_chunk_lookup(chunks)
    primary_by_id = {
        str(candidate.get("chunk_id") or ""): (rank, candidate)
        for rank, candidate in enumerate(primary_candidates, start=1)
        if str(candidate.get("chunk_id") or "") in lookup
    }
    original_query_terms = frozenset(_query_terms(query))
    lexical_by_id: dict[str, dict[str, Any]] = {}
    for mechanism_query in mechanism_queries:
        lexical, diagnostics = lexical_candidates(
            mechanism_query,
            chunks,
            limit=BROAD_MECHANISM_CANDIDATE_LIMIT,
        )
        query_term_count = max(int(diagnostics["query_term_count"]), 1)
        for candidate in lexical:
            chunk_id = str(candidate.get("chunk_id") or "")
            chunk = lookup.get(chunk_id)
            if chunk is None:
                continue
            original_query_match_count = len(
                original_query_terms.intersection(
                    _tokens(str(chunk.get("text") or ""))
                )
            )
            if original_query_match_count <= 0:
                continue
            mechanism_signal_score = _broad_mechanism_signal_score(
                chunk,
                role=role,
            )
            normalized_lexical_score = (
                float(candidate["score"]) / query_term_count
            )
            mechanism_utility_score = normalized_lexical_score * (
                1.0 + 0.02 * mechanism_signal_score
            )
            existing = lexical_by_id.get(chunk_id)
            if existing is None or mechanism_utility_score > float(
                existing["mechanism_utility_score"]
            ):
                lexical_by_id[chunk_id] = {
                    "lexical_rank": int(candidate["rank"]),
                    "original_query_match_count": original_query_match_count,
                    "mechanism_signal_score": mechanism_signal_score,
                    "mechanism_utility_score": mechanism_utility_score,
                }
    # The provider-relevance pool already carries semantic primaries. Keeping
    # primary-only candidates here would give every provider result a second,
    # artificial "mechanism" vote during broad-stage consensus. This pool is
    # therefore limited to candidates independently found by the bounded
    # lexical mechanism route; semantic rank remains available as a tie-break.
    candidate_ids = set(lexical_by_id)
    ranked: list[dict[str, Any]] = []
    for chunk_id in candidate_ids:
        chunk = lookup[chunk_id]
        primary_entry = primary_by_id.get(chunk_id)
        lexical_entry = lexical_by_id.get(chunk_id)
        primary_rank = primary_entry[0] if primary_entry else None
        lexical_rank = (
            int(lexical_entry["lexical_rank"])
            if lexical_entry is not None
            else None
        )
        mechanism_signal_score = (
            int(lexical_entry["mechanism_signal_score"])
            if lexical_entry is not None
            else _broad_mechanism_signal_score(chunk, role=role)
        )
        mechanism_utility_score = (
            float(lexical_entry["mechanism_utility_score"])
            if lexical_entry is not None
            else 0.0
        )
        ranked.append(
            {
                "chunk_id": chunk_id,
                "document": str(chunk.get("document") or ""),
                "rrf_score": mechanism_utility_score,
                "mechanism_signal_score": mechanism_signal_score,
                "mechanism_utility_score": mechanism_utility_score,
                "original_query_match_count": (
                    int(lexical_entry["original_query_match_count"])
                    if lexical_entry is not None
                    else 0
                ),
                "primary_rank": primary_rank,
                "lexical_rank": lexical_rank,
            }
        )

    ranked.sort(
        key=lambda candidate: (
            -float(candidate["mechanism_utility_score"]),
            -int(candidate["original_query_match_count"]),
            -int(candidate["mechanism_signal_score"]),
            int(candidate["primary_rank"] or 10**9),
            int(candidate["lexical_rank"] or 10**9),
            str(candidate["chunk_id"]),
        )
    )
    return ranked[:BROAD_MECHANISM_CANDIDATE_LIMIT], mechanism_queries


def retrieve_plan_from_collection(
    plan: object,
    collection_handle: Any,
    chunks: list[dict[str, Any]],
    *,
    n_results: int = 5,
    embedding_client: OpenAI | None = None,
    corpus: Mapping[str, Any] | None = None,
    max_final_sources: int = MAX_FINAL_SOURCES,
) -> PlannedContext:
    """Retrieve a validated query plan through bounded lanes sharing one embedding call."""
    if n_results <= 0:
        raise ValueError("n_results must be greater than zero")
    if max_final_sources <= 0:
        raise ValueError("max_final_sources must be greater than zero")

    raw_facets = _plan_value(plan, "facets", ())
    facets = list(raw_facets) if isinstance(raw_facets, (list, tuple)) else []
    if not facets:
        raise ValueError("query plan must contain at least the original facet")
    original_facets = [
        facet for facet in facets if str(_plan_value(facet, "role", "")) == "original"
    ]
    if len(original_facets) != 1:
        raise ValueError("query plan must contain exactly one original facet")

    raw_traits = _plan_value(plan, "traits", ())
    traits = tuple(
        str(getattr(value, "value", value))
        for value in (raw_traits or ())
    )
    broad = "broad_synthesis" in traits
    long_lineage = "long_institutional_lineage" in traits
    absence_sensitive = "absence_sensitive" in traits
    document_order, document_ordinal_by_id = _eligible_document_ordinals(chunks)
    queries = [str(_plan_value(facet, "search_query", "")).strip() for facet in facets]
    if any(not query for query in queries):
        raise ValueError("query plan contains an empty search facet")
    original_query = str(
        _plan_value(original_facets[0], "search_query", "")
    ).strip()
    broad_narrative_span = (
        broad
        and not long_lineage
        and requires_broad_narrative_span(original_query)
    )
    requirements = tuple(_plan_value(plan, "requirements", ()) or ())
    requirement_by_id = {
        str(_plan_value(requirement, "requirement_id", "")): requirement
        for requirement in requirements
        if str(_plan_value(requirement, "requirement_id", ""))
    }
    lookup = build_chunk_lookup(chunks)
    broad_stage_positions = (
        _broad_stage_positions(facets, requirements) if broad else {}
    )
    broad_stage_facets = (
        sorted(
            (
                facet
                for facet in facets
                if str(_plan_value(facet, "role", "")) in _BROAD_STAGE_ROLES
            ),
            key=lambda facet: (
                broad_stage_positions.get(
                    str(_plan_value(facet, "facet_id", "")),
                    (10**9, 10**9),
                )[0],
                str(_plan_value(facet, "facet_id", "")),
            ),
        )
        if broad
        else []
    )
    canonical_query_specs: list[tuple[str, str]] = []
    if broad:
        for facet in broad_stage_facets:
            facet_id = str(_plan_value(facet, "facet_id", ""))
            role = str(_plan_value(facet, "role", ""))
            canonical_query_specs.append(
                (
                    facet_id,
                    _broad_canonical_execution_query(
                        original_query,
                        role,
                        broad_stage_positions.get(facet_id),
                    ),
                )
            )
    transition_query_specs: list[
        tuple[str, str, str, str, str]
    ] = []
    if broad:
        for predecessor, successor in zip(
            broad_stage_facets,
            broad_stage_facets[1:],
            strict=False,
        ):
            predecessor_facet_id = str(
                _plan_value(predecessor, "facet_id", "")
            )
            successor_facet_id = str(
                _plan_value(successor, "facet_id", "")
            )
            predecessor_intent_query = _broad_stage_intent_query(
                predecessor,
                requirement_by_id,
            )
            successor_intent_query = _broad_stage_intent_query(
                successor,
                requirement_by_id,
            )
            transition_query_specs.append(
                (
                    predecessor_facet_id,
                    successor_facet_id,
                    predecessor_intent_query,
                    successor_intent_query,
                    _broad_transition_query(
                        predecessor_intent_query,
                        successor_intent_query,
                    ),
                )
            )
    batched_queries = [
        *queries,
        *(query for _facet_id, query in canonical_query_specs),
        *(
            query
            for (
                _predecessor_facet_id,
                _successor_facet_id,
                _predecessor_intent_query,
                _successor_intent_query,
                query,
            ) in transition_query_specs
        ),
    ]
    batched_embeddings = embed_queries(
        batched_queries,
        embedding_client=embedding_client,
    )
    embeddings = batched_embeddings[: len(queries)]
    canonical_embedding_by_facet = {
        facet_id: embedding
        for (facet_id, _query), embedding in zip(
            canonical_query_specs,
            batched_embeddings[
                len(queries) : len(queries) + len(canonical_query_specs)
            ],
            strict=True,
        )
    }
    canonical_query_by_facet = dict(canonical_query_specs)
    transition_embedding_by_pair = {
        (predecessor_facet_id, successor_facet_id): embedding
        for (
            predecessor_facet_id,
            successor_facet_id,
            _predecessor_intent_query,
            _successor_intent_query,
            _query,
        ), embedding in zip(
            transition_query_specs,
            batched_embeddings[
                len(queries) + len(canonical_query_specs) :
            ],
            strict=True,
        )
    }
    collection_count = int(collection_handle.count())
    lane_primary_limit = (
        max_final_sources
        if broad
        else min(max(n_results, 3), max_final_sources)
    )
    candidate_count = min(collection_count, max(SEMANTIC_CANDIDATE_LIMIT, n_results))
    corpus_trace = dict(corpus or {})
    corpus_trace.setdefault("collection_count", collection_count)
    hnsw_space = _collection_hnsw_space(collection_handle)
    if hnsw_space:
        corpus_trace.setdefault("hnsw_space", hnsw_space)

    lanes: list[dict[str, Any]] = []
    for facet, query, embedding in zip(facets, queries, embeddings, strict=True):
        facet_id = str(_plan_value(facet, "facet_id", ""))
        role = str(_plan_value(facet, "role", ""))
        raw_hints = _plan_value(facet, "document_hints", ())
        document_hints = tuple(str(value) for value in (raw_hints or ()))
        stage_position = broad_stage_positions.get(facet_id)
        facet_requirement_ids = tuple(
            str(value)
            for value in (
                _plan_value(facet, "requirement_ids", ()) or ()
            )
        )
        institutional_handoff = (
            _plan_value(
                requirement_by_id.get(facet_requirement_ids[0]),
                "institutional_handoff",
                None,
            )
            if len(facet_requirement_ids) == 1
            else None
        )
        stage_intent_query = (
            _broad_stage_intent_query(facet, requirement_by_id)
            if broad and role in _BROAD_STAGE_ROLES
            else ""
        )
        stage_intent_terms, stage_distinctive_intent_terms = (
            _broad_stage_intent_terms(
                original_query,
                stage_intent_query,
            )
            if stage_intent_query
            else (frozenset(), frozenset())
        )
        (
            stage_scope,
            chronology_band,
            chronology_min_document_ordinal,
            chronology_max_document_ordinal,
        ) = (
            _broad_stage_scope(
                role,
                document_order,
                stage_index=(
                    broad_stage_positions[facet_id][0]
                    if facet_id in broad_stage_positions
                    else None
                ),
                stage_count=(
                    broad_stage_positions[facet_id][1]
                    if facet_id in broad_stage_positions
                    else None
                ),
                narrative_span=broad_narrative_span,
            )
            if broad
            else ((), "none", None, None)
        )
        structural_anchor_scope = (
            _broad_structural_anchor_scope(
                document_order,
                stage_index=(
                    broad_stage_positions[facet_id][0]
                    if facet_id in broad_stage_positions
                    else None
                ),
                stage_count=(
                    broad_stage_positions[facet_id][1]
                    if facet_id in broad_stage_positions
                    else None
                ),
                narrative_span=broad_narrative_span,
            )
            if broad and role in _BROAD_STAGE_ROLES
            else ()
        )
        if (
            long_lineage
            and role in _BROAD_STAGE_ROLES
            and document_hints
        ):
            hinted_stage_scope = tuple(
                document
                for document in document_order
                if document in set(document_hints)
            )
            if hinted_stage_scope:
                stage_scope = hinted_stage_scope
                hinted_ordinals = [
                    document_ordinal_by_id[document]
                    for document in hinted_stage_scope
                ]
                chronology_min_document_ordinal = min(hinted_ordinals)
                chronology_max_document_ordinal = max(hinted_ordinals)
        document_scope = stage_scope or document_hints
        lane_chunks = [
            chunk
            for chunk in chunks
            if not document_scope
            or str(chunk.get("document") or "") in document_scope
        ]
        semantic_results = (
            _semantic_lane_query(
                collection_handle,
                embedding,
                candidate_count=candidate_count,
                document_hints=document_scope,
            )
            if lane_chunks
            else _empty_semantic_results()
        )
        bounded_related_fallback = (
            absence_sensitive
            and facet_id != "F0"
            and bool(document_hints)
            and role in _BOUNDED_RELATED_FALLBACK_ROLES
        )
        allow_fallback = role == "original" or bounded_related_fallback
        results = build_hybrid_results(
            query,
            semantic_results,
            lane_chunks,
            n_results=lane_primary_limit,
            corpus=corpus_trace,
            allow_semantic_fallback=allow_fallback,
            retrieval_mode_override=("broad_synthesis" if broad else None),
            broad_max_per_document=(1 if broad else None),
        )
        hybrid = results.get("hybrid")
        primary_candidates = (
            list(hybrid.get("primary_candidates", []))
            if isinstance(hybrid, Mapping)
            else []
        )

        canonical_query = canonical_query_by_facet.get(facet_id)
        canonical_chunks = [
            chunk
            for chunk in chunks
            if str(chunk.get("document") or "") in stage_scope
        ]
        canonical_primary_candidates: list[dict[str, Any]] = []
        canonical_mechanism_candidates: list[dict[str, Any]] = []
        canonical_mechanism_queries: tuple[str, ...] = ()
        if canonical_query is not None and canonical_chunks:
            canonical_semantic_results = _semantic_lane_query(
                collection_handle,
                canonical_embedding_by_facet[facet_id],
                candidate_count=candidate_count,
                document_hints=stage_scope,
            )
            canonical_results = build_hybrid_results(
                canonical_query,
                canonical_semantic_results,
                canonical_chunks,
                n_results=lane_primary_limit,
                corpus=corpus_trace,
                allow_semantic_fallback=False,
                retrieval_mode_override="broad_synthesis",
                broad_max_per_document=1,
            )
            canonical_hybrid = canonical_results.get("hybrid")
            canonical_primary_candidates = (
                list(canonical_hybrid.get("primary_candidates", []))
                if isinstance(canonical_hybrid, Mapping)
                else []
            )
            (
                canonical_mechanism_candidates,
                canonical_mechanism_queries,
            ) = _broad_mechanism_candidates(
                canonical_query,
                role,
                canonical_chunks,
                canonical_primary_candidates,
            )
        canonical_core_candidates = (
            canonical_mechanism_candidates or canonical_primary_candidates
        )

        mechanism_scope = document_hints or stage_scope
        mechanism_chunks = [
            chunk
            for chunk in chunks
            if str(chunk.get("document") or "") in mechanism_scope
        ]
        mechanism_candidates, mechanism_queries = (
            _broad_mechanism_candidates(
                query,
                role,
                mechanism_chunks,
                primary_candidates,
            )
            if broad and role in _BROAD_STAGE_ROLES and mechanism_chunks
            else ([], ())
        )
        endpoint_anchor_candidates: list[dict[str, Any]] = []
        narrative_documents = _broad_narrative_documents(document_order)
        if (
            broad
            and role == "endpoint"
            and stage_position is not None
            and stage_position[0] == stage_position[1] - 1
            and narrative_documents
        ):
            endpoint_scope = (
                stage_scope
                if long_lineage and document_hints and stage_scope
                else (narrative_documents[-1],)
            )
            endpoint_chunks = [
                chunk
                for chunk in chunks
                if str(chunk.get("document") or "") in endpoint_scope
            ]
            endpoint_semantic_results = _semantic_lane_query(
                collection_handle,
                canonical_embedding_by_facet.get(facet_id, embedding),
                candidate_count=candidate_count,
                document_hints=endpoint_scope,
            )
            endpoint_results = build_hybrid_results(
                canonical_query or query,
                endpoint_semantic_results,
                endpoint_chunks,
                n_results=1,
                corpus=corpus_trace,
                allow_semantic_fallback=True,
                retrieval_mode_override="broad_synthesis",
                broad_max_per_document=1,
            )
            endpoint_hybrid = endpoint_results.get("hybrid")
            endpoint_anchor_candidates = (
                list(endpoint_hybrid.get("primary_candidates", []))
                if isinstance(endpoint_hybrid, Mapping)
                else []
            )
        lane_trace = hybrid.get("trace", {}) if isinstance(hybrid, Mapping) else {}
        lane = {
            "facet": facet,
            "facet_id": facet_id,
            "role": role,
            "query": query,
            "document_hints": document_hints,
            "stage_scope": stage_scope,
            "structural_anchor_scope": structural_anchor_scope,
            "chronology_band": chronology_band,
            "chronology_min_document_ordinal": chronology_min_document_ordinal,
            "chronology_max_document_ordinal": chronology_max_document_ordinal,
            "stage_position": stage_position,
            "institutional_handoff": institutional_handoff,
            "stage_intent_query": stage_intent_query,
            "stage_intent_term_count": len(stage_intent_terms),
            "stage_distinctive_intent_term_count": len(
                stage_distinctive_intent_terms
            ),
            "candidates": primary_candidates,
            "mechanism_candidates": mechanism_candidates,
            "mechanism_queries": mechanism_queries,
            "canonical_query": canonical_query,
            "canonical_primary_candidates": canonical_primary_candidates,
            "canonical_mechanism_candidates": canonical_mechanism_candidates,
            "canonical_mechanism_queries": canonical_mechanism_queries,
            "canonical_core_candidates": canonical_core_candidates,
            "endpoint_anchor_candidates": endpoint_anchor_candidates,
            "trace": lane_trace,
        }
        ranked_stage_anchor_candidates = (
            _ranked_broad_stage_anchor_candidates(
                lane,
                document_ordinal_by_id=document_ordinal_by_id,
                chunk_by_id=lookup,
                original_query=original_query,
                stage_intent_query=stage_intent_query,
                role=role,
            )
            if broad and role in _BROAD_STAGE_ROLES
            else []
        )
        if structural_anchor_scope:
            structural_anchor_documents = set(structural_anchor_scope)
            ranked_stage_anchor_candidates = [
                candidate
                for candidate in ranked_stage_anchor_candidates
                if str(
                    lookup.get(
                        str(candidate.get("chunk_id") or ""),
                        {},
                    ).get("document")
                    or ""
                )
                in structural_anchor_documents
            ]
        lane["stage_anchor_diagnostics"] = ranked_stage_anchor_candidates
        lane["stage_anchor_candidates"] = [
            candidate
            for candidate in ranked_stage_anchor_candidates
            if bool(candidate.get("stage_anchor_eligible"))
        ]
        lanes.append(lane)

    lane_by_facet_id = {
        str(lane["facet_id"]): lane for lane in lanes
    }
    transition_lanes: list[dict[str, Any]] = []
    for (
        predecessor_facet_id,
        successor_facet_id,
        predecessor_intent_query,
        successor_intent_query,
        transition_query,
    ) in transition_query_specs:
        predecessor_lane = lane_by_facet_id[predecessor_facet_id]
        successor_lane = lane_by_facet_id[successor_facet_id]
        transition_document_scope = tuple(
            document
            for document in document_order
            if document
            in {
                *predecessor_lane["stage_scope"],
                *successor_lane["stage_scope"],
            }
        )
        transition_chunks = [
            chunk
            for chunk in chunks
            if str(chunk.get("document") or "") in transition_document_scope
        ]
        transition_candidates: list[dict[str, Any]] = []
        if transition_chunks:
            transition_semantic_results = _semantic_lane_query(
                collection_handle,
                transition_embedding_by_pair[
                    (predecessor_facet_id, successor_facet_id)
                ],
                candidate_count=candidate_count,
                document_hints=transition_document_scope,
            )
            transition_results = build_hybrid_results(
                transition_query,
                transition_semantic_results,
                transition_chunks,
                n_results=lane_primary_limit,
                corpus=corpus_trace,
                allow_semantic_fallback=False,
                retrieval_mode_override="broad_synthesis",
                broad_max_per_document=1,
            )
            transition_hybrid = transition_results.get("hybrid")
            transition_primary_candidates = (
                list(transition_hybrid.get("primary_candidates", []))
                if isinstance(transition_hybrid, Mapping)
                else []
            )
            transition_candidates = _ranked_broad_transition_candidates(
                transition_primary_candidates,
                chunk_by_id=lookup,
                original_query=original_query,
                predecessor_intent_query=predecessor_intent_query,
                successor_intent_query=successor_intent_query,
            )
        transition_lane = {
            "transition_id": (
                f"{predecessor_facet_id}_{successor_facet_id}"
            ),
            "predecessor_facet_id": predecessor_facet_id,
            "successor_facet_id": successor_facet_id,
            "query": transition_query,
            "document_scope": transition_document_scope,
            "candidates": transition_candidates,
            "eligible_candidates": [
                candidate
                for candidate in transition_candidates
                if bool(candidate.get("transition_eligible"))
            ],
        }
        transition_lanes.append(transition_lane)
        successor_lane["incoming_transition"] = transition_lane

    ordered_lanes = sorted(lanes, key=lambda lane: _facet_priority(lane["facet"]))
    selected_ids: set[str] = set()
    selected_documents: set[str] = set()
    selected_chunks: list[dict[str, Any]] = []
    selected_by_facet: dict[str, list[str]] = {
        str(lane["facet_id"]): [] for lane in lanes
    }
    stage_anchor_selected_by_facet: dict[str, list[str]] = {
        str(lane["facet_id"]): [] for lane in lanes
    }
    transition_selected_by_pair: dict[tuple[str, str], list[str]] = {
        (
            str(lane["predecessor_facet_id"]),
            str(lane["successor_facet_id"]),
        ): []
        for lane in transition_lanes
    }
    pre_transition_selected_ids: set[str] = set()
    transition_extra_source_capacity_count = 0
    transition_reuse_satisfied_count = 0
    transition_new_source_satisfied_count = 0
    transition_capacity_limited_count = 0
    transition_candidate_shortfall_count = 0
    transition_selection_shortfall_count = 0

    def accept(candidate: Mapping[str, Any], facet_id: str) -> bool:
        chunk_id = str(candidate.get("chunk_id") or "")
        if not chunk_id:
            return False
        if chunk_id in selected_ids:
            if chunk_id not in selected_by_facet[facet_id]:
                selected_by_facet[facet_id].append(chunk_id)
            return False
        chunk = lookup.get(chunk_id)
        if chunk is None or should_skip_document(str(chunk.get("document") or "")):
            return False
        selected_ids.add(chunk_id)
        selected_documents.add(str(chunk.get("document") or ""))
        selected_chunks.append(chunk)
        selected_by_facet[facet_id].append(chunk_id)
        return True

    def accept_for_facets(
        candidate: Mapping[str, Any],
        facet_ids: Sequence[str],
    ) -> bool:
        if not facet_ids:
            return False
        accepted = accept(candidate, facet_ids[0])
        for facet_id in facet_ids[1:]:
            accept(candidate, facet_id)
        return accepted

    if broad:
        stage_lanes = sorted(
            (
                lane
                for lane in lanes
                if lane["role"] in _BROAD_STAGE_ROLES
            ),
            key=lambda lane: (
                (
                    int(lane["stage_position"][0])
                    if lane["stage_position"] is not None
                    else int(lane["chronology_min_document_ordinal"] or 10**9)
                ),
                str(lane["facet_id"]),
            ),
        )
        # Protect one role-eligible candidate for every narrative stage, then
        # rank only those candidates by cross-route agreement. No ineligible
        # fallback may silently stand in for a missing historical function.
        for lane in stage_lanes:
            if len(selected_chunks) >= max_final_sources:
                break
            candidate = _pick_first_lane_candidate(
                lane["stage_anchor_candidates"],
                selected_ids=selected_ids,
                selected_documents=selected_documents,
                prefer_new_document=True,
            )
            if candidate is None:
                continue
            facet_id = str(lane["facet_id"])
            if accept(candidate, facet_id):
                stage_anchor_selected_by_facet[facet_id].append(
                    str(candidate["chunk_id"])
                )

        # Preserve any non-stage verification lane before optional broad refill.
        for lane in ordered_lanes:
            if (
                lane["role"] == "original"
                or lane["role"] in _BROAD_STAGE_ROLES
                or len(selected_chunks) >= max_final_sources
            ):
                continue
            candidate = _pick_first_lane_candidate(
                lane["candidates"],
                selected_ids=selected_ids,
                selected_documents=selected_documents,
                prefer_new_document=False,
            )
            if candidate is not None:
                accept(candidate, str(lane["facet_id"]))

        # The final narrative document is an application-owned structural
        # anchor, retrieved with the canonical endpoint query.
        for lane in stage_lanes:
            if len(selected_chunks) >= max_final_sources:
                break
            candidate = _pick_first_lane_candidate(
                lane["endpoint_anchor_candidates"],
                selected_ids=selected_ids,
                selected_documents=selected_documents,
                prefer_new_document=True,
            )
            if candidate is not None:
                accept(candidate, str(lane["facet_id"]))

        # An adjacent-pair lane may earn a source only when one passage names
        # both stage intents and states an explicit causal or institutional
        # transition. Rank these lanes globally so facet order cannot consume
        # the remaining context slots.
        pre_transition_selected_ids = set(selected_ids)
        transition_extra_source_capacity_count = max(
            0,
            max_final_sources - len(selected_chunks),
        )
        transition_options = sorted(
            (
                {
                    "lane": transition_lane,
                    "candidate": candidate,
                }
                for transition_lane in transition_lanes
                for candidate in transition_lane["eligible_candidates"]
            ),
            key=lambda option: (
                (
                    0
                    if str(option["candidate"].get("chunk_id") or "")
                    in pre_transition_selected_ids
                    else 1
                ),
                -min(
                    int(
                        option["candidate"][
                            "predecessor_intent_match_count"
                        ]
                    ),
                    int(
                        option["candidate"][
                            "successor_intent_match_count"
                        ]
                    ),
                ),
                -int(option["candidate"]["transition_signal_score"]),
                -float(option["candidate"].get("rrf_score") or 0.0),
                str(option["lane"]["transition_id"]),
                str(option["candidate"]["chunk_id"]),
            ),
        )
        for option in transition_options:
            transition_lane = option["lane"]
            pair = (
                str(transition_lane["predecessor_facet_id"]),
                str(transition_lane["successor_facet_id"]),
            )
            if transition_selected_by_pair[pair]:
                continue
            candidate = option["candidate"]
            chunk_id = str(candidate.get("chunk_id") or "")
            if (
                chunk_id not in selected_ids
                and len(selected_chunks) >= max_final_sources
            ):
                continue
            accept_for_facets(candidate, pair)
            if chunk_id in selected_ids:
                transition_selected_by_pair[pair].append(chunk_id)

        transition_reuse_satisfied_count = sum(
            bool(chunk_ids)
            and chunk_ids[0] in pre_transition_selected_ids
            for chunk_ids in transition_selected_by_pair.values()
        )
        transition_new_source_satisfied_count = sum(
            bool(chunk_ids)
            and chunk_ids[0] not in pre_transition_selected_ids
            for chunk_ids in transition_selected_by_pair.values()
        )
        for transition_lane in transition_lanes:
            pair = (
                str(transition_lane["predecessor_facet_id"]),
                str(transition_lane["successor_facet_id"]),
            )
            if transition_selected_by_pair[pair]:
                continue
            eligible_chunk_ids = tuple(
                str(candidate.get("chunk_id") or "")
                for candidate in transition_lane["eligible_candidates"]
                if str(candidate.get("chunk_id") or "")
            )
            if not eligible_chunk_ids:
                transition_candidate_shortfall_count += 1
            elif (
                not any(
                    chunk_id in selected_ids
                    for chunk_id in eligible_chunk_ids
                )
                and len(selected_chunks) >= max_final_sources
            ):
                transition_capacity_limited_count += 1
            else:
                transition_selection_shortfall_count += 1

        # Aggregate candidate ranks globally. This replaces the old facet-order
        # refill in which the earliest stage always consumed the spare slot.
        supplemental_options = _ranked_broad_supplemental_options(
            lanes,
            document_ordinal_by_id=document_ordinal_by_id,
        )
        while len(selected_chunks) < max_final_sources:
            available = [
                option
                for option in supplemental_options
                if option["chunk_id"] not in selected_ids
            ]
            if not available:
                break
            unseen_document_options = [
                option
                for option in available
                if option["document"] not in selected_documents
            ]
            option = (unseen_document_options or available)[0]
            if not accept_for_facets(
                option["candidate"],
                option["facet_ids"],
            ):
                supplemental_options.remove(option)
    else:
        # Standard plans retain one-per-lane coverage and round-robin refill.
        for lane in ordered_lanes:
            facet_id = str(lane["facet_id"])
            coverage_candidates = lane["candidates"]
            shared_candidate = (
                coverage_candidates[0]
                if coverage_candidates
                and str(coverage_candidates[0].get("chunk_id") or "")
                in selected_ids
                else None
            )
            if shared_candidate is not None:
                accept(shared_candidate, facet_id)
                continue
            if len(selected_chunks) >= max_final_sources:
                continue
            candidate = _pick_first_lane_candidate(
                coverage_candidates,
                selected_ids=selected_ids,
                selected_documents=selected_documents,
                prefer_new_document=False,
            )
            if candidate is not None:
                accept(candidate, facet_id)

        candidate_offsets = {
            str(lane["facet_id"]): 0 for lane in ordered_lanes
        }
        while len(selected_chunks) < max_final_sources:
            made_progress = False
            for lane in ordered_lanes:
                facet_id = str(lane["facet_id"])
                candidates = lane["candidates"]
                offset = candidate_offsets[facet_id]
                while offset < len(candidates):
                    candidate = candidates[offset]
                    offset += 1
                    if accept(candidate, facet_id):
                        made_progress = True
                        break
                candidate_offsets[facet_id] = offset
                if len(selected_chunks) >= max_final_sources:
                    made_progress = True
                    break
            if not made_progress:
                break

    expanded = expand_with_neighbors(
        selected_chunks,
        lookup=lookup,
        primary_first=True,
    )
    final_chunks = expanded[:max_final_sources]
    if broad:
        corpus_ordinal = {
            str(chunk.get("chunk_id") or ""): ordinal
            for ordinal, chunk in enumerate(chunks)
        }
        final_chunks.sort(
            key=lambda chunk: (
                corpus_ordinal.get(str(chunk.get("chunk_id") or ""), 10**9),
                str(chunk.get("chunk_id") or ""),
            )
        )

    source_number_by_id = {
        str(chunk.get("chunk_id") or ""): source_number
        for source_number, chunk in enumerate(final_chunks, start=1)
    }
    facet_source_numbers = {
        facet_id: tuple(
            source_number_by_id[chunk_id]
            for chunk_id in chunk_ids
            if chunk_id in source_number_by_id
        )
        for facet_id, chunk_ids in selected_by_facet.items()
    }
    lane_by_chunk: dict[str, list[str]] = {}
    for facet_id, chunk_ids in selected_by_facet.items():
        for chunk_id in chunk_ids:
            lane_by_chunk.setdefault(chunk_id, []).append(facet_id)
    stage_lanes = [
        lane
        for lane in lanes
        if str(lane.get("chronology_band") or "none") != "none"
    ]
    stage_coverage_required_count = len(stage_lanes)
    stage_coverage_satisfied_count = sum(
        any(
            chunk_id in source_number_by_id
            for chunk_id in stage_anchor_selected_by_facet[
                str(lane["facet_id"])
            ]
        )
        for lane in stage_lanes
    )
    canonical_core_required_count = len(stage_lanes) if broad else 0
    canonical_core_satisfied_count = (
        sum(
            any(
                chunk_id in source_number_by_id
                for chunk_id in stage_anchor_selected_by_facet[
                    str(lane["facet_id"])
                ]
            )
            for lane in stage_lanes
        )
        if broad
        else 0
    )
    transition_coverage_required_count = len(transition_lanes) if broad else 0
    transition_coverage_satisfied_count = (
        sum(
            any(
                chunk_id in source_number_by_id
                for chunk_id in transition_selected_by_pair[
                    (
                        str(lane["predecessor_facet_id"]),
                        str(lane["successor_facet_id"]),
                    )
                ]
            )
            for lane in transition_lanes
        )
        if broad
        else 0
    )

    safe_lane_trace = []
    for lane in lanes:
        selection = lane["trace"].get("selection", {})
        safe_lane_trace.append(
            {
                "facet_id": lane["facet_id"],
                "role": lane["role"],
                "query_sha256": hashlib.sha256(
                    lane["query"].encode("utf-8")
                ).hexdigest(),
                "query_char_count": len(lane["query"]),
                "provider_query_sha256": hashlib.sha256(
                    lane["query"].encode("utf-8")
                ).hexdigest(),
                "provider_query_char_count": len(lane["query"]),
                "document_hint_sha256s": [
                    document_identifier_sha256(hint)
                    for hint in lane["document_hints"]
                ],
                "chronology_band": lane["chronology_band"],
                "chronology_min_document_ordinal": lane[
                    "chronology_min_document_ordinal"
                ],
                "chronology_max_document_ordinal": lane[
                    "chronology_max_document_ordinal"
                ],
                "candidate_chunk_ids": [
                    chunk_id
                    for chunk_id in dict.fromkeys(
                        str(candidate.get("chunk_id") or "")
                        for candidate in (
                            *lane["candidates"],
                            *lane["mechanism_candidates"],
                            *lane["canonical_primary_candidates"],
                            *lane["canonical_mechanism_candidates"],
                            *lane["endpoint_anchor_candidates"],
                        )
                    )
                    if chunk_id
                ],
                **(
                    {
                        "mechanism_query_sha256s": [
                            hashlib.sha256(query.encode("utf-8")).hexdigest()
                            for query in lane["mechanism_queries"]
                        ],
                        "mechanism_query_char_counts": [
                            len(query) for query in lane["mechanism_queries"]
                        ],
                        "mechanism_candidate_chunk_ids": [
                            str(candidate.get("chunk_id") or "")
                            for candidate in lane["mechanism_candidates"]
                            if str(candidate.get("chunk_id") or "")
                        ],
                    }
                    if lane["mechanism_queries"]
                    else {}
                ),
                **(
                    {
                        "stage_intent_query_sha256": hashlib.sha256(
                            lane["stage_intent_query"].encode("utf-8")
                        ).hexdigest(),
                        "stage_intent_query_char_count": len(
                            lane["stage_intent_query"]
                        ),
                        "stage_intent_term_count": lane[
                            "stage_intent_term_count"
                        ],
                        "stage_distinctive_intent_term_count": lane[
                            "stage_distinctive_intent_term_count"
                        ],
                        "stage_required_distinctive_intent_match_count": (
                            min(
                                2,
                                int(
                                    lane[
                                        "stage_distinctive_intent_term_count"
                                    ]
                                ),
                            )
                        ),
                        "canonical_query_sha256": hashlib.sha256(
                            lane["canonical_query"].encode("utf-8")
                        ).hexdigest(),
                        "canonical_query_char_count": len(
                            lane["canonical_query"]
                        ),
                        "canonical_candidate_chunk_ids": [
                            str(candidate.get("chunk_id") or "")
                            for candidate in lane[
                                "canonical_core_candidates"
                            ]
                            if str(candidate.get("chunk_id") or "")
                        ],
                        "canonical_core_selected_chunk_ids": (
                            stage_anchor_selected_by_facet[
                                str(lane["facet_id"])
                            ]
                        ),
                        "stage_anchor_selected_chunk_ids": (
                            stage_anchor_selected_by_facet[
                                str(lane["facet_id"])
                            ]
                        ),
                        "stage_anchor_consensus_candidates": [
                            {
                                "chunk_id": str(
                                    candidate.get("chunk_id") or ""
                                ),
                                "eligible": bool(
                                    candidate.get("stage_anchor_eligible")
                                ),
                                "eligibility": str(
                                    candidate.get(
                                        "stage_anchor_eligibility",
                                        "missing_chunk",
                                    )
                                ),
                                "intent_match_count": int(
                                    candidate.get(
                                        "stage_intent_match_count",
                                        0,
                                    )
                                ),
                                "distinctive_intent_match_count": int(
                                    candidate.get(
                                        "stage_distinctive_intent_match_count",
                                        0,
                                    )
                                ),
                                "required_distinctive_intent_match_count": int(
                                    candidate.get(
                                        "stage_required_distinctive_intent_match_count",
                                        0,
                                    )
                                ),
                                "role_signal_score": int(
                                    candidate.get(
                                        "stage_role_signal_score",
                                        0,
                                    )
                                ),
                                "pool_names": list(
                                    candidate.get("anchor_pool_names") or ()
                                ),
                                "pool_ranks": dict(
                                    candidate.get("anchor_pool_ranks") or {}
                                ),
                                "pool_hit_count": int(
                                    candidate.get("anchor_pool_hit_count") or 0
                                ),
                            }
                            for candidate in lane["stage_anchor_diagnostics"]
                            if str(candidate.get("chunk_id") or "")
                        ],
                    }
                    if lane["canonical_query"] is not None
                    else {}
                ),
                **(
                    {
                        "transition_id": lane["incoming_transition"][
                            "transition_id"
                        ],
                        "transition_predecessor_facet_id": lane[
                            "incoming_transition"
                        ]["predecessor_facet_id"],
                        "transition_query_sha256": hashlib.sha256(
                            lane["incoming_transition"]["query"].encode(
                                "utf-8"
                            )
                        ).hexdigest(),
                        "transition_query_char_count": len(
                            lane["incoming_transition"]["query"]
                        ),
                        "transition_document_scope_sha256s": [
                            document_identifier_sha256(document)
                            for document in lane["incoming_transition"][
                                "document_scope"
                            ]
                        ],
                        "transition_candidate_chunk_ids": [
                            str(candidate.get("chunk_id") or "")
                            for candidate in lane["incoming_transition"][
                                "candidates"
                            ]
                            if str(candidate.get("chunk_id") or "")
                        ],
                        "transition_selected_chunk_ids": (
                            transition_selected_by_pair[
                                (
                                    str(
                                        lane["incoming_transition"][
                                            "predecessor_facet_id"
                                        ]
                                    ),
                                    str(
                                        lane["incoming_transition"][
                                            "successor_facet_id"
                                        ]
                                    ),
                                )
                            ]
                        ),
                        "transition_candidates": [
                            {
                                "chunk_id": str(
                                    candidate.get("chunk_id") or ""
                                ),
                                "eligible": bool(
                                    candidate.get("transition_eligible")
                                ),
                                "eligibility": str(
                                    candidate.get(
                                        "transition_eligibility",
                                        "missing_chunk",
                                    )
                                ),
                                "predecessor_intent_match_count": int(
                                    candidate.get(
                                        "predecessor_intent_match_count",
                                        0,
                                    )
                                ),
                                "successor_intent_match_count": int(
                                    candidate.get(
                                        "successor_intent_match_count",
                                        0,
                                    )
                                ),
                                "transition_signal_score": int(
                                    candidate.get(
                                        "transition_signal_score",
                                        0,
                                    )
                                ),
                            }
                            for candidate in lane["incoming_transition"][
                                "candidates"
                            ]
                            if str(candidate.get("chunk_id") or "")
                        ],
                    }
                    if "incoming_transition" in lane
                    else {}
                ),
                "selected_chunk_ids": selected_by_facet[str(lane["facet_id"])],
                "raw_primary_fallback_detected": bool(
                    selection.get("raw_primary_fallback_detected")
                ),
                "semantic_fallback_used": bool(
                    selection.get("fusion_pool_fallback_used")
                ),
            }
        )

    plan_schema = str(_plan_value(plan, "schema", ""))
    trace = {
        "schema": RETRIEVAL_TRACE_SCHEMA,
        "trace_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "retrieval_version": FACETED_RETRIEVAL_VERSION,
        "query": {
            "sha256": hashlib.sha256(original_query.encode("utf-8")).hexdigest(),
            "char_count": len(original_query),
            "mode": "planned" if len(facets) > 1 else "standard",
        },
        "corpus": _safe_corpus_trace(corpus_trace),
        "parameters": {
            "semantic_candidate_limit": SEMANTIC_CANDIDATE_LIMIT,
            "lexical_candidate_limit": LEXICAL_CANDIDATE_LIMIT,
            "semantic_distance_threshold": MAX_PRIMARY_DISTANCE,
            "final_context_source_limit": max_final_sources,
            "lane_primary_limit": lane_primary_limit,
            "facet_embedding": "single_batched_request",
            "lane_selection": (
                "consensus_stage_anchor_then_transition_then_global_supplement"
                if broad
                else "one_each_then_round_robin"
            ),
            "broad_execution_version": (
                BROAD_CANONICAL_EXECUTION_VERSION
                if broad
                else "not_applicable"
            ),
            "broad_mechanism_lexical_version": (
                BROAD_MECHANISM_LEXICAL_VERSION if broad else "not_applicable"
            ),
            "broad_mechanism_candidate_limit": (
                BROAD_MECHANISM_CANDIDATE_LIMIT if broad else 0
            ),
            "broad_transition_lane_version": (
                BROAD_TRANSITION_LANE_VERSION
                if broad
                else "not_applicable"
            ),
            "lineage_stage_contract_version": (
                LONG_LINEAGE_CONTRACT_VERSION
                if long_lineage
                else "not_applicable"
            ),
            "lineage_transition_capacity_policy": (
                LONG_LINEAGE_TRANSITION_CAPACITY_POLICY
                if long_lineage
                else "not_applicable"
            ),
            "premise_lane_reservation": True,
            "broad_context_order": "corpus_ordinal" if broad else "selection",
            "neighbor_expansion": "primaries_first_then_immediate_neighbors",
        },
        "plan": {
            "schema": plan_schema,
            "traits": list(traits),
            "planner_used": bool(_plan_value(plan, "planner_used", False)),
            "fallback_reason": _plan_value(plan, "fallback_reason"),
            "facet_count": len(facets),
            "requirement_count": len(tuple(requirements or ())),
            "lineage_stage_required_count": (
                LONG_INSTITUTIONAL_LINEAGE_STAGE_REQUIREMENTS
                if long_lineage
                else 0
            ),
            "lineage_stage_planned_count": (
                len(stage_lanes) if long_lineage else 0
            ),
            "lineage_stage_source_capacity_count": (
                min(
                    LONG_INSTITUTIONAL_LINEAGE_STAGE_REQUIREMENTS,
                    max_final_sources,
                )
                if long_lineage
                else 0
            ),
        },
        "lanes": safe_lane_trace,
        "candidates": {},
        "selection": {
            "primary_chunk_ids": [
                str(chunk.get("chunk_id") or "") for chunk in selected_chunks
            ],
            "stage_coverage_required_count": stage_coverage_required_count,
            "stage_coverage_satisfied_count": stage_coverage_satisfied_count,
            "stage_coverage_shortfall_count": (
                stage_coverage_required_count - stage_coverage_satisfied_count
            ),
            "stage_capacity_shortfall_count": (
                max(
                    0,
                    stage_coverage_required_count - max_final_sources,
                )
                if broad
                else 0
            ),
            "canonical_core_required_count": canonical_core_required_count,
            "canonical_core_satisfied_count": canonical_core_satisfied_count,
            "canonical_core_shortfall_count": (
                canonical_core_required_count - canonical_core_satisfied_count
            ),
            "transition_coverage_required_count": (
                transition_coverage_required_count
            ),
            "transition_coverage_satisfied_count": (
                transition_coverage_satisfied_count
            ),
            "transition_coverage_shortfall_count": (
                transition_coverage_required_count
                - transition_coverage_satisfied_count
            ),
            "transition_extra_source_capacity_count": (
                transition_extra_source_capacity_count
            ),
            "transition_reuse_satisfied_count": (
                transition_reuse_satisfied_count
            ),
            "transition_new_source_satisfied_count": (
                transition_new_source_satisfied_count
            ),
            "transition_capacity_limited_count": (
                transition_capacity_limited_count
            ),
            "transition_candidate_shortfall_count": (
                transition_candidate_shortfall_count
            ),
            "transition_selection_shortfall_count": (
                transition_selection_shortfall_count
            ),
            "discarded": [],
            "document_distribution": {
                "selected_primary": _document_distribution(selected_chunks),
                "context": _document_distribution(final_chunks),
            },
            "context": [
                {
                    **_safe_chunk_fields(chunk),
                    "document_ordinal": document_ordinal_by_id.get(
                        str(chunk.get("document") or "")
                    ),
                    "source_number": source_number,
                    "origin": (
                        "primary"
                        if str(chunk.get("chunk_id") or "") in selected_ids
                        else "neighbor"
                    ),
                    "facet_ids": lane_by_chunk.get(
                        str(chunk.get("chunk_id") or ""),
                        [],
                    ),
                }
                for source_number, chunk in enumerate(final_chunks, start=1)
            ],
        },
        "evidence": {},
        "generation_contract": {},
    }
    return PlannedContext(
        final_chunks=final_chunks,
        facet_source_numbers=facet_source_numbers,
        trace=trace,
        lane_by_chunk_id={
            chunk_id: tuple(facet_ids)
            for chunk_id, facet_ids in lane_by_chunk.items()
        },
        broad_stage_anchor_chunk_ids={
            facet_id: chunk_id
            for facet_id, chunk_ids in stage_anchor_selected_by_facet.items()
            for chunk_id in chunk_ids
            if chunk_id in source_number_by_id
        },
        broad_transition_chunk_ids={
            pair: chunk_id
            for pair, chunk_ids in transition_selected_by_pair.items()
            for chunk_id in chunk_ids
            if chunk_id in source_number_by_id
        },
    )


def retrieve(query: str, n_results: int = 5):
    corpus_trace = {
        "collection_name": "manuscript",
        "corpus_manifest_sha256": _file_sha256(
            BASE_DIR / "fixtures" / "corpus_manifest.json"
        ),
        "chunks_sha256": _file_sha256(BASE_DIR / "output" / "chunks.json"),
        "hnsw_space": str(
            getattr(collection, "configuration", {}).get("hnsw", {}).get(
                "space",
                "",
            )
        ),
    }
    return retrieve_from_collection(
        query,
        collection,
        get_all_chunks(),
        n_results=n_results,
        corpus={
            key: value
            for key, value in corpus_trace.items()
            if value is not None
        },
    )


def _hybrid_payload(results: Mapping[str, Any]) -> Mapping[str, Any] | None:
    hybrid = results.get("hybrid")
    return hybrid if isinstance(hybrid, Mapping) else None


def _append_trace_discard(
    trace: Mapping[str, Any] | None,
    chunk: Mapping[str, Any],
    *,
    stage: str,
    reason: str,
    displacement_cause: str | None = None,
) -> None:
    if not isinstance(trace, dict):
        return
    selection = trace.setdefault("selection", {})
    discarded = selection.setdefault("discarded", [])
    record = {
        **_safe_chunk_fields(chunk),
        "stage": stage,
        "reason": reason,
    }
    if displacement_cause is not None:
        record["displacement_cause"] = displacement_cause
    if record not in discarded:
        discarded.append(record)


def get_filtered_primary_chunks(
    results: Mapping[str, Any],
    max_distance: float = MAX_PRIMARY_DISTANCE,
    *,
    lookup: dict[str, dict] | None = None,
    prefer_hybrid: bool = False,
) -> list[dict]:
    """
    Return canonical primary chunks selected for context.

    Hybrid results have already applied the semantic distance rule, lexical rescue,
    fusion, and diversity. Plain semantic results retain the original distance
    filtering behavior, including its all-distant fallback.
    """
    hybrid = _hybrid_payload(results) if prefer_hybrid else None
    if hybrid is not None:
        lookup = lookup if lookup is not None else get_chunk_lookup()
        trace = hybrid.get("trace")
        primary_chunks: list[dict] = []
        primary_ids = hybrid.get("primary_chunk_ids", [])
        if not isinstance(primary_ids, list):
            raise RuntimeError("hybrid retrieval primary IDs are malformed")
        unresolved_ids: list[str] = []
        for raw_chunk_id in primary_ids:
            chunk_id = str(raw_chunk_id)
            chunk = lookup.get(chunk_id)
            if chunk is None:
                _append_trace_discard(
                    trace,
                    {"chunk_id": chunk_id},
                    stage="primary_resolution",
                    reason="missing_disk_chunk",
                )
                unresolved_ids.append(chunk_id)
                continue
            if should_skip_document(str(chunk.get("document") or "")):
                _append_trace_discard(
                    trace,
                    chunk,
                    stage="primary_resolution",
                    reason="structural_document",
                    displacement_cause="document_filtering",
                )
                unresolved_ids.append(chunk_id)
                continue
            primary_chunks.append(chunk)
        if unresolved_ids:
            raise RuntimeError(
                "hybrid retrieval selected unavailable corpus chunks: "
                + ", ".join(unresolved_ids)
            )
        return primary_chunks

    metadatas = _first_batch(results, "metadatas")
    distances = _first_batch(results, "distances")

    primary_chunks: list[dict] = []

    for meta, dist in zip(metadatas, distances):
        if not isinstance(meta, Mapping):
            continue
        if should_skip_document(meta.get("document", "")):
            continue
        if dist <= max_distance:
            primary_chunks.append(dict(meta))

    if not primary_chunks:
        primary_chunks = [
            dict(meta)
            for meta in metadatas
            if isinstance(meta, Mapping)
            and not should_skip_document(meta.get("document", ""))
        ]

    return primary_chunks


def expand_with_neighbors(
    primary_chunks: list[dict],
    lookup: dict[str, dict] | None = None,
    *,
    primary_first: bool = False,
) -> list[dict]:
    """
    Expand primary chunks with immediate neighbors and de-duplicate them.

    The legacy interleaved order remains the default for Index Mode. Answer Mode
    reserves every primary first so optional neighbors cannot displace stronger
    later anchors when the final source cap is applied.
    """
    lookup = lookup if lookup is not None else get_chunk_lookup()
    expanded: list[dict] = []
    seen: set[str] = set()

    def append_chunk(chunk_id: str) -> None:
        chunk = lookup.get(chunk_id)
        if not chunk:
            return
        if should_skip_document(str(chunk.get("document") or "")):
            return
        if chunk_id not in seen:
            expanded.append(chunk)
            seen.add(chunk_id)

    valid_primary_ids = [
        str(meta.get("chunk_id"))
        for meta in primary_chunks
        if meta.get("chunk_id")
    ]
    if primary_first:
        for chunk_id in valid_primary_ids:
            append_chunk(chunk_id)

    for chunk_id in valid_primary_ids:
        neighbor_ids = get_neighbor_chunk_ids(chunk_id)
        if primary_first:
            for neighbor_id in neighbor_ids:
                append_chunk(str(neighbor_id))
            continue

        prev_id = neighbor_ids[0] if len(neighbor_ids) == 2 else None
        next_id = neighbor_ids[-1] if neighbor_ids else None

        ordered_ids = []
        if prev_id:
            ordered_ids.append(prev_id)
        ordered_ids.append(chunk_id)
        if next_id and next_id != prev_id:
            ordered_ids.append(next_id)

        for cid in ordered_ids:
            append_chunk(str(cid))

    return expanded


def _trace_scope() -> dict[str, str | None]:
    scope = current_usage_context()
    return {
        "project_id": scope.project_id,
        "conversation_id": scope.conversation_id,
        "turn_id": scope.turn_id,
    }


def plan_context_chunks(
    results: Mapping[str, Any],
    chunks: list[dict] | None = None,
    lookup: dict[str, dict] | None = None,
    max_primary_distance: float = MAX_PRIMARY_DISTANCE,
    max_final_sources: int = MAX_FINAL_SOURCES,
) -> RetrievalOutcome:
    """Build the exact ordered Answer Mode context and complete its trace."""
    if lookup is None and chunks is not None:
        lookup = build_chunk_lookup(chunks)
    lookup = lookup if lookup is not None else get_chunk_lookup()
    primary_chunks = get_filtered_primary_chunks(
        results,
        max_distance=max_primary_distance,
        lookup=lookup,
        prefer_hybrid=True,
    )
    expanded_chunks = expand_with_neighbors(
        primary_chunks,
        lookup=lookup,
        primary_first=True,
    )
    final_chunks = expanded_chunks[:max_final_sources]

    hybrid = _hybrid_payload(results)
    raw_trace = hybrid.get("trace") if hybrid is not None else None
    trace = raw_trace if isinstance(raw_trace, dict) else {}
    if trace:
        parameters = trace.setdefault("parameters", {})
        configured_distance = float(
            parameters.get("semantic_distance_threshold", MAX_PRIMARY_DISTANCE)
        )
        if max_primary_distance != configured_distance:
            raise ValueError(
                "hybrid results were built with a different semantic distance threshold"
            )
        parameters["finalizer_max_primary_distance"] = max_primary_distance
        parameters["final_context_source_limit"] = max_final_sources
        trace["scope"] = _trace_scope()
        selection = trace.setdefault("selection", {})
        primary_ids = {
            str(chunk.get("chunk_id"))
            for chunk in primary_chunks
            if chunk.get("chunk_id")
        }
        primary_candidates = hybrid.get("primary_candidates", [])
        fused_ranks = {
            str(candidate.get("chunk_id")): candidate.get("fused_rank")
            for candidate in primary_candidates
            if isinstance(candidate, Mapping) and candidate.get("chunk_id")
        }
        neighbor_parents: dict[str, list[str]] = {}
        for primary_id in primary_ids:
            for neighbor_id in get_neighbor_chunk_ids(primary_id):
                neighbor_parents.setdefault(str(neighbor_id), []).append(primary_id)

        context_trace = []
        for source_number, chunk in enumerate(final_chunks, start=1):
            chunk_id = str(chunk.get("chunk_id") or "")
            is_primary = chunk_id in primary_ids
            context_trace.append(
                {
                    **_safe_chunk_fields(chunk),
                    "source_number": source_number,
                    "origin": "primary" if is_primary else "neighbor",
                    "parent_primary_chunk_ids": (
                        [chunk_id]
                        if is_primary
                        else sorted(neighbor_parents.get(chunk_id, []))
                    ),
                    "fused_rank": fused_ranks.get(chunk_id),
                }
            )
        selection["context"] = context_trace
        distributions = selection.setdefault("document_distribution", {})
        distributions["context"] = _document_distribution(context_trace)

        final_ids = {
            str(chunk.get("chunk_id"))
            for chunk in final_chunks
            if chunk.get("chunk_id")
        }
        for chunk in expanded_chunks[max_final_sources:]:
            _append_trace_discard(
                trace,
                chunk,
                stage="context",
                reason="final_source_cap",
                displacement_cause="truncation",
            )
        for chunk in primary_chunks:
            chunk_id = str(chunk.get("chunk_id") or "")
            if chunk_id and chunk_id not in final_ids:
                _append_trace_discard(
                    trace,
                    chunk,
                    stage="context",
                    reason="final_source_cap",
                    displacement_cause="truncation",
                )

    return RetrievalOutcome(final_chunks=final_chunks, trace=trace)


def _diagnostics_enabled() -> bool:
    return os.getenv(RETRIEVAL_DIAGNOSTICS_ENV, "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _emit_trace(
    trace: Mapping[str, Any],
    trace_sink: Callable[[Mapping[str, Any]], object] | None,
) -> None:
    sink = trace_sink
    if sink is None and _diagnostics_enabled():
        sink = FileTraceSink()
    if sink is None or not trace:
        return
    try:
        sink(deepcopy(dict(trace)))
    except Exception:
        logger.warning(
            "Retrieval diagnostics could not be persisted",
            exc_info=True,
        )


def emit_retrieval_trace(
    trace: Mapping[str, Any],
    trace_sink: Callable[[Mapping[str, Any]], object] | None = None,
) -> None:
    """Expose the same nonfatal text-free trace boundary to planned Answer Mode."""
    _emit_trace(trace, trace_sink)


def finalize_context_chunks(
    results: Mapping[str, Any],
    chunks: list[dict] | None = None,
    lookup: dict[str, dict] | None = None,
    max_primary_distance: float = MAX_PRIMARY_DISTANCE,
    max_final_sources: int = MAX_FINAL_SOURCES,
    *,
    trace_sink: Callable[[Mapping[str, Any]], object] | None = None,
) -> list[dict]:
    outcome = plan_context_chunks(
        results,
        chunks=chunks,
        lookup=lookup,
        max_primary_distance=max_primary_distance,
        max_final_sources=max_final_sources,
    )
    _emit_trace(outcome.trace, trace_sink)
    return outcome.final_chunks


def _build_numbered_context(
    final_chunks: list[dict],
    label: str,
    bracketed_header: bool,
) -> str:
    context_blocks = []

    for i, chunk in enumerate(final_chunks, start=1):
        header = f"[{label} {i}]" if bracketed_header else f"{label} {i}:"
        block = (
            f"{header}\n"
            f"Document: {chunk.get('document', 'N/A')}\n"
            f"Chapter: {chunk.get('chapter_title', 'N/A')}\n"
            f"Chunk ID: {chunk.get('chunk_id', 'N/A')}\n"
            f"Paragraphs: {chunk.get('paragraph_start', '?')}–{chunk.get('paragraph_end', '?')}\n"
            f"Text:\n{chunk.get('text', '')}\n"
        )
        context_blocks.append(block)

    return "\n\n".join(context_blocks)


def build_context(final_chunks: list[dict]) -> str:
    return _build_numbered_context(final_chunks, "Source", bracketed_header=True)


def build_comparison_context(chunks: list[dict]) -> str:
    return _build_numbered_context(chunks, "Existing Index", bracketed_header=False)


def find_exact_match_chunks(
    term: str,
    chunks: list[dict] | None = None,
    empty_term_matches: bool = True,
) -> list[dict]:
    """
    Return chunks whose text contains the term as a case-insensitive substring.
    """
    if chunks is None:
        chunks = get_all_chunks()

    term_lower = term.lower().strip()
    if not term_lower and not empty_term_matches:
        return []
    matches = []

    for chunk in chunks:
        if should_skip_document(chunk.get("document", "")):
            continue

        text = chunk.get("text", "").lower()
        if term_lower in text:
            matches.append(chunk)

    return matches


def finalize_index_context(
    term: str,
    semantic_results,
    chunks: list[dict] | None = None,
    lookup: dict[str, dict] | None = None,
    empty_term_matches: bool = True,
    max_primary_distance: float = MAX_PRIMARY_DISTANCE,
    max_final_sources: int = MAX_FINAL_SOURCES,
) -> list[dict]:
    """
    Prefer exact text matches for index terms; fall back to semantic retrieval.
    """
    chunks = chunks if chunks is not None else get_all_chunks()
    lookup = lookup if lookup is not None else build_chunk_lookup(chunks)
    exact_matches = find_exact_match_chunks(
        term,
        chunks,
        empty_term_matches=empty_term_matches,
    )

    seen = set()
    final_chunks = []

    # exact matches first
    for chunk in exact_matches:
        cid = chunk["chunk_id"]
        if cid not in seen and not should_skip_document(chunk.get("document", "")):
            final_chunks.append(chunk)
            seen.add(cid)

    # neighbors of exact matches
    for chunk in exact_matches:
        for neighbor_id in get_neighbor_chunk_ids(chunk["chunk_id"]):
            neighbor = lookup.get(neighbor_id)
            if neighbor and neighbor["chunk_id"] not in seen and not should_skip_document(neighbor.get("document", "")):
                final_chunks.append(neighbor)
                seen.add(neighbor["chunk_id"])

    # semantic fallback
    primary_chunks = get_filtered_primary_chunks(
        semantic_results,
        max_distance=max_primary_distance,
        lookup=lookup,
        prefer_hybrid=False,
    )
    semantic_expanded = expand_with_neighbors(primary_chunks, lookup=lookup)

    for chunk in semantic_expanded:
        cid = chunk["chunk_id"]
        if cid not in seen and not should_skip_document(chunk.get("document", "")):
            final_chunks.append(chunk)
            seen.add(cid)

    return final_chunks[:max_final_sources]
