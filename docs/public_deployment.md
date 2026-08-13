# Archivist Public-Demo Deployment

This runbook deploys Archivist as a single public Render web service while keeping the manuscript,
typeset PDF, chunks, and Chroma index out of GitHub. Cromblog is the public doorway; the Archivist
service runs separately at the canonical public address
`https://archivist.mcrombie.com`. Render's generated
`https://archivist-cradle-of-the-empire.onrender.com` address remains enabled as an operational
fallback.

## Prepared architecture

- Render Hobby workspace
- one paid Starter web-service instance
- one 1 GB persistent disk mounted at `/var/data`
- one Uvicorn worker and one service instance
- trusted Render proxy headers so the in-memory per-reader gate sees the forwarded client address
- server-selected `public_demo` exposure profile
- private full-corpus runtime bundle copied to the disk after deployment
- OpenAI key stored only as a Render secret
- release identity read from Render's automatic `RENDER_GIT_COMMIT` environment value
- versioned `$2.00` maximum for each public Complete-RAG request, enforced by the server
- application-enforced monthly OpenAI budget and request limits

The repository-root `render.yaml` is the source of truth for the service configuration. Automatic
deploys are disabled initially so a source-code push cannot unexpectedly replace the running
version.

## Files that stay private

Never commit or upload these files as source:

- the DOCX manuscript;
- the typeset PDF;
- `output/chunks.json`;
- `chroma_db/`;
- `.env`;
- API keys;
- the generated runtime archive under `runtime/`.

The generated archive contains only the pruned 481-record Chroma collection, the matching private
chunk file, and a text-free identity manifest. It does not contain the original DOCX or PDF. It is
still private manuscript infrastructure and must not be attached to a public release.

Current prepared bundle:

| Property | Value |
|---|---|
| Local path | `runtime/archivist-public-runtime.tar.gz` |
| SHA-256 | `37642f9d495d93834829d0749d2c25389c069bd160caf438bbc34b6c2f4ad78f` |
| Size | 3,274,947 bytes |
| Chroma collection | `manuscript` |
| Embedded records | 481 |
| Chunks SHA-256 | `02e87cd42dc366a04f4b1ec43936599475cf18d120e26ce729da482a5949d6cc` |
| Corpus-manifest SHA-256 | `b7ff94315a3f1f28c831e2c3ca62c385567d2b1447c19ff45139d175c3ff3c17` |

Regenerate the archive only after the live corpus changes:

```powershell
uv run python scripts/build_public_runtime_bundle.py
```

The builder refuses to overwrite an existing archive. Move the old archive to a safe private
location before deliberately building a replacement.

## Owner setup in Render

These are the first steps that require the owner's Render account and billing method:

1. Sign in to Render with GitHub.
2. Keep the free Hobby workspace.
3. Grant Render access to `mcrombie/archivist` only.
4. Add a billing method.
5. Select **New > Blueprint**, choose `mcrombie/archivist`, and use the repository-root
   `render.yaml`.
6. Review the proposed Starter service and 1 GB disk before creating either resource.
7. Enter `OPENAI_API_KEY` directly in Render when the Blueprint asks for the unsynchronized
   secret. Never paste it into source control, a screenshot, or chat.

The Blueprint sets the ordinary public OpenAI ceiling to `$10.00` per calendar month. The history
matters: it was temporarily raised from `$5.00` to `$10.00` on 2026-08-11 for the separately capped
33-request production-performance cohort, then returned to `$5.00` after that run closed. On
2026-08-12, the owner made a separate decision to raise the ongoing public-demo ceiling to
`$10.00`. The persistent ledger retains spend already recorded in the current UTC calendar month;
raising the ceiling does not reset it. Because production deploys are manual, verify that the live
Render environment matches the Blueprint. Change `ARCHIVIST_PUBLIC_MONTHLY_BUDGET_USD` in Render
only as a deliberate owner decision; a cohort runner's own authorization cap remains independent
and cannot be increased by this setting. Render hosting charges are separate from OpenAI usage.

## Seed the private disk

The first source deployment can become live before its private corpus is present:

- `GET /api/live` should return `200`;
- `GET /api/health` should return `503` until the disk is seeded.

Render's dashboard shows the service-specific SSH command. Use that exact destination to copy the
private archive to `/var/data`; do not record the destination or SSH details in the repository.
From this repository, the transfer has this shape:

```powershell
scp -s runtime/archivist-public-runtime.tar.gz <render-ssh-destination>:/var/data/
```

Then open the Render Shell and extract it:

```sh
cd /var/data
sha256sum archivist-public-runtime.tar.gz
tar -xzf archivist-public-runtime.tar.gz
```

The reported archive hash must exactly match the value in this runbook. Confirm that
`/var/data/runtime_bundle.json`, `/var/data/output/chunks.json`, and
`/var/data/chroma_db/` exist. Restart the service from the Render dashboard after extraction so
the process opens the newly seeded Chroma store cleanly.

## Readiness and anonymous release checks

After restart:

1. `GET /api/live` returns `200` with `{"status":"live"}`.
2. `GET /api/health` returns `200` with `{"status":"ready"}`.
3. `GET /api/version` reports schema `archivist.public_runtime_identity/4`, a non-null
   `deployment_commit` equal to the exact commit deployed by Render, one `process_epoch`,
   `answer_policy_version=retrieval-authored-v3`, `evidence_retrieval_kind=hybrid_bm25_rrf`,
   `embedding_model=text-embedding-3-small`, `generated_prose_model=gpt-5.6-sol`, the corpus-
   manifest SHA-256, the frozen-candidate identity,
   `public-rag-request-ceiling-v1`, and `2000000000` nano-USD (`$2.00`) as the public RAG request
   ceiling. A missing or malformed `RENDER_GIT_COMMIT` is not acceptable for a measurement release;
   Render's value is authoritative and cannot be masked by the local/test override.
4. `GET /api/config` reports the `public_demo` profile, 481 searchable and embedded chunks,
   `full_source_text: false`, `public_page_locators: true`, and `progressive_answers: true`.
5. The opening page loads from the service's HTTPS `onrender.com` fallback URL.
6. One neutral question returns an answer with edition-qualified Typeset PDF page locators.
7. Source cards expose no full chunk text, chunk IDs, physical PDF pages, or internal diagnostics.
8. `/docs`, `/openapi.json`, project-management, embedding, source-file, and cost-setting routes
   return `404`.
9. A request containing `n_results` or `allow_over_budget` returns `422`.
10. A request larger than the public body limit returns `413`.
11. Repeated requests eventually return `429` and a `Retry-After` header.

Do not connect Cromblog until all eleven checks pass on the deployed URL.

Also confirm without sending another request that the composer summary says **Settings**, the
active **Perspective** appears above the input, and any facet or appearance override changes the
active top-right and Settings-panel label to exactly **Custom** while retaining the base preset in
its explanatory copy.

The post-v3 behavior check is separately costed and separately authorized: one generated-mode
personal question should return an uncited in-character reply with a manuscript-leading question
and record exactly one `answer_generation` event, with no embedding event or source payload. The
character call has a 12-second timeout, low reasoning, low verbosity, and a 576-token output
ceiling. This paid check is not authorized merely by following this runbook, and no such live check
has yet run.

## Connect Cromblog

Cromblog is prepared to discover the demo URL at build time:

```text
NEXT_PUBLIC_ARCHIVIST_URL=https://archivist.mcrombie.com
```

Set that value in Cromblog's existing hosting environment and rebuild Cromblog. Its featured
Archivist panel and Projects entry will then expose an **Open live demo** link. Without the
variable, the panel honestly links to the Archivist project record and says **Deployment ready**.

The production value is set in Vercel and the rebuilt Cromblog surfaces link to the canonical
address.

## Custom domain

The canonical public address is `https://archivist.mcrombie.com`. It is configured in three
places:

1. Render's Archivist service registers `archivist.mcrombie.com` as a custom domain and issues its
   TLS certificate.
2. Cloudflare DNS contains a **DNS-only** CNAME named `archivist` targeting
   `archivist-cradle-of-the-empire.onrender.com`.
3. Cromblog's Vercel Production environment sets
   `NEXT_PUBLIC_ARCHIVIST_URL=https://archivist.mcrombie.com`, followed by a production rebuild.

Keep Render's generated subdomain enabled. It provides a direct recovery address if the custom
DNS record is changed or temporarily unavailable. A custom-domain incident should not prompt a
manuscript upload, index rebuild, or application redeploy: first verify the Cloudflare CNAME,
Render's custom-domain verification and certificate status, and the Vercel environment variable.

## Public-payload frontend regression

Public responses intentionally omit private `run_diagnostics`, `resolved_query`, costs, and ledger
state. On July 28, 2026, the first live-answer test exposed a presentation-contract mismatch: the
public API correctly omitted `run_diagnostics`, but the frontend dereferenced it as a required
object and crashed to a blank page. Commit `1dd45aa` made the public-only fields optional in the
TypeScript response contract and guarded diagnostic reads. It also moved the stored-vibe
initializer into the bundled application so the public CSP no longer blocks it as inline script.

Treat both sides of this boundary as release checks:

- `tests/test_public_api.py` verifies that public question responses omit private diagnostics;
- `npm run build` type-checks the frontend against that optional public response shape.

Before promoting a frontend change, submit one live public question and confirm that the answer
renders even though no `run_diagnostics` object is returned.

## Progressive-response release check

The optional Progressive response uses a same-origin NDJSON `POST` at
`/api/projects/current/question/progressive`. It adds no provider call and never exposes raw tokens
or private reasoning. Essential may emit exact citation-rendered direct evidence as
`checked_claim` objects after the public edition-locator and rolling quotation checks pass.
Generated modes do not stream their model-authored prose as checked claims: local support-ID
validation is structural, not semantic-entailment proof. They show stages and heartbeats until the
complete authored answer or direct-evidence fallback is ready. Historical/manuscript turns in
every current mode make the shared query-embedding request; every registered generated mode --
Professional, Pretty Pink Princess, Baleful Black Baron, and Ruthless Red Realist -- adds the same
one no-retry authored-response call as Complete answer. A narrowly classified personal turn in any
registered generated mode instead makes one compact, no-retry character
call with no embedding, retrieval, manuscript, sources, or citations. Provider/refusal/validation
failure uses deterministic local character dialogue rather than Essential. Complete answer remains
the strict default.
The protocol and invariants are specified in
[Answer delivery modes](answer_delivery.md).

The public rate/concurrency slot belongs to the full stream lifetime, not merely to the time needed
to return response headers. It must be released exactly once after normal completion, terminal
failure, or disconnect cleanup. Once an accepted stream has begun, the server reports a late
failure in one safe terminal NDJSON frame; the client does not automatically replay the `POST`.

Before promoting this transport, run a live smoke through `https://archivist.mcrombie.com`:

1. Confirm Complete answer is still selected on a new browser session and an ordinary question
   retains the existing behavior.
2. Select Progressive response and submit an Essential question. Fixed operational progress must
   appear first, the elapsed-work indicator must continue updating on roughly three-second
   heartbeats, and at least one exact locally compiled evidence excerpt should appear before the
   terminal result when the evidence compiler emits one. Repeat in a generated mode and confirm no
   model-authored prose appears in a `checked_claim` frame.
3. In the browser network panel, confirm the progressive response is
   `application/x-ndjson` with schema `archivist.answer_stream/2`, monotonically sequenced frames,
   and exactly one terminal frame. It must contain no chain-of-thought, private diagnostics,
   unbounded source text, raw token delta, authored-response payload, or incomplete evidence card.
4. Confirm Essential working evidence is visibly marked not final, then is replaced—not
   duplicated—by the authoritative answer with citations and edition-qualified public sources.
5. Interrupt one accepted stream. Confirm there is no automatic retry and no partial answer is
   retained as a completed conversation turn.
6. While a public stream is held open, confirm a competing request is refused by the configured
   concurrency limit; after completion or disconnect cleanup, confirm a new request is admitted.
7. Repeat the Progressive question through Render's generated `onrender.com` address. If the
   direct address shows a claim earlier than `https://archivist.mcrombie.com`, investigate
   Cloudflare buffering rather than changing generation or retrieval.
8. Inspect the Render log for the single `progressive_delivery_timing` record. Compare the first
   checked claim and terminal/worker/stream milestones. The record must contain durations and
   milestone names only—never question, source, manuscript, prompt, answer, or error text.

This smoke checks deployment behavior that the offline suite cannot establish, including Render
proxy buffering and stream cleanup. It requires fresh authorization because current Essential
retrieval sends the question to the embedding provider and generated modes also send the dossier
to Sol. No such live smoke has run for `retrieval-authored-v3` or
`character-conversation-v2`; this runbook makes no latency,
quality, or model-performance claim.

## Production-performance cohort

The fixed resume-claim cohort specified in
[Production performance protocol](production_performance.md) completed on 2026-08-11 against
deployed wrapper commit `e71d9b79a60a894cb38451c37e0d43b7f9149fa9`. It attempted all 33
predeclared requests without retry or replacement: 29 were valid successful completions, four were
request failures (12.1212% of all attempts), and zero were instrumentation failures. Server
p50/p95 were 54.393/113.801 seconds across the 29 successes; client p50/p95 were
54.493/113.829 seconds. The run recorded 500,164 tokens, 80 priced and zero unpriced events, and
`$4.90594694` estimated API cost. The text-free
[public summary](evidence/production-performance-v1-2026-08-11/public-summary.json) has file
SHA-256 `dd13ad2cf60a863daf88e549106059a1d05126b40ffa3c66c3c8e18cb6246b7f`; its embedded canonical
artifact hash is `e2fcc051e66b115cf56abf7061fa93bfcd3c12297396cbdc3fad42b8bd1bfd30`.

The four failed requests were not infrastructure or budget denials. Planning and direct-answer
evidence selection succeeded, but structured generation failed closed: two
`missing_unit_requirement_id`, one `obligation_role_mismatch`, and one
`unsupported_requirement_has_unit`. Treat the 29/33 response-contract completion rate as a
product-reliability finding; repair it in a new release and never replay this sealed cohort.

Those results describe one observed warm production cohort, not an SLA, uptime study, load test,
or guarantee. The commands below preserve the workflow for audit and separately declared future
cohorts; they are not instructions to replay or replace any sealed attempt from the completed run.

After committing and deploying the instrumented release, use a clean local checkout at the exact
deployed commit to prepare the private manifest:

```powershell
$archivistProdRunId = "production-performance-YYYY-MM-DD-01"
$archivistProdRunRoot = "runtime/production-performance/$archivistProdRunId"
uv run python scripts/run_production_performance.py prepare `
  --run-root $archivistProdRunRoot `
  --run-id $archivistProdRunId `
  --base-url https://archivist.mcrombie.com
```

Transfer that private run root to `/var/data/runtime/production-performance/`. In Render Shell,
from the deployed source directory, run the paid phase only after the owner separately authorizes
the exact data scope and numeric cap:

```sh
ARCHIVIST_PROD_RUN_ID=production-performance-YYYY-MM-DD-01
uv run python scripts/run_production_performance.py run \
  --run-root "/var/data/runtime/production-performance/$ARCHIVIST_PROD_RUN_ID" \
  --usage-db /var/data/runtime/usage.sqlite3 \
  --authorize-production-performance \
  --max-cost-usd <owner-authorized-cap>
```

The run command verifies two ready `/api/health` observations, `/api/version`, the exact deployed
commit, and one unchanged process epoch before sending any question. It attempts exactly 33 fresh
Essential/Complete/RAG first turns, sequentially and at least 12 seconds apart, with no retry,
replacement, or paid warm-up. It also binds `/api/version`'s `public-rag-request-ceiling-v1`
identity and requires the full server-enforced `$2.00` maximum beneath the owner cap before each
next attempt. The server checks that maximum against the monthly budget before RAG, projects every
provider operation before send, and requires strict request-scoped usage.

For a newly prepared current-policy manifest, each successful Essential request must record exactly
one `query_embedding` event and no authored-response event. The manifest binds runtime identity
schema 4, `retrieval-authored-v3`, `hybrid_bm25_rrf`, and `text-embedding-3-small`. This is a future
cohort contract only; it does not reinterpret or alter the sealed production-performance-v1
manifest, identity, usage ledger, or report.

Before creating an intent or POSTing, the runner rejects any prepared conversation/turn scope that
already exists in the live ledger. A timeout or other ambiguous transport result is sealed without
replay, stops that invocation, and consumes the full `$2.00` maximum in conservative authorization
accounting before a later untouched ordinal may run. It is never reported as zero spend. A
successful response with zero recorded usage is an instrumentation failure and is excluded from the
latency denominator.

Generate the aggregate reports on Render without another provider call:

```sh
uv run python scripts/run_production_performance.py report \
  --run-root "/var/data/runtime/production-performance/$ARCHIVIST_PROD_RUN_ID" \
  --usage-db /var/data/runtime/usage.sqlite3
```

Only `public-summary.json` and `public-report.md` are publishable. They contain aggregate identity,
latency, outcome, token, and cost data but no H-item IDs or question text. Everything else in that
run root stays private and gitignored.

## Operational limits

- The persistent disk restricts Archivist to one Render service instance.
- The in-memory rate/concurrency gate is intentionally correct only for that one-instance design.
- The service is not directly internet-reachable behind Render's proxy; Uvicorn trusts that
  proxy's forwarded client address for per-reader rate limiting.
- The app's monthly OpenAI ceiling is enforced by a ledger stored under `/var/data/runtime/`.
- The public UI does not expose the ledger, model diagnostics, or budget bypass controls.
- The typeset page locators apply only to `Typeset PDF (July 6, 2026)`.
- Conversation history lasts for the open browser page and is not a durable account feature.
- Deployment does not make Archivist a general-purpose chatbot; it remains a conversation with
  one book.

If the Starter instance proves too memory-constrained, inspect the failure before changing its
instance type. An upgrade is a separate hosting-cost decision, not an automatic deployment step.
