from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
import httpx
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from corpus import get_neighbor_chunk_ids
from filters import should_skip_document
from importers import (
    SUPPORTED_DOCUMENT_SUFFIXES,
    build_chunks_for_imported_document,
    import_document,
    split_existing_index_section,
    chapter_title_from_text,
)
from ingest import clean_title_from_filename, extract_chapter_title
from retrieval import MAX_FINAL_SOURCES, MAX_PRIMARY_DISTANCE


BASE_DIR = Path(__file__).resolve().parent.parent
PROJECTS_DIR = BASE_DIR / "projects"
CHROMA_DIR = BASE_DIR / "chroma_db"
LEGACY_CHUNKS_FILE = BASE_DIR / "output" / "chunks.json"
LEGACY_MANUSCRIPT_DIR = BASE_DIR / "manuscript"
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-5"

load_dotenv(BASE_DIR / ".env")

SUPPORTED_UPLOAD_SUFFIXES = SUPPORTED_DOCUMENT_SUFFIXES | {".zip"}
INDEX_NAME_PATTERN = re.compile(r"(^|[_\-\s])index($|[_\-\s\.])", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "untitled"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / slugify(project_id)


def manifest_path(project_id: str) -> Path:
    return project_dir(project_id) / "manifest.json"


def chunks_path(project_id: str) -> Path:
    return project_dir(project_id) / "chunks.json"


def existing_index_path(project_id: str) -> Path:
    return project_dir(project_id) / "existing_index_chunks.json"


def source_dir(project_id: str) -> Path:
    return project_dir(project_id) / "source"


def collection_name(project_id: str) -> str:
    if project_id == "current":
        return "manuscript"
    return f"archivist_{slugify(project_id).replace('-', '_')}"


def load_manifest(project_id: str) -> dict[str, Any]:
    if project_id == "current":
        return current_project_manifest()
    manifest = read_json(manifest_path(project_id), None)
    if not manifest:
        raise FileNotFoundError(f"Project not found: {project_id}")
    return manifest


def save_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest["updated_at"] = utc_now()
    write_json(manifest_path(manifest["id"]), manifest)
    return manifest


def load_project_chunks(project_id: str) -> list[dict[str, Any]]:
    if project_id == "current":
        return read_json(LEGACY_CHUNKS_FILE, [])
    return read_json(chunks_path(project_id), [])


def load_existing_index_chunks(project_id: str) -> list[dict[str, Any]]:
    return read_json(existing_index_path(project_id), [])


def build_chunk_lookup(chunks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(chunk.get("chunk_id")): chunk for chunk in chunks if chunk.get("chunk_id")}


def current_project_manifest() -> dict[str, Any]:
    chunks = read_json(LEGACY_CHUNKS_FILE, [])
    filtered_chunks = [chunk for chunk in chunks if not should_skip_document(chunk.get("document", ""))]
    index_chunks = [chunk for chunk in chunks if is_index_document_name(chunk.get("document", ""))]
    return {
        "id": "current",
        "name": "Current manuscript",
        "created_at": "",
        "updated_at": "",
        "settings": {
            "ignore_existing_index": True,
            "consult_existing_index": False,
        },
        "source_files": [path.name for path in sorted(LEGACY_MANUSCRIPT_DIR.glob("*.md"))],
        "ignored_documents": sorted({chunk.get("document", "") for chunk in chunks if should_skip_document(chunk.get("document", ""))}),
        "existing_index_documents": sorted({chunk.get("document", "") for chunk in index_chunks}),
        "stats": {
            "source_files": len(list(LEGACY_MANUSCRIPT_DIR.glob("*.md"))),
            "chunks": len(chunks),
            "searchable_chunks": len(filtered_chunks),
            "existing_index_chunks": len(index_chunks),
        },
        "embedded": chroma_collection_count("current") > 0,
        "embedded_chunks": chroma_collection_count("current"),
        "is_builtin": True,
    }


def list_projects() -> list[dict[str, Any]]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    projects = [current_project_manifest()]
    for path in sorted(PROJECTS_DIR.glob("*/manifest.json")):
        try:
            projects.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return projects


def is_index_document_name(name: str) -> bool:
    return bool(INDEX_NAME_PATTERN.search(Path(name).name))


def is_index_document(path: Path, text: str) -> bool:
    if is_index_document_name(path.name):
        return True
    title = extract_chapter_title(text, fallback=clean_title_from_filename(path.stem)).strip().lower()
    return title in {"index", "index of names", "general index"}


def copy_upload_to_source(project_id: str, filename: str, content: bytes) -> list[str]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
        raise ValueError(f"Unsupported file type: {filename}")

    root = source_dir(project_id)
    root.mkdir(parents=True, exist_ok=True)
    stored_files: list[str] = []

    if suffix == ".zip":
        archive_path = root / safe_filename(filename)
        archive_path.write_bytes(content)
        extract_root = root / archive_path.stem
        extract_root.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                member_name = Path(member.filename)
                if member_name.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
                    continue
                destination = (extract_root / safe_filename(member_name.name)).resolve()
                if not str(destination).startswith(str(extract_root.resolve())):
                    continue
                with archive.open(member) as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                stored_files.append(str(destination.relative_to(root)))
        return stored_files

    destination = root / safe_filename(filename)
    destination.write_bytes(content)
    stored_files.append(destination.name)
    return stored_files


def safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    cleaned = re.sub(r"[^a-zA-Z0-9._() \-]+", "_", name)
    return cleaned or "upload.md"


def build_project(
    project_name: str,
    uploaded_files: list[tuple[str, bytes]],
    ignore_existing_index: bool,
    consult_existing_index: bool,
) -> dict[str, Any]:
    project_id = unique_project_id(project_name)
    root = project_dir(project_id)
    root.mkdir(parents=True, exist_ok=False)

    stored_files: list[str] = []
    for filename, content in uploaded_files:
        stored_files.extend(copy_upload_to_source(project_id, filename, content))

    chunks: list[dict[str, Any]] = []
    existing_index_chunks: list[dict[str, Any]] = []
    ignored_documents: set[str] = set()
    index_documents: set[str] = set()

    for file_path in sorted(source_dir(project_id).rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
            continue
        imported_document = import_document(file_path)
        manuscript_document, embedded_index_document = split_existing_index_section(imported_document)
        index_doc = is_index_document(file_path, imported_document.text)
        skip_doc = should_skip_document(file_path.name)
        embedded_index_chunks: list[dict[str, object]] = []

        if index_doc:
            index_documents.add(file_path.name)
            existing_index_chunks.extend(build_chunks_for_imported_document(imported_document))
            if ignore_existing_index:
                ignored_documents.add(file_path.name)
                continue

        if embedded_index_document:
            index_documents.add(embedded_index_document.document_name)
            embedded_index_chunks = build_chunks_for_imported_document(embedded_index_document)
            existing_index_chunks.extend(embedded_index_chunks)

        if skip_doc:
            ignored_documents.add(file_path.name)
            continue

        if manuscript_document:
            chunks.extend(build_chunks_for_imported_document(manuscript_document))

        if embedded_index_document:
            if ignore_existing_index:
                ignored_documents.add(embedded_index_document.document_name)
            else:
                chunks.extend(embedded_index_chunks)

    write_json(chunks_path(project_id), chunks)
    write_json(existing_index_path(project_id), existing_index_chunks)

    manifest = {
        "id": project_id,
        "name": project_name.strip() or project_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "settings": {
            "ignore_existing_index": bool(ignore_existing_index),
            "consult_existing_index": bool(consult_existing_index),
        },
        "source_files": stored_files,
        "ignored_documents": sorted(ignored_documents),
        "existing_index_documents": sorted(index_documents),
        "stats": {
            "source_files": len(stored_files),
            "chunks": len(chunks) + len(existing_index_chunks),
            "searchable_chunks": len(chunks),
            "existing_index_chunks": len(existing_index_chunks),
        },
        "embedded": False,
        "embedded_chunks": 0,
        "is_builtin": False,
    }
    return save_manifest(manifest)


def unique_project_id(project_name: str) -> str:
    base = slugify(project_name) or "project"
    candidate = base
    counter = 2
    while project_dir(candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    if should_trust_environment_proxy():
        return OpenAI(api_key=api_key)
    return OpenAI(api_key=api_key, http_client=httpx.Client(trust_env=False))


def should_trust_environment_proxy() -> bool:
    return os.getenv("ARCHIVIST_TRUST_ENV_PROXY", "").strip().lower() in {"1", "true", "yes", "on"}


def friendly_openai_error(exc: OpenAIError) -> str:
    error_name = exc.__class__.__name__
    if error_name in {"APIConnectionError", "APITimeoutError"}:
        return (
            "Could not reach OpenAI while building embeddings. "
            "Check your internet connection, VPN/firewall, and API access, then retry the search index build."
        )
    if error_name == "AuthenticationError":
        return "OpenAI authentication failed. Check OPENAI_API_KEY in the Archivist .env file."
    if error_name == "RateLimitError":
        return "OpenAI rate limit or quota was reached. Wait a bit or check project billing, then retry."
    return f"OpenAI request failed: {exc}"


def chroma_client() -> chromadb.PersistentClient:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def chroma_collection_count(project_id: str) -> int:
    try:
        collection = chroma_client().get_collection(name=collection_name(project_id))
        return int(collection.count())
    except Exception:
        return 0


def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    try:
        response = client.embeddings.create(model=EMBED_MODEL, input=texts)
        return [item.embedding for item in response.data]
    except OpenAIError as exc:
        raise RuntimeError(friendly_openai_error(exc)) from exc


def embed_project(project_id: str) -> dict[str, Any]:
    manifest = load_manifest(project_id)
    chunks = [chunk for chunk in load_project_chunks(project_id) if not should_skip_document(chunk.get("document", ""))]
    if not chunks:
        raise RuntimeError("This project has no searchable chunks.")

    client = openai_client()
    store = chroma_client()
    name = collection_name(project_id)
    if project_id != "current":
        try:
            store.delete_collection(name=name)
        except Exception:
            pass
    collection = store.get_or_create_collection(name=name)

    batch_size = 50
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        texts = [chunk["text"] for chunk in batch]
        ids = [chunk["chunk_id"] for chunk in batch]
        embeddings = embed_texts(client, texts)
        collection.upsert(ids=ids, embeddings=embeddings, metadatas=batch)

    manifest["embedded"] = True
    manifest["embedded_chunks"] = len(chunks)
    return save_manifest(manifest)


def retrieve_project(project_id: str, query: str, n_results: int = 5) -> dict[str, Any]:
    collection = chroma_client().get_collection(name=collection_name(project_id))
    embedding = embed_texts(openai_client(), [query])[0]
    return collection.query(
        query_embeddings=[embedding],
        n_results=n_results,
        include=["metadatas", "distances"],
    )


def get_filtered_primary_chunks(results: dict[str, Any], max_distance: float = MAX_PRIMARY_DISTANCE) -> list[dict[str, Any]]:
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    primary_chunks = []
    for meta, distance in zip(metadatas, distances):
        if should_skip_document(meta.get("document", "")):
            continue
        if distance <= max_distance:
            primary_chunks.append(meta)
    if not primary_chunks:
        primary_chunks = [meta for meta in metadatas if not should_skip_document(meta.get("document", ""))]
    return primary_chunks


def expand_with_neighbors(primary_chunks: list[dict[str, Any]], lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    seen: set[str] = set()
    for meta in primary_chunks:
        chunk_id = meta.get("chunk_id")
        if not chunk_id:
            continue
        neighbor_ids = get_neighbor_chunk_ids(chunk_id)
        prev_id = neighbor_ids[0] if len(neighbor_ids) == 2 else None
        next_id = neighbor_ids[-1] if neighbor_ids else None
        ordered_ids = []
        if prev_id:
            ordered_ids.append(prev_id)
        ordered_ids.append(chunk_id)
        if next_id and next_id != prev_id:
            ordered_ids.append(next_id)
        for cid in ordered_ids:
            chunk = lookup.get(cid)
            if not chunk or should_skip_document(chunk.get("document", "")) or cid in seen:
                continue
            expanded.append(chunk)
            seen.add(cid)
    return expanded


def finalize_question_context(project_id: str, results: dict[str, Any], max_final_sources: int = MAX_FINAL_SOURCES) -> list[dict[str, Any]]:
    lookup = build_chunk_lookup(annotate_chapter_titles(load_project_chunks(project_id)))
    primary = [lookup.get(str(chunk.get("chunk_id")), chunk) for chunk in get_filtered_primary_chunks(results)]
    return expand_with_neighbors(primary, lookup)[:max_final_sources]


def annotate_chapter_titles(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    current_document: str | None = None
    current_title: str | None = None
    for chunk in chunks:
        item = dict(chunk)
        document = str(item.get("document", ""))
        if document != current_document:
            current_document = document
            current_title = str(item.get("chapter_title") or "")
        detected = chapter_title_from_text(str(item.get("text", "")))
        if detected:
            current_title = detected
        item["chapter_title"] = current_title or item.get("chapter_title", "N/A")
        annotated.append(item)
    return annotated


def build_context(chunks: list[dict[str, Any]], label: str = "Source") -> str:
    blocks = []
    for chunk in chunks:
        citation = citation_label(chunk)
        blocks.append(
            f"[{citation if label == 'Source' else f'{label}: {citation}'}]\n"
            f"Document: {chunk.get('document', 'N/A')}\n"
            f"Chapter: {chunk.get('chapter_title', 'N/A')}\n"
            f"Chunk ID: {chunk.get('chunk_id', 'N/A')}\n"
            f"Paragraphs: {chunk.get('paragraph_start', '?')}-{chunk.get('paragraph_end', '?')}\n"
            f"Text:\n{chunk.get('text', '')}\n"
        )
    return "\n\n".join(blocks)


def citation_label(chunk: dict[str, Any]) -> str:
    chapter = str(chunk.get("chapter_title") or "").strip()
    if not chapter or chapter == "N/A" or re.fullmatch(r"page\s+\d+", chapter, flags=re.IGNORECASE):
        chapter = Path(str(chunk.get("document") or "Manuscript")).stem
    if len(chapter) > 90:
        chapter = chapter[:87].rstrip() + "..."
    start = chunk.get("paragraph_start", "?")
    end = chunk.get("paragraph_end", "?")
    paragraph_label = f"¶{start}" if start == end else f"¶{start}–{end}"
    return f"{chapter}, {paragraph_label}"


def merge_adjacent_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge selected neighboring chunks after retrieval without changing stored RAG chunks."""
    if not chunks:
        return []

    ranked = list(enumerate(chunks))
    ranked.sort(key=lambda item: (
        str(item[1].get("document", "")),
        int(item[1].get("paragraph_start") or 0),
        item[0],
    ))
    merged: list[dict[str, Any]] = []

    for _, chunk in ranked:
        current = dict(chunk)
        current["chunk_ids"] = list(chunk.get("chunk_ids") or [str(chunk.get("chunk_id", "N/A"))])
        if not merged:
            merged.append(current)
            continue

        previous = merged[-1]
        same_document = previous.get("document") == current.get("document")
        same_chapter = previous.get("chapter_title") == current.get("chapter_title")
        previous_end = int(previous.get("paragraph_end") or 0)
        current_start = int(current.get("paragraph_start") or 0)
        neighboring = current_start <= previous_end + 1

        if not same_document or not same_chapter or not neighboring:
            merged.append(current)
            continue

        overlap = max(0, previous_end - current_start + 1)
        current_paragraphs = str(current.get("text", "")).split("\n\n")
        new_text = "\n\n".join(current_paragraphs[overlap:]).strip()
        if new_text:
            previous["text"] = f"{str(previous.get('text', '')).rstrip()}\n\n{new_text}"
        previous["paragraph_end"] = max(previous_end, int(current.get("paragraph_end") or previous_end))
        previous["chunk_ids"] = [*previous["chunk_ids"], *current["chunk_ids"]]
    return merged


def answer_project_question(project_id: str, question: str, n_results: int = 5) -> tuple[str, list[dict[str, Any]]]:
    results = retrieve_project(project_id, question, n_results=n_results)
    final_chunks = merge_adjacent_chunks(finalize_question_context(project_id, results))
    context = build_context(final_chunks)
    prompt = f"""You are a historian specializing in the development of the American imperial system through Virginia.

Answer the user's question using only the provided sources.

Cite sources inline after specific claims using the exact bracketed citation labels supplied below.
Do not group multiple sources only at the end of a paragraph.
Each important factual claim should have its own citation.
If the sources do not contain enough information, say so.

Answer in 1-3 short paragraphs or structured bullet points when appropriate.

Question:
{question}

Sources:
{context}
"""
    response = openai_client().responses.create(model=CHAT_MODEL, input=prompt)
    return response.output_text, final_chunks


def find_exact_match_chunks(term: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    term_lower = term.lower().strip()
    if not term_lower:
        return []
    return [
        chunk for chunk in chunks
        if not should_skip_document(chunk.get("document", ""))
        and term_lower in chunk.get("text", "").lower()
    ]


def finalize_index_context(project_id: str, term: str, semantic_results: dict[str, Any], max_final_sources: int = MAX_FINAL_SOURCES) -> list[dict[str, Any]]:
    chunks = annotate_chapter_titles(load_project_chunks(project_id))
    lookup = build_chunk_lookup(chunks)
    exact_matches = find_exact_match_chunks(term, chunks)
    seen: set[str] = set()
    final_chunks: list[dict[str, Any]] = []

    for chunk in exact_matches:
        cid = chunk["chunk_id"]
        if cid not in seen:
            final_chunks.append(chunk)
            seen.add(cid)

    for chunk in exact_matches:
        for neighbor_id in get_neighbor_chunk_ids(chunk["chunk_id"]):
            neighbor = lookup.get(neighbor_id)
            if neighbor and neighbor["chunk_id"] not in seen and not should_skip_document(neighbor.get("document", "")):
                final_chunks.append(neighbor)
                seen.add(neighbor["chunk_id"])

    semantic_primary = [
        lookup.get(str(chunk.get("chunk_id")), chunk)
        for chunk in get_filtered_primary_chunks(semantic_results)
    ]
    for chunk in expand_with_neighbors(semantic_primary, lookup):
        cid = chunk["chunk_id"]
        if cid not in seen:
            final_chunks.append(chunk)
            seen.add(cid)

    return final_chunks[:max_final_sources]


def search_existing_index(project_id: str, term: str, limit: int = 8) -> list[dict[str, Any]]:
    index_chunks = load_existing_index_chunks(project_id)
    matches = find_exact_match_chunks(term, index_chunks)
    return matches[:limit]


def generate_index_entry(project_id: str, term: str, consult_existing_index: bool) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    semantic_results = retrieve_project(project_id, term, n_results=5)
    final_chunks = merge_adjacent_chunks(finalize_index_context(project_id, term, semantic_results))
    existing_index_chunks = merge_adjacent_chunks(search_existing_index(project_id, term)) if consult_existing_index else []
    context = build_context(final_chunks)
    existing_context = build_context(existing_index_chunks, label="Existing Index") if existing_index_chunks else "No existing index context supplied."

    prompt = f"""You are helping build a back-of-the-book index for a historical manuscript.

Using only the provided manuscript sources, produce a candidate index entry for the term below.

Term:
{term}

Instructions:
- Write a 2-4 sentence summary of how this term is used in the manuscript.
- Then list the strongest candidate locations.
- Then suggest 0-5 possible subentries if they are clearly supported by the sources.
- Be cautious: if the term is only mentioned briefly or weakly, say so.
- Do not invent page numbers.
- Use the exact bracketed human-readable citation labels supplied below when making claims.
- If existing index context is supplied, use it only as a comparison reference. Do not copy it blindly.

Format exactly like this:

Index term: <term>

Summary:
<summary>

Key locations:
- [<citation label>] <brief note>

Suggested subentries:
- <subentry>

Existing index context:
{existing_context}

Manuscript sources:
{context}
"""
    response = openai_client().responses.create(model=CHAT_MODEL, input=prompt)
    return response.output_text, final_chunks, existing_index_chunks


def candidate_terms(project_id: str, limit: int = 50) -> list[dict[str, Any]]:
    chunks = load_project_chunks(project_id)
    counter: Counter[str] = Counter()
    stop = {
        "The", "A", "An", "And", "But", "For", "This", "That", "These", "Those",
        "In", "On", "At", "By", "From", "As", "It", "Its", "They", "Their",
        "Chapter", "Appendix", "Introduction",
    }
    phrase_pattern = re.compile(r"\b([A-Z][A-Za-z]+(?:\s+(?:of|the|and|de|du|[A-Z][A-Za-z]+)){0,4})\b")
    for chunk in chunks:
        if should_skip_document(chunk.get("document", "")):
            continue
        for match in phrase_pattern.finditer(chunk.get("text", "")):
            phrase = re.sub(r"\s+", " ", match.group(1)).strip()
            first = phrase.split()[0]
            if first in stop or len(phrase) < 4:
                continue
            counter[phrase] += 1
    return [{"term": term, "count": count} for term, count in counter.most_common(limit)]


def source_payload(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = []
    for i, chunk in enumerate(chunks, start=1):
        payload.append({
            "source_number": i,
            "citation_label": citation_label(chunk),
            "document": chunk.get("document", "N/A"),
            "chapter_title": chunk.get("chapter_title", "N/A"),
            "chunk_id": chunk.get("chunk_id", "N/A"),
            "chunk_ids": chunk.get("chunk_ids") or [chunk.get("chunk_id", "N/A")],
            "paragraph_start": chunk.get("paragraph_start"),
            "paragraph_end": chunk.get("paragraph_end"),
            "text": chunk.get("text", ""),
        })
    return payload
