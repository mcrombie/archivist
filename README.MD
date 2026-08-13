# Archivist

Archivist is a source-grounded conversational interface for one book: *Cradle of the Empire: A
Big History of Virginia*. It searches the complete substantive manuscript, answers with inline
`[Source N]` citations, and carries context across follow-up questions.

Public demo: [https://archivist.mcrombie.com](https://archivist.mcrombie.com)

The source tree described below implements `retrieval-authored-v3`. Production deploys are manual;
the live service must report runtime identity schema 4 before it can be described as running this
policy. That live parity has not yet been verified.

Archivist is not a manuscript-upload service, a general-purpose chatbot, or an unrestricted source
browser. The public application never exposes its private manuscript, vector store, full retrieved
chunks, internal traces, or arbitrary file paths.

## Current product

The built-in RAG product now defaults to `retrieval-authored-v3` over **481
retrieval-eligible chunks**. Archivist resolves high-confidence ordinary follow-ups locally, makes
one `text-embedding-3-small` query-embedding request, and uses the shared dense/BM25
reciprocal-rank-fusion retriever and context finalizer. It packages four to eight evidence units,
targeting about 2,500 estimated evidence tokens with a hard 4,500-token evidence ceiling. Whole
chunks are preferred; only complete paragraph ranges may be used when the hard ceiling requires
shortening. The chunks cover the Introduction, geological formation, Prologue,
Chapters 1–20, Epilogue, Afterword, and Appendices A–D. Front matter, the table of contents,
acknowledgments, illustration notes, bibliography, printed index, and credits are excluded from
retrieval.

The reader experience includes:

- a one-page, multi-turn conversation with contextual follow-up resolution;
- local follow-up resolution, hybrid dense/BM25 retrieval, rich evidence-dossier compilation, and
  inline source citations;
- **5 reader-selectable modes**: Professional, Essential, Pretty Pink Princess, Baleful Black
  Baron, and Ruthless Red Realist;
- **5 mode-linked visual appearances**; dormant appearance assets are hidden compatibility data;
- Professional as the new-visitor default and Essential as the neutral evidence-first baseline for
  API, CLI, and evaluation callers that omit a mode;
- **Complete answer** as the fail-closed default delivery mode;
- **Progressive response** as an experimental advanced setting that may reveal locally checked,
  cited evidence from the same request before the canonical answer finishes validation;
- typeset-PDF page locators and tightly bounded excerpts in the public demo; and
- local cost estimates and budget controls for development.

In current RAG, Essential returns direct cited manuscript evidence and makes **no
prose-generation call**. It is not providerless: the shared hybrid search still makes one query-
embedding request. Every registered generated mode -- currently Professional, Pretty Pink Princess,
Baleful Black Baron, and Ruthless Red Realist -- adds exactly one
no-retry `gpt-5.6-sol` authored-response call with low reasoning, medium verbosity, and a 1,800
output-token ceiling. The model receives the question, locally resolved turn, and rich dossier; it
may freely synthesize, paraphrase, choose useful length, and write in the selected character.
Generated modes end with one to three in-character follow-up questions. A provider failure or
refusal, or a structurally invalid authored response, falls back to direct Essential evidence
without retry. The browser keeps that cited evidence usable but displays a visible, nonfatal notice
headed **Essential fallback**: “Archivist could not complete the {Mode label} AI response, so it
returned Essential's direct manuscript evidence instead.” A valid Princess in-character refusal
remains a generated answer.

Advanced lens, voice, and worldview settings guide framing and prose in generated modes. They do
not apply to Essential and never change retrieval or the underlying dossier. Historical mode
definitions and assets remain only so stored and server compatibility data continue to resolve;
they are not selectable through the current UI or API.

Every registered generated mode also recognizes a deliberately narrow set of direct social and
personal questions such as “How are you?” before retrieval begins. This includes Professional,
Pretty Pink Princess, Baleful Black Baron, and Ruthless Red Realist now and automatically includes
future modes when they register generated-mode instructions. Essential remains outside the route.
A matching turn uses `character-conversation-v2`: exactly one no-retry `gpt-5.6-sol` call with low reasoning, low
verbosity, a 12-second timeout, and at most 576 output tokens. It sends only the question and selected-character
instructions—not an embedding, manuscript passage, retrieval result, dossier, or conversation
history. The reply is fictional character conversation, carries no citations or historical facts,
and ends with one to three in-character questions that explicitly lead back to the manuscript or
*Cradle of the Empire*. Invalid output, refusal, or provider failure returns a deterministic local
reply in the same character instead of unrelated Essential evidence. Essential, historical
questions, manuscript questions, and mixed social-plus-historical questions continue through
their normal grounded path; this is not a general-purpose chatbot route.

The v3 authored-response policy retains input/output schemas
`archivist.authored_response_input/1` and `archivist.retrieval_authored_answer/1` plus renderer
`retrieval-authored-renderer-v1`. Character conversation likewise retains schemas
`archivist.character_conversation_input/1` and `archivist.character_conversation_answer/1` plus
renderer `character-conversation-renderer-v1`; its v2 policy name records registry-generalized
routing rather than a changed wire shape.

Ruthless Red Realist uses the existing Ember & Ink appearance and the wire ID `ember_and_ink`.
It reads history through power, leverage, incentives, bargaining positions, credible commitments,
tradeoffs, institutional capacity, and statecraft. Its high-level realist inspiration is loosely
associated with Machiavelli and Henry Kissinger, but no outside work was ingested and the mode may
not impersonate, imitate, quote, or attribute claims to either person. Historical claims still
come only from Archivist's retrieved manuscript dossier.

The composer explains the active **Perspective** above the text field. Its collapsed control is
labeled **Settings**. Changing any advanced facet or appearance makes the active top and Settings
labels exactly **Custom**. The perspective explanation still names the underlying preset because
its character/influence remains active. An appearance-only override explicitly says the underlying
perspective is unchanged. Completed-turn badges retain the preset plus Custom so their provenance
remains legible.

Progressive response is not chain-of-thought and does not make a second answer-model call. It may
show locally compiled direct evidence in Essential, but generated prose remains terminal because
support-ID validation is not semantic-entailment proof. Stages and heartbeats keep the generated
request legible while the one authored-response call runs. Any provisional evidence is discarded
if the final response fails validation. Complete answer remains the reference behavior.

An experimental `full-context-v2` strategy also exists behind server-side feature flags and
remains disabled on the public deployment. Because Full Context is generative, API requests that
combine it with Essential are rejected. Frozen `evidence-planned-v26` remains immutable and
callable only when a developer explicitly requests that policy. The unpromoted V27 compact policy
is retained as a historical development experiment. Its old reader-facing selector has been
removed; neither V26 nor V27 is the current product default.

## Architecture

```text
private DOCX and typeset PDF
        |
        v
deterministic preparation, manifest, and edition locators
        |
        v
private Chroma index (481 eligible text-embedding-3-small vectors)
        |
        v
local high-confidence follow-up resolution
        |
        +--> narrow social turn in any registered generated mode: no retrieval or manuscript evidence
        |        one compact no-retry gpt-5.6-sol character call (12-second timeout)
        |        deterministic in-character local fallback on failure
        |        manuscript-leading questions, no citations or historical claims
        |
        v
one text-embedding-3-small query call + dense/BM25 reciprocal-rank fusion
        |
        v
4-8 source-bound dossier units (~2,500 target / 4,500 hard evidence tokens)
        |
        +--> Essential RAG: direct cited evidence, no prose-generation call
        |
        `--> four generated modes: one no-retry gpt-5.6-sol call
                     authors free prose + 1-3 follow-up questions
                     grounded runs name opaque dossier-unit IDs
                     (failure falls back to direct evidence)
        |
        v
local support-ID -> [Source N] mapping + public exposure validation
        |
        +--> development: private diagnostics and full source inspection
        |
        `--> public_demo: page locators and bounded excerpts only
        |
        v
FastAPI service + React/Vite conversation interface
```

Only the four generated-prose modes use `gpt-5.6-sol`, with low reasoning, medium verbosity, and
an explicit output ceiling. Follow-up resolution, BM25/RRF fusion, dossier compilation, Essential
rendering, and citation mapping are local; dense retrieval requires the one embedding request.
Local support-ID validation proves that cited dossier units exist, but it does not prove semantic
entailment or faithfulness. For formal evaluation, Archivist prefers immutable dated snapshots, but
OpenAI's current catalog exposes only the canonical current-snapshot IDs `gpt-5.6-sol` and
`gpt-5.6-terra`, not dated variants. The first answer-quality cohort therefore binds the committed
provider-catalog observation, exact requested and provider-returned IDs, role-specific settings,
and response IDs, while disclosing that provider-side weights may change behind those names. The
generator and judge use different predeclared identifiers; Archivist never manufactures a dated
snapshot name.

## Local quickstart

Requirements:

- Python 3.13;
- Node.js and npm;
- `uv`;
- an OpenAI API key for current RAG retrieval and the four generated-prose modes; and
- the private runtime corpus already present under `output/` and `chroma_db/`.

Install dependencies and build the frontend:

```powershell
uv sync --frozen
Set-Location frontend
npm ci
npm run build
Set-Location ..
```

Create `.env` in the repository root:

```text
OPENAI_API_KEY=your_project_scoped_key
```

Run the development application:

```powershell
uv run uvicorn web_api:app --app-dir src --reload
```

Open `http://127.0.0.1:8000`. Development mode exposes private diagnostic tools and must not be
published to the internet.

### Explicit legacy development policies

Omitting `rag_policy_version` uses `retrieval-authored-v3`. The superseded
`retrieval-authored-v1` and `retrieval-authored-v2` candidates remain historical/manual evidence
rather than selectable API policies. A local development API caller may still explicitly request `evidence-planned-v26` or
`evidence-planned-v27` for compatibility and
historical investigation. The browser no longer exposes that selector, and the public request
contract accepts neither field. V26 remains the immutable evaluated candidate; V27 compact was
never promoted. See [`docs/latency_optimization.md`](docs/latency_optimization.md).

To exercise the hardened public profile locally:

```powershell
$env:ARCHIVIST_EXPOSURE_PROFILE = "public_demo"
$env:ARCHIVIST_PUBLIC_MONTHLY_BUDGET_USD = "10.00"
uv run uvicorn web_api:app --app-dir src
```

## Private data and deployment

The repository ignores the manuscript, typeset PDF, extracted chunks, Chroma database, runtime
bundles, usage databases, API keys, and generated frontend build. Committed fixtures identify the
corpus and edition mapping by stable IDs and hashes rather than by reproducing book text.

The public service searches the same 481-chunk substantive corpus privately. Its startup-selected
`public_demo` profile removes upload, project, indexing, diagnostic, cost-management, and full-source
routes; sanitizes errors; disables API documentation; fixes retrieval depth server-side; limits
request size, rate, concurrency, and monthly spend; and serves only edition-qualified locations and
short excerpts. Page numbers currently refer specifically to **Typeset PDF (July 6, 2026)**.

Build the gitignored deployment bundle only when preparing or refreshing the Render disk:

```powershell
uv run python scripts/build_public_runtime_bundle.py
```

Rebuild the committed, text-free edition locator only from the authorized private PDF:

```powershell
uv run python scripts/build_edition_locators.py `
  "C:\path\to\Cradle_of_the_Empire_FINAL_PDF_revised_0706.pdf"
```

Render hosts the FastAPI service and private runtime disk. `archivist.mcrombie.com` is the canonical
reader URL; the generated `onrender.com` address remains an operational fallback. Deployment,
recovery, environment variables, and smoke checks are documented in
[`docs/public_deployment.md`](docs/public_deployment.md).

### Production observability and performance status

Archivist now has a privacy-safe production-measurement path: one random request identifier
correlates a public request with its text-free server record; successful answer runs retain
pipeline-stage timings, returned token usage, and estimated API cost; and safe failure records keep
the HTTP outcome without storing the question, answer, manuscript passage, prompt, or source text.
The current source version endpoint reports `archivist.public_runtime_identity/4`, binding a
running process to Render's `RENDER_GIT_COMMIT`, `retrieval-authored-v3`, hybrid BM25/RRF retrieval,
`text-embedding-3-small`, the generated-prose model, the corpus manifest, the frozen V26 candidate
identity, and the versioned public request-cost contract. On Render, its automatic commit identity
is authoritative. Manual deployment and live identity parity for this redesign remain unverified.
Current generated turns share a 25-second provider deadline across retrieval and authoring: the
embedding operation receives at most eight seconds and the single prose call receives at most
twenty seconds of the remaining allowance. This is a fail-fast implementation boundary, not a
measured latency claim or an SLA.

The predeclared production cohort is now **complete** against deployed wrapper commit
`e71d9b79a60a894cb38451c37e0d43b7f9149fa9`. It attempted exactly 33 answerable held-out items with
no retry or replacement. Twenty-nine were valid successful completions and four were request
failures, for an all-attempt error rate of 12.1212%; there were zero instrumentation failures.
Across the 29 successful completions, end-to-end server latency was 54.393 seconds at p50 and
113.801 seconds at nearest-rank p95. Client-observed latency was 54.493 seconds at p50 and 113.829
seconds at p95. The cohort recorded 500,164 tokens across 80 priced and zero unpriced events, with
estimated API cost of `$4.90594694`.

The four failures were fail-closed generation-contract rejections after successful planning and
evidence selection: two `missing_unit_requirement_id` cases, one `obligation_role_mismatch`, and
one `unsupported_requirement_has_unit`. They were not budget, transport, deployment, or telemetry
failures. This preserves a strong observability result while exposing an 87.9% public
response-contract completion rate that should be improved in a separately versioned release.

Each measured request was a fresh, sequential Essential/Complete/RAG first turn with empty history,
and request starts remained at least 12 seconds apart so the cohort did not accidentally exercise
the configured per-client rate limit. Warm status was established by readiness and process-identity
checks rather than by making an unmeasured paid request. Server latency ran from request ingress
through construction of the complete response. The
[public summary](docs/evidence/production-performance-v1-2026-08-11/public-summary.json) and
[readable report](docs/evidence/production-performance-v1-2026-08-11/public-report.md) are
text-free. The summary file SHA-256 is
`dd13ad2cf60a863daf88e549106059a1d05126b40ffa3c66c3c8e18cb6246b7f`; its embedded canonical
artifact hash is `e2fcc051e66b115cf56abf7061fa93bfcd3c12297396cbdc3fad42b8bd1bfd30`.
These numbers describe one observed warm production cohort, not an SLA, uptime study, load test,
or latency guarantee. This sealed production-performance v1 cohort exercised frozen V26 before
either later product policy. Its identities, results, and interpretation are unchanged. The narrow
Edwin Sandys smoke subsequently exercised the superseded `application-compiled-v1` cue selector:
three no-retry calls passed in 8.357, 6.839, and 5.162 seconds for `$0.060071250`. It does not
measure `retrieval-authored-v1`, `retrieval-authored-v2`, or `retrieval-authored-v3`. No paid or live test has run for the
current policy, so there is no
current latency, quality, or reliability improvement claim.

Provider-using public Complete-RAG paths retain a server-owned, versioned **$2.00 per-request
maximum**. The service checks that maximum against the monthly budget, projects each provider
operation before sending it, and requires strict usage accounting. Current Essential RAG makes one
query-embedding request and is therefore subject to provider usage, budget, and request-cost
controls even though it makes no prose-generation call. A future current-policy Essential cohort
expects exactly that embedding event. Historical production-performance v1 retains its original
deployed ceiling and accounting contract. An ambiguous provider transport outcome is never
replayed or treated as free: it consumes the full maximum in conservative authorization accounting,
and exact cohort spend remains unavailable unless every attempt has request-scoped usage. Existing
conversation/turn scopes are rejected before a cohort POST so stale production records cannot be
reused as measurements.

The source configuration temporarily raised the application budget to `$10.00` for the separately
authorized 2026-08-11 cohort and returned it to `$5.00` after the run. On 2026-08-12, the owner
separately raised the ordinary public-demo ceiling to `$10.00`. That change does not erase this
calendar month's recorded spend or alter the server-owned `$2.00` per-request maximum. Because
production deploys are manual, the live Render value must be checked against the source setting.
The complete protocol, artifact boundary, and exact resume wording are in
[`docs/production_performance.md`](docs/production_performance.md).

## Verification

Run the offline backend checks:

```powershell
uv run ruff check src tests scripts
uv run pytest
```

Run the focused frontend suites and production build:

```powershell
Set-Location frontend
npm run test:delivery
npm run test:modes
npm run build
```

**Verification snapshot — August 13, 2026:** repository-wide Ruff passed; **1,298 Python tests passed
and 1 was intentionally skipped**; both focused frontend suites passed; and the production frontend
built successfully. These checks are offline and make no paid OpenAI calls. Live deployment behavior
still requires the release smoke checks in the deployment runbook.

## Evaluation status

The familiar ten-question cohort is a development regression set, not held-out evidence. On
August 7, 2026, the owner formally locked 37 retained held-out questions spanning all six
contracted strata; H020, H039, and H040 are intentionally absent. `fixtures/gold_set.json` and its
version-4 provenance sidecar bind the exact owner-field commitment, final gold bytes, frozen V26
candidate, corpus manifest, and development registry. Historical Claude drafting is disclosed
retrospectively without claiming a prospectively blinded or complete raw-draft record. Schema,
composition, locations, development-overlap, privacy, provenance, and frozen-candidate checks all
pass.

The first held-out measurement is now complete: a retrieval-only dense-versus-hybrid diagnostic
against the untouched frozen candidate. It used one cached query embedding per item, invoked no
planner, answer model, generator, or judge, and wrote no question or manuscript text to its result.
Of the 37 items, 33 answerable items contribute to recall; the four out-of-corpus items are excluded
from that denominator by contract.

| Retrieval arm | Macro Recall@5 | Hit@5 | Context recall | Essential coverage in context |
|---|---:|---:|---:|---:|
| Dense | 24.71% | 90.91% | 31.96% | 44.98% |
| Hybrid BM25/dense RRF | 25.97% | 93.94% | 33.74% | 47.22% |

The predeclared primary delta is **+1.26 percentage points** for hybrid retrieval. Five fixed-subset
repetitions were deterministic, but the effect is mixed rather than universal: hybrid improved the
focused-biographical stratum while regressing on conceptual questions. This is retrieval evidence,
not an answer-quality result and not permission to tune V26 before the complete held-out baseline.

The offline preflight is safe to run without an API key:

```powershell
uv run python scripts/run_retrieval_benchmark.py preflight
```

The completed run used separately recorded owner authorization because a missing cache sent exactly
the 37 locked question strings—not the gold annotations or manuscript—to OpenAI's
`text-embedding-3-small` endpoint in one request. Automatic retries were disabled. The operation
used 521 tokens and recorded an estimated cost of **$0.00001042**. The command-line acknowledgement
remains a safety interlock for any deliberate cache rebuild, not a substitute for authorization:

```powershell
uv run python scripts/run_retrieval_benchmark.py run `
  --authorize-openai-query-embeddings `
  --max-cost-usd 0.01
```

The private, gitignored embedding cache is reused by both arms, every value of `k`, and the five
retrieval repetitions; later offline reproductions do not make another API call. The complete
answer-quality cohort is also complete. Recovery-04 preserves all 37 frozen V26 answer artifacts:
35 completed/released answers and two generation-side technical-error artifacts. Canonical
decomposition made exactly 37 one-attempt-only Terra calls, with ten usable decompositions and 27
technical measurement failures—26 `exact_span_mismatch` and H029's one `incomplete_response`. No
answer or decomposition attempt was retried or repaired. The 27 failures belong to the Terra
measurement instrument; they do **not** mean V26 failed 27 answers. The baseline reports every
immediately computable result and leaves semantic fields explicitly pending where calibrated
judgment is still required.

The answer-evaluation preflight is offline and makes no provider call:

```powershell
uv run python scripts/run_answer_evaluation.py preflight
```

The owner authorized the complete frozen cohort up to a cumulative `$20.00`. A fresh run uses this
single paid entry point:

```powershell
uv run python scripts/run_answer_evaluation.py run-37 `
  --authorize-openai-full-evaluation `
  --max-cost-usd 20
```

The command-line acknowledgement is a safety interlock, not authorization by itself. It runs all
37 answers first, makes exactly one canonical answer-only decomposition attempt per answer, and
then writes the sealed private binding plus the closed, text-free mechanical JSON and Markdown
reports. It performs no calibration repeats or semantic-judge calls.

The first authorized execution stopped fail-closed at H003. H001 and H002 were sealed; H003 made
exactly one embedding call and reached a trace-backed deterministic `clean_abstention` before
answer generation. No retry and no H003 answer-generation call occurred. The exact offline
migration below preserved those results, and the resumed run then sealed all 37 V26 answers. The
abstention remains evaluation behavior—likely a false abstention—not an item repaired or rerun.

Recovery is deliberately offline and non-destructive. After committing and verifying the harness
correction, leave the original partial root
`runtime/evaluations/v26-held-out-answer-quality-2026-08-07` untouched and create its audited
sibling:

```powershell
uv run python scripts/run_answer_evaluation.py recover-interrupted
```

That command makes no provider call. It preserves the H001/H002 inner generated-item payloads
unchanged, explicitly reconstructs H003 from its exact sealed trace and existing usage ledger, and
binds the source and sibling roots in `migration-audit.json`. Resume only the missing operations:

```powershell
uv run python scripts/run_answer_evaluation.py run-37 `
  --run-root runtime/evaluations/v26-held-out-answer-quality-2026-08-07-harness-recovery-01 `
  --authorize-openai-full-evaluation `
  --max-cost-usd 20
```

The cumulative cap includes the already recorded calls. The final private/public artifacts bind
the migration hash and identify H003 as trace-recovered. Because its full-turn duration cannot be
reconstructed, generation latency is reported over **36 of 37** items rather than imputed; the
public report carries that limitation. “Uninterrupted” forbids calibration or changes to V26,
prompts, models, retrieval, corpus, gold, or UI—not exact provider-free recovery after a harness
stop.

Canonical decomposition then stopped fail-closed on each of its first two items. The H001 and H002
Terra responses each completed and were charged exactly once, but returned claim strings that did
not exactly equal the answer substrings declared by their character spans. The existing responses
were retrieved afterward by provider response ID through `responses.retrieve`, which made no model
call, and preserved in private snapshots with SHA-256
`dd6ca585e3d1f8fac6af4070187b0230115ded0482837c23b4f12beda82c1f1e` (H001) and
`5dc006d3de7f2ae64f4aea1db76907c0cbda2f9b60ee060ffb3edac1eff42c0d` (H002). The harness did not
correct either result, retry either item, or promote an invalid canonical decomposition.
Recovery-02 contains 90 provider events and cumulative recorded spend of **`$5.46195397`**.

Recovery-02 remains immutable. The completed provider-free migration created recovery-03 with the
historical command below after the generalized no-retry harness was committed:

```powershell
uv run python scripts/run_answer_evaluation.py recover-decomposition-failure `
  --source-run-root runtime/evaluations/v26-held-out-answer-quality-2026-08-07-harness-recovery-02
```

That migration binds all 37 answer checkpoints, the complete existing ledger, both response
snapshots and validation failures, and the source and destination runner identities. It made no
provider call. The resumed run skipped H001 and H002 and made exactly one Terra call for each
previously untouched item until H029 returned terminal status `incomplete`:

```powershell
uv run python scripts/run_answer_evaluation.py run-37 `
  --run-root runtime/evaluations/v26-held-out-answer-quality-2026-08-07-harness-recovery-03 `
  --authorize-openai-full-evaluation `
  --max-cost-usd 20
```

A completed parseable result that fails one of the four predeclared local claim-ID/span invariants
is sealed immediately as a technical measurement failure and is never corrected or retried; the
run continues to the next untouched item. An exact provider status of `incomplete` is likewise
sealed as a technical measurement failure and may continue after its one attempt is durably bound.
An unknown status, provider or network failure, returned-model mismatch, missing parse, or
unavailable citation number still stops fail-closed. The completed baseline reports **all 37 answer
artifacts and exactly 37 canonical decomposition attempts: ten usable decompositions and 27
technical failures**. Failures are excluded only from decomposition-dependent denominators and are
never imputed as empty claim sets or scored as candidate answer failures. This recovery repaired
the measurement harness's representation, not the frozen answers.

Recovery-03 made exactly one `gpt-5.6-terra` call for H029 before stopping on provider status
`incomplete`. Response `resp_04c5799aa1b46c76006a78a779f5e8819f84b2edbf39a416c5` contained no
output and recorded 923 input tokens, 8,000 output tokens—all 8,000 reasoning tokens—and 8,923 total
tokens, costing `$0.1223075`. The existing response was retrieved afterward by exact ID without a
model call and preserved at
`runtime/evaluations/v26-held-out-answer-quality-2026-08-07-h029-decomposition-response.json`, with
SHA-256 `84503bc1cd861bafc09cb33bbe32f581ee56a63ed15c66e8d5ccb7562d1d8617`. It was not retried,
parsed from nonexistent output, or attributed to the candidate answer. Recovery-03 is now immutable
at 116 priced provider events, `$6.80227647` cumulative recorded spend, and zero unpriced events.

Recovery-04 was created from recovery-03 with the exact provider-free command below. The migration
sealed H029 as technical `incomplete_response`, preserved all 37 answers and the 27 earlier
decomposition outcomes, and changed no candidate, prompt, gold, or provider evidence:

```powershell
uv run python scripts/run_answer_evaluation.py recover-decomposition-failure `
  --source-run-root runtime/evaluations/v26-held-out-answer-quality-2026-08-07-harness-recovery-03 `
  --run-root runtime/evaluations/v26-held-out-answer-quality-2026-08-07-harness-recovery-04
```

The final resume called only the nine untouched items, H030–H038, against recovery-04 under the
original cumulative cap:

```powershell
uv run python scripts/run_answer_evaluation.py run-37 `
  --run-root runtime/evaluations/v26-held-out-answer-quality-2026-08-07-harness-recovery-04 `
  --authorize-openai-full-evaluation `
  --max-cost-usd 20
```

The resulting report covers 198 sources, 251 citation references, and 41 claims from ten
schema-valid decompositions. Two of those ten are zero-claim records attached to the two generation-
error artifacts, so the 41 claim-derived observations cover eight substantive releases:

| Mechanical metric | Result |
|---|---:|
| Citation resolvability | 251/251 (1.000) |
| Malformed citation rate | 0/250 (0.000) |
| Citation completeness | 34/41 (0.829) |
| Cited-source gold-location match | 23/34 (0.676) |
| Gold-location retrieval coverage | 75/428 (0.175) |

Answer-level citation syntax metrics retain all applicable answer/citation observations;
claim- and decomposition-dependent metrics use only the eight substantively decomposed releases.
The high 27/37 decomposition-instrument failure rate therefore sharply limits interpretation of the latter. The
generation pipeline has 36 exact latency observations in its 37-item scope because of the disclosed
H003 recovery: 1,817.196 seconds total, 50.478-second mean, 47.928-second p50, 91.695-second p95,
and 108.685-second maximum. The closed ledger contains 125 priced events, zero unpriced events, and
**`$7.02298147`** total estimated API cost, safely below the authorized `$20.00` cap.

Those are held-out **evaluation generation-pipeline** timings, not production HTTP/server latency.
They do not fill the production-performance resume claim.

The text-free public report and summary are
`runtime/evaluations/v26-held-out-answer-quality-2026-08-07-harness-recovery-04/precalibration-public-report.md`
and `precalibration-public-summary.json`. Their summary SHA-256 is
`eaa6d33460c0c616467e9cd9cb043c762e16c5e6a6654cfe2eebd3360655dc7a`; the bound private,
generation, decomposition, and migration artifact hashes are respectively
`6d3fe51abcc3167e69b8e58fa46bceefeb29cf5c8ae9666c575f12757fe1312a`,
`61a58409b18025487d04f68ef2057005e757a91eb32223e71455e97cd4f13083`,
`1d7c759821e8a71fad70886878be06cb81b731f320a9cc30bf5d6f51b3d77d7b`, and
`41b5f8f5ca98753ee3297a4dc9a9285d51ddcaf9cec4adc1f8067245c444f8a8`.
The sealed run identity records harness commit
`c7cd58bcdc0963e13b4626854cdfc3e786be5b72`; exact replay validation should use that producing
commit in a detached worktree rather than the later documentation-only head.

This is a complete **descriptive baseline**, not yet a full semantic answer-quality scorecard.
Faithfulness, abstention, gold-claim recall, and related semantic measures remain pending by design.
The current product replaces the briefly shipped closed cue selector with
`retrieval-authored-v3`, while keeping `retrieval-authored-v1`, `retrieval-authored-v2`, frozen V26, the superseded selector
smoke, and all completed
measurements unchanged. The new default has not had a paid latency or quality cohort, so no speed,
quality, or reliability improvement is claimed. The next measurement-instrument work is still to diagnose and redesign canonical
decomposition without changing or rerunning the held-out baseline; an optional
calibration/semantic supplement remains lower priority.

## Documentation map

- [`B0_project_brief.md`](B0_project_brief.md) — product scope and non-negotiable constraints.
- [`ROADMAP.md`](ROADMAP.md) — current phase, remaining work, and release evidence.
- [`EVAL_CONTRACT.md`](EVAL_CONTRACT.md) — formal measurement and held-out governance contract.
- [`docs/project_notes.md`](docs/project_notes.md) — canonical corpus, model, index, and UI state.
- [`docs/rag_next_optimization_design.md`](docs/rag_next_optimization_design.md) — V26 RAG design
  lineage and contracts.
- [`docs/full_context_answer_strategy_design.md`](docs/full_context_answer_strategy_design.md) —
  disabled full-context experiment.
- [`docs/answer_delivery.md`](docs/answer_delivery.md) — Complete and Progressive delivery rules.
- [`docs/latency_optimization.md`](docs/latency_optimization.md) — historical, unpromoted V27
  compact-response experiment and its superseded promotion protocol.
- [`docs/public_demo_design.md`](docs/public_demo_design.md) — public exposure and citation design.
- [`docs/public_deployment.md`](docs/public_deployment.md) — Render deployment and recovery runbook.
- [`docs/production_performance.md`](docs/production_performance.md) — protocol and interpretation
  for the completed privacy-safe production cohort; the publishable
  [report](docs/evidence/production-performance-v1-2026-08-11/public-report.md) and
  [JSON summary](docs/evidence/production-performance-v1-2026-08-11/public-summary.json) are
  preserved alongside it.
- [`docs/gold_set_authoring.md`](docs/gold_set_authoring.md) — private held-out authoring workflow.
- [`docs/cost_tracking.md`](docs/cost_tracking.md) — local estimates, budgets, and billing caveats.
- [`BLOGNOTES.md`](BLOGNOTES.md) and [`DEFECTS.md`](DEFECTS.md) — development narrative and defect
  history.

## Author

Michael Crombie  
B.S. Computer Science & History, William & Mary
