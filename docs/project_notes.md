# Archivist Project Notes

## Canonical manuscript status

Michael supplied the authoritative July 6 DOCX for *Cradle of the Empire*. Its SHA-256 is
`81d172186475e8f9a63070ceacb85cac0ffb411159b02cf4acc59fb78eedc3b8`. The deterministic
preparation is active and verified: 36 Markdown documents, 910 total chunks, 34 Heading 1
sections, and 629 resolved footnotes. The owner has since settled an Introduction-first retrieval
and evaluation boundary: `01_Front Matter.md`, `02_Table of Contents.md`,
`03_Acknowledgments.md`, and `04_Note on Illustrations.md` are excluded, along with documents
matched by the `32_Bibliography.md` sentinel under substring matching. This leaves 481
retrieval-eligible chunks and seven skipped documents; the Epilogue, Afterword, and appendices
remain in scope. A matching 594-page July 6 PDF was used only for secondary visual and pagination
checks because its text is not identical to the newer DOCX.

At the initial July 6 activation, after explicit owner authorization, the 488 chunks then eligible
under the earlier scope were embedded with
`text-embedding-3-small` in 10 calls totaling 215,381 tokens. Archivist's local ledger estimates
the indexing cost at `$0.00430762`. That historical cost remains unchanged. The active
Introduction-first collection reuses 481 of those vectors, made no new embedding API calls, uses
explicit L2 distance, and matches the current text-free corpus manifest, whose SHA-256 is
`b7ff94315a3f1f28c831e2c3ca62c385567d2b1447c19ff45139d175c3ff3c17`.

The former April reader corpus remains recoverable under
`old_manuscript/snapshots/2026-04-active-before-0706/`; a second pre-promotion holding copy is
retained under `runtime/corpus-staging/0706/replaced-active/`. The shared Chroma store's nine
non-reader collections were preserved with identical records and metadata. The immediately
preceding 488-vector store and its manifest remain recoverable under
`runtime/corpus-staging/introduction-scope-20260723/replaced-active/`.

## Current: optimize against the practical neutral baseline

The present RAG is a basic semantic-retrieval system. The canonical manuscript is active and a
frozen ten-question practical neutral baseline now exists, so measured work on hybrid retrieval,
reranking, threshold calibration, query routing, generation completeness, and related changes can
begin. The practical baseline is directional rather than a formal run of record; its role is to
support paired before-and-after development against the unchanged owner test document. The earlier
conversation-design pass deliberately left embeddings, retrieval parameters, the Answer Mode
prompt, and the generation model unchanged. The subsequent model-configuration step changes only
the generation model and its explicit settings; it does not itself tune retrieval or the Answer
Mode prompt.

## Current generation-model configuration

The interactive answer generator and conversational follow-up resolver are separate roles in the
central model configuration. Both currently use the official `gpt-5.6-sol` model through the
Responses API with explicit `medium` reasoning effort and `medium` verbosity. Those values preserve
the effective defaults of the former `gpt-5` integration while preventing future default changes
from silently changing those two sampling choices. The deferred index-generation path shares the
generator settings.

This development configuration is **not** a formal evaluation pin. OpenAI's currently documented
identifier is `gpt-5.6-sol`, without a dated snapshot suffix. Archivist therefore rejects it when
asked to validate a run-of-record model; no dated identifier has been invented, and the stricter
rule in `EVAL_CONTRACT.md` remains unchanged. A formal baseline stays blocked until an official
dated snapshot is available and selected.

## Current UI scope

The reader-facing interface is being treated separately from retrieval quality. It may support a
multi-turn transcript, contextual follow-up resolution, and selectable visual vibes. Answer
framing is exposed as three provisional, independent settings: Historiographical lens, Voice, and
Worldview. Evidence-first + Scholarly + None remains the unchanged Neutral baseline. These answer
settings affect generation only; visual vibes are presentation only. Neither may alter retrieval,
source ordering, or citation rules.
