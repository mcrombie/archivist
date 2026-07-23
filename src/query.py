from collections.abc import Mapping

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
    semantic_primary_ids = {
        chunk.get("chunk_id")
        for chunk in get_filtered_primary_chunks(
            results,
            prefer_hybrid=False,
        )
    }
    final_chunks = finalize_context_chunks(results)
    final_ids = {chunk.get("chunk_id") for chunk in final_chunks}
    lookup = get_chunk_lookup()
    hybrid = results.get("hybrid")
    trace = hybrid.get("trace") if isinstance(hybrid, Mapping) else None
    fused_primary_ids = (
        {
            str(chunk_id)
            for chunk_id in hybrid.get("primary_chunk_ids", [])
        }
        if isinstance(hybrid, Mapping)
        else semantic_primary_ids
    )

    print("\nRaw semantic top-k:")
    for rank, (chunk, distance) in enumerate(zip(metadatas, distances), start=1):
        chunk_id = str(chunk.get("chunk_id", "N/A"))
        if should_skip_document(chunk.get("document", "")):
            semantic_status = "dropped: structural document filter"
        elif chunk_id not in lookup:
            semantic_status = "dropped: missing from disk lookup"
        elif chunk_id not in semantic_primary_ids:
            semantic_status = f"filtered: distance > {MAX_PRIMARY_DISTANCE}"
        else:
            semantic_status = "eligible"
        fused_status = (
            "selected"
            if chunk_id in fused_primary_ids
            else "not selected"
        )
        context_status = "kept" if chunk_id in final_ids else "not kept"
        print(
            f"  {rank}. {chunk_id}  distance={distance:.4f}"
            f"  semantic={semantic_status}"
            f"  fused={fused_status}"
            f"  context={context_status}"
        )

    if isinstance(trace, Mapping):
        candidates = trace.get("candidates", {})
        lexical = candidates.get("lexical", []) if isinstance(candidates, Mapping) else []
        fused = candidates.get("fused", []) if isinstance(candidates, Mapping) else []
        print("\nLexical candidates (text-free BM25 diagnostics):")
        for item in lexical:
            print(
                f"  {item.get('rank')}. {item.get('chunk_id', 'N/A')}"
                f"  bm25={float(item.get('bm25_score') or 0):.4f}"
            )
        print("\nFused primary ranking:")
        for item in fused:
            selected = "selected" if item.get("selected_primary") else "not selected"
            print(
                f"  {item.get('rank')}. {item.get('chunk_id', 'N/A')}"
                f"  rrf={float(item.get('rrf_score') or 0):.6f}  {selected}"
            )

    print("\nFinalized model context:")
    context_trace = (
        trace.get("selection", {}).get("context", [])
        if isinstance(trace, Mapping)
        else []
    )
    origins = {
        str(item.get("chunk_id")): str(item.get("origin"))
        for item in context_trace
        if isinstance(item, Mapping)
    }
    for source_number, chunk in enumerate(final_chunks, start=1):
        chunk_id = str(chunk.get("chunk_id") or "N/A")
        origin = origins.get(
            chunk_id,
            "primary"
            if chunk.get("chunk_id") in fused_primary_ids
            else "neighbor",
        )
        print(f"  Source {source_number}: {chunk_id} ({origin})")


def main() -> None:
    while True:
        query = input("\nAsk a question (or 'exit'): ").strip()
        if query.lower() == "exit":
            break
        inspect_query(query)


if __name__ == "__main__":
    main()
