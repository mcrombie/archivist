# Archivist production performance cohort

This is a text-free operational measurement of the deployed Complete-answer boundary. It is separate from the frozen answer-quality evaluation and does not score response content.

## Cohort

- Planned and attempted requests: 33
- Successful public completions: 29
- Failures: 4 (12.12%)
- Instrumentation failures (reported separately): 0
- Latency-eligible completions: 29
- Delivery/configuration: Complete, Essential, RAG, empty history, first turn
- Execution: sequential, no retries or replacement requests, at least 12 seconds between starts
- Warm boundary: two ready health checks on one process epoch; cold starts were excluded and not measured

## Latency

- Server observations: 29
- Server p50: 54.393 seconds
- Server p95 (nearest rank): 113.801 seconds
- Operator-client observations: 29
- Operator-client p50: 54.493 seconds
- Operator-client p95 (nearest rank): 113.829 seconds

## Usage

- Estimated API cost: $4.905947
- Recorded API-cost lower bound: $4.905947
- Conservative authorization accounting (recorded cost plus the enforced maximum for each unknown attempt): $4.905947
- Recorded tokens: 500164
- Priced events: 80
- Unpriced events: 0
- Attempts with unavailable usage: 0
- Owner-authorized cohort ceiling: $10.00
- Enforced maximum accounted per next/unknown attempt: $2.000000
- Request-cost ceiling contract: `public-rag-request-ceiling-v1`

## Identity

- Deployed wrapper commit: `e71d9b79a60a894cb38451c37e0d43b7f9149fa9`
- Frozen candidate commit: `8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e`
- Frozen RAG policy: `evidence-planned-v26`
- Corpus manifest SHA-256: `b7ff94315a3f1f28c831e2c3ca62c385567d2b1447c19ff45139d175c3ff3c17`
- Gold-set SHA-256: `72c4e8450a40dcf608757abd1244fe45cb57d3c1c1daccee10bedf4283e8f2f2`
