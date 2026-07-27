# Archivist — Brief Roadmap

## Purpose

Maps the sequence of briefs for Archivist, a retrieval-augmented QA system over a single published historical manuscript. Distinguishes the plannable "spine" — everything up to and including the first measured baseline — from the work that **cannot** be written as briefs in advance, because it responds to what the baseline actually shows.

*A Big History of Virginia* is the corpus Archivist is built and evaluated against, not a demo dataset. The engine's contract is with a manuscript of that *shape* — chaptered markdown, one paragraph per line — not with that manuscript's contents.

## Two phases

**Phase 1 — Answer Mode, measured.** Grounded, cited question answering, evaluated against a hand-authored gold set, reproducible, and deployable without exposing the manuscript.

**Phase 2 — Index Mode and perspective modes.** The back-of-book index assistant, and the perspective experiment in which the same question is answered from the same retrieved passages in different registers.

**The gate between phases is not "the answers are good."** Phase 1 is complete when Answer Mode is **measured, bounded, reproducible, and its limitations written down** (`B0_project_brief.md`, Success criterion).

### Why this order

**The perspective-mode experiment is unverifiable without Phase 1.** Four registers answering one question is a parlour trick unless every register passes the *same* faithfulness and citation checks — facts fixed, only framing varying. That constraint is what makes the idea serious, and it cannot be enforced or even stated without the measurement apparatus. It is also the idea most likely to jump the queue, which is why it is named explicitly and placed last.

**Index Mode is separable and has its own unmeasured defect.** `finalize_index_context` fills the entire source budget with exact matches in corpus order before consulting semantic results, so for a common term the model is handed "the first eight chunks in the book containing this string" and asked to identify the strongest locations. Fixing that wants its own measurement. Doing both modes at once produces two unmeasured systems instead of one measured one.

**The evaluation is the highest-leverage work, and it is also the least enjoyable.** That combination is the project's documented failure mode. The roadmap is ordered to make skipping it visible.

---

## Phase 1 briefs

**0. Project Brief** — vision, the three layers, the current state as read from the code, the settled decisions, the Phase 1 success criterion, explicit non-goals. Establishes `AGENTS.md` as the standing rules file and `EVAL_CONTRACT.md` as the locked measurement specification.

**1. Unify the Answer Mode Path** — *written in full separately.* Collapse the three partial copies of the retrieval core into one, adopt a single Answer Mode prompt, and establish `[Source N]` as the model-facing citation contract with human-readable labels rendered at presentation. Also owns the project bootstrap: `pyproject.toml`, `uv.lock`, package layout, test layout, ruff config.

⚠ **This brief changes no retrieval behavior and must be able to prove it.** Its acceptance criteria are dominated by equivalence assertions for exactly that reason. One behavioral change is deliberate and recorded: `merge_adjacent_chunks` moves out of the context path into presentation, which changes what the web surface sends the model. That is a cohort change, logged as such.

The reason this comes before the evaluation rather than after: an eval written against `retrieval.py` would not measure what the frontend does, so an unmerged repository forces every number to be produced twice or published about the wrong binary. **Tripwire: one sitting.** If it grows beyond that, stop, evaluate the CLI path as-is, and unify afterwards — the unification is not permitted to become the comfortable task that displaces the eval.

**2. Freeze the Corpus and Pin the Run** — make a run reproducible. Generate and commit `fixtures/corpus_manifest.json` per `EVAL_CONTRACT.md` §2.4, containing hashes and identifiers but **no manuscript text**. Determine the Chroma distance space empirically and set `hnsw:space` explicitly thereafter. Replace the `gpt-5` alias with a pinned dated snapshot, and add a startup assertion rejecting any model string without a date suffix. Implement the run-identity object, including the clean-tree check and `dirty_fingerprint`. Implement the §2.5 re-ingest verification as a mechanical check.

Note the lazy corpus accessor is **Brief 1's**, not this brief's — Brief 1's own tests cannot be collected without it.

⚠ **The `MAX_PRIMARY_DISTANCE = 1.05` threshold is currently expressed in units nobody has written down**, because the collection is created without an explicit `hnsw:space`. On unit-normalized embeddings the *ranking* is unaffected either way, but the *threshold* is not. Record the space; do not silently change it, since changing it opens a cohort and invalidates nothing else but must be recorded as such.

**3. The Gold Question Set** — 34–46 questions with known answers and known source locations, authored by the project owner per the schema in `EVAL_CONTRACT.md` §3. The input to all three measurements and the artifact only the author can produce.

⚠ **Model assistance is limited to formatting, deduplication, and schema validation.** A model may not decide what the correct answer is or where it lives. A model-authored gold set measures agreement between two runs of the same system and will systematically omit the questions the system is bad at, because the author had the same blind spots.

The owner has now settled the scope explicitly: retrieval and evaluation begin with
`05_Introduction.md`. `01_Front Matter.md`, `02_Table of Contents.md`,
`03_Acknowledgments.md`, and `04_Note on Illustrations.md` are excluded, along with every document
matched by the existing `32_Bibliography.md` sentinel under substring matching. The Epilogue,
Afterword, and appendices remain in scope. That leaves 481 of 910 chunks retrieval-eligible across
a corpus with seven skipped documents. Gold supporting and relevant locations must name chunks in
that eligible set, not merely chunks present in the manifest.

This is the tedious brief. It is also the one everything else is blocked on.

**4. Retrieval Recall Harness** — `EVAL_CONTRACT.md` §4. **No model is invoked**, which makes this the cheapest brief and the first that can produce a number. Measures `S_primary@k` and `S_context` separately at k ∈ {1, 3, 5, 8, 10, 20}, reports `expansion_displacement` split by cause, and counts distance-filter fallback events.

The separation is the point: `S_primary` measures the embedding and index; `S_context` measures the pipeline built on them. If `recall@20` is high while `recall_context` is low, retrieval is finding the material and the pipeline is discarding it — a completely different fix from a poor embedding, and not distinguishable without both numbers.

Can be built against a partial gold set while Brief 3 is still in progress.

**5. Citation Accuracy Harness** — `EVAL_CONTRACT.md` §5. Owns two things beyond its own metric: the **answer-generation harness** (run the gold set through Answer Mode, persist answers with their source lists under a run identity) and the **claim-decomposition substrate** that Brief 6 also consumes. Specifying decomposition once, here, is what stops two definitions of "a claim" from drifting apart.

Measures resolvability, groundedness, and completeness separately, and counts malformed citations rather than repairing them. Establishes the §1.4 noise floor for the mechanical metrics by running a fixed 10-question subset five times unchanged.

⚠ **Groundedness has ground truth available for gold-matched claims** — the gold `supporting_chunk_ids` set is authoritative and any member counts as correct, since chunk overlap means a claim can legitimately live in two chunks. Only claims the gold set does not enumerate need a judge. Report the two populations separately; merging them launders an estimate into a fact.

**6. Faithfulness Harness and the Calibration Pilot** — `EVAL_CONTRACT.md` §6, plus §7 abstention. Consumes Brief 5's decomposition. Owns the judge: a **separately pinned snapshot, never the generator's**.

⚠ **This brief begins with the calibration pilot, and the pilot is what settles the contract.** Ten gold items across at least four strata; every decomposed claim hand-labelled **before** any judge output is seen; judge–human agreement computed; then §6 and §7 are ratified or revised and locked, with the lock recorded in `DEFECTS.md` as a contract event. Several things §6 needs — whether the three-level rubric survives contact, whether judging against full context differs from judging against cited chunks, judge variance at temperature 0 — can only be answered by running it.

Extends the noise floor to the judged metrics. **The envelopes in `EVAL_CONTRACT.md` §8.2 are authored at the end of this brief**, after the pilot establishes feasibility and before Brief 7 runs the baseline. That window is part of the contract: envelopes written earlier are aspirations, written later they are descriptions with a tolerance drawn around them.

**7. Baseline Run and Evaluation Rewrite** — run the full gold set under a clean-tree run of record, and rewrite `docs/evaluation.md` from scratch with numbers, noise floors, per-stratum breakdowns, and the stated limitations.

The existing `docs/evaluation.md` is not a baseline and is not amended. It reports seven hand-picked queries with verdicts of the form "High relevance," "Good synthesis," "Accurate citations," "✅ Strong performance" — no counts, no denominators, no gold set — and asserts citation accuracy while printing only chunk IDs and paragraph ranges, never chunk text, so the assertion is not checkable from the document even in principle. It is the specimen the whole apparatus exists to replace.

**This is the brief the first blog post is written from.**

**8. Public Demo Safety Gate** — the deployment brief, and the only one that may touch the web
surface's data exposure. The public service searches the same complete 481-chunk substantive
corpus as development while keeping it private on the server. It returns edition-qualified
locators and tightly bounded quotations rather than whole chunks; enforces rate, concurrency,
abuse, and spend limits; and removes or authenticates local-only endpoints.

⚠ Two endpoints are not deployable as they stand: `GET /api/projects/{id}/sources` returns full chunk text with arbitrary offset and a limit of 50, and `GET /api/projects/{id}/source-file/{path}` streams the original uploaded file. Together they publish the book by pagination.

The first locator profile is bound to the finalized 594-page July 6 typeset PDF and must label
citations as `Typeset PDF (July 6, 2026)`. Roman front matter and the Arabic restart at the Prologue
are part of the mapping contract. The mapping is presentation metadata keyed by chunk ID and must
not alter retrieval, source order, `[Source N]` resolution, or evaluation results. See
`docs/public_demo_design.md`.

**Depends on Brief 7, not merely on Brief 5.** The faithfulness measurement does double duty here: an answer that paraphrases rather than reproduces is simultaneously a grounding property and a licensing one, and the excerpt policy should be set against a measured reproduction rate rather than a guess.

---

## Not pre-written: the measurement-driven briefs

Everything above is plannable because none of it depends on a result. The work that follows the baseline **cannot** be specified in advance, because its content is whatever Brief 7 reveals.

Candidates, listed as anticipations rather than commitments — each becomes a brief only if the baseline shows it matters, and each is forbidden before then:

| Anticipated | What would license it |
|---|---|
| **Broad-thematic retrieval fix** | `recall_context` materially below `recall@20` on the `broad_thematic` stratum, with `expansion_displacement` attributing the loss to truncation. The suspected cause is expansion-then-truncation discarding scored hits in favour of unscored neighbours. |
| **Distance-threshold recalibration** | A high fallback rate on answerable items, or a threshold whose meaning in the recorded `hnsw_space` turns out not to match its intent |
| **Prompt iteration on citation completeness** | `completeness` low while `groundedness` is high — the model citing correctly but not per-claim |
| **Abstention prompt work** | `false_abstention_rate` near zero *and* `abstention_rate` near zero, i.e. the system answers everything |
| **Re-ranking or query-type routing** | `recall@20` ≫ `recall@5`, meaning the material is reachable but not ranked |
| **Chunking parameter change** | Claims systematically split across chunk boundaries, visible as low `essential_coverage` with high `hit_rate` |

**A change made before the baseline exists cannot be shown to have helped.** That is the entire reason this section is empty of commitments. The impulse to make any of these changes now should be written into the relevant brief's completion notes, per `AGENTS.md` — that record is the raw material these briefs are eventually written from, and it documents where the unaided system was *expected* to fall short versus where it actually did.

---

## Phase 2 briefs (not written yet)

**9. Index Mode Measurement and Fix** — Index Mode gets its own gold set (terms with known correct locations and known correct subentries) and its own metric. The known defect is that exact-match results fill the source budget in corpus order, unranked, so a common term yields the earliest occurrences rather than the strongest ones — while the prompt asks the model for "the strongest candidate locations" from a set that was never ranked. Measure before fixing.

**10. Perspective Modes** — the same question answered from the same retrieved passages in neutral, wry, tragic, and triumphant registers, paired with an essay on how framing shapes historical narrative. An interactive demonstration of the book's own argument.

⚠ **The constraint that makes this serious is that every register passes the same faithfulness and citation checks as the neutral one.** Facts fixed; only framing varies. Without that, it is four prompt templates. With it, it is a real claim about what grounding does and does not constrain — and it is testable only because Phase 1 built the apparatus.

Note the interaction with `AGENTS.md`: the evaluated system gets no personality. Perspective modes are not an exception to that rule but an application of it — the registers are the *object of measurement*, held to the neutral path's standard, rather than decoration applied to it.

---

## Deferred (parked, not discarded)

Excluded from Phase 1 to keep it finishable. Not rejected.

| | Deferred | Why it's worth revisiting | Blocked on |
|---|---|---|---|
| 1 | **The generic multi-project stack** — upload, manifests, per-project collections, `importers.py` | The *importers* are corpus handling and worth keeping — the manuscript is docx with an existing index section. The *project management* is the generic tool and is what conflicts with the corpus-specific strategy. Splitting the two is the eventual cut. | The baseline. Deciding now costs a week and changes no measurement. |
| 2 | **Additional edition locator profiles** | Paperback, hardcover, and ebook numbering can let readers use the edition they own | The typeset-PDF profile is active design work in Brief 8; other profiles wait for edition-specific pagination from the owner |
| 3 | **Hybrid retrieval for Answer Mode** | Index Mode's exact-match path exists; Answer Mode has no lexical component at all | Brief 7 showing that semantic-only retrieval is what's failing |
| 4 | **Learned re-ranking** | The heuristic pipeline is the known weak point | A baseline to beat, and enough labelled data — which the gold set at 40 items is not |
| 5 | **Reader-facing persona on the public demo** | Book marketing; explicitly permitted by the settled decisions, on the demo only | Brief 8, and never on the evaluated path |

**The reason to defer is diagnostic, not aesthetic.** Add hybrid retrieval now and, if recall is still poor, there is no way to tell whether the fault is the embedding, the expansion, the truncation, or the new lexical component. Each layer added before the one beneath it is understood costs the ability to attribute a failure.

---

## Blog posts

**Post 1 — Answer Mode**, written from Brief 7. The story is not "I built a RAG system." It is "I measured one, and here is what the measurement found." The interesting content is the gap between `S_primary` and `S_context`, the per-stratum breakdown, the noise floor, and the failure the numbers located.

**Post 2 — Index Mode**, after Brief 9.

The perspective-mode essay is a third piece, after Brief 10, and depends on Post 1 having established that the faithfulness checks mean something.
