"""Build an ignored, private runtime bundle containing only the live corpus index."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import chromadb


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from rag_pipeline import preflight_answer_corpus  # noqa: E402
from web_project import (  # noqa: E402
    LEGACY_CHUNKS_FILE,
    chroma_client,
    collection_name,
    load_project_chunks,
    read_json,
)


BUNDLE_SCHEMA = "archivist.public_runtime_bundle/1"
CORPUS_MANIFEST = BASE_DIR / "fixtures" / "corpus_manifest.json"
DEFAULT_OUTPUT = BASE_DIR / "runtime" / "archivist-public-runtime.tar.gz"
BATCH_SIZE = 100


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_live_collection(destination: Path):
    source_collection = chroma_client().get_collection(name=collection_name("current"))
    records = source_collection.get(
        include=["embeddings", "metadatas"],
    )
    ids = list(records.get("ids") or [])
    embeddings = records.get("embeddings")
    metadatas = list(records.get("metadatas") or [])
    if embeddings is None or len(ids) != 481 or len(metadatas) != len(ids):
        raise RuntimeError("The source collection is incomplete.")

    destination.mkdir(parents=True, exist_ok=True)
    target_client = chromadb.PersistentClient(path=str(destination))
    target_collection = target_client.create_collection(
        name="manuscript",
        configuration={"hnsw": {"space": "l2"}},
        metadata=dict(source_collection.metadata or {}),
        embedding_function=None,
    )
    for start in range(0, len(ids), BATCH_SIZE):
        end = start + BATCH_SIZE
        target_collection.add(
            ids=ids[start:end],
            embeddings=embeddings[start:end].tolist(),
            metadatas=metadatas[start:end],
        )
    return target_client, target_collection


def build_bundle(output_path: Path) -> dict[str, object]:
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing bundle: {output_path}")
    if not LEGACY_CHUNKS_FILE.is_file() or not CORPUS_MANIFEST.is_file():
        raise FileNotFoundError("The private chunks or corpus manifest are unavailable.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = (output_path.parent / ".archivist-public-bundle-staging").resolve()
    if staging.parent != output_path.parent.resolve():
        raise RuntimeError("The staging directory escaped the selected output directory.")
    if staging.exists():
        raise FileExistsError(f"Refusing to replace existing staging directory: {staging}")
    staging.mkdir()
    target_client = None
    try:
        staged_chunks = staging / "output" / "chunks.json"
        staged_chunks.parent.mkdir(parents=True)
        staged_chunks.write_bytes(LEGACY_CHUNKS_FILE.read_bytes())
        target_client, target_collection = copy_live_collection(staging / "chroma_db")

        manifest = read_json(CORPUS_MANIFEST, None)
        manifest_sha256 = sha256_file(CORPUS_MANIFEST)
        chunks = load_project_chunks("current")
        integrity = preflight_answer_corpus(
            collection_handle=target_collection,
            chunks=chunks,
            corpus_manifest=manifest,
            corpus_manifest_sha256=manifest_sha256,
            require_store_identity=True,
        )
        if not integrity.passed:
            raise RuntimeError(
                "The staged public collection failed identity verification: "
                f"{', '.join(integrity.failure_codes)}"
            )

        collection_count = target_collection.count()
        bundle_manifest = {
            "schema": BUNDLE_SCHEMA,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "corpus_manifest_sha256": manifest_sha256,
            "chunks_sha256": sha256_file(staged_chunks),
            "collection_name": "manuscript",
            "collection_count": collection_count,
            "contents": ["chroma_db/", "output/chunks.json"],
        }
        (staging / "runtime_bundle.json").write_text(
            json.dumps(bundle_manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        target_client.close()
        target_client = None
        with tarfile.open(output_path, "w:gz") as archive:
            archive.add(staging / "chroma_db", arcname="chroma_db")
            archive.add(staging / "output", arcname="output")
            archive.add(
                staging / "runtime_bundle.json",
                arcname="runtime_bundle.json",
            )
    finally:
        if target_client is not None:
            target_client.close()
        shutil.rmtree(staging)

    return {
        **bundle_manifest,
        "bundle_path": str(output_path),
        "bundle_sha256": sha256_file(output_path),
        "bundle_bytes": output_path.stat().st_size,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a private, gitignored bundle for the single-instance public service."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination .tar.gz; an existing file is never overwritten.",
    )
    args = parser.parse_args(argv)
    try:
        result = build_bundle(args.output.resolve())
    except (FileExistsError, FileNotFoundError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
