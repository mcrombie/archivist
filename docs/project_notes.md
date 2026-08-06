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

## Current: hold the candidate while the completed gold set is locked

The active retrieval path is `evidence-planned-v26`, with `query-planner-v11` and
`evidence-coverage-v11`. The familiar ten-question cohort is development data: it helped shape the
system and cannot establish a held-out quality claim. On August 6 the owner completed and
mechanically cleaned a private 38-item held-out workbook spanning all six contracted strata; H020
was replaced and all 570 recorded chunk references were found in the frozen inventory. The
candidate remains held while one explicitly documented H039 reading is settled, the workbook is
converted to canonical private JSON, and the cohort is provenance-locked under
`EVAL_CONTRACT.md`. The practical standard preserves realistic user wording, treats claims as
independently scorable rubric units, permits materially useful background, bounds optional
`must_not_claim` tripwires, and records source-verified owner adoption or revision through
`archivist.gold_provenance/3`.

The next engineering work is limited to closing the Markdown/JSON leakage-audit tooling gap and
supporting the declared lock-and-measure sequence. Hybrid retrieval, reranking, threshold changes,
and further answer-quality tuning wait until the gold ruler is frozen and the formal baseline has
identified a measured defect.

## Current generation-model configuration

The interactive answer generator and conversational follow-up resolver are separate roles in the
central model configuration. Both currently use the official `gpt-5.6-sol` model through the
Responses API with explicit `medium` reasoning effort and `medium` verbosity. Those values preserve
the effective defaults of the former `gpt-5` integration while preventing future default changes
from silently changing those two sampling choices. The deferred index-generation path shares the
generator settings.

This development configuration is **not** a formal evaluation pin. OpenAI's currently documented
identifier is `gpt-5.6-sol`, without a dated snapshot suffix. Archivist therefore rejects it when
asked to validate a run-of-record model; no dated identifier has been invented, and the stricter
rule in `EVAL_CONTRACT.md` remains unchanged. A formal baseline stays blocked until an official
dated snapshot is available and selected.

## Current UI scope

The reader-facing interface is being treated separately from retrieval quality. It supports a
multi-turn transcript, contextual follow-up resolution, and ten versioned presets that bind
appearance to answer character: Professional, Essential, Mythical Forest Folio, Cromb Coo Coo,
Pretty Pink Princess, Baleful Black Baron, Tidal Archivist, Ember & Ink, Illuminated Codex, and
Cosmic Almanac. Professional is the new-visitor frontend default. Essential remains the unchanged
Evidence-first + Scholarly + None baseline when an API, CLI, or evaluation caller omits a mode.
The other presets supply bounded literary or editorial influence rather than historical evidence.

An interpretive influence is a reviewed generation instruction, never another answer corpus. It
may shape emphasis, cadence, and judgment after retrieval, but cannot alter query planning,
retrieved chunks, source order, citation obligations, premise handling, or absence decisions.
Professional uses a reviewed method profile distilled from Craven, Beard, and Du Bois; Forest uses
formal qualities distilled from Dunsany's *The King of Elfland's Daughter*. Neither source pack is
placed in Chroma or sent as historical evidence. Exact provenance, hashes, rights cautions, and the
role contract are recorded in `docs/archivist_modes.md`.

Cromb Coo Coo uses the Cromb appearance with Evidence-first + Romantic + Secular humanist defaults
and influence profile `cromb_coo_coo_manuscript/1`. Its reviewed traits are affectionate
absurdity, grotesque high fantasy, comic deflation of grandeur, sensory specificity, tenderness
amid violence, contingency, and eccentric agency. The owner-supplied 226-page private PDF and
temporary extracts stay local: they are neither committed nor sent to an API, and no author is
inferred from the artifact. The profile is generation-only and is forbidden from supplying names,
plot, lore, quotations, facts, evidence, or citations. Reader-facing Cromb style checks remain
development smokes; held-out and gold evaluation continues to use Essential.

Pretty Pink Princess is deliberately and visibly optimistic, while still requiring material harm
to be stated without minimization. Baleful Black Baron makes tragedy, coercion, loss, and
foreclosed possibilities its dominant judgment without inventing them. Tidal Archivist replaces
the Forest mode's Dunsany influence with a reviewed, generation-only Moby-Dick profile frozen to
Project Gutenberg #15. Ember & Ink uses a text-free Realist Statecraft editorial profile associated
with Henry Kissinger's historical tradition; no Kissinger work is ingested, quoted, paraphrased,
imitated, or treated as evidence.

Illuminated Codex uses Evidence-first + Scholarly + Secular humanist defaults with the text-free
`modern_liberal_history/1` profile. It foregrounds rights, dignity, pluralism, toleration,
representative institutions, rule of law, reform, inclusion, accountable power, and gaps between
declared ideals and lived access. It treats progress as contested and reversible, not automatic,
and is explicitly lowercase-l liberal historical analysis rather than current party advocacy.

Cosmic Almanac uses Evidence-first + Scholarly + Enlightenment rationalist defaults with the
text-free `future_science_history/1` profile. It connects long time horizons, systems, demography,
ecology and climate where supported, technology, energy, infrastructure, information, institutions,
path dependence, feedback loops, uncertainty, and plausible future consequences. It cannot invent
future facts, write science fiction, treat a projection as evidence, or assume technological
progress is inevitable. All reader modes remain downstream of retrieval and keep *Cradle* as the sole
source of historical facts and citations.

Evidence scope remains a separate control. The independent Historiographical lens, Voice, and
Worldview selectors now sit under Advanced interpretive settings, together with an explicitly
appearance-only selector that preserves all eleven visual appearances. A custom value applies to
future turns, while each completed turn and retry retains its resolved mode and facets. A non-default
voice changes prose style without guaranteeing more text. A non-Evidence-first lens or non-None
worldview uses a separate structured-output contract with an uncited interpretive opening of two
or three sentences, the ordinary cited factual answer, and an uncited one-sentence interpretive
conclusion. The opening and conclusion must directly name the trusted subject of the question, use
no first-person narration, and flow with the cited middle as ordinary paragraphs in one cohesive
reader-facing answer. Their boundary remains internal: they may make value judgments but may not
introduce historical facts, satisfy factual coverage requirements, or enter follow-up conversation
history as evidence-bearing answer text. Interpretive strength is evidence-conditioned: a tragic
lens, for example, must locate a specific loss, coercion, incomplete reform, failed plan, or other
tension already present in the factual middle rather than manufacture an unnamed human cost or
foreclosed possibility. When several settings are active, the lens supplies one central judgment,
the worldview evaluates that same judgment, and the voice shapes its expression.

Complete answer is the recommended fail-closed delivery default. Progressive response is an
experimental Advanced setting: it streams only locally checked, complete cited claims from the
same answer-model request and still withholds the canonical turn until terminal validation passes.
It is not chain-of-thought, does not remove planning or retrieval latency, and is not the formal
evaluation presentation.

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
