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

- Opens to a simple upload-first manuscript screen.
- Processes the manuscript before presenting mode selection.
- Offers Q&A mode and index mode as separate focused workspaces.
- Upload one or more `.md` / `.txt` / `.docx` / `.pdf` files, or a `.zip` containing them.
- Convert `.docx` paragraphs/tables and selectable `.pdf` text into Archivist chunks.
- Split a final `Index`, `General Index`, or `Index of Names` section into existing-index consultation chunks.
- Process a manuscript into a local project under `projects/`.
- Ignore detected index files and embedded index sections when building the searchable manuscript corpus.
- Store detected index chunks separately for consultation.
- Build or rebuild a Chroma search index for uploaded projects.
- Retry the search-index build from the mode-selection screen if embedding fails after import.
- Ask source-cited questions against a project.
- Generate candidate index entries for a term.
- Search an existing index when one is present.
- Browse candidate index terms extracted from the manuscript.
