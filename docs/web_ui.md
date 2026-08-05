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
- Uses recent completed turns to resolve follow-up references, then retrieves fresh manuscript
  evidence for each answer.
- Keeps the composer available at the bottom of the conversation and supports Enter to send or
  Shift+Enter for a new line.
- Uses compact numbered citations in the answer while preserving the full reference in accessible
  labels, hover text, and the source details.
- Keeps sources collapsed in a compact post-answer utility row and scopes citation links to the
  turn they support.
- Provides retry and copy-answer controls, plus a clearly labeled Start new conversation action
  in both the conversation header and the top-of-page introduction.
- Offers ten reader-facing Archivist modes that bundle appearance and answer character:
  Professional, Essential, Mythical Forest Folio, Cromb Coo Coo, Pretty Pink Princess, Baleful
  Black Baron, Tidal Archivist, Ember & Ink, Illuminated Codex, and Cosmic Almanac. Professional is
  the new-visitor default; Essential is the unchanged concise neutral baseline. Princess is
  consistently optimistic without minimizing harm; Baron is strongly tragic without inventing
  loss; Tidal uses a bounded Moby-Dick-informed maritime profile; Ember uses a project-authored
  realist-statecraft frame associated with Henry Kissinger without ingesting or imitating his
  works; Codex uses a lowercase-l modern liberal frame without present-day party advocacy; and
  Almanac uses a future-science perspective attentive to systems, long horizons, and uncertainty
  without turning projections into facts. Every mode keeps historical claims and citations
  grounded in *Cradle of the Empire*.
- Keeps Evidence scope separate from interpretation. Retrieved passages and experimental Full book
  select what manuscript context the answer receives; neither choice selects a personality.
- Moves the independent Historiographical lens, Voice, and Worldview selectors into an Advanced
  interpretive settings disclosure. The same disclosure retains all eleven visual appearances as
  explicit appearance-only overrides. Custom values apply to future turns, retries retain the
  settings that originally produced the turn, and Reset to mode restores the active preset.
- A non-default voice changes expression without automatically lengthening the answer. A
  non-Evidence-first lens or any worldview frames the cited factual answer with an uncited
  interpretive opening and conclusion. Both framing paragraphs must directly address the
  question's subject and use impersonal prose. They display with the evidence as one cohesive
  answer, while the application keeps their internal boundary so only the factual middle enters
  follow-up conversation history. Interpretive claims must grow from concrete facts in that
  middle; combined settings elaborate one judgment rather than multiplying unrelated themes.
- Shows a locally persisted API-cost estimate for each answer, conversation, UTC month, and all
  tracked use, with optional budget warnings and a local hard stop. OpenAI billing remains the
  financial source of truth; see [Cost tracking](cost_tracking.md).

Conversation history currently lasts for the open page. Starting a new conversation or reloading
the page clears it; durable saved conversations are not part of this UI pass.
