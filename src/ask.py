import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import chromadb
from openai import OpenAI

import json
import re

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "chroma_db"
CHUNKS_FILE = BASE_DIR / "output" / "chunks.json"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
collection = chroma_client.get_or_create_collection(name="manuscript")

MAX_PRIMARY_DISTANCE = 1.05
MAX_FINAL_SOURCES = 8


def load_chunks() -> list[dict]:
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_chunk_lookup(chunks: list[dict]) -> dict[str, dict]:
    return {chunk["chunk_id"]: chunk for chunk in chunks}


def get_filtered_primary_chunks(results, max_distance: float = MAX_PRIMARY_DISTANCE) -> list[dict]:
    """
    Return the primary retrieved chunks whose distances are within the threshold.
    If filtering removes everything, fall back to the original retrieved chunks.
    """
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    primary_chunks = []

    for meta, dist in zip(metadatas, distances):
        if dist <= max_distance:
            primary_chunks.append(meta)

    # Fallback: if everything gets filtered out, keep the original primary hits
    if not primary_chunks:
        primary_chunks = metadatas

    return primary_chunks


def get_neighbor_chunk_ids(chunk_id: str) -> list[str]:
    """
    Given a chunk_id like '04_Introduction_002', return the previous and next
    chunk IDs if they can be inferred.
    """
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
            if chunk and cid not in seen:
                expanded.append(chunk)
                seen.add(cid)

    return expanded


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


def finalize_context_chunks(
    results,
    max_primary_distance: float = MAX_PRIMARY_DISTANCE,
    max_final_sources: int = MAX_FINAL_SOURCES,
) -> list[dict]:
    """
    Build the canonical final source list used both for model context and display.
    """
    primary_chunks = get_filtered_primary_chunks(results, max_distance=max_primary_distance)
    expanded_chunks = expand_with_neighbors(primary_chunks)

    # Cap final context length
    final_chunks = expanded_chunks[:max_final_sources]

    return final_chunks


def answer_question(question: str, n_results: int = 5):
    results = retrieve(question, n_results=n_results)
    final_chunks = finalize_context_chunks(results)
    context = build_context(final_chunks)

    prompt = f"""You are a historian specializing in the development of the American imperial system through Virginia.

Answer the user's question using only the provided sources.

Cite sources inline after specific claims using [Source X].
Do not group multiple sources only at the end of a paragraph.
Each important factual claim should have its own citation.
If a sentence contains multiple distinct claims, cite each claim separately.
If multiple sources support the same claim, cite them together like [Source 2, Source 3].

Do not place citations only at the end of bullets or paragraphs. Place them immediately after the sentence or clause they support.

Be precise, avoid vague generalizations, and do not invent information.

If the sources do not contain enough information, say so.

Answer in 1–3 short paragraphs or structured bullet points when appropriate.

Question:
{question}

Sources:
{context}
"""

    response = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    return response.output_text, final_chunks


def main() -> None:
    while True:
        question = input("\nAsk a question (or 'exit'): ").strip()

        if question.lower() == "exit":
            break

        answer, final_chunks = answer_question(question)

        print("\nAnswer:\n")
        print(answer)

        print("\nSources shown to model:\n")
        for i, chunk in enumerate(final_chunks, start=1):
            print(f"Source {i}")
            print(f"  Document: {chunk.get('document', 'N/A')}")
            print(f"  Chapter: {chunk.get('chapter_title', 'N/A')}")
            print(f"  Chunk ID: {chunk.get('chunk_id', 'N/A')}")
            print(f"  Paragraphs: {chunk.get('paragraph_start', '?')}–{chunk.get('paragraph_end', '?')}")
            print("-" * 60)
            

if __name__ == "__main__":
    main()