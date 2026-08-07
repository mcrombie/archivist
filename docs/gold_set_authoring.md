# Held-out gold-set authoring

The final gold set is the owner-designed, owner-adjudicated, never-before-run input to
Archivist's formal measurements. It contains 34–46 questions across the six locked strata in
`EVAL_CONTRACT.md` §3.4. The questions, strata, Behavior values, and inclusion decisions are
owner-authored. A future cohort may use a prospectively blinded external draft protocol, but those
drafts would not be ground truth. For this cohort, the owner elected to retain already completed,
source-reviewed annotations and disclose their historical Claude assistance rather than request a
new annotation pass solely to create prospective paperwork.

It is not the repeatedly used ten-question practical set. Those questions, the earlier Brief 1
questions, opening-screen examples, and known manual smoke questions are development data recorded
in `fixtures/development_question_registry.json`.

> **Owner-adjudicated source preserved — 2026-08-06.** H039 was removed by owner
> decision, leaving 37 retained questions across all six contracted strata; H020 and H040 also
> remain intentionally absent. A separate final DOCX and private canonical JSON were generated
> without overwriting either owner source. The canonical draft passes run-of-record schema,
> composition, location, and development-overlap checks. Its ordered owner fields are committed as
> a text-free SHA-256 binding to frozen candidate
> `8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e` / `evidence-planned-v26`. No fresh annotation request
> was made and no held-out item has been sent to Archivist. The annotation fields already reviewed
> by the owner are the authoritative source for final canonicalization. Their historical Claude
> drafting is disclosed retrospectively without claiming a prospectively blinded or hash-captured
> draft. The two inherited claims responsible for three copied-phrase flags were paraphrased without
> changing their rubric meaning or source bindings; no held-out question triggered the privacy audit.

## Non-negotiable authority and candidate-independence boundary

Only the manuscript owner decides:

- which questions belong in the set;
- whether each question should be answered or declined;
- each question's stratum; and
- whether to accept, adopt, revise, or reject every drafted claim, essentiality flag, supporting or
  relevant chunk ID, `must_not_claim` entry, and note.

Historical Claude drafting contributed to parts of the annotation prose before the repository had
a prospective question commitment and raw-draft protocol. The exact model, surface, raw draft, and
prospective blinding record were not captured. They must be recorded as unavailable, not recreated
or guessed. This limitation does not authorize any new external call and is not described as a
prospectively blinded annotation workflow.

The owner checked every retained proposal directly against the corpus, made the inclusion and
scoring decisions, and consciously adopted or revised the completed annotations. Accurate draft
wording does not need cosmetic paraphrasing merely to prove ownership. Plausibility is not
verification and a rubber-stamp review does not satisfy the contract. The privacy audit covers
questions, claims, `must_not_claim`, and notes before commit and still rejects copied manuscript
language.

For a future gold set, the unused prospective workflow remains available in
`docs/gold_annotation_prompt_claude.md` and `scripts/prepare_gold_annotation_batches.py`. It must be
separately authorized and run before the owner adjudicates those new drafts. The prepared private
packet for this cohort was never sent and is not part of its provenance.

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

The old V21 binding is superseded. The application reports policy V26. The clean implementation
checkpoint immediately preceding the evaluation-only canonicalization work is now frozen as:

```text
candidate commit: 8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e
RAG policy:       evidence-planned-v26
```

If the answer pipeline changes after that commit, freeze a new candidate and rebind provenance
before any held-out item is run.

## Gate 1: finish and fingerprint the owner-controlled fields

The private owner workbook was finalized and transcribed without overwriting the source:

```powershell
uv run python scripts\import_gold_review_docx.py --force
```

The importer removes only declared excluded blocks, updates mechanical workbook status text,
applies owner-approved claim paraphrases from the ignored private
`runtime/gold-authoring/gold_claim_paraphrases.json` sidecar, transcribes claims and locations, and
refuses ambiguous rows. Each replacement is bound to the expected SHA-256 of its original claim
prose, and the importer fails if a replacement is stale, targets the wrong ordinal, or goes unused.
Keeping those two pre-lock rubric statements out of tracked source avoids publishing private gold
prose through the importer itself. The importer validates the result in run-of-record mode against
the exact corpus manifest before writing the ignored private JSON.

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

Before any held-out item reaches Archivist, run the leakage audit over the completed owner question set.
Exact development reuse is forbidden. A fuzzy flag requires substantive review, not a cosmetic
word substitution. Preserve the resulting review decision in provenance before this gate passes.

The earlier Markdown/JSON tooling gap is closed. `scripts/fingerprint_gold_questions.py` accepts
the same private canonical JSON used by the overlap checker, including intentionally gapped stable
H-identifiers. `scripts/audit_gold_leakage.py --output` preserves a private text-free audit report.
The 37-item projection has zero exact duplicates and zero deterministic near-match flags against
the committed development registry.

After every ID, question, stratum, and Behavior value is final, write a text-free commitment:

```powershell
uv run python scripts\fingerprint_gold_questions.py `
  runtime\gold-authoring\gold_set.draft.json `
  --output fixtures\gold_questions.commitment.json
```

Copy the resulting `question_set_sha256` into the private provenance draft and commit the
commitment, contract, and candidate binding **before** sending any held-out item to Archivist. The final
provenance validator recomputes the same ordered ID/question/stratum/Behavior projection from
`fixtures/gold_set.json`; annotation edits cannot alter it silently.

## Gate 2: disclose historical assistance without inventing provenance

The present cohort retains the annotations in the completed owner-review workbook. Parts began as
Claude-generated drafts, but the historical assistance preceded the prospective protocol. The
project does not have a complete raw-draft record, an exact model or surface record, or evidence
that the drafting was prospectively blinded. Provenance v4 therefore records:

- method `owner_adjudication_with_historical_ai_drafting/1`;
- provider `Anthropic (Claude)`;
- model and surface as `not recorded`;
- both raw-draft-record and prospective-blinding-record availability as `false`; and
- a plain-language limitation explaining that owner source adjudication occurred later.

This is a weaker annotation-process record than a prospective blind protocol, but it is the honest
record. Candidate independence remains protected by the owner-authored questions, the development-
question overlap check, the frozen pre-run commitment, and the prohibition on sending an H-item to
Archivist before lock.

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
chunks. Historical Claude text had no independent authority: the owner directly confirmed support
for each retained scorable claim unit, searched for omissions within the declared scope, and
consciously adopted or revised the completed annotation.

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
5. Preserve the retrospective assistance disclosure exactly; do not add a raw-draft or blinding
   claim that cannot be supported.
6. Set each owner attestation to `true` only if it is true.
7. Save the completed sidecar as `fixtures/gold_set.provenance.json`.

The version-4 sidecar binds the owner-controlled question projection, exact final gold bytes,
frozen candidate, V26 policy, corpus manifest, and development registry while explicitly recording
the historical-assistance limitation. The hash-bound JSON files are pinned to LF line endings in
`.gitattributes`, so a Windows checkout cannot silently change their hashes.

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
- the final owner fields disagree with `fixtures/gold_questions.commitment.json`;
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
