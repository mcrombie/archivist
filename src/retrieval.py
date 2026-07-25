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
from dataclasses import dataclass
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
FACETED_RETRIEVAL_VERSION = "faceted-hybrid-rrf-v2"
RETRIEVAL_TRACE_SCHEMA = "archivist.retrieval_trace/2"
RETRIEVAL_DIAGNOSTICS_ENV = "ARCHIVIST_RETRIEVAL_DIAGNOSTICS"
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


class FileTraceSink:
    """Persist one private, text-free retrieval trace per JSON file."""

    def __init__(self, root: Path = RETRIEVAL_DIAGNOSTICS_DIR) -> None:
        self.root = root

    def __call__(self, trace: Mapping[str, Any]) -> Path:
        if trace.get("schema") != RETRIEVAL_TRACE_SCHEMA:
            raise ValueError("retrieval trace schema is missing or unsupported")
        _assert_trace_is_text_free(trace)
        unknown_fields = set(trace) - _TRACE_TOP_LEVEL_FIELDS
        if unknown_fields:
            raise ValueError(
                "retrieval trace contains unsupported top-level fields: "
                + ", ".join(sorted(str(field) for field in unknown_fields))
            )
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


def _assert_trace_is_text_free(value: object) -> None:
    sensitive_keys = {
        "chunk",
        "content",
        "excerpt",
        "manuscript_text",
        "metadata",
        "metadatas",
        "passage",
        "prompt",
        "question",
        "raw_query",
        "response",
        "answer",
        "text",
    }

    def walk(item: object, path: str) -> None:
        if isinstance(item, Mapping):
            for raw_key, nested in item.items():
                key = str(raw_key).casefold()
                if key in sensitive_keys:
                    raise ValueError(
                        f"retrieval trace contains forbidden field {path}.{raw_key}"
                    )
                if key == "query" and not isinstance(nested, Mapping):
                    raise ValueError(
                        "retrieval trace query must contain only hashed diagnostics"
                    )
                walk(nested, f"{path}.{raw_key}")
        elif isinstance(item, list):
            for index, nested in enumerate(item):
                walk(nested, f"{path}[{index}]")

    walk(value, "trace")


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
        "document": str(chunk.get("document") or ""),
        "chapter_title": str(chunk.get("chapter_title") or ""),
        "paragraph_start": chunk.get("paragraph_start"),
        "paragraph_end": chunk.get("paragraph_end"),
    }


def _document_distribution(items: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(item.get("document") or "") for item in items)
    counts.pop("", None)
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
) -> dict[str, Any]:
    """Attach deterministic BM25/RRF primary anchors to raw semantic results."""
    if n_results <= 0:
        raise ValueError("n_results must be greater than zero")

    semantic = _semantic_candidates(semantic_results)
    lexical, lexical_query = lexical_candidates(query, chunks)
    retrieval_mode = classify_retrieval_mode(query)
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
            MAX_PRIMARY_PER_DOCUMENT
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
                MAX_PRIMARY_PER_DOCUMENT
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

    queries = [str(_plan_value(facet, "search_query", "")).strip() for facet in facets]
    if any(not query for query in queries):
        raise ValueError("query plan contains an empty search facet")
    embeddings = embed_queries(queries, embedding_client=embedding_client)
    collection_count = int(collection_handle.count())
    lane_primary_limit = min(max(n_results, 3), max_final_sources)
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
        lane_chunks = [
            chunk
            for chunk in chunks
            if not document_hints
            or str(chunk.get("document") or "") in document_hints
        ]
        semantic_results = (
            _semantic_lane_query(
                collection_handle,
                embedding,
                candidate_count=candidate_count,
                document_hints=document_hints,
            )
            if lane_chunks
            else _empty_semantic_results()
        )
        allow_fallback = role == "original"
        results = build_hybrid_results(
            query,
            semantic_results,
            lane_chunks,
            n_results=lane_primary_limit,
            corpus=corpus_trace,
            allow_semantic_fallback=allow_fallback,
        )
        hybrid = results.get("hybrid")
        primary_candidates = (
            list(hybrid.get("primary_candidates", []))
            if isinstance(hybrid, Mapping)
            else []
        )
        lane_trace = hybrid.get("trace", {}) if isinstance(hybrid, Mapping) else {}
        lanes.append(
            {
                "facet": facet,
                "facet_id": facet_id,
                "role": role,
                "query": query,
                "document_hints": document_hints,
                "candidates": primary_candidates,
                "trace": lane_trace,
            }
        )

    raw_traits = _plan_value(plan, "traits", ())
    traits = tuple(
        str(getattr(value, "value", value))
        for value in (raw_traits or ())
    )
    broad = "broad_synthesis" in traits
    ordered_lanes = sorted(lanes, key=lambda lane: _facet_priority(lane["facet"]))
    selected_ids: set[str] = set()
    selected_documents: set[str] = set()
    selected_chunks: list[dict[str, Any]] = []
    selected_by_facet: dict[str, list[str]] = {
        str(lane["facet_id"]): [] for lane in lanes
    }
    lookup = build_chunk_lookup(chunks)

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

    # Coverage pass: give each live lane an anchor before any lane receives a second.
    for lane in ordered_lanes:
        facet_id = str(lane["facet_id"])
        shared_candidate = (
            lane["candidates"][0]
            if lane["candidates"]
            and str(lane["candidates"][0].get("chunk_id") or "")
            in selected_ids
            else None
        )
        if shared_candidate is not None:
            accept(shared_candidate, facet_id)
            continue
        if len(selected_chunks) >= max_final_sources:
            continue
        candidate = _pick_first_lane_candidate(
            lane["candidates"],
            selected_ids=selected_ids,
            selected_documents=selected_documents,
            prefer_new_document=broad and lane["role"] not in {
                "premise_support",
                "premise_counter",
                "framing",
            },
        )
        if candidate is not None:
            accept(candidate, facet_id)
    # Fill remaining positions round-robin so one prolific lane cannot monopolize context.
    candidate_offsets = {str(lane["facet_id"]): 0 for lane in ordered_lanes}
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

    original_query = str(_plan_value(original_facets[0], "search_query", ""))
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
                "document_hints": list(lane["document_hints"]),
                "candidate_chunk_ids": [
                    str(candidate.get("chunk_id") or "")
                    for candidate in lane["candidates"]
                ],
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
    requirements = _plan_value(plan, "requirements", ())
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
            "lane_selection": "one_each_then_round_robin",
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
        },
        "lanes": safe_lane_trace,
        "candidates": {},
        "selection": {
            "primary_chunk_ids": [
                str(chunk.get("chunk_id") or "") for chunk in selected_chunks
            ],
            "discarded": [],
            "document_distribution": {
                "selected_primary": _document_distribution(selected_chunks),
                "context": _document_distribution(final_chunks),
            },
            "context": [
                {
                    **_safe_chunk_fields(chunk),
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
