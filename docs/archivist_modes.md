# Archivist modes and interpretive influence contract

**Status:** current retrieval-authored-v5 candidate; no declared v5 live cohort as of 2026-08-13
**Scope:** reader-facing modes, interpretive influence provenance, advanced overrides, and the
boundary between influence and evidence

## Product model

An Archivist mode is a versioned preset that joins three reader-visible choices:

1. an appearance theme;
2. default Historiographical lens, Voice, and Worldview settings; and
3. an optional, reviewed interpretive influence profile.

It does **not** change the evidence corpus. Historical assertions and numbered citations in every
mode remain grounded in the retrieval-eligible text of *Cradle of the Empire*. The current
`retrieval-authored-v5` historical/manuscript path makes one query-embedding request, runs shared dense/BM25 reciprocal-
rank fusion, and compiles a rich source-bound dossier before any generated prose call.

The application recognizes three different source roles:

| Role | May affect | May not affect |
|---|---|---|
| `evidence_source` | factual claims, citations, completeness, absence decisions | uncited factual invention |
| `interpretive_influence` | framing, emphasis, cadence, value judgment | retrieval, source admission, historical claims, quotations |
| `visual_reference` | color, typography, ornament, layout | answer content |

Influence works never enter the Chroma collection, retrieval, dossier evidence, source numbering,
citation validator, or public source panel. Reviewed influence prompts may guide generated framing
and prose, but they are not evidence and cannot authorize a historical assertion.

## Primary modes

| Mode | Appearance | Default answer settings | Influence profile |
|---|---|---|---|
| **Professional** | Professional | Evidence-first, Plainspoken, Secular humanist | `professional_public_history/1` |
| **Essential** | Essential | Evidence-first, Scholarly, None | none |
| **Pretty Pink Princess** | Pretty Pink Princess | Triumphalist, Romantic, Secular humanist | `rose_tinted_optimism/1` |
| **Baleful Black Baron** | Baleful Black Baron | Tragic, Romantic, None | `severe_tragic_history/1` |
| **Ruthless Red Realist** (`ember_and_ink`) | Ember & Ink | Evidence-first, Plainspoken, Enlightenment rationalist | `realist_statecraft/1` |

Professional is the frontend default for a new visitor. It is a restrained public-history
prototype, not a claim of neutrality. Essential is the direct-evidence mode and the API default
when no mode is supplied. In current RAG it makes no prose-generation call, but it uses the shared
`text-embedding-3-small` query request before direct evidence is compiled.

Every registered generated mode -- currently Professional, Pretty Pink Princess, Baleful Black
Baron, and Ruthless Red Realist -- makes exactly one no-retry `gpt-5.6-sol` authored-response call
with low reasoning and medium verbosity. The existing local `QuestionPlan` selects its length
profile: ordinary questions target 500-700 reader-visible answer tokens with a 1,800-token API
ceiling, while `BROAD_SYNTHESIS` plans target 900-1,100 with a 2,400-token ceiling. Targets are
advisory, concise special dispositions may be shorter, and padding, repetition, or invention is
forbidden. The call receives the question, locally resolved turn, and four-to-eight-unit rich
dossier. It may synthesize, paraphrase, and write in character. Every answer ends with
one to three in-character follow-up questions. Grounded prose names opaque dossier-unit IDs;
persona prose carries no evidence ID. The provider-visible schema makes these mutually exclusive
object variants: grounded requires one to eight IDs, and persona permits none. Application code
verifies grounded IDs and maps them to `[Source N]`.
The adaptive profile advances only the authored input to `archivist.authored_response_input/2`;
output remains `archivist.retrieval_authored_answer/1` and rendering remains
`retrieval-authored-renderer-v1`.
The shared provider allowance is 35 seconds, with embedding capped at eight seconds and authoring
at thirty. Timeout, transport failure, provider exception/refusal, structured-output rejection, or
local contract-validation failure falls back to the same direct Essential evidence without retry.
Internal diagnostics distinguish those classes without exposing exception text. The browser visibly identifies that nonfatal fallback so the reader does not mistake direct
evidence for an answer authored in the selected generated mode; ordinary Essential answers and
successful generated answers show no fallback notice. The notice is headed **Essential fallback**
and says, “Archivist could not complete the {Mode label} AI response, so it returned Essential's
direct manuscript evidence instead.”

Every registered generated mode also has a separate, narrow pre-retrieval route for direct social
or personal questions addressed to its persona. `is_character_conversation_question(question,
mode)` is conservative and derives eligibility from the generated-mode registry rather than a
list of personality IDs. An eligible turn uses `character-conversation-v2`: exactly one no-retry `answer_generation` call to
`gpt-5.6-sol`, with low reasoning, low verbosity, a 12-second timeout, and at most 576 output tokens. Its input schema is
`archivist.character_conversation_input/1`; its structured output schema is
`archivist.character_conversation_answer/1`, its renderer is
`character-conversation-renderer-v1`, and its only disposition is `character_reply`. The call
receives the question, selected mode, and character instructions. It receives no conversation
history, query embedding, manuscript text, retrieved source, dossier, citation, or factual premise.
Its one to three questions must each mention the manuscript or *Cradle of the Empire*, end with a
question mark, and invite the reader back into book discussion.

A successful social call has status `generated`. Provider failure, invalid structure, or refusal
uses a deterministic application-owned reply for that same character with status `local_fallback`
and failure code `provider_failure`, `invalid_response`, or `refusal`. It never substitutes
Essential evidence and never makes a retry. A historical, manuscript, mixed social-and-historical,
long, or uncertain turn falls through to the grounded retrieval-authored path. Professional,
Pretty Pink Princess, Baleful Black Baron, and Ruthless Red Realist are covered now; Essential has
no generated-mode contract and is excluded. A future mode inherits the route when it registers its
authored instructions, conversational instructions, and deterministic fallback copy. This boundary
lets the personas answer “How are you?” without turning Archivist into an uncited general chatbot.

These five modes and their five matching appearances are the only selectable reader choices.
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
Cromb Coo Coo, Tidal Archivist, Illuminated Codex, and Cosmic Almanac are not current
selectable modes, and their matching appearances are not current selectable appearances. Retaining
their IDs and assets does not authorize the browser or public API to expose them.

**Fey Fir-Green Folklorist** is the selected name for a possible future Forest Folio persona. It
remains dormant: no mode contract, prompt, registry entry, public selector, or evaluation cohort is
authorized by recording the name.

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

## Current generated profiles and historical extensions

Professional, Pretty Pink Princess, Baleful Black Baron, and Ruthless Red Realist are current
selectable generated modes. Their authored personas are deliberately perceptible, but the evidence
contract still outranks the theme.

**Professional** is measured, diplomatic, attentive, and approachable. On a narrowly recognized
social turn it answers like a thoughtful public historian between research questions, then invites
the reader back to a person, event, or argument in the manuscript.

**Pretty Pink Princess** is consistently rose-tinted. It looks first for courage, adaptation,
fellowship, recovery, creative agency, and possibilities opened under pressure. That optimism is a
judgment about meaning, not permission to rewrite the record: violence, enslavement, dispossession,
exploitation, failure, exclusion, and suffering must still be stated plainly and may never be
buried, euphemized, or converted into a happy ending. She may sing tiny original songs and wander
into fictional tangents about friends, family, pets, or a prince she fancies, but those flourishes
must remain persona material. She may refuse a centrally bleak or scary question in character and
offer gentler related follow-ups rather than falsify or sanitize the history.
For a narrowly recognized personal question, she instead speaks entirely as playful fiction about
her delightful imaginary life and then asks where the reader would like to enter the manuscript.

**Baleful Black Baron** applies an unmistakably tragic view of history. It emphasizes coercion,
loss, broken promises, narrowing choices, unintended consequences, and possibilities foreclosed.
It may not manufacture suffering, inevitability, or unsupported motives; its tragedy must arise
from concrete facts in the *Cradle* evidence supplied for the answer. Brooding Gothic asides and
fictional business in the Baron's imaginary keep remain uncited persona runs.
For a narrowly recognized personal question, he may be magnificently miserable about that
imaginary keep and then tempt the reader toward a grim ambition or troubled turn in the manuscript.

**Ruthless Red Realist** promotes the former Ember & Ink identity into a cold strategic persona.
It asks who holds power, which incentives govern conduct, what leverage or bargaining position each
actor possesses, whether commitments are credible, what institutions can actually enforce, and
which tradeoff an apparent victory conceals. The approach is loosely inspired by high-level realist
statecraft associated with Machiavelli and Henry Kissinger, but it does not impersonate, imitate,
quote, or attribute doctrine to either person. No work by either was ingested, and neither is a
source of manuscript facts. On a social turn it applies dry strategic wit to its fictional daily
life and then asks which contest of power in the manuscript the reader wants to dissect.

The Tidal, Illuminated, and Cosmic descriptions below are historical records for dormant modes;
the intervening Ember & Ink provenance paragraph documents the current Red Realist profile.

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

**Ember & Ink / Realist Statecraft provenance** is a project-authored profile associated at a high
level with the realist traditions of Machiavelli and Henry Kissinger. It asks about interests, power, bargaining leverage,
security, institutional capacity, credible commitments, constraints, tradeoffs, and unintended
consequences, while refusing to equate domination with wisdom or reduce every action to cynicism.
No work by Machiavelli or Henry Kissinger is ingested, retrieved, embedded, stored, cited, quoted,
paraphrased, or imitated. The mode reproduces neither voice nor characteristic phrasing and is not
affiliated with or endorsed by either person, their estates, or any publisher. Its provenance is therefore a text-free
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

The composer labels its collapsed control **Settings** and keeps two secondary disclosures:

- **Evidence scope** controls retrieved-passages versus the experimental full-book strategy. It is
  not an interpretive setting.
- **Advanced interpretive settings** exposes Historiographical lens, Voice, Worldview, and an
  appearance-only override. Changing an advanced value marks the preset as customized. Resetting
  restores the active mode's complete defaults. The only selectable appearances are the five that
  match the current modes.

Above the text field, a **Perspective** note makes the current framing explicit. Its label, the
header control, **Current mode** inside Settings, and each turn's mode badge open the same shared
chooser. The chooser always selects the current perspective for future answers. A historical turn
continues to display its snapshotted mode, facets, and appearance; opening its badge does not
retroactively relabel that answer, and retry continues to use the original turn settings. Preset
copy is:

- Professional: “Measured and diplomatic, with a present-minded focus on human agency,
  institutions, and material consequences.”
- Essential: “No added interpretive persona: direct, cited evidence from the manuscript without a
  prose-generation rewrite.”
- Pretty Pink Princess: “Hopeful and triumphalist, favoring achievement and charm while avoiding
  subjects she finds too bleak or frightening.”
- Baleful Black Baron: “Tragic and severe, emphasizing coercion, loss, ruin, and human suffering.”
- Ruthless Red Realist: “Cold-blooded strategic calculation centered on power, leverage,
  incentives, tradeoffs, and statecraft; loosely inspired by Machiavelli and Kissinger without
  impersonating either.”

Any facet or appearance override makes the active top-right and Settings-panel labels exactly
**Custom**. Facet-custom copy names its base preset, selected lens, voice, and worldview because
advanced facets do not remove the preset's registered character or influence. An appearance-only
override explicitly says that appearance is customized while the underlying preset perspective is
unchanged. Completed-turn badges retain “{Preset} · Custom” so historical provenance stays clear,
even though the badge is an actionable entry point to the future-answer chooser.
Custom is a resolved presentation/settings state, not a sixth server mode: character-social turns
retain their registered generated-mode identity, while advanced interpretive facets shape generated
historical/manuscript prose.

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
- influence/profile identity and authored-response prompt hashes where applicable; and
- the existing evidence-corpus and generation diagnostics.

Unknown or dormant mode IDs fail validation on the current public answer surface. A missing mode
resolves to Essential. All five current modes use the same retrieval and dossier construction for
historical/manuscript turns; only eligible social turns in registered generated modes bypass it by the narrow
contract above.
Generated modes return typed grounded/persona runs and one to three follow-up questions. Local code
requires the provider schema itself to express the mutually exclusive run shapes: a grounded run
has at least one support ID and a persona run has none. It then rejects unknown support IDs, forged citations, links, HTML, malformed structure, and extended
manuscript copying, then maps valid IDs to source numbers. This proves ID resolution, not semantic
entailment. Failures fall closed to Essential without retry.

## Evaluation gates

Frozen V26 evaluation results remain historical results for that explicit candidate. They are not
results for `retrieval-authored-v1`, `retrieval-authored-v2`, `retrieval-authored-v3`,
`retrieval-authored-v4`, or `retrieval-authored-v5`, and the current product must be measured in a separately
declared cohort. Professional becoming the public frontend default does not turn an Essential
evaluation into evidence about an interpretive mode.

Offline tests must establish:

1. omitted mode and explicit Essential use one query-embedding call, no prose-generation call, and
   return the same direct evidence;
2. all historical/manuscript turns in all five modes use the same retrieval and rich dossier
   construction, while only conservatively classified social turns in registered generated modes bypass it;
3. generated modes add exactly one `gpt-5.6-sol` low-reasoning, medium-verbosity call with no retry;
4. the response schema uses mutually exclusive grounded/persona variants, requires a nonempty
   support-ID list only for grounded runs, and requires one to three follow-up questions;
5. unknown support IDs, forged citations, malformed structures, and extended copying fail closed;
6. local rendering maps support IDs to citations without claiming semantic entailment;
7. each v5 timeout, transport, provider, refusal, structured-output, or local-validation failure
   receives its stable text-free code and returns direct Essential evidence without replay;
8. only five mode IDs and five appearances are selectable, while dormant definitions remain hidden;
9. no V26/V27 selector appears in the UI, while explicit development API compatibility remains;
10. advanced overrides and retries preserve the resolved per-turn settings; and
11. public responses disclose the mode without exposing private prompts or diagnostics;
12. social character calls send no manuscript, evidence, history, or embedding, make exactly one
    compact no-retry call, and require one to three explicit manuscript-leading questions; and
13. every social provider/refusal/validation failure returns deterministic in-character local
    dialogue without retrieval, Essential substitution, or replay.

The current architecture has focused offline contract coverage but no declared post-change live
model test. Ad hoc manual turns exposed the earlier provider/local mismatch: three of three observed
Baron calls and one of three observed Princess calls completed at the API but returned a grounded
run with no support ID and therefore fell back locally. Those observations diagnose the old schema;
they do not prove the repair or the new social route. The narrowly authorized three-mode compatibility smoke belongs to
superseded `application-compiled-v1`, not to this authored-response policy. Any formal evaluation of
`retrieval-authored-v3` belongs to its terminal timeout-diagnostic cohort. The v4 evaluation is
sealed under its fixed-length identity; v1-v3 and the frozen V26 record remain unchanged. No live
v5 call or v5 persona cohort has run, so v4 results cannot support an adaptive-policy claim.
