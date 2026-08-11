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
manuscript. Its public reader experience is already live; its retrieval-only held-out diagnostic
and its first formal held-out answer-quality baseline are complete. The latter is a descriptive
mechanical baseline, not yet a complete semantic answer-quality scorecard, and those accomplishments
must not be conflated.

## Current checkpoint — 2026-08-11

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

The public service is live at `https://archivist.mcrombie.com`, and the first fixed production-
performance cohort is complete against deployed wrapper commit
`e71d9b79a60a894cb38451c37e0d43b7f9149fa9`. Production deploys remain manual. `/api/version`
bound Render's authoritative `RENDER_GIT_COMMIT`, one unchanged process epoch, the corpus and RAG
identities, and the versioned `$2.00` public Complete-RAG request ceiling before any measured
question was sent.

The cohort attempted all 33 predeclared answerable items without retry or replacement. Twenty-nine
were valid successful completions and four failed, for a 12.1212% all-attempt error rate; there
were zero instrumentation failures. Server p50/p95 were 54.393/113.801 seconds across those 29
successes; client p50/p95 were 54.493/113.829 seconds. The run recorded 500,164 tokens, 80 priced
and zero unpriced events, and `$4.90594694` estimated API cost. This is one observed warm cohort,
not an SLA or performance guarantee.

The four failures were localized after successful planning and evidence selection at the
generation-contract boundary: two `missing_unit_requirement_id` cases, one
`obligation_role_mismatch`, and one `unsupported_requirement_has_unit`. None was a budget,
transport, deployment-identity, or instrumentation failure.

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
completed the formal held-out evaluation described below; frozen V26 is now the candidate under
measurement.

### Formal held-out gold lock

**Locked — 2026-08-07.** The private-safe gold JSON and version-4 provenance sidecar are committed
against the frozen V26 candidate. Schema, composition, source-location, question-commitment,
development-overlap, privacy, provenance, and clean candidate-boundary checks pass. No held-out
item had reached Archivist at lock time.

**Owner-adjudicated source preserved — 2026-08-06.** H039 was removed by owner decision,
leaving 37 questions across the contracted six strata: 8 focused biographical, 8 focused
analytical, 5 conceptual, 10 broad thematic, 4 out-of-corpus, and 2 adversarial-premise. H020 and
H040 also remain intentionally absent. The final DOCX and canonical private JSON are separate from
the source workbook. Run-of-record schema, composition, manifest-location, and development-overlap
checks passed before candidate exposure. The answer-quality run later began on August 9.

The ordered owner fields and final annotations are bound to candidate
`8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e` under
`evidence-planned-v26`. No external annotation request was made before lock and no H-item had then
reached the answer generator. The later retrieval-only diagnostic sent the 37 locked question
strings to the declared embedding endpoint, but no gold annotation or manuscript passage
accompanied them.

### Answer-quality run incidents and recovery

**Interrupted fail-closed — 2026-08-09.** The owner-authorized `$20.00` run sealed H001 and H002.
H003 then made one embedding call and reached a trace-backed deterministic `clean_abstention`
before answer generation. The harness did not recognize that valid early-release shape and stopped
fail-closed. It made no retry and no H003 answer-generation call. Cumulative recorded spend is
approximately `$0.2957022`. H003 is likely a false abstention and remains part of the result.

Recovery is exact and provider-free. Preserve the original partial run root unchanged; migrate its
audited contents into the dedicated sibling root; retain the H001/H002 inner generated-item
payloads unchanged; construct H003 only from its sealed retrieval trace and existing ledger; then
resume at the first missing provider operation under the same cumulative cap. The final report
binds the migration artifact, identifies H003 as trace-recovered, observes generation latency for
36 of 37 items, and discloses that limitation publicly. This is continuation of the unchanged
cohort, not a retry or a repair of H003.

**All answers sealed; two decompositions stopped fail-closed — 2026-08-09.** The audited recovery
completed all 37 frozen V26 answers. The first two canonical Terra calls, for H001 and H002, each
completed once but returned claim text that did not exactly match declared character spans in the
sealed answer. The harness rejected both outputs. Each provider response was retrieved by its
existing response ID without a model call and preserved as a private hash-bound snapshot. No span
or text repair and no retry occurred. Recovery-02 now contains 90 provider events and recorded
cumulative spend of `$5.46195397`.

Leave recovery-02 immutable. The next recovery is a provider-free recovery-03 sibling migration
that binds all 37 answers, the ledger, both private response snapshots, and two explicit technical
decomposition failures. Resume must skip H001 and H002 and make exactly 35 missing Terra calls,
one per remaining answer, under the same cumulative `$20.00` cap. Any further completed parseable
result that reproduces one of the four predeclared local ID/span failures is sealed without repair
or retry and the run continues; every other unexpected failure stops. Completion means 37 answers
and exactly 37 attempted canonical decomposition calls, partitioned into `N` usable decompositions
and `37 - N` disclosed technical failures. Only decomposition-dependent denominators exclude those
failed attempts. This is measurement-instrument recovery, not candidate repair.

**Recovery-03 advanced, then H029 ended incomplete — 2026-08-09.** The provider-free migration
preserved H001/H002, and the resumed pass sealed 27 ordered outcomes. H029's one Terra call then
ended with provider status `incomplete`: 8,000 output tokens, all reported as reasoning, and no
output text. No retry occurred. The existing response was retrieved by ID without a model call and
privately snapshotted. Recovery-03 has 116 provider events and cumulative spend of `$6.80227647`.

**Recovery-04 closed the complete descriptive baseline — 2026-08-09.** The provider-free migration
preserved recovery-03, sealed H029 as `incomplete_response`, and the resume made exactly the nine
untouched H030–H038 calls. No answer or decomposition attempt was retried. All 37 answer artifacts
are preserved: 35 completed/released answers and two generation-side technical-error artifacts.
The decomposition ledger closes at exactly 37 Terra attempts, of which ten are usable and 27 are
technical measurement failures—26 `exact_span_mismatch` and one `incomplete_response`. The latter
are failures of the measurement instrument, not 27 failed V26 answers.

The report covers 198 sources and 251 citation references. Available mechanical results are
citation resolvability 251/251 (1.000), malformed citations 0/250, citation completeness 34/41
(0.829), cited-source to gold-location match 23/34 (0.676), and gold-location retrieval coverage
75/428 (0.175). Two of the ten schema-valid decompositions are zero-claim generation-error records,
so the 41-claim denominator covers eight substantive releases; answer-level
citation syntax measures retain all applicable answers. Semantic measures remain pending by design.
The exact ledger records 125 priced events, zero unpriced events, and `$7.02298147` total spend.
This is a complete descriptive baseline, but the 27/37 instrument-failure rate sharply limits
claim-derived interpretation.

Parts of the completed annotations began as historical Claude drafts, then were directly checked,
adopted, or revised by the manuscript owner. The owner has elected to retain that adjudicated work
rather than commission a new pass solely to manufacture prospective records. Provenance v4 records
the exact limitation: the model/surface and complete raw draft were not captured, and prospective
blinding is not claimed. The owner adjudication is authoritative; the historical drafting is
assistance, not ground truth. Two claims responsible for three copied-language flags were
paraphrased without changing their source bindings, and the private privacy audit now reports zero
flags.

After formal lock:

- run H-items only through the predeclared measurement sequence and preserve every result;
- never revise the locked gold or V26 in response to a held-out result;
- treat any later answer-pipeline change as a new cohort rather than a repair to this baseline;
- keep the workbook, DOCX review copy, raw drafts, and manuscript evidence private and ignored;
  and preserve the committed private-safe gold and provenance artifacts unchanged.

## Workstreams and brief status

| Workstream / brief | Status | What remains |
|---|---|---|
| **0. Project brief and boundaries** | **Complete** | Maintain the book-specific product boundary and links to the governing documents. |
| **1. Unified Answer Mode path** | **Complete** | Preserve one shared implementation of every retrieval primitive across retrieval-backed surfaces. |
| **2. Frozen corpus and reproducible run identity** | **Mostly complete** | The corpus manifest, stable chunk IDs, hashes, eligible boundary, and explicit `l2` distance space exist. Because OpenAI currently exposes canonical `gpt-5.6-sol` and `gpt-5.6-terra` IDs but no immutable dated snapshots, the first answer cohort must bind the committed catalog observation plus requested/returned IDs and disclose the limitation. |
| **3. Held-out gold question set** | **Complete and formally locked** | Preserve the synchronized private source, committed private-safe gold, provenance sidecar, and frozen-candidate boundary unchanged. |
| **4. Retrieval recall and dense-vs-hybrid benchmark** | **Complete** | The frozen run found 24.71% dense versus 25.97% hybrid macro Recall@5 (+1.26 points), with a mixed per-stratum effect. Preserve the private text-free result and do not tune V26 from it before the answer-quality baseline. |
| **5. Citation-accuracy harness** | **Complete for the first descriptive baseline** | Preserve recovery-04 and its exact 37-attempt closure. Mechanical citation results are emitted with exact denominators; decomposition-dependent results use ten usable outcomes and disclose 27 technical instrument failures. |
| **6. Faithfulness and abstention calibration** | **Deferred, lower priority** | After the full baseline is preserved, label the fixed ten-item subset, measure judge agreement, and settle §§6–7. This work may fill semantic fields in a separate supplement; it may not delay or overwrite the baseline. |
| **7. Formal baseline and evaluation report** | **Complete descriptive baseline; semantic scoring pending** | Preserve the public/private hash-bound reports. Diagnose the decomposition instrument in a separate new measurement cohort before relying heavily on claim-derived results; any later semantic calibration is a separate supplement. |
| **8. Public-demo safety gate** | **Complete for the launched public boundary** | Continue bounded excerpts, edition-qualified locators, server-side controls, and private corpus handling. Confirm deployed-commit parity manually after releases. |
| **8A. Production observability and latency evidence** | **Complete for the first observed cohort** | Preserve the text-free public artifacts and private audit root. The 33-attempt run produced 29 latency-eligible successes, four request failures, zero instrumentation failures, 54.393-second server p50, 113.801-second server p95, and `$4.90594694` estimated cost. Treat these as one observed warm cohort, not an SLA. |

## Next sequence

The order below is the shortest credible path from the completed owner-authoring milestone to
publishable measurement. Do not substitute another retrieval iteration for the lock work at the
top of the list.

1. **Completed — hold the system still until the gold set is locked.** Existing code may be repaired for an
   independently discovered security or correctness defect, but no change may be derived from an
   H-item or its draft annotation.
2. **Completed — canonicalize the owner workbook.** H039 was removed, 37 retained items were parsed
   into private canonical JSON, and schema, location, overlap, and privacy diagnostics were run.
3. **Completed — freeze and fingerprint before first candidate exposure.** Candidate
   `8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e` / `evidence-planned-v26` is frozen; the common JSON
   projection closes the old tooling gap; and `fixtures/gold_questions.commitment.json` records the
   text-free owner-field commitment.
4. **Completed — preserve owner-adjudicated annotations honestly.** The completed workbook remains
   the authoritative source. Historical Claude drafting is disclosed retrospectively; no fresh
   batch, complete raw-draft record, or prospective-blinding claim is being invented.
5. **Completed — complete and lock provenance.** The validated JSON and version-4 provenance are
   committed; exact gold, question commitment, corpus, development-registry, owner-attestation,
   privacy, and clean frozen-candidate checks pass.
6. **Completed — run the retrieval-only benchmark.** One authorized, no-retry embedding operation
   cached all 37 locked question vectors. Dense macro Recall@5 was 24.71%; hybrid was 25.97%, a
   predeclared +1.26-point delta. Hit@5 was 90.91% versus 93.94%. The five fixed-subset repetitions
   had zero spread, while the per-stratum result remained mixed. No generator or judge ran, and V26
   was not changed.
7. **Completed — finish canonical decomposition without retrying failed instrument calls.**
   Recovery-04 preserved every earlier result, recorded H029 as `incomplete_response`, and made
   exactly the nine untouched H030–H038 calls. The cohort closes with all 37 answer artifacts and
   exactly 37 Terra attempts: ten usable decompositions, 26 `exact_span_mismatch` failures, and one
   `incomplete_response`. No answer or attempted decomposition was retried, corrected, or replaced.
8. **Completed — emit the descriptive baseline artifacts.** The private machine-readable result
   and text-free public-safe summary/report bind cohort identity, cost, latency, response status,
   mechanical citation measures, limitations, every migration, H003 recovery, and all measurement-
   instrument failures. Generation latency reports the 36 observed full turns: 1,817.196 seconds
   total, 50.478-second mean, 47.928-second p50, 91.695-second p95, and 108.685-second maximum.
   Semantic fields remain explicitly pending rather than blocking publication.
9. **Completed — run the production-performance cohort.** The measured release passed the fixed
   identity and warm-process checks, then attempted exactly 33 fresh, sequential Essential/Complete/
   RAG first turns with empty history, no retry or replacement, and a minimum 12-second start
   interval. Twenty-nine completions entered the latency sample; four request failures remained in
   the all-attempt denominator; instrumentation failures were zero. Server p50/p95 were
   54.393/113.801 seconds, and estimated spend was `$4.90594694`.
10. **Completed — fill the evidence-backed production claim.** The text-free public report supports
    the exact 33-attempt denominator, 29-success latency denominator, 12.1212% request-failure rate,
    zero instrumentation failures, and observed cost. Publish the result as one warm cohort rather
    than an SLA or generalized production guarantee.
11. **Next — repair the three production generation-contract defects.** Strengthen the structured
    generation contract so every non-premise-correction unit links to a requirement, obligation
    dimensions accept only compatible unit roles, and unsupported requirements cannot own answer
    units. Add synthetic regressions for all three closed codes. Any later live comparison must be
    a separately versioned cohort; do not retry or overwrite this sealed run.
12. **Then — rebuild the decomposition instrument in a new measurement cohort.** Diagnose why 26
    of 37 outputs violated exact-span validation, then prospectively declare and test a revised
    instrument without changing or rerunning this baseline. The eight substantively decomposed
    releases are enough to preserve limited mechanical measurements, not enough to support strong
    claim-derived conclusions.
13. **Later — calibrate semantic scoring if it remains useful.** Hand-label the predeclared ten-item
    subset only after all 37 answers, all 37 canonical attempts, every usable decomposition, and the
    technical failures are preserved, measure judge and decomposition agreement, and publish a
    hash-bound scoring supplement. Judge failure selects manual/pending dimensions and never changes
    the original baseline. This is optional, lower-priority work and must not be represented as part
    of the completed descriptive baseline.

## Why this order

The gold set is the ruler. Improving the system before the ruler is frozen makes it impossible to
know whether later success reflects a better RAG or a test shaped by the system's known behavior.
Prospectively blinded drafting can reduce clerical work on a future benchmark, but this cohort does
not pretend that workflow occurred. Its defensible boundary is narrower: owner-authored questions,
no candidate exposure before lock, explicit retrospective assistance disclosure, and source-level
owner adjudication preserve the distinction between assistance and authority.

Retrieval is measured before generation so the result can distinguish “the index did not find the
evidence” from “the context builder or model did not use evidence that was found.” Citation,
faithfulness, and abstention then measure separate boundaries rather than collapsing every failure
into a subjective answer-quality score.

Production latency follows the frozen measurements because it must identify the same V26 RAG
policy and corpus boundary whose historical behavior was measured. The observability implementation
may live in a later release commit, so the production report binds both that deployed commit and
the unchanged policy/corpus identities. Timing an unidentified deployment or a new retrieval/prompt
cohort would produce an operational number about a different system.

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
| **Index Assistant Mode** | The original back-of-book indexing idea remains useful, but its exact-match ranking defect needs a separate gold set and metric. | The Answer Mode descriptive baseline is complete; write an Index-specific contract before resuming this work. |
| **Multi-corpus Archivist** | A second public-domain Virginia history could test corpus identity, isolation, and transferability without exposing *Cradle*. | Preserve byte-identical *Cradle* chunk IDs and retrieval behavior first; require fail-closed exposure policy and corpus-local absence messages. |
| **Additional edition locator profiles** | Paperback, hardcover, and ebook locators would let readers use the edition they own. | The owner supplies edition-specific pagination; each profile binds to its own source hash. |
| **Precision@k as a public metric** | It is useful only when non-relevant labels are genuinely exhaustive. | Amend the contract before results and complete owner-verified exhaustive relevance judgments; otherwise report Recall@k and context recall. |
| **Learned reranking or new retrieval tuning** | It may improve ordering, and the first baseline now documents low gold-location retrieval coverage, but its held-out questions cannot become tuning data. | Diagnose the retrieval-specific defect and build a fresh development set before opening a new comparison cohort. |
| **Durable saved conversations** | It would improve return visits but adds storage and privacy obligations. | Define retention, deletion, consent, and public abuse boundaries first. |

## Resume-claim release criteria

The numerical retrieval and production bullets are now publishable because their applicable gates
have closed. The following remain permanent publication conditions; the faithfulness condition
applies only if a later claim reports faithfulness:

- the evaluated commit, deployed commit, corpus manifest, index, model/configuration, and gold-set
  hashes identify one frozen candidate;
- the owner-designed, owner-adjudicated held-out gold set—with historical drafting assistance
  disclosed under provenance v4—passes schema,
  leakage, privacy, location, and provenance validation;
- the committed retrieval runner reproduces vector-only and hybrid results from one command;
- every reported metric states its denominator; the first descriptive baseline explicitly states
  that generator spread is not yet measured, and every later comparative claim reports it;
- the dense-vs-hybrid comparison uses the predeclared metric rather than a favorable metric chosen
  after results;
- faithfulness dimensions use either an owner-ratified qualifying judge or the declared
  manual/pending fallback;
- the production report covers exactly 33 attempted answerable first turns with no retry or
  replacement; states the valid-success denominator for p50/p95, the all-attempt error rate,
  instrumentation failures, recorded and conservative cost accounting, unavailable-usage attempts,
  the bound request-cost ceiling, and cold/warm handling; and
- public artifacts contain no manuscript text, held-out question text, private prompts,
  credentials, or raw user conversations.

The retrieval evidence supports this form:

> Published a 37-question retrieval benchmark with owner-authored questions and source-level
> owner-adjudicated annotations, measuring Recall@5 and context recall; dense/BM25
> reciprocal-rank fusion increased macro Recall@5 from 24.71% to 25.97% (+1.26 percentage points)
> versus vector-only retrieval.

> Deployed on Render with privacy-safe request tracing, per-stage latency, and token/cost
> telemetry; in a predeclared 33-request warm production cohort, observed 54.393-second p50 and
> 113.801-second p95 end-to-end server latency across 29 successful completions, with four request
> failures (12.1212%), zero instrumentation failures, and `$4.90594694` estimated API cost.

The production form is an observed cohort result rather than an SLA, uptime study, load test, or
guarantee. It states that p50/p95 cover 29 valid successful completions in 33 attempts while the
12.1212% failure rate uses all 33 attempts; the four failures were not replaced.

Use “improved” only where the frozen comparison actually improved, retain every denominator, and
link each claim to the same reproducible artifacts.

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
