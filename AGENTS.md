# AGENTS.md — Archivist Standing Rules

These rules apply across every brief in this project, independent of any single brief's scope. Check them before starting implementation on any brief.

## What Archivist is

Archivist is a **retrieval-augmented question-answering system over one long-form historical manuscript**. It is not a general document-QA tool; *A Big History of Virginia* is the corpus it is built for and evaluated against. But nothing in the retrieval or generation machinery may branch on that fact — anything that would break on a different manuscript of the same shape is a bug.

The distinction that matters, because it is the one most likely to erode: **the system is optimized for a known corpus and its plumbing is corpus-agnostic.** Optimizing for the corpus means tuning retrieval parameters, chunking, and prompts against measured behavior on this book. It does not mean typing "Virginia," "Powhatan," or a chapter name into engine code. If you find yourself special-casing a person, place, or chapter, that is scenario logic leaking into the engine — log it.

The corpus is also the moat. Rigorous evaluation depends on knowing the source material well enough to state what a correct answer is; that is only possible because the project owner wrote the book. A generic ingest-anything tool would forfeit exactly that.

## Current priorities and answer surfaces

The source tree now implements `retrieval-authored-v4`; the highest-leverage unfinished product
work is a separately authorized measurement of that new default without altering the completed
V26 records or the terminal v3 timeout-diagnostic cohort. Recent ad hoc manual turns exposed and diagnosed a
provider-schema defect and a missing personal-conversation contract, but they are not a declared
smoke, latency cohort, or quality cohort and do not prove either repair in live behavior. The
earlier authorized
three-mode Edwin Sandys smoke measured the now-superseded `application-compiled-v1` cue selector;
its 8.357, 6.839, and 5.162-second calls and `$0.060071250` estimated cost are historical
compatibility evidence only and are not evidence about the current authored-response path. The highest-leverage unfinished
measurement work is now encoded in a v4-specific adapter but has made no live call. It must first
exercise a fixed ten-question Professional prefix once, then run the remaining 27 only if the
predeclared mechanical gates pass; claim decomposition and the four-mode social suite remain
separate phases. The
completed baselines and production cohort must stay unchanged. The objective is not "the answers
look good." Retrieval, faithfulness, citation, abstention, release reliability, latency, and spend
must be measured, bounded, reproducible, and have their failures written down. A system with
mediocre but characterized numbers is better evidence than a system with excellent-looking answers
and no defensible measurement.

As of 2026-08-09, the 37 retained owner-controlled held-out questions and their owner-adjudicated
annotations are formally locked against frozen V26 candidate
`8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e`. H020, H039, and H040 are intentionally absent.
Historical Claude drafting is disclosed retrospectively under provenance v4; the repository must
not claim that it was prospectively blinded or fully hash-captured. The predeclared retrieval-only
benchmark and the first descriptive answer-quality baseline are complete. Recovery-04 preserves
all 37 V26 answer artifacts: 35 completed/released answers and two generation-side technical-error
artifacts. The earlier H003 local-release incident remains preserved through its audited sibling
migration, with no provider replay and 36 exact observations in the 37-item generation-latency
scope. Canonical measurement made exactly one `gpt-5.6-terra` attempt for every answer and no item
was retried or repaired. Ten attempts produced usable decompositions; 27 are disclosed technical
measurement failures—26 `exact_span_mismatch` and H029's one `incomplete_response`. Those 27 are
failures of the Terra decomposition instrument, not findings that V26 failed 27 answers.

The completed baseline contains 198 sources, 251 citation references, and 41 claims from the ten
schema-valid decompositions. Two of those ten belong to generation-error artifacts and contain zero
claims, so claim-derived metrics cover eight substantive releases. Its immediately available
mechanical results are citation resolvability
251/251 (1.000), malformed citations 0/250, citation completeness 34/41 (0.829), cited-source to
gold-location match 23/34 (0.676), and gold-location retrieval coverage 75/428 (0.175). Answer-level
citation syntax measures retain their full applicable denominators; claim- and decomposition-
dependent measures use only those eight substantively decomposed releases. Semantic answer-quality
measures remain pending by design, so this is a complete descriptive baseline rather than a complete semantic
scorecard. The closed ledger has 125 priced events, zero unpriced events, and `$7.02298147` in
recorded spend, safely below the authorized `$20.00` cap.

The first production-performance cohort is also complete. Against deployed wrapper commit
`e71d9b79a60a894cb38451c37e0d43b7f9149fa9`, it attempted exactly 33 fresh
Essential/Complete/RAG first turns with no retries or replacements. Twenty-nine were valid public
response-contract completions and four failed (12.1212%); instrumentation failures were zero.
Server p50/p95 were 54.393/113.801 seconds over the 29 successful completions. Usage closed at
500,164 tokens, 80 priced and zero unpriced events, and `$4.90594694`. The four failures were
fail-closed generation-contract rejections after successful planning and direct-answer evidence
selection: two `missing_unit_requirement_id`, one `obligation_role_mismatch`, and one
`unsupported_requirement_has_unit`. Never retry, replace, or overwrite this cohort. Repair those
relationships with synthetic cases, then use a separately versioned cohort for any comparison.

The v3 Professional cohort is terminally closed as a timeout diagnostic rather than a quality
cohort. It attempted all 37 generations exactly once: 30 authored responses and seven Essential
fallbacks. It stopped after 14 held-out decomposition attempts, ran zero rubric calls, and recorded
`$1.591521500`; its provider-free closure made zero calls. Never resume, retry, or overwrite it.

The next measurement priority is to measure v4 with the redesigned decomposition instrument in a
new, explicitly separate measurement cohort. The V26 instrument's 27/37 technical-failure rate sharply limits how far
the current claim-derived metrics can be interpreted. Never change, repair, or rerun this completed
baseline to improve those denominators, and never treat the 27 instrument failures as empty claim
sets or candidate-answer failures. A later low-priority calibration or semantic supplement may add
faithfulness and abstention results without overwriting the baseline. Once an H-item is run, never
change the gold set or V26 in response to its result; any later system or instrument change opens a
new cohort rather than repairing this one in place.

The product has nevertheless moved beyond the original two-phase description. Reader-facing
appearance and interpretive modes are implemented and public; they are no longer forbidden work.
Index Assistant Mode remains deferred and requires its own measurement before repair or promotion.
Do not mistake a shipped reader feature for completion of the evaluation.

Archivist currently documents seven answer-policy families, including superseded product paths:

- **`retrieval-authored-v4`.** This is the default for current built-in RAG. For manuscript and
  historical questions, Archivist retains the v1 evidence path: it resolves
  high-confidence ordinary follow-ups locally, makes one `text-embedding-3-small` query-embedding
  request, and runs the shared dense/BM25 reciprocal-rank-fusion retrieval and context finalizer.
  It packages four to eight finalized units in retrieval order, targeting about 2,500 estimated
  evidence tokens with a hard 4,500-token evidence ceiling. Whole chunks are preferred; only a
  range of complete paragraphs may be used when the hard ceiling requires shortening. Essential
  makes no prose-generation call, but it is not providerless because it uses the shared embedding
  request. Every registered generated mode -- currently Professional, Pretty Pink Princess,
  Baleful Black Baron, and Ruthless Red Realist -- adds exactly one
  no-retry `gpt-5.6-sol` authored-response call with low reasoning, medium verbosity, and a 1,800
  output-token ceiling. The embedding and authoring operations share one 35-second provider
  deadline: retrieval receives at most eight seconds and authoring receives at most thirty seconds
  of whatever time remains; exhausted headroom returns direct Essential evidence rather than
  starting another call. The model may freely synthesize and choose useful length. It returns typed
  grounded and persona runs plus one to three in-character follow-up questions. The provider-visible
  input/output schemas remain `archivist.authored_response_input/1` and
  `archivist.retrieval_authored_answer/1`; rendering remains `retrieval-authored-renderer-v1`.
  The v4 policy identity records the longer authoring deadline and granular diagnostics, not changed
  wire shapes. The
  schema exposes grounded and persona runs as mutually exclusive object variants: every grounded
  run requires at least one opaque dossier-unit ID, while persona runs cannot carry support IDs.
  Local code validates grounded IDs and maps them to `[Source N]`. Timeout, transport failure,
  provider exception or refusal, structured-output rejection, or local contract-validation failure
  is recorded with a text-free diagnostic code and falls back to direct Essential evidence without a
  retry. An accepted generated-mode fallback remains a successful cited answer, but the browser
  must identify it with the nonfatal **Essential fallback** notice: “Archivist could not complete
  the {Mode label} AI response, so it returned Essential's direct manuscript evidence instead.”
  Ordinary Essential and successfully authored answers show no such notice. These five modes and
  linked appearances are the only current UI/API choices; dormant
  definitions and assets are compatibility-only.
  Before any manuscript retrieval, a narrow local router may recognize a social or personal
  question in any registered generated mode. This registry-derived rule includes Professional,
  Pretty Pink Princess, Baleful Black Baron, and Ruthless Red Realist now and automatically covers
  a future mode when it registers both authored-response and character-conversation instructions.
  Essential has no generated-mode contract and is excluded. The branch sends only the
  conversational question and character instructions to exactly one compact, no-retry
  `gpt-5.6-sol` call with a 12-second timeout. It sends no manuscript text, retrieved evidence, dossier, or embedding
  request; it returns no manuscript citation and must end with one or more in-character questions
  that lead the reader back into *Cradle of the Empire*. A provider, refusal, or structural failure
  on this branch returns deterministic application-owned dialogue for the selected character,
  never Essential evidence. It must not become a general factual-chat route: historical,
  manuscript, or mixed factual questions continue through retrieval and the grounded dossier.
  Its input/output schemas remain `archivist.character_conversation_input/1` and
  `archivist.character_conversation_answer/1`, and its renderer remains
  `character-conversation-renderer-v1`; `character-conversation-v2` records the generalized routing
  contract rather than a changed wire shape.
- **`retrieval-authored-v3`.** This is the immediately preceding generated-mode policy. It used the
  same Sol prompt, strict `/1` schemas, 1,800-token ceiling, single client, and no-retry contract,
  but shared a 25-second provider deadline and capped authoring at twenty seconds. Its terminal
  diagnostic cohort observed 30 authored responses and seven Essential fallbacks across 37
  one-attempt generations; decomposition stopped after 14 attempts and rubric/persona scoring did
  not begin. Those observations remain v3 evidence and are not v4 performance claims.
- **`retrieval-authored-v2`.** This is the immediately preceding character-conversation candidate.
  It preserved the v1 historical/manuscript path and added `character-conversation-v1` only for
  Pretty Pink Princess and Baleful Black Baron. Professional still sent a personal question through
  retrieval, and future generated modes would have required another hard-coded route edit. Its
  offline checks and ad hoc observations remain attached to v2; they are not v3 evidence.
- **`retrieval-authored-v1`.** This is the immediately preceding authored-response candidate. Its
  historical/manuscript design remains preserved as historical/manual candidate evidence, but it
  has no pre-retrieval character-social branch and is not the default or a selectable API policy. Its
  ad hoc manual observations and offline checks remain attached to v1; they are not v2 latency,
  quality, or reliability evidence.
- **`application-compiled-v1`.** This is the superseded 2026-08-12 cue-selector design. Preserve
  its narrow smoke and documentation as historical evidence, but do not describe its three
  32-word cards, zero-provider Essential path, or locally authored cue prose as current behavior.
- **`evidence-planned-v26` and V27 compatibility policies.** Frozen V26 remains immutable, callable
  only by an explicit development/evaluation policy, and continues to identify its completed
  cohorts. V27 compact remains an unpromoted historical experiment. Its former reader-facing
  selector is removed. Neither policy is the current product default.
- **`full-context-v2`.** This separately versioned experiment supplies the complete eligible corpus
  and intentionally bypasses query planning, ranking, retrieval, neighbour expansion, and the RAG
  evidence-obligation contract. It shares corpus-integrity, conversation, cost, mode-style,
  citation-remapping, and public-disclosure boundaries where those concepts apply. It is disabled
  by default and must remain behind the server-side full-context flags; the public flag cannot
  enable it unless the general flag is also enabled. Essential is incompatible with this generative
  scope and API requests combining Essential with Full Context are rejected. Never mix its results
  into a retrieval cohort.

## The layers

In decreasing order of fixedness. Changes to a lower number are more expensive and more dangerous.

1. **The measurement contract (`EVAL_CONTRACT.md`).** Run identity and cohorts, the corpus contract, the gold-set schema, and the exact definitions of recall@k, citation accuracy, faithfulness, and abstention.

   This is the experimental control, and it plays the role invariants play in a simulation project. **Implement the definitions exactly as written; never adjust one to make a number come out better.** Only the project owner may change them, and any change must be logged in `DEFECTS.md` as a contract change and treated as invalidating every earlier run for comparison. If a result only holds because a metric definition moved, the result is worthless.

   Sections settle on their own clocks. §§1–5 — run identity, the corpus contract, the gold-set schema, retrieval recall, citation accuracy — are settleable at the desk and are locked. §6 faithfulness and §7 abstention are drafted but **not yet settled**, because judge agreement and threshold placement can only be answered by a later calibration exercise. That work begins only after all 37 baseline answers and canonical decompositions are preserved, and its pending state cannot delay the baseline. The sections lock once calibration has answered what only runs can answer. There is no category of formal metric that stays permanently adjustable.

2. **The system under test.** The current Essential retrieval-authored path, any generated-prose
   mode and its model configuration, the frozen V26 candidate when reproducing its cohort, and any
   separately declared experimental arm. Freely changeable — that is the point — but every
   behavioral change either opens a new run cohort or is a defect, and which one it is must be
   stated (see Run identity and cohorts). A reader mode's interpretive prompt is behavior, not mere
   presentation.

3. **Presentation.** Citation rendering, source disclosure, layout, animation, and appearance CSS.
   Pure presentation changes must not alter what the model sees. If one moves an Essential metric,
   the boundary has been violated and that is a defect.

## The gold set is not a target

**Never edit a gold entry after seeing what the system produced for it.**

This is the single easiest way to destroy the project's value and it will feel reasonable every time. The system returns an answer that disagrees with the gold answer; on inspection the gold answer looks arguably too strict, or the "known location" looks arguably incomplete, and widening it turns a failure into a pass. Sometimes the gold entry really is wrong — the corpus is 594 pages and the author is human. The rule is not "gold entries are infallible." The rule is about **provenance and timing**:

| | Situation | Verdict |
|---|---|---|
| **Legitimate** | A gold entry is found to be factually wrong about the manuscript, independent of any system output — the cited chunk genuinely does not contain the claim | Correct it. Log the correction in `DEFECTS.md`, bump the gold-set version, and treat prior runs as a different cohort. |
| **Not legitimate** | A gold entry is widened, softened, or relocated *because* a run failed it | Tuning to the test. Do not. Log the impulse instead. |

The test is whether the correction would have been made had the run passed. If the answer is no, it is not a correction.

The same applies to metric definitions. "Recall@k should probably count a neighbouring chunk as a hit" may well be true — but decided *after* seeing a bad recall number, it is indistinguishable from moving the goalposts. Raise it, log it, change it deliberately as a contract change, and re-baseline.

**Never send an `H###` held-out item to Archivist, its retriever, planner, answer model, judge, or a
system-informed annotation workflow before the final gold set and provenance sidecar are locked.**
An H-item may be inspected directly against the private corpus for owner adjudication, but it may
not become development data. If an H-item is exposed accidentally, record the contamination and
replace or reclassify it under the contract; do not quietly keep it held out.

## External and paid operations require authorization

No API call, embedding request, hosted-model query, external upload, paid evaluation, live smoke
test, or other network operation that can disclose private material or incur cost is authorized by
an implementation request alone. Obtain explicit owner authorization for the specific operation,
scope, data, and reasonable cost ceiling before starting it. An earlier authorization does not
silently cover a later cohort, retry, or expanded corpus.

Offline inspection, linting, unit tests, builds, and local deterministic audits are safe defaults.
Never convert an offline verification command into a live call by supplying credentials or enabling
network-backed fixtures without saying so first. Automatic paid retries are forbidden.

## Wanting to skip the measurement is data

The project's recurring failure mode is documented and expected: **exciting work crowds out the tedious high-leverage work.** New reader modes, visual polish, and speculative retrieval changes are all more enjoyable than adjudicating a held-out cohort with known answers and running a harness.

Concretely, this has already happened once. A generic multi-project upload-and-index stack exists in `src/web_api.py` and `src/web_project.py` — an architecturally satisfying generalization that was built while the evaluation was not. That is not a criticism of the code; it is the pattern, in evidence, in this repository.

If you find yourself wanting to improve retrieval before it has been measured, that impulse is not a licence — but it is information. Write down what you wanted to change and why in the brief's completion notes. That list is the raw material for the post-baseline briefs, which respond to measured weaknesses rather than guessed ones. A change made before the baseline exists cannot be shown to have helped.

## One retrieval core

There is exactly **one** implementation of each retrieval primitive — BM25 ranking, distance
filtering, neighbour expansion, context finalization, and context building. The
retrieval-authored path uses the shared dense retriever, BM25 ranker, reciprocal-rank fusion, and
context finalizer; explicit V26/V27 policies use their existing shared retrieval core. A
mode-specific variation is a parameter on a shared function, never a second copy of it.

Prior to Brief 1 there were three partial copies (`retrieval.py`, `web_project.py`, `query.py`). The
duplication was drift, not design, and it will re-form the moment a mode asks for "just a small
variation." Log any new duplicate as a defect.

`full-context-v2` is the deliberate exception to the *use* of retrieval, not an alternate
implementation of it. Because that strategy supplies the entire eligible corpus, retrieval
ranking and expansion have no referent and are intentionally bypassed. Do not force it through RAG
primitives merely to make the architectures look alike, and do not let it grow duplicate RAG
primitives.

**Transferability is demonstrated by corpus-agnostic plumbing and shared retrieval primitives, not
by a public upload-anything surface.**

## The citation contract

**In the historical/manuscript branch of `retrieval-authored-v4`, the generated modes own their
prose and local code owns citation resolution.** The model may synthesize and paraphrase the
dossier rather than copy fixed excerpts.
It must classify each output run as grounded or persona material and attach existing opaque
evidence-unit IDs to every grounded run. This is also a provider-visible, mutually exclusive schema
choice rather than a rule introduced only after parsing: the grounded variant requires a nonempty
support-ID list and the persona variant permits no support IDs. Local validation rejects unknown IDs, forged citation
labels, links, HTML, malformed structure, and extended manuscript copying, then maps valid IDs to
mechanically assigned `[Source N]` citations. This proves that the referenced dossier units exist;
it does **not** mechanically prove that each sentence is semantically entailed by those units or
that the model classified every sentence correctly. Never describe local ID resolution as a
faithfulness or semantic-entailment judge. Essential displays locally compiled direct evidence
from the same retrieval result. The v4 character-social branch is deliberately outside this
citation contract: it receives no evidence and may emit only fictional persona conversation plus
manuscript-leading questions, not uncited historical claims. Explicit v1/V26/V27 retrieval-backed
generation retains its historical model-facing
`[Source N]` contract. The separately versioned `full-context-v2` experiment instead returns stable
chunk IDs in its structured claim payload; local validation resolves those IDs against the exact
supplied corpus and mechanically renders the same compact `[Source N]` presentation. The UI never
invents, parses, or renumbers citations.

Human-readable citations — `Chapter 4 Cradle of the Empire (1601 – 1622), ¶49–52` — are **presentation**. They are attached to each source in the API payload and rendered by the frontend by substitution. They never appear in the prompt.

The reason is measurement, not taste. `[Source 3]` resolves to exactly one chunk, which makes citation accuracy a mechanical check. A prose label must be parsed back out of generated text, where it can be truncated, paraphrased, or malformed — so label-formatting failures would mix into the grounding numbers as a confound, and a metric that cannot separate two failure modes cannot direct a fix.

## Run identity and cohorts

A question does not identify a run, and neither does a date. Every eval run records, and reproduction requires, all of:

**corpus manifest hash · gold-set version and hash · prompt version hash · generator model identity · judge model identity · retrieval parameters · commit hash · `working_tree` · `dirty_fingerprint` · dependency-lock hash**

Runs of record require a **clean working tree**. A dirty run is permitted — exploration is the normal case — and records `"working_tree": "dirty"` plus `dirty_fingerprint`: SHA-256 over `git diff HEAD` concatenated with the contents of every untracked non-ignored file, in `git status --porcelain` order. Untracked content belongs in the fingerprint because a new source file otherwise changes behaviour while leaving the fingerprint unchanged. **A dirty run may never be cited as a run of record**, and may never appear in `docs/evaluation.md`.

**Prefer immutable dated model snapshots and never invent one.** When the provider exposes a dated
snapshot, request and record it. OpenAI's catalog currently exposes only the canonical current-
snapshot identifiers `gpt-5.6-sol` and `gpt-5.6-terra`, with no immutable dated variants. The first
answer-quality cohort may therefore use those exact identifiers only while binding the committed
provider-catalog observation, recording both requested and provider-returned IDs for every paid
operation, preserving role-specific settings and response IDs, and stating that provider-side
weights may change behind those names. A returned identifier that differs from the predeclared
catalog identifier invalidates the cohort. The generator and judge remain different predeclared
identifiers; a future dated snapshot opens a new cohort.

**Two different things invalidate a comparison, and they are not the same:**

| | Changed | Consequence |
|---|---|---|
| **Contract change** | a definition in `EVAL_CONTRACT.md`, or a gold entry | earlier runs invalid as evidence about system quality; log in `DEFECTS.md` |
| **New cohort** | prompt text, model identity or settings, `n_results`, `MAX_PRIMARY_DISTANCE`, `MAX_FINAL_SOURCES`, chunking parameters, the corpus snapshot | earlier runs stay valid; they belong to a different cohort |

Runs are comparable **within** a cohort, never across. Raising `MAX_FINAL_SOURCES` from 8 to 12 opens a cohort; it is not a contract edit, because no definition moved. Redefining what counts as a retrieval hit is a contract edit even if no code changes.

## Non-determinism rules

The success criterion is a before-and-after comparison across code versions, so controlling variance is load-bearing rather than housekeeping.

- **Pin the generator identifier explicitly.** Use an immutable dated snapshot when one exists.
  When the provider exposes only a canonical current-snapshot identifier, the narrow catalog-bound
  exception in Run identity applies and its reproducibility limitation must be reported.
- **The judge model is a separate pinned identity from the generator**, recorded independently. If the two are the same string, a generator upgrade silently moves the judge and every faithfulness delta becomes uninterpretable. They must be able to move independently, and in general the judge should not be the model under test.
- **Set every sampling parameter the API exposes and record it** — temperature, top_p, seed, reasoning effort, verbosity — rather than relying on defaults, which are not stable across snapshots.
- **Residual non-determinism is expected and must be measured, not assumed away.** The first
  complete 37-item run is a descriptive baseline and may report exact denominators while stating
  explicitly that generator spread has not yet been measured. Before any later before/after,
  significance, or production-guarantee claim, repeat one fixed subset **five times unchanged**
  and report that spread alongside the comparison. A change smaller than the measured spread is
  not a result.
- **Judge calls carry no conversation state.** One question per call, no shared history, no batching several gold items into one prompt — batching lets one item's judgement contaminate the next.

The fixed ten-item calibration subset is not a preliminary quality gate or a disposable pilot. It
is drawn from the already preserved 37-item cohort only after every answer and canonical
decomposition exists. Calibration locks how semantic dimensions are scored, not whether the
candidate deserves to run or whether results may be reported. If the automatic judge misses its
predeclared agreement thresholds, use manual scoring for the affected dimensions or report them
pending; judge failure must not alter, delay, rerun, or suppress any of the 37 preserved answers.

“Uninterrupted” forbids behavioral intervention, not exact fail-closed recovery. A provider-free
resume may reuse sealed work after a harness stop. If accepting a valid old artifact requires a
harness correction, keep the source root immutable and migrate into a distinct sibling root under
a sealed audit; inner answer payloads, trace evidence, local early-release outcomes, and usage
events must remain unchanged. Never retry an H-item merely because its answer, abstention, or error
is unfavorable. Disclose recovered items and missing latency observations in the public report.

## Define what you test

Every brief must convert the terms it tests into explicit, computable metrics before it can claim to pass. Prose like "accurate," "grounded," "relevant," "good synthesis," or "strong performance" is not an acceptance criterion.

This is not hypothetical. The current `docs/evaluation.md` reaches verdicts of exactly that form — "High relevance," "Good synthesis," "Accurate citations," "✅ Strong performance" — across seven hand-picked queries, with no numbers, no denominators, and no gold set. It also asserts citation accuracy while printing only chunk IDs and paragraph ranges, never chunk text, so the claim is not checkable from the document even in principle. That file is the specimen this rule exists to prevent recurring, and Brief 6 replaces it.

If a brief tests a behavior, it states the number: k for recall, the threshold that constitutes a hit, the rubric levels a judge may return, the agreement rate that qualifies a judge for use, the spread below which a delta is noise. A criterion that can't be computed can't fail, and a criterion that can't fail isn't testing anything.

### Development sentinels do not hide the cohort

The repeatedly used practical questions `G001`–`G010` are development data, not held-out gold.
A focused item may run first to prove that a changed parser, allocator, trace, citation mapper, or
other measurement boundary works. It may block the broader development run only on a
**predeclared mechanical invalidity**: wrong frozen identity, dirty tree, unintended call or retry,
invalid trace, broken identifier mapping, or cost-safety stop.

Its answer-quality score is never a promotion veto. Once the focused measurement is mechanically
valid, run the complete unchanged practical cohort and report the difficult item inside that
profile, even when it misses a previously used claim-coverage or target-coverage threshold.
Formal quality gates belong to the owner-designed and owner-adjudicated held-out gold contract, its
scoring lock, and any later predeclared comparison criteria—not to one question repeatedly used to
guide repairs. The first complete 37-item answer cohort is descriptive rather than a pass/fail gate.

## Controlled private corpus boundary

The manuscript is a commercial product. "Private" has several distinct, explicitly controlled
contexts; it does not mean "only on one developer machine":

- **Local private runtime.** Source files, extracted chunks, indexes, annotation drafts, and runtime
  bundles may exist in gitignored local directories for development and evaluation.
- **Private hosted runtime.** The complete retrieval corpus may exist on the private Render service
  and persistent disk required to operate the public demo. The public interface must not expose
  that store as a browseable document service.
- **Owner-authorized external annotation.** A declared question batch and the necessary private
  corpus material may be sent to an external annotation model only after the owner explicitly
  authorizes that provider, data scope, and operation. Follow
  `docs/gold_annotation_prompt_claude.md`; keep the assistant blinded to Archivist outputs and
  development results. This narrow authorization is not permission for any other upload or model
  call.

The present held-out cohort does **not** use that prospective workflow. Parts of its annotations
began as historical Claude drafts whose exact model, surface, raw response record, and prospective
blinding evidence were not captured. Retain the owner-adjudicated annotations, disclose those
limits under `archivist.gold_provenance/4`, and do not reconstruct evidence that does not exist.

The hard boundary rules are:

- **No manuscript text is committed to the repository, ever** — not in fixtures, test data,
  example outputs, docstrings, briefs, or logs. `manuscript/`, `output/`, `projects/`, private
  annotation drafts, vector stores, and runtime bundles stay gitignored.
- **Committed artifacts reference the corpus by identifier and hash, never by content.** Chunk IDs,
  paragraph ranges, document names, edition locators, and SHA-256 digests are the allowed binding
  material.
- **Gold questions, strata, Behavior values, and inclusion decisions are owner-authored without
  candidate output.** Model-drafted annotation prose has no authority until the owner verifies and
  adjudicates every field directly against the private corpus. Any claimed blinding or raw-draft
  provenance must be supported by records created at the time, never inferred later.
- **All accepted gold-set annotations are source-verified and consciously adopted or revised by
  the owner.** Accurate AI-drafted wording need not be performatively paraphrased, but committed
  prose must remain a paraphrase rather than copied manuscript text. Raw drafts remain private and
  gitignored.

For public deployment, responses expose generated prose, edition-qualified locations, and only
tightly bounded cited excerpts—never whole chunks. Arbitrary source browsing and source-file
streaming stay disabled. Server-side exposure profile, rate, concurrency, abuse, quotation, and
spend controls are fail-closed and cannot be selected by the client. Development endpoints that
return full text are not public-deployable.

Reader-facing page citations are edition-specific presentation metadata. Every page or location
must name its edition profile (for example, `Typeset PDF (July 6, 2026), pp. 33-35`), and a new
paperback, hardcover, or ebook profile must bind to its own source hash. Locator changes must not
alter retrieval, source ordering, the `[Source N]` contract, or evaluation results. See
`docs/public_demo_design.md`.

## Defect log

Log to `DEFECTS.md` whenever:

- a gold entry or metric definition is suspected of having been changed in response to a result
- a presentation-layer change moved a measured number
- corpus-specific logic has leaked into engine code
- a retrieval primitive has been duplicated rather than parameterized
- a reader mode changed retrieval/evidence behavior, or its result was represented as evidence for
  the Essential evaluation cohort without a declared comparison
- a prose model could attach a valid evidence-card ID or citation to factual text that the
  application did not compile from that card
- `full-context-v2` was silently substituted for retrieval, enabled outside its flags, or mixed into
  a retrieval cohort
- a metric's run-to-run spread exceeds the effect being claimed
- manuscript text has entered a committed file
- an H-item was exposed to Archivist or candidate-informed material before the gold lock
- an external or paid call ran without the owner's explicit authorization
- **the brief itself was underspecified and the implementer had to invent a mechanic**

That last one is not a courtesy entry. **A gap in the brief is a defect**, logged the same as a code fault. On the previous project most defects traced to specification gaps rather than to model output, and that pattern only became visible because they were counted.

Use the entry format at the top of that file.

## Language and tooling

| | Pinned | Why |
|---|---|---|
| Language | **Python 3.13** | Matches the ecosystem baseline used across the owner's projects; supported by every relevant package. |
| Deps & venv | **uv** | One tool for install, virtualenv, resolution, and lockfile. Commit `uv.lock`; its SHA-256 goes in every run identity. |
| Tests | **pytest** | |
| Lint & format | **ruff** | |
| Vector store | **ChromaDB, persistent; HNSW `l2`** | The corpus manifest pins the store contract. |
| Embeddings | **`text-embedding-3-small`** | Current, not deprecated, and re-embedding is expensive — no reason to move. |
| Interactive authored response | **`gpt-5.6-sol`, low reasoning, medium verbosity, at most 1,800 output tokens, exactly one no-retry call** | Applies to every registered generated mode after one shared query-embedding call: currently Professional, Pretty Pink Princess, Baleful Black Baron, and Ruthless Red Realist. It writes the answer and follow-up questions over the rich dossier. Essential omits this prose call but still uses the embedding provider. |
| Character conversation | **`gpt-5.6-sol`, low reasoning, low verbosity, 12-second timeout, at most 576 output tokens, exactly one no-retry call** | Applies to narrowly classified social/personal turns in every registered generated mode, including future modes added through that registry. Essential is excluded. It receives no manuscript or evidence, writes no historical claims or citations, and falls back locally in the selected character. |
| Formal generation/judging | **Dated snapshots when exposed; otherwise catalog-bound canonical IDs** | Bind the catalog observation plus requested/returned IDs, report the limitation, and keep generator and judge independent. |

### Distance contract

`fixtures/corpus_manifest.json` pins `store.hnsw_space` to **`l2`**, the embedding model to
`text-embedding-3-small`, the collection name, and the embedded chunk count. Runtime corpus
preflight must reject a collection whose configuration disagrees with that manifest. Changing the
space, embedding model, chunking, or distance threshold opens a new cohort and may require a new
index; never infer or silently substitute those values.

## Offline verification

From the repository root, the current complete offline verification sequence is exactly:

```powershell
uv run ruff check src tests scripts
uv run pytest
Set-Location frontend
npm run test:delivery
npm run test:modes
npm run build
Set-Location ..
```

These commands must not make OpenAI calls or require an API key. Run the smallest focused tests
while iterating, then this complete sequence before handing off a broad backend/frontend change.
If the suite cannot run because of an environment or filesystem failure, report that distinction;
do not describe an unrun check as passing. Live Render/Cloudflare behavior, paid model behavior,
and provider streaming require separately authorized smoke tests and are not proven offline.

## Documentation duties

Keep documentation synchronized as part of the change, not as a later archaeology project:

- update `README.MD` when setup, public behavior, modes, architecture, or verification commands
  change;
- update `ROADMAP.md` when a milestone changes status, ordering, dependency, or acceptance gate;
- append `BLOGNOTES.md` for major development decisions, measurements, launches, reversals, and
  lessons worth preserving for the eventual public account;
- update `DEFECTS.md` for contract changes, contamination, privacy failures, cohort mistakes,
  underspecified mechanics, and resolved defects; and
- update the narrow design or runbook document that owns a changed protocol. Keep `AGENTS.md` for
  durable operating rules rather than daily chronology.

Documentation claims must match code and committed artifacts. Do not copy manuscript text, private
prompts, credentials, or raw external-model drafts into documentation.

## Settled — do not re-litigate

These are decided. A brief may note a consequence, but may not reopen the question.

- **Do not rebuild the code.** It is modular and reasonably clean. The remaining measurement gap is
  not evidence that a rewrite would help; a rebuild produces equally unmeasured code.
- **The completed first baseline is immutable.** The highest-leverage next measurement action is a
  new-cohort decomposition-instrument repair; do not rerun the baseline or tune retrieval against
  its held-out questions.
- **The gold set is the first artifact** and the input to all three measurements.
- **Optimize for this manuscript; keep the plumbing corpus-agnostic.**
- **Answer Mode reaches done without Index Mode.**
- **Frozen V26 Essential is the neutral evaluated retrieval baseline.** Current RAG
  `retrieval-authored-v4` Essential is the direct-evidence product default and omits prose
  generation, but its shared hybrid retrieval makes one embedding call. It has no paid quality or
  performance cohort. Reader-mode or new-policy results do not become evidence for the frozen
  baseline without their own declared cohorts and checks.
- **`full-context-v2` remains a disabled, separately versioned experiment.** It is not a silent
  fallback, retrieval improvement, or substitute evaluation arm. Its generative scope is
  incompatible with Essential and the API rejects that combination.
- **`[Source N]` is the common reader-facing citation contract for evidence-bearing answers.**
  Retrieval-authored answers map model-returned opaque support IDs to it locally; the narrow
  character-social route has no evidence or citations; explicit v1/V26/V27 generation retains its historical model-facing form;
  `full-context-v2` uses validated stable chunk IDs internally and remaps them locally.
  Human-readable labels remain presentation.
- **The generic multi-project stack is deferred**, not deleted. Do not extend it incidentally while
  working on the single-corpus product or its evaluation.
