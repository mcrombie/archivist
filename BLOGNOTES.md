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

### 2026-07-23 — A guided first conversation

- Reworked the opening copy so the product declares its scope immediately: Archivist is a
  conversation with one specific book, not a general-purpose chatbot or an open-web search tool.
- Added three compact orientation cues—searches this book, remembers the thread, and shows
  supporting passages—so readers can understand the interaction model before spending a query.
- Added four catalog-style conversation starters organized by intent: meet a person, understand a
  system, explore an argument, and trace a theme. Selecting one only fills and focuses the
  composer; the reader can edit it, and no API call occurs until Ask Archivist is pressed.
- Chose starter prompts from the earlier non-gold demo pool rather than exposing any of the frozen
  ten-question pilot or its expected claims before the paired rerun.
- Made Start new conversation explicit in the sticky conversation header and at the top of the
  introduction after a thread has opened. The responsive header now keeps a visible “New” label
  instead of reducing the action to an ambiguous plus icon.
- Starting over still clears the page-local transcript, answer-style choices, conversation cost
  scope, and conversation identifier; durable conversation history remains a later feature.
- Retrieval, generation, prompts, model settings, and the frozen evaluation set were deliberately
  unchanged. No paid evaluation call was made during this UI pass.
- Verification: the TypeScript check and Vite production build completed successfully; 140
  backend tests passed and one opt-in live test was skipped.

Useful blog lesson: onboarding can teach both capability and restraint. A good starter should show
what kinds of questions fit the product while leaving the paid send action explicit and preserving
the integrity of the benchmark used to measure later RAG changes.

### 2026-07-23 — Making the chat spend its space on reading

- Compared Archivist’s active conversation with the spatial hierarchy used by ChatGPT and Claude.
  The useful lesson was not to copy their brands or add a sidebar; it was to favor one restrained
  reading column, content-sized user messages, low-weight metadata, and a compact persistent
  composer.
- Narrowed the conversation and composer to a shared 840-pixel reading rail, tightened turn rhythm,
  and made short user questions size to their contents rather than filling most of the column.
- Reduced the sticky conversation header from 72 to 56 pixels. Monthly spend remains available as
  an icon and amount, Start new conversation stays explicit, and the vibe control becomes compact
  without losing its menu.
- Flattened the assistant hierarchy: the turn number is now screen-reader context, the Neutral
  baseline chip is omitted, and customized answer styles remain visible only when they add useful
  information.
- Preserved the archival-paper answer identity while reducing ceremonial chrome: smaller padding,
  a quiet provenance eyebrow instead of a large repeated title, a lighter shadow, denser line
  spacing, and shorter paragraph gaps.
- Replaced long in-answer citation banners with compact numbered markers. Full citation labels
  remain available to assistive technology, native hover text, previews, and the expandable source
  records, so the density gain does not remove inspectability.
- Moved Sources, estimated turn cost, and Copy into one understated post-answer utility row.
  Sources remain keyboard-accessible and expand into the same manuscript evidence cards.
- Reduced the fixed composer footprint and shortened its visible style summary to “Neutral” at the
  default while preserving all three selectors in the disclosure.
- Limited the large last-turn spacer to the pending state; completed turns retain only enough
  clearance to stay readable above the fixed composer.
- Retrieval, prompts, model configuration, conversation context, and the frozen evaluation set did
  not change. No paid API call was made during this redesign.
- Verification: the TypeScript check and Vite production build completed successfully; 140
  backend tests passed and one opt-in live test was skipped.

Useful blog lesson: visual identity does not require every answer to behave like a framed artifact.
The paper texture and typography can carry the archive metaphor while the surrounding interaction
adopts the compact, continuous rhythm readers already understand from modern chat products.

### 2026-07-23 — A quieter opening and an Archivist that helps readers begin

- Compared the opening hierarchy with current ChatGPT and Claude entry screens. The transferable
  lesson was to make one composer the dominant object, then disclose examples, settings, and help
  only when the reader asks for them.
- Reduced the cover from nearly half the desktop viewport to a bounded identity rail while retaining
  the commissioned art and title. On narrow screens the cover now becomes a short banner so the
  question box appears without an introductory scroll.
- Replaced the two-line marketing headline, long explanation, three capability pills, four large
  starter cards, and permanently expanded style controls with one question, one sentence, a compact
  composer, two quiet examples, and one guided-start action.
- Reused the conversation composer’s Answer style disclosure on the opening screen. Historiographical
  lens, Voice, and Worldview remain available, but their three selectors no longer compete with the
  first question.
- Added a two-step, client-side guided start. Archivist first asks whether the reader wants to
  explore a person, event or system, argument or theme, or passage or topic. It then asks what kind
  of treatment would be useful and places an editable question scaffold in the composer with its
  bracketed placeholder selected.
- The guide neither submits a request nor creates a synthetic chat turn. Its questions never enter
  RAG history, never trigger follow-up resolution, never change interpretive settings, and never
  spend an API call.
- Preserved the all-neutral generation path byte for byte so the planned paired ten-question RAG
  rerun remains comparable. Neutral therefore continues to favor a short, direct evidence-based
  answer.
- Added a separate response contract that appears only when at least one interpretive characteristic
  is non-default. It makes the active lens control the answer’s organizing arc, the worldview control
  its stakes, and the voice control diction and cadence. It asks for a direct answer plus a brief
  interpretive bridge and permits one specific, source-grounded next question when that genuinely
  advances the conversation.
- Rewrote each non-default Markdown fragment as a concrete rhetorical pattern rather than a list of
  mood adjectives—for example, tragic answers move from open possibility through consequential
  choice to cost, while triumphalist answers move from challenge through adaptation to durable
  capacity. Evidence, citation, uncertainty, and anti-invention guardrails remain shared.
- No model, retrieval, embedding, corpus, neutral prompt, or paid evaluation setting changed, and no
  API call was made during this pass.
- Verification: the TypeScript check and Vite production build passed; the focused interpretive
  suite passed all 28 tests. The full backend suite reached 149 passing and one skipped test, with
  three failures isolated to a pre-existing uncommitted `src/web_project.py` change that removes
  corpus hashes and the semantic-only index helper; that unrelated edit was deliberately preserved.

Useful blog lesson: conversational onboarding does not require another model call. A small local
exchange can teach the product’s shape, help a reader form a better query, and protect both privacy
and evaluation integrity. Personality also becomes more legible when prompts prescribe observable
organization and sentence behavior instead of asking the model to “sound tragic” or “be romantic.”

### 2026-07-23 — Clean semantic/hybrid paired rerun

- Before spending on the comparison, found and corrected an accidental evaluation-boundary
  regression introduced during the UI work. Answer traces again carry corpus hashes, and deferred
  Index Mode again uses its semantic-only helper rather than the new hybrid Answer Mode path.
- Recorded the correction as commit
  `c6c54f00e02afc7e20485c6bda6b9b2eb860a018`. Preflight verification passed 152 backend tests with
  one skipped.
- Built the semantic side from the clean pre-hybrid commit
  `f92e4a882090f78512f651f71f04c8b7e0e1853d` in an isolated worktree and the hybrid side from the
  corrected current commit. Both used the same frozen ten questions, 58-claim rubric, 481-passage
  corpus, neutral prompt, model configuration, empty histories, and request settings.
- The first three semantic calls exposed a harness problem: the OpenAI SDK still had its implicit
  two-retry allowance even though the evaluation runner itself never retried. No retry was observed,
  but those outputs were excluded. Both cohorts restarted with SDK retries explicitly disabled and
  a private live-server identity checked before any paid question.
- Each clean cohort completed exactly ten query embeddings and ten answer generations. There were
  no follow-up, judge, corpus-embedding, failed, duplicate, or unpriced events.
- Estimated spend:
  - clean semantic: `$0.23756083`;
  - clean hybrid: `$0.35567608`;
  - clean pair: `$0.59323691`;
  - excluded diagnostic: `$0.11546479`;
  - total against the owner's `$0.90` authorization: `$0.70870170`.
- Do not use the raw semantic-versus-hybrid price difference as a retrieval-cost claim. The repeated
  semantic questions received cache reads after the aborted diagnostic, while the hybrid cohort
  began with cold cache writes. The hybrid run also sent more context.
- Hybrid retrieval increased final source breadth:
  - 62 to 79 final passages;
  - 1.8 to 3.0 distinct documents per question on average;
  - 12/26 to 15/26 expected document groups represented in final context.
- That broader context did not improve strict answer completeness in this single paired sample.
  Both cohorts covered 19 of 58 essential claims. Semantic recorded 36 absent and three
  contradicted claims; hybrid recorded 35 absent and four contradicted claims.
- The most revealing result was the separation between retrieval and generation:
  - the conceptual question gained its missing Afterword target without gaining the omitted
    argumentative nuance;
  - the broad war-and-power question gained two historical target groups but still covered none of
    its seven composite answer claims;
  - the clean-abstention question acquired analogous chartered-company material and became worse;
  - the false 1898-origin premise remained uncorrected in both cohorts.
- Median response time remained similar: 7.048 seconds for semantic and 7.905 seconds for hybrid.
- All source-number citations were syntactically valid and resolved to returned sources. That still
  measures citation plumbing rather than citation faithfulness.
- This remains a directional development result, not a formal run of record. The generator is an
  undated `gpt-5.6-sol` alias, each retrieval mode has only one sample, and generation is
  nondeterministic.
- Full requests, responses, source passages, exact answer spans, and claim-level grading remain
  private under gitignored `runtime/evaluations/`. No manuscript text was added to the repository.

Useful blog lesson: retrieval breadth and answer completeness are different engineering problems.
Hybrid fusion can put more of the right book in front of the model without making the final answer
more complete. The next gains require query decomposition, premise checking, absence handling, and
a source-bounded completeness pass rather than a still larger undifferentiated context window.

### 2026-07-23 — Designing the evidence-planned RAG pass

- Converted the paired-run failure modes into an implementation design at
  `docs/rag_next_optimization_design.md`. This was a design-only step: it made no OpenAI calls and
  changed no application behavior.
- Designed one shared Answer Mode pipeline rather than four independent patches:
  - query decomposition turns broad and multi-part questions into bounded retrieval facets;
  - premise checking reserves both supporting and counterevidence searches before the answer is
    written;
  - a local corpus scanner separates direct mentions, bounded related material, and misleading
    analogues;
  - a structured evidence-coverage answer maps each user-requested facet to sources before
    rendering concise prose.
- Kept the original question as a global search lane, capped the first design at eight final
  sources, and required all supplemental facet embeddings to share one batched request.
- Chose a one-call structured answer with deterministic validation instead of a draft followed by a
  second model critic. The latter would add serial cost and latency without guaranteeing that the
  critic notices or safely repairs an omission.
- Protected absence claims with a trust boundary: only surface forms mechanically derived from the
  reader's question can certify a direct mention or its absence. Model-suggested synonyms and
  analogues may help discovery but can never prove that the manuscript treats the requested
  subject.
- Defined calibrated outcomes for direct answers, partial answers, bounded near matches, clean
  abstentions, and indeterminate searches. A certified clean abstention skips answer generation
  instead of paying a model to improvise from irrelevant sources.
- Renamed the proposed “source-bounded completeness pass” to `evidence_coverage_v1` in the technical
  design. The evaluation contract already uses “completeness” for citation coverage, so keeping the
  terms separate avoids quietly changing a locked metric.
- Verified against current OpenAI documentation and the installed SDK that the Responses API can
  return strict schema-shaped output through native Pydantic parsing. The design still requires
  application validation because a valid structure does not make a factual decision correct.
- Planned isolation before integration: first test the structured answer against frozen retrieved
  contexts, then test decomposition and evidence routing without answer generation, and only then
  rerun the unchanged ten-question set as a new cohort.

Useful blog lesson: a trustworthy RAG system needs to know more than which passages are “similar.”
It needs an explicit account of what the reader asked, which premise is being tested, whether the
named subject is actually present, which requested facets the sources support, and where the
evidence stops.

### 2026-07-24 - Implementing evidence-planned answers

- Implemented the four planned RAG mechanisms as one shared Answer Mode pipeline for the web app
  and CLI:
  - query decomposition gives broad and multi-part questions bounded retrieval facets;
  - premise-sensitive questions reserve support, counterevidence, and framing lanes;
  - a local evidence gate distinguishes direct treatment, bounded related material, broader
    analogues, clean absence, and indeterminate corpus state;
  - a structured evidence-coverage answer must account for requested requirements and premises
    before deterministic prose rendering.
- Added conversation-aware question resolution. Follow-ups can inherit entities, scope, and
  relationships from earlier user turns. Prior assistant answer text is not sent to the resolver
  and is never accepted as manuscript evidence. Absence certification can use only wording
  traceable to the current or prior user.
- Kept model-call growth bounded. A turn can use a resolver only when history exists, a planner only
  when deterministic routing finds that it is useful, one batched embedding request for all search
  facets, and one structured answer generation. There is no automatic critic, repair retry, or
  second draft. A clean absence makes no generation call.
- Added a strict preflight before paid work. The private corpus manifest, ordered chunk IDs, text
  hashes, character counts, paragraph metadata, collection size, distance metric, and embedding
  model must agree with the live index. The check reads the actual Chroma collection name,
  collection metadata, stored IDs, and per-chunk metadata, so a same-count stale collection cannot
  pass on count alone. A stale or corrupt index fails before paying for follow-up resolution,
  planning, embedding, or an answer.
- Exercised that preflight locally against the current private corpus: 481 eligible chunks matched
  the 481-vector collection with the expected `manuscript` collection and L2 configuration. No
  manuscript text or private evaluation claims were added to source control.
- Improved absence handling so an exact corpus mention outside the initially retrieved eight
  passages can be promoted into answer context. Generic analogues are suppressed after a direct
  hit, and model-invented synonyms cannot certify a near match or an absence.
- Added deterministic premise-correction ordering and source validation. A contradicted premise
  must be corrected first and cite only admitted source numbers; unknown, malformed, duplicate, or
  mismatched coverage data fails closed rather than producing polished unsupported prose.
- Hardened two mechanical edge cases found during review:
  - causal questions such as one named entity affecting another now treat the second entity as the
    requested relationship facet instead of rejecting both as ambiguous subjects;
  - a lowercase ordinary word can no longer masquerade as an acronym derived from a multiword
    name, while explicit uppercase and dotted initialisms remain searchable.
- Extended the local hard cost limit from a turn-start check to a check immediately before every
  tracked OpenAI operation. If a resolver or planner crosses the limit, the next embedding or
  generation call stops unless the reader explicitly authorized the per-request override.
- Added text-free audit mappings from planned facets through selected chunks to final source
  numbers, plus hashes for the active policy, prompts, schemas, style settings, and generator
  configuration. The API now exposes answer status and the evidence decision to the interface.
- Preserved the previous prompt and answer path as a rollback/baseline implementation. Deferred
  Index Mode remains semantic-only, and custom projects without the new manifest identity contract
  continue on the legacy route.
- Verification was local and incurred no OpenAI spend:
  - 274 backend tests passed and one was skipped;
  - Ruff passed across `src` and `tests`;
  - strict OpenAI schema conversion succeeded for the resolver, planner, and evidence answer;
  - the frontend TypeScript/Vite production build passed.
- This is a new retrieval-and-prompt cohort. Its effect on the unchanged ten-question set is not yet
  measured, and no claims of improved answer quality, faithfulness, or abstention accuracy should
  be made until a separately authorized paid run completes.

Useful blog lesson: conversational memory and evidentiary memory should not be the same thing. The
Archivist can remember what the reader meant without treating its own earlier answer as historical
proof. The same separation also makes absence claims safer and keeps every factual reply bounded by
the current manuscript sources.

### 2026-07-24 - Paid two-turn smoke: structurally fixed, qualitatively unfinished

- Ran a clean, neutral two-turn smoke at commit `dbafcd3` with a private isolated ledger, no
  automatic retries, a `$0.12` operational stop, and owner authorization up to `$0.20`.
  - opening question: “How does the manuscript connect tobacco to labor?”
  - follow-up: “How did that relationship shape everyday exchange in Jamestown?”
- The local ledger recorded `$0.09010135`:
  - turn 1: `$0.02621092` and 14.77 seconds;
  - turn 2: `$0.06389043` and 33.01 seconds.
  These remain estimates rather than an invoice.
- Both turns cleared the machine-readable boundary: `answered`, `direct_answer`, valid coverage
  contract, no validation error, eight returned passages, and citations resolving to those
  passages. Neither turn needed the new mechanical normalizer.
- The follow-up resolver worked. It expanded “that relationship” into a self-contained question
  retaining tobacco, labor, Jamestown, and everyday exchange, then retrieved fresh evidence rather
  than using the first answer as evidence.
- Human source review produced a more useful split verdict:
  - turn 1 was only partial under a strict standard. Its claims were mostly supported in aggregate,
    but it omitted the book's clearest mechanism: labor-intensive tobacco created chronic labor
    shortages, encouraging indentures and headrights. The retrieval trace shows that exact linking
    chunk was selected as a primary result and then displaced from the eight-passage generation
    context by an added neighbor.
  - turn 1 also bundled citations across compound claims, and slightly overstated the causal link
    between tobacco work and later cigar-company activism.
  - turn 2 was substantively strong. It recovered the missing mechanism and connected commodity
    payment, units of account, indentured passage, headrights, and river commerce to the follow-up.
    Its remaining citation issue was minor but real: one joint citation should have been split by
    clause for pairwise entailment.
- Turn 2 exposed a separate operational defect. It spent 15.98 seconds attempting model-based query
  planning, fell back locally with `planner_call_failed`, and still answered well. The failed
  planner produced no local usage row, so the `$0.09010135` ledger total may omit a billable request
  and should be checked against the provider dashboard. The exact planner exception was swallowed
  by the fallback and is not recoverable from current diagnostics.
- This smoke confirms that the original generic failure has been repaired, but it does **not**
  establish that the opening answer is complete or strictly cited. The next engineering targets
  are now narrower: protect primary evidence from neighbor displacement, enforce citation
  locality, and make planner failures observable or avoid that planner call when local
  decomposition is sufficient.

Useful blog lesson: a valid response is not necessarily a good response. Schema validation proved
that the model followed the evidence bookkeeping contract; human review still found a missing
causal mechanism and over-broad citations. The most revealing trace was not a low semantic score
but a strong primary passage being selected and then lost during context assembly.

### 2026-07-24 - Repairing the three paid-smoke defects

- Opened the `evidence-planned-v3` cohort to address the three specific defects found in the paid
  two-turn smoke. The evaluation contract and frozen expected-answer material were not changed.
- Corrected context assembly so every selected primary passage survives the eight-source cap.
  Immediate neighbors are now optional enrichment and can fill only unused slots; they can no
  longer displace a later high-value primary.
- Versioned faceted retrieval as `faceted-hybrid-rrf-v2` and added regressions for both sides of
  the rule: a late primary remains present when the context is full, and a neighbor still fills a
  genuinely spare slot.
- Tightened the evidence-coverage generation contract:
  - each answer unit must state one independently checkable factual claim;
  - it must end with exactly one citation group and nothing after it;
  - grouped citations are allowed only when every listed source independently supports that same
    claim;
  - compound facts or facts needing different sources must become separate units.
- Deterministic validation reserves all sentence-ending punctuation for the terminal citation.
  Answer prose must therefore spell out or rephrase period-containing abbreviations, titles,
  initials, and decimals. This makes punctuated extra sentences, multiple citation groups,
  post-citation text, newlines, and semicolon-separated claims mechanically rejectable. It still
  does not pretend that syntax can prove semantic atomicity or source entailment; those require
  source-aware evaluation.
- Bounded resolved follow-ups of the form “the relationship between X and Y as ...” now decompose
  locally into X, Y, and the requested context. This removes the unnecessary planner call exposed
  by the smoke while leaving genuinely ambiguous relationship questions eligible for planning.
  The local grammar preserves names containing words such as “for,” refuses factive or unclear
  tails, and routes any composed search that would exceed its length bound to the planner instead
  of silently truncating it.
- Added versioned planner diagnostics to retrieval traces, answer-run diagnostics, and the local
  ledger. Each turn records `not_called`, `succeeded`, or `failed`; failures retain only safe
  exception classes, allowlisted provider codes, or numeric HTTP statuses. Arbitrary code strings,
  provider exception messages, questions, answers, paths, and manuscript text are not persisted.
- If a failed provider request raises before returning token usage, the local ledger still cannot
  infer its billable cost. The diagnostic now proves that the attempt failed, while the provider
  dashboard remains authoritative for any charge. The exact bounded follow-up from the smoke
  avoids that uncertainty because it no longer makes the planner call.
- Bumped the evidence-coverage prompt to `evidence-coverage-v2`, answer-run diagnostics to version
  2, and the RAG policy to `evidence-planned-v3`. Historical diagnostic rows migrate with an
  explicit `unknown` planner status rather than inventing an outcome.
- Verification was entirely local and incurred no OpenAI spend:
  - 214 focused backend tests passed across retrieval, coverage, planning, conversation, and
    diagnostics persistence;
  - the full backend suite passed with 353 tests and one skipped;
  - Ruff passed across `src` and `tests`;
  - the frontend TypeScript/Vite production build passed.
- This proves the three code defects have local regressions, not that the live answers have
  improved. The correct next gate is one separately authorized paid repeat of the same two-turn
  smoke. Only if that passes should the unchanged ten-question comparison proceed.

Useful blog lesson: the paid smoke did its job by separating three different failure classes that
looked like one mediocre answer: evidence was retrieved and then discarded, citations were
structurally valid but too broad, and a needless orchestration call added latency while hiding its
failure. Each required a different boundary-level repair.

### 2026-07-24 - Paid v3 smoke: content repaired, planner gate still open

- Repeated the same neutral two-turn smoke against clean commit `db7d914` and the 481-passage
  private index. The questions, manuscript, evaluation contract, and expected-answer material were
  unchanged, and no automatic retries occurred.
- The first turn cost an estimated `$0.09000667` and took 32.37 seconds. That left too little room
  under the original `$0.12` operational stop and `$0.05` second-turn reserve, so the runner stopped
  before making another call. The already-authorized run was resumed for only the missing second
  turn with a `$0.18` operational stop under the unchanged `$0.20` total authorization; turn 1 was
  not repeated.
- The completed local estimate was `$0.18810122`:
  - turn 1: `$0.09000667`;
  - turn 2: `$0.09809455`;
  - total elapsed time: 81.99 seconds.
  These are local token-based estimates, not an invoice.
- Both turns passed the machine-readable boundary: answered, direct evidence, valid coverage
  structure, no validation error, and every citation resolving to a returned passage.
- Turn 1 applied the bounded `source_mapping_mismatch` normalization before its final valid result.
  That repair changed only redundant bookkeeping; it did not rewrite prose or citations.
- Human source review also passed both answers:
  - the opening answer now retained the crucial Chapter 4 primary passage that the previous
    neighbor-expansion policy had displaced. It directly covered tobacco payment, labor and
    tobacco as units of account, chronic labor shortage, indentured passage, and headrights;
  - the follow-up connected Jamestown tobacco cultivation to commodity payment, units of account,
    indenture, headrights, and river exchange;
  - the new atomic answer units kept factual sentences locally cited. No materially unsupported or
    overstated claim was found.
- The opening answer was strong but deliberately focused rather than exhaustive. It did not cover
  every later labor development, including servant mortality, estate concentration, or the longer
  transition toward enslaved labor. The smoke therefore confirms the repaired mechanism and
  citation locality, not comprehensive treatment of the manuscript's entire tobacco-and-labor arc.
- The operational planner defect did **not** clear. The resolver produced `How did the relationship
  between tobacco and labor shape everyday exchange in Jamestown?`, while the local grammar only
  recognized a narrower relationship form. The generic `between ... and` broad pattern sent this
  already-resolved question to the model planner, which failed with a safely recorded
  `ValidationError` after 12.93 seconds. Local fallback still retrieved good evidence.
- The failed planner returned no usage object and therefore has no local ledger row. Actual
  provider billing may be higher than `$0.18810122` and should be checked in the OpenAI dashboard.
  No further paid calls were made.
- Audit artifacts have two secondary reproducibility gaps: the v3 run did not persist a standalone
  retrieval trace, and its summary did not include the corpus-manifest hash. Runtime preflight
  still confirmed all 481 eligible chunks against the live index, and comparison with the prior
  trace strongly confirms that all eight selected primaries—including the previously lost Chapter
  4 passage—reached turn 1's final context. Future smoke artifacts should prove both facts directly.
- Compared with the prior v2 smoke, the stricter atomic contract materially increased generated
  output and reasoning. The local estimate rose from `$0.09010135` to `$0.18810122`, and total
  elapsed time rose from 47.78 to 81.99 seconds. Better citation locality came with a real
  cost-and-latency tradeoff that needs measurement rather than concealment.
- Gate decision: do not start the unchanged ten-question comparison yet. First recognize the
  resolver's actual corpus-agnostic relationship wording locally, retain any available failed-parse
  usage, persist retrieval and corpus identity in the smoke artifact, lock those behaviors with
  regressions, and request separate authorization for the smallest paid confirmation that can
  prove the planner is no longer called.

Useful blog lesson: a smoke test can pass on answer quality and still fail as an orchestration
gate. Here, the repaired retrieval and evidence contract produced substantially better answers,
but one uncovered phrasing doubled down on the expensive path. Quality, latency, and spend need
separate verdicts.

### 2026-07-24 - Turning a paid validation failure into an actionable defect

- Reader testing exposed a particularly bad failure: an opening-screen sample question retrieved
  eight passages and paid for a substantial GPT-5.6 Sol response, but the local evidence contract
  rejected the generated structure and the interface displayed only a generic failure sentence.
  The existing ledger recorded about $0.061 of API usage but not the exact validation rule.
- The private corpus plainly contained relevant material, so this was not an honest
  insufficient-evidence answer. The immediate failure boundary was
  `retrieval -> generation -> local validation -> discarded response`.
- Opened the `evidence-planned-v2` cohort without changing the evaluation contract or gold set:
  - relational requests now receive separate searches for each concept and for evidence explicitly
    linking them;
  - that decomposition is deterministic for simple `connect`, `relate`, and `link ... to` forms,
    so it does not add a paid planning-model call;
  - every opening-screen sample is now loaded from a test-visible data file and must pass a local
    planning regression.
- Added a deliberately narrow evidence-contract normalizer. It can repair ordering and recompute
  redundant unit/source mappings when the factual answer units and exact citation sets are already
  unchanged. It cannot rewrite prose, add or remove citations, resolve unknown source numbers,
  repair malformed citations, or attach a factual unit to an unsupported requirement. The strict
  validator still runs after normalization.
- Added durable, text-free turn diagnostics alongside the cost ledger. Future turns preserve the
  exact validation code, whether a safe repair occurred, the repair codes, and timings for
  preflight, conversation resolution, planning, retrieval, evidence gating, generation,
  validation, and total latency. The record also carries the retrieval policy, planner,
  coverage-contract, normalizer, and generator identifiers needed to separate future cohorts. No
  manuscript passage, user question, or generated answer is written to this diagnostics table.
  Custom-project turns that still use the legacy answer path are explicitly labeled
  `legacy-answer-v1`, with the inapplicable v2 components marked as such.
- Changed the failure presentation. A rejected generation is no longer styled as an answer from
  the manuscript. It appears as an error with optional collapsed technical details, estimated cost,
  and an explicit user-controlled retry; Archivist never performs an automatic paid retry.
- Verification was entirely local and made no OpenAI calls:
  - 137 focused backend tests passed across coverage, routing, the pipeline, homepage prompts,
    conversation behavior, and cost diagnostics;
  - the full backend suite passed with 296 tests and one skipped;
  - Ruff lint and whitespace checks passed;
  - the frontend TypeScript/Vite production build passed.
- This work makes the failure safer and diagnosable and gives the relationship question better
  retrieval coverage. It does not yet prove that the live answer is better. That claim waits for
  an explicitly authorized paid confirmation under the new cohort.

Useful blog lesson: strict grounding is not enough by itself. A safety check that discards a useful
answer for harmless bookkeeping and cannot say why creates an expensive black box. The better
boundary separates factual safety failures from locally repairable structure, then records exactly
what happened without retaining the private source text.

### 2026-07-25 - Clearing the planner gate with one measured API call

- Opened `evidence-planned-v4` because deterministic routing behavior changed. The resolver's
  observed `How did the relationship between X and Y shape Z?` form now decomposes locally into
  both relationship operands and the requested context. Ambiguous causal tails still go to the
  planner; this is a bounded grammar repair, not a corpus-specific shortcut.
- Changed structured-response accounting so a completed provider response is recorded before the
  SDK performs Pydantic post-parse validation. A schema failure can therefore retain returned token
  usage without making a second request. Transport failures that never return authoritative usage
  remain visible only in the provider dashboard.
- Added reusable smoke artifacts that bind a run to the corpus-manifest and chunks hashes,
  manifest and embedded counts, vector-store identity, commit, clean/dirty state, exact dirty
  fingerprint, dependency-lock hash, runner hash, and per-turn retrieval-trace hashes. The
  validator requires that complete reproducibility identity rather than accepting only the two
  corpus hashes. A resolver-only check explicitly records retrieval traces as not applicable
  instead of silently omitting them.
- Hardened the retrieval-trace privacy boundary during review. Trace schema
  `archivist.retrieval_trace/3` allows only closed, field-specific diagnostic values; document
  labels and planner exception classes are hashed; unknown nested fields and non-hash prose in
  SHA-labeled fields are rejected. The writer and artifact certifier use the same validator, so a
  weaker reader cannot certify what the persistence boundary would reject.
- The final offline suite passed with 372 tests and one skipped; Ruff and whitespace checks passed.
  The three warnings were existing Chroma legacy-embedding configuration deprecations.
- Ran one separately bounded resolver-only confirmation with no automatic retries:
  - one `followup_resolution` request, 449 input tokens and 154 output tokens;
  - resolved query: `How did the manuscript describe the relationship between tobacco and labor
    as shaping everyday exchange in Jamestown?`;
  - route: relationship only;
  - planner required: false;
  - planner calls: zero, with diagnostic status `not_called`;
  - elapsed time: 6.954 seconds;
  - local estimated cost: `$0.006865`, below the `$0.02` hard stop.
- The ignored private artifact records runner SHA-256
  `2be80e40ee9df745d93814b5527585a7bdfa9d87d1e7266abebe69d3a9dad284`, corpus-manifest SHA-256
  `b7ff94315a3f1f28c831e2c3ca62c385567d2b1447c19ff45139d175c3ff3c17`, 910 manifest chunks,
  481 embedded searchable passages, and the exact dirty routing-state fingerprint
  `8c0e9ac044fbca106eb9a1671407d01ab8f731de05a034ea580955542e484008`.
- This was deliberately a dirty exploratory gate, not a run of record. It proves only that the
  resolver retains the needed context and the repaired local router avoids the paid planner. It
  made no embedding, retrieval, or answer-generation call and says nothing new about answer
  quality. The final trace-privacy and artifact-validator hardening followed this resolver-only
  call and was verified offline; the paid artifact contained no retrieval trace and validates
  under the completed artifact contract. The unchanged ten-question evaluation was not started.

Useful blog lesson: after an expensive end-to-end smoke exposes one orchestration defect, the next
paid experiment can be much smaller. One resolver call was enough to test the exact uncertainty
without paying again for retrieval and generation or confusing answer quality with routing.

### 2026-07-25 - The unchanged ten questions found a real regression

- Committed the verified v4 boundary as
  `cab97262c34a7dd64c070e71179ca4a311a76f34`, then ran the owner's unchanged ten
  questions once from that clean tree. The private run froze the same question-source,
  58-claim-rubric, corpus-manifest, and searchable-chunks hashes used by the prior practical
  comparison.
- This remained a directional development evaluation, not a formal run of record. It uses the
  undated `gpt-5.6-sol` model name, the practical rubric is not the locked chunk-level gold set,
  and one nondeterministic sample cannot establish a noise floor.
- The run completed all ten questions without a retry or API error under a `$1.25` hard cap:
  - 10 query embeddings, 8 planner calls, and 5 answer-generation calls;
  - 23 priced events and zero unpriced events;
  - `$1.02332782` total estimated cost;
  - 347.621 seconds summed question latency, 36.220-second median, and a
    1.786–70.307-second range;
  - ten independently hashed schema-v3 retrieval traces certified against the clean commit,
    runner, dependency lock, corpus, and vector store.
- The strict unchanged-rubric result was 11/58 essential claims present, 47 absent, and none
  contradicted. Final returned sources covered 11/26 target document groups. The four accepted
  generated answers used 33 well-formed, resolvable citations with no malformed or out-of-range
  source numbers.
- The safety/utility tradeoff moved too far toward withholding:
  - G008 correctly declined the absent Hudson's Bay Company request without substituting an
    analogous company;
  - G002 falsely certified the combined Dulles subject absent even though retrieval had found both
    expected document groups;
  - G004 and G006 returned insufficient evidence;
  - G009 correctly found no literal COVID-19 mention but suppressed the bounded Epilogue
    near-match;
  - G010 retrieved earlier-origin and 1898 passages but discarded its paid premise correction
    after source-remapping and validation failures.
- The dominant defect was more basic than retrieval tuning: every paid planner result failed its
  contract. Five raised structured-output `ValidationError`; three were rejected as
  `invalid_planner_output`; none supplied the plan used by retrieval. Those failed calls alone
  cost `$0.57508750`, 56.2% of the entire run.
- For directional context only, the previous clean hybrid sample observed 19/58 present claims and
  15/26 target groups at `$0.35567608` and 78.538 seconds. The v4 sample observed eight fewer
  claims and four fewer target groups while costing 2.88 times as much and taking 4.43 times as
  long. Different cohorts and single samples prevent a formal delta claim, but the failure is
  large and mechanically explained enough to reject v4 as a quality improvement.
- No expected claim, question, rubric rule, or measurement definition was changed after seeing
  the result. The useful next targets are now concrete: make live planner output satisfy its
  schema, split compound entity anchors, preserve bounded-related absence answers, distinguish
  planner failure from evidence ambiguity, and repair premise-correction source remapping.

Useful blog lesson: a system can become safer, more elaborate, and more expensive while becoming
less useful. The evaluation paid for itself by showing that the sophisticated layer was not merely
under-tuned: its planner never became operational, and its safety gate was suppressing evidence
the retriever had already found. Without the unchanged questions, clean identity, and per-stage
traces, those failures would have looked like vague model weakness.

### 2026-07-25 - Three traced failures became the v5 repair cohort

- Opened `evidence-planned-v5` because planner, evidence-admission, and answer-normalization
  behavior all changed. The frozen questions, expected claims, rubric, corpus, and index were not
  changed.
- The planner failure was mostly truncation rather than bad retrieval:
  - G004, G006, G008, and G010 each stopped at exactly the old 3,000-output-token ceiling;
  - G003 was the one non-truncation Pydantic/SDK validation failure;
  - three other responses parsed before failing the application validator.
- Replaced the provider-facing full `QuestionPlan` with a compact
  `archivist.planner_question_plan/1` proposal containing only requirements, facets, and premise
  hypotheses. The application still owns routing traits, trusted targets, ordering, `F0`,
  execution status, and fallback state. Cross-field semantics now run locally after parsing, so a
  shape-valid but unusable proposal is distinguishable from an SDK parse failure.
- Kept the designed capacity of eight requirements and seven added facets, while asking the model
  to prefer a smaller plan when it can preserve every requested part. The output ceiling rose from
  3,000 to 4,000 tokens; the one-call/no-retry rule remains unchanged. This may increase worst-case
  planner cost, so the next paid smoke must measure both success and latency before the full set is
  rerun.
- Replaced the all-or-nothing multi-target gate with bounded local rules:
  - an exact compound personal-name surface can split into two exact user-written anchors;
  - all directly present subjects retain the retrieved context;
  - mixed presence retains only direct/neighbor material and becomes a partial answer;
  - multiple subjects plus a facet remain indeterminate until a joint relationship rule exists;
  - no multi-subject clean absence is certified unless every subject independently qualifies.
- Added a qualified near-match path derived only from an exact trusted user-message tail. Its
  broader term and related probe must occur in one passage or immediate neighbors. It cannot use
  resolver-only prose, model aliases, or semantic similarity as an absence certificate.
- Tightened premise-correction normalization. A contradicted premise may shed redundant extra
  source numbers only when its mapping is a nonempty strict superset of the valid leading
  correction unit's citations. Empty, disjoint, duplicate, out-of-range, wrong-role, and already
  valid subset mappings are not rewritten.
- An offline replay against the exact frozen v4 retrieved contexts, with no API calls, changed the
  evidence decisions as intended:
  - G002, G004, and G006 now admit all eight retrieved sources as direct-answer contexts;
  - G008 remains a clean abstention;
  - G009 becomes a qualified near match limited to the two bounded passages;
  - G010's promoted-anchor/source-remap shape now renders a validated leading premise correction
    in the synthetic end-to-end fixture.
- Component versions are now `query-planner-v3`, `evidence-gate-v2`, and
  `evidence-coverage-normalizer/2`. Historical versions remain accepted by the text-free trace
  validator, while new turns report the v5 cohort explicitly.
- The complete offline suite passes with 396 tests and one skipped. Strict conversion of the
  compact planner model to the provider schema also succeeds at the full eight-requirement,
  seven-added-facet limits.
- This is an offline repair, not a claim that answer quality improved. No OpenAI request was made.
  The next gate is a separately authorized paid smoke that exercises a real planner response,
  bounded absence/near-match behavior, and premise correction before rerunning all ten questions.

Useful blog lesson: the valuable distinction was not “the model failed.” Four planner calls ran
out of output budget, several answers were stopped by local evidence policy, and one good
correction was discarded by redundant bookkeeping. Stage-specific traces turned one disappointing
score into three small, independently testable engineering repairs.

### 2026-07-25 - The v5 focused smoke passed two branches and isolated one more contract defect

- A private, dirty-worktree exploratory smoke ran the unchanged G008-G010 questions once with no
  retries. It used three planner calls, three query embeddings, and two answer-generation calls,
  took 77.292 seconds in total, and cost an estimated `$0.22260367` under the separately enforced
  `$0.55` operational stop and `$0.75` authorization ceiling.
- The compact live planner succeeded on G008 and G010. Its average recorded planner cost fell
  materially from the v4 failure sample, but this three-question, single-run smoke is not a formal
  latency or cost comparison.
- G008 passed the protected-absence branch: the system found no direct treatment of the named
  company, returned no analogous company as a substitute, skipped answer generation, and incurred
  an estimated `$0.02728943`.
- G010 passed the premise-correction branch: it rejected the question's 1898 founding premise,
  placed the manuscript's earlier-origin framing first, distinguished 1898 as a major overseas
  turn, and returned seven well-formed citations resolving against eight sources. The previous
  `premise_correction_invalid` failure did not recur.
- G009 proved that retrieval and the new evidence gate were working: the system certified the
  named event absent, admitted exactly two bounded related passages, and selected
  `qualified_near_match`. It still did not display an answer because:
  - its parsed planner proposal was rejected by local semantic validation and collapsed into the
    generic `invalid_planner_output` code;
  - its structured answer then failed the redundant status/gap bookkeeping rule with
    `status_gap_mismatch`.
- The planner artifact proves the failure was not truncation, refusal, transport, or provider
  schema parsing, but the exact local semantic rejection was not retained. The next repair must
  preserve a finite text-free validation code rather than loosening an unknown rule.
- The answer status has a one-to-one required gap reason, so its mismatched gap value can be
  canonicalized from the unchanged status without adding or removing a claim, source, citation, or
  answer unit. Strict validation still has to reject unsupported records with factual units,
  missing units, malformed citations, and source-mapping errors.
- This smoke is a gate, not a replacement for the practical evaluation. The planned sequence is:
  repair these two G009 contract boundaries, confirm that single branch once, commit the frozen
  implementation, and then run the unchanged ten-question evaluation with no intervening UI work
  or new optimization target.

Useful blog lesson: the most encouraging result was not that two answers looked good. It was that
the failed third question retained the right two passages and a precise evidence decision. That
reduced a vague RAG failure to one redundant answer field and one missing planner diagnostic.

### 2026-07-25 - The final G009 contract repair was completed offline

- Opened `evidence-planned-v6` for two deliberately narrow changes; no corpus, index, frozen
  question, expected claim, rubric rule, retrieval decision, or model setting changed.
- `evidence-coverage-normalizer/3` now derives the redundant gap reason from the model's unchanged
  requirement status. The repair is recorded and the complete strict validator still runs.
  Missing required units and unsupported factual units remain failures, and no answer unit,
  source, citation, or status is created or changed.
- Planner diagnostics schema `archivist.planner_call_diagnostics/2` now preserves a finite
  text-free local validation code when a parsed proposal fails semantic validation. Structural
  failures receive `plan_structure_invalid`; historical version-1 artifacts remain readable.
  Validation was not weakened, the planner is not retried, and neither provider prose nor
  manuscript/question text enters the trace or cost ledger.
- The complete offline suite passes with 403 tests and one skip. Ruff checks and the modified-file
  format check pass, and `git diff --check` reports no whitespace errors. No OpenAI request was
  made during the repair or verification.
- Development is now deliberately sequenced to prevent another evaluation detour: repeat only
  G009 once, freeze and commit the confirmed repair, then run the owner's unchanged ten-question
  evaluation immediately. That one-question confirmation is the final micro-gate, not a
  replacement for the practical evaluation.
- The separately authorized confirmation cleared that gate. G009 completed once with no retry in
  24.721 seconds for an estimated `$0.07107566`. The live planner succeeded; the evidence decision
  remained `qualified_near_match`; exactly two bounded sources reached generation; normalization
  recorded `status_gap_mismatch`; strict validation passed; and four emitted source references
  all resolved. The answer accurately marked the named event absent from the retrieved evidence
  before discussing the two related episodes.
- The confirmation was an exploratory dirty-worktree artifact, not a run of record. Its purpose
  was to confirm the repaired branch before freezing the code; the unchanged ten-question
  directional evaluation remains the practical measurement.

Useful blog lesson: strict source validation is valuable only when its failures remain
diagnosable. A safe local repair can correct a redundant enum field without laundering factual
content, while a closed diagnostic vocabulary can reveal which planner rule failed without
storing private text.

### 2026-07-25 - The unchanged ten-question v6 evaluation measured recovery and the next ceiling

- Committed the frozen evidence-planned repair as
  `8a0d6c9eaffaaaab2fb365f0b0a0a049b3dbc67d` before evaluation. The run began from that clean
  commit; its ignored runner and private artifacts did not enter Git.
- Ran the owner's unchanged ten questions and unchanged 58-claim practical rubric once, with
  empty conversation history, neutral interpretation settings, no retries, and an isolated local
  usage ledger. All ten items and all ten text-free retrieval traces completed.
- The run cost an estimated `$0.92185165` and took 280.803 seconds across the ten questions:
  - eight planner calls: 23,526 tokens and `$0.19846525`;
  - nine answer generations: 64,201 tokens and `$0.72337950`;
  - ten query embeddings: 345 tokens and `$0.00000690`;
  - zero unpriced events.
- Directional strict grading, using the same threshold precedents as the preserved v4 assessment,
  found:
  - 17/58 expected claims present, 41 absent, and none contradicted;
  - 17/26 expected document groups represented in final context;
  - 8/10 high-level behavior checks passing;
  - 58 emitted source references, all well formed and resolvable;
  - six accepted live planner proposals out of eight eligible questions.
- The v4 comparison moved from 11 to 17 claims, 11 to 17 target groups, and five to eight
  high-level behavior passes. Estimated total cost fell 9.9%, latency fell 19.2%, and planner cost
  fell 65.5%. This is one directional sample per cohort, not a statistically reliable performance
  claim.
- Two successful answers still demonstrate why answer acceptance is not the same as adequacy:
  - the broad institutional-lineage answer covered only 2/8 expected historical document groups;
  - the broad war-and-central-power answer covered 2/5 groups and no complete strict claims.
- The premise-correction item now returned a valid cited answer and rejected the proposed 1898
  origin, but did not supply the manuscript's Jamestown origin frame. Mechanical validity improved
  without complete realization of the requested correction.
- Most importantly, the unchanged G009 passed the focused smoke and failed in the full cohort.
  In the full run, a successful planner introduced a premise hypothesis that overrode the
  mechanically certified absence route; the required Epilogue material was present, but strict
  generation failed on `premise_source_mismatch`. The paired outcomes are concrete evidence of
  residual model variance and a brittle precedence boundary, not a reason to rewrite the test.
- The measured next targets are now narrow:
  1. define premise-versus-absence precedence and retain bounded related evidence;
  2. preserve requirement and era coverage through final source allocation under the existing
     eight-source cap;
  3. validate that a premise correction realizes its source-bounded origin requirement.

Useful blog lesson: the unchanged evaluation did exactly what a good test should do. It showed a
real recovery in useful behavior, prevented a successful smoke from becoming an overconfident
conclusion, and replaced a vague desire for “better RAG” with three traceable engineering
boundaries.

### 2026-07-25 - Evidence-planned v7 turned the three measured failures into local contracts

- Opened `evidence-planned-v7` directly from the unchanged v6 evaluation evidence. No manuscript,
  index, frozen question, expected claim, grading rule, model setting, source cap, or API-call
  budget changed, and this implementation pass made no OpenAI request.
- Made premise ownership application-controlled. The planner now receives the local route traits,
  and a proposal containing a premise is rejected unless deterministic routing already marked the
  question `premise_sensitive`. The evidence gate repeats that check defensively, so a
  model-invented premise can no longer widen an absence-only context through
  `premise_evaluation_pending`.
- Split two superficially similar question forms. A manuscript-treatment question with a
  conservative named target remains absence-sensitive; an unbounded “how does the book treat…”
  theme without such a target is now broad synthesis. Broad planner proposals require at least
  two ordered requirements with a dedicated facet for each, while the deterministic fallback
  reserves origin, development/mechanism, and later-consequence/endpoint lanes.
- Protected broad coverage under the unchanged eight-source cap. Direct-anchor promotion admits
  at most one certified hit per scan, then preserves one source for every answer requirement,
  premise side, and live broad facet before filling spare positions. The trace records requested
  anchors, deferred anchors, protected sources, and any protection shortfall. A synthetic
  pressure test confirms that four promoted anchors can coexist with origin, mechanism,
  transition, and endpoint evidence.
- Separated premise correction from ordinary answer coverage in
  `archivist.evidence_coverage/2`. A correction unit must have no requirement IDs; every ordinary
  unit must have at least one. The application now passes exact post-gate support, counter, and
  framing source scopes to both generation and validation. A contradicted premise must cite its
  correction’s exact sources and, whenever a framing source survived, include at least one such
  source. The requested answer still has to be supplied in separate non-correction units.
- Versioned the affected prompt, normalizer, diagnostics, and trace allowlists. Premise source
  scopes are retained only as safe IDs and source numbers; no question, answer, or manuscript
  prose enters the diagnostic.
- Verification is entirely offline: 416 tests pass with one intentional skip, including focused
  regressions for G009-style precedence, G006/G007-style source pressure, and G010-style framing
  provenance. Ruff passes. The first sandboxed full-suite attempt could not access pytest’s
  Windows temporary directory; the same suite passed outside that sandbox. No paid quality
  improvement is claimed until the unchanged affected questions are run again.

Useful blog lesson: prompting alone could not fix these failures. The reliable improvement was to
move model-sensitive judgments into small, auditable boundaries: the application owns whether a
premise exists, source allocation owns which planned obligations survive, and validation owns
whether a correction used the source lane that was retrieved for it.

### 2026-07-25 - The focused v7 confirmation passed mechanically and failed substantively

- Ran the unchanged G006, G007, G009, and G010 questions as a separately metered dirty-worktree
  confirmation. All four completed without a retry. The planner, answer contract, eight-source
  bound, and citation resolution passed on every item. Estimated OpenAI API spend was
  `$0.45132009`.
- The frozen practical rubric prevented those green structural checks from being mistaken for a
  useful retrieval result. G006 remained at 1/8 strict claims and 2/8 target document groups.
  G007 remained at 0/7 strict claims while improving from 2/5 to 3/5 target groups. G009 improved
  to a valid qualified answer with 2/5 strict claims, but both bounded sources came from Chapter
  20 rather than the required Epilogue, leaving target coverage at 0/1. G010 now gives a valid,
  cited Jamestown replacement for the false 1898 premise and covers both target groups, but only
  1/4 strict composite claims is complete.
- The repairs therefore did fix control machinery: planner-created premises no longer override
  absence routing; broad planning preserves named lanes; and premise corrections have separate,
  source-bounded provenance. They did not yet make the broad lanes span the whole requested
  chronology, make final allocation prefer document diversity, or make a bounded absence probe
  choose the most relevant near-match.
- Applied the predeclared hard stop. The full unchanged ten-question cohort was not run, and the
  v7 implementation was not frozen as a successful release. Spending more after the focused
  content gate failed would have measured known defects again rather than testing an uncertain
  improvement.
- The next work is correspondingly narrow: historical-stage coverage must be explicit in broad
  planning and traces; spare source slots must prefer uncovered documents/stages; anchor
  promotion must not evict a unique stage source; and bounded absence ranking must preserve the
  requested facet, not merely the broad related term.

Useful blog lesson: a valid citation map is necessary but not sufficient. The system can cite
every sentence correctly and still assemble the wrong slice of a long book. A content rubric is
what turns "the pipeline worked" into the harder question, "did it retrieve the book-wide
argument the reader actually asked for?"

### 2026-07-25 - V8 fixed the bounded absence example but exposed a false broad-coverage signal

- Opened `evidence-planned-v8` without changing the manuscript, index, frozen questions, practical
  rubric, GPT-5.6 Sol settings, eight-source cap, or one-planner/one-generator call budget.
- Broad synthesis now requires an ordered origin, transition-or-mechanism, and endpoint chain.
  Each stage searches an application-owned early, middle, or late document band rather than
  trusting a model hint to define chronology. Spare source slots prefer previously uncovered
  documents, protected stage sources reserve capacity before corpus anchors, and final broad
  context returns to corpus order.
- The trace was versioned to `archivist.retrieval_trace/4` and records each stage's chronology
  band and safe document-ordinal bounds plus required, satisfied, and shortfall counts. This made
  the broad failure inspectable without storing question or manuscript prose.
- Qualified absence retrieval can now retain at most two planner-ranked related passages only
  when a substantive facet has an exact validated document hint and its query preserves the
  trusted subject and relation surfaces. This ranking occurs before the older exact-tail
  co-occurrence fallback and cannot turn semantic similarity into direct evidence.
- Offline verification passed 421 tests with one intentional skip; Ruff and whitespace checks
  passed. The separately metered unchanged G006/G007/G009 confirmation then completed without
  retry for `$0.29427521`, and every structural, source-bound, and citation check passed.
- G009 is the clear success. It used exactly two Epilogue passages, stated the evidence boundary,
  connected pandemic-exposed supply chains to reshoring and military spending, and did not invent
  COVID-era procurement analysis. It improved from 2/5 to about 3/5 strict claims and from 0/1 to
  1/1 target groups.
- Broad synthesis remains below the content gate. G006 improved from 1/8 claims and 2/8 groups to
  2/8 and 3/8. G007 remained at 0/7 claims and fell from 3/5 to 2/5 groups. Both traces said 3/3
  stages survived, proving that three coarse chronology bands are an allocation invariant, not a
  measure of whether a book-wide institutional or causal argument was retrieved.
- The full ten-question cohort was not run on v8. The next measured repair is narrower than a
  larger context window: broad plans need more substantive historical obligations within the
  existing eight slots, and diagnostics must distinguish chronology-band survival from
  argument-stage coverage.

Useful blog lesson: observability can falsify its own reassuring metric. "Three of three stages
covered" sounded like success until the unchanged answer rubric showed that those stages were too
coarse to represent the argument. The trace did not prove quality, but it made the next defect
precise.

### 2026-07-26 - The eight-source ceiling was tested instead of defended by intuition

- Ran a controlled retrieval-only comparison on the unchanged broad G006 and G007 questions.
  Each question made one live planner call and one batched facet-embedding call; the resulting
  plan and embeddings were reused locally at source ceilings of 8, 12, and 16. The normal evidence
  gate ran at each limit, but answer generation and judges were disabled.
- The experiment completed without retries for `$0.05277158`: exactly two planner calls and two
  embedding calls. Every larger context retained all eight baseline chunks, so gains did not come
  from exchanging one baseline source for another.
- G006 showed a genuine capacity effect. Target-document groups rose from 3/8 at eight sources to
  3/8 at twelve and 6/8 at sixteen. The sixteen-source variant newly reached Chapter 11, Chapter
  20, and the Epilogue, although it still missed Chapter 5 and Chapter 17.
- G007 showed no capacity effect. Coverage remained 3/5 at all three limits. Twelve and sixteen
  added distinct documents, but neither reached the missing Chapters 4-5 or Epilogue groups. The
  shared three-requirement/four-facet plan and its ranking, not the final source ceiling, remained
  the binding constraint for this question.
- This rules out both attractive shortcuts. Eight is not reliably sufficient for broad lineage
  questions, but a universal increase to sixteen is not a broad-synthesis repair. Twelve was
  strictly dominated in this sample: it doubled neither question's target coverage.
- No production limit changed. The evidence supports a broad-only sixteen-source ceiling as a
  candidate cohort, not as a universal setting. Before adopting it, generation should be tested
  on G006's richer context, while G007 needs a separate planner change that expresses more
  substantive argument stages than coarse origin/middle/endpoint lanes.

Useful blog lesson: parameter debates are often two different defects hiding in one number. The
same eight-source limit genuinely constrained one question and was irrelevant to the other. A
controlled retrieval-only run separated those mechanisms for about five cents.

### 2026-07-26 - More passages did not repair the broad answer, but better stages repaired coverage

- Tested actual G006 generation at 8 versus 16 sources before changing production. One live plan
  and one embedding batch were shared across both allocations. The eight-source answer validated
  from 2/8 target groups. Sixteen reached 6/8 groups, but the generation contract still declared
  eight as its maximum legal source count and rejected `source_count=16` as `invalid_context`.
- The already-paid sixteen-source structured output was recovered from its stored response rather
  than regenerated. It added the Crown's takeover and several intermediate institutions, but
  still omitted the rubric's Hamiltonian capital/debt step, Federal Reserve/FTC step,
  Pentagon/cost-plus step, Chapter 20 endpoint, and Epilogue endpoint. More context produced a
  longer lineage, not the required lineage, so production stayed at eight sources.
- The comparison cost `$0.23826382` with one planner, two embedding batches, and two generations.
  The second embedding batch was a recovery check after the shell closed its output pipe: the
  exact stored planner response was reused, and the reconstructed eight-source context had to
  match the persisted first variant chunk-for-chunk before the missing variant could run. Neither
  answer was regenerated.
- Opened `evidence-planned-v9` / `query-planner-v6` for the independent G007 defect. Broad plans
  now require five dedicated ordered narrative stages instead of three generic terciles. When a
  numbered book structure is available, chronology begins at Chapter 1 and ends at the
  conclusion or Epilogue, excluding Afterword and appendices from stage allocation.
- The first focused G007 run accepted the five-stage live plan and returned a valid answer, but
  remained at 3/5 target groups for `$0.18608978`. It repaired the Jamestown stage while rigid
  stage boundaries displaced the Civil War group, and its endpoint lane never considered an
  Epilogue passage.
- `Evidence-planned-v10` kept the same accepted plan, eight-source cap, corpus, model settings, and
  generator prompt. Retrieval alone changed: adjacent stages overlap by two narrative documents,
  and the endpoint facet performs a structural check against the book's own conclusion or
  Epilogue using the same query embedding.
- The controlled v10 G007 confirmation made no planner call, cost `$0.10395228`, validated its
  answer, and improved target-document coverage from 3/5 to 5/5. Its eight passages included
  Chapter 4, Chapter 11, Chapter 14, Chapter 17, and the Epilogue.
- Document coverage is not yet claim completeness. The v10 answer still omitted or only partially
  expressed the imperial-interior recurrence, Revolutionary-war-debt mechanism, Pentagon and
  Virginia employment, NSC-68/Keynesian permanent spending, NATO persistence, and the
  Epilogue's security-dilemma component. The unchanged ten-question cohort remains gated while
  passage-level mechanism targeting is refined.
- Offline verification for the five-stage implementation passes 422 tests with one intentional
  skip. Ruff and `git diff --check` pass.

Useful blog lesson: a context window and a chronology plan solve different problems. Sixteen
sources could not rescue a vague lineage, while eight sources could cover every required era once
the planner and allocator agreed on five overlapping narrative obligations. Even then, reaching
the right chapters was not the same as reaching the right claims.

### 2026-07-26 - Mechanism-aware retrieval improved breadth, then the full test exposed the next boundary

- Froze the v10 checkpoint at commit `c8045a3` and opened `evidence-planned-v11` as a retrieval-only
  cohort. The final source ceiling stayed at eight, the planner and generator prompts stayed
  unchanged, and no additional planner, embedding, generation, critic, or retry call was added.
- Inside planner-scoped narrative stages, retrieval now makes deterministic, corpus-agnostic
  lexical probes for origin, fiscal consolidation, institutional or military mechanisms, and
  endpoint persistence or transformation. The trace records only hashes, candidate IDs, counts,
  and role labels.
- A zero-cost replay against preserved G007 candidates recovered all five target document groups.
  Because the original query vectors were not persisted, this was a directional replay rather
  than a claim of exact semantic reconstruction.
- One paid focused G007 confirmation reused the exact accepted five-stage plan. Its eight sources
  covered all five target groups and included the early colonial frame, federal consolidation,
  Civil War centralization, permanent national-security spending, NATO transformation, and the
  Epilogue. It cost an estimated `$0.13844353`, made one embedding call and one generation call,
  and made no planner call or retry.
- That focused answer still realized only about 1/7 strict rubric claims. Several mechanisms were
  already present in the selected passages but disappeared during generation. The test therefore
  separated source selection from source-bounded answer adequacy.
- Ran the owner's unchanged ten questions once from clean commit
  `7ba7382ff48828c1c854034e2d78217751eba826`. The questions, 58-claim practical rubric, corpus,
  index, neutral interpretation, eight-source limit, and no-retry policy were unchanged.
- The clean v11 cohort completed all ten questions for an estimated `$0.91198718`. It made eight
  planning calls, ten embedding calls, and nine answer-generation calls. Total question latency
  was 334.051 seconds; median latency was 25.461 seconds.
- Directional grading found 19/58 expected claims present, 21/26 target document groups represented,
  and 8/10 high-level behaviors passing. All 61 rendered citation tokens were syntactically valid
  and resolved to returned sources. Compared with the earlier clean v6 sample, that is two more
  claims and four more target groups at slightly lower estimated API cost, but about 19 percent
  greater total latency.
- The broad items improved without becoming complete. G006 rose from 2/8 to 5/8 target groups;
  G007 rose from 2/5 to 3/5 and now explicitly reached NATO's post-Cold-War transformation. A
  fresh G007 plan nevertheless fell short of the focused confirmation's 5/5 coverage, exposing
  residual planner and allocation variance.
- G010 is the clearest answer-level success: it rejected the 1898 premise, placed the manuscript's
  origin at Jamestown, and described the Spanish-American War as an overseas turn rather than the
  beginning.
- G001 and G009 retrieved the expected source groups and paid for generation, then failed closed
  on `citation_locality_invalid`. This is a generation-contract defect, not a retrieval miss.
- The next work is deliberately bounded: repair citation locality without weakening validation,
  express broad stages as explicit source-bounded mechanism obligations for generation, and make
  broad plan allocation less variable. The frozen questions and rubric will not be changed.
- Offline verification at this milestone passes 424 tests with one intentional skip. Ruff and
  whitespace checks pass.

Useful blog lesson: retrieval quality and answer quality can finally be seen as different layers.
The system can reach the right pages and still leave the book's argument unstated; conversely, a
strict validator can protect readers by refusing an answer whose source mapping is ambiguous.
Progress came from measuring both layers instead of treating a fluent response as proof that the
RAG worked.

### 2026-07-27 - V12 turns three observed failures into explicit application-owned contracts

- Opened `evidence-planned-v12` without changing the manuscript, index, frozen questions, practical
  rubric, neutral model settings, eight-source cap, or number of paid operation types.
- The two v11 citation-locality failures were reconstructed from their stored response IDs without
  regenerating answers. Every rejected unit had the same harmless shape:
  `claim.[Source N].`. V12 repairs only that exact duplicated terminator, then reruns the full
  validator. Multiple sentences, semicolons, newlines, extra citation groups, trailing material,
  changed source sets, and other locality failures still fail closed. The provider schema now
  receives the same atomic-citation pattern, and traces retain only a finite failure subtype plus
  unit ID and ordinal.
- Broad answers now receive a paragraph-addressable obligation ledger inside the existing single
  generation call. Each obligation binds one source range to allowed requirement IDs, a generic
  narrative focus, and dimensions such as stage development, mechanism, consequence, continuity,
  or qualification. Generated units must map back to exact obligation/dimension pairs, use a
  compatible claim role, and cite that obligation's source. This makes source-present omissions
  visible instead of treating a high source count as evidence that the answer used the passages.
- The ledger is corpus-agnostic and bounded. Exact paragraph metadata produces paragraph-level
  scopes; mismatched metadata falls back to a whole-source scope; oversized contexts are
  deterministically grouped into at most 32 contiguous ranges without dropping a retained source.
- Fresh broad plans no longer own the protected stage queries. Each stage gets an
  application-derived canonical core made from unchanged F0 plus fixed stage vocabulary. Planner
  wording and hints remain supplemental, all vectors still share one batched embedding operation,
  and spare source slots are allocated by global rank utility instead of early-facet priority.
- Trace schema 6 records canonical/provider query hashes, core candidate and selected IDs,
  obligation ranges, dimension mappings, and safe counts without storing questions, manuscript
  prose, or generated answer text.
- Offline verification passes 439 tests with one intentional skip. Ruff and whitespace checks
  pass. No OpenAI generation, planning, or embedding call was made during implementation. The
  focused live G001/G007/G009 gate remains deliberately separate and must pass before another
  unchanged ten-question run.

Useful blog lesson: once a failure is reproducible, the repair can be much narrower than a more
powerful model or a larger context. One defect was a single redundant period, one was missing
accountability between selected paragraphs and answer claims, and one was provider wording
deciding protected retrieval slots. Each needed a different contract.

### 2026-07-27 - The focused v12 gate found an application capacity bug, not a retrieval miss

- Ran the clean focused G001/G007/G009 confirmation without changing the manuscript, index,
  questions, neutral settings, eight-source limit, or no-retry rule. Combined estimated API cost
  was `$0.49895119`.
- G001 confirmed the narrow citation repair and G009 confirmed the bounded qualified-near-match
  path. Both validated against their returned sources. They do not need to be regenerated.
- The first process launcher stopped waiting after fourteen seconds while G001's API call was
  still completing. Its provider response ID had been recorded, so the already-paid result was
  recovered read-only instead of making a duplicate generation call. This is a useful operational
  lesson: a client-side timeout is not proof that a provider-side request failed.
- G007 took 116.9 seconds and failed closed on `obligation_unit_mapping_mismatch`. A structural,
  text-free diagnosis showed why: v12 supplied 32 paragraph obligations containing 84 historical
  dimension slots, but the structured answer schema permits only 32 answer units. The generated
  structure attempted 61 unit IDs; 29 of them were outside the possible `U1`-through-`U32` range.
- Opened `evidence-planned-v13` as a narrow application-contract repair. Every paragraph scope now
  receives exactly one rotating historical dimension, and broad ledgers reserve capacity for any
  premise-correction units. A new validator error,
  `obligation_dimension_capacity_exceeded`, prevents an impossible trusted ledger from being
  blamed on generated output.
- A zero-cost replay of the exact failed G007 scope structure reduced the ledger from 84 to 32
  required dimension slots. It retained all 32 paragraph ranges and still represented stage
  development, cause or enabler, mechanism, consequence, continuity or change, and qualification.
- Offline verification now passes 441 tests with one intentional skip. Ruff and whitespace checks
  pass. No API call was made for v13 implementation or replay. The next paid action is one
  G007-only confirmation; the full ten-question evaluation remains gated on that result.

Useful blog lesson: strict validation did its job, but it initially obscured who had broken the
contract. The model's impossible source map was downstream of an impossible ledger supplied by the
application. Counting the contract's requested slots against its output capacity turned a vague
generation failure into a small, testable repair.

### 2026-07-27 - V13 restored every answer, but verbosity did not improve strict recall

- Froze the capacity repair at commit `87bee716e5fcc79607c843e8ad3087bf2fe0ae08`.
  The implementation, tests, and development notes are separate from the private manuscript and
  evaluation artifacts.
- The G007-only confirmation completed once without retry in 102.9 seconds for an estimated
  `$0.26043497`. It made one planner call, one batched embedding call, and one answer-generation
  call. The answer validated with 28 well-formed, resolvable citations and no mechanical repair.
- That focused result proved the 84-slot/32-unit capacity defect was gone, but it did not prove
  answer quality. Strict grading found 0/7 composite claims and 4/5 target document groups.
- Honoring the decision not to keep deferring the central evaluation, ran the owner's unchanged
  ten questions once from the same clean commit. The questions, 58 claims, 26 target groups,
  corpus, index, neutral interpretation, eight-source ceiling, and no-retry rule were unchanged.
- All ten turns completed once. Nine generated answers validated and the absent-subject item
  cleanly abstained without answer generation. The run used eight planner calls, ten embedding
  calls, and nine answer-generation calls; it contained zero unpriced events and cost an estimated
  `$1.22828221`.
- All 106 rendered citation tokens were well formed and resolved to returned sources. G001 and
  G009, which had failed closed in v11, now returned bounded visible answers. High-level behavior
  therefore improved from 8/10 to 10/10.
- Strict answer completeness did not improve in aggregate: 19/58 expected claims and 21/26 target
  document groups, exactly matching the clean v11 sample. No expected claim was contradicted.
  Seven of eight live plans were accepted; G003's planner output failed on `query_drift`, and the
  deterministic fallback still produced a valid answer without a retry.
- The broad items explain the ceiling. G006 emitted 30 citations and G007 emitted 28, yet each
  realized only one strict composite claim. Generation usage rose from 60,399 tokens in v11 to
  83,024 in v13; total question latency rose from 334.051 to 456.336 seconds. More paragraph-level
  accountability produced more prose, not a better reconstruction of the book's argument.
- G007's missing Civil War requirement was honestly marked unsupported. Its trace showed relevant
  Chapter 14 passages inside the provider and mechanism candidate pools, while the protected
  generic canonical stage core admitted a different passage. G006 likewise missed four of eight
  target groups, including its modern endpoint.
- The next repair should be narrow and two-part: select each protected broad-stage anchor by
  consensus across canonical, mechanism, and provider-relevance pools; then distinguish passages
  the model must inspect from historical mechanisms the answer must explicitly synthesize. This
  should reduce tangential output rather than purchasing more sources or another model call.

Useful blog lesson: grounding, reliability, and completeness are separate achievements. V13 made
every answer visible and every citation resolvable, which matters. But a source-grounded list of 30
facts can still miss the argument a reader asked for. The next quality gain has to come from
choosing and organizing evidence, not merely requiring more of it to appear.

### 2026-07-27 - Public sources become edition locators, not an online manuscript reader

- Inspected Archivist and Cromblog before beginning integration. Cromblog already has an Archivist
  feature panel, a typed project registry, and support for links to separately hosted apps. The
  portfolio wiring is small; securely publishing the Python RAG service is the substantial part.
- Verified the active private corpus rather than assuming it was complete. The July 6 DOCX
  produces 910 total chunks, of which 481 substantive chunks are retrieval-eligible. Chroma
  contains exactly those 481 records, and the full hash- and metadata-aware corpus preflight
  passes. The excluded material is front matter, contents, acknowledgments, illustration notes,
  bibliography/credits, and the printed Index - not a public-demo sample of the narrative.
- Clarified an easy terminology trap for the product story: the RAG "index" is the private Chroma
  embedding map used to find passages. It is not the printed Index at the back of the book, and it
  does not mean all 594 pages are sent to the model on every question.
- The earlier representative-subset public plan is superseded. Public Archivist should search all
  481 substantive chunks while keeping the corpus private. Disclosure is controlled at the API
  response boundary, not by withholding chapters from retrieval.
- Preserved the existing full-passage source panel as a development feature. Large source blocks
  are valuable while diagnosing retrieval and citation behavior, but the public client will use a
  separate server-selected profile. That profile cannot be activated or escaped by a browser
  toggle.
- Inspected the supplied final typeset PDF. It is 594 physical pages with SHA-256
  `89d68cdc186432d4d4804fbaff6aac0deb599d351dd016fe250b25f2a4771b3f`. Its PDF-internal labels are
  merely physical positions, while the book itself has Roman front matter and restarts Arabic
  numbering at the Prologue. The Introduction begins on typeset page `xi`; physical PDF page 51,
  for example, is typeset page 33.
- Ran a read-only mapping-feasibility pilot with six exact 12-token anchors sampled across each
  eligible chunk. All 481 chunks mapped with at least two exact PDF anchors: 39 preliminary spans
  covered one page, 360 covered two, 76 covered three, and 6 covered four. No embedding or paid
  model call was made.
- Page citations are now explicitly edition-qualified. The first profile is
  `Typeset PDF (July 6, 2026)`, so the UI will say `Typeset PDF ..., p./pp. ...` rather than imply
  that paperback, hardcover, ebook, and PDF pagination are interchangeable.
- The locator schema leaves room for paperback, hardcover, and ebook profiles keyed to the same
  chunk IDs. Each future profile binds to its own source hash and may use pages, ebook locations,
  or sections. Adding one does not require re-embedding the manuscript or opening a new RAG
  evaluation cohort.
- Public source cards will show an edition-qualified location for every cited source and only a
  small number of brief, claim-local quotations. The initial design caps one excerpt at 280
  characters/two sentences, three excerpts per answer, and 700 quoted characters total, with no
  route for fetching surrounding passages. These are conservative implementation defaults to
  test, not a legal conclusion.
- The public safety gate must also remove uploads, embedding, source browsing, raw source files,
  index tools, mutable cost settings, and the client-controlled budget override; enforce
  server-side request/concurrency/abuse/spend limits; and sanitize public errors. Only after that
  gate passes should Cromblog's feature panel and Projects page link to the separate Archivist
  deployment.
- No source UI, API, deployment, or Cromblog code changed during this design pass. The retrieval
  path, source order, model-facing `[Source N]` contract, and evaluation results remain untouched.

Useful blog lesson: "search the whole book" and "publish the whole book" are not the same
architecture. A private full-corpus index can support better answers while an edition-aware
presentation layer gives readers verifiable locations and only the minimum quotation needed to
check a claim.

### 2026-07-27 - The first enforceable interpretation was still too neutral

- Replaced the earlier vague request for an interpretive "bridge" with a concrete output rule.
  Evidence-first + Scholarly + None still uses the byte-for-byte neutral prompt path and remains
  concise.
- The first implementation required an additional cited interpretive paragraph for a non-neutral
  lens or worldview. It made answer length enforceable but still asked the same paragraph to be
  both visibly biased and evidentially cautious.
- A live triumphalist test about Pocahontas exposed the contradiction. The model used phrases such
  as "cross-cultural capacities" and "achievement forged through adaptation," then immediately
  balanced them with coercion. The result was defensible but read almost neutral.
- Replaced that design with an internal three-part frame: an uncited interpretive opening of two or
  three sentences, the unchanged source-grounded factual middle, and an uncited one-sentence
  interpretive conclusion. The structured contract records the exact rhetorical move requested.
- A second live test about Edwin Sandys exposed a presentation and relevance failure: the model
  wrote generic first-person judgments such as “I read this record” and “My judgment,” while the
  UI split those sentences into conspicuous labeled boxes. The stance was stronger, but the answer
  did not feel like a response to the actual question.
- The application now supplies trusted question targets such as `Edwin Sandys` to the generation
  contract and rejects an interpretive opening or conclusion that does not name every required
  target. It separately rejects first-person pronouns and narrator self-reference.
- The UI no longer labels, boxes, italicizes, or separately copies the interpretive parts. The
  opening, cited middle, and conclusion display and copy as ordinary consecutive paragraphs in one
  cohesive answer. Their boundary remains machine-readable, so follow-up conversation history
  still sends only the factual middle back for contextual resolution.
- A direct tragic-versus-triumphalist comparison then exposed a subtler calibration failure. The
  triumphalist reading could point to the answer's actual institution-building evidence, while the
  tragic reading supplied unnamed “human cost,” “better paths,” and “moral burden” that the factual
  middle never identified. The result performed tragedy instead of interpreting the retrieved
  facts.
- The tragic move is now `tragic_tension_and_contingency`, replacing the contract language that
  itself demanded loss and foreclosure. Its prompt must first find a concrete loss, coercion,
  failed plan, incomplete reform, or supported tension in the factual answer. If the evidence
  offers only a limited tension, the judgment must remain proportionate and genuine achievement
  must remain achievement.
- Combined settings now form one thesis: the lens determines the central interpretation, the
  worldview evaluates that same interpretation, and the voice controls its expression. The pious
  prompt chooses the smallest relevant moral frame instead of layering duty, sin, sacrifice,
  redemption, and providence into every answer.
- The interpretive framing paragraphs may make clear value judgments but cannot contain citations
  or introduce new names, dates, events, quantities, quotations, motives, or historical assertions. The
  triumphalist prompt now explicitly leads with accomplishment and forbids a closing qualification
  from canceling the stance; the other lenses and worldviews receive parallel instructions.
- A selected voice alone still changes diction and cadence without automatically adding the
  preface and conclusion. If the factual answer is entirely unsupported, Archivist returns its
  abstention without the subjective frame.
- No retrieval, source ordering, neutral prompt, model setting, corpus, or embedding changed, and
  no paid API call was made.
- Verification: Ruff checks passed, the OpenAI structured-output adapter accepted the new schema,
  the focused perspectives, evidence-coverage, and RAG pipeline suites passed all 166 tests, and
  the frontend production build passed.

Useful blog lesson: more prose is not the same as a different perspective, and stronger judgment
is not enough if it floats above the user's question. The two live tests led to a useful split:
keep editorial and evidentiary prose separate in the machine contract, but make them read as one
subject-specific, impersonal answer in the interface.

## Suggested demo sequence

1. Open the cover-led landing page and briefly explain that the app is built around one specific
   manuscript rather than asking the reader to upload a file.
2. Ask a non-gold, focused question so the public demo does not contaminate an unfinished
   evaluation item.
3. Show the transition into the full-width answer and open one cited source to reveal an
   edition-qualified page range and brief supporting quotation, not a full chunk.
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
- The archival-paper answer treatment with a visible citation and a compact
  `Typeset PDF, p./pp.` source card.
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
- Do not imply that typeset-PDF page numbers apply to the paperback, hardcover, or ebook.
- Do not imply that the verified typeset-PDF locator profile also verifies paperback, hardcover,
  or ebook pagination.

## Privacy and publishing guardrails

- Never commit or publish manuscript text, full chunks, private review pages, or source files.
- Public screenshots should show only short excerpts necessary to explain citations.
- Do not expose endpoints that return arbitrary full chunks or stream source documents.
- Search the complete substantive corpus privately, but expose only edition-qualified locators and
  server-bounded excerpts; enforce rate, concurrency, abuse, and spend limits.
- Keep the development/public exposure profile server-controlled and impossible for a public
  client to override.
- API keys stay server-side and out of frontend storage.

## Open threads for later entries

- Preserve the v6 result as the directional comparison point; do not change its frozen questions
  or rubric in response to the observed failures.
- Preserve the successful v8 bounded-absence rule and v10's five-stage G007 document coverage.
  Do not widen G006 to sixteen; target the missing within-stage mechanisms before another full
  ten-question run.
- Later conversion of the practical pilot into exact chunk-level gold data if publication-grade
  retrieval and citation metrics require it.
- Retrieval-only pilot results before any answer generation is graded.
- Judge-human agreement and the final faithfulness/abstention thresholds.
- A pinned dated generator snapshot suitable for a run of record.
- Baseline retrieval, citation, faithfulness, and abstention measurements with run-to-run spread.
- Measurement-driven retrieval changes such as hybrid search, reranking, or query routing.
- Durable saved conversations.
- Paperback, hardcover, and ebook locator profiles after their pagination is supplied.
- Hosted public-demo observation: real cold-start/latency behavior, memory headroom, abuse traffic,
  and whether the initial monthly budget is appropriate.

### 2026-07-27 - The typeset-PDF locator became a verified production artifact

- Built a deterministic edition-locator generator bound to the exact hashes of the private July 6
  typeset PDF, text-free corpus manifest, and private chunk file. It refuses to run if any of those
  inputs change.
- Generated edition-qualified page spans for all 481 retrieval-eligible chunks. The committed
  fixture contains only chunk IDs, page labels, physical alignment positions, hashes, methods, and
  confidence metadata; it contains no manuscript or PDF text.
- The mapper uses six exact twelve-token anchors to identify each chunk's monotonic occurrence and
  denser local anchors to recover page boundaries that sparse sampling can miss. Ten repeated-anchor
  cases were resolved without allowing document order to regress.
- Visual review covered the Introduction, the Roman-to-Arabic numbering transition, a chapter
  opening, a footnote-heavy page, a multi-page span, the Epilogue, Afterword, and Appendices A, B,
  and D. That review found a useful real defect: Appendix B continues onto typeset page 452 even
  though its sparse anchors initially landed only on 451. Dense boundary refinement corrected the
  public locator to `pp. 451-452`.
- The final distribution is 31 one-page, 353 two-page, and 97 three-page chunk spans. This differs
  from the earlier feasibility sample because the production pass deliberately maps complete
  endpoints instead of reporting only the outermost sparse sample hits.
- This locator profile applies only to `Typeset PDF (July 6, 2026)`. Paperback, hardcover, and
  ebook addresses remain separate future profiles and must not inherit these page numbers.

### 2026-07-27 - Public Archivist became a bounded product rather than a public copy of development

- Added two startup-only exposure profiles over the same 481-chunk retrieval corpus. Local
  `development` keeps the full diagnostic source display and owner cost tools. `public_demo`
  cannot be selected by the browser and exposes only the conversation needed for the built-in
  manuscript.
- Kept the private and public products on one retrieval and answer path. The public boundary does
  not weaken the RAG by searching a sample of the book; it limits what leaves the server after
  generation.
- Replaced public full-chunk source objects with a minimal, versioned DTO. Every cited source keeps
  its model-assigned number and receives a chapter title plus a qualified
  `Typeset PDF (July 6, 2026), p./pp.` location. At most three sources receive excerpts; one
  excerpt is capped at 280 characters/two sentences and the complete source panel at 700 quoted
  characters.
- Added a second release guard that rejects an answer reproducing 45 or more contiguous manuscript
  words. This is deliberately separate from excerpt truncation: source-card limits cannot protect
  the book if the generated answer itself turns into a long quotation.
- Removed the public attack surface instead of hiding controls. The public app allowlists
  liveness, readiness, configuration, and the current-book question endpoint. Upload, project
  creation, embedding, index, source-file, source-search, cost-management, OpenAPI, and arbitrary
  project routes return `404`.
- Removed browser control of retrieval depth and the budget override. The server fixes retrieval
  depth, caps request size, permits one active model request, rate-limits each reader and the
  single instance globally, and requires a positive monthly OpenAI ceiling before public mode can
  start.
- Added safe public failures and browser security headers. Public errors retain an internal
  request ID for logs without returning exception messages, filenames, paths, diagnostics,
  resolved queries, costs, or ledger state.
- Kept liveness distinct from readiness. A new service can boot while its empty persistent disk is
  being seeded, but readiness does not pass until all 481 Chroma records, private chunks, manifest,
  and edition locators pass the full identity preflight.
- Built a private, gitignored deployment archive containing only the pruned live Chroma collection,
  matching chunks, and a text-free identity manifest. It is 3,274,947 bytes with SHA-256
  `37642f9d495d93834829d0749d2c25389c069bd160caf438bbc34b6c2f4ad78f`.
  Neither the source DOCX nor PDF is inside it, and the archive still must never be published.
- Selected a paid, single-instance Render web service with a 1 GB encrypted persistent disk as the
  first hosting shape. This matches the current native Python/FastAPI/Chroma application and its
  in-memory concurrency gate. The Hobby workspace can remain free; the expected baseline host
  charge is one Starter instance plus one GB of disk. Hosting is separate from OpenAI API usage.
- Added a repository-root Render Blueprint with automatic deploys initially disabled and a
  `$5.00` application-level monthly OpenAI ceiling. The OpenAI key remains an unsynchronized
  dashboard secret. The manuscript bundle is transferred directly to `/var/data` only after the
  service exists.
- Ran a four-turn public-mode release smoke against an isolated ledger:
  - focused Edwin Sandys opening: answered in 32.63 seconds;
  - contextual self-government follow-up: answered in 16.27 seconds;
  - broad tobacco/labor synthesis: answered in 51.21 seconds;
  - absent cause of Sandys's death: correctly returned `insufficient_evidence` in 3.86 seconds.
- The smoke cost an estimated `$0.27691761`: four answer-generation calls, one query-planning call,
  one follow-up-resolution call, and four tiny query embeddings. The broad synthesis was both the
  slowest and most expensive turn, which is an honest early public-performance constraint rather
  than a reason to remove its completeness pass.
- The broad answer returned eight edition locators but only three excerpts; its longest excerpt
  was 277 characters. All public answers omitted costs, diagnostics, resolved queries, internal
  paths, physical PDF positions, chunk IDs, and full text.
- Direct anonymous abuse checks confirmed `404` for private/API-documentation routes, `422` for
  client retrieval tuning, `413` for an oversized body, and `429` plus `Retry-After` after the
  per-reader request limit. CSP, clickjacking, referrer, and MIME-sniffing headers were present.
- Prepared Cromblog without inventing a production URL. Archivist now has a real Projects entry,
  and the featured panel contains an English product explanation instead of placeholder Latin.
  Before deployment it says `Deployment ready` and links to that entry. Once
  `NEXT_PUBLIC_ARCHIVIST_URL` contains a verified HTTPS address, both surfaces expose the live
  demo automatically. No Archivist blog post was added.
- Wrote an owner deployment runbook covering account setup, Blueprint review, the private disk
  transfer, exact hashes, restart/readiness checks, anonymous release checks, and the final
  Cromblog environment variable. The remaining boundary is external and deliberate: create the
  Render account and payment method, review the billable resources, and enter the API key without
  sharing it.
- Full local verification passed before the hosting handoff: 471 backend tests passed with one
  intentional skip, Ruff passed, both frontend production builds passed, and the isolated private
  runtime bundle returned ready with all 481 records.

Useful blog lesson: deploying a RAG demo is not just putting its development server on the
internet. The retrieval corpus, disclosure payload, cost authority, route surface, and readiness
definition are separate design decisions. Cromblog can make the experience feel like one portfolio
without forcing a static Next.js host to carry Python, native Chroma, or a private manuscript.

### 2026-07-28 - The first live Blueprint review caught a disk-specific Render constraint

- Created the Render Hobby workspace, added billing, and pushed the prepared Archivist and
  Cromblog commits to GitHub so the hosting handoff could begin.
- Render successfully found the repository-root Blueprint, but rejected one optional lifecycle
  setting: `maxShutdownDelaySeconds` is not supported on a service that also mounts a persistent
  disk.
- Removed that setting rather than weakening the one-instance persistent-disk architecture. The
  application still handles ordinary process shutdown, while Render supplies its supported
  disk-backed service lifecycle.
- This was a configuration preflight failure only. No service or disk had been created and no
  hosting deployment had begun when the correction was made.

Useful blog lesson: a checked-in infrastructure file can be syntactically valid yet still violate
a provider rule that depends on a combination of resources. Reviewing the provider's proposed
resources before pressing Deploy caught the issue before it created a billable service.

### 2026-07-28 - Archivist went live with its private corpus outside GitHub

- Deployed commit `b2a7ace` as the paid Starter service
  `archivist-cradle-of-the-empire` in Render's Virginia region. The generated public address is
  `https://archivist-cradle-of-the-empire.onrender.com`.
- Confirmed that the process-only liveness probe returned `200` while readiness and public
  configuration returned `503` before the corpus was installed. That distinction let the web
  service deploy normally without pretending an empty disk could answer questions.
- Authorized the development computer with a public SSH key and transferred the private
  3,274,947-byte runtime archive directly to `/var/data`. The SHA-256 checksum on Render exactly
  matched `37642f9d495d93834829d0749d2c25389c069bd160caf438bbc34b6c2f4ad78f`
  before extraction.
- The persistent disk contains the pruned Chroma collection, matching 481-chunk payload, and
  text-free bundle manifest. The original manuscript DOCX and typeset PDF were not uploaded to
  GitHub or included in the deployment archive.
- After extraction, the already-running process passed readiness without a restart. Public
  configuration reported `public_demo`, 481 searchable and embedded chunks, no cost ledger, no
  local tools, no full source text, and enabled typeset-PDF page locators.
- Ran one paid neutral live question: “Who was Edwin Sandys, and what did he do?” It completed in
  about 41 seconds with `answered` status, six edition-qualified source locators, and excerpts on
  only three of them. The response omitted internal paths, chunk IDs, retrieval diagnostics,
  ledger data, and full manuscript blocks.
- Anonymous boundary checks passed: the app shell returned `200`; API documentation, project
  enumeration, and private routes returned `404`; a client retrieval override returned `422`; an
  oversized body returned `413`; and invalid no-model requests reached `429` with a
  `Retry-After` header.
- GitHub deployment records confirmed that Cromblog's production environment is Vercel. Its
  prepared integration reads `NEXT_PUBLIC_ARCHIVIST_URL`, keeping the service address in
  deployment configuration rather than hard-coded source.
- Set that variable for Cromblog's Vercel Production environment and rebuilt the existing
  `20aaeca` deployment. External checks confirmed `200` for the homepage and Projects page, a
  live-demo label and verified Render link on both surfaces, and `200` from the final Archivist
  target. No Archivist announcement post was added; that remains a separate editorial step.

Useful blog lesson: keeping the corpus out of the repository did not require reducing the public
demo to a sample. Code and the disclosure-safe interface deployed first, the complete private
retrieval bundle crossed a separate authenticated channel, and readiness changed only after all
481 records passed identity checks.

### 2026-07-28 - The public boundary found one frontend assumption before launch closeout

- The first live public answer reached the browser successfully, but the page turned blank while
  rendering it. The API had behaved correctly: public mode deliberately omits
  `run_diagnostics`, resolved queries, and other private implementation details.
- The frontend still treated `run_diagnostics` as mandatory and read
  `validation_error_code` from the missing object. That presentation-contract mismatch produced
  the browser `TypeError`; it was not a retrieval, model, or manuscript-index failure.
- Commit `1dd45aa` made public-only response fields optional in TypeScript and guarded diagnostic
  reads. The same fix moved the stored-vibe initializer out of inline HTML and into the compiled
  application bundle so the public Content Security Policy could remain strict.
- The backend public-boundary test now explicitly checks the route's successful minimal response
  without `run_diagnostics`, while the production frontend build type-checks every diagnostic read
  against the optional contract. A live public question remains the final end-to-end release check.

Useful blog lesson: privacy filtering changes an API's shape, not merely its contents. A frontend
tested only against the richer development payload can fail precisely because the production
server is withholding sensitive diagnostics as designed.

### 2026-07-28 - Archivist received a canonical portfolio address

- Registered `archivist.mcrombie.com` on the existing Render service. Render verified the domain
  and issued its HTTPS certificate.
- Added a Cloudflare **DNS-only** CNAME from `archivist` to
  `archivist-cradle-of-the-empire.onrender.com`. The generated Render address remains enabled as
  an operational fallback.
- Updated Cromblog's Vercel Production `NEXT_PUBLIC_ARCHIVIST_URL` to
  `https://archivist.mcrombie.com`, rebuilt the site, and verified that the custom-domain app and
  the portfolio link both work.
- This was an infrastructure and presentation change only. It did not move the corpus, rebuild the
  private index, alter retrieval, or change the public disclosure boundary.

Useful blog lesson: one portfolio can span several providers cleanly. Vercel serves Cromblog,
Render runs the stateful Python/Chroma application, and Cloudflare supplies the small DNS bridge
that gives the separate service a coherent `mcrombie.com` identity.

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
