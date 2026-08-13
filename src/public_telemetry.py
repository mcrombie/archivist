"""Text-free identity and observation contracts for the public service."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_RUNTIME_IDENTITY_SCHEMA = "archivist.public_runtime_identity/4"
PUBLIC_REQUEST_OBSERVATION_SCHEMA = "archivist.public_request_observation/1"
PUBLIC_EVIDENCE_RETRIEVAL_KIND = "hybrid_bm25_rrf"
PUBLIC_EMBEDDING_MODEL = "text-embedding-3-small"
PROCESS_EPOCH = uuid4().hex

_COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_SAFE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/_-]{0,127}$")


class PublicTelemetryIdentityError(ValueError):
    """Raised when a committed runtime identity fixture is unavailable or invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validated_deployment_commit(
    environment: Mapping[str, str] | None = None,
) -> str | None:
    """Return Render's deploy SHA, or a local/test override off Render only."""

    env = os.environ if environment is None else environment
    render_raw = str(env.get("RENDER_GIT_COMMIT") or "").strip()
    if render_raw:
        normalized_render = render_raw.casefold()
        return (
            normalized_render if _COMMIT_PATTERN.fullmatch(normalized_render) is not None else None
        )

    override_raw = str(env.get("ARCHIVIST_DEPLOY_COMMIT") or "").strip()
    if override_raw:
        normalized_override = override_raw.casefold()
        if _COMMIT_PATTERN.fullmatch(normalized_override) is not None:
            return normalized_override
    return None


def render_instance_id(environment: Mapping[str, str] | None = None) -> str | None:
    """Return Render's opaque instance identifier only when it is a safe token."""

    env = os.environ if environment is None else environment
    raw = str(env.get("RENDER_INSTANCE_ID") or "").strip()
    if not raw or _SAFE_TOKEN_PATTERN.fullmatch(raw) is None:
        return None
    return raw


def _required_mapping(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PublicTelemetryIdentityError(f"invalid identity fixture: {path.name}") from exc
    if not isinstance(payload, Mapping):
        raise PublicTelemetryIdentityError(f"invalid identity fixture: {path.name}")
    return payload


def public_runtime_identity(
    *,
    environment: Mapping[str, str] | None = None,
    corpus_manifest_path: Path | None = None,
    provenance_path: Path | None = None,
) -> dict[str, object]:
    """Build the closed public identity payload without loading private corpus text."""

    # Keep these imports local so the persistence layer can use this module's
    # data contract without creating a costs -> RAG -> costs import cycle.
    from costs import (
        PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD,
        PUBLIC_RAG_REQUEST_COST_CEILING_VERSION,
    )
    from authored_response import (
        AUTHORED_RESPONSE_POLICY_VERSION,
        AUTHORED_RESPONSE_SETTINGS,
    )

    manifest_path = corpus_manifest_path or BASE_DIR / "fixtures" / "corpus_manifest.json"
    gold_provenance_path = provenance_path or BASE_DIR / "fixtures" / "gold_set.provenance.json"
    try:
        manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PublicTelemetryIdentityError("corpus manifest identity is unavailable") from exc
    if _SHA256_PATTERN.fullmatch(manifest_sha256) is None:
        raise PublicTelemetryIdentityError("corpus manifest identity is invalid")

    provenance = _required_mapping(gold_provenance_path)
    candidate_commit = provenance.get("candidate_commit")
    candidate_policy = provenance.get("candidate_rag_policy")
    bound_manifest_sha256 = provenance.get("corpus_manifest_sha256")
    if (
        not isinstance(candidate_commit, str)
        or _COMMIT_PATTERN.fullmatch(candidate_commit) is None
        or not isinstance(candidate_policy, str)
        or _SAFE_TOKEN_PATTERN.fullmatch(candidate_policy) is None
        or bound_manifest_sha256 != manifest_sha256
    ):
        raise PublicTelemetryIdentityError("frozen candidate identity is invalid")

    return {
        "schema": PUBLIC_RUNTIME_IDENTITY_SCHEMA,
        "deployment_commit": validated_deployment_commit(environment),
        "process_epoch": PROCESS_EPOCH,
        "answer_policy_version": AUTHORED_RESPONSE_POLICY_VERSION,
        "evidence_retrieval_kind": PUBLIC_EVIDENCE_RETRIEVAL_KIND,
        "embedding_model": PUBLIC_EMBEDDING_MODEL,
        "generated_prose_model": AUTHORED_RESPONSE_SETTINGS.model,
        "corpus_manifest_sha256": manifest_sha256,
        "frozen_candidate_commit": candidate_commit,
        "frozen_candidate_rag_policy": candidate_policy,
        "public_rag_request_cost_ceiling_version": (PUBLIC_RAG_REQUEST_COST_CEILING_VERSION),
        "public_rag_request_cost_ceiling_nano_usd": (PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD),
    }


@dataclass(frozen=True, slots=True)
class PublicRequestObservation:
    """One terminal, text-free public request observation."""

    request_id: str
    recorded_at: str
    deployment_commit: str | None
    process_epoch: str
    render_instance_id: str | None
    route: str
    delivery: str
    conversation_id: str | None
    turn_id: str | None
    archivist_mode: str | None
    answer_strategy: str | None
    http_status: int
    duration_ms: float
    schema: str = PUBLIC_REQUEST_OBSERVATION_SCHEMA

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def new_public_request_observation(
    *,
    request_id: str,
    route: str,
    delivery: str,
    conversation_id: str | None,
    turn_id: str | None,
    archivist_mode: str | None,
    answer_strategy: str | None,
    http_status: int,
    duration_ms: float,
    environment: Mapping[str, str] | None = None,
) -> PublicRequestObservation:
    return PublicRequestObservation(
        request_id=request_id,
        recorded_at=utc_now(),
        deployment_commit=validated_deployment_commit(environment),
        process_epoch=PROCESS_EPOCH,
        render_instance_id=render_instance_id(environment),
        route=route,
        delivery=delivery,
        conversation_id=conversation_id,
        turn_id=turn_id,
        archivist_mode=archivist_mode,
        answer_strategy=answer_strategy,
        http_status=http_status,
        duration_ms=round(max(0.0, float(duration_ms)), 3),
    )


def observation_log_payload(observation: PublicRequestObservation) -> dict[str, object]:
    """Return the smaller structured log record; omit client-supplied scope IDs."""

    return {
        "schema": observation.schema,
        "request_id": observation.request_id,
        "deployment_commit": observation.deployment_commit,
        "process_epoch": observation.process_epoch,
        "route": observation.route,
        "delivery": observation.delivery,
        "archivist_mode": observation.archivist_mode,
        "answer_strategy": observation.answer_strategy,
        "http_status": observation.http_status,
        "duration_ms": observation.duration_ms,
    }


__all__ = [
    "PROCESS_EPOCH",
    "PUBLIC_EMBEDDING_MODEL",
    "PUBLIC_EVIDENCE_RETRIEVAL_KIND",
    "PUBLIC_REQUEST_OBSERVATION_SCHEMA",
    "PUBLIC_RUNTIME_IDENTITY_SCHEMA",
    "PublicRequestObservation",
    "PublicTelemetryIdentityError",
    "new_public_request_observation",
    "observation_log_payload",
    "public_runtime_identity",
    "render_instance_id",
    "validated_deployment_commit",
]
