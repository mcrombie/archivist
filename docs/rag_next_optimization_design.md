# Next RAG optimization: evidence-planned answers

Status: evidence-planned-v15 implemented, verified offline, and measured in both a focused paid
G006/G007 gate and the complete unchanged ten-question cohort on 2026-07-29
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

The `evidence-planned-v7` cohort implements those three measured boundaries without changing the
corpus, index, frozen evaluation, model settings, eight-source cap, or one-generation-call design:

- query-planner input includes application-owned route traits. A provider premise is rejected
  unless local routing already marked the question `premise_sensitive`, and the evidence gate
  repeats that condition before widening context for premise evaluation;
- unbounded manuscript-treatment questions without a conservative named target route as broad
  synthesis. Broad proposals require at least two ordered requirements with a dedicated facet for
  each, and deterministic fallback reserves origin, development/mechanism, and endpoint lanes;
- direct-anchor promotion admits at most one certified hit per target scan, then protects one
  source for each answer requirement, premise side, and live broad facet before filling remaining
  positions. Text-free trace counts expose requested/deferred anchors and protected-source
  shortfalls;
- `archivist.evidence_coverage/2` separates premise-correction units from ordinary requirement
  units. Exact post-gate support, counter, and framing source scopes are passed to generation and
  validation. A contradicted premise must cite the correction’s exact sources and include a
  retained framing source when available; the underlying requested answer must be covered in
  separate units.

No OpenAI request was made while implementing v7. The complete offline suite passes with 416 tests
and one intentional skip, and Ruff passes. These checks establish contract behavior only; v7 has
not yet demonstrated better claim or document-group coverage on the unchanged paid questions.

The focused v7 confirmation subsequently showed that those control repairs were real but
substantive coverage remained weak. G006 covered 1/8 strict claims and 2/8 target groups; G007
covered 0/7 and 3/5; G009 produced a valid qualification but selected Chapter 20 rather than the
required Epilogue. That evidence opened `evidence-planned-v8`:

- broad plans require an ordered origin, transition-or-mechanism, and endpoint chain;
- those lanes search application-owned early, middle, and late document bands;
- spare slots prefer an unseen document before same-document surplus, and protected stage
  sources reserve capacity before newly promoted anchors;
- trace schema 4 records safe chronology-band and stage-survival diagnostics;
- absence-sensitive planner facets may rank distant related material only when an exact validated
  document hint and every trusted subject/relation surface are preserved, with a two-source cap.

The complete v8 offline suite passes with 421 tests and one intentional skip; Ruff and
`git diff --check` pass. Its unchanged G006/G007/G009 confirmation completed without retries for
`$0.29427521`. G009 improved to about 3/5 strict claims and 1/1 target groups using exactly two
Epilogue passages. G006 improved modestly to 2/8 and 3/8. G007 remained 0/7 and fell to 2/5.
Because both broad traces reported 3/3 stages covered, v8 demonstrates that chronology-band
survival is a useful allocation invariant but an inadequate proxy for book-wide argument-stage
coverage. The full ten-question cohort remains gated pending a narrower broad-stage repair.

A subsequent controlled retrieval-only diagnostic tested whether the fixed source ceiling itself
was binding. For each of G006 and G007, one accepted live plan and one batched facet embedding
were reused at limits 8, 12, and 16; no answer or judge call was made. G006 target-group coverage
was 3/8, 3/8, and 6/8. G007 remained 3/5 at every limit. All larger contexts retained their eight
baseline chunks. The run cost `$0.05277158` across exactly two planner and two embedding calls.

The result splits the next work into independent cohort changes:

- a broad-only sixteen-source ceiling is justified for an answer-generation test because it
  recovered three additional G006 target groups;
- twelve sources has no measured advantage in this sample;
- G007 requires richer argument-stage planning or ranking because sixteen sources did not recover
  its missing early and endpoint groups;
- focused questions retain eight, and qualified absence retains its separate two-source cap.

The two follow-up gates resolved those candidates differently.

For G006, one accepted live plan and its embeddings were allocated at 8 and 16 sources and each
allocation received one structured generation. The eight-source context covered 2/8 target
groups; sixteen covered 6/8. The sixteen-source answer could not validate because the independent
evidence-coverage contract still bounds `source_count` at eight. Its already-paid stored
structured output was recovered without regeneration and inspected directly. It added several
intermediate institutions but still missed most of the unchanged lineage rubric, including its
modern endpoint. A broad-only sixteen-source production ceiling was therefore not adopted.

For G007, `query-planner-v6` now requires at least five ordered requirements with exactly one
dedicated narrative-stage facet per requirement: origin, at least three distinct
transition-or-mechanism stages, and endpoint. Deterministic fallback has the same five-stage
shape. Retrieval recognizes numbered-book structure, starts stage allocation at Chapter 1, ends
at conclusion or Epilogue, and excludes supplemental back matter from narrative chronology.

The first `evidence-planned-v9` confirmation accepted that live plan and validated its answer but
remained at 3/5 target groups. Its trace showed that rigid band boundaries excluded the
Revolutionary/Civil-War passages intended by adjacent queries, while the endpoint lane never
considered the Epilogue. `Evidence-planned-v10` therefore overlaps each adjacent stage by two
narrative documents and performs one additional endpoint-restricted Chroma lookup with the same
embedding. It does not add a planner call, embedding call, source slot, retry, or corpus-specific
chapter name.

A controlled v10 confirmation reused the exact accepted v9 requirements and queries. With only
retrieval behavior changed, G007 improved from 3/5 to 5/5 target-document groups, returned eight
sources, passed strict citation/source validation, and cost `$0.10395228` for one embedding and
one generation. The complete offline suite passes 422 tests with one intentional skip.

That result clears argument-stage allocation, not answer completeness. The returned passages and
answer still miss several required within-stage mechanisms: imperial conflict for the interior,
war debt as Hamiltonian federal power, Pentagon/employment, NSC-68 and Keynesian permanent
spending, NATO persistence, and the Epilogue's security-dilemma component. The next bounded
optimization target is passage-level mechanism query/ranking inside the five recovered stages.
The unchanged ten-question cohort remains gated.

`Evidence-planned-v11` implemented that bounded retrieval target without changing the source
limit, query planner, generator prompt, or operation count:

- within planner-hinted narrative documents, deterministic role-scoped lexical probes rank
  origin, fiscal/consolidation, institutional or military mechanism, and endpoint
  persistence/transformation evidence;
- broad coverage prefers distinct candidates for distinct stages when capacity allows and can
  protect one additional mechanism-bearing hinted document;
- mechanism queries and candidates are represented in trace schema 5 only by hashes, IDs, counts,
  and finite role labels;
- the complete offline suite passes 424 tests with one intentional skip, and Ruff and whitespace
  checks pass.

A zero-cost G007 replay was followed by one focused paid confirmation that reused the exact
accepted five-stage plan. The focused context covered 5/5 target document groups for an estimated
`$0.13844353`, but the answer still realized only about 1/7 strict claims. Much of the omitted
material was present in the selected passages, moving the dominant defect from stage retrieval to
source-bounded generation obligations.

The clean unchanged ten-question v11 cohort then completed at commit
`7ba7382ff48828c1c854034e2d78217751eba826` for an estimated `$0.91198718`. Directional grading
found 19/58 expected claims, 21/26 target document groups, and 8/10 high-level behaviors. This is
two more claims and four more target groups than v6 at slightly lower estimated API cost, but
total latency rose from 280.803 to 334.051 seconds. All 61 rendered citation tokens resolved.

Three bounded defects now replace the earlier full-cohort gate:

1. G001 and G009 found their expected source groups but failed closed on
   `citation_locality_invalid`;
2. broad stage labels remain too coarse to require every supported mechanism to appear in the
   answer; and
3. fresh broad planning remains variable: focused G007 covered 5/5 target groups while the clean
   cohort's accepted fresh plan covered 3/5.

The next implementation should address those boundaries separately and should reuse preserved
contexts for offline or zero-cost isolation before another paid full cohort. The frozen questions,
claims, target groups, and grading rules remain unchanged.

`Evidence-planned-v12` implements those three repairs without changing the frozen evaluation,
manuscript, index, eight-source ceiling, or one-planner/one-embedding/one-generation operation
budget:

- the answer schema exposes the exact atomic terminal-citation pattern to Structured Outputs, and
  the local normalizer removes only the observed redundant terminator shape
  `claim.[Source N].`; it changes no words, claims, or sources, while every other locality shape
  still fails closed with a text-free subtype;
- broad generation receives an ordered paragraph-addressable evidence-obligation ledger. Each
  obligation names one retained source range, its allowed requirement IDs, a generic narrative
  focus, and explicit evidence dimensions. Units must link back to exact obligation/dimension
  pairs with compatible roles and the same single source. Unsupported dimensions remain explicit,
  and a coarse requirement cannot remain fully supported when any required source-bound
  obligation is incomplete;
- when exact paragraph metadata and blank-line blocks agree, the ledger addresses each paragraph.
  A metadata mismatch becomes one source-wide range, while an unusually large context is
  deterministically coalesced to at most 32 contiguous ranges without dropping a source;
- broad retrieval derives one protected canonical query per narrative stage solely from unchanged
  F0 plus fixed position/role vocabulary. Provider queries and hints remain useful only in the
  supplemental pool. Canonical and provider embeddings share the same single batched API
  operation, and spare slots use global rank utility rather than earliest-facet order;
- retrieval trace schema 6 and evidence diagnostics schema 5 record only hashes, IDs, source and
  paragraph numbers, finite enums, mappings, and counts for these decisions.

The v12 offline suite passed 439 tests with one intentional skip; Ruff and whitespace checks
passed. Those checks established deterministic contracts, trace privacy, stage-core stability
under provider wording/hint/order variation, and paragraph-ledger validation, but did not establish
live model adherence or improved historical answers.

The clean focused G001/G007/G009 gate then spent an estimated `$0.49895119` in total with no retry.
G001 validated after the exact redundant-terminator repair, and G009 validated as a bounded
qualified near match. The first launcher stopped waiting after fourteen seconds even though the
G001 API operation had completed; the response was recovered by its stored provider ID instead of
being regenerated. G007 took 116.9 seconds and failed on `obligation_unit_mapping_mismatch`.

The G007 failure was an application-owned capacity defect, not evidence that the model had ignored
the ledger. V12 supplied 32 paragraph obligations containing 84 dimension slots while the answer
schema allowed only 32 units. The generated structure attempted 61 unit IDs, including 29 IDs that
could not exist in the bounded schema. `Evidence-planned-v13` assigns one rotating historical
dimension to each paragraph obligation, reserves answer-unit capacity for any premise corrections,
and rejects an over-capacity trusted context with
`obligation_dimension_capacity_exceeded`. A zero-cost replay of the same G007 scopes reduces the
ledger from 84 to 32 dimension slots while retaining all 32 source ranges and representation of all
six historical-function dimensions. The v13 suite passes 441 tests with one intentional skip;
Ruff and whitespace checks pass.

The G007-only v13 confirmation then completed once without retry in 102.9 seconds for an estimated
`$0.26043497`. Its answer validated with 28 well-formed, resolvable citation tokens and no repair.
The capacity defect was therefore fixed. The content gate remained weak: directional strict
grading found 0/7 composite claims and 4/5 target document groups. The answer accounted for 28
selected paragraphs but did not reconstruct the requested mechanism chain.

The subsequent clean v13 cohort ran all ten unchanged questions at commit
`87bee716e5fcc79607c843e8ad3087bf2fe0ae08`. All ten completed once without retry for an estimated
`$1.22828221`; nine generated answers validated, and G008 cleanly abstained before generation. All
106 rendered citation tokens were well formed and resolved to returned sources. Directional strict
grading found 19/58 claims, 21/26 target document groups, no contradicted expected claim, and 10/10
high-level behaviors. Relative to the clean v11 sample, claim realization and target breadth were
unchanged, while the two previous contract failures became visible bounded answers.

The reliability gain came with a 37 percent increase in generation tokens, from 60,399 to 83,024,
and comparable increases in cost and latency. G006 and G007 produced 30 and 28 citations but only
one strict composite claim each. The next bounded repair is therefore not a larger context or a
second model call. It should choose protected broad-stage anchors by consensus across canonical,
mechanism, and provider-relevance pools, then distinguish paragraphs that must be inspected from
historical mechanisms that must become claims.

`Evidence-planned-v14` implements that two-part repair without changing the manuscript, index,
model configuration, eight-source ceiling, or one-generation-call boundary:

- `faceted-hybrid-rrf-v8` ranks each protected broad-stage anchor by reciprocal-rank agreement
  across three independent pools: the application-owned canonical route, the role-scoped mechanism
  route, and provider relevance. Three-pool agreement outranks two-pool agreement, which outranks
  a singleton; when no two pools agree, selection falls back in canonical, mechanism, then provider
  order.
- The selected anchor is retained by chunk identity through direct-anchor promotion, corpus-order
  sorting, evidence gating, and final source renumbering. Text-free lane diagnostics record pool
  names, ranks, hit counts, and the selected anchor without persisting query or manuscript prose.
- `evidence-coverage-v6` separates `inspection_passages` from `synthesis_obligations`. Every
  retained source range remains part of the source-bounded inspection pass, but supplemental
  paragraphs no longer force one answer unit merely to prove inspection.
- Only the protected anchor for each surviving broad stage creates a synthesis obligation. That
  obligation uses only the stage facet's requirement IDs and all role-compatible dimensions, with
  deterministic capacity trimming that preserves at least one dimension per stage.
- Ordinary relevant units may remain unlinked to a synthesis obligation. Linked units retain the
  stricter one-source, role, requirement, citation, and dimension checks, and a requirement still
  cannot be marked supported when any required synthesis dimension is missing.

The closed trace contract is now `archivist.retrieval_trace/7`, and the answer request is
`archivist.answer_request/3`. The full offline suite passes 476 tests with one intentional skip.

The subsequent unchanged G006/G007 gate ran once at clean commit
`8becb2193303f79814c5f080db532541b539b789`, with no retry, for an estimated `$0.40612293`.
Both answers validated, used eight sources, and emitted 33 well-formed, resolvable citation tokens.
The inspection/synthesis split reduced v13's forced output, but strict content grading did not
improve: G006 scored 0/8 claims and 4/8 target groups; G007 scored 1/7 claims and 4/5 target groups.
G006 gained Chapter 20 while losing another modern target, and G007 gained the Civil War target
while losing the Jamestown origin target.

The result rejects consensus rank as a sufficient relevance test. Every protected stage anchor
survived, and several had agreement from all three pools, but G006's middle stage still settled in
Chapter 15 and G007's origin stage settled in Chapter 2. A high-confidence answer to an imprecise
stage query remains the wrong anchor. The next bounded repair must make stage intent constrain
anchor relevance and require the generated synthesis to state the causal or institutional link
between surviving stages. The full ten-question rerun remains held because the focused gate missed
its strict-claim and target-group thresholds.

`Evidence-planned-v15` implements that repair as two explicit fail-closed contracts:

- `faceted-hybrid-rrf-v9` derives each stage's intended historical function from its dedicated
  requirement label and search facet. Before consensus ranking, a candidate must match the
  distinctive stage intent and a corpus-agnostic, role-appropriate historical signal: formation or
  enabling for origins; change, consolidation, or financing for transitions; implementation or
  institutional mechanism for mechanism stages; and persistence, transformation, or consequence
  for endpoints.
- Consensus still ranks canonical, mechanism, and provider routes, but only inside that eligible
  set. An ineligible three-route agreement cannot defeat an eligible lower-consensus passage, and
  no canonical or provider fallback can conceal an empty eligible set. A missing eligible anchor is
  recorded as a stage shortfall and creates no synthesis obligation.
- The trace records only hashes, term counts, match counts, role-signal counts, finite eligibility
  codes, and chunk IDs. It does not persist requirement labels, facet queries, or manuscript text.
- Each pair of surviving consecutive stage anchors creates a required
  `adjacent_stage_link` obligation in addition to its ordinary stage obligations. The link carries
  the two ordered requirement IDs and names the predecessor source for orientation, but the claim
  is bound to the later-stage source.
- A link can be supported only by one atomic cause-or-mechanism unit that maps to both requirements
  and whose later source explicitly states a causal or institutional continuation,
  transformation, or departure. Independent truth at the two stages is not enough. If the later
  source does not state the relationship, the model must mark the link unsupported; both affected
  requirements are then prevented from claiming complete support.

This opens retrieval trace schema `archivist.retrieval_trace/8`, answer request
`archivist.answer_request/4`, evidence coverage `archivist.evidence_coverage/4`, and diagnostics
`archivist.evidence_coverage_diagnostics/6`. It keeps `query-planner-v6`, the pinned models, the
same eight final sources, one batched embedding operation, one answer-generation operation, no
retry, and no second critic or verifier. The complete offline suite passes 483 tests with one
intentional skip; focused Ruff checks pass. No OpenAI request was made while implementing or
verifying v15.

The unchanged v15 G006/G007 gate then ran once at clean commit
`5b37e72bdf8069dd59db6c2b8a6c31e14f6dd3e9`, with no retry, for an estimated
`$0.54793856`. The owner test-set, practical rubric, corpus, private index, model settings,
neutral interpretation, eight-source limit, and operation count matched the v14 gate. Both answers
validated, and all 39 citation tokens resolved to returned sources.

The quality gate did not clear. Strict grading found G006 at 1/8 claims and 3/8 target groups, and
G007 at 0/7 claims and 4/5 target groups. Relative to v14, the pair remained at one strict claim in
aggregate and fell from eight to seven covered target groups. This result originally held the full
ten-question rerun while the next repair was being designed.

The result separates two effects:

- the adjacent-link contract behaved correctly as an absence boundary. G006 supported one of
  three required links and G007 one of four; every other link was recorded as
  `no_direct_support`, and the affected requirements were downgraded rather than completed with
  invented connective tissue;
- role eligibility remained too generic to guarantee requirement relevance. G006 reported one
  canonical-stage shortfall but still reached only three frozen target groups. G007 satisfied all
  five canonical stages while admitting a Chapter 2 imperial-war passage for the origin stage and
  missing the required Jamestown group.

An origin-like, transition-like, or endpoint-like vocabulary is therefore not enough. The next
bounded repair should require an eligible anchor to cover the planned stage's distinctive named
institution, actor, event, or mechanism before role and consensus ranking apply. Cross-stage
evidence should be retrieved through a dedicated transition lane scoped to each adjacent
requirement pair, rather than presumed to occur in the later stage anchor. That design can retain
one batched embedding request, eight final sources, one answer generation, and no retry.

The owner subsequently chose to measure the whole system before another repair. The unchanged
ten-question v15 cohort ran once at clean commit
`ad3017daad4d8efd0a9b7d96b310393ef433b6ad`, with the same frozen questions, 58-claim practical
rubric, corpus and index hashes, neutral interpretation, eight-source limit, pinned models, and
no-retry policy. All ten items completed exactly once. Eight planning calls, ten batched-embedding
calls, and nine answer-generation calls consumed 106,703 priced tokens for an estimated
`$1.11784972`; the clean absence case skipped generation. There were no unpriced events, API
errors, or retries.

Application mechanics passed across the cohort: all eight eligible plans succeeded, all nine
generated answers validated, all 85 citation tokens were well formed and resolvable, and all ten
high-level expected behaviors passed. Strict answer quality did not improve. V15 realized 18/58
essential claims and covered 21/26 target document groups, compared with 19/58 and 21/26 in the
clean v13 sample. Four of 25 listed failure modes were present and no frozen claim was contradicted.
Estimated cost fell 9.0 percent and generation tokens 2.5 percent, while total latency rose 8.0
percent in this single nondeterministic comparison.

The full profile changes the optimization priority. G006/G007 together remained at 2/15 strict
claims and 8/13 target groups, merely redistributing coverage relative to v13. But focused G002
and G005 also reached their expected document groups while realizing zero and one composite claims.
The next repair therefore needs both requirement-specific broad anchors with an adjacent-pair
transition lane and a stronger material-component completeness contract for focused answers.
Future focused smoke tests may verify mechanics, but should not indefinitely replace the unchanged
ten-question measurement.

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

The current implementation was verified with 422 passing offline tests and one skipped test,
strict provider-schema conversion, local inspection of the current private index, and replay of
preserved retrieval contexts. Earlier paid smokes verified narrower source-retention,
citation-structure, and relationship-routing behaviors. The v5 smoke passed G008 and G010 and
isolated a G009 contract boundary; the v6 confirmation passed that branch, and the subsequent
unchanged ten-question cohort exposed the three v7 targets recorded above. V8 received the
three-item directional confirmation described above; v9 and v10 received the bounded G007
confirmations recorded above. None is a full run of record.

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

That first-cohort ceiling has now been measured rather than assumed. A later retrieval-only
diagnostic found that sixteen sources doubled G006 target-group coverage from 3/8 to 6/8 but did
not improve G007 beyond 3/5; twelve improved neither. Any production change should therefore be
route-specific and should treat sixteen as a broad ceiling, not a quota or universal replacement.

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
    schema: "archivist.evidence_coverage/2"
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
          "qualification" | "chronology" | "premise_correction"
    text: str
    source_numbers: tuple[int, ...]
    paragraph: int

# Trusted application input, not model-owned output:
PremiseSourceScope
    premise_id: str
    support_source_numbers: tuple[int, ...]
    counter_source_numbers: tuple[int, ...]
    framing_source_numbers: tuple[int, ...]
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
8. emit `[Source N]` in each factual unit;
9. keep a premise correction separate from requirement coverage and, when framing candidates
   survive source selection, state the positive replacement frame using at least one of them.

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
- require ordinary units to map to a requirement and premise-correction units to map to none;
- validate premise decisions and corrections against exact support, counter, and framing source
  scopes supplied by the application;
- require every contradicted premise to use exactly one leading correction and require that
  correction to cite a retained framing source whenever one is available;
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
2. application-owned route classification and trusted-target extraction;
3. source-backed premise contradiction, but only for a locally premise-sensitive route;
4. direct subject and facet evidence;
5. partial direct evidence;
6. certified absence with a qualified broader match;
7. certified absence with clean abstention;
8. indeterminate insufficiency.

No provider-created premise may override the application-owned route. No later step may promote an
analogue or semantic-only passage into direct evidence.

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
- broad proposals require dedicated requirements/facets and their protected sources survive
  direct-anchor promotion under the eight-source cap;
- protected broad anchors must pass stage-intent and historical-role eligibility before consensus,
  and an empty eligible set must remain an observable shortfall;
- adjacent surviving stages create source-bounded link obligations that cannot be satisfied by
  juxtaposing independently true passages;
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
- planner-created premises cannot override an application-owned absence-only route;
- premise contradiction takes precedence and is source-cited.

### Evidence coverage

- missing, duplicate, unknown, and out-of-order IDs;
- out-of-range, missing, malformed, and mismatched citations;
- unsupported requirements containing factual units;
- supported requirements missing units;
- premise corrections cannot satisfy answer requirements, and ordinary units cannot omit them;
- premise support/correction citations stay within their support, counter, and framing lanes;
- a retained premise-framing source is required in a contradicted correction;
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

## V16 implementation: material components and adjacent-pair evidence

The full v15 ten-question run showed two distinct completeness failures: some focused answers
retrieved the intended source groups but omitted material layers already present in them, while
broad answers still lacked passages that explicitly connected adjacent historical stages. V16
addresses both without increasing the eight-source ceiling or adding model calls.

### Focused material-component pass

For an ordinary focused question, application code now inspects only the already admitted sources
mapped to each requirement. It recognizes four bounded, source-visible component types:

- subject or definition;
- action or mechanism;
- significance or consequence; and
- qualification or counterargument.

A component becomes an evidence obligation only when its source contains both question/requirement
vocabulary and a finite lexical signal for that component. No component obligation is created
unless at least two distinct component types are detected for the same requirement. This threshold
prevents a simple one-fact question from being inflated merely because a passage contains a copular
verb. Premise-sensitive, absence-sensitive, and broad-synthesis routes retain their existing
specialized contracts and do not use this pass.

Each activated component is bound to one strongest admitted source and one requirement. The
structured answer must attempt it, map it to the compatible answer-unit role, and cite only that
source. A requirement cannot be marked fully supported while a required detected component is
missing. The detector does not assert a fact or use gold-answer language; it only turns visible
source structure into a completeness obligation.

### Stronger broad-stage anchors

Protected stage anchors now require distinctive stage content, not merely topic overlap plus a
generic origin/transition/mechanism/endpoint signal. The planner is explicitly instructed to name
the stage's distinctive institution, actor, event, or mechanism. When two or more distinctive
terms are available, an anchor must match at least two; when one is available, it must match that
one. A stage with no distinctive terms fails closed and produces an observable trace shortfall.
Only eligible candidates proceed to canonical/mechanism/provider consensus ranking.

### Dedicated adjacent-pair transition lane

Each adjacent planned stage pair now receives one neutral transition query combining both stage
intents with causal and institutional transition vocabulary. All facet, canonical-stage, and
transition queries remain in the same single batched embedding operation. The transition search is
restricted to the union of the two chronological stage scopes.

A transition candidate is eligible only when one passage:

1. matches the predecessor stage's intent;
2. matches the successor stage's intent; and
3. contains an explicit causal, institutional, continuity, replacement, or transformation signal.

Eligible transition candidates compete globally for the context slots remaining after protected
stage anchors, non-stage verification lanes, and the structural narrative endpoint. This preserves
the eight-source limit while preventing early facet order from automatically consuming spare
capacity. The text-free trace records required, satisfied, and shortfall counts plus hashes, IDs,
match counts, and finite eligibility codes.

An `adjacent_stage_link` obligation is now created only when a selected dedicated transition
passage survives evidence gating and source renumbering. The link cites that transition passage,
not the later stage anchor. If no passage directly states the connection, no later-stage source is
silently repurposed as connective evidence.

### Version and measurement boundary

The implementation cohort is:

- `evidence-planned-v16`;
- `faceted-hybrid-rrf-v10`;
- `broad-stage-role-eligibility-v3`;
- `adjacent-pair-transition-v1`;
- query planner prompt v7;
- evidence coverage prompt v8;
- answer request 5;
- evidence coverage 5 / interpretive coverage 3;
- evidence diagnostics 7 and normalizer 6; and
- retrieval trace 9.

Offline verification passed 489 tests with one intentional skip, and Ruff passed across `src` and
`tests`. No OpenAI call was made. These checks establish contract behavior, not answer-quality
improvement. The next quality measurement should be the owner's unchanged ten-question evaluation
under a fresh v16 cohort, with the same manuscript/index identity, model settings, neutral
interpretation, source ceiling, and no-retry policy used for the v15 comparison.
