# Archivist — Roadmap

## Purpose

This file records Archivist's current workstreams, gates, and next evidence-producing sequence. It
is a roadmap, not the detailed experimental contract or the historical development journal:

- [`EVAL_CONTRACT.md`](EVAL_CONTRACT.md) defines what formal measurement means;
- [`docs/gold_set_authoring.md`](docs/gold_set_authoring.md) defines the private held-out authoring
  and provenance workflow;
- [`AGENTS.md`](AGENTS.md) contains standing implementation rules; and
- [`BLOGNOTES.md`](BLOGNOTES.md) preserves the development history and article material.

Archivist remains a retrieval-augmented question-answering system over one long-form historical
manuscript. Its public reader experience is already live; its formal held-out evaluation has not
yet run. Those are different accomplishments and must not be conflated.

## Current checkpoint — 2026-08-05

The repository's current Answer Mode is `evidence-planned-v26`, with
`query-planner-v11` and `evidence-coverage-v11`. It searches 481 retrieval-eligible chunks from the
complete substantive manuscript. The code also contains the separately versioned
`full-context-v2` experiment, which is feature-gated and disabled on the public deployment by
default.

The reader-facing application now implements:

- a live, book-specific public demo with private server-side corpus storage and bounded source
  disclosure;
- ten reader modes that combine appearance with bounded interpretive framing;
- eleven appearance-only themes under Advanced controls;
- Complete answer as the recommended fail-closed default; and
- Progressive response as an experimental checked-claim delivery option.

These product features do not constitute formal RAG-quality evidence. Essential remains the
neutral evaluation baseline. Reader modes may change framing, but they do not authorize changes to
retrieval evidence, historical claims, or citation rules. Progressive and Complete share the same
answer request, although the schema reordering required for checked-claim release opened the
current generation cohorts.

The public service is live at `https://archivist.mcrombie.com`, but the repository cannot prove
which commit Render is currently serving: production deploys are manual. Verify the deployed
commit in Render before claiming that production and `main` are identical.

### Last measured development checkpoint

V24 remains the last complete unchanged ten-question **development** cohort. It completed all ten
items with zero retries and valid traces, mappings, and citation tokens. Strict manual grading
found 21/58 essential claims, 23/26 target document groups, 4/25 listed failure modes, and 9/10
expected behaviors. It took 589.577 seconds and cost an estimated `$1.53158052`.

That cohort is useful diagnostic history, not held-out evidence. The ten practical questions were
repeatedly used to guide V11–V26 and therefore cannot support a public benchmark or resume
improvement claim. G007 remains a mechanical development sentinel only; its reader-quality score
is not a gate that may suppress the full development cohort.

V25 subsequently added source-bounded completeness and explicit complete/partial/insufficient
outcomes. V26 added corpus-agnostic comparison grammar before premise adjudication. Neither has
received the formal held-out evaluation described below.

### Gold-set checkpoint and development pause

The private owner workbook contains 40 proposed held-out questions across the contracted six
strata. No held-out item has been run through Archivist. The owner is pausing system development to
review the questions and expected evidence carefully.

H020 is a blocking question-design defect: its current recession-comparison wording remains too
close to registered development item `DEV-MANUAL-008`. It must be replaced with a substantively
different owner-authored question before the question set is frozen.

The current private workbook also contains Claude-drafted annotation material, but that material
is **exploratory and noncanonical**. It predates the required committed question fingerprint, and
the canonical private draft ledger does not yet contain the exact batch responses and manifests
required by `archivist.gold_provenance/2`. It may help the owner notice ambiguities, but it cannot be
treated as protocol-compliant ground truth or bound retroactively as if the pre-assistance
commitment existed.

During this pause:

- do not send H001–H040 to Archivist, its retriever, planner, answer model, or evaluation judge;
- do not tune retrieval, prompts, or validation against the private questions or draft
  annotations;
- keep the workbook, DOCX review copy, raw drafts, and manuscript evidence private and ignored;
  and
- treat any later answer-pipeline change as requiring a newly frozen candidate and rebound
  provenance before the first held-out run.

## Workstreams and brief status

| Workstream / brief | Status | What remains |
|---|---|---|
| **0. Project brief and boundaries** | **Complete** | Maintain the book-specific product boundary and links to the governing documents. |
| **1. Unified Answer Mode path** | **Complete** | Preserve one shared implementation of every retrieval primitive across retrieval-backed surfaces. |
| **2. Frozen corpus and reproducible run identity** | **Mostly complete** | The corpus manifest, stable chunk IDs, hashes, eligible boundary, and explicit `l2` distance space exist. A formal run still requires an eligible pinned dated generator snapshot rather than the interactive `gpt-5.6-sol` name. |
| **3. Held-out gold question set** | **Active, owner pause** | Replace H020; finish the owner-controlled questions, strata, Behavior values, and inclusion decisions; fingerprint them; obtain fresh compliant blinded annotation batches; adjudicate every field; and lock provenance. |
| **4. Retrieval recall and dense-vs-hybrid benchmark** | **Not run** | Build/run the committed retrieval-only comparison against the untouched locked gold set. Generation is excluded. |
| **5. Citation-accuracy harness** | **Not run** | Run the locked answer-generation and claim-decomposition workflow, establish mechanical citation measures, and preserve complete run identity. |
| **6. Faithfulness and abstention calibration** | **Not run** | Hand-label the pilot before judge output, measure judge-human agreement and noise, settle §§6–7, and write the §8 envelopes before the baseline. |
| **7. Formal baseline and evaluation report** | **Not run** | Run the complete held-out set once under the locked contract and publish text-free reproducible artifacts, limitations, and exact denominators. |
| **8. Public-demo safety gate** | **Complete for the launched public boundary** | Continue bounded excerpts, edition-qualified locators, server-side controls, and private corpus handling. Confirm deployed-commit parity manually after releases. |
| **8A. Production observability and latency evidence** | **Partial and unmeasured** | Stage timing and token/cost records exist. Add/confirm privacy-safe request correlation and run the declared warm production cohort before publishing latency statistics. |

## Next sequence

The order below is the shortest credible path from the present pause to publishable measurement.
Do not substitute another retrieval iteration for the owner work at the top of the list.

1. **Hold the system still while the owner reviews the gold set.** Existing code may be repaired for
   an independently discovered security or correctness defect, but no change may be derived from
   an H-item or its draft annotation.
2. **Repair and finish the owner-controlled exam.** Replace H020, review every question for clarity
   and distinctness, and settle each ID, stratum, `answer`/`abstain` Behavior, and inclusion
   decision. Existing Claude prose remains only a private review aid.
3. **Freeze the candidate and fingerprint the questions before fresh assistance.** Commit the clean
   candidate and record its exact policy and corpus identity. First close the current tooling gap
   between the Markdown question-fingerprint input and the JSON-only leakage audit (or create an
   equivalent private JSON projection); then run that audit and create
   `fixtures/gold_questions.commitment.json` from the final ordered owner fields.
4. **Obtain fresh compliant blinded annotation batches.** Use the canonical Claude prompt in
   five-item batches. Supply only the frozen questions, eligible private chunks, and corpus
   manifest—never Archivist output, retrieval results, traces, failures, or scores. Preserve the
   exact raw manifests and responses in the private draft ledger.
5. **Adjudicate and lock provenance.** Independently verify every claim, essentiality flag,
   supporting/relevant chunk ID, prohibited claim, and note against the manuscript; search for
   omissions; rewrite accepted prose in the owner's words; pass schema, leakage, privacy, location,
   and provenance checks; and lock from a clean tree.
6. **Run the retrieval-only benchmark.** Compare vector-only retrieval with dense/BM25
   reciprocal-rank fusion using identical questions, corpus, eligibility, query embeddings, and
   values of `k`. Publish Recall@k/context-recall results only from the predeclared contract.
7. **Run citation measurement and the faithfulness/abstention pilot.** Establish mechanical citation
   metrics, hand-label the calibration subset before judge output, measure judge agreement and
   run-to-run spread, then settle the remaining contract sections and performance envelopes.
8. **Run the formal baseline once.** Execute the untouched held-out set against the frozen candidate
   and publish a text-free machine-readable result, readable report, exact rerun command, cohort
   identity, limitations, and per-stratum denominators.
9. **Measure production behavior.** Deploy the exact evaluated candidate, verify the production
   commit, and collect the predeclared 30–50 successful warm first-turn cohort while reporting
   failures, cold starts, follow-ups, p50, p95, and cost.
10. **Fill resume and blog claims only from those artifacts.** If hybrid retrieval does not improve
    the predeclared metric, report that result rather than tuning against the used holdout. A later
    system change requires a new holdout for a new improvement claim.

## Why this order

The gold set is the ruler. Improving the system before the ruler is frozen makes it impossible to
know whether later success reflects a better RAG or a test shaped by the system's known behavior.
Blinded drafting can reduce clerical work, but only a pre-assistance question commitment and
source-level owner adjudication preserve the distinction between assistance and authority.

Retrieval is measured before generation so the result can distinguish “the index did not find the
evidence” from “the context builder or model did not use evidence that was found.” Citation,
faithfulness, and abstention then measure separate boundaries rather than collapsing every failure
into a subjective answer-quality score.

Production latency comes last because it must describe the same candidate whose historical
behavior was measured. Timing an older deployment or an unmeasured new prompt produces an
operational number about a different system.

## Reader experience workstream

The visual and interpretive reader experience exists now; it is no longer a hypothetical second
phase. Its formal comparative evaluation remains deferred until the neutral baseline is measured.

Current contract:

- Professional is the new-reader default.
- Essential is the neutral, evidence-first evaluation path.
- Reader modes may influence framing, emphasis, length, and style only after manuscript evidence
  has been selected.
- Fine-grained lens, voice, worldview, and appearance overrides remain Advanced controls.
- Complete answer is the recommended default.
- Progressive response is experimental and may show only locally checked complete factual claims;
  it is not chain-of-thought and does not promise lower total latency.
- Full book is a separately versioned, high-cost evidence-scope experiment and remains disabled on
  the public deployment unless the owner deliberately enables its additional safety and budget
  controls.

Until the baseline is complete, work in this stream should be limited to independently motivated
usability, accessibility, privacy, and correctness fixes. A later perspective-mode study must ask
the same questions of multiple modes while holding retrieved evidence fixed and applying the same
grounding and citation checks to every answer.

## Deferred work

Deferred means valuable but not on the critical path to the first defensible measurement.

| Deferred item | Why revisit it | Entry condition |
|---|---|---|
| **Index Assistant Mode** | The original back-of-book indexing idea remains useful, but its exact-match ranking defect needs a separate gold set and metric. | Complete the Answer Mode baseline, then write an Index-specific contract. |
| **Multi-corpus Archivist** | A second public-domain Virginia history could test corpus identity, isolation, and transferability without exposing *Cradle*. | Preserve byte-identical *Cradle* chunk IDs and retrieval behavior first; require fail-closed exposure policy and corpus-local absence messages. |
| **Additional edition locator profiles** | Paperback, hardcover, and ebook locators would let readers use the edition they own. | The owner supplies edition-specific pagination; each profile binds to its own source hash. |
| **Precision@k as a public metric** | It is useful only when non-relevant labels are genuinely exhaustive. | Amend the contract before results and complete owner-verified exhaustive relevance judgments; otherwise report Recall@k and context recall. |
| **Learned reranking or new retrieval tuning** | It may improve ordering, but the current project has no held-out baseline proving what needs improvement. | A completed baseline identifies a retrieval-specific defect and a fresh development set supports iteration. |
| **Durable saved conversations** | It would improve return visits but adds storage and privacy obligations. | Define retention, deletion, consent, and public abuse boundaries first. |

## Resume-claim release criteria

The numerical Archivist bullets remain blank until all of the following are true:

- the evaluated commit, deployed commit, corpus manifest, index, model/configuration, and gold-set
  hashes identify one frozen candidate;
- the owner-designed, blinded-draft-assisted, owner-adjudicated held-out gold set passes schema,
  leakage, privacy, location, and provenance validation;
- the committed retrieval runner reproduces vector-only and hybrid results from one command;
- every reported metric states its denominator and measured run-to-run spread;
- the dense-vs-hybrid comparison uses the predeclared metric rather than a favorable metric chosen
  after results;
- the faithfulness judge clears the owner-ratified agreement requirement;
- the production report covers the declared warm cohort and states p50, p95, error rate, spend,
  and cold-start handling; and
- public artifacts contain no manuscript text, held-out question text, private prompts,
  credentials, or raw user conversations.

The intended evidence-backed forms remain placeholders until those gates close:

> Published an N-question retrieval benchmark with owner-authored questions and source-level
> owner-adjudicated annotations, measuring Recall@5 and context recall; dense/BM25
> reciprocal-rank fusion changed macro Recall@5 from A% to B% (X percentage points) versus
> vector-only retrieval.

> Deployed on Render with privacy-safe request tracing, per-stage latency, and token/cost
> telemetry; p50 server latency was Y seconds across N warm production-like queries (p95 Z
> seconds, error rate E%).

Use “improved” only if the frozen comparison actually improves. Replace every placeholder with the
observed value and link the claim to the same reproducible artifacts.

## Publication sequence

1. **Answer Mode post:** the public product, the context-window design, the held-out benchmark,
   dense-vs-hybrid result, citation/faithfulness findings, production latency, failures, and privacy
   boundary.
2. **Index Mode post:** only after its separate measurement and repair.
3. **Perspective-mode essay:** a paired demonstration of how framing changes interpretation while
   evidence and factual checks remain fixed.

The first post is not “I built a RAG.” Its defensible story is “I built one, learned why attractive
answers were not enough, and constructed a measurement and privacy boundary capable of showing
where it succeeds and fails.”
