# Archivist modes and interpretive influence contract

**Status:** current application-compiled release, offline-verified 2026-08-12
**Scope:** reader-facing modes, interpretive influence provenance, advanced overrides, and the
boundary between influence and evidence

## Product model

An Archivist mode is a versioned preset that joins three reader-visible choices:

1. an appearance theme;
2. default Historiographical lens, Voice, and Worldview settings; and
3. an optional, reviewed interpretive influence profile.

It does **not** change the evidence corpus. Historical assertions and numbered citations in every
mode remain grounded in the retrieval-eligible text of *Cradle of the Empire*. The current
`application-compiled-v1` path admits and ranks evidence locally, then compiles immutable evidence
cards and citations in application code.

The application recognizes three different source roles:

| Role | May affect | May not affect |
|---|---|---|
| `evidence_source` | factual claims, citations, completeness, absence decisions | uncited factual invention |
| `interpretive_influence` | framing, emphasis, cadence, value judgment | retrieval, source admission, historical claims, quotations |
| `visual_reference` | color, typography, ornament, layout | answer content |

Influence works never enter the Chroma collection, retrieval plan, evidence obligations, source
numbering, citation validator, or public source panel. Their reviewed ideas are represented by
closed, application-owned editorial cue catalogs rather than by placing influence passages in a
live request.

## Primary modes

| Mode | Appearance | Default answer settings | Influence profile |
|---|---|---|---|
| **Professional** | Professional | Evidence-first, Plainspoken, Secular humanist | `professional_public_history/1` |
| **Essential** | Essential | Evidence-first, Scholarly, None | none |
| **Pretty Pink Princess** | Pretty Pink Princess | Triumphalist, Romantic, Secular humanist | `rose_tinted_optimism/1` |
| **Baleful Black Baron** | Baleful Black Baron | Tragic, Romantic, None | `severe_tragic_history/1` |

Professional is the frontend default for a new visitor. It is a restrained public-history
prototype, not a claim of neutrality. Essential is the direct-evidence mode and the API default
when no mode is supplied. In current RAG it makes no provider call: local BM25 retrieval and the
application evidence compiler return the bounded evidence cards exactly as compiled.

Professional, Pretty Pink Princess, and Baleful Black Baron each make exactly one no-retry
`gpt-5.6-sol` call with low reasoning. The call cannot write displayed prose. It may select only
exact evidence-card placeholders and typed IDs from that mode's closed editorial cue catalog.
Application code substitutes every factual sentence, editorial sentence, label, and `[Source N]`.
Invalid output or provider/client failure falls back to the same direct Essential evidence.

These four modes and their four matching appearances are the only selectable reader choices.
Other historical mode IDs, profiles, and visual assets remain dormant in the repository solely for
compatibility and possible later redesign; the current UI and public API do not offer them.

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

## Dormant historical profiles

The following profile records preserve earlier design and provenance work. Mythical Forest Folio,
Cromb Coo Coo, Tidal Archivist, Ember & Ink, Illuminated Codex, and Cosmic Almanac are not current
selectable modes, and their matching appearances are not current selectable appearances. Retaining
their IDs and assets does not authorize the browser or public API to expose them.

### Mythical Forest Folio profile (historical)

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

### Cromb Coo Coo profile (historical)

Cromb Coo Coo was the fourth reader-facing semantic mode. It joined the Cromb visual appearance
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

## Current character profiles and historical extensions

Pretty Pink Princess and Baleful Black Baron are current selectable character modes. Their closed
cue catalogs are deliberately perceptible, but the evidence contract still outranks the theme.

**Pretty Pink Princess** is consistently rose-tinted. It looks first for courage, adaptation,
fellowship, recovery, creative agency, and possibilities opened under pressure. That optimism is a
judgment about meaning, not permission to rewrite the record: violence, enslavement, dispossession,
exploitation, failure, exclusion, and suffering must still be stated plainly and may never be
buried, euphemized, or converted into a happy ending.

**Baleful Black Baron** applies an unmistakably tragic view of history. It emphasizes coercion,
loss, broken promises, narrowing choices, unintended consequences, and possibilities foreclosed.
It may not manufacture suffering, inevitability, or unsupported motives; its tragedy must arise
from concrete facts in the *Cradle* evidence supplied for the answer.

The remaining descriptions in this section are historical records for dormant modes.

**Tidal Archivist (historical)** replaced the Forest Folio's Dunsany influence with high-level formal qualities
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

**Ember & Ink (historical)** used a project-authored Realist Statecraft profile associated at a high level with
the historical tradition of Henry Kissinger. It asks about interests, power, bargaining leverage,
security, institutional capacity, credible commitments, constraints, tradeoffs, and unintended
consequences, while refusing to equate domination with wisdom or reduce every action to cynicism.
No Henry Kissinger work is ingested, retrieved, embedded, stored, cited, quoted, paraphrased, or
imitated. The mode does not reproduce his voice or characteristic phrasing and is not affiliated
with or endorsed by him, his estate, or any publisher. Its provenance is therefore a text-free
project editorial record, `conceptual-profile:realist-statecraft:no-text-ingested`, rather than a
book artifact.

**Illuminated Codex (historical)** used a project-authored, lowercase-l modern liberal historiographical
profile. It attends to individual rights and dignity, pluralism, toleration, representative
institutions, rule of law, reform, inclusion, accountable power, and the gap between declared
ideals and lived access. It treats progress as incremental, contested, reversible, and uneven
rather than automatic. The profile may evaluate institutions by whom they protect, include, or
exclude, but it may not import present-day party positions, turn historical actors into proxies
for current political factions, hide coercion behind reform language, or add unsupported facts.
It is a text-free project editorial profile with no outside-work provenance rather than another
book artifact.

**Cosmic Almanac (historical)** used a project-authored future-science history profile. It read historical
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
  restores the active mode's complete defaults. The only selectable appearances are the four that
  match the current modes.

Dormant appearance definitions and assets remain loadable by compatibility code but are not shown
as reader controls. The UI also exposes no V26/V27 latency or RAG-policy selector. Explicit V26 and
V27 policy requests remain available only through the development API compatibility boundary.

## API and reproducibility

The server, not the browser, owns the allowlisted mode registry and influence prompts. A request
may send a known mode identifier plus the resolved advanced settings; it may not send prompt text,
source paths, or an arbitrary influence identifier.

Every answer records:

- mode ID and version;
- resolved lens, voice, and worldview;
- influence/cue profile identity and renderer hashes where applicable; and
- the existing evidence-corpus and generation diagnostics.

Unknown or dormant mode IDs fail validation on the current public answer surface. A missing mode
resolves to Essential. All four current modes receive the same locally compiled cards and source
numbers. In generated modes the model returns only a validated arrangement of exact card
placeholders and mode-bound cue IDs; local code performs substitution. Cross-mode cue IDs, raw
model prose, missing or repeated cards, and malformed arrangements fail closed to Essential.

## Evaluation gates

Frozen V26 evaluation results remain historical results for that explicit candidate. They are not
results for `application-compiled-v1`, and the current product must be measured in a separately
declared cohort. Professional becoming the public frontend default does not turn an Essential
evaluation into evidence about an interpretive mode.

Offline tests must establish:

1. omitted mode and explicit Essential make zero provider calls and return the same direct evidence;
2. all four modes receive identical immutable evidence text, source order, and citations;
3. generated modes make exactly one `gpt-5.6-sol` low-reasoning call with no retry;
4. the response schema accepts only exact card placeholders and mode-bound application cue IDs;
5. every card appears exactly once, while raw prose, unknown cues, and cross-mode cues fail closed;
6. every displayed factual word, editorial word, label, and citation originates in local code;
7. provider/client failure returns the direct Essential evidence;
8. only four mode IDs and four appearances are selectable, while dormant definitions remain hidden;
9. no V26/V27 selector appears in the UI, while explicit development API compatibility remains;
10. advanced overrides and retries preserve the resolved per-turn settings; and
11. public responses disclose the mode without exposing private prompts or diagnostics.

The current architecture has passed its offline contract checks and one narrowly authorized
three-mode compatibility smoke. That smoke is not a quality, latency, or production-performance
claim. Any evaluation of `application-compiled-v1` belongs to a new, explicitly declared cohort;
the frozen V26 record remains unchanged.
