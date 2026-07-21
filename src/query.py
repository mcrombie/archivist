from corpus import get_chunk_lookup
from filters import should_skip_document
from retrieval import (
    MAX_PRIMARY_DISTANCE,
    finalize_context_chunks,
    get_filtered_primary_chunks,
    retrieve,
)


def inspect_query(query: str, n_results: int = 5) -> None:
    results = retrieve(query, n_results=n_results)
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    primary_ids = {
        chunk.get("chunk_id") for chunk in get_filtered_primary_chunks(results)
    }
    final_chunks = finalize_context_chunks(results)
    final_ids = {chunk.get("chunk_id") for chunk in final_chunks}
    lookup = get_chunk_lookup()

    print("\nRaw top-k retrieval:")
    for rank, (chunk, distance) in enumerate(zip(metadatas, distances), start=1):
        chunk_id = chunk.get("chunk_id", "N/A")
        if should_skip_document(chunk.get("document", "")):
            status = "dropped: structural document filter"
        elif chunk_id not in primary_ids:
            status = f"dropped: distance > {MAX_PRIMARY_DISTANCE}"
        elif chunk_id not in lookup:
            status = "dropped: missing from disk lookup"
        elif chunk_id not in final_ids:
            status = "dropped: final source cap"
        else:
            status = "kept in model context"
        print(f"  {rank}. {chunk_id}  distance={distance:.4f}  {status}")

    print("\nFinalized model context:")
    for source_number, chunk in enumerate(final_chunks, start=1):
        origin = "primary" if chunk.get("chunk_id") in primary_ids else "neighbor"
        print(f"  Source {source_number}: {chunk.get('chunk_id', 'N/A')} ({origin})")


def main() -> None:
    while True:
        query = input("\nAsk a question (or 'exit'): ").strip()
        if query.lower() == "exit":
            break
        inspect_query(query)


if __name__ == "__main__":
    main()
