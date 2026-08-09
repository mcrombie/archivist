from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence
from uuid import uuid4

import chromadb


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from answer_evaluation import (  # noqa: E402
    AnswerEvaluationCohortManifest,
    CalibrationLabelFile,
    CohortItemBinding,
    DecomposedPilotItem,
    InstrumentLock,
    PrivateDecompositionCheckpoint,
    PrivateGeneratedItem,
    PrivateGenerationCheckpoint,
    PrivateTraceReference,
    PrivateUsageEvent,
    PublicPrecalibrationSummary,
    PublicEvaluationSummary,
    ScoringDimension,
    ScoringMode,
    PRIVATE_DECOMPOSITION_CHECKPOINT_SCHEMA,
    build_cohort_manifest,
    build_calibration_label_template,
    build_decomposed_claim,
    build_decomposed_pilot_item,
    build_instrument_lock,
    build_private_decomposition_checkpoint,
    build_private_generated_item,
    build_private_generation_checkpoint,
    build_private_source,
    build_private_usage_event,
    canonical_json_sha256,
    sha256_file,
    validate_calibration_labels_for_judge,
    validate_cohort_manifest,
    validate_private_decomposition_checkpoint,
    validate_private_generation_checkpoint,
    validate_public_precalibration_summary,
    validate_public_summary,
    write_json_atomic_no_overwrite,
)
from answer_coverage import EvidenceCoverageAnswer  # noqa: E402
from archivist_modes import ArchivistMode, archivist_mode_metadata  # noqa: E402
from corpus import load_chunks  # noqa: E402
from costs import UsageLedger, usage_scope  # noqa: E402
from evaluation_artifacts import (  # noqa: E402
    SmokeArtifactRecorder,
    build_corpus_identity,
    build_git_worktree_identity,
)
from evaluation_judge import (  # noqa: E402
    AtomicClaim,
    CLAIM_EVIDENCE_PROMPT_SHA256,
    CLAIM_EVIDENCE_PROMPT_VERSION,
    CLAIM_DECOMPOSITION_PROMPT_SHA256,
    CLAIM_DECOMPOSITION_PROMPT_VERSION,
    ITEM_RUBRIC_PROMPT_SHA256,
    ITEM_RUBRIC_PROMPT_VERSION,
    ClaimDecomposition,
    ClaimEvidenceVerdict,
    ItemRubricVerdict,
    JUDGE_MODEL,
    JUDGE_SETTINGS,
    build_item_rubric_input,
    decompose_answer_claims,
    judge_claim_evidence,
    judge_item_rubric,
)
from evaluation_results import (  # noqa: E402
    BaselineSemanticAggregate,
    BaselineSemanticItem,
    CalibrationAgreementProjection,
    CalibrationSemanticAggregate,
    ClaimEvidenceResult,
    DecompositionStability,
    ItemRubricResult,
    ManualScoringAggregate,
    PrecalibrationPrivateArtifact,
    PrivateFullRunArtifact,
    build_baseline_semantic_aggregate,
    build_baseline_semantic_item,
    build_baseline_semantic_item_from_calibration,
    build_calibration_semantic_aggregate,
    build_calibration_semantic_item,
    build_claim_evidence_result,
    build_decomposition_stability,
    build_item_rubric_result,
    build_manual_scoring_aggregate,
    build_private_full_run_artifact,
    build_precalibration_private_artifact,
    project_calibration_agreement,
    validate_calibration_semantic_aggregate,
    validate_claim_evidence_result,
    validate_decomposition_stability,
    validate_item_rubric_result,
    validate_baseline_semantic_aggregate,
    validate_manual_scoring_aggregate,
    validate_private_full_run_artifact,
    validate_precalibration_private_artifact,
)
from evaluation_reporting import (  # noqa: E402
    build_public_precalibration_summary,
    build_public_evaluation_summary,
    render_public_precalibration_markdown,
    render_public_evaluation_markdown,
)
from evaluation_scoring import select_calibration_item_ids  # noqa: E402
from evidence_policy import tokenize_anchor  # noqa: E402
from gold_provenance import validate_gold_provenance_file  # noqa: E402
from gold_set import validate_gold_set_file  # noqa: E402
from model_config import GENERATOR_SETTINGS, QUERY_PLANNER_SETTINGS  # noqa: E402
from perspectives import AnswerVoice, HistoriographicalLens, Worldview  # noqa: E402
from query_planning import ResolvedTurn, build_question_plan  # noqa: E402
from query_planning import PlannerQuestionPlan, QUERY_PLANNER_INSTRUCTIONS  # noqa: E402
from rag_pipeline import (  # noqa: E402
    EVIDENCE_PLANNED_POLICY,
    EVIDENCE_COVERAGE_INSTRUCTIONS,
    EVIDENCE_COVERAGE_PROMPT_VERSION,
    QUERY_PLANNER_ADDITIONAL_INSTRUCTIONS,
    QUERY_PLANNER_PROMPT_VERSION,
    RAG_POLICY_VERSION,
    STRUCTURAL_STAGE_SHORTFALL_MESSAGE,
    _clean_abstention,
    preflight_answer_corpus,
    run_evidence_planned_answer,
)
from retrieval import MAX_FINAL_SOURCES, MAX_PRIMARY_DISTANCE  # noqa: E402
from retrieval_benchmark import LockedGold, load_locked_gold  # noqa: E402
from validate_gold_holdout import validate_candidate_lock  # noqa: E402


EVALUATION_ID = "v26-held-out-answer-quality-2026-08-07"
CALIBRATION_GENERATION_SCHEMA = "archivist.answer_evaluation.calibration_generation/1"
CALIBRATION_DECOMPOSITION_SCHEMA = "archivist.answer_evaluation.calibration_decomposition/1"
BASELINE_GENERATION_SCHEMA = "archivist.answer_evaluation.baseline_generation/1"
BASELINE_DECOMPOSITION_SCHEMA = "archivist.answer_evaluation.baseline_decomposition/1"
DECOMPOSITION_CHECKPOINT_SCHEMA = PRIVATE_DECOMPOSITION_CHECKPOINT_SCHEMA
CALIBRATION_REPETITIONS = 3
FIXED_CALIBRATION_IDS = (
    "H001",
    "H009",
    "H017",
    "H023",
    "H033",
    "H034",
    "H035",
    "H036",
    "H037",
    "H038",
)
CALIBRATION_COST_ESTIMATE_LOW_USD = 1.75
CALIBRATION_COST_ESTIMATE_HIGH_USD = 3.50
CALIBRATION_RECOMMENDED_CAP_USD = 4.00
FULL_EVALUATION_COST_ESTIMATE_LOW_USD = 6.00
FULL_EVALUATION_COST_ESTIMATE_HIGH_USD = 12.00
FULL_EVALUATION_RECOMMENDED_CAP_USD = 20.00
GENERATION_ITEM_COST_RESERVE_USD = 0.80
DECOMPOSITION_CALL_COST_RESERVE_USD = 0.15
CLAIM_EVIDENCE_CALL_COST_RESERVE_USD = 0.15
ITEM_RUBRIC_CALL_COST_RESERVE_USD = 0.20
EMBEDDING_MODEL = "text-embedding-3-small"
INSTRUMENT_ID = "v26-held-out-answer-quality-scoring-lock"
INTERRUPTED_RUNNER_SHA256 = "c79edf5287f9c7fa3e1c9a54a287c555a4c0d25917187422d7d5b38ef7806f84"
INTERRUPTED_COHORT_FILE_SHA256 = "4828f20d20a9d2de35e04f81265da45259139e96b4a0c28397933d0c71aca56e"
INTERRUPTED_GENERATED_CHECKPOINT_SHA256S = {
    "H001": "8899e3756b2405ca1e92cc6eb6a058679e08efaf1b5c5282537ad0021280368c",
    "H002": "cd57cf9a2caf4e23f7b561443ba9b90a1996f565709659c6d1d4decdcf865618",
}
INTERRUPTED_H003_TRACE_SHA256 = "ad968ef4d972bd738a387149bf578ccc9a1b9fe0b8de8e0f4387225c73f19e20"

DEFAULT_GOLD = BASE_DIR / "fixtures" / "gold_set.json"
DEFAULT_PROVENANCE = BASE_DIR / "fixtures" / "gold_set.provenance.json"
DEFAULT_MANIFEST = BASE_DIR / "fixtures" / "corpus_manifest.json"
DEFAULT_REGISTRY = BASE_DIR / "fixtures" / "development_question_registry.json"
DEFAULT_COMMITMENT = BASE_DIR / "fixtures" / "gold_questions.commitment.json"
DEFAULT_CATALOG = BASE_DIR / "fixtures" / "evaluation_model_catalog.json"
DEFAULT_CHUNKS = BASE_DIR / "output" / "chunks.json"
DEFAULT_RUN_ROOT = BASE_DIR / "runtime" / "evaluations" / EVALUATION_ID
DEFAULT_RECOVERY_ROOT = DEFAULT_RUN_ROOT.with_name(EVALUATION_ID + "-harness-recovery-01")
DEFAULT_LABELS = DEFAULT_RUN_ROOT / "calibration-labels.json"
PRIVATE_EVALUATION_ROOT = (BASE_DIR / "runtime" / "evaluations").resolve()

NEXT_ACTION_OWNER_LABELS = "complete-owner-labels-then-run-validate-labels"
NEXT_ACTION_CALIBRATION_JUDGE = "run-separately-authorized-calibration-judge"
NEXT_ACTION_LOCK_INSTRUMENT = "owner-ratify-and-lock-scoring-instrument"
NEXT_ACTION_BASELINE = "complete_37_question_evaluation"


class AnswerEvaluationError(RuntimeError):
    """A fail-closed answer-evaluation precondition or artifact error."""


def _require_private_run_root(path: Path) -> Path:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(PRIVATE_EVALUATION_ROOT)
    except ValueError as exc:
        raise AnswerEvaluationError(
            "evaluation run root must stay under gitignored runtime/evaluations"
        ) from exc
    if not relative.parts:
        raise AnswerEvaluationError(
            "evaluation run root must be a named child of runtime/evaluations"
        )
    return resolved


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    gold: LockedGold
    gold_items: tuple[Mapping[str, object], ...]
    calibration_ids: tuple[str, ...]
    calibration_items: tuple[Mapping[str, object], ...]
    remaining_ids: tuple[str, ...]
    manifest: Mapping[str, object]
    manifest_sha256: str
    chunks: list[dict[str, Any]]
    collection: object
    corpus_identity: Mapping[str, object]
    corpus_trace: Mapping[str, object]
    model_catalog: Mapping[str, object]
    model_catalog_sha256: str
    run_identity: Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen V26 held-out answer-quality workflow. Preflight is offline; "
            "every external phase has its own explicit authorization flag and cost ceiling."
        )
    )
    parser.add_argument(
        "command",
        choices=(
            "preflight",
            "recover-interrupted",
            "run-37",
            "calibration-generate",
            "validate-labels",
            "calibration-judge",
            "lock-instrument",
            "baseline",
            "report",
        ),
    )
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--question-commitment", type=Path, default=DEFAULT_COMMITMENT)
    parser.add_argument("--model-catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--source-run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument(
        "--authorize-openai-full-evaluation",
        action="store_true",
        help=(
            "Authorize all 37 frozen V26 RAG turns and one canonical answer-only Terra "
            "decomposition per answer. No calibration repeats or semantic judge verdicts "
            "are included."
        ),
    )
    parser.add_argument(
        "--authorize-openai-calibration-generation",
        action="store_true",
        help=("Retired: use run-37 and --authorize-openai-full-evaluation."),
    )
    parser.add_argument(
        "--authorize-openai-calibration-judge",
        action="store_true",
        help="Authorize semantic calibration only after complete owner labels validate.",
    )
    parser.add_argument(
        "--authorize-openai-remaining-baseline",
        action="store_true",
        help=(
            "Authorize later semantic-scoring calls after the optional instrument lock. "
            "This phase cannot generate or decompose missing answers."
        ),
    )
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument(
        "--owner-ratifies-scoring-lock",
        action="store_true",
        help="Required by lock-instrument after calibration results exist.",
    )
    return parser


def _load_json_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AnswerEvaluationError(f"{label} is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AnswerEvaluationError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AnswerEvaluationError(f"{label} must be a JSON object: {path}")
    return value


def _required_string(value: Mapping[str, object], field: str, *, label: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise AnswerEvaluationError(f"{label} is missing nonempty {field}")
    return result


def _validate_model_catalog(path: Path) -> tuple[dict[str, object], str]:
    catalog = _load_json_object(path, label="provider model catalog")
    if catalog.get("schema") != "archivist.provider_model_catalog/1":
        raise AnswerEvaluationError("provider model catalog schema is unsupported")
    if catalog.get("provider") != "OpenAI":
        raise AnswerEvaluationError("provider model catalog must name OpenAI")
    raw_models = catalog.get("models")
    if not isinstance(raw_models, list):
        raise AnswerEvaluationError("provider model catalog models must be an array")
    by_role: dict[str, Mapping[str, object]] = {}
    for model in raw_models:
        if not isinstance(model, Mapping):
            raise AnswerEvaluationError("provider model catalog entries must be objects")
        role = model.get("role")
        if not isinstance(role, str) or role in by_role:
            raise AnswerEvaluationError("provider model catalog roles must be unique strings")
        by_role[role] = model
    expected = {
        "generator_and_planner": GENERATOR_SETTINGS.model,
        "evaluation_judge": JUDGE_MODEL,
    }
    for role, model_name in expected.items():
        record = by_role.get(role)
        if record is None:
            raise AnswerEvaluationError(f"provider model catalog is missing role {role}")
        if record.get("requested_model") != model_name:
            raise AnswerEvaluationError(f"provider model catalog {role} model changed")
        if record.get("provider_current_snapshot") != model_name:
            raise AnswerEvaluationError(f"provider model catalog {role} snapshot changed")
        if record.get("immutable_dated_snapshot_exposed") is not False:
            raise AnswerEvaluationError(
                f"provider model catalog {role} dated-snapshot observation changed"
            )
    if QUERY_PLANNER_SETTINGS.model != GENERATOR_SETTINGS.model:
        raise AnswerEvaluationError("frozen planner and generator model identifiers diverged")
    return catalog, sha256_file(path)


def _validated_gold(args: argparse.Namespace) -> LockedGold:
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
    if gold.candidate_rag_policy != RAG_POLICY_VERSION:
        raise AnswerEvaluationError("active RAG policy differs from locked gold provenance")
    return gold


def _partition_gold_items(
    items: Sequence[Mapping[str, object]],
) -> tuple[
    tuple[str, ...],
    tuple[Mapping[str, object], ...],
    tuple[str, ...],
]:
    gold_ids = tuple(_required_string(item, "id", label="gold item") for item in items)
    if len(gold_ids) != len(set(gold_ids)):
        raise AnswerEvaluationError("gold item IDs are not unique")
    by_id = dict(zip(gold_ids, items, strict=True))
    calibration_ids = select_calibration_item_ids(items)
    if calibration_ids != FIXED_CALIBRATION_IDS:
        raise AnswerEvaluationError(
            "the fixed calibration selector changed: " + ", ".join(calibration_ids)
        )
    calibration_items = tuple(by_id[item_id] for item_id in calibration_ids)
    remaining_ids = tuple(item_id for item_id in gold_ids if item_id not in calibration_ids)
    if len(calibration_ids) != 10 or len(remaining_ids) != 27:
        raise AnswerEvaluationError("the fixed 10+27 cohort partition changed")
    return calibration_ids, calibration_items, remaining_ids


def _build_context(args: argparse.Namespace, *, require_clean: bool) -> EvaluationContext:
    gold = _validated_gold(args)
    if require_clean:
        validate_candidate_lock(BASE_DIR, gold.candidate_commit)
    run_identity = build_git_worktree_identity(BASE_DIR)
    if require_clean and run_identity.get("working_tree") != "clean":
        raise AnswerEvaluationError("paid held-out phases require a clean working tree")

    calibration_ids, calibration_items, remaining_ids = _partition_gold_items(gold.items)

    model_catalog, model_catalog_sha256 = _validate_model_catalog(args.model_catalog)
    manifest = _load_json_object(args.manifest, label="corpus manifest")
    corpus_identity = build_corpus_identity(
        manifest_path=args.manifest,
        chunks_path=args.chunks,
    )
    if corpus_identity.get("corpus_manifest_sha256") != gold.corpus_manifest_sha256:
        raise AnswerEvaluationError("active corpus differs from locked gold provenance")
    store = manifest.get("store")
    if not isinstance(store, Mapping):
        raise AnswerEvaluationError("corpus manifest store identity is missing")
    collection_name = _required_string(store, "collection_name", label="corpus store")
    collection = chromadb.PersistentClient(path=str(BASE_DIR / "chroma_db")).get_collection(
        name=collection_name,
        embedding_function=None,
    )
    chunks = load_chunks(args.chunks)
    integrity = preflight_answer_corpus(
        collection_handle=collection,
        chunks=chunks,
        corpus_manifest=manifest,
        corpus_manifest_sha256=str(corpus_identity["corpus_manifest_sha256"]),
        require_store_identity=True,
    )
    if not integrity.passed:
        raise AnswerEvaluationError(
            "active corpus/index integrity failed: " + ", ".join(integrity.failure_codes)
        )
    corpus_trace = {
        "collection_name": corpus_identity["collection_name"],
        "collection_count": int(collection.count()),
        "corpus_manifest_sha256": corpus_identity["corpus_manifest_sha256"],
        "chunks_sha256": corpus_identity["chunks_sha256"],
        "hnsw_space": corpus_identity["hnsw_space"],
    }
    return EvaluationContext(
        gold=gold,
        gold_items=gold.items,
        calibration_ids=calibration_ids,
        calibration_items=calibration_items,
        remaining_ids=remaining_ids,
        manifest=manifest,
        manifest_sha256=sha256_file(args.manifest),
        chunks=chunks,
        collection=collection,
        corpus_identity=corpus_identity,
        corpus_trace=corpus_trace,
        model_catalog=model_catalog,
        model_catalog_sha256=model_catalog_sha256,
        run_identity=run_identity,
    )


def _prompt_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _expected_cohort_manifest(
    context: EvaluationContext,
    *,
    runner_sha256: str,
) -> AnswerEvaluationCohortManifest:
    query_planner_prompt = QUERY_PLANNER_INSTRUCTIONS + "\n" + QUERY_PLANNER_ADDITIONAL_INSTRUCTIONS
    return build_cohort_manifest(
        evaluation_id=EVALUATION_ID,
        candidate_commit=context.gold.candidate_commit,
        rag_policy=context.gold.candidate_rag_policy,
        gold_set_sha256=context.gold.gold_set_sha256,
        question_set_sha256=context.gold.question_set_sha256,
        corpus_manifest_sha256=context.gold.corpus_manifest_sha256,
        chunks_sha256=str(context.corpus_identity["chunks_sha256"]),
        model_catalog_sha256=context.model_catalog_sha256,
        runner_sha256=runner_sha256,
        items=context.gold_items,
        calibration_item_ids=context.calibration_ids,
        generator={
            "model_id": GENERATOR_SETTINGS.model,
            "settings": {
                "reasoning_effort": GENERATOR_SETTINGS.reasoning_effort,
                "verbosity": GENERATOR_SETTINGS.verbosity,
            },
        },
        planner={
            "model_id": QUERY_PLANNER_SETTINGS.model,
            "settings": {
                "reasoning_effort": QUERY_PLANNER_SETTINGS.reasoning_effort,
                "verbosity": QUERY_PLANNER_SETTINGS.verbosity,
            },
        },
        judge={
            "model_id": JUDGE_MODEL,
            "settings": {
                "reasoning_effort": JUDGE_SETTINGS.reasoning_effort,
                "verbosity": JUDGE_SETTINGS.verbosity,
            },
        },
        embedding_model=EMBEDDING_MODEL,
        retrieval={
            "n_results": 5,
            "max_primary_distance": MAX_PRIMARY_DISTANCE,
            "max_final_sources": MAX_FINAL_SOURCES,
            "hnsw_space": context.corpus_identity["hnsw_space"],
            "neighbor_expansion_policy": "primaries_first_then_immediate_neighbors",
            "merge_adjacent_chunks": False,
            "collection_name": context.corpus_identity["collection_name"],
            "collection_count": int(context.collection.count()),
        },
        prompts=(
            {
                "prompt_id": "query_planner",
                "version": QUERY_PLANNER_PROMPT_VERSION,
                "prompt_sha256": _prompt_sha256(query_planner_prompt),
            },
            {
                "prompt_id": "evidence_coverage",
                "version": EVIDENCE_COVERAGE_PROMPT_VERSION,
                "prompt_sha256": _prompt_sha256(EVIDENCE_COVERAGE_INSTRUCTIONS),
            },
            {
                "prompt_id": "claim_decomposition",
                "version": CLAIM_DECOMPOSITION_PROMPT_VERSION,
                "prompt_sha256": CLAIM_DECOMPOSITION_PROMPT_SHA256,
            },
            {
                "prompt_id": "claim_evidence",
                "version": CLAIM_EVIDENCE_PROMPT_VERSION,
                "prompt_sha256": CLAIM_EVIDENCE_PROMPT_SHA256,
            },
            {
                "prompt_id": "item_rubric",
                "version": ITEM_RUBRIC_PROMPT_VERSION,
                "prompt_sha256": ITEM_RUBRIC_PROMPT_SHA256,
            },
        ),
        structured_outputs=(
            {
                "output_id": "planner_question_plan",
                "schema_sha256": canonical_json_sha256(PlannerQuestionPlan.model_json_schema()),
            },
            {
                "output_id": "evidence_coverage_answer",
                "schema_sha256": canonical_json_sha256(EvidenceCoverageAnswer.model_json_schema()),
            },
            {
                "output_id": "claim_decomposition",
                "schema_sha256": canonical_json_sha256(ClaimDecomposition.model_json_schema()),
            },
            {
                "output_id": "claim_evidence_verdict",
                "schema_sha256": canonical_json_sha256(ClaimEvidenceVerdict.model_json_schema()),
            },
            {
                "output_id": "item_rubric_verdict",
                "schema_sha256": canonical_json_sha256(ItemRubricVerdict.model_json_schema()),
            },
        ),
    )


def _load_or_write_cohort_manifest(
    path: Path,
    *,
    context: EvaluationContext,
    runner_sha256: str,
) -> tuple[AnswerEvaluationCohortManifest, str]:
    expected = _expected_cohort_manifest(context, runner_sha256=runner_sha256)
    if path.is_file():
        actual = AnswerEvaluationCohortManifest.model_validate(
            _load_json_object(path, label="answer-evaluation cohort manifest")
        )
        validate_cohort_manifest(actual, expected=expected)
    else:
        write_json_atomic_no_overwrite(path, expected)
        actual = expected
    return actual, sha256_file(path)


def _archive_bytes_no_overwrite(*, source: Path, destination: Path) -> None:
    payload = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        if destination.read_bytes() != payload:
            raise AnswerEvaluationError(f"immutable migration archive changed: {destination}")


def _usage_turn_ids(path: Path) -> tuple[str, ...]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            """
            SELECT DISTINCT turn_id FROM usage_events
            WHERE project_id = ? AND conversation_id = ?
            ORDER BY turn_id
            """,
            (EVALUATION_ID, "held-out-37"),
        ).fetchall()
    finally:
        connection.close()
    return tuple(str(row[0]) for row in rows)


def _logical_usage_bindings(path: Path) -> tuple[dict[str, object], ...]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT id, turn_id, response_id, operation, requested_model, actual_model,
                   input_tokens, cached_tokens, cache_write_tokens, output_tokens,
                   reasoning_tokens, total_tokens, estimated_cost_nano_usd,
                   pricing_version, unpriced
            FROM usage_events
            WHERE project_id = ? AND conversation_id = ? ORDER BY id
            """,
            (EVALUATION_ID, "held-out-37"),
        ).fetchall()
    finally:
        connection.close()
    bindings = []
    for ordinal, row in enumerate(rows, start=1):
        fields = {key: row[key] for key in row.keys() if key != "id"}
        bindings.append(
            {
                "ordinal": ordinal,
                "turn_id": str(row["turn_id"]),
                "response_id": str(row["response_id"]),
                "event_sha256": canonical_json_sha256(fields),
            }
        )
    return tuple(bindings)


def _print_preflight(context: EvaluationContext) -> None:
    print("VALID V26 ANSWER-EVALUATION PREFLIGHT")
    print(f"Candidate: {context.gold.candidate_commit} / {context.gold.candidate_rag_policy}")
    print(f"Gold set: {len(context.gold_items)} items / {context.gold.gold_set_sha256}")
    print(f"Question-set SHA-256: {context.gold.question_set_sha256}")
    print(
        f"Later calibration subset (never a generation gate): {', '.join(context.calibration_ids)}"
    )
    print(f"Full uninterrupted generation cohort: {len(context.gold_items)} questions")
    print(
        "Corpus/index: "
        f"{context.corpus_identity['embedded_chunk_count']} eligible chunks, "
        f"{context.corpus_identity['hnsw_space']} distance, identity verified"
    )
    print(
        "Models: planner/generator "
        f"{GENERATOR_SETTINGS.model}; judge/decomposer {JUDGE_MODEL}; "
        f"catalog SHA-256 {context.model_catalog_sha256}"
    )
    print("Working tree: " + str(context.run_identity["working_tree"]))
    print(
        "If separately authorized, run-37 executes 37 frozen V26 RAG turns. Each turn "
        "uses one batched text-embedding-3-small request and one gpt-5.6-sol generation; "
        "the existing pipeline may also use up to one gpt-5.6-sol planning call. Retrieved "
        "private manuscript passages are included only in generation prompts. Each answer is "
        "then sent alone to gpt-5.6-terra once for canonical claim decomposition, for 37 "
        "decomposition calls total. No calibration repeats, gold annotations, semantic "
        "verdicts, history, or automatic retries."
    )
    print(
        "Reasonable full-cohort estimate: "
        f"${FULL_EVALUATION_COST_ESTIMATE_LOW_USD:.2f}-"
        f"${FULL_EVALUATION_COST_ESTIMATE_HIGH_USD:.2f}; "
        f"recommended authorization ceiling ${FULL_EVALUATION_RECOMMENDED_CAP_USD:.2f}."
    )
    print(
        "Exact paid command after authorization: python scripts/run_answer_evaluation.py "
        "run-37 --authorize-openai-full-evaluation --max-cost-usd 20"
    )
    print(
        "Calibration and semantic scoring are later optional measurement work. They cannot "
        "block generation or preservation of any of the 37 evaluation answers."
    )


def _require_paid_authorization(
    args: argparse.Namespace,
    *,
    flag_name: str,
) -> float:
    if not bool(getattr(args, flag_name)):
        option = "--" + flag_name.replace("_", "-")
        raise AnswerEvaluationError(f"paid phase requires explicit {option}")
    maximum = args.max_cost_usd
    if (
        not isinstance(maximum, (int, float))
        or isinstance(maximum, bool)
        or not math.isfinite(float(maximum))
        or float(maximum) < 0.01
    ):
        raise AnswerEvaluationError("paid phase requires finite --max-cost-usd of at least $0.01")
    return float(maximum)


@contextmanager
def _isolated_usage_db(path: Path):
    previous = os.environ.get("ARCHIVIST_USAGE_DB")
    os.environ["ARCHIVIST_USAGE_DB"] = str(path.resolve())
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("ARCHIVIST_USAGE_DB", None)
        else:
            os.environ["ARCHIVIST_USAGE_DB"] = previous


def _usage_rows(path: Path, *, turn_id: str) -> list[sqlite3.Row]:
    if not path.is_file():
        raise AnswerEvaluationError(f"usage ledger was not created for {turn_id}")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        return list(
            connection.execute(
                """
                SELECT response_id, recorded_at, operation, requested_model, actual_model,
                       input_tokens, cached_tokens, cache_write_tokens, output_tokens,
                       reasoning_tokens, total_tokens, estimated_cost_nano_usd,
                       pricing_version, unpriced
                FROM usage_events
                WHERE project_id = ? AND conversation_id = ? AND turn_id = ?
                ORDER BY id ASC
                """,
                (EVALUATION_ID, "held-out-37", turn_id),
            ).fetchall()
        )
    finally:
        connection.close()


def _usage_rows_if_any(path: Path, *, turn_id: str) -> list[sqlite3.Row]:
    if not path.is_file():
        return []
    return _usage_rows(path, turn_id=turn_id)


def _require_no_orphan_usage(path: Path, *, turn_id: str) -> None:
    if _usage_rows_if_any(path, turn_id=turn_id):
        raise AnswerEvaluationError(
            f"usage exists for {turn_id} without its checkpoint; refusing a repeat call"
        )


def _private_usage_events(
    path: Path,
    *,
    turn_id: str,
    phase: str,
    provider_observations: Sequence[_ProviderObservation] = (),
    local_release_proven: bool = False,
    audited_ledger_recovery: bool = False,
):
    rows = _usage_rows(path, turn_id=turn_id)
    if not rows:
        raise AnswerEvaluationError(f"no tracked OpenAI usage was preserved for {turn_id}")
    operations = [str(row["operation"]) for row in rows]
    if phase == "generation":
        allowed_sequences = (
            ["query_embedding", "answer_generation"],
            ["query_planning", "query_embedding", "answer_generation"],
        )
        local_release_sequences = (
            ["query_embedding"],
            ["query_planning", "query_embedding"],
        )
        if operations not in allowed_sequences and not (
            local_release_proven and operations in local_release_sequences
        ):
            raise AnswerEvaluationError(
                f"{turn_id}: expected exactly one optional planner, one batched "
                "query embedding, and one answer generation in order"
            )
    elif phase == "decomposition":
        if operations != ["eval_claim_decomposition"]:
            raise AnswerEvaluationError(
                f"{turn_id}: decomposition requires exactly one tracked judge call"
            )
    elif phase == "claim_evidence":
        if operations != ["eval_claim_evidence"]:
            raise AnswerEvaluationError(
                f"{turn_id}: claim evidence requires exactly one tracked judge call"
            )
    elif phase == "item_rubric":
        if operations != ["eval_item_rubric"]:
            raise AnswerEvaluationError(
                f"{turn_id}: item rubric requires exactly one tracked judge call"
            )
    else:  # pragma: no cover - internal misuse
        raise ValueError(f"unknown usage phase {phase!r}")

    observed: dict[str, str] = {}
    for value in provider_observations:
        previous_model = observed.get(value.response_id)
        if previous_model is not None and previous_model != value.model:
            raise AnswerEvaluationError(
                f"{turn_id}: raw provider observations disagree on model identity"
            )
        observed[value.response_id] = value.model
    events = []
    for sequence, row in enumerate(rows, start=1):
        operation = str(row["operation"])
        expected_model = {
            "query_planning": QUERY_PLANNER_SETTINGS.model,
            "query_embedding": EMBEDDING_MODEL,
            "answer_generation": GENERATOR_SETTINGS.model,
            "eval_claim_decomposition": JUDGE_MODEL,
            "eval_claim_evidence": JUDGE_MODEL,
            "eval_item_rubric": JUDGE_MODEL,
        }.get(operation)
        if expected_model is None:
            raise AnswerEvaluationError(f"unexpected evaluation operation {operation!r}")
        if row["requested_model"] != expected_model or row["actual_model"] != expected_model:
            raise AnswerEvaluationError(
                f"{turn_id}: {operation} model identity mismatch "
                f"({row['requested_model']!r} / {row['actual_model']!r})"
            )
        response_id = str(row["response_id"])
        if observed.get(response_id) != row["actual_model"] and not (
            audited_ledger_recovery and local_release_proven and not provider_observations
        ):
            raise AnswerEvaluationError(
                f"{turn_id}: {operation} ledger identity does not match the raw response"
            )
        events.append(
            build_private_usage_event(
                sequence=sequence,
                response_id=str(row["response_id"]),
                recorded_at=str(row["recorded_at"]),
                operation=operation,
                requested_model=str(row["requested_model"]),
                actual_model=str(row["actual_model"]),
                input_tokens=int(row["input_tokens"]),
                cached_tokens=int(row["cached_tokens"]),
                cache_write_tokens=int(row["cache_write_tokens"]),
                output_tokens=int(row["output_tokens"]),
                reasoning_tokens=int(row["reasoning_tokens"]),
                total_tokens=int(row["total_tokens"]),
                estimated_cost_nano_usd=(
                    None
                    if row["estimated_cost_nano_usd"] is None
                    else int(row["estimated_cost_nano_usd"])
                ),
                pricing_version=str(row["pricing_version"]),
                unpriced=bool(row["unpriced"]),
            )
        )
    if not (audited_ledger_recovery and local_release_proven and not provider_observations) and (
        set(observed) != {event.response_id for event in events}
    ):
        raise AnswerEvaluationError(
            f"{turn_id}: raw provider response cardinality differs from tracked usage"
        )
    return tuple(events)


@dataclass(frozen=True, slots=True)
class _LocalReleaseProof:
    answer: str
    status: str
    evidence_decision: str
    diagnostics: Mapping[str, object]
    trace_reference: PrivateTraceReference
    elapsed_seconds: float


def _trace_reference_from_path(item_root: Path, trace_path: Path) -> PrivateTraceReference:
    payload = _load_json_object(trace_path, label="retrieval trace")
    query = payload.get("query")
    if not isinstance(query, Mapping):
        raise AnswerEvaluationError("retrieval trace has no query binding")
    return PrivateTraceReference(
        sequence=1,
        schema_id=_required_string(payload, "schema", label="retrieval trace"),
        trace_id=_required_string(payload, "trace_id", label="retrieval trace"),
        path=trace_path.relative_to(item_root).as_posix(),
        sha256=sha256_file(trace_path),
        query_sha256=_required_string(query, "sha256", label="retrieval trace query"),
        retrieval_version=_required_string(payload, "retrieval_version", label="retrieval trace"),
    )


def _prove_local_early_release(
    *,
    item_root: Path,
    question: str,
    trace_reference: PrivateTraceReference,
    usage_db: Path,
    expected_answer: str | None = None,
    expected_status: str | None = None,
    expected_evidence_decision: str | None = None,
    final_source_count: int = 0,
) -> _LocalReleaseProof:
    trace_path = (item_root / trace_reference.path).resolve()
    try:
        trace_path.relative_to(item_root.resolve())
    except ValueError as exc:
        raise AnswerEvaluationError("retrieval trace path escapes its item directory") from exc
    if sha256_file(trace_path) != trace_reference.sha256:
        raise AnswerEvaluationError("retrieval trace hash changed")
    trace = _load_json_object(trace_path, label="retrieval trace")
    if trace_reference.query_sha256 != hashlib.sha256(question.encode("utf-8")).hexdigest():
        raise AnswerEvaluationError("retrieval trace belongs to another question")
    evidence = trace.get("evidence")
    generation = trace.get("generation_contract")
    plan_trace = trace.get("plan")
    if not all(isinstance(value, Mapping) for value in (evidence, generation, plan_trace)):
        raise AnswerEvaluationError("local-release trace is incomplete")
    decision = evidence.get("decision")
    if not isinstance(decision, Mapping):
        raise AnswerEvaluationError("local-release evidence decision is missing")
    if (
        decision.get("skip_answer_generation") is not True
        or generation.get("structured_generation_called") is not False
        or decision.get("allowed_source_numbers") != []
        or final_source_count != 0
    ):
        raise AnswerEvaluationError("trace does not prove an empty-source local release")
    operations = [str(row["operation"]) for row in _usage_rows(usage_db, turn_id=item_root.name)]
    planner_used = plan_trace.get("planner_used") is True
    expected_operations = (
        ["query_planning", "query_embedding"] if planner_used else ["query_embedding"]
    )
    if operations != expected_operations:
        raise AnswerEvaluationError("local-release provider-call shape disagrees with its trace")

    status = str(generation.get("status"))
    evidence_decision = str(decision.get("value"))
    rules = decision.get("rules_fired")
    if status == "clean_abstention" and evidence_decision == "clean_abstention":
        target_label: str | None = None
        if not planner_used:
            fallback = build_question_plan(
                ResolvedTurn(standalone_question=question, trusted_user_texts=(question,))
            )
            targets = evidence.get("targets")
            if (
                not isinstance(targets, list)
                or len(targets) != 1
                or not isinstance(targets[0], Mapping)
            ):
                raise AnswerEvaluationError("clean-abstention trace has no unique target proof")
            target_record = targets[0]
            matching = [
                target.query_surface_span
                for target in fallback.targets
                if (
                    len(target.query_surface_span) == target_record.get("target_character_count")
                    and hashlib.sha256(
                        " ".join(tokenize_anchor(target.query_surface_span)).encode("utf-8")
                    ).hexdigest()
                    == target_record.get("target_sha256")
                )
            ]
            if len(matching) != 1:
                raise AnswerEvaluationError("clean-abstention target cannot be reconstructed")
            target_label = matching[0]
        elif expected_answer is None:
            raise AnswerEvaluationError(
                "planner-derived clean abstention cannot be reconstructed offline"
            )
        answer = expected_answer or _clean_abstention(target_label)
    elif (
        "structural_stage_shortfall" in (rules if isinstance(rules, list) else [])
        and evidence_decision == "indeterminate"
    ):
        answer = STRUCTURAL_STAGE_SHORTFALL_MESSAGE
    else:
        raise AnswerEvaluationError("trace status is not a supported deterministic local release")
    if expected_answer is not None and answer != expected_answer:
        raise AnswerEvaluationError("local-release answer disagrees with deterministic trace proof")
    if expected_status is not None and status != expected_status:
        raise AnswerEvaluationError("local-release status disagrees with runtime result")
    if expected_evidence_decision is not None and evidence_decision != expected_evidence_decision:
        raise AnswerEvaluationError("local-release decision disagrees with runtime result")

    _required_string(trace, "created_at", label="trace")
    planner = plan_trace.get("planner_call")
    diagnostics = {
        "rag_policy_version": str(plan_trace.get("policy_version")),
        "archivist_mode": archivist_mode_metadata(ArchivistMode.ESSENTIAL),
        "evidence": dict(evidence),
        "generation": dict(generation),
        "planner": dict(planner) if isinstance(planner, Mapping) else {},
        "stage_timings_ms": {},
        "offline_recovery": {
            "schema": "archivist.answer_evaluation.local_release_recovery/1",
            "trace_sha256": trace_reference.sha256,
            "full_turn_latency_recovered": False,
            "latency_limitation": "full_turn_elapsed_seconds_was_not_checkpointed",
        },
    }
    return _LocalReleaseProof(
        answer=answer,
        status=status,
        evidence_decision=evidence_decision,
        diagnostics=diagnostics,
        trace_reference=trace_reference,
        elapsed_seconds=0.0,
    )


def _trace_references(summary: Mapping[str, object]) -> tuple[PrivateTraceReference, ...]:
    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise AnswerEvaluationError("trace summary is missing artifacts")
    turns = artifacts.get("turns")
    if not isinstance(turns, list) or len(turns) != 1 or not isinstance(turns[0], Mapping):
        raise AnswerEvaluationError("item trace summary must contain exactly one turn")
    raw_references = turns[0].get("retrieval_traces")
    if not isinstance(raw_references, list) or not raw_references:
        raise AnswerEvaluationError("item trace summary contains no retrieval trace")
    return tuple(
        PrivateTraceReference(
            sequence=sequence,
            schema_id=_required_string(raw, "schema", label="trace reference"),
            trace_id=_required_string(raw, "trace_id", label="trace reference"),
            path=_required_string(raw, "path", label="trace reference"),
            sha256=_required_string(raw, "sha256", label="trace reference"),
            query_sha256=_required_string(raw, "query_sha256", label="trace reference"),
            retrieval_version=_required_string(
                raw,
                "retrieval_version",
                label="trace reference",
            ),
        )
        for sequence, raw in enumerate(raw_references, start=1)
        if isinstance(raw, Mapping)
    )


def _json_value(value: object) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _private_sources(chunks: Sequence[Mapping[str, object]]):
    sources = []
    for source_number, chunk in enumerate(chunks, start=1):
        chunk_id = _required_string(chunk, "chunk_id", label="retrieved chunk")
        text = chunk.get("text")
        if not isinstance(text, str):
            raise AnswerEvaluationError(f"retrieved chunk {chunk_id} is missing text")
        metadata = {
            key: _json_value(chunk.get(key))
            for key in (
                "document",
                "chapter_title",
                "paragraph_start",
                "paragraph_end",
            )
        }
        sources.append(
            build_private_source(
                source_number=source_number,
                chunk_id=chunk_id,
                text=text,
                metadata=metadata,
            )
        )
    return tuple(sources)


def _load_generated_checkpoint(
    path: Path,
    *,
    item: Mapping[str, object],
    cohort_manifest_sha256: str,
    cohort_item: CohortItemBinding,
) -> PrivateGeneratedItem:
    payload = _load_json_object(path, label="generated item checkpoint")
    checkpoint = validate_private_generation_checkpoint(
        PrivateGenerationCheckpoint.model_validate(payload),
        cohort_manifest_sha256=cohort_manifest_sha256,
        expected_item=cohort_item,
    )
    generated = checkpoint.item
    if generated.item_id != _required_string(item, "id", label="gold item"):
        raise AnswerEvaluationError("generated checkpoint belongs to another gold item")
    if generated.question != _required_string(item, "question", label="gold item"):
        raise AnswerEvaluationError("generated checkpoint question differs from locked gold")
    return generated


def _run_one_generated_item(
    *,
    args: argparse.Namespace,
    context: EvaluationContext,
    item: Mapping[str, object],
    client: object,
    usage_db: Path,
    runner_sha256: str,
    cohort_manifest_sha256: str,
    cohort_item: CohortItemBinding,
) -> PrivateGeneratedItem:
    item_id = _required_string(item, "id", label="gold item")
    question = _required_string(item, "question", label=f"gold item {item_id}")
    item_root = args.run_root / "items" / item_id
    checkpoint = item_root / "generated.json"
    if checkpoint.is_file():
        return _load_generated_checkpoint(
            checkpoint,
            item=item,
            cohort_manifest_sha256=cohort_manifest_sha256,
            cohort_item=cohort_item,
        )
    orphan_rows = _usage_rows_if_any(usage_db, turn_id=item_id)
    if orphan_rows:
        trace_paths = sorted((item_root / "retrieval-traces").glob("*/*.json"))
        if len(trace_paths) != 1:
            raise AnswerEvaluationError(
                f"usage exists for {item_id} without one recoverable retrieval trace; "
                "refusing a repeat call"
            )
        trace_reference = _trace_reference_from_path(item_root, trace_paths[0])
        proof = _prove_local_early_release(
            item_root=item_root,
            question=question,
            trace_reference=trace_reference,
            usage_db=usage_db,
        )
        generated = build_private_generated_item(
            item_id=item_id,
            question=question,
            stratum=_required_string(item, "stratum", label=f"gold item {item_id}"),
            expected_behavior=_required_string(
                item, "expected_behavior", label=f"gold item {item_id}"
            ),
            answer=proof.answer,
            status=proof.status,
            evidence_decision=proof.evidence_decision,
            diagnostics=_json_value(proof.diagnostics),
            sources=(),
            elapsed_seconds=proof.elapsed_seconds,
            usage_events=_private_usage_events(
                usage_db,
                turn_id=item_id,
                phase="generation",
                local_release_proven=True,
                audited_ledger_recovery=True,
            ),
            trace_references=(proof.trace_reference,),
        )
        strict_checkpoint = build_private_generation_checkpoint(
            cohort_manifest_sha256=cohort_manifest_sha256,
            item=generated,
        )
        audit = _sealed_artifact(
            {
                "schema": "archivist.answer_evaluation.local_release_recovery_audit/1",
                "item_id": item_id,
                "runner_sha256": runner_sha256,
                "cohort_manifest_sha256": cohort_manifest_sha256,
                "trace_sha256": proof.trace_reference.sha256,
                "usage_event_sha256s": [
                    canonical_json_sha256(event.model_dump(mode="json"))
                    for event in generated.usage_events
                ],
                "generated_item_sha256": generated.item_sha256,
                "provider_calls_repeated": False,
            }
        )
        audit_path = item_root / "local-release-recovery-audit.json"
        if audit_path.is_file():
            if _load_json_object(audit_path, label="local release recovery audit") != audit:
                raise AnswerEvaluationError("local release recovery audit changed")
        else:
            write_json_atomic_no_overwrite(audit_path, audit)
        write_json_atomic_no_overwrite(checkpoint, strict_checkpoint)
        return generated

    recorder = SmokeArtifactRecorder(
        run_root=item_root,
        project_root=BASE_DIR,
        manifest_path=args.manifest,
        chunks_path=args.chunks,
    )
    started = perf_counter()
    capturing_client = _ProviderCapturingClient(client)
    with (
        recorder.capture_turn(1),
        usage_scope(
            project_id=EVALUATION_ID,
            conversation_id="held-out-37",
            turn_id=item_id,
            enforce_budget=True,
        ),
    ):
        result = run_evidence_planned_answer(
            resolved_turn=ResolvedTurn(
                standalone_question=question,
                trusted_user_texts=(question,),
            ),
            collection_handle=context.collection,
            chunks=context.chunks,
            client=capturing_client,
            n_results=5,
            corpus_trace=context.corpus_trace,
            corpus_manifest=context.manifest,
            corpus_manifest_sha256=context.manifest_sha256,
            require_store_identity=True,
            historiographical_lens=HistoriographicalLens.EVIDENCE_FIRST,
            voice=AnswerVoice.SCHOLARLY,
            worldview=Worldview.NONE,
            archivist_mode=ArchivistMode.ESSENTIAL,
            policy=EVIDENCE_PLANNED_POLICY,
        )
    elapsed = perf_counter() - started
    trace_summary = recorder.attach_to_summary(
        {"runner_sha256": runner_sha256},
        expected_turn_numbers=(1,),
    )
    trace_references = _trace_references(trace_summary)
    operations = [str(row["operation"]) for row in _usage_rows(usage_db, turn_id=item_id)]
    local_release = "answer_generation" not in operations
    if local_release:
        _prove_local_early_release(
            item_root=item_root,
            question=question,
            trace_reference=trace_references[0],
            usage_db=usage_db,
            expected_answer=result.answer,
            expected_status=result.status,
            expected_evidence_decision=result.evidence_decision,
            final_source_count=len(result.final_chunks),
        )
    generated = build_private_generated_item(
        item_id=item_id,
        question=question,
        stratum=_required_string(item, "stratum", label=f"gold item {item_id}"),
        expected_behavior=_required_string(
            item,
            "expected_behavior",
            label=f"gold item {item_id}",
        ),
        answer=result.answer,
        status=result.status,
        evidence_decision=result.evidence_decision,
        diagnostics=_json_value(result.diagnostics),
        sources=_private_sources(result.final_chunks),
        elapsed_seconds=elapsed,
        usage_events=_private_usage_events(
            usage_db,
            turn_id=item_id,
            phase="generation",
            provider_observations=capturing_client.observations,
            local_release_proven=local_release,
        ),
        trace_references=trace_references,
    )
    strict_checkpoint = build_private_generation_checkpoint(
        cohort_manifest_sha256=cohort_manifest_sha256,
        item=generated,
    )
    write_json_atomic_no_overwrite(checkpoint, strict_checkpoint)
    return generated


def _provider_payload(provider: object) -> dict[str, object | None]:
    return {
        "id": getattr(provider, "id", None),
        "model": getattr(provider, "model", None),
        "created_at": getattr(provider, "created_at", None),
        "system_fingerprint": getattr(provider, "system_fingerprint", None),
    }


def _openai_client_type():
    from openai import OpenAI

    return OpenAI


def _create_openai_client(api_key: str) -> object:
    return _openai_client_type()(api_key=api_key, max_retries=0)


@dataclass(frozen=True, slots=True)
class _ProviderObservation:
    response_id: str
    model: str


def _capture_provider_observation(
    value: object,
    observations: list[_ProviderObservation],
) -> None:
    if isinstance(value, Mapping):
        response_id = value.get("id") or value.get("_request_id")
        model = value.get("model")
    else:
        response_id = getattr(value, "id", None) or getattr(value, "_request_id", None)
        model = getattr(value, "model", None)
    if not isinstance(response_id, str) or not response_id:
        raise AnswerEvaluationError("provider response omitted its raw response ID")
    if not isinstance(model, str) or not model:
        raise AnswerEvaluationError("provider response omitted its raw model ID")
    observation = _ProviderObservation(response_id, model)
    if observation not in observations:
        observations.append(observation)


class _CapturingHttpResponse:
    def __init__(self, response: object, observations: list[_ProviderObservation]) -> None:
        self._response = response
        self._observations = observations

    def json(self) -> object:
        value = getattr(self._response, "json")()
        _capture_provider_observation(value, self._observations)
        return value

    def __getattr__(self, name: str) -> object:
        return getattr(self._response, name)


class _CapturingRawResponse:
    def __init__(self, response: object, observations: list[_ProviderObservation]) -> None:
        self._response = response
        self._observations = observations

    @property
    def http_response(self) -> _CapturingHttpResponse:
        return _CapturingHttpResponse(
            getattr(self._response, "http_response"),
            self._observations,
        )

    def parse(self) -> object:
        value = getattr(self._response, "parse")()
        _capture_provider_observation(value, self._observations)
        return value

    def __getattr__(self, name: str) -> object:
        if name == "json":
            reader = getattr(self._response, "json")

            def capturing_json() -> object:
                value = reader()
                _capture_provider_observation(value, self._observations)
                return value

            return capturing_json
        return getattr(self._response, name)


class _CapturingRawResponses:
    def __init__(self, resource: object, observations: list[_ProviderObservation]) -> None:
        self._resource = resource
        self._observations = observations

    def parse(self, **kwargs: object) -> _CapturingRawResponse:
        value = getattr(self._resource, "parse")(**kwargs)
        return _CapturingRawResponse(value, self._observations)


class _CapturingResponses:
    def __init__(self, resource: object, observations: list[_ProviderObservation]) -> None:
        self._resource = resource
        self._observations = observations

    def parse(self, **kwargs: object) -> object:
        response = getattr(self._resource, "parse")(**kwargs)
        _capture_provider_observation(response, self._observations)
        return response

    @property
    def with_raw_response(self) -> _CapturingRawResponses:
        return _CapturingRawResponses(
            getattr(self._resource, "with_raw_response"),
            self._observations,
        )


class _CapturingEmbeddings:
    def __init__(self, resource: object, observations: list[_ProviderObservation]) -> None:
        self._resource = resource
        self._observations = observations

    def create(self, **kwargs: object) -> object:
        response = getattr(self._resource, "create")(**kwargs)
        _capture_provider_observation(response, self._observations)
        return response


class _ProviderCapturingClient:
    def __init__(
        self,
        client: object,
        observations: list[_ProviderObservation] | None = None,
    ) -> None:
        self._client = client
        self.observations = observations if observations is not None else []

    @property
    def responses(self) -> _CapturingResponses:
        return _CapturingResponses(getattr(self._client, "responses"), self.observations)

    @property
    def embeddings(self) -> _CapturingEmbeddings:
        return _CapturingEmbeddings(getattr(self._client, "embeddings"), self.observations)

    def with_options(self, **kwargs: object) -> "_ProviderCapturingClient":
        configured = getattr(self._client, "with_options")(**kwargs)
        return _ProviderCapturingClient(configured, self.observations)

    def __getattr__(self, name: str) -> object:
        return getattr(self._client, name)


def _validate_decomposition_against_generated(
    decomposition: DecomposedPilotItem,
    generated: PrivateGeneratedItem,
) -> None:
    if decomposition.item_id != generated.item_id:
        raise AnswerEvaluationError("decomposition belongs to another generated item")
    if decomposition.answer_sha256 != generated.answer_sha256:
        raise AnswerEvaluationError("decomposition answer binding changed")
    available_sources = {source.source_number for source in generated.sources}
    for claim in decomposition.claims:
        if claim.char_end > len(generated.answer):
            raise AnswerEvaluationError("decomposition claim span exceeds the answer")
        if generated.answer[claim.char_start : claim.char_end] != claim.text:
            raise AnswerEvaluationError("decomposition claim text no longer matches its span")
        if not set(claim.cited_source_numbers).issubset(available_sources):
            raise AnswerEvaluationError("decomposition cites an unavailable source number")


def _validate_decomposition_checkpoint_payload(
    payload: Mapping[str, object],
    *,
    generated: PrivateGeneratedItem,
    repetition: int,
    cohort_manifest_sha256: str,
) -> DecomposedPilotItem:
    expected_settings = {
        "reasoning_effort": JUDGE_SETTINGS.reasoning_effort,
        "verbosity": JUDGE_SETTINGS.verbosity,
    }
    checkpoint = validate_private_decomposition_checkpoint(
        PrivateDecompositionCheckpoint.model_validate(payload),
        cohort_manifest_sha256=cohort_manifest_sha256,
        generated_item=generated,
        repetition=repetition,
        prompt_version=CLAIM_DECOMPOSITION_PROMPT_VERSION,
        prompt_sha256=CLAIM_DECOMPOSITION_PROMPT_SHA256,
        judge_model=JUDGE_MODEL,
        judge_settings=expected_settings,
    )
    return checkpoint.decomposition


def _decomposition_checkpoint(
    *,
    args: argparse.Namespace,
    generated: PrivateGeneratedItem,
    repetition: int,
    client: object,
    usage_db: Path,
    cohort_manifest_sha256: str,
) -> dict[str, object]:
    path = args.run_root / "items" / generated.item_id / f"decomposition-{repetition}.json"
    if path.is_file():
        payload = _load_json_object(path, label="decomposition checkpoint")
        _validate_decomposition_checkpoint_payload(
            payload,
            generated=generated,
            repetition=repetition,
            cohort_manifest_sha256=cohort_manifest_sha256,
        )
        return payload

    turn_id = f"{generated.item_id}:decomposition:{repetition}"
    _require_no_orphan_usage(usage_db, turn_id=turn_id)
    with usage_scope(
        project_id=EVALUATION_ID,
        conversation_id="held-out-37",
        turn_id=turn_id,
        enforce_budget=True,
    ):
        result = decompose_answer_claims(client, answer=generated.answer)
    claims = tuple(
        build_decomposed_claim(
            claim_id=claim.claim_id,
            text=claim.text,
            char_start=claim.char_start,
            char_end=claim.char_end,
            cited_source_numbers=claim.cited_sources,
        )
        for claim in result.parsed.claims
    )
    decomposition = build_decomposed_pilot_item(
        item_id=generated.item_id,
        answer_sha256=generated.answer_sha256,
        claims=claims,
    )
    strict_checkpoint = build_private_decomposition_checkpoint(
        cohort_manifest_sha256=cohort_manifest_sha256,
        item_id=generated.item_id,
        answer_sha256=generated.answer_sha256,
        repetition=repetition,
        prompt_version=CLAIM_DECOMPOSITION_PROMPT_VERSION,
        prompt_sha256=CLAIM_DECOMPOSITION_PROMPT_SHA256,
        judge_model=JUDGE_MODEL,
        judge_settings={
            "reasoning_effort": JUDGE_SETTINGS.reasoning_effort,
            "verbosity": JUDGE_SETTINGS.verbosity,
        },
        provider=_provider_payload(result.provider),
        usage_event=_private_usage_events(
            usage_db,
            turn_id=turn_id,
            phase="decomposition",
            provider_observations=(
                _ProviderObservation(
                    response_id=str(getattr(result.provider, "id", "")),
                    model=str(getattr(result.provider, "model", "")),
                ),
            ),
        )[0],
        decomposition=decomposition,
    )
    payload = strict_checkpoint.model_dump(mode="json")
    write_json_atomic_no_overwrite(path, strict_checkpoint)
    return payload


def _validate_generation_artifact(
    path: Path,
    *,
    args: argparse.Namespace,
    context: EvaluationContext,
    runner_sha256: str,
    cohort_manifest: AnswerEvaluationCohortManifest,
    cohort_manifest_sha256: str,
) -> tuple[tuple[PrivateGeneratedItem, ...], str]:
    payload = _load_json_object(path, label="calibration generation artifact")
    expected: dict[str, object] = {
        "schema": CALIBRATION_GENERATION_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "candidate_commit": context.gold.candidate_commit,
        "rag_policy": context.gold.candidate_rag_policy,
        "gold_set_sha256": context.gold.gold_set_sha256,
        "question_set_sha256": context.gold.question_set_sha256,
        "corpus_manifest_sha256": context.gold.corpus_manifest_sha256,
        "model_catalog_sha256": context.model_catalog_sha256,
        "runner_sha256": runner_sha256,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "run_identity": dict(context.run_identity),
        "calibration_item_ids": list(context.calibration_ids),
        "remaining_item_count": len(context.remaining_ids),
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise AnswerEvaluationError(f"calibration generation {field} changed")
    created_at = payload.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        raise AnswerEvaluationError("calibration generation created_at is missing")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise AnswerEvaluationError("calibration generation items are missing")
    generated = tuple(PrivateGeneratedItem.model_validate(item) for item in raw_items)
    if tuple(item.item_id for item in generated) != context.calibration_ids:
        raise AnswerEvaluationError("calibration generation item order changed")
    for gold_item, generated_item in zip(
        context.calibration_items,
        generated,
        strict=True,
    ):
        expected_id = _required_string(gold_item, "id", label="gold item")
        expected_question = _required_string(
            gold_item,
            "question",
            label=f"gold item {expected_id}",
        )
        if generated_item.item_id != expected_id or generated_item.question != expected_question:
            raise AnswerEvaluationError("calibration generation differs from locked gold")
        checkpoint = args.run_root / "items" / expected_id / "generated.json"
        cohort_item = next(value for value in cohort_manifest.items if value.item_id == expected_id)
        checkpoint_item = _load_generated_checkpoint(
            checkpoint,
            item=gold_item,
            cohort_manifest_sha256=cohort_manifest_sha256,
            cohort_item=cohort_item,
        )
        if checkpoint_item.model_dump(mode="json") != generated_item.model_dump(mode="json"):
            raise AnswerEvaluationError(
                f"generated checkpoint {expected_id} differs from the final artifact"
            )
    return generated, sha256_file(path)


def _validate_decomposition_artifact(
    path: Path,
    *,
    generated_items: Sequence[PrivateGeneratedItem],
    generation_sha256: str,
    context: EvaluationContext,
    cohort_manifest_sha256: str,
) -> tuple[tuple[DecomposedPilotItem, ...], str]:
    payload = _load_json_object(path, label="calibration decomposition artifact")
    expected: dict[str, object] = {
        "schema": CALIBRATION_DECOMPOSITION_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "pilot_artifact_sha256": generation_sha256,
        "model_catalog_sha256": context.model_catalog_sha256,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "prompt_version": CLAIM_DECOMPOSITION_PROMPT_VERSION,
        "prompt_sha256": CLAIM_DECOMPOSITION_PROMPT_SHA256,
        "model": JUDGE_MODEL,
        "repetitions_per_item": CALIBRATION_REPETITIONS,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise AnswerEvaluationError(f"calibration decomposition {field} changed")
    created_at = payload.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        raise AnswerEvaluationError("calibration decomposition created_at is missing")
    raw_records = payload.get("items")
    if not isinstance(raw_records, list) or len(raw_records) != len(generated_items):
        raise AnswerEvaluationError("calibration decomposition item count changed")
    canonical: list[DecomposedPilotItem] = []
    for generated, record in zip(generated_items, raw_records, strict=True):
        if not isinstance(record, Mapping):
            raise AnswerEvaluationError("calibration decomposition record is malformed")
        if record.get("item_id") != generated.item_id:
            raise AnswerEvaluationError("calibration decomposition item order changed")
        if record.get("answer_sha256") != generated.answer_sha256:
            raise AnswerEvaluationError("calibration decomposition answer binding changed")
        repetitions = record.get("repetitions")
        if not isinstance(repetitions, list) or len(repetitions) != CALIBRATION_REPETITIONS:
            raise AnswerEvaluationError("calibration decomposition repetition count changed")
        validated: list[DecomposedPilotItem] = []
        for repetition, checkpoint_payload in enumerate(repetitions, start=1):
            if not isinstance(checkpoint_payload, Mapping):
                raise AnswerEvaluationError("calibration decomposition checkpoint is malformed")
            decomposition = _validate_decomposition_checkpoint_payload(
                checkpoint_payload,
                generated=generated,
                repetition=repetition,
                cohort_manifest_sha256=cohort_manifest_sha256,
            )
            checkpoint_path = (
                path.parent / "items" / generated.item_id / f"decomposition-{repetition}.json"
            )
            checkpoint_on_disk = _load_json_object(
                checkpoint_path,
                label="decomposition checkpoint",
            )
            if checkpoint_on_disk != dict(checkpoint_payload):
                raise AnswerEvaluationError(
                    f"decomposition checkpoint {generated.item_id}/{repetition} "
                    "differs from the final artifact"
                )
            validated.append(decomposition)
        canonical.append(validated[0])
    return tuple(canonical), sha256_file(path)


def _load_or_write_label_template(
    path: Path,
    *,
    generated_items: Sequence[PrivateGeneratedItem],
    decomposed_items: Sequence[DecomposedPilotItem],
    gold_items: Sequence[Mapping[str, object]],
    generation_sha256: str,
    decomposition_sha256: str,
) -> CalibrationLabelFile:
    expected = build_calibration_label_template(
        generated_items=generated_items,
        decomposed_items=decomposed_items,
        gold_items=gold_items,
        pilot_artifact_sha256=generation_sha256,
        decomposition_artifact_sha256=decomposition_sha256,
    )
    if path.is_file():
        actual = CalibrationLabelFile.model_validate(
            _load_json_object(path, label="owner label template")
        )
        if actual.model_dump(mode="json") != expected.model_dump(mode="json"):
            raise AnswerEvaluationError("existing owner label template binding changed")
        return actual
    write_json_atomic_no_overwrite(path, expected)
    return expected


def _next_action_after_generation(
    args: argparse.Namespace,
    context: EvaluationContext,
    *,
    generated_items: Sequence[PrivateGeneratedItem],
    decomposed_items: Sequence[DecomposedPilotItem],
    generation_sha256: str,
    decomposition_sha256: str,
) -> str:
    if not args.labels.is_file():
        return NEXT_ACTION_OWNER_LABELS
    labels = CalibrationLabelFile.model_validate(
        _load_json_object(args.labels, label="owner calibration labels")
    )
    validate_calibration_labels_for_judge(
        labels,
        generated_items=generated_items,
        decomposed_items=decomposed_items,
        gold_items=context.calibration_items,
        pilot_artifact_sha256=generation_sha256,
        decomposition_artifact_sha256=decomposition_sha256,
    )
    return NEXT_ACTION_CALIBRATION_JUDGE


def _ledger_total_cost(ledger: UsageLedger) -> float:
    value = ledger.summary().get("all_time_usd")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise AnswerEvaluationError("isolated usage ledger has no numeric total")
    return float(value)


def _require_cost_within_cap(ledger: UsageLedger, maximum: float) -> None:
    spent = _ledger_total_cost(ledger)
    if spent > maximum + 1e-12:
        raise AnswerEvaluationError(
            f"recorded estimated cost ${spent:.6f} exceeded authorized ${maximum:.2f}; "
            "completed checkpoints were preserved and no further call will run"
        )


def _require_cost_reserve(
    ledger: UsageLedger,
    maximum: float,
    *,
    reserve_usd: float,
    label: str,
) -> None:
    spent = _ledger_total_cost(ledger)
    if spent + reserve_usd > maximum + 1e-12:
        raise AnswerEvaluationError(
            f"{label} requires a ${reserve_usd:.2f} prospective reserve; "
            f"${spent:.6f} is already recorded against the ${maximum:.2f} authorization"
        )


def _calibration_generate(args: argparse.Namespace, context: EvaluationContext) -> None:
    if not (
        (args.run_root / "baseline-generated.json").is_file()
        and (args.run_root / "baseline-decompositions.json").is_file()
    ):
        raise AnswerEvaluationError(
            "calibration work requires the completed 37-item generation and canonical "
            "decomposition artifacts; it cannot create a ten-item paid cohort first"
        )
    maximum = _require_paid_authorization(
        args,
        flag_name="authorize_openai_calibration_generation",
    )
    args.run_root = _require_private_run_root(args.run_root)
    args.run_root.mkdir(parents=True, exist_ok=True)
    generation_path = args.run_root / "calibration-generated.json"
    decomposition_path = args.run_root / "calibration-decompositions.json"
    label_template_path = args.run_root / "calibration-labels.template.json"
    if decomposition_path.is_file() and not generation_path.is_file():
        raise AnswerEvaluationError(
            "decomposition artifact exists without its bound generation artifact"
        )
    if label_template_path.is_file() and not decomposition_path.is_file():
        raise AnswerEvaluationError(
            "owner label template exists without its bound decomposition artifact"
        )

    usage_db = args.run_root / "usage.sqlite3"
    runner_sha256 = sha256_file(Path(__file__))
    cohort_manifest, cohort_manifest_sha256 = _load_or_write_cohort_manifest(
        args.run_root / "cohort-manifest.json",
        context=context,
        runner_sha256=runner_sha256,
    )
    cohort_by_id = {item.item_id: item for item in cohort_manifest.items}
    ledger: UsageLedger | None = None
    client: object | None = None

    def ensure_ledger() -> UsageLedger:
        nonlocal ledger
        if ledger is None:
            ledger = UsageLedger(usage_db)
            ledger.update_settings(
                monthly_budget_usd=maximum,
                warning_threshold_percent=100,
                hard_limit_enabled=True,
            )
            _require_cost_within_cap(ledger, maximum)
        return ledger

    def ensure_client() -> object:
        nonlocal client
        if client is None:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise AnswerEvaluationError("OPENAI_API_KEY is unavailable")
            ensure_ledger()
            client = _create_openai_client(api_key)
        return client

    print(
        "AUTHORIZED RESUMABLE PHASE: any completed, bound artifacts will be verified and reused. "
        "Only missing checkpoints may call the frozen V26 Sol RAG path or the three Terra "
        "decompositions. Gold annotations, semantic verdicts, conversation history, automatic "
        "retries, and regeneration of completed answers are excluded."
    )

    with _isolated_usage_db(usage_db):
        if generation_path.is_file():
            generated_items, generation_sha256 = _validate_generation_artifact(
                generation_path,
                args=args,
                context=context,
                runner_sha256=runner_sha256,
                cohort_manifest=cohort_manifest,
                cohort_manifest_sha256=cohort_manifest_sha256,
            )
        else:
            ensure_ledger()
            generated_list: list[PrivateGeneratedItem] = []
            for item in context.calibration_items:
                item_id = _required_string(item, "id", label="gold item")
                checkpoint = args.run_root / "items" / item_id / "generated.json"
                if not checkpoint.is_file():
                    _require_cost_reserve(
                        ensure_ledger(),
                        maximum,
                        reserve_usd=GENERATION_ITEM_COST_RESERVE_USD,
                        label=f"generation item {item_id}",
                    )
                generated_list.append(
                    _run_one_generated_item(
                        args=args,
                        context=context,
                        item=item,
                        client=None if checkpoint.is_file() else ensure_client(),
                        usage_db=usage_db,
                        runner_sha256=runner_sha256,
                        cohort_manifest_sha256=cohort_manifest_sha256,
                        cohort_item=cohort_by_id[item_id],
                    )
                )
                _require_cost_within_cap(ensure_ledger(), maximum)
            generated_items = tuple(generated_list)

            generation_artifact: dict[str, object] = {
                "schema": CALIBRATION_GENERATION_SCHEMA,
                "evaluation_id": EVALUATION_ID,
                "created_at": datetime.now(UTC).isoformat(),
                "candidate_commit": context.gold.candidate_commit,
                "rag_policy": context.gold.candidate_rag_policy,
                "gold_set_sha256": context.gold.gold_set_sha256,
                "question_set_sha256": context.gold.question_set_sha256,
                "corpus_manifest_sha256": context.gold.corpus_manifest_sha256,
                "model_catalog_sha256": context.model_catalog_sha256,
                "runner_sha256": runner_sha256,
                "cohort_manifest_sha256": cohort_manifest_sha256,
                "run_identity": dict(context.run_identity),
                "calibration_item_ids": list(context.calibration_ids),
                "remaining_item_count": len(context.remaining_ids),
                "items": [item.model_dump(mode="json") for item in generated_items],
            }
            generation_sha256 = write_json_atomic_no_overwrite(
                generation_path,
                generation_artifact,
            )

        if decomposition_path.is_file():
            canonical_decompositions, decomposition_sha256 = _validate_decomposition_artifact(
                decomposition_path,
                generated_items=generated_items,
                generation_sha256=generation_sha256,
                context=context,
                cohort_manifest_sha256=cohort_manifest_sha256,
            )
        else:
            ensure_ledger()
            decomposition_records: list[dict[str, object]] = []
            canonical_list: list[DecomposedPilotItem] = []
            for generated in generated_items:
                repetitions: list[dict[str, object]] = []
                for repetition in range(1, CALIBRATION_REPETITIONS + 1):
                    checkpoint = (
                        args.run_root
                        / "items"
                        / generated.item_id
                        / f"decomposition-{repetition}.json"
                    )
                    if not checkpoint.is_file():
                        _require_cost_reserve(
                            ensure_ledger(),
                            maximum,
                            reserve_usd=DECOMPOSITION_CALL_COST_RESERVE_USD,
                            label=f"decomposition {generated.item_id}/{repetition}",
                        )
                    repetitions.append(
                        _decomposition_checkpoint(
                            args=args,
                            generated=generated,
                            repetition=repetition,
                            client=None if checkpoint.is_file() else ensure_client(),
                            usage_db=usage_db,
                            cohort_manifest_sha256=cohort_manifest_sha256,
                        )
                    )
                _require_cost_within_cap(ensure_ledger(), maximum)
                canonical = DecomposedPilotItem.model_validate(repetitions[0]["decomposition"])
                _validate_decomposition_against_generated(canonical, generated)
                canonical_list.append(canonical)
                decomposition_records.append(
                    {
                        "item_id": generated.item_id,
                        "answer_sha256": generated.answer_sha256,
                        "repetitions": repetitions,
                    }
                )
            canonical_decompositions = tuple(canonical_list)

            decomposition_artifact: dict[str, object] = {
                "schema": CALIBRATION_DECOMPOSITION_SCHEMA,
                "evaluation_id": EVALUATION_ID,
                "created_at": datetime.now(UTC).isoformat(),
                "pilot_artifact_sha256": generation_sha256,
                "model_catalog_sha256": context.model_catalog_sha256,
                "cohort_manifest_sha256": cohort_manifest_sha256,
                "prompt_version": CLAIM_DECOMPOSITION_PROMPT_VERSION,
                "prompt_sha256": CLAIM_DECOMPOSITION_PROMPT_SHA256,
                "model": JUDGE_MODEL,
                "repetitions_per_item": CALIBRATION_REPETITIONS,
                "items": decomposition_records,
            }
            decomposition_sha256 = write_json_atomic_no_overwrite(
                decomposition_path,
                decomposition_artifact,
            )

        _load_or_write_label_template(
            label_template_path,
            generated_items=generated_items,
            decomposed_items=canonical_decompositions,
            gold_items=context.calibration_items,
            generation_sha256=generation_sha256,
            decomposition_sha256=decomposition_sha256,
        )
        next_action = _next_action_after_generation(
            args,
            context,
            generated_items=generated_items,
            decomposed_items=canonical_decompositions,
            generation_sha256=generation_sha256,
            decomposition_sha256=decomposition_sha256,
        )

    spent = 0.0 if ledger is None else _ledger_total_cost(ledger)
    print(f"Preserved 10 generated answers: {generation_path}")
    print(f"Preserved 30 answer-only decompositions: {decomposition_path}")
    print(f"Owner label template: {label_template_path}")
    print(f"Recorded estimated calibration cost in this isolated ledger: ${spent:.6f}")
    print(f"NEXT ACTION: {next_action}")
    print(
        "No semantic judge verdict has been requested. Complete the owner labels before the "
        "separately authorized calibration-judge phase."
    )


def _write_or_validate_calibration_generation_subset(
    *,
    args: argparse.Namespace,
    context: EvaluationContext,
    runner_sha256: str,
    cohort_manifest: AnswerEvaluationCohortManifest,
    cohort_manifest_sha256: str,
    generated_items: Sequence[PrivateGeneratedItem],
) -> tuple[tuple[PrivateGeneratedItem, ...], str]:
    by_id = {item.item_id: item for item in generated_items}
    calibration_generated = tuple(by_id[item_id] for item_id in context.calibration_ids)
    path = args.run_root / "calibration-generated.json"
    if not path.is_file():
        payload: dict[str, object] = {
            "schema": CALIBRATION_GENERATION_SCHEMA,
            "evaluation_id": EVALUATION_ID,
            "created_at": datetime.now(UTC).isoformat(),
            "candidate_commit": context.gold.candidate_commit,
            "rag_policy": context.gold.candidate_rag_policy,
            "gold_set_sha256": context.gold.gold_set_sha256,
            "question_set_sha256": context.gold.question_set_sha256,
            "corpus_manifest_sha256": context.gold.corpus_manifest_sha256,
            "model_catalog_sha256": context.model_catalog_sha256,
            "runner_sha256": runner_sha256,
            "cohort_manifest_sha256": cohort_manifest_sha256,
            "run_identity": dict(context.run_identity),
            "calibration_item_ids": list(context.calibration_ids),
            "remaining_item_count": len(context.remaining_ids),
            "items": [item.model_dump(mode="json") for item in calibration_generated],
        }
        write_json_atomic_no_overwrite(path, payload)
    validated, artifact_sha256 = _validate_generation_artifact(
        path,
        args=args,
        context=context,
        runner_sha256=runner_sha256,
        cohort_manifest=cohort_manifest,
        cohort_manifest_sha256=cohort_manifest_sha256,
    )
    if validated != calibration_generated:
        raise AnswerEvaluationError(
            "calibration generation subset differs from the preserved 37-item cohort"
        )
    return validated, artifact_sha256


def _retired_calibration_generate() -> None:
    raise AnswerEvaluationError(
        "calibration-generate is retired: it cannot run a ten-item paid cohort. "
        "Use run-37 --authorize-openai-full-evaluation so all 37 frozen answers are "
        "generated before any optional calibration work."
    )


def _load_canonical_decomposition_checkpoints(
    *,
    run_root: Path,
    generated_items: Sequence[PrivateGeneratedItem],
    cohort_manifest_sha256: str,
) -> tuple[PrivateDecompositionCheckpoint, ...]:
    checkpoints: list[PrivateDecompositionCheckpoint] = []
    for generated in generated_items:
        payload = _load_json_object(
            run_root / "items" / generated.item_id / "decomposition-1.json",
            label=f"canonical decomposition checkpoint {generated.item_id}/1",
        )
        _validate_decomposition_checkpoint_payload(
            payload,
            generated=generated,
            repetition=1,
            cohort_manifest_sha256=cohort_manifest_sha256,
        )
        checkpoints.append(PrivateDecompositionCheckpoint.model_validate(payload))
    if len(checkpoints) != 37:
        raise AnswerEvaluationError(
            "immediate evaluation result requires exactly 37 canonical decompositions"
        )
    return tuple(checkpoints)


def _load_or_write_precalibration_private_artifact(
    path: Path,
    *,
    expected: PrecalibrationPrivateArtifact,
    cohort_manifest_sha256: str,
    generation_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    gold_set_sha256: str,
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    gold_items: Sequence[Mapping[str, object]],
    decomposition_checkpoints: Sequence[PrivateDecompositionCheckpoint],
    migration_artifact_sha256: str | None = None,
    recovered_item_ids: Sequence[str] = (),
) -> PrecalibrationPrivateArtifact:
    if path.is_file():
        actual = validate_precalibration_private_artifact(
            _load_json_object(path, label="private pre-calibration result"),
            cohort_manifest_sha256=cohort_manifest_sha256,
            generation_artifact_sha256=generation_artifact_sha256,
            decomposition_artifact_sha256=decomposition_artifact_sha256,
            gold_set_sha256=gold_set_sha256,
            generated_items=generated_items,
            decompositions=decompositions,
            gold_items=gold_items,
            decomposition_checkpoints=decomposition_checkpoints,
            migration_artifact_sha256=migration_artifact_sha256,
            recovered_item_ids=recovered_item_ids,
        )
        if actual != expected:
            raise AnswerEvaluationError(
                "private pre-calibration result differs from the exact 37-item inputs"
            )
        return actual
    write_json_atomic_no_overwrite(path, expected)
    return expected


def _load_or_write_precalibration_public_summary(
    path: Path,
    *,
    expected: PublicPrecalibrationSummary,
) -> str:
    if path.is_file():
        actual = validate_public_precalibration_summary(
            _load_json_object(path, label="public pre-calibration summary")
        )
        if actual != expected:
            raise AnswerEvaluationError(
                "public pre-calibration summary differs from the exact private result"
            )
        return sha256_file(path)
    write_json_atomic_no_overwrite(path, expected)
    return sha256_file(path)


def _emit_precalibration_results(
    *,
    args: argparse.Namespace,
    context: EvaluationContext,
    cohort_manifest: AnswerEvaluationCohortManifest,
    cohort_manifest_sha256: str,
    generated_items: Sequence[PrivateGeneratedItem],
    generation_artifact_sha256: str,
    decompositions: Sequence[DecomposedPilotItem],
    decomposition_artifact_sha256: str,
    migration_artifact_sha256: str | None = None,
    recovered_item_ids: Sequence[str] = (),
) -> tuple[Path, Path, Path]:
    checkpoints = _load_canonical_decomposition_checkpoints(
        run_root=args.run_root,
        generated_items=generated_items,
        cohort_manifest_sha256=cohort_manifest_sha256,
    )
    expected_private = build_precalibration_private_artifact(
        cohort_manifest_sha256=cohort_manifest_sha256,
        generation_artifact_sha256=generation_artifact_sha256,
        decomposition_artifact_sha256=decomposition_artifact_sha256,
        gold_set_sha256=context.gold.gold_set_sha256,
        generated_items=generated_items,
        decompositions=decompositions,
        gold_items=context.gold_items,
        decomposition_checkpoints=checkpoints,
        migration_artifact_sha256=migration_artifact_sha256,
        recovered_item_ids=recovered_item_ids,
    )
    private_path = args.run_root / "precalibration-private.json"
    private_artifact = _load_or_write_precalibration_private_artifact(
        private_path,
        expected=expected_private,
        cohort_manifest_sha256=cohort_manifest_sha256,
        generation_artifact_sha256=generation_artifact_sha256,
        decomposition_artifact_sha256=decomposition_artifact_sha256,
        gold_set_sha256=context.gold.gold_set_sha256,
        generated_items=generated_items,
        decompositions=decompositions,
        gold_items=context.gold_items,
        decomposition_checkpoints=checkpoints,
        migration_artifact_sha256=migration_artifact_sha256,
        recovered_item_ids=recovered_item_ids,
    )
    expected_public = build_public_precalibration_summary(
        candidate_id=context.gold.candidate_rag_policy,
        cohort_manifest=cohort_manifest,
        generated_items=generated_items,
        decompositions=decompositions,
        gold_items=context.gold_items,
        decomposition_checkpoints=checkpoints,
        private_artifact=private_artifact,
        migration_artifact_sha256=migration_artifact_sha256,
        recovered_item_ids=recovered_item_ids,
    )
    summary_path = args.run_root / "precalibration-public-summary.json"
    summary_sha256 = _load_or_write_precalibration_public_summary(
        summary_path,
        expected=expected_public,
    )
    report_path = args.run_root / "precalibration-public-report.md"
    markdown = render_public_precalibration_markdown(
        expected_public,
        public_summary_json_sha256=summary_sha256,
    )
    _load_or_write_public_report(report_path, expected=markdown)
    return private_path, summary_path, report_path


def _validated_recovery_reporting_binding(
    *,
    run_root: Path,
    context: EvaluationContext,
    runner_sha256: str,
    cohort_manifest: AnswerEvaluationCohortManifest,
    cohort_manifest_sha256: str,
    usage_db: Path,
) -> tuple[str | None, tuple[str, ...]]:
    audit_path = run_root / "migration-audit.json"
    if not audit_path.is_file():
        return None, ()
    audit = _load_json_object(audit_path, label="interrupted-run migration audit")
    if audit.get("schema") != "archivist.answer_evaluation.interrupted_run_migration/1":
        raise AnswerEvaluationError("interrupted-run migration audit schema changed")
    artifact_hash = audit.get("artifact_sha256")
    if (
        not isinstance(artifact_hash, str)
        or canonical_json_sha256(
            {key: value for key, value in audit.items() if key != "artifact_sha256"}
        )
        != artifact_hash
    ):
        raise AnswerEvaluationError("interrupted-run migration audit seal changed")
    expected_destination = run_root.relative_to(PRIVATE_EVALUATION_ROOT).as_posix()
    if (
        audit.get("source_runner_sha256") != INTERRUPTED_RUNNER_SHA256
        or audit.get("source_cohort_manifest_file_sha256") != INTERRUPTED_COHORT_FILE_SHA256
        or audit.get("destination_runner_sha256") != runner_sha256
        or audit.get("destination_run_root") != expected_destination
        or audit.get("destination_cohort_manifest_file_sha256") != cohort_manifest_sha256
        or audit.get("provider_calls_repeated") is not False
        or audit.get("recovered_item_id") != "H003"
        or audit.get("full_turn_latency_recovered") is not False
    ):
        raise AnswerEvaluationError("interrupted-run migration identity changed")

    preserved = audit.get("logical_usage_events")
    if not isinstance(preserved, list) or audit.get("logical_usage_event_count") != len(preserved):
        raise AnswerEvaluationError("migration audit has no exact logical usage prefix")
    current = list(_logical_usage_bindings(usage_db))
    if current[: len(preserved)] != preserved:
        raise AnswerEvaluationError("preserved logical usage prefix changed")
    response_ids = [str(event.get("response_id")) for event in current]
    if len(response_ids) != len(set(response_ids)):
        raise AnswerEvaluationError("evaluation usage contains duplicate provider response IDs")

    cohort_by_id = {item.item_id: item for item in cohort_manifest.items}
    gold_by_id = {
        _required_string(item, "id", label="gold item"): item for item in context.gold_items
    }
    generated = {
        item_id: _load_generated_checkpoint(
            run_root / "items" / item_id / "generated.json",
            item=gold_by_id[item_id],
            cohort_manifest_sha256=cohort_manifest_sha256,
            cohort_item=cohort_by_id[item_id],
        )
        for item_id in ("H001", "H002", "H003")
    }
    raw_bindings = audit.get("generated_item_bindings")
    if not isinstance(raw_bindings, list):
        raise AnswerEvaluationError("migration audit has no preserved checkpoint bindings")
    by_id = {
        str(binding.get("item_id")): binding
        for binding in raw_bindings
        if isinstance(binding, Mapping)
    }
    for item_id in ("H001", "H002"):
        binding = by_id.get(item_id)
        if (
            not isinstance(binding, Mapping)
            or binding.get("unchanged_generated_item_sha256") != generated[item_id].item_sha256
            or binding.get("source_checkpoint_file_sha256")
            != INTERRUPTED_GENERATED_CHECKPOINT_SHA256S[item_id]
            or binding.get("destination_checkpoint_file_sha256")
            != sha256_file(run_root / "items" / item_id / "generated.json")
        ):
            raise AnswerEvaluationError(f"{item_id} recovered checkpoint binding changed")
    h003 = generated["H003"]
    h003_trace = h003.trace_references[0] if len(h003.trace_references) == 1 else None
    if (
        h003.item_sha256 != audit.get("recovered_generated_item_sha256")
        or audit.get("recovered_checkpoint_file_sha256")
        != sha256_file(run_root / "items" / "H003" / "generated.json")
        or h003.status != "clean_abstention"
        or h003.evidence_decision != "clean_abstention"
        or h003.sources
        or h003_trace is None
        or h003_trace.sha256 != INTERRUPTED_H003_TRACE_SHA256
        or sha256_file(run_root / "items" / "H003" / h003_trace.path)
        != INTERRUPTED_H003_TRACE_SHA256
        or audit.get("recovery_trace_sha256") != INTERRUPTED_H003_TRACE_SHA256
        or [event.operation for event in h003.usage_events] != ["query_embedding"]
    ):
        raise AnswerEvaluationError("H003 trace-recovered binding changed")
    recovery_audit_path = run_root / "items" / "H003" / "local-release-recovery-audit.json"
    recovery_audit = _load_json_object(
        recovery_audit_path, label="H003 local release recovery audit"
    )
    recovery_seal = recovery_audit.get("artifact_sha256")
    if (
        not isinstance(recovery_seal, str)
        or canonical_json_sha256(
            {key: value for key, value in recovery_audit.items() if key != "artifact_sha256"}
        )
        != recovery_seal
        or recovery_audit.get("generated_item_sha256") != h003.item_sha256
        or recovery_audit.get("trace_sha256") != INTERRUPTED_H003_TRACE_SHA256
        or recovery_audit.get("provider_calls_repeated") is not False
    ):
        raise AnswerEvaluationError("H003 local recovery audit changed")
    return sha256_file(audit_path), ("H003",)


def _recover_interrupted_run(args: argparse.Namespace, context: EvaluationContext) -> None:
    source_root = _require_private_run_root(args.source_run_root)
    destination_root = (
        DEFAULT_RECOVERY_ROOT
        if args.run_root.resolve() == DEFAULT_RUN_ROOT.resolve()
        else _require_private_run_root(args.run_root)
    )
    destination_root = _require_private_run_root(destination_root)
    if destination_root == source_root:
        raise AnswerEvaluationError("offline recovery requires a distinct destination run root")
    runner_sha256 = sha256_file(Path(__file__))
    expected = _expected_cohort_manifest(context, runner_sha256=runner_sha256)
    audit_path = destination_root / "migration-audit.json"
    if audit_path.is_file():
        audit = _load_json_object(audit_path, label="interrupted-run migration audit")
        if (
            audit.get("source_run_root")
            != source_root.relative_to(PRIVATE_EVALUATION_ROOT).as_posix()
        ):
            raise AnswerEvaluationError("interrupted-run migration audit source changed")
        manifest, manifest_sha = _load_or_write_cohort_manifest(
            destination_root / "cohort-manifest.json",
            context=context,
            runner_sha256=runner_sha256,
        )
        usage_path = destination_root / "full-evaluation-usage.sqlite3"
        _validated_recovery_reporting_binding(
            run_root=destination_root,
            context=context,
            runner_sha256=runner_sha256,
            cohort_manifest=manifest,
            cohort_manifest_sha256=manifest_sha,
            usage_db=usage_path,
        )
        print(f"VALIDATED EXISTING OFFLINE RECOVERY: {destination_root}")
        print(
            "Resume with: python scripts/run_answer_evaluation.py run-37 "
            f"--run-root {destination_root} --authorize-openai-full-evaluation "
            "--max-cost-usd 20"
        )
        return
    if destination_root.exists():
        raise AnswerEvaluationError(
            "recovery destination exists without a complete immutable migration audit"
        )

    source_manifest_path = source_root / "cohort-manifest.json"
    if sha256_file(source_manifest_path) != INTERRUPTED_COHORT_FILE_SHA256:
        raise AnswerEvaluationError("source cohort is not the exact known interrupted run")
    source_manifest = AnswerEvaluationCohortManifest.model_validate(
        _load_json_object(source_manifest_path, label="source cohort manifest")
    )
    if source_manifest.runner_sha256 != INTERRUPTED_RUNNER_SHA256:
        raise AnswerEvaluationError("source cohort runner is not the known interrupted runner")
    old_fields = source_manifest.model_dump(mode="json")
    new_fields = expected.model_dump(mode="json")
    old_fields.pop("runner_sha256")
    new_fields.pop("runner_sha256")
    old_fields.pop("manifest_sha256")
    new_fields.pop("manifest_sha256")
    if old_fields != new_fields:
        raise AnswerEvaluationError("source cohort differs beyond the harness runner binding")

    usage_source = source_root / "full-evaluation-usage.sqlite3"
    if _usage_turn_ids(usage_source) != ("H001", "H002", "H003"):
        raise AnswerEvaluationError("source usage contains an unknown or missing interrupted turn")
    staging_root = destination_root.with_name(f".{destination_root.name}.staging-{uuid4().hex}")
    staging_root.mkdir(parents=True, exist_ok=False)
    usage_destination = staging_root / "full-evaluation-usage.sqlite3"
    _archive_bytes_no_overwrite(source=usage_source, destination=usage_destination)
    if sha256_file(usage_source) != sha256_file(usage_destination):
        raise AnswerEvaluationError("usage ledger copy changed bytes")
    write_json_atomic_no_overwrite(staging_root / "cohort-manifest.json", expected)
    new_manifest_sha256 = sha256_file(staging_root / "cohort-manifest.json")
    old_manifest_sha256 = sha256_file(source_manifest_path)
    old_by_id = {item.item_id: item for item in source_manifest.items}
    new_by_id = {item.item_id: item for item in expected.items}
    bindings = []
    for item_id, expected_checkpoint_sha in INTERRUPTED_GENERATED_CHECKPOINT_SHA256S.items():
        source_checkpoint_path = source_root / "items" / item_id / "generated.json"
        if sha256_file(source_checkpoint_path) != expected_checkpoint_sha:
            raise AnswerEvaluationError(f"{item_id} source checkpoint changed")
        source_checkpoint = validate_private_generation_checkpoint(
            PrivateGenerationCheckpoint.model_validate(
                _load_json_object(source_checkpoint_path, label=f"{item_id} source checkpoint")
            ),
            cohort_manifest_sha256=old_manifest_sha256,
            expected_item=old_by_id[item_id],
        )
        destination_item_root = staging_root / "items" / item_id
        for trace in source_checkpoint.item.trace_references:
            _archive_bytes_no_overwrite(
                source=source_root / "items" / item_id / trace.path,
                destination=destination_item_root / trace.path,
            )
        rebound = build_private_generation_checkpoint(
            cohort_manifest_sha256=new_manifest_sha256,
            item=source_checkpoint.item,
        )
        destination_checkpoint = destination_item_root / "generated.json"
        write_json_atomic_no_overwrite(destination_checkpoint, rebound)
        validate_private_generation_checkpoint(
            rebound,
            cohort_manifest_sha256=new_manifest_sha256,
            expected_item=new_by_id[item_id],
        )
        bindings.append(
            {
                "item_id": item_id,
                "unchanged_generated_item_sha256": source_checkpoint.item.item_sha256,
                "source_checkpoint_file_sha256": expected_checkpoint_sha,
                "destination_checkpoint_file_sha256": sha256_file(destination_checkpoint),
            }
        )

    h003_source_traces = sorted(
        (source_root / "items" / "H003" / "retrieval-traces").glob("*/*.json")
    )
    if (
        len(h003_source_traces) != 1
        or sha256_file(h003_source_traces[0]) != INTERRUPTED_H003_TRACE_SHA256
    ):
        raise AnswerEvaluationError("H003 source trace is not the exact known interrupted trace")
    h003_destination_trace = (
        staging_root
        / "items"
        / "H003"
        / h003_source_traces[0].relative_to(source_root / "items" / "H003")
    )
    _archive_bytes_no_overwrite(source=h003_source_traces[0], destination=h003_destination_trace)
    h003_gold = next(item for item in context.gold_items if item.get("id") == "H003")
    h003 = _run_one_generated_item(
        args=argparse.Namespace(
            run_root=staging_root,
            manifest=args.manifest,
            chunks=args.chunks,
        ),
        context=context,
        item=h003_gold,
        client=None,
        usage_db=usage_destination,
        runner_sha256=runner_sha256,
        cohort_manifest_sha256=new_manifest_sha256,
        cohort_item=new_by_id["H003"],
    )
    audit = _sealed_artifact(
        {
            "schema": "archivist.answer_evaluation.interrupted_run_migration/1",
            "source_run_root": source_root.relative_to(PRIVATE_EVALUATION_ROOT).as_posix(),
            "destination_run_root": destination_root.relative_to(
                PRIVATE_EVALUATION_ROOT
            ).as_posix(),
            "source_runner_sha256": INTERRUPTED_RUNNER_SHA256,
            "destination_runner_sha256": runner_sha256,
            "source_cohort_manifest_file_sha256": old_manifest_sha256,
            "destination_cohort_manifest_file_sha256": new_manifest_sha256,
            "usage_ledger_initial_file_sha256": sha256_file(usage_destination),
            "preserved_usage_turn_ids": ["H001", "H002", "H003"],
            "logical_usage_event_count": len(_logical_usage_bindings(usage_destination)),
            "logical_usage_events": list(_logical_usage_bindings(usage_destination)),
            "generated_item_bindings": bindings,
            "recovered_item_id": h003.item_id,
            "recovered_generated_item_sha256": h003.item_sha256,
            "recovered_checkpoint_file_sha256": sha256_file(
                staging_root / "items" / "H003" / "generated.json"
            ),
            "recovery_trace_sha256": INTERRUPTED_H003_TRACE_SHA256,
            "full_turn_latency_recovered": False,
            "provider_calls_repeated": False,
        }
    )
    write_json_atomic_no_overwrite(staging_root / "migration-audit.json", audit)
    os.replace(staging_root, destination_root)
    print(f"OFFLINE INTERRUPTED RUN RECOVERED WITHOUT PROVIDER CALLS: {destination_root}")
    print(
        "Resume with: python scripts/run_answer_evaluation.py run-37 "
        f"--run-root {destination_root} --authorize-openai-full-evaluation "
        "--max-cost-usd 20"
    )


def _run_37(args: argparse.Namespace, context: EvaluationContext) -> None:
    maximum = _require_paid_authorization(
        args,
        flag_name="authorize_openai_full_evaluation",
    )
    args.run_root = _require_private_run_root(args.run_root)
    args.run_root.mkdir(parents=True, exist_ok=True)
    calibration_generation_path = args.run_root / "calibration-generated.json"
    generation_path = args.run_root / "baseline-generated.json"
    decomposition_path = args.run_root / "baseline-decompositions.json"

    if generation_path.is_file() and not calibration_generation_path.is_file():
        raise AnswerEvaluationError(
            "37-item generation artifact exists without its bound calibration subset"
        )
    if decomposition_path.is_file() and not generation_path.is_file():
        raise AnswerEvaluationError(
            "37-item decomposition artifact exists without its bound generation artifact"
        )
    usage_db = args.run_root / "full-evaluation-usage.sqlite3"
    runner_sha256 = sha256_file(Path(__file__))
    cohort_manifest, cohort_manifest_sha256 = _load_or_write_cohort_manifest(
        args.run_root / "cohort-manifest.json",
        context=context,
        runner_sha256=runner_sha256,
    )
    cohort_by_id = {item.item_id: item for item in cohort_manifest.items}
    migration_artifact_sha256, recovered_item_ids = _validated_recovery_reporting_binding(
        run_root=args.run_root,
        context=context,
        runner_sha256=runner_sha256,
        cohort_manifest=cohort_manifest,
        cohort_manifest_sha256=cohort_manifest_sha256,
        usage_db=usage_db,
    )
    ledger: UsageLedger | None = None
    client: object | None = None

    def ensure_ledger() -> UsageLedger:
        nonlocal ledger
        if ledger is None:
            ledger = UsageLedger(usage_db)
            ledger.update_settings(
                monthly_budget_usd=maximum,
                warning_threshold_percent=100,
                hard_limit_enabled=True,
            )
            _require_cost_within_cap(ledger, maximum)
        return ledger

    def ensure_client() -> object:
        nonlocal client
        if client is None:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise AnswerEvaluationError("OPENAI_API_KEY is unavailable")
            ensure_ledger()
            client = _create_openai_client(api_key)
        return client

    print(
        "AUTHORIZED RESUMABLE 37-QUESTION EVALUATION: all frozen questions run before "
        "optional calibration. Completed bound checkpoints are verified and reused; only "
        "missing checkpoints may call the V26 RAG path or answer-only Terra decomposition. "
        "No gold annotations, semantic verdicts, history, retries, or answer regeneration."
    )

    with _isolated_usage_db(usage_db):
        ensure_ledger()
        if generation_path.is_file():
            calibration_generated, calibration_generation_sha = (
                _write_or_validate_calibration_generation_subset(
                    args=args,
                    context=context,
                    runner_sha256=runner_sha256,
                    cohort_manifest=cohort_manifest,
                    cohort_manifest_sha256=cohort_manifest_sha256,
                    generated_items=tuple(
                        _load_generated_checkpoint(
                            args.run_root
                            / "items"
                            / _required_string(item, "id", label="gold item")
                            / "generated.json",
                            item=item,
                            cohort_manifest_sha256=cohort_manifest_sha256,
                            cohort_item=cohort_by_id[
                                _required_string(item, "id", label="gold item")
                            ],
                        )
                        for item in context.calibration_items
                    ),
                )
            )
            generated_items, generation_sha = _validate_baseline_generation_artifact(
                generation_path,
                args=args,
                context=context,
                runner_sha256=runner_sha256,
                cohort_manifest=cohort_manifest,
                cohort_manifest_sha256=cohort_manifest_sha256,
                calibration_generation_sha256=calibration_generation_sha,
            )
        else:
            generated_list: list[PrivateGeneratedItem] = []
            for item in context.gold_items:
                item_id = _required_string(item, "id", label="gold item")
                checkpoint_path = args.run_root / "items" / item_id / "generated.json"
                if not checkpoint_path.is_file():
                    _require_cost_reserve(
                        ensure_ledger(),
                        maximum,
                        reserve_usd=GENERATION_ITEM_COST_RESERVE_USD,
                        label=f"generation item {item_id}",
                    )
                generated_list.append(
                    _run_one_generated_item(
                        args=args,
                        context=context,
                        item=item,
                        client=None if checkpoint_path.is_file() else ensure_client(),
                        usage_db=usage_db,
                        runner_sha256=runner_sha256,
                        cohort_manifest_sha256=cohort_manifest_sha256,
                        cohort_item=cohort_by_id[item_id],
                    )
                )
                _require_cost_within_cap(ensure_ledger(), maximum)
            generated_items = tuple(generated_list)
            calibration_generated, calibration_generation_sha = (
                _write_or_validate_calibration_generation_subset(
                    args=args,
                    context=context,
                    runner_sha256=runner_sha256,
                    cohort_manifest=cohort_manifest,
                    cohort_manifest_sha256=cohort_manifest_sha256,
                    generated_items=generated_items,
                )
            )
            fields = _baseline_generation_fields(
                context=context,
                runner_sha256=runner_sha256,
                cohort_manifest_sha256=cohort_manifest_sha256,
                calibration_generation_sha256=calibration_generation_sha,
                generated_items=generated_items,
            )
            write_json_atomic_no_overwrite(generation_path, _sealed_artifact(fields))
            generation_sha = sha256_file(generation_path)

        if decomposition_path.is_file():
            decompositions, _decomposition_events, decomposition_sha = (
                _validate_baseline_decomposition_artifact(
                    decomposition_path,
                    context=context,
                    generated_items=generated_items,
                    generation_artifact_sha256=generation_sha,
                    cohort_manifest_sha256=cohort_manifest_sha256,
                )
            )
        else:
            canonical_records: list[dict[str, object]] = []
            canonical_decompositions: list[DecomposedPilotItem] = []
            for generated in generated_items:
                checkpoint_path = (
                    args.run_root / "items" / generated.item_id / "decomposition-1.json"
                )
                if not checkpoint_path.is_file():
                    _require_cost_reserve(
                        ensure_ledger(),
                        maximum,
                        reserve_usd=DECOMPOSITION_CALL_COST_RESERVE_USD,
                        label=f"decomposition {generated.item_id}/1",
                    )
                checkpoint_payload = _decomposition_checkpoint(
                    args=args,
                    generated=generated,
                    repetition=1,
                    client=None if checkpoint_path.is_file() else ensure_client(),
                    usage_db=usage_db,
                    cohort_manifest_sha256=cohort_manifest_sha256,
                )
                _require_cost_within_cap(ensure_ledger(), maximum)
                canonical = _validate_decomposition_checkpoint_payload(
                    checkpoint_payload,
                    generated=generated,
                    repetition=1,
                    cohort_manifest_sha256=cohort_manifest_sha256,
                )
                canonical_decompositions.append(canonical)
                canonical_records.append(
                    {
                        "item_id": generated.item_id,
                        "answer_sha256": generated.answer_sha256,
                        "checkpoint": dict(checkpoint_payload),
                    }
                )
            decompositions = tuple(canonical_decompositions)
            fields = _baseline_decomposition_fields(
                context=context,
                generation_artifact_sha256=generation_sha,
                cohort_manifest_sha256=cohort_manifest_sha256,
                records=canonical_records,
            )
            write_json_atomic_no_overwrite(decomposition_path, _sealed_artifact(fields))
            decomposition_sha = sha256_file(decomposition_path)

        private_result, public_summary, public_report = _emit_precalibration_results(
            args=args,
            context=context,
            cohort_manifest=cohort_manifest,
            cohort_manifest_sha256=cohort_manifest_sha256,
            generated_items=generated_items,
            generation_artifact_sha256=generation_sha,
            decompositions=decompositions,
            decomposition_artifact_sha256=decomposition_sha,
            migration_artifact_sha256=migration_artifact_sha256,
            recovered_item_ids=recovered_item_ids,
        )

    spent = _ledger_total_cost(ensure_ledger())
    print(f"Preserved all 37 generated answers: {generation_path}")
    print(f"Preserved all 37 canonical decompositions: {decomposition_path}")
    print(f"Preserved immediate private result binding: {private_result}")
    print(f"Preserved immediate public mechanical summary: {public_summary}")
    print(f"Preserved immediate public mechanical report: {public_report}")
    print(f"Recorded estimated full-cohort cost: ${spent:.6f}")
    print(
        "Immediate mechanical results are ready. Optional owner calibration and semantic "
        "scoring may follow, but cannot delay or replace those results."
    )


def _load_calibration_artifacts(args: argparse.Namespace, context: EvaluationContext):
    args.run_root = _require_private_run_root(args.run_root)
    generation_path = args.run_root / "calibration-generated.json"
    decomposition_path = args.run_root / "calibration-decompositions.json"
    runner_sha256 = sha256_file(Path(__file__))
    cohort_manifest, cohort_manifest_sha256 = _load_or_write_cohort_manifest(
        args.run_root / "cohort-manifest.json",
        context=context,
        runner_sha256=runner_sha256,
    )
    generated, generation_sha256 = _validate_generation_artifact(
        generation_path,
        args=args,
        context=context,
        runner_sha256=runner_sha256,
        cohort_manifest=cohort_manifest,
        cohort_manifest_sha256=cohort_manifest_sha256,
    )
    canonical, decomposition_sha256 = _validate_decomposition_artifact(
        decomposition_path,
        generated_items=generated,
        generation_sha256=generation_sha256,
        context=context,
        cohort_manifest_sha256=cohort_manifest_sha256,
    )
    return (
        generated,
        canonical,
        generation_sha256,
        decomposition_sha256,
    )


def _validate_labels(args: argparse.Namespace, context: EvaluationContext) -> None:
    generated, decomposed, generation_sha, decomposition_sha = _load_calibration_artifacts(
        args,
        context,
    )
    labels = CalibrationLabelFile.model_validate(
        _load_json_object(args.labels, label="owner calibration labels")
    )
    validate_calibration_labels_for_judge(
        labels,
        generated_items=generated,
        decomposed_items=decomposed,
        gold_items=context.calibration_items,
        pilot_artifact_sha256=generation_sha,
        decomposition_artifact_sha256=decomposition_sha,
    )
    print("VALID COMPLETE OWNER CALIBRATION LABELS")
    print(f"Items: {len(labels.items)}")
    print(f"Labels SHA-256: {sha256_file(args.labels)}")
    print("Semantic judge calibration may now be separately authorized.")


def _judge_settings_payload() -> dict[str, object]:
    return {
        "reasoning_effort": JUDGE_SETTINGS.reasoning_effort,
        "verbosity": JUDGE_SETTINGS.verbosity,
    }


def _atomic_claim(claim: object) -> AtomicClaim:
    return AtomicClaim(
        claim_id=str(getattr(claim, "claim_id")),
        text=str(getattr(claim, "text")),
        char_start=int(getattr(claim, "char_start")),
        char_end=int(getattr(claim, "char_end")),
        cited_sources=list(getattr(claim, "cited_source_numbers")),
    )


def _load_validated_calibration_inputs(
    args: argparse.Namespace,
    context: EvaluationContext,
) -> tuple[
    tuple[PrivateGeneratedItem, ...],
    tuple[DecomposedPilotItem, ...],
    str,
    str,
    str,
    CalibrationLabelFile,
]:
    generated, decomposed, generation_sha, decomposition_sha = _load_calibration_artifacts(
        args, context
    )
    cohort_manifest_sha = sha256_file(args.run_root / "cohort-manifest.json")
    labels = CalibrationLabelFile.model_validate(
        _load_json_object(args.labels, label="owner calibration labels")
    )
    validate_calibration_labels_for_judge(
        labels,
        generated_items=generated,
        decomposed_items=decomposed,
        gold_items=context.calibration_items,
        pilot_artifact_sha256=generation_sha,
        decomposition_artifact_sha256=decomposition_sha,
    )
    return (
        generated,
        decomposed,
        generation_sha,
        decomposition_sha,
        cohort_manifest_sha,
        labels,
    )


def _claim_evidence_checkpoint(
    *,
    args: argparse.Namespace,
    generated: PrivateGeneratedItem,
    decomposition: DecomposedPilotItem,
    claim: object,
    call_ordinal: int,
    client: object | None,
    ledger: UsageLedger,
    maximum: float,
    usage_db: Path,
    cohort_manifest_sha256: str,
) -> ClaimEvidenceResult:
    claim_id = str(getattr(claim, "claim_id"))
    path = (
        args.run_root
        / "items"
        / generated.item_id
        / f"claim-evidence-{claim_id}-{call_ordinal}.json"
    )
    if path.is_file():
        return validate_claim_evidence_result(
            ClaimEvidenceResult.model_validate(
                _load_json_object(path, label="claim-evidence checkpoint")
            ),
            cohort_manifest_sha256=cohort_manifest_sha256,
            generated_item=generated,
            decomposition=decomposition,
            claim=claim,
            call_ordinal=call_ordinal,
            prompt_version=CLAIM_EVIDENCE_PROMPT_VERSION,
            prompt_sha256=CLAIM_EVIDENCE_PROMPT_SHA256,
            judge_model=JUDGE_MODEL,
            judge_settings=_judge_settings_payload(),
        )

    turn_id = f"{generated.item_id}:claim-evidence:{claim_id}:{call_ordinal}"
    _require_no_orphan_usage(usage_db, turn_id=turn_id)
    _require_cost_reserve(
        ledger,
        maximum,
        reserve_usd=CLAIM_EVIDENCE_CALL_COST_RESERVE_USD,
        label=f"claim evidence {generated.item_id}/{claim_id}/{call_ordinal}",
    )
    if client is None:  # pragma: no cover - internal call-order guard
        raise AnswerEvaluationError("missing provider client for claim-evidence call")
    source_texts = {source.source_number: source.text for source in generated.sources}
    capturing_client = _ProviderCapturingClient(client)
    with usage_scope(
        project_id=EVALUATION_ID,
        conversation_id="held-out-37",
        turn_id=turn_id,
        enforce_budget=True,
    ):
        judged = judge_claim_evidence(
            capturing_client,
            claim=_atomic_claim(claim),
            source_texts=source_texts,
        )
    usage_event = _private_usage_events(
        usage_db,
        turn_id=turn_id,
        phase="claim_evidence",
        provider_observations=capturing_client.observations,
    )[0]
    result = build_claim_evidence_result(
        cohort_manifest_sha256=cohort_manifest_sha256,
        generated_item=generated,
        decomposition=decomposition,
        claim=claim,
        call_ordinal=call_ordinal,
        prompt_version=CLAIM_EVIDENCE_PROMPT_VERSION,
        prompt_sha256=CLAIM_EVIDENCE_PROMPT_SHA256,
        judge_model=JUDGE_MODEL,
        judge_settings=_judge_settings_payload(),
        provider=_provider_payload(judged.provider),
        usage_event=usage_event,
        verdict=judged.parsed,
    )
    write_json_atomic_no_overwrite(path, result)
    return result


def _item_rubric_checkpoint(
    *,
    args: argparse.Namespace,
    generated: PrivateGeneratedItem,
    decomposition: DecomposedPilotItem,
    gold_item: Mapping[str, object],
    client: object | None,
    ledger: UsageLedger,
    maximum: float,
    usage_db: Path,
    cohort_manifest_sha256: str,
) -> ItemRubricResult:
    path = args.run_root / "items" / generated.item_id / "item-rubric.json"
    rubric = build_item_rubric_input(
        question=generated.question,
        gold_item=gold_item,
    )
    if path.is_file():
        return validate_item_rubric_result(
            ItemRubricResult.model_validate(
                _load_json_object(path, label="item-rubric checkpoint")
            ),
            cohort_manifest_sha256=cohort_manifest_sha256,
            generated_item=generated,
            decomposition=decomposition,
            rubric=rubric,
            prompt_version=ITEM_RUBRIC_PROMPT_VERSION,
            prompt_sha256=ITEM_RUBRIC_PROMPT_SHA256,
            judge_model=JUDGE_MODEL,
            judge_settings=_judge_settings_payload(),
        )

    turn_id = f"{generated.item_id}:item-rubric"
    _require_no_orphan_usage(usage_db, turn_id=turn_id)
    _require_cost_reserve(
        ledger,
        maximum,
        reserve_usd=ITEM_RUBRIC_CALL_COST_RESERVE_USD,
        label=f"item rubric {generated.item_id}",
    )
    if client is None:  # pragma: no cover - internal call-order guard
        raise AnswerEvaluationError("missing provider client for item-rubric call")
    capturing_client = _ProviderCapturingClient(client)
    with usage_scope(
        project_id=EVALUATION_ID,
        conversation_id="held-out-37",
        turn_id=turn_id,
        enforce_budget=True,
    ):
        judged = judge_item_rubric(
            capturing_client,
            answer=generated.answer,
            answer_claims=tuple(_atomic_claim(claim) for claim in decomposition.claims),
            rubric=rubric,
        )
    usage_event = _private_usage_events(
        usage_db,
        turn_id=turn_id,
        phase="item_rubric",
        provider_observations=capturing_client.observations,
    )[0]
    result = build_item_rubric_result(
        cohort_manifest_sha256=cohort_manifest_sha256,
        generated_item=generated,
        decomposition=decomposition,
        rubric=rubric,
        prompt_version=ITEM_RUBRIC_PROMPT_VERSION,
        prompt_sha256=ITEM_RUBRIC_PROMPT_SHA256,
        judge_model=JUDGE_MODEL,
        judge_settings=_judge_settings_payload(),
        provider=_provider_payload(judged.provider),
        usage_event=usage_event,
        verdict=judged.parsed,
    )
    write_json_atomic_no_overwrite(path, result)
    return result


def _require_calibration_semantic_checkpoints(
    run_root: Path,
    *,
    generated: Sequence[PrivateGeneratedItem],
    decomposed: Sequence[DecomposedPilotItem],
) -> None:
    """Refuse to recreate component calls behind an existing aggregate."""

    for generated_item, decomposition in zip(generated, decomposed, strict=True):
        required = [
            run_root / "items" / generated_item.item_id / "item-rubric.json",
            *(
                run_root
                / "items"
                / generated_item.item_id
                / f"claim-evidence-{claim.claim_id}-1.json"
                for claim in decomposition.claims
            ),
        ]
        if decomposition.claims:
            required.append(
                run_root
                / "items"
                / generated_item.item_id
                / f"claim-evidence-{decomposition.claims[0].claim_id}-2.json"
            )
        missing = [path for path in required if not path.is_file()]
        if missing:
            raise AnswerEvaluationError(
                "calibration semantic aggregate exists without all component "
                f"checkpoints ({missing[0]}); refusing a repeat call"
            )


def _require_baseline_semantic_checkpoints(
    run_root: Path,
    *,
    generated: Sequence[PrivateGeneratedItem],
    decomposed: Sequence[DecomposedPilotItem],
    calibration_item_ids: Sequence[str],
    evidence_active: bool,
    rubric_active: bool,
) -> None:
    """Refuse to recreate remaining-item calls behind an existing aggregate."""

    calibration_ids = set(calibration_item_ids)
    for generated_item, decomposition in zip(generated, decomposed, strict=True):
        if generated_item.item_id in calibration_ids:
            continue
        required: list[Path] = []
        if evidence_active:
            required.extend(
                run_root
                / "items"
                / generated_item.item_id
                / f"claim-evidence-{claim.claim_id}-1.json"
                for claim in decomposition.claims
            )
        if rubric_active:
            required.append(run_root / "items" / generated_item.item_id / "item-rubric.json")
        missing = [path for path in required if not path.is_file()]
        if missing:
            raise AnswerEvaluationError(
                "baseline semantic aggregate exists without all component "
                f"checkpoints ({missing[0]}); refusing a repeat call"
            )


def _expected_semantic_results(
    *,
    args: argparse.Namespace,
    context: EvaluationContext,
    generated: Sequence[PrivateGeneratedItem],
    decomposed: Sequence[DecomposedPilotItem],
    generation_sha256: str,
    decomposition_sha256: str,
    cohort_manifest_sha256: str,
    checkpoint_loader: object,
) -> CalibrationSemanticAggregate:
    semantic_items = []
    for generated_item, decomposition, gold_item in zip(
        generated,
        decomposed,
        context.calibration_items,
        strict=True,
    ):
        first_results = tuple(
            checkpoint_loader(
                kind="claim",
                generated=generated_item,
                decomposition=decomposition,
                claim=claim,
                call_ordinal=1,
                gold_item=gold_item,
            )
            for claim in decomposition.claims
        )
        repeat = (
            None
            if not decomposition.claims
            else checkpoint_loader(
                kind="claim",
                generated=generated_item,
                decomposition=decomposition,
                claim=decomposition.claims[0],
                call_ordinal=2,
                gold_item=gold_item,
            )
        )
        rubric = checkpoint_loader(
            kind="rubric",
            generated=generated_item,
            decomposition=decomposition,
            claim=None,
            call_ordinal=None,
            gold_item=gold_item,
        )
        semantic_items.append(
            build_calibration_semantic_item(
                first_call_claim_evidence=first_results,
                item_rubric=rubric,
                repeat_first_claim_evidence=repeat,
            )
        )
    return build_calibration_semantic_aggregate(
        cohort_manifest_sha256=cohort_manifest_sha256,
        pilot_artifact_sha256=generation_sha256,
        decomposition_artifact_sha256=decomposition_sha256,
        calibration_item_ids=context.calibration_ids,
        items=semantic_items,
    )


def _load_or_validate_semantic_aggregate(
    path: Path,
    *,
    expected: CalibrationSemanticAggregate,
) -> CalibrationSemanticAggregate:
    if path.is_file():
        actual = validate_calibration_semantic_aggregate(
            CalibrationSemanticAggregate.model_validate(
                _load_json_object(path, label="calibration semantic aggregate")
            ),
            cohort_manifest_sha256=expected.cohort_manifest_sha256,
            pilot_artifact_sha256=expected.pilot_artifact_sha256,
            decomposition_artifact_sha256=expected.decomposition_artifact_sha256,
            calibration_item_ids=expected.calibration_item_ids,
        )
        if actual != expected:
            raise AnswerEvaluationError(
                "calibration semantic aggregate differs from its sealed call checkpoints"
            )
        return actual
    write_json_atomic_no_overwrite(path, expected)
    return expected


def _load_or_validate_agreement_projection(
    path: Path,
    *,
    aggregate: CalibrationSemanticAggregate,
    labels: CalibrationLabelFile,
) -> CalibrationAgreementProjection:
    expected = project_calibration_agreement(aggregate, labels)
    if path.is_file():
        actual = CalibrationAgreementProjection.model_validate(
            _load_json_object(path, label="calibration agreement projection")
        )
        if actual != expected:
            raise AnswerEvaluationError(
                "calibration agreement projection differs from semantic results and labels"
            )
        return actual
    write_json_atomic_no_overwrite(path, expected)
    return expected


def _calibration_judge(args: argparse.Namespace, context: EvaluationContext) -> None:
    maximum = _require_paid_authorization(
        args,
        flag_name="authorize_openai_calibration_judge",
    )
    args.run_root = _require_private_run_root(args.run_root)
    (
        generated,
        decomposed,
        generation_sha,
        decomposition_sha,
        cohort_manifest_sha,
        labels,
    ) = _load_validated_calibration_inputs(args, context)

    usage_db = args.run_root / "calibration-judge-usage.sqlite3"
    semantic_path = args.run_root / "calibration-semantic-results.json"
    agreement_path = args.run_root / "calibration-agreement-projection.json"
    if agreement_path.is_file() and not semantic_path.is_file():
        raise AnswerEvaluationError("agreement projection exists without its semantic aggregate")
    if semantic_path.is_file():
        _require_calibration_semantic_checkpoints(
            args.run_root,
            generated=generated,
            decomposed=decomposed,
        )

    ledger: UsageLedger | None = None
    client: object | None = None

    def ensure_ledger() -> UsageLedger:
        nonlocal ledger
        if ledger is None:
            ledger = UsageLedger(usage_db)
            ledger.update_settings(
                monthly_budget_usd=maximum,
                warning_threshold_percent=100,
                hard_limit_enabled=True,
            )
            _require_cost_within_cap(ledger, maximum)
        return ledger

    def ensure_client() -> object:
        nonlocal client
        if client is None:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise AnswerEvaluationError("OPENAI_API_KEY is unavailable")
            ensure_ledger()
            client = _create_openai_client(api_key)
        return client

    print(
        "AUTHORIZED RESUMABLE SEMANTIC CALIBRATION: complete owner labels have exact-"
        "validated. Each missing checkpoint makes one non-retrying Terra call with an "
        "isolated turn ID. Claim-evidence calls receive the full ordered source union and "
        "no gold fields; item-rubric calls receive the sanitized rubric and no sources."
    )

    with _isolated_usage_db(usage_db):

        def checkpoint_loader(**values: object) -> object:
            kind = values["kind"]
            generated_item = values["generated"]
            decomposition = values["decomposition"]
            if not isinstance(generated_item, PrivateGeneratedItem) or not isinstance(
                decomposition,
                DecomposedPilotItem,
            ):
                raise TypeError("semantic checkpoint loader received invalid item inputs")
            if kind == "claim":
                claim = values["claim"]
                call_ordinal = values["call_ordinal"]
                claim_id = str(getattr(claim, "claim_id"))
                checkpoint = (
                    args.run_root
                    / "items"
                    / generated_item.item_id
                    / f"claim-evidence-{claim_id}-{call_ordinal}.json"
                )
                return _claim_evidence_checkpoint(
                    args=args,
                    generated=generated_item,
                    decomposition=decomposition,
                    claim=claim,
                    call_ordinal=int(call_ordinal),
                    client=None if checkpoint.is_file() else ensure_client(),
                    ledger=ensure_ledger(),
                    maximum=maximum,
                    usage_db=usage_db,
                    cohort_manifest_sha256=cohort_manifest_sha,
                )
            gold_item = values["gold_item"]
            if not isinstance(gold_item, Mapping):
                raise TypeError("semantic checkpoint loader received invalid gold item")
            checkpoint = args.run_root / "items" / generated_item.item_id / "item-rubric.json"
            return _item_rubric_checkpoint(
                args=args,
                generated=generated_item,
                decomposition=decomposition,
                gold_item=gold_item,
                client=None if checkpoint.is_file() else ensure_client(),
                ledger=ensure_ledger(),
                maximum=maximum,
                usage_db=usage_db,
                cohort_manifest_sha256=cohort_manifest_sha,
            )

        expected = _expected_semantic_results(
            args=args,
            context=context,
            generated=generated,
            decomposed=decomposed,
            generation_sha256=generation_sha,
            decomposition_sha256=decomposition_sha,
            cohort_manifest_sha256=cohort_manifest_sha,
            checkpoint_loader=checkpoint_loader,
        )
        aggregate = _load_or_validate_semantic_aggregate(
            semantic_path,
            expected=expected,
        )
        projection = _load_or_validate_agreement_projection(
            agreement_path,
            aggregate=aggregate,
            labels=labels,
        )
        if ledger is not None:
            _require_cost_within_cap(ledger, maximum)

    spent = 0.0 if ledger is None else _ledger_total_cost(ledger)
    print(f"Preserved semantic calibration: {semantic_path}")
    print(f"Preserved agreement projection: {agreement_path}")
    print(
        "Pooled exact agreement: "
        f"{projection.pooled_exact_agreement.agreement_count}/"
        f"{projection.pooled_exact_agreement.denominator}; repeat agreement: "
        f"{projection.repeat_agreement.agreement_count}/"
        f"{projection.repeat_agreement.denominator}"
    )
    print(f"Recorded estimated semantic-calibration cost: ${spent:.6f}")
    print(f"NEXT ACTION: {NEXT_ACTION_LOCK_INSTRUMENT}")


def _load_semantic_inputs_offline(
    args: argparse.Namespace,
    context: EvaluationContext,
) -> tuple[
    CalibrationSemanticAggregate,
    CalibrationAgreementProjection,
    str,
    str,
    str,
    CalibrationLabelFile,
]:
    (
        generated,
        decomposed,
        generation_sha,
        decomposition_sha,
        cohort_manifest_sha,
        labels,
    ) = _load_validated_calibration_inputs(args, context)

    def checkpoint_loader(**values: object) -> object:
        generated_item = values["generated"]
        decomposition = values["decomposition"]
        if not isinstance(generated_item, PrivateGeneratedItem) or not isinstance(
            decomposition,
            DecomposedPilotItem,
        ):
            raise TypeError("semantic checkpoint loader received invalid item inputs")
        if values["kind"] == "claim":
            claim = values["claim"]
            call_ordinal = int(values["call_ordinal"])
            claim_id = str(getattr(claim, "claim_id"))
            path = (
                args.run_root
                / "items"
                / generated_item.item_id
                / f"claim-evidence-{claim_id}-{call_ordinal}.json"
            )
            return validate_claim_evidence_result(
                ClaimEvidenceResult.model_validate(
                    _load_json_object(path, label="claim-evidence checkpoint")
                ),
                cohort_manifest_sha256=cohort_manifest_sha,
                generated_item=generated_item,
                decomposition=decomposition,
                claim=claim,
                call_ordinal=call_ordinal,
                prompt_version=CLAIM_EVIDENCE_PROMPT_VERSION,
                prompt_sha256=CLAIM_EVIDENCE_PROMPT_SHA256,
                judge_model=JUDGE_MODEL,
                judge_settings=_judge_settings_payload(),
            )
        gold_item = values["gold_item"]
        if not isinstance(gold_item, Mapping):
            raise TypeError("semantic checkpoint loader received invalid gold item")
        rubric = build_item_rubric_input(
            question=generated_item.question,
            gold_item=gold_item,
        )
        path = args.run_root / "items" / generated_item.item_id / "item-rubric.json"
        return validate_item_rubric_result(
            ItemRubricResult.model_validate(
                _load_json_object(path, label="item-rubric checkpoint")
            ),
            cohort_manifest_sha256=cohort_manifest_sha,
            generated_item=generated_item,
            decomposition=decomposition,
            rubric=rubric,
            prompt_version=ITEM_RUBRIC_PROMPT_VERSION,
            prompt_sha256=ITEM_RUBRIC_PROMPT_SHA256,
            judge_model=JUDGE_MODEL,
            judge_settings=_judge_settings_payload(),
        )

    expected = _expected_semantic_results(
        args=args,
        context=context,
        generated=generated,
        decomposed=decomposed,
        generation_sha256=generation_sha,
        decomposition_sha256=decomposition_sha,
        cohort_manifest_sha256=cohort_manifest_sha,
        checkpoint_loader=checkpoint_loader,
    )
    aggregate = _load_or_validate_semantic_aggregate(
        args.run_root / "calibration-semantic-results.json",
        expected=expected,
    )
    projection = _load_or_validate_agreement_projection(
        args.run_root / "calibration-agreement-projection.json",
        aggregate=aggregate,
        labels=labels,
    )
    return (
        aggregate,
        projection,
        generation_sha,
        decomposition_sha,
        cohort_manifest_sha,
        labels,
    )


def _load_decomposition_repetitions(
    args: argparse.Namespace,
    *,
    generated: Sequence[PrivateGeneratedItem],
    cohort_manifest_sha256: str,
) -> tuple[tuple[DecomposedPilotItem, ...], ...]:
    payload = _load_json_object(
        args.run_root / "calibration-decompositions.json",
        label="calibration decomposition artifact",
    )
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or len(raw_items) != len(generated):
        raise AnswerEvaluationError("calibration decomposition item count changed")
    result: list[tuple[DecomposedPilotItem, ...]] = []
    for generated_item, raw_item in zip(generated, raw_items, strict=True):
        if not isinstance(raw_item, Mapping) or raw_item.get("item_id") != generated_item.item_id:
            raise AnswerEvaluationError("calibration decomposition item order changed")
        raw_repetitions = raw_item.get("repetitions")
        if not isinstance(raw_repetitions, list) or len(raw_repetitions) != 3:
            raise AnswerEvaluationError(
                f"{generated_item.item_id}: decomposition repetition count changed"
            )
        repetitions = tuple(
            _validate_decomposition_checkpoint_payload(
                raw,
                generated=generated_item,
                repetition=repetition,
                cohort_manifest_sha256=cohort_manifest_sha256,
            )
            for repetition, raw in enumerate(raw_repetitions, start=1)
            if isinstance(raw, Mapping)
        )
        if len(repetitions) != 3:
            raise AnswerEvaluationError(
                f"{generated_item.item_id}: malformed decomposition repetition"
            )
        result.append(repetitions)
    return tuple(result)


def _load_or_write_decomposition_stability(
    args: argparse.Namespace,
    *,
    generated: Sequence[PrivateGeneratedItem],
    decomposition_sha256: str,
    cohort_manifest_sha256: str,
    calibration_item_ids: Sequence[str],
) -> DecompositionStability:
    repetitions = _load_decomposition_repetitions(
        args,
        generated=generated,
        cohort_manifest_sha256=cohort_manifest_sha256,
    )
    expected = build_decomposition_stability(
        decomposition_artifact_sha256=decomposition_sha256,
        calibration_item_ids=calibration_item_ids,
        repetitions=repetitions,
    )
    path = args.run_root / "calibration-decomposition-stability.json"
    if path.is_file():
        return validate_decomposition_stability(
            DecompositionStability.model_validate(
                _load_json_object(path, label="decomposition stability artifact")
            ),
            decomposition_artifact_sha256=decomposition_sha256,
            calibration_item_ids=calibration_item_ids,
            repetitions=repetitions,
        )
    write_json_atomic_no_overwrite(path, expected)
    return expected


def _expected_instrument_lock(
    *,
    args: argparse.Namespace,
    aggregate: CalibrationSemanticAggregate,
    projection: CalibrationAgreementProjection,
    generation_sha: str,
    decomposition_sha: str,
    cohort_manifest_sha: str,
) -> InstrumentLock:
    pooled_rate = projection.pooled_exact_agreement.agreement_rate
    repeat_rate = projection.repeat_agreement.agreement_rate
    if pooled_rate is None or repeat_rate is None:
        raise AnswerEvaluationError(
            "calibration agreement has an empty pooled or repeat denominator"
        )
    dimension_agreements: dict[ScoringDimension, tuple[float, int]] = {}
    for dimension in projection.dimensions:
        if dimension.agreement_rate is None:
            raise AnswerEvaluationError(
                f"calibration dimension {dimension.dimension.value} has no decisions"
            )
        dimension_agreements[dimension.dimension] = (
            dimension.agreement_rate,
            dimension.denominator,
        )
    return build_instrument_lock(
        instrument_id=INSTRUMENT_ID,
        cohort_manifest_sha256=cohort_manifest_sha,
        pilot_artifact_sha256=generation_sha,
        decomposition_artifact_sha256=decomposition_sha,
        human_labels_sha256=sha256_file(args.labels),
        judge_results_sha256=aggregate.aggregate_sha256,
        judge_model=JUDGE_MODEL,
        judge_settings=_judge_settings_payload(),
        decomposition_prompt_sha256=CLAIM_DECOMPOSITION_PROMPT_SHA256,
        evidence_prompt_sha256=CLAIM_EVIDENCE_PROMPT_SHA256,
        rubric_prompt_sha256=ITEM_RUBRIC_PROMPT_SHA256,
        pooled_agreement=pooled_rate,
        repeat_agreement=repeat_rate,
        dimension_agreements=dimension_agreements,
    )


def _load_locked_instrument(
    args: argparse.Namespace,
    context: EvaluationContext,
) -> tuple[
    InstrumentLock,
    CalibrationSemanticAggregate,
    CalibrationAgreementProjection,
    str,
    str,
    str,
    CalibrationLabelFile,
]:
    (
        aggregate,
        projection,
        generation_sha,
        decomposition_sha,
        cohort_manifest_sha,
        labels,
    ) = _load_semantic_inputs_offline(args, context)
    expected = _expected_instrument_lock(
        args=args,
        aggregate=aggregate,
        projection=projection,
        generation_sha=generation_sha,
        decomposition_sha=decomposition_sha,
        cohort_manifest_sha=cohort_manifest_sha,
    )
    path = args.run_root / "instrument-lock.json"
    if not path.is_file():
        raise AnswerEvaluationError("scoring instrument lock is missing")
    locked = InstrumentLock.model_validate(_load_json_object(path, label="scoring instrument lock"))
    if locked != expected:
        raise AnswerEvaluationError(
            "existing scoring instrument lock differs from its exact inputs"
        )
    return (
        locked,
        aggregate,
        projection,
        generation_sha,
        decomposition_sha,
        cohort_manifest_sha,
        labels,
    )


def _lock_instrument(args: argparse.Namespace, context: EvaluationContext) -> None:
    if not args.owner_ratifies_scoring_lock:
        raise AnswerEvaluationError(
            "lock-instrument requires explicit --owner-ratifies-scoring-lock"
        )
    args.run_root = _require_private_run_root(args.run_root)
    (
        aggregate,
        projection,
        generation_sha,
        decomposition_sha,
        cohort_manifest_sha,
        _labels,
    ) = _load_semantic_inputs_offline(args, context)
    generated, _, _, _ = _load_calibration_artifacts(args, context)
    stability = _load_or_write_decomposition_stability(
        args,
        generated=generated,
        decomposition_sha256=decomposition_sha,
        cohort_manifest_sha256=cohort_manifest_sha,
        calibration_item_ids=context.calibration_ids,
    )
    # InstrumentLock v1 has no decomposition-stability field. The separate
    # artifact is exactly bound to the decomposition artifact and remains a
    # descriptive calibration result, never an eligibility gate.
    expected = _expected_instrument_lock(
        args=args,
        aggregate=aggregate,
        projection=projection,
        generation_sha=generation_sha,
        decomposition_sha=decomposition_sha,
        cohort_manifest_sha=cohort_manifest_sha,
    )
    path = args.run_root / "instrument-lock.json"
    if path.is_file():
        actual = InstrumentLock.model_validate(
            _load_json_object(path, label="scoring instrument lock")
        )
        if actual != expected:
            raise AnswerEvaluationError(
                "existing scoring instrument lock differs from its exact inputs"
            )
        locked = actual
    else:
        write_json_atomic_no_overwrite(path, expected)
        locked = expected
    print(f"LOCKED SCORING INSTRUMENT: {path}")
    print(
        "Descriptive decomposition stability: "
        f"{stability.stability_sha256} (not a judge-eligibility gate)"
    )
    print(f"Overall scoring mode: {locked.scoring_mode.value}")
    for dimension in locked.dimensions:
        print(
            f"{dimension.dimension.value}: {dimension.scoring_mode.value} "
            f"({dimension.agreement:.3f}, n={dimension.denominator})"
        )
    print(
        "Low agreement selects manual fallback only for affected dimensions; it does not "
        "change, delay, or suppress the already preserved 37-question results."
    )
    print(f"OPTIONAL SCORING ACTION: {locked.baseline_next_action}")


def _sealed_artifact(fields: Mapping[str, object]) -> dict[str, object]:
    raw = dict(fields)
    if "artifact_sha256" in raw:
        raise ValueError("artifact fields must not supply artifact_sha256")
    raw["artifact_sha256"] = canonical_json_sha256(raw)
    return raw


def _validate_sealed_artifact(
    payload: Mapping[str, object],
    *,
    expected_without_hash: Mapping[str, object],
    label: str,
) -> None:
    expected_keys = set(expected_without_hash) | {"artifact_sha256"}
    if set(payload) != expected_keys:
        raise AnswerEvaluationError(f"{label} fields changed")
    if payload.get("artifact_sha256") != canonical_json_sha256(expected_without_hash):
        raise AnswerEvaluationError(f"{label} artifact_sha256 changed")
    for field, expected in expected_without_hash.items():
        if payload.get(field) != expected:
            raise AnswerEvaluationError(f"{label} {field} changed")


def _baseline_generation_fields(
    *,
    context: EvaluationContext,
    runner_sha256: str,
    cohort_manifest_sha256: str,
    calibration_generation_sha256: str,
    generated_items: Sequence[PrivateGeneratedItem],
) -> dict[str, object]:
    return {
        "schema": BASELINE_GENERATION_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "candidate_commit": context.gold.candidate_commit,
        "rag_policy": context.gold.candidate_rag_policy,
        "gold_set_sha256": context.gold.gold_set_sha256,
        "question_set_sha256": context.gold.question_set_sha256,
        "corpus_manifest_sha256": context.gold.corpus_manifest_sha256,
        "model_catalog_sha256": context.model_catalog_sha256,
        "runner_sha256": runner_sha256,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "calibration_generation_artifact_sha256": calibration_generation_sha256,
        "run_identity": dict(context.run_identity),
        "item_ids": [item.item_id for item in generated_items],
        "items": [item.model_dump(mode="json") for item in generated_items],
    }


def _validate_baseline_generation_artifact(
    path: Path,
    *,
    args: argparse.Namespace,
    context: EvaluationContext,
    runner_sha256: str,
    cohort_manifest: AnswerEvaluationCohortManifest,
    cohort_manifest_sha256: str,
    calibration_generation_sha256: str,
) -> tuple[tuple[PrivateGeneratedItem, ...], str]:
    payload = _load_json_object(path, label="baseline generation artifact")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise AnswerEvaluationError("baseline generation items are missing")
    generated = tuple(PrivateGeneratedItem.model_validate(item) for item in raw_items)
    expected_ids = tuple(
        _required_string(item, "id", label="gold item") for item in context.gold_items
    )
    if tuple(item.item_id for item in generated) != expected_ids or len(generated) != 37:
        raise AnswerEvaluationError("baseline generation must contain all 37 items in order")
    fields = _baseline_generation_fields(
        context=context,
        runner_sha256=runner_sha256,
        cohort_manifest_sha256=cohort_manifest_sha256,
        calibration_generation_sha256=calibration_generation_sha256,
        generated_items=generated,
    )
    _validate_sealed_artifact(
        payload,
        expected_without_hash=fields,
        label="baseline generation artifact",
    )
    cohort_by_id = {item.item_id: item for item in cohort_manifest.items}
    for gold_item, generated_item in zip(context.gold_items, generated, strict=True):
        item_id = _required_string(gold_item, "id", label="gold item")
        checkpoint_item = _load_generated_checkpoint(
            args.run_root / "items" / item_id / "generated.json",
            item=gold_item,
            cohort_manifest_sha256=cohort_manifest_sha256,
            cohort_item=cohort_by_id[item_id],
        )
        if checkpoint_item != generated_item:
            raise AnswerEvaluationError(
                f"generated checkpoint {item_id} differs from the baseline artifact"
            )
    return generated, sha256_file(path)


def _baseline_decomposition_fields(
    *,
    context: EvaluationContext,
    generation_artifact_sha256: str,
    cohort_manifest_sha256: str,
    records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "schema": BASELINE_DECOMPOSITION_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "generation_artifact_sha256": generation_artifact_sha256,
        "model_catalog_sha256": context.model_catalog_sha256,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "prompt_version": CLAIM_DECOMPOSITION_PROMPT_VERSION,
        "prompt_sha256": CLAIM_DECOMPOSITION_PROMPT_SHA256,
        "model": JUDGE_MODEL,
        "repetitions_per_item": 1,
        "item_ids": [str(record["item_id"]) for record in records],
        "items": [dict(record) for record in records],
    }


def _validate_baseline_decomposition_artifact(
    path: Path,
    *,
    context: EvaluationContext,
    generated_items: Sequence[PrivateGeneratedItem],
    generation_artifact_sha256: str,
    cohort_manifest_sha256: str,
) -> tuple[
    tuple[DecomposedPilotItem, ...],
    tuple[PrivateUsageEvent, ...],
    str,
]:
    payload = _load_json_object(path, label="baseline decomposition artifact")
    raw_records = payload.get("items")
    if not isinstance(raw_records, list) or len(raw_records) != 37:
        raise AnswerEvaluationError("baseline decomposition must contain exactly 37 records")
    records: list[dict[str, object]] = []
    decompositions: list[DecomposedPilotItem] = []
    usage_events: list[PrivateUsageEvent] = []
    for generated, raw_record in zip(generated_items, raw_records, strict=True):
        if not isinstance(raw_record, Mapping) or set(raw_record) != {
            "item_id",
            "answer_sha256",
            "checkpoint",
        }:
            raise AnswerEvaluationError("baseline decomposition record fields changed")
        if (
            raw_record.get("item_id") != generated.item_id
            or raw_record.get("answer_sha256") != generated.answer_sha256
        ):
            raise AnswerEvaluationError("baseline decomposition item binding changed")
        raw_checkpoint = raw_record.get("checkpoint")
        if not isinstance(raw_checkpoint, Mapping):
            raise AnswerEvaluationError("baseline decomposition checkpoint is malformed")
        decomposition = _validate_decomposition_checkpoint_payload(
            raw_checkpoint,
            generated=generated,
            repetition=1,
            cohort_manifest_sha256=cohort_manifest_sha256,
        )
        checkpoint_path = path.parent / "items" / generated.item_id / "decomposition-1.json"
        if _load_json_object(
            checkpoint_path,
            label="baseline decomposition checkpoint",
        ) != dict(raw_checkpoint):
            raise AnswerEvaluationError(
                f"decomposition checkpoint {generated.item_id}/1 differs from baseline"
            )
        checkpoint = PrivateDecompositionCheckpoint.model_validate(raw_checkpoint)
        records.append(dict(raw_record))
        decompositions.append(decomposition)
        usage_events.append(checkpoint.usage_event)
    fields = _baseline_decomposition_fields(
        context=context,
        generation_artifact_sha256=generation_artifact_sha256,
        cohort_manifest_sha256=cohort_manifest_sha256,
        records=records,
    )
    _validate_sealed_artifact(
        payload,
        expected_without_hash=fields,
        label="baseline decomposition artifact",
    )
    return tuple(decompositions), tuple(usage_events), sha256_file(path)


def _instrument_lane_activity(instrument: InstrumentLock) -> tuple[bool, bool]:
    modes = {entry.dimension: entry.scoring_mode for entry in instrument.dimensions}
    evidence_active = any(
        modes[dimension] is ScoringMode.JUDGE
        for dimension in (
            ScoringDimension.FAITHFULNESS,
            ScoringDimension.CITED_SOURCE_SUPPORT,
        )
    )
    rubric_active = any(
        modes[dimension] is ScoringMode.JUDGE
        for dimension in (
            ScoringDimension.CLAIM_MAPPING,
            ScoringDimension.GOLD_STATUS,
            ScoringDimension.MUST_NOT_TRIPWIRES,
            ScoringDimension.RESPONSE_BEHAVIOR,
        )
    )
    return evidence_active, rubric_active


def _calibration_decomposition_usage_events(
    args: argparse.Namespace,
    *,
    generated_items: Sequence[PrivateGeneratedItem],
    cohort_manifest_sha256: str,
) -> tuple[PrivateUsageEvent, ...]:
    payload = _load_json_object(
        args.run_root / "calibration-decompositions.json",
        label="calibration decomposition artifact",
    )
    raw_records = payload.get("items")
    if not isinstance(raw_records, list) or len(raw_records) != 10:
        raise AnswerEvaluationError("calibration decomposition records changed")
    events: list[PrivateUsageEvent] = []
    for generated, record in zip(generated_items, raw_records, strict=True):
        if not isinstance(record, Mapping):
            raise AnswerEvaluationError("calibration decomposition record is malformed")
        repetitions = record.get("repetitions")
        if not isinstance(repetitions, list) or len(repetitions) != 3:
            raise AnswerEvaluationError("calibration decomposition repetitions changed")
        for repetition, raw_checkpoint in enumerate(repetitions, start=1):
            if not isinstance(raw_checkpoint, Mapping):
                raise AnswerEvaluationError("calibration decomposition checkpoint is malformed")
            _validate_decomposition_checkpoint_payload(
                raw_checkpoint,
                generated=generated,
                repetition=repetition,
                cohort_manifest_sha256=cohort_manifest_sha256,
            )
            events.append(PrivateDecompositionCheckpoint.model_validate(raw_checkpoint).usage_event)
    return tuple(events)


def _validate_or_write_baseline_semantic(
    path: Path,
    *,
    expected: BaselineSemanticAggregate,
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    gold_items: Sequence[Mapping[str, object]],
    instrument: InstrumentLock,
) -> BaselineSemanticAggregate:
    rubrics = tuple(
        build_item_rubric_input(question=generated.question, gold_item=gold_item)
        for generated, gold_item in zip(generated_items, gold_items, strict=True)
    )
    if path.is_file():
        actual = BaselineSemanticAggregate.model_validate(
            _load_json_object(path, label="baseline semantic aggregate")
        )
        validate_baseline_semantic_aggregate(
            actual,
            cohort_manifest_sha256=expected.cohort_manifest_sha256,
            generation_artifact_sha256=expected.generation_artifact_sha256,
            decomposition_artifact_sha256=expected.decomposition_artifact_sha256,
            item_ids=expected.item_ids,
            generated_items=generated_items,
            decompositions=decompositions,
            rubrics=rubrics,
            instrument_lock=instrument,
            evidence_prompt_version=CLAIM_EVIDENCE_PROMPT_VERSION,
            evidence_prompt_sha256=CLAIM_EVIDENCE_PROMPT_SHA256,
            rubric_prompt_version=ITEM_RUBRIC_PROMPT_VERSION,
            rubric_prompt_sha256=ITEM_RUBRIC_PROMPT_SHA256,
            judge_model=JUDGE_MODEL,
            judge_settings=_judge_settings_payload(),
        )
        if actual != expected:
            raise AnswerEvaluationError(
                "baseline semantic aggregate differs from its exact checkpoints"
            )
        return actual
    write_json_atomic_no_overwrite(path, expected)
    return expected


def _load_or_write_manual_template(
    path: Path,
    *,
    context: EvaluationContext,
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    generation_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    cohort_manifest_sha256: str,
    instrument: InstrumentLock,
    calibration_labels: CalibrationLabelFile,
) -> ManualScoringAggregate:
    label_template = build_calibration_label_template(
        generated_items=generated_items,
        decomposed_items=decompositions,
        gold_items=context.gold_items,
        pilot_artifact_sha256=generation_artifact_sha256,
        decomposition_artifact_sha256=decomposition_artifact_sha256,
    )
    calibration_by_id = {item.item_id: item for item in calibration_labels.items}
    labels = tuple(calibration_by_id.get(item.item_id, item) for item in label_template.items)
    rubrics = tuple(
        build_item_rubric_input(question=generated.question, gold_item=gold_item)
        for generated, gold_item in zip(generated_items, context.gold_items, strict=True)
    )
    expected = build_manual_scoring_aggregate(
        cohort_manifest_sha256=cohort_manifest_sha256,
        generation_artifact_sha256=generation_artifact_sha256,
        decomposition_artifact_sha256=decomposition_artifact_sha256,
        instrument_lock=instrument,
        generated_items=generated_items,
        decompositions=decompositions,
        rubrics=rubrics,
        items=labels,
    )
    if path.is_file():
        actual = ManualScoringAggregate.model_validate(
            _load_json_object(path, label="manual-scoring template")
        )
        if actual != expected:
            raise AnswerEvaluationError(
                "manual-scoring template differs from the exact baseline inputs"
            )
        return actual
    write_json_atomic_no_overwrite(path, expected)
    return expected


def _load_optional_manual_scoring(
    path: Path,
    *,
    context: EvaluationContext,
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    generation_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    cohort_manifest_sha256: str,
    instrument: InstrumentLock,
) -> ManualScoringAggregate | None:
    if not path.is_file():
        return None
    rubrics = tuple(
        build_item_rubric_input(question=generated.question, gold_item=gold_item)
        for generated, gold_item in zip(generated_items, context.gold_items, strict=True)
    )
    return validate_manual_scoring_aggregate(
        ManualScoringAggregate.model_validate(
            _load_json_object(path, label="manual-scoring aggregate")
        ),
        cohort_manifest_sha256=cohort_manifest_sha256,
        generation_artifact_sha256=generation_artifact_sha256,
        decomposition_artifact_sha256=decomposition_artifact_sha256,
        instrument_lock=instrument,
        generated_items=generated_items,
        decompositions=decompositions,
        rubrics=rubrics,
    )


def _load_or_write_private_full_run(
    path: Path,
    *,
    expected: PrivateFullRunArtifact,
    cohort_manifest_sha256: str,
    generation_artifact_sha256: str,
    decomposition_artifact_sha256: str,
    generated_items: Sequence[PrivateGeneratedItem],
    decompositions: Sequence[DecomposedPilotItem],
    semantic_aggregate: BaselineSemanticAggregate,
    instrument: InstrumentLock,
    calibration_semantic_aggregate: CalibrationSemanticAggregate,
    additional_usage_events: Sequence[PrivateUsageEvent],
    manual_scoring_aggregate: ManualScoringAggregate | None,
) -> PrivateFullRunArtifact:
    if path.is_file():
        actual = validate_private_full_run_artifact(
            PrivateFullRunArtifact.model_validate(
                _load_json_object(path, label="private full-run artifact")
            ),
            cohort_manifest_sha256=cohort_manifest_sha256,
            generation_artifact_sha256=generation_artifact_sha256,
            decomposition_artifact_sha256=decomposition_artifact_sha256,
            generated_items=generated_items,
            decompositions=decompositions,
            semantic_aggregate=semantic_aggregate,
            instrument_lock=instrument,
            calibration_semantic_aggregate=calibration_semantic_aggregate,
            additional_usage_events=additional_usage_events,
            manual_scoring_aggregate=manual_scoring_aggregate,
        )
        if actual != expected:
            raise AnswerEvaluationError(
                "private full-run artifact differs from its exact baseline inputs"
            )
        return actual
    write_json_atomic_no_overwrite(path, expected)
    return expected


def _baseline(args: argparse.Namespace, context: EvaluationContext) -> None:
    maximum = _require_paid_authorization(
        args,
        flag_name="authorize_openai_remaining_baseline",
    )
    args.run_root = _require_private_run_root(args.run_root)
    args.run_root.mkdir(parents=True, exist_ok=True)
    for name in ("baseline-generated.json", "baseline-decompositions.json"):
        if not (args.run_root / name).is_file():
            raise AnswerEvaluationError(
                "semantic baseline scoring cannot generate missing answers; "
                f"run-37 must first preserve {name}"
            )
    required_calibration = (
        "cohort-manifest.json",
        "calibration-generated.json",
        "calibration-decompositions.json",
        "calibration-semantic-results.json",
        "calibration-agreement-projection.json",
        "instrument-lock.json",
    )
    for name in required_calibration:
        if not (args.run_root / name).is_file():
            raise AnswerEvaluationError(f"baseline prerequisite is missing: {name}")

    (
        instrument,
        calibration_semantic,
        _projection,
        calibration_generation_sha,
        _calibration_decomposition_sha,
        cohort_manifest_sha,
        calibration_labels,
    ) = _load_locked_instrument(args, context)
    calibration_generated, calibration_decomposed, _, _ = _load_calibration_artifacts(
        args,
        context,
    )
    runner_sha256 = sha256_file(Path(__file__))
    cohort_manifest, checked_cohort_sha = _load_or_write_cohort_manifest(
        args.run_root / "cohort-manifest.json",
        context=context,
        runner_sha256=runner_sha256,
    )
    if checked_cohort_sha != cohort_manifest_sha:
        raise AnswerEvaluationError("baseline cohort manifest binding changed")
    cohort_by_id = {item.item_id: item for item in cohort_manifest.items}
    generation_path = args.run_root / "baseline-generated.json"
    decomposition_path = args.run_root / "baseline-decompositions.json"
    semantic_path = args.run_root / "baseline-semantic.json"
    if decomposition_path.is_file() and not generation_path.is_file():
        raise AnswerEvaluationError("baseline decomposition exists without its generation artifact")
    if semantic_path.is_file() and not decomposition_path.is_file():
        raise AnswerEvaluationError(
            "baseline semantic aggregate exists without its decomposition artifact"
        )

    usage_db = args.run_root / "remaining-baseline-usage.sqlite3"
    ledger: UsageLedger | None = None
    client: object | None = None

    def ensure_ledger() -> UsageLedger:
        nonlocal ledger
        if ledger is None:
            ledger = UsageLedger(usage_db)
            ledger.update_settings(
                monthly_budget_usd=maximum,
                warning_threshold_percent=100,
                hard_limit_enabled=True,
            )
            _require_cost_within_cap(ledger, maximum)
        return ledger

    def ensure_client() -> object:
        nonlocal client
        if client is None:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise AnswerEvaluationError("OPENAI_API_KEY is unavailable")
            ensure_ledger()
            client = _create_openai_client(api_key)
        return client

    print(
        "AUTHORIZED OPTIONAL SEMANTIC SCORING: all 37 generated answers and canonical "
        "decompositions are reused exactly. Only missing semantic checkpoints may call the "
        "scoring lanes marked JUDGE by the locked instrument; generation and decomposition "
        "are unavailable in this phase."
    )
    with _isolated_usage_db(usage_db):
        if generation_path.is_file():
            generated_items, generation_sha = _validate_baseline_generation_artifact(
                generation_path,
                args=args,
                context=context,
                runner_sha256=runner_sha256,
                cohort_manifest=cohort_manifest,
                cohort_manifest_sha256=cohort_manifest_sha,
                calibration_generation_sha256=calibration_generation_sha,
            )
        else:
            by_id = {item.item_id: item for item in calibration_generated}
            gold_by_id = {
                _required_string(item, "id", label="gold item"): item for item in context.gold_items
            }
            for item_id in context.remaining_ids:
                item = gold_by_id[item_id]
                checkpoint = args.run_root / "items" / item_id / "generated.json"
                if not checkpoint.is_file():
                    _require_cost_reserve(
                        ensure_ledger(),
                        maximum,
                        reserve_usd=GENERATION_ITEM_COST_RESERVE_USD,
                        label=f"generation item {item_id}",
                    )
                by_id[item_id] = _run_one_generated_item(
                    args=args,
                    context=context,
                    item=item,
                    client=object() if checkpoint.is_file() else ensure_client(),
                    usage_db=usage_db,
                    runner_sha256=runner_sha256,
                    cohort_manifest_sha256=cohort_manifest_sha,
                    cohort_item=cohort_by_id[item_id],
                )
                if ledger is not None:
                    _require_cost_within_cap(ledger, maximum)
            generated_items = tuple(
                by_id[_required_string(item, "id", label="gold item")]
                for item in context.gold_items
            )
            fields = _baseline_generation_fields(
                context=context,
                runner_sha256=runner_sha256,
                cohort_manifest_sha256=cohort_manifest_sha,
                calibration_generation_sha256=calibration_generation_sha,
                generated_items=generated_items,
            )
            write_json_atomic_no_overwrite(
                generation_path,
                _sealed_artifact(fields),
            )
            generation_sha = sha256_file(generation_path)

        if decomposition_path.is_file():
            decompositions, decomposition_events, decomposition_sha = (
                _validate_baseline_decomposition_artifact(
                    decomposition_path,
                    context=context,
                    generated_items=generated_items,
                    generation_artifact_sha256=generation_sha,
                    cohort_manifest_sha256=cohort_manifest_sha,
                )
            )
        else:
            calibration_by_id = {item.item_id: item for item in calibration_decomposed}
            records: list[dict[str, object]] = []
            decomposition_list: list[DecomposedPilotItem] = []
            decomposition_event_list: list[PrivateUsageEvent] = []
            for generated in generated_items:
                checkpoint_path = (
                    args.run_root / "items" / generated.item_id / "decomposition-1.json"
                )
                if generated.item_id in calibration_by_id:
                    checkpoint_payload = _load_json_object(
                        checkpoint_path,
                        label="calibration decomposition checkpoint",
                    )
                else:
                    if not checkpoint_path.is_file():
                        _require_cost_reserve(
                            ensure_ledger(),
                            maximum,
                            reserve_usd=DECOMPOSITION_CALL_COST_RESERVE_USD,
                            label=f"decomposition {generated.item_id}/1",
                        )
                    checkpoint_payload = _decomposition_checkpoint(
                        args=args,
                        generated=generated,
                        repetition=1,
                        client=(object() if checkpoint_path.is_file() else ensure_client()),
                        usage_db=usage_db,
                        cohort_manifest_sha256=cohort_manifest_sha,
                    )
                decomposition = _validate_decomposition_checkpoint_payload(
                    checkpoint_payload,
                    generated=generated,
                    repetition=1,
                    cohort_manifest_sha256=cohort_manifest_sha,
                )
                checkpoint = PrivateDecompositionCheckpoint.model_validate(checkpoint_payload)
                decomposition_list.append(decomposition)
                decomposition_event_list.append(checkpoint.usage_event)
                records.append(
                    {
                        "item_id": generated.item_id,
                        "answer_sha256": generated.answer_sha256,
                        "checkpoint": checkpoint_payload,
                    }
                )
                if ledger is not None:
                    _require_cost_within_cap(ledger, maximum)
            decompositions = tuple(decomposition_list)
            decomposition_events = tuple(decomposition_event_list)
            fields = _baseline_decomposition_fields(
                context=context,
                generation_artifact_sha256=generation_sha,
                cohort_manifest_sha256=cohort_manifest_sha,
                records=records,
            )
            write_json_atomic_no_overwrite(
                decomposition_path,
                _sealed_artifact(fields),
            )
            decomposition_sha = sha256_file(decomposition_path)

        evidence_active, rubric_active = _instrument_lane_activity(instrument)
        if semantic_path.is_file():
            _require_baseline_semantic_checkpoints(
                args.run_root,
                generated=generated_items,
                decomposed=decompositions,
                calibration_item_ids=context.calibration_ids,
                evidence_active=evidence_active,
                rubric_active=rubric_active,
            )
        calibration_semantic_by_id = {item.item_id: item for item in calibration_semantic.items}
        semantic_items: list[BaselineSemanticItem] = []
        for generated, decomposition, gold_item in zip(
            generated_items,
            decompositions,
            context.gold_items,
            strict=True,
        ):
            calibration_item = calibration_semantic_by_id.get(generated.item_id)
            if calibration_item is not None:
                semantic_items.append(
                    build_baseline_semantic_item_from_calibration(
                        calibration_item,
                        decomposition=decomposition,
                        instrument_lock=instrument,
                    )
                )
                continue
            evidence_results: tuple[ClaimEvidenceResult, ...] = ()
            if evidence_active:
                values: list[ClaimEvidenceResult] = []
                for claim in decomposition.claims:
                    checkpoint_path = (
                        args.run_root
                        / "items"
                        / generated.item_id
                        / f"claim-evidence-{claim.claim_id}-1.json"
                    )
                    values.append(
                        _claim_evidence_checkpoint(
                            args=args,
                            generated=generated,
                            decomposition=decomposition,
                            claim=claim,
                            call_ordinal=1,
                            client=(None if checkpoint_path.is_file() else ensure_client()),
                            ledger=(
                                ensure_ledger()
                                if not checkpoint_path.is_file()
                                else ledger or object()  # type: ignore[arg-type]
                            ),
                            maximum=maximum,
                            usage_db=usage_db,
                            cohort_manifest_sha256=cohort_manifest_sha,
                        )
                    )
                evidence_results = tuple(values)
            rubric_result: ItemRubricResult | None = None
            if rubric_active:
                rubric_checkpoint = args.run_root / "items" / generated.item_id / "item-rubric.json"
                rubric_result = _item_rubric_checkpoint(
                    args=args,
                    generated=generated,
                    decomposition=decomposition,
                    gold_item=gold_item,
                    client=(None if rubric_checkpoint.is_file() else ensure_client()),
                    ledger=(
                        ensure_ledger() if not rubric_checkpoint.is_file() else ledger or object()  # type: ignore[arg-type]
                    ),
                    maximum=maximum,
                    usage_db=usage_db,
                    cohort_manifest_sha256=cohort_manifest_sha,
                )
            semantic_items.append(
                build_baseline_semantic_item(
                    decomposition=decomposition,
                    instrument_lock=instrument,
                    first_call_claim_evidence=evidence_results,
                    item_rubric=rubric_result,
                )
            )
            if ledger is not None:
                _require_cost_within_cap(ledger, maximum)

        expected_semantic = build_baseline_semantic_aggregate(
            cohort_manifest_sha256=cohort_manifest_sha,
            generation_artifact_sha256=generation_sha,
            decomposition_artifact_sha256=decomposition_sha,
            instrument_lock=instrument,
            item_ids=tuple(item.item_id for item in generated_items),
            items=semantic_items,
        )
        semantic = _validate_or_write_baseline_semantic(
            semantic_path,
            expected=expected_semantic,
            generated_items=generated_items,
            decompositions=decompositions,
            gold_items=context.gold_items,
            instrument=instrument,
        )
        _load_or_write_manual_template(
            args.run_root / "manual-scoring.template.json",
            context=context,
            generated_items=generated_items,
            decompositions=decompositions,
            generation_artifact_sha256=generation_sha,
            decomposition_artifact_sha256=decomposition_sha,
            cohort_manifest_sha256=cohort_manifest_sha,
            instrument=instrument,
            calibration_labels=calibration_labels,
        )
        manual = _load_optional_manual_scoring(
            args.run_root / "manual-scoring.json",
            context=context,
            generated_items=generated_items,
            decompositions=decompositions,
            generation_artifact_sha256=generation_sha,
            decomposition_artifact_sha256=decomposition_sha,
            cohort_manifest_sha256=cohort_manifest_sha,
            instrument=instrument,
        )
        calibration_decomposition_events = _calibration_decomposition_usage_events(
            args,
            generated_items=calibration_generated,
            cohort_manifest_sha256=cohort_manifest_sha,
        )
        remaining_id_set = set(context.remaining_ids)
        remaining_decomposition_events = tuple(
            event
            for generated, event in zip(
                generated_items,
                decomposition_events,
                strict=True,
            )
            if generated.item_id in remaining_id_set
        )
        repeat_evidence_events = tuple(
            item.repeat_first_claim_evidence.usage_event
            for item in calibration_semantic.items
            if item.repeat_first_claim_evidence is not None
        )
        additional_usage = (
            *calibration_decomposition_events,
            *remaining_decomposition_events,
            *repeat_evidence_events,
        )
        base_full = build_private_full_run_artifact(
            cohort_manifest_sha256=cohort_manifest_sha,
            generation_artifact_sha256=generation_sha,
            decomposition_artifact_sha256=decomposition_sha,
            generated_items=generated_items,
            decompositions=decompositions,
            semantic_aggregate=semantic,
            instrument_lock=instrument,
            calibration_semantic_aggregate=calibration_semantic,
            additional_usage_events=additional_usage,
            manual_scoring_aggregate=None,
        )
        _load_or_write_private_full_run(
            args.run_root / "private-full-run.json",
            expected=base_full,
            cohort_manifest_sha256=cohort_manifest_sha,
            generation_artifact_sha256=generation_sha,
            decomposition_artifact_sha256=decomposition_sha,
            generated_items=generated_items,
            decompositions=decompositions,
            semantic_aggregate=semantic,
            instrument=instrument,
            calibration_semantic_aggregate=calibration_semantic,
            additional_usage_events=additional_usage,
            manual_scoring_aggregate=None,
        )
        if manual is not None:
            manual_full = build_private_full_run_artifact(
                cohort_manifest_sha256=cohort_manifest_sha,
                generation_artifact_sha256=generation_sha,
                decomposition_artifact_sha256=decomposition_sha,
                generated_items=generated_items,
                decompositions=decompositions,
                semantic_aggregate=semantic,
                instrument_lock=instrument,
                calibration_semantic_aggregate=calibration_semantic,
                additional_usage_events=additional_usage,
                manual_scoring_aggregate=manual,
            )
            _load_or_write_private_full_run(
                args.run_root / "private-full-run.manual.json",
                expected=manual_full,
                cohort_manifest_sha256=cohort_manifest_sha,
                generation_artifact_sha256=generation_sha,
                decomposition_artifact_sha256=decomposition_sha,
                generated_items=generated_items,
                decompositions=decompositions,
                semantic_aggregate=semantic,
                instrument=instrument,
                calibration_semantic_aggregate=calibration_semantic,
                additional_usage_events=additional_usage,
                manual_scoring_aggregate=manual,
            )
        if ledger is not None:
            _require_cost_within_cap(ledger, maximum)

    spent = 0.0 if ledger is None else _ledger_total_cost(ledger)
    print(f"Preserved all 37 generated answers: {generation_path}")
    print(f"Preserved all 37 canonical decompositions: {decomposition_path}")
    print(f"Preserved baseline semantic aggregate: {semantic_path}")
    print(f"Recorded remaining-baseline cost in its isolated ledger: ${spent:.6f}")
    print("NEXT ACTION: run the offline report command")


@dataclass(frozen=True, slots=True)
class _CompletedBaseline:
    cohort_manifest: AnswerEvaluationCohortManifest
    instrument: InstrumentLock
    calibration_semantic: CalibrationSemanticAggregate
    generated_items: tuple[PrivateGeneratedItem, ...]
    decompositions: tuple[DecomposedPilotItem, ...]
    semantic: BaselineSemanticAggregate
    additional_usage_events: tuple[PrivateUsageEvent, ...]
    manual: ManualScoringAggregate | None
    base_full: PrivateFullRunArtifact
    manual_full: PrivateFullRunArtifact | None


def _load_completed_baseline(
    args: argparse.Namespace,
    context: EvaluationContext,
) -> _CompletedBaseline:
    required = (
        "cohort-manifest.json",
        "calibration-generated.json",
        "calibration-decompositions.json",
        "calibration-semantic-results.json",
        "calibration-agreement-projection.json",
        "instrument-lock.json",
        "baseline-generated.json",
        "baseline-decompositions.json",
        "baseline-semantic.json",
        "private-full-run.json",
    )
    for name in required:
        if not (args.run_root / name).is_file():
            raise AnswerEvaluationError(f"completed baseline artifact is missing: {name}")
    (
        instrument,
        calibration_semantic,
        _projection,
        calibration_generation_sha,
        _calibration_decomposition_sha,
        cohort_manifest_sha,
        _calibration_labels,
    ) = _load_locked_instrument(args, context)
    calibration_generated, _, _, _ = _load_calibration_artifacts(args, context)
    runner_sha256 = sha256_file(Path(__file__))
    cohort_manifest = AnswerEvaluationCohortManifest.model_validate(
        _load_json_object(
            args.run_root / "cohort-manifest.json",
            label="answer-evaluation cohort manifest",
        )
    )
    validate_cohort_manifest(
        cohort_manifest,
        expected=_expected_cohort_manifest(context, runner_sha256=runner_sha256),
    )
    if sha256_file(args.run_root / "cohort-manifest.json") != cohort_manifest_sha:
        raise AnswerEvaluationError("completed baseline cohort manifest changed")
    generated_items, generation_sha = _validate_baseline_generation_artifact(
        args.run_root / "baseline-generated.json",
        args=args,
        context=context,
        runner_sha256=runner_sha256,
        cohort_manifest=cohort_manifest,
        cohort_manifest_sha256=cohort_manifest_sha,
        calibration_generation_sha256=calibration_generation_sha,
    )
    decompositions, decomposition_events, decomposition_sha = (
        _validate_baseline_decomposition_artifact(
            args.run_root / "baseline-decompositions.json",
            context=context,
            generated_items=generated_items,
            generation_artifact_sha256=generation_sha,
            cohort_manifest_sha256=cohort_manifest_sha,
        )
    )
    evidence_active, rubric_active = _instrument_lane_activity(instrument)
    calibration_semantic_by_id = {item.item_id: item for item in calibration_semantic.items}
    semantic_items: list[BaselineSemanticItem] = []
    for generated, decomposition, gold_item in zip(
        generated_items,
        decompositions,
        context.gold_items,
        strict=True,
    ):
        calibration_item = calibration_semantic_by_id.get(generated.item_id)
        if calibration_item is not None:
            semantic_items.append(
                build_baseline_semantic_item_from_calibration(
                    calibration_item,
                    decomposition=decomposition,
                    instrument_lock=instrument,
                )
            )
            continue
        evidence_results: list[ClaimEvidenceResult] = []
        if evidence_active:
            for claim in decomposition.claims:
                path = (
                    args.run_root
                    / "items"
                    / generated.item_id
                    / f"claim-evidence-{claim.claim_id}-1.json"
                )
                if not path.is_file():
                    raise AnswerEvaluationError(
                        f"completed baseline claim checkpoint is missing: {path.name}"
                    )
                evidence_results.append(
                    validate_claim_evidence_result(
                        ClaimEvidenceResult.model_validate(
                            _load_json_object(path, label="claim-evidence checkpoint")
                        ),
                        cohort_manifest_sha256=cohort_manifest_sha,
                        generated_item=generated,
                        decomposition=decomposition,
                        claim=claim,
                        call_ordinal=1,
                        prompt_version=CLAIM_EVIDENCE_PROMPT_VERSION,
                        prompt_sha256=CLAIM_EVIDENCE_PROMPT_SHA256,
                        judge_model=JUDGE_MODEL,
                        judge_settings=_judge_settings_payload(),
                    )
                )
        rubric_result: ItemRubricResult | None = None
        if rubric_active:
            path = args.run_root / "items" / generated.item_id / "item-rubric.json"
            if not path.is_file():
                raise AnswerEvaluationError(
                    f"completed baseline rubric checkpoint is missing: {generated.item_id}"
                )
            rubric = build_item_rubric_input(
                question=generated.question,
                gold_item=gold_item,
            )
            rubric_result = validate_item_rubric_result(
                ItemRubricResult.model_validate(
                    _load_json_object(path, label="item-rubric checkpoint")
                ),
                cohort_manifest_sha256=cohort_manifest_sha,
                generated_item=generated,
                decomposition=decomposition,
                rubric=rubric,
                prompt_version=ITEM_RUBRIC_PROMPT_VERSION,
                prompt_sha256=ITEM_RUBRIC_PROMPT_SHA256,
                judge_model=JUDGE_MODEL,
                judge_settings=_judge_settings_payload(),
            )
        semantic_items.append(
            build_baseline_semantic_item(
                decomposition=decomposition,
                instrument_lock=instrument,
                first_call_claim_evidence=evidence_results,
                item_rubric=rubric_result,
            )
        )
    expected_semantic = build_baseline_semantic_aggregate(
        cohort_manifest_sha256=cohort_manifest_sha,
        generation_artifact_sha256=generation_sha,
        decomposition_artifact_sha256=decomposition_sha,
        instrument_lock=instrument,
        item_ids=tuple(item.item_id for item in generated_items),
        items=semantic_items,
    )
    semantic = _validate_or_write_baseline_semantic(
        args.run_root / "baseline-semantic.json",
        expected=expected_semantic,
        generated_items=generated_items,
        decompositions=decompositions,
        gold_items=context.gold_items,
        instrument=instrument,
    )
    manual = _load_optional_manual_scoring(
        args.run_root / "manual-scoring.json",
        context=context,
        generated_items=generated_items,
        decompositions=decompositions,
        generation_artifact_sha256=generation_sha,
        decomposition_artifact_sha256=decomposition_sha,
        cohort_manifest_sha256=cohort_manifest_sha,
        instrument=instrument,
    )
    calibration_decomposition_events = _calibration_decomposition_usage_events(
        args,
        generated_items=calibration_generated,
        cohort_manifest_sha256=cohort_manifest_sha,
    )
    remaining_id_set = set(context.remaining_ids)
    remaining_decomposition_events = tuple(
        event
        for generated, event in zip(
            generated_items,
            decomposition_events,
            strict=True,
        )
        if generated.item_id in remaining_id_set
    )
    repeat_evidence_events = tuple(
        item.repeat_first_claim_evidence.usage_event
        for item in calibration_semantic.items
        if item.repeat_first_claim_evidence is not None
    )
    additional_usage = (
        *calibration_decomposition_events,
        *remaining_decomposition_events,
        *repeat_evidence_events,
    )
    base_full_expected = build_private_full_run_artifact(
        cohort_manifest_sha256=cohort_manifest_sha,
        generation_artifact_sha256=generation_sha,
        decomposition_artifact_sha256=decomposition_sha,
        generated_items=generated_items,
        decompositions=decompositions,
        semantic_aggregate=semantic,
        instrument_lock=instrument,
        calibration_semantic_aggregate=calibration_semantic,
        additional_usage_events=additional_usage,
        manual_scoring_aggregate=None,
    )
    base_full = _load_or_write_private_full_run(
        args.run_root / "private-full-run.json",
        expected=base_full_expected,
        cohort_manifest_sha256=cohort_manifest_sha,
        generation_artifact_sha256=generation_sha,
        decomposition_artifact_sha256=decomposition_sha,
        generated_items=generated_items,
        decompositions=decompositions,
        semantic_aggregate=semantic,
        instrument=instrument,
        calibration_semantic_aggregate=calibration_semantic,
        additional_usage_events=additional_usage,
        manual_scoring_aggregate=None,
    )
    manual_full: PrivateFullRunArtifact | None = None
    if manual is not None:
        manual_path = args.run_root / "private-full-run.manual.json"
        if not manual_path.is_file():
            raise AnswerEvaluationError(
                "manual scoring exists without private-full-run.manual.json; rerun baseline"
            )
        manual_expected = build_private_full_run_artifact(
            cohort_manifest_sha256=cohort_manifest_sha,
            generation_artifact_sha256=generation_sha,
            decomposition_artifact_sha256=decomposition_sha,
            generated_items=generated_items,
            decompositions=decompositions,
            semantic_aggregate=semantic,
            instrument_lock=instrument,
            calibration_semantic_aggregate=calibration_semantic,
            additional_usage_events=additional_usage,
            manual_scoring_aggregate=manual,
        )
        manual_full = _load_or_write_private_full_run(
            manual_path,
            expected=manual_expected,
            cohort_manifest_sha256=cohort_manifest_sha,
            generation_artifact_sha256=generation_sha,
            decomposition_artifact_sha256=decomposition_sha,
            generated_items=generated_items,
            decompositions=decompositions,
            semantic_aggregate=semantic,
            instrument=instrument,
            calibration_semantic_aggregate=calibration_semantic,
            additional_usage_events=additional_usage,
            manual_scoring_aggregate=manual,
        )
    elif (args.run_root / "private-full-run.manual.json").is_file():
        raise AnswerEvaluationError("manual full-run artifact exists without manual-scoring.json")
    return _CompletedBaseline(
        cohort_manifest=cohort_manifest,
        instrument=instrument,
        calibration_semantic=calibration_semantic,
        generated_items=generated_items,
        decompositions=decompositions,
        semantic=semantic,
        additional_usage_events=additional_usage,
        manual=manual,
        base_full=base_full,
        manual_full=manual_full,
    )


def _load_or_write_public_summary(
    path: Path,
    *,
    expected: PublicEvaluationSummary,
) -> str:
    if path.is_file():
        actual = validate_public_summary(_load_json_object(path, label="public evaluation summary"))
        if actual != expected:
            raise AnswerEvaluationError(
                "public summary differs from the exact private full-run inputs"
            )
        return sha256_file(path)
    write_json_atomic_no_overwrite(path, expected)
    return sha256_file(path)


def _public_report_markdown(
    summary: PublicEvaluationSummary,
    *,
    public_summary_sha256: str,
) -> str:
    validated = validate_public_summary(summary)
    return render_public_evaluation_markdown(
        validated,
        public_summary_json_sha256=public_summary_sha256,
    )


def _write_text_atomic_no_overwrite(path: Path, text_value: str) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text_value.encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise FileExistsError(f"Refusing to overwrite evaluation report: {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _load_or_write_public_report(path: Path, *, expected: str) -> None:
    if path.is_file():
        if path.read_text(encoding="utf-8") != expected:
            raise AnswerEvaluationError(
                "public Markdown report differs from its bound public summary"
            )
        return
    _write_text_atomic_no_overwrite(path, expected)


def _report(args: argparse.Namespace, context: EvaluationContext) -> None:
    args.run_root = _require_private_run_root(args.run_root)
    completed = _load_completed_baseline(args, context)

    def publish(
        *,
        suffix: str,
        full_run: PrivateFullRunArtifact,
        manual: ManualScoringAggregate | None,
    ) -> tuple[Path, Path]:
        summary = build_public_evaluation_summary(
            candidate_id=context.gold.candidate_rag_policy,
            cohort_manifest=completed.cohort_manifest,
            generated_items=completed.generated_items,
            decompositions=completed.decompositions,
            gold_items=context.gold_items,
            semantic_aggregate=completed.semantic,
            calibration_semantic_aggregate=completed.calibration_semantic,
            additional_usage_events=completed.additional_usage_events,
            private_full_run_artifact=full_run,
            instrument_lock=completed.instrument,
            manual_scoring_aggregate=manual,
        )
        summary_name = f"public-summary{suffix}.json"
        report_name = f"public-report{suffix}.md"
        summary_path = args.run_root / summary_name
        report_path = args.run_root / report_name
        summary_sha = _load_or_write_public_summary(summary_path, expected=summary)
        markdown = _public_report_markdown(
            summary,
            public_summary_sha256=summary_sha,
        )
        _load_or_write_public_report(report_path, expected=markdown)
        return summary_path, report_path

    base_summary, base_report = publish(
        suffix="",
        full_run=completed.base_full,
        manual=None,
    )
    print(f"Preserved text-free public summary: {base_summary}")
    print(f"Preserved text-free public report: {base_report}")
    if completed.manual is not None and completed.manual_full is not None:
        manual_summary, manual_report = publish(
            suffix=".manual",
            full_run=completed.manual_full,
            manual=completed.manual,
        )
        print(f"Preserved owner-scored public summary: {manual_summary}")
        print(f"Preserved owner-scored public report: {manual_report}")
    print("No OpenAI client was constructed; reporting was fully offline.")


def _not_yet_available(command: str) -> None:
    prerequisite = {
        "baseline": ("Complete run-37 first; optional semantic scoring cannot generate answers."),
        "report": "Complete and preserve all 37 answers before emitting the text-free report.",
    }[command]
    raise AnswerEvaluationError(prerequisite)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        context = _build_context(args, require_clean=args.command != "preflight")
        if args.command == "preflight":
            _print_preflight(context)
        elif args.command == "recover-interrupted":
            _recover_interrupted_run(args, context)
        elif args.command == "run-37":
            _run_37(args, context)
        elif args.command == "calibration-generate":
            _retired_calibration_generate()
        elif args.command == "validate-labels":
            _validate_labels(args, context)
        elif args.command == "calibration-judge":
            _calibration_judge(args, context)
        elif args.command == "lock-instrument":
            _lock_instrument(args, context)
        elif args.command == "baseline":
            _baseline(args, context)
        elif args.command == "report":
            _report(args, context)
        else:
            _not_yet_available(args.command)
    except Exception as exc:
        print(f"ANSWER EVALUATION FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
