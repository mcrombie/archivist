# Retrieval-authored-v4 evaluation runbook

**Status:** adapter implemented offline; no live/provider call or quality result exists

**Cohort:** `retrieval-authored-v4-professional-2026-08-13`

**Manifest schema:** `archivist.retrieval_authored_v4_cohort_manifest/1`
**Product commit:** `536acc818193f4963a2d31ed9e3acc20732e40d6`

This adapter creates a new private cohort for the committed post-timeout product. It never opens
or extends the terminal retrieval-authored-v3 timeout-diagnostic cohort. The locked 37-question
benchmark is reused and therefore remains descriptive rather than a pristine blind holdout.

The manifest binds product commit `536acc8` by its canonical 40-character commit identity and Git
blob identities, the clean harness commit, locked corpus and benchmark hashes, validated cached
query embeddings, the frozen G001-G010 text-anchor decomposition artifact, product deadlines, and
one exact cumulative cost cap. Preparing or reporting is provider-free. Every paid command requires
fresh, v4-specific owner authorization plus `--authorize-openai`; implementation alone is not
authorization.

The product under test keeps `gpt-5.6-sol`, low reasoning, medium verbosity, strict `/1` Pydantic
Structured Outputs, the 1,800-token output ceiling, one shared client, and no retries. Its public
wrapper shares a 35-second provider allowance, with embedding capped at eight seconds and
authoring at thirty. Because this evaluation reuses cached vectors, its generation phase measures
the direct 30-second authoring stage rather than the full public embedding-plus-authoring path.
Those are implementation boundaries, not measured latency or reliability claims.
Internal text-free product diagnostics distinguish `request_timeout`, `transport_failure`,
`provider_exception`, `refusal`, `structured_output_rejected`, and
`local_contract_validation_failed`; readers still see only the generic Essential-fallback notice.

H001-H010 are the first ten once-only Professional observations. They test mechanical readiness
first, but answer quality, success rate, latency, and cost are report-only and cannot suppress the
remaining 27. `generate-rest` begins with H011 and never calls the first ten again. Decomposition
begins only after all 37 generation dispositions are sealed and uses a 60-second evaluation-only
timeout with explicit latency. Rubric scoring begins only after all 37 decomposition dispositions.
The separate social suite then evaluates Professional, Pretty Pink Princess, Baleful Black Baron,
and Ruthless Red Realist across three personal-conversation prompts per mode.

Before every provider boundary, the adapter atomically seals the request hash and exact worst-case
projection, verifies the actual SDK kwargs against that projection, and seals a boundary marker.
There are no retries. A boundary with no usage event automatically receives an immutable
worst-case cost reserve. A process interruption after the boundary is settled provider-free and is
never replayed. Execution continues only while recorded spend plus all reserves plus the next exact
projection fits the sealed cap.

The first authorized sentinel sealed ten generated outcomes and ten priced events for
`$0.458209000`, with zero embedding calls. Its post-sentinel gate then found that the harness had
copied colon-delimited private ledger keys (`generation:H###`) into the trace's restricted
`scope.turn_id`. The remaining command stopped before H011. The outcomes may not be rewritten or
replayed. A clean descendant harness must run the provider-free reconciliation below once; it
binds every original outcome and trace hash to only the deterministic `generation-H###`
trace-scope normalization and proves H011 is untouched. Future generation outcomes normalize that
trace-only field before sealing.

Example commands, after replacing the cap with the separately authorized exact amount:

```powershell
.venv\Scripts\python.exe scripts\run_retrieval_authored_v4_evaluation.py preflight --product-commit 536acc818193f4963a2d31ed9e3acc20732e40d6 --max-total-cost-usd <authorized-cap>
.venv\Scripts\python.exe scripts\run_retrieval_authored_v4_evaluation.py prepare --product-commit 536acc818193f4963a2d31ed9e3acc20732e40d6 --max-total-cost-usd <authorized-cap>
.venv\Scripts\python.exe scripts\run_retrieval_authored_v4_evaluation.py sentinel --product-commit 536acc818193f4963a2d31ed9e3acc20732e40d6 --authorize-openai --max-total-cost-usd <authorized-cap>
.venv\Scripts\python.exe scripts\run_retrieval_authored_v4_evaluation.py reconcile-trace-scope --product-commit 536acc818193f4963a2d31ed9e3acc20732e40d6 --max-total-cost-usd <authorized-cap>
.venv\Scripts\python.exe scripts\run_retrieval_authored_v4_evaluation.py generate-rest --product-commit 536acc818193f4963a2d31ed9e3acc20732e40d6 --authorize-openai --max-total-cost-usd <authorized-cap>
.venv\Scripts\python.exe scripts\run_retrieval_authored_v4_evaluation.py decompose --product-commit 536acc818193f4963a2d31ed9e3acc20732e40d6 --authorize-openai --max-total-cost-usd <authorized-cap>
.venv\Scripts\python.exe scripts\run_retrieval_authored_v4_evaluation.py rubric --product-commit 536acc818193f4963a2d31ed9e3acc20732e40d6 --authorize-openai --max-total-cost-usd <authorized-cap>
.venv\Scripts\python.exe scripts\run_retrieval_authored_v4_evaluation.py social --product-commit 536acc818193f4963a2d31ed9e3acc20732e40d6 --authorize-openai --max-total-cost-usd <authorized-cap>
.venv\Scripts\python.exe scripts\run_retrieval_authored_v4_evaluation.py report --product-commit 536acc818193f4963a2d31ed9e3acc20732e40d6 --max-total-cost-usd <authorized-cap>
```

The report command refuses to seal early: it requires all 37 generation, decomposition, and rubric
dispositions and all 12 social outcomes. Its committed-safe shape contains only hashes, counts,
rates, status categories, retrieval/citation/coverage metrics, cost, and latency—not question,
answer, manuscript, or excerpt text. Semantic rubric results remain explicitly exploratory and
uncalibrated.
# Cost-ceiling resumption note

The rubric phase initially stopped before H036's provider boundary because the
harness supplied remaining headroom as a cumulative request ceiling, thereby
double-counting recorded spend. H036 contains an intent but no boundary marker,
outcome, usage event, or provider attempt. The repaired scope supplies the
effective cohort ceiling (owner cap less ambiguity reservations); the ledger
and exact request projection still enforce the actual remaining balance. A
clean descendant commit may therefore resume at H036 without retrying any
provider operation.
