# AGENTS.md — Archivist Standing Rules

These rules apply across every brief in this project, independent of any single brief's scope. Check them before starting implementation on any brief.

## What Archivist is

Archivist is a **retrieval-augmented question-answering system over one long-form historical manuscript**. It is not a general document-QA tool; *A Big History of Virginia* is the corpus it is built for and evaluated against. But nothing in the retrieval or generation machinery may branch on that fact — anything that would break on a different manuscript of the same shape is a bug.

The distinction that matters, because it is the one most likely to erode: **the system is optimized for a known corpus and its plumbing is corpus-agnostic.** Optimizing for the corpus means tuning retrieval parameters, chunking, and prompts against measured behavior on this book. It does not mean typing "Virginia," "Powhatan," or a chapter name into engine code. If you find yourself special-casing a person, place, or chapter, that is scenario logic leaking into the engine — log it.

The corpus is also the moat. Rigorous evaluation depends on knowing the source material well enough to state what a correct answer is; that is only possible because the project owner wrote the book. A generic ingest-anything tool would forfeit exactly that.

## Which phase are you in

The project runs in two phases (see `ROADMAP.md`). **Phase 1 is Answer Mode: grounded, cited question answering, measured against a gold set, reproducible, and deployable without exposing the manuscript.** Phase 2 is Index Assistant Mode and the perspective-mode experiment.

Nearly all current work is Phase 1. If a brief doesn't say otherwise, assume Phase 1 rules.

**The gate to Phase 2 is not "the answers are good."** It is: Answer Mode's retrieval, faithfulness, and citation behavior are **measured, bounded, and reproducible, and where it fails is written down.** A system with mediocre but characterized numbers has passed the gate. A system with excellent-looking answers and no numbers has not.

This ordering is not aesthetic. Phase 2's perspective modes — the same question answered from the same retrieved passages in a neutral, wry, tragic, or triumphant register — are only defensible if every register passes the *same* faithfulness and citation checks. The claim "framing varies, facts don't" is unverifiable without the Phase 1 measurement apparatus, so the apparatus comes first. Index Mode is likewise deferred: Answer Mode reaches done without it.

## The layers

In decreasing order of fixedness. Changes to a lower number are more expensive and more dangerous.

1. **The measurement contract (`EVAL_CONTRACT.md`).** Run identity and cohorts, the corpus contract, the gold-set schema, and the exact definitions of recall@k, citation accuracy, faithfulness, and abstention.

   This is the experimental control, and it plays the role invariants play in a simulation project. **Implement the definitions exactly as written; never adjust one to make a number come out better.** Only the project owner may change them, and any change must be logged in `DEFECTS.md` as a contract change and treated as invalidating every earlier run for comparison. If a result only holds because a metric definition moved, the result is worthless.

   Sections settle on their own clocks. §§1–5 — run identity, the corpus contract, the gold-set schema, retrieval recall, citation accuracy — are settleable at the desk and are locked. §6 faithfulness and §7 abstention are drafted but **not yet settled**, because judge agreement and threshold placement can only be answered by a pilot run. They lock once the pilot has answered what only runs can answer. There is no category of Phase 1 metric that stays permanently adjustable.

2. **The system under test.** The retrieval core, the Answer Mode prompt, and the model configuration. Freely changeable — that is the point — but every change either opens a new run cohort or is a defect, and which one it is must be stated (see Run identity and cohorts).

3. **Presentation.** Citation rendering, chunk merging for display, the frontend. Changes here must not be able to alter what the model sees. If a presentation change moves a metric, the boundary has been violated and that is a defect.

## The gold set is not a target

**Never edit a gold entry after seeing what the system produced for it.**

This is the single easiest way to destroy the project's value and it will feel reasonable every time. The system returns an answer that disagrees with the gold answer; on inspection the gold answer looks arguably too strict, or the "known location" looks arguably incomplete, and widening it turns a failure into a pass. Sometimes the gold entry really is wrong — the corpus is 594 pages and the author is human. The rule is not "gold entries are infallible." The rule is about **provenance and timing**:

| | Situation | Verdict |
|---|---|---|
| **Legitimate** | A gold entry is found to be factually wrong about the manuscript, independent of any system output — the cited chunk genuinely does not contain the claim | Correct it. Log the correction in `DEFECTS.md`, bump the gold-set version, and treat prior runs as a different cohort. |
| **Not legitimate** | A gold entry is widened, softened, or relocated *because* a run failed it | Tuning to the test. Do not. Log the impulse instead. |

The test is whether the correction would have been made had the run passed. If the answer is no, it is not a correction.

The same applies to metric definitions. "Recall@k should probably count a neighbouring chunk as a hit" may well be true — but decided *after* seeing a bad recall number, it is indistinguishable from moving the goalposts. Raise it, log it, change it deliberately as a contract change, and re-baseline.

## Wanting to skip the measurement is data

The project's recurring failure mode is documented and expected: **exciting work crowds out the tedious high-leverage work.** Rebuilding retrieval, adding personality, and building perspective modes are all more enjoyable than authoring forty questions with known answers and running a harness.

Concretely, this has already happened once. A generic multi-project upload-and-index stack exists in `src/web_api.py` and `src/web_project.py` — an architecturally satisfying generalization that was built while the evaluation was not. That is not a criticism of the code; it is the pattern, in evidence, in this repository.

If you find yourself wanting to improve retrieval before it has been measured, that impulse is not a licence — but it is information. Write down what you wanted to change and why in the brief's completion notes. That list is the raw material for the post-baseline briefs, which respond to measured weaknesses rather than guessed ones. A change made before the baseline exists cannot be shown to have helped.

## One retrieval core

From Brief 1 onward there is exactly **one** implementation of each retrieval primitive — distance filtering, neighbour expansion, context finalization, context building — and both modes call it.

Prior to Brief 1 there were three partial copies (`retrieval.py`, `web_project.py`, `query.py`). This is why the rule is stated as a standing rule rather than left to Brief 1: the duplication was drift, not design, and it will re-form the moment a mode needs "just a small variation." A mode-specific variation is a parameter on the shared function, never a second copy of it.

**Transferability is demonstrated by the shared core serving two modes, not by the system accepting arbitrary corpora.** These are different claims and only the first one is in scope.

## The citation contract

**The model always emits `[Source N]`, where N is a 1-based index into the ordered source list it was given.** This is the model-facing contract and it does not vary by surface.

Human-readable citations — `Chapter 4 Cradle of the Empire (1601 – 1622), ¶49–52` — are **presentation**. They are attached to each source in the API payload and rendered by the frontend by substitution. They never appear in the prompt.

The reason is measurement, not taste. `[Source 3]` resolves to exactly one chunk, which makes citation accuracy a mechanical check. A prose label must be parsed back out of generated text, where it can be truncated, paraphrased, or malformed — so label-formatting failures would mix into the grounding numbers as a confound, and a metric that cannot separate two failure modes cannot direct a fix.

## Run identity and cohorts

A question does not identify a run, and neither does a date. Every eval run records, and reproduction requires, all of:

**corpus manifest hash · gold-set version and hash · prompt version hash · generator model snapshot · judge model snapshot · retrieval parameters · commit hash · `working_tree` · `dirty_fingerprint` · dependency-lock hash**

Runs of record require a **clean working tree**. A dirty run is permitted — exploration is the normal case — and records `"working_tree": "dirty"` plus `dirty_fingerprint`: SHA-256 over `git diff HEAD` concatenated with the contents of every untracked non-ignored file, in `git status --porcelain` order. Untracked content belongs in the fingerprint because a new source file otherwise changes behaviour while leaving the fingerprint unchanged. **A dirty run may never be cited as a run of record**, and may never appear in `docs/evaluation.md`.

**Model aliases are forbidden in run configuration.** `gpt-5` is an alias that currently resolves to the snapshot `gpt-5-2025-08-07`, which OpenAI has scheduled for removal from the API on 11 December 2026. An alias silently re-points; a run recorded against one is not reproducible and its number cannot be compared to anything. Record and request the dated snapshot.

**Two different things invalidate a comparison, and they are not the same:**

| | Changed | Consequence |
|---|---|---|
| **Contract change** | a definition in `EVAL_CONTRACT.md`, or a gold entry | earlier runs invalid as evidence about system quality; log in `DEFECTS.md` |
| **New cohort** | prompt text, model snapshot, `n_results`, `MAX_PRIMARY_DISTANCE`, `MAX_FINAL_SOURCES`, chunking parameters, the corpus snapshot | earlier runs stay valid; they belong to a different cohort |

Runs are comparable **within** a cohort, never across. Raising `MAX_FINAL_SOURCES` from 8 to 12 opens a cohort; it is not a contract edit, because no definition moved. Redefining what counts as a retrieval hit is a contract edit even if no code changes.

## Non-determinism rules

The success criterion is a before-and-after comparison across code versions, so controlling variance is load-bearing rather than housekeeping.

- **Pin the generator snapshot explicitly**, never an alias. Record it in the run identity.
- **The judge model is a separate pinned snapshot from the generator**, recorded independently. If the two are the same string, a generator upgrade silently moves the judge and every faithfulness delta becomes uninterpretable. They must be able to move independently, and in general the judge should not be the model under test.
- **Set every sampling parameter the API exposes and record it** — temperature, top_p, seed, reasoning effort, verbosity — rather than relying on defaults, which are not stable across snapshots.
- **Residual non-determinism is expected and must be measured, not assumed away.** Repeated identical requests to the same pinned snapshot can differ. Before any metric is reported as a single number, the pilot establishes its run-to-run spread by repeating one fixed subset **five times unchanged**; that spread is reported alongside every later figure. A change smaller than the measured spread is not a result.
- **Judge calls carry no conversation state.** One question per call, no shared history, no batching several gold items into one prompt — batching lets one item's judgement contaminate the next.

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
Formal quality gates belong to the owner-authored held-out gold contract, its noise floor, and its
predeclared §8 envelopes—not to one question repeatedly used to guide repairs.

## The corpus never leaves the machine

The manuscript is a commercial product sold on Amazon. Three rules, all hard:

- **No manuscript text is committed to the repository, ever** — not in fixtures, not in test data, not in example outputs, not in a docstring, not in a brief. `manuscript/`, `output/`, and `projects/` stay gitignored.
- **Committed artifacts reference the corpus by identifier and hash, never by content.** Chunk IDs, paragraph ranges, document names, and SHA-256 digests are safe and are what run identity and the gold set are built from.
- **Gold-set answers are stated as claim lists in the author's own words**, not as quoted passages. A gold set full of verbatim excerpts is a partial reproduction of the book with extra steps.

For any public deployment: the complete retrieval-eligible corpus may remain private on the server,
but responses expose short cited excerpts only, never whole chunks; arbitrary source browsing and
source-file streaming are disabled; and server-side rate, concurrency, abuse, and spend limits are
required. The public/development exposure profile is selected at server startup and may never be a
client-controlled option. The endpoints that return full chunk text or stream source files are not
deployable as they stand. This is a deployment gate, specified in Brief 8 - not something to solve
incidentally in an earlier brief.

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
- a Phase 2 concern — Index Mode, persona, perspective modes — has crept into Phase 1 work
- a metric's run-to-run spread exceeds the effect being claimed
- manuscript text has entered a committed file
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
| Vector store | **ChromaDB, persistent** | Already in use. See the note below on distance space. |
| Embeddings | **`text-embedding-3-small`** | Current, not deprecated, and re-embedding is expensive — no reason to move. |
| Generation | **A pinned dated GPT-5-family snapshot** | Never the bare `gpt-5` alias. See Run identity. |

### The distance space must be stated, not assumed

The `manuscript` collection is created with `get_or_create_collection(name="manuscript")` and no `metadata={"hnsw:space": ...}`, so it uses Chroma's **default** space rather than an explicitly chosen one. `MAX_PRIMARY_DISTANCE = 1.05` is therefore a threshold in units nobody has written down.

Brief 2 must determine the space empirically from the installed Chroma version, record it in the corpus manifest, and state what 1.05 means in it. On unit-normalized embeddings squared-L2 and cosine distance are monotonically related, so the *ranking* is unaffected either way — but the *threshold* is not, and a filter whose cut point has no stated meaning cannot be tuned deliberately. Set `hnsw:space` explicitly from that point on.

### Requirements hygiene

`requirements.txt` is currently UTF-16-encoded, contains a corrupted entry (`chromadb==1.5.5dir`), and ends with duplicated unpinned lines. `pip install -r requirements.txt` fails on it. Replaced by `pyproject.toml` plus `uv.lock` in Brief 1; do not patch it in place.

## Settled — do not re-litigate

These are decided. A brief may note a consequence, but may not reopen the question.

- **Do not rebuild the code.** It is modular and reasonably clean. The gap is that behavior is unmeasured, not that the code is bad, and a rebuild produces equally unmeasured code.
- **The evaluation is the highest-leverage next action**, ahead of any retrieval improvement.
- **The gold set is the first artifact** and the input to all three measurements.
- **Optimize for this manuscript; keep the plumbing corpus-agnostic.**
- **Answer Mode reaches done without Index Mode.**
- **An evaluated system gets no personality.** Grounded and boring is the achievement. A light persona is acceptable only on a reader-facing public demo, as book marketing, and never on the evaluated path.
- **`[Source N]` is the model-facing citation contract**; human-readable labels are presentation.
- **The generic multi-project stack is deferred**, not deleted and not extended. It is out of scope for every Phase 1 brief. Revisit after the baseline exists.
