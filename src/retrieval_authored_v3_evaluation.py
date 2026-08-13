"""Isolated evaluation adapter for the retrieval-authored-v3 Professional cohort.

The frozen V26 runner remains the historical record.  This module defines a
new cohort that reuses the already validated held-out query vectors, executes
the current deterministic retrieval/dossier path locally, and makes at most
one no-retry authoring operation per item.  All artifacts live below an
ignored private runtime root.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import sqlite3
import subprocess
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import Any
from uuid import uuid4

from archivist_modes import ArchivistMode, settings_for_archivist_mode
from authored_response import (
    AUTHORED_RESPONSE_INPUT_SCHEMA,
    AUTHORED_RESPONSE_OUTPUT_SCHEMA,
    AUTHORED_RESPONSE_POLICY_VERSION,
    AUTHORED_RESPONSE_RENDERER_VERSION,
    AUTHORED_RESPONSE_SETTINGS,
    MAX_AUTHORED_RESPONSE_OUTPUT_TOKENS,
    AuthoredFailureCode,
    AuthoredResponse,
    AuthoredResponseResult,
    AuthoredResponseStatus,
    authored_response_prompt_metadata,
    generate_authored_response,
    validate_and_render_authored_response,
)
from character_conversation import is_character_conversation_question
from corpus import get_all_chunks
from costs import UsageLedger, usage_scope
from evaluation_artifacts import build_corpus_identity, build_git_worktree_identity
from evaluation_judge import (
    ITEM_RUBRIC_PROMPT_SHA256,
    ITEM_RUBRIC_PROMPT_VERSION,
    JUDGE_MODEL,
    JUDGE_SETTINGS,
    build_item_rubric_input,
)
from evaluation_scoring import audit_citations
from evidence_compiler import compile_evidence_packet, render_direct_evidence_answer
from evidence_dossier import (
    DEFAULT_HARD_EVIDENCE_TOKEN_LIMIT,
    DEFAULT_MAX_DOSSIER_UNITS,
    DEFAULT_MIN_DOSSIER_UNITS,
    DEFAULT_TARGET_EVIDENCE_TOKENS,
    RetrievalDossier,
    build_retrieval_dossier,
)
from gold_provenance import normalized_question_sha256
from query_planning import ResolvedTurn
from rag_pipeline import preflight_answer_corpus
from retrieval import (
    BM25_B,
    BM25_K1,
    HYBRID_RETRIEVAL_VERSION,
    LEXICAL_CANDIDATE_LIMIT,
    LEXICAL_WEIGHT,
    MAX_FINAL_SOURCES,
    MAX_PRIMARY_DISTANCE,
    RRF_K,
    SEMANTIC_CANDIDATE_LIMIT,
    SEMANTIC_WEIGHT,
    build_hybrid_results,
    plan_context_chunks,
)
from retrieval_benchmark import (
    K_VALUES,
    LockedGold,
    load_locked_gold,
    sha256_file,
    validate_embedding_cache,
)


V3_EVALUATION_SCHEMA = "archivist.retrieval_authored_v3_evaluation/1"
V3_COHORT_MANIFEST_SCHEMA = "archivist.retrieval_authored_v3_cohort_manifest/1"
V3_GENERATION_INTENT_SCHEMA = "archivist.retrieval_authored_v3_generation_intent/1"
V3_GENERATION_OUTCOME_SCHEMA = "archivist.retrieval_authored_v3_generation_outcome/1"
V3_DECOMPOSITION_INTENT_SCHEMA = "archivist.retrieval_authored_v3_decomposition_intent/1"
V3_DECOMPOSITION_OUTCOME_SCHEMA = "archivist.retrieval_authored_v3_decomposition_outcome/1"
V3_RUBRIC_INTENT_SCHEMA = "archivist.retrieval_authored_v3_rubric_intent/1"
V3_RUBRIC_OUTCOME_SCHEMA = "archivist.retrieval_authored_v3_rubric_outcome/1"
V3_INSTRUMENT_FREEZE_SCHEMA = "archivist.retrieval_authored_v3_instrument_freeze/1"
V3_PUBLIC_SUMMARY_SCHEMA = "archivist.retrieval_authored_v3_public_summary/1"

EVALUATION_ID = "retrieval-authored-v3-professional-2026-08-13"
COHORT_CLASSIFICATION = "reused_locked_benchmark_not_pristine_held_out"
PRODUCT_COMMIT = "4e9d6ed01a7ed1d92f2124aefc07c3259675f1ad"
MASTER_REQUEST_ID = f"{EVALUATION_ID}-master"
MASTER_PROJECT_ID = "archivist-v3-evaluation"
MASTER_CONVERSATION_ID = EVALUATION_ID
MASTER_COST_CAP_NANO_USD = 7_000_000_000
MASTER_COST_CAP_USD = Decimal("7.00")

EXPECTED_GOLD_SHA256 = "72c4e8450a40dcf608757abd1244fe45cb57d3c1c1daccee10bedf4283e8f2f2"
EXPECTED_PROVENANCE_SHA256 = "b4a023cce4639558ce5c26dc1ec473e072bef72ba2fb77dfab8b7d61ddc4ae6a"
EXPECTED_COMMITMENT_SHA256 = "7e5dcb7f92fbb03f5943b0913d37486355de6b658d734d3bc262cafeda0f1f0c"
EXPECTED_MANIFEST_SHA256 = "b7ff94315a3f1f28c831e2c3ca62c385567d2b1447c19ff45139d175c3ff3c17"
EXPECTED_CHUNKS_SHA256 = "02e87cd42dc366a04f4b1ec43936599475cf18d120e26ce729da482a5949d6cc"
EXPECTED_CACHE_SHA256 = "80524b064086d4b677b0f7f5b2cf5f0579256ba7c262c63c06c3807bece7ce09"
EXPECTED_QUESTION_SET_SHA256 = "4bd59fb7cb56a77402dac5f59a1bd092eb6ae2353553ab1c9e85743289e8c6d8"
EXPECTED_INDEX_IDENTITY_SHA256 = (
    "2c0a15e6fb728528942cc1cdf664b532aab63dda2956981a607242bce361448c"
)
EXPECTED_ITEM_COUNT = 37
EXPECTED_COLLECTION_COUNT = 481
N_RESULTS = 5


class V3EvaluationError(RuntimeError):
    """Raised before a cohort invariant can be weakened or made ambiguous."""


@dataclass(frozen=True, slots=True)
class V3Paths:
    root: Path
    gold: Path
    provenance: Path
    question_commitment: Path
    corpus_manifest: Path
    chunks: Path
    cache: Path
    catalog: Path
    uv_lock: Path
    chroma: Path

    @property
    def ledger(self) -> Path:
        return self.root / "usage.sqlite3"

    @property
    def cohort_manifest(self) -> Path:
        return self.root / "cohort-manifest.json"

    @property
    def instrument_freeze(self) -> Path:
        return self.root / "instrument-freeze.json"


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    response_id: str | None
    model: str | None
    status: str | None
    created_at: int | float | str | None
    system_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class PreparedV3Cohort:
    paths: V3Paths
    gold: LockedGold
    items: tuple[Mapping[str, object], ...]
    embeddings: Mapping[str, list[float]]
    collection: object
    chunks: list[dict[str, Any]]
    corpus_trace: Mapping[str, object]
    manifest: Mapping[str, object]


def default_paths(base_dir: Path, *, root: Path | None = None) -> V3Paths:
    runtime_root = _private_evaluation_root(
        base_dir,
        root or base_dir / "runtime" / "evaluations" / EVALUATION_ID,
    )
    return V3Paths(
        root=runtime_root.resolve(),
        gold=base_dir / "fixtures" / "gold_set.json",
        provenance=base_dir / "fixtures" / "gold_set.provenance.json",
        question_commitment=base_dir / "fixtures" / "gold_questions.commitment.json",
        corpus_manifest=base_dir / "fixtures" / "corpus_manifest.json",
        chunks=base_dir / "output" / "chunks.json",
        cache=base_dir / "runtime" / "evaluations" / "retrieval-query-embeddings.json",
        catalog=base_dir / "fixtures" / "evaluation_model_catalog.json",
        uv_lock=base_dir / "uv.lock",
        chroma=base_dir / "chroma_db",
    )


def _private_evaluation_root(base_dir: Path, root: Path) -> Path:
    """Resolve one gitignored run root strictly below ``runtime/evaluations``."""

    allowed_parent = (base_dir / "runtime" / "evaluations").resolve()
    resolved = root.resolve()
    try:
        relative = resolved.relative_to(allowed_parent)
    except ValueError as exc:
        raise V3EvaluationError(
            "v3 artifacts must stay under the private runtime/evaluations directory"
        ) from exc
    if not relative.parts:
        raise V3EvaluationError(
            "v3 artifacts require a dedicated child root under runtime/evaluations"
        )
    return resolved


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _json_default(value: object) -> object:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    if hasattr(value, "value"):
        return getattr(value, "value")
    raise TypeError(f"cannot serialize {type(value).__name__}")


def read_json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise V3EvaluationError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise V3EvaluationError(f"JSON artifact must be an object: {path}")
    return value


def write_json_no_overwrite(path: Path, value: Mapping[str, object]) -> None:
    if path.exists():
        raise V3EvaluationError(f"sealed artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_or_validate_json(path: Path, value: Mapping[str, object]) -> None:
    if path.exists():
        if read_json_object(path) != dict(value):
            raise V3EvaluationError(f"existing artifact changed: {path}")
        return
    write_json_no_overwrite(path, value)


def _git_commit(base_dir: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=base_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise V3EvaluationError("could not resolve harness commit")
    return completed.stdout.strip()


def _require_hash(path: Path, expected: str, label: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise V3EvaluationError(f"{label} SHA-256 changed: {actual}")


def _required_string(value: Mapping[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise V3EvaluationError(f"missing non-blank {field}")
    return item


def _index_identity(collection: object, manifest: Mapping[str, object]) -> dict[str, object]:
    store = manifest.get("store")
    if not isinstance(store, Mapping):
        raise V3EvaluationError("corpus manifest has no store identity")
    count_method = getattr(collection, "count", None)
    if not callable(count_method):
        raise V3EvaluationError("collection has no count method")
    metadata = getattr(collection, "metadata", None)
    configuration = getattr(collection, "configuration", None)
    hnsw = configuration.get("hnsw") if isinstance(configuration, Mapping) else None
    actual_space = (
        hnsw.get("space") if isinstance(hnsw, Mapping) else None
    ) or (metadata.get("hnsw:space") if isinstance(metadata, Mapping) else None)
    actual_chunks_hash = metadata.get("chunks_sha256") if isinstance(metadata, Mapping) else None
    actual_model = metadata.get("embedding_model") if isinstance(metadata, Mapping) else None
    identity = {
        "collection_name": str(store.get("collection_name") or ""),
        "collection_count": int(count_method()),
        "hnsw_space": str(actual_space or ""),
        "embedding_model": str(actual_model or ""),
        "chunks_sha256": str(actual_chunks_hash or ""),
    }
    if identity != {
        "collection_name": "manuscript",
        "collection_count": EXPECTED_COLLECTION_COUNT,
        "hnsw_space": "l2",
        "embedding_model": "text-embedding-3-small",
        "chunks_sha256": EXPECTED_CHUNKS_SHA256,
    }:
        raise V3EvaluationError("active vector index identity changed")
    if canonical_json_sha256(identity) != EXPECTED_INDEX_IDENTITY_SHA256:
        raise V3EvaluationError("active vector index identity hash changed")
    return identity


def _authored_schema_sha256() -> str:
    return canonical_json_sha256(AuthoredResponse.model_json_schema())


def _source_file_hashes(base_dir: Path) -> dict[str, str]:
    names = (
        "src/archivist_modes.py",
        "src/authored_response.py",
        "src/character_conversation.py",
        "src/corpus.py",
        "src/costs.py",
        "src/evidence_dossier.py",
        "src/evidence_compiler.py",
        "src/model_config.py",
        "src/public_sources.py",
        "src/query_planning.py",
        "src/rag_pipeline.py",
        "src/retrieval.py",
        "src/retrieval_trace_contract.py",
    )
    return {name: sha256_file(base_dir / name) for name in names}


def _require_product_source_unchanged(base_dir: Path) -> None:
    """Prove the later harness commit did not silently alter the frozen product."""

    for name in _source_file_hashes(base_dir):
        current = subprocess.run(
            ["git", "hash-object", name],
            cwd=base_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        product = subprocess.run(
            ["git", "rev-parse", f"{PRODUCT_COMMIT}:{name}"],
            cwd=base_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        if current.returncode != 0 or product.returncode != 0:
            raise V3EvaluationError(f"product commit omitted source binding {name}")
        if current.stdout.strip() != product.stdout.strip():
            raise V3EvaluationError(
                f"current {name} differs from declared product commit {PRODUCT_COMMIT}"
            )


def _decomposition_identity() -> Mapping[str, object]:
    try:
        from evaluation_decomposition_v2 import decomposition_instrument_identity
    except ImportError as exc:
        raise V3EvaluationError("decomposition-v2 instrument is unavailable") from exc
    return decomposition_instrument_identity()


def build_v3_manifest(
    *,
    base_dir: Path,
    paths: V3Paths,
    gold: LockedGold,
    cache: Mapping[str, object],
    corpus_identity: Mapping[str, object],
    index_identity: Mapping[str, object],
    require_clean: bool,
) -> dict[str, object]:
    worktree = build_git_worktree_identity(base_dir)
    if require_clean and worktree.get("working_tree") != "clean":
        raise V3EvaluationError("v3 run-of-record phases require a clean working tree")
    harness_commit = _git_commit(base_dir)
    _require_product_source_unchanged(base_dir)
    prompt = authored_response_prompt_metadata(ArchivistMode.PROFESSIONAL)
    lens, voice, worldview = settings_for_archivist_mode(ArchivistMode.PROFESSIONAL)
    items = [
        {
            "id": _required_string(item, "id"),
            "question_sha256": normalized_question_sha256(_required_string(item, "question")),
            "stratum": _required_string(item, "stratum"),
            "expected_behavior": _required_string(item, "expected_behavior"),
        }
        for item in gold.items
    ]
    return {
        "schema": V3_COHORT_MANIFEST_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "classification": COHORT_CLASSIFICATION,
        "classification_limitation": (
            "The unchanged locked benchmark is reused after prior V26 exposure; this is a "
            "descriptive current-system cohort, not a pristine blind first-look test."
        ),
        "system_under_test": {
            "product_commit": PRODUCT_COMMIT,
            "harness_commit": harness_commit,
            "rag_policy": AUTHORED_RESPONSE_POLICY_VERSION,
            "mode": ArchivistMode.PROFESSIONAL.value,
            "source_file_sha256": _source_file_hashes(base_dir),
        },
        "working_tree": worktree,
        "locked_inputs": {
            "gold_set_sha256": gold.gold_set_sha256,
            "gold_provenance_sha256": sha256_file(paths.provenance),
            "question_commitment_sha256": sha256_file(paths.question_commitment),
            "question_set_sha256": gold.question_set_sha256,
            "corpus_manifest_sha256": corpus_identity["corpus_manifest_sha256"],
            "chunks_sha256": corpus_identity["chunks_sha256"],
            "embedding_cache_sha256": sha256_file(paths.cache),
            "provider_catalog_sha256": sha256_file(paths.catalog),
            "dependency_lock_sha256": sha256_file(paths.uv_lock),
        },
        "query_embeddings": {
            "source": "validated_cached_vectors",
            "cache_schema": cache.get("schema"),
            "model": cache.get("model"),
            "item_count": cache.get("question_count"),
            "provider_operations_in_this_cohort": 0,
        },
        "corpus": dict(corpus_identity),
        "index": {
            **dict(index_identity),
            "identity_sha256": canonical_json_sha256(index_identity),
        },
        "retrieval": {
            "version": HYBRID_RETRIEVAL_VERSION,
            "n_results": N_RESULTS,
            "semantic_candidate_limit": SEMANTIC_CANDIDATE_LIMIT,
            "lexical_candidate_limit": LEXICAL_CANDIDATE_LIMIT,
            "max_primary_distance": MAX_PRIMARY_DISTANCE,
            "max_final_sources": MAX_FINAL_SOURCES,
            "rrf_k": RRF_K,
            "semantic_weight": SEMANTIC_WEIGHT,
            "lexical_weight": LEXICAL_WEIGHT,
            "bm25_k1": BM25_K1,
            "bm25_b": BM25_B,
        },
        "dossier": {
            "target_evidence_tokens": DEFAULT_TARGET_EVIDENCE_TOKENS,
            "hard_evidence_token_limit": DEFAULT_HARD_EVIDENCE_TOKEN_LIMIT,
            "minimum_units": DEFAULT_MIN_DOSSIER_UNITS,
            "maximum_units": DEFAULT_MAX_DOSSIER_UNITS,
        },
        "authoring": {
            "input_schema": AUTHORED_RESPONSE_INPUT_SCHEMA,
            "output_schema": AUTHORED_RESPONSE_OUTPUT_SCHEMA,
            "output_schema_sha256": _authored_schema_sha256(),
            "renderer_version": AUTHORED_RESPONSE_RENDERER_VERSION,
            "renderer_sha256": hashlib.sha256(
                (
                    AUTHORED_RESPONSE_RENDERER_VERSION
                    + "\n"
                    + inspect.getsource(validate_and_render_authored_response)
                ).encode("utf-8")
            ).hexdigest(),
            **prompt,
            "requested_model": AUTHORED_RESPONSE_SETTINGS.model,
            "reasoning_effort": AUTHORED_RESPONSE_SETTINGS.reasoning_effort,
            "verbosity": AUTHORED_RESPONSE_SETTINGS.verbosity,
            "max_output_tokens": MAX_AUTHORED_RESPONSE_OUTPUT_TOKENS,
            "historiographical_lens": lens.value,
            "voice": voice.value,
            "worldview": worldview.value,
            "automatic_retries": 0,
            "attempts_per_item": 1,
            "replacements": 0,
            "provider_timeout_seconds": 20.0,
        },
        "decomposition": dict(_decomposition_identity()),
        "semantic_rubric": {
            "status": "exploratory_uncalibrated",
            "phase_order": "after_all_37_generation_and_decomposition_outcomes_are_sealed",
            "prompt_version": ITEM_RUBRIC_PROMPT_VERSION,
            "prompt_sha256": ITEM_RUBRIC_PROMPT_SHA256,
            "requested_model": JUDGE_MODEL,
            "reasoning_effort": JUDGE_SETTINGS.reasoning_effort,
            "verbosity": JUDGE_SETTINGS.verbosity,
            "formal_or_owner_adjudicated": False,
        },
        "paid_scope": {
            "provider": "OpenAI",
            "master_request_id": MASTER_REQUEST_ID,
            "shared_private_ledger": "usage.sqlite3",
            "maximum_total_cost_nano_usd": MASTER_COST_CAP_NANO_USD,
            "maximum_total_cost_usd": float(MASTER_COST_CAP_USD),
            "automatic_retries": 0,
        },
        "items": items,
        "item_count": len(items),
        "privacy": {
            "artifact_root": "gitignored_private_runtime",
            "committed_manuscript_text": False,
            "gold_visible_to_generation": False,
            "gold_visible_to_decomposition": False,
        },
    }


def prepare_v3_cohort(
    *,
    base_dir: Path,
    paths: V3Paths,
    collection: object | None = None,
    chunks: list[dict[str, Any]] | None = None,
    require_clean: bool = True,
    persist_manifest: bool = False,
) -> PreparedV3Cohort:
    if paths.root.resolve() != _private_evaluation_root(base_dir, paths.root):
        raise V3EvaluationError("v3 evaluation root did not resolve canonically")
    for path, expected, label in (
        (paths.gold, EXPECTED_GOLD_SHA256, "gold set"),
        (paths.provenance, EXPECTED_PROVENANCE_SHA256, "gold provenance"),
        (paths.question_commitment, EXPECTED_COMMITMENT_SHA256, "question commitment"),
        (paths.corpus_manifest, EXPECTED_MANIFEST_SHA256, "corpus manifest"),
        (paths.chunks, EXPECTED_CHUNKS_SHA256, "chunks"),
        (paths.cache, EXPECTED_CACHE_SHA256, "query embedding cache"),
    ):
        _require_hash(path, expected, label)
    gold = load_locked_gold(paths.gold, paths.provenance)
    if gold.gold_set_sha256 != EXPECTED_GOLD_SHA256:
        raise V3EvaluationError("loaded gold set changed")
    if gold.question_set_sha256 != EXPECTED_QUESTION_SET_SHA256:
        raise V3EvaluationError("locked question-set hash changed")
    if len(gold.items) != EXPECTED_ITEM_COUNT:
        raise V3EvaluationError("locked item count changed")
    routed_social = [
        _required_string(item, "id")
        for item in gold.items
        if is_character_conversation_question(
            _required_string(item, "question"),
            ArchivistMode.PROFESSIONAL,
        )
    ]
    if routed_social:
        raise V3EvaluationError(
            "Professional quality cohort contains character-social routes: "
            + ", ".join(routed_social)
        )
    cache = read_json_object(paths.cache)
    embeddings = validate_embedding_cache(cache, gold)

    manifest_payload = read_json_object(paths.corpus_manifest)
    active_chunks = get_all_chunks() if chunks is None else chunks
    if collection is None:
        import chromadb

        collection_name = str(manifest_payload["store"]["collection_name"])
        active_collection = chromadb.PersistentClient(path=str(paths.chroma)).get_collection(
            name=collection_name,
            embedding_function=None,
        )
    else:
        active_collection = collection
    corpus_identity = build_corpus_identity(
        manifest_path=paths.corpus_manifest,
        chunks_path=paths.chunks,
    )
    integrity = preflight_answer_corpus(
        collection_handle=active_collection,
        chunks=active_chunks,
        corpus_manifest=manifest_payload,
        corpus_manifest_sha256=str(corpus_identity["corpus_manifest_sha256"]),
        require_store_identity=True,
    )
    if not integrity.passed:
        raise V3EvaluationError(
            "active corpus/index integrity failed: " + ", ".join(integrity.failure_codes)
        )
    index_identity = _index_identity(active_collection, manifest_payload)
    corpus_trace = {
        "collection_name": corpus_identity["collection_name"],
        "collection_count": int(active_collection.count()),
        "corpus_manifest_sha256": corpus_identity["corpus_manifest_sha256"],
        "chunks_sha256": corpus_identity["chunks_sha256"],
        "hnsw_space": corpus_identity["hnsw_space"],
    }
    cohort_manifest = build_v3_manifest(
        base_dir=base_dir,
        paths=paths,
        gold=gold,
        cache=cache,
        corpus_identity=corpus_identity,
        index_identity=index_identity,
        require_clean=require_clean,
    )
    if persist_manifest:
        paths.root.mkdir(parents=True, exist_ok=True)
        write_or_validate_json(paths.cohort_manifest, cohort_manifest)
    return PreparedV3Cohort(
        paths=paths,
        gold=gold,
        items=gold.items,
        embeddings=embeddings,
        collection=active_collection,
        chunks=active_chunks,
        corpus_trace=corpus_trace,
        manifest=cohort_manifest,
    )


@contextmanager
def master_usage_scope(
    paths: V3Paths,
    *,
    maximum_usd: Decimal = MASTER_COST_CAP_USD,
    turn_id: str | None = None,
) -> Iterator[UsageLedger]:
    if maximum_usd <= 0 or maximum_usd > MASTER_COST_CAP_USD:
        raise V3EvaluationError("maximum cost must be positive and no greater than $7.00")
    ceiling_nano = int(maximum_usd * Decimal(1_000_000_000))
    previous = os.environ.get("ARCHIVIST_USAGE_DB")
    os.environ["ARCHIVIST_USAGE_DB"] = str(paths.ledger)
    try:
        ledger = UsageLedger(paths.ledger)
        ledger.update_settings(
            monthly_budget_usd=maximum_usd,
            warning_threshold_percent=80,
            hard_limit_enabled=True,
        )
        _validate_master_ledger(paths.ledger)
        try:
            with usage_scope(
                project_id=MASTER_PROJECT_ID,
                conversation_id=MASTER_CONVERSATION_ID,
                turn_id=turn_id,
                request_id=MASTER_REQUEST_ID,
                enforce_budget=True,
                allow_over_budget=False,
                request_cost_ceiling_nano_usd=ceiling_nano,
            ):
                yield ledger
        finally:
            _validate_master_ledger(paths.ledger)
    finally:
        if previous is None:
            os.environ.pop("ARCHIVIST_USAGE_DB", None)
        else:
            os.environ["ARCHIVIST_USAGE_DB"] = previous


def _validate_master_ledger(path: Path) -> None:
    if not path.exists():
        return
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT DISTINCT request_id FROM usage_events ORDER BY request_id"
        ).fetchall()
        unpriced = int(
            connection.execute("SELECT COALESCE(SUM(unpriced), 0) FROM usage_events").fetchone()[0]
        )
    identifiers = {row[0] for row in rows}
    if identifiers - {MASTER_REQUEST_ID}:
        raise V3EvaluationError("shared ledger contains another request scope")
    if None in identifiers:
        raise V3EvaluationError("shared ledger contains an unscoped paid event")
    if unpriced:
        raise V3EvaluationError("shared ledger contains unpriced usage")


def _first_batch(results: Mapping[str, object], key: str) -> list[object]:
    value = results.get(key)
    if not isinstance(value, list) or not value or not isinstance(value[0], list):
        return []
    return list(value[0])


def retrieve_with_cached_embedding(
    *,
    question: str,
    embedding: Sequence[float],
    collection: object,
    chunks: list[dict[str, Any]],
    corpus_trace: Mapping[str, object],
    n_results: int = N_RESULTS,
    profile_k: bool = True,
) -> tuple[Mapping[str, object], object, Mapping[str, list[str]]]:
    """Reproduce the product retrieval/finalizer without an embedding request."""

    if n_results <= 0:
        raise V3EvaluationError("n_results must be positive")
    query_method = getattr(collection, "query", None)
    count_method = getattr(collection, "count", None)
    if not callable(query_method) or not callable(count_method):
        raise V3EvaluationError("collection must expose count() and query()")
    candidate_count = min(int(count_method()), max(SEMANTIC_CANDIDATE_LIMIT, n_results))
    if candidate_count <= 0:
        raise V3EvaluationError("retrieval collection is empty")
    semantic = query_method(
        query_embeddings=[list(embedding)],
        n_results=candidate_count,
        include=["metadatas", "distances"],
    )
    if not isinstance(semantic, Mapping):
        raise V3EvaluationError("collection query returned malformed results")
    hybrid = build_hybrid_results(
        question,
        semantic,
        chunks,
        n_results=n_results,
        corpus=corpus_trace,
    )
    outcome = plan_context_chunks(hybrid, chunks=chunks)
    primary_by_k: dict[str, list[str]] = {}
    for k in K_VALUES if profile_k else ():
        bounded = min(k, candidate_count)
        profile = build_hybrid_results(
            question,
            deepcopy(dict(semantic)),
            chunks,
            n_results=bounded,
            corpus=corpus_trace,
        )
        raw_hybrid = profile.get("hybrid")
        raw_ids = raw_hybrid.get("primary_chunk_ids") if isinstance(raw_hybrid, Mapping) else None
        if not isinstance(raw_ids, list):
            raise V3EvaluationError("hybrid profile omitted primary IDs")
        primary_by_k[str(k)] = [str(value) for value in raw_ids]
    return hybrid, outcome, primary_by_k


def preflight_all_cached_items(cohort: PreparedV3Cohort) -> dict[str, object]:
    """Prove every H item can reach the one-call boundary without an embedding call."""

    item_summaries: list[dict[str, object]] = []
    for item in cohort.items:
        item_id = _required_string(item, "id")
        question = _required_string(item, "question")
        vector = cohort.embeddings.get(item_id)
        if vector is None:
            raise V3EvaluationError(f"cached embedding is missing for {item_id}")
        _, retrieval_outcome, _ = retrieve_with_cached_embedding(
            question=question,
            embedding=vector,
            collection=cohort.collection,
            chunks=cohort.chunks,
            corpus_trace=cohort.corpus_trace,
            profile_k=False,
        )
        dossier = build_retrieval_dossier(
            question,
            retrieval_outcome.final_chunks,
            retrieval_query=question,
        )
        if not dossier.units:
            raise V3EvaluationError(f"{item_id} cannot reach the authoring boundary")
        item_summaries.append(
            {
                "item_id": item_id,
                "finalized_chunk_count": len(retrieval_outcome.final_chunks),
                "dossier_unit_count": len(dossier.units),
            }
        )
    return {
        "item_count": len(item_summaries),
        "items_ready_for_one_authoring_call": len(item_summaries),
        "query_embedding_provider_operations": 0,
        "minimum_finalized_chunks": min(
            int(value["finalized_chunk_count"]) for value in item_summaries
        ),
        "minimum_dossier_units": min(
            int(value["dossier_unit_count"]) for value in item_summaries
        ),
    }


def _score_ids(item: Mapping[str, object], ids: Sequence[str]) -> dict[str, object]:
    raw_relevant = item.get("relevant_chunk_ids")
    if not isinstance(raw_relevant, list):
        raise V3EvaluationError("gold relevant_chunk_ids must be an array")
    relevant = {str(value) for value in raw_relevant}
    retrieved = set(ids)
    overlap = relevant & retrieved
    raw_claims = item.get("claims")
    if not isinstance(raw_claims, list):
        raise V3EvaluationError("gold claims must be an array")
    essential = [claim for claim in raw_claims if isinstance(claim, Mapping) and claim.get("essential") is True]
    essential_covered = 0
    for claim in essential:
        supporting = claim.get("supporting_chunk_ids")
        if not isinstance(supporting, list):
            raise V3EvaluationError("gold supporting_chunk_ids must be an array")
        essential_covered += bool({str(value) for value in supporting} & retrieved)
    return {
        "retrieved_count": len(ids),
        "relevant_count": len(relevant),
        "retrieved_relevant_count": len(overlap),
        "recall": len(overlap) / len(relevant) if relevant else None,
        "hit": bool(overlap) if relevant else None,
        "essential_claim_count": len(essential),
        "covered_essential_claim_count": essential_covered,
        "essential_coverage": essential_covered / len(essential) if essential else None,
    }


def _dossier_chunks(dossier: RetrievalDossier, finalized: Sequence[Mapping[str, object]]) -> list[dict[str, Any]]:
    by_id = {str(chunk.get("chunk_id") or ""): dict(chunk) for chunk in finalized}
    values: list[dict[str, Any]] = []
    for unit in dossier.units:
        if unit.chunk_id not in by_id:
            raise V3EvaluationError("dossier unit is not from finalized retrieval")
        chunk = dict(by_id[unit.chunk_id])
        chunk["text"] = unit.text
        chunk["paragraph_start"] = unit.source.paragraph_start
        chunk["paragraph_end"] = unit.source.paragraph_end
        values.append(chunk)
    return values


def _observation(value: object) -> ProviderObservation:
    def field(name: str) -> object:
        return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)

    response_id = field("id") or field("_request_id")
    model = field("model")
    status = field("status")
    created_at = field("created_at")
    fingerprint = field("system_fingerprint")
    return ProviderObservation(
        response_id=str(response_id) if response_id is not None else None,
        model=str(model) if model is not None else None,
        status=str(status) if status is not None else None,
        created_at=created_at if isinstance(created_at, (int, float, str)) else None,
        system_fingerprint=str(fingerprint) if fingerprint is not None else None,
    )


class _CapturingResponses:
    def __init__(
        self,
        resource: object,
        observations: list[ProviderObservation],
        attempts: list[int],
        on_provider_attempt: Callable[[], None] | None,
    ) -> None:
        self._resource = resource
        self._observations = observations
        self._attempts = attempts
        self._on_provider_attempt = on_provider_attempt

    def _mark_attempt(self) -> None:
        if self._on_provider_attempt is not None:
            self._on_provider_attempt()
        self._attempts[0] += 1

    def parse(self, **kwargs: object) -> object:
        self._mark_attempt()
        response = getattr(self._resource, "parse")(**kwargs)
        _append_observation(self._observations, response)
        return response

    @property
    def with_raw_response(self) -> _CapturingRawResponses | None:
        resource = getattr(self._resource, "with_raw_response", None)
        if resource is None:
            return None
        return _CapturingRawResponses(
            resource,
            self._observations,
            self._attempts,
            self._on_provider_attempt,
        )

    def __getattr__(self, name: str) -> object:
        return getattr(self._resource, name)


def _raw_response_payload(raw_response: object) -> object | None:
    reader = getattr(raw_response, "json", None)
    if callable(reader):
        try:
            return reader()
        except Exception:
            return None
    http_response = getattr(raw_response, "http_response", None)
    reader = getattr(http_response, "json", None)
    if callable(reader):
        try:
            return reader()
        except Exception:
            return None
    return None


def _append_observation(
    observations: list[ProviderObservation],
    value: object,
) -> bool:
    observation = _observation(value)
    if not any(asdict(observation).values()):
        return False
    if observation not in observations:
        observations.append(observation)
    return True


class _CapturingRawResponse:
    def __init__(
        self,
        raw_response: object,
        observations: list[ProviderObservation],
        raw_observation_captured: bool,
    ) -> None:
        self._raw_response = raw_response
        self._observations = observations
        self._raw_observation_captured = raw_observation_captured

    def parse(self) -> object:
        response = getattr(self._raw_response, "parse")()
        if not self._raw_observation_captured:
            _append_observation(self._observations, response)
        return response

    def __getattr__(self, name: str) -> object:
        return getattr(self._raw_response, name)


class _CapturingRawResponses:
    def __init__(
        self,
        resource: object,
        observations: list[ProviderObservation],
        attempts: list[int],
        on_provider_attempt: Callable[[], None] | None,
    ) -> None:
        self._resource = resource
        self._observations = observations
        self._attempts = attempts
        self._on_provider_attempt = on_provider_attempt

    def parse(self, **kwargs: object) -> _CapturingRawResponse:
        # ``tracked_responses_parse`` performs both budget checks before this
        # method.  The callback therefore seals intent at the actual provider
        # boundary, without turning a local or cost-precheck failure into an
        # ambiguous paid attempt.
        if self._on_provider_attempt is not None:
            self._on_provider_attempt()
        self._attempts[0] += 1
        raw_response = getattr(self._resource, "parse")(**kwargs)
        payload = _raw_response_payload(raw_response)
        captured = payload is not None and _append_observation(self._observations, payload)
        return _CapturingRawResponse(raw_response, self._observations, captured)

    def __getattr__(self, name: str) -> object:
        return getattr(self._resource, name)


class ProviderCapturingClient:
    def __init__(
        self,
        client: object,
        observations: list[ProviderObservation] | None = None,
        attempts: list[int] | None = None,
        on_provider_attempt: Callable[[], None] | None = None,
    ) -> None:
        self._client = client
        self.observations = observations if observations is not None else []
        self._attempts = attempts if attempts is not None else [0]
        self._on_provider_attempt = on_provider_attempt

    @property
    def attempt_count(self) -> int:
        return self._attempts[0]

    @property
    def responses(self) -> _CapturingResponses:
        return _CapturingResponses(
            getattr(self._client, "responses"),
            self.observations,
            self._attempts,
            self._on_provider_attempt,
        )

    def with_options(self, **kwargs: object) -> ProviderCapturingClient:
        configured = getattr(self._client, "with_options")(**kwargs)
        return ProviderCapturingClient(
            configured,
            self.observations,
            self._attempts,
            self._on_provider_attempt,
        )

    def __getattr__(self, name: str) -> object:
        return getattr(self._client, name)


def _item_dir(paths: V3Paths, item_id: str) -> Path:
    return paths.root / "items" / item_id


def _intent_or_resume(*, intent_path: Path, outcome_path: Path, intent: Mapping[str, object]) -> bool:
    """Return true for a sealed pair; never create intent before a paid boundary."""

    if outcome_path.exists():
        if not intent_path.exists() or read_json_object(intent_path) != dict(intent):
            raise V3EvaluationError(f"sealed outcome has a changed intent: {outcome_path}")
        return True
    if intent_path.exists():
        if read_json_object(intent_path) != dict(intent):
            raise V3EvaluationError(f"attempt intent changed: {intent_path}")
        raise V3EvaluationError(
            f"attempt intent exists without outcome; provider-attempt state is ambiguous: {intent_path}"
        )
    return False


def _capturing_attempt_client(
    client: object,
    *,
    intent_path: Path,
    intent: Mapping[str, object],
) -> ProviderCapturingClient:
    def seal_intent() -> None:
        write_json_no_overwrite(intent_path, intent)

    return ProviderCapturingClient(client, on_provider_attempt=seal_intent)


def _turn_operation_evidence(
    paths: V3Paths,
    *,
    turn_id: str,
    expected_operation: str,
) -> dict[str, object]:
    rows: list[sqlite3.Row] = []
    if paths.ledger.exists():
        with sqlite3.connect(paths.ledger) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT response_id, operation, project_id, conversation_id, turn_id,
                       request_id, requested_model, actual_model, input_tokens,
                       output_tokens, reasoning_tokens, total_tokens,
                       estimated_cost_nano_usd, unpriced
                FROM usage_events
                WHERE request_id = ? AND turn_id = ?
                ORDER BY id
                """,
                (MASTER_REQUEST_ID, turn_id),
            ).fetchall()
    events = [
        {
            "response_id": str(row["response_id"]),
            "operation": str(row["operation"]),
            "requested_model": str(row["requested_model"]),
            "actual_model": str(row["actual_model"]),
            "input_tokens": int(row["input_tokens"]),
            "output_tokens": int(row["output_tokens"]),
            "reasoning_tokens": int(row["reasoning_tokens"]),
            "total_tokens": int(row["total_tokens"]),
            "estimated_cost_nano_usd": (
                int(row["estimated_cost_nano_usd"])
                if row["estimated_cost_nano_usd"] is not None
                else None
            ),
            "unpriced": bool(row["unpriced"]),
        }
        for row in rows
    ]
    scope_valid = all(
        row["project_id"] == MASTER_PROJECT_ID
        and row["conversation_id"] == MASTER_CONVERSATION_ID
        and row["turn_id"] == turn_id
        and row["request_id"] == MASTER_REQUEST_ID
        for row in rows
    )
    operations_valid = all(row["operation"] == expected_operation for row in rows)
    return {
        "turn_id": turn_id,
        "expected_operation": expected_operation,
        "event_count": len(events),
        "scope_valid": scope_valid,
        "operations_valid": operations_valid,
        "at_most_one_event": len(events) <= 1,
        "exactly_one_expected_event": (
            len(events) == 1 and scope_valid and operations_valid and not events[0]["unpriced"]
        ),
        "events": events,
    }


def _require_operation_evidence(
    evidence: Mapping[str, object],
    *,
    completed_response_required: bool,
    label: str,
) -> None:
    del completed_response_required
    event_count = evidence.get("event_count")
    if event_count != 1:
        raise V3EvaluationError(
            f"{label} lacks exactly one priced provider usage event; "
            "billing state is ambiguous and no later call may run"
        )
    if evidence.get("scope_valid") is not True or evidence.get("operations_valid") is not True:
        raise V3EvaluationError(f"{label} provider usage event scope or operation changed")
    if evidence.get("exactly_one_expected_event") is not True:
        raise V3EvaluationError(f"{label} lacks exactly one priced usage event")


def generate_professional_item(
    cohort: PreparedV3Cohort,
    *,
    item: Mapping[str, object],
    client: object,
    author: Callable[..., AuthoredResponseResult] = generate_authored_response,
    require_provider_observation: bool = True,
    on_provider_attempt: Callable[[], None] | None = None,
) -> dict[str, object]:
    item_id = _required_string(item, "id")
    question = _required_string(item, "question")
    vector = cohort.embeddings.get(item_id)
    if vector is None:
        raise V3EvaluationError(f"cached embedding is missing for {item_id}")
    retrieval_started = perf_counter_ns()
    hybrid, retrieval_outcome, primary_by_k = retrieve_with_cached_embedding(
        question=question,
        embedding=vector,
        collection=cohort.collection,
        chunks=cohort.chunks,
        corpus_trace=cohort.corpus_trace,
    )
    retrieval_ms = (perf_counter_ns() - retrieval_started) / 1_000_000
    finalized = list(retrieval_outcome.final_chunks)
    dossier = build_retrieval_dossier(question, finalized, retrieval_query=question)
    if not dossier.units:
        raise V3EvaluationError(f"{item_id} produced no dossier units; authoring call not made")
    dossier_chunks = _dossier_chunks(dossier, finalized)
    packet = compile_evidence_packet(question, dossier_chunks)
    direct = render_direct_evidence_answer(packet)
    resolved_turn = ResolvedTurn(
        standalone_question=question,
        trusted_user_texts=(question,),
    )
    lens, voice, worldview = settings_for_archivist_mode(ArchivistMode.PROFESSIONAL)
    capturing = ProviderCapturingClient(
        client,
        on_provider_attempt=on_provider_attempt,
    )
    generation_started = perf_counter_ns()
    authored = author(
        capturing,
        question=question,
        resolved_turn=resolved_turn,
        dossier=dossier,
        mode=ArchivistMode.PROFESSIONAL,
        historiographical_lens=lens,
        voice=voice,
        worldview=worldview,
    )
    generation_ms = (perf_counter_ns() - generation_started) / 1_000_000
    generated = authored.status is AuthoredResponseStatus.GENERATED and authored.answer is not None
    answer = authored.answer if generated else direct.answer
    observations = capturing.observations
    provider_failed_without_response = (
        authored.status is not AuthoredResponseStatus.GENERATED
        and authored.failure_code is not None
        and authored.failure_code.value == "provider_failure"
        and not observations
    )
    if (
        require_provider_observation
        and len(observations) != 1
        and not provider_failed_without_response
    ):
        raise V3EvaluationError(
            f"{item_id} expected one provider response observation, found {len(observations)}"
        )
    if len(observations) > 1:
        raise V3EvaluationError(f"{item_id} made more than one authoring call")
    if require_provider_observation and capturing.attempt_count != 1:
        raise V3EvaluationError(
            f"{item_id} expected one authoring attempt, found {capturing.attempt_count}"
        )
    provider = observations[0] if observations else ProviderObservation(None, None, None, None, None)
    if provider.model is not None and provider.model != AUTHORED_RESPONSE_SETTINGS.model:
        raise V3EvaluationError(
            f"{item_id} provider model mismatch: {provider.model!r}"
        )

    finalized_ids = [str(chunk.get("chunk_id") or "") for chunk in finalized]
    dossier_ids = [unit.chunk_id for unit in dossier.units]
    if generated:
        used_numbers = list(authored.used_source_numbers)
        cited_ids = [
            dossier_ids[number - 1]
            for number in used_numbers
            if 1 <= number <= len(dossier_ids)
        ]
        displayed_chunks = dossier_chunks
        cited_id_basis = "generated_dossier_source_number"
    else:
        used_numbers = [card.source_number for card in packet.cards]
        cited_ids = [card.chunk_id for card in packet.cards]
        displayed_chunks = list(packet.source_chunks)
        packet_source_ids = [str(chunk.get("chunk_id") or "") for chunk in displayed_chunks]
        if cited_ids != packet_source_ids:
            raise V3EvaluationError("direct fallback card/source mapping changed")
        cited_id_basis = "direct_packet_card_chunk_id"
    displayed_ids = [str(chunk.get("chunk_id") or "") for chunk in displayed_chunks]
    citation = audit_citations(answer, source_count=len(displayed_ids))
    relevant_ids = {str(value) for value in item.get("relevant_chunk_ids", [])}
    hybrid_trace = hybrid.get("hybrid") if isinstance(hybrid, Mapping) else None
    trace = hybrid_trace.get("trace") if isinstance(hybrid_trace, Mapping) else None
    retrieval_metrics = {
        "primary_by_k": {
            k: {"ids": ids, "metrics": _score_ids(item, ids)} for k, ids in primary_by_k.items()
        },
        "finalized": {"ids": finalized_ids, "metrics": _score_ids(item, finalized_ids)},
        "dossier": {"ids": dossier_ids, "metrics": _score_ids(item, dossier_ids)},
        "cited": {"ids": cited_ids, "metrics": _score_ids(item, cited_ids)},
    }
    selection = trace.get("selection") if isinstance(trace, Mapping) else None
    discarded = selection.get("discarded") if isinstance(selection, Mapping) else None
    displacement = Counter(
        str(entry.get("displacement_cause"))
        for entry in discarded or []
        if isinstance(entry, Mapping) and entry.get("displacement_cause")
    )
    retrieval_metrics["fallbacks"] = {
        "raw_primary_fallback_used": bool(
            selection.get("raw_primary_fallback_used")
            if isinstance(selection, Mapping)
            else False
        ),
        "fusion_pool_fallback_used": bool(
            selection.get("fusion_pool_fallback_used")
            if isinstance(selection, Mapping)
            else False
        ),
    }
    retrieval_metrics["displacement_counts"] = dict(displacement)
    return {
        "schema": V3_GENERATION_OUTCOME_SCHEMA,
        "item_id": item_id,
        "question_sha256": normalized_question_sha256(question),
        "status": "generated" if generated else "essential_fallback",
        "answer": answer,
        "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        "disposition": authored.disposition.value if authored.disposition is not None else None,
        "failure_code": authored.failure_code.value if authored.failure_code is not None else None,
        "provider": asdict(provider),
        "provider_attempt_count": capturing.attempt_count,
        "attempt_count": 1,
        "automatic_retries": 0,
        "replacement": False,
        "query_embedding_provider_operations": 0,
        "timings_ms": {
            "retrieval_local": retrieval_ms,
            "authored_response_boundary": generation_ms,
        },
        "timing_definition": (
            "authored_response_boundary includes request construction, provider wait, SDK "
            "structured parsing, and local authored-response validation/rendering; it excludes "
            "cached-vector retrieval and dossier construction"
        ),
        "retrieval": retrieval_metrics,
        "retrieval_trace": deepcopy(dict(trace)) if isinstance(trace, Mapping) else {},
        "finalized_retrieval_chunk_ids": finalized_ids,
        "dossier": {
            "dossier_id": dossier.dossier_id,
            "model_visible_units": [
                {
                    "unit_id": unit.unit_id,
                    "chunk_id": unit.chunk_id,
                    "source_numbers": list(unit.source.source_numbers),
                    "text_scope": unit.text_scope,
                    "text": unit.text,
                    "text_sha256": hashlib.sha256(unit.text.encode("utf-8")).hexdigest(),
                }
                for unit in dossier.units
            ],
            "diagnostics": dossier.diagnostics,
        },
        "rendered_used_unit_ids": list(authored.used_unit_ids) if generated else [],
        "rendered_cited_source_numbers": used_numbers,
        "rendered_cited_chunk_ids": cited_ids,
        "rendered_cited_chunk_id_basis": cited_id_basis,
        "displayed_source_chunk_ids": displayed_ids,
        "citation_audit": asdict(citation),
        "cited_source_gold_location_matches": sum(chunk_id in relevant_ids for chunk_id in cited_ids),
        "cited_source_gold_location_total": len(cited_ids),
    }


def _local_technical_generation_outcome(
    cohort: PreparedV3Cohort,
    *,
    item: Mapping[str, object],
    exc: Exception,
) -> dict[str, object]:
    """Compile the deterministic fallback after an already-started call failed."""

    def fallback_author(*_args: object, **_kwargs: object) -> AuthoredResponseResult:
        return AuthoredResponseResult(
            status=AuthoredResponseStatus.FALLBACK_REQUIRED,
            mode=ArchivistMode.PROFESSIONAL,
            answer=None,
            disposition=None,
            paragraphs=(),
            follow_up_questions=(),
            used_unit_ids=(),
            used_source_numbers=(),
            failure_code=AuthoredFailureCode.PROVIDER_FAILURE,
        )

    outcome = generate_professional_item(
        cohort,
        item=item,
        client=object(),
        author=fallback_author,
        require_provider_observation=False,
    )
    outcome.update(
        {
            "status": "technical_failure",
            "delivered_answer_status": "essential_fallback",
            "failure_code": str(
                getattr(exc, "failure_code", "provider_or_validation_failure")
            ),
            "failure_type": type(exc).__name__,
        }
    )
    return outcome


def _generation_intent(item: Mapping[str, object], manifest: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema": V3_GENERATION_INTENT_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "item_id": _required_string(item, "id"),
        "question_sha256": normalized_question_sha256(_required_string(item, "question")),
        "cohort_manifest_sha256": canonical_json_sha256(manifest),
        "operation": "answer_generation",
        "requested_model": AUTHORED_RESPONSE_SETTINGS.model,
        "attempt_count": 1,
        "automatic_retries": 0,
        "replacement": False,
        "query_embedding_provider_operations": 0,
        "master_request_id": MASTER_REQUEST_ID,
    }


def run_generation_phase(
    cohort: PreparedV3Cohort,
    *,
    client: object,
    maximum_usd: Decimal = MASTER_COST_CAP_USD,
) -> None:
    require_instrument_freeze(cohort.paths)
    freeze_sha256 = sha256_file(cohort.paths.instrument_freeze)
    for item in cohort.items:
        item_id = _required_string(item, "id")
        root = _item_dir(cohort.paths, item_id)
        intent_path = root / "generation-intent.json"
        outcome_path = root / "generation.json"
        intent = {
            **_generation_intent(item, cohort.manifest),
            "instrument_freeze_sha256": freeze_sha256,
        }
        if _intent_or_resume(intent_path=intent_path, outcome_path=outcome_path, intent=intent):
            _validate_generation_pair(cohort, item=item, intent=intent)
            continue
        attempt_count = [0]

        def seal_intent() -> None:
            write_json_no_overwrite(intent_path, intent)
            attempt_count[0] += 1

        turn_id = f"{item_id}:generation"
        try:
            with master_usage_scope(
                cohort.paths,
                maximum_usd=maximum_usd,
                turn_id=turn_id,
            ):
                outcome = generate_professional_item(
                    cohort,
                    item=item,
                    client=client,
                    on_provider_attempt=seal_intent,
                )
        except Exception as exc:
            if attempt_count[0] == 0:
                # Local preparation and both cost checks occur before the
                # provider-boundary callback.  They are safe to correct and
                # rerun because no paid attempt has started.
                raise
            outcome = _local_technical_generation_outcome(
                cohort,
                item=item,
                exc=exc,
            )
            outcome["provider_attempt_count"] = attempt_count[0]
        evidence = _turn_operation_evidence(
            cohort.paths,
            turn_id=turn_id,
            expected_operation="answer_generation",
        )
        provider = outcome.get("provider")
        provider_response_observed = bool(
            isinstance(provider, Mapping) and provider.get("response_id")
        )
        completed_response_required = (
            outcome.get("status") != "technical_failure" or provider_response_observed
        )
        operation_error: str | None = None
        try:
            _require_operation_evidence(
                evidence,
                completed_response_required=completed_response_required,
                label=f"{item_id} generation",
            )
        except V3EvaluationError as exc:
            operation_error = str(exc)
        if outcome.get("status") == "essential_fallback" and not provider_response_observed:
            outcome["status"] = "technical_failure"
            outcome["delivered_answer_status"] = "essential_fallback"
            outcome["failure_type"] = "ProviderTransportFailure"
        if operation_error is not None:
            outcome["status"] = "technical_failure"
            outcome["delivered_answer_status"] = "essential_fallback"
            outcome["failure_type"] = "UsageEventContractFailure"
            outcome["usage_event_contract_error"] = operation_error
        outcome.update(
            {
                "cohort_manifest_sha256": canonical_json_sha256(cohort.manifest),
                "instrument_freeze_sha256": freeze_sha256,
                "intent_sha256": canonical_json_sha256(intent),
                "provider_attempt_count": attempt_count[0],
                "operation_evidence": evidence,
            }
        )
        write_json_no_overwrite(outcome_path, outcome)
        _validate_generation_pair(cohort, item=item, intent=intent)
    require_complete_generation(cohort)


def _validate_generation_pair(
    cohort: PreparedV3Cohort,
    *,
    item: Mapping[str, object],
    intent: Mapping[str, object],
) -> Mapping[str, object]:
    item_id = _required_string(item, "id")
    root = _item_dir(cohort.paths, item_id)
    intent_path = root / "generation-intent.json"
    outcome_path = root / "generation.json"
    if not intent_path.is_file() or read_json_object(intent_path) != dict(intent):
        raise V3EvaluationError(f"{item_id} generation intent is missing or changed")
    outcome = read_json_object(outcome_path)
    required_equal = {
        "schema": V3_GENERATION_OUTCOME_SCHEMA,
        "item_id": item_id,
        "question_sha256": intent["question_sha256"],
        "cohort_manifest_sha256": intent["cohort_manifest_sha256"],
        "instrument_freeze_sha256": intent["instrument_freeze_sha256"],
        "intent_sha256": canonical_json_sha256(intent),
        "attempt_count": 1,
        "automatic_retries": 0,
        "replacement": False,
        "query_embedding_provider_operations": 0,
        "provider_attempt_count": 1,
    }
    for field, expected in required_equal.items():
        if outcome.get(field) != expected:
            raise V3EvaluationError(f"{item_id} generation outcome changed {field}")
    answer = _required_string(outcome, "answer")
    if outcome.get("answer_sha256") != hashlib.sha256(answer.encode("utf-8")).hexdigest():
        raise V3EvaluationError(f"{item_id} generation answer hash changed")
    status = outcome.get("status")
    if status not in {"generated", "essential_fallback", "technical_failure"}:
        raise V3EvaluationError(f"{item_id} generation status is invalid")
    provider = outcome.get("provider")
    if not isinstance(provider, Mapping):
        raise V3EvaluationError(f"{item_id} generation provider metadata is invalid")
    provider_response_observed = bool(provider.get("response_id"))
    if provider_response_observed and provider.get("model") != AUTHORED_RESPONSE_SETTINGS.model:
        raise V3EvaluationError(f"{item_id} generation provider model changed")
    current_evidence = _turn_operation_evidence(
        cohort.paths,
        turn_id=f"{item_id}:generation",
        expected_operation="answer_generation",
    )
    if outcome.get("operation_evidence") != current_evidence:
        raise V3EvaluationError(f"{item_id} generation usage evidence changed")
    _require_operation_evidence(
        current_evidence,
        completed_response_required=(status != "technical_failure" or provider_response_observed),
        label=f"{item_id} generation",
    )
    if status == "technical_failure" and outcome.get("delivered_answer_status") != "essential_fallback":
        raise V3EvaluationError(f"{item_id} technical generation did not bind its fallback")
    if status != "generated":
        cited_ids = outcome.get("rendered_cited_chunk_ids")
        displayed_ids = outcome.get("displayed_source_chunk_ids")
        if (
            outcome.get("rendered_cited_chunk_id_basis")
            != "direct_packet_card_chunk_id"
            or cited_ids != displayed_ids
        ):
            raise V3EvaluationError(f"{item_id} fallback citations are not packet-bound")
    timings = outcome.get("timings_ms")
    if not isinstance(timings, Mapping) or "authored_response_boundary" not in timings:
        raise V3EvaluationError(f"{item_id} generation timing boundary is missing")
    if not isinstance(outcome.get("citation_audit"), Mapping):
        raise V3EvaluationError(f"{item_id} generation citation audit is missing")
    return outcome


def require_complete_generation(cohort: PreparedV3Cohort) -> None:
    missing = [
        _required_string(item, "id")
        for item in cohort.items
        if not (_item_dir(cohort.paths, _required_string(item, "id")) / "generation.json").is_file()
    ]
    if missing:
        raise V3EvaluationError(f"generation phase is incomplete: {missing}")
    freeze_sha256 = sha256_file(cohort.paths.instrument_freeze)
    for item in cohort.items:
        intent = {
            **_generation_intent(item, cohort.manifest),
            "instrument_freeze_sha256": freeze_sha256,
        }
        _validate_generation_pair(cohort, item=item, intent=intent)


def _dev_answer(path: Path) -> str:
    payload = read_json_object(path)
    response = payload.get("response")
    answer = response.get("answer") if isinstance(response, Mapping) else None
    if not isinstance(answer, str) or not answer.strip():
        raise V3EvaluationError(f"development artifact has no answer: {path}")
    return answer


def _decomposition_paths(paths: V3Paths, item_id: str, *, development: bool) -> tuple[Path, Path]:
    parent = paths.root / ("development" if development else "items") / item_id
    return parent / "decomposition-intent.json", parent / "decomposition.json"


def _judge_failure_provider(
    capturing: ProviderCapturingClient,
    exc: Exception,
) -> Mapping[str, object] | None:
    provider = getattr(exc, "provider", None)
    if provider is not None:
        return asdict(provider)
    if not capturing.observations:
        return None
    observed = capturing.observations[-1]
    return {
        "id": observed.response_id,
        "model": observed.model,
        "created_at": observed.created_at,
        "system_fingerprint": observed.system_fingerprint,
        "status": observed.status,
    }


def _decomposition_outcome(
    *,
    item_id: str,
    answer_sha256: str,
    intent: Mapping[str, object],
    result: object | None,
    failure: Exception | None,
    capturing: ProviderCapturingClient,
    evidence: Mapping[str, object],
) -> dict[str, object]:
    if result is not None:
        parsed = getattr(result, "parsed")
        provider = asdict(getattr(result, "provider"))
        outcome: dict[str, object] = {
            "schema": V3_DECOMPOSITION_OUTCOME_SCHEMA,
            "item_id": item_id,
            "status": "valid",
            "answer_sha256": getattr(result, "answer_sha256"),
            "claim_count": len(parsed.claims),
            "claims": [claim.model_dump(mode="json") for claim in parsed.claims],
            "provider": provider,
        }
    else:
        assert failure is not None
        outcome = {
            "schema": V3_DECOMPOSITION_OUTCOME_SCHEMA,
            "item_id": item_id,
            "status": "technical_failure",
            "answer_sha256": answer_sha256,
            "failure_type": type(failure).__name__,
            "failure_code": str(
                getattr(failure, "failure_code", "provider_or_validation_failure")
            ),
            "provider": _judge_failure_provider(capturing, failure),
        }
    provider_value = outcome.get("provider")
    response_observed = bool(
        isinstance(provider_value, Mapping) and provider_value.get("id")
    )
    operation_error: str | None = None
    try:
        _require_operation_evidence(
            evidence,
            completed_response_required=(result is not None or response_observed),
            label=f"{item_id} decomposition",
        )
    except V3EvaluationError as exc:
        operation_error = str(exc)
    if operation_error is not None:
        outcome["status"] = "technical_failure"
        outcome["failure_type"] = "UsageEventContractFailure"
        outcome["failure_code"] = "usage_event_contract_failure"
        outcome["usage_event_contract_error"] = operation_error
        outcome.pop("claims", None)
        outcome.pop("claim_count", None)
    outcome.update(
        {
            "intent_sha256": canonical_json_sha256(intent),
            "provider_attempt_count": capturing.attempt_count,
            "operation_evidence": dict(evidence),
            "attempt_count": 1,
            "automatic_retries": 0,
        }
    )
    return outcome


def _validate_decomposition_pair(
    paths: V3Paths,
    *,
    item_id: str,
    intent: Mapping[str, object],
    development: bool,
) -> Mapping[str, object]:
    intent_path, outcome_path = _decomposition_paths(
        paths,
        item_id,
        development=development,
    )
    if not intent_path.is_file() or read_json_object(intent_path) != dict(intent):
        raise V3EvaluationError(f"{item_id} decomposition intent is missing or changed")
    outcome = read_json_object(outcome_path)
    for field, expected in {
        "schema": V3_DECOMPOSITION_OUTCOME_SCHEMA,
        "item_id": item_id,
        "answer_sha256": intent["answer_sha256"],
        "intent_sha256": canonical_json_sha256(intent),
        "provider_attempt_count": 1,
        "attempt_count": 1,
        "automatic_retries": 0,
    }.items():
        if outcome.get(field) != expected:
            raise V3EvaluationError(f"{item_id} decomposition outcome changed {field}")
    status = outcome.get("status")
    if status not in {"valid", "technical_failure"}:
        raise V3EvaluationError(f"{item_id} decomposition status is invalid")
    instrument = intent.get("instrument")
    if not isinstance(instrument, Mapping):
        raise V3EvaluationError(f"{item_id} decomposition instrument is missing")
    current_evidence = _turn_operation_evidence(
        paths,
        turn_id=f"{item_id}:decomposition",
        expected_operation=str(instrument["operation"]),
    )
    if outcome.get("operation_evidence") != current_evidence:
        raise V3EvaluationError(f"{item_id} decomposition usage evidence changed")
    provider = outcome.get("provider")
    response_observed = bool(isinstance(provider, Mapping) and provider.get("id"))
    _require_operation_evidence(
        current_evidence,
        completed_response_required=(status == "valid" or response_observed),
        label=f"{item_id} decomposition",
    )
    if status == "valid":
        claims = outcome.get("claims")
        if not isinstance(claims, list) or outcome.get("claim_count") != len(claims):
            raise V3EvaluationError(f"{item_id} decomposition claims are invalid")
        if not isinstance(provider, Mapping) or provider.get("model") != instrument.get("model"):
            raise V3EvaluationError(f"{item_id} decomposition provider model changed")
    elif "claims" in outcome or "claim_count" in outcome:
        raise V3EvaluationError(f"{item_id} failed decomposition contains scored claims")
    return outcome


def run_development_decomposition_phase(
    paths: V3Paths,
    *,
    source_root: Path,
    client: object,
    maximum_usd: Decimal = MASTER_COST_CAP_USD,
) -> None:
    from evaluation_decomposition_v2 import decompose_answer_claims_v2

    identity = dict(_decomposition_identity())
    for ordinal in range(1, 11):
        item_id = f"G{ordinal:03d}"
        answer = _dev_answer(source_root / f"{item_id}.json")
        intent_path, outcome_path = _decomposition_paths(paths, item_id, development=True)
        intent = {
            "schema": V3_DECOMPOSITION_INTENT_SCHEMA,
            "evaluation_id": EVALUATION_ID,
            "item_id": item_id,
            "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            "instrument": identity,
            "input_boundary": "answer_only_no_gold_no_source_text",
            "attempt_count": 1,
            "automatic_retries": 0,
            "master_request_id": MASTER_REQUEST_ID,
        }
        if _intent_or_resume(intent_path=intent_path, outcome_path=outcome_path, intent=intent):
            _validate_decomposition_pair(
                paths,
                item_id=item_id,
                intent=intent,
                development=True,
            )
            continue
        capturing = _capturing_attempt_client(
            client,
            intent_path=intent_path,
            intent=intent,
        )
        result = None
        failure: Exception | None = None
        try:
            with master_usage_scope(
                paths,
                maximum_usd=maximum_usd,
                turn_id=f"{item_id}:decomposition",
            ):
                result = decompose_answer_claims_v2(capturing, answer=answer)
        except Exception as exc:
            if capturing.attempt_count == 0:
                raise
            failure = exc
        evidence = _turn_operation_evidence(
            paths,
            turn_id=f"{item_id}:decomposition",
            expected_operation=str(identity["operation"]),
        )
        outcome = _decomposition_outcome(
            item_id=item_id,
            answer_sha256=hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            intent=intent,
            result=result,
            failure=failure,
            capturing=capturing,
            evidence=evidence,
        )
        write_json_no_overwrite(outcome_path, outcome)
        _validate_decomposition_pair(
            paths,
            item_id=item_id,
            intent=intent,
            development=True,
        )


def freeze_decomposition_instrument(paths: V3Paths) -> dict[str, object]:
    outcomes: list[dict[str, object]] = []
    for ordinal in range(1, 11):
        item_id = f"G{ordinal:03d}"
        _, path = _decomposition_paths(paths, item_id, development=True)
        if not path.is_file():
            raise V3EvaluationError(f"development decomposition is missing: {item_id}")
        intent_path, _ = _decomposition_paths(paths, item_id, development=True)
        intent = read_json_object(intent_path)
        _validate_decomposition_pair(
            paths,
            item_id=item_id,
            intent=intent,
            development=True,
        )
        value = read_json_object(path)
        if value.get("status") != "valid":
            raise V3EvaluationError(f"development decomposition did not validate: {item_id}")
        outcomes.append(value)
    frozen = {
        "schema": V3_INSTRUMENT_FREEZE_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "instrument": dict(_decomposition_identity()),
        "development_item_ids": [f"G{ordinal:03d}" for ordinal in range(1, 11)],
        "valid_item_count": len(outcomes),
        "failed_item_count": 0,
        "outcome_sha256": {
            str(value["item_id"]): canonical_json_sha256(value) for value in outcomes
        },
        "frozen_at": datetime.now(UTC).isoformat(),
    }
    if paths.instrument_freeze.exists():
        existing = read_json_object(paths.instrument_freeze)
        comparable_existing = {key: value for key, value in existing.items() if key != "frozen_at"}
        comparable_expected = {key: value for key, value in frozen.items() if key != "frozen_at"}
        if comparable_existing != comparable_expected:
            raise V3EvaluationError("instrument freeze changed")
        return existing
    write_json_no_overwrite(paths.instrument_freeze, frozen)
    return frozen


def require_instrument_freeze(paths: V3Paths) -> Mapping[str, object]:
    if not paths.instrument_freeze.is_file():
        raise V3EvaluationError("decomposition instrument has not been frozen on G001-G010")
    value = read_json_object(paths.instrument_freeze)
    if value.get("instrument") != dict(_decomposition_identity()):
        raise V3EvaluationError("frozen decomposition instrument identity changed")
    if value.get("valid_item_count") != 10 or value.get("failed_item_count") != 0:
        raise V3EvaluationError("frozen development instrument did not validate all ten items")
    outcome_hashes = value.get("outcome_sha256")
    if not isinstance(outcome_hashes, Mapping):
        raise V3EvaluationError("frozen development outcome hashes are missing")
    for ordinal in range(1, 11):
        item_id = f"G{ordinal:03d}"
        intent_path, outcome_path = _decomposition_paths(paths, item_id, development=True)
        intent = read_json_object(intent_path)
        if intent.get("instrument") != dict(_decomposition_identity()):
            raise V3EvaluationError(f"frozen development intent changed: {item_id}")
        outcome = _validate_decomposition_pair(
            paths,
            item_id=item_id,
            intent=intent,
            development=True,
        )
        if outcome_hashes.get(item_id) != canonical_json_sha256(outcome):
            raise V3EvaluationError(f"frozen development outcome hash changed: {item_id}")
    return value


def run_held_out_decomposition_phase(
    cohort: PreparedV3Cohort,
    *,
    client: object,
    maximum_usd: Decimal = MASTER_COST_CAP_USD,
) -> None:
    from evaluation_decomposition_v2 import decompose_answer_claims_v2

    require_instrument_freeze(cohort.paths)
    require_complete_generation(cohort)
    identity = dict(_decomposition_identity())
    freeze_sha256 = sha256_file(cohort.paths.instrument_freeze)
    for item in cohort.items:
        item_id = _required_string(item, "id")
        generated = read_json_object(_item_dir(cohort.paths, item_id) / "generation.json")
        answer = _required_string(generated, "answer")
        intent_path, outcome_path = _decomposition_paths(cohort.paths, item_id, development=False)
        intent = {
            "schema": V3_DECOMPOSITION_INTENT_SCHEMA,
            "evaluation_id": EVALUATION_ID,
            "item_id": item_id,
            "answer_sha256": generated["answer_sha256"],
            "instrument": identity,
            "instrument_freeze_sha256": freeze_sha256,
            "input_boundary": "answer_only_no_gold_no_source_text",
            "attempt_count": 1,
            "automatic_retries": 0,
            "master_request_id": MASTER_REQUEST_ID,
        }
        if _intent_or_resume(intent_path=intent_path, outcome_path=outcome_path, intent=intent):
            _validate_decomposition_pair(
                cohort.paths,
                item_id=item_id,
                intent=intent,
                development=False,
            )
            continue
        capturing = _capturing_attempt_client(
            client,
            intent_path=intent_path,
            intent=intent,
        )
        result = None
        failure: Exception | None = None
        try:
            with master_usage_scope(cohort.paths, maximum_usd=maximum_usd, turn_id=f"{item_id}:decomposition"):
                result = decompose_answer_claims_v2(capturing, answer=answer)
        except Exception as exc:
            if capturing.attempt_count == 0:
                raise
            failure = exc
        evidence = _turn_operation_evidence(
            cohort.paths,
            turn_id=f"{item_id}:decomposition",
            expected_operation=str(identity["operation"]),
        )
        outcome = _decomposition_outcome(
            item_id=item_id,
            answer_sha256=str(generated["answer_sha256"]),
            intent=intent,
            result=result,
            failure=failure,
            capturing=capturing,
            evidence=evidence,
        )
        write_json_no_overwrite(outcome_path, outcome)
        _validate_decomposition_pair(
            cohort.paths,
            item_id=item_id,
            intent=intent,
            development=False,
        )
    require_complete_decomposition(cohort)


def require_complete_decomposition(cohort: PreparedV3Cohort) -> None:
    missing = []
    for item in cohort.items:
        item_id = _required_string(item, "id")
        _, path = _decomposition_paths(cohort.paths, item_id, development=False)
        if not path.is_file():
            missing.append(item_id)
    if missing:
        raise V3EvaluationError(f"decomposition phase is incomplete: {missing}")
    identity = dict(_decomposition_identity())
    freeze_sha256 = sha256_file(cohort.paths.instrument_freeze)
    for item in cohort.items:
        item_id = _required_string(item, "id")
        generated = read_json_object(_item_dir(cohort.paths, item_id) / "generation.json")
        intent = {
            "schema": V3_DECOMPOSITION_INTENT_SCHEMA,
            "evaluation_id": EVALUATION_ID,
            "item_id": item_id,
            "answer_sha256": generated["answer_sha256"],
            "instrument": identity,
            "instrument_freeze_sha256": freeze_sha256,
            "input_boundary": "answer_only_no_gold_no_source_text",
            "attempt_count": 1,
            "automatic_retries": 0,
            "master_request_id": MASTER_REQUEST_ID,
        }
        _validate_decomposition_pair(
            cohort.paths,
            item_id=item_id,
            intent=intent,
            development=False,
        )


def _validate_rubric_pair(
    cohort: PreparedV3Cohort,
    *,
    item: Mapping[str, object],
    intent: Mapping[str, object],
) -> Mapping[str, object]:
    item_id = _required_string(item, "id")
    root = _item_dir(cohort.paths, item_id)
    intent_path = root / "rubric-intent.json"
    outcome_path = root / "rubric.json"
    if not intent_path.is_file() or read_json_object(intent_path) != dict(intent):
        raise V3EvaluationError(f"{item_id} rubric intent is missing or changed")
    outcome = read_json_object(outcome_path)
    expected_attempts = int(intent["attempt_count"])
    for field, expected in {
        "schema": V3_RUBRIC_OUTCOME_SCHEMA,
        "item_id": item_id,
        "measurement_status": "exploratory_uncalibrated",
        "answer_sha256": intent["answer_sha256"],
        "decomposition_sha256": intent["decomposition_sha256"],
        "intent_sha256": canonical_json_sha256(intent),
        "provider_attempt_count": expected_attempts,
        "attempt_count": expected_attempts,
        "automatic_retries": 0,
    }.items():
        if outcome.get(field) != expected:
            raise V3EvaluationError(f"{item_id} rubric outcome changed {field}")
    status = outcome.get("status")
    allowed = {"scored", "technical_failure", "not_scored_decomposition_failure"}
    if status not in allowed:
        raise V3EvaluationError(f"{item_id} rubric status is invalid")
    current_evidence = _turn_operation_evidence(
        cohort.paths,
        turn_id=f"{item_id}:rubric",
        expected_operation="eval_item_rubric",
    )
    if outcome.get("operation_evidence") != current_evidence:
        raise V3EvaluationError(f"{item_id} rubric usage evidence changed")
    provider = outcome.get("provider")
    response_observed = bool(isinstance(provider, Mapping) and provider.get("id"))
    if expected_attempts:
        _require_operation_evidence(
            current_evidence,
            completed_response_required=(status == "scored" or response_observed),
            label=f"{item_id} rubric",
        )
    elif current_evidence["event_count"] != 0:
        raise V3EvaluationError(f"{item_id} unscored rubric recorded a provider event")
    if status == "scored":
        if not isinstance(outcome.get("coverage"), Mapping) or not isinstance(
            outcome.get("verdict"), Mapping
        ):
            raise V3EvaluationError(f"{item_id} scored rubric has no verdict")
        if not isinstance(provider, Mapping) or provider.get("model") != JUDGE_MODEL:
            raise V3EvaluationError(f"{item_id} rubric provider model changed")
    return outcome


def require_complete_rubric(cohort: PreparedV3Cohort) -> None:
    missing = []
    for item in cohort.items:
        item_id = _required_string(item, "id")
        if not (_item_dir(cohort.paths, item_id) / "rubric.json").is_file():
            missing.append(item_id)
    if missing:
        raise V3EvaluationError(f"rubric phase is incomplete: {missing}")
    for item in cohort.items:
        item_id = _required_string(item, "id")
        generated = read_json_object(_item_dir(cohort.paths, item_id) / "generation.json")
        decomposition = read_json_object(_item_dir(cohort.paths, item_id) / "decomposition.json")
        intent = {
            "schema": V3_RUBRIC_INTENT_SCHEMA,
            "evaluation_id": EVALUATION_ID,
            "item_id": item_id,
            "answer_sha256": generated["answer_sha256"],
            "decomposition_sha256": canonical_json_sha256(decomposition),
            "measurement_status": "exploratory_uncalibrated",
            "phase_precondition": "all_37_generation_and_decomposition_outcomes_sealed",
            "attempt_count": 1 if decomposition.get("status") == "valid" else 0,
            "automatic_retries": 0,
            "master_request_id": MASTER_REQUEST_ID,
        }
        _validate_rubric_pair(cohort, item=item, intent=intent)


def run_exploratory_rubric_phase(
    cohort: PreparedV3Cohort,
    *,
    client: object,
    maximum_usd: Decimal = MASTER_COST_CAP_USD,
) -> None:
    from evaluation_decomposition_v2 import (
        aggregate_gold_claim_coverage,
        judge_item_rubric_v2,
    )
    from evaluation_judge import AtomicClaim, ClaimDecomposition

    require_complete_generation(cohort)
    require_complete_decomposition(cohort)
    for item in cohort.items:
        item_id = _required_string(item, "id")
        generated = read_json_object(_item_dir(cohort.paths, item_id) / "generation.json")
        decomposition = read_json_object(_item_dir(cohort.paths, item_id) / "decomposition.json")
        root = _item_dir(cohort.paths, item_id)
        intent_path = root / "rubric-intent.json"
        outcome_path = root / "rubric.json"
        intent = {
            "schema": V3_RUBRIC_INTENT_SCHEMA,
            "evaluation_id": EVALUATION_ID,
            "item_id": item_id,
            "answer_sha256": generated["answer_sha256"],
            "decomposition_sha256": canonical_json_sha256(decomposition),
            "measurement_status": "exploratory_uncalibrated",
            "phase_precondition": "all_37_generation_and_decomposition_outcomes_sealed",
            "attempt_count": 1 if decomposition.get("status") == "valid" else 0,
            "automatic_retries": 0,
            "master_request_id": MASTER_REQUEST_ID,
        }
        if _intent_or_resume(intent_path=intent_path, outcome_path=outcome_path, intent=intent):
            _validate_rubric_pair(cohort, item=item, intent=intent)
            continue
        if decomposition.get("status") != "valid":
            write_json_no_overwrite(intent_path, intent)
            write_json_no_overwrite(
                outcome_path,
                {
                    "schema": V3_RUBRIC_OUTCOME_SCHEMA,
                    "item_id": item_id,
                    "status": "not_scored_decomposition_failure",
                    "measurement_status": "exploratory_uncalibrated",
                    "answer_sha256": generated["answer_sha256"],
                    "decomposition_sha256": canonical_json_sha256(decomposition),
                    "intent_sha256": canonical_json_sha256(intent),
                    "provider_attempt_count": 0,
                    "operation_evidence": _turn_operation_evidence(
                        cohort.paths,
                        turn_id=f"{item_id}:rubric",
                        expected_operation="eval_item_rubric",
                    ),
                    "attempt_count": 0,
                    "automatic_retries": 0,
                },
            )
            _validate_rubric_pair(cohort, item=item, intent=intent)
            continue
        claims = ClaimDecomposition(
            claims=[AtomicClaim.model_validate(value) for value in decomposition["claims"]]
        )
        rubric = build_item_rubric_input(
            question=_required_string(item, "question"),
            gold_item=item,
        )
        capturing = _capturing_attempt_client(
            client,
            intent_path=intent_path,
            intent=intent,
        )
        result = None
        failure: Exception | None = None
        try:
            with master_usage_scope(cohort.paths, maximum_usd=maximum_usd, turn_id=f"{item_id}:rubric"):
                result = judge_item_rubric_v2(
                    capturing,
                    answer=_required_string(generated, "answer"),
                    decomposition=claims,
                    rubric=rubric,
                )
        except Exception as exc:
            if capturing.attempt_count == 0:
                raise
            failure = exc
        evidence = _turn_operation_evidence(
            cohort.paths,
            turn_id=f"{item_id}:rubric",
            expected_operation="eval_item_rubric",
        )
        if result is not None:
            coverage = aggregate_gold_claim_coverage(rubric=rubric, verdict=result.parsed)
            outcome: dict[str, object] = {
                "schema": V3_RUBRIC_OUTCOME_SCHEMA,
                "item_id": item_id,
                "status": "scored",
                "measurement_status": "exploratory_uncalibrated",
                "formal_or_owner_adjudicated": False,
                "verdict": result.parsed.model_dump(mode="json"),
                "coverage": asdict(coverage),
                "provider": asdict(result.provider),
            }
        else:
            assert failure is not None
            outcome = {
                "schema": V3_RUBRIC_OUTCOME_SCHEMA,
                "item_id": item_id,
                "status": "technical_failure",
                "measurement_status": "exploratory_uncalibrated",
                "failure_type": type(failure).__name__,
                "provider": _judge_failure_provider(capturing, failure),
            }
        provider = outcome.get("provider")
        response_observed = bool(isinstance(provider, Mapping) and provider.get("id"))
        try:
            _require_operation_evidence(
                evidence,
                completed_response_required=(result is not None or response_observed),
                label=f"{item_id} rubric",
            )
        except V3EvaluationError as exc:
            outcome["status"] = "technical_failure"
            outcome["failure_type"] = "UsageEventContractFailure"
            outcome["usage_event_contract_error"] = str(exc)
            outcome.pop("verdict", None)
            outcome.pop("coverage", None)
        outcome.update(
            {
                "answer_sha256": generated["answer_sha256"],
                "decomposition_sha256": canonical_json_sha256(decomposition),
                "intent_sha256": canonical_json_sha256(intent),
                "provider_attempt_count": capturing.attempt_count,
                "operation_evidence": evidence,
                "attempt_count": 1,
                "automatic_retries": 0,
            }
        )
        write_json_no_overwrite(outcome_path, outcome)
        _validate_rubric_pair(cohort, item=item, intent=intent)
    require_complete_rubric(cohort)


def _percentile(values: Sequence[float], proportion: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil(proportion * len(ordered)) - 1))
    return ordered[rank]


def build_public_summary(cohort: PreparedV3Cohort) -> dict[str, object]:
    require_complete_generation(cohort)
    require_complete_decomposition(cohort)
    require_complete_rubric(cohort)
    generations = [
        read_json_object(_item_dir(cohort.paths, _required_string(item, "id")) / "generation.json")
        for item in cohort.items
    ]
    decompositions = []
    rubrics = []
    for item in cohort.items:
        item_id = _required_string(item, "id")
        decomp = _item_dir(cohort.paths, item_id) / "decomposition.json"
        rubric = _item_dir(cohort.paths, item_id) / "rubric.json"
        decompositions.append(read_json_object(decomp))
        rubrics.append(read_json_object(rubric))
    latencies = [
        float(value["timings_ms"]["authored_response_boundary"])
        for value in generations
    ]
    statuses = Counter(str(value["status"]) for value in generations)
    dispositions = Counter(
        str(value.get("disposition") or "not_applicable_fallback")
        for value in generations
    )
    failure_codes = Counter(
        str(value["failure_code"])
        for value in generations
        if value.get("failure_code") is not None
    )
    citation_fields = (
        "well_formed_group_count",
        "source_reference_count",
        "malformed_bracket_token_count",
        "resolvable_group_count",
        "resolvable_reference_count",
        "out_of_range_reference_count",
    )
    citations = {
        field: sum(int(value["citation_audit"][field]) for value in generations)
        for field in citation_fields
    }
    retrieval: dict[str, object] = {}
    for label in (*[f"primary_at_{k}" for k in K_VALUES], "finalized", "dossier", "cited"):
        scored = []
        for value in generations:
            if label.startswith("primary_at_"):
                k = label.removeprefix("primary_at_")
                metrics = value["retrieval"]["primary_by_k"][k]["metrics"]
            else:
                metrics = value["retrieval"][label]["metrics"]
            if metrics["recall"] is not None:
                scored.append(metrics)
        retrieval[label] = {
            "applicable_items": len(scored),
            "macro_recall": (
                sum(float(metrics["recall"]) for metrics in scored) / len(scored)
                if scored
                else None
            ),
            "hit_rate": (
                sum(bool(metrics["hit"]) for metrics in scored) / len(scored)
                if scored
                else None
            ),
            "essential_claim_context_coverage": (
                sum(int(metrics["covered_essential_claim_count"]) for metrics in scored)
                / sum(int(metrics["essential_claim_count"]) for metrics in scored)
                if sum(int(metrics["essential_claim_count"]) for metrics in scored)
                else None
            ),
        }
    retrieval["fallbacks"] = {
        "raw_primary_fallback_item_count": sum(
            bool(value["retrieval"]["fallbacks"]["raw_primary_fallback_used"])
            for value in generations
        ),
        "fusion_pool_fallback_item_count": sum(
            bool(value["retrieval"]["fallbacks"]["fusion_pool_fallback_used"])
            for value in generations
        ),
    }
    retrieval["displacement_counts"] = dict(
        sum(
            (
                Counter(value["retrieval"]["displacement_counts"])
                for value in generations
            ),
            Counter(),
        )
    )
    coverage_rows = [value["coverage"] for value in rubrics if value.get("status") == "scored"]
    valid_claims = [
        claim
        for value in decompositions
        if value.get("status") == "valid"
        for claim in value.get("claims", [])
        if isinstance(claim, Mapping)
    ]
    cited_claim_count = sum(bool(claim.get("cited_sources")) for claim in valid_claims)
    all_total = sum(int(value["all_total"]) for value in coverage_rows)
    all_present = sum(int(value["all_present"]) for value in coverage_rows)
    essential_total = sum(int(value["essential_total"]) for value in coverage_rows)
    essential_present = sum(int(value["essential_present"]) for value in coverage_rows)
    item_by_id = {_required_string(item, "id"): item for item in cohort.items}
    rubric_by_id = {str(value["item_id"]): value for value in rubrics}
    by_stratum: dict[str, object] = {}
    for stratum in sorted({_required_string(item, "stratum") for item in cohort.items}):
        stratum_generations = [
            value
            for value in generations
            if _required_string(item_by_id[str(value["item_id"])], "stratum") == stratum
        ]
        context_metrics = [
            value["retrieval"]["finalized"]["metrics"]
            for value in stratum_generations
            if value["retrieval"]["finalized"]["metrics"]["recall"] is not None
        ]
        stratum_coverages = [
            rubric_by_id[str(value["item_id"])]["coverage"]
            for value in stratum_generations
            if str(value["item_id"]) in rubric_by_id
            and rubric_by_id[str(value["item_id"])].get("status") == "scored"
        ]
        stratum_all_total = sum(int(value["all_total"]) for value in stratum_coverages)
        stratum_all_present = sum(int(value["all_present"]) for value in stratum_coverages)
        by_stratum[stratum] = {
            "item_count": len(stratum_generations),
            "generation_fallback_count": sum(
                value["status"] == "essential_fallback" for value in stratum_generations
            ),
            "authored_response_boundary_latency_median_ms": median(
                [
                    float(value["timings_ms"]["authored_response_boundary"])
                    for value in stratum_generations
                ]
            ),
            "finalized_context_macro_recall": (
                sum(float(value["recall"]) for value in context_metrics)
                / len(context_metrics)
                if context_metrics
                else None
            ),
            "exploratory_gold_claim_present_rate": (
                stratum_all_present / stratum_all_total if stratum_all_total else None
            ),
        }
    ledger = UsageLedger(cohort.paths.ledger)
    usage = ledger.summary(recent_limit=0) if cohort.paths.ledger.exists() else None
    return {
        "schema": V3_PUBLIC_SUMMARY_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "classification": COHORT_CLASSIFICATION,
        "product_commit": PRODUCT_COMMIT,
        "harness_commit": cohort.manifest["system_under_test"]["harness_commit"],
        "item_count": len(generations),
        "phase_completeness": {
            "generation_outcomes": len(generations),
            "decomposition_outcomes": len(decompositions),
            "rubric_outcomes": len(rubrics),
            "expected_each": EXPECTED_ITEM_COUNT,
            "all_required_phases_complete": (
                len(generations)
                == len(decompositions)
                == len(rubrics)
                == EXPECTED_ITEM_COUNT
            ),
        },
        "generation": {
            "status_counts": dict(statuses),
            "disposition_counts": dict(dispositions),
            "failure_code_counts": dict(failure_codes),
            "fallback_count": statuses["essential_fallback"],
            "attempt_count": sum(int(value["attempt_count"]) for value in generations),
            "automatic_retries": 0,
            "query_embedding_provider_operations": 0,
        },
        "authored_response_boundary_wall_time_ms": {
            "count": len(latencies),
            "median": median(latencies) if latencies else None,
            "p95_nearest_rank": _percentile(latencies, 0.95),
            "minimum": min(latencies) if latencies else None,
            "maximum": max(latencies) if latencies else None,
            "scope": (
                "request construction plus provider wait, SDK structured parsing, and local "
                "authored-response validation/rendering; cached-vector retrieval and dossier "
                "construction excluded; not a provider-only or end-to-end latency metric"
            ),
        },
        "retrieval": retrieval,
        "by_stratum": by_stratum,
        "citation_syntax_and_local_resolvability": {
            **citations,
            "answer_scope": "all rendered answers, including Essential fallbacks",
            "not_measured": "semantic entailment, source correctness, or faithfulness",
        },
        "citation_completeness": {
            "cited_factual_claims": cited_claim_count,
            "decomposed_factual_claims": len(valid_claims),
            "rate": (
                cited_claim_count / len(valid_claims) if valid_claims else None
            ),
            "scope": "only schema-valid exact-text decompositions",
        },
        "cited_chunk_gold_location_overlap": {
            "matches": sum(int(value["cited_source_gold_location_matches"]) for value in generations),
            "total": sum(int(value["cited_source_gold_location_total"]) for value in generations),
            "definition": (
                "mechanical overlap between locally resolved cited chunk IDs and the gold "
                "relevant_chunk_ids set; not citation entailment or semantic accuracy"
            ),
        },
        "decomposition": {
            "outcome_count": len(decompositions),
            "valid_count": sum(value.get("status") == "valid" for value in decompositions),
            "technical_failure_count": sum(
                value.get("status") == "technical_failure" for value in decompositions
            ),
        },
        "gold_claim_coverage": {
            "measurement_status": "exploratory_uncalibrated",
            "formal_or_owner_adjudicated": False,
            "scored_item_count": len(coverage_rows),
            "all_claims_present": all_present,
            "all_claims_total": all_total,
            "all_claim_present_rate": all_present / all_total if all_total else None,
            "essential_claims_present": essential_present,
            "essential_claims_total": essential_total,
            "essential_claim_present_rate": (
                essential_present / essential_total if essential_total else None
            ),
            "must_not_claim_asserted": sum(
                int(value["must_not_claim_asserted"]) for value in coverage_rows
            ),
        },
        "cost": {
            "maximum_total_usd": float(MASTER_COST_CAP_USD),
            "recorded_total_usd": usage["all_time_usd"] if usage else 0.0,
            "unpriced_events": usage["unpriced_events"] if usage else 0,
            "operations": usage["operations"] if usage else [],
            "shared_with_development_and_social_phases": True,
        },
        "limitations": [
            "The benchmark was reused after prior V26 exposure and is not pristine held-out data.",
            "Cached query vectors eliminate query-embedding calls; reported authoring-boundary wall time is neither provider-only nor end-to-end latency.",
            "Semantic gold-claim coverage is an exploratory uncalibrated judge estimate, not owner-adjudicated formal scoring.",
            "Canonical model names are mutable provider snapshots; requested and returned IDs are retained per item.",
        ],
    }


def write_public_summary(cohort: PreparedV3Cohort) -> dict[str, object]:
    summary = build_public_summary(cohort)
    path = cohort.paths.root / "public-summary.json"
    write_or_validate_json(path, summary)
    return summary


__all__ = [
    "COHORT_CLASSIFICATION",
    "EVALUATION_ID",
    "MASTER_COST_CAP_NANO_USD",
    "MASTER_COST_CAP_USD",
    "MASTER_REQUEST_ID",
    "PRODUCT_COMMIT",
    "PreparedV3Cohort",
    "ProviderCapturingClient",
    "V3EvaluationError",
    "V3Paths",
    "build_public_summary",
    "build_v3_manifest",
    "canonical_json_sha256",
    "default_paths",
    "freeze_decomposition_instrument",
    "generate_professional_item",
    "master_usage_scope",
    "prepare_v3_cohort",
    "preflight_all_cached_items",
    "require_complete_decomposition",
    "require_complete_generation",
    "require_instrument_freeze",
    "retrieve_with_cached_embedding",
    "run_development_decomposition_phase",
    "run_exploratory_rubric_phase",
    "run_generation_phase",
    "run_held_out_decomposition_phase",
    "write_public_summary",
]
