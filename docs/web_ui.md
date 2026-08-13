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
- Uses recent completed turns to resolve follow-up references locally, then ranks fresh manuscript
  evidence with local BM25 for each current RAG answer.
- Keeps the composer available at the bottom of the conversation and supports Enter to send or
  Shift+Enter for a new line.
- Uses compact numbered citations in the answer while preserving the full reference in accessible
  labels, hover text, and the source details.
- Keeps sources collapsed in a compact post-answer utility row and scopes citation links to the
  turn they support.
- Provides retry and copy-answer controls, plus a clearly labeled Start new conversation action
  in both the conversation header and the top-of-page introduction.
- Places Answer delivery inside a collapsed **Advanced delivery settings** disclosure under
  Reading options. **Complete answer** is the recommended strict default. **Progressive
  response** is experimental: after fixed operational progress, it reveals locally compiled
  immutable evidence cards while the final arrangement remains provisional. A roughly
  three-second heartbeat keeps an elapsed-work indicator active. Essential needs no provider call;
  in a generated mode the cards can appear while the one no-retry selector call chooses card order
  and local cue IDs. The canonical answer, sources, copy action, and conversation history appear
  only after final validation; interruption or late failure discards the working view. It exposes
  neither model reasoning nor model-authored prose and adds no provider call. See
  [Answer delivery modes](answer_delivery.md).
- Offers exactly four reader-facing Archivist modes: Professional, Essential, Pretty Pink
  Princess, and Baleful Black Baron. Professional is the new-visitor default. Essential returns
  the direct evidence compiled by the application with zero provider calls. Each generated mode
  makes exactly one no-retry, low-reasoning `gpt-5.6-sol` call that may select only exact evidence
  placeholders and IDs from its application-owned cue catalog. Local code supplies every displayed
  factual and editorial word and every citation; a failed call falls back to Essential.
- Keeps Evidence scope separate from interpretation. Retrieved passages and experimental Full book
  select what manuscript context the answer receives; neither choice selects a personality.
- Moves the independent Historiographical lens, Voice, and Worldview selectors into an Advanced
  interpretive settings disclosure. Its appearance override offers only the four appearances that
  match the current modes. Dormant mode IDs, appearance definitions, and assets remain in the code
  for compatibility but are not selectable. Custom values apply to future turns, retries retain
  the settings that originally produced the turn, and Reset to mode restores the active preset.
- Generated modes use the resolved interpretive settings to constrain selection from a closed,
  mode-specific cue catalog. The model cannot return free prose, and local validation rejects raw
  text, unknown cue IDs, cross-mode cues, or a card arrangement that does not use every evidence
  card exactly once.
- Exposes no V26/V27 latency or RAG-policy selector. Explicit V26/V27 compatibility remains a
  development API concern, not a reader control.
- Shows a locally persisted API-cost estimate for each answer, conversation, UTC month, and all
  tracked use, with optional budget warnings and a local hard stop. OpenAI billing remains the
  financial source of truth; see [Cost tracking](cost_tracking.md).

Conversation history currently lasts for the open page. Starting a new conversation or reloading
the page clears it; durable saved conversations are not part of this UI pass.
