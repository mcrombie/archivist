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


def search(query: str, n_results: int = 5):
    query_embedding = embed_query(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["metadatas", "distances"]
    )

    return results


def main() -> None:
    while True:
        query = input("\nAsk a question (or 'exit'): ").strip()

        if query.lower() == "exit":
            break

        results = search(query)

        print("\nTop results:\n")

        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not metadatas:
            print("No results found.")
            continue

        for i, meta in enumerate(metadatas, start=1):
            distance = distances[i - 1] if i - 1 < len(distances) else None

            print(f"Result {i}")
            print(f"Document: {meta.get('document', 'N/A')}")
            print(f"Chapter: {meta.get('chapter_title', 'N/A')}")
            print(f"Chunk ID: {meta.get('chunk_id', 'N/A')}")
            print(f"Paragraphs: {meta.get('paragraph_start', '?')}–{meta.get('paragraph_end', '?')}")
            if distance is not None:
                print(f"Distance: {distance:.4f}")

            text = meta.get("text", "")
            preview = text[:900] + ("..." if len(text) > 900 else "")
            print(preview)
            print("-" * 80)


if __name__ == "__main__":
    main()