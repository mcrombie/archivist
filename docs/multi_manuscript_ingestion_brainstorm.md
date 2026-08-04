# Multi-manuscript ingestion exploration

Status: exploratory branch only. This document proposes a bounded second-corpus experiment; it
does not change Archivist's current product identity, public deployment, evaluation candidate, or
private *Cradle of the Empire* corpus.

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
State of Virginia* (first published in 1705). It is thematically related, historically distant from
the current book, and small enough to expose ingestion and metadata problems without immediately
creating another 500-page evaluation project.

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

## Proposed corpus contract

Each curated corpus should own an immutable identity record containing at least:

- `corpus_id` and schema version;
- title, author, original publication date, and selected edition;
- source provenance, rights status, retrieval date, and raw-source SHA-256;
- normalized-document and chunk-set hashes;
- importer and normalization versions;
- chunking parameters and retrieval-eligibility rules;
- collection name, vector count, embedding model, and explicit distance space;
- supported locator profiles, each bound to an edition hash;
- exposure policy: private commercial text or public-domain text; and
- evaluation-set identity, if that corpus later becomes formally evaluated.

Chunk IDs must be stable within a corpus and unambiguous across corpora. Prefer an explicit
`corpus_id` field in every record and API object; do not rely only on increasingly long chunk-ID
prefixes to carry identity.

## Bounded ingestion pipeline

1. **Acquire and quarantine the exact source.** Store it outside committed source until rights,
   edition, and quality are reviewed.
2. **Import without interpretation.** Convert the selected TXT, HTML, EPUB, DOCX, or PDF edition
   into a normalized document model. OCR-derived input must retain page/order diagnostics and flag
   suspect text rather than silently cleaning it into authority.
3. **Normalize reproducibly.** Produce chaptered UTF-8 Markdown or the equivalent internal
   paragraph sequence, with deterministic titles and ordering.
4. **Chunk and manifest offline.** Generate text-free committed metadata and private chunks. Verify
   stable IDs, hashes, counts, skipped matter, and ordering before paying for embeddings.
5. **Build an isolated index.** Use a distinct collection, explicit distance metric, recorded
   embedding model, tracked token usage, and a pre-authorized cost ceiling.
6. **Reopen and verify.** Confirm exact ID, metadata, text-hash, vector-count, and collection
   identity after persistence. A failed build never replaces a working corpus.
7. **Promote explicitly.** Add the corpus to the curated library only after offline and indexed
   artifacts agree. Promotion should be atomic and reversible.

## Reader and API model

- Replace the special meaning of `current` at internal boundaries with an explicit `corpus_id`,
  while retaining a compatibility alias until the current deployment is migrated deliberately.
- Bind `conversation_id` to exactly one `corpus_id`; reject attempts to switch books inside an
  existing conversation.
- Return title and edition identity with every answer, source locator, cost record, and diagnostic.
- Keep retrieval and citation numbering local to one answer. `[Source 1]` must never be ambiguous
  about which corpus supplied it.
- Keep the public library allowlisted by the server. A client cannot promote an uploaded corpus or
  select a private exposure profile.
- If comparison mode is added, represent it as two answer results plus an optional derived
  comparison, not as one source list with mixed identities.

## Evaluation implications

The existing *Cradle of the Empire* development and gold questions cannot measure a second book.
For the first ingestion experiment, use a small, explicitly developmental smoke set to test:

- corpus selection and conversation isolation;
- retrieval from the intended collection only;
- source resolution and edition labels;
- absence behavior when a topic belongs only to the other book;
- no cross-corpus citation or manuscript leakage; and
- stable cost and run identity per corpus.

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
toggle.

## Questions this branch should answer before implementation

1. Is the durable domain object a `project`, a `corpus`, a `book`, or a `work + edition` pair?
2. Can the strong `current` manifest/integrity path be parameterized without changing frozen RAG
   behavior for the existing book?
3. Which import format yields the cleanest, most reproducible first public-domain corpus?
4. How are stable document and chunk IDs preserved when an OCR or transcription is corrected?
5. Should each corpus have its own skip rules and prompt metadata, and how can those remain data
   rather than corpus-specific engine branches?
6. How much disk, memory, startup time, and Render persistent storage does one additional index
   require?
7. Does the public UI present a small curated library, or keep the current book-first landing page
   with a separate experimental collection?
8. What does "compare these books" mean: independent answers, claim alignment, historiographical
   contrast, or all three in stages?

## Suggested sequence

1. Select and verify one public-domain work and exact digital edition.
2. Write a source/edition intake record and importer acceptance fixture without source prose.
3. Produce chunks and a corpus manifest offline; make no embedding or generation call.
4. Measure corpus size and estimate embedding, storage, and per-question costs.
5. Build and verify an isolated index after explicit cost authorization.
6. Bring the second corpus onto the same integrity-checked answer pipeline behind a development-only
   feature flag.
7. Add a minimal corpus selector and prove conversation isolation locally.
8. Run a small developmental smoke set, document failures, and decide whether parallel comparison
   is justified.
9. Only then consider public deployment, cross-corpus synthesis, or generic user uploads.

## Non-goals for the first pass

- arbitrary user uploads in the public application;
- automatic internet downloading;
- mixing evidence from several books in one answer;
- corpus-specific historical names or chapter titles in engine code;
- changing the existing book's frozen evaluation contract;
- changing the live Cromblog/Render deployment; or
- committing either the commercial manuscript or an unreviewed bulk public-domain text.

## Initial success criterion

The experiment succeeds when two separately identified historical works can be ingested,
integrity-checked, indexed, selected, and queried through the same modern answer pipeline, while a
mechanical test proves that no conversation, source, citation, or public-disclosure rule crosses
the corpus boundary. Answer quality comparison is a later measurement, not an ingestion acceptance
criterion.
