# Archivist — Defect Log

Entry format:

```
## [YYYY-MM-DD] Short title
Phase/Brief: <which phase and brief surfaced this>
Symptom: what was observed, stated as an observation rather than a diagnosis
         (e.g. "completeness fell 12 points with no prompt change")
Cause: contract edited / gold entry changed after a result / presentation change moved a
       metric / corpus logic leaked into engine / retrieval primitive duplicated /
       Phase 2 concern in Phase 1 work / noise floor exceeds claimed effect /
       manuscript text committed / spec gap in the brief / model error / other
Resolution and verification: what changed, and what check now confirms it
```

Log an entry whenever:

- a gold entry or a metric definition is suspected of having been changed in response to a result
- a presentation-layer change moved a measured number
- corpus-specific logic has leaked into engine code — a person, place, or chapter name in a retrieval or generation path
- a retrieval primitive has been duplicated rather than parameterized
- a Phase 2 concern — Index Mode, persona, perspective modes — has crept into Phase 1 work
- a metric's run-to-run spread exceeds the effect being claimed from it
- manuscript text has entered a committed file
- a model alias appears in a run configuration where a dated snapshot was required
- a run cited as a run of record turns out to have had a dirty working tree
- **the brief itself was underspecified and the implementer had to invent a mechanic**

## Two entry kinds that are not defects but are logged here anyway

**Contract events.** Locking `EVAL_CONTRACT.md` §6 or §7 after the calibration pilot, and filling the §8.2 envelopes, are logged as dated contract events. They are not faults, but they are the moments at which comparability changes, and a reader tracing an old number back needs to find them.

**Cohort openings.** Any change to prompt text, model snapshot, sampling parameters, retrieval parameters, chunking parameters, or the corpus snapshot. Not a fault — this is the normal way the system improves — but earlier runs stop being comparable and the boundary has to be findable.

## Why the specification-gap entry matters

**A gap in the brief is a defect, logged the same as a code fault.** On the previous project most defects traced to specification gaps rather than to model output, and that pattern only became visible because they were counted. A brief that forces the implementer to invent a mechanic has failed at its job, and the invented mechanic is unreviewed by definition.

## Why the "wanted to change it" entry matters

`AGENTS.md` requires recording the impulse to improve retrieval before it has been measured. Those are not defects and do not get a numbered entry — they go in the relevant brief's completion notes. But if such a change is *made* before the baseline exists, that is a defect and belongs here, because the change can no longer be shown to have helped.

Entries below, most recent first.

---

## [2026-07-29] Eight chronological roles did not constitute an institutional lineage
Phase/Brief: Phase 1 evidence-planned-v18 unchanged ten-question evaluation
Symptom: G006 received the required eight-stage plan. Retrieval satisfied seven stage anchors,
six of seven transitions, and four of eight target document groups, yet the answer realized none
of the frozen strict claims. The selected stages formed a broad chronological sequence of
governing and economic regimes rather than the institutional succession requested.
Cause: spec gap in the brief - the v18 validator proves cardinality, advancing document hints,
and vocabulary-distinct roles, but it does not require a named institutional capacity to pass
from one bearer to the next or bind each role to both endpoints of the question.
Resolution and verification: repaired offline in `evidence-planned-v19`; paid quality measurement
is pending. Every long-lineage stage now declares a distinct bearer, inherited capacity,
transfer-or-transformation mechanism, and outgoing capacity. Each outgoing capacity must exactly
become the next stage's inherited capacity, explicit question endpoints bind the first and last
bearers, and generic-only handoff fields are rejected. Protected anchors must match both the bearer
and a concrete handoff term; adjacent transitions must match both stages, their shared capacity,
and an explicit transition signal. The generation ledger receives one source-bounded
`institutional_handoff` obligation per stage, while planner fields are marked as non-evidence
orientation. Corpus-agnostic regressions and the full offline suite passed (505 tests, one
intentional skip); Ruff and `git diff --check` passed. No paid calls were made, so the unchanged
G006 result remains the quality gate.

## [2026-07-29] Target-bearing broad context remained outside answer obligations
Phase/Brief: Phase 1 evidence-planned-v18 unchanged ten-question evaluation
Symptom: G007 returned all five expected target document groups, retained all five planned stage
anchors, satisfied all four transition searches, and produced a locally valid answer. The answer
nevertheless realized none of the seven frozen strict claims; several target-bearing passages
never entered a supported stage or transition unit in the generated answer.
Cause: spec gap in the brief - target breadth, planned-stage coverage, and answer-obligation
coverage are measured independently, but the contract does not require a selected passage that
carries a supported stage or handoff to be realized in the answer. Generic unsupported-link
notices can coexist with an otherwise valid broad answer.
Resolution and verification: unresolved. The next repair must bind supported stage and handoff
evidence to explicit answer obligations and distinguish a genuinely unsupported connection from
one whose relevant passage is present but unused. It must add no critic call, retry, gold hint,
or manuscript-specific rule.

## [2026-07-29] A five-stage plan falsely satisfied a longer institutional lineage
Phase/Brief: Phase 1 evidence-planned-v16 unchanged ten-question evaluation
Symptom: G006 asked for a long institutional lineage spanning eight expected historical roles.
The accepted plan contained only five stages, yet retrieval reported five of five stage anchors
and four of four transitions satisfied. The green counters overstated completeness, and the
answer realized none of the frozen strict claims.
Cause: spec gap in the brief - broad synthesis had a minimum-stage rule but no separate contract
for explicit institutional-lineage questions, no role-distinctness test, and no accounting for
the competition between stage anchors and transition passages under the eight-source ceiling.
Resolution and verification: resolved in `evidence-planned-v18`. An application-owned route trait
now requires exactly eight ordered, role-distinct stages for explicit long institutional
lineages, plus advancing exact document hints when a catalog is available. Ordinary broad
questions remain five-stage. Retrieval reserves the eight final source slots for the eight stage
anchors, prefers already selected stage sources for transition evidence, and reports stage and
transition capacity shortfalls separately in retrieval trace 10. Synthetic end-to-end coverage
retains all eight roles through generation. The full offline suite passed 500 tests with one
intentional skip, and Ruff passed across `src` and `tests`. No paid calls were made; gold-set
quality remains to be measured in the unchanged ten-question evaluation.

## [2026-07-29] Dedicated transition evidence was rejected by the older validation context
Phase/Brief: Phase 1 evidence-planned-v16 unchanged ten-question evaluation
Symptom: G007's final returned context covered all five expected target document groups, and its
retrieval trace reported four of five stage anchors plus four of four transition searches. The
application nevertheless paid for a full answer generation and then returned no usable answer
because local validation classified the context as `invalid_context`.
Cause: contract edited and spec gap in the brief - the v16 obligation builder correctly binds an
`adjacent_stage_link` to its selected dedicated transition passage, but the older
validation-context check still requires that link's source number to equal the successor stage
anchor's source number. Builder and validator tests exercised their own assumptions separately;
no end-to-end fixture used a transition source distinct from both stage anchors.
Resolution and verification: resolved in `evidence-planned-v17`. The validator now accepts the
dedicated transition passage as the link source while still requiring consecutive requirements,
exactly one surviving stage scope at each endpoint, the correct predecessor anchor, and in-range
source numbers. The same public trusted-context validator runs before answer generation and after
parsing, so an invalid local context fails with `structured_generation_called=false` before a paid
answer call. End-to-end synthetic regressions prove that distinct predecessor, successor, and
transition passages validate, while a missing successor stage fails before generation. The full
offline suite passed 494 tests with one intentional skip, and Ruff passed across `src` and `tests`.

## [2026-07-26] Valid source selections were discarded by citation-locality validation
Phase/Brief: Phase 1 evidence-planned-v11 directional ten-question evaluation
Symptom: G001 retrieved both expected document groups and G009 correctly stayed on the
qualified-near-match route with only the expected Epilogue group. Both paid for a full structured
generation and then returned no reader-facing answer because strict validation reported
`citation_locality_invalid`. G001 therefore regressed from its earlier valid answer, while G009
failed after the absence and near-match retrieval repairs had already succeeded.
Cause: model error and spec gap in the brief - the one-generation evidence-coverage contract can
still emit an answer-unit/citation shape that violates the application's atomic locality rule.
The failure is correctly closed, but diagnostics do not yet isolate a safe canonical repair from
a genuinely compound or unsupported unit.
Resolution and verification: unresolved. The next repair must preserve the existing citation
grammar and fail-closed validation, distinguish mechanically repairable locality shapes from
substantive multi-claim units, and prove the distinction with synthetic G001- and G009-shaped
fixtures before one focused paid confirmation. It must not move citations, split prose, or infer
support unless the transformation is deterministic and source scopes remain identical.

## [2026-07-26] Retrieved broad mechanisms were omitted by the answer contract
Phase/Brief: Phase 1 evidence-planned-v11 focused G007 confirmation and directional ten-question
evaluation
Symptom: the focused G007 confirmation returned passages covering all 5/5 expected document
groups, including source text for several required mechanisms, but its answer realized only about
1/7 strict claims. The clean ten-question run improved broad target coverage to 5/8 for G006 and
3/5 for G007, yet realized only 2/8 and 1/7 claims. Five high-level stage requirements did not
force the generator to state the source-present submechanisms inside those stages.
Cause: spec gap in the brief - retrieval obligations are stage-sized while generation
requirements remain too coarse to express the independently supportable mechanisms found within
each selected passage. A requirement can be marked covered even when only one part of its
historical mechanism reaches the answer.
Resolution and verification: unresolved. The next repair should derive explicit, source-bounded
mechanism obligations from the selected evidence and pass those obligations through the existing
coverage ledger. It must remain corpus-agnostic, use no private expected-answer text, add no
automatic critic or retry, and be tested first against preserved contexts before paid generation.

## [2026-07-25] Bounded absence retrieval chose adjacent contracting history instead of the requested near-match
Phase/Brief: Phase 1 evidence-planned-v7 focused paid confirmation
Symptom: unchanged G009 now routed and validated correctly as `qualified_near_match`, stated the
COVID/federal-contracting evidence boundary first, used exactly two bounded sources, and resolved
all citations. Both selected sources were from Chapter 20, however, and the answer discussed
post-Soviet layoffs and post-Al-Qaeda contracting. It omitted the Epilogue's generic pandemic,
supply-chain, reshoring, and military-spending treatment required by the unchanged rubric. Strict
coverage was 2/5 claims and 0/1 target groups.
Cause: other and spec gap in the brief - a trusted-tail bounded probe certifies co-occurrence of
the broad related terms, but final ranking does not measure whether a candidate preserves the
requested absent subject's facet. Related contracting examples can therefore outrank the closest
bounded thematic substitute.
Resolution and verification: resolved in `evidence-planned-v8` without changing
premise/absence precedence. A planner-ranked related passage is eligible only for an
absence-sensitive, substantive non-premise facet with an exact validated document hint whose
query preserves the trusted subject and relation surfaces. Admission occurs before the older
exact-tail fallback and is capped at two sources. Synthetic tests prove that the hinted related
lane outranks an exact but off-facet contracting co-occurrence and that three qualified candidates
are still capped at two. The complete offline suite passes with 421 tests and one skip. The
unchanged paid G009 confirmation then returned a valid qualified answer from exactly two Epilogue
passages, covered the required 1/1 target group and about 3/5 strict claims, and invented no
pandemic procurement analysis.

## [2026-07-25] Premise planning bypassed certified absence on the unchanged G009
Phase/Brief: Phase 1 evidence-planned-v6 directional ten-question evaluation
Symptom: the focused v6 G009 confirmation returned a valid bounded near-match answer from two
sources, but the same unchanged question later returned `generation_contract_failed` in the full
cohort. The full-run planner succeeded, the target scanner again certified the named subject
absent, and the required Epilogue group was present, but a planner-created premise hypothesis made
`premise_evaluation_pending` take precedence. All eight sources entered generation as
`direct_answer`; status/gap normalization succeeded; strict validation then rejected
`premise_source_mismatch`.
Cause: other and spec gap in the brief - the evidence-decision precedence does not define whether
a model-proposed premise may override mechanically certified subject absence, and a declarative
question about an absent subject can be reclassified as premise-sensitive nondeterministically.
Resolution and verification: repaired offline in `evidence-planned-v7`. Planner input now includes
application-owned route traits, and local validation rejects any proposed premise unless the
deterministic route is already `premise_sensitive`. The evidence gate repeats that condition
before applying `premise_evaluation_pending`, so an absence-only route cannot be widened by a
provider proposal. A synthetic G009-shaped regression verifies `premise_route_mismatch` fallback,
and a defensive gate regression verifies that a surviving untrusted premise cannot override clean
absence. The complete offline suite passes with 416 tests and one skip. The unchanged paid v7
confirmation then retained only `absence_sensitive`, certified absence, returned
`qualified_near_match`, and passed strict validation from two bounded sources. This precedence
defect is resolved; the separate semantic near-match defect is logged above.

## [2026-07-25] Accepted broad plans did not produce source-bounded historical coverage
Phase/Brief: Phase 1 evidence-planned-v6 directional ten-question evaluation
Symptom: G006 and G007 both accepted live planner proposals and returned valid cited answers, but
covered only 2/8 and 2/5 expected document groups and realized 1/8 and 0/7 strict claims. G006
clustered six of eight sources in Chapters 2-4 and jumped to one modern chapter; G007 again
collapsed largely into the twentieth century.
Cause: spec gap in the brief - plan validity guarantees that requirements map to facets, while
lane selection and the eight-source cap do not guarantee that a live facet yields a source or that
one surviving source represents each required era. A syntactically accepted plan can therefore
lose most of its intended historical span during retrieval and final allocation.
Resolution and verification: mitigation was implemented in `evidence-planned-v7` at the two
measured boundaries. An unbounded manuscript-treatment question now routes as broad synthesis
unless it has a conservative named absence target. Broad proposals require ordered requirements
and dedicated facets; final allocation protects requirements and live broad facets under the
unchanged eight-source cap. The complete offline suite passes with 416 tests and one skip.
Unchanged paid confirmation showed that the defect is not resolved: G006 remained at 1/8 claims
and 2/8 groups, while G007 remained at 0/7 claims and improved only to 3/5 groups. Protection
reported no shortfall, but coarse origin/transition/endpoint facets still failed to span the full
chronology, duplicate documents consumed slots, and anchor promotion displaced a unique useful
stage source. The full cohort was stopped pending a narrower allocation and stage-coverage repair.

`Evidence-planned-v8` added application-owned early/middle/late document bands, mandatory ordered
origin/transition-or-mechanism/endpoint plans, unseen-document refill, capacity-first stage
protection, and traceable stage counts. Offline verification passes with 421 tests and one skip.
The unchanged paid confirmation proves the defect remains unresolved: G006 improved modestly to
2/8 claims and 3/8 groups, while G007 remained at 0/7 claims and regressed to 2/5 groups. Both
traces reported 3/3 stage coverage with zero shortfall. The new signal therefore verifies only
coarse chronology-band survival, not recovery of the substantive stages in a book-wide argument.
The next repair must increase or refine planned argument-stage obligations within the unchanged
eight-source cap rather than treating three terciles as adequate coverage.

A controlled retrieval-only 8/12/16 comparison refined that diagnosis. With one shared planner
result and embedding batch per question, G006 target-group coverage was 3/8, 3/8, and 6/8,
respectively; G007 remained 3/5 at every limit. Every larger context retained all eight baseline
chunks. The eight-source ceiling is therefore a measured constraint for G006, while planning and
ranking remain the measured constraint for G007. The earlier assumption that both repairs should
fit under an unchanged eight-source cap is no longer justified. No production parameter changed;
a broad-only sixteen-source ceiling and richer argument-stage planning must be evaluated as
separate cohort changes before integration. The diagnostic made two planner calls, two embedding
calls, no answer call, no retry, and cost an estimated `$0.05277158`.

The separate G006 generation gate rejected the broad-only ceiling. Sixteen sources increased
target-document coverage from 2/8 to 6/8 in that live-plan sample, but the answer contract exposed
a hidden integration boundary: `source_count=16` is illegal while `MAX_SOURCES=8`. Recovering the
already-paid structured output showed that the larger context also failed the substantive gate:
it added the Crown takeover but still omitted the Hamiltonian, Federal Reserve/FTC,
Pentagon/cost-plus, Chapter 20, and Epilogue steps. Production therefore remains at eight rather
than widening both retrieval and generation contracts without an answer gain.

`Evidence-planned-v9` replaced three coarse broad stages with five dedicated ordered narrative
stages and scoped numbered books from Chapter 1 through conclusion/Epilogue. Its focused G007 run
validated mechanically but remained at 3/5 target groups: it repaired Jamestown, displaced the
Civil War group at a rigid stage boundary, and missed the Epilogue. `Evidence-planned-v10` added
two-document overlap between adjacent narrative stages and one structural endpoint lookup against
the book's own conclusion/Epilogue, sharing the existing embedding and retaining the eight-source
cap. A controlled rerun reused the exact accepted v9 plan and improved G007 source coverage from
3/5 to 5/5 for `$0.10395228`; the complete offline suite passes 422 tests with one skip.

The broad-source-allocation symptom is resolved at the target-document level for G007 but not at
the expected-claim level. The answer still lacks several specific mechanisms inside those
chapters, including war debt as Hamiltonian power, Pentagon/employment, NSC-68 and Keynesian
permanent spending, NATO persistence, and the security dilemma. The next defect is therefore
passage-level mechanism targeting/ranking inside the now-correct narrative stages, not another
source-limit increase or chronology-band change. The full ten-question cohort remains gated.

`Evidence-planned-v11` added deterministic role-scoped mechanism probes inside the accepted
narrative stages without adding an API operation or changing the eight-source ceiling. A focused
G007 confirmation reused the accepted v9 five-stage plan and covered 5/5 target groups. The clean
unchanged ten-question v11 cohort then improved G006 from 2/8 to 5/8 target groups and G007 from
2/5 to 3/5 compared with v6. The fresh G007 plan's regression from the focused 5/5 context to 3/5
shows that broad allocation remains nondeterministic across accepted plans. Mechanism-aware
ranking is retained as a directional breadth improvement, while plan stability remains
unresolved and the separate source-present generation omission is logged above.

## [2026-07-25] A valid premise correction still omitted the manuscript's origin frame
Phase/Brief: Phase 1 evidence-planned-v6 directional ten-question evaluation
Symptom: G010 changed from a rejected generation in v4 to a valid nine-citation answer in v6. It
explicitly rejected 1898 as the origin and covered both expected document groups, but used a later
Federalist counterpoint instead of stating the manuscript's Jamestown origin. It realized only
1/4 strict expected claims and retained the listed failure mode for correcting a premise without
stating where the book places the origin.
Cause: spec gap in the brief - premise validation checks that a leading cited correction exists,
not that the correction realizes the independently requested source-bounded origin requirement.
Mechanical premise validity and answer adequacy therefore diverge.
Resolution and verification: repaired offline in `evidence-planned-v7` without hard-coding a
place, chapter, or expected answer. `archivist.evidence_coverage/2` requires premise-correction
units to carry no requirement IDs and requires ordinary units to carry at least one, preventing a
correction from satisfying the requested answer by bookkeeping. The application supplies exact
post-gate support, counter, and framing source scopes; a contradicted correction must cite its
exact declared sources and include a retained framing source whenever one exists. The prompt
requires a positive replacement chronology, origin, identity, or causal frame before separate
substantive units. Provenance, separation, and text-free diagnostic regressions pass within the
416-test offline suite. Unchanged paid G010 confirmation then produced a leading, cited Jamestown
replacement frame, kept the correction outside ordinary requirement coverage, covered both
target-document groups, and passed strict validation. The narrow missing-origin defect is
resolved. Strict rubric completeness remains only 1/4 because the answer did not realize the full
Introduction/Cradle framing, identify Chapter 11, or complete the Spanish-imperial-transition
claim; those are answer-completeness targets rather than a recurrence of the provenance defect.

## [2026-07-25] Qualified near-match answer failed on redundant status/gap bookkeeping
Phase/Brief: Phase 1 evidence-planned-v5 focused paid smoke
Symptom: G009 certified direct absence of the named event, admitted exactly two bounded related
passages, and reached `qualified_near_match`, but the paid structured answer was discarded with
`generation_contract_failed` and `status_gap_mismatch`. No answer units or citations were rendered
even though retrieval and source bounding had succeeded.
Cause: other and spec gap in the brief - requirement status and gap reason are specified as a
closed one-to-one mapping, but the normalizer repairs other redundant mappings while leaving this
derived field pair to fail closed. The failure artifact preserves the stable code but not the exact
generated pair.
Resolution and verification: repaired offline in `evidence-planned-v6` with
`evidence-coverage-normalizer/3`. The normalizer derives only `gap_reason` from the unchanged
requirement status, records `status_gap_mismatch` as a repair code, and then runs the full strict
validator. Tests prove that it changes no unit, source, citation, or status, while missing units
and unsupported factual units still fail closed. The complete offline suite passes with 403 tests
and one skip. The separately authorized G009 confirmation then returned an `answered`,
`qualified_near_match` result from exactly two bounded sources; normalization recorded
`status_gap_mismatch`, strict validation passed, and all four emitted source references resolved.
The confirmation cost an estimated `$0.07107566` with no retry.

## [2026-07-25] Planner semantic fallback erased its actionable validation code
Phase/Brief: Phase 1 evidence-planned-v5 focused paid smoke
Symptom: G009's 339-output-token planner response parsed successfully and was then rejected by
local semantic materialization. The artifact retained only `invalid_planner_output`; it cannot
distinguish missing requirement mappings, query drift, unknown document hints, duplicate queries,
or another local validation rule. G008 and G010 planner proposals succeeded.
Cause: model error and spec gap in the brief - `build_question_plan` catches
`PlanValidationError`, Pydantic `ValidationError`, and `ValueError` together and intentionally
collapses them into one fallback reason, discarding the already text-free
`PlanValidationError.code`.
Resolution and verification: repaired offline in `evidence-planned-v6`. Planner diagnostics schema
`archivist.planner_call_diagnostics/2` retains one finite allowlisted
`planner_validation_code` beside the existing generic failure while preserving one-call/no-retry
fallback. Semantic failures retain their local code; structural Pydantic/ValueError failures use
`plan_structure_invalid`. Historical schema version 1 artifacts remain readable. Contract, ledger,
trace, and privacy tests reject missing, unknown, and non-text-free values and never persist the
proposal, exception prose, query, document hint, or manuscript text. The complete offline suite
passes with 403 tests and one skip. The separately authorized G009 confirmation's planner
succeeded, so the new failure code was not needed on that sample; its version-2 diagnostic was
valid and text-free. The semantic-failure path remains covered synthetically rather than claimed
from this successful live call.

## [2026-07-25] Every paid query-planner result failed its contract
Phase/Brief: Phase 1 evidence-planned-v4 directional ten-question evaluation
Symptom: all eight planner-eligible questions made exactly one paid `query_planning` request, but
none produced an accepted plan. Five failed SDK/Pydantic validation with safe exception class
`ValidationError`; three parsed but were rejected as `invalid_planner_output`. All eight questions
therefore used local fallback planning. The failed planner calls consumed 35,775 tokens,
`$0.57508750`, and 56.2% of the run's total estimated cost. G004 and G006 then returned no answer,
and G007 still collapsed its broad chronology into a narrow twentieth-century account.
Cause: other and spec gap in the brief — the planner prompt, output schema, token ceiling, and
post-parse plan validator were tested synthetically but not demonstrated to agree on a live model
response before planner-backed retrieval was treated as an optimization.
Resolution and verification: repaired offline in the new `evidence-planned-v5` cohort. Ledger
inspection established that G004, G006, G008, and G010 each exhausted exactly 3,000 planner output
tokens; G003 was the lone non-truncation SDK/Pydantic failure. The provider now returns a compact
shape-only `archivist.planner_question_plan/1` proposal, while the application supplies route
traits, trusted targets, requirement order, `F0`, status, and cross-field validation. The ceiling
is 4,000 tokens, the full eight-requirement/seven-added-facet capacity remains available, and
one-call/no-retry behavior is unchanged. Synthetic parse/materialization/fallback and strict
OpenAI-schema tests pass. A separately budgeted live planner smoke is still required before the
ten-question rerun; the frozen questions and rubric were not changed.

## [2026-07-25] Absence certification suppressed answerable and bounded-related evidence
Phase/Brief: Phase 1 evidence-planned-v4 directional ten-question evaluation
Symptom: G008 correctly abstained without substituting analogous chartered-company material, but
the same gate falsely abstained on G002, over-abstained on G009, and returned
`insufficient_evidence` on G004 and G006. G002's retrieval context included both expected Dulles
document groups before the gate certified the combined name absent and suppressed all eight
passages. G009 correctly found no literal COVID-19 mention but returned none of the bounded
Epilogue treatment required by the rubric. Across the ten questions, only five answer generations
were attempted and high-level expected behavior failed on five items.
Cause: other and spec gap in the brief — exact direct-subject anchoring does not safely decompose
compound named subjects, certified literal absence is allowed to erase qualified broader
discussion, and multi-target fallback ambiguity is treated as a reason to withhold all context.
Resolution and verification: repaired offline as `evidence-gate-v2` inside
`evidence-planned-v5`. Exact compound personal names split only into exact trusted user surfaces;
all-present and mixed-present subjects have separate admission rules; and compound subjects plus
a facet remain conservatively indeterminate. A bounded related probe can be derived only from an
exact trusted user-message tail and must co-occur with its broader term in one chunk or immediate
neighbors. Generic positive, partial, true-absence, noncooccurrence, organization-name, and
resolver-provenance regressions pass. Replaying the frozen v4 contexts without API calls routes
G002/G004/G006 to direct answer, preserves G008's clean abstention, and routes G009 to a bounded
qualified near match. A paid smoke remains required.

## [2026-07-25] Premise-correction generation was discarded after source remapping
Phase/Brief: Phase 1 evidence-planned-v4 directional ten-question evaluation
Symptom: G010 retrieved eight passages spanning the 1898 material and earlier-origin evidence, paid
for both planning and answer generation, then returned only `I could not produce a validated
source-grounded answer from the retrieved passages.` Diagnostics record
`generation_contract_failed`, repair code `source_mapping_mismatch`, and validation error
`premise_correction_invalid`. The final answer corrected neither the false premise nor the book's
origin framing and contained no citation.
Cause: other and spec gap in the brief — the interaction among anchor promotion, post-promotion
source numbering, premise-correction bookkeeping, and the structured generation validator was not
covered by an end-to-end contract fixture before the paid run.
Resolution and verification: repaired offline as `evidence-coverage-normalizer/2` inside
`evidence-planned-v5`. A contradicted premise's redundant source mapping is contracted to its
designated leading correction unit only when the original mapping is a nonempty strict superset
and both source sets are unique and in range. Empty, disjoint, duplicate, out-of-range,
wrong-role, and already-valid subset cases remain unchanged or fail closed. A corpus-agnostic
end-to-end fixture promotes an anchor to Source 1, remaps the prior passage to Source 2, passes all
numbered sources to generation, and renders the leading cited correction. A focused paid
premise-correction smoke is still required.

## [2026-07-24] Paid v3 smoke exposed an uncovered resolved-relationship form
Phase/Brief: Phase 1 post-optimization paid confirmation smoke
Symptom: both neutral smoke turns produced valid, source-supported answers, but the follow-up still
spent 12.93 seconds in query planning before falling back. Its resolved wording was `How did the
relationship between tobacco and labor shape everyday exchange in Jamestown?`; diagnostics record
`planner_call_failed` with safe exception class `ValidationError`, while the local usage ledger has
no planner event. The two-turn local estimate was `$0.18810122`, so any provider charge for that
failed request is not represented locally. The v3 artifacts also omitted a standalone retrieval
trace and the smoke summary omitted the corpus-manifest hash, weakening reproducibility even
though runtime preflight passed.
Cause: other and cohort-gate failure — the bounded local relationship grammar covered the earlier
`the relationship between X and Y as shaping ...` form but not the resolver's actual
`the relationship between X and Y shape ...` output. The generic broad-pattern check therefore
classified `between ... and` as requiring model planning. The tracked structured-response helper
records token usage only after successful parsing, and the smoke artifact contract does not yet
require a persisted retrieval trace or manifest hash.
Resolution and verification: resolved in the new `evidence-planned-v4` cohort. The exact
corpus-agnostic directional relationship form now decomposes locally, while ambiguous tails retain
planner routing. Structured-response accounting records completed raw-response usage before SDK
post-parse validation without retrying or double-recording. Reusable smoke artifacts now bind
corpus, vector-store, Git worktree, lockfile, runner, and per-turn trace identity. Trace schema
`archivist.retrieval_trace/3` hashes document labels and planner exception classes and accepts only
closed, field-specific diagnostic values, blocking unknown nested prose and encoded text channels.
The full offline suite passes with 372 tests and one skipped.

A separately bounded resolver-only API confirmation then resolved the observed follow-up to `How
did the manuscript describe the relationship between tobacco and labor as shaping everyday
exchange in Jamestown?`, retained all four required concepts, routed relationship-only, recorded
planner status `not_called`, and made exactly one `followup_resolution` request. It used 449 input
and 154 output tokens, took 6.954 seconds, and cost an estimated `$0.006865` under a `$0.02` hard
stop. No embedding, retrieval, planner, or answer-generation call occurred. The artifact records a
dirty exploratory worktree and is not a run of record. The unchanged ten-question evaluation
remains separately budgeted and was not started.

## [2026-07-24] Valid smoke answer lost primary evidence and hid a planner failure
Phase/Brief: Phase 1 post-optimization paid smoke
Symptom: both turns of the neutral tobacco-and-labor smoke passed the structured coverage contract,
but strict source review rated the opening answer only partial. It omitted the clearest
labor-shortage, indenture, and headright mechanism even though retrieval had selected that passage
as a primary result. The follow-up answered well but took 33 seconds; 16 seconds were attributed to
query planning, while the usage ledger contained no planner event.
Cause: other and spec gap — neighbor expansion was allowed to displace a selected primary passage
under the eight-source generation cap; the coverage contract validates citation membership and
requirement bookkeeping but not pairwise claim-to-source entailment; and the planner fallback
catches every exception without retaining an exact failure code or any available failed-request
usage.
Resolution and verification: opened `evidence-planned-v3`. Context assembly now preserves every
selected primary passage before optional neighbors fill unused slots. The evidence-coverage prompt
and schema require one independently checkable factual claim and one terminal citation group per
answer unit; deterministic validation rejects mechanically detectable extra sentences, citation
groups, post-citation prose, newlines, and semicolon-separated claims. Bounded resolved
relationship follow-ups decompose locally into both operands and their context, so the smoke's
follow-up shape no longer invokes the planner. Every planner outcome is also persisted as a
versioned text-free diagnostic; a failure retains only a safe exception class, an allowlisted
provider code, or a numeric HTTP status, never exception messages. The full offline suite passes
with 353 tests and one skipped, Ruff passes, and the
frontend production build passes. No OpenAI call was made. Semantic claim-to-source entailment
still requires evaluation rather than punctuation heuristics. Failed provider calls that return no
usage object also remain dashboard-only for billing. A separately authorized paid smoke must
confirm the live behavior before the unchanged ten-question comparison.

## [2026-07-24] A source-grounded draft was discarded without an actionable diagnosis
Phase/Brief: Phase 1 post-optimization reader testing
Symptom: a question recommended on the opening screen retrieved eight passages and incurred a full
answer-generation charge, but the interface displayed the generic generation-contract failure as
though it were the manuscript's answer. The local usage ledger showed substantial generated output,
while the application did not persist the exact validation rule that rejected it.
Cause: other and cohort opening — the evidence-coverage validator treated safe redundant
bookkeeping mismatches like factual grounding failures, the relational request had only its
unchanged original retrieval lane, and post-validation diagnostics stopped inside the backend.
Resolution and verification: opened `evidence-planned-v2`. Relational prompts now receive separate
local concept and connection lanes without a paid planner call. A conservative normalizer may
reorder trusted IDs and recompute redundant mappings only when factual units and exact citation
sets are unchanged; unsupported claims, unknown sources, malformed citations, and citation-set
changes still fail closed. Exact validation and repair codes plus stage timings are returned and
persisted with the relevant policy, prompt, normalizer, and generator cohort identifiers in a
text-free turn-level ledger record. The chat renders a rejected generation as an error with
collapsed technical details instead of archival answer paper. Homepage prompts are now data-backed
regression inputs. Legacy custom-project turns carry an explicit `legacy-answer-v1` cohort rather
than being misclassified as v2. The full offline backend suite passes with 296 tests and one
skipped, Ruff lint passes, and the frontend production build passes. No OpenAI call was made, no
gold entry or metric definition changed, and this cohort is not claimed better until a paid
confirmation run.

## [2026-07-23] Opening-screen commit absorbed an unrelated retrieval regression
Phase/Brief: Phase 1 paired practical rerun preflight
Symptom: clean commit `c1ab639` failed three backend tests: Answer retrieval traces no longer
included the frozen chunk and corpus hashes, the semantic-only web helper had disappeared, and
deferred Index generation was routed through hybrid Answer retrieval.
Cause: presentation work crossed the system-under-test boundary — a pre-existing unstaged
`src/web_project.py` edit was included with the opening-screen commit even though it was unrelated
to that UI task.
Resolution and verification: restored the exact post-optimization boundary from `d4656df`.
Answer Mode retains hybrid retrieval and its text-free corpus identity; Index Mode again calls the
semantic-only helper. The full offline backend suite passes with 152 tests and one opt-in test
skipped. No API call was made, and no paid evaluation began while the regression was present.

## [2026-07-23] Interpretive demo prompting advances Phase 2 beside neutral Phase 1
Phase/Brief: Phase 1 reader-facing UI, owner-directed perspective demonstration
Symptom: the owner requested more conversational answers when any Historiographical lens, Voice,
or Worldview characteristic is active, while the neutral Answer Mode evaluation and paired RAG
rerun are still open Phase 1 work.
Cause: Phase 2 concern in Phase 1 work and cohort opening — non-default interpretive prompt text
changed.
Resolution and verification: the new reader-facing response rules are emitted only when at least
one setting is non-default. The all-default Evidence-first + Scholarly + None path still uses the
frozen base prompt byte for byte, so the neutral retrieval comparison is not moved. Every
non-default facet now defines an observable rhetorical structure and shares the same citation,
uncertainty, and anti-invention guardrails; this is a separate experimental cohort and cannot be
claimed faithful until it passes the later perspective-mode checks. Focused tests cover all seven
active facets, combined settings, legacy mappings, and neutral exclusion without an API call.

## [2026-07-23] Guided-start mechanics were not specified
Phase/Brief: Phase 1 reader-facing onboarding
Symptom: the requested start feature said Archivist should ask questions that help a reader decide
what they want from the application, but did not define the number of steps, categories, resulting
questions, API boundary, conversation-history behavior, or whether the guide could alter answer
style.
Cause: spec gap in the brief.
Resolution and verification: the implementation uses a deterministic two-step client-side guide.
It asks for a subject class and then the desired treatment, fills an editable corpus-agnostic
question scaffold, selects the bracketed placeholder, and waits for the reader to press Ask. It
does not call the API, create a synthetic conversation turn, enter follow-up history, or change
Historiographical lens, Voice, or Worldview. The production frontend build verifies the typed
interaction path; no paid call was made.

## [2026-07-23] Hybrid Answer Mode retrieval opens a new retrieval cohort
Phase/Brief: Phase 1, post-baseline retrieval optimization
Symptom: the first ten-question practical baseline used only the five nearest semantic results,
then interleaved each primary with neighbors before applying the eight-source cap. Exact names
could be missed, optional neighbors could displace later primary evidence, and broad questions
could collapse to one document.
Cause: cohort opening — Answer Mode retrieval parameters and context ordering changed.
Resolution and verification: Answer Mode now makes the same single query-embedding call but asks
Chroma for a 20-candidate semantic pool, ranks the eligible corpus locally with deterministic
BM25, and fuses the two ranks with equal-weight reciprocal-rank fusion (`k=60`). Standard queries
remain relevance-ordered. Queries classified as broad synthesis may apply a three-primary
per-document diversity pass only when an alternative remains within 75% of the strongest deferred
candidate, then backfill by fused rank. Every selected primary is reserved before immediate
neighbors. The raw semantic top five remain separately visible, Index Mode retains its prior
exact-match and semantic-fallback behavior, and the generation prompt and model are unchanged.
Synthetic no-API tests cover lexical promotion, semantic-only fallback, deterministic fusion,
guarded diversity, primary-first expansion, shared CLI/web behavior, Index Mode isolation,
contract-facing displacement attribution, and private diagnostics. The full suite passes with
140 tests and one opt-in test skipped. The semantic-only practical
baseline belongs to the previous cohort; improvement must be established by rerunning the same
frozen ten questions.

## [2026-07-23] Hybrid retrieval mechanics were not specified
Phase/Brief: Phase 1, post-baseline retrieval optimization
Symptom: the approved next step called for hybrid lexical/semantic retrieval, diagnostics, and
source diversity but did not define tokenization, lexical scoring, fusion weights, candidate
depth, tie-breaking, diversity safeguards, neighbor priority, trace privacy, or persistence.
Cause: spec gap in the brief.
Resolution and verification: the implementation uses a corpus-agnostic NFKD Unicode word
tokenizer with possessive normalization, a versioned dependency-free BM25 scorer
(`k1=1.2`, `b=0.75`), equal-weight RRF with deterministic rank and chunk-ID tie-breaking, and the
guarded broad-query diversity rule recorded above. A versioned text-free trace records hashes,
ranks, scores, distance/fallback states, selection reasons, context order, document
distribution, corpus hashes, Chroma distance space, and every effective parameter; raw questions,
prompts, metadata blobs, and chunk text are rejected from persisted traces. Persistence is opt-in
under gitignored `runtime/` and a sink failure cannot prevent an answer. These choices are now
explicit and tested, but remain
tunable retrieval parameters rather than changes to `EVAL_CONTRACT.md`.

## [2026-07-23] Gold locations could name chunks excluded from retrieval
Phase/Brief: Phase 1, Brief 3 preparation
Symptom: gold-set validation accepted any chunk ID present in the corpus manifest, even when the
chunk's document matched `ingest.skip_files` and could never enter evaluated retrieval context.
Cause: contract/spec gap — existence and retrieval eligibility had not been distinguished in the
gold validation rule.
Resolution and verification: `EVAL_CONTRACT.md` §§2.5, 3.6, and 4.1 now require every supporting
and relevant location to both exist and be retrieval-eligible under the referenced manifest. The
validator now derives the eligible ID set from `chunks[*].document` and `ingest.skip_files` and
rejects skipped locations as hard errors. This clarification was made before a gold pilot or run
of record, so it invalidates no earlier gold entry or run-of-record evidence.

## [2026-07-23] Retrieval and evaluation had no settled opening boundary
Phase/Brief: Phase 1, Brief 3 preparation
Symptom: the contract and roadmap left front matter, the tentative Afterword, and appendices as an
open owner decision while the implementation default made most of them retrieval targets.
Cause: contract clarification and corpus-cohort opening — the brief intentionally deferred a scope
decision that became necessary before authoring gold locations.
Resolution and verification: the owner selected an Introduction-first boundary. Retrieval and
evaluation begin at `05_Introduction.md`; the four preceding structural documents and documents
matched by the existing `32_Bibliography.md` sentinel are excluded, while the Epilogue, Afterword,
and appendices remain eligible. The frozen counts are 910 total chunks, 481 eligible chunks, and
seven skipped documents. The decision preceded all gold queries and runs of record, so no result
informed it and no prior run-of-record evidence is invalidated; the revised corpus snapshot opens
the first evaluable cohort.

## [2026-07-23] Ten-item gold pilot had no mechanical final-set boundary
Phase/Brief: Phase 1, Brief 3 preparation and Brief 6 calibration pilot
Symptom: `EVAL_CONTRACT.md` defines the final 34–46-item composition, and Brief 6 calls for a
ten-item pilot spanning at least four strata, but neither specifies how an `archivist.gold/1`
pilot file is mechanically distinguished from a final gold set or prevented from being used under
the weaker validation profile.
Cause: spec gap in the brief.
Resolution and verification: gold validation now has explicit `pilot` and `run-of-record` modes.
Pilot mode requires exactly ten items, at least four represented strata, and a `-pilot` semantic
version marker; run-of-record mode rejects prerelease versions and enforces every locked §3.4
stratum range. The committed template is empty, manifest-bound, and marked `0.1.0-pilot`. Tests
prove a valid pilot cannot pass run-of-record validation. `EVAL_CONTRACT.md` is unchanged.

## [2026-07-23] Official GPT-5.6 Sol identifier does not satisfy the dated-snapshot contract
Phase/Brief: Phase 1, Brief 2
Symptom: the requested and currently documented flagship model identifier is `gpt-5.6-sol`,
but Brief 2 also requires startup rejection of every model identifier without a date suffix.
No official dated GPT-5.6 Sol identifier is documented, so those requirements cannot both govern
the interactive application without either inventing an identifier or preventing it from starting.
Cause: spec gap in the brief, surfaced by a change in available model identifiers.
Resolution and verification: interactive runtime settings and formal evaluation validation are
separated. The runtime uses the documented `gpt-5.6-sol` identifier, while
`require_run_of_record_snapshot` rejects it for a formal run. Tests prove the documented identifier
is not represented as a pin and that the contract's known dated `gpt-5-2025-08-07` form passes the
date-suffix check. `EVAL_CONTRACT.md` is unchanged, no dated identifier was invented, and a formal
run of record remains blocked until an official dated snapshot is available and selected.

## [2026-07-23] GPT-5.6 Sol opens a new generation cohort
Phase/Brief: Phase 1, Brief 2
Symptom: active answer, follow-up-resolution, and deferred index-generation requests previously
used the bare `gpt-5` alias with implicit reasoning and verbosity defaults.
Cause: cohort opening — the generation model and recorded sampling settings changed.
Resolution and verification: the generation roles now use centralized `gpt-5.6-sol` settings with
explicit `medium` reasoning effort and `medium` verbosity, preserving the former documented
effective defaults while changing the model. Focused request-capture tests verify all active
generation paths receive the correct role settings. Earlier generated outputs, if retained, belong
to the previous cohort and are not directly comparable.

## [2026-07-22] Reader-facing cost tracking required a new local accounting contract
Phase/Brief: Phase 1 reader-facing UI, owner-directed cost visibility pass
Symptom: the application made several independently billed API calls per conversation turn but
         exposed neither their returned usage nor an estimate of cumulative spend.
Cause: spec gap in the brief -- the requested cost meter did not define persistence, price-version
       handling, unknown models, invoice reconciliation, or whether a budget was a warning or cap.
Resolution and verification: completed API responses are recorded in a local SQLite ledger using
       returned token usage and a versioned rate table. The UI distinguishes this estimate from
       OpenAI's authoritative Costs data. Budgets default to disabled; the optional local hard stop
       blocks only the next request and permits an explicit one-request override. Contract tests
       cover pricing, idempotency, aggregation, unknown models, and the enforcement boundary. No
       prompt, retrieval parameter, model setting, or manuscript context changed.

## [2026-07-23] Authoritative DOCX ingest and safe index promotion were unspecified
Phase/Brief: Phase 1 corpus replacement, before Brief 2
Symptom: the repository could not mechanically prove that a supplied Word manuscript became the
         reader-active Markdown, chunks, and vectors without losing footnotes or overwriting
         unrelated project collections in the shared Chroma store.
Cause: spec gap - the corpus contract defined the finished manifest but not Word body-order
       extraction, structural end-matter mapping, note handling, staged paid embedding, rollback,
       or preservation of non-reader Chroma collections.
Resolution and verification: added a deterministic OOXML preparation path that rejects ambiguous
       revisions, comments, unresolved notes, real endnotes, and malformed structure; added a
       text-free corpus manifest; added a budget-aware fresh-index builder that reopens and verifies
       persisted vectors; and added an offline promotion assembler that preserves every unrelated
       collection. Synthetic tests cover failure atomicity and a real local Chroma round trip.
       The July 6 corpus passed two byte-identical offline preparations. After explicit owner
       authorization, 488 chunks were embedded in 10 tracked calls and the new corpus was activated
       with exact ID, metadata, text-hash, vector, and L2 checks. All nine unrelated Chroma
       collections retained identical records and metadata. The full backend suite passed against
       the active corpus, and the production frontend build succeeded.

## [2026-07-22] Combined perspective prototype split into three prompt facets
Phase/Brief: Phase 2 perspective-mode prototype, requested during Phase 1
Symptom: the combined perspective selector conflated historiographical framing, prose voice, and
         moral or metaphysical worldview, preventing those dimensions from being selected
         independently in the reader-facing demonstration.
Cause: cohort opening - non-neutral generation prompts now compose three independent,
       allowlisted Markdown facets in a fixed order.
Resolution and verification: historiographical lens, voice, and worldview are separate request
fields and their values are recorded on each answer; every all-default request still produces the
frozen neutral prompt byte-for-byte, and the settings do not enter retrieval or change the model.
Legacy combined requests map to their corresponding single facet. Tests cover the registries,
prompt composition, API mapping, and retrieval boundary. This remains an unevaluated reader-facing
prototype and is not a run-of-record cohort.

## [2026-07-22] Conversational follow-ups opened a separate reader-facing cohort
Phase/Brief: Phase 1 reader-facing UI, owner-directed conversation design pass
Symptom: follow-up questions such as pronouns or implicit references cannot be retrieved reliably
         when every request is treated as an isolated question.
Cause: cohort opening — multi-turn requests now use a separate query-resolution prompt before the
       unchanged Answer Mode retrieval and generation path.
Resolution and verification: first-turn requests remain byte-for-byte on the existing path. For a
follow-up, only the newest bounded completed turns enter the resolver; its standalone question is
used for fresh retrieval, and prior assistant prose never enters the evidence or answer prompt.
Contract tests cover the boundary. This conversational cohort is not a run of record and must be
evaluated separately from the frozen single-turn neutral cohort.

## [2026-07-21] Perspective prototype advanced before the Phase 2 measurement gate
Phase/Brief: Phase 2 perspective-mode prototype, requested during Phase 1
Symptom: the reader-facing web application now needs selectable historical perspectives before
         the neutral Answer Mode baseline and faithfulness calibration are complete.
Cause: Phase 2 concern in Phase 1 work — the owner deliberately advanced the interactive
       demonstration ahead of its scheduled brief.
Resolution and verification: perspective is confined to an optional, allowlisted generation
       overlay in the web path. Neutral remains the default and produces the frozen Answer Mode
       prompt byte-for-byte; retrieval, ordered source context, citation syntax, abstention, and
       the CLI/evaluation path remain unchanged. Contract tests verify those boundaries. The
       non-neutral perspectives are provisional and must not be treated as evaluated until each
       passes the same Phase 1 faithfulness and citation checks.

## [2026-07-21] Web index comparison context had a second Source namespace
Phase/Brief: Phase 1, Brief 1
Symptom: applying `[Source N]` independently to manuscript and existing-index blocks produced two `[Source 1]` headers, while the verbatim format example still requested `<citation label>`.
Cause: spec gap in the brief — it mandated the citation-token change but did not define numbering for the web prompt's second, comparison-only context.
Resolution and verification: comparison excerpts use unbracketed `Existing Index N:` headings and the prompt forbids citing them; manuscript chunks remain the sole `[Source N]` list, and the format example now says `[Source N]`. A synthetic prompt test asserts these properties.

## [2026-07-21] Annotation invariant included unreachable structural chunks
Phase/Brief: Phase 1, Brief 1
Symptom: the required all-disk assertion found eight title changes, all in the skipped Table of Contents document; no retrieval-eligible chunk changed.
Cause: spec gap in the brief — its rationale described evaluated context while its assertion included structural documents that cannot reach that context.
Resolution and verification: with owner approval, the blocking invariant now covers every retrieval-eligible chunk and the full corpus remains a diagnostic. Tests assert zero eligible mismatches and the known structural mismatch set.

## [2026-07-21] Chunk merging moved behind the model boundary
Phase/Brief: Phase 1, Brief 1 cohort opening
Symptom: the web path previously merged adjacent chunks before prompt construction, so one citation could resolve to several chunks.
Cause: cohort opening — a presentation operation changed what the model saw.
Resolution and verification: prompts now receive the same unmerged numbered chunks on CLI and web paths; `display_groups` preserves merged reading presentation and a test proves computing it cannot alter the prompt.

## [2026-07-21] Imported-document chunk parameters are duplicated
Phase/Brief: Phase 1, Brief 1; assigned to Brief 2
Symptom: `build_chunks_for_imported_document` hardcodes chunk size 4 and overlap 1 instead of using the constants in `ingest.py`.
Cause: duplicated configuration constant.
Resolution and verification: intentionally not changed in Brief 1. Brief 2 must give the import path one parameter source before recording chunking configuration in the corpus manifest.

## Pre-existing, logged at project setup (2026-07-21)

Found by reading `main` before Brief 1. Recorded here so they are tracked rather than rediscovered, with the brief that owns each. **None of these are to be fixed opportunistically** — each is fixed by its owning brief or not at all.

### [2026-07-21] `sources` endpoint destroys its own `document` filter
Phase/Brief: Phase 1, pre-Brief-1
Symptom: `GET /api/projects/{id}/sources?document=X` does not filter to document X.
Cause: model error. In `web_api.sources`, the function parameter `document` is reassigned inside the chunk loop (`document = str(chunk.get("document", ""))`). By the time `if document:` is evaluated it holds the last processed chunk's document name, so the filter always applies using that value regardless of what the caller asked for.
Resolution and verification: **unowned — not in scope for Brief 1.** Brief 1 is a unification brief and fixing an unrelated bug inside it would make its equivalence assertions unverifiable. Assign to Brief 8 or a standalone fix. Verification when fixed: request two different documents, assert the returned sets differ and each matches its requested document.

### [2026-07-21] Nothing in the repository runs from a fresh clone
Phase/Brief: Phase 1, pre-Brief-1
Symptom: `import retrieval` raises `FileNotFoundError` on a clean clone; `pip install -r requirements.txt` fails.
Cause: model error, two independent causes. `output/` is gitignored while `corpus.py` calls `load_chunks()` at module import, so every dependent module raises on import. Separately, `requirements.txt` is UTF-16 encoded, contains a corrupted entry (`chromadb==1.5.5dir`), and ends with duplicated unpinned lines.
Resolution and verification: both owned by **Brief 1** — the lazy corpus accessor, and `pyproject.toml` + `uv.lock` replacing `requirements.txt` rather than patching it. Brief 1 cannot collect its own tests otherwise. Verification: a clean clone installs and `pytest` collects without `output/chunks.json` present.

### [2026-07-21] Retrieval core duplicated across three modules
Phase/Brief: Phase 1, pre-Brief-1
Symptom: `get_filtered_primary_chunks` and `expand_with_neighbors` exist in both `retrieval.py` and `web_project.py`; `query.py` carries a third partial copy of the embed-and-query path that applies neither filtering nor expansion.
Cause: retrieval primitive duplicated rather than parameterized. The web copies take a `lookup` argument the originals do not, which is a parameter difference presented as a code fork.
Resolution and verification: owned by **Brief 1**. Verification: exactly one definition of each primitive in the package, asserted by a test that greps the source tree.

### [2026-07-21] Two Answer Mode prompts, one a silent subset of the other
Phase/Brief: Phase 1, pre-Brief-1
Symptom: `ask.py` and `web_project.answer_project_question` send different instructions for the same task. The web prompt omits three instructions present in the CLI prompt: per-claim splitting within a sentence, the multi-source `[Source 2, Source 3]` form, and "Be precise, avoid vague generalizations, and do not invent information."
Cause: model error — drift, not design. There is no recorded reason for the omissions.
Resolution and verification: owned by **Brief 1**; the CLI text becomes the single prompt. Verification: byte-identical prompt text emitted by both paths for identical inputs.

### [2026-07-21] `docs/evaluation.md` asserts a claim it cannot support
Phase/Brief: Phase 1, pre-Brief-1
Symptom: the document reaches the verdict "Accurate citations" while printing only chunk IDs and paragraph ranges, never chunk text. Neither a reader nor the author can check whether `[Source 1]` contains the claim attached to it.
Cause: spec gap — an evaluation document with no computable criteria. All seven verdicts are of this form.
Resolution and verification: owned by **Brief 7**, which replaces the file wholesale. It is not amended in the interim and is not cited as a baseline.

### [2026-07-21] Model alias in generation configuration
Phase/Brief: Phase 1, pre-Brief-1
Symptom: `ask.py`, `index_mode.py`, and `web_project.CHAT_MODEL` all specify `"gpt-5"`.
Cause: model alias where a dated snapshot is required. The alias currently resolves to `gpt-5-2025-08-07`, which OpenAI has scheduled for removal from the API on 11 December 2026; an alias re-points silently, so any run recorded against it is unreproducible.
Resolution and verification: owned by **Brief 2**. Verification: run identity records a dated snapshot string, and a startup assertion rejects any model string without a date suffix.

### [2026-07-21] Distance threshold in undetermined units
Phase/Brief: Phase 1, pre-Brief-1
Symptom: `MAX_PRIMARY_DISTANCE = 1.05` filters on a distance whose metric is never specified. The collection is created via `get_or_create_collection(name="manuscript")` with no `metadata={"hnsw:space": ...}`, so Chroma's default applies.
Cause: spec gap. Ranking is unaffected by the choice on unit-normalized embeddings, but the threshold's meaning is not, and a cut point with no stated units cannot be tuned deliberately.
Resolution and verification: owned by **Brief 2** — determine the space empirically from the installed Chroma version, record it in the corpus manifest, set it explicitly thereafter. Verification: `hnsw_space` present and non-null in every run identity.

### [2026-07-21] Distance filter can silently no-op
Phase/Brief: Phase 1, pre-Brief-1
Symptom: when every retrieved chunk exceeds `MAX_PRIMARY_DISTANCE`, `get_filtered_primary_chunks` returns the unfiltered set instead of an empty one. Retrieval therefore never returns "nothing relevant," and no signal distinguishes a confident retrieval from a fallback.
Cause: model error, arguably deliberate. Not fixed here either way — the behaviour is measured before it is changed.
Resolution and verification: **not a fix; a measurement.** Owned by **Brief 4**, which counts fallback events per question and reports the rate per stratum. A change to the fallback behaviour is licensed only by that number.

### [2026-07-21] Index Mode exact-match path is unranked
Phase/Brief: Phase 2, pre-Brief-9
Symptom: for `Virginia Company`, the eight sources supplied are Chapter 3 chunk `_010` followed by Chapter 4 chunks `_002`–`_009`, stopping there — corpus order, earliest occurrences, nothing from Chapter 5 where the Company's dissolution is discussed.
Cause: model error. `find_exact_match_chunks` returns every chunk containing the term in corpus order, and those fill `MAX_FINAL_SOURCES` before semantic results are consulted. The prompt then asks the model to identify "the strongest candidate locations" from a set that was never ranked. `docs/evaluation.md` records this case as "✅ Fixed and reliable."
Resolution and verification: **Phase 2, Brief 9.** Explicitly not fixed in Phase 1. Verification when fixed: for a term appearing in more than `MAX_FINAL_SOURCES` chunks, the supplied set is not the first N in corpus order.
