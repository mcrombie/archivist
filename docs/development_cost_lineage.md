# Archivist development API cost lineage

Generated from isolated local evaluation ledgers. This artifact is text-free: it contains
no questions, answers, source passages, or manuscript text.

RAG selection window: V18–V25; matching RAG ledgers and all discovered full-context ledgers are included in separate strategy namespaces.

## Strategy-version totals

| Strategy | Policy | Runs | Calls | Tokens | Estimated USD | Unpriced events |
|---|---|---:|---:|---:|---:|---:|
| rag | evidence-planned-v18 | 1 | 27 | 122503 | $1.322573510 | 0 |
| rag | evidence-planned-v19 | 2 | 6 | 39929 | $0.470555410 | 0 |
| rag | evidence-planned-v20 | 1 | 6 | 53277 | $0.537319470 | 0 |
| rag | evidence-planned-v21 | 1 | 3 | 26508 | $0.298705430 | 0 |
| rag | evidence-planned-v22 | 1 | 3 | 25257 | $0.252074060 | 0 |
| rag | evidence-planned-v23 | 1 | 2 | 11667 | $0.084300310 | 0 |
| rag | evidence-planned-v24 | 3 | 31 | 215080 | $1.846304580 | 0 |
| full_context | full-context-v1 | 1 | 1 | 251436 | $1.625146250 | 0 |

## Run details

| Run | Strategy | Policy | Commit | Status | Items | Retries | Latency (s) | Operational cap | Calls | Tokens | Estimated USD |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| evidence-planned-v18-clean-20260729-1 | rag | evidence-planned-v18 | 97ca2bc96fd1 | completed | 10 | 0 | 750.837 | $2.50 | 27 | 122503 | $1.322573510 |
| evidence-planned-v19-confirm-g006-g007-20260729-1 | rag | evidence-planned-v19 | 3c393103f08a | error | 1 | 0 | 280.133 | $0.75 | 3 | 21374 | $0.262197370 |
| evidence-planned-v19-continuation-g007-20260729-1 | rag | evidence-planned-v19 | 3c393103f08a | completed | 1 | 0 | 86.160 | $0.48780263 | 3 | 18555 | $0.208358040 |
| evidence-planned-v20-confirm-g006-g007-20260729-1 | rag | evidence-planned-v20 | f13534a85d41 | completed | 2 | 0 | 173.728 | $0.90 | 6 | 53277 | $0.537319470 |
| evidence-planned-v21-confirm-g007-20260729-1 | rag | evidence-planned-v21 | bf424c880bca | completed | 1 | 0 | 104.985 | $0.40 | 3 | 26508 | $0.298705430 |
| evidence-planned-v22-confirm-g007-20260729-1 | rag | evidence-planned-v22 | 0691b3da9a49 | completed | 1 | 0 | 95.735 | $0.50 | 3 | 25257 | $0.252074060 |
| evidence-planned-v23-confirm-g007-20260729-1 | rag | evidence-planned-v23 | d89f4332b21f | completed | 1 | 0 | 24.655 | $0.50 | 2 | 11667 | $0.084300310 |
| evidence-planned-v24-clean-20260730-1 | rag | evidence-planned-v24 | 67c735fff37d | error | 1 | 0 | 2.940 | $3.00 | 0 | 0 | $0.000000000 |
| evidence-planned-v24-clean-20260730-2 | rag | evidence-planned-v24 | 1b75e8676319 | completed | 10 | 0 | 589.577 | $3.00 | 28 | 187228 | $1.531580520 |
| evidence-planned-v24-mechanical-g007-20260730-1 | rag | evidence-planned-v24 | 67c735fff37d | completed | 1 | 0 | 108.851 | $0.50 | 3 | 27852 | $0.314724060 |
| full-context-v1-g007-20260730-1 | full_context | full-context-v1 | c01ce00177d6 | error | 1 | 0 | 42.154 | $4.00 | 1 | 251436 | $1.625146250 |

## Cumulative total

- Runs: **11**
- API operations: **79**
- Priced tokens: **745657**
- Estimated API cost: **$6.436979020**
- Unpriced events: **0**

These are application estimates reconstructed from returned token usage. The provider invoice remains authoritative.
