import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import chromadb
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "chroma_db"

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


def build_context(results) -> str:
    metadatas = results.get("metadatas", [[]])[0]

    context_blocks = []

    for i, meta in enumerate(metadatas, start=1):
        block = (
            f"[Source {i}]\n"
            f"Document: {meta.get('document', 'N/A')}\n"
            f"Chapter: {meta.get('chapter_title', 'N/A')}\n"
            f"Chunk ID: {meta.get('chunk_id', 'N/A')}\n"
            f"Paragraphs: {meta.get('paragraph_start', '?')}–{meta.get('paragraph_end', '?')}\n"
            f"Text:\n{meta.get('text', '')}\n"
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