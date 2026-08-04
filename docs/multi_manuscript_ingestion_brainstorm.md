# Multi-manuscript ingestion exploration

Status: exploratory branch only. This document proposes a bounded second-corpus experiment; it
does not change Archivist's current product identity, public deployment, evaluation candidate, or
private *Cradle of the Empire* corpus. No second corpus may call a generalized shared path until
that path has first reproduced the current corpus's deterministic behavior exactly.

## Why explore this

Archivist is intentionally built around one known book. That focus made it possible to develop a
serious corpus contract, source-grounded answers, edition-aware citations, privacy controls, and an
evaluation methodology. A second curated book could now test whether the underlying plumbing is
actually reusable without turning Archivist back into an ingest-anything upload service.

The useful question is not "Can Chroma hold two collections?" It already can. The useful question
is: **which assumptions belong to one corpus, which belong to a class of long historical works, and
which still leak the current book's identity into the engine or deployment?**

## Proposed first experiment

Start with one Virginia history whose text is clearly in the public domain and available in a
reliable digital edition. A promising first candidate is Robert Beverley's *The History and Present
State of Virginia*. It is thematically related, historically distant from the current book, and
small enough to expose ingestion and metadata problems without immediately creating another
500-page evaluation project.

"Beverley's History" is not yet a sufficient source identity. Beverley substantially revised the
1705 text for a 1722 second edition. The pilot must select a digital transcription whose base text
is identified well enough to distinguish those versions; an unattributed transcription is rejected
at intake. For Archivist's model, the 1705 and 1722 texts are **separate corpora** within the same
work family, not two locator profiles or normalization revisions of one corpus. A future
1705-versus-1722 feature would therefore be a cross-corpus comparison.

Other candidates worth comparing before selection:

- William Stith, *The History of the First Discovery and Settlement of Virginia* (1747);
- Charles Campbell, *History of the Colony and Ancient Dominion of Virginia* (1860); and
- a suitably stable public-domain state history from the late nineteenth or early twentieth
  century.

Before downloading anything, record the exact work, edition, host, file format, source URL,
download date, source hash, and public-domain rationale. "The underlying work is old" is not enough
to identify a usable digital edition: an edition can contain later editorial material, OCR, or
images with different rights and quality.

## Product shapes, in increasing order of difficulty

### 1. One selected book per conversation — recommended first

The reader chooses a book before asking a question. A conversation is permanently bound to that
corpus. Retrieval, answers, citations, cost records, and follow-up resolution all remain isolated
inside it.

This tests real multi-corpus plumbing while preserving Archivist's clearest mental model: a
conversation with one book.

### 2. Parallel comparison

The reader asks one question and receives two independently grounded answers, one from each book.
Each answer keeps its own source list and clearly named corpus identity. A comparison layer may
describe agreements or differences only after both source-bounded answers exist.

This could become a compelling historical feature: not merely asking what happened, but seeing how
a 1705 account and a modern synthesis construct Virginia differently.

### 3. Blended multi-book synthesis — defer

One answer draws evidence from multiple corpora. This creates harder provenance, ranking,
completeness, citation, interpretation, and evaluation questions. It should not be approximated by
concatenating collections or allowing the model to blur which book supports which statement.

## What already exists

Archivist already contains much of a local multi-project skeleton:

- project directories with manifests, chunks, source files, and existing-index data;
- separate Chroma collection names per project;
- upload/import, build, embed, list, and question endpoints in the development API; and
- a shared retrieval core capable of accepting a collection and chunk list.

That is not yet equivalent to first-class multi-manuscript support:

- `current` receives the strongest corpus-manifest and integrity checks;
- non-current projects still use a legacy answer path;
- the public API and reader UI are deliberately bound to `current`;
- public source disclosure, edition locators, evaluation identity, and deployment readiness assume
  one corpus; and
- project creation currently describes a generic upload workflow rather than a curated library of
  known books.

The experiment should promote one additional curated corpus to parity. It should not revive the
generic upload interface as the public product.

## Corpus A parity gate

The first implementation subject is not the public-domain book. It is the existing *Cradle of the
Empire* path, treated as **corpus A**. Before generalization, capture a text-free conformance
artifact from the frozen implementation. Then extract the integrity logic into a pure function
while the existing `current` wrapper continues supplying its present hardcoded paths, collection,
manifest, and policy values.

Before corpus B may call that function, corpus A must reproduce exactly:

- the corpus-manifest, chunk-set, index, and configuration identities;
- every existing chunk ID as the same byte-for-byte string and every chunk text hash;
- the ordered primary and final-context chunk IDs for every locked gold question;
- the byte-identical serialized deterministic gold-retrieval report, including every per-question
  and aggregate score and denominator;
- the ordered source list and serialized generator-facing context/prompt bytes; and
- the private exposure decision and denial behavior of every source-disclosure route.

Exact equality is the gate, not "acceptable" similarity. Every difference must be captured,
documented, and explained, but an explanation does not turn it into a pass: the difference remains
a failed regression and blocks corpus B from the shared path unless the owner separately authorizes
an intentional corpus-A cohort change. Generative answer text and judged metrics remain subject to
their existing nondeterminism protocol; they do not replace exact equality of retrieval, sources,
and model inputs.

If corpus A's gold set has not yet been locked, this gate cannot be declared complete. Importer and
manifest design may proceed on the exploratory branch, but the generalized path cannot merge or
deploy until the locked questions produce the exact before-and-after retrieval results above.

## Proposed corpus contract

Identity has three layers:

- `work_id` groups historically related texts, such as Beverley's history as a work family;
- `corpus_id` identifies one base text or edition, so the 1705 and 1722 Beverley texts receive
  different values; and
- `corpus_version` monotonically identifies a particular normalized, chunked realization of that
  base text.

The addressable key is `(corpus_id, corpus_version)`. Each version record is immutable and may name
one exact predecessor with `supersedes`. Correcting OCR, normalization, ordering, eligibility, or
chunk text creates a new version with new derived hashes; it never mutates the old record. Locator
profiles bind to an exact corpus version. Carry-over of an unchanged locator or gold location
requires the existing ID-plus-text-hash check rather than an assumption that the new version is
close enough.

Each immutable version record contains at least:

- `work_id`, `corpus_id`, `corpus_version`, schema version, and optional `supersedes` key;
- title, author, original publication date, and selected edition;
- source provenance, rights status, retrieval date, and raw-source SHA-256;
- normalized-document and chunk-set hashes;
- importer and normalization versions;
- chunking parameters and retrieval-eligibility rules;
- collection name, vector count, embedding model, and explicit distance space;
- supported locator profiles, each bound to an edition hash;
- exposure policy: private commercial text or public-domain text; and
- evaluation-set identity, if that corpus later becomes formally evaluated.

Corpus A's existing chunk IDs are frozen strings. `corpus_id` and `corpus_version` are sidecar
fields on records and API objects and **never enter or rewrite an already-indexed chunk-ID string**.
A build aborts before persistence if corpus A's ordered chunk-ID set changes. New corpora also use
stable local chunk IDs, but global identity is the composite `(corpus_id, corpus_version,
chunk_id)`, not a prefix retrofitted onto legacy IDs.

Exposure is an allowlisted enum, not a permissive boolean. An absent, blank, or unrecognized value
resolves to `private_deny`; it never inherits a server, project, or neighboring corpus default.
Corpus A must mechanically resolve to the private commercial policy before and after the refactor.
Public source inspection requires an affirmative corpus-version policy plus a route-specific
permission; public-domain metadata alone does not open an endpoint.

## Bounded ingestion pipeline

1. **Acquire and quarantine the exact base edition.** Store it outside committed source until
   rights, edition ancestry, and quality are reviewed. Reject a Beverley transcription that does
   not identify whether its base text is 1705, 1722, or another documented edition.
2. **Import without interpretation.** Convert the selected TXT, HTML, EPUB, DOCX, or PDF edition
   into a normalized document model. OCR-derived input must retain page/order diagnostics and flag
   suspect text rather than silently cleaning it into authority.
3. **Normalize reproducibly.** Produce chaptered UTF-8 Markdown or the equivalent internal
   paragraph sequence, with deterministic titles and ordering.
4. **Chunk and manifest offline.** Generate text-free committed metadata and private chunks under
   one immutable corpus-version record. Verify stable IDs, hashes, counts, skipped matter,
   ordering, exposure, and any `supersedes` link before paying for embeddings.
5. **Build an isolated index.** Use a distinct collection, explicit distance metric, recorded
   embedding model, tracked token usage, and a pre-authorized cost ceiling.
6. **Reopen and verify.** Confirm exact ID, metadata, text-hash, vector-count, and collection
   identity after persistence. A failed build never replaces a working corpus.
7. **Promote explicitly.** Add the corpus to the curated library only after offline and indexed
   artifacts agree. Promotion should be atomic and reversible.

## Reader and API model

- Preserve the existing `current` wrapper and its hardcoded corpus-A arguments while pure
  internals gain explicit corpus-version parameters. Remove the alias only in a separately tested
  migration after parity has been proved.
- Bind `conversation_id` to exactly one `(corpus_id, corpus_version)`; reject attempts to switch
  books or versions inside an existing conversation.
- Return title and edition identity with every answer, source locator, cost record, and diagnostic.
- Keep retrieval and citation numbering local to one answer. `[Source 1]` must never be ambiguous
  about which corpus supplied it.
- Keep the public library allowlisted by the server. A client cannot promote an uploaded corpus or
  select a private exposure profile.
- Make absence responses corpus-local and incurious: "The selected corpus does not provide enough
  evidence to answer this question." The answer must not name, search, or infer a neighboring
  corpus merely because that corpus might contain the topic.
- If comparison mode is added, represent it as two answer results plus an optional derived
  comparison, not as one source list with mixed identities.

## Evaluation implications

The existing *Cradle of the Empire* development and gold questions cannot measure a second book.
For the first ingestion experiment, use a small, explicitly developmental smoke set to test:

- corpus selection and conversation isolation;
- retrieval from the intended collection only;
- source resolution and edition labels;
- corpus-local insufficiency when the requested material is absent here but present only in the
  other book, without identifying or making a claim about that other book;
- no cross-corpus citation or manuscript leakage; and
- stable cost and run identity per corpus.

This smoke set sits **outside `EVAL_CONTRACT.md`**. It carries no gold provenance attestation,
cannot support a quality or resume claim, and is permanently non-promotable into a formal
evaluation because its questions are development-seen. A later formal evaluation for corpus B
requires a distinct held-out set, its own provenance attestation, and its own contract locked before
the questions' first use. Every smoke question is added to the development-question registry before
it is run so it cannot later enter a held-out set. Smoke artifacts remain under the existing
development/runtime rules; the gold validation lock does not learn a second, weaker artifact class.

For the cross-corpus absence case, the expected behavior is only a corpus-local insufficiency. A
message that volunteers that the topic belongs to another book is itself an ungrounded cross-corpus
claim and fails the smoke.

A formal quality claim about the second corpus would require its own question set, source labels,
and documented annotator competence. Cross-book comparison would require a third evaluation
contract: it is not adequately scored by running the two single-book gold sets side by side.

## Public-domain text does and does not change

Public-domain status can permit a more transparent demo, including longer source inspection if the
selected edition allows it. It does not remove the need for:

- exact edition and source provenance;
- input validation and path isolation;
- prompt-injection and malformed-document defenses;
- source-size, request-rate, concurrency, and API-spend limits;
- text-free operational logs; or
- a clear boundary preventing the public corpus's permissive disclosure rules from weakening the
  commercial manuscript's protections.

Exposure policy belongs to corpus metadata enforced by the server, not to a reader-controlled
toggle. This refactor changes privacy from safety-by-construction to safety-by-configuration, so the
configuration boundary is itself a security gate:

- missing or unknown exposure values fail closed to `private_deny`;
- corpus A is asserted private mechanically in unit, integration, and deployment-readiness tests;
- one corpus's public-domain permission never becomes a default for another corpus; and
- bulk text or source-file routes require their own explicit allow decision after corpus policy is
  resolved.

## Questions this branch should answer before implementation

The work/corpus/version identity, immutable supersession, legacy chunk-ID preservation,
fail-closed exposure default, corpus-local absence behavior, and smoke-set governance are settled
above. The remaining questions are:

1. Which exact deterministic artifact should capture corpus A's pre-refactor gold retrieval results
   and generator inputs without storing manuscript prose?
2. Which import format yields the cleanest, most reproducible first public-domain corpus?
3. Should each corpus have its own skip rules and prompt metadata, and how can those remain data
   rather than corpus-specific engine branches?
4. How much disk, memory, startup time, and Render persistent storage does one additional index
   require?
5. Does the public UI present a small curated library, or keep the current book-first landing page
   with a separate experimental collection?
6. What does "compare these books" mean: independent answers, claim alignment, historiographical
   contrast, or all three in stages?

## Suggested sequence

1. Freeze a text-free corpus-A conformance artifact from the unchanged implementation.
2. Extract the integrity calculation into a pure function while the existing `current` wrapper
   supplies exactly its former hardcoded arguments.
3. Prove exact corpus-A parity on identities, legacy chunk IDs and hashes, gold retrieval scores,
   ordered retrieved/context IDs, generator inputs, and private exposure behavior.
4. Select and verify one public-domain work, base text, and exact digital edition.
5. Write its work/corpus/version intake record and importer acceptance fixture without source prose.
6. Produce corpus-B chunks and an immutable manifest offline; make no embedding or generation call.
7. Measure corpus size and estimate embedding, storage, and per-question costs.
8. Build and verify an isolated index after explicit cost authorization.
9. Only after step 3 remains green, let corpus B call the same pure integrity and modern answer
   functions behind a development-only feature flag.
10. Add a minimal corpus selector and prove conversation and exposure isolation locally.
11. Register and run the non-promotable developmental smoke set, document failures, and decide
    whether parallel comparison is justified.
12. Only then consider public deployment, cross-corpus synthesis, or generic user uploads.

## Non-goals for the first pass

- arbitrary user uploads in the public application;
- automatic internet downloading;
- mixing evidence from several books in one answer;
- corpus-specific historical names or chapter titles in engine code;
- changing the existing book's frozen evaluation contract;
- changing the live Cromblog/Render deployment; or
- committing either the commercial manuscript or an unreviewed bulk public-domain text.

## Initial success criterion

The experiment succeeds only when **both** sides of the change are proved:

1. Corpus A retains the same manifest/index identities, byte-identical legacy chunk-ID strings and
   chunk hashes, identical ordered retrieval/context IDs and a byte-identical serialized
   deterministic gold-retrieval report for every locked gold question, identical ordered model
   inputs, and an explicit private-deny exposure result. Any diff fails the gate and must be
   documented and explained; it is not averaged into an acceptable result.
2. Corpus B can be edition-identified, versioned immutably, ingested, integrity-checked, indexed,
   selected, and queried through the same pure internals without a conversation, source, citation,
   absence message, or disclosure decision crossing the corpus boundary.

If corpus A lacks a locked gold set, the branch may demonstrate ingestion mechanics but cannot
claim this success criterion or merge the generalized answer path. Comparative answer quality is a
later measurement, not an ingestion acceptance criterion.
