# Product latency smoke

`product-latency-smoke-v1` is a small operational check for the current
retrieval-authored product. It is intentionally separate from the 37-question
quality evaluation: it measures latency and accounting only, and it does not
score retrieval or answer quality.

Status: **completed and sealed on 2026-08-14**. All three Professional turns were authored with
zero fallbacks and zero retries. Recorded cost was `$0.177749880`. End-to-end wall time was
19.772 seconds minimum, 21.967 seconds median, and 26.105 seconds maximum. The two ordinary turns
were 19.772 and 21.967 seconds; the broad turn was 26.105 seconds. Answer-generation stages were
17.399 and 18.929 seconds for ordinary turns and 25.449 seconds for the broad turn. Preserve this
root unchanged; it is current v5 evidence for these three observations only.

## Fixed scope

The fixture contains exactly three non-held-out questions already registered as
development data:

- two questions that the deterministic question plan classifies as `ordinary`;
- one question that it classifies as `broad`.

Each was sent as a fresh first turn in Professional mode through the real local
retrieval-authored product path. A valid measurement has exactly one
`query_embedding` event and one `answer_generation` event per question. The
smoke makes no automatic retries.

The runner writes an intent before each attempt. An exception, missing or
unpriced usage event, changed operation count, or answer-length profile mismatch
seals a text-free failure outcome and stops the run. Never rerun or resume that
root; investigate it and use a new root only under a new explicit live-run
authorization.

## Cost and authorization used

Creating the harness and running its offline tests made no provider call. The completed live smoke
sent three questions and selected private manuscript evidence to OpenAI under a separate exact
owner authorization for this scope.

The command requires an explicit `$6.00` aggregate ceiling: three attempts
times the public request ceiling of `$2.00`. This is a defensive worst-case cap,
not an estimate of likely spend. The isolated ledger enforces both the per-turn
ceiling and the aggregate budget.

The historical invocation was run from a clean, committed working tree with a new child directory:

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
uv run python scripts/run_product_latency_smoke.py `
  --run-root runtime/evaluations/product-latency-smoke-v1/2026-08-14-local-01 `
  --max-total-cost-usd 6.00 `
  --authorize-openai-latency-smoke
```

Do not rerun or resume that root. A different experiment requires its own identity, unused root,
and authorization; the paired Standard-versus-Fast experiment is documented separately in
[`product_fast_latency_comparison.md`](product_fast_latency_comparison.md).

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
