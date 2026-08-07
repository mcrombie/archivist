from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Mapping, Sequence

import chromadb
from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from corpus import get_all_chunks  # noqa: E402
from evaluation_artifacts import (  # noqa: E402
    build_corpus_identity,
    build_git_worktree_identity,
)
from gold_provenance import (  # noqa: E402
    GoldProvenanceValidationError,
    validate_gold_provenance_file,
)
from gold_set import GoldSetValidationError, validate_gold_set_file  # noqa: E402
from rag_pipeline import preflight_answer_corpus  # noqa: E402
from retrieval_benchmark import (  # noqa: E402
    PROVIDER_BATCH_WORST_CASE_USD,
    RetrievalBenchmarkError,
    build_benchmark_artifact,
    embedding_preflight_summary,
    evaluate_item,
    load_locked_gold,
    request_query_embedding_cache,
    select_noise_subset,
    sha256_file,
    validate_embedding_cache,
    write_json_atomic,
)

from validate_gold_holdout import CandidateLockError, validate_candidate_lock  # noqa: E402


DEFAULT_GOLD = BASE_DIR / "fixtures" / "gold_set.json"
DEFAULT_PROVENANCE = BASE_DIR / "fixtures" / "gold_set.provenance.json"
DEFAULT_MANIFEST = BASE_DIR / "fixtures" / "corpus_manifest.json"
DEFAULT_REGISTRY = BASE_DIR / "fixtures" / "development_question_registry.json"
DEFAULT_COMMITMENT = BASE_DIR / "fixtures" / "gold_questions.commitment.json"
DEFAULT_CHUNKS = BASE_DIR / "output" / "chunks.json"
DEFAULT_CACHE = BASE_DIR / "runtime" / "evaluations" / "retrieval-query-embeddings.json"
DEFAULT_OUTPUT = BASE_DIR / "runtime" / "evaluations" / "retrieval-benchmark-v1.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the locked, retrieval-only dense-versus-hybrid benchmark. "
            "No answer, planner, generator, or judge model is invoked."
        )
    )
    parser.add_argument("command", choices=("preflight", "embed", "score", "run"))
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--question-commitment", type=Path, default=DEFAULT_COMMITMENT)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--embedding-cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--authorize-openai-query-embeddings",
        action="store_true",
        help=(
            "Required before a missing cache may send the 37 locked question strings "
            "to OpenAI text-embedding-3-small in one request."
        ),
    )
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        help="Owner-authorized maximum cost for the one embedding operation.",
    )
    return parser


def _validated_gold(args: argparse.Namespace):
    gold = load_locked_gold(args.gold, args.provenance)
    validate_gold_set_file(args.gold, args.manifest, mode="run-of-record")
    validate_gold_provenance_file(
        args.provenance,
        args.gold,
        args.manifest,
        args.registry,
        args.question_commitment,
        expected_gold_set_path="fixtures/gold_set.json",
        expected_candidate_commit=gold.candidate_commit,
        expected_rag_policy=gold.candidate_rag_policy,
        repository_root=BASE_DIR,
    )
    return gold


def _require_clean_candidate(gold) -> dict[str, object]:
    validate_candidate_lock(BASE_DIR, gold.candidate_commit)
    identity = build_git_worktree_identity(BASE_DIR)
    if identity.get("working_tree") != "clean":
        raise RetrievalBenchmarkError("run-of-record benchmark requires a clean working tree")
    return identity


def _load_manifest(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RetrievalBenchmarkError("corpus manifest must be a JSON object")
    return value


def _collection_and_corpus(args: argparse.Namespace, gold):
    corpus_identity = build_corpus_identity(
        manifest_path=args.manifest,
        chunks_path=args.chunks,
    )
    if corpus_identity["corpus_manifest_sha256"] != gold.corpus_manifest_sha256:
        raise RetrievalBenchmarkError("active corpus does not match locked gold provenance")
    manifest = _load_manifest(args.manifest)
    store = manifest.get("store")
    if not isinstance(store, Mapping):
        raise RetrievalBenchmarkError("corpus manifest store identity is missing")
    collection_name = str(store.get("collection_name") or "")
    if not collection_name:
        raise RetrievalBenchmarkError("corpus manifest collection name is missing")
    client = chromadb.PersistentClient(path=str(BASE_DIR / "chroma_db"))
    collection = client.get_collection(name=collection_name, embedding_function=None)
    chunks = get_all_chunks()
    integrity = preflight_answer_corpus(
        collection_handle=collection,
        chunks=chunks,
        corpus_manifest=manifest,
        corpus_manifest_sha256=str(corpus_identity["corpus_manifest_sha256"]),
        require_store_identity=True,
    )
    if not integrity.passed:
        raise RetrievalBenchmarkError(
            "active corpus/index integrity failed: " + ", ".join(integrity.failure_codes)
        )
    corpus_trace = {
        "collection_name": corpus_identity["collection_name"],
        "collection_count": int(collection.count()),
        "corpus_manifest_sha256": corpus_identity["corpus_manifest_sha256"],
        "chunks_sha256": corpus_identity["chunks_sha256"],
        "hnsw_space": corpus_identity["hnsw_space"],
    }
    return collection, chunks, corpus_identity, corpus_trace


def _print_preflight(
    gold,
    args: argparse.Namespace,
    *,
    corpus_identity: Mapping[str, object],
) -> None:
    summary = embedding_preflight_summary(gold)
    identity = build_git_worktree_identity(BASE_DIR)
    print("VALID RETRIEVAL BENCHMARK PREFLIGHT")
    print(f"Locked items: {summary['question_count']}")
    print(f"Question-set SHA-256: {summary['question_set_sha256']}")
    print(f"Gold-set SHA-256: {summary['gold_set_sha256']}")
    print(f"Candidate: {gold.candidate_commit} / {gold.candidate_rag_policy}")
    print(f"Working tree: {identity['working_tree']}")
    print(
        "Local corpus/index: "
        f"{corpus_identity['embedded_chunk_count']} chunks, "
        f"{corpus_identity['hnsw_space']} distance, identity verified"
    )
    print(
        "External scope if authorized: one OpenAI text-embedding-3-small request "
        f"containing {summary['question_count']} locked question strings only"
    )
    print(
        "Provider-hard-limit worst case at the current rate: "
        f"${summary['provider_batch_worst_case_usd']:.4f}"
    )
    if args.embedding_cache.is_file():
        cache = json.loads(args.embedding_cache.read_text(encoding="utf-8"))
        if not isinstance(cache, Mapping):
            raise RetrievalBenchmarkError("existing embedding cache is malformed")
        validate_embedding_cache(cache, gold)
        print(f"Embedding cache: valid ({args.embedding_cache})")
    else:
        print(f"Embedding cache: absent ({args.embedding_cache})")


def _create_cache(args: argparse.Namespace, gold) -> dict[str, object]:
    if args.embedding_cache.exists():
        cache = json.loads(args.embedding_cache.read_text(encoding="utf-8"))
        if not isinstance(cache, Mapping):
            raise RetrievalBenchmarkError("existing embedding cache is malformed")
        validate_embedding_cache(cache, gold)
        print("Reusing the existing locked query-embedding cache; no API call made.")
        return dict(cache)

    if not args.authorize_openai_query_embeddings:
        raise RetrievalBenchmarkError(
            "embedding cache is missing; explicit OpenAI query-embedding authorization is required"
        )
    if args.max_cost_usd is None:
        raise RetrievalBenchmarkError("--max-cost-usd is required for the paid embedding operation")
    if not math.isfinite(args.max_cost_usd) or args.max_cost_usd <= 0:
        raise RetrievalBenchmarkError("--max-cost-usd must be a finite positive number")
    if args.max_cost_usd + 1e-12 < PROVIDER_BATCH_WORST_CASE_USD:
        raise RetrievalBenchmarkError(
            "authorized ceiling is below the single-request provider-limit worst case "
            f"(${PROVIDER_BATCH_WORST_CASE_USD:.4f})"
        )
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RetrievalBenchmarkError("OPENAI_API_KEY is unavailable")

    print(
        "AUTHORIZED EXTERNAL OPERATION: sending only the locked question strings "
        "to OpenAI text-embedding-3-small in one request; automatic retries disabled."
    )
    client = OpenAI(api_key=api_key, max_retries=0)
    cache = request_query_embedding_cache(gold, embedding_client=client)
    write_json_atomic(args.embedding_cache, cache)
    usage = cache.get("usage")
    estimated_cost = usage.get("estimated_cost_usd") if isinstance(usage, Mapping) else None
    if isinstance(estimated_cost, (int, float)):
        if float(estimated_cost) > args.max_cost_usd + 1e-12:
            raise RetrievalBenchmarkError("recorded embedding cost exceeded the authorized ceiling")
        print(f"Recorded estimated embedding cost: ${float(estimated_cost):.8f}")
    print(f"Wrote private text-free embedding cache: {args.embedding_cache}")
    return cache


def _load_cache(args: argparse.Namespace, gold) -> dict[str, object]:
    if not args.embedding_cache.is_file():
        raise RetrievalBenchmarkError(
            "embedding cache is missing; run the authorized embed command first"
        )
    value = json.loads(args.embedding_cache.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise RetrievalBenchmarkError("embedding cache must be a JSON object")
    validate_embedding_cache(value, gold)
    return dict(value)


def _require_output_absent(args: argparse.Namespace) -> None:
    if args.output.exists():
        raise RetrievalBenchmarkError(
            f"benchmark output already exists and will not be overwritten: {args.output}"
        )


def _score(args: argparse.Namespace, gold, cache: Mapping[str, object]) -> dict[str, object]:
    _require_output_absent(args)
    run_identity = _require_clean_candidate(gold)
    collection, chunks, corpus_identity, corpus_trace = _collection_and_corpus(args, gold)
    embeddings = validate_embedding_cache(cache, gold)

    item_results = [
        evaluate_item(
            item,
            embeddings[str(item["id"])],
            collection=collection,
            chunks=chunks,
            corpus_trace=corpus_trace,
        )
        for item in gold.items
    ]
    by_id = {str(item["id"]): item for item in item_results}
    gold_by_id = {str(item["id"]): item for item in gold.items}
    subset_ids = select_noise_subset(gold.items)
    noise_repetitions: list[list[Mapping[str, object]]] = [
        [by_id[item_id] for item_id in subset_ids]
    ]
    for _ in range(4):
        noise_repetitions.append(
            [
                evaluate_item(
                    gold_by_id[item_id],
                    embeddings[item_id],
                    collection=collection,
                    chunks=chunks,
                    corpus_trace=corpus_trace,
                )
                for item_id in subset_ids
            ]
        )

    artifact = build_benchmark_artifact(
        gold=gold,
        embedding_cache=cache,
        item_results=item_results,
        noise_repetitions=noise_repetitions,
        run_identity=run_identity,
        corpus_identity=corpus_identity,
        embedding_cache_sha256=sha256_file(args.embedding_cache),
    )
    write_json_atomic(args.output, artifact)
    comparison = artifact["comparison"]
    assert isinstance(comparison, Mapping)
    print("VALID RETRIEVAL-ONLY BENCHMARK")
    print(f"Items: {len(item_results)}")
    print(f"Primary metric: {comparison['metric']}")
    print(f"Dense: {comparison['dense']}")
    print(f"Hybrid: {comparison['hybrid']}")
    print(f"Hybrid - dense: {comparison['hybrid_minus_dense']}")
    print(f"Wrote private text-free result: {args.output}")
    return artifact


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        gold = _validated_gold(args)
        if args.command == "preflight":
            _, _, corpus_identity, _ = _collection_and_corpus(args, gold)
            _print_preflight(gold, args, corpus_identity=corpus_identity)
            return 0

        _require_clean_candidate(gold)
        _collection_and_corpus(args, gold)
        if args.command == "embed":
            _create_cache(args, gold)
            return 0
        if args.command == "score":
            _require_output_absent(args)
            cache = _load_cache(args, gold)
            _score(args, gold, cache)
            return 0

        _require_output_absent(args)
        cache = _create_cache(args, gold)
        _score(args, gold, cache)
        return 0
    except (
        CandidateLockError,
        GoldProvenanceValidationError,
        GoldSetValidationError,
        OSError,
        RetrievalBenchmarkError,
        ValueError,
    ) as exc:
        errors = getattr(exc, "errors", (str(exc),))
        print(f"RETRIEVAL BENCHMARK FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
