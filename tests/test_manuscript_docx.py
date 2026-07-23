from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from filters import should_skip_document
from manuscript_docx import (
    MANIFEST_SCHEMA,
    MarkdownDocument,
    ManuscriptPreparationError,
    build_chunks,
    build_corpus_manifest,
    build_markdown_documents,
    extract_docx,
    prepare_docx_corpus,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
COMMIT = "a" * 40

STYLES_XML = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="{W_NS}">
  <w:style w:type="paragraph" w:styleId="Normal">
    <w:name w:val="Normal"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="TOCHeading">
    <w:name w:val="TOC Heading"/>
    <w:basedOn w:val="Heading1"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="TOC1">
    <w:name w:val="toc 1"/>
  </w:style>
</w:styles>
"""


def _document_xml(body: str) -> str:
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}">
  <w:body>
    {body}
    <w:sectPr/>
  </w:body>
</w:document>
"""


def _write_docx(
    path: Path,
    body: str,
    *,
    footnotes: str | None = None,
    styles: str = STYLES_XML,
    extras: dict[str, str] | None = None,
) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", _document_xml(body))
        archive.writestr("word/styles.xml", styles)
        if footnotes is not None:
            archive.writestr("word/footnotes.xml", footnotes)
        for name, content in (extras or {}).items():
            archive.writestr(name, content)
    return path


def _paragraph(
    paragraph_id: str,
    text: str,
    *,
    style: str = "Normal",
) -> str:
    return (
        f'<w:p w14:paraId="{paragraph_id}">'
        f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
        f"<w:r><w:t>{text}</w:t></w:r>"
        "</w:p>"
    )


def _minimal_body(*, reference_id: str | None = None) -> str:
    reference = (
        f'<w:r><w:footnoteReference w:id="{reference_id}"/></w:r>'
        if reference_id is not None
        else ""
    )
    return (
        _paragraph("00000001", "Contents", style="TOCHeading")
        + _paragraph("00000002", "Section One 1", style="TOC1")
        + _paragraph("00000003", "Section One", style="Heading1")
        + (
            '<w:p w14:paraId="00000004"><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
            f"<w:r><w:t>Plain body</w:t></w:r>{reference}</w:p>"
        )
    )


def _footnotes(*definitions: tuple[str, str]) -> str:
    notes = [
        '<w:footnote w:id="-1" w:type="separator">'
        "<w:p><w:r><w:separator/></w:r></w:p></w:footnote>"
    ]
    for note_id, text in definitions:
        notes.append(
            f'<w:footnote w:id="{note_id}"><w:p>'
            "<w:r><w:footnoteRef/></w:r>"
            f"<w:r><w:t>{text}</w:t></w:r>"
            "</w:p></w:footnote>"
        )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><w:footnotes xmlns:w="{W_NS}">'
        + "".join(notes)
        + "</w:footnotes>"
    )


def test_prepare_splits_nested_sdt_and_preserves_supported_content(tmp_path: Path) -> None:
    body = (
        _paragraph("00000001", "Archive Sample", style="Title")
        + (
            "<w:sdt><w:sdtContent>"
            + _paragraph("00000002", "Complete Contents", style="TOCHeading")
            + (
                '<w:p w14:paraId="00000003"><w:pPr><w:pStyle w:val="TOC1"/></w:pPr>'
                "<w:r><w:t>Section One</w:t></w:r><w:r><w:tab/></w:r>"
                "<w:r><w:t>7</w:t></w:r></w:p>"
            )
            + "</w:sdtContent></w:sdt>"
        )
        + (
            '<w:p w14:paraId="00000004">'
            '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
            "<w:r><w:t>  Section   One</w:t><w:br/><w:t>Complete  </w:t></w:r>"
            "</w:p>"
        )
        + (
            '<w:p w14:paraId="00000005"><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
            "<w:r><w:t>Visible body</w:t></w:r>"
            '<w:r><w:footnoteReference w:id="1"/></w:r>'
            '<w:fldSimple w:instr="DO NOT EMIT"><w:r><w:t> DISPLAY VALUE</w:t></w:r>'
            "</w:fldSimple>"
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            "<w:r><w:instrText> HIDDEN INSTRUCTION </w:instrText></w:r>"
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            "<w:r><w:t> COMPLEX DISPLAY</w:t></w:r>"
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
            "<w:r><w:br/><w:t>after break</w:t></w:r>"
            "</w:p>"
        )
        + (
            '<w:p w14:paraId="00000006"><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
            "<w:r><w:drawing/></w:r></w:p>"
        )
        + _paragraph("00000007", "Subsection", style="Heading2")
        + _paragraph("00000008", "Works Consulted", style="Heading1")
        + _paragraph("00000009", "Reference item")
        + _paragraph(
            "0000000A",
            "Illustration Credits and Generation Notes",
            style="Heading1",
        )
        + _paragraph("0000000B", "Image maker")
        + _paragraph("0000000C", "Index", style="Heading1")
        + _paragraph("0000000D", "Entry, 3")
    )
    source = _write_docx(
        tmp_path / "sample.docx",
        body,
        footnotes=_footnotes(("1", "Resolved note text")),
    )
    manuscript = tmp_path / "prepared" / "manuscript"
    output = tmp_path / "prepared" / "output"
    manifest_path = tmp_path / "prepared" / "corpus_manifest.json"

    prepared = prepare_docx_corpus(
        source,
        manuscript,
        output,
        manifest_path,
        title="Overridden Corpus Title",
        ingest_commit=COMMIT,
    )

    names = sorted(path.name for path in manuscript.glob("*.md"))
    assert names == [
        "01_Front Matter.md",
        "02_Table of Contents.md",
        "03_Section One Complete.md",
        "04_Works Consulted__32_Bibliography.md",
        "05_Illustration Credits and Generation Notes__32_Bibliography.md",
        "06_Index__32_Bibliography.md",
    ]
    assert should_skip_document(names[1])
    assert all(should_skip_document(name) for name in names[3:])
    assert len(set(names[3:])) == 3

    front = (manuscript / names[0]).read_text(encoding="utf-8")
    toc = (manuscript / names[1]).read_text(encoding="utf-8")
    section = (manuscript / names[2]).read_text(encoding="utf-8")
    assert front.startswith("# Overridden Corpus Title\n")
    assert "Archive Sample" in front
    assert toc.startswith("# Complete Contents\n")
    assert "Section One\t7" in toc
    assert section.startswith("# Section One Complete\n")
    assert "[Footnote 1: Resolved note text]" in section
    assert "DISPLAY VALUE" in section
    assert "COMPLEX DISPLAY" in section
    assert "DO NOT EMIT" not in section
    assert "HIDDEN INSTRUCTION" not in section
    assert "Visible body" in section and "<br>after break" in section
    assert "[IMAGE]" in section
    assert "## Subsection" in section

    chunks = json.loads(prepared.chunks_path.read_text(encoding="utf-8"))
    assert all(set(chunk) == {
        "chapter_title",
        "chunk_id",
        "document",
        "paragraph_end",
        "paragraph_start",
        "text",
    } for chunk in chunks)
    assert "[IMAGE]" not in "\n".join(str(chunk["text"]) for chunk in chunks)
    assert len({chunk["chunk_id"] for chunk in chunks}) == len(chunks)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert manifest["manifest_schema"] == MANIFEST_SCHEMA
    assert manifest["source"]["filename"] == "sample.docx"
    assert manifest["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest["ingest"]["ingest_commit"] == COMMIT
    assert manifest["store"]["hnsw_space"] == "l2"
    assert manifest["extraction"]["heading_1_count"] == 4
    assert manifest["extraction"]["toc_heading_count"] == 1
    assert manifest["extraction"]["footnote_reference_count"] == 1
    assert manifest["extraction"]["resolved_footnote_reference_count"] == 1
    assert manifest["extraction"]["image_only_paragraph_count"] == 1
    assert "Visible body" not in manifest_text
    assert "Resolved note text" not in manifest_text
    assert all("text" not in chunk for chunk in manifest["chunks"])
    assert prepared.document_count == 6
    assert prepared.chunk_count == len(chunks)


def test_preparation_is_byte_deterministic(tmp_path: Path) -> None:
    source = _write_docx(tmp_path / "same.docx", _minimal_body())
    prepared: list[tuple[Path, Path, Path]] = []

    for run in ("one", "two"):
        base = tmp_path / run
        manuscript = base / "manuscript"
        output = base / "output"
        manifest = base / "manifest.json"
        prepare_docx_corpus(
            source,
            manuscript,
            output,
            manifest,
            title="Stable Title",
            ingest_commit=COMMIT,
        )
        prepared.append((manuscript, output / "chunks.json", manifest))

    first_documents = {
        path.name: path.read_bytes() for path in sorted(prepared[0][0].glob("*.md"))
    }
    second_documents = {
        path.name: path.read_bytes() for path in sorted(prepared[1][0].glob("*.md"))
    }
    assert first_documents == second_documents
    assert prepared[0][1].read_bytes() == prepared[1][1].read_bytes()
    assert prepared[0][2].read_bytes() == prepared[1][2].read_bytes()


def test_unresolved_footnote_is_an_error(tmp_path: Path) -> None:
    source = _write_docx(tmp_path / "missing-note.docx", _minimal_body(reference_id="9"))

    with pytest.raises(ManuscriptPreparationError, match="Unresolved footnote reference '9'"):
        extract_docx(source)


def test_duplicate_footnote_id_is_an_error(tmp_path: Path) -> None:
    source = _write_docx(
        tmp_path / "duplicate-note.docx",
        _minimal_body(reference_id="1"),
        footnotes=_footnotes(("1", "First note"), ("1", "Second note")),
    )

    with pytest.raises(ManuscriptPreparationError, match="Duplicate footnote ID '1'"):
        extract_docx(source)


def test_real_endnotes_are_rejected_instead_of_silently_lost(tmp_path: Path) -> None:
    body = _minimal_body() + (
        '<w:p w14:paraId="00000005"><w:r>'
        '<w:endnoteReference w:id="1"/>'
        "</w:r></w:p>"
    )
    endnotes = (
        f'<w:endnotes xmlns:w="{W_NS}">'
        '<w:endnote w:id="-1" w:type="separator"><w:p/></w:endnote>'
        '<w:endnote w:id="1"><w:p><w:r><w:t>Endnote text</w:t></w:r></w:p></w:endnote>'
        "</w:endnotes>"
    )
    source = _write_docx(
        tmp_path / "endnotes.docx",
        body,
        extras={"word/endnotes.xml": endnotes},
    )

    with pytest.raises(ManuscriptPreparationError, match="real endnotes"):
        extract_docx(source)


def test_missing_toc_heading_is_an_error(tmp_path: Path) -> None:
    body = (
        _paragraph("00000001", "Section", style="Heading1")
        + _paragraph("00000002", "Body")
    )
    source = _write_docx(tmp_path / "no-toc.docx", body)

    with pytest.raises(ManuscriptPreparationError, match="no Word TOC Heading"):
        extract_docx(source)


def test_empty_toc_heading_section_is_an_error(tmp_path: Path) -> None:
    body = (
        _paragraph("00000001", "Contents", style="TOCHeading")
        + _paragraph("00000002", "Section", style="Heading1")
        + _paragraph("00000003", "Body")
    )
    source = _write_docx(tmp_path / "empty-toc.docx", body)

    with pytest.raises(ManuscriptPreparationError, match="no visible entries"):
        build_markdown_documents(extract_docx(source))


@pytest.mark.parametrize(
    ("body", "extras", "message"),
    [
        (
            _minimal_body()
            + '<w:p><w:ins w:id="4"><w:r><w:t>Revision</w:t></w:r></w:ins></w:p>',
            None,
            "tracked changes",
        ),
        (
            _minimal_body(),
            {
                "word/comments.xml": (
                    f'<w:comments xmlns:w="{W_NS}">'
                    '<w:comment w:id="1"><w:p><w:r><w:t>Comment</w:t></w:r></w:p>'
                    "</w:comment></w:comments>"
                )
            },
            "comments",
        ),
    ],
)
def test_tracked_changes_and_comments_are_errors(
    tmp_path: Path,
    body: str,
    extras: dict[str, str] | None,
    message: str,
) -> None:
    source = _write_docx(tmp_path / f"{message}.docx", body, extras=extras)

    with pytest.raises(ManuscriptPreparationError, match=message):
        extract_docx(source)


def test_duplicate_word_paragraph_id_is_an_error(tmp_path: Path) -> None:
    body = (
        _paragraph("ABCDEF01", "Contents", style="TOCHeading")
        + _paragraph("ABCDEF02", "Section", style="Heading1")
        + _paragraph("ABCDEF02", "Body")
    )
    source = _write_docx(tmp_path / "duplicate-paragraph.docx", body)

    with pytest.raises(ManuscriptPreparationError, match="Duplicate Word paragraph ID"):
        extract_docx(source)


def test_nonempty_targets_are_rejected_without_touching_data(tmp_path: Path) -> None:
    source = _write_docx(tmp_path / "safe.docx", _minimal_body())
    manuscript = tmp_path / "manuscript"
    output = tmp_path / "output"
    manuscript.mkdir()
    marker = manuscript / "owner-data.txt"
    marker.write_text("preserve", encoding="utf-8")

    with pytest.raises(ManuscriptPreparationError, match="not empty"):
        prepare_docx_corpus(
            source,
            manuscript,
            output,
            tmp_path / "manifest.json",
            ingest_commit=COMMIT,
        )

    assert marker.read_text(encoding="utf-8") == "preserve"
    assert not output.exists()
    assert not (tmp_path / "manifest.json").exists()


def test_standalone_manifest_builder_uses_hashes_not_chunk_text(tmp_path: Path) -> None:
    manuscript = tmp_path / "legacy"
    manuscript.mkdir()
    document = MarkdownDocument(
        filename="01_Generic.md",
        chapter_title="Generic",
        markdown="# Generic\n\nSynthetic sentence one.\n\nSynthetic sentence two.\n",
    )
    (manuscript / document.filename).write_bytes(document.markdown.encode("utf-8"))
    chunks = build_chunks([document])
    chunks_path = tmp_path / "chunks.json"
    chunks_path.write_text(
        json.dumps(chunks, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    manifest = build_corpus_manifest(
        manuscript,
        chunks_path,
        title="Rollback Snapshot",
        ingest_commit=COMMIT,
    )

    serialized = json.dumps(manifest, ensure_ascii=False)
    assert manifest["source"]["kind"] == "markdown_directory"
    assert manifest["source"]["filename"] is None
    assert manifest["source"]["document_count"] == 1
    assert manifest["documents"][0]["sha256"] == hashlib.sha256(
        document.markdown.encode("utf-8")
    ).hexdigest()
    assert manifest["chunks"][0]["text_sha256"] == hashlib.sha256(
        str(chunks[0]["text"]).encode("utf-8")
    ).hexdigest()
    assert "Synthetic sentence" not in serialized
    assert all("text" not in chunk for chunk in manifest["chunks"])
    assert manifest["chunks_sha256"] == hashlib.sha256(chunks_path.read_bytes()).hexdigest()

    with pytest.raises(ManuscriptPreparationError, match="cannot exceed"):
        build_corpus_manifest(
            manuscript,
            chunks_path,
            title="Rollback Snapshot",
            ingest_commit=COMMIT,
            embedded_chunk_count=2,
        )
