# Archivist Public Demo and Edition Locator Design

**Status:** pre-implementation design, 2026-07-27  
**Scope:** public source disclosure, edition-specific locators, and the safety gate before Cromblog
integration  
**Out of scope for this document:** retrieval tuning, answer-generation quality, deployment-provider
selection, and implementation

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

## What an index means here

The RAG index is not the printed index at the back of the book. It is the private Chroma collection
containing embeddings for the 481 retrieval-eligible manuscript chunks. At question time Archivist
embeds the question, finds relevant chunks in that collection, and sends only the selected evidence
to the answer model. Searching the complete manuscript therefore does not mean sending the
594-page book to the model on every turn.

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

### Feasibility pilot

A read-only alignment pilot normalized the active 481 chunks and the text extracted from all 594
PDF pages, then sampled six 12-token anchors across each chunk. Every eligible chunk produced at
least two exact anchors in the PDF:

| Preliminary mapped span | Chunks |
|---|---:|
| One physical page | 39 |
| Two physical pages | 360 |
| Three physical pages | 76 |
| Four physical pages | 6 |
| Unmapped | 0 |

This establishes that deterministic mapping is viable even though the DOCX and PDF are different
file representations. It is not yet the production locator artifact. Production mapping must also
verify monotonic order, resolve repeated phrases, bind every result to both source hashes, and
visually inspect boundary cases.

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

The first generated artifact should be
`fixtures/edition_locators/typeset_pdf_0706.json`. It may be committed only if it contains chunk
identifiers, edition metadata, page labels, hashes, confidence values, and no manuscript text. The
PDF itself remains private and gitignored.

Future profiles can add paperback, hardcover, and ebook locators without changing chunk IDs,
embeddings, retrieval, prompts, answers, or evaluation cohorts. Ebook editions may use a
`location` or `section` locator when stable page numbers do not exist. One profile is selected as
the server's display default; a reader-facing edition selector can be added later after at least
two verified profiles exist.

## Public citation and quotation contract

The model-facing citation contract remains `[Source N]`. Edition mapping happens after generation,
in presentation, so adding or changing a locator profile cannot change retrieval results or
measured answer behavior.

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

The public answer prompt should prefer concise paraphrase and forbid extended reproduction.
Separate output checks should flag unexpectedly long verbatim overlap before a response is
released. This is complementary to, not a substitute for, the source-payload limits.

## Public API boundary

The public deployment should expose an allowlisted API rather than attempting to hide local routes
in the frontend. At minimum:

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

The public build must be tested from an anonymous browser against route enumeration, not merely
through the intended UI.

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

## Cromblog integration gate

Cromblog integration remains straightforward but should wait until this public boundary exists.
The eventual flow is:

1. deploy Archivist as a separate, long-running service with its private full-corpus artifact;
2. verify public mode, page locators, excerpt limits, rate limits, cost limits, and long-answer
   behavior anonymously;
3. turn Cromblog's existing Archivist feature panel into a live-demo link;
4. add Archivist as a project entry with a clear explanation that it queries one published book;
5. add no Archivist blog post until the shareable version and its disclosed limitations are ready.

## Deferred edition work

The schema reserves room for:

- paperback page numbering;
- hardcover page numbering;
- ebook page or location numbering;
- a future reader selector between verified editions.

Those profiles cannot be populated until the owner supplies the relevant pagination or edition
artifact. Their absence must not block the typeset-PDF profile or the first public demo.
