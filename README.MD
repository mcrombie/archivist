# Archivist

Archivist is a source-grounded conversational interface for one book: *Cradle of the Empire: A
Big History of Virginia*. It searches the complete substantive manuscript, answers with inline
`[Source N]` citations, and carries context across follow-up questions.

Public demo: [https://archivist.mcrombie.com](https://archivist.mcrombie.com)

Archivist is not a manuscript-upload service, a general-purpose chatbot, or an unrestricted source
browser. The public application never exposes its private manuscript, vector store, full retrieved
chunks, internal traces, or arbitrary file paths.

## Current product

The interactive application currently uses RAG policy `evidence-planned-v26` over **481
retrieval-eligible chunks**. Those chunks cover the Introduction, geological formation, Prologue,
Chapters 1–20, Epilogue, Afterword, and Appendices A–D. Front matter, the table of contents,
acknowledgments, illustration notes, bibliography, printed index, and credits are excluded from
retrieval.

The reader experience includes:

- a one-page, multi-turn conversation with contextual follow-up resolution;
- query decomposition, premise checking, absence handling, evidence-coverage checks, and inline
  source citations;
- **10 semantic modes**: Professional, Essential, Mythical Forest Folio, Cromb Coo Coo, Pretty
  Pink Princess, Baleful Black Baron, Tidal Archivist, Ember & Ink, Illuminated Codex, and Cosmic
  Almanac;
- **11 visual appearances**, available separately under advanced controls;
- Professional as the new-visitor default and Essential as the neutral evidence-first baseline for
  API, CLI, and evaluation callers that omit a mode;
- **Complete answer** as the fail-closed default delivery mode;
- **Progressive response** as an experimental advanced setting that may reveal locally checked,
  cited claims from the same generation call before the canonical answer finishes validation;
- typeset-PDF page locators and tightly bounded excerpts in the public demo; and
- local cost estimates and budget controls for development.

Modes influence framing, emphasis, and prose style. They do not change the manuscript evidence,
retrieval corpus, citation requirements, premise checks, or absence decisions.

Progressive response is not chain-of-thought and does not make a second answer-model call. It may
improve perceived responsiveness, but planning and retrieval still occur before prose can be
released. Any provisional text is discarded if the final response fails validation. Complete
answer remains the reference behavior.

An experimental `full-context-v2` strategy also exists behind server-side feature flags. It is
disabled by default and disabled on the public deployment; the public demo uses the V26 RAG path.

## Architecture

```text
private DOCX and typeset PDF
        |
        v
deterministic preparation, manifest, and edition locators
        |
        v
private Chroma index (481 eligible text-embedding-3-small vectors)
        |
        v
V26 conversation resolution, planning, retrieval, and evidence checks
        |
        v
structured answer generation through the OpenAI Responses API
        |
        v
grounding, citation, premise, completeness, and exposure validation
        |
        +--> development: private diagnostics and full source inspection
        |
        `--> public_demo: page locators and bounded excerpts only
        |
        v
FastAPI service + React/Vite conversation interface
```

The interactive generator, follow-up resolver, and planner currently use the undated
`gpt-5.6-sol` identifier with explicit role-specific settings. That is a development and public-demo
configuration, not a reproducible evaluation pin. A future formal run of record must use separately
declared **dated model snapshots** for the generator and judge; Archivist rejects an undated alias
when run-of-record eligibility is checked.

## Local quickstart

Requirements:

- Python 3.13;
- Node.js and npm;
- `uv`;
- an OpenAI API key; and
- the private runtime corpus already present under `output/` and `chroma_db/`.

Install dependencies and build the frontend:

```powershell
uv sync --frozen
Set-Location frontend
npm ci
npm run build
Set-Location ..
```

Create `.env` in the repository root:

```text
OPENAI_API_KEY=your_project_scoped_key
```

Run the development application:

```powershell
uv run uvicorn web_api:app --app-dir src --reload
```

Open `http://127.0.0.1:8000`. Development mode exposes private diagnostic tools and must not be
published to the internet.

To exercise the hardened public profile locally:

```powershell
$env:ARCHIVIST_EXPOSURE_PROFILE = "public_demo"
$env:ARCHIVIST_PUBLIC_MONTHLY_BUDGET_USD = "5.00"
uv run uvicorn web_api:app --app-dir src
```

## Private data and deployment

The repository ignores the manuscript, typeset PDF, extracted chunks, Chroma database, runtime
bundles, usage databases, API keys, and generated frontend build. Committed fixtures identify the
corpus and edition mapping by stable IDs and hashes rather than by reproducing book text.

The public service searches the same 481-chunk substantive corpus privately. Its startup-selected
`public_demo` profile removes upload, project, indexing, diagnostic, cost-management, and full-source
routes; sanitizes errors; disables API documentation; fixes retrieval depth server-side; limits
request size, rate, concurrency, and monthly spend; and serves only edition-qualified locations and
short excerpts. Page numbers currently refer specifically to **Typeset PDF (July 6, 2026)**.

Build the gitignored deployment bundle only when preparing or refreshing the Render disk:

```powershell
uv run python scripts/build_public_runtime_bundle.py
```

Rebuild the committed, text-free edition locator only from the authorized private PDF:

```powershell
uv run python scripts/build_edition_locators.py `
  "C:\path\to\Cradle_of_the_Empire_FINAL_PDF_revised_0706.pdf"
```

Render hosts the FastAPI service and private runtime disk. `archivist.mcrombie.com` is the canonical
reader URL; the generated `onrender.com` address remains an operational fallback. Deployment,
recovery, environment variables, and smoke checks are documented in
[`docs/public_deployment.md`](docs/public_deployment.md).

## Verification

Run the offline backend checks:

```powershell
uv run ruff check src tests scripts
uv run pytest
```

Run the focused frontend suites and production build:

```powershell
Set-Location frontend
npm run test:delivery
npm run test:modes
npm run build
```

**Verification snapshot — August 5, 2026:** repository-wide Ruff passed; **768 Python tests passed
and 1 was intentionally skipped**; both focused frontend suites passed; and the production frontend
built successfully. These checks are offline and make no paid OpenAI calls. Live deployment behavior
still requires the release smoke checks in the deployment runbook.

## Evaluation status

The familiar ten-question cohort is a development regression set, not held-out evidence. Formal
measurement is paused while the owner completes a separate 34–46-item held-out gold set. Its
questions, strata, expected behaviors, and inclusion decisions are owner-authored; blinded Claude
drafts may assist with evidence annotations, but every field must be checked against the private
corpus, adjudicated by the owner, and rewritten before lock. H020 currently requires replacement
before the question set can be frozen.

No formal benchmark result should yet be claimed. A run of record requires one frozen candidate,
the locked gold set and provenance sidecar, predeclared metrics and thresholds, and dated generator
and judge model snapshots. The V26 interactive application and earlier practical evaluations are
development evidence only.

## Documentation map

- [`B0_project_brief.md`](B0_project_brief.md) — product scope and non-negotiable constraints.
- [`ROADMAP.md`](ROADMAP.md) — current phase, remaining work, and release evidence.
- [`EVAL_CONTRACT.md`](EVAL_CONTRACT.md) — formal measurement and held-out governance contract.
- [`docs/project_notes.md`](docs/project_notes.md) — canonical corpus, model, index, and UI state.
- [`docs/rag_next_optimization_design.md`](docs/rag_next_optimization_design.md) — V26 RAG design
  lineage and contracts.
- [`docs/full_context_answer_strategy_design.md`](docs/full_context_answer_strategy_design.md) —
  disabled full-context experiment.
- [`docs/answer_delivery.md`](docs/answer_delivery.md) — Complete and Progressive delivery rules.
- [`docs/public_demo_design.md`](docs/public_demo_design.md) — public exposure and citation design.
- [`docs/public_deployment.md`](docs/public_deployment.md) — Render deployment and recovery runbook.
- [`docs/gold_set_authoring.md`](docs/gold_set_authoring.md) — private held-out authoring workflow.
- [`docs/cost_tracking.md`](docs/cost_tracking.md) — local estimates, budgets, and billing caveats.
- [`BLOGNOTES.md`](BLOGNOTES.md) and [`DEFECTS.md`](DEFECTS.md) — development narrative and defect
  history.

## Author

Michael Crombie  
B.S. Computer Science & History, William & Mary
