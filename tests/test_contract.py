import hashlib
import inspect
import re

import ask
import web_project
from filters import SKIP_FILES
from ingest import PARAGRAPH_OVERLAP, PARAGRAPHS_PER_CHUNK
from prompts import (
    ANSWER_PROMPT_TEMPLATE,
    build_answer_prompt,
    build_index_prompt_cli,
    build_index_prompt_web,
)
from retrieval import (
    MAX_FINAL_SOURCES,
    MAX_PRIMARY_DISTANCE,
    build_context,
    finalize_context_chunks,
    finalize_index_context,
    retrieve,
)


CHUNKS = [
    dict(
        document="a.md", chapter_title="A", chunk_id="a_001",
        paragraph_start=1, paragraph_end=2, text="one\n\ntwo",
    ),
    dict(
        document="a.md", chapter_title="A", chunk_id="a_002",
        paragraph_start=2, paragraph_end=3, text="two\n\nneedle",
    ),
    dict(
        document="b.md", chapter_title="B", chunk_id="b_001",
        paragraph_start=1, paragraph_end=1, text="three",
    ),
]


def test_frozen_parameters():
    assert (MAX_PRIMARY_DISTANCE, MAX_FINAL_SOURCES) == (1.05, 8)
    assert inspect.signature(retrieve).parameters["n_results"].default == 5
    assert (PARAGRAPHS_PER_CHUNK, PARAGRAPH_OVERLAP) == (4, 1)
    assert SKIP_FILES == {
        "01_Front Matter.md",
        "02_Table of Contents.md",
        "03_Acknowledgments.md",
        "04_Note on Illustrations.md",
        "32_Bibliography.md",
    }


def test_context_snapshot_and_prompt_contract():
    expected = """[Source 1]
Document: a.md
Chapter: A
Chunk ID: a_001
Paragraphs: 1\N{EN DASH}2
Text:
one

two


[Source 2]
Document: a.md
Chapter: A
Chunk ID: a_002
Paragraphs: 2\N{EN DASH}3
Text:
two

needle


[Source 3]
Document: b.md
Chapter: B
Chunk ID: b_001
Paragraphs: 1\N{EN DASH}1
Text:
three
"""
    context = build_context(CHUNKS)
    assert context == expected
    assert re.findall(r"(?m)^\[Source\s+(\d+)\]$", context) == ["1", "2", "3"]
    assert hashlib.sha256(ANSWER_PROMPT_TEMPLATE.encode()).hexdigest() == (
        "b89dcdb0a520226708ad47830a421945cf1d1699ef99b3e013344756ab670a5a"
    )
    assert ask.build_answer_prompt is web_project.build_answer_prompt is build_answer_prompt


def test_prompts_never_receive_presentation_labels():
    payload = web_project.source_payload(CHUNKS)
    web_prompt = build_index_prompt_web("term", CHUNKS, CHUNKS[:1])
    prompts = [
        build_answer_prompt("question", CHUNKS),
        build_index_prompt_cli("term", CHUNKS),
        web_prompt,
    ]
    labels = {source["citation_label"] for source in payload["sources"]}
    assert all("\N{PILCROW SIGN}" not in prompt for prompt in prompts)
    assert all(label not in prompt for label in labels for prompt in prompts)
    assert re.findall(r"(?m)^\[Source (\d+)\]$", web_prompt) == ["1", "2", "3"]
    assert "Existing Index 1:" in web_prompt and "[Existing Index" not in web_prompt
    assert "<citation label>" not in web_prompt


def test_shared_finalizers_and_presentation_partition():
    results = {"metadatas": [[CHUNKS[1]]], "distances": [[0.2]]}
    assert [c["chunk_id"] for c in finalize_context_chunks(results, chunks=CHUNKS)] == [
        "a_002", "a_001",
    ]
    semantic = {"metadatas": [[CHUNKS[2]]], "distances": [[0.2]]}
    assert [c["chunk_id"] for c in finalize_index_context("needle", semantic, chunks=CHUNKS)] == [
        "a_002", "a_001", "b_001",
    ]
    assert finalize_index_context(
        " ", semantic, chunks=CHUNKS, empty_term_matches=False
    )[0] == CHUNKS[2]
    before = build_answer_prompt("question", CHUNKS)
    payload = web_project.source_payload(CHUNKS)
    grouped = [number for group in payload["display_groups"] for number in group["source_numbers"]]
    assert sorted(grouped) == [1, 2, 3] and len(grouped) == len(set(grouped))
    assert build_answer_prompt("question", CHUNKS) == before


def test_query_reports_missing_disk_chunk(monkeypatch, capsys):
    import query

    results = {"metadatas": [[{"chunk_id": "ghost_001"}]], "distances": [[0.2]]}
    monkeypatch.setattr(query, "retrieve", lambda *_args, **_kwargs: results)
    monkeypatch.setattr(query, "finalize_context_chunks", lambda _results: [])
    monkeypatch.setattr(query, "get_chunk_lookup", lambda: {})
    query.inspect_query("question")
    assert "dropped: missing from disk lookup" in capsys.readouterr().out
