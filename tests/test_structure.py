import ast
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APRIL_B1_CHUNKS_SHA256 = "4bafe77847f4956113e4f4ee874008e239f1b1274ac8495d0a9c21ff712f1d59"


def test_retrieval_primitives_have_one_definition():
    counts = {}
    for path in (ROOT / "src").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                counts[node.name] = counts.get(node.name, 0) + 1
    for name in (
        "embed_query", "get_filtered_primary_chunks", "expand_with_neighbors",
        "find_exact_match_chunks", "finalize_context_chunks", "finalize_index_context",
        "build_context",
    ):
        assert counts.get(name) == 1, (
            f"{name}: expected one definition, found {counts.get(name, 0)}"
        )


def test_imports_do_not_load_the_corpus():
    code = (
        "import dotenv; dotenv.load_dotenv=lambda *a,**k:False; "
        "import corpus; "
        "corpus.load_chunks=lambda *a,**k:(_ for _ in()).throw(AssertionError('eager load')); "
        "import retrieval,ask,query,web_project,index_mode"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    env.pop("OPENAI_API_KEY", None)
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, check=True)


def test_private_corpus_paths_are_untracked_and_ignored():
    tracked = subprocess.check_output(
        ["git", "ls-files", "--", "manuscript", "output", "projects"], cwd=ROOT, text=True
    )
    assert not tracked.strip()
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {"manuscript/", "output/", "projects/"} <= set(ignore)


def test_corpus_manifest_matches_private_disk_snapshot():
    manifest_path = ROOT / "fixtures" / "corpus_manifest.json"
    if not manifest_path.exists():
        pytest.skip("corpus manifest has not been generated")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifest_schema"] == "archivist.corpus_manifest/1"
    assert all("text" not in chunk for chunk in manifest["chunks"])

    manuscript_dir = ROOT / "manuscript"
    chunks_path = ROOT / "output" / "chunks.json"
    if not manuscript_dir.exists() or not chunks_path.exists():
        pytest.skip("private corpus is absent")

    from ingest import extract_chapter_title, split_into_paragraphs

    chunks_bytes = chunks_path.read_bytes()
    chunks = json.loads(chunks_bytes.decode("utf-8"))
    assert manifest["chunks_sha256"] == hashlib.sha256(chunks_bytes).hexdigest()

    paths = sorted(manuscript_dir.glob("*.md"), key=lambda path: path.name)
    documents = {item["filename"]: item for item in manifest["documents"]}
    assert set(documents) == {path.name for path in paths}
    chunk_counts = Counter(str(chunk["document"]) for chunk in chunks)

    for path in paths:
        source = path.read_bytes()
        text = source.decode("utf-8")
        document = documents[path.name]
        assert document["sha256"] == hashlib.sha256(source).hexdigest()
        assert document["paragraph_count"] == len(split_into_paragraphs(text))
        assert document["chunk_count"] == chunk_counts[path.name]
        assert document["chapter_title"] == extract_chapter_title(text, fallback=path.stem)

    chunk_manifest = {item["chunk_id"]: item for item in manifest["chunks"]}
    assert set(chunk_manifest) == {str(chunk["chunk_id"]) for chunk in chunks}
    for chunk in chunks:
        item = chunk_manifest[str(chunk["chunk_id"])]
        text = str(chunk["text"])
        assert item == {
            "chunk_id": chunk["chunk_id"],
            "document": chunk["document"],
            "paragraph_start": chunk["paragraph_start"],
            "paragraph_end": chunk["paragraph_end"],
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "char_count": len(text),
        }


def test_annotation_is_noop_for_retrieval_eligible_chunks():
    path = ROOT / "output" / "chunks.json"
    if not path.exists():
        pytest.skip("private corpus is absent")
    from filters import should_skip_document
    from web_project import annotate_chapter_titles

    chunks = json.loads(path.read_text(encoding="utf-8"))
    annotated = annotate_chapter_titles(chunks)
    mismatches = [
        original
        for original, changed in zip(chunks, annotated)
        if original.get("chapter_title") != changed.get("chapter_title")
    ]
    assert not [
        chunk for chunk in mismatches
        if not should_skip_document(chunk.get("document", ""))
    ]
    assert all(should_skip_document(chunk.get("document", "")) for chunk in mismatches)


def test_chroma_text_provenance_matches_disk():
    chunks_path, db_path = ROOT / "output" / "chunks.json", ROOT / "chroma_db"
    if not chunks_path.exists() or not db_path.exists():
        pytest.skip("private corpus index is absent")
    import chromadb

    from filters import should_skip_document

    chunks = {
        c["chunk_id"]: c
        for c in json.loads(chunks_path.read_text(encoding="utf-8"))
        if not should_skip_document(c.get("document", ""))
    }
    try:
        collection = chromadb.PersistentClient(path=str(db_path)).get_collection("manuscript")
        records = collection.get(include=["metadatas"])
    except Exception:
        pytest.skip("private corpus collection is absent")
    assert collection.count() == len(chunks)
    assert len(records["ids"]) == len(chunks)
    assert set(records["ids"]) == set(chunks)
    manifest_path = ROOT / "fixtures" / "corpus_manifest.json"
    if manifest_path.exists():
        store = json.loads(manifest_path.read_text(encoding="utf-8"))["store"]
        assert store["embedded_chunk_count"] == len(chunks)
        assert collection.metadata["embedding_model"] == store["embedding_model"]
        assert collection.metadata["hnsw:space"] == store["hnsw_space"]
        assert collection.configuration["hnsw"]["space"] == store["hnsw_space"]
    for chunk_id, metadata in zip(records["ids"], records["metadatas"]):
        assert hashlib.sha256(metadata["text"].encode()).digest() == hashlib.sha256(
            chunks[chunk_id]["text"].encode()
        ).digest()


@pytest.mark.skipif(os.getenv("ARCHIVIST_RUN_LIVE_B1") != "1", reason="live B1 check is opt-in")
def test_live_retrieval_matches_prechange_fixture():
    fixture_path = ROOT / "fixtures" / "b1_pre_change_chunk_ids.json"
    chunks_path = ROOT / "output" / "chunks.json"
    if not fixture_path.exists() or not chunks_path.exists():
        pytest.skip("private corpus or fixture is absent")
    if hashlib.sha256(chunks_path.read_bytes()).hexdigest() != APRIL_B1_CHUNKS_SHA256:
        pytest.skip("the frozen B1 fixture belongs to the April corpus cohort")
    from retrieval import finalize_context_chunks, retrieve
    from web_project import load_project_chunks, retrieve_project

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))["questions"]
    web_chunks = load_project_chunks("current")

    def ids(chunks):
        return [str(chunk.get("chunk_id")) for chunk in chunks]

    for question, expected in fixture.items():
        results = retrieve(question, n_results=5)
        assert ids(results.get("metadatas", [[]])[0]) == expected["primary"]
        cli_ids = ids(finalize_context_chunks(results))
        assert cli_ids == expected["context"]
        web_results = retrieve_project("current", question, n_results=5)
        assert ids(web_results.get("metadatas", [[]])[0]) == expected["primary"]
        assert ids(finalize_context_chunks(web_results, chunks=web_chunks)) == cli_ids
