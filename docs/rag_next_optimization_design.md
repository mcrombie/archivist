# Next RAG optimization: evidence-planned answers

Status: evidence-planned-v6 implemented and measured on the unchanged ten-question set on
2026-07-25; operational recovery confirmed, with three measured quality gaps remaining
Scope: Answer Mode only
Behavior changed by this document: evidence-planned policy available behind the orchestration
boundary; the legacy answer path remains callable

## Implementation status

Version 1 was implemented as `evidence-planned-v1` in the shared CLI/web answer pipeline.
Version 2 kept that bounded-call design and added conservative local normalization for redundant
evidence mappings, relational-query decomposition that did not need an extra planner call, and
durable text-free post-validation diagnostics. A paid two-turn smoke then exposed three narrower
defects: neighbor expansion displaced a selected primary passage, compound answer units weakened
citation locality, and a locally resolvable follow-up attempted a failing planner call.

The `evidence-planned-v3` cohort addressed those defects:

- every selected primary passage is retained before optional neighbors fill unused context slots;
- the evidence-coverage prompt and schema require one independently checkable factual claim and
  one terminal citation group per answer unit. Generated prose reserves its only sentence-ending
  punctuation for that citation, making extra punctuated sentences mechanically rejectable;
- bounded resolved relationship follow-ups decompose locally into both operands and their context
  instead of calling the planner;
- every planner outcome is represented by a versioned, text-free diagnostic. Failures preserve
  only safe class/code tokens, never provider messages or manuscript/question text.

The paid v3 smoke confirmed primary-passage retention, atomic citation locality, and substantively
supported answers. It did not confirm planner avoidance. The follow-up resolver emitted the
corpus-agnostic form `How did the relationship between X and Y shape Z?`, which fell outside the
local grammar and still attempted a planner call. That call failed with `ValidationError` after
12.93 seconds and returned no locally recordable usage. The unchanged ten-question evaluation
was therefore held behind a narrower orchestration gate.

The current `evidence-planned-v4` cohort clears that gate:

- the resolver's observed directional relationship form decomposes locally without weakening the
  ambiguous-tail planner boundary;
- completed structured responses record provider usage before SDK post-parse validation, with no
  retry or second request;
- reusable smoke artifacts bind corpus, vector-store, Git worktree, dependency lock, runner, and
  per-turn retrieval-trace identity;
- retrieval trace schema `archivist.retrieval_trace/3` hashes document labels and planner
  exception classes and accepts only closed, field-specific diagnostic values.

A separately authorized resolver-only confirmation made exactly one API request and no planner,
embedding, retrieval, or answer-generation call. It retained tobacco, labor, Jamestown, and
exchange in the standalone question; routed relationship-only; recorded planner status
`not_called`; took 6.954 seconds; and cost an estimated `$0.006865` under a `$0.02` hard stop. The
artifact was intentionally produced from a dirty exploratory worktree, so it is not a run of
record. It proves the orchestration repair, not answer quality.

The subsequent clean directional evaluation ran the owner's unchanged ten questions at commit
`cab97262c34a7dd64c070e71179ca4a311a76f34`. All ten completed once without retries under a
`$1.25` cap, costing an estimated `$1.02332782`. Strict grading against the unchanged 58-claim
practical rubric found 11 claims present, 47 absent, and none contradicted; final returned sources
covered 11 of 26 target document groups. Five of ten items met their high-level expected behavior.
The four accepted generated answers contained 33 well-formed, resolvable source references and no
malformed citations.

The run rejected the current v4 implementation as an answer-quality improvement:

- all eight planner-eligible questions paid for a planner result, but five failed structured-output
  validation and three were rejected as invalid plans; none supplied the accepted retrieval plan;
- those failed calls cost `$0.57508750`, 56.2% of the run;
- G002, G004, G006, and G009 falsely abstained, over-abstained, or returned insufficient evidence;
- G008 correctly certified absence without analogical substitution;
- G010 retrieved premise and counterevidence but discarded the generated correction after
  source-remapping and premise-validation failures;
- the broad G006 returned no answer and G007 covered none of its seven strict composite claims.

This is a directional single sample rather than a formal run of record. The generator/planner name
is undated, the practical rubric is not the locked chunk-level gold set, and the noise floor has not
been established. It nevertheless gives a mechanically explained repair order without changing
the questions, claims, rubric, or contract.

The `evidence-planned-v5` cohort implements those repairs without changing corpus or evaluation
identity:

- `query-planner-v3` parses a compact provider proposal containing only requirements, facets, and
  premise hypotheses. Application-owned routing, trusted targets, ordering, `F0`, status, and
  cross-field semantics are applied locally after shape parsing. The provider retains the version
  1 ceiling of eight requirements and seven added facets, is prompted to prefer smaller sufficient
  plans, and has a 4,000-token output ceiling. There is still no planner retry.
- `evidence-gate-v2` can split only two exact title-cased personal-name components copied from one
  trusted compound target. All-present subjects admit the retrieved context; mixed presence admits
  only direct/neighbor lanes; all-absent subjects certify absence only when each scan qualifies.
  Any multi-subject request that also contains a facet remains indeterminate pending a joint rule.
- A qualified related path can be derived only from an exact trusted user-message tail. The exact
  broader term and probe must occur in one eligible chunk or immediate neighbors; resolver-only
  additions, planner aliases, semantic similarity, and distant co-occurrence cannot qualify.
- `evidence-coverage-normalizer/2` may remove redundant extra premise-decision source numbers only
  when they form a nonempty strict superset of the cited leading correction unit. It never repairs
  empty, disjoint, duplicate, out-of-range, wrong-role, or already-valid subset mappings.

An offline replay of the preserved v4 retrieval contexts changed G002, G004, and G006 from
withholding to direct-answer admission, kept G008 as a clean abstention, and changed G009 to a
qualified near match limited to the two bounded passages. A synthetic promoted-anchor fixture
also validates the G010 source-number/correction shape. These checks made no OpenAI request and do
not establish live planner success or answer quality.

The separately authorized v5 smoke then ran the unchanged G008-G010 items once for an estimated
`$0.22260367`. G008 passed protected absence and skipped generation. G010 produced a valid cited
premise correction. G009 reached the intended `qualified_near_match` decision with exactly two
bounded sources, but its otherwise usable answer was discarded by redundant status/gap
bookkeeping. Its planner proposal also failed local semantic validation after provider parsing,
while the version-1 diagnostic collapsed the actionable local code into
`invalid_planner_output`.

The focused `evidence-planned-v6` cohort changes only those two contract boundaries:

- `evidence-coverage-normalizer/3` canonicalizes `gap_reason` from the unchanged requirement
  status, records the repair, and reruns strict validation. It does not alter answer units,
  sources, citations, or status; unsupported factual units and missing required units still fail.
- planner diagnostics schema `archivist.planner_call_diagnostics/2` retains a finite text-free
  semantic validation code, or `plan_structure_invalid` for a structural failure, beside the
  existing generic fallback reason. It does not loosen plan validation, retry, or persist provider
  prose. Historical version-1 diagnostics remain readable.

The v6 implementation itself made no OpenAI request. Its separately authorized G009 confirmation
then completed in 24.721 seconds for an estimated `$0.07107566`, with no retry. The planner
succeeded; evidence remained `qualified_near_match`; exactly two bounded sources were returned;
normalization recorded `status_gap_mismatch`; strict validation passed; and all four emitted source
references resolved. The confirmation therefore cleared the final micro-gate. The implementation
is now frozen for the owner's unchanged ten-question rerun, with no UI work, broad audit, or new
optimization target in between.

The clean v6 directional cohort then ran all ten unchanged questions at commit
`8a0d6c9eaffaaaab2fb365f0b0a0a049b3dbc67d`. Every item completed once with no retry, ten validated
retrieval traces, and zero unpriced usage events. It cost an estimated `$0.92185165` and took
280.803 seconds across the questions. Against the same frozen practical rubric and the same
grading thresholds used for v4, it observed:

- 17/58 expected claims present, 41 absent, and none contradicted;
- 17/26 expected document groups represented in final context;
- 8/10 high-level behaviors passing;
- 58 emitted source references, all well formed and resolvable;
- six accepted planner proposals out of eight eligible questions, versus none in v4.

Relative to the preserved v4 directional sample, this is six more claims, six more document
groups, and three more high-level behavior passes while estimated cost fell 9.9%, total latency
fell 19.2%, and planner cost fell 65.5%. It remains a single nondeterministic comparison rather
than a formal delta. It also remains below the earlier clean-hybrid sample's 19/58 strict claims
while costing and taking substantially more.

The evaluation isolated the next three quality boundaries:

- the unchanged G009 passed its focused confirmation but failed in the full cohort when a live
  premise hypothesis overrode certified absence, admitted all eight sources, and ended in
  `premise_source_mismatch`;
- successful broad plans did not survive source allocation: G006 covered 2/8 expected document
  groups and G007 covered 2/5;
- G010 became a mechanically valid premise correction but used a later earlier-than-1898 frame
  instead of realizing the manuscript's requested origin frame.

These are measurement results, not licenses to alter the questions or rubric. The next changes
must target premise/absence precedence, requirement survival through source allocation, and
source-bounded correction coverage separately.

The implementation follows the bounded-call design in this document:

- a follow-up resolver runs only when conversation history exists;
- a structured question planner runs only for routed broad, multi-part, premise-sensitive, or
  absence-sensitive questions;
- all retrieval facets share one batched embedding request;
- a clean, locally certified absence skips answer generation;
- every other admitted answer uses one structured evidence-coverage generation with no automatic
  critic or retry.

Conversation context is intentionally asymmetric. Prior user turns can clarify a referent, scope,
or requested relationship. Prior assistant answer text is not sent to the resolver, cannot become
manuscript evidence, and cannot supply the trusted wording used to certify an absence.

Before any paid operation, the pipeline validates the persisted corpus and vector index against the
private manifest. It reads the actual Chroma collection name, metadata, IDs, and stored per-chunk
metadata rather than trusting caller-supplied labels or count alone. A stale, reordered, incomplete,
or differently configured index fails operationally without spending on follow-up resolution,
planning, embedding, or generation. Non-current custom projects continue to use the legacy path
until they persist the same independent chunk-identity contract.

The question endpoint also rechecks the configured hard cost limit immediately before every tracked
OpenAI operation. If an earlier operation in the same turn crosses the limit, the next operation is
not sent unless the reader explicitly enabled the per-request override.

The implementation was verified with 403 passing offline tests and one skipped test, strict
provider-schema conversion, local inspection of the current private index, and replay of the
preserved v4 retrieval contexts. Earlier paid smokes verified narrower source-retention,
citation-structure, and relationship-routing behaviors, while the clean ten-question evaluation
exposed the three v4 failures repaired here. The v5 smoke passed G008 and G010 and isolated the
remaining G009 contract boundary; the v6 confirmation passed that branch, and the subsequent
unchanged ten-question cohort produced the directional results recorded above.

## Decision

The next RAG version should be one bounded pipeline with four cooperating parts:

1. decompose complex questions into explicit answer requirements and retrieval facets;
2. treat factual premises as hypotheses that require supporting and counterevidence;
3. distinguish direct subject evidence, bounded related evidence, analogues, and genuine
   insufficiency;
4. generate a concise answer from a validated source-coverage ledger.

The implementation name for the fourth part will be **evidence coverage**, not
“completeness.” `EVAL_CONTRACT.md` already defines completeness as the share of factual claims
carrying citations. Reusing that word for answer adequacy would silently change a locked metric.

This design does not change the gold set, grading rules, or evaluation contract. It opens a new
retrieval-and-prompt cohort when enabled.

## Why these are the next targets

The clean semantic/hybrid paired run separated source breadth from answer quality:

- hybrid retrieval increased final passages from 62 to 79 across the ten questions;
- average document breadth increased from 1.8 to 3.0 documents per question;
- expected document-group coverage increased from 12/26 to 15/26;
- strict claim coverage remained 19/58 in both cohorts.

The failures then divided into four useful classes:

- broad questions still needed several distinct searches rather than a more diverse result from one
  search;
- a question containing a false origin premise never retrieved the competing origin frame;
- an absent named subject attracted a semantically similar analogue;
- some source-present details were omitted by the answer even after retrieval found them.

The next version should address those mechanisms directly. Raising the source limit again would
mix more passages into the same undifferentiated prompt without telling retrieval what is missing
or generation what must be covered.

## Design boundaries

- Keep the engine corpus-agnostic. Production code must contain no people, dates, chapters,
  historical eras, or expected answers from the private test set.
- Preserve one retrieval core for CLI and web Answer Mode.
- Keep deferred Index Mode on its existing semantic-only path.
- Preserve the original resolved question as a global retrieval lane in every plan.
- Treat planner output as search control, never as evidence.
- Use only returned manuscript sources for factual answers and premise corrections.
- Keep the existing `[Source N]` citation grammar.
- Persist only hashes, counts, enum values, IDs, ranks, and chunk/source numbers in normal
  diagnostics. Raw questions, generated probes, manuscript text, and answer units may appear only
  in private gitignored evaluation artifacts.
- Do not add an automatic second generation or retry call in version 1.
- A formal run of record still requires dated model snapshots. The development model alias remains
  useful only for directional runs.

## Proposed pipeline

```text
current user turn
    |
    v
follow-up resolver, when history exists
    |
    v
deterministic route and trusted-anchor extraction
    |
    +---- focused question -------------------------+
    |                                               |
    +---- broad / multi-part / premise-sensitive ---+--> question plan
    |                 one structured planner call   |
    |                                               v
    +---- absence-sensitive, locally detectable --> faceted hybrid retrieval
                                                    one batched embedding call
                                                        |
                                                        v
                                              corpus evidence gate
                                                        |
                         +------------------------------+----------------------+
                         |                              |                      |
                   clean abstention              bounded near match      answerable
                   no answer call                 related lane only           |
                                                                                v
                                                              structured evidence-coverage
                                                              answer, one generation call
                                                                                |
                                                                                v
                                                              deterministic validation/render
```

Focused questions should retain the current cost and behavior until the evidence-coverage stage is
deliberately enabled for their cohort. Complex routing adds one compact planning call. All search
facets should be embedded together in a single request.

## Shared contracts

Use Pydantic models as the source of truth for both application types and JSON schemas. The
installed OpenAI SDK supports `client.responses.parse`, and OpenAI recommends native Pydantic
support to keep code and JSON Schema from diverging. Structured Outputs guarantee schema shape,
not factual correctness, so all IDs, counts, query constraints, and citation relationships still
need local validation. See the official
[Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).

The in-memory contract should have four layers:

```python
QuestionPlan
    schema: "archivist.question_plan/1"
    traits: tuple[
        "broad_synthesis" | "multi_part" |
        "premise_sensitive" | "absence_sensitive"
    ]
    requirements: tuple[AnswerRequirement, ...]
    facets: tuple[SearchFacet, ...]
    premises: tuple[PremiseHypothesis, ...]
    targets: tuple[EvidenceTarget, ...]
    planner_used: bool
    fallback_reason: str | None

AnswerRequirement
    requirement_id: str
    label: str
    order: int
    required: bool

SearchFacet
    facet_id: str
    requirement_ids: tuple[str, ...]
    role: "original" | "origin" | "transition" | "mechanism" |
          "endpoint" | "premise_support" | "premise_counter" |
          "framing" | "broader_related"
    search_query: str
    document_hints: tuple[str, ...]

PremiseHypothesis
    premise_id: str
    proposition: str
    support_facet_id: str
    counter_facet_id: str
    framing_facet_id: str | None

EvidenceTarget
    target_id: str
    query_surface_span: str
    role: "subject" | "facet"
    absence_checkable: bool
```

Labels, propositions, spans, and queries exist in memory because the model and local scanner need
them. The persisted trace stores their stable IDs, hashes, lengths, and classifications instead.

Version 1 limits:

- at most eight answer requirements;
- at most eight search facets, including the unchanged original question as `F0`;
- at most two premise hypotheses and three evidence targets;
- at most two exact catalog document hints per search facet;
- at most 240 characters per search query and 1,200 characters across added queries;
- no duplicate normalized search queries.

## 1. Query decomposition

### Routing

Run a deterministic, high-recall pre-router before any planner call. Traits are composable rather
than mutually exclusive.

Route to planning when the resolved question contains one or more of:

- broad lineage or change-over-time language;
- explicit start/end spans;
- coordinated subquestions or enumerated requests;
- requests for several causes, mechanisms, stages, comparisons, or consequences;
- a factive construction that assumes an attributed proposition is true;
- an explicit request about whether or how the manuscript treats a named subject.

Neutral focused requests such as “what does the book say about this subject?” should not become
premise-sensitive merely because they name the book. High-precision premise triggers include an
attributed assertion followed by a “why” or “how” that presupposes it.

Trusted evidence-target extraction is local and may run for any question. It recognizes only
conservative surface forms from the user’s own text: quoted phrases, multi-token proper names,
acronyms, hyphenated identifiers, and named numeric forms. A model-generated synonym can drive
discovery but can never certify presence or absence.

### Planner input and output

The planner receives:

- the resolved standalone question;
- an eligible document catalog containing document ID, chapter title, and corpus ordinal;
- instructions to decompose the request without answering it.

It does not receive prior assistant answers, expected claims, gold locations, or grading material.
It should not receive manuscript passages in version 1. This keeps the planning task separate from
evidence adjudication and prevents an initially retrieved passage from anchoring the whole plan.

The application always inserts the original question as global facet `F0`; the model may add no
more than seven facets. Planner-generated document hints are optional. They are accepted only when
they exactly match the eligible catalog and never replace `F0`.

Use a separate `QUERY_PLANNER_SETTINGS` role with the development model at low reasoning and low
verbosity. Give it a small structured-output ceiling, explicitly disable SDK retries, and record
the call as `query_planning`.

### Validation and fallback

Reject a plan that has:

- unknown, duplicate, or dangling IDs;
- unknown document hints;
- missing requirement-to-facet mappings;
- duplicate or oversized queries;
- a facet with no meaningful token shared with the question or a selected catalog title;
- claims framed as established answers rather than search hypotheses.

Do not pay for a planner retry. Fall back once to deterministic decomposition:

- a start/end construction becomes origin, endpoint, and relationship facets;
- coordinated clauses become separate requirements/facets;
- an origin assertion becomes a neutral origin facet plus event-role and earlier-framing facets;
- otherwise use only `F0`.

Planner refusal, timeout, invalid output, or low budget headroom must leave a usable standard
retrieval path.

### Faceted retrieval

Add a planned wrapper beside `retrieve_from_collection()`; do not fork a second ranking system.

1. Embed all unique facets in one batched `query_embedding` operation.
2. Run Chroma and local BM25 for each lane.
3. Reuse the existing hybrid fusion for each lane.
4. If a facet has document hints, filter both semantic and lexical candidates to those documents.
5. Do not apply the current all-distant fallback to scoped or verification lanes. A bad hint is a
   `no_hit`, not permission to force irrelevant evidence.
6. Select one accepted anchor per live facet before any facet receives a second.
7. Reserve premise-support, premise-counter, and framing anchors before filling spare positions.
8. Prefer a new document on the first pass for broad synthesis, but never select a passage merely
   to satisfy diversity.
9. De-duplicate chunks and keep all selected anchors ahead of optional neighbors.
10. Retain the current eight-source ceiling for the first cohort.
11. For broad synthesis, order the selected context by corpus ordinal after ranking so the model
    sees a coherent sequence.

The result is a `PlannedContext` containing ordered chunks, evidence-lane labels, and a
`facet_id -> source_numbers` map. This map is an input to evidence coverage, not a declaration that
the sources actually support the facet.

## 2. Premise checking

A premise-sensitive question must not be allowed to determine its own evidence frame.

The question plan turns each detected proposition into a hypothesis and creates:

- a support lane;
- a counterevidence lane;
- an origin/framing lane when the proposition concerns chronology, causation, or first occurrence.

The original wording remains in `F0`, but premise lanes receive reserved context positions.
Planner prose is never shown to the user and never counts as evidence.

Version 1 should not add a separate premise-verifier call. The structured answer call sees the
hypothesis and the numbered sources, then returns one of:

- `supported`;
- `contradicted`;
- `unresolved`;
- `not_applicable`.

Prompt behavior:

- `contradicted`: lead with a source-cited correction, then answer the useful underlying question;
- `unresolved`: state that the retrieved manuscript passages do not establish the proposition;
- `supported`: answer normally without repeating the premise as filler;
- distinguish an origin from a later development, example, escalation, or turn when the sources do;
- never correct or confirm from general knowledge.

Premise correction takes precedence over the absence gate. If retrieved sources contradict the
premise, the app should correct it rather than decline merely because the premise’s exact wording
does not occur.

## 3. Absence and near-match handling

The current lexical search treats tokens independently. A passage can therefore rank highly even
when a multiword subject never appears as a unit. Semantic similarity can then turn a peer
institution or broader event class into an apparent answer. Prompt wording alone cannot reliably
repair that source-selection error.

### Corpus scanner

Add a local, zero-model-call scanner over every retrieval-eligible chunk. Use a dedicated anchor
tokenizer that:

- performs Unicode normalization and case folding;
- normalizes apostrophes and possessives;
- treats hyphens and spaces as equivalent;
- retains numeric identifiers;
- checks compact mechanical forms;
- does not invent aliases.

Classify direct evidence as:

- **strong**: an exact normalized full-token-sequence hit;
- **weak**: every anchor token occurs within a 12-token window, or a mechanically derived
  initialism occurs without an expansion;
- **partial token collision**: never direct evidence, regardless of BM25 score;
- **semantic-only**: ranking evidence only, never proof that a named subject is present.

Certified direct absence is allowed only when:

- the target is conservatively marked `absence_checkable`;
- corpus integrity passes;
- strong and weak hit counts are both zero.

Corpus integrity means the loaded eligible chunks match the manifest identity and the collection
count expected for that corpus. A mismatch produces `indeterminate`, never a claim of absence.

### Evidence lanes and decisions

Every selected candidate receives one lane:

- `direct`;
- `broader_related`;
- `analogue`;
- `generic_semantic`.

Related probes may be supplied by the query planner, but they do not become trusted aliases. A
broader-class passage qualifies only when an exact broader term and at least one additional
related-probe term occur in the same chunk or an immediate neighbor.

An analogue is never passed to answer generation as if it concerned an absent named target.
Generic semantic-only passages are likewise suppressed on an absence route.

For a directly present subject, a requested relationship is supported only when subject and facet
evidence co-occur in the same chunk or an immediate neighbor. The system must not join distant
passages into a synthetic relationship.

The evidence gate returns:

| Decision | Condition | Behavior |
|---|---|---|
| `direct_answer` | Direct subject and relevant facet evidence | Normal source-grounded answer |
| `partial_answer` | Subject present, requested relationship incomplete | Answer supported parts and identify the gap |
| `qualified_near_match` | Certified direct absence plus safe broader material | State the boundary first, then give only the bounded related discussion |
| `clean_abstention` | Certified direct absence and no safe related material | Deterministic minimal response; skip answer generation |
| `indeterminate` | Ambiguous alias, conceptual target, or corpus-integrity failure | Cautious insufficiency response; never assert corpus-wide absence |

Reader-facing language must remain calibrated:

- direct-absence finding: “I could not find a direct mention in the searchable manuscript”;
- insufficiency: “The retrieved passages do not establish this relationship”;
- never: “the book definitely never discusses this” unless a future, separately validated
  contract supports that stronger claim.

Only positive claims about related material receive manuscript citations. The local scan result is
search metadata, not a disguised `[Source N]` citation.

## 4. Source-bounded evidence coverage

### One structured call, not draft plus critic

The first implementation should plan coverage and write the answer in the same structured
generation call. A draft/revision pair roughly doubles serial generation work, can cause the
second call to endorse the first call’s omissions, and creates another opportunity to introduce
unsupported claims.

The answer call receives:

- ordered answer requirements derived from the question;
- premise and absence decisions;
- ordered numbered manuscript sources;
- the existing interpretive settings, when non-neutral.

It returns:

```python
EvidenceCoverageAnswer
    schema: "archivist.evidence_coverage/1"
    premise_decisions: tuple[PremiseDecision, ...]
    coverage: tuple[RequirementCoverage, ...]
    answer_units: tuple[AnswerUnit, ...]

PremiseDecision
    premise_id: str
    status: "supported" | "contradicted" | "unresolved" | "not_applicable"
    source_numbers: tuple[int, ...]

RequirementCoverage
    requirement_id: str
    status: "supported" | "partial" | "unsupported" | "conflicting"
    unit_ids: tuple[str, ...]
    source_numbers: tuple[int, ...]
    gap_reason: "none" | "no_direct_support" | "partial_support" | "source_conflict"

AnswerUnit
    unit_id: str
    requirement_ids: tuple[str, ...]
    role: "definition" | "identity" | "cause" | "mechanism" | "event" |
          "consequence" | "quantity" | "counterargument" |
          "qualification" | "chronology"
    text: str
    source_numbers: tuple[int, ...]
    paragraph: int
```

The prompt requires the model to:

1. inspect every source for each requirement;
2. look explicitly for causal links, mechanisms, quantities, chronology, counterarguments, and
   qualifications relevant to that requirement;
3. ignore tangential passages rather than trying to mention every source;
4. produce at least one answer unit for every supported requirement;
5. leave unsupported requirements unsupported rather than filling them from memory;
6. state only retrieved-evidence insufficiency unless the absence gate supplied a corpus-scan
   certificate;
7. preserve requirement or chronological order;
8. emit `[Source N]` in each factual unit.

Neutral answers remain compact. Compact means no conversational filler; it does not mean omitting
source-supported requirements. Broad questions may use one concise bullet per supported stage
rather than the current universal one-to-three-paragraph limit.

Interpretive settings may alter diction and organization only after the evidence requirements are
fixed. They must not alter retrieval, coverage status, premise status, or source selection.

### Local validation and rendering

Before an answer is displayed:

- require exactly one coverage record per input requirement, in order;
- reject unknown, missing, or duplicate requirement, premise, facet, or unit IDs;
- require `supported` and `partial` requirements to reference existing units;
- forbid factual units for `unsupported` requirements;
- require all declared source numbers to be within `1..N`;
- parse each unit’s citations with the locked citation grammar;
- require cited source numbers to equal the unit’s declared source numbers;
- require every unit to map to a requirement and every referenced unit to exist;
- realize every validated unit exactly once;
- enforce bounded unit counts and text length.

The renderer builds the final answer only from validated units and deterministic gap language.
This guarantees schema conformance, coverage bookkeeping, and citation resolvability. It does not
prove that a cited passage entails a claim; existing and future faithfulness evaluation remains
necessary.

Failure behavior:

- no sources: deterministic retrieved-evidence insufficiency response;
- all requirements unsupported: deterministic insufficiency response;
- conflicting sources: show the conflict and cite both sides;
- invalid or refused structured output: return `generation_contract_failed`, do not show
  unvalidated prose, and do not automatically retry;
- partial support: answer the supported portion and name the unresolved requirement using only
  question-derived language.

The answer remains a normal string in the existing API response. Safe status and count fields may
be added without exposing the private structured ledger.

## Precedence rules

Apply decisions in this order:

1. corpus-integrity failure;
2. source-backed premise contradiction;
3. direct subject and facet evidence;
4. partial direct evidence;
5. certified absence with a qualified broader match;
6. certified absence with clean abstention;
7. indeterminate insufficiency.

No later step may promote an analogue or semantic-only passage into direct evidence.

## Observability, run identity, and privacy

Bump the Answer Mode trace schema and add text-free `plan`, `evidence`, and `generation_contract`
sections.

Record:

- question and facet hashes plus character/token counts;
- planner prompt, schema, model, reasoning, verbosity, and settings hashes;
- route traits, facet roles, catalog-hint document IDs, fallback reason, and plan version;
- embedding model, batch size, per-lane candidate counts, ranks, and no-hit status;
- multi-lane aggregation policy, caps, and selected chunk IDs;
- corpus manifest/chunk hashes and integrity checks;
- evidence-target hashes, strong/weak hit counts, evidence lanes, and decision rules fired;
- requirement/facet/premise IDs and their source-number mappings;
- coverage-status counts, answer-unit count, citation count, validation result, and stable error
  codes;
- exact token usage, estimated cost, elapsed time, and operation name.

Normal traces must not contain raw questions, target strings, facet queries, prompts, answers, or
manuscript text. Extend `FileTraceSink` tests so a future field cannot bypass this rule.

New cost-ledger operations:

- `query_planning`;
- `query_embedding` for the batched facets;
- existing `followup_resolution`, when applicable;
- existing `answer_generation`.

Run identity must also include the planning policy version, anchor-normalizer version,
evidence-gate thresholds, aggregation policy, structured schema hash, answer prompt hash, and
renderer version. Any change opens a new cohort.

## Cost and latency policy

- A focused turn remains one query embedding and one answer generation, plus follow-up resolution
  only when conversation history requires it.
- A planned turn adds one low-reasoning planner generation. Multiple facet embeddings are batched
  into one request; their token cost grows with query text but should remain small relative to
  answer generation.
- A certified clean abstention skips answer generation and may be cheaper than the current
  always-answer path.
- There is no hidden planner retry, answer retry, judge, verifier, or critic call.
- The ledger must show each operation separately so the new quality gain can be compared with its
  incremental cost and latency.

No dollar estimate should be promoted until representative requests have been measured with the
actual planner schema and model settings.

## Implementation shape

Suggested modules:

- `src/query_planning.py`: route traits, Pydantic contracts, planner prompt, validation, and
  deterministic fallback;
- `src/evidence_policy.py`: trusted-anchor normalization, corpus scan, lane classification, and
  evidence decision;
- `src/answer_coverage.py`: structured answer contracts, validator, renderer, and text-free
  diagnostics;
- `src/answer_generation.py`: the one shared tracked structured-generation call;
- `src/retrieval.py`: batched faceted retrieval and multi-lane aggregation built from the existing
  hybrid core;
- `src/model_config.py`: separate planner settings;
- `src/costs.py`: tracked structured-output wrapper without losing usage accounting;
- `src/prompts.py`: versioned planning, premise, absence-boundary, and evidence-coverage
  instructions while preserving the old baseline prompt;
- `src/web_project.py` and `src/ask.py`: delegate to the same Answer Mode orchestrator;
- `src/web_api.py`: preserve `answer` and `sources`, optionally add safe decision/status counts.

Feature policy:

```python
RagPolicy(
    version="evidence-planned-v1",
    decomposition=True,
    premise_checking=True,
    absence_gate=True,
    evidence_coverage=True,
)
```

Keep the previous policy callable for baseline reproduction. Do not scatter environment-variable
checks throughout ranking and prompting; choose one policy at the orchestration boundary and log
it.

## Test plan

All first-pass tests are local and synthetic. They must not include manuscript or gold text.

### Planning and retrieval

- broad, multi-part, premise-sensitive, and neutral focused routing;
- malformed, oversized, duplicate, dangling, and query-drift plans;
- unknown document hints and scoped no-hit behavior;
- one batched embedding operation for multiple facets;
- one anchor per live facet before second anchors;
- premise lanes reserved without displacing the original lane;
- no neighbor displaces a selected facet anchor;
- eight-source cap and chronological ordering;
- planner failure falls back without a paid retry;
- CLI/web use the same planning and retrieval core.

### Absence and premise

- absent named subject plus a close analogue produces clean abstention;
- exact lexical hit beyond the semantic threshold remains direct evidence;
- partial multiword token collisions never count as direct;
- possessive, hyphen, spacing, acronym, and numeric normalization;
- broader class plus a second related term can qualify a bounded near match;
- a broad term alone cannot qualify;
- direct subject plus absent relationship produces partial support;
- analogue and generic semantic lanes never enter an absence-route prompt;
- all-distant fallback cannot override the evidence gate;
- corpus mismatch produces `indeterminate`;
- clean abstention makes zero answer-generation calls;
- premise contradiction takes precedence and is source-cited.

### Evidence coverage

- missing, duplicate, unknown, and out-of-order IDs;
- out-of-range, missing, malformed, and mismatched citations;
- unsupported requirements containing factual units;
- supported requirements missing units;
- partial and conflicting support;
- deterministic unit rendering and chronological ordering;
- exactly one generation call;
- refusal and invalid structured output fail closed;
- interpretive style cannot change evidence mappings;
- traces remain text-free.

### Regression

- existing standard retrieval behavior remains available;
- existing baseline prompt stays byte-identical and its hash test continues to pass;
- deferred Index Mode remains semantic-only;
- source labels and API response compatibility remain intact;
- full backend and frontend suites pass.

## Measurement sequence

Build the shared plumbing once, but measure the mechanisms separately before enabling the
integrated policy.

1. **Offline contract cohort:** synthetic planner, lane, scanner, validator, renderer, trace, and
   failure tests. No OpenAI calls.
2. **Frozen-context generation isolation:** reuse the private clean-hybrid contexts. On questions
   where expected material was already present, measure whether evidence coverage realizes more of
   it. On broad questions with missing eras, verify that the system reports gaps rather than
   inventing connective tissue.
3. **Retrieval isolation:** run decomposition, premise lanes, and the absence gate without
   generating answers. Compare target-group breadth, direct/analogue classification, and false
   abstention behavior.
4. **Integrated ten-question cohort:** run the unchanged questions and rubric with a fresh run
   identity. Report claim coverage, contradictions, citation metrics, behavior on the false premise
   and absent subjects, cost, and latency.
5. **Repeat before strong claims:** one nondeterministic run remains directional.

`source_available_claim_realization` may be reported as an additional diagnostic: among expected
claims independently judged present in the supplied context, how many appeared in the answer. It
must not be called the contract’s completeness metric or replace independent grading.

Private acceptance gates for the unchanged test set:

- the broad questions retrieve materially more of their expected historical span;
- the false-premise question retrieves both the assumed frame and a competing origin frame, and
  the answer corrects rather than accepts the premise;
- the clean-abstention case does not substitute an analogous subject;
- the bounded-near-match case reaches the relevant broader discussion without inventing a
  subject-specific treatment;
- source-present omissions improve without a contradiction regression;
- no previously answerable test question falsely abstains;
- every emitted citation remains syntactically valid and resolvable;
- incremental cost and latency are reported by operation.

These gates belong only in the private evaluation harness. Production code and committed fixtures
must remain free of their expected documents and claims.

## Explicitly deferred

- a second draft/critic generation pass;
- model-based absence adjudication;
- a separate premise-verifier call;
- a larger context window or more than eight final sources;
- reranking-model purchases;
- changes to the locked evaluation metrics or gold answers;
- personality-specific evidence selection;
- Index Mode changes.

Each deferred item should be reconsidered only if the measured version-1 failure points to it.
