# Answer Delivery Modes

Archivist offers two delivery contracts over the same `retrieval-authored-v4` answer pipeline.
Delivery changes when eligible material crosses the server boundary; it does not select another
corpus, retrieval policy, evidence scope, or interpretive setting. The browser exposes no V26/V27
policy or latency selector.

## Shared current pipeline

Every historical or manuscript RAG turn resolves only high-confidence follow-up references locally, makes one
`text-embedding-3-small` query-embedding request, and runs the shared dense/BM25 reciprocal-rank-
fusion retriever and context finalizer. Archivist then packages four to eight source-bound evidence
units in retrieval order. The dossier targets about 2,500 estimated evidence tokens and has a hard
4,500-token evidence ceiling. It prefers whole chunks and may shorten only to a range of complete
paragraphs when the hard ceiling requires it.

Essential renders direct cited evidence and makes no prose-generation call. It is not a zero-
provider path because retrieval uses the embedding request. Every registered generated mode --
currently Professional, Pretty Pink Princess, Baleful Black Baron, and Ruthless Red Realist -- adds
exactly one no-retry `gpt-5.6-sol` authored-response call with low
reasoning, medium verbosity, and a 1,800 output-token ceiling. The model receives the question,
locally resolved turn, and rich dossier. It may synthesize, paraphrase, choose useful length, and
write in character; each generated answer must end with one to three in-character questions that
invite continued engagement.

The generated response separates grounded runs from persona runs. Grounded runs name opaque
dossier-unit IDs; local code verifies that those IDs exist and maps them to `[Source N]`. Persona
runs may contain only voice, metaphor, reactions, and fictional character business. The model does
not write citation labels. Unknown IDs, forged labels, malformed structure, links, HTML, or
extended manuscript copying fail closed to the direct Essential answer without a retry.
The v4 policy keeps authored input/output schemas `archivist.authored_response_input/1` and
`archivist.retrieval_authored_answer/1` and renderer `retrieval-authored-renderer-v1`.

This is a structural provenance boundary, not a semantic judge. Local support-ID resolution does
not prove that a sentence is entailed by the cited passage or that the model classified every run
correctly. Documentation, telemetry, and evaluation must not call that check faithfulness.

### Character conversation before retrieval

For every registered generated mode, a conservative local classifier recognizes a narrow set of
direct social or personal questions before retrieval. `character-conversation-v2`
then makes exactly one no-retry `answer_generation` call to `gpt-5.6-sol` with low reasoning, low
verbosity, a 12-second timeout, and at most 576 output tokens. It sends only the question, selected mode, and character
instructions—no conversation history, embedding, manuscript text, retrieved evidence, dossier,
source metadata, or citation. Its `character_reply` disposition contains fictional persona
conversation plus one to three in-character questions that explicitly lead back to the manuscript
or *Cradle of the Empire*. It may not state historical facts.
Its input/output schemas remain `archivist.character_conversation_input/1` and
`archivist.character_conversation_answer/1`; its renderer remains
`character-conversation-renderer-v1`. The v2 route identity reflects generalized mode eligibility,
not a changed structured-response shape.

A provider failure, refusal, or invalid response returns a deterministic mode-specific local reply
with the same manuscript-leading question. It does not retry, retrieve, or substitute Essential,
and therefore does not display the Essential-fallback notice. If a question mentions history, the
manuscript, Virginia, or a historical topic; combines social and factual requests; exceeds the
narrow classifier; or is addressed in Essential, it follows the ordinary grounded path. The
current registry covers Professional, Pretty Pink Princess, Baleful Black Baron, and Ruthless Red
Realist. A future mode inherits this route by registering generated-mode instructions and fallback
copy rather than by extending a router allowlist. The branch is intentionally not a general-chat
escape from retrieval.

## Reader choices

### Complete answer (default)

Complete answer is the recommended and evaluation-reference presentation. The interface waits
while Archivist retrieves, builds the dossier, optionally authors generated prose, validates the
result, and applies public-release checks. The answer, citations, and sources appear together only
after the terminal result is accepted. A generated-mode provider or validation failure returns the
Essential direct-evidence result from the same retrieval without another model call. That result
is still a successful, cited answer rather than a terminal transport error, but the browser must
show a visible nonfatal notice above it saying that the requested generated mode could not be
completed and Archivist returned Essential instead. Its heading is **Essential fallback** and its
message is “Archivist could not complete the {Mode label} AI response, so it returned Essential's
direct manuscript evidence instead.” The notice must not expose provider exception text, prompts,
manuscript contents, or private diagnostics.

### Progressive response (experimental)

Progressive response shows fixed application-owned operational stages and sends a text-free
heartbeat about every three seconds while work continues. It never exposes raw model tokens,
prompts, retrieval queries, structured output, reasoning, unbounded manuscript passages, or private
diagnostics.

Essential may release its locally compiled direct excerpts as ordered `checked_claim` frames after
their source mapping, edition-locator boundary, and rolling public quotation checks pass. Those
frames are exact application-owned evidence, not model-authored paraphrases.

Generated modes and character-social replies do **not** stream their authored prose as checked claims. The new model-written
sentences need terminal structural validation, and local support-ID checks do not establish
semantic entailment. A generated Progressive request therefore shows stages and heartbeats until
the complete authored answer or Essential fallback is ready. Progressive delivery adds no
additional provider operation and makes no promise of lower total latency.

On success, one terminal `complete` frame supplies the authoritative ordinary response and enables
sources, copying, cost metadata, and conversation history. On interruption or failure, the client
clears the working view and never commits a partial turn to history. Complete answer remains the
formal evaluation presentation.

## Latency and cost boundary

Current Essential uses one priced embedding operation. A generated manuscript turn normally uses two provider
operations total: the same embedding request plus one authored-response request. There is no
planner, judge, repair, or automatic retry call in this current path. Provider usage is recorded by
operation and remains inside the ordinary public budget and per-request ceiling. The provider
operations share one 35-second provider deadline. Retrieval receives at most eight seconds; the
authored response receives at most thirty seconds of the time that remains. If less than one second
remains after retrieval and local dossier construction, Archivist skips authoring and returns the
direct Essential evidence. These are fail-fast implementation bounds, not an end-to-end latency
guarantee. Text-free internal diagnostics distinguish request timeout, transport failure, generic
provider exception, provider refusal, structured-output rejection, and local contract-validation
failure. The reader-facing Essential-fallback notice remains generic.

A character-social turn has one provider operation total: the compact Sol answer-generation call.
It does not enter the embedding/retrieval deadline path and never starts a second provider call.
Its 576-token ceiling and low verbosity are latency-oriented design choices, not measured speed.

These choices are latency hypotheses, not measurements. No live smoke, paid latency cohort, or
quality cohort has run for `retrieval-authored-v4` or `character-conversation-v2`. The terminal v3
run is a timeout diagnostic—30 authored generations and seven fallbacks—not v4 evidence. The earlier Edwin Sandys timings measured the
superseded `application-compiled-v1` cue selector and cannot be attributed to this design.

## Public NDJSON protocol

The progressive transport is an HTTP `POST` to:

```text
/api/projects/{project_id}/question/progressive
```

For the public demo, `{project_id}` is `current`. The response is `application/x-ndjson`; each line
is one complete object carrying schema `archivist.answer_stream/2`, a monotonically increasing
`sequence`, and one of:

- `stage`, containing one allowlisted stage and fixed application-owned message;
- `heartbeat`, containing no answer or diagnostic data;
- `checked_claim`, used only for locally compiled direct evidence that passed its release gates;
- `complete`, containing the authoritative ordinary question-response object; or
- `error`, containing a safe code and message and, when available, a request identifier.

The fixed stages are `accepted`, `checking_corpus`, `resolving_question`, `planning_search`,
`retrieving_sources`, `checking_evidence`, `preparing_context`, `generating_answer`,
`validating_answer`, and `checking_release`. Exactly one terminal `complete` or `error` ends an
accepted stream. End-of-file without a terminal frame is interruption, not success. The client
bounds frame size, cumulative claim text, claim and paragraph ordering, stage ordering, and
terminal state. Working evidence never becomes conversation history.

### Retry, cancellation, and stream lifetime

The browser must not automatically retry after the server accepts a progressive request. A
disconnect may occur after the embedding or authored-response request began, and replay could
charge twice. A reader-controlled retry is a new request. Compatibility fallback to Complete
answer is allowed only when the progressive endpoint rejects before acceptance with an explicit
unavailable response such as `404`, `405`, or `501`.

An accepted public stream occupies the same rate and concurrency allowance as Complete answer.
The lease remains held until both the response stream and worker have ended, including disconnect
cleanup. The route remains inside the public request-size, schema, strategy, monthly-spend, source-
minimization, security-header, and private-route boundaries. Responses are not cacheable.

## Verification contract

Offline checks must establish that:

- Complete answer remains the default;
- Complete and Progressive use the same hybrid retrieval, dossier, and terminal processor;
- Essential makes exactly the query-embedding request and no prose-generation call;
- each generated mode makes the same embedding request plus exactly one no-retry authored-response
  call;
- only narrow social questions in registered generated modes enter `character-conversation-v2`, whose request
  contains no evidence/history and makes one compact no-retry call without retrieval;
- character-social output contains no citations or historical claims, requires one to three
  explicit manuscript-leading questions, and uses deterministic in-character local fallback on
  provider/refusal/validation failure;
- dossiers preserve four to eight source-bound units when retrieval and budget permit, with the
  2,500 target and 4,500 hard evidence-token limits;
- generated answers end with one to three questions;
- unknown support IDs, forged citations, malformed output, and provider failure fall back to
  Essential without replay;
- every accepted generated-mode fallback displays the nonfatal Essential-fallback notice, while
  ordinary Essential and successfully authored generated answers do not;
- generated prose never enters a `checked_claim` frame;
- direct checked evidence passes source, locator, rolling quotation, ordering, and cumulative
  limits before release;
- interruption clears working evidence and never creates conversation history; and
- public concurrency, body, rate, spend, and route controls remain in force through cleanup.

Deployment verification still requires separately authorized live testing. Confirm the elapsed
indicator, terminal answer replacement, citations, edition-qualified sources, no replay on
interruption, request-scoped provider events, and proxy buffering behavior. A local suite cannot
prove Render or browser streaming behavior, and this document records no live verification of the
current policy.
