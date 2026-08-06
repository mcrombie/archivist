# Held-out gold-set authoring

The final gold set is the owner-designed, owner-adjudicated, never-before-run input to
Archivist's formal measurements. It contains 34–46 questions across the six locked strata in
`EVAL_CONTRACT.md` §3.4. The questions, strata, Behavior values, and inclusion decisions are
owner-authored. Claude may draft the evidence annotations under a blinded protocol, but those
drafts are not ground truth.

It is not the repeatedly used ten-question practical set. Those questions, the earlier Brief 1
questions, opening-screen examples, and known manual smoke questions are development data recorded
in `fixtures/development_question_registry.json`.

> **Held Out Evaluation Set Complete — 2026-08-06.** Owner review and mechanical cleanup of the
> private workbook are complete, with 38 retained questions across all six contracted strata. H020
> has been replaced, the source DOCX remains untouched beside its cleaned copy, and all 570 recorded
> chunk references resolve against the frozen chunk inventory. Existing Claude-derived material
> still predates the provenance-v3 question commitment and canonical raw-draft manifest, so it is
> not by itself a protocol-compliant annotation cohort. The cleaned workbook also records one H039
> question/rubric reading conflict that must be settled before canonical conversion and lock.

## Non-negotiable authority and blinding boundary

Only the manuscript owner decides:

- which questions belong in the set;
- whether each question should be answered or declined;
- each question's stratum; and
- whether to accept, adopt, revise, or reject every drafted claim, essentiality flag, supporting or
  relevant chunk ID, `must_not_claim` entry, and note.

Claude may propose claims, essentiality, locations, relevance, prohibited claims, and notes only
after the owner-controlled fields are frozen. It must see only the declared question batch, private
eligible chunks, corpus manifest, and canonical instructions in
`docs/gold_annotation_prompt_claude.md`. It must never see Archivist answers, Archivist-selected
chunks, traces, scores, known failures, development answers, or evaluation output.

The owner then checks every proposal directly against the corpus, independently searches for
missing relevant chunks, and consciously adopts or revises every accepted annotation. Accurate
draft wording does not need cosmetic paraphrasing merely to prove ownership. Plausibility is not
verification and a rubber-stamp review does not satisfy the contract. Claude's raw drafts remain
private under `runtime/gold-authoring/`; only their hash enters provenance. The privacy audit covers
questions, claims, `must_not_claim`, and notes before commit and still rejects copied manuscript
language.

No held-out question may be sent to Archivist, its retriever, its planner, an answer model, or an
evaluation judge until the set and provenance sidecar are committed and locked.

## Practical adjudication standard

The gold set should resemble real use, not a collection of polished exam prompts. A question may
remain awkward, ambiguous, compound, typo-bearing, or premise-faulty when the owner can record a
stable intended behavior and scoring scope. Rewrite a question only for contamination or
duplication, unintelligibility, or the absence of any stable scoring interpretation. Resolve an
otherwise useful ambiguity in claims or notes rather than editing realism out of the question.

Claims are independently scorable rubric units, not necessarily one-clause microclaims. Keep
closely connected facts together when they have the same evidence, essentiality, and correctness
verdict; split them when those could differ. Use the smallest rubric that captures material
correctness. As a nonbinding starting point, a focused answer will often need about 3–5 essential
claims and a broad answer about 5–8, but the historical scope—not a quota—controls the final count.

Necessary historical background is in scope. It may be essential, optional, or merely relevant
when it materially helps answer the question. `relevant_chunk_ids` remains complete within the
declared scoring scope because it is the denominator for Recall@k; it is not every passage vaguely
related to the topic.

`must_not_claim` is an optional, deliberately non-exhaustive tripwire list. Empty is valid. Usually
zero to two plausible, consequential errors directly implicated by the question are enough, and
each must be affirmatively contradicted by the manuscript. Notes are optional and should preserve
only useful scoring, scope, ambiguity, or provenance decisions.

## Gate 0: freeze a current candidate

The old V21 binding is superseded. The application currently reports policy V26, and commit
`355f78d` is the verified implementation checkpoint immediately preceding the documentation
closeout. When the owner is ready to begin Gate 1, verify that `HEAD` is clean, rerun the complete
offline suite if any executable code has changed, and record that exact clean 40-character commit
as the candidate before canonical annotation starts:

```text
candidate commit: <clean frozen 40-character commit selected at Gate 1>
RAG policy:       evidence-planned-v26
```

If the answer pipeline changes after that commit, freeze a new candidate and rebind provenance
before any held-out item is run. Annotation itself may happen after the freeze because it is blind
to candidate output.

## Gate 1: finish and fingerprint the owner-controlled fields

Create a deliberately incomplete draft under the ignored `runtime/` directory:

```powershell
uv run python scripts\create_gold_authoring_workbook.py
Copy-Item fixtures\gold_set.provenance.template.json `
  runtime\gold-authoring\gold_set.provenance.draft.json
```

The workbook contains 40 blank slots with this neutral allocation:

| Stratum | Slots |
|---|---:|
| `focused_biographical` | 8 |
| `focused_analytical` | 8 |
| `conceptual` | 6 |
| `broad_thematic` | 10 |
| `out_of_corpus` | 5 |
| `adversarial_premise` | 3 |

Those counts are centered inside the locked ranges and may be adjusted by the owner as long as
every final count remains within §3.4. The generator refuses to overwrite an existing draft unless
`--force` is supplied.

Before writing the first question, replace `authoring_started_at` in the private provenance draft
with an honest timezone-aware ISO-8601 timestamp. Leave every attestation `false`.

Before Claude sees any question, run the leakage audit over the completed owner question set.
Exact development reuse is forbidden. A fuzzy flag requires substantive review, not a cosmetic
word substitution. Preserve the resulting review decision in provenance before this gate passes.

**Current tooling gap:** `scripts/fingerprint_gold_questions.py` reads the private Markdown form,
while `scripts/audit_gold_leakage.py` currently reads JSON. The fingerprint is not a leakage audit.
Canonical annotation must therefore wait until a later tooling change gives the overlap checker the
same Markdown projection (or emits an equivalent private JSON projection) and the owner resolves
every resulting flag. Do not work around this gap by committing the held-out questions or by
calling the existing exploratory Claude material canonical.

After every ID, question, stratum, and Behavior value is final, write a text-free commitment:

```powershell
uv run python scripts\fingerprint_gold_questions.py `
  runtime\gold-authoring\gold_set_questions.md `
  --output fixtures\gold_questions.commitment.json
```

Copy the resulting `question_set_sha256` into the private provenance draft and commit the
commitment, contract, prompt, and candidate binding **before** sending a batch to Claude. The final
provenance validator recomputes the same ordered ID/question/stratum/Behavior projection from
`fixtures/gold_set.json`; annotation edits cannot alter it silently.

## Gate 2: obtain blinded drafts in five-item batches

This gate applies to **fresh batches requested after Gate 1 is complete**. The Claude-derived text
already present in the private review form may inform owner editing, but it cannot supply the raw
draft hash or pre-assistance proof required by provenance v2.

Use `docs/gold_annotation_prompt_claude.md` verbatim and name one five-item batch in the message
immediately before it. Supply only those five private question blocks, `output/chunks.json`, and
`fixtures/corpus_manifest.json`. The chunk payload contains the commercial manuscript; upload it
only under data controls the owner accepts. This repository action does not authorize that external
disclosure.

Append Claude's manifest and five returned blocks to
`runtime/gold-authoring/claude_annotation_drafts.md`. Record the exact displayed model label,
provider, surface, final drafting timestamp, canonical prompt hash, and combined private-draft hash
in `annotation_assistance`. If Claude reports candidate output, web use, or contamination, stop the
batch.

Do not use the same Claude model as the later evaluation judge. A consumer UI may expose only a
moving model label; record exactly what it displays and retain that limitation rather than inventing
a dated snapshot.

## Gate 3: adjudicate from the manuscript, not from Archivist

Use direct knowledge of the book and the offline workbench. The workbench performs no retrieval,
ranking, embedding, or API call.

List text-free document metadata:

```powershell
uv run python scripts\gold_authoring_workbench.py --list-documents
```

List text-free chunk metadata, optionally for one exact document:

```powershell
uv run python scripts\gold_authoring_workbench.py --list-chunks
uv run python scripts\gold_authoring_workbench.py `
  --list-chunks "10_Chapter 4 Cradle of the Empire (1601 - 1622).md"
```

Display only an explicitly selected local chunk after its document and text hash are checked
against the frozen manifest:

```powershell
uv run python scripts\gold_authoring_workbench.py `
  --show "10_Chapter 4 Cradle of the Empire (1601 - 1622)_016"
```

Only exact `chunk_id` values are ground truth. Page numbers, chapter names, and paragraph ranges
are orientation. `supporting_chunk_ids` is claim-specific and may contain more than one valid
overlapping chunk. `relevant_chunk_ids` is question-wide and must include every supporting chunk.

An `answer` item needs at least one essential claim. An `abstain` item has no claims and no relevant
chunks. Claude's output is merely a search aid: independently confirm support for each scorable
claim unit, search for omitted aliases and locations within the declared scope, and consciously
adopt, revise, or reject each proposed annotation.

## Gate 4: run offline audits before locking

Validate the schema, eligible locations, item count, and stratum composition:

```powershell
uv run python scripts\validate_gold_set.py `
  runtime\gold-authoring\gold_set.draft.json --mode run-of-record
```

Reject exact reuse of a known development question and print deterministic near-match pairs for
owner review:

```powershell
uv run python scripts\audit_gold_leakage.py `
  runtime\gold-authoring\gold_set.draft.json
```

An exact normalized duplicate is never eligible. A fuzzy flag is not automatically a duplicate,
but the owner must either replace the question or record why it is substantively distinct in
`near_match_reviews`.

Check that questions, claims, prohibited claims, and notes are paraphrases rather than long copied
manuscript passages. This reads the private local chunks but emits only field labels, IDs, and
matched-token counts:

```powershell
uv run python scripts\audit_gold_privacy.py `
  --gold runtime\gold-authoring\gold_set.draft.json `
  --manifest fixtures\corpus_manifest.json `
  --chunks output\chunks.json `
  --output runtime\gold-authoring\privacy-audit.json
```

The command exits nonzero while quotation-risk flags remain. Review each flag manually and rewrite
copied manuscript language. This privacy step does not require cosmetic rewriting of an accurate
AI-drafted paraphrase that the owner has source-verified and consciously adopted.

## Gate 5: lock provenance

After the owner finishes the content:

1. Copy the completed draft to `fixtures/gold_set.json`.
2. Record its exact lowercase SHA-256 in `gold_set_sha256`.
3. Record `authoring_completed_at`.
4. Add one `approved_distinct` review with a substantive owner note for every remaining fuzzy
   match reported by the leakage audit.
5. Hash the exact combined private Claude draft and record the annotation metadata.
6. Set each owner attestation to `true` only if it is true.
7. Save the completed sidecar as `fixtures/gold_set.provenance.json`.

The version-3 sidecar binds the owner-controlled question projection, exact final gold bytes,
frozen candidate, V26 policy, corpus manifest, development registry, canonical Claude prompt, and
private raw draft. The hash-bound JSON files are pinned to LF line endings in `.gitattributes`, so
a Windows checkout cannot silently change their hashes.

Commit the gold set, completed provenance, and any owner-authored notes. From the resulting clean
tree run:

```powershell
uv run python scripts\validate_gold_holdout.py `
  --candidate-commit <next-clean-frozen-commit> `
  --lock
```

The lock fails if:

- the gold schema or composition is invalid;
- a gold location is absent or retrieval-ineligible;
- a development question is reused;
- any fuzzy flag lacks owner review;
- a file hash, candidate, policy, path, timestamp, or attestation is wrong;
- the working tree is dirty; or
- any system-under-test file changed after the candidate freeze.

Only after this command passes may a held-out question reach the system.

## Corpus changes after lock

If the manuscript or ingest parameters change, do not replace
`authored_against_corpus` and assume the locations survived. Run:

```powershell
uv run python scripts\check_gold_carryover.py `
  --gold fixtures\gold_set.json `
  --old-manifest path\to\old_corpus_manifest.json `
  --new-manifest fixtures\corpus_manifest.json `
  --output runtime\gold-authoring\carryover.json
```

An unchanged ID and text hash in an eligible document carries over. A changed hash, missing ID, or
newly skipped document quarantines the entire item until the owner relocates it by hand. A
quarantined set cannot be used for a run of record.

## Historical pilot material

`fixtures/gold_set.pilot.template.json` remains as a workflow artifact. The questions recorded in
`docs/gold_set_pilot_intake.md` were subsequently run repeatedly and are now development data.
They cannot be promoted into the final held-out set.
