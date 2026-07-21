from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from importers import chapter_title_from_text
from perspectives import AnswerPerspective

from web_project import (
    BASE_DIR,
    answer_project_question,
    build_project,
    candidate_terms,
    embed_project,
    generate_index_entry,
    list_projects,
    load_manifest,
    load_project_chunks,
    search_existing_index,
    source_payload,
    source_dir,
)


FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

app = FastAPI(
    title="Archivist API",
    version="0.1.0",
    description="Local-first manuscript RAG and indexing API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1)
    n_results: int = Field(default=5, ge=1, le=12)
    perspective: AnswerPerspective = AnswerPerspective.NEUTRAL


class IndexEntryRequest(BaseModel):
    term: str = Field(min_length=1)
    consult_existing_index: bool = False


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects")
def projects() -> dict[str, object]:
    return {"projects": list_projects()}


@app.get("/api/projects/{project_id}")
def project(project_id: str) -> dict[str, object]:
    try:
        return {"project": load_manifest(project_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects")
async def create_project(
    project_name: Annotated[str, Form()],
    ignore_existing_index: Annotated[bool, Form()] = True,
    consult_existing_index: Annotated[bool, Form()] = False,
    files: Annotated[list[UploadFile], File()] = [],
) -> dict[str, object]:
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one manuscript file.")

    uploaded_files: list[tuple[str, bytes]] = []
    for upload in files:
        uploaded_files.append((upload.filename or "upload.md", await upload.read()))

    try:
        manifest = build_project(
            project_name=project_name,
            uploaded_files=uploaded_files,
            ignore_existing_index=ignore_existing_index,
            consult_existing_index=consult_existing_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"project": manifest}


@app.post("/api/projects/{project_id}/embed")
def embed(project_id: str) -> dict[str, object]:
    try:
        return {"project": embed_project(project_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {exc}") from exc


@app.post("/api/projects/{project_id}/question")
def question(project_id: str, request: QuestionRequest) -> dict[str, object]:
    try:
        answer, chunks = answer_project_question(
            project_id,
            request.question,
            n_results=request.n_results,
            perspective=request.perspective,
        )
        return {
            "answer": answer,
            "perspective": request.perspective.value,
            **source_payload(chunks),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Question failed: {exc}") from exc


@app.post("/api/projects/{project_id}/index/entry")
def index_entry(project_id: str, request: IndexEntryRequest) -> dict[str, object]:
    try:
        output, chunks, existing_index_chunks = generate_index_entry(
            project_id=project_id,
            term=request.term,
            consult_existing_index=request.consult_existing_index,
        )
        payload = source_payload(chunks)
        return {
            "entry": output,
            **payload,
            "existing_index_sources": source_payload(existing_index_chunks)["sources"],
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Index entry failed: {exc}") from exc


@app.get("/api/projects/{project_id}/index/search")
def existing_index_search(
    project_id: str,
    term: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> dict[str, object]:
    try:
        chunks = search_existing_index(project_id, term, limit=limit)
        return {"results": source_payload(chunks)["sources"]}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/index/candidates")
def index_candidates(
    project_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, object]:
    try:
        return {"terms": candidate_terms(project_id, limit=limit)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/sources")
def sources(
    project_id: str,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    search: Annotated[str | None, Query(max_length=200)] = None,
    document: Annotated[str | None, Query(max_length=300)] = None,
) -> dict[str, object]:
    chunks = load_project_chunks(project_id)
    reading_chunks: list[dict[str, object]] = []
    previous_document: str | None = None
    previous_end = 0
    current_chapter_title: str | None = None

    for chunk in chunks:
        reading_chunk = dict(chunk)
        document = str(chunk.get("document", ""))
        start = int(chunk.get("paragraph_start") or 1)
        end = int(chunk.get("paragraph_end") or start)

        if document != previous_document:
            current_chapter_title = str(chunk.get("chapter_title", "N/A"))
        detected_title = chapter_title_from_text(str(chunk.get("text", "")))
        if detected_title:
            current_chapter_title = detected_title
        reading_chunk["chapter_title"] = current_chapter_title or "N/A"

        if document == previous_document and start <= previous_end:
            overlap = previous_end - start + 1
            paragraphs = str(chunk.get("text", "")).split("\n\n")
            reading_chunk["text"] = "\n\n".join(paragraphs[overlap:])
            reading_chunk["paragraph_start"] = start + overlap

        if str(reading_chunk.get("text", "")).strip():
            reading_chunks.append(reading_chunk)

        previous_document = document
        previous_end = end

    documents = sorted({str(chunk.get("document", "N/A")) for chunk in reading_chunks})
    filtered_chunks = reading_chunks
    if document:
        filtered_chunks = [chunk for chunk in filtered_chunks if str(chunk.get("document", "")) == document]
    if search and search.strip():
        needle = search.strip().casefold()
        filtered_chunks = [
            chunk
            for chunk in filtered_chunks
            if needle in str(chunk.get("text", "")).casefold()
            or needle in str(chunk.get("chapter_title", "")).casefold()
        ]

    selected = filtered_chunks[offset:offset + limit]
    return {
        "total": len(filtered_chunks),
        "sources": source_payload(selected)["sources"],
        "documents": documents,
    }


@app.get("/api/projects/{project_id}/source-file/{file_path:path}")
def source_file(project_id: str, file_path: str) -> FileResponse:
    root = source_dir(project_id).resolve()
    requested = (root / file_path).resolve()
    try:
        requested.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid source file path.") from exc
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="Source file not found.")
    return FileResponse(requested, media_type="application/pdf" if requested.suffix.lower() == ".pdf" else None)


@app.get("/{full_path:path}")
def app_shell(full_path: str) -> FileResponse:
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-store, max-age=0",
                "Pragma": "no-cache",
            },
        )
    raise HTTPException(status_code=404, detail="Frontend has not been built yet.")
