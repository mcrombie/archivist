# Archivist blog notes

Working notes for the announcement and demonstration of Archivist. This file is a development
journal, not polished post copy. Keep claims here factual, dated when possible, and clearly mark
anything that still requires measurement.

## The central story

Archivist is a book-specific retrieval-augmented conversation interface for *Cradle of the
Empire*. It is designed to answer questions from the manuscript, show the passages supporting its
answers, and eventually measure retrieval and grounding rigorously.

The strongest blog angle is not simply “I connected a book to an LLM.” The more interesting story
is the progression from a plausible RAG demo toward a system whose retrieval, citations,
faithfulness, abstention, costs, privacy boundaries, and failure modes can be inspected.

Important distinction for the post:

- The reader experience can be elegant, conversational, and visually distinctive.
- The evaluated path must remain neutral, reproducible, and independent of presentation.
- Good-looking answers are not yet evidence that the RAG is good. The gold-set evaluation is being
  built precisely so that claim can eventually be made with numbers.

## Development chronology

### 2026-07-21 — From generic document tool to a book-specific experience

- Removed the opening manuscript-upload decision from the primary path. Archivist now opens
  directly to the built-in *Cradle of the Empire* corpus.
- Temporarily removed Index Mode and manuscript-viewer controls from the reader interface. At this
  stage they created conceptual noise around the one important action: asking the book a question.
- Added an introduction explaining what Archivist is and used the book’s cover art as the visual
  anchor.
- Reworked the interface into a dark historical “reading room” rather than a generic utility UI.
- Added the scroll transition from the cover-led opening composition into a centered, full-width
  answer view. The cover establishes the book; it then recedes when the reader needs room to read.
- Redesigned answers as archival paper objects and displayed each user question immediately above
  its answer.
- Unified the Answer Mode prompt, source numbering, and retrieval primitives so the command-line
  and web paths no longer represented subtly different systems.

Useful blog lesson: visual hierarchy followed product clarity. The interface improved most after
the product stopped pretending to be a generic upload-and-analyze tool.

### 2026-07-22 — Conversation, interpretation, and cost visibility

- Converted the one-shot answer page into a multi-turn conversation. Earlier questions, answers,
  and sources remain visible during the open session.
- Follow-up questions use recent dialogue to resolve references, but every turn retrieves fresh
  manuscript evidence. Previous model answers are treated as untrusted conversational context,
  not as factual source material.
- Added a compact follow-up composer, collapsed source panels, retry, copy, and new-conversation
  controls after testing showed that repeated full-size answer and source panels overwhelmed the
  viewport.
- Added seven presentation “vibes,” adapted from the Cromblog design system. A vibe changes only
  appearance.
- Separated interpretive controls into three axes:
  - Historiographical lens
  - Voice
  - Worldview
- Preserved Evidence-first + Scholarly + None as the neutral baseline. Interpretive controls can
  affect expression and framing, but may not change retrieval, source order, or citation rules.
- Added a local cost ledger using token counts returned by completed OpenAI calls. It records
  estimated cost by operation, turn, conversation, month, and all time without storing manuscript
  text, questions, or answers.
- Added optional monthly warnings and a local hard stop. OpenAI’s Usage Dashboard remains the
  billing source of truth.

Useful blog lesson: perspective is only an honest experiment if the evidence stays fixed while the
framing changes. That requires the neutral measurement path first.

### 2026-07-23 — Canonical manuscript and model configuration

- Replaced the older reader corpus with the authoritative July 6 DOCX.
- The deterministic preparation produced:
  - 36 Markdown documents
  - 910 total chunks
  - 34 Heading 1 sections
  - 629 resolved footnotes
- The source DOCX SHA-256 is
  `81d172186475e8f9a63070ceacb85cac0ffb411159b02cf4acc59fb78eedc3b8`.
- The initial eligible corpus contained 488 chunks. With explicit owner authorization, those
  chunks were embedded using `text-embedding-3-small` in 10 calls totaling 215,381 tokens.
- The local ledger estimated that indexing run at `$0.00430762`. Preserve the word “estimated” in
  public copy.
- Configured the reader-facing answer generator and follow-up resolver to use `gpt-5.6-sol` with
  explicit medium reasoning effort and medium verbosity.
- Important evaluation caveat: `gpt-5.6-sol` is currently an undated identifier, so it is a
  development configuration rather than a valid run-of-record pin under the project’s stricter
  reproducibility contract.
- Improved chat usability so a new follow-up answer begins in a readable viewport rather than
  beneath a wall of previous sources and controls.

### 2026-07-23 — Introduction-first corpus boundary

- The owner set the evaluated manuscript boundary to begin with `05_Introduction.md`.
- Excluded the four structural documents before the Introduction:
  - `01_Front Matter.md`
  - `02_Table of Contents.md`
  - `03_Acknowledgments.md`
  - `04_Note on Illustrations.md`
- Bibliography-tagged documents remain excluded.
- The Epilogue, Afterword, and Appendices A–D remain retrieval targets.
- This changed the eligible corpus from 488 to 481 chunks.
- No re-embedding call was required. Archivist copied and verified the 481 already-computed vectors
  into a fresh staged index, preserved the other nine Chroma collections, and promoted the result
  with a recoverable backup of the prior 488-vector store.
- The active corpus manifest SHA-256 is
  `b7ff94315a3f1f28c831e2c3ca62c385567d2b1447c19ff45139d175c3ff3c17`.
- Verification at this milestone: 123 tests passed, 1 skipped; Ruff and diff checks passed.

Useful blog lesson: a corpus boundary is part of experimental identity. Changing it is not merely
hiding a few UI files; the retrieval filter, vector store, manifest, evaluation contract, and gold
locations all have to agree.

### 2026-07-23 — Gold-set intake and private owner review

- Received ten owner-authored questions with expected claims and known chapter-level targets.
- The pilot spans six strata:
  - focused biographical
  - focused analytical
  - conceptual
  - broad thematic
  - out of corpus
  - adversarial premise
- The questions are designed to expose different failure surfaces: name changes, appendix
  retrieval, precise figures, cross-chapter synthesis, clean absence, near-miss overclaiming, and a
  false premise.
- No gold question had been run through Archivist when the intake and location-review materials
  were prepared. This prevents system output from influencing ground truth.
- Strengthened gold validation so a supporting or relevant chunk must both exist in the manifest
  and remain retrieval-eligible.
- Prototyped a private, gitignored owner-review packet and local review interface:
  - all 481 eligible chunks are available;
  - every displayed chunk text hash is checked against the manifest;
  - literal searches and owner-named document filters assist navigation without preselecting
    locations;
  - the owner can create atomic claims, choose essential/optional status, assign supporting and
    relevant chunks, record must-not-claim propositions, and lock each approval group;
  - a Content Security Policy blocks network connections from the private review page;
  - manuscript text never enters the committed fixture;
  - the exported review state contains only questions, owner-authored paraphrases, flags, chunk
    IDs, notes, and approvals.
- The owner correctly challenged whether this formal annotation work was necessary before the
  first practical RAG comparison. The supplied document already contains ten questions, expected
  replies, retrieval targets, and failure modes—enough for a useful directional before/after run.
- Removed the temporary owner-review UI and its local server the same day. The practical pilot now
  runs directly from the frozen owner document, with no additional annotation burden.
- Exact chunk-level gold annotation remains useful later for publication-grade recall and citation
  metrics, but it is no longer blocking the first baseline.

Useful blog lessons: build only the evaluation machinery needed for the decision immediately in
front of the project, and do not confuse rigor with ceremony. The frozen expected-answer document
can establish a practical baseline now; stricter chunk-level ground truth can be added when the
project is ready to publish exact retrieval metrics. The test itself still must not be rewritten
in response to system output.

### 2026-07-23 — First neutral practical baseline

- Froze the owner's original ten-question document by SHA-256, preserved the question order, and
  recorded a claim checklist before viewing any generated answers.
- Ran all ten questions once as independent conversations with:
  - Evidence-first historiographical lens
  - Scholarly voice
  - no worldview
  - five primary retrieval results
  - `text-embedding-3-small` query embeddings
  - `gpt-5.6-sol` answer generation
- Each question made exactly two paid calls: one query embedding and one answer generation. There
  were no follow-up-resolution calls, judge-model calls, errors, or retries.
- The local ledger estimated the ten-question run at `$0.30459608`. The before/after all-time
  ledger delta matched that total exactly. Median end-to-end response time was 7.025 seconds, with
  a 3.182–11.429-second range.
- Directional human comparison found 21 of 58 strictly defined essential claim atoms present, 34
  absent, and three contradicted. This is useful diagnostic bookkeeping, not a single quality
  score and not a publication-grade metric.
- Focused retrieval sometimes worked well:
  - the NSC-68 question preserved the exact budget figures and causal frame;
  - the Dulles answer distinguished the brothers and ignored the Dulles Technology Corridor
    distractor;
  - the Paquiquineo answer reached both Chapter 2 and Appendix B.
- The run exposed two separate failure classes:
  - retrieval omitted required sections, especially on broad, near-miss, and false-premise
    questions;
  - generation sometimes omitted essential material that was already present in final context.
- Both broad synthesis questions failed source spread. One reconstructed only a loose three-
  document resemblance rather than the requested institutional chain; the other collapsed
  entirely to Chapter 17.
- All three special behavior tests failed in informative ways:
  - the clean-absence answer correctly denied treatment, then added unnecessary adjacent history;
  - the COVID near-miss safely declined but failed to retrieve the qualified Epilogue discussion;
  - the adversarial 1898 question accepted the false premise and produced a polished but
    fundamentally wrong founding narrative from Chapter 16 alone.
- All ten answers used syntactically valid, resolvable source numbers. This verifies citation
  plumbing, not citation accuracy or complete claim support.
- The immediate optimization targets are now concrete: hybrid lexical/semantic retrieval,
  reranking, broad-query decomposition with source diversity, corpus-level absence checks,
  adversarial-premise routing, and a generation completeness pass.
- Kept the detailed requests, responses, retrieved manuscript passages, rubric, timings, and costs
  private under gitignored `runtime/evaluations/`. No manuscript text entered this file.
- After removing the overbuilt owner-review UI, verification remained clean: 123 backend tests
  passed, one skipped, and the production frontend build succeeded.

Useful blog lesson: the most valuable baseline result was not a score. It was a map of where the
system fails. Fluent prose concealed a catastrophic false-premise error, while several weaker
answers had already retrieved the facts they failed to use. Retrieval and generation therefore
need to be measured and improved separately.

### 2026-07-23 — First retrieval optimization cohort

- Replaced Answer Mode's semantic-only selection with one shared deterministic hybrid retrieval
  path for the CLI and conversational web app.
- Each question still makes one paid query-embedding call. Archivist now requests a 20-result
  semantic candidate pool from the existing Chroma index and computes a second lexical ranking
  locally, so the lexical work adds no OpenAI API charge.
- The local ranker uses versioned BM25 scoring and normalizes Unicode and possessives, improving
  the chance that complete names and distinctive phrases enter consideration.
- Semantic and lexical ranks are fused with equal-weight reciprocal-rank fusion (`k=60`).
- Source diversity is deliberately guarded:
  - it runs only for questions classified as broad synthesis;
  - it initially limits one document to three primary passages;
  - a different-document candidate cannot replace stronger evidence unless its fused score is at
    least 75% of the strongest deferred candidate;
  - if useful diversity is unavailable, the selector backfills in fused-rank order.
- All selected primary passages are now placed into the model context before optional immediate
  neighbors. This prevents neighbors of the first result from consuming the eight-source limit
  before later primary evidence can appear.
- The raw semantic top five remain intact and separately inspectable. This matters because the
  project can now distinguish “what vector search returned” from “what hybrid retrieval selected”
  and from “what the model actually saw.”
- Added an opt-in, text-free retrieval trace under gitignored
  `runtime/retrieval-diagnostics/`. It records ranks, distances, scores, fallback states,
  contract-facing displacement causes, source order, corpus hashes, Chroma distance space, and
  effective parameters, but rejects raw questions, prompts, Chroma metadata blobs, and manuscript
  text.
- Index Mode was intentionally left on its previous exact-match and five-result semantic-fallback
  behavior through a separate wrapper around the same semantic-query primitive; it does not run
  lexical ranking or hybrid fusion.
  The neutral answer prompt, GPT-5.6 Sol settings, conversation behavior, citations, and public API
  response shape were also left unchanged.
- Implementation verification made no OpenAI calls: 140 backend tests passed, one opt-in live test
  was skipped, Ruff passed, and the diff check passed.
- This change opens a new retrieval cohort. It is not yet evidence that the RAG is better. The next
  valid comparison is a paired rerun of the same frozen ten-question test.
- Expected limits remain:
  - lexical fusion cannot retrieve a subject that truly has no literal corpus match;
  - semantic-only near matches still depend on vector quality;
  - a phrase match can reinforce a false premise rather than detect it;
  - broad-query classification and source diversity do not replace future query decomposition,
    reranking, corpus-level absence checks, or adversarial-premise routing.

Useful blog lesson: “hybrid search” is not one switch. It is a chain of explicit, reproducible
choices—candidate depth, tokenization, score fusion, diversity safeguards, and context ordering.
Keeping the untouched vector-search results beside the final context makes it possible to tell
which choice helped or hurt.

## Suggested demo sequence

1. Open the cover-led landing page and briefly explain that the app is built around one specific
   manuscript rather than asking the reader to upload a file.
2. Ask a non-gold, focused question so the public demo does not contaminate an unfinished
   evaluation item.
3. Show the transition into the full-width answer and open one cited source.
4. Ask a natural follow-up containing a pronoun or shorthand reference to demonstrate
   conversational continuity.
5. Show that the second turn retrieves its own evidence rather than treating the earlier answer as
   truth.
6. Open the interpretive controls and explain the three-axis design, then return to the neutral
   baseline.
7. Change a visual vibe to demonstrate that appearance is isolated from retrieval.
8. Open the cost panel and distinguish local estimates from authoritative billing.
9. End with the evaluation work: paragraph-addressable chunks, the owner-authored test set, the
   practical before baseline, and the plan to report failure modes instead of relying on
   impressive examples.

## Screenshots or clips worth capturing

- The opening composition with the cover and product introduction.
- The cover fading away while the first answer centers.
- The archival-paper answer treatment with a visible citation.
- A compact follow-up turn with prior sources collapsed.
- Historiographical lens, Voice, and Worldview shown as separate controls.
- Two different visual vibes displaying the same conversation.
- The local cost panel with an estimated per-turn and monthly total.
- The frozen ten-question pilot document beside a compact before/after results table, without
  exposing expected-answer or manuscript text.

## Claims to avoid until measurement exists

- Do not call the current RAG accurate, optimized, production-grade, or state of the art.
- Do not present the ten-question practical baseline as a formal run of record, publication-grade
  benchmark, or statistically representative sample.
- Do not publish recall, citation-accuracy, faithfulness, or abstention numbers until the harness
  has produced them under a complete run identity.
- Do not claim personality modes preserve facts until each mode passes the same grounding checks.
- Do not present local cost estimates as invoices.
- Do not imply conversation history survives a page reload; it currently lasts only for the open
  page.

## Privacy and publishing guardrails

- Never commit or publish manuscript text, full chunks, private review pages, or source files.
- Public screenshots should show only short excerpts necessary to explain citations.
- Do not expose endpoints that return arbitrary full chunks or stream source documents.
- Use a representative subset, rate limiting, and short excerpts before any public deployment.
- API keys stay server-side and out of frontend storage.

## Open threads for later entries

- Paired after-run results against the unchanged ten-question practical baseline.
- Later conversion of the practical pilot into exact chunk-level gold data if publication-grade
  retrieval and citation metrics require it.
- Retrieval-only pilot results before any answer generation is graded.
- Judge-human agreement and the final faithfulness/abstention thresholds.
- A pinned dated generator snapshot suitable for a run of record.
- Baseline retrieval, citation, faithfulness, and abstention measurements with run-to-run spread.
- Measurement-driven retrieval changes such as hybrid search, reranking, or query routing.
- Durable saved conversations.
- Public-demo corpus subset and manuscript-protection controls.

## Update convention

Add a dated subsection after any change that materially affects:

- the product story or reader workflow;
- corpus identity or privacy;
- retrieval, generation, or citations;
- model configuration or spend;
- evaluation definitions, gold provenance, or measured results; or
- a limitation that should be disclosed in the announcement.

Record what changed, why it mattered, what was deliberately not claimed, and the verification
performed.
