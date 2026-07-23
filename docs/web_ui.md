# Archivist Web UI

Archivist now has a local-first FastAPI and React interface.

## Run the Built UI

```powershell
.\venv\Scripts\python.exe -m uvicorn src.web_api:app --host 127.0.0.1 --port 8000
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
.\venv\Scripts\python.exe -m pip install -r requirements-web.txt
```

## Current Capabilities

- Opens directly to the built-in *Cradle of the Empire* manuscript.
- Presents the cover and introduction before the first question.
- Transitions into a full-width, multi-turn conversation after the first submission.
- Keeps earlier questions, answers, and their manuscript sources in the transcript.
- Uses recent completed turns to resolve follow-up references, then retrieves fresh manuscript
  evidence for each answer.
- Keeps the composer available at the bottom of the conversation and supports Enter to send or
  Shift+Enter for a new line.
- Keeps sources collapsed beneath the answer they support and scopes citation links to that turn.
- Provides retry, copy-answer, and new-conversation controls.
- Offers seven persistent visual vibes adapted from Cromblog. Vibes affect presentation only.
- Offers independent Historiographical lens, Voice, and Worldview selectors. Their all-default
  combination is the unchanged Neutral baseline, and the chosen settings are recorded on each
  answer.
- Shows a locally persisted API-cost estimate for each answer, conversation, UTC month, and all
  tracked use, with optional budget warnings and a local hard stop. OpenAI billing remains the
  financial source of truth; see [Cost tracking](cost_tracking.md).

Conversation history currently lasts for the open page. Starting a new conversation or reloading
the page clears it; durable saved conversations are not part of this UI pass.
