# Held-out gold-set authoring

The final gold set is the owner-authored, never-before-run input to Archivist's formal
measurements. It contains 34–46 questions across the six locked strata in
`EVAL_CONTRACT.md` §3.4.

It is not the repeatedly used ten-question practical set. Those questions, the earlier Brief 1
questions, opening-screen examples, and known manual smoke questions are development data recorded
in `fixtures/development_question_registry.json`.

## Non-negotiable authorship boundary

Only the manuscript owner decides:

- which questions belong in the set;
- whether each question should be answered or declined;
- what a correct answer must claim;
- which claims are essential;
- which chunks support each claim;
- which chunks are relevant to the complete question; and
- which plausible but false statements belong in `must_not_claim`.

Codex or another model may create blank forms, format owner-written material, find duplicate
wording, and run mechanical validation. It may not propose questions, historical claims, expected
answers, essentiality, source locations, relevant chunks, or false-claim traps. Claims must be
paraphrased in the owner's words, not copied from the manuscript.

No held-out question may be sent to Archivist, its retriever, its planner, an answer model, or an
evaluation judge until the set and provenance sidecar are committed and locked.

## Gate 0: accept one frozen candidate

The offline-verified V21 candidate is:

```text
candidate commit: bf424c880bca4728a8d13225f85978e27a8d8dcf
RAG policy:       evidence-planned-v21
```

Before beginning substantive gold authoring, finish the predeclared unchanged no-retry G007
confirmation and ten-question development evaluation. If that causes another system change, freeze
a new candidate and update the provenance template before authoring. This prevents the benchmark
from being bound to a candidate that was already known to need replacement.

## Gate 1: create the private owner workbook

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
with a timezone-aware ISO-8601 timestamp. Leave every attestation `false`.

## Gate 2: author from the manuscript, not from Archivist

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
chunks.

## Gate 3: run offline audits before locking

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

Check that claims are paraphrases rather than long copied passages. This reads the private local
chunks but emits only IDs and matched-token counts:

```powershell
uv run python scripts\audit_gold_privacy.py `
  --gold runtime\gold-authoring\gold_set.draft.json `
  --manifest fixtures\corpus_manifest.json `
  --chunks output\chunks.json `
  --output runtime\gold-authoring\privacy-audit.json
```

The command exits nonzero while quotation-risk flags remain. Review each flag manually and rewrite
copied prose in the owner's words.

## Gate 4: lock provenance

After the owner finishes the content:

1. Copy the completed draft to `fixtures/gold_set.json`.
2. Record its exact lowercase SHA-256 in `gold_set_sha256`.
3. Record `authoring_completed_at`.
4. Add one `approved_distinct` review with a substantive owner note for every remaining fuzzy
   match reported by the leakage audit.
5. Set each owner attestation to `true` only if it is true.
6. Save the completed sidecar as `fixtures/gold_set.provenance.json`.

The sidecar binds the exact gold bytes to the frozen candidate commit, V21 policy, corpus manifest,
and complete development-question registry. The hash-bound JSON files are pinned to LF line
endings in `.gitattributes`, so a Windows checkout cannot silently change their hashes.

Commit the gold set, completed provenance, and any owner-authored notes. From the resulting clean
tree run:

```powershell
uv run python scripts\validate_gold_holdout.py `
  --candidate-commit bf424c880bca4728a8d13225f85978e27a8d8dcf `
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
