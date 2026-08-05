# Answer Delivery Modes

Archivist offers two delivery contracts for the same question-answering pipeline. Delivery does
not select a different corpus, retrieval policy, prompt, model, evidence scope, or interpretive
setting. It controls when reader-visible prose may cross the server boundary.

## Reader choices

### Complete answer (default)

**Complete answer** is the recommended and evaluation-reference behavior. The interface waits
while Archivist retrieves, generates, and validates. The answer, citations, and sources appear
together only after the whole response passes its ordinary grounding and public-release gates.

This is the strict fail-closed choice: a response that fails whole-answer validation exposes no
answer prose.

### Progressive response (experimental)

**Progressive response** uses streaming on the existing final generation request. It first shows
the same fixed operational stages as Complete answer. While the model is producing its structured
answer, the server then extracts one complete factual claim at a time, checks that claim locally,
and sends an ordered `checked_claim` frame. The browser presents those claims as **checked
manuscript claims while the complete answer is still being assembled**.

This is not chain-of-thought or a transcript of private reasoning. The stream never contains raw
model tokens, partial JSON, prompts, retrieval queries, manuscript passages, source-admission
deliberations, validation traces, or private diagnostics. A claim becomes eligible only after its
complete structured object exists and its atomic sentence, identifier and paragraph order,
citation grammar and declared source mapping, source bounds, and cumulative limits pass local
checks.

The first releasable non-correction claim has an additional reader-facing gate: it must state the
bottom line in one sentence of no more than 45 words and, when the question supplies trustworthy
subject anchors, name that subject. A premise correction remains withheld until whole-answer
validation; the next factual claim becomes the first progressive candidate. Failure of this local
lead gate suppresses provisional prose but does not cancel, retry, or invalidate an otherwise
sound terminal answer.

For the public demo, every claim also passes the configured edition-locator boundary and a rolling
verbatim-overlap audit before release. The rolling audit includes all claims already released, so
splitting a long quotation across several short claims cannot bypass the quotation limit.

The claim gate is deliberately narrower than whole-answer validation. It cannot yet prove that all
requested parts were covered, that every premise and evidence obligation is globally consistent,
that a later claim will not duplicate or contradict an earlier one, or that an interpretive frame
will pass. Streamed claims therefore remain provisional **as a complete answer**, even though each
has passed its local release checks.

When generation finishes, Archivist runs the unchanged whole-answer validator and public release
gate. A successful terminal `complete` replaces the working claims with the canonical cohesive
answer and enables citations, sources, copying, cost metadata, and conversation history. On a late
validation failure or interruption, the client clears the working claims, shows a safe failure,
and never commits the partial turn to history. This means Progressive response intentionally does
not retain Complete answer's stronger promise that rejected prose was never briefly visible.

Interpretive prefaces and conclusions are not streamed. The shared generation schemas now
serialize the factual claim array immediately after the schema identifier, before private
premise, coverage, and obligation ledgers; interpretive fields follow later even though the final
renderer places the preface first. This ordering applies equally to Complete and Progressive and
opened the `evidence-coverage-v11` and `full-context-coverage-v3` generation cohorts. Delivery mode
still does not select a different prompt or schema within those cohorts. Progressive presents the
factual claims while working and introduces selected framing only in the canonical final answer.

## Latency and cost claim

Progressive response replaces the final blocking Responses API generation with one streamed
Responses API generation. It does not add a second generation or validation call. Existing work
that precedes generation—conversation resolution, optional planning, embeddings, retrieval, and
evidence admission—remains unchanged, so there can still be a meaningful delay before the first
claim. Total generation and validation time may remain similar; the improvement is earlier useful
prose once answer generation reaches its first complete claim.

During a prose-free interval, the server sends a text-free heartbeat every three seconds. The
browser turns those frames into a visible elapsed-work indicator rather than pretending a claim
exists. A private structured timing record is also written once per Progressive request after both
the paid worker and response stream end. It measures stage entry, first provider text delta,
provider terminal, first checked claim, terminal outcome, worker finish, and stream finish, but
contains no question, source, manuscript, prompt, answer, or error text. These measurements
distinguish upstream retrieval time, provider time, local release delay, and proxy/browser delay
without weakening the disclosure boundary.

Provider usage is recorded once from the terminal streamed response. A malformed structured
answer is still consumed through its provider terminal event before local parsing fails, so a
failed parse cannot silently disappear from the cost ledger. No automatic replay is permitted.

Complete answer remains the evaluation presentation. Progressive delivery is an experimental
reader surface, not an answer-quality cohort. Its final authoritative result must still use the
same whole-answer processor as Complete answer; a presentation-only difference must never be
reported as a RAG improvement.

## Public NDJSON protocol

The progressive transport is an HTTP `POST` to:

```text
/api/projects/{project_id}/question/progressive
```

For the public demo, `{project_id}` is `current`. The request uses the ordinary question schema.
The response is `application/x-ndjson`; each line is one complete object carrying schema
`archivist.answer_stream/2`, a monotonically increasing `sequence`, and one of:

- `stage`, containing one allowlisted stage and fixed application-owned message;
- `heartbeat`, emitted about every three seconds and containing no answer or diagnostic data;
- `checked_claim`, containing a contiguous one-based `claim_index`, a positive `paragraph`, and
  the locally checked citation-rendered `text` only;
- `complete`, containing the authoritative ordinary question-response object; or
- `error`, containing a safe code and message and, when available, a request identifier.

The fixed stages are `accepted`, `checking_corpus`, `resolving_question`, `planning_search`,
`retrieving_sources`, `checking_evidence`, `preparing_context`, `generating_answer`,
`validating_answer`, and `checking_release`. Stages may continue after checked claims begin because
whole-answer validation and the public gate occur after the last generated unit.

Exactly one terminal `complete` or `error` ends an accepted stream. End-of-file without a terminal
frame is interruption, not success. The client bounds frame size, cumulative claim text, claim and
paragraph ordering, stage ordering, and terminal state. It never treats working claims as an
authoritative answer or sends them back as conversation history.

### Retry, cancellation, and stream lifetime

The browser must not automatically retry after the server accepts a progressive request. A
disconnect may occur after paid work began, and a replay could charge twice. A reader-controlled
retry is a new request. Closing the page is not a guarantee that provider work stopped.

Compatibility fallback to Complete answer is allowed only when the progressive endpoint rejects
the request before acceptance with an explicit unavailable response such as `404`, `405`, or
`501`. There is no fallback after the first stream frame.

An accepted public stream occupies the same rate and concurrency allowance as Complete answer.
The lease remains held until both the response stream and paid worker have ended, including
disconnect cleanup. The route remains inside the public request-size, schema, strategy, monthly
spend, source minimization, security-header, and private-route boundaries. Responses are not
cacheable.

## Verification contract

Offline checks must establish that:

- Complete answer remains the default and its JSON behavior is unchanged;
- Complete and Progressive use the same prompt and property-ordered generation schema;
- progressive generation invokes the provider exactly once and records terminal usage once;
- a checked claim can arrive before `response.completed`;
- the first released factual claim is direct, subject-linked when possible, and at most 45 words;
- arbitrary token splits, escaped JSON, and truncated members never release an incomplete claim;
- claim indices, paragraphs, citations, declared sources, IDs, and cumulative limits fail closed;
- public locators and rolling cross-claim quotation limits run before each public claim release;
- late global failure or interruption clears claims and never creates conversation history;
- accepted streams end exactly once and are never automatically replayed;
- public concurrency remains occupied through worker and stream cleanup; and
- the progressive endpoint cannot bypass body, rate, concurrency, spend, or route controls.

Deployment verification still requires a live Render smoke. Confirm that the elapsed indicator
updates during prose-free work and that at least one `checked_claim` arrives in the browser before
the terminal provider result. Confirm that the final answer replaces rather than duplicates the
working claims and that citations and edition-qualified sources appear normally. Compare the
custom domain with Render's direct subdomain and inspect the private timing record to separate
application timing from proxy buffering. Interrupt a request to confirm no replay and no retained
partial turn, then repeat one question through Complete answer to verify its strict behavior is
unchanged. A local suite cannot prove how Render, Cloudflare, or the browser will buffer the
deployed stream.
