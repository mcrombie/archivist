# Latency optimization: compact provider contract

Status: **historical experiment; unpromoted and superseded by `application-compiled-v1`**
Date opened: **2026-08-12**

## Current disposition — 2026-08-12

V27 compact completed its offline representation gate but never received the paid comparison below
and was never promoted. The current built-in RAG default is now `application-compiled-v1`: local
follow-up resolution and planning, deterministic BM25 ranking, and at most three immutable bounded
evidence cards. Essential returns those cards directly with application-owned citations and zero
provider calls in current RAG; Essential plus Full Context is rejected. Professional, Pretty Pink
Princess, and Baleful Black Baron each use exactly one no-retry low-reasoning `gpt-5.6-sol`
selection call over card IDs/text. The model chooses only card order and typed mode-bound cue IDs;
local code owns every displayed word and citation, with direct-evidence fallback.

The former V26/V27 browser selector has been removed. Both policies remain callable only through an
explicit local development `rag_policy_version` for compatibility and historical investigation;
omitting that field selects `application-compiled-v1`, and the public API does not accept it. Frozen
V26 remains immutable. Production-performance v1 remains unchanged. After exact payload/provider
authorization, a bounded Edwin Sandys smoke made one no-retry call in each generated mode. All three
passed the closed cue contract in 8.357, 6.839, and 5.162 seconds; the isolated ledger records 6,292
tokens, three priced events, zero unpriced events, and `$0.060071250` estimated cost. This is a
single-question compatibility smoke, not a latency cohort, so this document supports no general
claim that the new path is faster or more reliable.

The remainder of this document preserves the V27 hypothesis, offline measurements, and proposed
protocol as historical design evidence. Its promotion instructions are no longer the active product
roadmap.

The original brief tested one narrow hypothesis: Archivist might spend less time in answer generation if the
model emits only the irreducible structured answer data and deterministic local code reconstructs
the redundant relationship ledgers required by the existing release validator. This is a
**universal provider contract for every eligible generated answer**, not a query-routed fast path
or a shortcut reserved for easy questions. It is a representation change, not permission to
weaken answer semantics, retrieval, or validation.

The experiment made **zero paid calls**: no provider call, live smoke, deployment, or paid
comparison ran. V27 remained unpromoted and was later superseded.

## Preserved baselines

Two completed records stay immutable:

- frozen V26 (`evidence-planned-v26`) and its completed 37-item descriptive evaluation; and
- production-performance v1: 33 attempts, 29 valid completions, four request failures, zero
  instrumentation failures, and observed server p50/p95 of 54.393/113.801 seconds.

This candidate does not repair, replace, or rerun either record. A prompt or provider-schema
change opens a new system cohort under `EVAL_CONTRACT.md` section 1.3; it does not change a metric
definition and therefore does not require a contract edit. The production v1 report remains the
historical baseline even if a later candidate performs better.

## The one variable being changed

The V26 generator examined by this experiment was asked to emit answer units plus relationship ledgers that repeat facts
already implied by those units and by the trusted request context. Producing and cross-checking
that redundant structure costs output tokens. The production cohort also observed relational
failure codes at this boundary:

- `missing_unit_requirement_id`;
- `obligation_role_mismatch`; and
- `unsupported_requirement_has_unit`.

The candidate makes the provider-facing representation compact. Deterministic local expansion then
reconstructs the canonical full payload consumed by the existing terminal validation and rendering
path. The compact schema identifier, its hash, the expanded validator-schema identifier, and its
hash must be recorded in every trace and later cohort identity.

The settled candidate identities are:

- neutral provider schema: `archivist.compact_evidence_coverage/1`;
- interpretive provider schema: `archivist.compact_interpretive_evidence_coverage/1`; and
- deterministic adapter: `compact-evidence-expander/1`.

The provider still owns answer units and prose, premise decisions, requirement statuses, ordered
obligation-dimension statuses, and interpretive fields. The adapter parses exact terminal citation
numbers and derives coverage/obligation unit-and-source ledgers plus deterministic gap reasons. It
then supplies canonical evidence-coverage v5 or interpretive v3 to the unchanged
normalizer/validator/renderer. It invents no claim, source, or status; invalid schema, identity, or
ordering remains fail-closed.

This may reduce the amount of mutually constrained structure the provider must serialize, but it
does **not** by itself eliminate or close the three semantic contract-defect classes represented by
the four production failures. Provider-owned statuses, requirement links, and obligation roles can
still disagree semantically. The unchanged validator must continue rejecting those cases, and the
paid comparison must measure rather than assume any reliability effect.

Everything semantic remains fixed:

- corpus and corpus manifest;
- planner, query decomposition, retrieval, ranking, neighbour expansion, evidence admission, and
  source ordering;
- maximum-source rules and the `[Source N]` citation contract;
- model identity, reasoning effort, verbosity, and output ceiling during the comparison;
- requirement, obligation, premise, support, completeness, and abstention meanings;
- interpretive-wrapper behavior;
- terminal evidence validator, fail-closed release policy, reader-visible rendering, and
  progressive checked-claim extraction.

The two provider prompts may necessarily differ in serialization instructions and `text_format`.
Their semantic instructions must otherwise be identical. Lowering reasoning effort, changing the
model, reducing sources, shortening evidence, weakening obligations, skipping checks, or lowering
the output ceiling would introduce another variable and belongs in another experiment.

## Offline gate

Offline work is safe by default and must not require `OPENAI_API_KEY`. The candidate is eligible
for a paid comparison only after all of the following pass:

1. **Authoritative expansion boundary.** The compact payload expands locally into the existing
   canonical answer object. The current terminal validator and renderer remain authoritative and
   unchanged.
2. **Behavior matrix.** Focused fixtures cover supported, partial, unsupported, and conflicting
   requirements; supported, contradicted, and unresolved premises plus premise correction;
   component, stage, adjacent-link, and institutional-handoff obligations; direct answer,
   qualified near-match, and abstention; interpretive wrapping; and progressive answer-unit
   extraction.
3. **Canonical equivalence.** For semantically equivalent synthetic fixtures, legacy-full output
   projected to compact form and expanded locally must equal the canonical full payload. The
   visible render, citation set and source order, answer status, diagnostics, and terminal
   validation code must also agree.
4. **Fail-closed malformed cases.** Unknown, duplicate, missing, or out-of-order identifiers;
   out-of-range source indices; incompatible obligation roles; unsupported requirements with
   answer units; invalid premise mappings; and citation mismatches must all fail locally without a
   provider retry.
5. **Pipeline boundary.** A mocked pipeline must prove that the provider receives the compact
   schema and that deterministic expansion, not a second model call, supplies the unchanged
   validator. Planning, retrieval, gate decisions, and source ordering must be identical.
6. **Trace identity.** Traces must carry both provider-schema and expanded-validator-schema
   identities and hashes, so an observed result cannot be mislabeled as legacy-full output.
7. **Representation measurement.** Compare serialized schema size and representative output size
   using synthetic fixtures and registered development fixtures only. Do not inspect or tune from
   held-out H-item answers or annotations.
8. **Repository verification.** Run focused contract/pipeline tests followed by the complete
   offline sequence in `AGENTS.md`.

### Offline gate result — passed 2026-08-12

The implementation, adapter, pipeline, trace, malformed-input, and equivalence checks pass. Using
minified, sorted-key UTF-8 JSON over the synthetic representative fixtures in the test suite
produced the following representation measurements (all fixture characters were ASCII,
so character and byte counts are identical):

| Representation | Canonical full | Compact V27 | Reduction |
|---|---:|---:|---:|
| Neutral JSON schema | 6,196 bytes | 5,297 bytes | 14.51% |
| Interpretive JSON schema | 7,438 bytes | 5,974 bytes | 19.68% |
| Representative neutral payload | 793 bytes | 626 bytes | 21.06% |
| Representative interpretive payload | 1,110 bytes | 943 bytes | 15.05% |

The complete repository verification also passed: repository-wide Ruff; **1,022 pytest tests with
one intentional skip**; both frontend delivery and mode test suites; and the frontend production
build. No OpenAI call, network operation, deployment, or paid operation was made for this gate.

This offline pass proves mechanical compatibility and a smaller serialized representation. It does
not prove a provider-token reduction, latency improvement, or reliability improvement, and it does
not authorize deployment.

## Historical development control

The V26/V27 browser control described in the original experiment was removed when
`application-compiled-v1` became the default. A local development caller can still explicitly set
`rag_policy_version` to `evidence-planned-v26` or `evidence-planned-v27` for compatibility. That
field is unavailable in the public request contract, and neither explicit policy is a reader-facing
product choice.

Any manual V26/V27 timing remains exploratory historical feedback, not an A/B result or promotion
evidence. The proposed directional paid protocol below was never run and is retained only as the
predeclared protocol for the unpromoted experiment.

## Proposed directional paid A/B protocol (never run)

The proposed comparison would have required fresh owner authorization naming OpenAI, the registered
`G001`-`G010` development questions, retrieved private manuscript passages, the two generator
representations, and a numeric cost ceiling. It must not include held-out H items. There are no
automatic retries or replacement questions.

### Paired inputs

For each registered G item:

1. run planning and retrieval once;
2. freeze the exact coverage input, admitted passages, source order, and gate decision;
3. send the legacy-full and compact arms the same frozen evidence, model (`gpt-5.6-sol`), reasoning
   setting, verbosity, semantic instructions, and output-token ceiling;
4. allow only representation instructions and structured schema to differ; and
5. counterbalance call order deterministically (odd G identifier: legacy then compact; even G
   identifier: compact then legacy).

Make one call per eligible arm. Do not retry, regenerate, replace, or repair a failed result. A
pre-generation abstention such as the historical G008 behavior remains an outcome check but is
excluded from the generation-latency denominator because neither arm made an answer-generation
call.

### Recorded observations

Record every item and both arm outcomes, including regressions:

- planning/retrieval identity and frozen-input hash;
- requested and returned model identity, response ID, schema identity/hash, and call order;
- answer-generation milliseconds;
- input, output, reasoning, and total tokens;
- exact estimated cost and priced/unpriced event count;
- release or terminal error code;
- visible answer characters;
- citation count, citation resolvability, malformed-citation count, and source ordering; and
- the unchanged practical strict-claim and target-document-group rubric.

The latency comparison uses paired items for which both generation calls produced a recorded
generation duration. Every attempted call remains visible in reliability and cost denominators;
failed compact calls cannot disappear from the report merely because they lack a releasable answer.

### Proposed directional promotion gates

All gates are predeclared:

- **Primary latency:** the median across per-item `compact_ms / legacy_ms` ratios must be at most
  `0.70`, equivalent to at least a 30% paired median reduction.
- **Mechanical validity:** every candidate release must expand and pass the unchanged terminal
  validator; citation resolvability must be 100%; malformed citations must be zero.
- **Reliability:** no new terminal contract-failure code, and the compact arm must release at least
  as many answers as the contemporaneous legacy arm.
- **Development quality:** no aggregate loss in the existing practical strict-claim or target-
  document-group coverage measurements.
- **Owner review:** the owner spot-checks the paired reader-visible answers before promotion.

Missing any gate leaves the candidate experimental. Passing them supports a product promotion
decision, but one paired pass remains directional development evidence rather than a formal causal
or production guarantee.

## Proposed optional noise-floor experiment

A publishable before/after improvement claim requires the non-determinism work in
`EVAL_CONTRACT.md` section 1.4: run the fixed ten-item subset five times unchanged per declared
system, report spread, and show that the predeclared 30% latency effect exceeds that spread. This is
substantially more expensive and is not required merely to decide whether the compact candidate
deserves a public smoke.

## Proposed V27 production-performance v2 (not opened)

Only after promotion, deployment, identity verification, and fresh authorization may a new
production cohort be opened. It must be a separately versioned `production-performance-v2`
record; never append observations to or overwrite v1.

The 33 already exposed answerable H question strings may be reused **only as a declared operational
latency workload**. Their answers, gold locations, or prior scores must not be used to tune the
compact representation, and the cohort must not be described as unseen answer-quality evidence.
Use the same fresh, sequential Essential/Complete/RAG first-turn shape with no retries or
replacements, and bind the new commit, RAG policy, provider-schema hash, expanded-validator-schema
hash, model identity, corpus manifest, and one process epoch.

Report exact attempt and success denominators, all-attempt failure and instrumentation-failure
rates, server p50/p95, token counts, and cost. The product target is server p50 below 35 seconds
while preserving the old 54.393-second observation as v1 history. Without the optional five-repeat
noise-floor experiment, any delta is an observed cohort comparison rather than an SLA or a causal
performance claim.

## Promotion and documentation boundary

Because V27 was not promoted:

- do not deploy or make the compact representation the public default;
- do not update README language to claim a faster system;
- do not change `EVAL_CONTRACT.md`, the frozen V26 artifacts, or production-performance v1;
- do not describe token reduction as measured latency reduction; and
- do not tune from held-out H results.

Retain this brief as negative/development evidence rather than silently deleting the experiment.
Any future revival would require a newly reviewed plan and fresh authorization; this historical
protocol does not authorize a paid call.
