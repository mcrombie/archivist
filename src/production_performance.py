"""Closed, text-free contracts for Archivist's production performance cohort.

This module deliberately does not import or extend the answer-quality evaluation
runner.  The production cohort is an operational measurement of the deployed
public request boundary, not a second score for the frozen V26 answers.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence
from uuid import uuid4

from costs import (
    PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD,
    PUBLIC_RAG_REQUEST_COST_CEILING_VERSION,
)
from authored_response import (
    AUTHORED_RESPONSE_POLICY_VERSION,
    AUTHORED_RESPONSE_SETTINGS,
)
from gold_set import validate_gold_set_file
from public_telemetry import PUBLIC_EMBEDDING_MODEL, PUBLIC_EVIDENCE_RETRIEVAL_KIND
from retrieval_benchmark import LockedGold, load_locked_gold


LEGACY_PROTOCOL_VERSION = "production-performance-v1"
PROTOCOL_VERSION = "production-performance-v2"
LEGACY_PREPARED_MANIFEST_SCHEMA = "archivist.production_performance_manifest/1"
APPLICATION_COMPILED_PREPARED_MANIFEST_SCHEMA = "archivist.production_performance_manifest/2"
PREPARED_MANIFEST_SCHEMA = "archivist.production_performance_manifest/3"
RUNTIME_SESSION_SCHEMA = "archivist.production_performance_session/1"
ATTEMPT_INTENT_SCHEMA = "archivist.production_performance_attempt_intent/1"
ATTEMPT_OUTCOME_SCHEMA = "archivist.production_performance_attempt_outcome/1"
PRIVATE_SUMMARY_SCHEMA = "archivist.production_performance_private_summary/1"
PUBLIC_SUMMARY_SCHEMA = "archivist.production_performance_public_summary/1"
LEGACY_PUBLIC_RUNTIME_IDENTITY_SCHEMA = "archivist.public_runtime_identity/2"
APPLICATION_COMPILED_PUBLIC_RUNTIME_IDENTITY_SCHEMA = "archivist.public_runtime_identity/3"
PUBLIC_RUNTIME_IDENTITY_SCHEMA = "archivist.public_runtime_identity/4"
PUBLIC_REQUEST_OBSERVATION_SCHEMA = "archivist.public_request_observation/1"

PLANNED_ATTEMPT_COUNT = 33
MINIMUM_START_INTERVAL_SECONDS = 12.0
MAX_NEXT_ATTEMPT_COST_USD = PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD / 1_000_000_000
PROVIDERLESS_MAX_NEXT_ATTEMPT_COST_NANO_USD = 0
PROVIDERLESS_MAX_NEXT_ATTEMPT_COST_USD = 0.0
PUBLIC_QUESTION_PATH = "/api/projects/current/question"
PUBLIC_HEALTH_PATH = "/api/health"
PUBLIC_VERSION_PATH = "/api/version"
REQUEST_TIMEOUT_SECONDS = 240.0
# New preparations bind the current product policy. Previously written v2
# manifests retain their own sealed expected identity and are never rewritten.
PRODUCTION_COHORT_ANSWER_POLICY_VERSION = AUTHORED_RESPONSE_POLICY_VERSION

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_PROCESS_EPOCH_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
_HELD_OUT_ID_PATTERN = re.compile(r"^H[0-9]{3}$")
_PUBLIC_FORBIDDEN_ID_PATTERN = re.compile(r"\bH[0-9]{3}\b")


class ProductionPerformanceError(ValueError):
    """Raised when the operational cohort would cease to be closed or reproducible."""


@dataclass(frozen=True, slots=True)
class SelectedItem:
    ordinal: int
    item_id: str
    question: str
    question_sha256: str
    conversation_id: str
    turn_id: str

    def private_binding(self) -> dict[str, object]:
        """Return the text-free binding persisted by ``prepare``."""

        return {
            "ordinal": self.ordinal,
            "item_id": self.item_id,
            "question_sha256": self.question_sha256,
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def sha256_value(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sealed_artifact(value: Mapping[str, object]) -> dict[str, object]:
    payload = dict(value)
    payload.pop("artifact_sha256", None)
    payload["artifact_sha256"] = sha256_value(payload)
    return payload


def validate_sealed_artifact(
    value: object,
    *,
    schema: str,
    label: str,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ProductionPerformanceError(f"{label} must be a JSON object")
    payload = dict(value)
    if payload.get("schema") != schema:
        raise ProductionPerformanceError(f"{label} uses an unsupported schema")
    observed_hash = payload.pop("artifact_sha256", None)
    if observed_hash != sha256_value(payload):
        raise ProductionPerformanceError(f"{label} hash does not bind its exact contents")
    payload["artifact_sha256"] = observed_hash
    return payload


def manifest_is_providerless_essential(manifest: Mapping[str, object]) -> bool:
    """Identify the v2 Essential contract without reinterpreting sealed v1 runs."""

    if manifest.get("schema") != APPLICATION_COMPILED_PREPARED_MANIFEST_SCHEMA:
        return False
    cost_contract = manifest.get("cost_contract")
    return (
        isinstance(cost_contract, Mapping)
        and cost_contract.get("answer_provider_contract")
        == "providerless_essential_zero_calls"
        and cost_contract.get("expected_provider_event_count_per_attempt") == 0
        and cost_contract.get("max_next_attempt_cost_usd") == 0
        and cost_contract.get("max_next_attempt_cost_nano_usd") == 0
    )


def manifest_is_query_embedding_essential(manifest: Mapping[str, object]) -> bool:
    """Identify the v3 Essential contract's one retrieval-provider operation."""

    if manifest.get("schema") != PREPARED_MANIFEST_SCHEMA:
        return False
    cost_contract = manifest.get("cost_contract")
    return (
        isinstance(cost_contract, Mapping)
        and cost_contract.get("answer_provider_contract")
        == "essential_query_embedding_only"
        and cost_contract.get("expected_provider_operations_per_attempt")
        == ["query_embedding"]
        and cost_contract.get("expected_provider_event_count_per_attempt") == 1
        and cost_contract.get("max_next_attempt_cost_usd") == MAX_NEXT_ATTEMPT_COST_USD
        and cost_contract.get("max_next_attempt_cost_nano_usd")
        == PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD
    )


def protocol_version_for_manifest(manifest: Mapping[str, object]) -> str:
    """Return the protocol bound to one manifest schema without rewriting history."""

    schema = manifest.get("schema")
    if schema == PREPARED_MANIFEST_SCHEMA:
        expected = PROTOCOL_VERSION
    elif schema in {
        LEGACY_PREPARED_MANIFEST_SCHEMA,
        APPLICATION_COMPILED_PREPARED_MANIFEST_SCHEMA,
    }:
        expected = LEGACY_PROTOCOL_VERSION
    else:
        raise ProductionPerformanceError("prepared manifest uses an unsupported schema")
    if manifest.get("protocol_version") != expected:
        raise ProductionPerformanceError("prepared manifest protocol does not match its schema")
    return expected


def project_usage_totals_for_manifest(
    value: Mapping[str, object],
    *,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    """Project current ledger totals into the manifest's sealed usage shape.

    Operation-level counts were introduced with manifest schema 3. Historical
    schema-1 and schema-2 outcomes remain byte-for-byte v1 artifacts, so replay
    compares the current ledger only after removing that later field.
    """

    protocol_version_for_manifest(manifest)
    projected = dict(value)
    if manifest.get("schema") != PREPARED_MANIFEST_SCHEMA:
        projected.pop("operation_event_counts", None)
    return projected


def read_json(path: Path, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionPerformanceError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ProductionPerformanceError(f"{label} must be a JSON object")
    return value


def write_json_no_overwrite(path: Path, value: Mapping[str, object]) -> None:
    """Create one checkpoint without permitting an earlier attempt to be replaced."""

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
    except FileExistsError as exc:
        raise ProductionPerformanceError(f"refusing to overwrite checkpoint: {path}") from exc


def write_json_atomic(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _git_output(repository_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise ProductionPerformanceError("could not establish the local Git identity")
    return result.stdout.strip()


def clean_wrapper_commit(repository_root: Path) -> str:
    commit = _git_output(repository_root, "rev-parse", "HEAD").casefold()
    if _COMMIT_PATTERN.fullmatch(commit) is None:
        raise ProductionPerformanceError("wrapper commit is not a full lowercase Git SHA")
    if _git_output(repository_root, "status", "--porcelain"):
        raise ProductionPerformanceError(
            "prepare requires a clean working tree so the runner is reproducible"
        )
    return commit


def load_closed_items(
    *,
    gold_path: Path,
    provenance_path: Path,
    corpus_manifest_path: Path,
    run_id: str,
    scope_nonce: str | None = None,
) -> tuple[LockedGold, tuple[SelectedItem, ...]]:
    """Validate and select the exact 33 answerable held-out items in file order."""

    validate_gold_set_file(gold_path, corpus_manifest_path, mode="run-of-record")
    locked = load_locked_gold(gold_path, provenance_path)
    if sha256_file(corpus_manifest_path) != locked.corpus_manifest_sha256:
        raise ProductionPerformanceError("corpus manifest differs from the frozen gold binding")
    if not _SAFE_ID_PATTERN.fullmatch(run_id):
        raise ProductionPerformanceError("run ID is not a safe identifier")
    selected_scope_nonce = scope_nonce or uuid4().hex
    if _PROCESS_EPOCH_PATTERN.fullmatch(selected_scope_nonce) is None:
        raise ProductionPerformanceError("production scope nonce is invalid")

    selected: list[SelectedItem] = []
    for raw in locked.items:
        if raw.get("expected_behavior") != "answer":
            continue
        item_id = raw.get("id")
        question = raw.get("question")
        if not isinstance(item_id, str) or _HELD_OUT_ID_PATTERN.fullmatch(item_id) is None:
            raise ProductionPerformanceError("selected gold item has an invalid held-out ID")
        if not isinstance(question, str) or not question.strip():
            raise ProductionPerformanceError(f"{item_id} has no usable question")
        ordinal = len(selected) + 1
        selected.append(
            SelectedItem(
                ordinal=ordinal,
                item_id=item_id,
                question=question,
                question_sha256=hashlib.sha256(question.encode("utf-8")).hexdigest(),
                conversation_id=f"prodperf-{selected_scope_nonce}-{ordinal:02d}",
                turn_id="first-turn",
            )
        )

    if len(selected) != PLANNED_ATTEMPT_COUNT:
        raise ProductionPerformanceError(
            f"production cohort requires exactly {PLANNED_ATTEMPT_COUNT} answerable items; "
            f"found {len(selected)}"
        )
    if len({item.item_id for item in selected}) != PLANNED_ATTEMPT_COUNT:
        raise ProductionPerformanceError("production cohort contains duplicate held-out IDs")
    return locked, tuple(selected)


def build_prepared_manifest(
    *,
    repository_root: Path,
    run_id: str,
    base_url: str,
    gold_path: Path,
    provenance_path: Path,
    corpus_manifest_path: Path,
) -> tuple[dict[str, object], tuple[SelectedItem, ...]]:
    scope_nonce = uuid4().hex
    locked, items = load_closed_items(
        gold_path=gold_path,
        provenance_path=provenance_path,
        corpus_manifest_path=corpus_manifest_path,
        run_id=run_id,
        scope_nonce=scope_nonce,
    )
    if not base_url.startswith("https://") or base_url.rstrip("/") != base_url:
        raise ProductionPerformanceError("base URL must be an HTTPS origin with no trailing slash")
    wrapper_commit = clean_wrapper_commit(repository_root)
    manifest = sealed_artifact(
        {
            "schema": PREPARED_MANIFEST_SCHEMA,
            "protocol_version": PROTOCOL_VERSION,
            "prepared_at": utc_now(),
            "run_id": run_id,
            "scope_nonce": scope_nonce,
            "base_url": base_url,
            "question_path": PUBLIC_QUESTION_PATH,
            "health_path": PUBLIC_HEALTH_PATH,
            "version_path": PUBLIC_VERSION_PATH,
            "wrapper_commit": wrapper_commit,
            "frozen_candidate_commit": locked.candidate_commit,
            "frozen_candidate_rag_policy": locked.candidate_rag_policy,
            "gold_set_version": locked.raw.get("version"),
            "gold_set_sha256": locked.gold_set_sha256,
            "question_set_sha256": locked.question_set_sha256,
            "corpus_manifest_sha256": locked.corpus_manifest_sha256,
            "planned_attempt_count": PLANNED_ATTEMPT_COUNT,
            "item_bindings": [item.private_binding() for item in items],
            "request_contract": {
                "delivery": "complete",
                "answer_strategy": "rag",
                "archivist_mode": "essential",
                "historiographical_lens": "evidence_first",
                "voice": "scholarly",
                "worldview": "none",
                "history": [],
                "first_turn": True,
                "sequential": True,
                "automatic_retries": 0,
                "replacement_attempts": 0,
                "minimum_start_interval_seconds": MINIMUM_START_INTERVAL_SECONDS,
                "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            },
            "warm_contract": {
                "paid_warmup_calls": 0,
                "required_ready_health_checks": 2,
                "required_version_checks": 1,
                "single_process_epoch": True,
                "cold_starts": "excluded_not_measured",
            },
            "latency_contract": {
                "primary": "public_server_request_duration_ms",
                "secondary": "operator_client_round_trip_ms",
                "p50": "median",
                "p95": "nearest_rank",
                "success_definition": (
                    "valid_2xx_complete_public_response_with_zero_instrumentation_failures"
                ),
                "no_outlier_trimming": True,
            },
            "cost_contract": {
                "answer_provider_contract": "essential_query_embedding_only",
                "expected_provider_operations_per_attempt": ["query_embedding"],
                "expected_provider_event_count_per_attempt": 1,
                "public_rag_request_cost_ceiling_version": (
                    PUBLIC_RAG_REQUEST_COST_CEILING_VERSION
                ),
                "public_rag_request_cost_ceiling_nano_usd": (
                    PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD
                ),
                "max_next_attempt_cost_usd": MAX_NEXT_ATTEMPT_COST_USD,
                "max_next_attempt_cost_nano_usd": (
                    PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD
                ),
                "ceiling_enforcement": (
                    "server_reserves_the_full_request_ceiling_before_RAG_and_projects_"
                    "every_provider_operation_before_send"
                ),
                "unpriced_events_allowed": False,
                "scope": "exact_request_ids_in_this_cohort",
            },
            "answer_policy_version_expected": PRODUCTION_COHORT_ANSWER_POLICY_VERSION,
            "evidence_retrieval_kind_expected": PUBLIC_EVIDENCE_RETRIEVAL_KIND,
            "embedding_model_expected": PUBLIC_EMBEDDING_MODEL,
            "generated_prose_model_expected": AUTHORED_RESPONSE_SETTINGS.model,
            "evaluation_relationship": (
                "separate operational cohort; no answer-quality scoring and no mutation of "
                "the frozen V26 evaluation"
            ),
        }
    )
    return manifest, items


def load_prepared_manifest(path: Path) -> dict[str, object]:
    value = read_json(path, label="prepared manifest")
    schema = value.get("schema")
    if schema not in {
        LEGACY_PREPARED_MANIFEST_SCHEMA,
        APPLICATION_COMPILED_PREPARED_MANIFEST_SCHEMA,
        PREPARED_MANIFEST_SCHEMA,
    }:
        raise ProductionPerformanceError("prepared manifest uses an unsupported schema")
    manifest = validate_sealed_artifact(value, schema=str(schema), label="prepared manifest")
    protocol_version_for_manifest(manifest)
    return manifest


def selected_items_from_manifest(
    manifest: Mapping[str, object],
    *,
    gold_path: Path,
    provenance_path: Path,
    corpus_manifest_path: Path,
) -> tuple[SelectedItem, ...]:
    run_id = manifest.get("run_id")
    scope_nonce = manifest.get("scope_nonce")
    if not isinstance(run_id, str):
        raise ProductionPerformanceError("prepared manifest has no run ID")
    if not isinstance(scope_nonce, str):
        raise ProductionPerformanceError("prepared manifest has no scope nonce")
    locked, items = load_closed_items(
        gold_path=gold_path,
        provenance_path=provenance_path,
        corpus_manifest_path=corpus_manifest_path,
        run_id=run_id,
        scope_nonce=scope_nonce,
    )
    expected_bindings = [item.private_binding() for item in items]
    if manifest.get("item_bindings") != expected_bindings:
        raise ProductionPerformanceError("prepared item bindings changed")
    for key, expected in (
        ("gold_set_sha256", locked.gold_set_sha256),
        ("question_set_sha256", locked.question_set_sha256),
        ("corpus_manifest_sha256", locked.corpus_manifest_sha256),
        ("frozen_candidate_commit", locked.candidate_commit),
        ("frozen_candidate_rag_policy", locked.candidate_rag_policy),
    ):
        if manifest.get(key) != expected:
            raise ProductionPerformanceError(f"prepared {key} changed")
    return items


def request_payload(item: SelectedItem) -> dict[str, object]:
    return {
        "question": item.question,
        "archivist_mode": "essential",
        "historiographical_lens": "evidence_first",
        "voice": "scholarly",
        "worldview": "none",
        "history": [],
        "conversation_id": item.conversation_id,
        "turn_id": item.turn_id,
        "answer_strategy": "rag",
    }


def build_attempt_intent(
    *,
    manifest: Mapping[str, object],
    item: SelectedItem,
    started_at: str | None = None,
) -> dict[str, object]:
    payload = request_payload(item)
    return sealed_artifact(
        {
            "schema": ATTEMPT_INTENT_SCHEMA,
            "protocol_version": protocol_version_for_manifest(manifest),
            "run_id": manifest["run_id"],
            "manifest_sha256": manifest["artifact_sha256"],
            "ordinal": item.ordinal,
            "item_id": item.item_id,
            "question_sha256": item.question_sha256,
            "conversation_id": item.conversation_id,
            "turn_id": item.turn_id,
            "request_payload_sha256": sha256_value(payload),
            "started_at": started_at or utc_now(),
            "automatic_retry_allowed": False,
        }
    )


def validate_runtime_identity(
    identity: object,
    *,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(identity, Mapping):
        raise ProductionPerformanceError("/api/version did not return a JSON object")
    value = dict(identity)
    providerless = manifest_is_providerless_essential(manifest)
    query_embedding = manifest_is_query_embedding_essential(manifest)
    if manifest.get("schema") == PREPARED_MANIFEST_SCHEMA and not query_embedding:
        raise ProductionPerformanceError("prepared v3 provider contract is invalid")
    if (
        manifest.get("schema") == APPLICATION_COMPILED_PREPARED_MANIFEST_SCHEMA
        and not providerless
    ):
        raise ProductionPerformanceError("prepared v2 provider contract is invalid")
    if query_embedding:
        required = {
            "schema",
            "deployment_commit",
            "process_epoch",
            "answer_policy_version",
            "evidence_retrieval_kind",
            "embedding_model",
            "generated_prose_model",
            "corpus_manifest_sha256",
            "frozen_candidate_commit",
            "frozen_candidate_rag_policy",
            "public_rag_request_cost_ceiling_version",
            "public_rag_request_cost_ceiling_nano_usd",
        }
        expected_schema = PUBLIC_RUNTIME_IDENTITY_SCHEMA
    elif providerless:
        required = {
            "schema",
            "deployment_commit",
            "process_epoch",
            "answer_policy_version",
            "evidence_retrieval_kind",
            "generated_prose_model",
            "corpus_manifest_sha256",
            "frozen_candidate_commit",
            "frozen_candidate_rag_policy",
            "public_rag_request_cost_ceiling_version",
            "public_rag_request_cost_ceiling_nano_usd",
        }
        expected_schema = APPLICATION_COMPILED_PUBLIC_RUNTIME_IDENTITY_SCHEMA
    elif manifest.get("schema") == LEGACY_PREPARED_MANIFEST_SCHEMA:
        required = {
            "schema",
            "deployment_commit",
            "process_epoch",
            "rag_policy_version",
            "generator_model",
            "corpus_manifest_sha256",
            "frozen_candidate_commit",
            "frozen_candidate_rag_policy",
            "public_rag_request_cost_ceiling_version",
            "public_rag_request_cost_ceiling_nano_usd",
        }
        expected_schema = LEGACY_PUBLIC_RUNTIME_IDENTITY_SCHEMA
    else:
        raise ProductionPerformanceError("prepared manifest uses an unsupported schema")
    if set(value) != required or value.get("schema") != expected_schema:
        raise ProductionPerformanceError("/api/version uses an unsupported identity contract")
    deployment_commit = value.get("deployment_commit")
    process_epoch = value.get("process_epoch")
    if (
        not isinstance(deployment_commit, str)
        or _COMMIT_PATTERN.fullmatch(deployment_commit) is None
    ):
        raise ProductionPerformanceError("deployment commit is unavailable or invalid")
    if (
        not isinstance(process_epoch, str)
        or _PROCESS_EPOCH_PATTERN.fullmatch(process_epoch) is None
    ):
        raise ProductionPerformanceError("process epoch is unavailable or invalid")
    if query_embedding:
        policy_comparisons = (
            ("answer_policy_version", manifest.get("answer_policy_version_expected")),
            (
                "evidence_retrieval_kind",
                manifest.get("evidence_retrieval_kind_expected"),
            ),
            ("embedding_model", manifest.get("embedding_model_expected")),
            ("generated_prose_model", manifest.get("generated_prose_model_expected")),
        )
    elif providerless:
        policy_comparisons = (
            ("answer_policy_version", manifest.get("answer_policy_version_expected")),
            (
                "evidence_retrieval_kind",
                manifest.get("evidence_retrieval_kind_expected"),
            ),
            ("generated_prose_model", manifest.get("generated_prose_model_expected")),
        )
    else:
        policy_comparisons = (
            ("rag_policy_version", manifest.get("frozen_candidate_rag_policy")),
            ("generator_model", manifest.get("generator_model_expected")),
        )
    cost_contract = manifest.get("cost_contract")
    comparisons = (
        ("deployment_commit", manifest.get("wrapper_commit")),
        *policy_comparisons,
        ("corpus_manifest_sha256", manifest.get("corpus_manifest_sha256")),
        ("frozen_candidate_commit", manifest.get("frozen_candidate_commit")),
        ("frozen_candidate_rag_policy", manifest.get("frozen_candidate_rag_policy")),
        (
            "public_rag_request_cost_ceiling_version",
            cost_contract.get("public_rag_request_cost_ceiling_version")
            if isinstance(cost_contract, Mapping)
            else None,
        ),
        (
            "public_rag_request_cost_ceiling_nano_usd",
            cost_contract.get("public_rag_request_cost_ceiling_nano_usd")
            if isinstance(cost_contract, Mapping)
            else None,
        ),
    )
    for key, expected in comparisons:
        if value.get(key) != expected:
            raise ProductionPerformanceError(f"deployed {key} differs from the prepared run")
    return value


def build_runtime_session(
    *,
    manifest: Mapping[str, object],
    identity: Mapping[str, object],
    health_observations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if len(health_observations) != 2:
        raise ProductionPerformanceError("warm contract requires exactly two health checks")
    epoch = identity.get("process_epoch")
    commit = identity.get("deployment_commit")
    for observation in health_observations:
        if observation.get("status") != 200 or observation.get("body_status") != "ready":
            raise ProductionPerformanceError("health warm-up did not report ready")
        if observation.get("process_epoch") != epoch:
            raise ProductionPerformanceError("health checks crossed a process epoch")
        if observation.get("deployment_commit") != commit:
            raise ProductionPerformanceError("health checks crossed a deployment commit")
    return sealed_artifact(
        {
            "schema": RUNTIME_SESSION_SCHEMA,
            "protocol_version": protocol_version_for_manifest(manifest),
            "run_id": manifest["run_id"],
            "manifest_sha256": manifest["artifact_sha256"],
            "established_at": utc_now(),
            "deployment_commit": commit,
            "process_epoch": epoch,
            "runtime_identity": dict(identity),
            "runtime_identity_sha256": sha256_value(identity),
            "health_observations": [dict(value) for value in health_observations],
            "paid_warmup_calls": 0,
        }
    )


def parse_server_timing(value: str | None) -> float | None:
    """Return ``app;dur=`` milliseconds from the closed response header."""

    if not isinstance(value, str):
        return None
    matches: list[float] = []
    for metric in value.split(","):
        parts = [part.strip() for part in metric.split(";")]
        if not parts or parts[0].casefold() != "app":
            continue
        for parameter in parts[1:]:
            key, separator, raw = parameter.partition("=")
            if separator and key.strip().casefold() == "dur":
                try:
                    number = float(raw.strip().strip('"'))
                except ValueError:
                    return None
                if not math.isfinite(number) or number < 0:
                    return None
                matches.append(round(number, 3))
    return matches[0] if len(matches) == 1 else None


def response_contract_projection(
    *,
    http_status: int,
    payload: object,
) -> tuple[bool, str | None, str | None]:
    """Check public success without retaining generated prose or source payloads."""

    if not 200 <= http_status < 300:
        error_code = None
        if isinstance(payload, Mapping):
            detail = payload.get("detail")
            if isinstance(detail, Mapping) and isinstance(detail.get("code"), str):
                error_code = str(detail["code"])
        return False, error_code or "http_error", None
    if not isinstance(payload, Mapping):
        return False, "invalid_json_contract", None
    if not isinstance(payload.get("answer"), str) or not str(payload["answer"]).strip():
        return False, "missing_public_answer", None
    if payload.get("answer_strategy") != "rag" or payload.get("archivist_mode") != "essential":
        return False, "public_mode_contract_changed", None
    if "run_diagnostics" in payload or "costs" in payload:
        return False, "private_diagnostics_exposed", None
    status = payload.get("answer_status")
    if not isinstance(status, str) or not status:
        return False, "missing_answer_status", None
    return True, None, status


def build_attempt_outcome(
    *,
    manifest: Mapping[str, object],
    intent: Mapping[str, object],
    request_id: str,
    http_status: int,
    response_contract_valid: bool,
    response_error_code: str | None,
    answer_status: str | None,
    response_payload_sha256: str | None,
    client_duration_ms: float | None,
    header_duration_ms: float | None,
    header_commit: str | None,
    header_process_epoch: str | None,
    observation: Mapping[str, object],
    diagnostics: Mapping[str, object] | None,
    usage_totals: Mapping[str, object],
    recovered_without_replay: bool = False,
) -> dict[str, object]:
    protocol_version = protocol_version_for_manifest(manifest)
    if intent.get("protocol_version") != protocol_version:
        raise ProductionPerformanceError("attempt intent protocol differs from its manifest")
    persisted_usage_totals = project_usage_totals_for_manifest(
        usage_totals,
        manifest=manifest,
    )
    instrumentation_failures: list[str] = []
    session_epoch = observation.get("process_epoch")
    session_commit = observation.get("deployment_commit")
    if observation.get("request_id") != request_id:
        instrumentation_failures.append("request_id_observation_mismatch")
    if observation.get("http_status") != http_status:
        instrumentation_failures.append("http_status_observation_mismatch")
    if header_duration_ms is None:
        instrumentation_failures.append("missing_server_timing_header")
    elif observation.get("duration_ms") != header_duration_ms:
        instrumentation_failures.append("server_timing_mismatch")
    if header_commit != session_commit:
        instrumentation_failures.append("deployment_commit_header_mismatch")
    if header_process_epoch != session_epoch:
        instrumentation_failures.append("process_epoch_header_mismatch")
    if diagnostics is None:
        instrumentation_failures.append("missing_answer_run_diagnostics")
    event_count = usage_totals.get("event_count")
    unpriced_count = usage_totals.get("unpriced_event_count")
    estimated_cost = usage_totals.get("estimated_cost_usd")
    total_tokens = usage_totals.get("total_tokens")
    operation_event_counts = usage_totals.get("operation_event_counts")
    usage_totals_valid = not (
        not isinstance(event_count, int)
        or isinstance(event_count, bool)
        or event_count < 0
        or not isinstance(unpriced_count, int)
        or isinstance(unpriced_count, bool)
        or unpriced_count < 0
        or not isinstance(total_tokens, int)
        or isinstance(total_tokens, bool)
        or total_tokens < 0
        or not isinstance(estimated_cost, (int, float))
        or isinstance(estimated_cost, bool)
        or not math.isfinite(float(estimated_cost))
        or float(estimated_cost) < 0
    )
    if not usage_totals_valid:
        instrumentation_failures.append("invalid_usage_totals")
    if unpriced_count:
        instrumentation_failures.append("unpriced_usage_event")
    if response_contract_valid and not manifest_is_providerless_essential(manifest):
        if manifest_is_query_embedding_essential(manifest):
            if event_count != 1:
                instrumentation_failures.append("unexpected_provider_event_count")
            if operation_event_counts != {"query_embedding": 1}:
                instrumentation_failures.append("unexpected_provider_operation")
        elif event_count == 0:
            instrumentation_failures.append("zero_usage_events")
    if usage_totals_valid and manifest_is_providerless_essential(manifest) and (
        event_count != 0 or total_tokens != 0 or float(estimated_cost) != 0
    ):
        instrumentation_failures.append("unexpected_provider_usage")
    if recovered_without_replay:
        instrumentation_failures.append("client_completion_unobserved")

    return sealed_artifact(
        {
            "schema": ATTEMPT_OUTCOME_SCHEMA,
            "protocol_version": protocol_version,
            "run_id": manifest["run_id"],
            "manifest_sha256": manifest["artifact_sha256"],
            "intent_sha256": intent["artifact_sha256"],
            "ordinal": intent["ordinal"],
            "item_id": intent["item_id"],
            "question_sha256": intent["question_sha256"],
            "conversation_id": intent["conversation_id"],
            "turn_id": intent["turn_id"],
            "request_id": request_id,
            "http_status": http_status,
            "response_contract_valid": response_contract_valid,
            "response_error_code": response_error_code,
            "answer_status": answer_status,
            "response_payload_sha256": response_payload_sha256,
            "client_duration_ms": client_duration_ms,
            "public_server_duration_ms": observation.get("duration_ms"),
            "server_timing_header_ms": header_duration_ms,
            "deployment_commit": session_commit,
            "process_epoch": session_epoch,
            "observation": dict(observation),
            "diagnostics": dict(diagnostics) if diagnostics is not None else None,
            "usage_totals": persisted_usage_totals,
            "usage_measurement_status": "recorded",
            "instrumentation_failures": sorted(set(instrumentation_failures)),
            "recovered_without_replay": recovered_without_replay,
            "automatic_retry_count": 0,
            "completed_at": utc_now(),
        }
    )


def build_ambiguous_transport_outcome(
    *,
    manifest: Mapping[str, object],
    session: Mapping[str, object],
    intent: Mapping[str, object],
    failure_code: str,
    client_duration_ms: float | None,
) -> dict[str, object]:
    """Seal one no-replay attempt whose terminal server state is unobservable.

    No zero-cost assertion is made: both usage and token totals remain explicitly
    unavailable.  Authorization accounting must reserve the application-owned
    maximum request projection for this attempt before any later POST may run.
    """

    allowed = {
        "client_connect_error",
        "client_protocol_error",
        "client_timeout",
        "client_transport_error",
        "missing_request_correlation",
        "missing_server_observation",
        "stale_scope_observation",
    }
    if failure_code not in allowed:
        raise ProductionPerformanceError("ambiguous transport failure code is not allowlisted")
    protocol_version = protocol_version_for_manifest(manifest)
    if intent.get("protocol_version") != protocol_version:
        raise ProductionPerformanceError("attempt intent protocol differs from its manifest")
    return sealed_artifact(
        {
            "schema": ATTEMPT_OUTCOME_SCHEMA,
            "protocol_version": protocol_version,
            "run_id": manifest["run_id"],
            "manifest_sha256": manifest["artifact_sha256"],
            "intent_sha256": intent["artifact_sha256"],
            "ordinal": intent["ordinal"],
            "item_id": intent["item_id"],
            "question_sha256": intent["question_sha256"],
            "conversation_id": intent["conversation_id"],
            "turn_id": intent["turn_id"],
            "request_id": None,
            "http_status": None,
            "response_contract_valid": False,
            "response_error_code": failure_code,
            "answer_status": None,
            "response_payload_sha256": None,
            "client_duration_ms": client_duration_ms,
            "public_server_duration_ms": None,
            "server_timing_header_ms": None,
            "deployment_commit": session["deployment_commit"],
            "process_epoch": session["process_epoch"],
            "observation": None,
            "diagnostics": None,
            "usage_totals": None,
            "usage_measurement_status": "unavailable_ambiguous_transport",
            "instrumentation_failures": [
                "client_transport_outcome_unknown",
                "missing_answer_run_diagnostics",
                "missing_server_observation",
                "missing_usage_totals",
            ],
            "recovered_without_replay": False,
            "automatic_retry_count": 0,
            "completed_at": utc_now(),
        }
    )


def normalize_usage_totals(value: object) -> dict[str, object]:
    """Project the ledger's request-scoped totals into the cohort contract."""

    if not isinstance(value, Mapping):
        raise ProductionPerformanceError("request usage totals are unavailable")
    unpriced = value.get("unpriced_event_count", value.get("unpriced_count"))
    projected = {
        "estimated_cost_usd": value.get("estimated_cost_usd"),
        "input_tokens": value.get("input_tokens"),
        "cached_tokens": value.get("cached_tokens"),
        "cache_write_tokens": value.get("cache_write_tokens"),
        "output_tokens": value.get("output_tokens"),
        "reasoning_tokens": value.get("reasoning_tokens"),
        "total_tokens": value.get("total_tokens"),
        "event_count": value.get("event_count"),
        "unpriced_event_count": unpriced,
        "operation_event_counts": value.get("operation_event_counts"),
    }
    integer_fields = {
        "input_tokens",
        "cached_tokens",
        "cache_write_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
        "event_count",
        "unpriced_event_count",
    }
    for key in integer_fields:
        raw = projected[key]
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            raise ProductionPerformanceError(f"request usage total {key} is invalid")
    cost = projected["estimated_cost_usd"]
    if (
        not isinstance(cost, (int, float))
        or isinstance(cost, bool)
        or not math.isfinite(float(cost))
        or float(cost) < 0
    ):
        raise ProductionPerformanceError("request usage cost is invalid")
    projected["estimated_cost_usd"] = round(float(cost), 9)
    operation_event_counts = projected["operation_event_counts"]
    if not isinstance(operation_event_counts, Mapping):
        raise ProductionPerformanceError("request usage operation counts are unavailable")
    normalized_operation_counts: dict[str, int] = {}
    for operation, count in operation_event_counts.items():
        if (
            not isinstance(operation, str)
            or not operation
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 1
        ):
            raise ProductionPerformanceError("request usage operation count is invalid")
        normalized_operation_counts[operation] = count
    if sum(normalized_operation_counts.values()) != projected["event_count"]:
        raise ProductionPerformanceError("request usage operation counts do not close")
    projected["operation_event_counts"] = dict(sorted(normalized_operation_counts.items()))
    return projected


def median(values: Sequence[float]) -> float:
    if not values:
        raise ProductionPerformanceError("median requires at least one observation")
    ordered = sorted(float(value) for value in values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def nearest_rank(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ProductionPerformanceError("percentile requires at least one observation")
    if not 0 < percentile <= 1:
        raise ProductionPerformanceError("nearest-rank percentile must be in (0, 1]")
    ordered = sorted(float(value) for value in values)
    rank = math.ceil(percentile * len(ordered))
    return ordered[rank - 1]


def _latency_summary(values_ms: Sequence[float]) -> dict[str, object] | None:
    if not values_ms:
        return None
    values = [float(value) for value in values_ms]
    return {
        "observation_count": len(values),
        "p50_seconds": round(median(values) / 1000, 3),
        "p95_seconds": round(nearest_rank(values, 0.95) / 1000, 3),
    }


def aggregate_summaries(
    *,
    manifest: Mapping[str, object],
    session: Mapping[str, object],
    authorization: Mapping[str, object],
    outcomes: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    protocol_version = protocol_version_for_manifest(manifest)
    if session.get("protocol_version") != protocol_version:
        raise ProductionPerformanceError("runtime session protocol differs from its manifest")
    if len(outcomes) != PLANNED_ATTEMPT_COUNT:
        raise ProductionPerformanceError(
            f"report requires exactly {PLANNED_ATTEMPT_COUNT} terminal outcomes"
        )
    ordered = sorted(outcomes, key=lambda value: int(value["ordinal"]))
    if any(value.get("protocol_version") != protocol_version for value in ordered):
        raise ProductionPerformanceError("attempt outcome protocol differs from its manifest")
    expected_ordinals = list(range(1, PLANNED_ATTEMPT_COUNT + 1))
    if [value.get("ordinal") for value in ordered] != expected_ordinals:
        raise ProductionPerformanceError("terminal outcomes do not cover each planned ordinal")
    if any(value.get("process_epoch") != session.get("process_epoch") for value in ordered):
        raise ProductionPerformanceError("cohort crossed the warmed process epoch")
    if any(value.get("deployment_commit") != session.get("deployment_commit") for value in ordered):
        raise ProductionPerformanceError("cohort crossed the deployed commit")

    successful = [value for value in ordered if value.get("response_contract_valid") is True]
    failures = len(ordered) - len(successful)
    instrumentation = [value for value in ordered if bool(value.get("instrumentation_failures"))]
    latency_eligible = [
        value
        for value in successful
        if not value.get("instrumentation_failures") and not value.get("recovered_without_replay")
    ]
    timed_server = [
        float(value["public_server_duration_ms"])
        for value in latency_eligible
        if isinstance(value.get("public_server_duration_ms"), (int, float))
        and not isinstance(value.get("public_server_duration_ms"), bool)
    ]
    timed_client = [
        float(value["client_duration_ms"])
        for value in latency_eligible
        if isinstance(value.get("client_duration_ms"), (int, float))
        and not isinstance(value.get("client_duration_ms"), bool)
    ]
    total_cost = 0.0
    total_tokens = 0
    priced_events = 0
    unpriced_events = 0
    unavailable_usage_attempts = 0
    for value in ordered:
        usage = value.get("usage_totals")
        measurement_status = value.get("usage_measurement_status")
        if measurement_status == "unavailable_ambiguous_transport":
            if usage is not None or value.get("request_id") is not None:
                raise ProductionPerformanceError(
                    "ambiguous outcome makes an unsupported zero-usage assertion"
                )
            unavailable_usage_attempts += 1
            continue
        if measurement_status != "recorded":
            raise ProductionPerformanceError("outcome usage measurement status is invalid")
        if not isinstance(usage, Mapping):
            raise ProductionPerformanceError("outcome has no usage totals")
        cost = usage.get("estimated_cost_usd")
        tokens = usage.get("total_tokens")
        events = usage.get("event_count")
        unpriced = usage.get("unpriced_event_count")
        if not isinstance(cost, (int, float)) or isinstance(cost, bool):
            raise ProductionPerformanceError("outcome cost is invalid")
        if not all(
            isinstance(item, int) and not isinstance(item, bool)
            for item in (tokens, events, unpriced)
        ):
            raise ProductionPerformanceError("outcome usage counts are invalid")
        total_cost += float(cost)
        total_tokens += int(tokens)
        priced_events += int(events) - int(unpriced)
        unpriced_events += int(unpriced)

    maximum = authorization.get("max_cost_usd")
    maximum_next = authorization.get("max_next_attempt_cost_usd")
    maximum_next_nano = authorization.get("max_next_attempt_cost_nano_usd")
    ceiling_version = authorization.get("request_cost_ceiling_version")
    ceiling_enforcement = authorization.get("cost_ceiling_enforcement")
    cost_contract = manifest.get("cost_contract")
    if not isinstance(cost_contract, Mapping):
        raise ProductionPerformanceError("prepared cost contract is unavailable")
    providerless = manifest_is_providerless_essential(manifest)
    expected_next = cost_contract.get("max_next_attempt_cost_usd")
    expected_next_nano = cost_contract.get(
        "max_next_attempt_cost_nano_usd",
        cost_contract.get("public_rag_request_cost_ceiling_nano_usd"),
    )
    expected_ceiling_version = cost_contract.get("public_rag_request_cost_ceiling_version")
    expected_enforcement = cost_contract.get("ceiling_enforcement")
    if (
        not isinstance(maximum, (int, float))
        or isinstance(maximum, bool)
        or not math.isfinite(float(maximum))
        or (float(maximum) != 0 if providerless else float(maximum) <= 0)
        or not isinstance(maximum_next, (int, float))
        or isinstance(maximum_next, bool)
        or not math.isfinite(float(maximum_next))
        or (float(maximum_next) != 0 if providerless else float(maximum_next) <= 0)
        or not isinstance(maximum_next_nano, int)
        or isinstance(maximum_next_nano, bool)
        or maximum_next_nano != round(float(maximum_next) * 1_000_000_000)
        or maximum_next != expected_next
        or maximum_next_nano != expected_next_nano
        or not isinstance(ceiling_version, str)
        or not ceiling_version
        or ceiling_version != expected_ceiling_version
        or not isinstance(ceiling_enforcement, str)
        or not ceiling_enforcement
        or ceiling_enforcement != expected_enforcement
    ):
        raise ProductionPerformanceError("authorization cost contract is invalid")
    if providerless and (total_cost != 0 or total_tokens != 0 or priced_events != 0):
        raise ProductionPerformanceError("providerless Essential recorded provider usage")
    authorization_accounted_cost = total_cost + (unavailable_usage_attempts * float(maximum_next))
    if authorization_accounted_cost > float(maximum) + 1e-12:
        raise ProductionPerformanceError(
            "conservative cohort cost accounting exceeds authorization"
        )
    if unpriced_events:
        raise ProductionPerformanceError("unpriced usage prevents a completed report")

    outcome_hashes = [str(value["artifact_sha256"]) for value in ordered]
    completed_at_values = [
        str(value.get("completed_at"))
        for value in ordered
        if isinstance(value.get("completed_at"), str)
    ]
    if len(completed_at_values) != PLANNED_ATTEMPT_COUNT:
        raise ProductionPerformanceError("terminal outcomes are missing completion timestamps")
    common = {
        "protocol_version": protocol_version,
        "run_id": manifest["run_id"],
        "manifest_sha256": manifest["artifact_sha256"],
        "authorization_sha256": authorization.get("artifact_sha256"),
        "wrapper_commit": manifest["wrapper_commit"],
        "deployment_commit": session["deployment_commit"],
        "frozen_candidate_commit": manifest["frozen_candidate_commit"],
        "frozen_candidate_rag_policy": manifest["frozen_candidate_rag_policy"],
        "corpus_manifest_sha256": manifest["corpus_manifest_sha256"],
        "gold_set_sha256": manifest["gold_set_sha256"],
        "question_set_sha256": manifest["question_set_sha256"],
        "runtime_identity_sha256": session["runtime_identity_sha256"],
        "process_epoch": session["process_epoch"],
        "planned_attempt_count": PLANNED_ATTEMPT_COUNT,
        "attempted_count": len(ordered),
        "successful_completion_count": len(successful),
        "failure_count": failures,
        "failure_rate": round(failures / PLANNED_ATTEMPT_COUNT, 6),
        "instrumentation_failure_count": len(instrumentation),
        "latency_eligible_completion_count": len(latency_eligible),
        "server_latency": _latency_summary(timed_server),
        "operator_client_latency": _latency_summary(timed_client),
        "latency_boundary": "Complete public endpoint middleware duration",
        "cold_start_handling": "Two ready health checks; cold starts excluded and not measured",
        "minimum_start_interval_seconds": MINIMUM_START_INTERVAL_SECONDS,
        "authorization": {
            "max_cost_usd": round(float(maximum), 9),
            "max_next_attempt_cost_usd": round(float(maximum_next), 9),
            "max_next_attempt_cost_nano_usd": maximum_next_nano,
            "request_cost_ceiling_version": ceiling_version,
            "cost_ceiling_enforcement": ceiling_enforcement,
        },
        "cost": {
            "estimated_cost_usd": (
                round(total_cost, 9) if unavailable_usage_attempts == 0 else None
            ),
            "recorded_estimated_cost_usd": round(total_cost, 9),
            "authorization_accounted_cost_usd": round(authorization_accounted_cost, 9),
            "recorded_total_tokens": total_tokens,
            "priced_event_count": priced_events,
            "unpriced_event_count": unpriced_events,
            "unavailable_usage_attempt_count": unavailable_usage_attempts,
            "usage_measurement_complete": unavailable_usage_attempts == 0,
        },
        "outcome_set_sha256": sha256_value(outcome_hashes),
        "automatic_retries": 0,
        "replacement_attempts": 0,
        "generated_at": max(completed_at_values),
    }
    private = sealed_artifact(
        {
            "schema": PRIVATE_SUMMARY_SCHEMA,
            **common,
            "item_outcomes": [
                {
                    "ordinal": value["ordinal"],
                    "item_id": value["item_id"],
                    "question_sha256": value["question_sha256"],
                    "request_id": value["request_id"],
                    "outcome_sha256": value["artifact_sha256"],
                }
                for value in ordered
            ],
        }
    )
    public_common = dict(common)
    public_common.pop("run_id", None)
    public_common.pop("process_epoch", None)
    public = sealed_artifact(
        {
            "schema": PUBLIC_SUMMARY_SCHEMA,
            **public_common,
        }
    )
    assert_public_safe(public, forbidden_item_ids=[str(value["item_id"]) for value in ordered])
    return private, public


def assert_public_safe(
    value: Mapping[str, object] | str,
    *,
    forbidden_item_ids: Sequence[str] = (),
) -> None:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    if _PUBLIC_FORBIDDEN_ID_PATTERN.search(text):
        raise ProductionPerformanceError("public artifact contains a held-out item ID")
    if any(item_id and item_id in text for item_id in forbidden_item_ids):
        raise ProductionPerformanceError("public artifact contains a private item binding")


def public_report_markdown(summary: Mapping[str, object]) -> str:
    assert_public_safe(summary)
    server = summary.get("server_latency")
    client = summary.get("operator_client_latency")
    cost = summary.get("cost")
    if server is not None and not isinstance(server, Mapping):
        raise ProductionPerformanceError("public summary has an invalid server latency aggregate")
    if client is not None and not isinstance(client, Mapping):
        raise ProductionPerformanceError("public summary has an invalid client latency aggregate")
    if not isinstance(cost, Mapping):
        raise ProductionPerformanceError("public summary lacks completed usage measurements")
    server_lines = (
        [
            f"- Server observations: {server['observation_count']}",
            f"- Server p50: {float(server['p50_seconds']):.3f} seconds",
            f"- Server p95 (nearest rank): {float(server['p95_seconds']):.3f} seconds",
        ]
        if isinstance(server, Mapping)
        else ["- Server p50/p95: unavailable (zero latency-eligible completions)"]
    )
    client_lines = (
        [
            f"- Operator-client observations: {client['observation_count']}",
            f"- Operator-client p50: {float(client['p50_seconds']):.3f} seconds",
            f"- Operator-client p95 (nearest rank): {float(client['p95_seconds']):.3f} seconds",
        ]
        if isinstance(client, Mapping)
        else ["- Operator-client p50/p95: unavailable (zero latency-eligible completions)"]
    )
    lines = [
        "# Archivist production performance cohort",
        "",
        "This is a text-free operational measurement of the deployed Complete-answer boundary. "
        "It is separate from the frozen answer-quality evaluation and does not score response content.",
        "",
        "## Cohort",
        "",
        f"- Planned and attempted requests: {summary['planned_attempt_count']}",
        f"- Successful public completions: {summary['successful_completion_count']}",
        f"- Failures: {summary['failure_count']} ({float(summary['failure_rate']) * 100:.2f}%)",
        f"- Instrumentation failures (reported separately): {summary['instrumentation_failure_count']}",
        f"- Latency-eligible completions: {summary['latency_eligible_completion_count']}",
        "- Delivery/configuration: Complete, Essential, RAG, empty history, first turn",
        "- Execution: sequential, no retries or replacement requests, at least 12 seconds between starts",
        "- Warm boundary: two ready health checks on one process epoch; cold starts were excluded and not measured",
        "",
        "## Latency",
        "",
        *server_lines,
        *client_lines,
        "",
        "## Usage",
        "",
        (
            f"- Estimated API cost: ${float(cost['estimated_cost_usd']):.6f}"
            if cost["estimated_cost_usd"] is not None
            else "- Estimated API cost: unavailable because one or more transport outcomes "
            "lack request-scoped usage observations"
        ),
        f"- Recorded API-cost lower bound: ${float(cost['recorded_estimated_cost_usd']):.6f}",
        "- Conservative authorization accounting (recorded cost plus the enforced maximum "
        f"for each unknown attempt): ${float(cost['authorization_accounted_cost_usd']):.6f}",
        f"- Recorded tokens: {cost['recorded_total_tokens']}",
        f"- Priced events: {cost['priced_event_count']}",
        f"- Unpriced events: {cost['unpriced_event_count']}",
        f"- Attempts with unavailable usage: {cost['unavailable_usage_attempt_count']}",
        f"- Owner-authorized cohort ceiling: ${float(summary['authorization']['max_cost_usd']):.2f}",
        "- Enforced maximum accounted per next/unknown attempt: "
        f"${float(summary['authorization']['max_next_attempt_cost_usd']):.6f}",
        "- Request-cost ceiling contract: "
        f"`{summary['authorization']['request_cost_ceiling_version']}`",
        "",
        "## Identity",
        "",
        f"- Deployed wrapper commit: `{summary['deployment_commit']}`",
        f"- Frozen candidate commit: `{summary['frozen_candidate_commit']}`",
        f"- Frozen RAG policy: `{summary['frozen_candidate_rag_policy']}`",
        f"- Corpus manifest SHA-256: `{summary['corpus_manifest_sha256']}`",
        f"- Gold-set SHA-256: `{summary['gold_set_sha256']}`",
        "",
    ]
    report = "\n".join(lines)
    assert_public_safe(report)
    return report


__all__ = [
    "ATTEMPT_INTENT_SCHEMA",
    "ATTEMPT_OUTCOME_SCHEMA",
    "APPLICATION_COMPILED_PREPARED_MANIFEST_SCHEMA",
    "APPLICATION_COMPILED_PUBLIC_RUNTIME_IDENTITY_SCHEMA",
    "LEGACY_PROTOCOL_VERSION",
    "LEGACY_PREPARED_MANIFEST_SCHEMA",
    "LEGACY_PUBLIC_RUNTIME_IDENTITY_SCHEMA",
    "MINIMUM_START_INTERVAL_SECONDS",
    "MAX_NEXT_ATTEMPT_COST_USD",
    "PLANNED_ATTEMPT_COUNT",
    "PREPARED_MANIFEST_SCHEMA",
    "PRIVATE_SUMMARY_SCHEMA",
    "PROTOCOL_VERSION",
    "PUBLIC_HEALTH_PATH",
    "PUBLIC_QUESTION_PATH",
    "PUBLIC_SUMMARY_SCHEMA",
    "PUBLIC_VERSION_PATH",
    "ProductionPerformanceError",
    "RUNTIME_SESSION_SCHEMA",
    "REQUEST_TIMEOUT_SECONDS",
    "SelectedItem",
    "aggregate_summaries",
    "assert_public_safe",
    "build_attempt_intent",
    "build_attempt_outcome",
    "build_ambiguous_transport_outcome",
    "build_prepared_manifest",
    "build_runtime_session",
    "canonical_json_bytes",
    "load_prepared_manifest",
    "manifest_is_providerless_essential",
    "manifest_is_query_embedding_essential",
    "median",
    "nearest_rank",
    "normalize_usage_totals",
    "parse_server_timing",
    "project_usage_totals_for_manifest",
    "protocol_version_for_manifest",
    "public_report_markdown",
    "read_json",
    "request_payload",
    "response_contract_projection",
    "sealed_artifact",
    "selected_items_from_manifest",
    "sha256_value",
    "utc_now",
    "validate_runtime_identity",
    "validate_sealed_artifact",
    "write_json_atomic",
    "write_json_no_overwrite",
]
