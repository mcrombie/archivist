# Brief 1: Unify the Answer Mode Path

Project: **Archivist** — see `B0_project_brief.md`, `ROADMAP.md`, `AGENTS.md`, `EVAL_CONTRACT.md`.

First brief of Phase 1. It makes the system measurable by giving it one retrieval core, one Answer Mode prompt, and one citation contract, so that a number produced later describes a single binary rather than one of three.

**`EVAL_CONTRACT.md` §§1–5 are locked** and this brief implements nothing from them. It establishes the preconditions: a single code path to measure, and a citation format that can be checked mechanically.

## Objective

Collapse three partial copies of the retrieval core into one parameterized implementation, adopt a single Answer Mode prompt, and establish `[Source N]` as the model-facing citation contract with human-readable labels rendered at presentation. Prove, by assertion rather than by inspection, that retrieval behavior is unchanged.

Also stand up the project's packaging and test harness, which do not currently exist.

## Why this scope

The evaluation is the highest-leverage work and this brief is not it. It exists because of a specific problem: an evaluation written against `retrieval.py` would not measure what the frontend does.

`ask.py` and `web_project.answer_project_question` currently send **different prompts** — the web one a strict subset, missing three instructions — through **different citation formats**, over **separately maintained copies** of the filtering and expansion logic. Measuring one and shipping the other means publishing numbers about the wrong binary. Measuring both means running every evaluation twice, forever, and reconciling two sets of results in the blog post.

The divergence is drift, not design. The web prompt's omissions have no recorded rationale, and the duplicated primitives differ only by a `lookup` argument — a parameter difference expressed as a code fork. `AGENTS.md` already commits to one retrieval core serving both modes; this brief executes that commitment rather than adding scope.

**It is also the brief most at risk of becoming the comfortable task that displaces the evaluation.** Refactoring is enjoyable and unbounded. See the tripwire.

## Scope

**In scope:**

- One definition of each retrieval primitive, parameterized rather than duplicated
- One Answer Mode prompt, extracted to a module constant
- `[Source N]` as the sole model-facing citation token, on every surface
- `citation_label` demoted to presentation, rendered from the API payload
- `merge_adjacent_chunks` moved out of the prompt path into presentation
- Corpus loading made lazy, so modules are importable without `output/chunks.json`
- `query.py` rewritten to show what the model is actually given
- Project bootstrap: `pyproject.toml`, `uv.lock`, test layout, ruff config
- Equivalence tests proving retrieval behavior is unchanged

**Out of scope (deferred to later briefs):**

- Corpus manifest, hashing, model-snapshot pinning, run identity (Brief 2)
- The lazy accessor is in scope here; everything else about reproducibility is Brief 2's
- Gold set (Brief 3), and any evaluation harness or metric code (Briefs 4–6)
- **Any change to retrieval behavior** — `n_results`, `MAX_PRIMARY_DISTANCE`, `MAX_FINAL_SOURCES`, chunking, `SKIP_FILES`, the distance-filter fallback, expansion order, truncation order. All frozen exactly as they are.
- **Any change to prompt wording.** The CLI text is adopted verbatim; not improved, not tightened, not modernized. Improving the prompt before it has been measured is precisely the move `AGENTS.md` forbids.
- The generic multi-project stack — not extended, not deleted, not refactored beyond the mechanical import changes this brief forces
- Index Mode's prompt content and its unranked exact-match defect (Brief 9)
- Every defect in `DEFECTS.md` not explicitly assigned to Brief 1 — in particular the `sources` endpoint's shadowed `document` parameter, which is a real bug and stays a real bug until its owning brief. Fixing an unrelated defect inside a unification brief makes the equivalence assertions unverifiable, because a behavior difference could then have two causes.
- Frontend work beyond rendering `[Source N]` → label and consuming `display_groups`

## Current state

Verified against `main`. The brief's job is to turn column 3 into column 4.

| Primitive | `retrieval.py` | `web_project.py` | `query.py` | After |
|---|---|---|---|---|
| `embed_query` | ✓ | inline in `retrieve_project` | ✓ | one, in `retrieval.py` |
| `get_filtered_primary_chunks` | ✓ | ✓ duplicate | — | one |
| `expand_with_neighbors` | ✓ (global lookup) | ✓ duplicate (`lookup` arg) | — | one, `lookup=None` defaulting to the corpus lookup |
| `find_exact_match_chunks` | ✓ (`chunks=None`) | ✓ duplicate (`chunks` required) | — | one; `retrieval.py`'s signature already generalizes |
| `finalize_context_chunks` / `finalize_question_context` | ✓ | ✓ variant | — | one, taking `chunks`/`lookup` |
| `finalize_index_context` | ✓ | ✓ variant | — | one, taking `chunks`/`lookup` |
| `build_context` | ✓ `[Source N]` | ✓ `[citation_label]` | — | one, `[Source N]` only |
| distance/cap constants | ✓ | imported from `retrieval` | — | unchanged, one home |

`web_project.py` additionally owns `citation_label`, `merge_adjacent_chunks`, `annotate_chapter_titles`, and `source_payload`. Their disposition is specified below.

## The citation contract

**The model always emits `[Source N]`**, where N is a 1-based index into the ordered source list supplied in the prompt. This is invariant across CLI and web.

**Human-readable labels are presentation.** `source_payload` attaches `citation_label` to each source; the frontend substitutes at render time so a reader sees `Chapter 4 Cradle of the Empire (1601 – 1622), ¶49–52` where the model wrote `[Source 3]`.

The reason is measurement, not taste, and it is spelled out in `EVAL_CONTRACT.md` §5.2. `[Source 3]` resolves to exactly one chunk, so citation resolvability is a mechanical check with no judge and no parser risk. A prose label must be recovered from generated text where it can be truncated — `citation_label` already truncates at 90 characters and appends an ellipsis — paraphrased, or malformed, so label-formatting failures would mix into the grounding number as a confound. A metric that cannot separate two failure modes cannot direct a fix.

**Consequence, and it is mandatory rather than optional:** `web_project.generate_index_entry`'s prompt currently instructs the model to "use the exact bracketed human-readable citation labels supplied below." Once `build_context` emits `[Source N]`, that instruction is false and must be updated to `[Source N]`. This is a required correction, not an unauthorized prompt change — the alternative is a prompt describing a format the context no longer uses.

## The single Answer Mode prompt

The **`ask.py` text is adopted verbatim** as the single prompt, restoring to the web path the three instructions it currently lacks: per-claim splitting within a sentence, the multi-source `[Source 2, Source 3]` form, and *"Be precise, avoid vague generalizations, and do not invent information."*

The CLI text wins because it is the superset and because the omissions have no recorded rationale. This is not a judgement that it is the better prompt — that is unknown, and will stay unknown until Brief 7. It is a judgement that one prompt is better than two, and that the superset is the safer default to measure first.

Prompts move to a new module holding them as named constants:

| Constant | Source | Change |
|---|---|---|
| `ANSWER_PROMPT_TEMPLATE` | `ask.py`, verbatim | none |
| `INDEX_PROMPT_TEMPLATE_CLI` | `index_mode.py`, verbatim | none |
| `INDEX_PROMPT_TEMPLATE_WEB` | `web_project.py` | citation-label instruction → `[Source N]`, per above. Otherwise verbatim |

The two index prompts stay separate and textually unchanged. Unifying them is Brief 9's job; the *retrieval* path underneath them is unified here, which is what `AGENTS.md` requires.

Prompts must be module constants rather than inline f-strings so that Brief 2 can hash them for the run identity. Prompt construction is extracted into a function returning the assembled string, so it can be asserted on without an API call.

## Chunk merging moves to presentation

`merge_adjacent_chunks` currently runs **before** `build_context` on the web path, fusing neighbouring chunks into a single source that carries a `chunk_ids` list. It moves out of the prompt path entirely.

**This is the one deliberate behavior change in the brief, and it is a cohort change.** Log it in `DEFECTS.md` as a cohort opening, not as a defect.

Two reasons, and the first is decisive:

1. **A merged source makes citation accuracy set-valued.** `[Source 3]` would resolve to a span of several chunks rather than one, so "does the cited chunk contain the claim" becomes "does any chunk in this region contain the claim" — a larger target, easier to hit, and inflated by construction. That directly undercuts the project's sharpest differentiator, which is that paragraph-level chunk IDs make citation accuracy unusually checkable.
2. **It changes what the model sees** — contiguous prose versus fragmented blocks with repeated headers — which plausibly affects answer quality. That is a real question and it is testable: after the baseline exists, "does merging help?" becomes a cohort comparison. It cannot be a cohort comparison while merging is entangled with the citation contract.

The reading experience is preserved. `source_payload` gains a `display_groups` field:

```json
{
  "sources": [ { "source_number": 1, "citation_label": "...", "chunk_id": "...", "text": "..." } ],
  "display_groups": [
    { "source_numbers": [1], "text": "...", "citation_labels": ["..."] },
    { "source_numbers": [2, 3], "text": "...merged...", "citation_labels": ["...", "..."] }
  ]
}
```

`sources` is the unmerged list the model was given, numbered 1..N, and is what citations resolve against. `display_groups` is derived from it by the existing merge logic and is what the frontend renders. Every `source_number` appears in exactly one group.

## Chapter-title annotation: the remaining path difference

Both paths already resolve chunk text through the on-disk lookup — `expand_with_neighbors` looks up *every* id it emits, including the primary chunk's own, so the Chroma metadata dict is used only to read `chunk_id`. Provenance is therefore already consistent and is not this brief's problem.

The real remaining difference is **`annotate_chapter_titles`**, which the web path applies to the chunk list before building its lookup and the CLI path does not. It rewrites each chunk's `chapter_title` by scanning the chunk text with `importers.chapter_title_from_text` and carrying the last detected heading forward.

That is not cosmetic: `chapter_title` is emitted as the `Chapter:` line of every source block, so **the two paths currently send the model different context text for the same chunks**, independently of the prompt template. Any unification that ignores this leaves a difference the prompt-identity assertion would not catch.

**Resolve by dropping annotation from the context path.**

`importers.chapter_title_from_text` scans a chunk's paragraphs for one beginning `Chapter <number|roman numeral>` and returns it as a heading. **On the legacy markdown corpus it cannot fire**, because `ingest.split_into_paragraphs` discards every line starting with `#` — and the manuscript's chapter headings are exactly that. The heading is captured once at ingest by `extract_chapter_title` and stored on every chunk in the file; no chunk text retains it.

Annotation exists for the **docx and PDF import paths**, where a heading survives as an ordinary prose paragraph and there is no markdown structure to read it from. That is import machinery for the deferred generic stack, not part of the evaluated path. Removing it from the context path removes nothing the manuscript corpus uses.

**Prove it rather than trusting the argument.** For every chunk on disk, assert the annotated `chapter_title` equals the stored one. Expected to pass everywhere; a failure means body prose somewhere opens with "Chapter N" and is being misread as a heading — which would be a retrieval-context defect worth having found, and an escalation rather than a proceed.

⚠ **Related, and out of scope here:** `importers.build_chunks_for_imported_document` calls `chunk_paragraphs(paragraphs, chunk_size=4, overlap=1)` with the values **hardcoded** rather than importing `PARAGRAPHS_PER_CHUNK` and `PARAGRAPH_OVERLAP` from `ingest`. The two chunking parameters therefore exist twice. Brief 2 records those parameters in the corpus manifest and would silently fail to describe the import path. Log it in `DEFECTS.md` as a duplicated constant, assigned to Brief 2; do not fix it here.

## Corpus loading becomes lazy

`corpus.py` executes `ALL_CHUNKS = load_chunks()` at module import, reading `output/chunks.json`, which is gitignored. Every module that transitively imports `corpus` therefore raises `FileNotFoundError` on a clean clone — including under `pytest` collection, which makes this brief's own tests impossible to run.

Replace the module-level constants with accessor functions that load on first call and cache. `ALL_CHUNKS` and `CHUNK_LOOKUP` may remain as names if they are lazy, but the import must not touch the filesystem.

Minimum change only. Everything else about reproducibility — the manifest, hashing, re-ingest verification — is Brief 2.

## `query.py` shows what the model sees

`query.py` currently duplicates the embed-and-query path and applies **neither** document filtering, distance filtering, neighbour expansion, nor truncation. It therefore displays a set of chunks that is not what Answer Mode sends the model, while presenting itself as a retrieval debugging tool.

Rewrite it as a thin wrapper over the unified core that prints **both** sets side by side: the raw top-*k* from `retrieve`, and the finalized set from `finalize_context_chunks`, marking which raw hits were dropped and by which stage.

This is not scope creep. It is the same `S_primary` versus `S_context` distinction `EVAL_CONTRACT.md` §4.2 is built on, and having it available by hand from Brief 1 makes Brief 4 easier to write and easier to trust. A debugging tool that shows something other than what the model receives is worse than no debugging tool.

## Project bootstrap

**The flat `src/` layout is kept.** Do not convert to a `src/archivist/` package.

Converting would touch every import in every module for no benefit this brief can measure, and `B0_project_brief.md` forbids rebuilding. Tests import the flat modules via pytest's `pythonpath` setting instead.

- `pyproject.toml` — Python 3.13; runtime deps `openai`, `chromadb`, `python-dotenv`, `fastapi`, `uvicorn`, `httpx`, `python-multipart` (required by the `Form`/`UploadFile` handlers in `web_api.py`); dev deps `pytest`, `ruff`; `[tool.pytest.ini_options] pythonpath = ["src"]`; ruff config
- `uv.lock`, committed — its SHA-256 enters the run identity in Brief 2
- `tests/` mirroring `src/`
- **`requirements.txt` is deleted, not repaired.** It is UTF-16-encoded, contains a corrupted entry (`chromadb==1.5.5dir`), and ends with duplicated unpinned lines; `pip install -r` fails on it. Patching a file that is being replaced is wasted work.

## Acceptance criteria

Every criterion is a computed check, not a judgement call.

**Structure**

- **Single definition.** A test scans `src/*.py` and asserts exactly one `def` for each of: `embed_query`, `get_filtered_primary_chunks`, `expand_with_neighbors`, `find_exact_match_chunks`, `build_context`, and the finalize functions. This test is the standing guard against re-forking and must remain after the brief closes.
- **Import cleanliness.** `python -c "import retrieval, ask, query, web_project, index_mode"` succeeds with `output/chunks.json` absent.
- **Install.** From a clean clone: `uv sync` succeeds and `pytest` collects with zero errors.

**Prompt identity**

- Given identical `(question, final_chunks)`, the prompt string built by the CLI path and by the web path is **byte-identical**. Asserted directly on the extracted prompt-construction function; no API call.
- `ANSWER_PROMPT_TEMPLATE` is byte-identical to the current `ask.py` prompt text. A committed SHA-256 of that string is checked by a test, so an accidental edit fails loudly rather than silently opening a cohort.

**Citation contract**

- **Context snapshot.** A fixed synthetic three-chunk list produces a `build_context` output byte-identical to a committed expected string. The fixture uses **synthetic text, never manuscript text**.
- **Grammar.** Every source header emitted by `build_context` matches `\[Source\s+\d+\]`, and the indices are contiguous from 1.
- **No labels in prompts.** No prompt string produced by any path contains a `¶` character or a `citation_label` output. Asserted by scanning the assembled prompt.
- **Payload round-trip.** For a synthetic source list, every `source_number` in `sources` appears in exactly one `display_groups` entry, and the union of group `source_numbers` equals the full 1..N range.

**Behavior is unchanged — the criteria this brief exists to satisfy**

- **Chunk-sequence equivalence.** Before making any change, run a fixed set of **10 questions** through `ask.answer_question` against the real corpus and commit the resulting ordered `chunk_id` lists as `fixtures/b1_pre_change_chunk_ids.json`. **Chunk IDs only — no text.** After the change, the same 10 questions must produce byte-identical lists.

  This is the brief's central assertion. Capture the "before" fixture as the first commit of the brief, not the last.

- **Cross-path equivalence.** The same 10 questions produce identical ordered `chunk_id` lists from the CLI path and the web path, with `merge_adjacent_chunks` applied only at presentation. Any difference is a defect, not a tolerance.
- **Annotation is a proven no-op.** For every chunk on disk, the `chapter_title` produced by `annotate_chapter_titles` equals the stored `chapter_title`. If this fails, annotation is doing real work on this corpus and the decision to drop it is wrong — escalate rather than proceeding.
- **Collection freshness.** For every chunk in the Chroma collection, `sha256(metadata["text"]) == sha256(disk_chunk["text"])`, and every collection `chunk_id` exists on disk. A mismatch means the collection is stale relative to `output/chunks.json` and gets a `DEFECTS.md` entry. This matters because `expand_with_neighbors` silently drops any retrieved chunk absent from the disk lookup, so staleness would show up as quietly missing sources rather than as an error.
- **Merging cannot reach the prompt.** For one fixed question, the assembled prompt string is identical whether or not `display_groups` is computed. Merging is presentation by construction, and this asserts it rather than trusting the call graph.
- **Parameters untouched.** A test asserts `MAX_PRIMARY_DISTANCE == 1.05`, `MAX_FINAL_SOURCES == 8`, the `retrieve` default `n_results == 5`, `PARAGRAPHS_PER_CHUNK == 4`, `PARAGRAPH_OVERLAP == 1`, and the two-entry `SKIP_FILES` set. These are the values Brief 2 will record and Brief 7 will report against; a silent change here would invalidate everything downstream.

**Corpus containment**

- `git ls-files` returns nothing under `manuscript/`, `output/`, or `projects/`, and those paths are present in `.gitignore`.
- No file under `tests/` or `fixtures/` contains manuscript prose. Enforced by the test-fixture rule above: synthetic text only, checked by review, with the `pre_change_chunk_ids` fixture containing identifiers exclusively.

## Deliverables

- `pyproject.toml`, `uv.lock`, `tests/`, ruff config; `requirements.txt` deleted
- One parameterized retrieval core in `retrieval.py`; duplicate definitions removed from `web_project.py` and `query.py`
- A prompts module holding the three named templates
- `build_context` emitting `[Source N]` exclusively
- `citation_label` and `merge_adjacent_chunks` reachable only from `source_payload`; `display_groups` added to the payload
- Lazy corpus accessors in `corpus.py`
- `query.py` rewritten to display raw-versus-finalized retrieval with drop reasons
- Frontend rendering `[Source N]` → label and consuming `display_groups`
- `fixtures/b1_pre_change_chunk_ids.json`, committed **before** the refactor
- The test suite above
- `DEFECTS.md` entries: one cohort opening for the merge relocation; one for any provenance mismatch found

## Tripwire

**One sitting.** If the diff exceeds roughly 400 changed lines excluding `pyproject.toml` and `uv.lock`, or if the work extends past a single session, **stop and escalate.**

The fallback is defined in advance so that stopping is a decision rather than a failure: abandon the unification, evaluate the CLI path as-is, and revisit unification after the baseline exists. Briefs 2 through 7 all remain executable against `ask.py` alone; they would simply describe the CLI binary rather than both.

This tripwire exists because refactoring is the enjoyable, unbounded task and the evaluation is the tedious, high-leverage one. `AGENTS.md` names that pattern as the project's documented failure mode, and this brief is where it would first recur.

## Completion notes (fill in when closing the brief)

Per `AGENTS.md`, record here rather than acting on:

- Every retrieval change you wanted to make and did not. Threshold adjustments, expansion-order changes, re-ranking, anything. This list is the raw material for the post-baseline briefs, and it records what the system was *expected* to get wrong — which is worth far more once compared against what it actually got wrong.
- Anything the brief left underspecified that forced an invented mechanic. That is a defect and gets a `DEFECTS.md` entry, not a note.
- The measured diff size, against the tripwire.
