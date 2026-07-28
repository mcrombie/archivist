from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from edition_locators import EditionLocatorError, build_typeset_pdf_artifact  # noqa: E402


def extract_pdf_pages(path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise EditionLocatorError(
            "PDF extraction requires pypdf; install the locked project dependencies"
        ) from exc
    reader = PdfReader(path)
    return [page.extract_text() or "" for page in reader.pages]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the text-free July 6 typeset-PDF locator artifact from private inputs."
        )
    )
    parser.add_argument("pdf", type=Path, help="Private July 6 typeset PDF.")
    parser.add_argument(
        "--chunks",
        type=Path,
        default=BASE_DIR / "output" / "chunks.json",
        help="Private deterministic chunks JSON.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=BASE_DIR / "fixtures" / "corpus_manifest.json",
        help="Committed text-free corpus manifest.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BASE_DIR / "fixtures" / "edition_locators" / "typeset_pdf_0706.json",
        help="Text-free locator artifact to create.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    try:
        artifact = build_typeset_pdf_artifact(
            pdf_path=args.pdf,
            chunks_path=args.chunks,
            manifest_path=args.manifest,
            extract_pdf_pages=extract_pdf_pages,
        )
    except (EditionLocatorError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    locators = artifact["locators"]
    assert isinstance(locators, list)
    repeated = sum(int(item["repeated_anchor_count"] > 0) for item in locators)
    spans: dict[int, int] = {}
    for item in locators:
        span = int(item["physical_page_end"]) - int(item["physical_page_start"]) + 1
        spans[span] = spans.get(span, 0) + 1
    print(f"Wrote {len(locators)} text-free locators to {args.output}")
    print(f"Repeated-anchor locators resolved monotonically: {repeated}")
    print(f"Physical page spans: {dict(sorted(spans.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
