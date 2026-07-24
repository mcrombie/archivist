import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from corpus import get_all_chunks
from costs import tracked_responses_create
from model_config import GENERATOR_SETTINGS
from prompts import build_answer_prompt
from query_planning import ResolvedTurn
from rag_pipeline import run_evidence_planned_answer
from retrieval import (
    collection,
    default_openai_client,
    finalize_context_chunks,
    retrieve,
)


BASE_DIR = Path(__file__).resolve().parent.parent


def answer_question_legacy(question: str, n_results: int = 5):
    results = retrieve(question, n_results=n_results)
    final_chunks = finalize_context_chunks(results)
    prompt = build_answer_prompt(question, final_chunks)

    response = tracked_responses_create(
        default_openai_client(),
        operation="answer_generation",
        input=prompt,
        **GENERATOR_SETTINGS.responses_create_kwargs(),
    )

    return response.output_text, final_chunks


def answer_question_result(question: str, n_results: int = 5):
    """Answer through the same evidence-planned core used by the web app."""
    manifest_path = BASE_DIR / "fixtures" / "corpus_manifest.json"
    chunks_path = BASE_DIR / "output" / "chunks.json"
    corpus_manifest: Mapping[str, object] | None = None
    manifest_sha256: str | None = None
    if manifest_path.is_file():
        corpus_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    corpus_trace: dict[str, object] = {"collection_name": "manuscript"}
    if chunks_path.is_file():
        corpus_trace["chunks_sha256"] = hashlib.sha256(
            chunks_path.read_bytes()
        ).hexdigest()
    if manifest_sha256 is not None:
        corpus_trace["corpus_manifest_sha256"] = manifest_sha256
    configuration = getattr(collection, "configuration", {})
    if isinstance(configuration, Mapping):
        hnsw = configuration.get("hnsw")
        if isinstance(hnsw, Mapping):
            corpus_trace["hnsw_space"] = str(hnsw.get("space") or "")

    result = run_evidence_planned_answer(
        resolved_turn=ResolvedTurn(
            standalone_question=question,
            trusted_user_texts=(question,),
        ),
        collection_handle=collection,
        chunks=get_all_chunks(),
        client=default_openai_client(),
        n_results=n_results,
        corpus_trace=corpus_trace,
        corpus_manifest=corpus_manifest,
        corpus_manifest_sha256=manifest_sha256,
        require_store_identity=True,
    )
    return result


def answer_question(question: str, n_results: int = 5):
    """Compatibility wrapper for the interactive terminal."""
    result = answer_question_result(question, n_results=n_results)
    return result.answer, result.final_chunks


def main() -> None:
    while True:
        question = input("\nAsk a question (or 'exit'): ").strip()

        if question.lower() == "exit":
            break

        answer, final_chunks = answer_question(question)

        print("\nAnswer:\n")
        print(answer)

        print("\nSources shown to model:\n")
        for i, chunk in enumerate(final_chunks, start=1):
            print(f"Source {i}")
            print(f"  Document: {chunk.get('document', 'N/A')}")
            print(f"  Chapter: {chunk.get('chapter_title', 'N/A')}")
            print(f"  Chunk ID: {chunk.get('chunk_id', 'N/A')}")
            print(f"  Paragraphs: {chunk.get('paragraph_start', '?')}–{chunk.get('paragraph_end', '?')}")
            print("-" * 60)


if __name__ == "__main__":
    main()
