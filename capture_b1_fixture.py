"""
Capture the Brief 1 "before" fixture.

Run this BEFORE any Brief 1 refactoring begins. It records which chunks the
current code retrieves for a fixed set of questions, so that after the refactor
you can prove the behavior did not change.

Records chunk IDs only -- no manuscript text -- so the output is safe to commit.

Usage, from the repository root:

    python capture_b1_fixture.py

Writes:  fixtures/b1_questions.json          (the frozen question list)
         fixtures/b1_pre_change_chunk_ids.json

Commit both before touching any other file.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
FIXTURES_DIR = BASE_DIR / "fixtures"

sys.path.insert(0, str(SRC_DIR))

import retrieval  # noqa: E402  (must follow the sys.path insert)


# Ten questions spanning easy -> hard. These are a smoke fixture for proving
# Brief 1 changed nothing; they are NOT the gold set. Edit them if you like,
# but freeze them before you run, and do not change them afterwards.
QUESTIONS = [
    # focused / biographical
    "What does the manuscript say about Paquiquineo?",
    "Who was Edwin Sandys and what did he do?",
    # focused / analytical
    "What role did Jamestown play as a corporate experiment?",
    "How did the headright system work?",
    "What was the Starving Time and how did the Virginia Company describe it?",
    # conceptual
    "What does the manuscript say about propaganda in the interwar period?",
    "How does the manuscript treat the relationship between tobacco and labor?",
    # broad / thematic
    "What does the manuscript say about slavery?",
    "How did Virginia's relationship with westward expansion change over time?",
    # out of corpus
    "What does the manuscript say about the founding of Oregon?",
]


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=BASE_DIR, text=True
        ).strip()
    except Exception:
        return "unknown"


def working_tree_state() -> str:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=BASE_DIR, text=True
        )
        return "clean" if not out.strip() else "dirty"
    except Exception:
        return "unknown"


def chunk_ids_for(question: str) -> dict[str, list[str]]:
    """Return both the raw retrieval hits and the finalized context set."""
    results = retrieval.retrieve(question, n_results=5)

    metadatas = results.get("metadatas", [[]])[0]
    primary = [str(m.get("chunk_id")) for m in metadatas]

    final_chunks = retrieval.finalize_context_chunks(results)
    context = [str(c.get("chunk_id")) for c in final_chunks]

    return {"primary": primary, "context": context}


def capture() -> dict[str, dict[str, list[str]]]:
    captured: dict[str, dict[str, list[str]]] = {}
    for i, question in enumerate(QUESTIONS, start=1):
        print(f"  [{i:2}/{len(QUESTIONS)}] {question[:60]}")
        captured[question] = chunk_ids_for(question)
    return captured


def main() -> None:
    FIXTURES_DIR.mkdir(exist_ok=True)

    print("Pass 1 of 2 -- capturing")
    first = capture()

    print("\nPass 2 of 2 -- checking the result is stable")
    second = capture()

    if first != second:
        print("\n*** UNSTABLE ***")
        print("The same questions produced different chunks on two consecutive runs.")
        print("Do NOT proceed with Brief 1. An equality assertion against a fixture")
        print("that is not reproducible would fail for reasons unrelated to the")
        print("refactor. Investigate the source of the variance first.")
        for question in QUESTIONS:
            if first[question] != second[question]:
                print(f"\n  differs: {question}")
                print(f"    run 1 context: {first[question]['context']}")
                print(f"    run 2 context: {second[question]['context']}")
        sys.exit(1)

    payload = {
        "fixture_schema": "archivist.b1_pre_change/1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_commit(),
        "working_tree": working_tree_state(),
        "retrieval_params": {
            "n_results": 5,
            "max_primary_distance": retrieval.MAX_PRIMARY_DISTANCE,
            "max_final_sources": retrieval.MAX_FINAL_SOURCES,
        },
        "questions": first,
    }

    (FIXTURES_DIR / "b1_questions.json").write_text(
        json.dumps({"questions": QUESTIONS}, indent=2), encoding="utf-8"
    )
    (FIXTURES_DIR / "b1_pre_change_chunk_ids.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    print("\nStable across both passes.")
    print(f"Wrote {FIXTURES_DIR / 'b1_questions.json'}")
    print(f"Wrote {FIXTURES_DIR / 'b1_pre_change_chunk_ids.json'}")
    print("\nCommit both files now, before starting Brief 1.")

    if payload["working_tree"] != "clean":
        print("\nNote: your working tree is dirty. Consider committing or stashing")
        print("first, so the fixture's `commit` field actually describes the code")
        print("that produced it.")


if __name__ == "__main__":
    main()
