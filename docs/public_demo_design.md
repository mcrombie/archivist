# Archivist Public Demo and Edition Locator Design

**Status:** implemented, deployed, and publicly verified, 2026-07-28
**Scope:** public source disclosure, edition-specific locators, and the safety gate before Cromblog
integration  
**Out of scope for this document:** retrieval tuning and the broader ten-question answer-quality
evaluation

## Implementation outcome

The design is now represented in code:

- a verified, text-free locator artifact covers all 481 retrieval-eligible chunks;
- `development` and `public_demo` are startup-only server exposure profiles;
- public source objects contain edition-qualified locations and bounded excerpts rather than
  diagnostic chunks;
- the public app exposes an explicit route allowlist, server-fixed retrieval depth, rate and
  concurrency controls, a hard monthly OpenAI ceiling, safe errors, and security headers;
- the private public-runtime archive has passed the same full corpus/store identity preflight as
  the local application;
- a Render Blueprint and an owner runbook prepare a paid single-instance service with an encrypted
  persistent disk;
- the canonical demo is `https://archivist.mcrombie.com`, with Render's generated subdomain kept
  as an operational fallback;
- Cromblog discovers that address through `NEXT_PUBLIC_ARCHIVIST_URL` without hard-coding hosting
  details into either repository; and
- the browser defaults new visitors to Professional while the omitted-mode API resolves to
  Essential; current RAG identifies itself as `application-compiled-v1` through public runtime
  identity schema `archivist.public_runtime_identity/3`.

The public smoke performed on July 27 used four paid turns: a focused opening question, a
context-dependent follow-up, a broad tobacco/labor question, and a deliberate absence question.
The three answerable turns succeeded; the absent fact produced `insufficient_evidence`. Measured
latencies were 32.63, 16.27, 51.21, and 3.86 seconds. The isolated ledger estimated `$0.27691761`
for the complete smoke.

## Product decision

Archivist will use the same complete retrieval-eligible manuscript in development and in the public
demo. For the current corpus, that means all 481 substantive chunks spanning the Introduction
through Appendix D. The public/private distinction is not which parts of the book can be searched;
it is how much source text a reader can retrieve from the application.

The current large source blocks remain useful during local development because they make retrieval
failures and citation mappings inspectable. They must not be available from the public deployment.
The application therefore needs two server-selected presentation profiles over one retrieval and
generation path:

| Profile | Retrieval corpus | Reader-facing source display |
|---|---|---|
| `development` | All 481 eligible chunks | Current full-passage diagnostic display and local-only tooling |
| `public_demo` | All 481 eligible chunks | Edition-qualified page locators plus tightly bounded quotations |

The profile is a server startup setting, never a query parameter, browser preference, or hidden UI
toggle. A public client must not be able to request development payloads.

This supersedes the earlier representative-subset proposal. The full corpus stays private on the
server; public responses disclose only the answer, citation metadata, page locators, and short
claim-local excerpts.

## Reader modes and public disclosure

Reader modes do not widen the public evidence boundary. Exactly four modes are selectable:
Professional, Essential, Pretty Pink Princess, and Baleful Black Baron. Their four matching
appearances are the only selectable appearances. Dormant IDs, reviewed historical profiles, and
visual assets remain in the repository for compatibility but are not public choices.

Current RAG ranks with local BM25 and application code compiles bounded immutable evidence cards.
Essential returns those cards directly and makes zero provider calls. Professional, Pretty Pink
Princess, and Baleful Black Baron each make exactly one no-retry `gpt-5.6-sol` call with low
reasoning. That call selects only exact evidence-card placeholders and typed IDs from the selected
mode's closed, application-owned cue catalog. Local code supplies every displayed factual word,
editorial word, label, and citation. Raw prose, unknown or cross-mode cues, malformed card use, or
provider/client failure cannot enter the answer and instead produce the direct Essential evidence.
See `docs/archivist_modes.md` for the current registry and preserved historical provenance.

The public request contract accepts only allowlisted mode IDs and resolved facet values. It does
not accept prompt text, source paths, arbitrary influence identifiers, or raw influence excerpts.
The response records mode, compiler, and selector metadata for reproducibility. Advanced overrides
are reader-visible and apply only to future turns; completed answers retain their resolved
settings. The UI has no V26/V27 selector. Those policies remain accessible only through explicit
development API compatibility requests.

## What an index means here

The RAG index is not the printed index at the back of the book. The private runtime retains the
481 retrieval-eligible manuscript chunks and the frozen Chroma collection used by explicit legacy
policies. Current `application-compiled-v1` RAG ranks those private chunks with local BM25 and
compiles only the selected bounded evidence cards. Essential sends no question or evidence to an
answer model. A generated mode sends only the question, selected cards, and closed selector
contract to its one optional arrangement call; it never sends the 594-page book.

The printed Index, front matter, table of contents, acknowledgments, illustration notes,
bibliography, and illustration credits remain outside the answer corpus. The complete substantive
text - Introduction, geological formation, Prologue, Chapters 1-20, Epilogue, Afterword, and
Appendices A-D - remains searchable.

## Typeset PDF locator profile

The first locator profile is tied explicitly to the supplied typeset PDF:

| Field | Value |
|---|---|
| Profile ID | `typeset_pdf_0706` |
| Display name | `Typeset PDF (July 6, 2026)` |
| Filename | `Cradle_of_the_Empire_FINAL_PDF_revised_0706 (1).pdf` |
| SHA-256 | `89d68cdc186432d4d4804fbaff6aac0deb599d351dd016fe250b25f2a4771b3f` |
| Physical PDF pages | 594 |
| Locator kind | `page` |
| Corpus manifest SHA-256 | `b7ff94315a3f1f28c831e2c3ca62c385567d2b1447c19ff45139d175c3ff3c17` |

PDF-internal page labels are simple physical positions from 1 through 594 and are not suitable for
reader citations. The typeset book uses Roman-numbered front matter and restarts Arabic numbering
at the Prologue:

- the Introduction begins on typeset page `xi`, physical PDF page 11;
- the Prologue begins on typeset page `1`, physical PDF page 19;
- in the Arabic body, the typeset page is the physical PDF page minus 18;
- chapter-opening pages may suppress the visible footer, but their page label remains inferable
  from the continuous typeset sequence.

Every public page citation must name its edition. Use `Typeset PDF (July 6, 2026), p. 33` or
`Typeset PDF (July 6, 2026), pp. 33-35`, never an unqualified `p. 33`.

### Production locator result

A deterministic alignment pass normalized the active 481 chunks and text extracted from all 594
PDF pages, then combined six sampled 12-token anchors with dense boundary anchors and monotonic
document-order checks. Every eligible chunk received an edition locator:

| Verified mapped span | Chunks |
|---|---:|
| One typeset page | 31 |
| Two typeset pages | 353 |
| Three typeset pages | 97 |
| Unmapped | 0 |

The artifact verifies input hashes, resolves repeated anchors without allowing document order to
regress, binds results to the source and corpus identities, and records confidence and method
without manuscript text. Stratified visual review covered the Introduction, the numbering
transition, chapter openings, footnote-heavy and multi-page chunks, Epilogue, Afterword, and
appendices. That review corrected Appendix B's endpoint from page 451 to pages 451–452.

## Edition-independent locator model

Page numbers are edition facts, not manuscript facts. Locator records therefore belong in a
separate presentation artifact keyed by stable chunk ID:

```text
EditionProfile
  edition_id
  display_name
  locator_kind             # page, location, or section
  source_asset_sha256
  corpus_manifest_sha256
  mapping_version
  status

ChunkLocator
  chunk_id
  edition_id
  label_start              # string so Roman numerals and ebook locations are valid
  label_end
  physical_page_start      # internal alignment aid; not required in the public payload
  physical_page_end
  confidence
  method
```

The first generated artifact is
`fixtures/edition_locators/typeset_pdf_0706.json`. It contains chunk
identifiers, edition metadata, page labels, hashes, confidence values, and no manuscript text. The
PDF itself remains private and gitignored.

Future profiles can add paperback, hardcover, and ebook locators without changing chunk IDs,
embeddings, retrieval, prompts, answers, or evaluation cohorts. Ebook editions may use a
`location` or `section` locator when stable page numbers do not exist. One profile is selected as
the server's display default; a reader-facing edition selector can be added later after at least
two verified profiles exist.

## Public citation and quotation contract

In current RAG, `[Source N]` is application-owned. The evidence compiler assigns it mechanically,
and the optional selector can reference only the exact evidence-card placeholder; it cannot write
or renumber citations. Edition mapping remains a local presentation step, so adding or changing a
locator profile cannot change retrieval results or the immutable evidence text. Explicit V26/V27
compatibility policies retain their historical model-facing citation contract.

Every cited public source receives:

- source number;
- chapter or document title;
- explicitly named edition profile;
- page or location range;
- an optional, claim-local quotation within the public excerpt budget.

The initial public excerpt budget is deliberately conservative and server enforced:

- no more than 280 Unicode characters and two sentences for one excerpt;
- no more than three quoted excerpts per answer;
- no more than 700 quoted characters across the answer's source panel;
- truncation at word or sentence boundaries with a visible ellipsis;
- no previous/next passage controls and no endpoint for fetching surrounding text;
- direct requests for quotation remain subject to the same limits.

Every cited source can still show its edition locator even when it does not receive one of the
three excerpt slots. These figures are implementation defaults to validate with disclosure tests,
not a licensing claim.

The current evidence compiler enforces bounded excerpt cards before answer assembly. Public output
checks and source-payload limits remain separate safeguards; a selector response cannot introduce
additional manuscript prose because local rendering accepts no free text.

## Public API boundary

The public deployment exposes an allowlisted API rather than attempting to hide local routes in
the frontend:

- allow the health check and the built-in manuscript question endpoint;
- return a public source DTO with locators and bounded `excerpt`, never full `text` or merged
  `display_groups`;
- disable or authenticate project creation, upload, embedding, index-generation, source-browser,
  source-search, source-file, and cost-settings endpoints;
- remove the client-controlled `allow_over_budget` escape hatch;
- enforce server-side monthly spend, per-client request, concurrency, and abuse limits;
- disable public OpenAPI and documentation routes;
- replace raw exception messages with public-safe errors;
- keep the OpenAI key, chunks, Chroma store, source PDF, and manuscript files server-side.

Direct anonymous HTTP checks verified the release boundary independently of the intended UI:
documentation, management, source, embedding, cost, and custom-project routes return `404`;
client-supplied tuning returns `422`; oversized input returns `413`; and the request gate returns
`429` with `Retry-After`. Public responses also carry CSP, frame, referrer, and MIME-sniffing
protections.

## Production mapping acceptance criteria

The first edition locator implementation is complete only when:

1. the input PDF and corpus manifest hashes match the profile;
2. all 481 eligible chunks receive a locator;
3. mapped locations are monotonic within each document except for explicitly reviewed repeats;
4. locator labels handle Roman front matter, Arabic body pages, and suppressed chapter-opening
   footers correctly;
5. a stratified visual review covers the Introduction, numbering transition, chapter openings,
   footnote-heavy pages, multi-page chunks, Epilogue/Afterword, and appendices;
6. the committed mapping artifact contains no manuscript or PDF text;
7. public API tests prove that full text and local-only routes cannot be requested;
8. development-mode tests prove that the existing diagnostic source view remains available
   locally;
9. retrieval, source ordering, `[Source N]` resolution, and evaluation results are unchanged.

## Cromblog integration outcome

The integration gate passed on July 28, 2026:

1. Archivist runs as a separate Render service with its private full-corpus artifact on the
   persistent disk.
2. Public mode, page locators, excerpt limits, rate limits, cost limits, and the disclosure
   boundary passed anonymous checks.
3. Cloudflare routes the DNS-only `archivist` CNAME to
   `archivist-cradle-of-the-empire.onrender.com`; Render verified
   `archivist.mcrombie.com` and issued its certificate.
4. Cromblog's Vercel Production environment sets
   `NEXT_PUBLIC_ARCHIVIST_URL=https://archivist.mcrombie.com`, and its featured panel and project
   entry expose that live link.
5. Render's generated address remains enabled as a fallback. The announcement blog post remains a
   separate editorial step.

The first live answer also exposed a useful contract defect: public payloads correctly omit
private `run_diagnostics`, while the frontend had assumed the object was always present. Commit
`1dd45aa` made those fields optional, guarded the UI diagnostic reads, and moved an inline
startup script into the CSP-compliant bundle. The release check now treats a minimal public
answer—with no private diagnostics—as the required frontend shape rather than an exceptional one.

## Deferred edition work

The schema reserves room for:

- paperback page numbering;
- hardcover page numbering;
- ebook page or location numbering;
- a future reader selector between verified editions.

Those profiles cannot be populated until the owner supplies the relevant pagination or edition
artifact. Their absence must not block the typeset-PDF profile or the first public demo.
