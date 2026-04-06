# Archivist Evaluation

This document evaluates Archivist’s retrieval and generation quality across a set of representative queries.

The goal is to assess:
- retrieval relevance
- answer coherence
- citation accuracy
- behavior across different query types

---


## Key Takeaways

- Archivist performs strongly on focused, contextual, and biographical queries
- Index mode reliably identifies and organizes cross-chapter themes
- The main limitation is broad thematic questions, which tend to over-focus on dense sections of the manuscript
- Hybrid retrieval strategies significantly improve named-entity and indexing performance

---


## Test Setup

- Corpus: full manuscript (Markdown chunks)
- Embeddings: `text-embedding-3-small`
- Vector DB: Chroma (persistent)
- Retrieval:
  - semantic search (top 5)
  - neighbor chunk expansion
  - distance filtering
  - context cap (8 chunks)
- Index mode:
  - exact match + semantic hybrid retrieval

---

## Query Categories

### 1. Focused Analytical Questions

#### Example

What role did Jamestown play as a corporate experiment?

Answer:

- Jamestown functioned as the Virginia Company’s profit‑driven corporate outpost: the Company used its trade monopoly to sell settlers supplies at high rates in exchange for tobacco, compelling planters to grow the leaf to meet company terms [Source 1]. Tobacco and days of labor became the colony’s units of account because coin was scarce, embedding company extraction into everyday exchange [Source 1]. To solve labor and land needs, the Company imported indentured servants and granted 50 acres per head under the headright system; high mortality meant masters often inherited servants’ property and claims, accelerating estate concentration [Source 1]. After the Starving Time, Company promoters minimized the catastrophe in print and reorganized management away from communal labor toward private plots and incentives, sharpening the settlement’s commercial footing [Source 8]. Under Deputy Governor Samuel Argall, Jamestown even served as a pirate base against Spain, tying colonial revenues to privateering [Source 1]. Weeks later, Jamestown received the “twenty and odd” Ndongans from such raiding, whom Governor Yeardley obtained for food, the first recorded Africans forcibly brought into English Virginia [Source 3]. In England, wealthy merchants invested in the Company as Parliament grew more business‑oriented, linking Jamestown’s fortunes to metropolitan commercial power [Source 2].

- It was also a laboratory for company‑designed governance: under Sir Edwin Sandys, the Company repealed harsh laws and allowed settlers to organize their own legislature [Source 2]. Governor Yeardley convened a General Assembly from 11 Virginia boroughs; because the Company’s instructions lacked a new legal code, the Assembly drafted and enacted its own laws [Source 2][Source 3]. In its first years it established English common law, 
regulated tobacco, legislated on servants and moral codes, limited Indian interaction, and codified land policy including headrights [Source 3][Source 7]. The Company’s Great Charter then reorganized this body into a bicameral legislature—the Governor’s Council and the elected House of Burgesses—planting a tradition of representative government under a corporate charter [Source 7]. After the 1622 war, a royal commission condemned the 
Company as a lethal, profit‑first operation and King James dissolved it, but the Crown assured the General Assembly its rights would remain, carrying Jamestown’s corporate‑era institutions into royal rule [Source 5][Source 6].

Sources shown to model:

Source 1
  Document: 10_Chapter 4 Cradle of the Empire (1601 - 1622).md
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_016
  Paragraphs: 49–52
------------------------------------------------------------
Source 2
  Document: 10_Chapter 4 Cradle of the Empire (1601 - 1622).md
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_017
  Paragraphs: 52–55
------------------------------------------------------------
Source 3
  Document: 10_Chapter 4 Cradle of the Empire (1601 - 1622).md
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_018
  Paragraphs: 55–58
------------------------------------------------------------
Source 4
  Document: 11_Chapter 5 Wrath of Mangopeesomon (1622-1646).md
  Chapter: Chapter 5 Wrath of Mangopeesomon (1622-1646)
  Chunk ID: 11_Chapter 5 Wrath of Mangopeesomon (1622-1646)_004
  Paragraphs: 10–13
------------------------------------------------------------
Source 5
  Document: 11_Chapter 5 Wrath of Mangopeesomon (1622-1646).md
  Chapter: Chapter 5 Wrath of Mangopeesomon (1622-1646)
  Chunk ID: 11_Chapter 5 Wrath of Mangopeesomon (1622-1646)_005
  Paragraphs: 13–16
------------------------------------------------------------
Source 6
  Document: 11_Chapter 5 Wrath of Mangopeesomon (1622-1646).md
  Chapter: Chapter 5 Wrath of Mangopeesomon (1622-1646)
  Chunk ID: 11_Chapter 5 Wrath of Mangopeesomon (1622-1646)_006
  Paragraphs: 16–19
------------------------------------------------------------
Source 7
  Document: 10_Chapter 4 Cradle of the Empire (1601 - 1622).md
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_019
  Paragraphs: 58–61
------------------------------------------------------------
Source 8
  Document: 10_Chapter 4 Cradle of the Empire (1601 - 1622).md
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_011
  Paragraphs: 32–35
------------------------------------------------------------


**Result:**
- Retrieved Chapter 4 and 5 chunks
- Strong discussion of:
  - Virginia Company structure
  - labor systems
  - tobacco economy

**Assessment:**
- High relevance
- Good synthesis
- Accurate citations

**Verdict:** ✅ Strong performance

---

### 2. Biographical Questions

#### Example

What does the manuscript say about Paquiquineo?                    

Answer:

- The manuscript identifies Paquiquineo as likely born into a noble family along the Powhatan (James) River, trained from boyhood in archery and warfare amid threats from Siouan and Iroquoian neighbors. [Source 2]      
- In Powhatan society, boys underwent the huskanaw initiation before manhood; the text situates Paquiquineo’s first encounter with Europeans sometime after he would have completed this rite. [Source 2]
- He and a companion approached a Spanish ship on the river; the Spaniards took them aboard and crossed the Atlantic, with Spanish accounts claiming he went willingly and some historians arguing he was kidnapped. [Source 2]
- During the long Atlantic passage he began learning Spanish and exchanged information with two Indigenous men from Mexico; the author notes speculation that Paquiquineo learned of Spain’s conquest, enslavement, and forced conversion there, though the details are uncertain. [Source 2, Source 3]
- Delivered to Spain after months at sea, he was taken to Madrid to meet King Philip II. [Source 3]
- Seeing an opportunity to anchor Spain’s claim to La Florida in the Chesapeake, Philip II sponsored Paquiquineo’s education and then sent him to New Spain to train as an interpreter for colonizing his homeland. [Source 4]
- In New Spain he saw enslaved people laboring and fell ill; he requested baptism, received the name Don Luis de Velasco, recovered, and then missed the departing Ajacán expedition. [Source 4]
- Because he was now a Christian, officials would not return him without clergy; for years he promoted Ajacán by describing Virginia’s population, mineral prospects, and a possible northwest passage, while he continued 
observing Spanish colonial practices. [Source 5]
- Governor Pedro Menéndez de Avilés later backed the Ajacán mission; Don Luis traveled among Spanish outposts and, according to the manuscript’s reading of Brickhouse, misdirected the 1566 expedition and helped turn the crew against settling, leading them to abandon the attempt and return to Spain. [Source 5]
- The appendix reviews a long-standing but contested hypothesis that Don Luis (Paquiquineo) was the Powhatan leader Opechancanough; some historians have entertained the idea, while others argue they were from different 
elite families or that Paquiquineo may have been a close maternal relative instead. [Source 6]

Sources shown to model:

Source 1
  Document: 08_Chapter 2 Tsenacomoco (1542-1572).md
  Chapter: Chapter 2 Tsenacomoco (1542-1572)
  Chunk ID: 08_Chapter 2 Tsenacomoco (1542-1572)_002
  Paragraphs: 4–7
------------------------------------------------------------
Source 2
  Document: 08_Chapter 2 Tsenacomoco (1542-1572).md
  Chapter: Chapter 2 Tsenacomoco (1542-1572)
  Chunk ID: 08_Chapter 2 Tsenacomoco (1542-1572)_003
  Paragraphs: 7–10
------------------------------------------------------------
Source 3
  Document: 08_Chapter 2 Tsenacomoco (1542-1572).md
  Chapter: Chapter 2 Tsenacomoco (1542-1572)
  Chunk ID: 08_Chapter 2 Tsenacomoco (1542-1572)_004
  Paragraphs: 10–13
------------------------------------------------------------
Source 4
  Document: 08_Chapter 2 Tsenacomoco (1542-1572).md
  Chapter: Chapter 2 Tsenacomoco (1542-1572)
  Chunk ID: 08_Chapter 2 Tsenacomoco (1542-1572)_005
  Paragraphs: 13–16
------------------------------------------------------------
Source 5
  Document: 08_Chapter 2 Tsenacomoco (1542-1572).md
  Chapter: Chapter 2 Tsenacomoco (1542-1572)
  Chunk ID: 08_Chapter 2 Tsenacomoco (1542-1572)_006
  Paragraphs: 16–19
------------------------------------------------------------
Source 6
  Document: 30_Appendix B Was Don Luis Opechancanough.md
  Chapter: Appendix B Was Don Luis Opechancanough
  Chunk ID: 30_Appendix B Was Don Luis Opechancanough_001
  Paragraphs: 1–3
------------------------------------------------------------


**Result:**
- Retrieved Chapter 2 chunks
- Retrieved Appendix B chunk
- Included:
  - early contact with Spanish
  - return to Virginia
  - Jesuit mission
  - identity ambiguity (Don Luis vs Opechancanough)

**Assessment:**
- Narrative coherence improved with neighbor chunks
- Slight sensitivity to context cap (later events sometimes trimmed)

**Verdict:** ✅ Good, minor completeness tradeoff

---

### 3. Thematic Questions (Broad)

#### Example

What does the manuscript say about slavery?

Answer:

- After independence, Virginia’s economy remained anchored in coerced labor by hundreds of thousands of enslaved Black people. [Source 6] Enslaved people made up about 40% of the state’s population. [Source 6] Many Virginia elites called slavery immoral and inefficient yet treated abolition as an intractable “Gordian knot” because enslaved people constituted a core part of elite wealth. [Source 6]

- The 1782 Manumission Act allowed owners to free enslaved people. [Source 6] Robert Carter manumitted over 500 people. [Source 6] Richard Randolph freed more than seventy people and left them a fifth of his plantation. [Source 6] Most owners rejected manumission and decried the growth of Virginia’s free Black population. [Source 6]

- In Massachusetts, the Quock Walker cases led Chief Justice William Cushing to hold slavery unconstitutional under the state constitution, effectively ending slavery in that state. [Source 6] This helped propel a wider movement to abolish slavery across the states and globally. [Source 6]

- Among Southern planters, many Virginians favored ending the transatlantic slave trade after a grace period, since natural increase had produced a labor glut. [Source 7] Consequently, Virginians sold surplus enslaved people to other states, often splitting families. [Source 7] By contrast, South Carolina secured a twenty‑year delay in ending legal slave imports. [Source 7]

- Nat Turner’s 1831 rebellion killed nearly sixty white people in Southampton County. [Source 5] Militia and federal troops crushed the revolt within days, executing Turner, his followers, and many innocents, and displaying severed heads on pikes to terrorize others. [Source 5]

- In the aftermath, violent repression spread amid rumors of wider conspiracies. [Source 1] Debate flared, with some calling for gradual or immediate abolition and removal of Black people from Virginia. [Source 1] Clergy often defended slavery even as major Protestant denominations fractured over the issue. [Source 1] Thomas Jefferson Randolph’s proposal for gradual emancipation was swiftly defeated in the General Assembly. [Source 1] Instead, lawmakers imposed tighter restrictions on free and enslaved Black people’s assembly, worship, and bearing arms. [Source 1]

- The political wind shifted toward defending slavery as a “positive good.” [Source 1, Source 2] One Virginia speaker even proclaimed slavery a divine institution sanctioned by Scripture. [Source 2]

- Northern abolitionists intensified their attacks: William Lloyd Garrison denounced slavery in The Liberator. [Source 2] The American Anti‑Slavery Society declared slaveholding “man‑stealing,” pronounced pro‑slavery laws null before God, and demanded their immediate abrogation. [Source 2, Source 3]

- British industrial demand for cotton encouraged Southern planters to entrench slavery further. [Source 3] Virginia’s General Assembly passed a statute severely punishing challenges to slavery; critics called it a First Amendment violation, though it was rarely enforced. [Source 3]

- Some Virginians promoted colonization: emancipation followed by resettlement of Black Virginians in Africa as prospective Christian allies. [Source 4] The projected costs made the scheme unrealistic. [Source 4] Even so, the American Colonization Society sent thousands of often reluctant Black Virginians to Liberia over about a generation. [Source 4] Joseph Jenkins Roberts, a free Black Virginian, migrated to Monrovia, built an export business, became high sheriff, and suppressed indigenous resistance to Americo‑Liberian rule. [Source 4]

Sources shown to model:

Source 1
  Document: 19_Chapter 13 Conquest of the Continent (1824-1850).md
  Chapter: Chapter 13 Conquest of the Continent (1824-1850)
  Chunk ID: 19_Chapter 13 Conquest of the Continent (1824-1850)_005
  Paragraphs: 13–16
------------------------------------------------------------
Source 2
  Document: 19_Chapter 13 Conquest of the Continent (1824-1850).md
  Chapter: Chapter 13 Conquest of the Continent (1824-1850)
  Chunk ID: 19_Chapter 13 Conquest of the Continent (1824-1850)_006
  Paragraphs: 15–18
------------------------------------------------------------
Source 3
  Document: 19_Chapter 13 Conquest of the Continent (1824-1850).md
  Chapter: Chapter 13 Conquest of the Continent (1824-1850)
  Chunk ID: 19_Chapter 13 Conquest of the Continent (1824-1850)_007
  Paragraphs: 17–20
------------------------------------------------------------
Source 4
  Document: 19_Chapter 13 Conquest of the Continent (1824-1850).md
  Chapter: Chapter 13 Conquest of the Continent (1824-1850)
  Chunk ID: 19_Chapter 13 Conquest of the Continent (1824-1850)_008
  Paragraphs: 20–23
------------------------------------------------------------
Source 5
  Document: 19_Chapter 13 Conquest of the Continent (1824-1850).md
  Chapter: Chapter 13 Conquest of the Continent (1824-1850)
  Chunk ID: 19_Chapter 13 Conquest of the Continent (1824-1850)_004
  Paragraphs: 10–13
------------------------------------------------------------
Source 6
  Document: 17_Chapter 11 The American Empire (1776 - 1800).md
  Chapter: Chapter 11 The American Empire (1776 - 1800)
  Chunk ID: 17_Chapter 11 The American Empire (1776 - 1800)_009
  Paragraphs: 25–28
------------------------------------------------------------
Source 7
  Document: 17_Chapter 11 The American Empire (1776 - 1800).md
  Chapter: Chapter 11 The American Empire (1776 - 1800)
  Chunk ID: 17_Chapter 11 The American Empire (1776 - 1800)_010
  Paragraphs: 28–31
------------------------------------------------------------
Source 8
  Document: 17_Chapter 11 The American Empire (1776 - 1800).md
  Chapter: Chapter 11 The American Empire (1776 - 1800)
  Chunk ID: 17_Chapter 11 The American Empire (1776 - 1800)_011
  Paragraphs: 31–34
------------------------------------------------------------


**Result:**
- Retrieved mostly mid/late chapters (11–13)
- Focused on:
  - post-independence slavery
  - Nat Turner rebellion
  - pro-slavery ideology

**Issue:**
- Missed earlier material:
  - 1619 introduction of Africans
  - early labor systems
  - Indigenous enslavement

**Assessment:**
- Answer is correct but **not comprehensive**
- Retrieval is too localized for broad themes

**Verdict:** ⚠️ Known limitation

**Cause:**
- Semantic retrieval clusters around dense conceptual sections rather than distributing across the full manuscript timeline

---

### 4. Conceptual Questions

#### Example

What does the manuscript say about propaganda in the interwar period?

Answer:

- The manuscript says that, after World War I, Virginians joined a national reassessment of how the war had been sold to the public, sparked by Britain’s former Chief of Intelligence admitting to fabricating lies about 
Germany. [Source 2] A Richmond Times-Dispatch editorial denounced the infamous “corpses to fat” story and lamented that citizens had been made “dupes and fools” by their own governments’ wartime falsehoods. [Source 2]  

- It argues that the Creel Committee’s wartime success and the 1920s advertising boom demonstrated how powerfully propaganda could shape mass opinion. [Source 2] Edward Bernays went so far as to claim that deliberate manipulation of public habits and opinions is integral to democracy and that those who do it form an “invisible government” that is the country’s true ruling power. [Source 2, Source 3]

- Another contemporary observer warned that controllers of the press and radio had become an administrative bureaucracy serving business interests. [Source 3, Source 4] The text links these claims to new technologies that let a handful of men mold the views of tens of millions, with radio spreading rapidly into homes as hundreds of stations opened and farmers came to see a set as “a necessity.” [Source 4]

Sources shown to model:

Source 1
  Document: 23_Chapter 17 War for the World (1917 - 1945).md
  Chapter: Chapter 17 War for the World (1917 - 1945)
  Chunk ID: 23_Chapter 17 War for the World (1917 - 1945)_014
  Paragraphs: 40–43
------------------------------------------------------------
Source 2
  Document: 23_Chapter 17 War for the World (1917 - 1945).md
  Chapter: Chapter 17 War for the World (1917 - 1945)
  Chunk ID: 23_Chapter 17 War for the World (1917 - 1945)_015
  Paragraphs: 43–46
------------------------------------------------------------
Source 3
  Document: 23_Chapter 17 War for the World (1917 - 1945).md
  Chapter: Chapter 17 War for the World (1917 - 1945)
  Chunk ID: 23_Chapter 17 War for the World (1917 - 1945)_016
  Paragraphs: 45–48
------------------------------------------------------------
Source 4
  Document: 23_Chapter 17 War for the World (1917 - 1945).md
  Chapter: Chapter 17 War for the World (1917 - 1945)
  Chunk ID: 23_Chapter 17 War for the World (1917 - 1945)_017
  Paragraphs: 47–50
------------------------------------------------------------
Source 5
  Document: 28_Afterword (Tentative).md
  Chapter: Afterword (Tentative)
  Chunk ID: 28_Afterword (Tentative)_005
  Paragraphs: 14–17
------------------------------------------------------------
Source 6
  Document: 28_Afterword (Tentative).md
  Chapter: Afterword (Tentative)
  Chunk ID: 28_Afterword (Tentative)_006
  Paragraphs: 17–20
------------------------------------------------------------
Source 7
  Document: 28_Afterword (Tentative).md
  Chapter: Afterword (Tentative)
  Chunk ID: 28_Afterword (Tentative)_007
  Paragraphs: 20–21
------------------------------------------------------------


**Result:**
- Retrieved Chapter 17 (WWI/WWII era)
- Retrieved Afterword
- Included:
  - Creel Committee
  - Bernays
  - media influence

**Assessment:**
- Strong conceptual synthesis
- Good use of quotes and supporting evidence

**Verdict:** ✅ Strong performance

---

### 5. Index Mode (Proper Nouns)

#### Example

Virginia Company

Candidate index entry:

Index term: Virginia Company

Summary:
The manuscript traces the Virginia Company from its Elizabethan conception as a joint-stock venture inspired by earlier companies to its formation under James I to plant a colony in Virginia [Source 1; Source 2]. It funded and directed the Jamestown expedition and early policies, including diplomatic instructions to Newport and later the more coercive demands of the Second Supply; it struggled to produce profits and resorted to public lotteries [Source 3; Source 5; Source 6; Source 7]. A major reorientation came with the 1609 charter, which reorganized governance, ordered the subjugation of Powhatan peoples, launched the Third Supply, and dramatically expanded Virginia’s theoretical territorial claims [Source 8]. Overall, the Company is treated as the driving institutional force behind early English colonization, from strategy and finance to on-the-ground directives [Source 2; Source 6–8].

Key locations:
- [Source 1] Chapter 3 The Virgin Queen's Colony (1572-1601)_010 — envisioning a Virginia Company from earlier joint-stock successes
- [Source 2] Chapter 4 Cradle of the Empire (1601 - 1622)_002 — formation as a joint-stock company; risk-sharing; goals for first colony
- [Source 3] Chapter 4 Cradle of the Empire (1601 - 1622)_003 — Virginia Company expedition’s arrival at Cape Henry
- [Source 5] Chapter 4 Cradle of the Empire (1601 - 1622)_006 — Company orders to establish friendly relations; youth exchanges
- [Source 6] Chapter 4 Cradle of the Empire (1601 - 1622)_007 — investor impatience; Second Supply; directives to crown Powhatan and explore west
- [Source 7] Chapter 4 Cradle of the Empire (1601 - 1622)_008 — financial troubles; reliance on public lotteries; Popham failure context
- [Source 8] Chapter 4 Cradle of the Empire (1601 - 1622)_009 — 1609 charter, governance overhaul, Third Supply, expanded territorial claim

Suggested subentries:
- joint-stock model and investors [Source 2; Source 6–7]
- first expedition and Jamestown landing [Source 3]
- Second Supply and directives (crowning Powhatan; westward expedition) [Source 6]
- 1609 charter and Third Supply; expanded territorial claims [Source 8]
- financing through public lotteries [Source 7]

Sources shown to model:

Source 1
  Chapter: Chapter 3 The Virgin Queen's Colony (1572-1601)
  Chunk ID: 09_Chapter 3 The Virgin Queen's Colony (1572-1601)_010
  Paragraphs: 28–30
------------------------------------------------------------
Source 2
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_002
  Paragraphs: 4–7
------------------------------------------------------------
Source 3
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_003
  Paragraphs: 7–10
------------------------------------------------------------
Source 4
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_004
  Paragraphs: 10–13
------------------------------------------------------------
Source 5
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_006
  Paragraphs: 17–20
------------------------------------------------------------
Source 6
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_007
  Paragraphs: 20–23
------------------------------------------------------------
Source 7
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_008
  Paragraphs: 23–26
------------------------------------------------------------
Source 8
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_009
  Paragraphs: 26–29
------------------------------------------------------------


**Initial Issue:**
- Semantic retrieval failed to find Chapter 4
- Returned unrelated charter material

**Fix:**
- Added exact-match-first retrieval

**Result After Fix:**
- Correctly retrieves Chapter 3 and 4
- Identifies:
  - corporate structure
  - investment model
  - governance

**Verdict:** ✅ Fixed and reliable

---

### 6. Index Mode (Concepts)

#### Example

propaganda

Candidate index entry:

Index term: propaganda

Summary:
The manuscript treats propaganda as a recurring tool of power—from early corporate spin by the Virginia Company to modern state-directed mass persuasion. It emphasizes World War I as a turning point, when governments systematically mobilized public opinion via modern media and U.S. Liberty Bond drives, even masking financial failures to avoid a German “propaganda coup” [Source 3; Source 4; Source 2]. Postwar reflections highlight the 
Creel Committee’s success, public anger over fabricated atrocity stories, and theoretical critiques by Bernays and others, with television later extending propaganda’s reach in the consumer age [Source 6; Source 7; Source 8; Source 5; Source 1].

Key locations:
- [Source 3] Chapter 16: Governments deploy modern media to rouse populations during WWI.
- [Source 4] Chapter 17: U.S. Liberty Bonds paired with a massive campaign to sell the war.
- [Source 2] Chapter 16: British war-bond cover-up to prevent a German “propaganda coup.”
- [Source 6] Chapter 17: Postwar outrage over fabricated wartime stories; Creel Committee’s success; Bernays on “invisible government.”
- [Source 7] Chapter 17: Rorty on media serving vested business interests (propaganda critique).
- [Source 8] Chapter 18: Television revolutionizes home entertainment and propaganda.
- [Source 5] Chapter 17: Public sets aside concerns about government propaganda and civil rights violations.
- [Source 1] Chapter 4: Early example—Virginia Company propaganda failing to mask Jamestown’s crisis.

Suggested subentries:
- World War I mobilization and modern media [Source 3; Source 4]
- British bond cover-up to avert a German “propaganda coup” [Source 2]
- Creel Committee and postwar reassessment [Source 6]
- Bernays on “invisible government” of opinion-shaping [Source 6; Source 7]
- Television as a postwar propaganda medium [Source 8]

Sources shown to model:

Source 1
  Chapter: Chapter 4 Cradle of the Empire (1601 - 1622)
  Chunk ID: 10_Chapter 4 Cradle of the Empire (1601 - 1622)_013
  Paragraphs: 40–43
------------------------------------------------------------
Source 2
  Chapter: Chapter 16 The Lords of North America (1893 - 1917)
  Chunk ID: 22_Chapter 16 The Lords of North America (1893 - 1917)_033
  Paragraphs: 89–92
------------------------------------------------------------
Source 3
  Chapter: Chapter 16 The Lords of North America (1893 - 1917)
  Chunk ID: 22_Chapter 16 The Lords of North America (1893 - 1917)_035
  Paragraphs: 94–97
------------------------------------------------------------
Source 4
  Chapter: Chapter 17 War for the World (1917 - 1945)
  Chunk ID: 23_Chapter 17 War for the World (1917 - 1945)_003
  Paragraphs: 7–10
------------------------------------------------------------
Source 5
  Chapter: Chapter 17 War for the World (1917 - 1945)
  Chunk ID: 23_Chapter 17 War for the World (1917 - 1945)_012
  Paragraphs: 34–37
------------------------------------------------------------
Source 6
  Chapter: Chapter 17 War for the World (1917 - 1945)
  Chunk ID: 23_Chapter 17 War for the World (1917 - 1945)_015
  Paragraphs: 43–46
------------------------------------------------------------
Source 7
  Chapter: Chapter 17 War for the World (1917 - 1945)
  Chunk ID: 23_Chapter 17 War for the World (1917 - 1945)_016
  Paragraphs: 45–48
------------------------------------------------------------
Source 8
  Chapter: Chapter 18 The Warfare State (1945 - 1971)
  Chunk ID: 24_Chapter 18 The Warfare State (1945 - 1971)_004
  Paragraphs: 10–13
------------------------------------------------------------


**Result:**
- Retrieved:
  - wartime propaganda
  - Bernays
  - media evolution
- Suggested subentries:
  - public relations
  - radio
  - wartime mobilization

**Assessment:**
- Useful for index-building
- Captures cross-chapter theme

**Verdict:** ✅ Strong performance

---

### 7. Index Mode (Cross-Chapter Themes)

#### Example

Canals

Candidate index entry:

Index term: Canals

Summary:
Canals appear as central to Virginia’s long effort to overcome the Appalachian barrier and capture western commerce, from George Washington’s early James and Potomac schemes to link the Ohio Basin to Tidewater, to the protracted, underfunded James River and Kanawha Canal that dragged on for decades and ultimately failed [Source 2; Source 5; Source 6]. The narrative ties canals to speculative finance and infrastructure corporations in 
the 1790s, to interstate competition as Pennsylvania and New York raced ahead, and to widening regional tensions between eastern planters and western settlers over internal improvements [Source 3; Source 4; Source 5]. By the mid-19th century, state-backed canal projects had saddled Virginia with heavy debts via the Board of Public Works and helped spark later political battles over debt repayment and public schooling, even as railroads eclipsed the canal vision [Source 6; Source 7].

Key locations:
- [Source 2] Chapter 11, chunk _015 — Washington’s James River and Potomac companies; “politics would not wait for canals.”
- [Source 3] Chapter 11, chunk _020 — Age of easy credit; rise of infrastructure corporations building turnpikes and canals.
- [Source 4] Chapter 12, chunk _001 — Pennsylvania and New York racing to build canals to the Mississippi watershed; Virginia’s relative decline.
- [Source 5] Chapter 12, chunk _008 — Western Virginia’s push for state-backed canals; stalled James River and Kanawha Canal; internal improvements debate and Staunton Convention context.
- [Source 6] Chapter 14, chunk _004 — Board of Public Works financing of canals; eastern elites preferring the James–Kanawha Canal; canal unfinished and costly; Norfolk’s backlash.
- [Source 7] Chapter 15, chunk _009 — Postwar debt crisis tied to roads, canals, and railroads; Funders vs. Readjusters.

Suggested subentries:
- James River and Kanawha Canal: delays and ultimate failure [Source 5; Source 6]
- Washington’s canal vision: James River Company and Potomac Company [Source 2]
- Board of Public Works financing and state debt [Source 6; Source 7]
- Northern canal competition (Pennsylvania, New York) [Source 4]
- Western Virginia internal improvements agitation [Source 5]

Sources shown to model:

Source 1
  Chapter: Chapter 11 The American Empire (1776 - 1800)
  Chunk ID: 17_Chapter 11 The American Empire (1776 - 1800)_014
  Paragraphs: 40–43
------------------------------------------------------------
Source 2
  Chapter: Chapter 11 The American Empire (1776 - 1800)
  Chunk ID: 17_Chapter 11 The American Empire (1776 - 1800)_015
  Paragraphs: 43–46
------------------------------------------------------------
Source 3
  Chapter: Chapter 11 The American Empire (1776 - 1800)
  Chunk ID: 17_Chapter 11 The American Empire (1776 - 1800)_020
  Paragraphs: 58–61
------------------------------------------------------------
Source 4
  Chapter: Chapter 12 The Virginia Dynasty (1800-1824)
  Chunk ID: 18_Chapter 12 The Virginia Dynasty (1800-1824)_001
  Paragraphs: 1–4
------------------------------------------------------------
Source 5
  Chapter: Chapter 12 The Virginia Dynasty (1800-1824)
  Chunk ID: 18_Chapter 12 The Virginia Dynasty (1800-1824)_008
  Paragraphs: 23–26
------------------------------------------------------------
Source 6
  Chapter: Chapter 14 Knell of the Union (1850-1870)
  Chunk ID: 20_Chapter 14 Knell of the Union (1850-1870)_004
  Paragraphs: 10–13
------------------------------------------------------------
Source 7
  Chapter: Chapter 15 An Industrial Revolution (1870 - 1893)
  Chunk ID: 21_Chapter 15 An Industrial Revolution (1870 - 1893)_009
  Paragraphs: 25–28
------------------------------------------------------------
Source 8
  Chapter: Chapter 11 The American Empire (1776 - 1800)
  Chunk ID: 17_Chapter 11 The American Empire (1776 - 1800)_013
  Paragraphs: 37–40
------------------------------------------------------------


**Result:**
- Retrieved multiple chapters
- Identified:
  - canal infrastructure
  - economic development
  - political debates

**Assessment:**
- Demonstrates ability to track themes over time
- Generates useful subentries

**Verdict:** ✅ Distinctive capability

---

## Improvements Implemented

### 1. Neighbor Chunk Expansion
- Prevents fragmentation of arguments
- Keeps quotes attached to analysis

### 2. Inline Footnotes
- Preserves source context within chunks
- Improves retrieval quality

### 3. Context Finalization Layer
- Ensures consistent source numbering
- Prevents citation mismatch

### 4. Document Filtering
- Excludes:
  - Table of Contents
  - Bibliography
- Reduces noise in retrieval

### 5. Hybrid Retrieval (Index Mode)
- Combines:
  - exact match
  - semantic retrieval
- Fixes named-entity failures

---

## Known Limitations

### 1. Thematic Retrieval Bias
Broad queries tend to:
- overweight dense sections
- underrepresent earlier/later material

### 2. No Page-Level Mapping
- Sources reference chunks, not pages
- Will be addressed after final manuscript formatting

### 3. Heuristic-Based Retrieval
- No learned reranking
- No query-type adaptation (yet)

---

## Future Work

- Hybrid retrieval for Answer Mode (broad themes)
- Page-number integration
- Improved query classification
- UI for exploration and browsing
- Index export tooling

---

## Summary

Archivist performs strongly on:
- focused analytical questions
- biographical queries
- conceptual topics
- index generation

The primary limitation is:
- handling broad thematic queries across the entire manuscript

Overall, the system demonstrates that RAG can be effectively applied to long-form historical texts when augmented with domain-specific retrieval strategies such as hybrid search and context expansion.