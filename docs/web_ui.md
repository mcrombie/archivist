# Archivist Web UI

Archivist now has a local-first FastAPI and React interface.

## Run the Built UI

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.web_api:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Development UI

```powershell
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to FastAPI at `http://127.0.0.1:8000`.

## Python Dependencies

The web API needs:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
```

## Current Capabilities

- Opens directly to the built-in *Cradle of the Empire* manuscript.
- Opens under a prominent **Archivist** wordmark, the application's name, with the tagline
  “An AI historian grounded in a single manuscript” (stacked beneath the wordmark below 1180px),
  on the manuscript's title. The title is set smaller, in italics as a book title in prose, and runs straight into a
  one-sentence description of the book (“Cradle of the Empire: A Big History of Virginia
  traces…”), followed by the question box.
  Nothing interrupts a first visit: **How Archivist works** starts the same orientation on request,
  and the tour shows only the steps whose control is currently on screen. One non-modal Sources note
  waits until a source-bearing answer actually exists. The tour cannot send a request or activate
  the highlighted controls. See [Reader onboarding](reader_onboarding.md).
- Presents the cover as a compact identity rail beside a composer-first, one-book introduction.
  Settings join the composer only once a conversation exists. Every visit starts in the
  Professional perspective; choosing another is an advanced setting that lasts for the page.
- Opens in the **Cradle of the Empire** visual theme drawn from the book's own cover: ivory
  parchment, engraved sepia, pine, and restrained amber. The theme is its own Settings section,
  independent of the perspective, and every visit starts in Cradle.
- Offers four general starter questions, each of which sends on a single click, plus a quiet **Help
  me choose a question** link to a local two-step guide. The guide asks what the reader wants to
  explore and what kind of treatment would help, then fills an editable question scaffold without
  sending a request or adding synthetic turns to conversation history.
- Transitions into a full-width, multi-turn conversation after the first submission.
- Keeps earlier questions, answers, and their manuscript sources in the transcript.
- Uses recent completed turns to resolve high-confidence follow-up references locally, then makes
  one query-embedding request and ranks fresh manuscript evidence with shared dense/BM25
  reciprocal-rank fusion for each current RAG answer.
- Keeps the composer available at the bottom of the conversation and supports Enter to send or
  Shift+Enter for a new line.
- Uses compact numbered citations in the answer while preserving the full reference in accessible
  labels, hover text, and the source details.
- Keeps sources collapsed in a compact post-answer utility row and scopes citation links to the
  turn they support.
- Provides retry and copy-answer controls, plus a clearly labeled Start new conversation action
  in both the conversation header and the top-of-page introduction.
- Labels the collapsed composer control **Settings**, which appears with the docked composer once a
  conversation exists, and places Answer delivery inside its
  **Advanced delivery settings** disclosure. **Complete answer** is the recommended strict default. **Progressive
  response** is experimental. A roughly three-second heartbeat keeps an elapsed-work indicator
  active. Essential may reveal locally compiled direct evidence before its terminal result.
  Generated prose is not streamed as a checked claim because local support-ID validation is not a
  semantic-entailment proof; generated modes show stages and heartbeats until the complete answer
  or Essential fallback is ready. The canonical answer, sources, copy action, and conversation
  history appear only after final validation; interruption or late failure discards the working
  view. It exposes neither model reasoning nor raw tokens and adds no provider call. See
  [Answer delivery modes](answer_delivery.md).
- Offers exactly five reader-facing Archivist modes: Professional, Essential, Classical
  Chronicler, Perky Pollyanna, and Dour Doomsayer. Pretty Pink Princess, Baleful Black Baron, and
  Ruthless Red Realist are retired from the UI but remain defined in the repository and accepted by
  the API. Professional is the starting perspective on every visit. Essential returns
  direct cited evidence with no prose-generation call, but the shared hybrid retrieval uses one
  embedding request. Each generated mode adds exactly one no-retry, low-reasoning, medium-verbosity
  `gpt-5.6-sol` call over a rich four-to-eight-unit dossier. It authors free prose and one to three
  in-character follow-up questions. Local code maps valid support IDs to citations; a failed call
  falls back to Essential without retry. An accepted fallback remains readable and cited, but a
  visible nonfatal notice above the answer tells the reader that the requested generated mode could
  not be completed and Essential was returned instead. The notice is absent from ordinary
  Essential turns and successful generated answers. Its heading is **Essential fallback** and its
  message is “Archivist could not complete the {Mode label} AI response, so it returned Essential's
  direct manuscript evidence instead.”
- Answers a closed set of direct product questions, including “What do you do?”, through
  `product-help-v1`. The fixed explanation is identical in every Perspective, makes no provider
  call, loads no corpus, returns no sources, and remains distinct from both fictional social chat
  and manuscript RAG.
- Answers “What is Cradle of the Empire about?” and close variants (“What is this book about?”)
  with `prepared-answer-v1`, a fixed overview written once from the Introduction and cited to
  those passages. It is used only in the default Professional perspective without overrides, makes
  no provider call, skips spend preflight, and still passes the public quotation and locator checks.
  Other perspectives answer the same question live. The answer footer labels it **Prepared answer**.
- Names exhausted OpenAI usage credits plainly. When OpenAI reports `insufficient_quota`, the turn
  shows **Archivist is out of usage credits.** and explains that the developer needs to add more
  credits, instead of inviting a retry that cannot succeed.
- Routes only narrowly classified social or personal questions in every registered generated mode
  through `character-conversation-v3` before retrieval. Professional, Classical Chronicler, Perky
  Pollyanna, Dour Doomsayer, and the retired Pretty Pink Princess, Baleful Black Baron, and Ruthless
  Red Realist are covered now; Essential is excluded and future
  generated modes inherit the route through registration. That route makes exactly one
  compact, no-retry, low-reasoning/low-verbosity `gpt-5.6-sol` call with a 12-second timeout and a 576-token ceiling and
  sends no embedding, manuscript text, retrieved evidence, dossier, citation, or conversation
  history. It accepts only a fictional character reply plus one to three questions that explicitly
  lead into the manuscript or *Cradle of the Empire*. Failure returns deterministic local dialogue
  in the same character, not Essential. Historical, manuscript, mixed, and Essential
  turns stay on their normal grounded route.
- Keeps Evidence scope separate from interpretation. Retrieved passages and experimental Full book
  select what manuscript context the answer receives; neither choice selects a personality. The
  choice appears only on deployments that enable full-book answers, so it is hidden today.
- Organizes Settings into **Advanced perspective settings**, **Visual theme**, and **Advanced
  delivery settings**. The perspective section is a plain one-click list of the five perspectives,
  each with a short description, and no other control changes the perspective. Visual theme offers
  every finished theme under its original name; choosing a theme never changes the perspective, and
  choosing a perspective never changes the theme. Historiographical lens, Voice, and Worldview
  overrides are hidden behind `INTERPRETIVE_OVERRIDES_VISIBLE` but remain in code; when shown,
  custom values apply to future turns and Reset to mode restores the active preset. Retries retain
  the settings that originally produced the turn. Dormant mode IDs remain in code but are not
  selectable.
- Labels each completed answer with a static **Perspective** naming the mode that produced it,
  including “{Preset} · Custom” when overrides were active.

The preset perspective copy is fixed and appears with the hidden overrides panel:

- Professional: “Measured and diplomatic, with a present-minded focus on human agency,
  institutions, and material consequences.”
- Essential: “No added interpretive persona: direct, cited evidence from the manuscript without a
  prose-generation rewrite.”
- Classical Chronicler: “Narrative and evidence-first, attentive to causes, the limits of
  testimony, human character, and the long arc a single episode sits inside.”
- Perky Pollyanna: “Hopeful and optimistic, drawn to resilience, reform, and recovery while still
  stating harm and failure plainly.”
- Dour Doomsayer: “Pessimistic and wary, drawn to fragility, overreach, and deferred costs while
  still crediting real achievement.”

Facet overrides use “Based on {Preset}, whose character remains active, using {lens} framing, a
{voice} voice, and {worldview}.” The collapsed Advanced perspective settings summary reads
“{Preset} · Custom” while overrides are active.
- Generated modes use the resolved interpretive settings to shape authored prose. The structured
  contract separates grounded from persona runs and requires existing support IDs for historical
  prose. Local validation rejects unknown IDs, forged citations, links, HTML, malformed structure,
  and extended copying. It does not claim to prove semantic entailment.
- Exposes no V26/V27 latency or RAG-policy selector. Explicit V26/V27 compatibility remains a
  development API concern, not a reader control.
- Locally, shows a persisted API-cost estimate for each answer, conversation, UTC month, and all
  tracked use, with optional budget warnings and a local hard stop. OpenAI billing remains the
  financial source of truth; see [Cost tracking](cost_tracking.md). The **This month** pill has a
  hover and focus tooltip. Its **Usage & budget** sheet also lists this conversation answer by
  answer and keeps the recent-call log folded.
- In the public demo, shows readers only what their own conversation has cost. Once a
  conversation starts, a pill in the conversation header shows the running total, with a tooltip
  saying the developer pays and asking is free. It opens a read-only **What this conversation
  cost** sheet: the total, each question with its estimate (prepared answers read **Free**), a
  three-step explanation of what an answer pays for, and a note that figures are estimates. Readers
  never see monthly or all-time totals, budget settings, models, or the call log, and answers carry
  no per-answer cost chip.

Conversation history currently lasts for the open page. Starting a new conversation or reloading
the page clears it; durable saved conversations are not part of this UI pass.
