# Answer Delivery Modes

Archivist offers two delivery contracts for the same question-answering pipeline. Delivery does
not select a different corpus, retrieval policy, evidence scope, or interpretive setting. It
controls when application-compiled evidence may cross the server boundary. It does not expose a
V26/V27 policy selector.

## Reader choices

### Complete answer (default)

**Complete answer** is the recommended and evaluation-reference behavior. The interface waits
while Archivist retrieves, compiles, optionally arranges, and validates. The answer, citations,
and sources appear together only after the whole response passes its ordinary grounding and
public-release gates.

Essential performs local BM25 retrieval and renders immutable evidence cards with zero provider
calls. Professional, Pretty Pink Princess, and Baleful Black Baron make exactly one no-retry,
low-reasoning `gpt-5.6-sol` call that may select only exact card placeholders and typed IDs from
the chosen mode's closed cue catalog. Local code supplies every displayed word and citation. A
selector or client failure returns the direct Essential evidence.

### Progressive response (experimental)

**Progressive response** first shows the same fixed operational stages as Complete answer. As the
application compiler creates each immutable evidence card, the server sends its exact
citation-rendered form in an ordered `checked_claim` frame. The browser presents those cards as
**checked manuscript evidence while the complete arrangement is still being assembled**. In a
generated mode this can happen before the one optional selector call finishes; Essential has no
provider call to wait for.

This is not chain-of-thought or a transcript of private reasoning. The stream never contains raw
model tokens, selector JSON, prompts, retrieval queries, unbounded manuscript passages,
source-admission deliberations, validation traces, or private diagnostics. A card becomes eligible
only after local compilation fixes its bounded excerpt, paragraph order, source mapping, citation,
and cumulative limits.

Each evidence card is bounded to the compiler's concise excerpt limit and keeps the question's
matched evidence in application-owned form. Progressive delivery does not summarize, paraphrase,
or extend it.

For the public demo, every claim also passes the configured edition-locator boundary and a rolling
verbatim-overlap audit before release. The rolling audit includes all claims already released, so
splitting a long quotation across several short claims cannot bypass the quotation limit.

The card gate is deliberately narrower than terminal validation. Streamed cards are immutable and
cited, but their final order and the placement of any local editorial cues are not yet settled.
They therefore remain provisional **as an arranged answer**, not as model-drafted factual prose.

When arrangement finishes, Archivist runs terminal validation and the public release gate. A
successful `complete` replaces the working cards with the canonical answer and enables sources,
copying, cost metadata, and conversation history. The final answer contains every evidence card
exactly once, although a generated mode may reorder them and interleave application-owned cues. On
interruption, the client clears the working view and never commits the partial turn to history.

Application-owned interpretations and character asides are not streamed. They appear only in the
canonical final answer after the generated-mode response has passed the closed placeholder/cue
schema. Delivery mode does not alter that schema or add a call.

The former V26 design streamed locally checked claims parsed from provider-authored structured
generation. That remains historical behavior of an explicit compatibility policy; it is not the
current `application-compiled-v1` reader contract.

## Latency and cost claim

Progressive response does not add a provider or validation call. Current follow-up resolution,
BM25 retrieval, evidence admission, and card compilation are local, so an Essential request is
provider-free. A generated mode uses the same single no-retry selector call as Complete answer.
The progressive benefit is that checked local evidence may become visible before optional
arrangement finishes; this document makes no latency guarantee.

During a prose-free interval, the server sends a text-free heartbeat every three seconds. The
browser turns those frames into a visible elapsed-work indicator rather than pretending a card
exists. A private structured timing record is written once per Progressive request after both the
worker and response stream end. It measures stage entry, first checked card, terminal outcome,
worker finish, and stream finish. It contains no question, source, manuscript, prompt, answer, or
error text.

Generated-mode provider usage is recorded once. Malformed selector output falls back to direct
Essential evidence and cannot silently trigger a replay. Essential records no provider usage. No
automatic replay is permitted.

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
optional arrangement, terminal validation, and the public gate occur after local card compilation.

Exactly one terminal `complete` or `error` ends an accepted stream. End-of-file without a terminal
frame is interruption, not success. The client bounds frame size, cumulative claim text, claim and
paragraph ordering, stage ordering, and terminal state. It never treats working claims as an
authoritative answer or sends them back as conversation history.

### Retry, cancellation, and stream lifetime

The browser must not automatically retry after the server accepts a progressive request. In a
generated mode, a disconnect may occur after paid work began and a replay could charge twice. A
reader-controlled retry is a new request. In a generated mode, closing the page is not a guarantee
that the one
selector call stopped. Essential has no paid work.

Compatibility fallback to Complete answer is allowed only when the progressive endpoint rejects
the request before acceptance with an explicit unavailable response such as `404`, `405`, or
`501`. There is no fallback after the first stream frame.

An accepted public stream occupies the same rate and concurrency allowance as Complete answer.
The lease remains held until both the response stream and worker have ended, including
disconnect cleanup. The route remains inside the public request-size, schema, strategy, monthly
spend, source minimization, security-header, and private-route boundaries. Responses are not
cacheable.

## Verification contract

Offline checks must establish that:

- Complete answer remains the default and its JSON behavior is unchanged;
- Complete and Progressive use the same evidence compiler and, where applicable, the same closed
  arrangement schema;
- Essential invokes no provider, while each generated mode invokes it exactly once with no retry;
- a checked evidence card can arrive before optional arrangement finishes;
- every released card is exact application-owned text with an application-owned citation;
- selector output, token boundaries, or malformed JSON can never alter a released card;
- claim indices, paragraphs, citations, declared sources, IDs, and cumulative limits fail closed;
- public locators and rolling cross-claim quotation limits run before each public claim release;
- interruption clears the working cards and never creates conversation history;
- accepted streams end exactly once and are never automatically replayed;
- public concurrency remains occupied through worker and stream cleanup; and
- the progressive endpoint cannot bypass body, rate, concurrency, spend, or route controls.

Deployment verification still requires a live Render smoke. Confirm that the elapsed indicator
updates, at least one `checked_claim` carries exact local evidence, and the final answer replaces
rather than duplicates the working cards. Confirm citations and edition-qualified sources appear
normally. Compare the custom domain with Render's direct subdomain and inspect the private timing
record to separate application timing from proxy buffering. Interrupt a request to confirm no
replay and no retained partial turn, then repeat one question through Complete answer. An
Essential smoke must record zero provider use; a generated-mode smoke must record at most its one
authorized selector call. A local suite cannot prove deployed proxy or browser buffering.
