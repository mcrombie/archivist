# Archivist

Archivist is a source-grounded conversational interface for one book:
*Cradle of the Empire: A Big History of Virginia*. It searches a private full-manuscript retrieval
index, answers with inline `[Source N]` citations, remembers the open conversation, and offers
versioned reader modes that combine visual presentation with bounded interpretive framing.

It is not a manuscript-upload service or a general-purpose chatbot.

Public demo: [https://archivist.mcrombie.com](https://archivist.mcrombie.com)

## Current product

- one-page, conversational book interface;
- contextual follow-up questions;
- query decomposition, premise checks, absence handling, and source-bounded completeness checks;
- ten reader-facing modes: Professional, Essential, Mythical Forest Folio, Cromb Coo Coo,
  Pretty Pink Princess, Baleful Black Baron, Tidal Archivist, Ember & Ink, Illuminated Codex, and
  Cosmic Almanac, with Professional as the new-visitor frontend default;
- an unchanged Essential evidence-first baseline for API, CLI, and evaluation callers that omit a
  mode;
- Historiographical lens, Voice, Worldview, and all eleven visual appearances under Advanced
  controls;
- Complete answer as the recommended fail-closed delivery default, with an experimental
  Progressive response that streams the same final-generation API call and reveals only complete,
  locally checked factual claims while the canonical answer is still being validated;
- interpretive influence profiles that shape framing only, never retrieval, evidence, or citations;
- local OpenAI usage estimates and budget controls;
- 481 retrieval-eligible chunks covering the complete substantive manuscript;
- edition-qualified public citations for `Typeset PDF (July 6, 2026)`;
- development and public-demo exposure profiles.

The printed Index, bibliography, table of contents, acknowledgments, illustration notes, and
credits are not part of the answer corpus. The Introduction, geological formation, Prologue,
Chapters 1–20, Epilogue, Afterword, and Appendices A–D are searchable.

## Architecture

```text
private manuscript chunks
        |
        v
private Chroma embedding index (481 records)
        |
        v
query planning and conversational resolution
        |
        v
retrieval, premise checking, and evidence coverage
        |
        v
GPT-5.6 Sol structured answer generation
        |
        +--> Progressive (experimental): claim-level release checks
        |                                  while generation continues
        |
        `--> Complete: no prose released before terminal validation
        |
        v
whole-answer grounding and [Source N] validation
        |
        v
edition-locator and exposure-policy release checks
        |
        +--> development: full diagnostic passages
        |
        `--> public_demo: page locators and bounded excerpts
```

The book is not sent to the answer model on every request. Archivist embeds the question, retrieves
a bounded set of relevant private chunks, and supplies only that evidence to answer generation.

## Answer delivery

**Complete** is the default and the evaluation reference. It withholds answer prose until the full
response has passed Archivist's grounding, citation, premise, completeness, and exposure checks.
If a terminal check fails, the rejected prose is never presented as an answer.

**Progressive** is an experimental presentation mode. It does not make a preview request or a
second answer request: the backend streams the existing final-generation call using the
`archivist.answer_stream/2` NDJSON protocol. It privately buffers structured-output deltas and may
release a complete factual claim only after checking its order, role, citations, source mapping,
and size. The shared generation schema places answer claims before terminal-only validation
ledgers, and the first releasable factual claim must be a direct, subject-linked sentence of no
more than 45 words. In the public profile, every provisional claim must also pass edition-locator
and rolling quotation-budget checks before it leaves the server.

The interface marks this material **Checked partial · Not final**. Provisional claims are excluded
from conversation memory, copying, and the final source display. A successful terminal event
replaces them with the canonical validated answer; an interruption or late validation failure
clears them. Interpretive prefaces and conclusions remain withheld until terminal validation.

Progressive delivery is not chain-of-thought, raw token streaming, or a promise that the whole
request will finish faster. Query resolution, planning, embeddings, retrieval, and evidence checks
still happen before final generation begins. Its narrower goal is to reduce the wait for the first
useful, releasable claim once that generation is underway, without adding another answer-model
call. While prose is unavailable, three-second heartbeat frames keep a visible elapsed-work
indicator moving without exposing model reasoning. Complete and Progressive use the same prompt
and schema within the current `evidence-coverage-v11` and `full-context-coverage-v3` generation
cohorts. A live deployment smoke test is still required before treating first-claim timing as
deployment-verified.

## Local setup

Requirements:

- Python 3.13;
- Node.js and npm;
- `uv`;
- an OpenAI API key;
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

Run the local development application:

```powershell
uv run uvicorn web_api:app --app-dir src --reload
```

Then open `http://127.0.0.1:8000`.

Development mode is the default. It preserves the full diagnostic source display and the local
cost interface. Do not expose this profile to the public internet.

## Public-demo profile

The public profile is selected only at server startup:

```powershell
$env:ARCHIVIST_EXPOSURE_PROFILE = "public_demo"
$env:ARCHIVIST_PUBLIC_MONTHLY_BUDGET_USD = "5.00"
uv run uvicorn web_api:app --app-dir src
```

Public mode:

- fixes retrieval depth on the server;
- removes upload, project, embedding, index, source-file, and cost-management routes;
- hides full chunks, internal paths, diagnostics, and per-turn costs;
- maps citations to a named edition;
- limits excerpts to 280 characters each, three excerpts, and 700 characters total;
- applies the same locator and rolling quotation limits to every provisional Progressive claim;
- enforces request-size, per-client, global, concurrency, and monthly-spend limits;
- disables API documentation and sanitizes errors.

See [`docs/public_demo_design.md`](docs/public_demo_design.md) for the disclosure design,
[`docs/answer_delivery.md`](docs/answer_delivery.md) for the Complete/Progressive transport and
release contract, and [`docs/public_deployment.md`](docs/public_deployment.md) for the Render
deployment and recovery runbook. The generated
[`onrender.com`](https://archivist-cradle-of-the-empire.onrender.com) address remains enabled as
an operational fallback, but `https://archivist.mcrombie.com` is the canonical reader-facing URL.

## Edition locators

The committed locator fixture contains no book text:

```text
fixtures/edition_locators/typeset_pdf_0706.json
```

Its 481 records are bound to the exact typeset PDF, chunks, and corpus-manifest hashes. These page
numbers apply only to `Typeset PDF (July 6, 2026)`. Future paperback, hardcover, and ebook profiles
can reuse stable chunk IDs without changing retrieval or re-embedding the manuscript.

The private PDF is required only when deliberately rebuilding the locator artifact:

```powershell
uv run python scripts/build_edition_locators.py `
  "C:\path\to\Cradle_of_the_Empire_FINAL_PDF_revised_0706.pdf"
```

## Private runtime bundle

The public deployment receives its full retrieval corpus through a private, gitignored archive:

```powershell
uv run python scripts/build_public_runtime_bundle.py
```

The archive contains the pruned Chroma collection and its matching chunks, but not the source DOCX
or PDF. It remains private and must never be committed or attached to a public release.

## Cost tracking

Archivist records local per-operation estimates for OpenAI Responses and embeddings. Use a
project-scoped OpenAI key for clean attribution. The OpenAI Usage Dashboard remains the billing
source of truth; local estimates are an operational guardrail.

See [`docs/cost_tracking.md`](docs/cost_tracking.md).

## Verification

Run backend checks:

```powershell
uv run ruff check src tests scripts
uv run pytest
```

Run the focused frontend delivery and reader-mode checks, then the production build:

```powershell
Set-Location frontend
npm run test:delivery
npm run test:modes
npm run build
```

These checks are offline and do not make paid OpenAI API calls. The current local implementation
passes Ruff, 760 Python tests (with one skipped), both focused frontend suites, and the production
build. Progressive delivery still requires the live deployment smoke described above.

The repeatedly used ten-question set is a development regression suite, not held-out evidence.
Formal measurement is gated on a separately owner-authored 34–46 item gold set whose questions,
claims, and source locations are locked before any item is run. Passing the public security
boundary does not by itself mean every historical answer is correct.

## Privacy

The repository intentionally ignores the manuscript, PDF, chunks, vector store, runtime bundles,
usage databases, API keys, and generated frontend build. Public responses disclose only generated
answers, source numbers, edition-qualified page locations, and tightly bounded excerpts.

## Author

Michael Crombie  
B.S. Computer Science & History, William & Mary
