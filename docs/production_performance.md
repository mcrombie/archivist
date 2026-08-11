# Archivist Production Performance Protocol

This document defines the operational cohort used to support Archivist's production-observability
and latency claim. It is deliberately separate from `EVAL_CONTRACT.md`: the frozen V26 retrieval
and answer-quality baseline remains unchanged, while this cohort measures one deployed HTTP path.
It does not score historical correctness, retrieval quality, faithfulness, or answer style.

## Current status

**Complete and measured — 2026-08-11.** The run of record is
`production-performance-2026-08-11-01`, measured against deployed wrapper commit
`e71d9b79a60a894cb38451c37e0d43b7f9149fa9`. Its text-free
[public summary](evidence/production-performance-v1-2026-08-11/public-summary.json) has file
SHA-256 `dd13ad2cf60a863daf88e549106059a1d05126b40ffa3c66c3c8e18cb6246b7f`; the JSON's embedded
canonical artifact hash is `e2fcc051e66b115cf56abf7061fa93bfcd3c12297396cbdc3fad42b8bd1bfd30`.
The cohort sent the 33 locked question strings and the passages retrieved by the private Render
service to OpenAI under the owner's explicit authorization and cost cap.

| Measure | Observed result |
|---|---:|
| Attempted requests | 33 |
| Valid successful completions / latency denominator | 29 |
| Request failures | 4 |
| All-attempt request error rate | 12.1212% |
| Instrumentation failures | 0 |
| Server p50 / nearest-rank p95 | 54.393 s / 113.801 s |
| Client p50 / nearest-rank p95 | 54.493 s / 113.829 s |
| Tokens | 500,164 |
| Priced / unpriced events | 80 / 0 |
| Estimated API cost | `$4.90594694` |

These are observations from one fixed warm production cohort. They are not an SLA, load test,
uptime study, significance claim, or guarantee of future latency or reliability.

The four failures were all fail-closed structured-generation contract rejections after successful
planning and direct-answer evidence selection: two `missing_unit_requirement_id`, one
`obligation_role_mismatch`, and one `unsupported_requirement_has_unit`. They were not budget,
transport, deployment-identity, retrieval-availability, or instrumentation failures. The latency
figures therefore describe the 29 successful response-contract completions, while the 12.1212%
failure rate remains a separate product-reliability result over all 33 attempts.

## Fixed cohort

- The denominator is exactly **33 attempted requests**: the answerable items from the locked
  37-question held-out set. The four out-of-corpus items are excluded because this cohort measures
  the latency of the ordinary answer-producing path. Their absence behavior remains part of the
  frozen answer-quality baseline.
- Held-out IDs and question text remain private runner inputs. Public reports contain only counts,
  hashes, identities, and aggregate results; they never enumerate the IDs or reproduce question
  text.
- Every attempt is a new first turn with a fresh conversation ID and turn ID, `Essential` mode,
  `Complete answer` delivery, the ordinary RAG strategy, and empty conversation history.
- Requests run sequentially. Their starts are at least **12 seconds apart**, and that pacing delay
  is excluded from request latency. This prevents the measurement from accidentally becoming a
  test of the configured six-requests-per-minute per-client gate if several requests finish
  quickly.
- There is no automatic or manual retry and no replacement. A timeout, non-successful HTTP result,
  malformed response, or missing observation keeps its original place in the 33-attempt
  denominator. The operator-client timeout is fixed at **240 seconds** per request.

## Deployment and warm-process identity

The runner must bind the live service before it submits a paid question. It issues exactly two
`/api/health` readiness checks and one `/api/version` check. The latter must use
`archivist.public_runtime_identity/2`. Its deployment identity comes from Render's
`RENDER_GIT_COMMIT`, and it also records the process epoch, active RAG policy, generator model,
corpus-manifest SHA-256, frozen-candidate identity, `public-rag-request-ceiling-v1`, and its
`2000000000` nano-USD amount. On Render, `RENDER_GIT_COMMIT` is authoritative; a local/test override
cannot mask a present invalid or different Render identity. All three responses must identify the
same deployment commit and process epoch, and the deployed commit must equal the clean local commit
that prepared the cohort. The run stops if the service restarts or any bound identity changes.

There is **no paid warm-up question**. “Warm” means the already-running Render process passed the
two readiness observations and retained one process epoch; it does not claim that OpenAI model
weights, provider caches, or every network connection were pre-warmed. The report records that
definition and must not call the result a cold-start measurement.

## Latency and outcome definitions

- **Server duration** starts when the public application accepts the question request and ends
  after it has constructed the complete terminal HTTP response. It excludes the runner's pacing
  delay, browser rendering, and UI animation. It is not merely model-generation time.
- A **valid successful completion** requires a successful HTTP response, the expected public answer
  shape, a correlated privacy-safe request observation, matching deployment commit/process epoch,
  and internally consistent server-duration metadata.
- **p50** is the ordinary median of valid successful server durations.
- **p95** is nearest rank: after sorting the `S` valid successful durations, use rank
  `ceil(0.95 * S)`, counting from one.
- The report always states `S`. Latency is never described as covering all 33 requests unless all
  33 are valid successful completions.
- **Request error rate** uses all 33 attempts as its denominator. HTTP failures, transport
  timeouts, and malformed terminal response shapes are request failures.
- A missing, duplicate, mismatched, or invalid correlation/measurement record is an
  **instrumentation failure**. It is reported separately rather than silently discarded or
  converted into an application-quality verdict. An attempt can therefore be absent from the
  latency distribution without being replaced.
- A contract-valid successful response with zero request-scoped usage events is also an
  instrumentation failure and is ineligible for latency. It is not evidence of a free RAG answer.
  If `S` is zero, p50 and p95 remain explicitly unavailable.

Valid application-level releases such as a source-bounded insufficient-evidence response remain
successful HTTP completions when their response and observation contracts pass. This cohort
measures delivery behavior, not whether an answer deserves a favorable historical score.

## Cost boundary

The live command requires both an explicit paid-operation acknowledgement and an owner-authorized
numeric cohort cap. The public service owns a versioned **$2.00 maximum per Complete RAG request**.
It checks that the full amount fits beneath the monthly budget before RAG begins, projects every
provider operation before sending it, requires strict usage recording, and stops a request whose
projected cumulative cost would cross the ceiling. `/api/version` exposes the ceiling version and
nano-USD amount; the prepared manifest, deployed identity, and authorization record must agree.

Before each new attempt, the runner requires headroom for the same server-exposed $2.00 maximum.
Recorded request-scoped usage replaces that maximum when it is available. If a timeout or other
transport failure leaves acceptance and spend unknowable, the attempt is sealed without replay,
that invocation stops, exact spend remains unavailable, and the full $2.00 maximum is permanently
charged to conservative authorization accounting. A later request can start only if recorded spend
plus all such unknown allowances plus another $2.00 remains within the owner cap. Neither unused
headroom nor a stop permits retry or replacement.

The numeric cap is a run input and may not exceed the owner's separately authorized ceiling. The
runner requires it to be finite and at least $2.00. The
private result and public summary distinguish recorded estimated cost, conservative authorization-
accounted cost, and attempts with unavailable usage; an exact total is withheld if any transport
outcome remains unknown. They also state the ceiling version and amount, priced and unpriced event
counts, and tokens. Provider billing remains authoritative.

## Runner workflow and reproduction boundary

The completed run used the workflow below. Do not rerun or replace any of its 33 sealed attempts.
For a separately declared future cohort, run these steps only after its instrumented commit is
committed, pushed, deployed, and visible as Render's exact `RENDER_GIT_COMMIT`. The local checkout
used by `prepare` must be clean and at that same commit.

Prepare the sealed private manifest locally. This command is offline:

```powershell
$archivistProdRunId = "production-performance-YYYY-MM-DD-01"
$archivistProdRunRoot = "runtime/production-performance/$archivistProdRunId"
uv run python scripts/run_production_performance.py prepare `
  --run-root $archivistProdRunRoot `
  --run-id $archivistProdRunId `
  --base-url https://archivist.mcrombie.com
```

The prepared root contains private H-item bindings, though no question text. Create the matching
private directory on Render's persistent disk and transfer that root using the service-specific SSH
destination shown by Render. Do not record that destination in the repository:

```powershell
scp -s -r $archivistProdRunRoot `
  <render-ssh-destination>:/var/data/runtime/production-performance/
```

In Render Shell, change to the deployed source directory containing `pyproject.toml`. Only after the
owner has explicitly authorized the 33 locked questions, their retrieved manuscript passages,
OpenAI, and a numeric cap, run:

```sh
ARCHIVIST_PROD_RUN_ID=production-performance-YYYY-MM-DD-01
uv run python scripts/run_production_performance.py run \
  --run-root "/var/data/runtime/production-performance/$ARCHIVIST_PROD_RUN_ID" \
  --usage-db /var/data/runtime/usage.sqlite3 \
  --authorize-production-performance \
  --max-cost-usd <owner-authorized-cap>
```

The runner uses the local persistent usage database to correlate each public response with its
private server observation and request-scoped usage. It will not work as evidence if pointed at an
unrelated or copied ledger. Before writing an intent or sending a POST, it rejects any prepared
conversation/turn scope already present in that ledger, preventing stale request identities from
being mistaken for this cohort. If it stops, preserve the run root. Re-running the same command may
recover an already accepted intent from the same ledger or continue only untouched ordinals; it
never replays a sealed or ambiguous paid attempt and may not cross a deployment commit, process
epoch, authorization, or request-cost-ceiling contract.

After all 33 terminal outcomes are sealed, build the reports without another network call:

```sh
uv run python scripts/run_production_performance.py report \
  --run-root "/var/data/runtime/production-performance/$ARCHIVIST_PROD_RUN_ID" \
  --usage-db /var/data/runtime/usage.sqlite3
```

The run root then contains:

- `prepared-manifest.json`, `authorization.json`, and `runtime-session.json`;
- one immutable `intent.json` and `outcome.json` beneath each ordinal in `attempts/`;
- private, text-free `private-summary.json`; and
- publishable, text-free `public-summary.json` and `public-report.md`.

Copy only the two public artifacts out of Render for publication. Keep the manifest, session,
authorization, attempts, private summary, and live usage database private and gitignored.

## Artifact boundary

The private, gitignored run root may retain request-level timing and correlation records needed to
audit the aggregate. A publishable report and JSON summary must be text-free. They may contain:

- deployed commit plus corpus/policy/model identities and a hash of the private runtime identity;
- attempted, valid-success, request-failure, and instrumentation-failure counts;
- aggregate latency values and their exact denominators;
- status and safe error-code counts;
- aggregate token and operation totals, recorded cost, conservative authorization-accounted cost,
  unavailable-usage count, and the versioned request ceiling; and
- runner/report schema versions and artifact hashes.

They must not contain held-out IDs or question text, answers, prompts, retrieved passages, source
labels, manuscript text, conversation or turn IDs, provider response IDs, client addresses,
credentials, or raw user conversations.

## Interpretation and resume language

This is one observed production cohort, not an SLA, uptime study, load test, significance claim, or
single-number guarantee. The exact evidence-backed resume form is:

> Deployed on Render with privacy-safe request correlation, per-stage timing, and token/cost
> telemetry; in a predeclared 33-request warm production cohort, observed 54.393-second p50 and
> 113.801-second p95 end-to-end server latency across 29 successful completions, with four request
> failures (12.1212%), zero instrumentation failures, and `$4.90594694` estimated API cost.

For a shorter resume, round without hiding the denominators: “54.4 s p50 / 113.8 s p95 across 29
successful completions in 33 attempts; 12.1% request failures and zero instrumentation failures.”
The four failures were not replaced, and the latency denominator must not be represented as 33.
