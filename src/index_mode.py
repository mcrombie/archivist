import os
import json
import re
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import chromadb
from openai import OpenAI

from filters import SKIP_FILES

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "chroma_db"
CHUNKS_FILE = BASE_DIR / "output" / "chunks.json"

MAX_PRIMARY_DISTANCE = 1.05
MAX_FINAL_SOURCES = 8

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
collection = chroma_client.get_or_create_collection(name="manuscript")


def load_chunks() -> list[dict]:
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_chunk_lookup(chunks: list[dict]) -> dict[str, dict]:
    return {chunk["chunk_id"]: chunk for chunk in chunks}


def get_neighbor_chunk_ids(chunk_id: str) -> list[str]:
    match = re.match(r"^(.*)_(\d{3})$", chunk_id)
    if not match:
        return []

    prefix = match.group(1)
    number = int(match.group(2))

    neighbors = []
    if number > 1:
        neighbors.append(f"{prefix}_{number - 1:03}")
    neighbors.append(f"{prefix}_{number + 1:03}")

    return neighbors


ALL_CHUNKS = load_chunks()
CHUNK_LOOKUP = build_chunk_lookup(ALL_CHUNKS)


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
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    primary_chunks = []

    for meta, dist in zip(metadatas, distances):
        if dist <= max_distance:
            primary_chunks.append(meta)

    if not primary_chunks:
        primary_chunks = metadatas

    return primary_chunks


def expand_with_neighbors(primary_chunks: list[dict]) -> list[dict]:
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
            if chunk and cid not in seen:
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


def find_exact_match_chunks(term: str, chunks: list[dict]) -> list[dict]:
    """
    Return chunks whose text contains the term as a case-insensitive substring.
    """
    term_lower = term.lower().strip()
    matches = []

    for chunk in chunks:
        # Filter chunks
        if chunk.get("document") in SKIP_FILES:
            continue

        text = chunk.get("text", "").lower()
        if term_lower in text:
            matches.append(chunk)

    return matches


def finalize_index_context(term: str, semantic_results) -> list[dict]:
    """
    Prefer exact text matches for index terms; fall back to semantic retrieval.
    """
    exact_matches = find_exact_match_chunks(term, ALL_CHUNKS)

    seen = set()
    final_chunks = []

    # First: exact matches
    for chunk in exact_matches:
        cid = chunk["chunk_id"]
        if cid not in seen:
            final_chunks.append(chunk)
            seen.add(cid)

    # Then: neighbors of exact matches
    for chunk in exact_matches:
        for neighbor_id in get_neighbor_chunk_ids(chunk["chunk_id"]):
            neighbor = CHUNK_LOOKUP.get(neighbor_id)
            if neighbor and neighbor["chunk_id"] not in seen:
                final_chunks.append(neighbor)
                seen.add(neighbor["chunk_id"])

    # Then: semantic fallback if exact matches are sparse
    primary_chunks = get_filtered_primary_chunks(semantic_results)
    semantic_expanded = expand_with_neighbors(primary_chunks)

    for chunk in semantic_expanded:
        cid = chunk["chunk_id"]
        if cid not in seen:
            final_chunks.append(chunk)
            seen.add(cid)

    return final_chunks[:MAX_FINAL_SOURCES]


def generate_index_entry(term: str, final_chunks: list[dict]) -> str:
    context = build_context(final_chunks)

    prompt = f"""You are helping build a back-of-the-book index for a historical manuscript.

Using only the provided sources, produce a candidate index entry for the term below.

Term:
{term}

Instructions:
- Write a 2-4 sentence summary of how this term is used in the manuscript.
- Then list the strongest candidate locations.
- Then suggest 0-5 possible subentries if they are clearly supported by the sources.
- Be cautious: if the term is only mentioned briefly or weakly, say so.
- Do not invent page numbers.
- Use source numbers when making claims, like [Source 2].

Format exactly like this:

Index term: <term>

Summary:
<summary>

Key locations:
- [Source X] <chapter / chunk / brief note>
- [Source X] <chapter / chunk / brief note>

Suggested subentries:
- <subentry>
- <subentry>

Sources:
{context}
"""

    response = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    return response.output_text


def main() -> None:
    while True:
        term = input("\nEnter index term (or 'exit'): ").strip()

        if term.lower() == "exit":
            break

        results = retrieve(term)
        final_chunks = finalize_index_context(term, results)
        output = generate_index_entry(term, final_chunks)

        print("\nCandidate index entry:\n")
        print(output)

        print("\nSources shown to model:\n")
        for i, chunk in enumerate(final_chunks, start=1):
            print(f"Source {i}")
            print(f"  Chapter: {chunk.get('chapter_title', 'N/A')}")
            print(f"  Chunk ID: {chunk.get('chunk_id', 'N/A')}")
            print(f"  Paragraphs: {chunk.get('paragraph_start', '?')}–{chunk.get('paragraph_end', '?')}")
            print("-" * 60)


if __name__ == "__main__":
    main()