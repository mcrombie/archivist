# Brief 0: Project Brief — Archivist

## What Archivist is

**Archivist is a retrieval-augmented question-answering system over a single long-form historical manuscript** — *A Big History of Virginia*, 594 pages, researched, written and published by the project owner in 2026. It retrieves passages, generates a grounded answer, and cites every claim back to the passage that supports it.

Archivist is not a document-QA product. The manuscript is not a demo dataset it happens to be pointed at; it is the reason the project can be evaluated at all. Rigorous evaluation requires knowing what the correct answer is and where it lives, and that is only possible because the owner wrote the book.

The engine, however, is corpus-agnostic. Nothing in retrieval or generation branches on a person, place, or chapter. **Optimizing for a known corpus and hardcoding a corpus are different things, and only the first is in scope.**

The project is also a portfolio piece and a two-post blog series, documenting the design process — briefs, standing rules, defect log, and above all the measurements — as much as the result. It is the centerpiece of a return to software engineering after roughly four years away, positioned around applied AI and RAG engineering.

## The premise: the interesting claim is measurable grounding

Any competent engineer can wire an embedding model to a vector store and get plausible answers out of an LLM. That is a weekend, and it is a commodity.

**What is not commodity is being able to say, with numbers, how often the retrieval finds the passage that actually contains the answer, how often the generated claims follow from what was retrieved, and how often a `[Source N]` tag resolves to the chunk that supports the sentence it is attached to.** Almost no portfolio RAG project can answer any of those questions. Most, on inspection, have never asked them.

Archivist's central claim is therefore not "it answers questions about Virginia well." It is: **this system's behavior is measured, its failure modes are located and quantified, and improvements to it can be shown to be improvements.** That is what the project has to earn, and it is the only part of it that is hard.

The paragraph-level chunk identifiers make the third measurement — citation accuracy — unusually checkable, because a citation resolves to a specific addressable span of specific paragraphs rather than to a document or a page. Few RAG systems can compute that metric at all. This is the project's sharpest differentiator and it should be treated as such.

## Current state, as read from the code

Recorded here so that later briefs argue with the repository rather than with a recollection of it. All of this was verified against `main` before this brief was written.

**Working.** Markdown chapters are chunked by `ingest.py` into 4-paragraph windows with 1-paragraph nominal overlap, adjusted by rhetorical heuristics that pull a quote's setup paragraph in and skip weak transitions. Chunks carry `document`, `chapter_title`, `chunk_id`, `paragraph_start`, `paragraph_end`, `text`. `embed.py` embeds them with `text-embedding-3-small` into a persistent Chroma collection, storing the full chunk dict as metadata. `retrieval.py` does semantic search at `n_results=5`, drops two structural documents, filters on `distance <= 1.05`, expands each hit with its immediate neighbours, and truncates to 8 sources. `ask.py` generates a cited answer; `index_mode.py` generates back-of-book index candidates using exact-match-first retrieval. A FastAPI server and a React frontend exist in the working tree.

**Unmeasured.** Everything above. `docs/evaluation.md` presents seven hand-picked queries with qualitative verdicts and no numbers of any kind, and asserts citation accuracy while printing only chunk IDs — never chunk text — so the assertion is not checkable from the document.

**Known problems, located in code rather than inferred.** Six that later briefs act on:

1. **Expansion-then-truncation discards low-ranked hits.** Five primary hits expand to as many as fifteen chunks, then truncate to the first eight in primary-rank order with no re-ranking. Typically only the top two or three semantic hits survive, and unscored neighbours of hit #1 displace scored hits #4 and #5 entirely. This is a concrete mechanical candidate for the broad-thematic over-focus that `docs/evaluation.md` reports qualitatively.
2. **The distance filter can silently no-op.** If every hit exceeds 1.05, `get_filtered_primary_chunks` falls back to the unfiltered set. There is no path on which retrieval declines to return sources, so the entire burden of declining to answer sits on the prompt — untested.
3. **Two Answer Modes had diverged.** `ask.py` and `web_project.answer_project_question` carried different prompts (the web one a strict subset, missing three instructions) and different citation formats. Brief 1 resolves this.
4. **Three partial copies of the retrieval core.** `retrieval.py`, `web_project.py`, and `query.py`. `query.py` applies neither filtering nor expansion, so it does not show what the model is actually given.
5. **Nothing is reproducible from a clone.** `output/` is gitignored and `corpus.py` loads `chunks.json` at module import, so every dependent module raises on import. `requirements.txt` is UTF-16 with a corrupted entry and will not install.
6. **Index Mode's exact-match path is unranked.** `find_exact_match_chunks` returns every chunk containing the term in corpus order, and those fill the 8-source budget before semantic results are consulted. For a common term this yields "the first eight chunks in the book containing this string," which the prompt then asks the model to treat as the strongest candidate locations.

## Two phases

**Phase 1 — Answer Mode, measured.** Unify the retrieval core, freeze the corpus, author the gold set, build and run the three evaluations, publish the baseline, and gate a public deployment that does not expose the manuscript. Nothing else.

**Phase 2 — Index Mode and perspective modes.** The back-of-book index assistant reaches its own done state, and the perspective experiment — the same question answered from the same retrieved passages in a neutral, wry, tragic, or triumphant register — becomes buildable.

**The gate between phases is not "the answers are good."** Requiring good answers first would be circular: the post-baseline briefs exist precisely to fix what the baseline reveals. Phase 1 is complete when Answer Mode is **measured, bounded, reproducible, and its limitations written down.** A mediocre but well-characterized system has passed; an impressive-looking one with no numbers has not.

### Why this order

**The perspective-mode experiment is unverifiable without Phase 1.** Four registers answering the same question from the same passages is a parlour trick unless every register passes the *same* faithfulness and citation checks — facts fixed, only framing varying. That constraint is the entire reason the idea is serious rather than cute, and it cannot be enforced, or even stated, without the measurement apparatus. It is also the idea most likely to jump the queue, which is why it is named here and placed last.

**Index Mode is genuinely separable.** Answer Mode reaches done without it, the two share a retrieval core built once, and the blog posts are sequenced Answer Mode first. Index Mode also has a known retrieval defect (§6 above) that would want its own measurement, and doing both at once means two unmeasured systems instead of one measured one.

## The three layers

In decreasing order of fixedness. Only the first is off-limits.

1. **The measurement contract (`EVAL_CONTRACT.md`).** Run identity and cohorts, the corpus contract, the gold-set schema, and the exact definitions of recall@k, citation accuracy, faithfulness, and abstention. The experimental control. Authored by the project owner; implementers are forbidden to edit it, and a needed change is escalated rather than made.

   **Sections settle on their own clocks.** §§1–5 are settleable at the desk and lock before any harness code exists. §6 faithfulness and §7 abstention are drafted but not settled, because judge–human agreement and threshold placement can only be answered by a pilot run. `EVAL_CONTRACT.md` states explicitly which open questions are desk questions and which require runs.

2. **The system under test.** Retrieval core, prompt, model configuration, parameters. Changed freely — that is the work — but every change either opens a run cohort or is a defect, and which one must be stated.

3. **Presentation.** Citation rendering, chunk merging for display, the frontend. **A presentation change must not be able to move a measured number.** If one does, the boundary has been violated and the violation is the finding.

## Success criterion

**Phase 1 succeeds when Answer Mode is characterized.** Not when it is good.

- **Reproducible** — identical output from an identical run identity: corpus manifest hash, gold-set version, prompt version, pinned generator and judge snapshots, retrieval parameters, commit, dependency lock. A pinned snapshot alone is not enough, and a model *alias* is not a pin at all.
- **Measured, with a stated noise floor** — recall@k, citation accuracy, and faithfulness each reported as a number with its run-to-run spread, established by repeating a fixed subset five times unchanged. A reported improvement smaller than that spread is not a result.
- **Bounded** — each metric falls within an envelope stated *in advance* in `EVAL_CONTRACT.md` and checked. Stating the envelope before the run is what makes the run capable of failing.
- **Differentiated across difficulty** — the gold set spans focused/biographical through broad/thematic, and results are reported per stratum. A single aggregate number would hide the one failure mode already known to exist.
- **Understood at its limits** — where the system fails is written down, in `docs/evaluation.md`, with numbers. Broad thematic over-focus, abstention behavior on out-of-corpus questions, whatever else the run reveals.

None of that asks whether the answers are impressive. A well-characterized mediocre baseline is a valid — arguably more useful — starting point, because it states precisely what the post-baseline briefs need to fix.

**Every criterion is designed to be capable of failing.** A brief that cannot produce a failing run is not testing anything.

## The corpus boundary

The manuscript is a commercial product. This constrains the architecture, not just the deployment.

- **Nothing derived from the manuscript that contains its text may be committed.** `manuscript/`, `output/`, and `projects/` stay gitignored. Committed artifacts reference the corpus by identifier and hash — chunk IDs, paragraph ranges, document names, SHA-256 digests — never by content.
- **The gold set states owner-adjudicated answers as claim lists rewritten in the author's own words**, not as manuscript or raw AI-draft quotations, so that it can be committed.
- **Public deployment searches the complete 481-chunk substantive corpus privately**, but serves
  edition-qualified page locators and short cited excerpts rather than whole chunks. The exposure
  profile is fixed by the server, not selected by the browser, and the public surface is
  rate-, concurrency-, abuse-, and spend-limited.
- **The faithfulness evaluation does double duty here.** An answer that paraphrases rather than reproduces is both a grounding property and a licensing property, and one measurement establishes both.

The endpoints that return full chunk text (`GET /api/projects/{id}/sources`, paginated, arbitrary
offset) and stream source files (`GET /api/projects/{id}/source-file/{path}`) are not deployable as
they stand. Upload, embedding, index, mutable-cost-setting, and client budget-override surfaces are
also local-only. Handled in Brief 8, deliberately not incidentally in an earlier one.

Page numbers are edition facts rather than universal book addresses. The first public locator
profile is explicitly `Typeset PDF (July 6, 2026)` and is bound to the supplied PDF hash. Future
paperback, hardcover, and ebook profiles may be added without changing retrieval or evaluation.
See `docs/public_demo_design.md`.

## Settled decisions

Restated as project commitments. A brief may note a consequence; it may not reopen the question.

1. **Do not rebuild.** The code is modular and reasonably clean. The gap is measurement, not quality, and a rebuild produces equally unmeasured code.
2. **The evaluation is the highest-leverage next action** — three measurements: retrieval recall@k, faithfulness, citation accuracy.
3. **The gold set is the first artifact**: 30–50 questions with known answers and known source locations, spanning focused to broad. It is the input to all three.
4. **Optimize for this manuscript; keep the plumbing corpus-agnostic.** Transferability is shown by one retrieval core serving two modes, not by accepting arbitrary corpora.
5. **Answer Mode reaches done without Index Mode.** Shared core built once, cleanly separated from mode-specific logic.
6. **Public deployment must not expose the manuscript.**
7. **The evaluated system gets no personality.** Grounded and boring is the achievement. A light persona is acceptable only on a reader-facing public demo, never on the evaluated path.
8. **Perspective modes come after the evaluation**, and are constrained by it: every register passes the same faithfulness and citation checks.
9. **Public retrieval uses the complete substantive corpus, with disclosure controlled at the
   presentation boundary.**
10. **Every page citation names its edition.** Typeset PDF, paperback, hardcover, and ebook
    locators are separate profiles over stable chunk IDs.

## Non-goals (explicit; revisit only by amending this brief)

- **No rebuild or architectural rewrite of retrieval.** Brief 1's unification is de-duplication, not redesign; it changes no retrieval behavior.
- **No retrieval improvements before the baseline exists.** Including ones that are obviously correct. Especially those — an unmeasured fix to an unmeasured system is indistinguishable from a no-op.
- **No work on the generic multi-project stack.** Not extended, not deleted, not refactored. Deferred entirely until the baseline exists.
- **No Index Mode work in Phase 1**, beyond keeping it compiling against the shared core.
- **No persona, tone, or perspective-mode work in Phase 1.**
- **No unqualified or guessed page-number mapping.** The finalized typeset PDF now licenses its own
  verified locator profile; paperback, hardcover, and ebook profiles remain empty until their
  numbering is supplied.
- **No new frontend features.** Presentation changes are limited to what Brief 1 requires for the citation contract.

## Tech context

Python 3.13 with uv, pytest, and ruff, per `AGENTS.md`. ChromaDB persistent, `text-embedding-3-small` for embeddings, a pinned dated GPT-5-family snapshot for generation and a separately pinned snapshot for judging. FastAPI backend, React/Vite frontend.

Two facts pinned in `AGENTS.md` and worth surfacing here because they invalidate results silently rather than loudly. **`gpt-5` is an alias**, currently resolving to `gpt-5-2025-08-07`, which is scheduled for removal from the API on 11 December 2026 — a run recorded against an alias is not reproducible. And the Chroma collection is created without an explicit `hnsw:space`, so the `MAX_PRIMARY_DISTANCE = 1.05` threshold is currently expressed in units nobody has written down.

## Relationship to other documents

- **`ROADMAP.md`** sequences the briefs and marks where the plannable spine stops and measurement-driven work begins.
- **`EVAL_CONTRACT.md`** is the locked measurement specification: run identity and cohorts (§1), the corpus contract (§2), the gold-set schema (§3), retrieval recall (§4), citation accuracy (§5), faithfulness (§6, not yet settled), abstention (§7, not yet settled). **Authored by the project owner; implementers are forbidden to edit it.**
- **`AGENTS.md`** is the standing rules file every brief must respect.
- **`DEFECTS.md`** logs contract violations, gold-set edits made in response to results, corpus leakage, duplicated primitives, Phase 2 creep, and brief gaps.
- **`B1_unify_answer_mode.md`** is the first implementation brief.
- **`docs/evaluation.md`** is the current, qualitative evaluation document. It is a specimen of the problem, not a baseline, and is replaced wholesale in Brief 6.
- **`docs/public_demo_design.md`** specifies the server-selected development/public source profiles,
  edition-qualified locator model, bounded quotation policy, and Cromblog integration gate.
