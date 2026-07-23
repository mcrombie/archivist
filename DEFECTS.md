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
