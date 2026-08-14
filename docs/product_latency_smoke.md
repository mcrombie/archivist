# Product latency smoke

`product-latency-smoke-v1` is a small operational check for the current
retrieval-authored product. It is intentionally separate from the 37-question
quality evaluation: it measures latency and accounting only, and it does not
score retrieval or answer quality.

## Fixed scope

The fixture contains exactly three non-held-out questions already registered as
development data:

- two questions that the deterministic question plan classifies as `ordinary`;
- one question that it classifies as `broad`.

Each is sent as a fresh first turn in Professional mode through the real local
application-compiled path. A valid measurement has exactly one
`query_embedding` event and one `answer_generation` event per question. The
smoke makes no automatic retries.

The runner writes an intent before each attempt. An exception, missing or
unpriced usage event, changed operation count, or answer-length profile mismatch
seals a text-free failure outcome and stops the run. Never rerun or resume that
root; investigate it and use a new root only under a new explicit live-run
authorization.

## Cost and authorization

Creating the harness and running its offline tests makes no provider call. A
live smoke sends three questions and selected private manuscript evidence to
OpenAI. It therefore requires a separate owner authorization for this exact
scope.

The command requires an explicit `$6.00` aggregate ceiling: three attempts
times the public request ceiling of `$2.00`. This is a defensive worst-case cap,
not an estimate of likely spend. The isolated ledger enforces both the per-turn
ceiling and the aggregate budget.

Run from a clean, committed working tree with a new child directory:

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
uv run python scripts/run_product_latency_smoke.py `
  --run-root runtime/evaluations/product-latency-smoke-v1/2026-08-13-local-01 `
  --max-total-cost-usd 6.00 `
  --authorize-openai-latency-smoke
```

Do not add the authorization flag until the owner has authorized the named
three-question run, private evidence disclosure, and `$6.00` maximum.

## Artifacts and interpretation

The ignored run root contains:

- `prepared.json`, binding the clean commit, dependency lock, corpus manifest,
  development registry, current authored-response policy, model, and adaptive
  length policy;
- one text-free `intent.json` and `outcome.json` per attempted question;
- an isolated `usage.sqlite3` ledger;
- `report.json` and `report.md` after all three attempts complete.

Artifacts retain IDs, hashes, statuses, fallback codes, profile labels, source
counts, token/accounting totals, and stage/end-to-end timings. They do not retain
question text, answer text, source text or IDs, manuscript text, or provider
error messages.

The report gives end-to-end minimum, median, and maximum latency overall and by
ordinary/broad profile, plus status and fallback counts, provider-operation
counts, output tokens, and exact recorded cost. It deliberately does not report
p95: a three-item sample cannot support a useful tail-latency estimate. Treat it
as a quick regression signal, not a production SLA or quality verdict. Its
end-to-end clock surrounds the local answer function; browser rendering, client
network transit, public rate limiting, and deployment queueing are outside this
small test.
