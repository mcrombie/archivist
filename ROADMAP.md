# Archivist — Brief Roadmap

## Purpose

Maps the sequence of briefs for Archivist, a retrieval-augmented QA system over a single published historical manuscript. Distinguishes the plannable "spine" — everything up to and including the first measured baseline — from the work that **cannot** be written as briefs in advance, because it responds to what the baseline actually shows.

*A Big History of Virginia* is the corpus Archivist is built and evaluated against, not a demo dataset. The engine's contract is with a manuscript of that *shape* — chaptered markdown, one paragraph per line — not with that manuscript's contents.

## Two phases

**Phase 1 — Answer Mode, measured.** Grounded, cited question answering, evaluated against a hand-authored gold set, reproducible, and deployable without exposing the manuscript.

**Phase 2 — Index Mode and perspective modes.** The back-of-book index assistant, and the perspective experiment in which the same question is answered from the same retrieved passages in different registers.

**The gate between phases is not "the answers are good."** Phase 1 is complete when Answer Mode is **measured, bounded, reproducible, and its limitations written down** (`B0_project_brief.md`, Success criterion).

## Current state and resume-evidence sequence (2026-07-30)

Archivist is already beyond the original implementation outline in several respects. Answer Mode
uses versioned dense/BM25 reciprocal-rank fusion over the complete eligible manuscript, the public
demo is live with bounded source disclosure, and per-answer stage timing and token/cost records
exist. V24's RAG implementation was frozen at
`67c735fff37d26288a2a887205b0a20682d9320d`; the complete unchanged development cohort ran from
clean governance-and-cost checkpoint `1b75e8676319ad89f5b09bb851c5df5fad184c6c`, which did not
change the RAG. All ten items completed once with zero retries, valid traces and mappings, and 72
resolvable citation tokens. Strict manual grading found 21/58 essential claims, 23/26 target
document groups, 4/25 listed failure modes, and 9/10 expected behaviors. The run took 589.577
seconds and cost an estimated `$1.53158052`. The public deployment remains on V13. These are real
engineering accomplishments, but they do not yet support the drafted numerical resume claims.

The owner's existing ten-question practical set is now **development and calibration evidence**.
It has repeatedly located defects and guided changes through V20, so it is no longer an unbiased
held-out benchmark and must not be presented as one. G007 remains a useful mechanical sentinel for
the V24 parser/allocation path, but its repeatedly tuned claim and target scores no longer veto
measurement of the complete practical cohort.

The next evidence-producing sequence is:

1. **Enforce source-bounded completeness offline.** V24 often retrieves the intended chapters but
   permits a broad answer to validate while its own diagnostics mark required stages and
   transitions partial or unsupported. Separate structural JSON validity from content status;
   define route-specific `valid_complete`, `valid_partial`, and `insufficient_evidence`
   outcomes; require surviving protected stages and institutional handoffs to be realized or
   concisely bounded; and restore clean abstention when a corpus-level absence is established and
   the user did not ask for analogues. Use only synthetic fixtures and add no source slot, model
   call, retry, critic, or development-answer hint.
2. **Freeze and measure the repaired candidate once.** Run the unchanged ten development
   questions in a fresh isolated directory with zero retries. Compare the complete distribution
   with V24 rather than reinstating a G007 reader-quality veto. If the repair does not improve the
   declared completeness and absence behaviors, retain V24's measured limitations or revise the
   contract before calling the candidate final.
3. **Author and freeze the final held-out gold set.** The blank 40-slot private workbook,
   development-question registry, leakage and quotation audits, provenance binding, location
   carry-over check, and Git freeze validator are implemented. The owner must now supply the
   34–46 questions and exact relevance/support labels required by Brief 3 without running those
   items through Archivist. The existing practical, Brief 1, opening-screen, smoke, and known
   manual questions remain development data. Private authoring may proceed while development
   uses only that registered development set, but the final provenance sidecar must be rebound to
   the next passing frozen candidate before the gold set is ingested or scored.
4. **Run a retrieval-only controlled comparison.** Compare vector-only retrieval with the current
   dense/BM25 reciprocal-rank-fusion path using the same corpus, eligibility rules, question text,
   query embedding, and values of `k`. Generation is excluded.
5. **Publish the reproducible evaluation artifacts.** Preserve the clean commit, corpus/index/gold
   hashes, retrieval configurations, denominators, per-stratum results, limitations, and a
   text-free machine-readable result plus a human-readable report and rerun command.
6. **Complete production observability and measure a live cohort.** Add privacy-safe request
   correlation and outcome records, aggregate the existing stage telemetry, then measure a frozen
   cohort of 30–50 successful warm production-like first turns. Report p50, p95, and error rate in
   seconds, with cold starts and follow-ups labelled separately.
7. **Fill the resume only from those artifacts.** If hybrid retrieval does not improve the
   predeclared metric, revise the claim rather than tuning against the held-out set. Any later
   tuning requires a new holdout before another improvement claim.

Until that sequence is complete, the defensible wording is qualitative: Archivist has a versioned
ten-question development workflow tracking strict claim coverage, target-source coverage,
citation validity, latency, and API cost; its Render deployment has persistent per-stage timing
and token/cost diagnostics, health checks, request limits, and an application-enforced API budget.

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

**3. The Gold Question Set** — 34–46 questions with known answers and known source locations,
authored by the project owner per the schema in `EVAL_CONTRACT.md` §3. This is the held-out input
to the formal measurements and the artifact only the author can produce. The ten-question
practical set already used to optimize V11–V20 is a development/calibration set, not part of the
held-out evidence for a resume comparison.

⚠ **Model assistance is limited to formatting, deduplication, and schema validation.** A model may not decide what the correct answer is or where it lives. A model-authored gold set measures agreement between two runs of the same system and will systematically omit the questions the system is bad at, because the author had the same blind spots.

The owner has now settled the scope explicitly: retrieval and evaluation begin with
`05_Introduction.md`. `01_Front Matter.md`, `02_Table of Contents.md`,
`03_Acknowledgments.md`, and `04_Note on Illustrations.md` are excluded, along with every document
matched by the existing `32_Bibliography.md` sentinel under substring matching. The Epilogue,
Afterword, and appendices remain in scope. That leaves 481 of 910 chunks retrieval-eligible across
a corpus with seven skipped documents. Gold supporting and relevant locations must name chunks in
that eligible set, not merely chunks present in the manifest.

Once candidate-system answers have been inspected, an item cannot silently be moved into the
held-out set. If a final-gold result motivates a system change, record that result as a completed
evaluation and use a new holdout for any subsequent improvement claim.

**4. Retrieval Recall Harness and Dense-vs-Hybrid Benchmark** — `EVAL_CONTRACT.md` §4.
**No generation model is invoked.** Implement one committed runner that evaluates vector-only
retrieval and dense/BM25 reciprocal-rank fusion under identical corpus, eligibility, query,
embedding, and `k` conditions. Query embeddings should be reused between arms so the comparison
isolates retrieval behavior.

Measure `S_primary@k` and `S_context` separately at k ∈ {1, 3, 5, 8, 10, 20}; report hit rate,
essential coverage, context recall, `expansion_displacement` split by cause, and distance-filter
fallback events. Report abstain items separately rather than placing undefined recall values into
the answerable-item denominator. Include macro results, per-stratum results, and paired
per-question differences.

The separation is the point: `S_primary` measures the embedding and index; `S_context` measures the pipeline built on them. If `recall@20` is high while `recall_context` is low, retrieval is finding the material and the pipeline is discarding it — a completely different fix from a poor embedding, and not distinguishable without both numbers.

`Precision@k` is not presently defined by the locked contract. Do not add it after seeing results.
Either the owner supplies exhaustive relevance labels and the contract is amended before the
benchmark, or the public and resume claim uses the already-defined `Recall@5` and context-recall
measures. Publish a text-free JSON artifact, a readable Markdown report, and the exact rerun
command under a frozen run identity.

The runner can be built against a partial development set while Brief 3 is in progress, but the
resume comparison is run once against the untouched final gold set. A result that does not show a
hybrid advantage is still a valid result and changes the wording of the claim.

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

**8A. Production Observability and Latency Evidence** — turn the existing diagnostics into a
coherent, privacy-safe operational record. Persist a correlation ID for both successes and
failures, HTTP outcome/status, total server duration, error class, cohort and model identity, stage
timings, token counts, and estimated cost. Never persist raw questions, answers, quotations, or
manuscript passages in the observability artifact.

Add a private report command or dashboard that produces request count, success/error rate, p50 and
p95 total latency, stage distributions, and spend for an explicitly named cohort. The report must
separate cold starts, warm first turns, and follow-ups. It must include failed requests rather than
measuring only the happy path.

For a resume latency claim, deploy the exact frozen candidate evaluated above and collect 30–50
successful warm production-like first-turn requests, while reporting the cohort's failures
alongside them. Latency is expressed in seconds unless the measured result genuinely supports a
millisecond figure. The old V11 median and the two-item V20 diagnostic pair are historical
development observations, not production benchmarks.

---

## Resume claim release criteria

The numerical Archivist bullets remain blank until all of the following are true:

- the evaluated commit, deployed commit, corpus manifest, index, model/configuration, and gold-set
  hashes identify one frozen candidate;
- the owner-authored 34–46 item held-out gold set passes schema and provenance validation;
- the committed retrieval runner reproduces vector-only and hybrid results from one command;
- the report states the predeclared metric and denominator, with Recall@5/context recall preferred
  unless exhaustive labels justified a prior Precision@5 contract;
- the reported percentage-point difference is the observed paired result, not a selected best run;
- the production telemetry report covers the declared 30–50-request warm cohort and states p50,
  p95, error rate, and cold-start handling; and
- the public report contains no manuscript text, private prompts, credentials, or raw user
  conversations.

The intended evidence-backed form is:

> Published a 34–46-question, owner-authored retrieval benchmark measuring Recall@5 and context
> recall; dense/BM25 reciprocal-rank fusion changed macro Recall@5 from A% to B% (X percentage
> points) versus vector-only retrieval.

> Deployed on Render with privacy-safe request tracing, per-stage latency, and token/cost
> telemetry; p50 server latency was Y seconds across N warm production-like queries (p95 Z seconds,
> error rate E%).

Use "improved" only if the frozen comparison actually improves. Replace 34–46 with the exact final
item count, and do not publish either sentence with placeholders.

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
| 3 | **Precision@k as a formal public metric** | It can describe how much of a short result list is relevant, but only when relevance judgments are exhaustive enough to make non-relevant labels meaningful | An owner-authored exhaustive relevance set and a pre-result amendment to `EVAL_CONTRACT.md`; otherwise use Recall@k and context recall |
| 4 | **Learned re-ranking** | The heuristic pipeline is the known weak point | A baseline to beat, and enough labelled data — which the gold set at 40 items is not |
| 5 | **Reader-facing persona on the public demo** | Book marketing; explicitly permitted by the settled decisions, on the demo only | Brief 8, and never on the evaluated path |

**The reason to defer is diagnostic, not aesthetic.** Hybrid retrieval now exists, but the
controlled vector-only comparison does not; Brief 4 supplies the missing attribution. Each
additional layer added before the one beneath it is understood makes a failure harder to locate.

---

## Blog posts

**Post 1 — Answer Mode**, written from the frozen baseline, dense-vs-hybrid retrieval benchmark,
and production-observability cohort. The story is not "I built a RAG system." It is "I measured
one, and here is what the measurement found." The interesting content is the gap between
`S_primary` and `S_context`, the controlled retrieval comparison, the per-stratum breakdown, the
noise floor, the failures the numbers located, and the measured latency/cost tradeoff. Resume
numbers should link back to the same reproducible artifacts.

**Post 2 — Index Mode**, after Brief 9.

The perspective-mode essay is a third piece, after Brief 10, and depends on Post 1 having established that the faithfulness checks mean something.
