# Archivist blog notes

Working notes for the announcement and demonstration of Archivist. This file is a development
journal, not polished post copy. Keep claims here factual, dated when possible, and clearly mark
anything that still requires measurement.

## Current checkpoint — 2026-08-12

- **Product:** the public, book-specific reader is live at `https://archivist.mcrombie.com`. The
  local code reports `evidence-planned-v26`, `query-planner-v11`, and
  `evidence-coverage-v11` over 481 retrieval-eligible manuscript chunks. Render deploys remain
  manual. The production cohort bound deployed wrapper commit
  `e71d9b79a60a894cb38451c37e0d43b7f9149fa9`, one process epoch, policy, model, corpus manifest,
  and the versioned `$2.00` Complete-RAG request ceiling before sending any measured question.
- **Public spend ceiling:** the owner raised the ongoing public-demo ceiling from `$5.00` to
  `$10.00` on 2026-08-12. The source configuration records that decision; Render's manual Blueprint
  sync must still make the live environment match it. The persistent August ledger retains the
  `$4.90594694` production-cohort spend, leaving `$5.09405306` beneath the new ceiling before any
  later public usage. The separate `$2.00` conservative per-request maximum is unchanged.
- **Reader experience:** Complete answer is the default. Progressive response is an experimental
  advanced setting. Ten semantic modes and eleven visual appearances are implemented; they are
  public interpretive prototypes, not formal evidence that perspective changes preserve answer
  quality. Opening-page advanced settings now expand in document flow so all controls remain
  reachable by ordinary page scrolling; docked settings remain a viewport-bounded overlay. The
  separate full-context-v2 experiment remains disabled on the public server.
- **Measurement:** the unchanged ten-question cohort is development evidence. The 37-item
  owner-adjudicated gold set and provenance are formally locked against frozen V26. Its first
  held-out measurement is complete: dense macro Recall@5 was 24.71% and hybrid Recall@5 was 25.97%
  (+1.26 points). This is a retrieval-only diagnostic, not an answer-quality score. The authorized
  answer-quality baseline is now complete. Recovery-04 preserves all 37 answer artifacts: 35
  completed/released answers and two generation-side technical-error artifacts. Exactly 37 Terra
  decomposition attempts produced ten usable decompositions and 27 technical measurement failures
  (26 `exact_span_mismatch`, one `incomplete_response`). No answer or attempted decomposition was
  retried or repaired. The 27 failures belong to the ruler, not to 27 candidate answers.
- **Gold-set status:** the private workbook retains 37 questions across all six contracted strata:
  8 focused biographical, 8 focused analytical, 5 conceptual, 10 broad thematic, 4 out-of-corpus,
  and 2 adversarial-premise items. H020, H039, and H040 are intentionally absent. The owner source
  remains untouched beside cleaned and final copies. Canonical schema, composition, location,
  question-commitment, overlap, privacy, provenance, and frozen-candidate checks pass. Parts of the
  annotations began as historical Claude drafts, but the owner later source-verified and
  adjudicated them. This is disclosed without a prospective-blinding claim.
- **Baseline result:** the report covers 198 sources, 251 citation references, and 41 claims from
  ten schema-valid decompositions. Two of those are zero-claim generation-error records, so the 41
  claims cover eight substantive releases. Citation resolvability is 251/251 (1.000); malformed
  citations are 0/250; citation completeness is 34/41 (0.829); cited-source to gold-location match is 23/34
  (0.676); and gold-location retrieval coverage is 75/428 (0.175). Claim-derived measures use only
  the eight substantively decomposed releases, while answer-level citation syntax measures retain all applicable
  observations. Semantic answer-quality fields remain pending by design.
- **Cost and latency:** the closed ledger records 125 priced events, zero unpriced events, and
  `$7.02298147` total estimated API cost under the `$20.00` cap. H003's audited recovery leaves 36
  exact generation-latency observations in the 37-item scope: 1,817.196 seconds total, 50.478-second
  mean, 47.928-second p50, 91.695-second p95, and 108.685-second maximum. These are evaluation
  generation-pipeline timings, not production HTTP latency.
- **Production-performance status:** the fixed warm cohort is complete. It attempted exactly 33
  answerable held-out first turns with no retry or replacement. Twenty-nine were valid successful
  completions and four were request failures (12.1212%); instrumentation failures were zero.
  Server p50/p95 were 54.393/113.801 seconds across those 29 successes, while client p50/p95 were
  54.493/113.829 seconds. The run recorded 500,164 tokens, 80 priced and zero unpriced events, and
  `$4.90594694` estimated API cost. The public summary is text-free. Its file SHA-256 is
  `dd13ad2cf60a863daf88e549106059a1d05126b40ffa3c66c3c8e18cb6246b7f`, and its embedded
  canonical artifact hash is `e2fcc051e66b115cf56abf7061fa93bfcd3c12297396cbdc3fad42b8bd1bfd30`.
  This is one observed cohort, not an SLA or latency guarantee.
- The four failures all occurred after successful planning and direct-answer evidence selection,
  at the generation-contract release boundary: two `missing_unit_requirement_id`, one
  `obligation_role_mismatch`, and one `unsupported_requirement_has_unit`. This is reassuring for
  infrastructure observability but not for product reliability: the public response-contract
  completion rate was 29/33, or 87.9%.
- **Next evidence step:** preserve the descriptive and production cohorts unchanged. The production
  resume blank can now be filled with the exact observed denominators. If stronger claim-derived
  answer scoring is still useful, diagnose and redesign the decomposition instrument in a separate
  cohort. Semantic calibration remains optional, lower-priority supplemental work.

This checkpoint is the source of truth for current blog drafting. Entries below preserve what was
known at the time they were written and should not be silently rewritten into present-tense claims.

## 2026-08-12 — Let advanced settings enlarge the opening page

- A desktop usability check found that expanding Archivist's reading options on the opening page
  could reveal more controls than the viewport allowed, while the bottom of the panel remained
  unreachable. The panel was absolutely positioned below the compact composer inside a clipped
  landing section, so neither the document nor the panel's own scrollbar could expose everything.
- Kept the compact overlay behavior for an active conversation, but made the opening-page
  disclosure participate in normal document flow. Expanding its advanced delivery,
  interpretation, or appearance controls now makes the page longer and lets ordinary page
  scrolling reach the final controls. The docked overlay also uses the dynamic viewport and safe
  area when calculating its scrollable height on small screens.
- This was a presentation-only repair. It did not change the selected reader mode, evidence scope,
  prompts, retrieval, model calls, or any preserved evaluation result.

## 2026-08-12 — Give the public demo a deliberate monthly allowance

- After the production cohort, Archivist's ordinary `$5.00` monthly ceiling left only
  `$0.09405306` above the `$4.90594694` already recorded in August. That was below the service's
  separate `$2.00` conservative reserve for admitting another Complete-RAG request, so the public
  demo correctly stopped before making another paid call.
- The owner deliberately raised the ongoing public-demo ceiling to `$10.00`. This is distinct from
  the temporary `$10.00` allowance used for the fixed 2026-08-11 cohort: the cohort limit was an
  experimental cap, while this change funds ordinary reader access. The dated cohort history and
  sealed results remain unchanged.
- Raising the ceiling does not erase recorded usage. Against the existing August cohort spend, it
  creates `$5.09405306` of remaining application-level headroom. Actual OpenAI billing remains
  authoritative, and the `$2.00` maximum per request plus existing rate and concurrency limits stay
  in force.
- The repository Blueprint is the source of truth, but Render deploys are manual. The new ceiling
  takes effect only after the Blueprint is synchronized and the live environment and persistent
  ledger agree with the deployed source.

Useful blog lesson: a safety budget should distinguish a one-time benchmark authorization from the
ordinary allowance needed to keep a public demonstration usable. Raising the latter changes future
spending authority; it does not rewrite past spend.

## 2026-08-10 — Turned the last resume blank into a fixed production protocol

- The first production-latency plan said “30–50 successful warm first turns” while also promising
  an error rate. That wording left a serious loophole: failed requests could be replaced until the
  success target was reached, producing a survivor-biased latency distribution and an unstable
  error denominator. It also left warm status, the latency boundary, p95 calculation, and spending
  reserve undefined.
- Replaced that loose target with exactly 33 **attempted** requests: the answerable items from the
  already locked 37-question set. Every item remains in the denominator once started. There is no
  retry or replacement, every request has a fresh conversation and empty history, and the public
  artifacts expose neither H identifiers nor question text.
- Fixed the product path rather than constructing a faster test-only path: Essential mode,
  Complete-answer delivery, ordinary RAG, sequential first turns, and at least 12 seconds between
  request starts. The pacing interval is excluded from latency and prevents an accidental rate-
  limit test against the six-per-minute per-client gate.
- Defined “warm” narrowly and honestly. Two readiness observations and `/api/version` must bind one
  running Render process epoch, exact `RENDER_GIT_COMMIT`, active policy/model, corpus manifest, and
  frozen candidate. There is no unmeasured paid warm-up request and no claim that provider caches
  are warm.
- Defined server latency from request ingress through complete response construction. p50 is the
  median; p95 is nearest rank; both use only the explicitly reported `S` valid successful
  completions. Request error rate uses all 33 attempts, while missing or mismatched telemetry is a
  separate instrumentation failure rather than a silently discarded row.
- Added privacy-safe request correlation across the public observation, answer diagnostics, and
  token/cost ledger. The publishable summary is aggregate and text-free; request-level private
  artifacts remain gitignored. The paid runner also requires an explicit acknowledgement and
  owner-authorized cohort cap.
- Replaced the runner-invented `$1.00` reserve with a server-owned request contract. The public
  Complete-RAG service exposes `public-rag-request-ceiling-v1` and its `$2.00` maximum through
  `/api/version`, checks the full maximum against the monthly budget before RAG, projects each
  provider operation before send, and requires usage to be recorded. The prepared manifest,
  deployed identity, authorization record, and runner must all bind that same contract.
- Made ambiguous transport outcomes expensive in the accounting rather than deceptively cheap. If
  the client cannot prove whether a request was accepted or billed, that ordinal is sealed without
  replay and consumes the full `$2.00` maximum against the owner authorization. Recorded cost stays
  a lower bound and the exact total is marked unavailable until every attempt has measured usage.
- A successful response with zero usage events is now an instrumentation failure and cannot enter
  the latency distribution. The runner also rejects a pre-existing conversation/turn scope before
  writing an intent or POSTing, so stale production records cannot impersonate a cohort attempt.
  Render's `RENDER_GIT_COMMIT` wins over any local/test override and remains the authoritative live
  release identity.
- No live request or OpenAI call was made during this implementation. The release still has to be
  deployed and identity-checked, and the owner must separately authorize the 33-question data scope
  and numeric cost ceiling. Until then, the production p50, p95, error rate, and spend remain blank.

Useful blog lesson: a median is not credible merely because the arithmetic is correct. The attempt
denominator, failure policy, process identity, clock boundary, pacing, and cost stop all determine
which observations were allowed to reach that median.

## 2026-08-09 — The 37-question baseline is complete, and the ruler is part of the result

- The evaluation finally closed exactly as authorized: all 37 frozen V26 answer artifacts are
  preserved, followed by exactly one Terra decomposition attempt per answer. Recovery-04 first
  converted H029's already-spent, empty `incomplete` response into an auditable technical outcome,
  then called only the nine untouched items H030–H038. There were no retries.
- The answer side and the measurement side tell different stories. Archivist produced 35
  completed/released answers plus two generation-side technical-error artifacts. Terra supplied ten
  usable decompositions, while 26 outputs failed exact text/span validation and one exhausted its
  reasoning allowance without producing output. Calling these 27 failed *answers* would blame the
  candidate for the ruler's malformed readings.
- The mechanically available citation evidence is still useful. All 251 citation references
  resolved; none of 250 syntax-eligible citations was malformed; 34 of 41 decomposed claims carried
  a citation; 23 of those 34 citations matched an owner-recorded gold location; and retrieval found
  75 of 428 gold locations. The last two figures show how much evidence coverage remains to improve,
  but the 41-claim universe represents only eight substantively decomposed releases.
- The run cost `$7.02298147` across 125 priced and zero unpriced events. Its 36 exact generation
  timings totaled 1,817.196 seconds, with a 47.928-second median and 91.695-second p95; H003's
  trace-backed recovery is disclosed rather than assigned an invented duration.
- The sealed run identity points to harness commit
  `c7cd58bcdc0963e13b4626854cdfc3e786be5b72`. Later documentation commits intentionally change the
  live Git identity, so an exact replay audit should use that producing commit in a detached
  worktree rather than pretending the report was generated by the documentation-only head.
- This is the project's first complete descriptive answer-quality baseline. It is not yet the full
  semantic scorecard: faithfulness, abstention, gold-claim recall, and related judgments remain
  pending. More importantly, a 27/37 failure rate means the next instrument should be rebuilt and
  validated in a new cohort. The completed baseline stays frozen as evidence of what both the
  candidate and its first ruler actually did.
- The public-safe, text-free local report is
  `runtime/evaluations/v26-held-out-answer-quality-2026-08-07-harness-recovery-04/precalibration-public-report.md`;
  its summary SHA-256 is
  `eaa6d33460c0c616467e9cd9cb043c762e16c5e6a6654cfe2eebd3360655dc7a`.

Useful blog lesson: evaluation infrastructure is not an invisible neutral observer. When a strict
ruler fails mechanically, preserving that failure can be more credible than forcing a tidy score.
The useful claim is not that every answer was good; it is that every answer and every attempted
measurement survived intact, with the limits of each denominator made visible.

## 2026-08-09 — Turning a repeated malformed measurement into an honest cohort outcome

- H002 showed that H001 was not a one-off interruption worth handling with another bespoke retry
  decision. Terra produced a second parseable decomposition whose offsets did not reproduce its
  own claim text. The strict validator rejected it, and the run correctly spent nothing on a retry.
- The existing response was retrieved by ID rather than regenerated, then preserved as a private
  snapshot. This made the distinction visible: the model call happened and belongs in cost and
  attempt counts, but its output cannot be used as canonical claim measurement.
- The harness now needs to represent that distinction directly. Each of the 37 answers still gets
  exactly one Terra attempt. A successful decomposition contributes to claim-dependent metrics; a
  mechanically proven local ID/span failure contributes a disclosed technical outcome instead.
  Neither is silently discarded, repaired, converted to zero claims, or counted as an answer miss.
- A durable pre-call intent and exact final ledger closure turn “no automatic retries” from a client
  setting into a recoverable audit rule. If an interruption leaves the call's status ambiguous, the
  next run stops rather than guessing and risking a duplicate charge.
- This repair is deliberately narrower than making the judge more forgiving. It preserves the
  frozen V26 answers and the failed measurement outputs as evidence, while allowing the remaining
  untouched items to finish under the original authorization.

## 2026-08-07 — The first held-out retrieval diagnostic

- Ran the predeclared dense-versus-hybrid benchmark against frozen candidate
  `8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e` / `evidence-planned-v26`. The 33 answerable items
  form the recall denominator; four out-of-corpus items remain reserved for absence behavior.
- The primary result was 24.71% dense macro Recall@5 versus 25.97% hybrid Recall@5, an absolute
  hybrid gain of 1.26 percentage points. Hit@5 rose from 90.91% to 93.94%; context recall rose from
  31.96% to 33.74%; and essential-claim coverage in assembled context rose from 44.98% to 47.22%.
- The aggregate hides a mixed result. Hybrid improved focused-biographical Recall@5 by 6.49 points
  and adversarial-premise Recall@5 by 12.50 points, but conceptual Recall@5 fell by 8.40 points.
  Focused-analytical recall was effectively flat, and its essential coverage was lower under
  hybrid retrieval. Eleven answerable items improved, thirteen were unchanged, and nine worsened.
- High Hit@5 alongside low Recall@5 is the central diagnostic: Archivist usually finds at least one
  relevant passage, but often fails to retrieve enough of the complete expected evidence set.
  Recall@20 reached 49.58% dense and 53.03% hybrid, showing useful headroom in candidate selection
  and context assembly rather than proving an answer-generation defect.
- Five fixed, stratified noise-floor repetitions produced zero spread. That establishes
  deterministic behavior for this path, not broad statistical significance. Hybrid is therefore a
  small, reproducible, heterogeneous improvement—not a universal retrieval victory.
- The run made one no-retry `text-embedding-3-small` request containing only the 37 locked question
  strings: 521 tokens and an estimated cost of `$0.00001042`. It invoked no planner, generator,
  answer model, or judge. The private text-free cache and result remain ignored under
  `runtime/evaluations/`; their SHA-256 digests are
  `80524b064086d4b677b0f7f5b2cf5f0579256ba7c262c63c06c3807bece7ce09` and
  `2f1eb1dca6f3713271d17d4cff4da3f659d31cded34a8d98d3f789e9394d9a4f`.
- The result does not authorize a repair. V26 and the gold set remain untouched so the next
  citation, faithfulness, abstention, and complete answer-quality measurements retain the same
  held-out boundary.

## 2026-08-07 — The held-out ruler is finally locked

- The owner explicitly confirmed the final attestation after completing the workbook review. The
  37-item private-safe gold JSON and provenance v4 sidecar were promoted to their committed paths;
  the original workbook and manuscript evidence remain private and ignored.
- The lock binds frozen candidate `8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e`, V26 policy, the
  text-free owner-field commitment, exact gold bytes, corpus manifest, and development registry.
- Offline gates report all six required strata, zero exact or near development-question overlap,
  zero copied-language flags, and valid source locations. No H-item was sent to Archivist while
  constructing or locking the ruler.
- The important transition is methodological: future misses are now evidence about the system,
  not invitations to edit the exam. Retrieval measurement comes next.

## 2026-08-06 — Choosing honest retrospective provenance over process theater

- The owner chose not to send the held-out set through a fresh Claude annotation pass merely to
  create cleaner paperwork. The completed annotations remain authoritative because the owner had
  already checked and adjudicated them against the manuscript; Claude's earlier contribution is
  described as drafting assistance rather than ground truth.
- This required a contract correction before any formal run. Provenance v4 explicitly records
  that the exact historical model, surface, complete raw draft, and prospective blinding record are
  unavailable. It does not backfill hashes or claim a process that did not occur.
- Candidate independence remains intact on the evidence available: the owner controlled the
  questions and scoring decisions, the question set has no registered development overlap, its
  text-free projection was frozen before any H-item reaches Archivist, and the answer pipeline
  remains fixed at V26.
- Two accurate rubric claims contained manuscript-like runs. They were paraphrased in the private
  Word source and synchronized JSON without changing essentiality or source bindings. The privacy
  audit fell from three flags across two claims to zero. No model or paid API call was made.
- A final guardrail review closed two quiet failure modes: formal lock now checks the committed
  owner-field fingerprint, and private paraphrases are digest-bound to their intended original
  claims and must all be consumed. A stale commitment, wrong ordinal, or unused replacement now
  fails loudly instead of silently changing the evaluation artifact.
- The evaluation-only checkpoint passed repository-wide Ruff and 774 Python tests with one
  intentional skip. The 63-page final workbook was rendered and visually checked before the
  checkpoint was saved.

## 2026-08-06 — Owner fields frozen and annotation handoff prepared

- Owner decision removed H039, leaving 37 retained questions while preserving the stable gapped
  identifiers. No other question was rewritten during canonicalization.
- A deterministic offline importer created a separate final DOCX and private canonical JSON,
  validated all retained structure and locations, and emitted no held-out prose to Git.
- The development-overlap audit found zero exact duplicates and zero fuzzy flags. The privacy audit
  found three long copied-phrase risks in two inherited annotation claims; those findings remain
  explicit for replacement or adjudication after fresh blinded drafting.
- Git now receives only a text-free commitment: 37-item count, six-stratum distribution, and the
  SHA-256 of ordered ID/question/stratum/Behavior fields. The private provenance draft binds it to
  frozen candidate `8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e` and V26 policy.
- Eight private question-only annotation batches, an exact hash manifest, an owner checklist, and a
  raw-response ledger were prepared offline. No Claude upload, Archivist request, API call, or paid
  operation occurred.
- The evaluation-only checkpoint passed repository-wide Ruff, 774 Python tests with one intentional
  skip, both focused frontend suites, and the production frontend build.

## 2026-08-06 — Held Out Evaluation Set Complete

- The owner finished the held-out question workbook and made the inclusion, behavior, category,
  claim, relevance, negative-tripwire, and note decisions for the retained cohort. Accepting a
  smaller final cohort left 38 questions, still inside the contract's 34–46-item envelope and every
  per-stratum range.
- Mechanical cleanup preserved every retained question and per-item claim count, normalized the
  document for comfortable review, and verified all 570 recorded chunk references against the
  frozen derived corpus. The source workbook was not overwritten.
- The workbook and manuscript-derived labels remain private under `runtime/gold-authoring/` and are
  intentionally absent from Git. This commit records the contract, process, tooling, and milestone,
  not the held-out answers themselves.
- The milestone checkpoint passed Ruff for the provenance implementation and tests plus 69 focused
  offline gold/provenance/holdout tests. No model or paid API call was made.
- “Complete” here names the owner-authoring milestone. It is not a benchmark score: canonical JSON,
  provenance lock, and the first untouched run still lie ahead. Mechanical cleanup also surfaced
  one explicit H039 question/rubric reading conflict for resolution before lock.

## 2026-08-06 — Rigor without performative annotation labor

- Reviewing H001 exposed a mismatch between benchmark rigor and the workbook's burden. The old
  guidance treated realistic ambiguity as a question defect, grammatical compounds as automatic
  microclaim work, accurate AI paraphrases as text that still had to be rewritten, and negative
  expectations as a potentially unbounded list.
- The owner-authorized contract amendment keeps the controls that matter: held-out questions remain
  owner-designed and candidate-blind; every proposed annotation is checked directly against the
  manuscript; every support and relevance location is adjudicated; and copied manuscript language
  remains forbidden.
- The lighter standard changes the labor, not the independence. Questions may look like real user
  questions when their scoring interpretation is stable. Claims are the smallest independently
  scorable units needed for material correctness. Historical background may be in scope.
  `must_not_claim` is an optional, non-exhaustive set of a few high-value tripwires.
- Accurate AI-drafted paraphrases may be consciously adopted after source verification rather than
  cosmetically rewritten. Provenance advances to `archivist.gold_provenance/3` so that distinction
  is explicit and auditable. No formal held-out run existed, so no formal result was invalidated.

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

## A useful conceptual frame: crafting an elegant context window

Archivist can reasonably be described as an attempt to craft an elegant context window for an
LLM. The model cannot usefully receive an entire long manuscript plus every conversational turn,
so most of the engineering is editorial:

- ingestion turns the book into stable, addressable passages;
- chunking decides which ideas should remain together;
- retrieval and query planning decide which passages deserve the limited context budget;
- neighbor expansion restores local continuity that chunking may have cut away;
- stage and transition contracts reserve room for the different historical roles a long question
  actually asks about;
- conversation resolution carries forward the user's intent without treating old model prose as
  evidence;
- citations preserve the route from generated claims back to the passages admitted to context;
  and
- validation and evaluation ask whether the selected context was sufficient and whether the model
  used it honestly.

The analogy should not imply that Archivist merely writes a clever prompt. The context window is
the center of the design, but corpus preparation, retrieval, source accounting, validation,
privacy, and measurement determine what can safely enter it. A good short description for the
eventual post is: **Archivist is a system for composing a small, inspectable reading packet from a
large book before asking an LLM to answer.**

## Development chronology

## Reconstructed pre-Codex chronology

The original journal began on July 21. The following history was reconstructed from the first 25
Git commits and their code, covering March 31 through July 14. Commits are grouped by calendar day
but listed individually so the path from the initial experiment to the first web application
remains auditable.

### 2026-03-31 - Local, private scaffolding

- `b8ec759` created the repository structure, environment exclusions, and first dependency
  snapshot. The manuscript, generated output, virtual environment, `.env`, and Python caches were
  excluded from Git from the first commit.
- The dependency snapshot already included OpenAI and Chroma, making the initial technical thesis
  visible before application code existed: keep the book local, create embeddings, and retrieve
  passages into a model context.

Useful blog lesson: the privacy boundary was not a late public-launch patch. The raw manuscript
began outside source control.

### 2026-04-01 - From manuscript files to addressable passages

- `1ee0051` added the first ingestion experiment. It read the Markdown manuscript, removed headings
  and image markers, and tested paragraph extraction. The commit records an important editorial
  correction: an export that moved all footnotes to the end was rejected in favor of inline
  footnotes so retrieved prose would retain its supporting context.
- `146d101` converted that experiment into deterministic ingestion. Sorted Markdown files became
  four-paragraph chunks with one-paragraph overlap, stable chunk IDs, chapter titles, paragraph
  ranges, and JSON output.

Useful blog lesson: RAG quality began with book production choices. Where footnotes appear and how
paragraphs are addressed affect what the model can know later.

### 2026-04-02 - Rhetorical chunking and the first vector search

- `a945941` made chunk boundaries sensitive to prose. It avoided beginning a chunk with a quotation
  whose setup lived in the prior paragraph and avoided weak transitional openings where possible.
- `88388cb` added the first complete embedding and query path. Chunks were embedded in batches of
  50 with `text-embedding-3-small`, stored in a persistent Chroma collection, and queried through a
  command-line semantic search that returned five passages.

Useful blog lesson: chunking is not only a token-size calculation. It is an editorial judgment
about which sentences require one another to remain intelligible.

### 2026-04-03 - The retriever became a source-grounded answer system

- `745c366` exposed document names, chapter titles, chunk IDs, paragraph ranges, distances, and
  longer previews in the query tool so relevance could be inspected rather than guessed.
- `c7ffe0a` created the first Answer Mode. It passed retrieved manuscript passages to `gpt-5`,
  required source-cited answers, and instructed the model to admit when the supplied evidence was
  insufficient.
- `2f6b034` strengthened the prompt's citation behavior.
- `44566c0` added immediate neighboring chunks around semantic hits so a good match would not lose
  the setup or consequence just across a chunk boundary.

Useful blog lesson: the project became RAG when retrieval stopped being a search demo and became a
bounded, visible evidence packet for generation.

### 2026-04-04 - The displayed sources were aligned with the model's sources

- `1b08639` required citations immediately after supported claims, allowed grouped citations for
  genuinely shared support, emphasized precision, and prohibited invention.
- `9956870` fixed a source-namespace bug in which an answer could cite an expanded source such as
  Source 9 while the CLI displayed only the original five retrieval hits. The exact expanded
  passages shown to the model became the exact passages shown to the user.

Useful blog lesson: citation syntax is meaningless unless every displayed label resolves against
the model's actual context.

### 2026-04-05 - A finite source budget and the original indexing use case

- `31f59b0` created a canonical context-finalization step: apply a configurable distance threshold
  to primary hits, retain a fallback when all hits exceed it, expand neighbors, and cap the final
  context at eight passages.
- `b3079a9` created Index Mode, originally considered the project's most practical purpose. It was
  intended to help build the book's back-of-book index after typesetting fixed the page numbers.
- `6b77658` repaired Index Mode after pure semantic retrieval failed to find repeated literal uses
  of “Virginia Company.” Exact case-insensitive matching, neighboring passages, and semantic
  fallback became a hybrid retrieval path.

Useful blog lesson: embeddings and literal search solve different problems. A good retrieval
system combines them instead of asking one ranking method to impersonate the other.

### 2026-04-06 - Shared retrieval primitives, noise filtering, and the first self-evaluation

- `d4acece` added optional filtering for structural material such as tables of contents and
  bibliographies so high-frequency but low-value text would not dominate retrieval.
- `d1efc24` moved corpus loading and retrieval/context logic into shared modules, removing the first
  substantial duplication between Answer Mode and Index Mode.
- `2baab9c` wrote the first README, describing the architecture, two operating modes, source
  transparency, limitations, and planned page-number mapping.
- `9e908e1` recorded a large manual evaluation with representative answers, retrieval locations,
  perceived strengths, and known failures. Its broad-theme weakness anticipated much of the later
  formal RAG work, although its favorable citation judgments were not yet backed by the later
  claim-level gold methodology.

Useful blog lesson: the first prototype already identified the enduring problem. Focused questions
could look impressive while broad questions overconcentrated on one dense section of the book.

### 2026-07-03 - The CLI became a local manuscript workbench

- `2888088` added the first FastAPI/React/Vite application. It introduced local project storage,
  manuscript upload, embedding controls, Q&A, index-entry generation, candidate terms,
  existing-index search, and expandable source cards.
- The interface was deliberately local-first, and uploaded projects lived under a gitignored
  directory. At this stage Archivist was still conceived as a general manuscript workbench rather
  than a public conversation with one book.

Useful blog lesson: putting a UI around a prototype reveals product ambiguity. The first web
version exposed every capability at once because the application had not yet chosen its central
reader experience.

### 2026-07-06 - A staged workflow replaced the crowded dashboard

- `4555b76` remodeled the interface around a sequence: upload a manuscript, process and embed it,
  then choose Q&A or Index Mode. It replaced the always-visible sidebar, upload controls, and mode
  tabs with focused screens and a library/archive visual language.

Useful blog lesson: reducing simultaneous choices was the first major UI improvement, even before
the later decision to make Archivist specific to *Cradle of the Empire*.

### 2026-07-07 - Word and PDF manuscripts became first-class inputs

- `f6c16a8` added a conversion layer for Markdown, text, DOCX, PDF, and ZIP uploads. DOCX import
  preserved paragraphs and tables; PDF import extracted selectable text with page markers.
- A final Index, General Index, or Index of Names section could be split from the searchable
  manuscript and retained separately for comparison. Failed embedding received clearer recovery
  instructions and could be retried after import.

Useful blog lesson: accepting a file is not the same as understanding its structure. Import logic
has to preserve the boundaries that retrieval and citations will later depend on.

### 2026-07-13 - Long-running work became legible, then readable

- `896fd8c` added staged processing messages for upload, parsing, embedding, retrieval, answer
  generation, candidate-term discovery, index generation, and index search.
- `bcd75f0` added Manuscript Viewer Mode with paginated processed text, document and chapter labels,
  paragraph references, navigation, and access before the semantic index was built.

Useful blog lesson: responsiveness is partly explanatory. When work takes time, showing which kind
of work is occurring helps the user form an accurate mental model of the system.

### 2026-07-14 - The viewer returned to the typeset artifact and citations became readable

- `cb39521` responded to repeated chapter, page, and overlap errors in the reconstructed viewer by
  opening the original PDF directly when available, while retaining a searchable processed-text
  fallback.
- `37a0df4` replaced opaque Source N labels with chapter-and-paragraph citations. Citations became
  clickable, hoverable evidence links; internal chunk IDs moved behind a copy control; and adjacent
  retrieved chunks from the same chapter were merged for display with duplicate overlap removed.
  Stored chunks, embeddings, and retrieval ranking were deliberately left unchanged.

Useful blog lesson: internal retrieval identifiers and reader-facing citations serve different
audiences. The interface can translate between them without altering the evidence supplied to the
model.

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
2. Use a registered development/example question—not an H-numbered held-out question—so the demo
   cannot contaminate the unfinished formal evaluation.
3. Show the transition into the full-width answer and open one cited source to reveal an
   edition-qualified page range and brief supporting quotation, not a full chunk.
4. Ask a natural follow-up containing a pronoun or shorthand reference to demonstrate
   conversational continuity.
5. Show that the second turn retrieves its own evidence rather than treating the earlier answer as
   truth.
6. Switch from Essential to one interpretive mode and explain that the preset combines appearance,
   historiographical lens, voice, and worldview while the cited manuscript evidence remains the
   answer's factual boundary. Advanced controls expose the individual axes.
7. Mention Progressive response only as an optional experiment; Complete answer remains the
   recommended default.
8. End with the evaluation work: paragraph-addressable chunks, the owner-designed held-out set,
   its blinded-draft/owner-adjudication protocol, and the deliberate pause before any formal score
   is claimed. The public deployment hides private cost and diagnostics panels.

## Screenshots or clips worth capturing

- The opening composition with the cover and product introduction.
- The cover fading away while the first answer centers.
- The archival-paper answer treatment with a visible citation and a compact
  `Typeset PDF, p./pp.` source card.
- A compact follow-up turn with prior sources collapsed.
- Essential and one interpretive mode displaying the same development question.
- The Advanced controls showing Historiographical lens, Voice, and Worldview as separate axes.
- A private development screenshot of the text-free timing or cost ledger, clearly labeled as
  operational evidence rather than public UI.
- The private gold-review workbook's cover and field legend only—never its held-out questions,
  expected claims, locations, or manuscript-derived working notes before lock.

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

- Replace H020 with a genuinely distinct conceptual question and finish the owner's review of all
  forty questions, strata, and Behavior values.
- Close the tooling gap between the private Markdown question form and the pre-assistance
  development-question overlap audit. A hash commitment alone does not prove held-out status.
- Record the question commitment, then obtain fresh canonical Claude batches under the blind
  protocol; treat all pre-commitment Claude text as exploratory only.
- Complete source-level owner adjudication, privacy and leakage audits, provenance lock, and the
  clean frozen-candidate boundary before any H-numbered item reaches Archivist.
- Run retrieval-only measurement first, followed by the citation/faithfulness/abstention pilot,
  baseline comparison, and only then a production cohort with run-to-run spread.
- Pin dated generator and judge snapshots suitable for a run of record; interactive
  `gpt-5.6-sol` is a development model label, not a reproducible snapshot.
- Confirm which Git commit is live after each manual Render deployment rather than inferring
  production parity from the repository.
- Use Progressive timing records to measure provider, schema/release, and proxy delay before
  considering any latency optimization.
- Durable saved conversations.
- Paperback, hardcover, and ebook locator profiles after their pagination is supplied.
- Multi-corpus ingestion and the deferred Index workflow only after the single-book measured path
  is complete.

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

### 2026-07-28 - V14 narrowed broad-answer pressure to the passages that carry the argument

- Closed the public launch record in commit `7c68c9f`. The repository now treats
  `https://archivist.mcrombie.com` as the canonical demo address, keeps the generated Render URL as
  an operational fallback, records the Cloudflare DNS-only bridge and Vercel production setting,
  and regression-tests the deliberately smaller public response contract.
- Implemented `evidence-planned-v14`, `faceted-hybrid-rrf-v8`, and
  `broad-stage-consensus-v1` without changing the manuscript, private index, pinned models,
  neutral baseline, eight-source ceiling, or one-generation-call architecture.
- Broad-stage anchors are no longer chosen from one route alone. Each stage now compares the
  application-owned canonical ranking, a role-specific mechanism ranking, and provider relevance.
  Three-way agreement beats two-way agreement; any agreement beats a singleton; fully disjoint
  rankings fall back in canonical, mechanism, then provider order.
- Preserved the chosen anchor by chunk identity through later context promotion, chronological
  sorting, evidence gating, and source renumbering. The versioned private trace records only
  text-free pool names, ranks, hit counts, and identifiers.
- Replaced the v13 paragraph-as-obligation design with two separate ledgers in
  `evidence-coverage-v6`. `inspection_passages` still cover every retained source range, but do not
  demand output. `synthesis_obligations` are created only for the protected anchor of each surviving
  historical stage.
- Each synthesis anchor now asks for all of the historical functions appropriate to that stage
  rather than rotating one function across arbitrary paragraphs. The local validator still
  requires every declared synthesis dimension before a coarse requirement can be called supported,
  while allowing other directly relevant, cited facts to enrich the answer without artificial
  obligation links.
- Bumped the closed diagnostic trace to `archivist.retrieval_trace/7` and the generation request to
  `archivist.answer_request/3`. The full offline suite passed 476 tests with one intentional skip;
  Ruff and whitespace checks passed. No OpenAI calls were made for this verification.
- The next measurement is deliberately small: one unchanged, no-retry G006/G007 confirmation on a
  clean v14 commit. It must show materially better mechanism synthesis without losing source-group
  coverage or introducing a contradiction before another full ten-question run is warranted.

Useful blog lesson: forcing a model to mention every retrieved paragraph can improve bookkeeping
while making the historical argument worse. A useful completeness pass distinguishes evidence the
model must inspect from the smaller set of mechanisms it must actually reconstruct.

### 2026-07-28 - A clean focused gate prevented an uninformative full rerun

- Froze the v14 implementation in commit `8becb21` before spending on evaluation. The unchanged
  G006/G007 runner required that exact clean commit, the same owner test-set and practical-rubric
  hashes, the same 481 embedded passages, an isolated empty cost ledger, eight final sources, and
  zero automatic retries.
- Both questions completed exactly once. The run made two planning calls, two batched-embedding
  calls, and two answer-generation calls, consuming 32,784 priced tokens for an estimated
  `$0.40612293`. There were no unpriced calls or retries.
- The application mechanics passed: both responses were visible direct answers, all protected
  stage anchors survived to the final context, both structured outputs validated, and all 33
  citation tokens were well formed and resolved to one of eight returned sources.
- The answer-quality gate did not pass. Under the same strict composite-claim grading, G006 scored
  0/8 claims and 4/8 target document groups; G007 scored 1/7 claims and 4/5 groups. The required
  thresholds were 2/8 plus 5/8 for G006 and 2/7 plus 5/5 for G007.
- Consensus selection changed the omissions rather than widening the historical span. G006 reached
  Chapter 20 but lost another needed modern institution; G007 recovered the Civil War group but
  lost the Jamestown origin. A stage anchor could have two- or three-pool agreement and still be
  highly relevant to an imprecisely framed subproblem rather than the role that the complete answer
  needed it to play.
- Separating inspection from synthesis cut forced citation output from the v13 pair's 58 citation
  tokens to 33 and reduced estimated cost by 18.2 percent. That was a useful efficiency result, but
  it did not make the connective argument explicit. G006 still read as a chronology of examples
  rather than an institutional lineage.
- Total question latency rose from 172.324 seconds in the comparable v13 pair to 196.971 seconds,
  driven by a 125.252-second G007 generation. Lower output and lower cost therefore did not imply a
  faster response in this single nondeterministic sample.
- Held the full ten-question evaluation instead of spending on eight more questions after the
  predeclared broad-question gate failed. The next bounded repair is narrower: constrain anchor
  relevance with the intended historical role, then require causal or institutional links between
  the surviving stages without adding a critic call, retry, larger context, or gold-answer hints.

Useful blog lesson: agreement among retrieval methods is evidence of ranking confidence, not proof
that the stage itself was framed correctly. A small paid gate can save both money and interpretive
confusion when a technically valid answer still misses the argument the reader asked for.

### 2026-07-28 - V15 turned historical role and connective argument into contracts

- Implemented `evidence-planned-v15`, `faceted-hybrid-rrf-v9`, and
  `broad-stage-role-eligibility-v2` after the v14 focused gate showed that agreement among retrieval
  routes could still select the wrong kind of passage for a stage.
- Every protected broad-stage candidate now has to match both the stage's distinctive planned
  intent and a general historical signal appropriate to its role before canonical, mechanism, and
  provider consensus can rank it. Three-route agreement no longer excuses a role mismatch.
- Removed the silent ineligible fallback. If no passage qualifies, the trace reports a genuine
  stage shortfall and generation receives no protected obligation for that stage. Supplemental
  passages may still be inspected, but they cannot masquerade as the missing argumentative anchor.
- Added a required `adjacent_stage_link` obligation for each surviving consecutive pair. It asks
  for one explicit causal or institutional connection, maps to both ordered stage requirements,
  and can cite only the later anchor that directly states the relationship. Merely placing two
  accurate historical facts next to each other is now insufficient.
- When that relationship is absent from the later source, the link remains unsupported and both
  affected requirements are downgraded from complete support. This makes gaps in the manuscript
  evidence visible instead of encouraging invented connective tissue.
- Kept the manuscript, private index, pinned model settings, eight-source limit, one batched
  embedding operation, one generation operation, and no-retry policy unchanged. The repair added
  no critic, verifier, or second answer call.
- Versioned the affected contracts as retrieval trace 8, answer request 4, evidence coverage 4,
  coverage prompt 7, and evidence diagnostics 6. Text-free traces expose only hashes, counts,
  finite eligibility codes, and IDs.
- The focused regression set passed 200 tests. The complete offline suite then passed 483 tests
  with one intentional skip, and Ruff passed on every changed Python and test file. No OpenAI call
  was made; answer-quality improvement remains a measurement question for a separately authorized
  focused gate.

Useful blog lesson: retrieval confidence and historical function are different properties, and a
chronology becomes an argument only when the evidence itself supports the links between its stages.
Encoding both distinctions as fail-closed contracts gives the model less room to sound complete
when the source chain is not.

### 2026-07-29 - The v15 gate distinguished honest gaps from useful synthesis

- Committed the role-aware broad-synthesis repair as `5b37e72`, then ran the unchanged G006/G007
  focused gate from that exact clean commit. The owner question file, practical rubric, corpus,
  private index, GPT-5.6 Sol settings, neutral interpretation, eight-source limit, and no-retry
  policy all matched v14.
- Both questions completed exactly once. Two planning calls, two batched-embedding calls, and two
  answer-generation calls consumed 39,224 priced tokens for an estimated `$0.54793856`, below the
  `$0.65` operational ceiling. G006 took 107.072 seconds and G007 116.683 seconds.
- The application mechanics passed. Both structured responses validated, all eight sources were
  retained per answer, and all 39 citation tokens were well formed and resolved. There were no
  unpriced operations, API errors, or retries.
- The answer-quality gate failed. Under the unchanged strict composite rubric, G006 scored 1/8
  claims and 3/8 target document groups; G007 scored 0/7 claims and 4/5 groups. The required
  thresholds remain 2/8 plus 5/8 for G006 and 2/7 plus 5/5 for G007.
- Compared with v14, the pair stayed at one strict claim in aggregate and fell from eight to seven
  covered target groups. Cost rose 34.9 percent, citation tokens rose from 33 to 39, and combined
  latency rose 13.6 percent in this single directional sample.
- The link contract did something important even though the answers remained incomplete. G006
  supported only one of three adjacent-stage links and G007 one of four; every other link was
  recorded as `no_direct_support`, and the affected requirements were downgraded rather than
  supplied with invented connective tissue.
- The remaining retrieval defect is now sharper. General role vocabulary can identify a plausible
  origin, transition, mechanism, or endpoint without identifying the specific institution, event,
  actor, or mechanism required by that stage. G007 satisfied all five canonical stages but again
  missed its Jamestown origin; G006 reported one stage shortfall and reached only three of eight
  frozen target groups.
- Held the full ten-question rerun. The next bounded experiment should make distinctive
  requirement content a hard eligibility condition before role and consensus scoring, then retrieve
  transition evidence through an adjacent-pair lane instead of assuming that the later anchor
  contains the relationship. It should keep the same one batched embedding, eight-source limit,
  one generation, and no-retry architecture.

Useful blog lesson: fail-closed behavior can be a real engineering success without being a product
quality success. V15 stopped the model from inventing historical connections, but the test exposed
that trustworthy incompleteness and a useful answer are separate milestones.

### 2026-07-29 - The complete ten-question run replaced a narrow gate with a product profile

- Ran the owner's unchanged ten-question cohort once from clean commit `ad3017d`, using the same
  frozen question and rubric hashes, private manuscript/index identity, neutral interpretation,
  GPT-5.6 Sol settings, eight-source ceiling, and no-retry policy as the earlier comparison.
- All ten questions completed exactly once. Eight planning calls, ten batched-embedding calls, and
  nine answer-generation calls consumed 106,703 priced tokens for an estimated `$1.11784972`.
  The clean absence case skipped generation. There were no API errors, retries, or unpriced events.
- The product-level mechanics were reliable: every eligible plan succeeded, all nine generated
  answers validated, all 85 citations resolved to returned sources, and all ten high-level
  behaviors passed, including abstention, bounded near-match handling, and premise correction.
- Strict completeness remained poor. The cohort realized 18 of 58 essential claims, covered 21 of
  26 target document groups, triggered four of 25 listed failure modes, and contradicted no frozen
  claim. The clean v13 sample had realized 19 claims with the same 21 target groups.
- Cost fell 9.0 percent and generation tokens fell 2.5 percent relative to v13, but total latency
  rose 8.0 percent. A single model sample is directional, so these shifts are not a noise study.
- The full run revealed what the G006/G007 gate could not. The application is mechanically sound
  across question types, while answer completeness is weak in both broad synthesis and some
  focused questions. G002 and G005 reached their expected document groups but realized zero and
  one strict composite claims, so another broad-retrieval-only repair would be too narrow.
- Across the two broad questions, v13 and this full v15 run both produced two of fifteen strict
  claims and covered eight of thirteen target groups. V15 redistributed which stages appeared
  rather than improving the combined historical argument.
- The next repair should preserve requirement-specific broad anchors and add a dedicated
  adjacent-pair transition lane, while also carrying the material components of focused
  relationships into the completeness ledger. A small smoke may verify mechanics, but it should
  not become another reason to postpone the next unchanged ten-question measurement.

Useful blog lesson: a narrow gate is useful for diagnosing one subsystem, but only the complete
evaluation shows whether the product is becoming more useful. Reliable citations and graceful
failure can improve while substantive answer coverage stays flat.

### 2026-07-29 - V16 made focused completeness and historical transitions source-visible

- Implemented the repair identified by the complete v15 evaluation rather than running another
  narrow paid gate. The new cohort is `evidence-planned-v16` with
  `faceted-hybrid-rrf-v10`, planner prompt v7, coverage prompt v8, answer request 5, and retrieval
  trace 9.
- Added a deterministic material-component pass for focused questions. When already admitted
  passages visibly contain at least two distinct layers--identity/definition, action/mechanism,
  significance/consequence, or qualification/counterargument--those layers become required,
  source-bounded coverage obligations. This directly targets the v15 cases that found the expected
  document groups but produced thin answers.
- Kept the trigger conservative. A lone detected layer does not expand a simple answer, and the
  pass does not run on broad, premise-sensitive, or absence-sensitive routes. It uses no gold
  answers and asserts no facts of its own.
- Tightened broad-stage eligibility so a protected anchor must match the stage's distinctive
  institution, actor, event, or mechanism. Generic topical relevance plus role vocabulary is no
  longer enough; missing distinctive content remains an explicit shortfall.
- Added a dedicated retrieval lane for each adjacent stage pair. One passage must match both stage
  intents and state an explicit causal, institutional, continuity, replacement, or transformation
  link before it can be selected as transition evidence.
- Batched the transition queries with the existing facet and canonical queries, preserving one
  embedding operation. Transition passages compete globally only for context capacity remaining
  after protected stage anchors, verification lanes, and the narrative endpoint, so the public
  eight-source ceiling remains unchanged.
- Rebound `adjacent_stage_link` obligations to the selected transition passage itself. The later
  stage anchor is no longer assumed to contain the connection merely because it follows the prior
  stage chronologically.
- Preserved one answer-generation call, zero automatic retries, the private manuscript/index
  boundary, and the existing cost-accounting path. This implementation verification made no
  OpenAI calls and incurred no API cost.
- Added synthetic regressions for component activation, single-layer nonactivation, component-role
  validation, two-stage transition eligibility, transition shortfalls, trace privacy, and
  post-gate transition source mapping. The full offline suite passed 489 tests with one intentional
  skip; Ruff passed across all source and test files.
- This is an engineering repair, not yet a quality claim. The next paid measurement should be the
  unchanged ten-question gold evaluation under a fresh v16 cohort, rather than another two-question
  detour.

Useful blog lesson: completeness can be made more concrete without asking a second model to judge
the answer. The application can identify visible layers and connective passages in the evidence,
then require the single generation call either to use them honestly or disclose the gap.

### 2026-07-29 - The full v16 evaluation found a narrow gain and a real regression

- Ran the owner's unchanged ten-question, 58-claim evaluation from clean commit `4586135`, with
  the same private corpus and index, neutral settings, eight-source ceiling, frozen rubric, and
  no-retry policy used for the v15 comparison. All ten questions ran exactly once.
- The isolated run cost an estimated `$1.28785761` across 27 priced operations and 116,367 tokens.
  It produced zero API errors, retries, or unpriced events.
- Strict coverage moved only from 18/58 claims in v15 to 19/58 in v16. Target-document coverage
  stayed at 21/26. Nine of ten expected high-level behaviors passed, down from ten of ten, while
  all 71 rendered citation tokens remained syntactically valid and resolvable.
- The focused component obligations helped narrowly: G001 and G002 each gained one strict claim,
  and G003 expressed one additional mechanism. G005 still realized only one of seven claims
  despite validating four source-visible component obligations. Generic completeness dimensions
  do not guarantee the particular composite relationship or counterargument a reader needs.
- The broad lineage question regressed from two strict claims to none. Its live plan represented
  only five stages of a longer book-spanning arc, so successful five-of-five stage and four-of-four
  transition counters overstated completeness relative to the user's actual question.
- G007 retrieved all five expected source groups but returned no usable answer after generation.
  Inspection found a deterministic integration defect: the new obligation builder correctly bound
  an adjacent-stage link to a dedicated transition passage, while the older validator still
  required that link to cite the later stage's anchor. The mismatch was locally knowable before
  the paid generation call but was checked only afterward.
- V16 therefore did not clear the overall product-quality bar. Its focused component work is worth
  preserving, but the one-claim gain came with one failed behavior, 15.2 percent higher estimated
  cost, and 19.7 percent higher total latency in this single directional sample.
- The next bounded repair is to align transition-source validation and run the complete trusted
  context check before generation, then add an explicit stage-cardinality and historical-role
  contract for longitudinal questions. After offline verification, return directly to the full
  unchanged ten-question evaluation rather than postponing it behind repeated narrow paid gates.

Useful blog lesson: internal green counters prove only that the system satisfied the plan it
created. If the plan compresses an eight-part historical arc into five stages, five-of-five can
still be substantively incomplete. Evaluation has to measure the reader's question, not merely
the pipeline's self-description.

### 2026-07-29 - V17 repaired the transition contract before another paid run

- Opened the `evidence-planned-v17` cohort to repair the deterministic G007 failure found by the
  full v16 evaluation. Retrieval, prompts, models, the eight-source ceiling, and the manuscript
  index remain unchanged.
- Removed the obsolete assumption that an adjacent-stage link must cite the successor stage's
  anchor. A link may now cite its selected dedicated transition passage while the validator still
  requires consecutive requirements, one surviving stage scope at each endpoint, the correct
  predecessor anchor, and source numbers inside the final context.
- Made trusted coverage-context validation a public, shared contract used both before generation
  and during final answer validation. Invalid local context now returns a fail-closed diagnostic
  with `structured_generation_called=false` instead of spending on an answer that local code was
  already certain to discard.
- Added a true integration fixture with separate predecessor-anchor, successor-anchor, and
  transition passages. It validates and reaches exactly one synthetic answer-generation call.
  A paired stage-shortfall fixture removes the successor scope and proves that generation is never
  invoked; its emitted retrieval trace also passes the text-free trace contract.
- Added unit coverage showing that the dedicated third passage is valid, a missing endpoint stage
  is invalid, and the predecessor source must still match the protected predecessor anchor.
- The full offline suite passed 494 tests with one intentional skip, and Ruff passed across all
  source and test files. No OpenAI calls were made and no API cost was incurred.
- This repair restores contract consistency; it does not claim better gold-set completeness. The
  remaining measured problem is broad stage planning: a five-stage plan can still underrepresent
  a longer institutional lineage. That stage-cardinality and historical-role contract is the next
  bounded repair before returning to the unchanged ten-question evaluation.

Useful blog lesson: fail-closed validation is only economical when it runs at the earliest point
where failure is knowable. The same strict check that protects readers after generation can also
protect the budget before generation, provided both paths share one contract.

### 2026-07-29 - V18 made long institutional-lineage plans match the question's span

- Opened the `evidence-planned-v18` cohort to repair the false-green completeness signal exposed
  by G006. The accepted v16 plan represented a book-spanning institutional lineage with only five
  stages, so five satisfied anchors and four satisfied transitions described the undersized plan
  rather than the reader's eight-part historical question.
- Added an application-owned `long_institutional_lineage` route trait. It activates only for
  explicitly institutional lineage, succession, or transformation questions that already qualify
  as broad synthesis; ordinary broad questions retain the established five-stage contract.
- Long-lineage plans now require exactly eight chronologically ordered stage requirements and
  eight corresponding search facets, in addition to the original-question facet. Each stage must
  name a distinct historical bearer, mechanism, or institutional role rather than repeating a
  generic theme under different dates.
- When the document catalog is available, every lineage stage must carry an exact document hint
  and the primary hints must advance through the corpus. This constrains each anchor to the
  historical role intended for that stage rather than allowing a generally relevant passage from
  another period to satisfy it.
- Kept the public final-source ceiling at eight. Stage anchors therefore receive the full capacity
  for an eight-stage lineage. The adjacent-stage transition lane first reuses already selected
  stage passages; it may add another passage only when capacity remains.
- Made the capacity tradeoff visible in the text-free retrieval trace: required, planned, and
  available stage counts; stage shortfall; spare transition capacity; transitions satisfied by
  reuse versus a new source; and capacity, candidate, or selection shortfalls are recorded
  separately. A transition can no longer disappear behind a single generic shortfall count.
- Versioned the planner and provider contracts for the expanded maximum: question-plan schema 2,
  planner schema 2, planner prompt v8, retrieval v11, retrieval trace 10, broad role execution v4,
  and transition lane v2.
- Added synthetic regressions for route precision, exact eight-stage cardinality, distinct stage
  roles, advancing document hints, ordinary five-stage preservation, all-eight-anchor retrieval,
  reuse-first transitions, explicit capacity shortfalls, trace privacy, and end-to-end retention
  of all eight roles through answer generation.
- The complete offline suite passed 500 tests with one intentional skip, and Ruff passed across
  all source and test files. No OpenAI calls were made and no API cost was incurred.
- This is a contract and observability repair, not yet a quality claim. The next measurement should
  be the unchanged ten-question gold evaluation under the fresh v18 cohort.

Useful blog lesson: a retrieval system can report perfect coverage of the wrong abstraction. The
plan's cardinality and historical roles have to match the reader's requested arc before downstream
coverage counters mean anything.

### 2026-07-29 - A whimsical interlude expanded the shared visual language

- Added three presentation-only vibes to Archivist and its parent portfolio, Cromblog: **Pretty
  Pink Princess**, **Baleful Black Baron**, and **Rose & Ruin**.
- Pretty Pink Princess uses blush parchment, pearl light, rose glass, soft courtly geometry, and
  restrained crown ornament. Baleful Black Baron uses near-black iron, oxblood, tarnished metal,
  sharper corners, and gothic heraldic forms. Rose & Ruin deliberately reconciles the two through
  black plum, dusty rose, champagne gold, and a more controlled courtly silhouette.
- The two applications retain their own materials while speaking the same visual language.
  Archivist applies each palette to the cover treatment, conversation chrome, user messages,
  controls, source panels, and archival answer paper. Cromblog carries the same identity through
  its sidebar, masthead seal, navigation, home hero, project and post cards, long-form article
  surfaces, and Archivist feature card.
- No new image assets were added. Cromblog reuses three existing art-directed hero images under
  theme-specific filters and overlays, keeping the interlude code-native and avoiding unnecessary
  disk growth.
- The Archivist appearance menu now safely scrolls when all ten vibes do not fit in a short
  viewport. Both registries contain the same ten choices, and the existing persistence and cycling
  mechanisms discover the additions from those registries without a second implementation.
- Both production frontend builds passed. Key foreground, muted, user-message, and answer-paper
  color pairs for all three themes measured above the 4.5:1 normal-text contrast target; the
  weakest checked pair was 5.05:1.
- Automated screenshot inspection was unavailable in this development session, so a final human
  visual pass across desktop and mobile remains appropriate before publishing the styles.
- This work changes presentation only. It does not alter retrieval, prompts, model context,
  citations, evaluation contracts, or the pending unchanged v18 gold-set run.

Useful blog lesson: a serious evidence system does not have to present itself with only one mood.
Keeping theme selection entirely on the presentation side makes room for play without allowing
the ornament to change the answer.

### 2026-07-29 - V18 restored reliability but not answer completeness

- Froze V18 at clean commit `97ca2bc` and ran the owner's unchanged ten-question, 58-claim
  evaluation exactly once. The questions, practical rubric, manuscript/index identity, neutral
  interpretation, GPT-5.6 Sol runtime model, eight-source ceiling, and zero-retry rule were
  unchanged.
- All ten items completed for an estimated `$1.32257351`. Eight planner-eligible questions
  accepted live plans, all nine generated answers validated, and the remaining item cleanly
  abstained before generation. V17 therefore repaired the paid-but-discarded transition failure
  that had reduced V16's high-level behavior result to 9/10.
- Strict completeness remained **19/58 claims**, while final-context target coverage improved
  from 21/26 to **22/26**. All 97 citation tokens were well formed and resolved to returned
  sources, but that mechanical result is not a faithfulness score.
- G006 demonstrated why a larger plan can still represent the wrong abstraction. Its planner
  supplied all eight required stages, retrieval satisfied seven anchors and six transitions, and
  the trace honestly reported the shortfalls. The chain still described a generic chronology of
  regimes and economic eras rather than the requested institutional succession; it covered only
  four of eight target groups and realized none of the strict claims.
- G007 demonstrated the second half of the problem. Its context contained all five target groups,
  its five stage anchors and four transition searches survived, and the answer was valid. It
  still realized none of the seven strict claims because passages that broadened context were not
  necessarily bound to the obligations that organized the prose.
- The new result narrows the next repair. Another increase in stages or sources is not justified.
  Long-lineage stages need explicit institutional bearers, inherited capacities, transfer
  mechanisms, and outgoing capacities; adjacent stages need a shared handoff, and supported
  handoffs must be realized in the answer.
- Total latency increased from 589.539 seconds in V16 to 750.837 seconds in V18, while estimated
  cost rose only 2.7 percent. The extra observability and reliability are useful, but the absence
  of a strict-claim gain means V18 is not an overall quality improvement.
- The private run directory contains the isolated usage ledger, full answers and passages,
  text-free traces, exact-span manual grading, and assessment. Those artifacts remain gitignored
  because they contain commercial manuscript text.

Useful blog lesson: a RAG pipeline can become more internally correct without becoming more
useful. V18 replaced a false green light with an honest instrument panel. The next challenge is
making the plan describe the reader's causal object rather than merely a tidy sequence through
time.

### 2026-07-29 - V19 turned a chronology into an explicit institutional handoff

- Implemented the bounded repair suggested by V18's G006 failure. An eight-stage plan is no
  longer sufficient merely because its topics advance through time and use different historical
  vocabulary.
- Every long-lineage stage now declares a distinct institutional bearer, the concrete capacity it
  inherits, the mechanism that transfers or transforms that capacity, and the capacity it passes
  onward. Each outgoing capacity must become the next stage's inherited capacity, and explicit
  "from X to Y" questions bind the first and last bearers to those endpoints.
- Tightened protected-stage retrieval. A passage must match the intended bearer and a concrete
  handoff function in addition to the existing distinctive-stage and historical-role checks.
- Tightened adjacent-stage retrieval. A transition passage must connect terms distinctive to both
  bearers, match their shared carried capacity, and state an explicit transition signal. Merely
  mentioning a topic common to both periods is no longer enough.
- Replaced generic long-lineage stage-development obligations with explicit
  `institutional_handoff` obligations. The planner's proposed bearer and capacity fields are sent
  to generation only as search orientation, clearly marked as non-evidence. The answer must verify
  all four fields against the one scoped manuscript passage or report that the handoff is only
  partial, unsupported, or conflicting.
- Preserved the user-visible constraints: eight final manuscript passages, one planner call, one
  answer call, no automatic retry, no critic model, and no manuscript-specific or gold-set hints
  in production code.
- Versioned the new cohort as `evidence-planned-v19`, planner prompt v9, coverage prompt v9,
  faceted retrieval v12, answer request 6, and retrieval trace 11.
- Added corpus-agnostic regressions for missing or discontinuous handoffs, duplicate bearers,
  endpoint mismatch, misuse on a non-lineage route, source-role qualification, and shared-capacity
  transition evidence. The full offline suite passed 505 tests with one intentional skip; Ruff
  and the diff integrity check passed. No OpenAI calls were made.
- This is not yet a quality claim. The next paid checkpoint should run the unchanged G006 and
  G007 questions once with no retries. G006 tests the new contract; G007 protects the ordinary
  broad route. V19 deliberately does not claim to fix G007's separate problem of retrieved broad
  evidence remaining unused in the answer. If that checkpoint is directionally sound, return to
  the complete unchanged ten-question evaluation rather than adding more narrow detours.

Useful blog lesson: an elegant context window is not just a pile of relevant passages. It is an
argument-shaped contract: who carries a capability, how it changes hands, which source supports
each link, and which planning suggestions must remain outside the evidence boundary.

### 2026-07-29 - V19's handoff contract made weak links visible but did not find the right lineage

- Froze V19 at clean commit `3c39310` and ran the owner's unchanged G006/G007 pair once with no
  model or API retries. The questions, 15-claim rubric subset, manuscript and index, neutral
  settings, GPT-5.6 Sol model, and eight-source ceiling were unchanged.
- The pair used two planner calls, two batched embeddings, and two answer generations: 39,929
  priced tokens and an estimated **`$0.47055541`**, below the authorized `$0.75` ceiling. Combined
  latency was 366.293 seconds.
- The answer-quality gate failed. G006 realized 0/8 strict claims, covered 3/8 target groups, and
  discarded its generated answer on `status_unit_mismatch`. G007 returned a valid answer with 15
  resolvable citations but realized 0/7 strict claims and covered 4/5 target groups. The
  predeclared thresholds were 2/8 plus 5/8 for G006 and 2/7 plus 5/5 for G007.
- V19's stricter transition rule was honest: only two of seven G006 handoffs survived instead of
  allowing generic chronological overlap to masquerade as institutional continuity. But the
  planner still chose an evenly advancing series of chapters rather than chapters performing the
  required corporate, fiscal, regulatory, procurement, and modern endpoint roles. A better-shaped
  request did not by itself give the planner grounded knowledge of each document's historical
  function.
- G006 exposed a separate local reliability defect. The provider assigned a non-unsupported
  status without the corresponding unit/source mapping. The normalizer did not safely downgrade
  the empty record, so strict validation rejected the entire paid answer rather than preserving
  only the supported units.
- G007 protected the ordinary broad route and showed a regression: it began too late, losing the
  early colonial origin that V18 had retrieved. Its four surviving historical regions still did
  not become the required causal argument.
- Both text-free traces passed the closed trace validator. The private grading and assessment
  preserve the exact frozen identities, source-group counts, usage, latency, and the evaluation
  harness interruption without committing manuscript text.
- The first foreground wrapper stopped waiting while G006 continued. G006 completed exactly once
  and wrote its artifacts, then could not print to the closed stdout pipe; G007 had not begun.
  G006 was not rerun. A G007-only continuation asserted the same commit and frozen hashes, used
  only the remaining authorization, and redirected output to files. The combined sample therefore
  remains exactly one call sequence per question.
- Held a full ten-question V19 rerun because this cohort is already known to lose one reader
  answer and two target groups relative to the unchanged V18 pair. The next offline repair is
  limited to honest empty-mapping normalization, corpus-derived document-role grounding, and an
  earliest-stage breadth guardrail for the ordinary broad route. If the unchanged pair then
  clears its gate, proceed directly to all ten questions.

Useful blog lesson: a stricter context contract can turn false confidence into a useful failure.
V19 did not improve the answer, but it separated three different problems that had looked like
one: choosing the wrong historical roles, proving too few real handoffs, and discarding an answer
because its support ledger was malformed.

### 2026-07-29 - V20 gave the planner a passage-free map of historical roles

- Clarified the distinction between the owner's current ten-question practical rubric and the
  formal gold artifacts. The empty `gold_set.pilot.template.json` is intentionally empty: the
  owner must supply the questions, essential claim paraphrases, exact per-claim supporting chunk
  IDs, complete per-question relevant chunk IDs, plausible forbidden claims, and answer-versus-
  abstain behavior before seeing a model answer. The formal pilot is exactly ten items and remains
  calibration-only; the eventual stable run-of-record gold set is 34-46 items across six locked
  strata. Automatically filling either from Archivist's output would make the benchmark circular.
- Opened the `evidence-planned-v20` cohort around the three failure shapes isolated by V19. The
  manuscript, embeddings, vector index, retrieval parameters, eight-source ceiling, generator,
  coverage prompt, and zero-retry boundary remain unchanged.
- Made empty provider bookkeeping failures survivable without loosening grounding. If a supported
  or partial status has no unit, no source, and no trusted ledger link, the normalizer now
  downgrades only that record to unsupported. A nonempty contradictory mapping still fails closed,
  and the repair never manufactures or relocates evidence.
- Built a bounded role profile for each eligible document from local corpus statistics. Each
  profile contains at most 48 normalized tokens balanced across title terms, acronyms, named
  actors and institutions, institutional mechanisms, periods, and general salience. No passage,
  sentence, paragraph, chunk ID, gold claim, target group, or expected answer enters the profile.
- The planner may use that token map to choose document hints, but cannot use it as evidence. Local
  validation rejects a broad stage whose primary document does not contain the proposed role.
  For causal "X as an engine of Y" questions, it also rejects an origin placed after the earliest
  narrative documents containing X. Both rules are corpus-agnostic.
- Balanced selection mattered. A first pure top-term profile could omit rare acronyms or decisive
  one-off institutions while preserving many generic high-frequency words. Reserving bounded
  representation for acronyms, names, mechanisms, and periods produced a more useful map without
  sending passages or allowing the planner input to grow without limit.
- Versioned the policy as V20, planner prompt v10, normalizer v7, retrieval trace 12, and document
  role profile v1. The complete offline suite passed 510 tests with one intentional skip; Ruff
  passed on every changed source and test file. No OpenAI call or API cost was incurred.
- This is not yet evidence that G006 or G007 improved. The token map increases planner input, so
  the next unchanged, zero-retry pair must measure latency, cost, strict claims, target groups, and
  whether a reader receives an answer. It requires a fresh explicit spending ceiling before it
  runs. The public V13 deployment remains untouched until V20 clears measurement.

Useful blog lesson: the planner did not need more manuscript prose; it needed a small index of
what kinds of historical work each document performs. That resembles crafting an elegant context
window at a second level: first orient the model with a compact map, then reserve the scarce source
slots for passages that can actually support the answer.

### 2026-07-29 - V20 fixed the lost answer and improved the lineage, but its fallback lost the war question

- Froze V20 at clean commit `f13534a` and ran the owner's unchanged G006/G007 pair once with no
  model or API retries. The 15-claim rubric subset, manuscript and index hashes, neutral settings,
  GPT-5.6 Sol model, and eight-source ceiling were unchanged. Persistent redirected logs ensured
  that a long first response could not be mistaken for a failed run and accidentally repeated.
- The pair used two planner calls, two batched embeddings, and two answer generations: 53,277
  priced tokens and an estimated **`$0.53731947`**, below the authorized `$0.90` ceiling. G006
  took 108.555 seconds, G007 took 65.173 seconds, and combined item latency was 173.728 seconds.
- V20 materially improved G006. It returned a valid reader answer, rose from 0/8 to **3/8 strict
  claims**, and covered **6/8 target document groups** rather than V19's 3/8. The answer captured
  the chartered-company blueprint, the Company-to-Crown transfer, and Ashburn's physical cloud
  endpoint. It still read more like a sequence than a proven institutional succession and omitted
  several middle and late mechanisms.
- The text-free G006 trace explains the gain. The accepted plan contained all eight required
  stages, filled all eight canonical stage slots, and supported four of seven adjacent
  transitions—twice V19's two. The bounded document-role map improved orientation without sending
  more manuscript prose to the planner.
- V20 also resolved V19's operational failure: both generated coverage objects validated and both
  answers reached the reader. The paid sample did not exercise the new empty-mapping downgrade,
  because the provider did not repeat that malformed output; its deterministic offline tests
  remain the evidence for that branch.
- The complete pair gate nevertheless failed on G007. The origin validator correctly rejected
  the live plan as `broad_origin_not_preserved`, but the zero-retry generic fallback then discarded
  the structured broad plan, satisfied only one of five canonical stages, and covered **3/5**
  frozen target groups. Its valid answer earned **0/7 strict composite claims**. Detecting a bad
  origin was correct; replacing the whole plan with a weaker fallback was not.
- Aggregate quality rose from V19's 0/15 claims, 7/13 groups, and one valid reader answer to
  **3/15 claims, 9/13 groups, and two valid reader answers**. Estimated cost rose 14.2 percent
  because the bounded role catalog enlarged planner input, while combined latency fell 52.6
  percent in this one directional sample.
- Held the complete ten-question rerun because the predeclared G007 threshold remains 2/7 claims
  and 5/5 groups. The next repair is narrow: preserve a broad plan that fails only the origin guard,
  replace or insert the locally eligible early origin, and revalidate it. If salvage cannot pass,
  the deterministic fallback must itself satisfy the broad stage and origin contracts rather than
  silently collapsing to one canonical stage.

Useful blog lesson: validation is only as good as the path it activates. V20 learned to recognize
that a proposed history began too late, but then threw away the useful remainder of the plan.
An elegant context window needs a graceful repair path as well as a strict gate.

### 2026-07-29 - Turned the drafted resume claims into an evidence plan

- Audited the draft resume language against the repository rather than filling its blanks from
  development anecdotes. The full-manuscript hybrid RAG and Render deployment are real, but the
  repository does not yet contain a formal vector-only versus hybrid retrieval benchmark or a
  current production latency cohort that supports the proposed numbers.
- Classified the repeatedly used ten-question practical set as development/calibration evidence.
  It remains the near-term V20 regression gate, but it cannot honestly serve as a held-out proof of
  improvement after guiding multiple repairs.
- Added a roadmap sequence that first stabilizes and deploys one candidate, then freezes the
  owner's untouched 34–46 question gold set, runs a retrieval-only paired comparison, publishes
  text-free reproducibility artifacts, and measures production behavior on that same candidate.
- Kept the formal metric contract honest. It currently defines Recall@k and context recall, not
  Precision@k. Precision can be added only before results and only if the owner supplies exhaustive
  relevance judgments; otherwise the resume should report Recall@5/context recall.
- Specified the missing observability bridge: persist privacy-safe success and failure correlation,
  HTTP outcome, total and per-stage duration, cohort/model, tokens, and cost; then report p50, p95,
  and error rate over 30–50 warm production-like first turns. Historical V11 latency and the
  two-item V20 diagnostic pair remain development observations, not production claims.
- Removed the stale roadmap statement that hybrid retrieval was deferred. Dense/BM25 reciprocal-
  rank fusion exists; what remains is the controlled vector-only comparison that can demonstrate
  whether it helped.

Useful blog lesson: a credible resume number is itself a small published research result. The
system, corpus, labels, comparator, denominator, and production cohort all need identities before a
percentage point or latency figure means anything.

### 2026-07-29 - V21 repairs one bad anchor without throwing away the map

- Opened `evidence-planned-v21` for the single defect exposed by V20's G007 result. V20 correctly
  recognized that the proposed history began too late, but then discarded all five useful
  structured stages and substituted a generic fallback.
- Shared the validator's corpus-derived early-origin calculation with a bounded local repair.
  When the only failure is `broad_origin_not_preserved`, the repair changes the unique origin
  facet's primary document hint, preserves the rejected hint as secondary when capacity permits,
  and leaves every requirement, query, premise, and later facet unchanged.
- Sent the repaired proposal through the complete validator again. An origin that cannot satisfy
  both the causal-origin and historical-role contracts still fails closed. The change adds no
  planner retry, critic call, source slot, manuscript-specific rule, gold location, or expected
  answer.
- Versioned the behavior as V21 while retaining planner prompt v10, coverage prompt v9,
  normalizer v7, retrieval trace 12, the eight-source ceiling, and the zero-retry boundary.
- Added synthetic plan and pipeline regressions proving one planner invocation, preservation of
  all five stages, isolation of the origin-hint change, and fail-closed behavior. The complete
  offline suite passed **511 tests with one intentional skip**, and Ruff passed. No API call or
  spend occurred.
- The code is ready to freeze as an exact release candidate, but offline success is not reader
  evidence. One unchanged no-retry G007 run must still reach the predeclared 2/7 strict claims and
  5/5 target groups before the unchanged ten-question development evaluation proceeds.

Useful blog lesson: strict validation should not erase good structure merely because one anchor is
wrong. A carefully engineered context window can repair the one faulty coordinate and then prove
the entire map still satisfies its contract.

### 2026-07-29 - Froze V21 and built a blind gold-authoring room

- Froze the offline-verified V21 system at exact commit
  `bf424c880bca4728a8d13225f85978e27a8d8dcf`. That hash is now the candidate identity carried by
  the held-out provenance template. It passed 511 tests with one intentional skip before the
  freeze; the paid G007 reader confirmation remains deliberately separate.
- Reclassified more than the familiar ten-question practical set as development data. The
  committed registry now includes all ten practical questions, all ten Brief 1 questions, both
  opening-screen suggestions, the recorded contextual smoke follow-up, and seven known manual
  queries—30 questions in all. Exact normalized reuse is a hard error; transparent token and
  sequence thresholds flag near matches for owner review.
- Added a private 40-slot workbook centered inside the six locked stratum ranges. It supplies IDs
  and blank fields only. It does not invent a question, answer, claim, essentiality decision,
  source location, relevance judgment, or false-claim trap; those remain the manuscript owner's
  work.
- Added an offline authoring workbench that lists text-free corpus metadata and reveals manuscript
  text only for chunk IDs the owner explicitly requests, after checking their frozen text and
  document hashes. It performs no semantic retrieval, ranking, embedding, or API call, so the
  candidate cannot help write its own exam.
- Bound the eventual gold file to the exact candidate, V21 policy, corpus manifest, development
  registry, timestamps, and four explicit owner attestations. A clean-tree lock rejects any
  system-under-test change after the candidate commit while permitting only enumerated evaluation
  artifacts and documentation.
- Implemented the missing re-ingest carry-over contract: unchanged eligible ID-plus-hash locations
  survive; changed, missing, or newly skipped locations quarantine the entire item. Also added a
  privacy audit that detects long exact token runs but emits only item, claim, and chunk IDs plus
  counts.
- Corrected the README and historical pilot ledger. The repeatedly used ten questions can still
  drive repairs, but can no longer be described or promoted as held-out evidence.
- The held-out machinery passed 61 focused tests and Ruff. It made no model, embedding, retrieval,
  or paid API call. The actual historical content is intentionally still blank because only the
  owner can make those judgments without circularity.

Useful blog lesson: building an evaluation set is less like asking an AI to write a quiz and more
like constructing a clean room. The interesting engineering is in proving what the candidate did
not see, what corpus the answers refer to, and that the measuring apparatus changed without the
measured system moving underneath it.

### 2026-07-29 - The frozen candidate failed usefully

- Ran the exact frozen V21 candidate
  `bf424c880bca4728a8d13225f85978e27a8d8dcf` once on the unchanged G007 question: “How does the
  book treat war as an engine of federal and central power?” The clean preflight rechecked the
  question, seven-claim rubric, corpus and chunk hashes, 481-passage index, eight-source limit,
  GPT-5.6 Sol settings, empty isolated ledger, and zero-retry rule.
- Launched the long request through a hidden file-backed process so the previous closed-stdout
  failure could not recur. It made exactly one planner call, one batched embedding call, and one
  generation call. The result took 104.985 seconds and cost an estimated **$0.29870543**, safely
  below the authorized `$0.40`; stderr stayed empty.
- The mechanics were healthy: a direct reader answer, valid local generation contract, closed
  text-free trace, eight sources, and 15 well-formed resolvable citation tokens. Strict content
  grading nevertheless reached only **1/7 claims and 3/5 target document groups**, below the
  predeclared 2/7 plus 5/5 gate. The ten-question development rerun therefore remains blocked.
- V21's narrow repair did not fail; it never ran. This time the provider produced a formally valid
  plan, so there was no `broad_origin_not_preserved` rejection to salvage. Retrieval then treated
  the Introduction's overview as the historical origin and skipped the Civil War group. An
  Epilogue passage was present in context but its required modern causal chain never appeared in
  the answer.
- Kept V21 frozen as a measured failed candidate rather than moving the goalposts after seeing the
  answer. The next work is again bounded and offline: exclude overview/front matter from origin
  anchors when body-chapter episodes exist, require the intended chronological stage cardinality,
  and preserve explicit unanswered obligations through generation. No extra retry, critic call,
  source slot, or gold-derived chapter rule is justified by this result.
- The held-out authoring room remains useful, but its final provenance must bind the next passing
  candidate rather than V21 before any held-out item is ingested or scored.

Useful blog lesson: freezing before testing makes a disappointing result valuable. Because the
question, corpus, rubric, code, cost boundary, and retry count could not move, the failure exposed
a new contract boundary instead of becoming another prompt-tuning anecdote.

### 2026-07-29 - V22 turned chronology into a protected contract

- Traced V21's miss to a subtle two-layer loophole. The planner validator approved the primary
  body-chapter origin but did not inspect its secondary Introduction hint. Retrieval then treated
  both hints as candidates and promoted the overview because it ranked well as a summary. The
  model had followed the literal contract; the contract had not expressed the intended history.
- Replaced the causal broad route's five generic stages with six structural obligations derived
  from corpus order: five non-overlapping bands across the numbered narrative body and one
  terminal Conclusion/Epilogue band. This is a reusable rule about book structure, not a hidden
  list of the chapters the G007 rubric wanted.
- Preserved overlap where it helps. Neighboring bands can still contribute discovery and
  transition evidence, but a protected stage anchor must come from its own exact core. All origin
  hints must be body documents, every stage stays inside its assigned span, and the endpoint is
  now the sixth protected anchor rather than an optional extra.
- Kept the budget shape intact. Six of the existing eight source positions are reserved for
  chronological anchors, leaving two for transitions. The request still uses one planner call,
  one batched embedding call, one generation call, and no retry or critic.
- Versioned the change as policy V22, planner prompt v11, broad execution v6, and faceted
  retrieval v13 without changing retrieval-trace schema 12. Ordinary noncausal broad questions
  remain five stages; long institutional-lineage questions remain eight.
- Added zero-call regressions for the exact failure modes: a secondary overview origin, a missing
  body band, a nonterminal endpoint, duplicate structural anchors, source-cap drift, and extra
  embedding calls. The focused set passed 204 tests; the complete offline suite passed 565 tests
  with one intentional skip, and repository-wide Ruff passed. A metadata-only private-corpus
  check produced five contiguous body spans followed by the Epilogue; no manuscript prose was
  added to code or fixtures.
- This is a repaired context-window contract, not yet proof of a better answer. V22 still needs an
  exact freeze and one unchanged no-retry G007 reader confirmation under the original
  2/7-claim plus 5/5-group gate. The practical ten-question run remains held until that gate
  passes.

Useful blog lesson: an elegant context window is not just a collection of relevant passages. It
is an allocation of scarce attention in which every narrative role has a protected seat, while
flexible overlap is reserved for discovering the connections between them.

### 2026-07-29 - V22 found the difference between a boundary and a guarantee

- Froze V22 at exact commit `0691b3da9a4926097c7d013d79266eee62f7de9b` after 565
  offline tests passed with one intentional skip and repository-wide Ruff passed.
- Ran the unchanged G007 reader confirmation once with no retry. It made one planner call, one
  batched embedding call, and one generation call, finishing in 95.735 seconds for an estimated
  `$0.25207406`. Its answer was valid, all 11 citations resolved, and its text-free trace passed.
- The score improved but missed the frozen gate: 1/7 strict claims and 4/5 target document groups,
  versus the required 2/7 and 5/5. V22 recovered the early body history that V21 had lost and
  retained the terminal Epilogue, but skipped the Civil War span.
- The trace showed why. The live planner proposal violated the new narrative-gap rule, so the
  deterministic six-stage fallback took over. That fallback declared six chronological stages,
  yet only one received a protected anchor. Five stages had candidates in the correct structural
  bands, but those candidates failed an older distinctive-intent threshold. The general ranking
  pass then filled all eight source slots, making the context look complete while five structural
  obligations were empty.
- The next repair is narrower than another planner or prompt change. In the deterministic causal
  fallback, the best available candidate from each exact structural core must be selected before
  optional relevance thresholds and transition evidence compete for the remaining slots. A truly
  empty core should produce an explicit failure instead of a cosmetically full context.
- The practical ten-question evaluation remains held. The frozen gate did its job again: it
  prevented a source count of eight, a valid answer, and a visibly broader result from being
  mistaken for the six-stage guarantee the code claimed to provide.

Useful blog lesson: restricting an anchor to the correct shelf is not the same as reserving it a
seat. A robust context window needs both boundaries and allocation guarantees—and diagnostics
that reveal when a later fill step makes a broken allocation look complete.

### 2026-07-29 - V23 gave every required stage a seat at the table

- V22 drew six chronological boxes, but it did not reserve six source positions. The paid trace
  showed that five boxes contained usable candidates whose generic fallback wording failed an
  older intent threshold. Global filling then occupied the context and made the broken allocation
  look complete.
- V23 turns each exact core in the deterministic six-stage fallback into an allocation
  obligation. The best available in-core candidate is selected before optional alternatives,
  transition evidence, or global supplementation compete for the remaining positions. The
  threshold still ranks optional evidence; it no longer gets to delete a required historical
  stage.
- Building the regression revealed a small but consequential parser bug. A regular-expression
  word boundary does not occur between `_` and `Chapter`, so real filenames such as
  `08_Chapter 1.md` could fail structural classification. Numbered and terminal documents now
  recognize the underscore-prefixed shape used by the corpus.
- A truly empty stage now stays visibly empty. Retrieval stops optional and neighbor filling, and
  the pipeline returns a text-free `structural_stage_shortfall` insufficiency before generation
  instead of producing a confident answer from a cosmetically full context.
- The repair adds no planner retry, critic, embedding request, generation request, source slot,
  manuscript-specific name, or gold-derived location. Strict provider-authored plans keep their
  existing role and intent checks; the relaxed allocation rule is limited to the deterministic
  structural fallback.
- Versioned the cohort as policy V23, broad execution v7, and faceted retrieval v14. Focused
  verification passed 207 tests; the complete offline suite passed 568 tests with one intentional
  skip, and repository-wide Ruff passed. No paid API call was made.
- Reader quality is deliberately still unclaimed. The next step is to freeze an exact V23 commit
  and repeat the same unchanged, no-retry G007 confirmation under the original 2/7-claim plus
  5/5-group gate. Only a pass unlocks the ten-question development evaluation.

Useful blog lesson: an elegant context window needs both a seating plan and an honest fire alarm.
Every required role needs a reserved place, and a missing role should stop the performance rather
than be hidden by filling the empty chair with unrelated evidence.

### 2026-07-29 - V23's fire alarm worked, and found the wrong fire

- Froze V23 at exact clean commit `d89f4332b21f0e41cb445780abe10f997b52626c` after 568
  offline tests passed with one intentional skip and repository-wide Ruff passed.
- Ran the unchanged G007 confirmation once with no retry. It made one planner call and one
  batched embedding call, finishing in 24.655 seconds for an estimated `$0.08430031`. The trace
  was closed, text-free, and valid.
- V23 failed closed before generation because it believed all six structural stages were empty.
  That behavior was safer than V22's globally filled but incomplete answer, but it still failed
  the reader gate: no answer, 0/7 claims, and 0/5 public target groups. The ten-question run
  remains held.
- The trace separated retrieval from classification. Candidate lanes contained numbered-chapter
  results, yet structural-band construction produced zero exact cores. The regression had tested
  a shortened filename such as `08_Chapter 1.md`; the real catalog shape continues with an
  underscore and title, such as `08_Chapter 1_ Sample title.md`.
- The parser accepted the underscore before `Chapter` but still required a regular-expression
  word boundary after the number. A digit and underscore are both word characters, so that
  boundary does not exist. A fixture meant to mirror production had reproduced only half of the
  filename grammar.
- The next repair is correspondingly small: recognize underscore, whitespace, punctuation, or
  end-of-string after numbered and terminal structural labels, test the complete filename shape,
  and assert that the catalog yields six nonempty bands. No prompt, ranking, source cap, or API
  call budget needs to move.

Useful blog lesson: failing closed is valuable even when the failure itself is mistaken. It
turned a hidden parser mismatch into a cheap, inspectable abstention—one planner and one embedding
call—rather than spending more to generate a persuasive answer from an invalid structure.

### 2026-07-29 - V24 tested the filename the application actually has

- Replaced the regex word boundary after `Chapter N`, `Epilogue`, and `Conclusion` with an
  explicit delimiter-or-end rule. Underscores, spaces, punctuation, and end-of-string now work;
  alphanumeric continuations still do not.
- Upgraded the six-stage tests from abbreviated filenames to the complete catalog shape, including
  ordinal prefix, structural label, trailing underscore, and synthetic title. Added direct
  negative cases for embedded labels and a catalog-level requirement that all six bands exist and
  are nonempty.
- Checked the private catalog metadata without manuscript prose. Its 20 numbered body documents
  now divide evenly into five bands of four, followed by one terminal document in the sixth band:
  4/4/4/4/4/1.
- Versioned the change as policy V24, broad execution v8, and faceted retrieval v15. The prompt,
  planner schema, eight-source ceiling, allocation rules, and call budget did not change.
- Focused verification passed 219 tests. The complete offline suite passed 580 tests with one
  intentional skip, and repository-wide Ruff passed. No API call was made.
- The parser contract is repaired offline, but reader quality remains unclaimed. The next
  evidence-producing action is still one unchanged G007 confirmation after an exact clean freeze;
  only the original 2/7-claim plus 5/5-group gate can unlock the ten-question development run.

Useful blog lesson: “production-shaped fixture” should mean the entire grammar, not merely the
part of a filename a developer happened to be thinking about. The cheapest live failure in this
sequence produced one of its clearest testing lessons.

### 2026-07-30 - The hardest question stopped hiding the other nine

- Revisited the repeated G007 promotion rule before spending on V24. G007 is the seventh question
  in the owner's unchanged practical set: how the book treats war as an engine of federal and
  central power. It is a valuable stress test for a long causal argument, but repeated use from
  V18 through V24 has made it development data rather than an unbiased release test.
- Corrected an evaluation-governance gap with the owner's authorization. The formal contract had
  never defined the notes' 2/7-claim plus 5/5-target threshold, even though that threshold had
  repeatedly prevented measurement of the complete ten-question cohort.
- Split the old gate into two concepts. G007 remains V24's first paid **mechanical sentinel**
  because it exercises the repaired filename parser, six structural bands, protected allocation,
  endpoint obligation, traces, mappings, call count, and no-retry boundary. Its claim and target
  scores remain visible results but can no longer veto the other nine development questions.
- Added the rule to `EVAL_CONTRACT.md`, the standing agent instructions, roadmap, defect log, and
  active optimization design. Historical notes retain the old decisions rather than pretending
  they were never made. No formal baseline was invalidated because the practical set was already
  classified as development evidence and no run of record exists.
- Added a text-free cross-run cost-lineage generator. It reads each ignored SQLite usage ledger in
  read-only mode, rejects duplicate provider response IDs, and reports candidate commit, status,
  items, retries, latency, authorized cap, calls, tokens, per-operation cost, and cumulative cost
  without reading any question, answer, source, or manuscript field into its output.
- The first reconstruction covered seven isolated V18–V23 run directories: 47 API operations,
  279,141 priced tokens, zero unpriced events, and **$2.965528190** estimated cumulative spend.
  V19's interrupted pair is represented by its original and continuation ledgers rather than a
  manually copied subtotal.
- Three focused cost-lineage tests passed. The complete offline suite then passed **583 tests with
  one intentional skip**, repository-wide Ruff passed, and the diff integrity check passed. No
  API request was made during this governance and tooling work.

Useful blog lesson: a difficult regression question is a microscope, not a courthouse. It can
prove that a repaired measurement path works and reveal a severe weakness, but letting it suppress
the rest of the experiment trades a broader diagnosis for increasingly elaborate attention to one
familiar failure.

### 2026-07-30 - V24 passed its mechanical sentinel, then the provider stopped the cohort

- Froze the governance-corrected V24 candidate at clean commit
  `67c735fff37d26288a2a887205b0a20682d9320d` and ran the unchanged G007 question once with no
  retry. It made one planner call, one batched embedding call, and one generation call; completed
  in 108.851 seconds; used eight sources; emitted 18 well-formed, resolvable citations; and cost an
  estimated `$0.31472406`.
- The predeclared mechanical sentinel passed. The trace required and satisfied all six canonical
  cores and all six protected stages, recorded no structural-stage shortfall, carried the terminal
  R6 endpoint into a supported generation obligation, and closed with a valid generation contract
  and source/citation mapping.
- The provider planner proposal failed local validation with `broad_narrative_gap`, after which
  the deterministic six-stage fallback completed correctly. This proves the repaired parser and
  fallback allocation path, but it does **not** resolve the separate V20/V21 concern about whether
  rejecting overview material can over-reject an otherwise valid live plan.
- Reader quality remained weak and is reported without acting as a veto: 1/7 strict claims and 4/5
  target document groups. The one credited claim was the Revolutionary-debt/Hamiltonian federal
  consolidation mechanism; the Civil War target group remained absent.
- In accordance with the corrected contract, immediately launched the complete unchanged
  ten-question development cohort. OpenAI rejected G001's first embedding request with
  `429 insufficient_quota`. The runner stopped in 2.940 seconds, made no automatic retry, recorded
  zero completed provider operations and `$0.000000000` for that cohort attempt, and preserved an
  explicit error artifact. This was an external account/project quota stop, not Archivist's
  `$3.00` operational cap and not a retrieval-quality result.
- Materialized the first committed, text-free V18-V24 cost lineage. Across nine isolated run
  attempts it records 50 completed API operations, 306,993 priced tokens, zero unpriced events,
  and **$3.280252250** estimated cumulative development spend. Failed attempts now retain their
  actual status, no-retry policy, and operational hard cap instead of being mislabeled as a
  partial run or displaying the broader owner authorization ceiling.
- The unchanged ten-question measurement remains the next action. Resume it in a new isolated run
  only after the OpenAI quota is available; do not treat the quota error as a failed question or
  tune V24 from it.
- Four focused cost-lineage tests passed. The complete offline suite passed **584 tests with one
  intentional skip**, repository-wide Ruff passed, and the diff integrity check passed.

Useful blog lesson: budget controls have two boundaries. The application's hard stop protects the
experiment from itself; the provider's quota can still stop the experiment from outside. Recording
both makes an interrupted cohort legible rather than mysterious.

### 2026-07-30 - The full V24 cohort separated finding evidence from using it

- Restored the provider quota and resumed without changing the RAG. Fresh isolated run
  `evidence-planned-v24-clean-20260730-2` asserted exact clean commit
  `1b75e8676319ad89f5b09bb851c5df5fad184c6c`, the unchanged ten questions and 58-claim practical
  rubric, the same corpus and index hashes, neutral settings, eight-source ceiling, zero retries,
  and a `$3.00` operational cap.
- All ten questions completed. The run made 28 API operations across eight planner calls, ten
  query embeddings, and ten answer generations; processed 187,228 priced tokens; took 589.577
  seconds of summed item latency; and cost an estimated **`$1.53158052`**. All ten traces closed,
  all outputs validated structurally, and all 72 citation tokens resolved.
- Strict manual grading found **21/58 essential claims, 23/26 target document groups, 4/25 listed
  failure modes, and 9/10 expected behaviors**. V18 had 19/58 claims, 22/26 groups, the same four
  listed failures, and 10/10 behaviors. The two-point claim gain and one-group gain are
  directional only; each cohort is one nondeterministic sample.
- The most important result is the mismatch between retrieval success and answer realization.
  G002 reached both target groups but ignored Appendix D's argumentative layer. G003 reached all
  three target chapter groups but expressed only one of seven strict claims. G006 reached six of
  eight target groups but expressed only two of eight strict claims.
- G006 made the contract defect unusually visible. Its trace reported all eight canonical stages,
  only five of seven transitions, and generation coverage of one supported, six partial, and one
  unsupported requirement. The answer was still marked valid and appended seven separate
  insufficiency notices. “Valid JSON with valid citations” had quietly become “valid answer,”
  even though the system's own diagnostics knew the content was incomplete.
- G008 found the other focused regression. It correctly qualified that the manuscript evidence
  did not directly establish the Hudson's Bay Company or Canadian fur trade, then supplied
  analogous Ohio Company material anyway. It did not fabricate an answer, but it failed the
  requested clean-abstention behavior. G009's useful bounded pandemic/supply-chain near match
  remained intact, so the repair must distinguish those two cases.
- The cumulative text-free V18-V24 ledger now covers ten isolated attempts, 78 completed API
  operations, 494,221 priced tokens, zero unpriced events, and **`$4.811832770`** in estimated
  development API cost. The failed quota attempt remains visible as a zero-call error rather than
  disappearing from the history.
- Selected the next repair from the full distribution: separate structural validity from
  `valid_complete`, `valid_partial`, and `insufficient_evidence`; enforce route-specific
  source-bounded obligation coverage; require surviving broad stages and handoffs to appear or be
  bounded concisely; and restore clean abstention after a corpus-level absence. No larger context,
  extra model call, retry, critic, or gold-derived location is justified.

Useful blog lesson: retrieval and generation are two different promises. Finding the right shelf
does not mean the answer carried the right argument off it. The most valuable diagnostic was not a
wrong citation; it was the application correctly reporting partial evidence internally and then
calling the result complete anyway.

### 2026-07-30 - V25 separated a valid answer from a complete answer

- Built V25 from the full V24 ten-question distribution rather than another G007-only patch. The
  repair targets the two failures the complete cohort made clearest: broad answers could validate
  while their own stage/obligation ledger said they were incomplete, and a certified absence
  could still lead to an unsolicited analogue.
- Kept structural correctness and content quality as different claims. JSON shape, source
  mapping, citation locality, and premise validation still decide whether the generation
  contract is valid. A new application-owned `content_outcome` separately reports
  `valid_complete`, `valid_partial`, or `insufficient_evidence`.
- Preserved the answer plan before retrieval so later stages cannot quietly disappear from the
  completeness denominator. Broad synthesis must realize the exact ordered stage chain, every
  adjacent transition, and every required source-bounded obligation. Long institutional
  lineages additionally require supported institutional handoffs.
- Made partial answers honest without making them unusable. A structurally sound answer can still
  be presented as `valid_partial`, but it gets one concise limitation rather than seven repeated
  gap notices. When sources disagree, that one limitation explicitly says they conflict.
- Tightened absence semantics around user intent. Permission comes only from the current raw user
  turn. Plain conjunctions, stale conversation history, negated analogue requests, and names such
  as “Parallel Council” or “Affect Society” do not authorize near-match material. Explicit
  analogue requests can use only bounded planner hints; causal near matches require a locally
  certified relation pair.
- Propagated the new outcome through the closed retrieval trace, answer-run diagnostics, the API,
  frontend types, and a backward-compatible nullable column in the local cost ledger. Historical
  rows remain readable with no invented completeness judgment.
- Deliberately did **not** change the generation prompt, planner prompt, structured output schema,
  retrieval core, eight-source ceiling, model-call count, retry policy, or manuscript-specific
  knowledge. This was an application contract repair, not another attempt to buy completeness
  with more context or more calls.
- Focused verification passed **246 tests**. The complete offline suite passed **598 tests with
  one intentional skip**, repository-wide Ruff passed, the production frontend build passed, and
  the whitespace integrity check passed. No OpenAI API call was made.
- V25 is not yet a measured improvement claim. The next step is to freeze the exact clean
  candidate and run all ten unchanged development questions once, with G007 reported as one item
  rather than restored as a quality veto.

Useful blog lesson: an LLM application needs two notions of “success.” A response can be perfectly
well-formed, accurately cited, and still fail to carry the argument the question asked for.
Treating those as separate contracts turns a vague quality complaint into a measurable system
state.

### 2026-07-30 - A second evidence scope, built to be compared rather than believed

- Implemented phase 1 of `docs/full_context_answer_strategy_design.md`: a reader can now choose an
  **evidence scope**, either the existing retrieved passages or the complete eligible manuscript.
  Retrieval remains the default and its prompts, schemas, planner, ranking, evidence gate, and
  policy version are unchanged.
- The point is not that a bigger context is better. Nobody has measured whether retrieval helps or
  gets in the way for this corpus, because there has never been a second arm to compare against.
  This builds the arm; it claims nothing about which one wins.
- Two new modules own the strategy: `src/full_context_pipeline.py` (serialization, prompt,
  one structured call, budget fail-safe) and `src/full_context_coverage.py` (schema, validation,
  remap, rendering). Neither imports the planner, retrieval ranking, or evidence gate, and a test
  parses their imports to keep it that way. None of those concepts has a referent once there is
  nothing to rank and nothing was filtered out before the model saw it.
- The citation contract is the load-bearing decision. The model cites **stable chunk IDs** in a
  structured per-claim field, never an inline bracket. Local code checks every ID against the exact
  set supplied for that request, then remaps the distinct cited IDs, in first-cited order, to
  compact `[Source N]` labels and attaches the brackets itself.
- Two consequences follow from that, and both are the reason it was chosen. Citation locality is
  true by construction, because the model never writes a bracket and cannot malform one. And a
  full-context answer arrives at the disclosure boundary in exactly the shape a retrieval answer
  has - prose with inline citations plus a short ordered list of cited chunks - so
  `public_source_payload`, the excerpt caps, the verbatim-overlap guard, and the frontend renderer
  all work unmodified and never see the whole corpus.
- An enum of the valid chunk IDs was considered and is infeasible rather than merely undesirable:
  481 chunk IDs total 23,753 characters against a documented 15,000-character limit for a string
  enum over 250 values.
- Absence changes character, so the corpus scanner was repurposed rather than retired. Retrieval
  scans to distinguish "not retrieved" from "not present." Full context has no retrieval miss to be
  suspicious of, which makes the model's claim that something is absent an unverifiable assertion
  about text it was shown in full. The scan now runs after generation, over every eligible chunk,
  searching only for surfaces the user themselves wrote, and a reported absence the scan
  contradicts downgrades the content outcome. It does not rewrite the answer, because silently
  editing prose would put unreviewed text in front of a reader.
- Cost accounting had to move first. `costs.py` carried a comment asserting that Archivist inputs
  stay below the GPT-5.6 long-context surcharge threshold; that stops being true on the first
  full-context call. The surcharge is now implemented as per-model data, and the existing cost
  tests caught the first attempt applying it to a large embedding request. How the surcharge
  interacts with cached-rate tokens is not settled by the documentation and is commented as an
  assumption rather than encoded as a fact.
- Everything is off by default. `ARCHIVIST_FULL_CONTEXT_ENABLED` and
  `ARCHIVIST_PUBLIC_FULL_CONTEXT_ENABLED` are two independent switches, and the public one is
  structurally powerless without the general one. A request for a disabled strategy is rejected
  explicitly rather than downgraded to retrieval, because a silent substitution would look
  identical to a successful full-context answer and would hide exactly the divergence the
  comparison exists to expose.
- Verification made no OpenAI call: 639 offline tests passed with one intentional skip,
  repository-wide Ruff passed, and the frontend production build and type-check passed.
- Confirmed the switch end to end without spending: with `ARCHIVIST_FULL_CONTEXT_ENABLED=true` the
  development `/api/config` reports `full_context_answers: true` and the reader control becomes
  selectable; with the variable absent it reports false and the control stays disabled. The
  variable is read once at process start, so a server already running when it is set never sees
  it - `--reload` watches files, not the environment.
- One control from the design is deliberately **not** implemented yet and is the first thing to
  add: §18's conservative pre-request budget check. The existing guard only refuses a call when the
  monthly budget is *already* exceeded; it does not predict that one full-context request could
  cross the remaining budget by itself. A retrieval turn costs about fifteen cents, so that
  distinction never mattered before. A cold full-context turn is estimated near three dollars, so
  now it does.
- This is a contract, not a result. No full-context request has been made. The next step is phase 2:
  enable the flag locally, run the development questions through it for debugging only, and measure
  real cold and warm cost, latency, and cache behavior before anything is claimed.

Useful blog lesson: the honest way to ask whether retrieval earns its complexity is to build the
alternative properly and measure it, not to argue about it. The interesting engineering was not
sending a big prompt - it was making the expensive path produce exactly the same auditable,
cited-only, disclosure-safe object the cheap path already produces, so the two can be compared at
all.

### 2026-07-30 - The first full-context call cost half the estimate and was thrown away

- Ran one unchanged G007 question through the frozen full-context candidate at commit `c01ce00`,
  clean tree, isolated ledger, `$4.00` authorized cap, no retries. G007 is development data that has
  guided repairs since V6, so this is a debugging and measurement run and its content score is not
  evidence about either strategy.
- The measurement corrected the design's own arithmetic. Actual input was **249,176 tokens**, not
  the roughly 286,000 the character-based estimate predicted - about 15 percent high. That matters
  for more than tidiness: 249,176 is **below** the documented 272,000-token long-context threshold,
  so the 2x input and 1.5x output surcharge never applied. The predicted `$2.50`-`$3.50` cold call
  actually cost an estimated **`$1.62514625`** in 42.154 seconds.
- A cold full-context turn is therefore roughly ten times a retrieval turn rather than twenty, and
  the whole corpus sits close enough to the surcharge threshold that a modestly longer manuscript,
  or a longer conversation history, would cross it. The threshold is not a comfortable distance
  away; it is about 9 percent away.
- Two cache readings disagree and the ledger took the expensive one. The live response reported
  249,173 cache-write tokens, priced at the 1.25x cache-write rate; the same response retrieved
  afterwards reports zero for both cache fields. At zero the call prices at `$1.31374000` instead.
  The provider dashboard is authoritative and this is now a concrete thing to check rather than the
  open question the design flagged. Either way the extractor is reading a real field rather than
  silently recording zero, which was the actual worry.
- The mechanical contract held on a live response, which is what the run was for. 481 eligible
  chunks were supplied; the answer cited 14. All 15 citation tokens resolved inside the remapped
  1-14 range, local validation passed with no error and no repair, and `final_chunks` carried 14
  entries rather than 481. Chunk-ID citation, membership validation, and the offline remap all
  survived contact with a real model.
- Then the harness threw the answer away. The run exited non-zero **after** generating and
  validating a good answer, because `evaluation_artifacts.SmokeArtifactRecorder` requires a
  retrieval trace for every turn and full context performs no retrieval. This is the project's
  familiar paid-but-discarded failure class, and it cost `$1.63` to rediscover in a new place.
- The response was recovered read-only from its stored provider ID rather than regenerated,
  following the precedent set when a client-side timeout stranded a paid G001 result. No second
  generation call was made.
- The fix needed no source change. The artifact contract already models a run with no traces as
  `not_applicable`, built for the earlier resolver-only confirmation; the full-context runner now
  uses that existing path, and fails closed in the other direction if a retrieval trace ever does
  appear, since that would mean full context reached the retrieval core.
- Source coverage is recorded as an observation and nothing more. The 14 cited chunks fall in
  Chapters 4, 11, 14, 17, 18, and 20, with no Epilogue passage. Chapter 14 is the Civil War group
  that the V21, V22, and V24 retrieval candidates repeatedly failed to reach. Strict manual
  grading was performed later under the same G007 rules used for retrieval: the answer realized
  **1/7 essential claims and 4/5 target groups** while self-reporting `valid_complete`. That is one
  nondeterministic development sample, not evidence that either strategy is better, but the
  mismatch is direct evidence that the application cannot treat a model completeness self-report
  as its own verdict.
- Still unmeasured, and now the most valuable next number: a warm call. The entire cost case for
  this strategy rests on prefix caching, and one cold call says nothing about it.

Useful blog lesson: an estimate labelled unverified is not the same as an estimate that is wrong in
a harmless direction, and this one was wrong twice over - too high on cost, and quietly close to a
pricing cliff it had assumed it was already past. The cheapest part of the run was the answer; the
expensive part was discovering that a validator written for one strategy silently assumed the other.

### 2026-08-01 - Full context became an audited experiment instead of a trusted long answer

- Reviewed the first full-context implementation against its live G007 artifact rather than the
  design's aspirations. The mechanical citation path was sound, but the application had accepted
  the model's own `valid_complete` label despite later grading of 1/7 strict claims and 4/5 target
  groups. It also let the model author absence subjects and reader-facing absence prose, accepted
  any in-corpus chunk ID without binding named targets to direct evidence, and weakly bound premise
  corrections.
- Opened `full-context-v2` as a new experimental cohort while leaving frozen RAG V25 untouched.
  Trusted targets are now extracted from the reader's own words and scanned exhaustively by the
  application. A present target needs at least one cited direct-hit chunk. An absent target needs an
  application-certified absence and an exact target-ID binding. Zero-claim insufficiency fails
  closed unless every trusted target passes that proof. The application writes the narrow evidence
  boundary sentence; the model does not. If no audited target has direct manuscript evidence, any
  extra claim now fails closed as an unsolicited analogue rather than quietly substituting a
  related subject. This also protects resolver-restored targets whose absence is deliberately not
  certifiable. A future analogue mode would need its own application-owned permission contract.
- Made completeness honest. Nonempty v2 answers can be grounded and readable, but they report
  `valid_partial` until a future application-owned requirement ledger can prove that every part of
  the question was answered. The model's completeness field is retained only as a diagnostic for
  measuring overconfidence. Contradictory claim/outcome shapes and incorrectly bound premise
  corrections fail the generation contract.
- Closed a public-disclosure hole before enabling the feature. Full context supplies the private
  manuscript but returns only cited chunks. The original public quotation guard inspected those
  returned chunks, so verbatim copying from an uncited chunk could evade it. Public full-context
  answers now audit against the complete eligible private corpus. Retrieval keeps the identical
  established `final_chunks` path, with a regression proving it never loads the full corpus.
- Added the pre-request hard-budget projection omitted from v1. Archivist prices maximum output
  under both ordinary uncached-input and observed cache-write shapes, takes the larger estimate,
  and refuses the call if it would cross the remaining monthly hard limit. The explicit
  `allow_over_budget` development override still works; public callers have no such override.
- Repaired cumulative cost accounting. The former report discovered only
  `evidence-planned-vN` directories and silently excluded the paid full-context call. Schema `/2`
  separates strategy from strategy version, rejects duplicate provider response IDs across both
  lineages, and reports **11 runs, 79 completed API operations, 745,657 priced tokens, and
  `$6.436979020` estimated cumulative development API cost**. The report remains text-free.
- Split the structured response and run-diagnostic schema identifiers, which v1 had accidentally
  made identical. Full-context response, prompt, renderer, and policy versions all advanced
  together to v2; both public and general feature flags remain disabled by default.
- Verification used no provider calls. The combined focused repair suite passed **120 tests**;
  the complete offline suite passed **667 tests with one intentional skip**; repository-wide Ruff
  lint passed; the production frontend TypeScript/Vite build passed; and whitespace integrity
  passed. Ruff's repository-wide formatter check still reports the pre-existing 51-file formatting
  baseline, so no unrelated mechanical reformat was mixed into this repair.

Useful blog lesson: giving a model the whole book removes retrieval scarcity, not the need for
contracts. The elegant context window is only half the system. The other half is deciding which
claims the application itself can verify: what the reader actually named, where that name occurs,
whether an absence is certifiable, whether a source was merely available or actually used, and
whether an expensive request should be permitted before it is sent.

### 2026-08-04 - Appearance and historical character became one honest reader control

- Replaced the ambiguous top-level “vibe” picker with three versioned Archivist modes that join an
  appearance, default Historiographical lens/Voice/Worldview settings, and an optional reviewed
  influence profile. Professional is the first-visitor frontend default; Essential is the neutral
  scholarly baseline; Mythical Forest Folio is a tragic, romantic, mythopoetic experiment.
- Kept the evaluation boundary intact. An omitted mode in the API, CLI, or test harness still
  resolves to Essential, and explicit Essential produces the old neutral prompt byte for byte.
  The browser sends Professional deliberately. This keeps a public product default from silently
  becoming a new RAG cohort or rewriting what earlier neutral measurements mean.
- Defined three source roles instead of calling every book a “source.” *Cradle of the Empire* is
  the sole `evidence_source`: it may support facts and citations. The selected public-domain works
  are `interpretive_influence`: they may shape method, emphasis, cadence, and judgment but cannot
  enter retrieval or supply historical content. Visual references affect CSS only. This is the
  same design discipline as an elegant context window: every piece of context has a declared job,
  and material that cannot do that job never enters the model-facing lane where it could be
  mistaken for evidence.
- Built the Professional profile from a deliberately complementary reviewed pack: Wesley Frank
  Craven for corporate and institutional mechanism, Charles A. Beard for material-interest and
  political-economy questions, and W. E. B. Du Bois for race, power, law, enforcement, and moral
  consequence. The resulting instruction is multicausal rather than deterministic and asks for
  clear public history rather than imitation of any author's prose.
- Bound the Professional profile to exact Project Gutenberg artifacts and hashes: Craven #28555
  (`7b647599…596c`), Beard #70677 (`3359e7ef…16e`), and Du Bois #17700
  (`08e42808…b9b`). Their records identify the artifacts as public domain in the United States,
  but rights outside the United States remain jurisdiction-specific. Craven's 1957 publication
  requires particular caution in life-plus-70 jurisdictions. Archivist stores only a manually
  reviewed prompt and provenance metadata; it neither commits nor redistributes the EPUB files.
- Built Mythical Forest Folio from the owner-supplied Project Gutenberg #61077 EPUB of Lord
  Dunsany's *The King of Elfland's Daughter*, frozen by SHA-256
  `b8a8a8ca…80b4`. The profile permits restrained wonder, landscape, thresholds, longing, and
  distance while expressly forbidding fictional names, places, lore, phrases, quotations, events,
  or claims. It is a literary influence, never a historical authority.
- Made the control hierarchy match what readers need first. The top-level picker chooses the
  coherent mode. Evidence scope remains separate. Lens, Voice, Worldview, and all ten visual
  themes moved into Advanced controls, where any departure is labeled Custom and Reset to mode
  restores the preset. Completed turns and retries preserve their resolved answer settings.
- Added server-owned allowlists, fixed profile files, mode/profile versions, prompt hashes, and
  provenance metadata. A client can request a known mode and granular overrides; it cannot submit
  arbitrary prompt text, influence paths, or new source IDs. Influence is inserted only after
  retrieval, so it cannot change primary hits, admitted evidence, source order, or citations.
- No manuscript text, influence-book text, or derived quotations entered the repository. No
  embedding, retrieval, corpus, model, or paid API call was changed for this pass. Detailed
  provenance and the evaluation/safety contract live in `docs/archivist_modes.md`.
- Offline verification passed 680 tests with one intentional skip, repository-wide Ruff lint,
  the TypeScript/Vite production build, and whitespace checks. The automated browser surface was
  unavailable in this session, so visual QA and a paid style-perceptibility smoke remain explicit
  follow-ups rather than implied claims.

Useful blog lesson: a theme stops being cosmetic when it changes how a reader is invited to see
the past. Making that honest requires more than colorful CSS: the interface must name the choice,
the prompt must bound what influence is allowed to do, the evidence lane must remain exclusive,
and the neutral experimental control must still be reproducible after the public default changes.

### 2026-08-04 - Cromb Coo Coo became the fourth semantic Archivist mode

- Joined the Cromb visual appearance to a reader-facing semantic preset with Evidence-first,
  Romantic, and Secular humanist defaults. The fixed influence profile is
  `cromb_coo_coo_manuscript/1`. Professional remains the first-visitor default, while Essential
  remains the omitted-mode compatibility baseline and the only mode used for held-out and gold
  evaluation.
- Distilled only reviewed formal traits from the private manuscript: affectionate absurdity,
  grotesque high fantasy, comic deflation of grandeur, sensory specificity, tenderness amid
  violence, and an emphasis on contingency and eccentric agency. The profile cannot quote,
  paraphrase, summarize, name, or allude to the manuscript's people, places, events, plot, lore,
  phrases, images, or factual claims.
- Froze a text-free local identity record for the owner-supplied private PDF without inferring an
  author: `Journey through Cromb Coo Coo_7_30_2026.pdf`, 226 pages, 815,751 bytes, SHA-256
  `f67f9ed3f622583abe2fca090d73881ff86a7f801cea88034589c986509ece74`, file modified
  `2026-07-30 10:05:30 -04:00`, PDF metadata creation `2026-07-30 10:05:29 -04:00`, created with
  Scrivener for Windows.
- Kept the private boundary mechanical. The PDF and temporary extracts are neither committed nor
  sent to an API. They do not enter Chroma, retrieval, evidence admission, source numbering,
  citations, completeness or absence checks, source cards, follow-up evidence, or logs. Only the
  short reviewed profile may affect generation after *Cradle* evidence is fixed.
- The interface now has four semantic modes and eleven visual appearances. The seven remaining
  legacy appearances remain appearance-only, so adding Cromb semantics did not quietly give those
  older themes invented answer behavior.
- Verified the implementation without provider calls: 683 offline tests passed with one intentional
  skip, repository-wide Ruff lint and focused formatting checks passed, the production frontend
  build passed, and whitespace checks passed. Browser screenshot automation remained unavailable,
  so perceptibility still needs a later manual or automated reader-facing smoke.

Useful blog lesson: a private creative work can influence an answer's sensibility without becoming
another answer corpus. The safe unit is not the manuscript text but a short reviewed contract that
names permitted formal qualities, forbids content leakage, and enters only after the historical
evidence has already been selected.

### 2026-08-04 - One expensive rejection began with one small grammatical mistake

- Traced a live Forest Folio failure for a nineteenth-versus-twentieth-century recession question
  through the text-free usage ledger. Archivist had found evidence and generated an answer; the
  strict validator rejected it afterward with `premise_provenance_mismatch`. Validation took only
  0.604 milliseconds. The request's 58.148 seconds and estimated `$0.19791642` were spent almost
  entirely on a planner call and answer generation that should never have received that premise
  contract.
- Found the root cause in deterministic routing, not in the Forest style or vector retrieval. A
  regex read the noun phrase `the cause of recessions` as though the reader had asserted `X caused
  Y`. At the same time, the router recognized neither side of `A versus B` as a bounded comparison,
  so it invented support, counter, and framing lanes for the whole question.
- Opened `evidence-planned-v26` with a corpus-agnostic comparison grammar. It creates one
  requirement for each side and a third for the contrast, keeps phrases such as `causes of X in A`
  intact in retrieval queries, and avoids the paid planner when that exact shape is locally
  unambiguous. Questions with subordinate assumptions, broad time spans, or oversized operands
  still go to the planner. Ordinary `How did X cause Y?` questions still receive premise checks.
- Kept the provenance validator strict. Instead of broadening eligible sources or silently
  rewriting model output, `evidence-coverage-v10` now tells the model the exact source-lane rules
  the application already enforced: supported premises cite support sources; contradicted ones
  cite counter/framing sources and include framing when available; unresolved ones cite nothing.
- The question had been drafted as H020 in the private gold-authoring workbook. Because it was
  submitted to Archivist and then used to choose a repair, it is no longer genuinely held out.
  Registered it as `DEV-MANUAL-008`, advanced the development registry to `1.1.0`, and rebound the
  unattested provenance template so the eventual gold audit will reject it. A new owner-authored
  H020 replacement will be needed before gold lock.
- Verification made no provider calls: 693 offline tests passed with one intentional skip,
  repository-wide Ruff passed, the production frontend built, and whitespace checks passed. The
  repaired route still needs one paid reader confirmation; offline correctness is not being
  presented as proof that the answer itself will be good.

Useful blog lesson: an elegant LLM context window begins before the context exists. A single word
can assign a question to the wrong evidence contract, causing a capable model to spend time and
money answering a problem the reader never posed. Good orchestration is partly the art of knowing
when *not* to call another model.

### 2026-08-04 - Six visual themes acquired a historical point of view

- Promoted Pretty Pink Princess, Baleful Black Baron, Tidal Archive, Ember & Ink, and Illuminated
  Codex, followed by Cosmic Almanac, from appearance-only overrides to versioned semantic Archivist
  modes. The interface now offers ten coherent mode presets while retaining all eleven appearances
  under Advanced controls.
- Made the contrasts deliberately legible. Pretty Pink Princess uses Triumphalist + Romantic +
  Secular humanist defaults and looks for courage, fellowship, adaptation, recovery, and possibility.
  Its optimism cannot erase or euphemize violence, enslavement, dispossession, exploitation, or
  failure. Baleful Black Baron uses Tragic + Romantic + None and makes cost, coercion, broken
  promises, narrowing choices, and foreclosed alternatives its dominant judgment without inventing
  suffering or inevitability.
- Replaced Tidal's previously cosmetic ocean theme with a Moby-Dick-informed maritime profile:
  oceanic scale, long-voyage uncertainty, moral pressure, hierarchy, obsession, limits of command,
  and restrained images of tide, depth, weather, course, or wake. It is intentionally distinct from
  Forest Folio's Dunsany register. The reviewed reference is Project Gutenberg #15, Gutenberg's
  preferred transcription based on the 1851 first American edition, frozen at SHA-256
  `8d76f75515a8e10b0ed0657275767f75b4b283177805a1c09c231840a0607d95` and artifact timestamp
  `2026-08-01T07:33:10Z`. No literary text enters retrieval or a live prompt, and the mode may not
  quote, paraphrase, imitate, or import Melville's characters, scenes, plot, symbols, or claims.
- Defined Ember & Ink as Realist Statecraft: a controlled, unsentimental reading attentive to
  interests, power, leverage, security, institutions, constraints, tradeoffs, and unintended
  consequences. Henry Kissinger is named only as an association with that broader historical
  tradition. No Kissinger work is ingested, retrieved, embedded, stored, cited, quoted, paraphrased,
  or imitated; the profile is a short, text-free project-authored contract rather than an authorial
  voice simulation.
- Defined Illuminated Codex as a lowercase-l modern liberal historian. It asks how rights,
  dignity, pluralism, toleration, representative institutions, rule of law, reform, inclusion,
  and accountable power changed who could participate and who remained excluded. It also requires
  the gap between declared ideals and lived access to remain visible, treats progress as contested,
  reversible, and uneven rather than automatic, and bars present-day party advocacy or the use of
  historical actors as proxies for current factions.
- Defined Cosmic Almanac as a future-science historian. It reads across long time horizons and
  looks for systems linking demography, ecology and climate where supported, technology, energy,
  infrastructure, information, institutions, path dependence, and feedback loops. It may discuss
  how historical choices constrain or open plausible futures only with explicit uncertainty; it
  may not invent future facts, write science fiction, treat projections as evidence, assume
  technological destiny, or explain historical actors through categories they did not possess.
- Kept the experimental boundary intact. All new profiles enter only after *Cradle* evidence has
  been selected. Essential is still byte-identical when omitted or selected explicitly and remains
  the sole held-out and gold-evaluation mode. The new modes open four Phase 2 style cohorts, not a
  new claim about neutral RAG quality.
- Verification used no provider calls: 29 focused backend mode tests and the focused frontend
  mapping test passed; the complete offline suite passed 706 tests with one intentional skip;
  repository-wide Ruff, the production frontend build, and whitespace checks passed. Paid paired
  style smokes remain a separate follow-up because offline prompt inspection cannot establish
  reader-visible tone.

Useful blog lesson: a dramatic theme is honest only when its invitation to interpret the past is
named and bounded. The Princess and Baron may disagree about meaning without disagreeing about
facts; Tidal and Ember may borrow a method or atmosphere without turning another author's work into
evidence; Codex may test institutions against liberal ideals without importing a current party
program; Almanac may look toward plausible futures without pretending they have already happened.
The most important implementation detail is where that influence enters the context.

### 2026-08-04 - Making a long answer feel alive without publishing the draft

> Historical v1 design, superseded by the protocol-v2 entry immediately below.

- Added an explicit answer-delivery choice beneath Evidence scope. **Complete answer** remains the
  recommended default: the reader waits and receives the answer, citations, and sources together.
  **Progressive response** is clearly Experimental and makes the wait legible with a fixed set of
  operational stages before revealing the completed answer incrementally.
- Rejected the tempting interpretation of “progressive” as raw model-token streaming. Archivist
  can decide only after generation whether an answer satisfies its evidence contract, and the
  public demo must also check extended quotation and construct its safe page-locator source
  payload. Publishing a draft a token at a time would let prose cross the boundary before the
  system knew whether it was grounded or safe to disclose.
- Kept the trust boundary simple: operational progress may say that the application is preparing,
  searching, composing, or checking, but it may never expose chain-of-thought, prompts, retrieval
  queries, manuscript text, draft prose, validation traces, or private diagnostics. Once every
  release gate passes, the already validated answer can be sent in ordered deltas and animated in
  the transcript without becoming provisional.
- Kept the experiment scientifically quiet. Both delivery modes send the same question,
  conversation history, interpretive choices, evidence scope, and RAG configuration to the same
  pipeline and resolve to the same answer and sources. Delivery therefore does not open an answer
  cohort. If it changes retrieved chunks, prose, citations, or a score, that is a presentation
  defect rather than a feature result.
- Defined a public same-origin NDJSON POST rather than adding a second conversational system. An
  accepted stream ends exactly once with completion or a safe error. The browser does not
  automatically replay an accepted request after a disconnect, because the upstream paid call may
  still be running and a replay could charge twice. Closing the tab is likewise not represented as
  a guarantee that model compute stopped.
- Made stream ownership part of the public abuse boundary. The request consumes its rate and
  concurrency allowance until the stream finishes or disconnect cleanup runs—not merely until
  Render receives response headers. This matters on the deliberately single-instance,
  single-worker deployment, where the gate is process-local.
- Recorded the honest latency story. Progressive response improves transparency and can make the
  wait feel shorter, but it does not shorten retrieval, generation, validation, or model compute.
  Because answer prose is withheld until approval, time-to-first-answer-word can remain nearly the
  full generation time. A live Render smoke is required to check browser/proxy buffering,
  disconnect cleanup, no automatic retry, and identical final answer/source behavior.
- Hardened the browser protocol after adversarial review: it accepts only the documented stage
  order, bounds NDJSON lines and cumulative answer text, requires deltas to reproduce the terminal
  answer exactly, clears interrupted partial prose, and never retries a request after the server
  has accepted it. Short post-validation chunks are paced in the interface so the reveal remains
  perceptible even when a browser or proxy delivers several network frames together.
- Closed the local verification pass with 714 Python tests passing (one skipped), Ruff clean, both
  frontend behavior suites passing, and a successful production frontend build. No paid model call
  was made for this implementation; the remaining live Render smoke is explicitly a deployment
  check rather than evidence that has already been gathered.

Useful blog lesson: streaming is not automatically more transparent. Raw model tokens would show
more motion while weakening the evidence and privacy promises that make Archivist interesting.
The more elegant design separates progress from reasoning and delivery from generation: explain
what the application is doing, keep the draft private, and reveal the answer only when it is ready
to stand behind.

### 2026-08-04 - When “progressive” turned out to be only an animation

- The first live test exposed a clean but important product mistake. Archivist displayed useful
  status messages during the long wait, but no answer prose arrived until every check had already
  finished. The browser then revealed the completed answer in paced chunks. It looked progressive
  after the fact; it did not make the answer arrive progressively.
- Replaced that post-validation reveal with genuine same-request Structured Output streaming. The
  existing final generation call now arrives as raw SDK events. Archivist buffers the structured
  JSON privately, releases nothing from an incomplete object, and extracts one whole factual claim
  only when that claim can be parsed and checked locally.
- Kept raw token deltas and model reasoning private. What appears in the transcript is neither a
  scratchpad nor an unfinished sentence: it is a complete cited claim with valid local identifiers,
  ordering, paragraph placement, source references, and size bounds. The public demo additionally
  proves page-locator availability and applies the cumulative quotation boundary before each
  claim, so dividing a long quotation among several claims cannot evade the limit.
- Made the tradeoff visible instead of pretending it does not exist. A locally checked claim is
  not yet a globally complete answer. Later validation can still discover missing coverage,
  inconsistent premise handling, or another whole-answer defect. Progressive mode therefore marks
  the working assembly **Checked partial · Not final**, excludes it from conversation memory,
  copying, citations, and sources, and erases it on interruption or late failure. The canonical
  answer replaces it only after the unchanged validator succeeds.
- Preserved Complete answer as the default for readers who prefer the strongest fail-closed
  contract: rejected prose is never shown at all. Progressive mode deliberately cannot make that
  same promise while also showing prose before global validation. This is now an explicit reader
  choice rather than a hidden implementation compromise.
- Withheld interpretive prefaces and conclusions until completion. In the structured answer
  contract the factual units are generated separately from the framing that ultimately surrounds
  them. Reordering that model-facing schema would have changed the system under test, so the live
  assembly presents manuscript claims first and introduces the selected historical voice only in
  the canonical answer.
- Kept the cost story honest. Progressive delivery uses one streamed final-generation API request,
  replacing the previous blocking form of that same request. It adds no preview or second answer
  call, and terminal provider usage is written to the ledger once before local schema parsing. The
  conversation resolver, planner, embeddings, retrieval, and evidence gates still happen before
  answer claims can appear, so the first claim will not be instantaneous and total compute should
  remain similar.
- Added a versioned NDJSON checked-claim protocol, a separate provisional frontend state, bounded
  parsers on both sides, no replay after acceptance, public concurrency ownership through worker
  cleanup, and adversarial tests for malformed, truncated, divergent, and late-failing streams.
  The remaining deployment question is empirical: whether Render, Cloudflare, and the browser pass
  frames through soon enough to make the first checked claim visibly earlier on the live site.
- Closed the local verification pass with **749 Python tests passing and one skipped**, Ruff clean,
  both frontend behavior suites passing, and a successful production build of 1,589 modules. A
  focused 309-test backend pass covered the changed delivery, accounting, validation, RAG, and
  full-context surfaces. No OpenAI request was made during implementation or verification.

Useful blog lesson: latency is partly a trust-design problem. One extra spinner cannot disguise a
blocking architecture, while raw token streaming can buy immediacy by giving up the right to check
what was said. Archivist’s middle path makes the unit of progress a checked factual claim—and is
honest that the complete argument is not trustworthy until the last gate closes.

### 2026-08-05 - The answer was waiting behind its own ledgers

- A second live test clarified why genuine checked-claim streaming still felt mostly silent. The
  answer did not merely encounter network buffering: the Structured Output contract itself asked
  the model to write private premise, coverage, and obligation ledgers before it reached the
  factual claim array. Because Archivist only releases complete claim objects, almost all useful
  prose was structurally scheduled near the end of the model's response.
- Reordered the shared schemas so factual claims are serialized immediately after the schema
  identifier and terminal-only ledgers follow them. This is deliberately shared by Complete and
  Progressive rather than a cheaper or differently prompted streaming path. Because property
  order is model-facing in Structured Outputs, the change opens `evidence-coverage-v11` and
  `full-context-coverage-v3`; it must not be smuggled into an old evaluation cohort or described as
  a measured RAG improvement.
- Added a narrow Progressive lead contract. The first releasable factual claim must answer the
  bottom line in one sentence, stay within 45 words, and name a trustworthy subject from the
  question when one is available. A premise correction is still too globally consequential to
  stream early, so it remains private and the following factual unit becomes the lead candidate.
  If that candidate fails the local rule, the stream stays fail-closed while the one paid request
  continues toward its ordinary canonical answer.
- Turned the previously invisible heartbeat into honest reader feedback. About every three
  seconds the interface updates an elapsed-work indicator without manufacturing prose or exposing
  chain-of-thought. Response headers also forbid caching and transformation to reduce avoidable
  proxy buffering.
- Kept the experiment deliberately subordinate to the main product. Complete answer remains the
  default, while Progressive response now sits inside a collapsed **Advanced delivery settings**
  disclosure rather than reading like a peer feature every visitor is expected to choose.
- Added one private, text-free timing record per Progressive request. It records application stage
  entry, first provider text delta, first checked claim, provider terminal, terminal outcome,
  worker finish, and stream finish. That makes the next live smoke diagnostic: a late first
  provider delta implicates the model; an early provider delta but late checked claim implicates
  schema/parsing/release; an early server claim but late browser claim implicates Render or
  Cloudflare. Questions, prompts, sources, manuscript text, answers, and error text are excluded.
- Deliberately did not cache the per-request corpus-integrity check. Its file reads and hashes may
  contribute to the wait, but a cheap metadata cache could miss a same-size, same-timestamp content
  mutation and weaken the private-corpus guarantee. The timing record lets a later optimization be
  evidence-led rather than speculative.
- Closed the offline pass with **760 Python tests passing and one skipped**, Ruff clean, both
  focused frontend suites passing, and a successful production build of 1,589 modules. No paid
  OpenAI call was made. The remaining proof is a deployed comparison of the custom domain and
  Render's direct address, using the timing milestones to distinguish provider latency from proxy
  buffering.

Useful blog lesson: in a structured-output application, JSON property order can become user
experience architecture. The answer was not waiting for a typing animation; it was queued behind
machine-facing paperwork. Moving reader-useful facts ahead of terminal ledgers preserved one
generation call and the validation boundary while giving the stream something worth showing
earlier.

### 2026-08-05 - Separating benchmark authorship from annotation labor

- Amended the still-unrun formal evaluation contract after the owner proposed having Claude draft
  the repetitive annotation fields. The important boundary is now stated more precisely: the owner
  writes and freezes the questions, strata, expected answer-versus-abstain behavior, and inclusion
  decisions; an external model may help search the corpus and propose evidence labels, but it does
  not become the ground-truth authority.
- Designed the assistance as a blind protocol. Claude receives a five-question batch, the private
  chunk payload, the corpus manifest, and a canonical prompt—never Archivist answers, retrieved
  contexts, traces, development results, known failures, or scores. Its output is visibly marked
  unverified, kept out of Git, and hashed for provenance.
- Added a text-free question fingerprint covering ordered IDs, question wording, strata, and
  Behavior values. Recording that fingerprint before assistance makes it possible to prove later
  that annotation work did not silently rewrite the exam, without publishing the held-out
  questions themselves.
- Strengthened the privacy audit because AI-drafted prose can leak through more than claim text.
  It now checks questions, `must_not_claim`, and notes too, while reporting only item/field/chunk
  identifiers and match lengths.
- Found an important preflight failure before any Claude work began: the replacement for H020 is
  still structurally and semantically too close to a registered development question that drove
  the V26 repair. A one-century substitution does not restore held-out status. H020 therefore needs
  a genuinely different owner-authored question before the complete question set can be frozen.
- Verified the amended machinery with 768 passing Python tests, one intentional skip, and Ruff.
  The private form fingerprints all 40 questions with the contracted 8/8/6/10/5/3 stratum mix.
  No OpenAI or Anthropic call was made.

Useful blog lesson: a trustworthy benchmark does not require pretending that no tool assisted with
the clerical work. It requires freezing the questions first, blinding the assistant to the system
under test, preserving an audit trail, and keeping final judgment with a human who checks the
sources rather than approving plausible prose.

### 2026-08-05 - Pausing feature work to build the ruler carefully

- Closed the current implementation checkpoint in commit `355f78d`. The checkpoint formalizes
  provenance-v2 for blinded annotation assistance, adds a text-free owner-question fingerprint,
  broadens quotation-risk checks beyond claims, and moves Progressive delivery into Advanced
  settings so an experiment does not compete with the recommended answer path.
- Verified the checkpoint with 768 passing Python tests and one intentional skip, Ruff, both
  focused frontend suites, and a production frontend build. The first sandboxed full run produced
  fixture setup errors because Windows denied Pytest's default temporary directory; the identical
  offline suite passed when rerun with an authorized repository-local fixture directory. No paid
  model call was made.
- Converted the private forty-question Markdown form into an editable owner-review Word workbook.
  The workbook visually separates owner-controlled fields from Claude-derived, unverified draft
  fields; adds a priority review queue and per-item revision notes; and marks H020 as a blocking
  replacement rather than disguising it as usable gold. The file remains private and gitignored.
- The review surfaced a protocol-history problem worth preserving rather than papering over: the
  current Claude-filled form was created before the question commitment and canonical raw-draft
  manifest existed. It can help the owner think, but it cannot honestly become the provenance-v2
  canonical annotation batch. Fresh blinded batches come only after the owner finalizes the exam
  and records its commitment.
- Paused RAG and reader-feature development while the owner works through the gold set. The next
  engineering action is not another answer-quality patch; it is closing the private-Markdown
  overlap-audit gap and then executing the declared evaluation sequence against a clean frozen
  candidate.
- Reconciled the README, roadmap, standing agent rules, project notes, evaluation contract, and
  gold-authoring guide around that pause. The current-state summaries now separate the live reader
  product from unrun formal measurement, distinguish ten semantic modes from eleven visual
  appearances, document the internal full-context citation remap, and leave one explicit restart
  path instead of several stale next-step lists.

Useful blog lesson: evaluation work is product work. A polished retrieval system needs a carefully
made ruler, and making that ruler can require more historical judgment than writing another search
heuristic. Stopping feature development here protects the eventual measurement from becoming one
more tuned demonstration.

### 2026-08-07 - Making the first held-out comparison executable before seeing a score

- The formal gold lock exposed one final experimental-design gap before any held-out retrieval:
  the roadmap promised a dense-versus-hybrid comparison, but the contract still defined
  `S_primary` only as raw Chroma output. It also left empty relevance sets, the comparison
  statistic, and the ten-item noise subset implicit. Running first and deciding those details
  afterward would have made metric selection part of the result.
- Closed the gap prospectively. The Dense arm is the raw `l2` vector ranking. The Hybrid arm is the
  already-shipped BM25/dense reciprocal-rank-fusion policy at each requested depth. Both receive
  the same question, corpus, eligible boundary, semantic candidate pool, and cached query vector.
  Macro Recall@5 over items with non-empty relevance sets is now the declared comparison; the full
  Recall@k, context, essential-coverage, fallback, displacement, and per-stratum profile remains
  mandatory rather than selectively reported.
- Made abstention items honest denominators. Questions with deliberately empty relevance sets do
  not become automatic zero-recall failures or zero-hit successes; retrieval recall is null for
  them, while their fallback events remain measured. Every aggregate carries the number of items
  that actually contributed to it.
- Built a retrieval-only runner that never calls the planner, generator, answer model, or judge.
  It sends the 37 question strings to `text-embedding-3-small` at most once, stores only hashes and
  vectors in a private gitignored cache, disables automatic retries, and reuses those exact vectors
  for both arms, all six values of `k`, and five fixed-subset repetitions. Result artifacts contain
  IDs, hashes, numbers, and configuration—not questions, annotations, answers, or manuscript text.
- Added mechanical brakes around the interesting moment: the runner rejects a changed gold hash,
  nonmatching candidate, dirty run-of-record tree, altered corpus/index, missing authorization,
  undersized cost ceiling, or pre-existing output. The owner authorization in conversation remains
  necessary; a command-line flag cannot manufacture it.
- A focused pre-run review caught four issues before they could affect a score or spend: noise
  spreads now cover every stratum and the declared Hybrid-minus-Dense comparison, embedding vectors
  are bound by validated provider indices rather than response position, an existing result aborts
  before a missing cache can trigger spending, and non-finite cost ceilings fail closed.
- The offline preflight verified the frozen 37-item gold binding and the active 481-chunk Chroma
  index in `l2` space. No cached held-out query embeddings exist yet, no H-item reached retrieval,
  no held-out content was sent externally, and no paid API request was made. OpenAI's current
  embedding documentation implies a provider-limit worst case of $0.006 for the one allowed batch,
  so the proposed authorization ceiling is $0.01.
- Offline implementation verification closed with repository-wide Ruff clean, **784 Python tests
  passing and one intentionally skipped**, both focused frontend suites passing, and a successful
  production frontend build. These checks were local and made no OpenAI request.

Useful blog lesson: pre-registration is often a series of small, unglamorous decisions made before
the first number appears. Choosing the arms, denominator, primary metric, and noise sample while
the result is still unknowable is what turns a convenient demo comparison into evidence that can
surprise its author.

### 2026-08-07 - Making calibration part of the evaluation instead of another delay

- Reframed the citation, faithfulness, and abstention calibration as the opening segment of one
  continuous answer-quality cohort. The fixed ten calibration answers are now the first ten of the
  same 37-item frozen V26 run, not a throwaway pilot. After the scoring instrument locks, the next
  substantive operation is the remaining 27 answers; no RAG, prompt, retrieval, model, or UI repair
  may be inserted between them.
- Removed a hidden veto from automatic judging. Human labels are still bound before semantic judge
  verdicts are revealed, and judge agreement is still measured, but a judge that misses its
  predeclared thresholds sends the affected dimensions to manual scoring or an explicit pending
  state. It cannot prevent the owner from learning how the full frozen candidate performed.
- Clarified what the first answer-quality result can honestly claim. The complete 37-item result is
  a descriptive held-out baseline with exact denominators. It may disclose that generator spread
  has not yet been measured; five unchanged repetitions become mandatory before a later
  before/after, significance, or production-guarantee claim rather than another prerequisite to
  seeing the baseline.
- Recorded a provider-level reproducibility limit instead of fabricating precision. OpenAI's
  current model catalog exposes `gpt-5.6-sol` and `gpt-5.6-terra` as canonical current-snapshot IDs
  but no immutable dated snapshots for them. The cohort will bind a committed catalog observation,
  every requested and provider-returned model ID, role-specific settings, and response IDs, and
  will say plainly that the names may not pin provider-side weights forever.
- Synchronized the standing rules, README, roadmap, and defect history before any held-out answer
  was generated. This documentation and harness implementation work made no paid or external model
  call. The separately completed retrieval-only diagnostic remains valid, and V26 remains frozen.
- Finished the resumable run-of-record harness before spending on the cohort. It seals the exact
  ten calibration answers and three answer-only decompositions apiece, requires owner labels before
  revealing semantic judge verdicts, projects those first calls unchanged into the 37-item result,
  and then permits only the remaining 27 frozen questions. Separate ledgers and authorization caps,
  no-retry orphan detection, hash-bound artifacts, and a text-free public report make interrupted or
  partially manual runs visible instead of silently rerunning or overwriting them.
- Offline verification passed Ruff, 121 focused evaluation/governance tests, and the production
  frontend build. The repository-wide Python suite reached its end twice, but the Windows test
  environment made Pytest's temporary directory unreadable during cleanup and prevented a valid
  final summary; this was recorded as an environment limitation rather than misreported as a pass.
  No OpenAI client was constructed during this implementation and verification work.

Useful blog lesson: calibration should make the ruler legible, not keep the object being measured
off the scale. A fallback from automatic to manual scoring preserves rigor without allowing the
measurement apparatus to suppress an inconvenient or incomplete result.

### 2026-08-09 - Taking the ruler out of the doorway

- The owner caught that the supposedly nonblocking calibration still divided the evaluation into a
  ten-question opening and a 27-question remainder. It no longer had a quality veto, but it still
  imposed an operational stop for labels and judge qualification before most answers could exist.
- Amended the contract prospectively because no held-out answer had yet been generated. The next
  substantive paid operation now generates and preserves all 37 frozen V26 answers and one
  canonical decomposition for each, without a calibration stop or intervening system change.
- Separated **producing the evidence** from **qualifying an automated scorer**. The initial baseline
  can report identity, answer status, citations, costs, latency, and other mechanical measurements
  immediately. Faithfulness, semantic coverage, abstention, and premise-correction metrics remain
  explicitly pending wherever they need the later calibrated judgment.
- Demoted the fixed ten-item exercise to what it actually is: later, lower-priority validation of
  the scoring instrument. Human labels, decomposition repeats, and judge-agreement checks may add a
  hash-bound supplement to the preserved baseline, but they cannot overwrite it, delay it, or
  decide whether the 37-question result is allowed to exist.
- Preserved the frozen V26 candidate, gold set, corpus, prompts, models, and earlier retrieval-only
  diagnostic. This was a sequencing correction before answer exposure, not a system repair or a
  retroactive response to a score.
- Implemented one resumable `run-37` entry point. It completes the 37 frozen V26 answer turns and
  then exactly one canonical answer-only decomposition for each result. Calibration repeats and
  semantic judge verdicts are absent from this operation; interrupted, already-bound checkpoints
  are verified and reused instead of silently purchased again.
- Made the first report part of that same command. Once the canonical decompositions exist, the
  harness writes a sealed private binding and closed, text-free JSON and Markdown summaries of
  completion, technical errors, cost, latency, citation syntax/resolvability/completeness, and
  source-to-gold-location diagnostics. Semantic measures are visibly pending rather than invented.
- Verified the evaluation subsystem with 129 focused tests plus Ruff and whitespace checks. A
  repository-wide run reached 827 passing and one skipped test before 81 tests encountered the
  repository's existing Windows temporary-directory access failure; no evaluation assertion
  failed. The offline preflight confirmed the exact 37-answer/37-decomposition scope and made no
  provider call.

Useful blog lesson: evaluation generation and evaluation scoring are different jobs. A careful
scorer can improve how a result is interpreted, but it should not stand in the doorway and prevent
the underlying evidence from being created.

### 2026-08-09 - A fail-closed stop that should not erase valid evidence

- The first paid held-out answer run finally began. H001 and H002 sealed successfully. On H003,
  Archivist made one embedding call, found insufficient evidence through its deterministic local
  release path, and returned `clean_abstention` without calling the answer model.
- The evaluation harness did exactly half of the right thing: it rejected an artifact shape it did
  not understand and stopped fail-closed. It made no retry, preserving both the budget and the
  experiment. The mistake was narrower—the production path's valid early abstention had never been
  represented in the harness's checkpoint assumptions.
- The stop left useful evidence, not a disposable failed run. H001/H002 are sealed; H003 has an
  exact retrieval trace and ledger entry proving its one embedding call and local release. Recorded
  spend at the stop is about `$0.2957022`. H003 is probably a false abstention, but that is precisely
  the kind of behavior a held-out evaluation is supposed to preserve rather than repair away.
- Designed recovery as an audited migration, not a do-over. The original partial root remains
  immutable. A provider-free command creates a sibling root, rebinds only the outer checkpoint
  envelopes required by the corrected runner, keeps H001/H002 inner payloads unchanged, and
  reconstructs H003 explicitly from its sealed trace. A migration artifact binds both roots,
  manifests, runner hashes, usage events, and recovered item.
- The resumed run starts at the first genuinely missing provider operation under the same
  cumulative `$20.00` ceiling. There is no calibration detour and no change to V26, prompts,
  retrieval, models, corpus, gold, or UI. “Uninterrupted cohort” now means uninterrupted behavioral
  conditions, while permitting exact provider-free continuation after a harness fault.
- Recovery has one irreducible measurement cost: H003's complete turn latency was not sealed. The
  final report therefore measures generation latency from 36 of 37 turns, identifies H003 as
  trace-recovered, binds the migration hash, and discloses the limitation publicly instead of
  inventing a duration.

Useful blog lesson: fail-closed does not have to mean throw everything away. If completed work is
cryptographically and operationally provable, the honest recovery is to preserve it, disclose the
migration, and continue without giving an unfavorable result a second chance.

### 2026-08-09 - When the measuring tool failed before the answer did

- The audited recovery worked: Archivist completed and sealed all 37 frozen V26 answers without
  retrying H003. That changed the state of the project from “answer generation interrupted” to
  “answer evidence complete.” The generation-latency limitation remains 36 observed turns out of
  37 because H003's original full-turn clock could not be reconstructed.
- Canonical claim decomposition then failed on its very first Terra call. H001's response was valid
  JSON, but five of its eight claim strings did not exactly match the frozen answer slices named by
  their character offsets. The strict check rejected it rather than quietly nudging the offsets
  into place. That is an evaluation-instrument failure, not evidence that the H001 answer itself is
  defective.
- The call was not repeated. Its completed provider response was retrieved later by exact response
  ID through a non-generating `responses.retrieve` operation and preserved in a private snapshot.
  The snapshot SHA-256 is
  `dd6ca585e3d1f8fac6af4070187b0230115ded0482837c23b4f12beda82c1f1e`.
  Cumulative recorded spend at the stop is `$5.42436647`.
- The recovery rule is intentionally asymmetric. H001 keeps its one failed attempt forever; the
  next run calls Terra only for the 36 items that have never received a decomposition attempt. A
  provider-free sibling migration binds the 37 answers, usage ledger, retrieved response,
  validation failure, prompts, runners, and both roots before any paid continuation begins.
- The eventual report will say exactly what happened: 37 answers, 37 attempted canonical
  decompositions, 36 usable decompositions, and one technical failure. Claim-based denominators
  exclude H001 explicitly. It will not be disguised as an answer with zero claims, counted as a
  candidate failure, or repaired into a passing instrument output.

Useful blog lesson: a held-out evaluation measures two systems at once—the candidate and the
ruler. When the ruler produces an invalid reading, preserving the failed reading and narrowing the
denominator is more honest than polishing it into data after the fact.

### 2026-08-09 - When the ruler ran out of thought before it produced a reading

- Recovery-03 advanced canonical decomposition from H003 through H028, then made H029's one
  contracted `gpt-5.6-terra` call. The provider returned `incomplete` with no output after using
  923 input tokens and 8,000 output tokens, all categorized as reasoning. The call cost
  `$0.1223075`.
  At the stop, all 37 V26 answers remained sealed, 28 decomposition attempts had occurred, and 27
  decomposition outcomes were already preserved.
- The empty result was not retried and was not turned into a fictional zero-claim answer. The
  existing response `resp_04c5799aa1b46c76006a78a779f5e8819f84b2edbf39a416c5` was retrieved by
  exact ID without a model call and stored in a private snapshot whose SHA-256 is
  `84503bc1cd861bafc09cb33bbe32f581ee56a63ed15c66e8d5ccb7562d1d8617`. The ledger now closes at
  116 priced events, `$6.80227647`, and zero unpriced events.
- Recovery-03 remains immutable. A provider-free migration to recovery-04 will record H029 as an
  `incomplete_response` measurement failure, preserve the 27 prior outcomes, and resume only the
  nine never-attempted items H030–H038. No V26 behavior, question, gold annotation, prompt, model,
  answer, or citation is being changed.
- The intended migration and resume commands are:

  ```powershell
  uv run python scripts/run_answer_evaluation.py recover-decomposition-failure `
    --source-run-root runtime/evaluations/v26-held-out-answer-quality-2026-08-07-harness-recovery-03 `
    --run-root runtime/evaluations/v26-held-out-answer-quality-2026-08-07-harness-recovery-04

  uv run python scripts/run_answer_evaluation.py run-37 `
    --run-root runtime/evaluations/v26-held-out-answer-quality-2026-08-07-harness-recovery-04 `
    --authorize-openai-full-evaluation `
    --max-cost-usd 20
  ```

- The continuation rule stays narrow. Another exact provider status of `incomplete` can be sealed
  once as a technical outcome and followed by the next untouched item. Unknown statuses, provider
  or network failures, a model mismatch, a missing parse, or an unavailable citation number still
  stop fail-closed. Answer-level measurements remain `n = 37`; only claim-decomposition metrics use
  the eventual `N` usable readings. Calibration and semantic judging remain later work and cannot
  delay this baseline.

Useful blog lesson: sometimes the model being evaluated has already answered, while a second model
used as a ruler consumes its entire allowance and says nothing. The honest result is neither a
retry nor a blank score—it is a disclosed instrument failure, preserved exactly once.

### 2026-08-11 - Separating the cohort cap from the service budget

- The owner authorized the locked 33-request production-performance cohort with no retries or
  replacements and a `$10.00` cohort cap. A read-only check of the live usage ledger showed no
  calendar-month spend, but the service still had its older `$5.00` monthly ceiling.
- Those two limits serve different purposes. The runner's `$10.00` cap limits this one cohort. The
  service budget governs every public request and must retain the versioned `$2.00` worst-case
  request allowance before accepting another turn. Leaving it at `$5.00` could therefore convert
  budget-denied requests into irreversible failures in the fixed 33-attempt denominator even when
  the cohort remained below its authorized cap.
- The Blueprint ceiling was aligned to `$10.00` before deployment. The runner still cannot exceed
  the owner's `$10.00` authorization, does not retry or replace failures, and reports recorded cost
  separately from conservative authorization accounting.

Useful blog lesson: a benchmark can have both an experimental spending cap and an application
safety budget. If they are not aligned before a no-retry run, the safety system itself becomes an
unintended experimental variable.

### 2026-08-11 - The production cohort filled the last resume blank without hiding failures

- Ran the predeclared warm production cohort against deployed wrapper commit
  `e71d9b79a60a894cb38451c37e0d43b7f9149fa9`. Two readiness checks and `/api/version` bound the
  same process epoch, corpus, RAG policy, model, and versioned `$2.00` request ceiling before the
  first paid request. There was no paid warm-up.
- Attempted all 33 answerable held-out questions as fresh Essential/Complete/RAG first turns with
  empty history, sequential execution, at least 12 seconds between request starts, and no retries or
  replacements. Twenty-nine requests completed successfully and four failed, so the all-attempt
  request-failure rate is **12.1212%**. The instrumentation-failure count is **zero**.
- The successful-completion denominator matters. Across those 29—not all 33—server latency was
  **54.393 seconds p50** and **113.801 seconds nearest-rank p95**. Client-observed latency was
  **54.493 seconds p50** and **113.829 seconds p95**.
- A private text-free diagnosis localized all four failures after successful planning and a
  `direct_answer` evidence decision. Two generated answers omitted a required unit-to-requirement
  link; one paired an obligation dimension with an impermissible unit role; one marked a
  requirement unsupported while still assigning it an answer unit. The public service rejected
  all four rather than releasing internally contradictory evidence mappings. None was a budget,
  transport, deployment, retrieval-availability, or instrumentation failure.
- The cohort recorded **500,164 tokens**, **80 priced events**, **zero unpriced events**, and
  **`$4.90594694`** estimated API cost. Its publishable summary contains no H-item IDs, questions,
  answers, sources, manuscript text, conversation identifiers, or provider response IDs; its
  file SHA-256 is `dd13ad2cf60a863daf88e549106059a1d05126b40ffa3c66c3c8e18cb6246b7f`;
  its embedded canonical artifact hash is
  `e2fcc051e66b115cf56abf7061fa93bfcd3c12297396cbdc3fad42b8bd1bfd30`.
- The temporary `$10.00` service budget created room for the independently authorized cohort. Once
  the sealed run closed beneath that cap, the source configuration returned the ordinary public
  monthly ceiling to `$5.00`; the live Render value still requires the normal manual-deployment
  parity check. The server's separate `$2.00` per-request ceiling remains unchanged.
- The defensible resume sentence is now: “Deployed on Render with privacy-safe request correlation,
  per-stage timing, and token/cost telemetry; in a predeclared 33-request warm production cohort,
  observed 54.393-second p50 and 113.801-second p95 end-to-end server latency across 29 successful
  completions, with four request failures (12.1212%), zero instrumentation failures, and
  `$4.90594694` estimated API cost.”
- This is deliberately an observed cohort, not an SLA, uptime claim, load test, or promise that a
  future query will complete within either percentile. The four failures are part of the product
  result, not rows to discard in pursuit of a cleaner median.

Useful blog lesson: observability is most credible when it makes the uncomfortable rows harder to
hide. The stronger portfolio evidence is not merely “median latency was measured”; it is that the
attempt denominator, successful-latency denominator, request failures, instrumentation failures,
and spend all closed together under one deployed identity.

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
