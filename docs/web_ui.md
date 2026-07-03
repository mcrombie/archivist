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

- Upload one or more `.md` / `.txt` files, or a `.zip` containing them.
- Process a manuscript into a local project under `projects/`.
- Ignore detected index files when building the searchable manuscript corpus.
- Store detected index chunks separately for consultation.
- Build or rebuild a Chroma search index for uploaded projects.
- Ask source-cited questions against a project.
- Generate candidate index entries for a term.
- Search an existing index when one is present.
- Browse candidate index terms extracted from the manuscript.
