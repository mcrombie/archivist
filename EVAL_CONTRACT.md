# Archivist — Locked Measurement Contract

The experimental control. These definitions are **authored by the project owner and forbidden to the implementer**, including during tuning. Changing anything here invalidates every prior run as evidence about system quality and must be logged in `DEFECTS.md` as a contract change.

This file specifies *what is measured and how*. It does not specify how to implement a harness.
Section 8 records fixed parameters and the prospective rules for later comparisons; the first
37-item baseline is descriptive and has no pass/fail quality threshold.

**Owner-authorized amendment, 2026-08-05:** §3.1 now permits blinded external-AI drafts of
annotation fields under source-level owner adjudication. No held-out run had occurred under the
superseded owner-only annotation rule, so this change invalidates no formal result; all earlier
practical runs remain development evidence only. Provenance for the eventual first run uses
`archivist.gold_provenance/2` and records the assistance explicitly; that unused draft schema is
superseded by the later amendment below.

**Owner-authorized amendment, 2026-08-06:** §3 now defines a practical owner-adjudication
standard. Natural user questions may remain awkward, ambiguous, compound, or premise-faulty when
their scoring intent is stable and recorded. Gold claims are independently scorable rubric units,
not clause-level exercises; materially useful background is in scope; and `must_not_claim` is an
optional bounded tripwire list. Source-verified AI-drafted prose may be consciously adopted or
revised without performative rewriting. No held-out run had occurred, so this change invalidates no
formal result. Provenance advances to `archivist.gold_provenance/3` for the revised owner
attestation; earlier practical runs remain development evidence only.

**Owner-authorized amendment, 2026-08-06 (annotation provenance):** the owner elected to retain
the completed, source-reviewed annotations rather than commission a new Claude pass solely to
manufacture cleaner process records. Some annotation prose began as historical Claude drafting,
but that assistance occurred before the prospective commitment, prompt-hash, raw-draft, and
blinding protocol existed. The project therefore makes no claim that those drafts were
prospectively blinded or reproducibly captured. The owner-controlled questions were still authored
without candidate output, no retained held-out item has been run through Archivist, and the owner
subsequently verified and adjudicated every retained annotation against the private corpus.
Provenance advances to `archivist.gold_provenance/4` to record that limitation explicitly. No
formal held-out run had occurred, so this amendment invalidates no result.

**Owner-authorized amendment, 2026-08-07 (first answer-quality run):** the first scoring
calibration is bounded and cannot become another quality gate in front of the held-out evaluation.
Its ten prospectively selected answers become ten members of the same 37-item V26 cohort; after
the scoring rules are locked, the next substantive operation is completion of the remaining 27
items, with no intervening RAG, prompt, retrieval, model, or UI repair. If the automatic judge does
not clear its predeclared agreement checks, the cohort still proceeds and the affected dimensions
are scored manually or reported pending rather than suppressing the results. Sections 1, 6, 7,
and 8 are clarified accordingly before any held-out answer has been generated.

The same amendment records a provider constraint discovered during preflight. OpenAI's official
model catalog currently exposes `gpt-5.6-sol` and `gpt-5.6-terra` as their own “current snapshot”
identifiers and exposes no dated immutable snapshot for either. The project will not invent one.
The first cohort therefore binds a committed catalog observation, exact requested identifiers,
exact provider-returned identifiers, role-specific settings, prompt hashes, and usage response IDs,
and states the resulting reproducibility limitation. A future dated snapshot opens a new cohort.

**Owner-authorized amendment, 2026-08-09 (run the complete cohort before calibration):** the
sequencing portion of the August 7 amendment is superseded before any held-out answer has been
generated. The next substantive paid operation is one uninterrupted generation and canonical
claim-decomposition pass over all 37 frozen V26 questions. The harness must preserve every answer,
source set, trace, usage record, canonical decomposition, and mechanically computable result before
any human-label or semantic-judge calibration work begins. No calibration result, owner-labeling
step, judge-agreement threshold, manual-scoring availability, or semantic metric may delay or stop
that complete pass. Calibration is later, lower-priority scoring-instrument work: it may add a
hash-bound supplemental scoring artifact, but it may not overwrite the preserved baseline or
condition whether the 37-item result exists. Metrics that require a calibrated semantic judgment
remain explicitly `pending` in the initial report; mechanical citation, status, cost, latency, and
other immediately computable results are reported without waiting. No RAG, prompt, retrieval,
model, UI, gold-set, or corpus change may intervene within the 37-item pass. Because no held-out
answer existed when this amendment was authorized, it invalidates no answer-quality result.

**Settled:** §§1–5. **Drafted, not settled:** §6 faithfulness, §7 abstention. The complete
37-question generation/decomposition baseline runs before either section is calibrated. Sections 6
and 7 lock later after the calibration work answers what only runs can answer; until then, affected
semantic metrics are reported as pending rather than delaying the baseline.

---

## 1. Run identity and cohorts

### 1.1 Identity

A run is identified by the following object, serialized as one UTF-8 JSON string and written alongside every result set. **A run whose identity cannot be reconstructed from its own output is not evidence.**

```json
{
  "identity_schema": "archivist.run_identity/1",
  "run_id": "2026-07-24T14:02:11Z-baseline-01",
  "commit": "<git rev-parse HEAD>",
  "working_tree": "clean",
  "dirty_fingerprint": null,
  "dependency_lock_sha256": "<sha256 of uv.lock>",
  "corpus": {
    "manifest_schema": "archivist.corpus_manifest/1",
    "manifest_sha256": "<sha256 of fixtures/corpus_manifest.json>",
    "chunks_sha256": "<sha256 of output/chunks.json>"
  },
  "gold_set": {
    "schema": "archivist.gold/1",
    "version": "1.0.0",
    "sha256": "<sha256 of fixtures/gold_set.json>"
  },
  "prompts": {
    "planner_prompt_sha256": "<sha256>",
    "answer_prompt_sha256": "<sha256 of the exact prompt template text>",
    "decompose_prompt_sha256": "<sha256>",
    "claim_evidence_judge_prompt_sha256": "<sha256>",
    "item_rubric_judge_prompt_sha256": "<sha256>"
  },
  "models": {
    "embedding": "text-embedding-3-small",
    "planner_requested": "gpt-5.6-sol",
    "planner_returned": "<provider-returned identifier>",
    "generator_requested": "gpt-5.6-sol",
    "generator_returned": "<provider-returned identifier>",
    "judge_requested": "gpt-5.6-terra",
    "judge_returned": "<provider-returned identifier>",
    "catalog_observation_sha256": "<sha256 of fixtures/evaluation_model_catalog.json>"
  },
  "sampling": {
    "generator": { "temperature": null, "top_p": null, "seed": null,
                   "reasoning_effort": "<as set>", "verbosity": "<as set>" },
    "planner":   { "temperature": null, "top_p": null, "seed": null,
                   "reasoning_effort": "low", "verbosity": "low" },
    "judge":     { "temperature": null, "top_p": null, "seed": null,
                   "reasoning_effort": "medium", "verbosity": "low" }
  },
  "retrieval": {
    "n_results": 5,
    "max_primary_distance": 1.05,
    "max_final_sources": 8,
    "hnsw_space": "<as recorded in the corpus manifest>",
    "neighbor_expansion": true,
    "merge_adjacent_in_context": false
  }
}
```

**Prefer immutable dated model snapshots and never manufacture one.** When the provider exposes a
dated snapshot, the run must request it. When the official provider catalog exposes only a
canonical current-snapshot identifier, a run may use that identifier only if it binds the committed
catalog observation, records requested and returned model IDs for every paid operation, and carries
the explicit limitation that the provider may change model weights behind that identifier. A
provider response whose model ID does not equal the predeclared catalog identifier invalidates the
cohort. The judge must use a different predeclared model identifier from the generator.

**Sampling parameters are recorded as `null` only where the API rejects them for that model**, never where they were simply left unset. "Unset" is not a value; defaults are not stable across snapshots.

### 1.2 Runs of record

Runs of record require a **clean working tree**. `commit` is meaningless if uncommitted changes were in play, so the harness checks `git status --porcelain` and writes `"working_tree": "clean"` with `"dirty_fingerprint": null`.

A dirty run is permitted — exploration is the normal case — and records `"working_tree": "dirty"` with **`dirty_fingerprint`**: SHA-256 over `git diff HEAD` concatenated with the contents of every untracked non-ignored file, in `git status --porcelain` order. Untracked content must be in the fingerprint, or a newly added source file changes behaviour while leaving the fingerprint identical.

**A dirty run may never be cited as a run of record**, may never appear in `docs/evaluation.md`, and may never be used as a before-or-after in a comparison.

### 1.3 Cohorts

**Two different things invalidate a comparison, and they are not the same:**

| | Changed | Consequence |
|---|---|---|
| **Contract change** | any definition in this file, or any gold-set entry | earlier runs invalid as evidence about system quality; log in `DEFECTS.md`; re-baseline |
| **New cohort** | prompt text, generator or judge snapshot, sampling parameters, `n_results`, `max_primary_distance`, `max_final_sources`, chunking parameters, the corpus snapshot, `hnsw_space` | earlier runs stay valid; they belong to a different cohort |

Runs are comparable **within** a cohort, never across. Raising `max_final_sources` from 8 to 12 opens a cohort; it is not a contract edit, because no definition moved. Redefining what counts as a retrieval hit is a contract edit even if no code changes.

### 1.4 The noise floor

The first complete 37-item cohort is a **descriptive held-out baseline**. Its values may be reported
with exact denominators and an explicit statement that generator run-to-run spread has not yet been
measured. It may not support a before/after improvement claim, a significance claim, or a
single-number production guarantee.

Before a later cohort is compared with this baseline, establish the affected metric's run-to-run
spread by running the same fixed 10-question subset five times unchanged on a clean tree. Report
the min, max, and standard deviation across those five runs. Deterministic offline rescoring may be
repeated locally; it is not a substitute for repeated generation when generation variance is the
quantity being claimed.

**A change smaller than the noise floor is not a result.** No brief may claim an improvement it cannot separate from repetition variance. This is the check that stops the post-baseline briefs from reporting their own noise back as progress.

Re-establish the noise floor whenever the generator identifier, judge identifier, or sampling
parameters change. This replication is deliberately **after**, not before, the first descriptive
37-item baseline.

### 1.5 Development diagnostics and mechanical sentinels

The owner's repeatedly used practical questions, identified as `G001` through `G010`, are
**development data**. They may diagnose failures, compare candidate behavior directionally, and
exercise the evaluation plumbing, but they are not held-out gold evidence and their scores are not
formal comparison criteria or release thresholds.

A focused development item may run before the complete practical cohort as a **mechanical
sentinel**. Its preflight must declare, before the call:

- the exact frozen question and rubric identity;
- the clean candidate commit and corpus/index identity;
- the intended pipeline boundary and text-free trace assertions;
- the permitted operation count, retry count, and spending cap; and
- which failures mean that the proposed measurement would itself be invalid.

Only those predeclared mechanical failures may stop the broader development measurement. Examples
include a mismatched frozen input, dirty candidate, unexpected retry or model call, invalid or
missing required trace, broken structural classification, unmappable source/citation identifiers,
or a cost-safety stop. A sentinel's claim coverage, target-document coverage, answer style, or
other reader-quality score is a **result**, not a licence to suppress the rest of the cohort.

After a mechanically valid sentinel, the complete unchanged practical cohort proceeds regardless
of whether the sentinel's reader-quality score improved. The full profile, including regressions,
is then used to choose later development work. A mechanically invalid sentinel is repaired and
repeated only to establish that the measurement path works; it does not acquire a quality
threshold through repetition.

No repeatedly tuned practical item may become a formal release gate or be moved into the held-out
gold set. Formal quality decisions use the owner-adjudicated held-out gold set, the metrics in §§4–7, the
noise-floor rule in §1.4, and the prospectively declared comparison rules in §8. The first
descriptive baseline has no pass/fail quality envelope.

---

## 2. The corpus contract

### 2.1 Chunk identity

The chunk is the unit of retrieval, citation, and ground truth.

- **`chunk_id`** has the form `{document_stem}_{NNN}`, where `NNN` is 1-based and zero-padded to three digits, assigned in document order by `ingest.build_chunks_for_file`. Example: `10_Chapter 4 Cradle of the Empire (1601 - 1622)_016`.
- **`chunk_id` is the only permitted identifier in gold-set locations, recall sets, and citation ground truth.** Not paragraph numbers, not chapter names, not page numbers.

### 2.2 Paragraph indices are internal, and must not be used as ground truth

`paragraph_start` and `paragraph_end` are **1-based indices into the filtered paragraph list for that document**, where `ingest.split_into_paragraphs` has already removed blank lines, `[IMAGE]` markers, and every line beginning with `#`.

They are therefore **not** line numbers, **not** positions in the published book, and **not** stable across a re-export of the manuscript. A heading added or an image marker removed shifts every subsequent index in that file.

They are safe for display and for human orientation. They are not ground truth, and any gold entry keyed to them is invalid.

### 2.3 Overlap: a claim may legitimately live in more than one chunk

Chunking uses `PARAGRAPHS_PER_CHUNK = 4` and `PARAGRAPH_OVERLAP = 1`, giving a nominal stride of 3. `ingest.adjust_chunk_start` then shifts a proposed start by ±1 to pull in a quote's setup paragraph or to skip a weak transition, so realized overlap is **0, 1, or 2 paragraphs** rather than exactly 1.

Consequence, and it is load-bearing for §5: **a paragraph near a chunk boundary appears in two chunks, and a claim drawn from it is correctly supported by either.** Every ground-truth location in the gold set is therefore a **set** of acceptable chunk IDs, never a single ID, and citing any member of the set is correct.

A citation-accuracy definition that demanded one exact chunk would penalize correct behaviour, and an assertion that fires on correct behaviour is worse than no assertion.

### 2.4 The corpus manifest

The corpus is frozen as `fixtures/corpus_manifest.json`, which is **committed** and **contains no manuscript text**:

| Field | Contents |
|---|---|
| `manifest_schema` | `archivist.corpus_manifest/1` |
| `documents[]` | per document: `filename`, `sha256` of the source markdown, `paragraph_count`, `chunk_count`, `chapter_title` |
| `chunks[]` | per chunk: `chunk_id`, `document`, `paragraph_start`, `paragraph_end`, `text_sha256`, `char_count` |
| `ingest` | `paragraphs_per_chunk`, `paragraph_overlap`, `ingest_commit`, `skip_files` |
| `store` | `hnsw_space` as determined empirically, `embedding_model`, `collection_name`, `embedded_chunk_count` |
| `chunks_sha256` | SHA-256 of `output/chunks.json` |

Retrieval eligibility is defined by the manifest's `ingest.skip_files`: a chunk can remain listed
in `chunks[]` for corpus identity while being ineligible for retrieval and evaluation because its
`document` matches a skip sentinel. Matching follows the application rule: a sentinel occurring
anywhere in the document filename excludes that document.

`text_sha256` per chunk is what makes gold-set carry-over checkable without storing text: a chunk whose ID and text hash both survive a re-ingest still supports whatever it supported before.

### 2.5 Re-ingest procedure

When the manuscript or the ingest parameters change, a new manifest is generated and the gold set is **re-verified**, not assumed:

1. For each gold location chunk ID: if the ID exists in the new manifest, remains retrieval-eligible, **and** its `text_sha256` is unchanged, the location carries over unmodified.
2. If the ID exists but the hash changed, the location is **invalidated** and must be re-located by hand against the new corpus.
3. If the ID no longer exists or is no longer retrieval-eligible, the location is invalidated.
4. Any gold entry with an invalidated location is quarantined until re-located. **A gold set with unverified locations may not be used for a run of record.**

Re-verification is a mechanical check and must be implemented as one. It is not a judgement call, and it is not optional because "probably nothing moved."

---

## 3. The gold-set schema

### 3.1 Purpose and constraints

The gold set is the input to all three measurements. Its **questions, strata, expected behaviors,
and inclusion decisions are authored by the project owner without seeing candidate-system
output**. Those fields define what the system must be tested on and may not be proposed, selected,
removed, or rewritten by an annotation model.

Held-out independence is substantive, not merely lexical. Replacing one date, entity, or comparison
endpoint in a development question does not make its close twin held out when that question form or
topic already shaped a candidate repair. A near-match review may approve genuinely different
questions that share vocabulary; it may not waive a parameter substitution or known tuned failure
family into the gold set.

An external model may assist with draft annotations—claims, essentiality, claim-specific supporting
chunk IDs, question-wide relevant chunk IDs, `must_not_claim`, and notes—but assistance never
becomes ground-truth authority. Every proposed field remains unverified until the owner checks it
against the private corpus, independently searches for omissions, decides whether to accept,
revise, or reject it, and explicitly adopts or revises every accepted annotation. The owner need
not paraphrase accurate draft wording merely to demonstrate authorship; the required work is source
verification and a conscious scoring decision, not cosmetic rewriting.

Held-out questions are samples of real user behavior, not polished examination prompts. They may
preserve ambiguity, awkward wording, typographical errors, compound structure, or a faulty premise.
Replace a question only when it is contaminated or duplicative, unintelligible, or lacks any stable
scoring interpretation. When wording permits more than one reasonable reading, the owner records
the intended behavior and scoring scope in the rubric or notes rather than silently perfecting the
question.

For any future prospective annotation workflow, the annotation model may receive only the frozen
owner-authored questions, the eligible private corpus and stable chunk identifiers, the corpus
manifest, and the annotation instructions. It may not receive or search for Archivist answers,
retrieved chunks selected by Archivist, planner or generation traces, development-run answers,
scores, known candidate failures, or any other candidate-system output. Discovery of such material
stops annotation for the affected batch and is recorded as possible benchmark contamination. The
annotation model may not later serve as the evaluation judge for that gold set. These prospective
controls are good practice, but they are not asserted retroactively for the present cohort.

**The hard rule is independence, not the fiction that a tool touched no draft text.** Allowing a
model to choose the questions or allowing its plausible annotations to pass without source-level
owner adjudication would make the benchmark measure model agreement rather than correctness. The
owner therefore verifies every claim, essential flag, support location, relevance set within the
declared scoring scope, prohibited-claim tripwire, and note. A rubber-stamp review does not satisfy
this contract.

Before any retained held-out item reaches the candidate system, a text-free hash commits the
ordered IDs, questions, strata, and expected behaviors. The provenance sidecar records that
commitment plus the annotation method, known provider/model/surface information, whether a raw
draft record and prospective blinding record actually exist, an explicit limitation statement, and
the owner's attestations. Unknown historical metadata is recorded as not recorded rather than
guessed away. The commitment proves the exam was fixed before its first run; it does not pretend to
predate historical drafting that had already occurred.

All committed claims, `must_not_claim` entries, and notes are paraphrases rather than copied
manuscript passages, so the gold set is committable without reproducing the book. After direct
source verification, the owner may adopt accurate AI-drafted wording or revise it as needed. Raw
AI drafts and manuscript-bearing inputs remain private and gitignored.

### 3.2 Schema — `archivist.gold/1`

```json
{
  "schema": "archivist.gold/1",
  "version": "1.0.0",
  "authored_against_corpus": "<corpus manifest sha256>",
  "items": [
    {
      "id": "G017",
      "question": "What does the manuscript say about the headright system?",
      "stratum": "focused_analytical",
      "expected_behavior": "answer",
      "claims": [
        {
          "claim_id": "G017.1",
          "text": "Fifty acres were granted per person transported.",
          "essential": true,
          "supporting_chunk_ids": ["10_Chapter 4 ..._016"]
        },
        {
          "claim_id": "G017.2",
          "text": "High mortality meant masters often inherited servants' claims, concentrating estates.",
          "essential": true,
          "supporting_chunk_ids": ["10_Chapter 4 ..._016", "10_Chapter 4 ..._017"]
        }
      ],
      "relevant_chunk_ids": ["10_Chapter 4 ..._016", "10_Chapter 4 ..._017", "10_Chapter 4 ..._019"],
      "must_not_claim": ["The headright system granted land to the transported person rather than the transporter."],
      "notes": ""
    }
  ]
}
```

### 3.3 Two location sets, deliberately distinct

Conflating these is the most likely schema error, and it would silently corrupt both metrics.

| Field | Scope | Consumed by | Meaning |
|---|---|---|---|
| **`supporting_chunk_ids`** | per **claim** | §5 citation accuracy | The chunks that actually contain this specific claim. Any one of them is a correct citation for it (see §2.3). |
| **`relevant_chunk_ids`** | per **question** | §4 recall | Every chunk materially useful to a complete answer within the owner-declared scoring scope. A superset of the union of the claim support sets; it may include necessary historical background and broad questions may extend beyond the minimal claim set. |

`relevant_chunk_ids` must be a superset of the union of `supporting_chunk_ids`; this is a validation assertion, not a convention.

Gold claims are **independently scorable rubric units**, not necessarily one grammatical clause
each. Closely connected facts may stay together when they share the same essentiality, evidence,
and correctness verdict. Split a unit when its parts could receive different scores, require
different evidence, or differ in essentiality. Use the smallest set that captures material
correctness; there is no fixed claim quota.

`must_not_claim` is optional and deliberately non-exhaustive. It contains only a small number of
plausible, consequential errors directly implicated by the question and affirmatively contradicted
by the manuscript. An empty list is normal, and omission says nothing about the acceptability of
other unsupported or false statements. Notes are likewise optional; use them to preserve scoring,
scope, ambiguity, or provenance decisions that a later evaluator actually needs.

### 3.4 Strata and composition

`stratum` is one of:

| Stratum | Description | Target count |
|---|---|---|
| `focused_biographical` | A person, their arc, mostly contiguous in the text | 7–9 |
| `focused_analytical` | A specific institution, event, or mechanism | 7–9 |
| `conceptual` | An idea traced within a bounded region of the book | 5–7 |
| `broad_thematic` | A theme spanning many chapters and centuries | **9–11** |
| `out_of_corpus` | Answerable-sounding, but the manuscript does not cover it | 4–6 |
| `adversarial_premise` | Contains a false presupposition the corpus contradicts | 2–4 |

**Total: 34–46 items**, within the 30–50 envelope.

`broad_thematic` is deliberately the largest stratum. It is the one failure mode already suspected from the code — expansion-then-truncation discarding low-ranked hits — and **a failure mode cannot be measured with three samples**. The other strata exist to establish that the system works where it is expected to; this one exists to characterize where it doesn't.

`out_of_corpus` and `adversarial_premise` exist because retrieval has no abstention path: `get_filtered_primary_chunks` silently falls back to unfiltered results when everything exceeds the distance threshold, so sources are *always* supplied and the entire burden of declining sits on the prompt. That behaviour is currently unmeasured in both directions.

### 3.5 Stated statistical limitation

**A gold set of this size cannot resolve small differences.** At 10 items in a stratum, the standard error on a proportion near 0.5 is roughly 16 percentage points; a within-stratum difference below about 15–20 points is not distinguishable from sampling variation, independently of the run-to-run noise floor in §1.4.

This is stated in advance, deliberately, and it **bounds what the post-baseline briefs may claim**. It is a real limitation of an owner-designed and owner-adjudicated gold set at feasible scale, and the correct response is to report it rather than to over-read the numbers. Aggregate (all-strata) figures are correspondingly tighter and may support smaller claims; per-stratum figures may not.

### 3.6 Validation

A gold set is invalid, and may not be used, if any of the following fail:

- the ordered owner-controlled projection (`id`, `question`, `stratum`, and
  `expected_behavior`) exactly matches the text-free question commitment recorded before the first
  candidate-system exposure
- the provenance sidecar exactly binds the final gold-set bytes, frozen candidate commit and RAG
  policy, corpus manifest, development-question registry, and owner-controlled question commitment
- annotation-assistance metadata identifies the declared method and known provider/model/surface
  information, truthfully records that no prospective blinding or complete raw-draft record is
  available for this historical assistance, and states the resulting limitation
- every required owner attestation is explicitly true, including honest disclosure of historical
  AI drafting without a prospective-blinding claim, source-level adjudication, conscious adoption
  or revision of accepted annotation prose, and the prohibition on pre-lock held-out runs
- no normalized held-out question exactly reuses a registered development question, and every
  deterministic fuzzy-match flag has one substantive owner review
- every `chunk_id` in `supporting_chunk_ids` and `relevant_chunk_ids` exists in the corpus manifest referenced by `authored_against_corpus` **and is retrieval-eligible under that manifest's `ingest.skip_files`**
- every claim has a non-empty `supporting_chunk_ids`
- `relevant_chunk_ids` ⊇ ⋃ `supporting_chunk_ids`, per item
- every item with `expected_behavior: "abstain"` has an empty `claims` list and an empty `relevant_chunk_ids`
- every item with `expected_behavior: "answer"` has at least one `essential` claim
- `claim_id` values are unique and prefixed by their item `id`
- stratum counts fall within §3.4
- the quotation-risk audit finds no unresolved copied run in a question, claim, `must_not_claim`
  entry, or note

The committed validators enforce the mechanical portions of this list. Historical correctness,
independently scorable claim grouping, complete relevance within the declared scope, and genuine
source support remain owner-adjudication duties; a validator success cannot substitute for reading
the evidence.

---

## 4. Retrieval recall

No planner, generator, answer model, or judge is invoked. This is the cheapest measurement and the
first one that should run. The 37 locked question strings are embedded once with the corpus-pinned
`text-embedding-3-small` model, cached privately by question hash, and reused unchanged by both
retrieval arms and every repetition. The embedding operation is not silently repeated.

### 4.1 Definitions

For question *q* with relevant set *R(q)* and a retrieved chunk-ID set *S*:

```
recall(q, S)      = |S ∩ R(q)| / |R(q)|
hit(q, S)         = 1 if |S ∩ R(q)| ≥ 1 else 0
essential(q, S)   = fraction of q's essential claims c for which
                    supporting_chunk_ids(c) ∩ S ≠ ∅
```

Set membership is exact string equality on `chunk_id`. **A gold `chunk_id` absent from the corpus manifest, or present only in a skipped document, is a hard error that aborts the run**, never a miss — a miss, a typo, and unreachable ground truth must not be able to look the same.

Items with an empty `R(q)` are excluded from recall, hit-rate, and essential-coverage denominators;
their values for those metrics are `null`, not zero. They remain in the fallback-rate denominator.
Every aggregate is the macro mean of the applicable per-question values, and every reported number
includes its exact applicable-item denominator. This keeps the four `out_of_corpus` items from
manufacturing either retrieval successes or failures for ground truth that deliberately does not
exist.

### 4.2 Two retrieval arms and two retrieved sets, measured separately

The comparison has exactly two arms. They receive the identical question string, cached query
embedding, corpus and eligibility boundary, raw 20-candidate semantic pool, and values of `k`.
Neither arm invokes query planning.

| Arm | Definition |
|---|---|
| **Dense** | the raw Chroma `l2` vector ranking produced by `collection.query` from the cached query embedding |
| **Hybrid** | the existing `build_hybrid_results` BM25/dense reciprocal-rank-fusion policy, including its pinned lexical tokenizer/scorer, distance rule, fallback rule, deterministic tie-break, and broad-query document-diversity policy |

For the Hybrid arm, `build_hybrid_results(..., n_results=k)` is evaluated independently for every
declared `k`; its returned `primary_chunk_ids` are `S_primary@k`. This mirrors what the existing
retriever returns at that requested depth and does not assume that hybrid result sets are nested.
The same raw semantic pool and cached embedding are reused locally for all `k`; BM25/RRF does not
make another external call.

Within each arm, search and context are then measured separately. This separation is the point of
the metric and must not be collapsed.

| Symbol | Set | Definition |
|---|---|---|
| **`S_primary@k`** | what the arm returned | Dense: the top *k* raw `collection.query` IDs. Hybrid: `primary_chunk_ids` from the pinned BM25/dense RRF policy requested at *k*. |
| **`S_context`** | what the model would see | the chunk IDs produced for that arm by the shared `finalize_context_chunks` path at the frozen runtime `n_results = 5`, post-filter, post-expansion, and post-truncation to `max_final_sources = 8` |

Dense `S_primary` measures the embedding and index alone. Hybrid `S_primary` measures the same
semantic evidence after the already-shipped lexical/fusion policy. `S_context` measures the shared
context pipeline built on each arm. The gap between each arm's five returned primaries and its
context is the downstream pipeline cost. The finalizer now reserves primaries before optional
neighbours; the benchmark measures rather than assumes whether filtering or the source ceiling
still displaces any of them.

### 4.3 Reported figures

Report all of the following, **per stratum and in aggregate**, each with its §1.4 noise floor:

- `recall@k` over `S_primary@k` for **k ∈ {1, 3, 5, 8, 10, 20}**
- `hit_rate@k` over `S_primary@k` for the same k
- `recall_context` and `hit_rate_context` over `S_context`
- `essential_coverage_context` over `S_context`
- **`expansion_displacement`** — per question, the number of chunk IDs present in `S_primary@n_results` but absent from `S_context`, split into those dropped by the distance filter, by document filtering, and by truncation

k values above the current `n_results = 5` and `max_final_sources = 8` are measured deliberately: they are what makes the post-baseline brief writable. If `recall@20` is high while `recall_context` is low, the retrieval is finding the material and the pipeline is discarding it — a different fix from a poor embedding, and one that cannot be distinguished without both numbers.

`expansion_displacement` split by cause is what turns "the pipeline loses things" into "the pipeline loses things *here*."

The prospectively declared dense-versus-hybrid comparison statistic is **macro `recall@5` over all
items with non-empty `R(q)`**. Report both arm values and `Hybrid - Dense`; do not substitute a more
favourable `k`, stratum, context metric, or micro average after seeing the result. Other contracted
figures remain diagnostics and are still reported in full.

For this retrieval measurement, the §1.4 fixed ten-item noise subset is selected mechanically,
before results, by lexicographic item ID within each stratum: 2 `focused_biographical`, 2
`focused_analytical`, 1 `conceptual`, 2 `broad_thematic`, 2 `out_of_corpus`, and 1
`adversarial_premise`. The first pass over those items may be the corresponding slice of the full
benchmark; four identical local repetitions complete the required five. The same cached embedding
is used every time.

### 4.4 Fallback events are counted, not silent

Dense `get_filtered_primary_chunks` falls back to the unfiltered result set when the distance
filter removes everything. Hybrid records the corresponding
`raw_primary_fallback_used` event from its existing trace. **Every arm's fallback is recorded per
question and reported as a rate over all items.** A high fallback rate on `out_of_corpus` items is
the expected finding; a high rate on answerable items means the threshold is suspect.

---

## 5. Citation accuracy

### 5.1 Claim decomposition (shared with §6)

Both §5 and §6 operate on claims, not sentences. Decomposition is defined **once**, here, and both metrics consume the same output — building it twice would let the two definitions drift.

An answer is decomposed by a pinned decomposition prompt against the pinned **judge** snapshot into an ordered list of atomic factual claims. Each claim carries:

- `text` — the claim as asserted by the answer
- `cited_sources` — the `[Source N]` indices attached to the sentence or clause asserting it
- `char_span` — offsets into the answer, so decomposition is auditable

**Decomposition stability is itself measured.** Every one of the 37 preserved answers first receives
one canonical decomposition in the uninterrupted baseline pass. Later, repeat decomposition
**three times total** on a fixed 10-answer subset and report the variance in claim count per answer.
If decomposition is unstable, every number built on it is unstable, and that must be visible rather
than assumed away. The repeated calibration decompositions may not delay or replace preservation
of the 37 canonical decompositions, and the check is repeated whenever the judge snapshot or
decomposition prompt changes.

The fixed later-calibration subset is selected before generation: every `out_of_corpus` and
`adversarial_premise` item, plus the lexicographically first item from each of the other four
strata. This produces exactly ten items spanning all six strata. All 37 canonical decompositions
run before human calibration labels exist because they define the units to preserve and later
score; **human labels must be
hash-bound and complete before any faithfulness, source-support, rubric-match, or response-behavior
verdict from the judge is revealed.**

### 5.2 Citation grammar

The only accepted citation forms are:

```
[Source N]
[Source N, Source M]           (and longer comma-separated runs)
```

matched by `\[Source\s+\d+(?:\s*,\s*Source\s+\d+)*\]`, case-sensitive on `Source`.

Anything bracketed that does not match — `[Source 3, 4]`, `[Sources 3]`, `[Chapter 4, ¶49]`, a bare `[3]` — is a **malformed citation**, counted and reported separately, and does not count as a citation for any other metric. Malformed citations are a prompt-compliance failure and must not be silently repaired by a lenient parser; repairing them hides exactly the signal that would tell you the prompt is not being followed.

### 5.3 The three metrics

Reported separately. They fail in different ways and a single combined number would let one mask another.

**1. Resolvability** — mechanical, no judge.

```
resolvability = (# citation tokens whose N is a valid 1-based index
                 into the source list supplied for that answer)
                / (# citation tokens)
```

Failures are hallucinated source numbers — `[Source 11]` when seven sources were supplied. Report the malformed-citation count alongside.

**2. Groundedness** — judged.

For each (claim, cited source) pair, does that chunk support that claim? A chunk *supports* a claim when the claim's substance can be read from that chunk alone. Being on the same topic is not support; containing an adjacent fact is not support.

```
groundedness = (# supported (claim, cited source) pairs) / (# pairs)
```

**Ground truth is available without the judge for any claim that matches a gold claim**: the gold `supporting_chunk_ids` set is authoritative, and any member counts as correct (§2.3). The judge is required only for claims the answer makes that the gold set does not enumerate. **Report gold-matched and judge-only groundedness separately** — the first is ground truth, the second is an estimate, and presenting them as one number would launder an estimate into a fact.

Semantic mapping from an answer claim to zero or more gold claim IDs is produced by the item-rubric
judge and calibrated against the later human labels. The mapping decision is an estimate; once a
mapping is accepted, membership of a cited chunk ID in the mapped gold claim's
`supporting_chunk_ids` is mechanical ground truth. Unmatched answer claims use the separately
calibrated source-support judgement and remain reported as judge-only groundedness.

**3. Completeness** — mechanical.

```
completeness = (# claims carrying ≥ 1 well-formed citation) / (# factual claims)
```

This is what measures the prompt's per-claim instruction. An answer that places one citation at the end of each paragraph can score high on groundedness and low here, which is precisely the behaviour the Answer Mode prompt is written to prevent and which nothing currently checks.

### 5.4 What is not measured here

Whether the answer is *complete* with respect to the gold claims — that is coverage, reported under §4 as `essential_coverage` and under §6 as claim recall. §5 is about the citations, not about the answer's adequacy.

---

## 6. Faithfulness — PREDECLARED; CALIBRATION FOLLOWS THE BASELINE

**This section is not locked for automatic semantic scoring.** That does not block a run of record:
generate and canonically decompose all 37 answers first, preserve and report every immediately
computable result, and mark the semantic fields defined here `pending`. Calibration and owner
ratification may later qualify an automatic judge or select manual scoring, producing a separate
hash-bound supplement to the preserved baseline.

### 6.1 Draft definition

A claim is judged against the **union of chunks placed in the prompt** — not against the manuscript, and not against the world. Faithfulness asks whether the generator invented anything given what it was shown; a claim that is true of Virginia but absent from the supplied context is *unsupported* and counts as a failure. This is deliberate: an answer that is right by luck or by pretraining is exactly the failure RAG exists to prevent.

Four levels:

| Level | Meaning |
|---|---|
| `supported` | The claim follows from the supplied context |
| `partially_supported` | The context supports the core claim but not its full scope, certainty, or causal force |
| `unsupported` | The context neither establishes nor contradicts it |
| `contradicted` | The context asserts otherwise |

```
faithfulness = # fully supported / # claims
```

`contradicted` is reported separately and never merged into `unsupported`. They are different defects: one is fabrication, the other is misreading, and they call for different fixes.

Also reported are the complete four-label distribution, essential and all-gold-claim recall, and
**`must_not_claim` violations**. Gold-claim presence, semantic answer-to-gold mapping, and bounded
tripwire detection are produced by one item-rubric judge call and calibrated against the later
calibration subset's
human labels. The tripwire list is not exhaustive, so its denominator and item count are always
reported and it is never described as a general hallucination rate.

### 6.2 Judge constraints (these parts are settled)

- **The judge is a different provider-catalog identifier from the generator**, recorded independently in the run identity. If they are the same string, a generator upgrade silently moves the judge and every faithfulness delta becomes uninterpretable.
- **One claim per claim-evidence judge call.** No batching several claims or several questions into
  one evidence call; batching lets one item's judgement contaminate the next.
- **The claim-evidence judge sees the claim and the complete supplied context, never the gold
  rubric.** A faithfulness judge shown the gold answer would score similarity to it, which is a
  different metric.
- **The separately named item-rubric judge sees one answer, its locked claim decomposition, the
  exact question, and a sanitized gold projection containing only claim ID/text/importance and
  bounded `must_not_claim` strings.** It never sees source passages, notes, relevant or supporting
  chunk IDs, provenance metadata, or the expected behavior label.
- **The calibration subset is hand-labelled after the full 37-answer/decomposition baseline is
  preserved but before any semantic judge verdict is seen.** Labelling after seeing the judge's
  verdicts measures the labeller's agreeableness.

### 6.3 Open questions

**Desk decisions settled before later calibration:**

- `partially_supported` is a fourth level and does not count as fully supported.
- Every claim, including one without a citation, is judged against the full context supplied to the
  generator. Citation completeness separately measures the missing citation.
- The same one-claim call returns both full-context faithfulness and per-cited-source support; those
  labels remain separate metrics.
- A zero applicable denominator produces `null` plus denominator `0`, never a manufactured zero.

**Run questions** — only the later calibration exercise can answer:

- Judge–human agreement on the hand-labelled calibration subset, and the agreement level below
  which the judge is unfit for automatic scoring of the affected dimension
- Judge run-to-run variance on identical inputs with the same explicit supported settings
- Whether the four-level rubric is used in practice or collapses to fewer categories
- Whether answer-to-gold mapping, source-support labels, and response-behavior classification are
  eligible for automatic scoring of the complete preserved 37-item cohort; an ineligible
  dimension is scored manually or reported pending and does not alter the baseline

**Settling procedure:** after all 37 answers and canonical decompositions are generated and
hash-locked, hand-label every decomposed claim and item behavior in the predeclared ten-item subset;
then run the semantic judge and the repeated decomposition check.
The automatic judge is eligible only when exact human agreement is at least `0.80` and repeat
agreement on the fixed repeat sample is at least `0.90`. The owner then ratifies the scoring lock.
Failure selects `manual` scoring for the affected dimensions or leaves them `pending`; it cannot
alter, suppress, or delay the already preserved 37-question cohort. Record the lock in
`DEFECTS.md` as a contract event.

For this first cohort, **exact human agreement** pools only predeclared atomic decisions: each
claim's four-level faithfulness label, each cited-source support label, the exact set of gold claim
IDs mapped to each answer claim, every gold-claim status, every bounded `must_not_claim` status,
and each item's response-behavior class. The denominator and each component agreement are reported
alongside the pooled value. The **fixed repeat sample** is the first decomposed factual claim, in
answer order, from each of the ten calibration items that has at least one claim. One identical
second evidence-judge call is made for each sampled claim; repeat agreement pools its faithfulness
and cited-source labels against the first call. These rules are committed before any semantic judge
verdict is requested and cannot be changed after results are visible.

---

## 7. Abstention and premise correction — PREDECLARED; CALIBRATION FOLLOWS THE BASELINE

### 7.1 Predeclared definition

For items with `expected_behavior: "abstain"`, the response is classified binary: does it **assert substantive factual claims about the corpus**, or does it **decline for want of information**? Partial declines that then answer anyway count as answering.

```
out_of_corpus_decline_rate = # correctly declined / # out_of_corpus items
false_abstention_rate      = # incorrectly declined / # answerable non-out-of-corpus items
premise_correction_rate    = # corrected false premise / # adversarial_premise items
```

Both are required. Reporting only the first rewards a system that declines everything.

For `adversarial_premise` items, correction is the intended behavior and is not counted as an
ordinary abstention. A response that first declines and then asserts a substantive answer is
`partial_decline_then_answer` and counts as answering for false-abstention purposes.

### 7.2 Open questions

**Desk decision:** rendered behavior is ultimately classified by the calibrated item-rubric judge
(or the manual fallback), not inferred from internal status codes or a phrase regex. Until that
classification is available, the initial baseline reports the semantic rate as `pending` while
preserving internal status and evidence-decision fields as diagnostics.

**Run question:** the base rate of abstention on answerable items remains unknown until the complete
cohort. Later calibration qualifies classification; it does not condition whether the cohort runs.

---

## 8. Parameters and prospective comparison rules

### 8.1 Current parameter values

Cohort-opening. Recorded in every run identity.

| Parameter | Value | Where |
|---|---|---|
| `n_results` | 5 | `retrieval.retrieve` default; API caps at 12 |
| `MAX_PRIMARY_DISTANCE` | 1.05 | `retrieval.py` |
| `MAX_FINAL_SOURCES` | 8 | `retrieval.py` |
| `PARAGRAPHS_PER_CHUNK` | 4 | `ingest.py` |
| `PARAGRAPH_OVERLAP` | 1 (realized 0–2) | `ingest.py` |
| `SKIP_FILES` | `01_Front Matter.md`; `02_Table of Contents.md`; `03_Acknowledgments.md`; `04_Note on Illustrations.md`; `32_Bibliography.md` sentinel | `filters.py` |
| `hnsw_space` | `l2` | `fixtures/corpus_manifest.json`; verified against the promoted collection |

The owner settled the retrieval and evaluation boundary before any gold run: the corpus begins with
`05_Introduction.md`. The four preceding structural documents are excluded, as are all documents
matched by the existing `32_Bibliography.md` sentinel; substring matching also excludes its
bibliography-tagged derived documents. The Introduction and all later non-bibliography manuscript
documents remain in scope, including the Epilogue, Afterword, and appendices. In this corpus
snapshot, 481 of 910 chunks are retrieval-eligible and seven documents are skipped.

### 8.2 First-baseline interpretation

The first 37-item answer-quality run is a descriptive baseline, not a pass/fail release exam. No
numeric envelope will be reverse-engineered from its result, and the absence of an envelope cannot
delay it. All 37 answers and canonical decompositions are generated and preserved before
calibration. Calibration later locks **how** semantic dimensions are scored; it does not establish
a quality threshold the candidate must clear and is not a prerequisite for the initial result.

Any later before/after improvement experiment must declare its comparison statistic, minimum
meaningful effect, and required noise-floor evidence before the later candidate is evaluated.

| Metric | First-baseline treatment | Gate before completion? |
|---|---|---|
| `recall_context` | already reported as a retrieval diagnostic | no |
| `essential_coverage_context` | already reported as a retrieval diagnostic | no |
| `resolvability` | descriptive with exact denominator | no |
| `groundedness` (gold-matched and judge-only separated) | descriptive | no |
| `completeness` | descriptive with exact denominator | no |
| `faithfulness` | pending initially; descriptive in later calibrated/manual supplement | no |
| `out_of_corpus_decline_rate` | pending initially; descriptive in later calibrated/manual supplement | no |
| `false_abstention_rate` | pending initially; descriptive in later calibrated/manual supplement | no |
| `premise_correction_rate` | pending initially; descriptive in later calibrated/manual supplement | no |

All first-baseline values are reported with exact denominators, unavailable values as `null`, and
the model-identity and generator-variance limitations from §1. They may locate the next defect; they
may not be used to revise V26 and rerun the same held-out set as though it were still unseen.
