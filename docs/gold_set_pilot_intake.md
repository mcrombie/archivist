# Gold-set pilot intake

Status: owner-authored questions received; exact claim locations not yet locked.

This ledger records provenance and decisions made before any pilot question is
run. It is not a gold set and must not be supplied to an evaluation harness.
The mechanically validated pilot will eventually live at
`fixtures/gold_set.pilot.json`.

## Provenance

- Owner source: `archivist_test_set.md`
- Owner source SHA-256:
  `714bf3883b4ec6176218c8e41ebb07e7a30a1692b0dd6dc63fbbdcf5c1ffc93e`
- Authored against:
  `Cradle_of_the_Empire_BASIS_FOR_TYPESETTING_DIGITAL_COPIES_revised_0706.docx`
- Authoritative DOCX SHA-256:
  `81d172186475e8f9a63070ceacb85cac0ffb411159b02cf4acc59fb78eedc3b8`
- Corpus manifest at intake:
  `d5025ffe1b6b873a54cc2959535d2c8d10d3410bcf505366a45b2c8dcc5c1109`
- Introduction-first corpus manifest:
  `b7ff94315a3f1f28c831e2c3ca62c385567d2b1447c19ff45139d175c3ff3c17`
- Intake date: 2026-07-23

At the time this intake ledger was frozen, the ten questions had not been sent
through Archivist. No retrieval results, generated answers, or judge output
had been viewed while defining this set. No API call is required for intake,
location review, or schema validation.

## Owner retrieval-scope decision

The evaluated manuscript begins with `05_Introduction.md`.

Excluded as pre-Introduction structural matter:

- `01_Front Matter.md`
- `02_Table of Contents.md`
- `03_Acknowledgments.md`
- `04_Note on Illustrations.md`

Included:

- `05_Introduction.md` through the Epilogue;
- `29_Afterword.md`; and
- Appendices A through D.

Bibliography-tagged documents remain excluded.

The active corpus manifest and vector store were synchronized to this decision
without new embeddings: 481 existing vectors remain eligible and seven
pre-Introduction vectors were removed. The Introduction-first manifest hash
above is the binding used by the empty pilot template. The pilot itself remains
unlocked until the owner approves exact claim locations.

## Question registry

| ID | Question | Stratum | Expected behavior |
|---|---|---|---|
| G001 | Who was Paquiquineo, and what became of him? | `focused_biographical` | `answer` |
| G002 | What role do John Foster and Allen Dulles play in the book's argument? | `focused_biographical` | `answer` |
| G003 | How does the book explain the shift from the Virginia Company's joint-stock structure to royal control of the colony? | `focused_analytical` | `answer` |
| G004 | What does the book say about NSC-68 and the defense budget during the Korean War? | `focused_analytical` | `answer` |
| G005 | What does the book mean by "the grand illusion"? | `conceptual` | `answer` |
| G006 | Trace the institutional lineage the book draws from the Virginia Company to the federal-corporate world of modern Northern Virginia. | `broad_thematic` | `answer` |
| G007 | How does the book treat war as an engine of federal and central power? | `broad_thematic` | `answer` |
| G008 | How does the book treat the Hudson's Bay Company and the Canadian fur trade? | `out_of_corpus` | `abstain` |
| G009 | What does the book say about COVID-19 and its effect on federal contracting? | `out_of_corpus` | qualified `answer` |
| G010 | The book argues American empire began with the Spanish-American War in 1898. Why does it identify that war as the founding moment? | `adversarial_premise` | premise-correcting `answer` |

This composition spans all six strata and satisfies the ten-item pilot
composition rule.

## Remaining owner approvals for a formal pilot fixture

These approvals apply if the practical test set is later promoted into the
strict `fixtures/gold_set.pilot.json` format. They did not block the completed
directional practical baseline, which is not a formal run of record.

Before the pilot JSON can be created, the owner reviews and approves:

- the atomic split of each supplied expected reply;
- which claims are essential and which are optional;
- every per-claim `supporting_chunk_ids` set;
- every question-level `relevant_chunk_ids` set; and
- any plausible-but-false propositions placed in `must_not_claim`.

Chapter names and paragraph ranges are orientation, not gold locations. Only
exact chunk IDs from the synchronized corpus manifest may enter location
fields. Generic failure descriptions such as "retrieval stops too early" or
"chunks cluster in one chapter" do not belong in `must_not_claim`.

For G009, positive Epilogue claims can carry supporting chunk IDs. Corpus-wide
absence conditions—COVID-19 is not named and pandemic-era federal contracting
is not discussed—remain behavioral constraints in the item notes rather than
unsupported positive claims.

Quoted manuscript language in the intake source must be replaced by an
owner-approved paraphrase before it enters a committed claim.
