from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from xml.etree import ElementTree

from filters import SKIP_FILES, should_skip_document
from ingest import (
    PARAGRAPH_OVERLAP,
    PARAGRAPHS_PER_CHUNK,
    chunk_paragraphs,
    clean_title_from_filename,
    extract_chapter_title,
    split_into_paragraphs,
)


WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WORD_2010_NAMESPACE = "http://schemas.microsoft.com/office/word/2010/wordml"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"

DOCUMENT_XML = "word/document.xml"
ENDNOTES_XML = "word/endnotes.xml"
FOOTNOTES_XML = "word/footnotes.xml"
STYLES_XML = "word/styles.xml"

MANIFEST_SCHEMA = "archivist.corpus_manifest/1"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_COLLECTION_NAME = "manuscript"
DEFAULT_HNSW_SPACE = "l2"

_END_MATTER_TITLES = {
    "bibliography",
    "general index",
    "illustration credits",
    "index",
    "index of names",
    "works cited",
    "works consulted",
}
_END_MATTER_SKIP_SUFFIX = "__32_Bibliography.md"
_TRACKED_CHANGE_NAMES = {
    "del",
    "ins",
    "moveFrom",
    "moveFromRangeEnd",
    "moveFromRangeStart",
    "moveTo",
    "moveToRangeEnd",
    "moveToRangeStart",
}
_INLINE_IGNORED_SUBTREES = {
    "del",
    "delText",
    "instrText",
    "moveFrom",
    "footnoteRef",
}
_IMAGE_NAMES = {"drawing", "object", "pict"}
_WINDOWS_RESERVED_STEMS = {
    "aux",
    "clock$",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "con",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
    "nul",
    "prn",
}


class ManuscriptPreparationError(ValueError):
    """Raised when a source cannot be converted without losing provenance."""


@dataclass(frozen=True)
class ParagraphBlock:
    """One visible Word paragraph and the style information needed for splitting."""

    text: str
    style_id: str | None
    style_name: str | None
    heading_level: int | None
    is_toc_heading: bool
    image_only: bool


@dataclass(frozen=True)
class DocxExtraction:
    """Deterministic, presentation-neutral content extracted from a DOCX."""

    paragraphs: tuple[ParagraphBlock, ...]
    suggested_title: str
    stats: Mapping[str, int]


@dataclass(frozen=True)
class MarkdownDocument:
    """A generated Markdown source document."""

    filename: str
    chapter_title: str
    markdown: str


@dataclass(frozen=True)
class PreparedCorpus:
    """Paths and metadata produced by a successful preparation."""

    manuscript_dir: Path
    chunks_path: Path
    manifest_path: Path
    document_count: int
    chunk_count: int
    manifest: Mapping[str, Any]


@dataclass(frozen=True)
class _Style:
    name: str
    based_on: str | None


class _ExtractionCounters:
    def __init__(self) -> None:
        self.body_paragraph_count = 0
        self.emitted_paragraph_count = 0
        self.heading_1_count = 0
        self.toc_heading_count = 0
        self.footnote_reference_count = 0
        self.resolved_footnote_reference_count = 0
        self.footnote_definition_count = 0
        self.image_only_paragraph_count = 0
        self.image_count = 0
        self.tab_count = 0
        self.break_count = 0
        self.field_count = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "body_paragraph_count": self.body_paragraph_count,
            "emitted_paragraph_count": self.emitted_paragraph_count,
            "heading_1_count": self.heading_1_count,
            "toc_heading_count": self.toc_heading_count,
            "footnote_definition_count": self.footnote_definition_count,
            "footnote_reference_count": self.footnote_reference_count,
            "resolved_footnote_reference_count": self.resolved_footnote_reference_count,
            "image_count": self.image_count,
            "image_only_paragraph_count": self.image_only_paragraph_count,
            "tab_count": self.tab_count,
            "break_count": self.break_count,
            "field_count": self.field_count,
        }


def extract_docx(source_docx: Path) -> DocxExtraction:
    """Extract styled paragraphs, images, and inline footnotes from a DOCX."""

    source_docx = Path(source_docx)
    if source_docx.suffix.casefold() != ".docx":
        raise ManuscriptPreparationError(f"Expected a .docx source, got {source_docx.name!r}.")
    if not source_docx.is_file():
        raise ManuscriptPreparationError(f"DOCX source does not exist: {source_docx}")

    counters = _ExtractionCounters()
    try:
        with zipfile.ZipFile(source_docx) as archive:
            _validate_archive_member_names(archive)
            _validate_no_revisions_or_comments(archive)
            document_root = _read_xml_part(archive, DOCUMENT_XML, required=True)
            styles = _read_styles(archive)
            _validate_no_real_endnotes(archive)
            footnotes = _read_footnotes(archive, counters)
    except zipfile.BadZipFile as exc:
        raise ManuscriptPreparationError(
            f"{source_docx.name} is not a readable DOCX archive."
        ) from exc

    body = document_root.find(_word_tag("body"))
    if body is None:
        raise ManuscriptPreparationError("word/document.xml does not contain a Word body.")

    paragraphs: list[ParagraphBlock] = []
    seen_paragraph_ids: set[str] = set()
    suggested_title = ""

    for paragraph in _iter_body_paragraphs(body):
        counters.body_paragraph_count += 1
        paragraph_id = paragraph.get(f"{{{WORD_2010_NAMESPACE}}}paraId")
        if paragraph_id:
            normalized_id = paragraph_id.casefold()
            if normalized_id in seen_paragraph_ids:
                raise ManuscriptPreparationError(
                    f"Duplicate Word paragraph ID {paragraph_id!r}."
                )
            seen_paragraph_ids.add(normalized_id)

        style_id = _paragraph_style_id(paragraph)
        style_name = styles.get(style_id, _Style(style_id or "", None)).name or None
        style_chain = _style_chain(style_id, styles)
        heading_level = _heading_level(style_chain)
        is_toc_heading = _is_toc_heading(style_chain)
        text, image_only = _render_body_paragraph(paragraph, footnotes, counters)

        if not text and not image_only:
            continue
        if is_toc_heading:
            text = normalize_heading(text)
            if not text:
                raise ManuscriptPreparationError("A TOC Heading paragraph has no visible text.")
            counters.toc_heading_count += 1
        elif heading_level == 1:
            text = normalize_heading(text)
            if not text:
                raise ManuscriptPreparationError("A Heading 1 paragraph has no visible text.")
            counters.heading_1_count += 1

        if not suggested_title and _style_has_name(style_chain, "title") and text:
            suggested_title = normalize_heading(text)

        paragraphs.append(
            ParagraphBlock(
                text=text,
                style_id=style_id,
                style_name=style_name,
                heading_level=heading_level,
                is_toc_heading=is_toc_heading,
                image_only=image_only,
            )
        )
        counters.emitted_paragraph_count += 1
        if image_only:
            counters.image_only_paragraph_count += 1

    if counters.heading_1_count == 0:
        raise ManuscriptPreparationError("The DOCX has no Word Heading 1 sections.")
    if counters.toc_heading_count == 0:
        raise ManuscriptPreparationError("The DOCX has no Word TOC Heading section.")
    if counters.toc_heading_count > 1:
        raise ManuscriptPreparationError("The DOCX contains duplicate TOC Heading sections.")
    if counters.resolved_footnote_reference_count != counters.footnote_reference_count:
        raise ManuscriptPreparationError("Not every real footnote reference was resolved.")

    if not suggested_title:
        suggested_title = normalize_heading(clean_title_from_filename(source_docx.stem))

    return DocxExtraction(
        paragraphs=tuple(paragraphs),
        suggested_title=suggested_title or "Manuscript",
        stats=counters.as_dict(),
    )


def build_markdown_documents(
    extraction: DocxExtraction,
    *,
    title: str | None = None,
) -> list[MarkdownDocument]:
    """Split an extraction into front matter, TOC, and one file per Heading 1."""

    corpus_title = normalize_heading(title) if title is not None else extraction.suggested_title
    if not corpus_title:
        raise ManuscriptPreparationError("The title override must contain visible text.")

    front_content: list[str] = []
    toc_content: list[str] = []
    toc_heading = "Table of Contents"
    sections: list[tuple[str, list[str]]] = []
    current_content = front_content
    toc_seen = False

    for block in extraction.paragraphs:
        if block.is_toc_heading:
            toc_seen = True
            toc_heading = block.text
            current_content = toc_content
            continue

        if block.heading_level == 1:
            section = (block.text, [])
            sections.append(section)
            current_content = section[1]
            continue

        rendered = _markdown_block(block)
        if rendered:
            current_content.append(rendered)

    documents = [
        MarkdownDocument(
            filename="01_Front Matter.md",
            chapter_title=corpus_title,
            markdown=_render_markdown_document(corpus_title, front_content),
        ),
        MarkdownDocument(
            filename="02_Table of Contents.md",
            chapter_title=toc_heading,
            markdown=_render_markdown_document(toc_heading, toc_content),
        ),
    ]

    seen_filenames = {document.filename.casefold() for document in documents}
    structural_end_matter = False
    for ordinal, (heading, content) in enumerate(sections, start=3):
        normalized_section = _normalized_section_title(heading)
        if normalized_section in {"bibliography", "works cited", "works consulted"}:
            structural_end_matter = True
        filename = _section_filename(
            ordinal,
            heading,
            force_skip=structural_end_matter,
        )
        if filename.casefold() in seen_filenames:
            raise ManuscriptPreparationError(f"Duplicate generated document ID {filename!r}.")
        seen_filenames.add(filename.casefold())
        documents.append(
            MarkdownDocument(
                filename=filename,
                chapter_title=heading,
                markdown=_render_markdown_document(heading, content),
            )
        )

    if not toc_seen:
        raise ManuscriptPreparationError("The extraction has no Word TOC Heading section.")
    if not toc_content:
        raise ManuscriptPreparationError("The Word TOC Heading section has no visible entries.")

    return documents


def build_chunks(documents: Sequence[MarkdownDocument]) -> list[dict[str, object]]:
    """Build the legacy six-field chunk records without writing manuscript text first."""

    chunks: list[dict[str, object]] = []
    seen_chunk_ids: set[str] = set()

    for document in sorted(documents, key=lambda item: item.filename):
        chapter_title = extract_chapter_title(
            document.markdown,
            fallback=clean_title_from_filename(Path(document.filename).stem),
        )
        paragraphs = split_into_paragraphs(document.markdown)
        paragraph_chunks = chunk_paragraphs(
            paragraphs,
            chunk_size=PARAGRAPHS_PER_CHUNK,
            overlap=PARAGRAPH_OVERLAP,
        )
        stem = Path(document.filename).stem

        for index, chunk in enumerate(paragraph_chunks, start=1):
            chunk_id = f"{stem}_{index:03}"
            if chunk_id in seen_chunk_ids:
                raise ManuscriptPreparationError(f"Duplicate generated chunk ID {chunk_id!r}.")
            seen_chunk_ids.add(chunk_id)
            chunks.append(
                {
                    "document": document.filename,
                    "chapter_title": chapter_title,
                    "chunk_id": chunk_id,
                    "paragraph_start": chunk["paragraph_start"],
                    "paragraph_end": chunk["paragraph_end"],
                    "text": chunk["text"],
                }
            )

    return chunks


def prepare_docx_corpus(
    source_docx: Path,
    manuscript_dir: Path,
    output_dir: Path,
    manifest_path: Path,
    *,
    title: str | None = None,
    ingest_commit: str | None = None,
    hnsw_space: str = DEFAULT_HNSW_SPACE,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedded_chunk_count: int = 0,
) -> PreparedCorpus:
    """Prepare a DOCX into empty private targets without making any API calls."""

    source_docx = Path(source_docx)
    manuscript_dir = Path(manuscript_dir)
    output_dir = Path(output_dir)
    manifest_path = Path(manifest_path)
    _validate_targets(manuscript_dir, output_dir, manifest_path)

    extraction = extract_docx(source_docx)
    documents = build_markdown_documents(extraction, title=title)
    chunks = build_chunks(documents)
    chunks_bytes = _json_bytes(chunks, trailing_newline=False)
    document_bytes = {
        document.filename: document.markdown.encode("utf-8") for document in documents
    }
    corpus_title = normalize_heading(title) if title is not None else extraction.suggested_title

    manifest = _assemble_manifest(
        manuscript_documents=document_bytes,
        chunks=chunks,
        chunks_bytes=chunks_bytes,
        source_docx=source_docx,
        title=corpus_title,
        extraction_stats=extraction.stats,
        ingest_commit=ingest_commit,
        hnsw_space=hnsw_space,
        embedding_model=embedding_model,
        collection_name=collection_name,
        embedded_chunk_count=embedded_chunk_count,
    )
    manifest_bytes = _json_bytes(manifest, trailing_newline=True)

    manuscript_existed = manuscript_dir.exists()
    output_existed = output_dir.exists()
    created_files: list[Path] = []
    try:
        manuscript_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in document_bytes.items():
            path = manuscript_dir / filename
            _write_exclusive(path, content)
            created_files.append(path)

        chunks_path = output_dir / "chunks.json"
        _write_exclusive(chunks_path, chunks_bytes)
        created_files.append(chunks_path)

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        _write_exclusive(manifest_path, manifest_bytes)
        created_files.append(manifest_path)
    except Exception:
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        if not manuscript_existed:
            manuscript_dir.rmdir()
        if not output_existed:
            output_dir.rmdir()
        raise

    return PreparedCorpus(
        manuscript_dir=manuscript_dir,
        chunks_path=output_dir / "chunks.json",
        manifest_path=manifest_path,
        document_count=len(documents),
        chunk_count=len(chunks),
        manifest=manifest,
    )


def build_corpus_manifest(
    manuscript_dir: Path,
    chunks_path: Path,
    *,
    source_docx: Path | None = None,
    title: str | None = None,
    extraction_stats: Mapping[str, int] | None = None,
    ingest_commit: str | None = None,
    hnsw_space: str = DEFAULT_HNSW_SPACE,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedded_chunk_count: int | None = None,
) -> dict[str, Any]:
    """Build a text-free manifest for any existing Markdown corpus and chunks file."""

    manuscript_dir = Path(manuscript_dir)
    chunks_path = Path(chunks_path)
    if not manuscript_dir.is_dir():
        raise ManuscriptPreparationError(f"Manuscript directory does not exist: {manuscript_dir}")
    if not chunks_path.is_file():
        raise ManuscriptPreparationError(f"Chunks file does not exist: {chunks_path}")

    paths = sorted(manuscript_dir.glob("*.md"), key=lambda path: path.name)
    if not paths:
        raise ManuscriptPreparationError(f"No Markdown documents found in {manuscript_dir}.")
    document_bytes = {path.name: path.read_bytes() for path in paths}

    try:
        chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManuscriptPreparationError(f"Invalid UTF-8 chunks JSON: {chunks_path}") from exc
    if not isinstance(chunks, list):
        raise ManuscriptPreparationError("chunks.json must contain a top-level JSON array.")
    _validate_chunks(chunks, set(document_bytes))

    derived_title = title
    if derived_title is None:
        first_text = document_bytes[paths[0].name].decode("utf-8")
        derived_title = extract_chapter_title(
            first_text,
            fallback=clean_title_from_filename(paths[0].stem),
        )

    return _assemble_manifest(
        manuscript_documents=document_bytes,
        chunks=chunks,
        chunks_bytes=chunks_path.read_bytes(),
        source_docx=Path(source_docx) if source_docx is not None else None,
        title=normalize_heading(derived_title),
        extraction_stats=extraction_stats,
        ingest_commit=ingest_commit,
        hnsw_space=hnsw_space,
        embedding_model=embedding_model,
        collection_name=collection_name,
        embedded_chunk_count=(
            len([chunk for chunk in chunks if not should_skip_document(chunk["document"])])
            if embedded_chunk_count is None
            else embedded_chunk_count
        ),
    )


def write_corpus_manifest(
    manifest_path: Path,
    manuscript_dir: Path,
    chunks_path: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build and exclusively write a standalone text-free corpus manifest."""

    manifest_path = Path(manifest_path)
    if manifest_path.exists():
        raise ManuscriptPreparationError(f"Manifest target already exists: {manifest_path}")
    manifest = build_corpus_manifest(manuscript_dir, chunks_path, **kwargs)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _write_exclusive(manifest_path, _json_bytes(manifest, trailing_newline=True))
    return manifest


def normalize_heading(text: str | None) -> str:
    """Return a full, single-line NFC heading without truncating it."""

    normalized = unicodedata.normalize("NFC", text or "").replace("\u00a0", " ")
    normalized = re.sub(r"<br\s*/?>", " ", normalized, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", normalized).strip()


def _read_xml_part(
    archive: zipfile.ZipFile,
    member: str,
    *,
    required: bool,
) -> ElementTree.Element | None:
    try:
        content = archive.read(member)
    except KeyError:
        if not required:
            return None
        raise ManuscriptPreparationError(f"DOCX is missing required part {member!r}.") from None
    try:
        return ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ManuscriptPreparationError(f"DOCX part {member!r} is invalid XML.") from exc


def _validate_archive_member_names(archive: zipfile.ZipFile) -> None:
    names = [item.filename for item in archive.infolist()]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        raise ManuscriptPreparationError(
            f"DOCX contains duplicate archive member IDs: {', '.join(duplicates)}"
        )


def _validate_no_revisions_or_comments(archive: zipfile.ZipFile) -> None:
    for member in sorted(
        item.filename
        for item in archive.infolist()
        if item.filename.startswith("word/") and item.filename.endswith(".xml")
    ):
        root = _read_xml_part(archive, member, required=True)
        assert root is not None
        for element in root.iter():
            namespace, local_name = _split_tag(element.tag)
            if namespace not in {WORD_NAMESPACE, WORD_2010_NAMESPACE}:
                continue
            if local_name in _TRACKED_CHANGE_NAMES or local_name.endswith("Change"):
                raise ManuscriptPreparationError(
                    f"DOCX contains tracked changes in {member!r}; accept or reject them first."
                )
            if local_name.startswith("comment"):
                raise ManuscriptPreparationError(
                    f"DOCX contains comments in {member!r}; remove them before preparation."
                )


def _read_styles(archive: zipfile.ZipFile) -> dict[str, _Style]:
    root = _read_xml_part(archive, STYLES_XML, required=False)
    if root is None:
        return {}

    styles: dict[str, _Style] = {}
    for element in root.findall(_word_tag("style")):
        if element.get(_word_attr("type")) != "paragraph":
            continue
        style_id = element.get(_word_attr("styleId"))
        if not style_id:
            continue
        if style_id in styles:
            raise ManuscriptPreparationError(f"Duplicate Word style ID {style_id!r}.")
        name_element = element.find(_word_tag("name"))
        based_on_element = element.find(_word_tag("basedOn"))
        name = (
            name_element.get(_word_attr("val"))
            if name_element is not None
            else style_id
        )
        based_on = (
            based_on_element.get(_word_attr("val"))
            if based_on_element is not None
            else None
        )
        styles[style_id] = _Style(name=name or style_id, based_on=based_on)
    return styles


def _read_footnotes(
    archive: zipfile.ZipFile,
    counters: _ExtractionCounters,
) -> dict[str, str]:
    root = _read_xml_part(archive, FOOTNOTES_XML, required=False)
    if root is None:
        return {}

    footnotes: dict[str, str] = {}
    seen_ids: set[str] = set()
    for footnote in root.findall(_word_tag("footnote")):
        note_id = footnote.get(_word_attr("id"))
        if note_id is None:
            raise ManuscriptPreparationError("A footnote definition is missing its Word ID.")
        if note_id in seen_ids:
            raise ManuscriptPreparationError(f"Duplicate footnote ID {note_id!r}.")
        seen_ids.add(note_id)

        note_type = (footnote.get(_word_attr("type")) or "").casefold()
        if note_id in {"-1", "0"} or note_type in {
            "continuationseparator",
            "separator",
        }:
            continue

        visible_parts: list[str] = []
        for paragraph in _iter_descendant_paragraphs(footnote):
            text, _has_image = _render_inline(paragraph, None, counters, count_stats=False)
            normalized = _normalize_footnote_text(text)
            if normalized:
                visible_parts.append(normalized)
        note_text = " ".join(visible_parts).strip()
        if not note_text:
            raise ManuscriptPreparationError(f"Footnote {note_id!r} has no visible text.")
        footnotes[note_id] = note_text
        counters.footnote_definition_count += 1
    return footnotes


def _validate_no_real_endnotes(archive: zipfile.ZipFile) -> None:
    root = _read_xml_part(archive, ENDNOTES_XML, required=False)
    if root is None:
        return

    for endnote in root.findall(_word_tag("endnote")):
        note_id = endnote.get(_word_attr("id"))
        note_type = (endnote.get(_word_attr("type")) or "").casefold()
        if note_id in {"-1", "0"} or note_type in {
            "continuationseparator",
            "separator",
        }:
            continue
        raise ManuscriptPreparationError(
            "DOCX contains real endnotes, which are not silently discarded; "
            "convert them to footnotes before preparation."
        )


def _iter_body_paragraphs(body: ElementTree.Element) -> Iterable[ElementTree.Element]:
    for child in body:
        if _local_name(child.tag) == "sectPr":
            continue
        yield from _iter_descendant_paragraphs(child)


def _iter_descendant_paragraphs(
    element: ElementTree.Element,
) -> Iterable[ElementTree.Element]:
    if _local_name(element.tag) == "p":
        yield element
        return
    for child in element:
        yield from _iter_descendant_paragraphs(child)


def _paragraph_style_id(paragraph: ElementTree.Element) -> str | None:
    properties = paragraph.find(_word_tag("pPr"))
    if properties is None:
        return None
    style = properties.find(_word_tag("pStyle"))
    return style.get(_word_attr("val")) if style is not None else None


def _style_chain(style_id: str | None, styles: Mapping[str, _Style]) -> list[str]:
    if not style_id:
        return []
    chain: list[str] = []
    seen: set[str] = set()
    current: str | None = style_id
    while current:
        if current in seen:
            raise ManuscriptPreparationError(f"Word style inheritance cycle at {current!r}.")
        seen.add(current)
        style = styles.get(current)
        chain.extend([current, style.name if style is not None else current])
        current = style.based_on if style is not None else None
    return chain


def _normalized_style_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def _style_has_name(style_chain: Sequence[str], name: str) -> bool:
    needle = _normalized_style_name(name)
    return any(_normalized_style_name(item) == needle for item in style_chain)


def _heading_level(style_chain: Sequence[str]) -> int | None:
    for item in style_chain:
        match = re.fullmatch(r"heading([1-6])", _normalized_style_name(item))
        if match:
            return int(match.group(1))
    return None


def _is_toc_heading(style_chain: Sequence[str]) -> bool:
    return any(
        _normalized_style_name(item) in {"tocheading", "tableofcontentsheading"}
        for item in style_chain
    )


def _render_body_paragraph(
    paragraph: ElementTree.Element,
    footnotes: Mapping[str, str],
    counters: _ExtractionCounters,
) -> tuple[str, bool]:
    text, has_image = _render_inline(paragraph, footnotes, counters, count_stats=True)
    text = _normalize_paragraph_text(text)
    image_only = has_image and not text
    return ("[IMAGE]" if image_only else text), image_only


def _render_inline(
    element: ElementTree.Element,
    footnotes: Mapping[str, str] | None,
    counters: _ExtractionCounters,
    *,
    count_stats: bool,
) -> tuple[str, bool]:
    parts: list[str] = []
    has_image = False

    def visit(node: ElementTree.Element) -> None:
        nonlocal has_image
        local_name = _local_name(node.tag)
        if local_name in _INLINE_IGNORED_SUBTREES:
            return
        if local_name == "t":
            parts.append(node.text or "")
            return
        if local_name == "tab":
            parts.append("\t")
            if count_stats:
                counters.tab_count += 1
            return
        if local_name in {"br", "cr"}:
            parts.append("\n")
            if count_stats:
                counters.break_count += 1
            return
        if local_name == "noBreakHyphen":
            parts.append("\u2011")
            return
        if local_name == "softHyphen":
            parts.append("\u00ad")
            return
        if local_name == "footnoteReference":
            note_id = node.get(_word_attr("id"))
            if note_id in {None, "-1", "0"}:
                return
            if count_stats:
                counters.footnote_reference_count += 1
            if footnotes is None or note_id not in footnotes:
                raise ManuscriptPreparationError(
                    f"Unresolved footnote reference {note_id!r}."
                )
            parts.append(f" [Footnote {note_id}: {footnotes[note_id]}]")
            if count_stats:
                counters.resolved_footnote_reference_count += 1
            return
        if local_name == "endnoteReference":
            note_id = node.get(_word_attr("id"))
            if note_id not in {None, "-1", "0"}:
                raise ManuscriptPreparationError(
                    f"DOCX contains unsupported real endnote reference {note_id!r}."
                )
            return
        if local_name in _IMAGE_NAMES:
            has_image = True
            if count_stats:
                counters.image_count += 1
            return
        if local_name == "fldSimple" and count_stats:
            counters.field_count += 1
        elif (
            local_name == "fldChar"
            and node.get(_word_attr("fldCharType")) == "begin"
            and count_stats
        ):
            counters.field_count += 1
        for child in node:
            visit(child)

    visit(element)
    return "".join(parts), has_image


def _normalize_paragraph_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    lines = [re.sub(r" +", " ", line).strip(" ") for line in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "<br>".join(lines)


def _normalize_footnote_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _markdown_block(block: ParagraphBlock) -> str:
    if block.image_only:
        return "[IMAGE]"
    if block.heading_level and block.heading_level > 1:
        return f"{'#' * block.heading_level} {normalize_heading(block.text)}"
    if block.text == "[IMAGE]":
        return r"\[IMAGE]"
    if block.text.lstrip().startswith("#"):
        offset = len(block.text) - len(block.text.lstrip())
        return f"{block.text[:offset]}\\{block.text[offset:]}"
    return block.text


def _render_markdown_document(heading: str, content: Sequence[str]) -> str:
    sections = [f"# {normalize_heading(heading)}", *content]
    return "\n\n".join(sections).rstrip() + "\n"


def _section_filename(ordinal: int, heading: str, *, force_skip: bool = False) -> str:
    safe_title = _safe_filename_component(heading)
    base = f"{ordinal:02d}_{safe_title}"
    normalized_title = _normalized_section_title(heading)
    if (
        force_skip
        or normalized_title in _END_MATTER_TITLES
        or normalized_title.startswith("illustration credits")
    ):
        return f"{base}{_END_MATTER_SKIP_SUFFIX}"
    return f"{base}.md"


def _safe_filename_component(text: str, max_length: int = 140) -> str:
    normalized = normalize_heading(text)
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" ._")
    normalized = normalized[:max_length].rstrip(" ._")
    if not normalized:
        normalized = "Untitled Section"
    if normalized.casefold() in _WINDOWS_RESERVED_STEMS:
        normalized = f"_{normalized}"
    return normalized


def _normalized_section_title(title: str) -> str:
    normalized = normalize_heading(title).casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _assemble_manifest(
    *,
    manuscript_documents: Mapping[str, bytes],
    chunks: Sequence[Mapping[str, Any]],
    chunks_bytes: bytes,
    source_docx: Path | None,
    title: str,
    extraction_stats: Mapping[str, int] | None,
    ingest_commit: str | None,
    hnsw_space: str,
    embedding_model: str,
    collection_name: str,
    embedded_chunk_count: int,
) -> dict[str, Any]:
    _validate_chunks(chunks, set(manuscript_documents))
    if embedded_chunk_count < 0:
        raise ManuscriptPreparationError("embedded_chunk_count cannot be negative.")
    if not hnsw_space.strip() or not embedding_model.strip() or not collection_name.strip():
        raise ManuscriptPreparationError("Store configuration values cannot be blank.")

    chunk_counts = Counter(str(chunk["document"]) for chunk in chunks)
    chapter_titles: dict[str, str] = {}
    for chunk in chunks:
        chapter_titles.setdefault(str(chunk["document"]), str(chunk["chapter_title"]))

    documents: list[dict[str, Any]] = []
    paragraph_total = 0
    for filename in sorted(manuscript_documents):
        content = manuscript_documents[filename]
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ManuscriptPreparationError(f"Markdown document is not UTF-8: {filename}") from exc
        chapter_title = extract_chapter_title(
            text,
            fallback=clean_title_from_filename(Path(filename).stem),
        )
        paragraphs = split_into_paragraphs(text)
        paragraph_total += len(paragraphs)
        documents.append(
            {
                "filename": filename,
                "sha256": _sha256(content),
                "paragraph_count": len(paragraphs),
                "chunk_count": chunk_counts[filename],
                "chapter_title": chapter_titles.get(filename, chapter_title),
            }
        )

    chunk_manifest: list[dict[str, Any]] = []
    for chunk in chunks:
        text = str(chunk["text"])
        chunk_manifest.append(
            {
                "chunk_id": str(chunk["chunk_id"]),
                "document": str(chunk["document"]),
                "paragraph_start": int(chunk["paragraph_start"]),
                "paragraph_end": int(chunk["paragraph_end"]),
                "text_sha256": _sha256(text.encode("utf-8")),
                "char_count": len(text),
            }
        )

    markdown_source_payload = [
        {"filename": item["filename"], "sha256": item["sha256"]} for item in documents
    ]
    if source_docx is not None:
        if not source_docx.is_file():
            raise ManuscriptPreparationError(f"Source DOCX does not exist: {source_docx}")
        source = {
            "kind": "docx",
            "filename": source_docx.name,
            "sha256": _sha256(source_docx.read_bytes()),
            "byte_count": source_docx.stat().st_size,
        }
    else:
        source_digest_input = json.dumps(
            markdown_source_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        source = {
            "kind": "markdown_directory",
            "filename": None,
            "sha256": _sha256(source_digest_input),
            "document_count": len(documents),
        }

    searchable_chunk_count = len(
        [chunk for chunk in chunks if not should_skip_document(str(chunk["document"]))]
    )
    if embedded_chunk_count > searchable_chunk_count:
        raise ManuscriptPreparationError(
            "embedded_chunk_count cannot exceed the number of searchable chunks."
        )

    extraction = {
        "document_count": len(documents),
        "paragraph_count": paragraph_total,
        "chunk_count": len(chunks),
        "searchable_chunk_count": searchable_chunk_count,
        "skipped_document_count": len(
            {
                str(chunk["document"])
                for chunk in chunks
                if should_skip_document(str(chunk["document"]))
            }
        ),
    }
    if extraction_stats:
        for key in sorted(extraction_stats):
            value = extraction_stats[key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ManuscriptPreparationError(
                    f"Extraction statistic {key!r} must be a non-negative integer."
                )
            extraction[key] = value

    return {
        "manifest_schema": MANIFEST_SCHEMA,
        "title": normalize_heading(title),
        "source": source,
        "documents": documents,
        "chunks": chunk_manifest,
        "extraction": extraction,
        "ingest": {
            "paragraphs_per_chunk": PARAGRAPHS_PER_CHUNK,
            "paragraph_overlap": PARAGRAPH_OVERLAP,
            "ingest_commit": ingest_commit or _current_git_commit(),
            "skip_files": sorted(SKIP_FILES),
        },
        "store": {
            "hnsw_space": hnsw_space,
            "embedding_model": embedding_model,
            "collection_name": collection_name,
            "embedded_chunk_count": embedded_chunk_count,
        },
        "chunks_sha256": _sha256(chunks_bytes),
    }


def _validate_chunks(
    chunks: Sequence[Mapping[str, Any]],
    document_names: set[str],
) -> None:
    required = {
        "chapter_title",
        "chunk_id",
        "document",
        "paragraph_end",
        "paragraph_start",
        "text",
    }
    seen_ids: set[str] = set()
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, Mapping):
            raise ManuscriptPreparationError(f"Chunk {index} is not a JSON object.")
        missing = required.difference(chunk)
        if missing:
            raise ManuscriptPreparationError(
                f"Chunk {index} is missing fields: {', '.join(sorted(missing))}"
            )
        chunk_id = str(chunk["chunk_id"])
        if not chunk_id or chunk_id in seen_ids:
            raise ManuscriptPreparationError(f"Duplicate or blank chunk ID {chunk_id!r}.")
        seen_ids.add(chunk_id)
        document = str(chunk["document"])
        if document not in document_names:
            raise ManuscriptPreparationError(
                f"Chunk {chunk_id!r} references missing document {document!r}."
            )
        start = chunk["paragraph_start"]
        end = chunk["paragraph_end"]
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 1
            or end < start
        ):
            raise ManuscriptPreparationError(
                f"Chunk {chunk_id!r} has an invalid paragraph range."
            )
        if not isinstance(chunk["text"], str) or not isinstance(chunk["chapter_title"], str):
            raise ManuscriptPreparationError(
                f"Chunk {chunk_id!r} text and chapter title must be strings."
            )


def _validate_targets(
    manuscript_dir: Path,
    output_dir: Path,
    manifest_path: Path,
) -> None:
    manuscript_resolved = manuscript_dir.resolve()
    output_resolved = output_dir.resolve()
    manifest_resolved = manifest_path.resolve()
    if manuscript_resolved == output_resolved:
        raise ManuscriptPreparationError("Manuscript and output targets must be different.")
    if manuscript_resolved in output_resolved.parents or output_resolved in manuscript_resolved.parents:
        raise ManuscriptPreparationError("Manuscript and output targets cannot contain one another.")
    if manifest_resolved == output_resolved / "chunks.json":
        raise ManuscriptPreparationError("Manifest target cannot replace chunks.json.")
    if manifest_resolved.is_relative_to(manuscript_resolved):
        raise ManuscriptPreparationError("Manifest target cannot be inside the manuscript directory.")

    for target in (manuscript_dir, output_dir):
        if target.exists() and not target.is_dir():
            raise ManuscriptPreparationError(f"Target is not a directory: {target}")
        if target.exists() and any(target.iterdir()):
            raise ManuscriptPreparationError(f"Target directory is not empty: {target}")
    if manifest_path.exists():
        raise ManuscriptPreparationError(f"Manifest target already exists: {manifest_path}")


def _write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)


def _json_bytes(value: Any, *, trailing_newline: bool) -> bytes:
    text = json.dumps(value, indent=2, ensure_ascii=False)
    if trailing_newline:
        text += "\n"
    return text.encode("utf-8")


def _current_git_commit() -> str:
    repository = Path(__file__).resolve().parent.parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return "unknown"
    commit = result.stdout.strip()
    return commit if re.fullmatch(r"[0-9a-fA-F]{40}", commit) else "unknown"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _word_tag(local_name: str) -> str:
    return f"{{{WORD_NAMESPACE}}}{local_name}"


def _word_attr(local_name: str) -> str:
    return f"{{{WORD_NAMESPACE}}}{local_name}"


def _split_tag(tag: str) -> tuple[str, str]:
    if tag.startswith("{") and "}" in tag:
        namespace, local_name = tag[1:].split("}", 1)
        return namespace, local_name
    return "", tag


def _local_name(tag: str) -> str:
    return _split_tag(tag)[1]
