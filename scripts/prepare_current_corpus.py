from __future__ import annotations

import argparse
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from manuscript_docx import (  # noqa: E402
    DEFAULT_COLLECTION_NAME,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_HNSW_SPACE,
    ManuscriptPreparationError,
    prepare_docx_corpus,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare an authoritative DOCX as chaptered Markdown, deterministic chunks, "
            "and a text-free corpus manifest. Targets must be empty."
        )
    )
    parser.add_argument("source_docx", type=Path, help="Authoritative manuscript DOCX.")
    parser.add_argument(
        "--manuscript-dir",
        type=Path,
        default=BASE_DIR / "manuscript",
        help="Empty target directory for private Markdown files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BASE_DIR / "output",
        help="Empty target directory for chunks.json.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=BASE_DIR / "fixtures" / "corpus_manifest.json",
        help="New path for the text-free corpus manifest.",
    )
    parser.add_argument(
        "--title",
        help="Optional corpus/front-matter title override; Heading 1 text is never rewritten.",
    )
    parser.add_argument(
        "--ingest-commit",
        help="Git commit to record; defaults to the current repository HEAD when available.",
    )
    parser.add_argument(
        "--hnsw-space",
        default=DEFAULT_HNSW_SPACE,
        help=f"Vector-store distance space to record (default: {DEFAULT_HNSW_SPACE}).",
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"Embedding model to record (default: {DEFAULT_EMBEDDING_MODEL}).",
    )
    parser.add_argument(
        "--collection-name",
        default=DEFAULT_COLLECTION_NAME,
        help=f"Chroma collection name to record (default: {DEFAULT_COLLECTION_NAME}).",
    )
    parser.add_argument(
        "--embedded-chunk-count",
        type=int,
        default=0,
        help="Already embedded chunks to record; normally zero during preparation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        prepared = prepare_docx_corpus(
            source_docx=args.source_docx,
            manuscript_dir=args.manuscript_dir,
            output_dir=args.output_dir,
            manifest_path=args.manifest,
            title=args.title,
            ingest_commit=args.ingest_commit,
            hnsw_space=args.hnsw_space,
            embedding_model=args.embedding_model,
            collection_name=args.collection_name,
            embedded_chunk_count=args.embedded_chunk_count,
        )
    except ManuscriptPreparationError as exc:
        parser.error(str(exc))

    source = prepared.manifest["source"]
    print(f"Prepared {prepared.document_count} Markdown documents.")
    print(f"Built {prepared.chunk_count} deterministic chunks.")
    print(f"Source SHA-256: {source['sha256']}")
    print(f"Markdown: {prepared.manuscript_dir}")
    print(f"Chunks: {prepared.chunks_path}")
    print(f"Manifest: {prepared.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
