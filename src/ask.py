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


def load_chunks() -> list[dict]:
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_chunk_lookup(chunks: list[dict]) -> dict[str, dict]:
    return {chunk["chunk_id"]: chunk for chunk in chunks}


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


def expand_with_neighbors(results) -> list[dict]:
    """
    Expand retrieved chunks with immediate neighbors and de-duplicate them.
    """
    retrieved = results.get("metadatas", [[]])[0]

    expanded = []
    seen = set()

    for meta in retrieved:
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


def build_context(results) -> str:
    expanded_chunks = expand_with_neighbors(results)

    context_blocks = []

    for i, chunk in enumerate(expanded_chunks, start=1):
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


def answer_question(question: str, n_results: int = 5):
    results = retrieve(question, n_results=n_results)
    context = build_context(results)

    prompt = f"""You are a research assistant for a historical manuscript about Virginia and the American empire.

Answer the question using only the provided sources.
Cite source numbers inline after major claims, like [Source 2].
If the sources are insufficient, say so.
Prefer specific, concrete answers over vague summaries.

Question:
{question}

Sources:
{context}
"""

    response = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    return response.output_text, results


def main() -> None:
    while True:
        question = input("\nAsk a question (or 'exit'): ").strip()

        if question.lower() == "exit":
            break

        answer, results = answer_question(question)

        print("\nAnswer:\n")
        print(answer)

        print("\nRetrieved sources:\n")
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, meta in enumerate(metadatas, start=1):
            distance = distances[i - 1] if i - 1 < len(distances) else None
            print(f"Source {i}")
            print(f"  Chapter: {meta.get('chapter_title', 'N/A')}")
            print(f"  Chunk ID: {meta.get('chunk_id', 'N/A')}")
            if distance is not None:
                print(f"  Distance: {distance:.4f}")
            print("-" * 60)


if __name__ == "__main__":
    main()