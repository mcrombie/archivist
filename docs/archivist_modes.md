# Archivist modes and interpretive influence contract

**Status:** implemented and offline-verified on `main`, 2026-08-04
**Scope:** reader-facing modes, interpretive influence provenance, advanced overrides, and the
boundary between influence and evidence

## Product model

An Archivist mode is a versioned preset that joins three reader-visible choices:

1. an appearance theme;
2. default Historiographical lens, Voice, and Worldview settings; and
3. an optional, reviewed interpretive influence profile.

It does **not** change the evidence corpus. Historical assertions and numbered citations in every
mode remain grounded in the retrieval-eligible text of *Cradle of the Empire*.

The application recognizes three different source roles:

| Role | May affect | May not affect |
|---|---|---|
| `evidence_source` | factual claims, citations, completeness, absence decisions | uncited factual invention |
| `interpretive_influence` | framing, emphasis, cadence, value judgment | retrieval, source admission, historical claims, quotations |
| `visual_reference` | color, typography, ornament, layout | answer content |

Influence works never enter the Chroma collection, retrieval plan, evidence obligations, source
numbering, citation validator, or public source panel. Archivist uses short, manually reviewed
prompt profiles distilled offline rather than placing influence passages in a live request.

## Primary modes

| Mode | Appearance | Default answer settings | Influence profile |
|---|---|---|---|
| **Professional** | Professional | Evidence-first, Plainspoken, Secular humanist | `professional_public_history/1` |
| **Essential** | Essential | Evidence-first, Scholarly, None | none |
| **Mythical Forest Folio** | Forest Folio | Tragic, Romantic, None | `dunsany_elfland/1` |

Professional is the frontend default for a new visitor. It is a restrained public-history
prototype, not a claim of neutrality. Essential remains the compatibility, evaluation, and
byte-identical neutral baseline when no mode is supplied to the API.

"No additional sources" in Essential means that Archivist adds no retrieved external text and no
curated influence profile. It does not claim that the underlying language model lacks pretrained
knowledge. The evidence and citation contract, rather than a claim about model pretraining, is the
enforceable boundary.

## Professional public-history profile

Professional combines three complementary historical methods. The combination is deliberate:
Craven supplies institutional and corporate mechanism; Beard supplies material-interest questions;
Du Bois supplies race, power, law, enforcement, and moral consequence. None is treated as a factual
authority for a question about *Cradle*.

| Work | Exact influence artifact | SHA-256 |
|---|---|---|
| Wesley Frank Craven, *The Virginia Company of London, 1606-1624* | Project Gutenberg #28555 EPUB3, modified 2026-07-11 | `7b6475993d63a640a8fae1044d342dbcb9d71321649357c52a0424e484d2596c` |
| Charles A. Beard, *An Economic Interpretation of the Constitution of the United States* | Project Gutenberg #70677 EPUB3, modified 2026-07-28 | `3359e7ef549af9281ffca2656aec82588ae1dc04017f05fdced4a5765e3ab16e` |
| W. E. B. Du Bois, *The Suppression of the African Slave Trade to the United States of America, 1638-1870* | Project Gutenberg #17700 EPUB3, modified 2026-07-07 | `08e428081e076e724cb91ba10229ed95ec66f53ef2e1d4e9c6875d3fda7a3b9b` |

The profile asks how formal institutions, material interests, racialized power, enforcement, and
human agency interact. It distinguishes intended design from actual operation and rejects both a
single-cause material determinism and an automatically celebratory account of institutions.

All three Gutenberg records identify their artifacts as public domain in the United States.
Rights outside the United States remain jurisdiction-specific. Craven is especially important to
treat narrowly: the work was published in 1957 and Gutenberg reports a United States
public-domain basis, but that does not imply public-domain status in every life-plus-70 country.
Archivist does not redistribute these EPUBs.

## Mythical Forest Folio profile

The supplied source artifact is Project Gutenberg #61077, Lord Dunsany's *The King of Elfland's
Daughter*:

- exact filename: `pg61077-images-3.epub`;
- artifact SHA-256:
  `b8a8a8cad9385000ae4154b61d9c8d4be645a4b346f7fe8aa580f77486cb80b4`;
- EPUB metadata modified timestamp: `2026-07-30T00:38:46Z`; and
- embedded rights statement: `Public domain in the USA.`

The profile draws only on reviewed formal qualities: mythopoetic cadence, landscape and
thresholds, restrained wonder, longing, consequence, distance, and things passing out of reach.
Dunsany is a literary influence, not a historian or an evidence source. The prompt expressly
forbids importing or alluding to his characters, places, events, lore, images, phrases, or claims.

The EPUB's title page points to a June 1969 Ballantine edition, while Gutenberg warns generally
that an ebook may not correspond cleanly to one print edition. Archivist therefore binds the
influence record to this exact Gutenberg artifact and hash without claiming a more precise base
transcription than the file establishes.

## Reader controls

The primary control is **Archivist mode**, because it changes both presentation and answer
character. Selecting a mode applies its appearance and interpretive defaults to future turns.
Completed turns retain their resolved mode and settings.

The composer keeps two secondary disclosures:

- **Evidence scope** controls retrieved-passages versus the experimental full-book strategy. It is
  not an interpretive setting.
- **Advanced interpretive settings** exposes Historiographical lens, Voice, Worldview, and an
  appearance-only override. Changing an advanced value marks the preset as customized. Resetting
  restores the active mode's complete defaults.

The seven other legacy visual themes remain available only as advanced appearance choices until
they receive reviewed interpretive profiles. Choosing one changes presentation without silently
inventing answer semantics.

## API and reproducibility

The server, not the browser, owns the allowlisted mode registry and influence prompts. A request
may send a known mode identifier plus the resolved advanced settings; it may not send prompt text,
source paths, or an arbitrary influence identifier.

Every answer records:

- mode ID and version;
- resolved lens, voice, and worldview;
- influence profile ID, version, and prompt hash; and
- the existing evidence-corpus and generation diagnostics.

Unknown modes fail validation. A missing mode resolves to Essential so existing API, CLI,
evaluation, and test callers retain the frozen baseline. Mode changes occur after retrieval and
must not change primary hits, final context IDs, source ordering, citations, premise decisions, or
absence behavior.

## Evaluation gates

The standing RAG and gold work continues to use Essential explicitly. Professional becoming the
public frontend default does not retroactively turn a neutral evaluation into evidence about the
public interpretive profile.

Offline tests must establish:

1. omitted mode and explicit Essential produce the previous prompt byte for byte;
2. retrieval and final source IDs are invariant across modes;
3. every influence prompt is fixed, hashed, and source-bounded;
4. Forest does not leak Dunsany proper nouns, quotations, fictional events, or lore;
5. Professional does not import claims from Craven, Beard, or Du Bois;
6. unknown mode IDs fail closed;
7. advanced overrides and retries preserve the resolved per-turn settings; and
8. public responses disclose the mode without exposing influence texts or private diagnostics.

Perceptibility and historical groundedness for Professional and Forest require a separate
reader-facing style smoke. That smoke is development evidence, not a substitute for the held-out
gold evaluation of factual answer quality.

Implementation verification completed without provider calls: the full offline suite passed 680
tests with one intentional skip, repository-wide Ruff lint passed, the production frontend build
passed, and whitespace checks passed. The session's automated browser surface was unavailable, so
this milestone does not claim screenshot-level visual QA or a paid perceptibility smoke.
