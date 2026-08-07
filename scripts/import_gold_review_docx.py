"""Finalize the private owner workbook and transcribe it to canonical gold JSON.

The command is intentionally offline.  It reads WordprocessingML directly,
removes owner-excluded item blocks, applies a few mechanical cover-page status
updates, and validates every transcribed location against the frozen corpus
manifest.  It never prints held-out question or rubric text.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gold_set import (  # noqa: E402
    GoldSetValidationError,
    load_json_object,
    sha256_file,
    validate_gold_set,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W = f"{{{W_NS}}}"
ET.register_namespace("w", W_NS)

DEFAULT_SOURCE = (
    BASE_DIR / "runtime" / "gold-authoring" / "gold_set_questions_owner_review_cleaned.docx"
)
DEFAULT_FINAL_DOCX = (
    BASE_DIR / "runtime" / "gold-authoring" / "gold_set_questions_owner_review_final.docx"
)
DEFAULT_GOLD_OUTPUT = BASE_DIR / "runtime" / "gold-authoring" / "gold_set.draft.json"
DEFAULT_MANIFEST = BASE_DIR / "fixtures" / "corpus_manifest.json"

ITEM_HEADING_RE = re.compile(r"^(H\d{3})\s*[Â··]\s*(.+?)\s*$")
BEHAVIOR_RE = re.compile(r"\bBehavior:\s*(answer|abstain)\b", re.IGNORECASE)
CLAIM_RE = re.compile(
    r"^(Essential|Optional)\s+(.*?)\s*Supporting chunk IDs:\s*(.+?)\s*$",
    re.IGNORECASE,
)
RELEVANT_RE = re.compile(r"^(.*?)\s*[Â··]\s*chunks?\s+(.+?)\s*$", re.IGNORECASE)

STRATUM_BY_LABEL = {
    "focused biographical": "focused_biographical",
    "focused analytical": "focused_analytical",
    "conceptual": "conceptual",
    "broad thematic": "broad_thematic",
    "out of corpus": "out_of_corpus",
    "adversarial premise": "adversarial_premise",
}


class GoldReviewImportError(ValueError):
    """Raised when the private workbook cannot be transcribed unambiguously."""


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(f".//{W}t"))


def _paragraph_style(paragraph: ET.Element) -> str:
    style = paragraph.find(f"./{W}pPr/{W}pStyle")
    return "" if style is None else str(style.get(f"{W}val", ""))


def _replace_paragraph_text(paragraph: ET.Element, text: str) -> None:
    nodes = paragraph.findall(f".//{W}t")
    if not nodes:
        run = paragraph.find(f"./{W}r")
        if run is None:
            run = ET.SubElement(paragraph, f"{W}r")
        nodes = [ET.SubElement(run, f"{W}t")]
    nodes[0].text = text
    nodes[0].set(f"{{{XML_NS}}}space", "preserve")
    for node in nodes[1:]:
        node.text = ""


def _front_matter_replacement(text: str) -> str | None:
    replacements = {
        "Owner-adjudicated edition  ·  38 held-out questions": (
            "Owner-adjudicated edition  ·  37 held-out questions"
        ),
        "Owner-adjudicated edition  Â·  38 held-out questions": (
            "Owner-adjudicated edition  Â·  37 held-out questions"
        ),
        "38 held-out questions": "37 held-out questions",
        "Resolve H039, transcribe to structured JSON, validate, and complete provenance.": (
            "Run fresh blinded annotation batches, owner-adjudicate the drafts, and "
            "complete formal lock."
        ),
        "H020 and H040 removed; identifier gaps are intentional.": (
            "H020, H039, and H040 removed; identifier gaps are intentional."
        ),
        (
            "The retained set contains 38 questions. H020 and H040 were removed; "
            "the remaining IDs stay intentionally gapped."
        ): (
            "The retained set contains 37 questions. H020, H039, and H040 were "
            "removed; the remaining IDs stay intentionally gapped."
        ),
        (
            "PENDING — Resolve H039's question/rubric conflict; all other stratum "
            "and Behavior choices are recorded."
        ): "COMPLETE — All retained question, stratum, and Behavior choices are recorded.",
        (
            " BLOCKING / REQUIRED   All owner decisions are recorded; the explicit "
            "H039 question/rubric conflict must be resolved before formal lock."
        ): (
            " READY FOR CANONICALIZATION   All retained owner decisions are recorded; "
            "no item-level question/rubric conflict remains."
        ),
    }
    if text in replacements:
        return replacements[text]
    if "Adversarial premise" in text and "H037, H038, H039" in text:
        return text.replace("H037, H038, H039", "H037, H038").replace(
            "3 items", "2 items"
        )
    if "3 items" in text and ("H037–H039" in text or "H037-H039" in text):
        return text.replace("3 items", "2 items").replace(
            "H037–H039", "H037–H038"
        ).replace("H037-H039", "H037-H038")
    return None


def finalize_document_xml(document_xml: bytes, *, excluded_ids: set[str]) -> bytes:
    """Return minimally edited document XML with excluded question blocks removed."""

    root = ET.fromstring(document_xml)
    for paragraph in root.findall(f".//{W}p"):
        replacement = _front_matter_replacement(_paragraph_text(paragraph))
        if replacement is not None:
            _replace_paragraph_text(paragraph, replacement)

    body = root.find(f"./{W}body")
    if body is None:
        raise GoldReviewImportError("DOCX has no WordprocessingML body")

    remove = False
    found: set[str] = set()
    for child in list(body):
        if child.tag == f"{W}p" and _paragraph_style(child) == "QuestionID":
            heading = ITEM_HEADING_RE.fullmatch(_paragraph_text(child).strip())
            if heading is not None:
                item_id = heading.group(1)
                remove = item_id in excluded_ids
                if remove:
                    found.add(item_id)
            elif not _paragraph_text(child).strip() and remove:
                body.remove(child)
                continue
        if child.tag == f"{W}sectPr":
            remove = False
        elif remove:
            body.remove(child)

    missing = sorted(excluded_ids - found)
    if missing:
        raise GoldReviewImportError(f"excluded item blocks were not found: {missing!r}")

    remaining_ids = [
        match.group(1)
        for paragraph in root.findall(f".//{W}p")
        if _paragraph_style(paragraph) == "QuestionID"
        and (match := ITEM_HEADING_RE.fullmatch(_paragraph_text(paragraph).strip()))
    ]
    leaked = sorted(excluded_ids.intersection(remaining_ids))
    if leaked:
        raise GoldReviewImportError(f"excluded item blocks remain in DOCX: {leaked!r}")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_final_docx(
    source: Path,
    output: Path,
    *,
    excluded_ids: set[str],
    force: bool,
) -> Path:
    if output.exists() and not force:
        raise GoldReviewImportError(f"refusing to overwrite existing output: {output}")
    if source.resolve() == output.resolve():
        raise GoldReviewImportError("source and final DOCX paths must differ")
    try:
        with ZipFile(source, "r") as archive:
            members = [(entry, archive.read(entry.filename)) for entry in archive.infolist()]
    except (OSError, KeyError) as exc:
        raise GoldReviewImportError(f"cannot read source DOCX {source}: {exc}") from exc

    replaced = False
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w") as archive:
        for entry, payload in members:
            if entry.filename == "word/document.xml":
                payload = finalize_document_xml(payload, excluded_ids=excluded_ids)
                replaced = True
            copied = ZipInfo(entry.filename, date_time=entry.date_time)
            copied.compress_type = entry.compress_type or ZIP_DEFLATED
            copied.comment = entry.comment
            copied.extra = entry.extra
            copied.internal_attr = entry.internal_attr
            copied.external_attr = entry.external_attr
            copied.create_system = entry.create_system
            archive.writestr(copied, payload)
    if not replaced:
        output.unlink(missing_ok=True)
        raise GoldReviewImportError("source archive has no word/document.xml")
    return output


def _split_ids(text: str) -> list[str]:
    return [value.strip() for value in re.split(r"\s*;\s*", text) if value.strip()]


def _manifest_document_lookup(manifest: dict[str, object]) -> tuple[dict[str, str], set[str]]:
    chunks = manifest.get("chunks")
    if not isinstance(chunks, list):
        raise GoldReviewImportError("corpus manifest has no chunks array")
    documents: dict[str, str] = {}
    chunk_ids: set[str] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_id = chunk.get("chunk_id")
        document = chunk.get("document")
        if isinstance(chunk_id, str) and isinstance(document, str):
            chunk_ids.add(chunk_id)
            stem = Path(document).stem
            documents[stem] = document
    return documents, chunk_ids


def _parse_relevant(
    rows: Iterable[str],
    *,
    documents: dict[str, str],
    manifest_chunk_ids: set[str],
    item_id: str,
) -> list[str]:
    result: list[str] = []
    for raw in rows:
        text = raw.strip()
        if not text or text.casefold() == "none supplied.":
            continue
        match = RELEVANT_RE.fullmatch(text)
        if match is None:
            raise GoldReviewImportError(f"{item_id}: ambiguous relevant-location row")
        document_stem = match.group(1).strip()
        if document_stem not in documents:
            raise GoldReviewImportError(f"{item_id}: relevant row names an unknown document")
        for suffix in (value.strip() for value in match.group(2).split(",")):
            chunk_id = f"{document_stem}_{suffix}"
            if chunk_id not in manifest_chunk_ids:
                raise GoldReviewImportError(
                    f"{item_id}: relevant row resolves to an unknown chunk ID"
                )
            if chunk_id not in result:
                result.append(chunk_id)
    return result


def parse_gold_from_document_xml(
    document_xml: bytes,
    *,
    manifest: dict[str, object],
    manifest_sha256: str,
) -> dict[str, object]:
    """Parse final owner-review WordprocessingML into ``archivist.gold/1``."""

    root = ET.fromstring(document_xml)
    paragraphs = root.findall(f".//{W}p")
    starts: list[tuple[int, re.Match[str]]] = []
    for index, paragraph in enumerate(paragraphs):
        if _paragraph_style(paragraph) != "QuestionID":
            continue
        match = ITEM_HEADING_RE.fullmatch(_paragraph_text(paragraph).strip())
        if match is not None:
            starts.append((index, match))
    if not starts:
        raise GoldReviewImportError("final DOCX has no H### question blocks")

    documents, manifest_chunk_ids = _manifest_document_lookup(manifest)
    items: list[dict[str, object]] = []
    for position, (start, heading) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(paragraphs)
        item_id = heading.group(1)
        label = " ".join(heading.group(2).casefold().split())
        stratum = STRATUM_BY_LABEL.get(label)
        if stratum is None:
            raise GoldReviewImportError(f"{item_id}: unknown stratum label")
        block = paragraphs[start + 1 : end]
        questions = [
            _paragraph_text(paragraph).strip()
            for paragraph in block
            if _paragraph_style(paragraph) == "QuestionPrompt"
            and _paragraph_text(paragraph).strip()
        ]
        if len(questions) != 1:
            raise GoldReviewImportError(f"{item_id}: expected exactly one question paragraph")
        behavior_hits = {
            match.group(1).casefold()
            for paragraph in block
            if (match := BEHAVIOR_RE.search(_paragraph_text(paragraph))) is not None
        }
        if len(behavior_hits) != 1:
            raise GoldReviewImportError(f"{item_id}: expected exactly one unambiguous Behavior")
        expected_behavior = next(iter(behavior_hits))

        fields: dict[str, list[str]] = {
            "Claims": [],
            "Relevant chunk IDs": [],
            "Must not claim": [],
            "Notes": [],
        }
        current_field: str | None = None
        for paragraph in block:
            text = _paragraph_text(paragraph).strip()
            if _paragraph_style(paragraph) == "FieldLabel":
                current_field = text if text in fields else None
                continue
            if current_field is not None and text:
                fields[current_field].append(text)

        claims: list[dict[str, object]] = []
        for claim_index, row in enumerate(fields["Claims"], start=1):
            match = CLAIM_RE.fullmatch(row)
            if match is None:
                raise GoldReviewImportError(f"{item_id}: ambiguous claim row")
            claims.append(
                {
                    "claim_id": f"{item_id}.{claim_index}",
                    "text": " ".join(match.group(2).split()),
                    "essential": match.group(1).casefold() == "essential",
                    "supporting_chunk_ids": _split_ids(match.group(3)),
                }
            )

        relevant = _parse_relevant(
            fields["Relevant chunk IDs"],
            documents=documents,
            manifest_chunk_ids=manifest_chunk_ids,
            item_id=item_id,
        )
        must_not_claim = [
            " ".join(row.split())
            for row in fields["Must not claim"]
            if row.casefold() != "none supplied."
        ]
        note_rows = [row for row in fields["Notes"] if row.casefold() != "n/a"]
        items.append(
            {
                "id": item_id,
                "question": questions[0],
                "stratum": stratum,
                "expected_behavior": expected_behavior,
                "claims": claims,
                "relevant_chunk_ids": relevant,
                "must_not_claim": must_not_claim,
                "notes": "\n".join(note_rows),
            }
        )

    identifiers = [str(item["id"]) for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise GoldReviewImportError("final DOCX contains duplicate question IDs")
    if identifiers != sorted(identifiers, key=lambda value: int(value[1:])):
        raise GoldReviewImportError("final DOCX question IDs are not strictly ascending")

    gold: dict[str, object] = {
        "schema": "archivist.gold/1",
        "version": "1.0.0",
        "authored_against_corpus": manifest_sha256,
        "items": items,
    }
    try:
        validate_gold_set(
            gold,
            manifest,
            corpus_manifest_sha256=manifest_sha256,
            mode="run-of-record",
        )
    except GoldSetValidationError as exc:
        raise GoldReviewImportError(
            f"transcribed gold failed run-of-record validation ({len(exc.errors)} errors): "
            + "; ".join(exc.errors)
        ) from exc
    return gold


def parse_gold_from_docx(
    docx_path: Path,
    *,
    manifest: dict[str, object],
    manifest_sha256: str,
) -> dict[str, object]:
    try:
        with ZipFile(docx_path, "r") as archive:
            document_xml = archive.read("word/document.xml")
    except (OSError, KeyError) as exc:
        raise GoldReviewImportError(f"cannot read final DOCX {docx_path}: {exc}") from exc
    return parse_gold_from_document_xml(
        document_xml,
        manifest=manifest,
        manifest_sha256=manifest_sha256,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Finalize the private owner-review DOCX and write a validated private gold JSON."
        )
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--final-docx-output", type=Path, default=DEFAULT_FINAL_DOCX)
    parser.add_argument("--gold-output", type=Path, default=DEFAULT_GOLD_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--exclude", action="append", default=["H039"])
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.gold_output.exists() and not args.force:
        print(f"ERROR: refusing to overwrite existing output: {args.gold_output}", file=sys.stderr)
        return 2
    try:
        manifest = load_json_object(args.manifest, label="corpus manifest")
        manifest_sha256 = sha256_file(args.manifest)
        final_docx = write_final_docx(
            args.source,
            args.final_docx_output,
            excluded_ids=set(args.exclude),
            force=args.force,
        )
        gold = parse_gold_from_docx(
            final_docx,
            manifest=manifest,
            manifest_sha256=manifest_sha256,
        )
        args.gold_output.parent.mkdir(parents=True, exist_ok=True)
        args.gold_output.write_text(
            json.dumps(gold, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except (OSError, GoldSetValidationError, GoldReviewImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    counts = Counter(str(item["stratum"]) for item in gold["items"])
    print(
        "Prepared private canonical gold: "
        f"{len(gold['items'])} items across {len(counts)} strata; no question text emitted."
    )
    print(f"Final owner-review DOCX: {final_docx}")
    print(f"Private canonical JSON: {args.gold_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
