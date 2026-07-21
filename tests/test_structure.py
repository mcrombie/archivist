import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


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
    assert [chunk["chunk_id"] for chunk in mismatches] == [
        f"02_Table of Contents_{number:03}" for number in range(1, 9)
    ]


def test_chroma_text_provenance_matches_disk():
    chunks_path, db_path = ROOT / "output" / "chunks.json", ROOT / "chroma_db"
    if not chunks_path.exists() or not db_path.exists():
        pytest.skip("private corpus index is absent")
    import chromadb

    chunks = {c["chunk_id"]: c for c in json.loads(chunks_path.read_text(encoding="utf-8"))}
    try:
        collection = chromadb.PersistentClient(path=str(db_path)).get_collection("manuscript")
        records = collection.get(include=["metadatas"])
    except Exception:
        pytest.skip("private corpus collection is absent")
    for chunk_id, metadata in zip(records["ids"], records["metadatas"]):
        assert chunk_id in chunks
        assert hashlib.sha256(metadata["text"].encode()).digest() == hashlib.sha256(
            chunks[chunk_id]["text"].encode()
        ).digest()


@pytest.mark.skipif(os.getenv("ARCHIVIST_RUN_LIVE_B1") != "1", reason="live B1 check is opt-in")
def test_live_retrieval_matches_prechange_fixture():
    fixture_path = ROOT / "fixtures" / "b1_pre_change_chunk_ids.json"
    if not fixture_path.exists() or not (ROOT / "output" / "chunks.json").exists():
        pytest.skip("private corpus or fixture is absent")
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
