# Product Fast latency comparison

`product-fast-latency-comparison-v1` is a paired operational experiment for the current
`retrieval-authored-v5` Professional answer path. It asks one narrow question: does OpenAI Fast
materially shorten answer-generation latency for the same three-question workload? It is not a
retrieval, answer-quality, citation-groundedness, production-SLA, or tail-latency evaluation; its
citation check is limited to syntax and local resolvability.

The experiment is separate from the completed [`product-latency-smoke-v1`](product_latency_smoke.md)
and never changes or resumes that sealed run.

## Frozen comparison

The comparison reuses the smoke's three registered non-held-out development questions: two
`ordinary` questions and one `broad` question. Each question is submitted twice as a fresh
Professional first turn, once per arm, for exactly six attempts:

- **Standard:** answer generation requests the `default` service tier.
- **Fast:** answer generation requests the SDK's pinned `priority` service-tier alias for OpenAI
  Fast.

The six-attempt order is frozen as question 1 Standard/Fast, question 2 Fast/Standard, and question
3 Standard/Fast so that neither arm always runs first. Question, committed product version, model,
reasoning effort, verbosity, retrieval policy, adaptive answer-length profile, and release checks
remain the same across a pair.
Only the answer-generation service tier changes. Query embeddings remain on the standard embedding
path; Fast does not apply to the embedding operation, and their requested/returned tier ledger
fields remain null because the embedding request carries no service-tier argument.

OpenAI documents Fast mode as a per-request service tier for lower and more consistent latency,
and documents its premium pricing separately: [Fast mode guide](https://developers.openai.com/api/docs/guides/fast-mode)
and [API pricing](https://developers.openai.com/api/docs/pricing?latest-pricing=fast). The runner
binds both the requested tier and the returned tier: Standard requires `default`/`default`, and
Fast requires `priority`/`priority`. A missing or unknown returned tier is unpriced. A different
recognized returned tier is priced according to what actually ran, but it invalidates the intended
arm and stops the comparison without a retry.

Every valid attempt must record exactly one `query_embedding` event and one `answer_generation`
event. There are no automatic retries, replacements, or resumptions. An ambiguous provider outcome,
missing or unpriced usage, operation-count mismatch, tier mismatch, profile mismatch, or artifact
contract failure seals a text-free failure and stops the run. Investigate a stopped root without
rewriting it; any later attempt requires a new root and new authorization.

## Authorization and cost boundary

Implementation, preparation, and offline tests make no provider call. A live comparison sends six
questions and selected private manuscript evidence to OpenAI and therefore needs a new, exact owner
authorization. Earlier authorization for the completed three-call smoke does not transfer.

The live command requires an exact `$12.00` aggregate ceiling: six attempts times the existing
public `$2.00` per-attempt ceiling. This is a defensive maximum, not forecast spend or a promotion
threshold. The isolated ledger enforces the per-attempt and aggregate boundaries. Do not add the
live authorization flag until the owner has authorized this named six-attempt comparison, private
evidence disclosure, and `$12.00` maximum.

The tier-aware local pricing table records `gpt-5.6-sol` `priority` generation at exactly twice
its Standard rate. This is still an estimate; the provider invoice remains authoritative.

After that authorization, run from a clean committed tree with a previously unused child root:

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
uv run python scripts/run_product_fast_latency_comparison.py `
  --run-root runtime/evaluations/product-fast-latency-comparison-v1/<new-child> `
  --max-total-cost-usd 12.00 `
  --authorize-openai-fast-latency-comparison
```

No acceptable-cost threshold has been specified for choosing Fast over Standard. The report must
therefore publish arm and paired cost observations, but the cost promotion result remains
`owner_pending`; the harness must not invent a dollars-per-second or percentage-premium gate after
seeing results.

## Artifacts and privacy

The ignored run root contains a prepared manifest, one intent and outcome per attempt, an isolated
usage ledger, and final JSON and Markdown reports. Public-safe artifacts retain only IDs, hashes,
arm and tier labels, response/fallback states, profile labels, operation counts, token and cost
totals, and stage/end-to-end timings. They never retain question text, answer text, source text or
IDs, manuscript text, or provider error messages.

The protocol is once-only. A completed root is immutable; a stopped root is terminal. The report
must disclose all six intended attempts, all actually attempted outcomes, fallback and validation
counts, returned tiers, exact operation counts, and spend.

## Predeclared interpretation

The primary latency statistic is paired answer-generation time. For every question with valid
observations in both arms, calculate `fast_generation_ms / standard_generation_ms`, then take the
median of those three ratios. The mechanical latency gate passes only when:

1. the median paired ratio is at most `0.70`; and
2. Fast is faster than Standard on at least two of the three questions.

The mechanical integrity gate is independent: all six attempts must be unambiguous, tier-correct,
fully accounted, and free of fallback or validation failure. Cost is reported separately with the
promotion decision `owner_pending` because the owner has not supplied an acceptable-cost threshold.
Passing the latency and integrity gates therefore does not automatically promote Fast.

With three pairs, the result is directional. Report the individual pairs and simple
minimum/median/maximum summaries, not p95, an SLA, a quality conclusion, or proof of a general
latency improvement. Browser rendering, public network transit, deployment queueing, and rate
limiting remain outside the local full-product-path clock.
