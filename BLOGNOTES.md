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

- A paid post-fix confirmation of the opening-screen relationship question, followed by the
  unchanged ten-question comparison under the new `evidence-planned-v2` cohort.
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
