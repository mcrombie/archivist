import os
from functools import lru_cache
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

from corpus import (
    build_chunk_lookup,
    get_all_chunks,
    get_chunk_lookup,
    get_neighbor_chunk_ids,
)
from costs import tracked_embeddings_create
from filters import should_skip_document

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "chroma_db"

MAX_PRIMARY_DISTANCE = 1.05
MAX_FINAL_SOURCES = 8

chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
collection = chroma_client.get_or_create_collection(name="manuscript")


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


def retrieve(query: str, n_results: int = 5):
    query_embedding = embed_query(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["metadatas", "distances"]
    )

    return results


def get_filtered_primary_chunks(results, max_distance: float = MAX_PRIMARY_DISTANCE) -> list[dict]:
    """
    Return the primary retrieved chunks whose distances are within the threshold.
    If filtering removes everything, fall back to the original retrieved chunks.
    """
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    primary_chunks = []

    for meta, dist in zip(metadatas, distances):
        if should_skip_document(meta.get("document", "")):
            continue
        if dist <= max_distance:
            primary_chunks.append(meta)

    if not primary_chunks:
        primary_chunks = [
            meta for meta in metadatas
            if not should_skip_document(meta.get("document", ""))
        ]

    return primary_chunks


def expand_with_neighbors(
    primary_chunks: list[dict],
    lookup: dict[str, dict] | None = None,
) -> list[dict]:
    """
    Expand a list of primary chunks with immediate neighbors and de-duplicate them.
    """
    lookup = lookup if lookup is not None else get_chunk_lookup()
    expanded = []
    seen = set()

    for meta in primary_chunks:
        chunk_id = meta.get("chunk_id")
        if not chunk_id:
            continue

        neighbor_ids = get_neighbor_chunk_ids(chunk_id)
        prev_id = neighbor_ids[0] if len(neighbor_ids) == 2 else None
        next_id = neighbor_ids[-1] if neighbor_ids else None

        ordered_ids = []
        if prev_id:
            ordered_ids.append(prev_id)
        ordered_ids.append(chunk_id)
        if next_id and next_id != prev_id:
            ordered_ids.append(next_id)

        for cid in ordered_ids:
            chunk = lookup.get(cid)
            if not chunk:
                continue
            if should_skip_document(chunk.get("document", "")):
                continue
            if cid not in seen:
                expanded.append(chunk)
                seen.add(cid)

    return expanded


def finalize_context_chunks(
    results,
    chunks: list[dict] | None = None,
    lookup: dict[str, dict] | None = None,
    max_primary_distance: float = MAX_PRIMARY_DISTANCE,
    max_final_sources: int = MAX_FINAL_SOURCES,
) -> list[dict]:
    if lookup is None and chunks is not None:
        lookup = build_chunk_lookup(chunks)
    primary_chunks = get_filtered_primary_chunks(results, max_distance=max_primary_distance)
    expanded_chunks = expand_with_neighbors(primary_chunks, lookup=lookup)
    final_chunks = expanded_chunks[:max_final_sources]
    return final_chunks


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
    )
    semantic_expanded = expand_with_neighbors(primary_chunks, lookup=lookup)

    for chunk in semantic_expanded:
        cid = chunk["chunk_id"]
        if cid not in seen and not should_skip_document(chunk.get("document", "")):
            final_chunks.append(chunk)
            seen.add(cid)

    return final_chunks[:max_final_sources]
