# Conversational persona evaluation

> Historical v3 plan: this suite never made a provider call before the v3 cohort was terminally
> closed. The current v4 adapter owns a separate four-mode, twelve-case social phase documented in
> [retrieval_authored_v4_evaluation.md](retrieval_authored_v4_evaluation.md). Do not run the v3
> commands below or charge them to the closed v3 scope. The legacy paid runner now detects the
> shared root's `diagnostic-closure.json` and stops before authorization artifacts, provider-client
> construction, or any call.

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
- owner-authorized cumulative cap: 7,000,000,000 nano-USD (`$7.00`)
- cumulative ambiguity reserve: dynamically read from the adapter's immutable continuation chain
- effective tracked ceiling: owner cap minus the cumulative ambiguity reserve

The reserve treats every unledgered but potentially billable provider-boundary attempt
conservatively. The current committed chain through H003 contains two reservations totaling
797,731,250 nano-USD, producing an effective tracked ceiling of 6,202,268,750 nano-USD
(`$6.202268750`). Later committed continuation entries can lower that ceiling again without a
persona-harness code change.

The CLI still requires the owner's exact `$7.00` authorization; a cumulative reserve is not a
smaller authorization and does not create another allowance. Before any persona call, the harness
validates that the shared ledger contains only the master request and no unpriced event. It also
validates the adapter-reported reservation count/list, cumulative reserve, effective ceiling,
tracked spend, remainder, and exact-USD representations. The full untouched four-call projection
must fit within that dynamic remainder. Every call and the shared ledger's monthly hard budget use
the adapter-reported effective ceiling. The manifest, authorization artifact, attempt intents, and
final report distinguish the owner cap, complete reservation chain, effective ceiling, and tracked
remainder.

## Fail-closed artifacts and resume

The run writes a sealed intent before constructing a client or attempting an item. A valid outcome
must match exactly one priced `answer_generation` event in the shared ledger for that item's turn
ID. Completed outcomes are skipped on resume. An intent without a provable outcome, a mismatched
ledger event count, foreign request scope, unpriced usage, a changed manifest, or insufficient
capacity beneath the reserve-adjusted ceiling stops the cohort without replaying the item.
Existing artifacts are never overwritten.

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
