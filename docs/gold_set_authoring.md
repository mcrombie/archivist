# Gold-set pilot authoring

The first gold-set pilot is ten owner-authored questions spanning at least four
strata. It is a workflow test and future calibration input, not a baseline or a
run-of-record artifact.

Only the manuscript's author decides:

- which questions belong in the set;
- what a correct answer must claim;
- which chunks support each claim; and
- which plausible statements the answer must not make.

Model assistance may format, deduplicate, and validate the JSON. It must not
write historical claims or choose their source locations. Claims must be
paraphrased in the author's own words; do not copy manuscript passages into the
gold set.

## Start the pilot

Copy the deliberately empty template to a working file:

```powershell
Copy-Item fixtures\gold_set.pilot.template.json fixtures\gold_set.pilot.json
```

Add exactly ten items. Use this field shape for each item, replacing every
angle-bracketed value:

```json
{
  "id": "<unique item ID>",
  "question": "<owner-authored question>",
  "stratum": "<one allowed stratum>",
  "expected_behavior": "answer",
  "claims": [
    {
      "claim_id": "<item ID>.1",
      "text": "<owner-authored paraphrase of an essential claim>",
      "essential": true,
      "supporting_chunk_ids": ["<exact corpus chunk ID>"]
    }
  ],
  "relevant_chunk_ids": ["<exact corpus chunk ID>"],
  "must_not_claim": [],
  "notes": ""
}
```

For an `abstain` item, both `claims` and `relevant_chunk_ids` must be empty.

The two location fields are intentionally different:

- `supporting_chunk_ids` belongs to one claim and contains every overlapping
  chunk that can correctly support that claim.
- `relevant_chunk_ids` belongs to the whole question and contains every chunk a
  complete answer should be able to use. It must include the union of all claim
  support sets.

Only exact `chunk_id` values from
[`fixtures/corpus_manifest.json`](../fixtures/corpus_manifest.json) are valid
locations. Paragraph numbers, page numbers, document names, and chapter names
are useful orientation but are not ground truth.

Allowed strata are:

- `focused_biographical`
- `focused_analytical`
- `conceptual`
- `broad_thematic`
- `out_of_corpus`
- `adversarial_premise`

Validate while authoring:

```powershell
uv run python scripts\validate_gold_set.py fixtures\gold_set.pilot.json
```

The command reads only the gold JSON and the text-free corpus manifest. It makes
no API calls. It reports all mechanical errors it finds in one pass.

The validator cannot establish that a claim is historically correct, that a
location genuinely supports it, that prose was paraphrased, or that the owner
authored it. Those are human provenance checks.

## Expanding to the final set

The pilot version must retain its `-pilot` marker. Pilot validation requires
exactly ten items across at least four strata and always prints `PILOT ONLY`.

A later final file should be saved as `fixtures/gold_set.json`, use a stable
version such as `1.0.0`, and contain the locked composition from
`EVAL_CONTRACT.md` section 3.4:

| Stratum | Required count |
|---|---:|
| `focused_biographical` | 7–9 |
| `focused_analytical` | 7–9 |
| `conceptual` | 5–7 |
| `broad_thematic` | 9–11 |
| `out_of_corpus` | 4–6 |
| `adversarial_premise` | 2–4 |

That produces 34–46 items. Check it with the explicit stronger mode:

```powershell
uv run python scripts\validate_gold_set.py fixtures\gold_set.json --mode run-of-record
```

Before completing the final set, the owner must also record whether front
matter, the Afterword, and the appendices are intended retrieval targets. A
schema-valid final file is still not a run of record by itself; the clean-tree
and complete run-identity requirements apply separately.

If the corpus manifest changes, do not merely replace
`authored_against_corpus`. Re-verify every stored location against the new
manifest using the chunk ID and `text_sha256` carry-over procedure in
`EVAL_CONTRACT.md` section 2.5.
