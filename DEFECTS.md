# Archivist — Defect Log

Entry format:

```
## [YYYY-MM-DD] Short title
Phase/Brief: <which phase and brief surfaced this>
Symptom: what was observed, stated as an observation rather than a diagnosis
         (e.g. "completeness fell 12 points with no prompt change")
Cause: contract edited / gold entry changed after a result / presentation change moved a
       metric / corpus logic leaked into engine / retrieval primitive duplicated /
       Phase 2 concern in Phase 1 work / noise floor exceeds claimed effect /
       manuscript text committed / spec gap in the brief / model error / other
Resolution and verification: what changed, and what check now confirms it
```

Log an entry whenever:

- a gold entry or a metric definition is suspected of having been changed in response to a result
- a presentation-layer change moved a measured number
- corpus-specific logic has leaked into engine code — a person, place, or chapter name in a retrieval or generation path
- a retrieval primitive has been duplicated rather than parameterized
- a Phase 2 concern — Index Mode, persona, perspective modes — has crept into Phase 1 work
- a metric's run-to-run spread exceeds the effect being claimed from it
- manuscript text has entered a committed file
- a formal run uses an unbound model alias or canonical ID without the required catalog observation,
  requested/returned IDs, and reproducibility limitation
- a run cited as a run of record turns out to have had a dirty working tree
- **the brief itself was underspecified and the implementer had to invent a mechanic**

## Two entry kinds that are not defects but are logged here anyway

**Contract events.** Locking `EVAL_CONTRACT.md` §6 or §7 after calibration, or declaring criteria
for a later comparative experiment, is logged as a dated contract event. These are not faults, but
they are moments at which interpretation or comparability changes, and a reader tracing an old
number back needs to find them.

**Cohort openings.** Any change to prompt text, model snapshot, sampling parameters, retrieval parameters, chunking parameters, or the corpus snapshot. Not a fault — this is the normal way the system improves — but earlier runs stop being comparable and the boundary has to be findable.

## Why the specification-gap entry matters

**A gap in the brief is a defect, logged the same as a code fault.** On the previous project most defects traced to specification gaps rather than to model output, and that pattern only became visible because they were counted. A brief that forces the implementer to invent a mechanic has failed at its job, and the invented mechanic is unreviewed by definition.

## Why the "wanted to change it" entry matters

`AGENTS.md` requires recording the impulse to improve retrieval before it has been measured. Those are not defects and do not get a numbered entry — they go in the relevant brief's completion notes. But if such a change is *made* before the baseline exists, that is a defect and belongs here, because the change can no longer be shown to have helped.

Entries below, most recent first.

**Historical-status note.** Older entries are preserved as a chronology of the rules and failures
that governed work at the time. Any older statement that G007 reader quality could veto a broader
cohort was superseded by the 2026-07-30 contract event below. Any older statement that a formal run
strictly required a date-suffixed model ID was superseded by the 2026-08-07 catalog-bound exception:
dated immutable snapshots remain preferred, but the exact canonical IDs are permitted when the
catalog observation, requested/returned IDs, settings, response IDs, and limitation are bound.
The 2026-08-07 requirement to stop after ten answers for scorer calibration was superseded
prospectively by the 2026-08-09 event below: the full 37-answer/decomposition baseline now completes
before calibration.
The closed-cue resolution in the first 2026-08-12 entry was itself superseded later that day by
`retrieval-authored-v1`: preserving only three 32-word evidence cards and local cue prose solved
the laundering risk but overconstrained relevance and substance. The older entry remains the exact
record of why that temporary contract existed.

---

## [2026-08-13] V4 sentinel traces inherited a ledger-only colon in `turn_id`
Phase/Brief: Retrieval-authored v4 evaluation, once-only H001-H010 sentinel
Symptom: all ten Professional sentinel outcomes were generated and sealed, but the first
`generate-rest` preflight stopped before H011 because each copied retrieval trace used
`generation:H###` as `scope.turn_id`. The text-free trace contract deliberately rejects colons in
identifiers. Ten priced generation events recorded `$0.458209000`; no H011 artifact or event was
created.
Cause: **measurement-harness specification gap.** The v4 harness reused one colon-delimited string
for both its private ledger turn key and the retrieval trace's restricted identifier field, and
the sentinel command did not run its own post-seal trace check before announcing completion.
Resolution and verification: the ten immutable outcomes are not rewritten or replayed. A clean,
descendant harness can seal one provider-free continuation binding every original outcome and
trace hash to the sole deterministic `generation-H###` normalization, while proving H011 was
untouched. Future generation outcomes normalize that trace-only identifier before sealing, and the
sentinel command now runs all mechanical checks itself. Focused tests cover immutable binding,
normalization without source mutation, H011 boundary protection, and post-sentinel validation.

## [2026-08-13] The v3 authoring deadline collapsed slow calls into opaque fallbacks
Phase/Brief: Retrieval-authored v3 diagnostic cohort and v4 operational boundary
Symptom: seven of 37 once-only Professional generation attempts returned Essential fallback. The
failures clustered around the twenty-second authoring boundary and produced no response metadata or
usage event. Internal diagnostics flattened timeout and unrelated provider/validation failures into
broad codes, while the evaluation harness required a new committed recovery declaration after each
zero-event ambiguity.
Cause: **operational-policy and specification gap.** The 25-second shared allowance left authoring
at most twenty seconds even though successful v3 latency reached roughly that boundary. The product
and cohort protocol had not separately defined stable text-free timeout, transport, provider,
structured-output, and local-validation dispositions or a prospective automatic ambiguity reserve.
Resolution and verification: v3 was terminally closed as a diagnostic after all 37 generation
attempts, 14 decomposition attempts, zero rubric/persona calls, and `$1.591521500` tracked spend;
its H014 reconciliation and closure made zero provider calls. `retrieval-authored-v4` raises the
shared allowance to 35 seconds and authoring cap to thirty while retaining the eight-second
embedding cap, same Sol configuration, strict `/1` schema, 1,800-token ceiling, shared client, and
zero retries. Current diagnostics distinguish `request_timeout`, `transport_failure`,
`provider_exception`, `refusal`, `structured_output_rejected`, and
`local_contract_validation_failed`; reader-facing fallback remains generic. The v4 adapter seals
request identity and exact worst-case cost before each boundary and reserves a zero-event ambiguity
without replay. Focused offline tests and the closed v3 report pass. No v4 live call has run, so
this resolution establishes no latency or reliability improvement.

## [2026-08-13] Character-conversation routing hard-coded two personalities instead of the generated-mode contract
Phase/Brief: Retrieval-authored generated-mode conversation and Ruthless Red Realist
Symptom: after the first personal-conversation repair, asking Professional a basic social question
such as “How are you?” still entered manuscript retrieval and could return Essential fallback.
Adding another generated personality would have repeated the same failure unless its ID was added
manually to the router.
Cause: **spec gap in the brief and mode-specific routing.** The first repair described the desired
behavior through the two character examples then present—Pretty Pink Princess and Baleful Black
Baron—rather than defining social conversation as a capability of every registered generated mode.
The route therefore encoded product IDs instead of deriving eligibility, instructions, and local
fallback behavior from the generated-mode registry.
Resolution and verification: `retrieval-authored-v3` and `character-conversation-v2` derive the
narrow pre-retrieval route from `supported_generated_modes()`. Professional, Pretty Pink Princess,
Baleful Black Baron, and Ruthless Red Realist are registered; Essential has no generated-mode
contract and remains excluded. Each generated definition owns authored instructions, conversational
instructions, and deterministic local fallback copy, so a future registered generated mode inherits
the route without another router edit. The compact route retains one no-retry Sol call, the
12-second timeout, 576-token ceiling, no manuscript/retrieval/history payload, no citations or
historical claims, and selected-character local fallback. The `/1` input and output schemas and
`character-conversation-renderer-v1` remain unchanged because their shapes did not change. The new
Ruthless Red Realist uses wire ID `ember_and_ink`, the existing Ember & Ink appearance, and a
text-free realist-statecraft profile; its high-level Machiavelli/Kissinger inspiration permits no
ingested outside facts, impersonation, imitation, quotation, or attributed doctrine. Offline
contract tests encode registry-derived coverage, Essential exclusion, payload minimization, and
mode-specific fallbacks. No provider call, paid smoke, deployment, latency cohort, quality cohort,
or live verification ran, so this entry makes no post-change performance claim. Repository-wide
Ruff, 1,298 Python tests with one intentional skip, both frontend suites, and the production
frontend build pass offline. V2 and all frozen cohorts remain unchanged historical records.

## [2026-08-13] Character modes had no valid persona-only contract for personal questions
Phase/Brief: Retrieval-authored character conversation
Symptom: asking Pretty Pink Princess a basic personal question such as “How are you?” produced an
Essential fallback saying that no concise manuscript excerpt answered the question. The selected
character therefore disappeared precisely when the user addressed her as a character.
Cause: **spec gap in the brief.** The authored-response contract defined grounded historical
answers, partial answers, insufficient evidence, and a narrow Princess refusal, but no ordinary
persona-only success. `answered` and `partial` required at least one grounded run, while direct
Essential evidence was the universal failure fallback. The design had not distinguished a fictional
social turn from an unsupported factual request. Widening the dossier author to general chat would
also have risked uncited factual drift and wasted an embedding/manuscript retrieval on a question
that required neither.
Resolution and verification: `retrieval-authored-v2` adds a narrow pre-retrieval route only for
Pretty Pink Princess and Baleful Black Baron. The conservative local classifier rejects historical,
manuscript, mixed, long, and uncertain questions. An eligible turn uses
`character-conversation-v1`: one no-retry `gpt-5.6-sol` answer-generation call with low reasoning,
low verbosity, a 12-second timeout, and a 576-token ceiling. It sends no history, embedding, manuscript, retrieved
evidence, dossier, source metadata, or citation. Its `character_reply` output contains fictional
persona conversation and one to three explicit manuscript-leading questions; provider failure,
refusal, or invalid output returns deterministic local dialogue in the same character rather than
Essential. Historical/manuscript questions retain the v1 hybrid/dossier path. Focused offline
contract tests cover routing, near misses, payload minimization, one-call/no-retry behavior,
validation, and all local fallbacks. No live/provider test, deployment, paid latency cohort, or
quality cohort has run, so this resolution makes no post-change performance claim. V1 and every
frozen cohort remain unchanged historical records.

## [2026-08-13] Provider schema permitted grounded prose that the local support contract rejected
Phase/Brief: Retrieval-authored response reliability
Symptom: three of three observed Baleful Black Baron calls and one of three observed Pretty Pink
Princess calls completed at the API, returned substantial structured output, and were then rejected
locally. In each rejected response, a run labeled `grounded` carried an empty support-ID list, so the
reader received the fail-closed Essential fallback despite a completed, billed authoring call.
Cause: provider/local schema mismatch. The root response schema allowed `support_unit_ids` to be
empty or defaulted for every run, while a Pydantic post-parse validator required at least one ID for
`grounded` and no IDs for `persona`. The provider therefore could satisfy the schema it received and
still fail Archivist's stronger local rule. The more frequent interleaving of factual and character
prose made the mismatch especially visible in the Baron, but this was not a timeout, refusal, safety
failure, or absent API response.
Resolution and verification: grounded and persona runs are now mutually exclusive provider-visible
object variants. The grounded variant requires one to eight support IDs; the persona variant cannot
carry any. Local unknown-ID, citation, markup, copying, and rendering checks remain unchanged, as do
the valid wire/render meaning, exactly-one-call/no-retry behavior, and direct-Essential fallback.
Because `retrieval-authored-v1` remained an uncommitted, manually exercised candidate with no formal
cohort, its policy, input/output schema, and renderer identifiers remain version 1; diagnostics bind
the concrete schema hash. Focused strict-schema and local-validation tests verify the repair;
repository-wide Ruff, 1,189 Python tests with one intentional skip, both frontend suites, and the
production frontend build pass offline. No new provider call was made, so live reliability after
the repair remains unproven.

## [2026-08-13] Silent generated-mode fallback was visually misattributed to the selected persona
Phase/Brief: Retrieval-authored reader fallback disclosure
Symptom: a failed Baleful Black Baron or Pretty Pink Princess authoring call returned useful direct
Essential evidence inside the still-selected themed interface, but the answer supplied no visible
indication that persona generation had failed. A reader could reasonably attribute the terse
direct-evidence response to the selected character or conclude that the mode had behaved poorly.
Cause: presentation-contract gap. The server already distinguished an accepted
`retrieval_authored_fallback` result from both an authored success and an ordinary Essential turn,
but the frontend rendered every accepted terminal answer without disclosing that distinction.
Resolution and verification: generated-mode fallback remains fail-closed, cited, and nonfatal; it
does not retry or make another provider call. The browser now uses the existing safe result status
to display a fixed notice above the answer explaining that the requested generated mode could not
be completed and Archivist returned Essential instead. It is headed **Essential fallback** and
says, “Archivist could not complete the {Mode label} AI response, so it returned Essential's direct
manuscript evidence instead.” The notice exposes no exception text, prompt, manuscript passage, or
private diagnostic. Frontend contract coverage distinguishes
fallback from successful generated output and ordinary Essential output. This is a presentation
repair and does not alter retrieval, model input, citations, provider-call count, or the completed
evaluation cohorts.

## [2026-08-12] The closed cue contract made safe structure substitute for a useful answer
Phase/Brief: Retrieval-authored answer redesign
Symptom: manually reviewed answers often repeated three short retrieved excerpts or attached a
generic local editorial sentence without answering the user's precise question in enough depth.
The output could be mechanically valid while still feeling simplistic, thin, or unrelated when
the three excerpts had missed an important aspect of the question.
Cause: design overcorrection. `application-compiled-v1` reduced the model to arranging at most
three 32-word cards and selecting closed cue IDs. That prevented the model from laundering new
factual prose behind a valid card ID, but it also prevented it from synthesizing the broader
retrieval, adapting useful length, or using its language ability to explain relationships.
Resolution and verification: `retrieval-authored-v1` keeps retrieval and citation mechanics local
without keeping prose local. One shared query-embedding call feeds dense/BM25 reciprocal-rank
fusion and the common context finalizer. A deterministic builder packages four to eight whole
chunks or complete paragraph ranges, targeting about 2,500 estimated evidence tokens under a hard
4,500-token evidence limit. Essential skips prose generation but still uses the embedding call.
Each generated mode gets exactly one no-retry low-reasoning, medium-verbosity `gpt-5.6-sol` call,
with at most 1,800 output tokens, to author free prose and one to three follow-up questions. The
embedding and authoring operations now share a 25-second provider deadline instead of each owning
an independent 30-second timeout; authoring is skipped in favor of direct evidence when its
remaining allowance is exhausted. Local
validation maps existing opaque support IDs to `[Source N]`, rejects malformed output, and falls
back to Essential; it does not claim to prove semantic entailment. Focused offline dossier,
renderer, pipeline, identity, and public-contract checks own the mechanical verification. No live
provider call or paid latency/quality test has run, so this resolution closes the implementation
defect but establishes no speed, quality, or reliability result. Frozen V26, V27, production-
performance v1, and the earlier cue-selector smoke are unchanged. The complete offline gate passed
repository-wide Ruff, 1,186 Python tests with one intentional skip, both frontend suites, and the
production frontend build.

## [2026-08-12] A valid card ID could have laundered invented factual prose
Phase/Brief: Application-compiled answer and prose-rendering contract
Symptom: the requested prose boundary allowed a generated segment to name an admitted evidence-card
ID while also supplying its own factual-looking sentence. Application code could then have attached
the card's valid `[Source N]` citation to model-authored text, making an invented or altered claim
look mechanically grounded even though the cited card text never said it.
Cause: specification gap. The brief correctly reserved evidence selection and citation numbering to
the application but did not specify whether a valid card ID authorized the prose model to rewrite
the card. That omitted mechanic would have conflated evidence ordering with factual authorship.
Resolution and verification: evidence segments now accept only the exact immutable
`<use-evidence-card>` placeholder and one known card ID. The application replaces that placeholder
with the frozen bounded card text and locally owned citation. Interpretation and character-aside
segments cannot carry card IDs or authored prose; they contain only typed, mode-bound cue IDs whose
distinct text and labels are owned by local code. Unknown/omitted cards, model-written citations,
raw prose, cross-mode cues, and invalid editorial shapes fail the one-call selection contract and trigger direct cited-evidence fallback
without retry. Focused offline renderer and application-pipeline tests cover immutable substitution,
labeling, failure fallback, exactly-one-call generated modes, and Essential's zero-provider path.
The current product transition also removed the V26/V27 reader selector: frozen V26 remains an
explicit immutable development/evaluation policy, and V27 remains an unpromoted historical
experiment superseded by `application-compiled-v1`. Essential plus Full Context is rejected so its
zero-provider contract is unambiguous. Production-performance v1 is unchanged. After exact owner
authorization, a bounded three-mode smoke produced three valid closed-cue responses with no retries,
but its one-question scope carries no latency or quality-improvement claim.

## [2026-08-12] Provider-authored redundant ledgers are a latency and reliability liability
Phase/Brief: Post-production latency optimization
Symptom: the sealed production cohort observed 54.393-second server p50 and 113.801-second p95
across 29 valid completions. Its four request failures all occurred after successful planning and
direct-answer evidence selection when the generated structured payload violated one of three
relational release checks: two `missing_unit_requirement_id`, one `obligation_role_mismatch`, and
one `unsupported_requirement_has_unit`.
Cause: generation-contract design hypothesis under investigation. The provider is asked to author
relationship ledgers that repeat information already implied by answer units and trusted request
context, so generation spends tokens on redundant structure and independently produced views can
disagree. The cohort does not prove that redundancy caused the four failures. Provider-owned
statuses, requirement links, and obligation roles can remain semantically incompatible even after
local derivation. The existing terminal validator correctly fails closed; weakening it would hide
rather than repair the defect.
Resolution and verification: implemented and offline-verified a universal representation-only
candidate in `docs/latency_optimization.md`. Under V27, every eligible generated answer uses the
compact provider contract, and deterministic local code expands it into the same canonical object
consumed by the unchanged validator and renderer. Equivalence, malformed-input, trace, and pipeline gates pass; repository-
wide Ruff, 1,022 pytest tests with one intentional skip, both frontend test suites, and the
production build also pass. Synthetic serialization measurements reduce the neutral and
interpretive schemas by 14.51% and 19.68%, and representative neutral and interpretive payloads by
21.06% and 15.05%. This entry is **not closed**: those are representation measurements, the
candidate does not itself eliminate the three semantic defect classes, no paid candidate call has
run, no provider latency or reliability improvement has been measured, and the candidate is not
promoted. Promotion requires the separately authorized paired G001-G010 A/B, including a
paired median generation-latency ratio at or below 0.70, preserved release reliability and
development quality, 100% citation resolvability, and zero malformed citations. Frozen V26 and
production-performance v1 remain unchanged.

## [2026-08-12] Opening-page advanced settings were clipped below the viewport
Phase/Brief: Public reader usability after the production cohort
Symptom: on the opening page, expanding the reading options and their advanced disclosures could
place the lower controls below the visible page with no usable route to scroll them into view.
Cause: presentation defect. The landing settings panel was absolutely positioned beneath the
composer inside a section with clipped overflow. Its own bounded scroll area extended beyond that
clipping ancestor, and because it was outside normal flow it could not make the page taller.
Resolution and verification: the landing disclosure now remains in normal document flow and uses
ordinary page scrolling; only the docked conversation version remains an overlay with its own
viewport-bounded scrolling. The docked height calculation now uses the dynamic viewport and safe
area. Frontend delivery/mode tests and the production build pass. This repair changes no model or
evaluation behavior.

## [2026-08-11] Production cohort preserved four request failures in the denominator
Phase/Brief: Production observability and resume-claim evidence
Symptom: the fixed live cohort attempted all 33 predeclared requests and produced 29 valid
successful completions plus four request failures, an all-attempt failure rate of 12.1212%. No
request was retried or replaced. The observability path itself produced zero instrumentation
failures.
Cause: all four failures occurred after successful planning and a `direct_answer` evidence decision,
when structured generation failed its relational release contract. Two were
`missing_unit_requirement_id`; one was `obligation_role_mismatch`; one was
`unsupported_requirement_has_unit`. None was a retrieval-availability, budget, transport,
deployment-boundary, or telemetry failure. The generation contract correctly refused to release
the invalid mappings, but only after the expensive planning/generation path had completed.
Resolution and verification: preserve the sealed outcomes and publish the observed denominator
unchanged. Server p50/p95 are 54.393/113.801 seconds across the 29 successful completions; client
p50/p95 are 54.493/113.829 seconds. The text-free public summary records 33 attempts, four failures,
zero instrumentation failures, 500,164 tokens, 80 priced and zero unpriced events, and
`$4.90594694` estimated cost. Repair the three relationships with synthetic contract regressions,
then measure any improvement only in a separately versioned cohort. Do not silently infer or repair
semantic requirement/role mappings, and do not overwrite this run. These are cohort observations,
not an SLA or generalized reliability claim. On 2026-08-12 the universal compact
provider-contract candidate above became an implemented, offline-verified latency experiment: it
derives redundant mappings locally before applying the same validator. It does not itself eliminate
these semantic defects. The production defect remains open until later work and a separately
authorized comparison demonstrate the result; passing offline checks alone does not close it.

## [2026-08-10] Runner-only cost reserve did not bound one live public RAG request
Phase/Brief: Production observability and resume-claim evidence
Symptom: the prepared cohort initially used a fixed `$1.00` runner-side next-attempt reserve, but
the public server had no matching versioned per-request contract. A single request could therefore
cost more than the runner assumed. A client transport failure without a correlated observation
could also be mistaken for zero spend, a contract-valid 2xx response with zero recorded usage could
enter the latency sample, and a stale conversation/turn scope could collide with a prepared attempt.
Cause: safety boundary mismatch. Cohort authorization, server admission, operation-level cost
projection, request-scoped usage, and deployment identity were not yet one closed contract.
Resolution and verification: the public Complete-RAG path now owns
`public-rag-request-ceiling-v1`, a `$2.00` maximum exposed by `/api/version`. The service checks the
full maximum against its monthly budget before RAG, projects every provider operation before send,
and fails closed on missing, duplicate, unpriced, or over-ceiling usage. The prepared manifest,
authorization, and runner bind the deployed ceiling version and amount. Before each next attempt,
the runner requires headroom for the full maximum; an unknown transport attempt is sealed without
replay and permanently consumes `$2.00` in conservative authorization accounting. A successful
zero-usage response is an instrumentation failure and latency-ineligible. A pre-existing request
scope is rejected before intent creation or POST, and Render's `RENDER_GIT_COMMIT` is authoritative
when present. Offline tests cover these contracts. The 2026-08-11 live cohort then completed all 33
attempts with 80 priced and zero unpriced events, exact estimated cost of `$4.90594694`, and zero
instrumentation failures, confirming that request-scoped usage remained measurable throughout the
cohort.

## [2026-08-10] Production-latency cohort lacked a fixed attempt denominator
Phase/Brief: Production observability and resume-claim evidence
Symptom: the roadmap called for "30-50 successful warm first turns" while also asking for an error
rate. It did not say whether failed requests would be replaced, what made a request warm, where the
latency clock began and ended, how p95 was calculated, how instrumentation failures differed from
application failures, or how the paid cohort reserved room beneath its cost cap. Those omissions
could have produced a success-only latency sample, a survivor-biased error denominator, and a run
whose result could not be reproduced.
Cause: spec gap in the brief. The proposed resume number had a target shape before the production
measurement protocol had computable mechanics.
Resolution and verification: `docs/production_performance.md` now fixes the cohort at exactly 33
attempted answerable held-out items, with no retry or replacement; fresh sequential Essential,
Complete-answer RAG first turns with empty history; process-identity and readiness checks without a
paid warm-up; a 12-second minimum interval between request starts; an ingress-through-complete-
response server-latency boundary; median p50 and nearest-rank p95 over explicitly counted valid
successful completions; error rate over all 33 attempts; separate instrumentation-failure
accounting; a predeclared cost cap bound to the server's versioned $2.00 per-request maximum; and
text-free public artifacts. The runner and offline tests implement those rules. The authorized
2026-08-11 cohort then preserved exactly 33 attempts without retry or replacement: 29 valid
successes, four request failures (12.1212%), and zero instrumentation failures. Its server
p50/p95 were 54.393/113.801 seconds across the 29 successes.

## [2026-08-09] Canonical decomposition instrument yielded only 10 usable readings from 37 attempts
Phase/Brief: Phase 1, Briefs 5–7 held-out answer-quality evaluation
Symptom: the frozen V26 baseline completed with exactly 37 answer-only `gpt-5.6-terra`
decomposition attempts, but only ten produced usable canonical decompositions. Twenty-six completed
outputs failed the exact answer-substring/character-span invariant and H029 produced one terminal
`incomplete_response`. The claim-derived portion of the report therefore contains 41 claims from
ten schema-valid outcomes, but two are zero-claim generation-error records: those claims cover only
eight substantive releases. These 27 technical outcomes are measurement-instrument failures; they do
not establish that V26 failed 27 answers.
Cause: the pinned Terra decomposition instrument did not reliably satisfy its exact-span output
contract. The harness correctly refused to realign spans, parse nonexistent output, fabricate empty
claim sets, or retry after seeing held-out results. Consequently, mechanically valid claim-derived
metrics have a much narrower evidence base than the 37-item answer cohort.
Resolution and verification: preserve recovery-04 and its result as the complete descriptive
baseline. It closes with all 37 answer artifacts, 37 unique Terra attempts, ten usable
decompositions, 26 `exact_span_mismatch` outcomes, one `incomplete_response`, 125 priced events,
zero unpriced events, and `$7.02298147` cumulative cost. Answer-level citation syntax measures keep
their full applicable denominators; decomposition-dependent measures explicitly use only ten.
Diagnose and prospectively redesign the decomposition instrument in a new measurement cohort rather
than changing or rerunning this baseline. Semantic calibration remains optional, lower-priority
supplemental work and cannot erase this limitation.

## [2026-08-09] Terra returned H029 incomplete without output
Phase/Brief: Phase 1, Briefs 5–7 held-out answer-quality evaluation
Symptom: recovery-03 preserved all 37 frozen V26 answers and reached 28 of the 37 contracted
answer-only decomposition attempts. H029's one `gpt-5.6-terra` call returned provider status
`incomplete` with an empty output. It used 923 input tokens, 8,000 output tokens, all 8,000 as
reasoning tokens, and 8,923 total tokens; the call cost `$0.1223075`. The harness stopped before
H030. The exact ledger now contains 116 priced events, `$6.80227647` cumulative spend, and zero
unpriced events.
Cause: a terminal provider-declared incomplete response from the measurement instrument, not a
candidate-answer defect and not parseable decomposition evidence. Retrying H029 would violate the
one-attempt contract, while treating its empty output as a claim set would fabricate a reading. The
existing response `resp_04c5799aa1b46c76006a78a779f5e8819f84b2edbf39a416c5` was retrieved by
exact ID without another model call and preserved privately with SHA-256
`84503bc1cd861bafc09cb33bbe32f581ee56a63ed15c66e8d5ccb7562d1d8617`.
Resolution and verification: recovery-03 remains unchanged. One provider-free recovery-04 migration
sealed H029 as technical `incomplete_response` alongside the 27 earlier outcomes, after which the
resume made exactly the nine previously untouched calls H030–H038. H029 was not retried, parsed from
empty output, or attributed to the candidate answer. Recovery-04 closes with all 37 answer
artifacts and exactly 37 Terra attempts; the ledger contains 125 priced events, `$7.02298147`
cumulative spend, and zero unpriced events. A future exact `incomplete` status may be sealed and
followed by the next untouched item; unknown statuses, provider or network failures, model-identity
mismatch, missing parse, and an unavailable citation number still stop fail-closed. This narrowed
the earlier H002 rule without authorizing a retry, fabricated parse, semantic judgment, gold change,
or candidate repair.

## [2026-08-09] Terra repeated the exact-span instrument failure for H002
Phase/Brief: Phase 1, Briefs 5–7 held-out answer-quality evaluation
Symptom: after provider-free recovery-02 sealed H001 as a technical decomposition failure, the
authorized resume skipped H001 and made exactly one Terra call for H002. That call completed and
was charged `$0.0375875`, but four of six returned claim strings did not exactly equal the frozen
answer substrings at their declared spans. The harness stopped before H003. Recovery-02 now holds
90 provider events and cumulative recorded spend of `$5.46195397`.
Cause: the same class of measurement-instrument/model-output contract failure seen on H001, now
demonstrating that a harness which stops for bespoke recovery after every known local span failure
cannot complete the authorized no-retry cohort. This is not evidence that either candidate answer
is defective. The response was retrieved by exact response ID without another model call and
preserved privately with SHA-256
`5dc006d3de7f2ae64f4aea1db76907c0cbda2f9b60ee060ffb3edac1eff42c0d`.
Resolution and verification: do not repair or retry H002. Preserve recovery-02 unchanged and make
one provider-free recovery-03 migration that binds both prior technical failures and every existing
usage event. For the remaining 35 items, seal and continue past only four predeclared, mechanically
reproducible post-parse failures: nonsequential claim IDs, out-of-bounds spans, overlapping or
out-of-order spans, and exact-substring mismatch. Any provider, network, incomplete-status,
model-identity, missing-parse, unavailable-source-number, or unknown failure still stops
fail-closed. A durable pre-call intent prevents an ambiguous interruption from becoming a duplicate
call. Final closure requires exactly 37 Terra attempts, unique response IDs, exact ledger-to-outcome
agreement, and `N` valid decompositions plus `37 - N` disclosed technical failures. Failures are
excluded only from decomposition-dependent denominators and never count as candidate-answer
failures.

## [2026-08-09] Terra returned an invalid canonical claim-to-span mapping for H001
Phase/Brief: Phase 1, Briefs 5–7 held-out answer-quality evaluation
Symptom: after the audited H003 recovery, the unchanged run sealed all 37 frozen V26 answers and
began canonical decomposition. The first and only Terra call, for H001, completed and was charged,
but strict validation found that several returned claim strings did not exactly equal the frozen
answer substrings at their declared character spans. The harness stopped fail-closed before H002.
Cumulative recorded spend is `$5.42436647`.
Cause: measurement-instrument/model-output contract failure, not a candidate-answer defect. The
judge returned structurally parseable JSON but violated the exact `text`/`char_span` audit
invariant. Accepting approximate offsets or silently realigning the claims would change the
measurement after seeing the held-out output.
Resolution and verification: do not repair the returned spans or text, do not retry H001, and do
not promote its output as a canonical decomposition. The completed provider response was retrieved
by exact response ID through `responses.retrieve`, which made no model call, and preserved in a
private snapshot bound by SHA-256
`dd6ca585e3d1f8fac6af4070187b0230115ded0482837c23b4f12beda82c1f1e`.
Leave the answer-complete recovery root immutable. An exact provider-free sibling migration must
bind the 37 answer checkpoints, cohort, ledger, H001 response ID and usage, retrieved snapshot,
answer and prompt hashes, validation failure, runners, and both roots. It records H001 as one
technical decomposition failure and resumes only H002–H038's 36 missing Terra calls under the same
cumulative `$20.00` cap. Final closure requires 37 sealed answers, 37 attempted canonical calls,
36 valid decompositions, one technical failure, and unique response IDs. H001 is excluded only from
decomposition-dependent denominators; it is not imputed as zero claims and not scored as an answer
failure. This repairs the harness's representation of an instrument failure, not V26 or H001.

## [2026-08-09] Harness rejected H003's valid deterministic early release
Phase/Brief: Phase 1, Briefs 5–7 held-out answer-quality evaluation
Symptom: the authorized run sealed H001 and H002. H003 then made one embedding call, produced a
trace-backed deterministic `clean_abstention`, and correctly skipped answer generation. The harness
rejected that valid early-release artifact shape and stopped fail-closed. It made no retry and no
H003 answer-generation call. Cumulative recorded spend at the stop is approximately `$0.2957022`.
Cause: implementation defect in the run-of-record harness. Its resume/checkpoint assumptions
covered provider-generated answers but did not admit the production RAG's valid locally released
clean-abstention path, even though the trace and usage ledger were sufficient to prove the outcome.
Resolution and verification: preserve the original partial root byte-for-byte and migrate only
through the exact provider-free recovery command into a distinct sibling root. The migration audit
binds source/destination runners, manifests, ledger events, and artifact hashes; H001/H002 retain
unchanged inner generated-item payloads; H003 is explicitly reconstructed from the exact sealed
trace, with no provider replay. Resume begins at the first missing operation under the same
cumulative `$20.00` cap. H003's likely false abstention remains evaluation behavior, not a repair
target. Its unavailable full-turn latency is not imputed: the final latency denominator is 36/37,
and the public summary/report bind the migration artifact and disclose the trace-recovered item.
This exact fail-closed recovery is compatible with the uninterrupted-cohort rule because it changes
no V26 behavior, prompt, model, retrieval, corpus, gold, calibration state, or prior provider output.

## [2026-08-09] Contract event: scorer calibration still interrupted the held-out baseline
Phase/Brief: Phase 1, Briefs 5–7 held-out answer-quality evaluation
Symptom: although the August 7 amendment removed calibration as a quality veto, the declared run
still generated ten answers, stopped for owner labeling and scorer qualification, and only then
allowed the remaining 27. In practice, a lower-priority scoring-instrument task still stood between
the owner and the complete evaluation result.
Cause: owner-authorized contract correction before any held-out answer-quality generation. The
previous repair changed the consequence of failed calibration but retained calibration as an
operational prerequisite for most of the cohort.
Resolution and verification: the next substantive paid operation is now one uninterrupted pass
that generates and canonically decomposes all 37 frozen V26 answers and preserves their sources,
traces, usage, and immediately computable metrics. Calibration occurs only afterward and may add a
hash-bound semantic-scoring supplement; its absence or failure leaves affected metrics pending and
cannot delay, overwrite, rerun, or suppress the baseline. No RAG, prompt, retrieval, model, UI,
gold, or corpus change may intervene within the pass. This amendment was made before any held-out
answer had been generated, so it invalidates no answer-quality result; the completed retrieval-only
diagnostic remains valid.

## [2026-08-07] Contract event: scoring calibration could have become a second gate
Phase/Brief: Phase 1, Briefs 5–7 held-out answer-quality evaluation
Symptom: the roadmap placed citation, faithfulness, and abstention calibration ahead of the full
held-out answer run without stating whether those answers belonged to the final cohort, what would
happen if the automatic judge failed calibration, or whether an unmeasured generator noise floor
could postpone the first baseline. The run-identity rules also required dated model snapshots even
though OpenAI's catalog currently exposes only canonical `gpt-5.6-sol` and `gpt-5.6-terra` current-
snapshot IDs for the selected roles.
Cause: owner-authorized contract clarification before any held-out answer-quality call. The prior
wording allowed a ten-item calibration to become a disposable pilot or quality veto and imposed a
provider capability the selected official model catalog does not currently offer.
Resolution and verification: the fixed ten calibration answers are now the first ten members of
the same 37-item frozen V26 cohort. Once the scoring instrument is locked, the remaining 27 run
immediately with no intervening RAG, prompt, retrieval, model, or UI repair. Failure of automatic
judge agreement selects manual scoring for affected dimensions or an explicit pending result; it
does not block cohort completion. The first 37-item answer result is descriptive, with exact
denominators and an explicit unmeasured-generator-spread limitation; five-repeat noise measurement
is required before later comparative or significance claims. Formal identity now binds the
committed provider-catalog observation, requested and returned model IDs, settings, and response
IDs, and states the canonical-ID reproducibility limitation rather than inventing dated snapshots.
The earlier retrieval-only diagnostic remains a separate valid measurement. No paid or external
call occurred during this implementation work, and no held-out answer-quality result existed to
invalidate.

## [2026-08-07] Contract event: retrieval comparison was not executable as written
Phase/Brief: Phase 1, Brief 4 held-out retrieval benchmark
Symptom: the roadmap required a dense-versus-BM25/RRF comparison, while the locked retrieval
section defined only raw `collection.query` sets. It did not define the Hybrid arm, the treatment
of empty relevance sets, the macro comparison statistic, or the fixed ten-item noise subset. It
also described an older context order in which neighbours could displace later primaries even
though the frozen finalizer now reserves primaries first.
Cause: owner-authorized contract correction before the first held-out retrieval run. The benchmark
brief and contract had been written at different stages of the retrieval implementation, leaving
the implementer to invent mechanics unless the gap was closed prospectively.
Resolution and verification: §4 now defines raw dense and existing BM25/dense RRF arms, requires one
cached query embedding per locked item for both arms and all repetitions, declares macro Recall@5
over non-empty relevance sets as the comparison statistic, makes empty-relevance denominators
explicit, and fixes a stratified ten-item/five-repeat noise protocol. A committed text-free runner
enforces the frozen gold/candidate/corpus identities, clean-tree boundary, single no-retry OpenAI
embedding operation, local reuse, and non-overwrite behavior. Synthetic tests cover cache binding,
provider-index validation, one-vector-query reuse, denominators, both arms, aggregate and
per-stratum noise spread (including the declared comparison delta), fixed repetition membership,
pre-spend output rejection, finite cost ceilings, and text exclusion. The active local
481-chunk `l2` index passed the offline integrity preflight; the query-embedding cache remains absent.
Repository-wide Ruff passed, 784 Python tests passed with one intentional skip, both focused
frontend suites passed, and the production frontend build completed successfully.
No H-item reached the retriever, no held-out content was sent externally, no paid call was made,
and no earlier formal result exists to invalidate.

## [2026-08-06] Contract event: historical annotation assistance disclosed retrospectively
Phase/Brief: Phase 1, Brief 3 held-out gold authoring
Symptom: the completed owner-review workbook contained annotations that began as Claude drafts,
but the fresh blinded workflow then required by provenance v3 had never been run. Treating the
existing work as prospectively blinded would have invented a raw-draft record, model/surface
metadata, and pre-assistance commitment that do not exist; discarding the owner-adjudicated work
and repeating it would create process theater rather than stronger ground truth.
Cause: owner-authorized contract correction before the first formal held-out run. The prior rule
mistook a preferred prospective annotation process for the only honest way to preserve
candidate-independent owner adjudication.
Resolution and verification: provenance advances to `archivist.gold_provenance/4`. It records the
method as owner adjudication with historical AI drafting, marks the complete raw-draft and
prospective-blinding records unavailable, and requires an explicit limitation plus an owner
attestation that no prospective-blinding claim is being made. The owner-authored question
commitment still must predate every candidate-system exposure. The synchronized private DOCX/JSON
retains the completed annotations; two accurate claims responsible for three copied-language flags
were paraphrased without changing essentiality or source bindings. The run-of-record schema,
location, overlap, and privacy audits pass with zero privacy flags. No H-item reached Archivist and
no external or paid call was made. No formal result existed to invalidate.

## [2026-08-06] Contract event: held-out annotation adopted a practical scoring standard
Phase/Brief: Phase 1, Brief 3 held-out gold authoring
Symptom: the authoring materials treated rigor as requiring polished user questions, clause-level
claim splitting, cosmetic rewriting of source-verified AI drafts, and potentially expansive
`must_not_claim` lists. That made owner review needlessly dense and risked turning the benchmark
into a test of ideal prompts rather than realistic questions.
Cause: owner-authorized contract correction before the first formal held-out run. The previous
instructions conflated independently scorable expectations with grammatical clauses and confused
owner adoption with owner rewording.
Resolution and verification: realistic questions may now remain awkward, compound, ambiguous, or
premise-faulty when their scoring intent is stable. Claims are grouped into the smallest useful
independently scorable units; necessary background may be essential, optional, or relevant;
`must_not_claim` is optional, non-exhaustive, and reserved for a few high-value tripwires. The
owner may adopt or revise source-verified draft prose without performative paraphrase. Relevant
locations remain complete within the owner-declared scoring scope. Provenance advances to
`archivist.gold_provenance/3`, and the prompt, prompt hash, template, validator, tests, authoring
guidance, and owner-review workbook were updated together. No formal held-out run exists, so no
formal result was invalidated; practical runs remain development evidence only. Focused offline
verification passed 64 tests and Ruff. Complete offline verification then passed repository-wide
Ruff, 768 Python tests with one intentional skip, both focused frontend suites, and the production
frontend build. No model or paid API call was made.

## [2026-08-05] Contract event: blinded AI drafts became permissible, not authoritative
Phase/Brief: Phase 1, Brief 3 held-out gold authoring
Symptom: the owner-only annotation rule made a forty-question benchmark unnecessarily laborious,
even though the owner had already written the questions and proposed reviewing a separate model's
evidence annotations manually. The old provenance attestation would also have falsely described
AI-drafted claims and locations as entirely owner-authored.
Cause: owner-authorized contract change before the first held-out run. The contract had conflated
who designs the exam and holds ground-truth authority with who may prepare an unverified evidence
draft.
Resolution and verification: §3.1 now keeps questions, strata, Behavior values, and inclusion
decisions exclusively owner-authored while allowing Claude to draft claims, essentiality,
support/relevance locations, prohibited claims, and notes under a candidate-output blind. Every
field still requires independent source-level owner adjudication and accepted prose must be
rewritten. Provenance advances to `archivist.gold_provenance/2`, binds a pre-assistance question
fingerprint plus prompt/private-draft hashes, and replaces the obsolete authorship attestation.
The privacy audit now covers questions, prohibited claims, and notes as well as claims. No formal
held-out run exists, so no formal score was invalidated; older practical runs remain development
evidence only. The current H020 replacement is still a strong near-match to registered development
item `DEV-MANUAL-008` and therefore blocks question freeze until the owner replaces it again.
Offline verification passed all 768 Python tests with one intentional skip and Ruff; the private
question form parses as 40 items in the contracted 8/8/6/10/5/3 stratum distribution. No model or
paid API call was made.

## [2026-08-05] Terminal ledgers delayed the first Progressive claim
Phase/Brief: Phase 1 presentation and public-demo operations
Symptom: after genuine checked-claim streaming replaced the earlier reveal animation, a live test
still showed no answer prose for most of the request and then delivered nearly the entire answer
in a few quick pieces near the end.
Cause: model-contract ordering and a reader-feedback gap. The Structured Output schemas asked the
model to serialize private premise, coverage, and obligation ledgers before the factual claim
array, so no complete claim object existed to release during most of generation. The browser also
discarded heartbeat frames, leaving valid upstream work visually silent. This repair changes the
shared generation contract and therefore opens new cohorts; it is not evidence of a RAG-quality
gain and changes no gold or evaluation contract.
Resolution and verification: the shared Evidence Coverage and Full Context schemas now place
factual claims immediately after the schema identifier and terminal-only ledgers afterward for
both Complete and Progressive, opening `evidence-coverage-v11` and
`full-context-coverage-v3`. A Progressive-only local lead gate releases only a direct,
subject-linked factual sentence of at most 45 words; premise corrections and interpretive framing
remain withheld until terminal validation. Three-second text-free heartbeats now drive a visible
elapsed indicator. One private text-free timing record measures stage entry, first provider delta,
first checked claim, provider terminal, terminal outcome, worker finish, and stream finish, and
no-cache/no-transform headers reduce avoidable proxy buffering. Corpus-integrity checks were not
cached because a cheap cache could miss same-metadata content changes. Offline verification is
Ruff clean with 760 Python tests passing and one skipped, both focused frontend suites passing,
and a successful production build. No paid OpenAI call was made; a deployed custom-domain versus
direct-Render smoke remains required.

## [2026-08-04] Progressive response animated a finished answer instead of streaming it
Phase/Brief: Phase 1 presentation and public-demo operations
Symptom: a live reader test spent nearly the entire request on the initial “Drafting” state, then
revealed an already completed answer quickly. The option was technically streamed transport, but
it did not improve time to first useful prose and therefore did not satisfy the intended
answer-built-over-time experience.
Cause: spec gap and implementation mismatch. The first contract resolved the ambiguity in favor
of never showing prose that might later fail whole-answer validation. That retained the Complete
mode guarantee, but made meaningful same-request answer streaming impossible and was not what the
reader meant by progressive delivery.
Resolution and verification: protocol v2 replaces post-validation answer deltas with complete
structured factual claims extracted during the existing final Responses API generation. Each
claim crosses the boundary only after local shape, order, citation, source, size, and (in public
mode) locator and rolling quotation checks. Claims are labeled partial and are kept out of
conversation history, copying, sources, and citation controls. The unchanged whole-answer
validator remains authoritative: success replaces the working claims with the canonical answer;
late failure or interruption clears them. Complete answer remains the strict default and retains
the stronger no-rejected-prose guarantee. This is one streamed final-generation request, not an
additional model call; upstream planning, embeddings, and retrieval are unchanged. Offline
verification closed with 749 Python tests passing and one skipped, Ruff clean, both frontend
behavior suites passing, and a successful production build. It covers transport, local gates,
terminal usage accounting, public disclosure, retraction, and client failure behavior. A live
Render smoke is still required to measure actual first-claim timing and proxy buffering.

## [2026-08-04] Progressive delivery lacked a release and stream-lifecycle contract
Superseded note: this entry records the original post-validation protocol. The newer defect entry
above defines the protocol-v2 checked-claim behavior.
Phase/Brief: Phase 1 presentation and public-demo operations
Symptom: the requested progressive-answer option did not specify whether generated prose could be
shown before evidence and privacy validation, which progress details were safe to expose, when an
accepted request could be retried, or how long the process-local public concurrency gate owned a
streaming request.
Cause: spec gap in the brief. The implementer otherwise had to invent a transport, trust boundary,
retry policy, and concurrency lifecycle for a feature presented as a UI option.
Resolution and verification: `docs/answer_delivery.md` now makes Complete answer the recommended
default and defines Progressive response as a presentation-only mode over the identical RAG run.
Only fixed operational progress may precede validation; chain-of-thought and drafts remain private;
answer deltas begin only after grounding, quotation/privacy, and public-source release gates pass.
The public transport is a same-origin NDJSON POST with one terminal frame, no automatic replay
after acceptance, and a concurrency slot held through completion or disconnect cleanup. The
document also defines offline invariants and a required live Render smoke. The mode remains
Experimental until those checks pass; no latency reduction is claimed.

## [2026-08-04] Six visual themes became Phase 2 interpretive modes
Phase/Brief: Phase 2 perspective-mode prototype advanced beside the frozen Phase 1 Essential path
Symptom: Pretty Pink Princess, Baleful Black Baron, Tidal Archive, Ember & Ink, Illuminated Codex,
and Cosmic Almanac existed as appearance-only choices, but their names implied answer character
that the application did not actually apply.
Cause: Phase 2 concern in Phase 1 work plus six mode-specific prompt cohort openings. The owner
deliberately requested strong semantic behavior: rose-tinted optimism, severe tragedy,
Moby-Dick-informed maritime framing, Kissinger-associated realist statecraft, and lowercase-l
modern liberal history, followed by a systems-minded future-science perspective.
Resolution and verification: promoted the six appearances to allowlisted, versioned semantic
modes while leaving omitted-mode and explicit Essential behavior unchanged. Influence is inserted
only after retrieval and cannot enter Chroma, source admission, citations, premise handling, or
absence decisions. Princess explicitly may not suppress harm; Baron may not invent tragedy; Tidal
uses a frozen public-domain Project Gutenberg #15 provenance record but may not quote, paraphrase,
imitate, or import literary content; Ember uses a text-free project editorial profile and no
Kissinger work is ingested, quoted, paraphrased, imitated, cited, or treated as evidence; Codex
must treat liberal progress as contested rather than automatic and may not become present-day party
advocacy; Almanac may discuss plausible future implications only as explicit uncertainty and may
not invent predictions, science fiction, teleology, or anachronistic scientific claims. Focused
backend tests, the focused frontend mapping test, and the complete offline suite establish those
mechanical boundaries. Reader-facing perceptibility and groundedness remain unconfirmed until
separate paid style smokes; none of these modes may be used as evidence about Essential or the
held-out gold cohort.

## [2026-08-04] A neutral comparison was misrouted as a disputed premise
Phase/Brief: Phase 1 Answer Mode, live reader test after semantic mode deployment
Symptom: the question asking how the book explains nineteenth-century versus twentieth-century
recessions retrieved evidence and generated an answer, then failed after 58.148 seconds and an
estimated `$0.19791642` with `premise_provenance_mismatch`. The deterministic validator took
0.604 milliseconds; planning and generation consumed essentially all latency and spend.
Cause: model error in application routing plus a prompt cohort opening. The factive-question regex
treated the noun phrase `cause of` as the causal verb `cause`, while `versus` had no bounded local
comparison decomposition. The system therefore invented support/counter/framing premise lanes for
a neutral comparison. The generation prompt also described those lanes without stating the
validator's exact subset rules.
Resolution and verification: opened `evidence-planned-v26` and `evidence-coverage-v10`. A
corpus-agnostic bounded grammar now decomposes `dimension of topic in A versus B` into both sides
and an explicit contrast, preserves the nominal phrase in retrieval queries, and skips the paid
planner only for the exact locally resolved route. Ambiguous, broad, or oversized forms defer to
the planner. Genuine `How did X cause Y?` questions retain premise checking. The strict provenance
validator was not weakened; its source-lane predicates are now explicit in the generation prompt.
The complete offline suite passed 693 tests with one intentional skip, Ruff passed, and the
production frontend built. No provider call was made for the repair.

Governance consequence: the failed question was H020 in the private authoring workbook. Because it
was submitted to Archivist and directly shaped this repair, it is now `DEV-MANUAL-008` in
development registry `1.1.0` and is permanently ineligible for the genuinely held-out gold set.
The unattested provenance template was rebound to the updated registry hash; H020 needs a fresh
owner-authored replacement before gold lock.

## [2026-08-01] Full-context v1 trusted its own completeness and absence assertions
Phase/Brief: Phase 1 full-context answer strategy, review after the first paid G007 debugging run
Symptom: the live answer self-reported `valid_complete`, while subsequent strict manual grading
found 1/7 essential claims and 4/5 target groups. Version 1 also accepted model-authored absence
subjects and prose, allowed a zero-claim insufficiency answer without application proof, treated any
eligible chunk ID as enough even when it did not directly support a named target, and permitted the
premise correction ID to point somewhere other than the correction-role claim.
Cause: contract implementation gap plus spec gaps. The design correctly separated cited chunks
from the full corpus, but still treated the model as the authority on whether it had read enough of
that corpus. It specified an absence cross-check as a downgrade rather than a fail-closed evidence
contract, and it did not define application-owned target or completeness ledgers.
Resolution and verification: opened the independent `full-context-v2` cohort without changing RAG
V25. Application-issued target IDs now bind absence findings; exhaustive strong and weak direct
matches own presence; certified absence owns absence; direct targets require a cited direct-hit
chunk; and zero-claim insufficiency is valid only when every trusted target is certified absent and
bound. When no audited target has direct manuscript evidence, any nonempty claim is rejected as an
unsolicited analogue until an application-owned analogue contract exists; non-certifiable
resolver-restored targets do not weaken that rule. Absence prose is deterministic application text.
Premise correction now has an exact
one-claim/one-ID/first-position contract. Nonempty answers are capped at `valid_partial` until an
application-owned requirement ledger exists. Response, prompt, renderer, policy, and diagnostic
schema identities were versioned consistently. Focused full-context and compatibility suites
passed; no provider call was made.

## [2026-08-01] The public quotation guard audited only cited full-context chunks
Phase/Brief: Phase 4 disclosure boundary review performed while the public full-context flag remains
disabled
Symptom: a full-context model sees every eligible private manuscript chunk but returns only cited
chunks. The public 45-word overlap guard inspected that returned list, so a response could copy a
long passage from an uncited chunk and evade the check by omitting the citation.
Cause: spec gap in the design. Converging full-context output to RAG's cited-only `final_chunks`
shape was correct for disclosure, but the claim that every downstream guard needed no change was
too broad: a guard over what the model could reproduce needs the private input scope, not merely the
public output scope.
Resolution and verification: the public full-context path reloads the current eligible corpus and
audits the answer against all of it before source minimization. It fails closed if that private
scope is unavailable. The RAG branch returns the identical existing `final_chunks` object and does
not load the corpus. An adversarial uncited 55-word reproduction is rejected, and a separate RAG
regression proves its path is unchanged. The public full-context flag remains disabled.

## [2026-08-01] Full-context spend was absent from cumulative development cost lineage
Phase/Brief: development-cost lineage review after the first paid full-context debugging call
Symptom: the text-free cumulative report still showed `$4.811832770` after a separately metered
`$1.625146250` full-context call, because discovery matched only `evidence-planned-vN` directories.
Cause: contract implementation gap. A cost report keyed only by RAG policy version had no strategy
dimension, so a second answer strategy was invisible and RAG V1 would collide conceptually with
full-context V1.
Resolution and verification: cost-lineage schema `/2` identifies each run by `answer_strategy` and
`answer_strategy_version`, discovers both namespaces, groups them independently, and retains the
cross-ledger provider-response duplicate check. Legacy `/1` reports remain renderable. The
regenerated text-free lineage reports 11 runs, 79 calls, 745,657 priced tokens, and
`$6.436979020` estimated cost. Focused mixed-strategy, duplicate-ID, legacy, and text-leak tests
passed; no provider call was made.

## [2026-08-01] Full-context requests could cross a remaining hard budget in one call
Phase/Brief: Phase 1 full-context answer strategy, implementation review of design section 18
Symptom: the existing pre-call guard stopped requests only after the monthly hard limit had already
been reached. A full-context request could therefore begin while under budget and exceed the
remaining amount by itself.
Cause: contract implementation gap. The design required a conservative prospective check, but v1
implemented only the ordinary current-spend check.
Resolution and verification: a shared prospective guard now compares an estimated request cost to
the remaining hard budget while preserving the explicit development override. Full context prices
maximum output under both ordinary uncached-input and observed cache-write shapes and uses the
larger estimate immediately before the provider call. Unknown pricing fails closed. Tests cover an
over-remaining request, an exact-remaining request, override behavior, invalid estimates, pricing on
both sides of the long-context threshold, and call ordering. No provider call was made.

## [2026-07-30] A paid full-context answer was discarded by a retrieval-only artifact rule
Phase/Brief: Phase 1 full-context answer strategy, first paid G007 debugging run
`full-context-v1-g007-20260730-1`
Symptom: the run generated and locally validated a good full-context answer, then exited non-zero
with `Turn 1 completed without a retrieval trace`. `G007.json` recorded `status: error`, and no run
summary or grading artifact was produced. Estimated spend `$1.62514625` for a discarded result.
Cause: spec gap. `evaluation_artifacts.SmokeArtifactRecorder._finish_capture` requires at least one
retrieval trace per captured turn. That is correct for a retrieval strategy and unsatisfiable for a
strategy that performs no retrieval. The full-context design specified diagnostics and artifacts but
never stated what the paid-run artifact recorder should do with a turn that has no retrieval trace.
Resolution and verification: no source change was needed. The artifact contract already models this
as `not_applicable` via `attach_to_summary(require_retrieval_traces=False)`, added for the earlier
resolver-only confirmation. The full-context runner now overrides the recorder to use that existing
path, and fails closed in the opposite direction: if a retrieval trace ever is emitted during a
full-context turn it raises, because that would mean the strategy reached the retrieval core. The
already-paid response was recovered read-only from its stored provider ID rather than regenerated,
so no second generation call was made. The repaired runner loads and its overrides are in place; it
has not been re-run, because a re-run costs another paid call and none is authorized.

## [2026-07-30] The full-context cost and token estimates were both wrong
Phase/Brief: Phase 1 full-context answer strategy, first paid G007 debugging run
Symptom: the design estimated roughly 286,000 input tokens and a `$2.50`-`$3.50` cold call. The
measured call used 249,176 input tokens and cost an estimated `$1.62514625`.
Cause: model error in the design, not in the code. The character-based token estimate (characters
divided by four) over-counted by about 15 percent, and the design then reasoned from that inflated
figure to the conclusion that every full-context request necessarily crosses the documented 272,000
token long-context threshold. The real request sits about 9 percent below it, so the 2x input and
1.5x output surcharge did not apply at all.
Resolution and verification: the estimate was explicitly labelled unverified and the pre-call
fail-safe deliberately biased high, so the error was in the safe direction and no code behaved
incorrectly. `costs.calculate_cost_nano_usd` applied no surcharge, which was correct for a 249,176
token request. The measured figures are recorded in the run's private assessment and in BLOGNOTES.
Two consequences carry forward: the corpus is much closer to the surcharge threshold than the design
assumed, so a longer manuscript or a long conversation history could cross it; and a live response
reported 249,173 cache-write tokens while the same response retrieved afterwards reports zero, a
`$0.31` difference on this one call that the provider dashboard must settle.

## [2026-07-30] Full-context answer strategy opened as a second evidence scope
Phase/Brief: Phase 1 full-context answer strategy, phase 1 of
`docs/full_context_answer_strategy_design.md`
Symptom: cohort opening, not a fault. A reader can now choose an evidence scope, so an answer's
identity needs a strategy as well as a policy version. Retrieval answers are unchanged and remain
comparable to every prior cohort; full-context answers are a new cohort with no prior runs.
Cause: cohort opening plus three spec gaps in the design document, listed under resolution.
Resolution and verification: added `AnswerStrategy`, two defaulted `AnswerModeResult` fields, a
strategy-aware answer-run cohort, `src/full_context_pipeline.py`, and
`src/full_context_coverage.py`. Both switches (`ARCHIVIST_FULL_CONTEXT_ENABLED`,
`ARCHIVIST_PUBLIC_FULL_CONTEXT_ENABLED`) default to disabled, so an operator who does nothing keeps
exactly today's behavior. The complete offline suite passed 637 tests with one intentional skip,
repository-wide Ruff passed, and the frontend production build passed. No OpenAI call was made.

Three design gaps required an invented mechanic and are recorded here because the invention is
unreviewed by definition:

1. The design specified a separate `archivist.full_context_run_diagnostics/1` schema in §21 while
   §10 required one shared answer-run cohort and ledger column. Those are incompatible. One shared
   `archivist.answer_run_diagnostics/3` record was kept, with RAG-only cohort fields reported as
   `not-applicable` for full context, following the existing `legacy_answer` precedent. This is
   what makes a cross-strategy comparison groupable in one table.
2. The design did not state whether the long-context surcharge applies to models without a
   documented long-context tier. Applying it globally silently doubled the estimate for a
   1M-token embedding request, which the existing cost tests caught. The threshold is now
   per-model data on `ModelPricing`, set only for the GPT-5.6 family.
3. The design's §16 implies full interpretive parity, but the structured interpretive
   preface/coda contract in `answer_coverage` is RAG-shaped and revalidating it for a second
   schema is its own piece of work. Version 1 passes lens, voice, and worldview through the shared
   style block only. A non-neutral setting therefore shapes a full-context answer's prose but does
   not produce the separately validated framing paragraphs a retrieval answer gets. The §22 formal
   comparison runs at the neutral baseline, so this does not block the measurement.

Not yet evidence of anything about answer quality. No full-context request has been made, and the
strategy cannot be reached without explicitly enabling it.

## [2026-07-30] Broad answers validated despite unsupported required content
Phase/Brief: Phase 1 V24 unchanged ten-question development evaluation
Symptom: all ten V24 outputs were structurally valid with resolvable citations, but G006 received
only 2/8 strict claims despite covering 6/8 target document groups. Its trace reported all eight
canonical stages, only 5/7 adjacent transitions, generation coverage of one supported, six
partial, and one unsupported requirement, and additional partial or unsupported obligation
dimensions. The generator still returned `valid` and appended seven repetitive insufficiency
notices.
Cause: contract implementation gap - structured-output validity, citation/source validity, and
content completeness share one terminal success state. The contract can prove that an answer is
well formed without requiring enough source-bounded obligations to justify presenting the broad
answer as complete.
Resolution and verification: resolved offline in `evidence-planned-v25`. Structural validation
still controls `answer_status`, while a separate content outcome reports `valid_complete`,
`valid_partial`, or `insufficient_evidence`. The application preserves the pre-retrieval ordered
requirements, requires the exact adjacent stage chain for broad routes, requires complete
source-bounded obligation coverage, and requires institutional-handoff dimensions for long
lineages. A structurally valid partial answer remains readable and receives one deterministic
limitation, with conflict identified explicitly, rather than repeated requirement notices.
Content outcome is propagated through the closed trace, API, frontend type, and locally migrated
cost ledger. Synthetic regressions cover missing stages, missing transitions, missing handoffs,
conflict, unsupported content, and ordinary focused answers. The complete offline suite passed
598 tests with one intentional skip; repository-wide Ruff and the production frontend build
passed. No provider call, retry, source slot, critic, or manuscript-specific hint was added.

## [2026-07-30] Absence handling supplied an unrequested analogue
Phase/Brief: Phase 1 V24 unchanged ten-question development evaluation
Symptom: G008 correctly said the retrieved material did not directly establish treatment of the
Hudson's Bay Company or Canadian fur trade, but then supplied Hudson Bay charter geography and
Ohio Company material. It scored 0/2 strict claims and failed the expected clean-abstention
behavior, although it did not fabricate that the analogue was the requested subject.
Cause: evidence-policy contract gap - `qualified_near_match` does not distinguish a useful bounded
near match requested by the user from an unsolicited analogue after the planner establishes a
corpus-level absence.
Resolution and verification: resolved offline in `evidence-planned-v25`. Near-match permission is
derived only from the current raw user turn. A plain conjunction, stale earlier request, negated
analogue request, or proper name containing words such as `Parallel` or `Affect` cannot authorize
related evidence. Explicit analogue requests may use at most the already bounded,
requirement-linked planner hints. Causal or relational requests additionally require a locally
certified broader/probe pair, preserving the G009-shaped implication path while making the
G008-shaped unsolicited analogue cleanly abstain. Synthetic regressions cover both directions.
The evidence gate is versioned as `evidence-gate-v4`; no provider call or retry was added.

## [2026-07-30] Provider quota stopped the V24 cohort before its first embedding
Phase/Brief: Phase 1 V24 unchanged ten-question development evaluation
Symptom: after the V24 mechanical sentinel passed, the full development runner began G001 and
OpenAI returned `429 insufficient_quota` on the first embedding request. The attempt ended after
2.940 seconds with no completed metered operation and no answer.
Cause: other - external OpenAI account/project quota. Archivist's preflight was clean, its
`$3.00` operational cap had not been approached, and the error is not evidence about retrieval or
answer quality.
Resolution and verification: the zero-retry runner stopped immediately, retained the error
attempt and G001 artifact, and did not start G002. The cumulative ledger classifies this as an
error with zero completed calls and records the operational cap separately from the owner's
broader authorization. Resume the unchanged ten questions in a fresh isolated run only after the
provider quota is available; no RAG repair is licensed by this incident.

Follow-up verification: quota was restored without a RAG change. Fresh isolated run
`evidence-planned-v24-clean-20260730-2` completed all ten items from exact clean commit
`1b75e8676319ad89f5b09bb851c5df5fad184c6c` with zero retries, 28 completed API operations,
187,228 priced tokens, 589.577 seconds of item latency, and estimated cost `$1.53158052`.

## [2026-07-30] An undocumented single-item quality gate suppressed broader development evidence
Phase/Brief: Phase 1 candidate stabilization and practical development evaluation
Symptom: successive V19–V24 notes required G007 to reach 2/7 strict claims and 5/5 target groups
before the unchanged ten-question development cohort could run, but `EVAL_CONTRACT.md` neither
defined that gate nor authorized one repeatedly tuned development item to veto broader
measurement.
Cause: owner-confirmed measurement-governance specification gap. A useful regression question was
allowed to serve two incompatible roles: mechanical sentinel for known broad-synthesis defects and
reader-quality promotion gate. Repeated repairs made G007 increasingly contaminated as development
data while its veto reduced visibility into regressions and improvements on the other nine items.
Resolution and verification: owner-authorized contract event. `EVAL_CONTRACT.md` §1.5 now
distinguishes predeclared mechanical invalidity from reader-quality results. A focused sentinel may
stop the broader development run only for invalid identity, calls/retries, traces, structural
classification, identifier mapping, or cost safety. Once mechanically valid, the complete
unchanged practical cohort proceeds regardless of claim or target score. G001–G010 remain
development-only and cannot become held-out gold or formal §8 release thresholds. The prior
practical runs remain historical development observations; no formal baseline or run of record
existed to invalidate.

Follow-up verification: clean V24 commit
`67c735fff37d26288a2a887205b0a20682d9320d` passed the predeclared G007 mechanical sentinel.
Its trace satisfied six of six canonical cores and six of six stage obligations with no
structural shortfall; terminal R6 was supported; the one-planner, one-embedding, one-generation,
zero-retry call shape held; and all 18 citations resolved. Descriptive reader grading remained
1/7 strict claims and 4/5 target groups, but correctly did not block launch of the full cohort.

## [2026-07-29] Structural filename fixture omitted the trailing title delimiter
Phase/Brief: Phase 1 evidence-planned-v23 unchanged G007 confirmation
Symptom: the exact frozen V23 candidate returned an explicit structural-stage insufficiency with
zero sources and no generation call. Its valid closed trace reported six required canonical
cores, zero satisfied cores, and six short, even though the retrieval lanes contained candidates
from numbered chapters.
Cause: test-fixture and parser-contract gap - V23 tested `08_Chapter 1.md`, but the corpus uses
the shape `08_Chapter 1_ Sample title.md`. The numbered-document regex still ended its number with
`\b`; because a digit and underscore are both word characters, the real filename has no boundary
there. All numbered body documents were excluded from structural-band construction. The terminal
pattern has the same latent delimiter assumption.
Resolution and verification: resolved offline in `evidence-planned-v24`. Numbered and terminal
labels now require an explicit delimiter or end of string, accepting underscore, whitespace, and
punctuation while rejecting alphanumeric continuations. Regressions use complete ordinal,
structural-label, underscore, and title shapes; a direct catalog test requires six nonempty
bands. The active private catalog metadata produces band sizes 4/4/4/4/4/1 without reading or
emitting manuscript prose. Focused verification passed 219 tests; the complete offline suite
passed 580 tests with one intentional skip, and repository-wide Ruff passed. No paid API call was
made. The prior clean V23 run at
`d89f4332b21f0e41cb445780abe10f997b52626c` made one planner call and one batched embedding
call, then failed closed before generation. It completed in 24.655 seconds for an estimated
`$0.08430031`; the trace was valid, but the reader gate scored 0/7 claims and 0/5 public target
groups. V24 is not yet reader-confirmed, so the ten-question run remains blocked.

## [2026-07-29] Six fallback stages produced only one protected anchor
Phase/Brief: Phase 1 evidence-planned-v22 unchanged G007 confirmation
Symptom: the exact frozen V22 candidate produced a valid eight-source answer and valid closed
trace, but reached only 1/7 strict claims and 4/5 target document groups against the unchanged
2/7 plus 5/5 gate. The Civil War group remained absent despite the six-stage contract.
Cause: contract implementation gap - the provider plan failed `broad_narrative_gap`, activating
the deterministic six-stage fallback. Structural cores constrained which candidates could become
anchors, but the existing distinctive-intent threshold could still reject every in-core
candidate. Five of six stage lanes therefore protected no anchor. Global and transition filling
then occupied all eight source positions and hid the structural shortfall behind a full context.
The structural filename recognizer also used a word boundary that did not match underscore-prefixed
corpus names, so an empty computed core could bypass the conditional exact-core filter.
Resolution and verification: resolved offline in `evidence-planned-v23`. Deterministic six-stage
fallback now allocates one best available candidate from each exact core before optional
thresholds or supplements. Exact-core filtering remains active for an empty core; an unresolved
shortfall suppresses optional and neighbor filling and returns an explicit
`structural_stage_shortfall` result before generation. The filename recognizer now accepts
underscore-prefixed numbered and terminal documents. Focused verification passed 207 tests; the
complete offline suite passed 568 tests with one intentional skip, and repository-wide Ruff
passed. No paid API call was made. V22's clean run at
`0691b3da9a4926097c7d013d79266eee62f7de9b` remains the measured failure: one planner call,
one batched embedding call, one generation call, no retry, 95.735 seconds, and estimated
`$0.25207406`. V23 subsequently froze and confirmed the allocation shortfall now fails closed,
but its reader gate exposed the separate trailing-delimiter parser defect above. The ten-question
run remains blocked.

## [2026-07-29] V22 opened a six-stage narrative-span contract
Phase/Brief: Phase 1 evidence-planned-v22 offline repair
Symptom: the frozen V21 reader confirmation showed that a formally valid five-stage broad plan
could protect an overview as its historical origin, skip a substantial middle period, and return
terminal evidence without making the endpoint an answer obligation.
Cause: cohort opening following a specification gap - V22 changes planner cardinality, plan
validation, structural retrieval allocation, and version identifiers. Earlier paid cohorts are
not directly comparable to this candidate.
Resolution and verification: implemented a corpus-ordered six-stage contract for broad causal
narrative-span questions: five non-overlapping numbered-body bands plus a terminal
Conclusion/Epilogue band. All origin hints must be body documents; every stage hint must remain
inside its structural band; protected anchors are filtered to the exact bands even though
neighboring bands remain available for discovery and transitions; and all six protected anchors
become existing generation obligations before two optional source positions are filled. Ordinary
noncausal broad plans remain five stages and long institutional-lineage plans remain eight.
Focused verification passed 204 tests; the complete offline suite passed 565 tests with one
intentional skip, and repository-wide Ruff passed. No paid API call was made. V22 is not yet
frozen or reader-confirmed, so the unchanged G007 gate and ten-question hold remain in force.

## [2026-07-29] A valid broad plan used an overview as historical origin
Phase/Brief: Phase 1 evidence-planned-v21 unchanged G007 confirmation
Symptom: the one no-retry G007 confirmation returned a valid eight-source reader answer and a
closed valid trace, but realized only 1/7 frozen strict claims and 3/5 target document groups
against the predeclared 2/7 plus 5/5 gate. It omitted the Chapter 4/5 origin and Chapter 14 Civil
War groups. An Epilogue passage was returned but its required recent-shock chain was not used.
Cause: spec gap in the brief and model error - the provider proposal passed local validation, so
V21's rejected-origin salvage path did not run. Validation examined only the primary origin hint;
a secondary Introduction hint therefore entered retrieval, outranked the body origin, and became
the protected anchor. The ordinary five-stage contract could also skip a middle period, and
returned endpoint evidence did not have to become a supported answer obligation.
Resolution and verification: resolved at the offline contract level in `evidence-planned-v22`.
Validation rejects an overview in any origin-hint position and assigns all six causal stages to
five exact numbered-body bands plus a terminal band. Retrieval independently filters protected
anchors to those non-overlapping cores, and the sixth protected endpoint flows through the
existing generation-obligation contract. The exact frozen V21 commit
`bf424c880bca4728a8d13225f85978e27a8d8dcf` remains the measured failed candidate: one planner,
one batched embedding, one generation, no retry, and `$0.29870543` estimated spend under the
`$0.40` cap. V22 has passed focused zero-call regression and lint checks but is not yet frozen or
reader-confirmed. The failed gate still does not license the unchanged ten-question run.

## [2026-07-29] Final gold workflow had no mechanical holdout or carry-over boundary
Phase/Brief: Phase 1, Briefs 2–3
Symptom: the repository could validate a completed gold JSON schema, but could not prove that its
questions differed from development questions, bind owner attestations and exact candidate/file
hashes, reject system changes after candidate freeze, detect long copied manuscript passages, or
execute the mandatory EVAL_CONTRACT §2.5 location carry-over procedure.
Cause: spec gap in the brief - the gold schema defined the artifact's content but not the complete
blind-authoring, provenance, leakage, privacy, and re-ingest workflow needed to make it credible.
Resolution and verification: added a 30-question development registry, exact and deterministic
near-match checks, an intentionally incomplete provenance sidecar bound to frozen V21 commit
`bf424c880bca4728a8d13225f85978e27a8d8dcf`, a blank private workbook, an offline owner-directed
chunk workbench, text-free quotation-risk and carry-over reports, and a clean-tree post-freeze
allowlist validator. Focused validation passed 61 tests and Ruff. No historical gold content was
model-authored; owner authoring and attestations remain pending.

## [2026-07-29] Correct origin rejection discarded an otherwise useful broad plan
Phase/Brief: Phase 1 evidence-planned-v20 focused G006/G007 confirmation
Symptom: G007's live five-stage plan failed `broad_origin_not_preserved`; the zero-retry path then
discarded the complete structured plan, satisfied only one canonical stage, covered 3/5 frozen
target groups, and realized 0/7 strict claims.
Cause: model error in the fallback boundary - all planner-validation failures shared one lossy
fallback even when local validation had isolated a single repairable document hint.
Resolution and verification: resolved offline in `evidence-planned-v21`. Only the isolated
origin failure activates local salvage; the unique origin hint is replaced using the validator's
same corpus-derived early-driver rule, the remaining plan is preserved, and the complete proposal
is revalidated. Unrepairable plans still fail closed. Synthetic plan and pipeline tests prove
stage preservation, repair isolation, one planner call, and zero retries. The complete offline
suite passed 511 tests with one intentional skip and Ruff passed. The unchanged paid G007
confirmation subsequently showed that this path was not invoked because the new provider plan
passed validation directly; the separate valid-plan origin defect above remains open.

## [2026-07-29] Empty supported-status mapping discarded a paid G006 answer
Phase/Brief: Phase 1 evidence-planned-v19 focused G006/G007 confirmation
Symptom: G006 completed one planner call, one embedding call, and one answer-generation call, but
the reader received only the validated-answer fallback. Local validation rejected the generated
coverage object with `status_unit_mismatch`; diagnostics recorded zero accepted answer units and
no local repair.
Cause: model error and spec gap in the brief - the provider can assign a non-unsupported
requirement or dimension status while omitting its unit/source mapping, and the canonical
normalizer does not distinguish that empty, safely downgradeable shape from a nonempty conflicting
mapping that must fail closed.
Resolution and verification: resolved offline in `evidence-planned-v20`. The canonical normalizer
now downgrades only an empty non-unsupported requirement or dimension mapping when no trusted
answer unit supplies the missing link. It produces the existing unsupported representation and
does not invent, relocate, or infer support. A nonempty invalid mapping still fails closed, while
a valid trusted-ledger mapping remains derivable. Requirement-level, dimension-level, conflict,
and preservation regressions pass; the complete offline suite passed 510 tests with one
intentional skip. The unchanged paid G006/G007 confirmation remains the reader-level check.

## [2026-07-29] Paid runner lost stdout after its parent stopped waiting
Phase/Brief: Phase 1 evidence-planned-v19 focused G006/G007 confirmation
Symptom: the foreground command wrapper stopped waiting after five seconds while G006 continued.
G006 completed and wrote its response and usage ledger exactly once, but then raised `OSError`
while printing to the closed stdout pipe. G007 had not started.
Cause: model error in the evaluation invocation - a long-running paid runner was attached to a
short-lived parent output pipe instead of a persistent redirected process.
Resolution and verification: the completed G006 was not rerun. A G007-only continuation asserted
the same clean commit, frozen hashes, settings, and zero-retry rule; reduced its cap to the unused
authorization; and redirected stdout/stderr to files. It completed exactly once. Future paid
runners should use persistent file redirection from launch. The combined private assessment
accounts for one call sequence per question and a total estimated cost of `$0.47055541`.

## [2026-07-29] Eight chronological roles did not constitute an institutional lineage
Phase/Brief: Phase 1 evidence-planned-v18 unchanged ten-question evaluation
Symptom: G006 received the required eight-stage plan. Retrieval satisfied seven stage anchors,
six of seven transitions, and four of eight target document groups, yet the answer realized none
of the frozen strict claims. The selected stages formed a broad chronological sequence of
governing and economic regimes rather than the institutional succession requested.
Cause: spec gap in the brief - the v18 validator proves cardinality, advancing document hints,
and vocabulary-distinct roles, but it does not require a named institutional capacity to pass
from one bearer to the next or bind each role to both endpoints of the question.
Resolution and verification: unresolved after `evidence-planned-v19`. V19 added distinct bearers,
contiguous capacities, transfer mechanisms, bearer-and-role anchor qualification, shared-capacity
transitions, and source-bounded `institutional_handoff` obligations. Offline regressions and the
full suite passed, but the unchanged paid G006 result fell to 0/8 claims and 3/8 target groups,
then discarded its answer on a separate `status_unit_mismatch`. The stricter contract correctly
rejected five weak transitions, yet the live planner still chose an evenly advancing chronology
rather than documents performing the required institutional roles. The next repair must ground a
proposed document hint in corpus-derived historical-role descriptors before accepting it; internal
handoff continuity alone is insufficient. V20 now supplies bounded passage-free role profiles and
rejects primary hints with no token-grounded stage-role match. Corpus-agnostic regressions and the
complete offline suite pass, but the defect remains open until the unchanged paid G006 check shows
that the planner chooses the requested institutional lineage rather than another internally valid
chronology.

## [2026-07-29] Target-bearing broad context remained outside answer obligations
Phase/Brief: Phase 1 evidence-planned-v18 unchanged ten-question evaluation
Symptom: G007 returned all five expected target document groups, retained all five planned stage
anchors, satisfied all four transition searches, and produced a locally valid answer. The answer
nevertheless realized none of the seven frozen strict claims; several target-bearing passages
never entered a supported stage or transition unit in the generated answer.
Cause: spec gap in the brief - target breadth, planned-stage coverage, and answer-obligation
coverage are measured independently, but the contract does not require a selected passage that
carries a supported stage or handoff to be realized in the answer. Generic unsupported-link
notices can coexist with an otherwise valid broad answer.
Resolution and verification: unresolved. V19 did not change the ordinary five-stage obligation
contract and the focused G007 guardrail regressed from V18's 5/5 target groups to 4/5, again
realizing 0/7 strict claims. The accepted plan began too late and omitted the early colonial
origin even though four later regions and all four adjacent transitions survived. The next repair
must preserve an explicit origin stage for early-to-late causal questions and bind supported stage
and handoff evidence to answer obligations. It must add no critic call, retry, gold hint, or
manuscript-specific rule. V20 now rejects an origin outside the earliest numbered narrative
documents containing the named causal driver, using only corpus-derived role tokens. That origin
contract passes offline tests. The broader obligation-realization defect remains open, and the
unchanged paid G007 check must still establish target-group and strict-claim behavior.

## [2026-07-29] A five-stage plan falsely satisfied a longer institutional lineage
Phase/Brief: Phase 1 evidence-planned-v16 unchanged ten-question evaluation
Symptom: G006 asked for a long institutional lineage spanning eight expected historical roles.
The accepted plan contained only five stages, yet retrieval reported five of five stage anchors
and four of four transitions satisfied. The green counters overstated completeness, and the
answer realized none of the frozen strict claims.
Cause: spec gap in the brief - broad synthesis had a minimum-stage rule but no separate contract
for explicit institutional-lineage questions, no role-distinctness test, and no accounting for
the competition between stage anchors and transition passages under the eight-source ceiling.
Resolution and verification: resolved in `evidence-planned-v18`. An application-owned route trait
now requires exactly eight ordered, role-distinct stages for explicit long institutional
lineages, plus advancing exact document hints when a catalog is available. Ordinary broad
questions remain five-stage. Retrieval reserves the eight final source slots for the eight stage
anchors, prefers already selected stage sources for transition evidence, and reports stage and
transition capacity shortfalls separately in retrieval trace 10. Synthetic end-to-end coverage
retains all eight roles through generation. The full offline suite passed 500 tests with one
intentional skip, and Ruff passed across `src` and `tests`. No paid calls were made; gold-set
quality remains to be measured in the unchanged ten-question evaluation.

## [2026-07-29] Dedicated transition evidence was rejected by the older validation context
Phase/Brief: Phase 1 evidence-planned-v16 unchanged ten-question evaluation
Symptom: G007's final returned context covered all five expected target document groups, and its
retrieval trace reported four of five stage anchors plus four of four transition searches. The
application nevertheless paid for a full answer generation and then returned no usable answer
because local validation classified the context as `invalid_context`.
Cause: contract edited and spec gap in the brief - the v16 obligation builder correctly binds an
`adjacent_stage_link` to its selected dedicated transition passage, but the older
validation-context check still requires that link's source number to equal the successor stage
anchor's source number. Builder and validator tests exercised their own assumptions separately;
no end-to-end fixture used a transition source distinct from both stage anchors.
Resolution and verification: resolved in `evidence-planned-v17`. The validator now accepts the
dedicated transition passage as the link source while still requiring consecutive requirements,
exactly one surviving stage scope at each endpoint, the correct predecessor anchor, and in-range
source numbers. The same public trusted-context validator runs before answer generation and after
parsing, so an invalid local context fails with `structured_generation_called=false` before a paid
answer call. End-to-end synthetic regressions prove that distinct predecessor, successor, and
transition passages validate, while a missing successor stage fails before generation. The full
offline suite passed 494 tests with one intentional skip, and Ruff passed across `src` and `tests`.

## [2026-07-26] Valid source selections were discarded by citation-locality validation
Phase/Brief: Phase 1 evidence-planned-v11 directional ten-question evaluation
Symptom: G001 retrieved both expected document groups and G009 correctly stayed on the
qualified-near-match route with only the expected Epilogue group. Both paid for a full structured
generation and then returned no reader-facing answer because strict validation reported
`citation_locality_invalid`. G001 therefore regressed from its earlier valid answer, while G009
failed after the absence and near-match retrieval repairs had already succeeded.
Cause: model error and spec gap in the brief - the one-generation evidence-coverage contract can
still emit an answer-unit/citation shape that violates the application's atomic locality rule.
The failure is correctly closed, but diagnostics do not yet isolate a safe canonical repair from
a genuinely compound or unsupported unit.
Resolution and verification: unresolved. The next repair must preserve the existing citation
grammar and fail-closed validation, distinguish mechanically repairable locality shapes from
substantive multi-claim units, and prove the distinction with synthetic G001- and G009-shaped
fixtures before one focused paid confirmation. It must not move citations, split prose, or infer
support unless the transformation is deterministic and source scopes remain identical.

## [2026-07-26] Retrieved broad mechanisms were omitted by the answer contract
Phase/Brief: Phase 1 evidence-planned-v11 focused G007 confirmation and directional ten-question
evaluation
Symptom: the focused G007 confirmation returned passages covering all 5/5 expected document
groups, including source text for several required mechanisms, but its answer realized only about
1/7 strict claims. The clean ten-question run improved broad target coverage to 5/8 for G006 and
3/5 for G007, yet realized only 2/8 and 1/7 claims. Five high-level stage requirements did not
force the generator to state the source-present submechanisms inside those stages.
Cause: spec gap in the brief - retrieval obligations are stage-sized while generation
requirements remain too coarse to express the independently supportable mechanisms found within
each selected passage. A requirement can be marked covered even when only one part of its
historical mechanism reaches the answer.
Resolution and verification: unresolved. The next repair should derive explicit, source-bounded
mechanism obligations from the selected evidence and pass those obligations through the existing
coverage ledger. It must remain corpus-agnostic, use no private expected-answer text, add no
automatic critic or retry, and be tested first against preserved contexts before paid generation.

## [2026-07-25] Bounded absence retrieval chose adjacent contracting history instead of the requested near-match
Phase/Brief: Phase 1 evidence-planned-v7 focused paid confirmation
Symptom: unchanged G009 now routed and validated correctly as `qualified_near_match`, stated the
COVID/federal-contracting evidence boundary first, used exactly two bounded sources, and resolved
all citations. Both selected sources were from Chapter 20, however, and the answer discussed
post-Soviet layoffs and post-Al-Qaeda contracting. It omitted the Epilogue's generic pandemic,
supply-chain, reshoring, and military-spending treatment required by the unchanged rubric. Strict
coverage was 2/5 claims and 0/1 target groups.
Cause: other and spec gap in the brief - a trusted-tail bounded probe certifies co-occurrence of
the broad related terms, but final ranking does not measure whether a candidate preserves the
requested absent subject's facet. Related contracting examples can therefore outrank the closest
bounded thematic substitute.
Resolution and verification: resolved in `evidence-planned-v8` without changing
premise/absence precedence. A planner-ranked related passage is eligible only for an
absence-sensitive, substantive non-premise facet with an exact validated document hint whose
query preserves the trusted subject and relation surfaces. Admission occurs before the older
exact-tail fallback and is capped at two sources. Synthetic tests prove that the hinted related
lane outranks an exact but off-facet contracting co-occurrence and that three qualified candidates
are still capped at two. The complete offline suite passes with 421 tests and one skip. The
unchanged paid G009 confirmation then returned a valid qualified answer from exactly two Epilogue
passages, covered the required 1/1 target group and about 3/5 strict claims, and invented no
pandemic procurement analysis.

## [2026-07-25] Premise planning bypassed certified absence on the unchanged G009
Phase/Brief: Phase 1 evidence-planned-v6 directional ten-question evaluation
Symptom: the focused v6 G009 confirmation returned a valid bounded near-match answer from two
sources, but the same unchanged question later returned `generation_contract_failed` in the full
cohort. The full-run planner succeeded, the target scanner again certified the named subject
absent, and the required Epilogue group was present, but a planner-created premise hypothesis made
`premise_evaluation_pending` take precedence. All eight sources entered generation as
`direct_answer`; status/gap normalization succeeded; strict validation then rejected
`premise_source_mismatch`.
Cause: other and spec gap in the brief - the evidence-decision precedence does not define whether
a model-proposed premise may override mechanically certified subject absence, and a declarative
question about an absent subject can be reclassified as premise-sensitive nondeterministically.
Resolution and verification: repaired offline in `evidence-planned-v7`. Planner input now includes
application-owned route traits, and local validation rejects any proposed premise unless the
deterministic route is already `premise_sensitive`. The evidence gate repeats that condition
before applying `premise_evaluation_pending`, so an absence-only route cannot be widened by a
provider proposal. A synthetic G009-shaped regression verifies `premise_route_mismatch` fallback,
and a defensive gate regression verifies that a surviving untrusted premise cannot override clean
absence. The complete offline suite passes with 416 tests and one skip. The unchanged paid v7
confirmation then retained only `absence_sensitive`, certified absence, returned
`qualified_near_match`, and passed strict validation from two bounded sources. This precedence
defect is resolved; the separate semantic near-match defect is logged above.

## [2026-07-25] Accepted broad plans did not produce source-bounded historical coverage
Phase/Brief: Phase 1 evidence-planned-v6 directional ten-question evaluation
Symptom: G006 and G007 both accepted live planner proposals and returned valid cited answers, but
covered only 2/8 and 2/5 expected document groups and realized 1/8 and 0/7 strict claims. G006
clustered six of eight sources in Chapters 2-4 and jumped to one modern chapter; G007 again
collapsed largely into the twentieth century.
Cause: spec gap in the brief - plan validity guarantees that requirements map to facets, while
lane selection and the eight-source cap do not guarantee that a live facet yields a source or that
one surviving source represents each required era. A syntactically accepted plan can therefore
lose most of its intended historical span during retrieval and final allocation.
Resolution and verification: mitigation was implemented in `evidence-planned-v7` at the two
measured boundaries. An unbounded manuscript-treatment question now routes as broad synthesis
unless it has a conservative named absence target. Broad proposals require ordered requirements
and dedicated facets; final allocation protects requirements and live broad facets under the
unchanged eight-source cap. The complete offline suite passes with 416 tests and one skip.
Unchanged paid confirmation showed that the defect is not resolved: G006 remained at 1/8 claims
and 2/8 groups, while G007 remained at 0/7 claims and improved only to 3/5 groups. Protection
reported no shortfall, but coarse origin/transition/endpoint facets still failed to span the full
chronology, duplicate documents consumed slots, and anchor promotion displaced a unique useful
stage source. The full cohort was stopped pending a narrower allocation and stage-coverage repair.

`Evidence-planned-v8` added application-owned early/middle/late document bands, mandatory ordered
origin/transition-or-mechanism/endpoint plans, unseen-document refill, capacity-first stage
protection, and traceable stage counts. Offline verification passes with 421 tests and one skip.
The unchanged paid confirmation proves the defect remains unresolved: G006 improved modestly to
2/8 claims and 3/8 groups, while G007 remained at 0/7 claims and regressed to 2/5 groups. Both
traces reported 3/3 stage coverage with zero shortfall. The new signal therefore verifies only
coarse chronology-band survival, not recovery of the substantive stages in a book-wide argument.
The next repair must increase or refine planned argument-stage obligations within the unchanged
eight-source cap rather than treating three terciles as adequate coverage.

A controlled retrieval-only 8/12/16 comparison refined that diagnosis. With one shared planner
result and embedding batch per question, G006 target-group coverage was 3/8, 3/8, and 6/8,
respectively; G007 remained 3/5 at every limit. Every larger context retained all eight baseline
chunks. The eight-source ceiling is therefore a measured constraint for G006, while planning and
ranking remain the measured constraint for G007. The earlier assumption that both repairs should
fit under an unchanged eight-source cap is no longer justified. No production parameter changed;
a broad-only sixteen-source ceiling and richer argument-stage planning must be evaluated as
separate cohort changes before integration. The diagnostic made two planner calls, two embedding
calls, no answer call, no retry, and cost an estimated `$0.05277158`.

The separate G006 generation gate rejected the broad-only ceiling. Sixteen sources increased
target-document coverage from 2/8 to 6/8 in that live-plan sample, but the answer contract exposed
a hidden integration boundary: `source_count=16` is illegal while `MAX_SOURCES=8`. Recovering the
already-paid structured output showed that the larger context also failed the substantive gate:
it added the Crown takeover but still omitted the Hamiltonian, Federal Reserve/FTC,
Pentagon/cost-plus, Chapter 20, and Epilogue steps. Production therefore remains at eight rather
than widening both retrieval and generation contracts without an answer gain.

`Evidence-planned-v9` replaced three coarse broad stages with five dedicated ordered narrative
stages and scoped numbered books from Chapter 1 through conclusion/Epilogue. Its focused G007 run
validated mechanically but remained at 3/5 target groups: it repaired Jamestown, displaced the
Civil War group at a rigid stage boundary, and missed the Epilogue. `Evidence-planned-v10` added
two-document overlap between adjacent narrative stages and one structural endpoint lookup against
the book's own conclusion/Epilogue, sharing the existing embedding and retaining the eight-source
cap. A controlled rerun reused the exact accepted v9 plan and improved G007 source coverage from
3/5 to 5/5 for `$0.10395228`; the complete offline suite passes 422 tests with one skip.

The broad-source-allocation symptom is resolved at the target-document level for G007 but not at
the expected-claim level. The answer still lacks several specific mechanisms inside those
chapters, including war debt as Hamiltonian power, Pentagon/employment, NSC-68 and Keynesian
permanent spending, NATO persistence, and the security dilemma. The next defect is therefore
passage-level mechanism targeting/ranking inside the now-correct narrative stages, not another
source-limit increase or chronology-band change. The full ten-question cohort remains gated.

`Evidence-planned-v11` added deterministic role-scoped mechanism probes inside the accepted
narrative stages without adding an API operation or changing the eight-source ceiling. A focused
G007 confirmation reused the accepted v9 five-stage plan and covered 5/5 target groups. The clean
unchanged ten-question v11 cohort then improved G006 from 2/8 to 5/8 target groups and G007 from
2/5 to 3/5 compared with v6. The fresh G007 plan's regression from the focused 5/5 context to 3/5
shows that broad allocation remains nondeterministic across accepted plans. Mechanism-aware
ranking is retained as a directional breadth improvement, while plan stability remains
unresolved and the separate source-present generation omission is logged above.

## [2026-07-25] A valid premise correction still omitted the manuscript's origin frame
Phase/Brief: Phase 1 evidence-planned-v6 directional ten-question evaluation
Symptom: G010 changed from a rejected generation in v4 to a valid nine-citation answer in v6. It
explicitly rejected 1898 as the origin and covered both expected document groups, but used a later
Federalist counterpoint instead of stating the manuscript's Jamestown origin. It realized only
1/4 strict expected claims and retained the listed failure mode for correcting a premise without
stating where the book places the origin.
Cause: spec gap in the brief - premise validation checks that a leading cited correction exists,
not that the correction realizes the independently requested source-bounded origin requirement.
Mechanical premise validity and answer adequacy therefore diverge.
Resolution and verification: repaired offline in `evidence-planned-v7` without hard-coding a
place, chapter, or expected answer. `archivist.evidence_coverage/2` requires premise-correction
units to carry no requirement IDs and requires ordinary units to carry at least one, preventing a
correction from satisfying the requested answer by bookkeeping. The application supplies exact
post-gate support, counter, and framing source scopes; a contradicted correction must cite its
exact declared sources and include a retained framing source whenever one exists. The prompt
requires a positive replacement chronology, origin, identity, or causal frame before separate
substantive units. Provenance, separation, and text-free diagnostic regressions pass within the
416-test offline suite. Unchanged paid G010 confirmation then produced a leading, cited Jamestown
replacement frame, kept the correction outside ordinary requirement coverage, covered both
target-document groups, and passed strict validation. The narrow missing-origin defect is
resolved. Strict rubric completeness remains only 1/4 because the answer did not realize the full
Introduction/Cradle framing, identify Chapter 11, or complete the Spanish-imperial-transition
claim; those are answer-completeness targets rather than a recurrence of the provenance defect.

## [2026-07-25] Qualified near-match answer failed on redundant status/gap bookkeeping
Phase/Brief: Phase 1 evidence-planned-v5 focused paid smoke
Symptom: G009 certified direct absence of the named event, admitted exactly two bounded related
passages, and reached `qualified_near_match`, but the paid structured answer was discarded with
`generation_contract_failed` and `status_gap_mismatch`. No answer units or citations were rendered
even though retrieval and source bounding had succeeded.
Cause: other and spec gap in the brief - requirement status and gap reason are specified as a
closed one-to-one mapping, but the normalizer repairs other redundant mappings while leaving this
derived field pair to fail closed. The failure artifact preserves the stable code but not the exact
generated pair.
Resolution and verification: repaired offline in `evidence-planned-v6` with
`evidence-coverage-normalizer/3`. The normalizer derives only `gap_reason` from the unchanged
requirement status, records `status_gap_mismatch` as a repair code, and then runs the full strict
validator. Tests prove that it changes no unit, source, citation, or status, while missing units
and unsupported factual units still fail closed. The complete offline suite passes with 403 tests
and one skip. The separately authorized G009 confirmation then returned an `answered`,
`qualified_near_match` result from exactly two bounded sources; normalization recorded
`status_gap_mismatch`, strict validation passed, and all four emitted source references resolved.
The confirmation cost an estimated `$0.07107566` with no retry.

## [2026-07-25] Planner semantic fallback erased its actionable validation code
Phase/Brief: Phase 1 evidence-planned-v5 focused paid smoke
Symptom: G009's 339-output-token planner response parsed successfully and was then rejected by
local semantic materialization. The artifact retained only `invalid_planner_output`; it cannot
distinguish missing requirement mappings, query drift, unknown document hints, duplicate queries,
or another local validation rule. G008 and G010 planner proposals succeeded.
Cause: model error and spec gap in the brief - `build_question_plan` catches
`PlanValidationError`, Pydantic `ValidationError`, and `ValueError` together and intentionally
collapses them into one fallback reason, discarding the already text-free
`PlanValidationError.code`.
Resolution and verification: repaired offline in `evidence-planned-v6`. Planner diagnostics schema
`archivist.planner_call_diagnostics/2` retains one finite allowlisted
`planner_validation_code` beside the existing generic failure while preserving one-call/no-retry
fallback. Semantic failures retain their local code; structural Pydantic/ValueError failures use
`plan_structure_invalid`. Historical schema version 1 artifacts remain readable. Contract, ledger,
trace, and privacy tests reject missing, unknown, and non-text-free values and never persist the
proposal, exception prose, query, document hint, or manuscript text. The complete offline suite
passes with 403 tests and one skip. The separately authorized G009 confirmation's planner
succeeded, so the new failure code was not needed on that sample; its version-2 diagnostic was
valid and text-free. The semantic-failure path remains covered synthetically rather than claimed
from this successful live call.

## [2026-07-25] Every paid query-planner result failed its contract
Phase/Brief: Phase 1 evidence-planned-v4 directional ten-question evaluation
Symptom: all eight planner-eligible questions made exactly one paid `query_planning` request, but
none produced an accepted plan. Five failed SDK/Pydantic validation with safe exception class
`ValidationError`; three parsed but were rejected as `invalid_planner_output`. All eight questions
therefore used local fallback planning. The failed planner calls consumed 35,775 tokens,
`$0.57508750`, and 56.2% of the run's total estimated cost. G004 and G006 then returned no answer,
and G007 still collapsed its broad chronology into a narrow twentieth-century account.
Cause: other and spec gap in the brief — the planner prompt, output schema, token ceiling, and
post-parse plan validator were tested synthetically but not demonstrated to agree on a live model
response before planner-backed retrieval was treated as an optimization.
Resolution and verification: repaired offline in the new `evidence-planned-v5` cohort. Ledger
inspection established that G004, G006, G008, and G010 each exhausted exactly 3,000 planner output
tokens; G003 was the lone non-truncation SDK/Pydantic failure. The provider now returns a compact
shape-only `archivist.planner_question_plan/1` proposal, while the application supplies route
traits, trusted targets, requirement order, `F0`, status, and cross-field validation. The ceiling
is 4,000 tokens, the full eight-requirement/seven-added-facet capacity remains available, and
one-call/no-retry behavior is unchanged. Synthetic parse/materialization/fallback and strict
OpenAI-schema tests pass. A separately budgeted live planner smoke is still required before the
ten-question rerun; the frozen questions and rubric were not changed.

## [2026-07-25] Absence certification suppressed answerable and bounded-related evidence
Phase/Brief: Phase 1 evidence-planned-v4 directional ten-question evaluation
Symptom: G008 correctly abstained without substituting analogous chartered-company material, but
the same gate falsely abstained on G002, over-abstained on G009, and returned
`insufficient_evidence` on G004 and G006. G002's retrieval context included both expected Dulles
document groups before the gate certified the combined name absent and suppressed all eight
passages. G009 correctly found no literal COVID-19 mention but returned none of the bounded
Epilogue treatment required by the rubric. Across the ten questions, only five answer generations
were attempted and high-level expected behavior failed on five items.
Cause: other and spec gap in the brief — exact direct-subject anchoring does not safely decompose
compound named subjects, certified literal absence is allowed to erase qualified broader
discussion, and multi-target fallback ambiguity is treated as a reason to withhold all context.
Resolution and verification: repaired offline as `evidence-gate-v2` inside
`evidence-planned-v5`. Exact compound personal names split only into exact trusted user surfaces;
all-present and mixed-present subjects have separate admission rules; and compound subjects plus
a facet remain conservatively indeterminate. A bounded related probe can be derived only from an
exact trusted user-message tail and must co-occur with its broader term in one chunk or immediate
neighbors. Generic positive, partial, true-absence, noncooccurrence, organization-name, and
resolver-provenance regressions pass. Replaying the frozen v4 contexts without API calls routes
G002/G004/G006 to direct answer, preserves G008's clean abstention, and routes G009 to a bounded
qualified near match. A paid smoke remains required.

## [2026-07-25] Premise-correction generation was discarded after source remapping
Phase/Brief: Phase 1 evidence-planned-v4 directional ten-question evaluation
Symptom: G010 retrieved eight passages spanning the 1898 material and earlier-origin evidence, paid
for both planning and answer generation, then returned only `I could not produce a validated
source-grounded answer from the retrieved passages.` Diagnostics record
`generation_contract_failed`, repair code `source_mapping_mismatch`, and validation error
`premise_correction_invalid`. The final answer corrected neither the false premise nor the book's
origin framing and contained no citation.
Cause: other and spec gap in the brief — the interaction among anchor promotion, post-promotion
source numbering, premise-correction bookkeeping, and the structured generation validator was not
covered by an end-to-end contract fixture before the paid run.
Resolution and verification: repaired offline as `evidence-coverage-normalizer/2` inside
`evidence-planned-v5`. A contradicted premise's redundant source mapping is contracted to its
designated leading correction unit only when the original mapping is a nonempty strict superset
and both source sets are unique and in range. Empty, disjoint, duplicate, out-of-range,
wrong-role, and already-valid subset cases remain unchanged or fail closed. A corpus-agnostic
end-to-end fixture promotes an anchor to Source 1, remaps the prior passage to Source 2, passes all
numbered sources to generation, and renders the leading cited correction. A focused paid
premise-correction smoke is still required.

## [2026-07-24] Paid v3 smoke exposed an uncovered resolved-relationship form
Phase/Brief: Phase 1 post-optimization paid confirmation smoke
Symptom: both neutral smoke turns produced valid, source-supported answers, but the follow-up still
spent 12.93 seconds in query planning before falling back. Its resolved wording was `How did the
relationship between tobacco and labor shape everyday exchange in Jamestown?`; diagnostics record
`planner_call_failed` with safe exception class `ValidationError`, while the local usage ledger has
no planner event. The two-turn local estimate was `$0.18810122`, so any provider charge for that
failed request is not represented locally. The v3 artifacts also omitted a standalone retrieval
trace and the smoke summary omitted the corpus-manifest hash, weakening reproducibility even
though runtime preflight passed.
Cause: other and cohort-gate failure — the bounded local relationship grammar covered the earlier
`the relationship between X and Y as shaping ...` form but not the resolver's actual
`the relationship between X and Y shape ...` output. The generic broad-pattern check therefore
classified `between ... and` as requiring model planning. The tracked structured-response helper
records token usage only after successful parsing, and the smoke artifact contract does not yet
require a persisted retrieval trace or manifest hash.
Resolution and verification: resolved in the new `evidence-planned-v4` cohort. The exact
corpus-agnostic directional relationship form now decomposes locally, while ambiguous tails retain
planner routing. Structured-response accounting records completed raw-response usage before SDK
post-parse validation without retrying or double-recording. Reusable smoke artifacts now bind
corpus, vector-store, Git worktree, lockfile, runner, and per-turn trace identity. Trace schema
`archivist.retrieval_trace/3` hashes document labels and planner exception classes and accepts only
closed, field-specific diagnostic values, blocking unknown nested prose and encoded text channels.
The full offline suite passes with 372 tests and one skipped.

A separately bounded resolver-only API confirmation then resolved the observed follow-up to `How
did the manuscript describe the relationship between tobacco and labor as shaping everyday
exchange in Jamestown?`, retained all four required concepts, routed relationship-only, recorded
planner status `not_called`, and made exactly one `followup_resolution` request. It used 449 input
and 154 output tokens, took 6.954 seconds, and cost an estimated `$0.006865` under a `$0.02` hard
stop. No embedding, retrieval, planner, or answer-generation call occurred. The artifact records a
dirty exploratory worktree and is not a run of record. The unchanged ten-question evaluation
remains separately budgeted and was not started.

## [2026-07-24] Valid smoke answer lost primary evidence and hid a planner failure
Phase/Brief: Phase 1 post-optimization paid smoke
Symptom: both turns of the neutral tobacco-and-labor smoke passed the structured coverage contract,
but strict source review rated the opening answer only partial. It omitted the clearest
labor-shortage, indenture, and headright mechanism even though retrieval had selected that passage
as a primary result. The follow-up answered well but took 33 seconds; 16 seconds were attributed to
query planning, while the usage ledger contained no planner event.
Cause: other and spec gap — neighbor expansion was allowed to displace a selected primary passage
under the eight-source generation cap; the coverage contract validates citation membership and
requirement bookkeeping but not pairwise claim-to-source entailment; and the planner fallback
catches every exception without retaining an exact failure code or any available failed-request
usage.
Resolution and verification: opened `evidence-planned-v3`. Context assembly now preserves every
selected primary passage before optional neighbors fill unused slots. The evidence-coverage prompt
and schema require one independently checkable factual claim and one terminal citation group per
answer unit; deterministic validation rejects mechanically detectable extra sentences, citation
groups, post-citation prose, newlines, and semicolon-separated claims. Bounded resolved
relationship follow-ups decompose locally into both operands and their context, so the smoke's
follow-up shape no longer invokes the planner. Every planner outcome is also persisted as a
versioned text-free diagnostic; a failure retains only a safe exception class, an allowlisted
provider code, or a numeric HTTP status, never exception messages. The full offline suite passes
with 353 tests and one skipped, Ruff passes, and the
frontend production build passes. No OpenAI call was made. Semantic claim-to-source entailment
still requires evaluation rather than punctuation heuristics. Failed provider calls that return no
usage object also remain dashboard-only for billing. A separately authorized paid smoke must
confirm the live behavior before the unchanged ten-question comparison.

## [2026-07-24] A source-grounded draft was discarded without an actionable diagnosis
Phase/Brief: Phase 1 post-optimization reader testing
Symptom: a question recommended on the opening screen retrieved eight passages and incurred a full
answer-generation charge, but the interface displayed the generic generation-contract failure as
though it were the manuscript's answer. The local usage ledger showed substantial generated output,
while the application did not persist the exact validation rule that rejected it.
Cause: other and cohort opening — the evidence-coverage validator treated safe redundant
bookkeeping mismatches like factual grounding failures, the relational request had only its
unchanged original retrieval lane, and post-validation diagnostics stopped inside the backend.
Resolution and verification: opened `evidence-planned-v2`. Relational prompts now receive separate
local concept and connection lanes without a paid planner call. A conservative normalizer may
reorder trusted IDs and recompute redundant mappings only when factual units and exact citation
sets are unchanged; unsupported claims, unknown sources, malformed citations, and citation-set
changes still fail closed. Exact validation and repair codes plus stage timings are returned and
persisted with the relevant policy, prompt, normalizer, and generator cohort identifiers in a
text-free turn-level ledger record. The chat renders a rejected generation as an error with
collapsed technical details instead of archival answer paper. Homepage prompts are now data-backed
regression inputs. Legacy custom-project turns carry an explicit `legacy-answer-v1` cohort rather
than being misclassified as v2. The full offline backend suite passes with 296 tests and one
skipped, Ruff lint passes, and the frontend production build passes. No OpenAI call was made, no
gold entry or metric definition changed, and this cohort is not claimed better until a paid
confirmation run.

## [2026-07-23] Opening-screen commit absorbed an unrelated retrieval regression
Phase/Brief: Phase 1 paired practical rerun preflight
Symptom: clean commit `c1ab639` failed three backend tests: Answer retrieval traces no longer
included the frozen chunk and corpus hashes, the semantic-only web helper had disappeared, and
deferred Index generation was routed through hybrid Answer retrieval.
Cause: presentation work crossed the system-under-test boundary — a pre-existing unstaged
`src/web_project.py` edit was included with the opening-screen commit even though it was unrelated
to that UI task.
Resolution and verification: restored the exact post-optimization boundary from `d4656df`.
Answer Mode retains hybrid retrieval and its text-free corpus identity; Index Mode again calls the
semantic-only helper. The full offline backend suite passes with 152 tests and one opt-in test
skipped. No API call was made, and no paid evaluation began while the regression was present.

## [2026-07-23] Interpretive demo prompting advances Phase 2 beside neutral Phase 1
Phase/Brief: Phase 1 reader-facing UI, owner-directed perspective demonstration
Symptom: the owner requested more conversational answers when any Historiographical lens, Voice,
or Worldview characteristic is active, while the neutral Answer Mode evaluation and paired RAG
rerun are still open Phase 1 work.
Cause: Phase 2 concern in Phase 1 work and cohort opening — non-default interpretive prompt text
changed.
Resolution and verification: the new reader-facing response rules are emitted only when at least
one setting is non-default. The all-default Evidence-first + Scholarly + None path still uses the
frozen base prompt byte for byte, so the neutral retrieval comparison is not moved. Every
non-default facet now defines an observable rhetorical structure and shares the same citation,
uncertainty, and anti-invention guardrails; this is a separate experimental cohort and cannot be
claimed faithful until it passes the later perspective-mode checks. Focused tests cover all seven
active facets, combined settings, legacy mappings, and neutral exclusion without an API call.

## [2026-07-23] Guided-start mechanics were not specified
Phase/Brief: Phase 1 reader-facing onboarding
Symptom: the requested start feature said Archivist should ask questions that help a reader decide
what they want from the application, but did not define the number of steps, categories, resulting
questions, API boundary, conversation-history behavior, or whether the guide could alter answer
style.
Cause: spec gap in the brief.
Resolution and verification: the implementation uses a deterministic two-step client-side guide.
It asks for a subject class and then the desired treatment, fills an editable corpus-agnostic
question scaffold, selects the bracketed placeholder, and waits for the reader to press Ask. It
does not call the API, create a synthetic conversation turn, enter follow-up history, or change
Historiographical lens, Voice, or Worldview. The production frontend build verifies the typed
interaction path; no paid call was made.

## [2026-07-23] Hybrid Answer Mode retrieval opens a new retrieval cohort
Phase/Brief: Phase 1, post-baseline retrieval optimization
Symptom: the first ten-question practical baseline used only the five nearest semantic results,
then interleaved each primary with neighbors before applying the eight-source cap. Exact names
could be missed, optional neighbors could displace later primary evidence, and broad questions
could collapse to one document.
Cause: cohort opening — Answer Mode retrieval parameters and context ordering changed.
Resolution and verification: Answer Mode now makes the same single query-embedding call but asks
Chroma for a 20-candidate semantic pool, ranks the eligible corpus locally with deterministic
BM25, and fuses the two ranks with equal-weight reciprocal-rank fusion (`k=60`). Standard queries
remain relevance-ordered. Queries classified as broad synthesis may apply a three-primary
per-document diversity pass only when an alternative remains within 75% of the strongest deferred
candidate, then backfill by fused rank. Every selected primary is reserved before immediate
neighbors. The raw semantic top five remain separately visible, Index Mode retains its prior
exact-match and semantic-fallback behavior, and the generation prompt and model are unchanged.
Synthetic no-API tests cover lexical promotion, semantic-only fallback, deterministic fusion,
guarded diversity, primary-first expansion, shared CLI/web behavior, Index Mode isolation,
contract-facing displacement attribution, and private diagnostics. The full suite passes with
140 tests and one opt-in test skipped. The semantic-only practical
baseline belongs to the previous cohort; improvement must be established by rerunning the same
frozen ten questions.

## [2026-07-23] Hybrid retrieval mechanics were not specified
Phase/Brief: Phase 1, post-baseline retrieval optimization
Symptom: the approved next step called for hybrid lexical/semantic retrieval, diagnostics, and
source diversity but did not define tokenization, lexical scoring, fusion weights, candidate
depth, tie-breaking, diversity safeguards, neighbor priority, trace privacy, or persistence.
Cause: spec gap in the brief.
Resolution and verification: the implementation uses a corpus-agnostic NFKD Unicode word
tokenizer with possessive normalization, a versioned dependency-free BM25 scorer
(`k1=1.2`, `b=0.75`), equal-weight RRF with deterministic rank and chunk-ID tie-breaking, and the
guarded broad-query diversity rule recorded above. A versioned text-free trace records hashes,
ranks, scores, distance/fallback states, selection reasons, context order, document
distribution, corpus hashes, Chroma distance space, and every effective parameter; raw questions,
prompts, metadata blobs, and chunk text are rejected from persisted traces. Persistence is opt-in
under gitignored `runtime/` and a sink failure cannot prevent an answer. These choices are now
explicit and tested, but remain
tunable retrieval parameters rather than changes to `EVAL_CONTRACT.md`.

## [2026-07-23] Gold locations could name chunks excluded from retrieval
Phase/Brief: Phase 1, Brief 3 preparation
Symptom: gold-set validation accepted any chunk ID present in the corpus manifest, even when the
chunk's document matched `ingest.skip_files` and could never enter evaluated retrieval context.
Cause: contract/spec gap — existence and retrieval eligibility had not been distinguished in the
gold validation rule.
Resolution and verification: `EVAL_CONTRACT.md` §§2.5, 3.6, and 4.1 now require every supporting
and relevant location to both exist and be retrieval-eligible under the referenced manifest. The
validator now derives the eligible ID set from `chunks[*].document` and `ingest.skip_files` and
rejects skipped locations as hard errors. This clarification was made before a gold pilot or run
of record, so it invalidates no earlier gold entry or run-of-record evidence.

## [2026-07-23] Retrieval and evaluation had no settled opening boundary
Phase/Brief: Phase 1, Brief 3 preparation
Symptom: the contract and roadmap left front matter, the tentative Afterword, and appendices as an
open owner decision while the implementation default made most of them retrieval targets.
Cause: contract clarification and corpus-cohort opening — the brief intentionally deferred a scope
decision that became necessary before authoring gold locations.
Resolution and verification: the owner selected an Introduction-first boundary. Retrieval and
evaluation begin at `05_Introduction.md`; the four preceding structural documents and documents
matched by the existing `32_Bibliography.md` sentinel are excluded, while the Epilogue, Afterword,
and appendices remain eligible. The frozen counts are 910 total chunks, 481 eligible chunks, and
seven skipped documents. The decision preceded all gold queries and runs of record, so no result
informed it and no prior run-of-record evidence is invalidated; the revised corpus snapshot opens
the first evaluable cohort.

## [2026-07-23] Ten-item gold pilot had no mechanical final-set boundary
Phase/Brief: Phase 1, Brief 3 preparation and Brief 6 calibration pilot
Symptom: `EVAL_CONTRACT.md` defines the final 34–46-item composition, and Brief 6 calls for a
ten-item pilot spanning at least four strata, but neither specifies how an `archivist.gold/1`
pilot file is mechanically distinguished from a final gold set or prevented from being used under
the weaker validation profile.
Cause: spec gap in the brief.
Resolution and verification: gold validation now has explicit `pilot` and `run-of-record` modes.
Pilot mode requires exactly ten items, at least four represented strata, and a `-pilot` semantic
version marker; run-of-record mode rejects prerelease versions and enforces every locked §3.4
stratum range. The committed template is empty, manifest-bound, and marked `0.1.0-pilot`. Tests
prove a valid pilot cannot pass run-of-record validation. `EVAL_CONTRACT.md` is unchanged.

## [2026-07-23] Official GPT-5.6 Sol identifier does not satisfy the dated-snapshot contract
Phase/Brief: Phase 1, Brief 2
Symptom: the requested and currently documented flagship model identifier is `gpt-5.6-sol`,
but Brief 2 also requires startup rejection of every model identifier without a date suffix.
No official dated GPT-5.6 Sol identifier is documented, so those requirements cannot both govern
the interactive application without either inventing an identifier or preventing it from starting.
Cause: spec gap in the brief, surfaced by a change in available model identifiers.
Resolution and verification: interactive runtime settings and formal evaluation validation are
separated. The runtime uses the documented `gpt-5.6-sol` identifier, while
`require_run_of_record_snapshot` rejects it for a formal run. Tests prove the documented identifier
is not represented as a pin and that the contract's known dated `gpt-5-2025-08-07` form passes the
date-suffix check. `EVAL_CONTRACT.md` is unchanged, no dated identifier was invented, and a formal
run of record remains blocked until an official dated snapshot is available and selected.

## [2026-07-23] GPT-5.6 Sol opens a new generation cohort
Phase/Brief: Phase 1, Brief 2
Symptom: active answer, follow-up-resolution, and deferred index-generation requests previously
used the bare `gpt-5` alias with implicit reasoning and verbosity defaults.
Cause: cohort opening — the generation model and recorded sampling settings changed.
Resolution and verification: the generation roles now use centralized `gpt-5.6-sol` settings with
explicit `medium` reasoning effort and `medium` verbosity, preserving the former documented
effective defaults while changing the model. Focused request-capture tests verify all active
generation paths receive the correct role settings. Earlier generated outputs, if retained, belong
to the previous cohort and are not directly comparable.

## [2026-07-22] Reader-facing cost tracking required a new local accounting contract
Phase/Brief: Phase 1 reader-facing UI, owner-directed cost visibility pass
Symptom: the application made several independently billed API calls per conversation turn but
         exposed neither their returned usage nor an estimate of cumulative spend.
Cause: spec gap in the brief -- the requested cost meter did not define persistence, price-version
       handling, unknown models, invoice reconciliation, or whether a budget was a warning or cap.
Resolution and verification: completed API responses are recorded in a local SQLite ledger using
       returned token usage and a versioned rate table. The UI distinguishes this estimate from
       OpenAI's authoritative Costs data. Budgets default to disabled; the optional local hard stop
       blocks only the next request and permits an explicit one-request override. Contract tests
       cover pricing, idempotency, aggregation, unknown models, and the enforcement boundary. No
       prompt, retrieval parameter, model setting, or manuscript context changed.

## [2026-07-23] Authoritative DOCX ingest and safe index promotion were unspecified
Phase/Brief: Phase 1 corpus replacement, before Brief 2
Symptom: the repository could not mechanically prove that a supplied Word manuscript became the
         reader-active Markdown, chunks, and vectors without losing footnotes or overwriting
         unrelated project collections in the shared Chroma store.
Cause: spec gap - the corpus contract defined the finished manifest but not Word body-order
       extraction, structural end-matter mapping, note handling, staged paid embedding, rollback,
       or preservation of non-reader Chroma collections.
Resolution and verification: added a deterministic OOXML preparation path that rejects ambiguous
       revisions, comments, unresolved notes, real endnotes, and malformed structure; added a
       text-free corpus manifest; added a budget-aware fresh-index builder that reopens and verifies
       persisted vectors; and added an offline promotion assembler that preserves every unrelated
       collection. Synthetic tests cover failure atomicity and a real local Chroma round trip.
       The July 6 corpus passed two byte-identical offline preparations. After explicit owner
       authorization, 488 chunks were embedded in 10 tracked calls and the new corpus was activated
       with exact ID, metadata, text-hash, vector, and L2 checks. All nine unrelated Chroma
       collections retained identical records and metadata. The full backend suite passed against
       the active corpus, and the production frontend build succeeded.

## [2026-07-22] Combined perspective prototype split into three prompt facets
Phase/Brief: Phase 2 perspective-mode prototype, requested during Phase 1
Symptom: the combined perspective selector conflated historiographical framing, prose voice, and
         moral or metaphysical worldview, preventing those dimensions from being selected
         independently in the reader-facing demonstration.
Cause: cohort opening - non-neutral generation prompts now compose three independent,
       allowlisted Markdown facets in a fixed order.
Resolution and verification: historiographical lens, voice, and worldview are separate request
fields and their values are recorded on each answer; every all-default request still produces the
frozen neutral prompt byte-for-byte, and the settings do not enter retrieval or change the model.
Legacy combined requests map to their corresponding single facet. Tests cover the registries,
prompt composition, API mapping, and retrieval boundary. This remains an unevaluated reader-facing
prototype and is not a run-of-record cohort.

## [2026-07-22] Conversational follow-ups opened a separate reader-facing cohort
Phase/Brief: Phase 1 reader-facing UI, owner-directed conversation design pass
Symptom: follow-up questions such as pronouns or implicit references cannot be retrieved reliably
         when every request is treated as an isolated question.
Cause: cohort opening — multi-turn requests now use a separate query-resolution prompt before the
       unchanged Answer Mode retrieval and generation path.
Resolution and verification: first-turn requests remain byte-for-byte on the existing path. For a
follow-up, only the newest bounded completed turns enter the resolver; its standalone question is
used for fresh retrieval, and prior assistant prose never enters the evidence or answer prompt.
Contract tests cover the boundary. This conversational cohort is not a run of record and must be
evaluated separately from the frozen single-turn neutral cohort.

## [2026-07-21] Perspective prototype advanced before the Phase 2 measurement gate
Phase/Brief: Phase 2 perspective-mode prototype, requested during Phase 1
Symptom: the reader-facing web application now needs selectable historical perspectives before
         the neutral Answer Mode baseline and faithfulness calibration are complete.
Cause: Phase 2 concern in Phase 1 work — the owner deliberately advanced the interactive
       demonstration ahead of its scheduled brief.
Resolution and verification: perspective is confined to an optional, allowlisted generation
       overlay in the web path. Neutral remains the default and produces the frozen Answer Mode
       prompt byte-for-byte; retrieval, ordered source context, citation syntax, abstention, and
       the CLI/evaluation path remain unchanged. Contract tests verify those boundaries. The
       non-neutral perspectives are provisional and must not be treated as evaluated until each
       passes the same Phase 1 faithfulness and citation checks.

## [2026-07-21] Web index comparison context had a second Source namespace
Phase/Brief: Phase 1, Brief 1
Symptom: applying `[Source N]` independently to manuscript and existing-index blocks produced two `[Source 1]` headers, while the verbatim format example still requested `<citation label>`.
Cause: spec gap in the brief — it mandated the citation-token change but did not define numbering for the web prompt's second, comparison-only context.
Resolution and verification: comparison excerpts use unbracketed `Existing Index N:` headings and the prompt forbids citing them; manuscript chunks remain the sole `[Source N]` list, and the format example now says `[Source N]`. A synthetic prompt test asserts these properties.

## [2026-07-21] Annotation invariant included unreachable structural chunks
Phase/Brief: Phase 1, Brief 1
Symptom: the required all-disk assertion found eight title changes, all in the skipped Table of Contents document; no retrieval-eligible chunk changed.
Cause: spec gap in the brief — its rationale described evaluated context while its assertion included structural documents that cannot reach that context.
Resolution and verification: with owner approval, the blocking invariant now covers every retrieval-eligible chunk and the full corpus remains a diagnostic. Tests assert zero eligible mismatches and the known structural mismatch set.

## [2026-07-21] Chunk merging moved behind the model boundary
Phase/Brief: Phase 1, Brief 1 cohort opening
Symptom: the web path previously merged adjacent chunks before prompt construction, so one citation could resolve to several chunks.
Cause: cohort opening — a presentation operation changed what the model saw.
Resolution and verification: prompts now receive the same unmerged numbered chunks on CLI and web paths; `display_groups` preserves merged reading presentation and a test proves computing it cannot alter the prompt.

## [2026-07-21] Imported-document chunk parameters are duplicated
Phase/Brief: Phase 1, Brief 1; assigned to Brief 2
Symptom: `build_chunks_for_imported_document` hardcodes chunk size 4 and overlap 1 instead of using the constants in `ingest.py`.
Cause: duplicated configuration constant.
Resolution and verification: intentionally not changed in Brief 1. Brief 2 must give the import path one parameter source before recording chunking configuration in the corpus manifest.

## Pre-existing, logged at project setup (2026-07-21)

Found by reading `main` before Brief 1. Recorded here so they are tracked rather than rediscovered, with the brief that owns each. **None of these are to be fixed opportunistically** — each is fixed by its owning brief or not at all.

### [2026-07-21] `sources` endpoint destroys its own `document` filter
Phase/Brief: Phase 1, pre-Brief-1
Symptom: `GET /api/projects/{id}/sources?document=X` does not filter to document X.
Cause: model error. In `web_api.sources`, the function parameter `document` is reassigned inside the chunk loop (`document = str(chunk.get("document", ""))`). By the time `if document:` is evaluated it holds the last processed chunk's document name, so the filter always applies using that value regardless of what the caller asked for.
Resolution and verification: **unowned — not in scope for Brief 1.** Brief 1 is a unification brief and fixing an unrelated bug inside it would make its equivalence assertions unverifiable. Assign to Brief 8 or a standalone fix. Verification when fixed: request two different documents, assert the returned sets differ and each matches its requested document.

### [2026-07-21] Nothing in the repository runs from a fresh clone
Phase/Brief: Phase 1, pre-Brief-1
Symptom: `import retrieval` raises `FileNotFoundError` on a clean clone; `pip install -r requirements.txt` fails.
Cause: model error, two independent causes. `output/` is gitignored while `corpus.py` calls `load_chunks()` at module import, so every dependent module raises on import. Separately, `requirements.txt` is UTF-16 encoded, contains a corrupted entry (`chromadb==1.5.5dir`), and ends with duplicated unpinned lines.
Resolution and verification: both owned by **Brief 1** — the lazy corpus accessor, and `pyproject.toml` + `uv.lock` replacing `requirements.txt` rather than patching it. Brief 1 cannot collect its own tests otherwise. Verification: a clean clone installs and `pytest` collects without `output/chunks.json` present.

### [2026-07-21] Retrieval core duplicated across three modules
Phase/Brief: Phase 1, pre-Brief-1
Symptom: `get_filtered_primary_chunks` and `expand_with_neighbors` exist in both `retrieval.py` and `web_project.py`; `query.py` carries a third partial copy of the embed-and-query path that applies neither filtering nor expansion.
Cause: retrieval primitive duplicated rather than parameterized. The web copies take a `lookup` argument the originals do not, which is a parameter difference presented as a code fork.
Resolution and verification: owned by **Brief 1**. Verification: exactly one definition of each primitive in the package, asserted by a test that greps the source tree.

### [2026-07-21] Two Answer Mode prompts, one a silent subset of the other
Phase/Brief: Phase 1, pre-Brief-1
Symptom: `ask.py` and `web_project.answer_project_question` send different instructions for the same task. The web prompt omits three instructions present in the CLI prompt: per-claim splitting within a sentence, the multi-source `[Source 2, Source 3]` form, and "Be precise, avoid vague generalizations, and do not invent information."
Cause: model error — drift, not design. There is no recorded reason for the omissions.
Resolution and verification: owned by **Brief 1**; the CLI text becomes the single prompt. Verification: byte-identical prompt text emitted by both paths for identical inputs.

### [2026-07-21] `docs/evaluation.md` asserts a claim it cannot support
Phase/Brief: Phase 1, pre-Brief-1
Symptom: the document reaches the verdict "Accurate citations" while printing only chunk IDs and paragraph ranges, never chunk text. Neither a reader nor the author can check whether `[Source 1]` contains the claim attached to it.
Cause: spec gap — an evaluation document with no computable criteria. All seven verdicts are of this form.
Resolution and verification: owned by **Brief 7**, which replaces the file wholesale. It is not amended in the interim and is not cited as a baseline.

### [2026-07-21] Model alias in generation configuration
Phase/Brief: Phase 1, pre-Brief-1
Symptom: `ask.py`, `index_mode.py`, and `web_project.CHAT_MODEL` all specify `"gpt-5"`.
Cause: model alias where a dated snapshot is required. The alias currently resolves to `gpt-5-2025-08-07`, which OpenAI has scheduled for removal from the API on 11 December 2026; an alias re-points silently, so any run recorded against it is unreproducible.
Resolution and verification: owned by **Brief 2**. Verification: run identity records a dated snapshot string, and a startup assertion rejects any model string without a date suffix.

### [2026-07-21] Distance threshold in undetermined units
Phase/Brief: Phase 1, pre-Brief-1
Symptom: `MAX_PRIMARY_DISTANCE = 1.05` filters on a distance whose metric is never specified. The collection is created via `get_or_create_collection(name="manuscript")` with no `metadata={"hnsw:space": ...}`, so Chroma's default applies.
Cause: spec gap. Ranking is unaffected by the choice on unit-normalized embeddings, but the threshold's meaning is not, and a cut point with no stated units cannot be tuned deliberately.
Resolution and verification: owned by **Brief 2** — determine the space empirically from the installed Chroma version, record it in the corpus manifest, set it explicitly thereafter. Verification: `hnsw_space` present and non-null in every run identity.

### [2026-07-21] Distance filter can silently no-op
Phase/Brief: Phase 1, pre-Brief-1
Symptom: when every retrieved chunk exceeds `MAX_PRIMARY_DISTANCE`, `get_filtered_primary_chunks` returns the unfiltered set instead of an empty one. Retrieval therefore never returns "nothing relevant," and no signal distinguishes a confident retrieval from a fallback.
Cause: model error, arguably deliberate. Not fixed here either way — the behaviour is measured before it is changed.
Resolution and verification: **not a fix; a measurement.** Owned by **Brief 4**, which counts fallback events per question and reports the rate per stratum. A change to the fallback behaviour is licensed only by that number.

### [2026-07-21] Index Mode exact-match path is unranked
Phase/Brief: Phase 2, pre-Brief-9
Symptom: for `Virginia Company`, the eight sources supplied are Chapter 3 chunk `_010` followed by Chapter 4 chunks `_002`–`_009`, stopping there — corpus order, earliest occurrences, nothing from Chapter 5 where the Company's dissolution is discussed.
Cause: model error. `find_exact_match_chunks` returns every chunk containing the term in corpus order, and those fill `MAX_FINAL_SOURCES` before semantic results are consulted. The prompt then asks the model to identify "the strongest candidate locations" from a set that was never ranked. `docs/evaluation.md` records this case as "✅ Fixed and reliable."
Resolution and verification: **Phase 2, Brief 9.** Explicitly not fixed in Phase 1. Verification when fixed: for a term appearing in more than `MAX_FINAL_SOURCES` chunks, the supplied set is not the first N in corpus order.
