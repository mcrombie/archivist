from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from ingest import clean_title_from_filename, chunk_paragraphs, extract_chapter_title, split_into_paragraphs


SUPPORTED_DOCUMENT_SUFFIXES = {".md", ".txt", ".docx", ".pdf"}
INDEX_SECTION_TITLES = {"index", "general index", "index of names"}


@dataclass(frozen=True)
class ImportedDocument:
    source_path: Path
    document_name: str
    chapter_title: str
    text: str


def import_document(path: Path) -> ImportedDocument:
    suffix = path.suffix.lower()

    if suffix == ".md":
        text = read_text_file(path)
        return ImportedDocument(
            source_path=path,
            document_name=path.name,
            chapter_title=extract_chapter_title(text, fallback=clean_title_from_filename(path.stem)),
            text=text,
        )

    if suffix == ".txt":
        text = read_text_file(path)
        return ImportedDocument(
            source_path=path,
            document_name=path.name,
            chapter_title=first_meaningful_line(text) or clean_title_from_filename(path.stem),
            text=text,
        )

    if suffix == ".docx":
        text = extract_docx_text(path)
        return ImportedDocument(
            source_path=path,
            document_name=path.name,
            chapter_title=first_meaningful_line(text) or clean_title_from_filename(path.stem),
            text=text,
        )

    if suffix == ".pdf":
        text = extract_pdf_text(path)
        return ImportedDocument(
            source_path=path,
            document_name=path.name,
            chapter_title=first_meaningful_line(text, ignore_page_markers=True) or clean_title_from_filename(path.stem),
            text=text,
        )

    raise ValueError(f"Unsupported document type: {path.name}")


def build_chunks_for_imported_document(document: ImportedDocument) -> list[dict[str, object]]:
    paragraphs = split_into_paragraphs(document.text)
    paragraph_chunks = chunk_paragraphs(paragraphs, chunk_size=4, overlap=1)
    safe_stem = safe_chunk_stem(document.source_path.stem)

    records: list[dict[str, object]] = []
    current_chapter_title = document.chapter_title
    for index, chunk in enumerate(paragraph_chunks, start=1):
        detected_title = chapter_title_from_text(str(chunk["text"]))
        if detected_title:
            current_chapter_title = detected_title
        records.append({
            "document": document.document_name,
            "chapter_title": current_chapter_title,
            "chunk_id": f"{safe_stem}_{index:03}",
            "paragraph_start": chunk["paragraph_start"],
            "paragraph_end": chunk["paragraph_end"],
            "text": chunk["text"],
        })

    return records


def chapter_title_from_text(text: str) -> str | None:
    """Return a chapter heading at the start of a passage, excluding its opening prose."""
    detected: str | None = None
    for paragraph in text.strip().split("\n\n"):
        paragraph = paragraph.strip()
        heading_match = re.match(r"^(chapter\s+(?:\d+|[ivxlcdm]+))\b", paragraph, flags=re.IGNORECASE)
        if not heading_match:
            continue

        title_parts = re.split(r"[\"\u201c\u201d]", paragraph, maxsplit=1)
        if len(title_parts) > 1:
            title = title_parts[0].strip().rstrip(" :-\u2013\u2014")
            if len(title) <= 160:
                detected = title
                continue

        # Some PDFs concatenate an unquoted chapter heading and its first prose
        # sentence. Preserve the reliable chapter number rather than prose.
        detected = heading_match.group(1)
    return detected


def split_existing_index_section(document: ImportedDocument) -> tuple[ImportedDocument | None, ImportedDocument | None]:
    paragraphs = split_into_paragraphs(document.text)
    index_start = find_index_section_start(paragraphs)

    if index_start is None:
        return document, None

    manuscript_paragraphs = paragraphs[:index_start]
    index_paragraphs = paragraphs[index_start:]

    if not manuscript_paragraphs:
        return None, document

    manuscript_document = ImportedDocument(
        source_path=document.source_path,
        document_name=document.document_name,
        chapter_title=document.chapter_title,
        text="\n\n".join(manuscript_paragraphs),
    )
    index_document = ImportedDocument(
        source_path=document.source_path,
        document_name=f"{document.source_path.stem} Existing Index{document.source_path.suffix}",
        chapter_title="Existing Index",
        text="\n\n".join(index_paragraphs),
    )
    return manuscript_document, index_document


def find_index_section_start(paragraphs: list[str]) -> int | None:
    if not paragraphs:
        return None

    earliest_allowed = max(0, int(len(paragraphs) * 0.55))
    for index, paragraph in enumerate(paragraphs):
        normalized = normalize_heading(paragraph)
        if normalized in INDEX_SECTION_TITLES and index >= earliest_allowed:
            return index

    return None


def read_text_file(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        try:
            document_xml = archive.read("word/document.xml")
        except KeyError as exc:
            raise ValueError(f"{path.name} is not a readable .docx file.") from exc

    root = ElementTree.fromstring(document_xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    body = root.find("w:body", namespace)
    if body is None:
        return ""

    blocks: list[str] = []
    for child in body:
        tag = strip_namespace(child.tag)
        if tag == "p":
            paragraph = paragraph_text(child, namespace)
            if paragraph:
                blocks.append(paragraph)
        elif tag == "tbl":
            table_lines = table_text(child, namespace)
            if table_lines:
                blocks.append("\n".join(table_lines))

    return "\n\n".join(blocks)


def paragraph_text(paragraph: ElementTree.Element, namespace: dict[str, str]) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        tag = strip_namespace(node.tag)
        if tag == "t" and node.text:
            parts.append(node.text)
        elif tag == "tab":
            parts.append("\t")
        elif tag in {"br", "cr"}:
            parts.append("\n")

    return normalize_inline_text("".join(parts))


def table_text(table: ElementTree.Element, namespace: dict[str, str]) -> list[str]:
    rows: list[str] = []
    for row in table.findall(".//w:tr", namespace):
        cells: list[str] = []
        for cell in row.findall("./w:tc", namespace):
            paragraphs = [
                paragraph_text(paragraph, namespace)
                for paragraph in cell.findall(".//w:p", namespace)
            ]
            cell_text = " ".join(paragraph for paragraph in paragraphs if paragraph)
            if cell_text:
                cells.append(cell_text)
        if cells:
            rows.append(" | ".join(cells))
    return rows


def extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF import requires pypdf. Install it with requirements-web.txt.") from exc

    reader = PdfReader(str(path))
    pages: list[str] = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = normalize_pdf_text(text)
        if text:
            pages.append(f"Page {page_number}\n\n{text}")

    if not pages:
        raise ValueError(f"No selectable text could be extracted from {path.name}.")

    return "\n\n".join(pages)


def normalize_pdf_text(text: str) -> str:
    lines = [normalize_inline_text(line) for line in text.replace("\r", "\n").split("\n")]
    paragraphs: list[str] = []
    current: list[str] = []

    for line in lines:
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue

        current.append(line)

    if current:
        paragraphs.append(" ".join(current))

    return "\n\n".join(paragraphs)


def normalize_inline_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def first_meaningful_line(text: str, ignore_page_markers: bool = False) -> str:
    for line in text.splitlines():
        cleaned = line.strip().strip("#").strip()
        if ignore_page_markers and re.fullmatch(r"page\s+\d+", cleaned, flags=re.IGNORECASE):
            continue
        if cleaned:
            return cleaned[:120]
    return ""


def normalize_heading(text: str) -> str:
    cleaned = re.sub(r"^[#\s]+", "", text.strip())
    cleaned = cleaned.rstrip(" :-.\u2013\u2014").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.lower()


def safe_chunk_stem(stem: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._() \-]+", "_", stem).strip()
    return cleaned or "document"


def strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def supported_suffixes_for_display() -> str:
    return ", ".join(sorted(SUPPORTED_DOCUMENT_SUFFIXES | {".zip"}))
