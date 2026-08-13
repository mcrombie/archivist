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
- Presents the cover as a compact identity rail beside a composer-first, one-book introduction.
- Offers two quiet example questions plus a local two-step guide. The guide asks what the reader
  wants to explore and what kind of treatment would help, then fills an editable question scaffold
  without sending a request or adding synthetic turns to conversation history.
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
- Labels the collapsed composer control **Settings** and places Answer delivery inside its
  **Advanced delivery settings** disclosure. **Complete answer** is the recommended strict default. **Progressive
  response** is experimental. A roughly three-second heartbeat keeps an elapsed-work indicator
  active. Essential may reveal locally compiled direct evidence before its terminal result.
  Generated prose is not streamed as a checked claim because local support-ID validation is not a
  semantic-entailment proof; generated modes show stages and heartbeats until the complete answer
  or Essential fallback is ready. The canonical answer, sources, copy action, and conversation
  history appear only after final validation; interruption or late failure discards the working
  view. It exposes neither model reasoning nor raw tokens and adds no provider call. See
  [Answer delivery modes](answer_delivery.md).
- Offers exactly five reader-facing Archivist modes: Professional, Essential, Pretty Pink
  Princess, Baleful Black Baron, and Ruthless Red Realist. Professional is the new-visitor default. Essential returns
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
- Routes only narrowly classified social or personal questions in every registered generated mode
  through `character-conversation-v2` before retrieval. Professional, Pretty Pink Princess,
  Baleful Black Baron, and Ruthless Red Realist are covered now; Essential is excluded and future
  generated modes inherit the route through registration. That route makes exactly one
  compact, no-retry, low-reasoning/low-verbosity `gpt-5.6-sol` call with a 12-second timeout and a 576-token ceiling and
  sends no embedding, manuscript text, retrieved evidence, dossier, citation, or conversation
  history. It accepts only a fictional character reply plus one to three questions that explicitly
  lead into the manuscript or *Cradle of the Empire*. Failure returns deterministic local dialogue
  in the same character, not Essential. Historical, manuscript, mixed, and Essential
  turns stay on their normal grounded route.
- Keeps Evidence scope separate from interpretation. Retrieved passages and experimental Full book
  select what manuscript context the answer receives; neither choice selects a personality.
- Moves the independent Historiographical lens, Voice, and Worldview selectors into an Advanced
  interpretive settings disclosure. Its appearance override offers only the five appearances that
  match the current modes. Dormant mode IDs, appearance definitions, and assets remain in the code
  for compatibility but are not selectable. Custom values apply to future turns, retries retain
  the settings that originally produced the turn, and Reset to mode restores the active preset.
- Shows a live **Perspective** explanation above the text field so the reader sees the selected
  interpretive bias before asking. Preset copy names the Professional, Essential, Princess,
  Baron, or Ruthless Red Realist viewpoint. Any facet or appearance override makes both the top-right active label and the
  Settings-panel mode label exactly **Custom**. Facet-custom copy still names its base preset and
  chosen lens, voice, and worldview because the base character/influence remains active;
  appearance-only copy says the underlying perspective is unchanged. Completed-turn badges retain
  “{Preset} · Custom” for provenance.

The preset Perspective copy is fixed and reader-facing:

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

Facet overrides use “Based on {Preset}, whose character remains active, using {lens} framing, a
{voice} voice, and {worldview}”; when appearance also differs, they append “Appearance is also
customized.” Appearance-only overrides say “The appearance is customized; the
underlying {Preset} perspective is unchanged,” followed by the preset copy. The settings panel
summarizes Custom as “Based on {Preset}. Advanced settings override this preset for future
answers.”
- Generated modes use the resolved interpretive settings to shape authored prose. The structured
  contract separates grounded from persona runs and requires existing support IDs for historical
  prose. Local validation rejects unknown IDs, forged citations, links, HTML, malformed structure,
  and extended copying. It does not claim to prove semantic entailment.
- Exposes no V26/V27 latency or RAG-policy selector. Explicit V26/V27 compatibility remains a
  development API concern, not a reader control.
- Shows a locally persisted API-cost estimate for each answer, conversation, UTC month, and all
  tracked use, with optional budget warnings and a local hard stop. OpenAI billing remains the
  financial source of truth; see [Cost tracking](cost_tracking.md).

Conversation history currently lasts for the open page. Starting a new conversation or reloading
the page clears it; durable saved conversations are not part of this UI pass.
