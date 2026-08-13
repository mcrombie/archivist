# Archivist Project Notes

## Canonical manuscript status

Michael supplied the authoritative July 6 DOCX for *Cradle of the Empire*. Its SHA-256 is
`81d172186475e8f9a63070ceacb85cac0ffb411159b02cf4acc59fb78eedc3b8`. The deterministic
preparation is active and verified: 36 Markdown documents, 910 total chunks, 34 Heading 1
sections, and 629 resolved footnotes. The owner has since settled an Introduction-first retrieval
and evaluation boundary: `01_Front Matter.md`, `02_Table of Contents.md`,
`03_Acknowledgments.md`, and `04_Note on Illustrations.md` are excluded, along with documents
matched by the `32_Bibliography.md` sentinel under substring matching. This leaves 481
retrieval-eligible chunks and seven skipped documents; the Epilogue, Afterword, and appendices
remain in scope.

The supplied 594-page typeset PDF is now the first edition-locator authority. Its SHA-256 is
`89d68cdc186432d4d4804fbaff6aac0deb599d351dd016fe250b25f2a4771b3f`. A read-only feasibility
pilot found at least two exact 12-token PDF anchors for every one of the 481 eligible chunks:
39 preliminary spans covered one physical page, 360 covered two, 76 covered three, and 6 covered
four. The PDF uses Roman-numbered front matter (the Introduction begins on `xi`) and restarts
Arabic numbering at the Prologue; public citations must therefore say
`Typeset PDF (July 6, 2026), p./pp. ...`, never present a bare page number. This mapping is
presentation metadata over the current DOCX corpus, not a claim that the two files are identical.

At the initial July 6 activation, after explicit owner authorization, the 488 chunks then eligible
under the earlier scope were embedded with
`text-embedding-3-small` in 10 calls totaling 215,381 tokens. Archivist's local ledger estimates
the indexing cost at `$0.00430762`. That historical cost remains unchanged. The active
Introduction-first collection reuses 481 of those vectors, made no new embedding API calls, uses
explicit L2 distance, and matches the current text-free corpus manifest, whose SHA-256 is
`b7ff94315a3f1f28c831e2c3ca62c385567d2b1447c19ff45139d175c3ff3c17`.

The former April reader corpus remains recoverable under
`old_manuscript/snapshots/2026-04-active-before-0706/`; a second pre-promotion holding copy is
retained under `runtime/corpus-staging/0706/replaced-active/`. The shared Chroma store's nine
non-reader collections were preserved with identical records and metadata. The immediately
preceding 488-vector store and its manifest remain recoverable under
`runtime/corpus-staging/introduction-scope-20260723/replaced-active/`.

## Current application-compiled release

Current built-in RAG uses `application-compiled-v1`. Follow-up resolution and BM25 ranking are
local. Application code compiles at most three bounded immutable evidence cards, including their
mechanical `[Source N]` citations. Essential returns that direct evidence with zero provider
calls.

Professional, Pretty Pink Princess, and Baleful Black Baron each make exactly one no-retry
`gpt-5.6-sol` call with low reasoning. The response may contain only exact evidence-card
placeholders and typed IDs from that mode's closed editorial cue catalog. The application—not the
model—supplies every factual sentence, editorial sentence, label, and citation. Raw prose,
unknown or cross-mode cues, missing or duplicated cards, and provider/client failure all fail
closed to the direct Essential answer.

The public runtime reports this boundary through `archivist.public_runtime_identity/3`, including
`answer_policy_version=application-compiled-v1`, `evidence_retrieval_kind=local_bm25`, and
`generated_prose_model=gpt-5.6-sol`. Frozen V26 and the V27 experiment remain explicit development
API compatibility policies; neither is selectable in the reader UI. Results from their historical
cohorts do not measure the current application-compiled product.

## Historical snapshot: candidate hold before the completed gold lock

As of August 6, the active retrieval path was `evidence-planned-v26`, with `query-planner-v11` and
`evidence-coverage-v11`. The familiar ten-question cohort was development data: it helped shape the
system and could not establish a held-out quality claim. On August 6 the owner completed and
mechanically cleaned a private 38-item held-out workbook spanning all six contracted strata; H020
was replaced and all 570 recorded chunk references were found in the frozen inventory. The
candidate remained held while one explicitly documented H039 reading was settled, the workbook was
converted to canonical private JSON, and the cohort was provenance-locked under
`EVAL_CONTRACT.md`. The practical standard preserves realistic user wording, treats claims as
independently scorable rubric units, permits materially useful background, bounds optional
`must_not_claim` tripwires, and records source-verified owner adoption or revision through
`archivist.gold_provenance/3`.

That work was subsequently completed and is preserved in the frozen evaluation record. This dated
snapshot is not the current product architecture or current next-step list.

## Current provider configuration

Essential current RAG has no provider configuration because it makes zero provider calls. The
three generated modes use `gpt-5.6-sol` with explicit low reasoning and low verbosity for one
no-retry arrangement call. It selects card placeholders and local cue IDs; it does not generate
reader-visible prose. The current local follow-up resolver is provider-free.

This interactive selector configuration is not a formal evaluation result or a retrospective pin
for V26. Model identity and settings for a future `application-compiled-v1` measurement belong in
that separately declared cohort's run identity.

## Current UI scope

The reader-facing interface is being treated separately from retrieval quality. It supports a
multi-turn transcript, local contextual follow-up resolution, and exactly four selectable modes:
Professional, Essential, Pretty Pink Princess, and Baleful Black Baron. Professional is the
new-visitor frontend default. Only their four matching appearances are selectable. Historical
mode IDs, profiles, definitions, and visual assets remain dormant for compatibility; they are not
offered by the current UI or public API. Their provenance records remain in
`docs/archivist_modes.md`.

Essential renders the locally compiled evidence directly. In the other three modes the one
optional model call selects card order and typed application-owned cue IDs. The interface never
displays model-authored prose: exact evidence text, interpretations, character asides, labels, and
citations are all substituted locally. A selector failure returns the Essential evidence rather
than replaying the call.

Evidence scope remains a separate control. The independent Historiographical lens, Voice, and
Worldview selectors now sit under Advanced interpretive settings, together with an explicitly
appearance-only selector limited to the same four appearances. A custom value applies to future
turns, while each completed turn and retry retains its resolved mode and facets. The selected
settings constrain which local cues the generated-mode selector may choose; they never authorize
free prose. No V26/V27 policy or latency selector appears in the UI.

Complete answer is the recommended fail-closed delivery default. Progressive response is an
experimental Advanced setting: it releases the locally compiled immutable evidence cards while
the final arrangement remains provisional, then replaces that working view with the canonical
answer. Essential uses no provider; generated modes use the same one selector call as Complete
answer, not an additional call. It is not chain-of-thought and is not the formal evaluation
presentation.

## Public demo and edition locators

The public demo at `https://archivist.mcrombie.com` searches the same complete 481-chunk
substantive corpus as local development.
The earlier representative-subset proposal is superseded. Manuscript protection moves to the
response boundary: the full corpus and Chroma index remain private on the server, while public
source cards expose edition-qualified locators and only brief, server-bounded quotations.

Local development retains the current full-passage source display because it is useful for
diagnosing retrieval and citation failures. The public/development distinction is a server startup
profile and cannot be selected by the browser. Public mode also removes the local upload,
embedding, source-browser, source-file, index, mutable-budget, and budget-override surfaces.

Locator metadata is edition-specific and keyed by stable chunk ID. The first profile is
`typeset_pdf_0706`; later paperback, hardcover, and ebook profiles can be added without rebuilding
embeddings or changing retrieval. Ebook profiles may use locations or sections rather than pages.
See `docs/public_demo_design.md` for the source DTO, preliminary excerpt budget, mapping acceptance
criteria, and Cromblog integration gate.

The app is hosted as the Render service `archivist-cradle-of-the-empire`; its generated
`onrender.com` address remains enabled as a fallback. Cloudflare supplies a DNS-only `archivist`
CNAME, Render owns certificate issuance for the custom domain, and Cromblog's Vercel Production
environment points `NEXT_PUBLIC_ARCHIVIST_URL` at the canonical address.

The first live public-answer test found a boundary mismatch rather than a RAG failure. Public mode
correctly omitted private `run_diagnostics`, but the frontend treated that object as required and
crashed after the response arrived. Commit `1dd45aa` made the public-only response fields optional,
guarded their reads, and moved the stored-vibe initializer into the CSP-compliant bundle. Public
payload omission and frontend optional handling are now paired release checks.
