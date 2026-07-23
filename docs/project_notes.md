# Archivist Project Notes

## Owner follow-up: replace the manuscript snapshot

Before corpus or retrieval work resumes, Michael should provide or identify the authoritative,
current manuscript for *Cradle of the Empire*. Archivist is still indexed from the April 1, 2026
Markdown export. A clean re-ingest must be accompanied by the source/chunk hash manifest planned
for Brief 2 so the application can identify exactly which manuscript version it is using.

## Deferred: characterize the current RAG before optimizing it

The present RAG is a basic semantic-retrieval baseline. Potential improvements—including hybrid
retrieval, reranking, threshold calibration, query routing, and chunking changes—remain deferred
until the canonical manuscript is installed and the neutral evaluation baseline exists. This
conversation-design pass deliberately does not change embeddings, retrieval parameters, the
Answer Mode prompt, or the generation model.

## Current UI scope

The reader-facing interface is being treated separately from retrieval quality. It may support a
multi-turn transcript, contextual follow-up resolution, and selectable visual vibes while Neutral
remains the default answer perspective. Visual vibes are presentation only and must never alter
retrieval, source ordering, citations, or answer prompts.
