# AGENTS.md — Archivist Standing Rules

These rules apply across every brief in this project, independent of any single brief's scope. Check them before starting implementation on any brief.

## What Archivist is

Archivist is a **retrieval-augmented question-answering system over one long-form historical manuscript**. It is not a general document-QA tool; *A Big History of Virginia* is the corpus it is built for and evaluated against. But nothing in the retrieval or generation machinery may branch on that fact — anything that would break on a different manuscript of the same shape is a bug.

The distinction that matters, because it is the one most likely to erode: **the system is optimized for a known corpus and its plumbing is corpus-agnostic.** Optimizing for the corpus means tuning retrieval parameters, chunking, and prompts against measured behavior on this book. It does not mean typing "Virginia," "Powhatan," or a chapter name into engine code. If you find yourself special-casing a person, place, or chapter, that is scenario logic leaking into the engine — log it.

The corpus is also the moat. Rigorous evaluation depends on knowing the source material well enough to state what a correct answer is; that is only possible because the project owner wrote the book. A generic ingest-anything tool would forfeit exactly that.

## Current priorities and answer surfaces

The highest-leverage unfinished work remains the formal held-out evaluation described in
`EVAL_CONTRACT.md` and `ROADMAP.md`. The objective is not "the answers look good." Retrieval,
faithfulness, citation, and abstention behavior must be measured, bounded, reproducible, and have
their failures written down. A system with mediocre but characterized numbers is better evidence
than a system with excellent-looking answers and no defensible measurement.

As of 2026-08-09, the 37 retained owner-controlled held-out questions and their owner-adjudicated
annotations are formally locked against frozen V26 candidate
`8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e`. H020, H039, and H040 are intentionally absent.
Historical Claude drafting is disclosed retrospectively under provenance v4; the repository must
not claim that it was prospectively blinded or fully hash-captured. The predeclared retrieval-only
benchmark is complete. The authorized answer-quality run has now sealed all 37 V26 answers. The
earlier H003 local-release incident remains preserved through its audited sibling migration, with
no provider replay and a 36/37 generation-latency denominator. Canonical claim decomposition then
began. The first and only Terra call for H001 completed, but its returned claim text did not exactly
match its declared character spans in the frozen answer. Strict validation stopped fail-closed.
The response was retrieved by provider response ID without another model call and preserved in a
private hash-bound snapshot; its spans were not corrected, the response was not retried, and no
canonical H001 decomposition was manufactured. Cumulative recorded spend at this second stop is
`$5.42436647`.

The next sequence is fixed: leave the answer-complete recovery root immutable, create an audited
provider-free sibling migration that records H001 as one technical decomposition failure, and call
Terra exactly once for each of the remaining 36 answers under the same cumulative `$20.00` cap.
The baseline must report 37 sealed answers, 37 attempted canonical decomposition calls, 36 usable
decompositions, and one technical decomposition failure. Decomposition-dependent denominators
exclude H001 with the exclusion disclosed; they must not impute zero claims or score the failure as
an answer-quality defect. Do not insert a calibration stop, owner-labeling step, semantic-judge
gate, RAG, prompt, retrieval, model, UI, gold, or corpus repair inside that pass. This is recovery
of a measurement-instrument failure, not repair of the candidate answer. Once an H-item is run,
never change the gold set or V26 in response to its result; any later system change opens a new
cohort rather than repairing this baseline in place.

The product has nevertheless moved beyond the original two-phase description. Reader-facing
appearance and interpretive modes are implemented and public; they are no longer forbidden work.
Index Assistant Mode remains deferred and requires its own measurement before repair or promotion.
Do not mistake a shipped reader feature for completion of the evaluation.

Archivist currently has two answer strategies:

- **Retrieval-backed Answer Mode.** `Essential` is the concise neutral default for API, CLI, and
  evaluation callers that omit a reader mode. It is the evaluated baseline. Professional and the
  other public reader modes may alter framing, voice, worldview, length, and appearance, but they
  use the same corpus identity, retrieval primitives, evidence admission, source ordering,
  citation contract, and terminal grounding checks. Reader-mode quality is not formal evidence
  about Essential unless it is evaluated in a separately declared cohort.
- **`full-context-v2`.** This separately versioned experiment supplies the complete eligible corpus
  and intentionally bypasses query planning, ranking, retrieval, neighbour expansion, and the RAG
  evidence-obligation contract. It shares corpus-integrity, conversation, cost, mode-style,
  citation-remapping, and public-disclosure boundaries where those concepts apply. It is disabled
  by default and must remain behind the server-side full-context flags; the public flag cannot
  enable it unless the general flag is also enabled. Never mix its results into a retrieval cohort.

## The layers

In decreasing order of fixedness. Changes to a lower number are more expensive and more dangerous.

1. **The measurement contract (`EVAL_CONTRACT.md`).** Run identity and cohorts, the corpus contract, the gold-set schema, and the exact definitions of recall@k, citation accuracy, faithfulness, and abstention.

   This is the experimental control, and it plays the role invariants play in a simulation project. **Implement the definitions exactly as written; never adjust one to make a number come out better.** Only the project owner may change them, and any change must be logged in `DEFECTS.md` as a contract change and treated as invalidating every earlier run for comparison. If a result only holds because a metric definition moved, the result is worthless.

   Sections settle on their own clocks. §§1–5 — run identity, the corpus contract, the gold-set schema, retrieval recall, citation accuracy — are settleable at the desk and are locked. §6 faithfulness and §7 abstention are drafted but **not yet settled**, because judge agreement and threshold placement can only be answered by a later calibration exercise. That work begins only after all 37 baseline answers and canonical decompositions are preserved, and its pending state cannot delay the baseline. The sections lock once calibration has answered what only runs can answer. There is no category of formal metric that stays permanently adjustable.

2. **The system under test.** The Essential retrieval path, its prompt and model configuration, and
   any separately declared experimental arm. Freely changeable — that is the point — but every
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

There is exactly **one** implementation of each retrieval primitive — distance filtering,
neighbour expansion, context finalization, and context building. Every retrieval-backed reader
mode, including Essential, calls those same primitives. A mode-specific variation is a parameter
on the shared function, never a second copy of it.

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

**Retrieval-backed generation emits `[Source N]`, where N is a 1-based index into the ordered
source list it was given.** The separately versioned `full-context-v2` experiment instead returns
stable chunk IDs in its structured claim payload; local validation resolves those IDs against the
exact supplied corpus and mechanically renders the same compact `[Source N]` presentation. The UI
never invents, parses, or renumbers model citations.

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
| Interactive generation | **`gpt-5.6-sol` with explicit settings** | Product configuration; separately identified from formal cohorts. |
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
- **The evaluation is the highest-leverage next action**, ahead of any retrieval improvement.
- **The gold set is the first artifact** and the input to all three measurements.
- **Optimize for this manuscript; keep the plumbing corpus-agnostic.**
- **Answer Mode reaches done without Index Mode.**
- **Essential is the neutral evaluated retrieval baseline.** Reader modes and advanced interpretive
  settings are legitimate product features, but they do not change retrieval or become formal
  evidence for Essential without their own declared cohorts and checks.
- **`full-context-v2` remains a disabled, separately versioned experiment.** It is not a silent
  fallback, retrieval improvement, or substitute evaluation arm.
- **`[Source N]` is the retrieval model-facing and common reader-facing citation contract.**
  `full-context-v2` uses validated stable chunk IDs internally and remaps them locally; human-readable
  labels remain presentation.
- **The generic multi-project stack is deferred**, not deleted. Do not extend it incidentally while
  working on the single-corpus product or its evaluation.
