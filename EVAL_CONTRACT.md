# Archivist — Locked Measurement Contract

The experimental control. These definitions are **authored by the project owner and forbidden to the implementer**, including during tuning. Changing anything here invalidates every prior run as evidence about system quality and must be logged in `DEFECTS.md` as a contract change.

This file specifies *what is measured and how*. It does not specify how to implement a harness, and it does not contain thresholds for what counts as good — those live in §8 and are authored at a specific, stated moment.

**Settled:** §§1–5. **Drafted, not settled:** §6 faithfulness, §7 abstention. Both lock after the calibration pilot (Brief 6) answers what only runs can answer; the open questions are enumerated at the end of each section, split by whether they are desk questions or run questions.

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
    "answer_prompt_sha256": "<sha256 of the exact prompt template text>",
    "decompose_prompt_sha256": "<sha256>",
    "judge_prompt_sha256": "<sha256>"
  },
  "models": {
    "embedding": "text-embedding-3-small",
    "generator": "gpt-5-2025-08-07",
    "judge": "<a different pinned dated snapshot>"
  },
  "sampling": {
    "generator": { "temperature": null, "top_p": null, "seed": null,
                   "reasoning_effort": "<as set>", "verbosity": "<as set>" },
    "judge":     { "temperature": 0, "top_p": 1, "seed": 20260724 }
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

**Model aliases are forbidden.** `gpt-5` is an alias; it currently resolves to `gpt-5-2025-08-07`, which OpenAI has scheduled for removal from the API on 11 December 2026. An alias re-points silently, so a run recorded against one is not reproducible and its number cannot be compared to anything — including to itself a month later. Record and request the dated snapshot. The same rule applies to the judge.

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

**Every metric is reported with a spread, never as a bare number.**

Before any metric is first published, its run-to-run spread is established by running the **same fixed 10-question subset five times, unchanged**, on a clean tree. Report the min, max, and standard deviation of each metric across those five runs. That spread is the metric's **noise floor** and is quoted alongside every later figure for that metric.

**A change smaller than the noise floor is not a result.** No brief may claim an improvement it cannot separate from repetition variance. This is the check that stops the post-baseline briefs from reporting their own noise back as progress.

Re-establish the noise floor whenever the generator snapshot, judge snapshot, or sampling parameters change.

### 1.5 Development diagnostics and mechanical sentinels

The owner's repeatedly used practical questions, identified as `G001` through `G010`, are
**development data**. They may diagnose failures, compare candidate behavior directionally, and
exercise the evaluation plumbing, but they are not held-out gold evidence and their scores are not
the passing envelopes defined in §8.

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
gold set. Formal quality decisions use the owner-authored gold set, the metrics in §§4–7, the
noise-floor rule in §1.4, and the envelopes written into §8 at the contracted time.

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

The gold set is the input to all three measurements. It is **authored by the project owner from knowledge of the manuscript**, not extracted from it by a model.

**This is a hard rule, and the reason is circularity.** If the same class of model that generates answers also authors the questions and answers, the evaluation measures agreement between two runs of the same system rather than correctness. A model-authored gold set will systematically fail to contain the questions the system is bad at, because the model that authored it had the same blind spots. Model assistance is permitted for *formatting, deduplication, and schema validation*; it is not permitted for deciding what the correct answer is or where it lives.

Claims are stated **in the author's own words**, never as quoted passages, so the gold set is committable without reproducing the book.

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
| **`relevant_chunk_ids`** | per **question** | §4 recall | Every chunk a complete answer should be able to draw on. A superset of the union of the claim support sets — broad questions have relevant material beyond the minimal set of claims. |

`relevant_chunk_ids` must be a superset of the union of `supporting_chunk_ids`; this is a validation assertion, not a convention.

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

This is stated in advance, deliberately, and it **bounds what the post-baseline briefs may claim**. It is a real limitation of a hand-authored gold set at feasible scale, and the correct response is to report it rather than to over-read the numbers. Aggregate (all-strata) figures are correspondingly tighter and may support smaller claims; per-stratum figures may not.

### 3.6 Validation

A gold set is invalid, and may not be used, if any of the following fail:

- every `chunk_id` in `supporting_chunk_ids` and `relevant_chunk_ids` exists in the corpus manifest referenced by `authored_against_corpus` **and is retrieval-eligible under that manifest's `ingest.skip_files`**
- every claim has a non-empty `supporting_chunk_ids`
- `relevant_chunk_ids` ⊇ ⋃ `supporting_chunk_ids`, per item
- every item with `expected_behavior: "abstain"` has an empty `claims` list and an empty `relevant_chunk_ids`
- every item with `expected_behavior: "answer"` has at least one `essential` claim
- `claim_id` values are unique and prefixed by their item `id`
- stratum counts fall within §3.4

---

## 4. Retrieval recall

No model is invoked. This is the cheapest measurement and the first one that should run.

### 4.1 Definitions

For question *q* with relevant set *R(q)* and a retrieved chunk-ID set *S*:

```
recall(q, S)      = |S ∩ R(q)| / |R(q)|
hit(q, S)         = 1 if |S ∩ R(q)| ≥ 1 else 0
essential(q, S)   = fraction of q's essential claims c for which
                    supporting_chunk_ids(c) ∩ S ≠ ∅
```

Set membership is exact string equality on `chunk_id`. **A gold `chunk_id` absent from the corpus manifest, or present only in a skipped document, is a hard error that aborts the run**, never a miss — a miss, a typo, and unreachable ground truth must not be able to look the same.

### 4.2 Two retrieved sets, measured separately

This separation is the point of the metric and must not be collapsed.

| Symbol | Set | Definition |
|---|---|---|
| **`S_primary@k`** | what search returned | the top *k* chunk IDs from `collection.query`, before document filtering, distance filtering, neighbour expansion, and truncation |
| **`S_context`** | what the model saw | the chunk IDs actually placed in the prompt by `finalize_context_chunks` — post-filter, post-expansion, post-truncation to `max_final_sources` |

`S_primary` measures the embedding and the index. `S_context` measures the pipeline built on top of them. The gap between the two is the pipeline's cost, and it is the quantity the broad-thematic hypothesis is about: five primary hits expand to as many as fifteen chunks and are then truncated to eight in primary-rank order, so unscored neighbours of the top hit can displace scored hits ranked fourth and fifth.

### 4.3 Reported figures

Report all of the following, **per stratum and in aggregate**, each with its §1.4 noise floor:

- `recall@k` over `S_primary@k` for **k ∈ {1, 3, 5, 8, 10, 20}**
- `hit_rate@k` over `S_primary@k` for the same k
- `recall_context` and `hit_rate_context` over `S_context`
- `essential_coverage_context` over `S_context`
- **`expansion_displacement`** — per question, the number of chunk IDs present in `S_primary@n_results` but absent from `S_context`, split into those dropped by the distance filter, by document filtering, and by truncation

k values above the current `n_results = 5` and `max_final_sources = 8` are measured deliberately: they are what makes the post-baseline brief writable. If `recall@20` is high while `recall_context` is low, the retrieval is finding the material and the pipeline is discarding it — a different fix from a poor embedding, and one that cannot be distinguished without both numbers.

`expansion_displacement` split by cause is what turns "the pipeline loses things" into "the pipeline loses things *here*."

### 4.4 Fallback events are counted, not silent

`get_filtered_primary_chunks` falls back to the unfiltered result set when the distance filter removes everything. **Every fallback is recorded per question and reported as a rate.** A high fallback rate on `out_of_corpus` items is the expected finding; a high rate on answerable items means the threshold is wrong.

---

## 5. Citation accuracy

### 5.1 Claim decomposition (shared with §6)

Both §5 and §6 operate on claims, not sentences. Decomposition is defined **once**, here, and both metrics consume the same output — building it twice would let the two definitions drift.

An answer is decomposed by a pinned decomposition prompt against the pinned **judge** snapshot into an ordered list of atomic factual claims. Each claim carries:

- `text` — the claim as asserted by the answer
- `cited_sources` — the `[Source N]` indices attached to the sentence or clause asserting it
- `char_span` — offsets into the answer, so decomposition is auditable

**Decomposition stability is itself measured.** Repeat decomposition **three times** on a fixed 10-answer subset and report the variance in claim count per answer. If decomposition is unstable, every number built on it is unstable, and that must be visible rather than assumed away. This check runs in the pilot and is repeated whenever the judge snapshot or decomposition prompt changes.

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

**3. Completeness** — mechanical.

```
completeness = (# claims carrying ≥ 1 well-formed citation) / (# factual claims)
```

This is what measures the prompt's per-claim instruction. An answer that places one citation at the end of each paragraph can score high on groundedness and low here, which is precisely the behaviour the Answer Mode prompt is written to prevent and which nothing currently checks.

### 5.4 What is not measured here

Whether the answer is *complete* with respect to the gold claims — that is coverage, reported under §4 as `essential_coverage` and under §6 as claim recall. §5 is about the citations, not about the answer's adequacy.

---

## 6. Faithfulness — DRAFTED, NOT SETTLED

**This section is not locked.** It may not be used for a run of record until the calibration pilot (Brief 6) has answered the open questions below and the owner has ratified the result. Implement the draft, run the pilot, then settle.

### 6.1 Draft definition

A claim is judged against the **union of chunks placed in the prompt** — not against the manuscript, and not against the world. Faithfulness asks whether the generator invented anything given what it was shown; a claim that is true of Virginia but absent from the supplied context is *unsupported* and counts as a failure. This is deliberate: an answer that is right by luck or by pretraining is exactly the failure RAG exists to prevent.

Three levels:

| Level | Meaning |
|---|---|
| `supported` | The claim follows from the supplied context |
| `unsupported` | The context neither establishes nor contradicts it |
| `contradicted` | The context asserts otherwise |

```
faithfulness = # supported / # claims
```

`contradicted` is reported separately and never merged into `unsupported`. They are different defects: one is fabrication, the other is misreading, and they call for different fixes.

Also reported: **`must_not_claim` violations** — the rate at which an answer asserts one of the gold set's enumerated plausible-but-false statements. This is a small, high-signal number and requires no judge.

### 6.2 Judge constraints (these parts are settled)

- **The judge is a different pinned snapshot from the generator**, recorded independently in the run identity. If they are the same string, a generator upgrade silently moves the judge and every faithfulness delta becomes uninterpretable.
- **One claim per judge call.** No batching several claims or several questions into one prompt; batching lets one item's judgement contaminate the next.
- **The judge sees the claim and the context, never the gold answer.** A judge shown the gold answer is scoring similarity to it, which is a different metric.
- **The calibration subset is hand-labelled before any judge output is seen.** Labelling after seeing the judge's verdicts measures the labeller's agreeableness.

### 6.3 Open questions

**Desk questions** — settleable without runs, before the pilot:

- Whether `contradicted` needs a fourth level for "partially supported / overstated," which is the most common real failure in cited historical prose
- Whether a claim citing no source is judged against the full context or scored as an automatic failure under §5.3-completeness only

**Run questions** — only a pilot can answer:

- Judge–human agreement on the hand-labelled calibration subset, and the agreement level below which the judge is unfit for use
- Judge run-to-run variance on identical inputs at temperature 0
- Whether the three-level rubric is used in practice or collapses to two
- Whether judging against the full context and judging against only the cited chunks produce meaningfully different numbers — if not, §6 and §5.3-groundedness can share one judge pass

**Settling procedure:** pilot on 10 gold items spanning at least four strata; hand-label every decomposed claim before running the judge; compute agreement; ratify or revise; then lock this section and record the lock in `DEFECTS.md` as a contract event.

---

## 7. Abstention — DRAFTED, NOT SETTLED

### 7.1 Draft definition

For items with `expected_behavior: "abstain"`, the response is classified binary: does it **assert substantive factual claims about the corpus**, or does it **decline for want of information**? Partial declines that then answer anyway count as answering.

```
abstention_rate       = # correctly declined / # out_of_corpus + adversarial_premise items
false_abstention_rate = # incorrectly declined / # answerable items
```

Both are required. Reporting only the first rewards a system that declines everything.

For `adversarial_premise` items, a third outcome matters and is counted separately: the response **corrects the false premise** rather than either answering it or declining. That is the best behaviour and a metric that cannot see it would mark it wrong.

### 7.2 Open questions

**Desk:** whether classification is done by regex over a closed phrase list (brittle, but mechanical and stable) or by the judge (robust, but adds a judged step to a metric that could otherwise be deterministic).

**Runs:** the base rate of abstention on answerable items — currently completely unknown, because retrieval always supplies sources and no test has ever exercised the prompt's "if the sources do not contain enough information, say so" instruction. If false abstention turns out to be near zero on answerable items, a regex classifier is sufficient and §7 becomes mechanical.

---

## 8. Parameters and envelopes

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
| `hnsw_space` | **undetermined** — Chroma default, never set explicitly | Brief 2 must record it |

The owner settled the retrieval and evaluation boundary before any gold run: the corpus begins with
`05_Introduction.md`. The four preceding structural documents are excluded, as are all documents
matched by the existing `32_Bibliography.md` sentinel; substring matching also excludes its
bibliography-tagged derived documents. The Introduction and all later non-bibliography manuscript
documents remain in scope, including the Epilogue, Afterword, and appendices. In this corpus
snapshot, 481 of 910 chunks are retrieval-eligible and seven documents are skipped.

### 8.2 Envelopes — authored after the pilot, before the baseline

**Envelopes are not filled in yet, and the moment at which they are filled is part of the contract.**

They cannot be authored now: with no pilot, any number written here would be an aspiration, and an envelope that has no relationship to achievable performance either passes trivially or fails meaninglessly.

They also may not be authored after the baseline. An envelope written once the baseline number is known is not a test; it is a description with a tolerance drawn around it, and it cannot fail.

**The window is: after the calibration pilot (Brief 6) has established feasibility and the §1.4 noise floor, and before the Brief 7 full baseline run.** At that point the owner writes, into this section, a lower bound for each metric, per stratum and in aggregate. The baseline then either falls inside those bounds or does not, and either outcome is a result.

| Metric | Aggregate bound | Per-stratum bounds | Filled |
|---|---|---|---|
| `recall_context` | — | — | ☐ |
| `essential_coverage_context` | — | — | ☐ |
| `resolvability` | — | — | ☐ |
| `groundedness` (gold-matched) | — | — | ☐ |
| `completeness` | — | — | ☐ |
| `faithfulness` | — | — | ☐ (blocked on §6) |
| `abstention_rate` | — | — | ☐ (blocked on §7) |
| `false_abstention_rate` | — | — | ☐ (blocked on §7) |

Bounds are stated as **lower bounds a passing baseline must reach**, not as targets to aim at later. A metric expected to be poor — `recall_context` on `broad_thematic` is the obvious candidate — should be given a bound that reflects the honest expectation. **A stratum predicted to fail should be given a bound it will fail**, and the prediction recorded. Predicting a failure and then observing it is a much stronger result than discovering one afterwards.
