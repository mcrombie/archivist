# Conversational persona evaluation

`persona-conversation-evaluation-v1` is a separate, non-gold development cohort for Archivist's
compact `character-conversation-v2` route. It does not measure retrieval, grounding, factual
answer quality, or the held-out manuscript benchmark.

## Fixed cohort

The manifest is derived from the current generated-mode registry and must cover it exactly:

- Professional
- Pretty Pink Princess
- Baleful Black Baron
- Ruthless Red Realist (`ember_and_ink`)

Every mode receives the same fixed, classifier-approved prompt: **How are you?** This directly
retests the reported social-turn failure while keeping the cross-mode distinctness comparison free
from question-wording differences. Each untouched item permits exactly one no-retry
`gpt-5.6-sol` call using the production character-conversation request. The payload contains only
the question and registry-owned character instructions: no history, embedding, retrieval,
manuscript text, evidence dossier, sources, or gold annotations.

## Spend and execution boundary

Preparation and reporting are offline. A live run is not authorized merely because the harness
exists. It requires both the explicit CLI authorization flag and an exact `$7.00` maximum:

```powershell
python scripts/run_persona_evaluation.py prepare
python scripts/run_persona_evaluation.py run `
  --authorize-live-persona-evaluation `
  --max-cost-usd 7.00
python scripts/run_persona_evaluation.py report
```

Do not run the live command until the owner expressly authorizes this cohort. The persona suite
does not create a separate `$7` allowance. It shares all of the following with the broader v3
evaluation:

- root: `runtime/evaluations/retrieval-authored-v3-professional-2026-08-13`
- ledger: `usage.sqlite3` beneath that root
- request ID: `retrieval-authored-v3-professional-2026-08-13-master`
- project ID: `archivist-v3-evaluation`
- cumulative request ceiling: 7,000,000,000 nano-USD

The runtime scope enables budget enforcement, disallows over-budget execution, and passes the same
request-level ceiling to every item. It does not alter ledger budget settings.

## Fail-closed artifacts and resume

The run writes a sealed intent before constructing a client or attempting an item. A valid outcome
must match exactly one priced `answer_generation` event in the shared ledger for that item's turn
ID. Completed outcomes are skipped on resume. An intent without a provable outcome, a mismatched
ledger event count, unpriced usage, a changed manifest, or insufficient capacity beneath the
shared ceiling stops the cohort without replaying the item. Existing artifacts are never
overwritten.

Private, gitignored outcome artifacts retain the response needed for local audit. The final report
contains no verbatim response prose. Apart from mode IDs, it retains only hashes, counts, and
labels from the fixed transparent signature lexicons, and reports:

- generated, local-fallback, and technical-failure status counts;
- per-item, median, and maximum latency;
- exact item/cohort cost and the shared master-ledger cost at report time;
- whether every follow-up is a question that explicitly leads back to the manuscript; and
- transparent mode-signature hits, reply hashes, and pairwise token Jaccard similarity.

The distinctness fields are a lightweight development diagnostic, not a semantic judge or a claim
that a persona is good. The structured response contract follows OpenAI's documented SDK pattern
for parsing typed structured output: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
