from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Dict


BASE_DIR = Path(__file__).resolve().parent.parent
MANUSCRIPT_DIR = BASE_DIR / "manuscript"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_FILE = OUTPUT_DIR / "chunks.json"

PARAGRAPHS_PER_CHUNK = 4
PARAGRAPH_OVERLAP = 1


def read_markdown_files(manuscript_dir: Path) -> List[Path]:
    """Return all markdown files in sorted order."""
    return sorted(manuscript_dir.glob("*.md"))


def extract_chapter_title(text: str, fallback: str) -> str:
    """Extract the first level-1 markdown heading as the chapter title."""
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def clean_title_from_filename(stem: str) -> str:
    """Remove leading sort numbers/underscores from a filename stem."""
    return re.sub(r"^\d+[_\-\s]*", "", stem).strip()


def split_into_paragraphs(text: str) -> List[str]:
    """
    Split text into paragraphs.

    Assumes the manuscript export currently uses one paragraph per line,
    with no blank lines between paragraphs.
    """
    lines = text.splitlines()
    paragraphs: List[str] = []

    for line in lines:
        cleaned = line.strip()

        if not cleaned:
            continue
        if cleaned == "[IMAGE]":
            continue
        if cleaned.startswith("#"):
            continue

        paragraphs.append(cleaned)

    return paragraphs


def is_quote_paragraph(paragraph: str) -> bool:
    """
    Check if a paragraph starts with a quote
    """
    stripped = paragraph.strip()
    return stripped.startswith(("“", '"', "‘", "'"))


def is_weak_transition(paragraph: str) -> bool:
    """
    Determines if a paragraph is a poor place to begin a new chunk
    """
    stripped = paragraph.strip()
    lower = stripped.lower()

    weak_starts = (
        "or,",
        "and,",
        "but,",
        "however,",
        "thus,",
        "yet,",
        "indeed,",
        "for example,",
        "for instance,",
        "as another",
        "as one",
        "as this",
    )

    if lower.startswith(weak_starts):
        return True

    if len(stripped) < 120:
        return True

    return False


def is_quote_setup(paragraph: str) -> bool:
    """
    Check if a paragraph is to be followed by a quote
    """
    stripped = paragraph.strip()
    lower = stripped.lower()

    setup_phrases = (
        "said:",
        "wrote:",
        "declared:",
        "argued:",
        "claimed:",
        "observed:",
        "described:",
        "fumed:",
        "went so far as to say:",
        "as follows:",
    )

    if stripped.endswith(":"):
        return True

    if any(lower.endswith(phrase) for phrase in setup_phrases):
        return True

    return False


def adjust_chunk_start(paragraphs: list[str], proposed_start: int, previous_start: int) -> int:
    """
    Adjust a proposed chunk start to better respect rhetorical boundaries.
    """
    start = proposed_start

    if start <= previous_start or start >= len(paragraphs):
        return start

    current = paragraphs[start]

    # If starting on a quote, try to pull in its setup paragraph.
    if is_quote_paragraph(current) and start - 1 > previous_start:
        prev_para = paragraphs[start - 1]
        if is_quote_setup(prev_para):
            start -= 1
            return start

    # If starting on a weak transition, try to skip forward.
    if is_weak_transition(current) and start + 1 < len(paragraphs):
        start += 1
        return start

    return start


def chunk_paragraphs(
    paragraphs: list[str],
    chunk_size: int,
    overlap: int,
) -> list[dict[str, object]]:
    """
    Group paragraphs into overlapping chunks, using simple heuristics
    to improve rhetorical coherence.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: list[dict[str, object]] = []
    start = 0
    paragraph_count = len(paragraphs)

    while start < paragraph_count:
        end = min(start + chunk_size, paragraph_count)
        current_paragraphs = paragraphs[start:end]

        chunks.append({
            "paragraph_start": start + 1,
            "paragraph_end": end,
            "text": "\n\n".join(current_paragraphs),
        })

        if end == paragraph_count:
            break

        proposed_start = start + chunk_size - overlap
        next_start = adjust_chunk_start(paragraphs, proposed_start, start)

        if next_start <= start:
            next_start = start + 1

        start = next_start

    return chunks

def build_chunks_for_file(file_path: Path) -> List[Dict[str, object]]:
    """Read one markdown file and return chunk records."""
    text = file_path.read_text(encoding="utf-8")
    chapter_title = extract_chapter_title(text,fallback=clean_title_from_filename(file_path.stem))
    paragraphs = split_into_paragraphs(text)

    records: List[Dict[str, object]] = []
    paragraph_chunks = chunk_paragraphs(
        paragraphs,
        chunk_size=PARAGRAPHS_PER_CHUNK,
        overlap=PARAGRAPH_OVERLAP,
    )

    for i, chunk in enumerate(paragraph_chunks, start=1):
        records.append({
            "document": file_path.name,
            "chapter_title": chapter_title,
            "chunk_id": f"{file_path.stem}_{i:03}",
            "paragraph_start": chunk["paragraph_start"],
            "paragraph_end": chunk["paragraph_end"],
            "text": chunk["text"],
        })

    return records


def main() -> None:
    """Build chunks from all manuscript markdown files and save as JSON."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    files = read_markdown_files(MANUSCRIPT_DIR)
    if not files:
        print("No markdown files found in manuscript/")
        return

    all_chunks: List[Dict[str, object]] = []

    print(f"Found {len(files)} markdown files.\n")

    for file_path in files:
        file_chunks = build_chunks_for_file(file_path)
        all_chunks.extend(file_chunks)
        print(f"{file_path.name}: created {len(file_chunks)} chunks")

    OUTPUT_FILE.write_text(
        json.dumps(all_chunks, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nSaved {len(all_chunks)} total chunks to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()