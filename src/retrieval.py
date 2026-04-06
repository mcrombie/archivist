import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import chromadb
from openai import OpenAI

from corpus import ALL_CHUNKS, CHUNK_LOOKUP, get_neighbor_chunk_ids
from filters import should_skip_document


BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "chroma_db"

MAX_PRIMARY_DISTANCE = 1.05
MAX_FINAL_SOURCES = 8

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
collection = chroma_client.get_or_create_collection(name="manuscript")


def embed_query(query: str) -> list[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=query
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


def expand_with_neighbors(primary_chunks: list[dict]) -> list[dict]:
    """
    Expand a list of primary chunks with immediate neighbors and de-duplicate them.
    """
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
            chunk = CHUNK_LOOKUP.get(cid)
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
    max_primary_distance: float = MAX_PRIMARY_DISTANCE,
    max_final_sources: int = MAX_FINAL_SOURCES,
) -> list[dict]:
    primary_chunks = get_filtered_primary_chunks(results, max_distance=max_primary_distance)
    expanded_chunks = expand_with_neighbors(primary_chunks)
    final_chunks = expanded_chunks[:max_final_sources]
    return final_chunks


def build_context(final_chunks: list[dict]) -> str:
    context_blocks = []

    for i, chunk in enumerate(final_chunks, start=1):
        block = (
            f"[Source {i}]\n"
            f"Document: {chunk.get('document', 'N/A')}\n"
            f"Chapter: {chunk.get('chapter_title', 'N/A')}\n"
            f"Chunk ID: {chunk.get('chunk_id', 'N/A')}\n"
            f"Paragraphs: {chunk.get('paragraph_start', '?')}–{chunk.get('paragraph_end', '?')}\n"
            f"Text:\n{chunk.get('text', '')}\n"
        )
        context_blocks.append(block)

    return "\n\n".join(context_blocks)


def find_exact_match_chunks(term: str, chunks: list[dict] | None = None) -> list[dict]:
    """
    Return chunks whose text contains the term as a case-insensitive substring.
    """
    if chunks is None:
        chunks = ALL_CHUNKS

    term_lower = term.lower().strip()
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
    max_primary_distance: float = MAX_PRIMARY_DISTANCE,
    max_final_sources: int = MAX_FINAL_SOURCES,
) -> list[dict]:
    """
    Prefer exact text matches for index terms; fall back to semantic retrieval.
    """
    exact_matches = find_exact_match_chunks(term, ALL_CHUNKS)

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
            neighbor = CHUNK_LOOKUP.get(neighbor_id)
            if neighbor and neighbor["chunk_id"] not in seen and not should_skip_document(neighbor.get("document", "")):
                final_chunks.append(neighbor)
                seen.add(neighbor["chunk_id"])

    # semantic fallback
    primary_chunks = get_filtered_primary_chunks(
        semantic_results,
        max_distance=max_primary_distance,
    )
    semantic_expanded = expand_with_neighbors(primary_chunks)

    for chunk in semantic_expanded:
        cid = chunk["chunk_id"]
        if cid not in seen and not should_skip_document(chunk.get("document", "")):
            final_chunks.append(chunk)
            seen.add(cid)

    return final_chunks[:max_final_sources]