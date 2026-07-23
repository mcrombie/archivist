# Archivist Project Notes

## Canonical manuscript status

Michael supplied the authoritative July 6 DOCX for *Cradle of the Empire*. Its SHA-256 is
`81d172186475e8f9a63070ceacb85cac0ffb411159b02cf4acc59fb78eedc3b8`. The deterministic
offline preparation is staged and verified: 36 Markdown documents, 910 total chunks, 488
retrieval-eligible chunks, 34 Heading 1 sections, and 629 resolved footnotes. A matching
594-page July 6 PDF was used only for secondary visual and pagination checks because its text
is not identical to the newer DOCX.

The reader still uses the April 1 corpus. Promotion is intentionally paused before embedding:
the next step would send the 488 retrieval-eligible manuscript chunks to OpenAI's
`text-embedding-3-small` endpoint. That data transfer requires explicit owner authorization.
No manuscript text has left the machine and no embedding cost has been incurred during staging.

## Deferred: characterize the current RAG before optimizing it

The present RAG is a basic semantic-retrieval baseline. Potential improvements—including hybrid
retrieval, reranking, threshold calibration, query routing, and chunking changes—remain deferred
until the canonical manuscript is installed and the neutral evaluation baseline exists. This
conversation-design pass deliberately does not change embeddings, retrieval parameters, the
Answer Mode prompt, or the generation model.

## Current UI scope

The reader-facing interface is being treated separately from retrieval quality. It may support a
multi-turn transcript, contextual follow-up resolution, and selectable visual vibes. Answer
framing is exposed as three provisional, independent settings: Historiographical lens, Voice, and
Worldview. Evidence-first + Scholarly + None remains the unchanged Neutral baseline. These answer
settings affect generation only; visual vibes are presentation only. Neither may alter retrieval,
source ordering, or citation rules.
