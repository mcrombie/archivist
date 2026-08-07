# Claude prompt for blinded gold-set annotation drafts

> **Optional future workflow; not used for the current held-out cohort.** The owner retained the
> completed, source-adjudicated annotations and provenance v4 discloses their historical Claude
> assistance without claiming prospective blinding. The prepared private batches were never sent.
> Using this prompt for a future gold set requires separate data/cost authorization and a provenance
> contract that prospectively captures the resulting records.

Use this prompt in batches of five questions. In a separate message immediately before it, tell
Claude the exact batch (for example, `Work only on H001-H005`). Do not edit this canonical prompt
inside a declared future cohort; hash its exact bytes in that cohort's provenance record.

Provide Claude privately with only:

- the five question blocks for the declared batch from
  `runtime/gold-authoring/gold_set_questions.md`;
- `output/chunks.json`;
- `fixtures/corpus_manifest.json`; and
- this prompt.

`output/chunks.json` contains the private commercial manuscript. Upload it only under data controls
the owner accepts. Never provide Archivist answers, retrieval results, traces, scores, development
failures, or evaluation output. Keep Claude's raw draft private and gitignored.

---

You are assisting with blinded annotation of a held-out evaluation set for Archivist, a
retrieval-augmented question-answering system over a private historical manuscript.

## Status and authority

Your response is an **AI-generated annotation draft, not ground truth**. Every field is unverified
until the manuscript owner personally checks it against the corpus, independently searches for
omissions, and adopts, revises, or rejects it. The owner—not you—has final authority over expected
behavior, claims, essentiality, source locations, relevant-chunk coverage, prohibited claims, and
notes.

Work only on the five item IDs named by the owner immediately before this prompt. Preserve every
supplied ID, stratum, description, question, and Behavior value exactly. If a Behavior value appears
wrong, do not silently change it; mark the item `ANNOTATION BLOCKED — OWNER DECISION REQUIRED` in
Notes.

## Blinding

Use only the supplied question blocks, `chunks.json`, and `corpus_manifest.json`. Do not use the web,
outside historical knowledge, or unstated assumptions. Do not ask for or inspect:

- an answer produced by Archivist;
- chunks retrieved or selected by Archivist;
- planner, retrieval, generation, or validation traces;
- candidate-system scores, known failures, or evaluation results; or
- development-test answers.

If any supplied material contains candidate-system output for an item in the batch, stop and report
possible benchmark contamination instead of annotating it.

## Source and privacy rules

- Treat every attachment as confidential.
- Never quote or reproduce manuscript passages or distinctive phrases.
- Write concise, independently scorable claim units in fresh paraphrase.
- Output only exact, retrieval-eligible `chunk_id` values as locations. Apply the manifest's
  `ingest.skip_files` rules; excluded chunks are never valid support or relevance labels.
- Do not use page numbers, paragraph numbers, chapter labels, inferred neighbors, or invented IDs.
- Do not summarize material unrelated to the selected questions.
- Do not reveal chain-of-thought. Give concise conclusions and evidence identifiers only.

## Field rules

### Claims

- Each claim is one independently scorable historical unit that directly helps answer the
  question. It may contain closely connected clauses when they share the same evidence,
  essentiality, and correctness verdict.
- `[x]` means essential to a materially correct and complete answer. It does not mean owner-approved.
- `[ ]` means supported and useful but nonessential.
- Split a statement when its parts require different evidence, could differ in essentiality, or
  could receive different correctness scores. Do not split merely because a sentence has more than
  one clause.
- Every `answer` item needs at least one essential claim.
- Use the smallest claim set that captures material correctness. There is no required claim quota.
- Do not add a proposition merely because it is plausible or historically familiar.

Put exact supporting chunk IDs after `||` on the same claim line. Every listed chunk must contain
evidence for the complete scorable unit. If different parts have different support, split the unit.

### Relevant

`Relevant` is question-wide, unlike claim-specific support. It must contain the union of all
supporting IDs plus every retrieval-eligible chunk containing evidence materially useful to a
complete answer within the question's declared scoring scope. Necessary historical background is
in scope even when it is not a standalone expected claim. Search the whole supplied corpus for
names, aliases, spelling variants, related institutions, and conceptually equivalent language.
Inspect neighboring chunks when a discussion crosses a boundary, but do not include a neighbor
merely because it is adjacent or every passage vaguely related to the topic. Flag uncertainty about
scope-complete coverage in Notes.

### Must not claim

This is an optional, deliberately non-exhaustive tripwire list. Include only a few specific,
plausible, consequential propositions directly implicated by the question and affirmatively
contradicted by the manuscript. Absence, uncertainty, disputed interpretation, or lack of support
is not contradiction. Record the contradicting chunk IDs in Notes. Leave the field empty when no
suitable proposition is contradicted; do not attempt to enumerate every possible falsehood.

### Behavior and Notes

For `answer`, supply at least one essential supported claim. For `abstain`, supply no claims and no
Relevant IDs; use only a corpus-local note such as “No answer located in the supplied corpus,” never
an answer from outside knowledge. For an adversarial premise, make the manuscript-supported
correction essential and put the false premise in Must not claim only when the corpus explicitly
contradicts it.

Begin every Notes field with:

`AI-DRAFT — UNVERIFIED — OWNER ADJUDICATION REQUIRED.`

Then record only concise audit information: aliases checked, genuine ambiguity, possible missing
coverage, why an optional claim is optional, and contradiction IDs for Must not claim entries.

## Required Markdown

Return each item in this exact shape:

```markdown
## H001 · focused_biographical

> Existing description, unchanged.

**Q:** Existing question, unchanged.

**Behavior:** answer

**Claims:**
- [x] Independently scorable essential paraphrased unit. || exact_chunk_id_001
- [ ] Independently scorable optional paraphrased unit. || exact_chunk_id_002, exact_chunk_id_003

**Relevant:** exact_chunk_id_001, exact_chunk_id_002, exact_chunk_id_003

**Must not claim:**
- Specific plausible proposition affirmatively contradicted by the manuscript.

**Notes:** AI-DRAFT — UNVERIFIED — OWNER ADJUDICATION REQUIRED. Concise audit notes. Must-not evidence: exact_chunk_id_004.
```

When Must not claim is empty, leave the heading with no list rows. For an abstain item, leave Claims
and Relevant empty.

## Final checks

Before responding, verify that:

1. IDs, strata, questions, descriptions, and Behavior values are unchanged.
2. Claims are independently scorable, responsive, and paraphrased.
3. Every answer item has an essential claim.
4. Every source ID exists exactly and is retrieval-eligible.
5. Every source supports the whole claim attached to it.
6. Relevant contains the support union and reflects a corpus-wide search within the declared scope,
   including materially useful background.
7. Must not claim is empty or contains only a few affirmatively contradicted tripwires, with
   evidence IDs in Notes.
8. No manuscript quotation or long copied phrase appears.
9. Every Notes field carries the unverified warning.

Start the response with this manifest, using the exact batch the owner supplied:

```text
DRAFT STATUS: UNVERIFIED — OWNER ADJUDICATION REQUIRED
BATCH: <exact item range>
MODEL LABEL: <exact displayed model label, or unknown; never guess>
CANDIDATE OUTPUTS SEEN: NO
EXTERNAL SOURCES USED: NO
```

Then output only the five completed Markdown blocks. Do not add an essay, JSON, an overall history
summary, or annotations for other items.
