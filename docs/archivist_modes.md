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
| **Cromb Coo Coo** | Cromb Coo Coo | Evidence-first, Romantic, Secular humanist | `cromb_coo_coo_manuscript/1` |
| **Pretty Pink Princess** | Pretty Pink Princess | Triumphalist, Romantic, Secular humanist | `rose_tinted_optimism/1` |
| **Baleful Black Baron** | Baleful Black Baron | Tragic, Romantic, None | `severe_tragic_history/1` |
| **Tidal Archivist** | Tidal Archive | Evidence-first, Romantic, None | `moby_dick_maritime/1` |
| **Ember & Ink** | Ember & Ink | Evidence-first, Plainspoken, Enlightenment rationalist | `realist_statecraft/1` |
| **Illuminated Codex** | Illuminated Codex | Evidence-first, Scholarly, Secular humanist | `modern_liberal_history/1` |
| **Cosmic Almanac** | Cosmic Almanac | Evidence-first, Scholarly, Enlightenment rationalist | `future_science_history/1` |

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

## Cromb Coo Coo profile

Cromb Coo Coo is the fourth reader-facing semantic mode. It joins the Cromb visual appearance
with Evidence-first, Romantic, and Secular humanist defaults and the fixed influence profile
`cromb_coo_coo_manuscript/1`.

The owner supplied one private local artifact for offline review. This identity record deliberately
does not infer or name an author:

| Field | Value |
|---|---|
| Filename | `Journey through Cromb Coo Coo_7_30_2026.pdf` |
| Access status | Owner-supplied private PDF |
| Physical PDF pages | 226 |
| File size | 815,751 bytes |
| SHA-256 | `f67f9ed3f622583abe2fca090d73881ff86a7f801cea88034589c986509ece74` |
| File modified | `2026-07-30 10:05:30 -04:00` |
| PDF metadata creation | `2026-07-30 10:05:29 -04:00` |
| Creator software | Scrivener for Windows |

The reviewed profile permits only high-level formal traits: affectionate absurdity, grotesque
high fantasy, comic deflation of grandeur, sensory specificity, tenderness amid violence, and
an emphasis on contingency and eccentric agency. It must not quote, paraphrase, summarize, name,
allude to, or import the private manuscript's people, places, events, plot, lore, phrases, images,
or factual claims.

This is a strict generation-only influence. The PDF remains outside the repository, and temporary
review renders were deleted after local inspection; neither is committed or sent to an API. They
never enter Chroma, retrieval,
evidence admission, source numbering, citations, completeness checks, absence decisions, public
source cards, follow-up evidence, or logs. Only the short, manually reviewed profile may enter the
generation prompt after *Cradle* evidence has been selected. Historical assertions and citations
remain grounded exclusively in *Cradle of the Empire*.

## Princess, Baron, Tidal, Ember, Codex, and Almanac profiles

Six former appearance-only themes now have explicit answer character. The profiles are deliberately
strong enough to be perceptible, but the evidence contract still outranks the theme.

**Pretty Pink Princess** is consistently rose-tinted. It looks first for courage, adaptation,
fellowship, recovery, creative agency, and possibilities opened under pressure. That optimism is a
judgment about meaning, not permission to rewrite the record: violence, enslavement, dispossession,
exploitation, failure, exclusion, and suffering must still be stated plainly and may never be
buried, euphemized, or converted into a happy ending.

**Baleful Black Baron** applies an unmistakably tragic view of history. It emphasizes coercion,
loss, broken promises, narrowing choices, unintended consequences, and possibilities foreclosed.
It may not manufacture suffering, inevitability, or unsupported motives; its tragedy must arise
from concrete facts in the *Cradle* evidence supplied for the answer.

**Tidal Archivist** replaces the Forest Folio's Dunsany influence with high-level formal qualities
reviewed from Herman Melville's *Moby-Dick; or, The Whale*: oceanic scale, long-voyage uncertainty,
moral pressure, hierarchy, obsession, the limits of command, and restrained maritime imagery. It
does not quote, paraphrase, imitate, or import Melville's characters, scenes, plot, symbols, famous
lines, or claims. The frozen influence artifact is Project Gutenberg #15, which Gutenberg
identifies as its highest-quality Moby-Dick transcription and as based on the 1851 first American
edition:

| Field | Value |
|---|---|
| Stable artifact URL | `https://www.gutenberg.org/ebooks/15.epub3.images` |
| File size | 914,544 bytes |
| SHA-256 | `8d76f75515a8e10b0ed0657275767f75b4b283177805a1c09c231840a0607d95` |
| Artifact modified | `2026-08-01T07:33:10Z` |
| Rights note | Project Gutenberg records public-domain status in the USA; other jurisdictions require a separate check |

The EPUB was used only to freeze provenance for the reviewed profile. The temporary review copy
remained outside version control and was removed after hash capture; it is not placed in Chroma or
a live request and is not redistributed by Archivist.

**Ember & Ink** uses a project-authored Realist Statecraft profile associated at a high level with
the historical tradition of Henry Kissinger. It asks about interests, power, bargaining leverage,
security, institutional capacity, credible commitments, constraints, tradeoffs, and unintended
consequences, while refusing to equate domination with wisdom or reduce every action to cynicism.
No Henry Kissinger work is ingested, retrieved, embedded, stored, cited, quoted, paraphrased, or
imitated. The mode does not reproduce his voice or characteristic phrasing and is not affiliated
with or endorsed by him, his estate, or any publisher. Its provenance is therefore a text-free
project editorial record, `conceptual-profile:realist-statecraft:no-text-ingested`, rather than a
book artifact.

**Illuminated Codex** uses a project-authored, lowercase-l modern liberal historiographical
profile. It attends to individual rights and dignity, pluralism, toleration, representative
institutions, rule of law, reform, inclusion, accountable power, and the gap between declared
ideals and lived access. It treats progress as incremental, contested, reversible, and uneven
rather than automatic. The profile may evaluate institutions by whom they protect, include, or
exclude, but it may not import present-day party positions, turn historical actors into proxies
for current political factions, hide coercion behind reform language, or add unsupported facts.
It is a text-free project editorial profile with no outside-work provenance rather than another
book artifact.

**Cosmic Almanac** uses a project-authored future-science history profile. It reads historical
events across long time horizons and looks for interacting systems: demography, ecology and
climate where the manuscript supports them, technology, energy, infrastructure, information,
institutions, path dependence, and feedback loops. It may discuss how historical choices constrain
or open plausible futures, but uncertainty and scenario language must remain explicit. It may not
invent future facts, treat a projection as manuscript evidence, write science fiction, assume
technological progress is inevitable, reduce history to a single system, or import anachronistic
scientific categories into historical actors. This is another text-free project editorial profile,
not an additional evidence source.

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

The one remaining legacy visual theme remains available only as an advanced appearance choice
until it receives a reviewed interpretive profile. Together with the ten semantic-mode
appearances, the interface therefore exposes eleven visual appearances. Choosing a legacy
appearance changes presentation without silently inventing answer semantics.

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
5. Cromb does not leak private-manuscript names, quotations, plot, lore, images, or claims;
6. Tidal does not leak or imitate Melville language, characters, scenes, plot, symbols, or claims;
7. Ember does not ingest, quote, paraphrase, or imitate Kissinger works and cannot treat realist
   framing as evidence;
8. Princess cannot hide or euphemize material harm, and Baron cannot invent tragedy;
9. Codex remains lowercase-l liberal historical analysis rather than present-day party advocacy
   and cannot assume progress, reform, or inclusion that the sources do not establish;
10. Almanac distinguishes supported history from uncertain future implications and cannot invent
    projections, science-fiction details, teleology, or technological determinism;
11. Professional does not import claims from Craven, Beard, or Du Bois;
12. unknown mode IDs fail closed;
13. advanced overrides and retries preserve the resolved per-turn settings; and
14. public responses disclose the mode without exposing influence texts or private diagnostics.

Perceptibility and historical groundedness for every non-Essential mode require separate
reader-facing style smokes, including paired Princess/Baron readings and direct checks that Tidal
is maritime rather than Forest-like, Ember is realist rather than merely formal, and Codex is
recognizably liberal without becoming presentist or partisan. Almanac must likewise read as
systems-minded and future-oriented without turning projections into facts. Those smokes are
development evidence, not substitutes for the held-out gold evaluation of factual answer quality.
Held-out and gold evaluation remains explicitly Essential.

Implementation verification completed without provider calls: 29 focused backend mode tests and
the focused frontend mapping test passed; the full offline suite passed 706 tests with one
intentional skip; repository-wide Ruff lint, the production frontend build, and whitespace checks
passed. This milestone does not claim screenshot-level visual QA or a paid perceptibility smoke.
