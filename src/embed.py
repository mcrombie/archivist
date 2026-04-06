from pathlib import Path
import json
import os

from dotenv import load_dotenv
load_dotenv()

import chromadb
from openai import OpenAI

from filters import should_skip_document

BASE_DIR = Path(__file__).resolve().parent.parent
CHUNKS_FILE = BASE_DIR / "output" / "chunks.json"
CHROMA_DIR = BASE_DIR / "chroma_db"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))

try:
    chroma_client.delete_collection(name="manuscript")
except Exception:
    pass

collection = chroma_client.get_or_create_collection(name="manuscript")

def load_chunks():
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def embed_texts(texts):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts
    )
    return [item.embedding for item in response.data]


def main():
    chunks = load_chunks()

    print(f"Loaded {len(chunks)} chunks")


    # Filter chunks
    filtered_chunks = [
        chunk for chunk in chunks
        if not should_skip_document(chunk.get("document", ""))
    ]

    print(f"After filtering: {len(filtered_chunks)} chunks")

    # Only use filtered chunks
    texts = [chunk["text"] for chunk in filtered_chunks]
    ids = [chunk["chunk_id"] for chunk in filtered_chunks]

    # Embed in batches (important)
    batch_size = 50

    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        batch_ids = ids[i:i + batch_size]
        batch_chunks = filtered_chunks[i:i + batch_size]

        embeddings = embed_texts(batch_texts)

        collection.add(
            ids=batch_ids,
            embeddings=embeddings,
            metadatas=batch_chunks
        )

        print(f"Embedded batch {i} → {i + len(batch_texts)}")

    print("Done.")


if __name__ == "__main__":
    main()