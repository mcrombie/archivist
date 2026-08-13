"""Clean-cohort evaluator for the post-timeout retrieval-authored-v4 product.

The v3 evaluator and its private timeout-diagnostic run are immutable.  This
module owns a separate run root and request scope.  It reuses v3's validated
cached-vector retrieval adapter and current product authoring path, while
providing a predeclared, data-driven recovery protocol for provider attempts
whose usage cannot be observed.

Importing this module performs no filesystem or provider operation.  Live
operations require an injected client and an exact, freshly authorized cap.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import subprocess
import re
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
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
    AUTHORED_RESPONSE_SETTINGS,
    MAX_AUTHORED_RESPONSE_OUTPUT_TOKENS,
    AuthoredResponse,
    authored_response_prompt_metadata,
    build_authored_response_input,
    build_authored_response_instructions,
)
from character_conversation import (
    CHARACTER_CONVERSATION_INPUT_SCHEMA,
    CHARACTER_CONVERSATION_OUTPUT_SCHEMA,
    CHARACTER_CONVERSATION_SETTINGS,
    MAX_CHARACTER_CONVERSATION_OUTPUT_TOKENS,
    CharacterConversationFailureCode,
    CharacterConversationResponse,
    CharacterConversationStatus,
    build_character_conversation_input,
    build_character_conversation_instructions,
    deterministic_character_conversation_fallback,
    generate_character_conversation,
    is_character_conversation_question,
)
from corpus import get_all_chunks
from costs import (
    PROVIDER_REQUEST_TOKEN_OVERHEAD_UPPER_BOUND,
    UsageLedger,
    _request_json_value,
    projected_provider_operation_cost_nano_usd,
    usage_scope,
)
from evaluation_artifacts import build_corpus_identity, build_git_worktree_identity
from evidence_dossier import build_retrieval_dossier
from gold_provenance import normalized_question_sha256
from query_planning import ResolvedTurn
from rag_pipeline import preflight_answer_corpus
from retrieval_authored_v3_evaluation import (
    EXPECTED_CACHE_SHA256,
    EXPECTED_CHUNKS_SHA256,
    EXPECTED_COMMITMENT_SHA256,
    EXPECTED_GOLD_SHA256,
    EXPECTED_ITEM_COUNT,
    EXPECTED_MANIFEST_SHA256,
    EXPECTED_PROVENANCE_SHA256,
    EXPECTED_QUESTION_SET_SHA256,
    PreparedV3Cohort,
    ProviderCapturingClient,
    _index_identity,
    generate_professional_item,
    preflight_all_cached_items,
    retrieve_with_cached_embedding,
)
from retrieval_benchmark import load_locked_gold, sha256_file, validate_embedding_cache
from retrieval_trace_contract import validate_text_free_retrieval_trace
from web_project import (
    AUTHORED_AUTHORING_TIMEOUT_SECONDS,
    AUTHORED_EMBEDDING_TIMEOUT_SECONDS,
    AUTHORED_TOTAL_PROVIDER_DEADLINE_SECONDS,
)
from persona_evaluation import PERSONA_SIGNATURES


V4_EVALUATION_SCHEMA = "archivist.retrieval_authored_v4_evaluation/1"
V4_COHORT_MANIFEST_SCHEMA = "archivist.retrieval_authored_v4_cohort_manifest/1"
V4_INTENT_SCHEMA = "archivist.retrieval_authored_v4_attempt_intent/1"
V4_ATTEMPT_STARTED_SCHEMA = "archivist.retrieval_authored_v4_attempt_started/1"
V4_RESERVATION_SCHEMA = "archivist.retrieval_authored_v4_ambiguity_reservation/1"
V4_GENERATION_OUTCOME_SCHEMA = "archivist.retrieval_authored_v4_generation_outcome/1"
V4_DECOMPOSITION_OUTCOME_SCHEMA = "archivist.retrieval_authored_v4_decomposition_outcome/1"
V4_SOCIAL_OUTCOME_SCHEMA = "archivist.retrieval_authored_v4_social_outcome/1"
V4_RUBRIC_OUTCOME_SCHEMA = "archivist.retrieval_authored_v4_rubric_outcome/1"
V4_PUBLIC_REPORT_SCHEMA = "archivist.retrieval_authored_v4_public_report/1"
V4_TRACE_SCOPE_CONTINUATION_SCHEMA = (
    "archivist.retrieval_authored_v4_trace_scope_continuation/1"
)

EVALUATION_ID = "retrieval-authored-v4-professional-2026-08-13"
COHORT_CLASSIFICATION = "reused_locked_benchmark_not_pristine_held_out"
MASTER_PROJECT_ID = "archivist-v4-evaluation"
MASTER_CONVERSATION_ID = EVALUATION_ID
MASTER_REQUEST_ID = f"{EVALUATION_ID}-master"
MAXIMUM_DESIGN_CAP_USD = Decimal("7.00")
NANO_USD_PER_USD = Decimal(1_000_000_000)
DECOMPOSITION_TIMEOUT_SECONDS = 60.0
SOCIAL_TIMEOUT_SECONDS = 12.0

# These are the first ten items in the same once-only 37-item sequence.  They
# are not a disposable pilot and are never called again by the full command.
SENTINEL_ITEM_IDS = tuple(f"H{ordinal:03d}" for ordinal in range(1, 11))
LOCKED_ITEM_IDS = tuple(
    [f"H{ordinal:03d}" for ordinal in range(1, 20)]
    + [f"H{ordinal:03d}" for ordinal in range(21, 39)]
)
SOCIAL_MODES = (
    ArchivistMode.PROFESSIONAL,
    ArchivistMode.PRETTY_PINK_PRINCESS,
    ArchivistMode.BALEFUL_BLACK_BARON,
    ArchivistMode.EMBER_AND_INK,
)
SOCIAL_QUESTIONS = (
    "How are you?",
    "What is your life like?",
    "What do you enjoy?",
)
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?", re.IGNORECASE)

FAILURE_CATEGORIES = frozenset(
    {
        "timeout",
        "transport",
        "provider_exception",
        "provider_refusal",
        "structured_output_rejection",
        "local_validation_failure",
        "usage_contract_failure",
        "unknown_provider_failure",
    }
)


def _expected_turn_operations() -> dict[str, str]:
    expected = {
        f"generation:{item_id}": "answer_generation" for item_id in LOCKED_ITEM_IDS
    }
    expected.update(
        {
            f"decomposition:{item_id}": "eval_claim_decomposition_v2"
            for item_id in LOCKED_ITEM_IDS
        }
    )
    expected.update(
        {f"rubric:{item_id}": "eval_item_rubric" for item_id in LOCKED_ITEM_IDS}
    )
    expected.update(
        {
            f"social:{mode.value}-{ordinal:02d}": "answer_generation"
            for mode in SOCIAL_MODES
            for ordinal in range(1, len(SOCIAL_QUESTIONS) + 1)
        }
    )
    return expected


class V4EvaluationError(RuntimeError):
    """The clean cohort can no longer prove its declared call contract."""


@dataclass(frozen=True, slots=True)
class V4Paths:
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
    def reservation_root(self) -> Path:
        return self.root / "ambiguity-reservations"

    @property
    def report(self) -> Path:
        return self.root / "public-report.json"

    @property
    def trace_scope_continuation(self) -> Path:
        return self.root / "trace-scope-continuation.json"

    @property
    def frozen_instrument_source(self) -> Path:
        return self.root.parent / "retrieval-authored-v3-professional-2026-08-13" / "instrument-freeze.json"


@dataclass(frozen=True, slots=True)
class PreparedV4Cohort:
    paths: V4Paths
    gold: object
    items: tuple[Mapping[str, object], ...]
    embeddings: Mapping[str, list[float]]
    collection: object
    chunks: list[dict[str, Any]]
    corpus_trace: Mapping[str, object]
    manifest: Mapping[str, object]

    def as_v3_retrieval_adapter(self) -> PreparedV3Cohort:
        """Expose only the common data shape consumed by shared v3 primitives."""

        return PreparedV3Cohort(
            paths=self.paths,  # type: ignore[arg-type]
            gold=self.gold,  # type: ignore[arg-type]
            items=self.items,
            embeddings=self.embeddings,
            collection=self.collection,
            chunks=self.chunks,
            corpus_trace=self.corpus_trace,
            manifest=self.manifest,
        )


class ExactRequestCapturingClient:
    """Verify actual parse kwargs against the sealed projection before network."""

    def __init__(
        self,
        client: object,
        *,
        expected_projection: Mapping[str, object],
        seal_boundary: Callable[[], None],
        attempt_state: list[int] | None = None,
    ) -> None:
        self._client = client
        self._expected = dict(expected_projection)
        self._seal_boundary = seal_boundary
        self._attempt_state = attempt_state if attempt_state is not None else [0]

    @property
    def attempt_count(self) -> int:
        return self._attempt_state[0]

    @property
    def responses(self) -> object:
        return _ExactResponses(self, getattr(self._client, "responses"))

    def with_options(self, **kwargs: object) -> ExactRequestCapturingClient:
        return ExactRequestCapturingClient(
            getattr(self._client, "with_options")(**kwargs),
            expected_projection=self._expected,
            seal_boundary=self._seal_boundary,
            attempt_state=self._attempt_state,
        )

    def __getattr__(self, name: str) -> object:
        return getattr(self._client, name)


class _ExactResponses:
    def __init__(self, owner: ExactRequestCapturingClient, resource: object) -> None:
        self._owner = owner
        self._resource = resource

    @property
    def with_raw_response(self) -> object:
        return _ExactRawResponses(
            self._owner,
            getattr(self._resource, "with_raw_response"),
        )

    def parse(self, **kwargs: object) -> object:
        self._verify_and_seal(kwargs)
        return getattr(self._resource, "parse")(**kwargs)

    def _verify_and_seal(self, kwargs: Mapping[str, object]) -> None:
        projected = project_request(
            operation=str(self._owner._expected["operation"]),
            request=kwargs,
            request_binding=self._owner._expected["request_binding"],
        )
        for field in (
            "provider_request_shape_sha256",
            "projected_worst_case_nano_usd",
            "max_output_tokens",
        ):
            if projected[field] != self._owner._expected[field]:
                raise V4EvaluationError(f"actual provider request changed {field}")
        if self._owner.attempt_count:
            raise V4EvaluationError("automatic or repeated provider attempt detected")
        self._owner._seal_boundary()
        self._owner._attempt_state[0] += 1

    def __getattr__(self, name: str) -> object:
        return getattr(self._resource, name)


class _ExactRawResponses(_ExactResponses):
    def parse(self, **kwargs: object) -> object:
        self._verify_and_seal(kwargs)
        return getattr(self._resource, "parse")(**kwargs)


def default_paths(base_dir: Path, *, root: Path | None = None) -> V4Paths:
    allowed = (base_dir / "runtime" / "evaluations").resolve()
    selected = (root or allowed / EVALUATION_ID).resolve()
    if selected == allowed or allowed not in selected.parents:
        raise V4EvaluationError("v4 run root must be a child of runtime/evaluations")
    return V4Paths(
        root=selected,
        gold=base_dir / "fixtures" / "gold_set.json",
        provenance=base_dir / "fixtures" / "gold_set.provenance.json",
        question_commitment=base_dir / "fixtures" / "gold_questions.commitment.json",
        corpus_manifest=base_dir / "fixtures" / "corpus_manifest.json",
        chunks=base_dir / "output" / "chunks.json",
        cache=allowed / "retrieval-query-embeddings.json",
        catalog=base_dir / "fixtures" / "evaluation_model_catalog.json",
        uv_lock=base_dir / "uv.lock",
        chroma=base_dir / "chroma_db",
    )


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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise V4EvaluationError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise V4EvaluationError(f"JSON artifact must be an object: {path}")
    return value


def atomic_seal_json(path: Path, value: Mapping[str, object]) -> None:
    """Publish one complete immutable JSON file without an overwrite window."""

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=_json_default,
    ).encode("utf-8") + b"\n"
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise V4EvaluationError(f"sealed artifact already exists: {path}") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_or_validate_json(path: Path, value: Mapping[str, object]) -> None:
    if path.exists():
        if read_json_object(path) != dict(value):
            raise V4EvaluationError(f"existing sealed artifact changed: {path}")
        return
    atomic_seal_json(path, value)


def _required_string(value: Mapping[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise V4EvaluationError(f"missing non-blank {field}")
    return item


def _git_commit(base_dir: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=base_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise V4EvaluationError("could not resolve git commit")
    return result.stdout.strip()


def _nano_usd(value: Decimal) -> int:
    if not value.is_finite() or value <= 0 or value > MAXIMUM_DESIGN_CAP_USD:
        raise V4EvaluationError("cap must be positive and no greater than $7.00")
    scaled = value * NANO_USD_PER_USD
    if scaled != scaled.to_integral_value():
        raise V4EvaluationError("cap supports at most nine decimal USD places")
    return int(scaled)


def exact_usd(nano_usd: int) -> str:
    return f"{Decimal(nano_usd) / NANO_USD_PER_USD:.9f}"


def classify_failure(exc: BaseException | None, *, failure_code: object = None) -> str:
    direct = str(getattr(failure_code, "value", failure_code) or "").casefold()
    direct_map = {
        "request_timeout": "timeout",
        "transport_failure": "transport",
        "provider_exception": "provider_exception",
        "refusal": "provider_refusal",
        "invalid_response": "structured_output_rejection",
        "structured_output_rejected": "structured_output_rejection",
        "local_contract_validation_failed": "local_validation_failure",
    }
    if direct in direct_map:
        return direct_map[direct]
    text = " ".join(
        part
        for part in (
            type(exc).__name__ if exc is not None else "",
            str(exc) if exc is not None else "",
            str(failure_code or ""),
        )
        if part
    ).casefold()
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "refusal" in text or "refused" in text:
        return "provider_refusal"
    if any(token in text for token in ("validation", "claim_text", "contract")):
        return "local_validation_failure"
    if any(token in text for token in ("schema", "parse", "structured", "incomplete")):
        return "structured_output_rejection"
    if any(token in text for token in ("connection", "transport", "network", "provider_failure")):
        return "transport"
    return "unknown_provider_failure"


def project_request(
    *,
    operation: str,
    request: Mapping[str, object],
    request_binding: Mapping[str, object],
) -> dict[str, object]:
    serialized = json.dumps(
        _request_json_value(request),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    projection = projected_provider_operation_cost_nano_usd(
        provider_kind="responses",
        request=request,
    )
    return {
        "operation": operation,
        "provider_kind": "responses",
        "request_binding": dict(request_binding),
        "request_binding_sha256": canonical_json_sha256(request_binding),
        "provider_request_shape_sha256": hashlib.sha256(serialized).hexdigest(),
        "provider_request_serialized_bytes": len(serialized),
        "provider_request_token_overhead_upper_bound": (
            PROVIDER_REQUEST_TOKEN_OVERHEAD_UPPER_BOUND
        ),
        "provider_input_token_upper_bound": (
            len(serialized) + PROVIDER_REQUEST_TOKEN_OVERHEAD_UPPER_BOUND
        ),
        "max_output_tokens": int(request["max_output_tokens"]),
        "projected_worst_case_nano_usd": int(projection),
        "projection_method": "costs.projected_provider_operation_cost_nano_usd",
    }


def generation_request_projection(
    cohort: PreparedV4Cohort,
    *,
    item: Mapping[str, object],
) -> dict[str, object]:
    item_id = _required_string(item, "id")
    question = _required_string(item, "question")
    vector = cohort.embeddings.get(item_id)
    if vector is None:
        raise V4EvaluationError(f"cached embedding missing for {item_id}")
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
        list(retrieval_outcome.final_chunks),
        retrieval_query=question,
    )
    if not dossier.units:
        raise V4EvaluationError(f"{item_id} has no authoring dossier")
    resolved = ResolvedTurn(standalone_question=question, trusted_user_texts=(question,))
    lens, voice, worldview = settings_for_archivist_mode(ArchivistMode.PROFESSIONAL)
    instructions = build_authored_response_instructions(
        ArchivistMode.PROFESSIONAL,
        historiographical_lens=lens,
        voice=voice,
        worldview=worldview,
    )
    request_input = build_authored_response_input(
        question=question,
        resolved_turn=resolved,
        dossier=dossier,
        mode=ArchivistMode.PROFESSIONAL,
    )
    request = {
        "instructions": instructions,
        "input": request_input,
        "text_format": AuthoredResponse,
        "max_output_tokens": MAX_AUTHORED_RESPONSE_OUTPUT_TOKENS,
        **AUTHORED_RESPONSE_SETTINGS.responses_create_kwargs(),
    }
    return project_request(
        operation="answer_generation",
        request=request,
        request_binding={
            "item_id": item_id,
            "model": AUTHORED_RESPONSE_SETTINGS.model,
            "instructions_sha256": hashlib.sha256(instructions.encode()).hexdigest(),
            "input_sha256": hashlib.sha256(request_input.encode()).hexdigest(),
            "dossier_id": dossier.dossier_id,
        },
    )


def decomposition_request_projection(*, item_id: str, answer: str) -> dict[str, object]:
    from evaluation_decomposition_v2 import (
        ClaimTextDecomposition,
        DECOMPOSITION_MAX_OUTPUT_TOKENS,
        DECOMPOSITION_PROMPT,
        DECOMPOSITION_SETTINGS,
        build_decomposition_input,
        serialize_decomposition_input,
    )

    request_input = serialize_decomposition_input(build_decomposition_input(answer=answer))
    request = {
        "instructions": DECOMPOSITION_PROMPT,
        "input": request_input,
        "text_format": ClaimTextDecomposition,
        "max_output_tokens": DECOMPOSITION_MAX_OUTPUT_TOKENS,
        **DECOMPOSITION_SETTINGS.responses_create_kwargs(),
    }
    return project_request(
        operation="eval_claim_decomposition_v2",
        request=request,
        request_binding={
            "item_id": item_id,
            "model": DECOMPOSITION_SETTINGS.model,
            "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
            "input_sha256": hashlib.sha256(request_input.encode()).hexdigest(),
            "timeout_seconds": DECOMPOSITION_TIMEOUT_SECONDS,
        },
    )


def social_request_projection(*, mode: ArchivistMode, question: str) -> dict[str, object]:
    instructions = build_character_conversation_instructions(mode)
    request_input = build_character_conversation_input(
        question=question,
        mode=mode,
    )
    request = {
        "instructions": instructions,
        "input": request_input,
        "text_format": CharacterConversationResponse,
        "max_output_tokens": MAX_CHARACTER_CONVERSATION_OUTPUT_TOKENS,
        **CHARACTER_CONVERSATION_SETTINGS.responses_create_kwargs(),
    }
    return project_request(
        operation="answer_generation",
        request=request,
        request_binding={
            "mode": mode.value,
            "model": CHARACTER_CONVERSATION_SETTINGS.model,
            "question_sha256": normalized_question_sha256(question),
            "instructions_sha256": hashlib.sha256(instructions.encode()).hexdigest(),
            "input_sha256": hashlib.sha256(request_input.encode()).hexdigest(),
            "timeout_seconds": SOCIAL_TIMEOUT_SECONDS,
        },
    )


def rubric_request_projection(
    *,
    item_id: str,
    answer: str,
    claims: Sequence[Mapping[str, object]],
    rubric: object,
) -> dict[str, object]:
    from evaluation_decomposition_v2 import RUBRIC_MAX_OUTPUT_TOKENS
    from evaluation_judge import ITEM_RUBRIC_PROMPT, ItemRubricVerdict, JUDGE_SETTINGS

    payload = {
        "answer": answer,
        "answer_claims": [
            {"claim_id": claim["claim_id"], "text": claim["text"]}
            for claim in claims
        ],
        "rubric": rubric.model_dump(mode="json"),
    }
    request_input = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    request = {
        "instructions": ITEM_RUBRIC_PROMPT,
        "input": request_input,
        "text_format": ItemRubricVerdict,
        "max_output_tokens": RUBRIC_MAX_OUTPUT_TOKENS,
        **JUDGE_SETTINGS.responses_create_kwargs(),
    }
    return project_request(
        operation="eval_item_rubric",
        request=request,
        request_binding={
            "item_id": item_id,
            "model": JUDGE_SETTINGS.model,
            "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
            "decomposition_sha256": canonical_json_sha256(list(claims)),
            "input_sha256": hashlib.sha256(request_input.encode()).hexdigest(),
            "timeout_seconds": DECOMPOSITION_TIMEOUT_SECONDS,
        },
    )


def _reservation_files(paths: V4Paths) -> list[Path]:
    if not paths.reservation_root.exists():
        return []
    return sorted(paths.reservation_root.glob("*.json"))


def _validate_attempt_registry(paths: V4Paths) -> None:
    expected = _expected_turn_operations()
    attempts_root = paths.root / "attempts"
    if not attempts_root.exists():
        return
    for directory in attempts_root.glob("*/*"):
        if not directory.is_dir():
            continue
        turn_id = f"{directory.parent.name}:{directory.name}"
        if turn_id not in expected:
            raise V4EvaluationError(f"v4 attempt registry contains foreign turn {turn_id}")


def _tracked_spend(paths: V4Paths) -> int:
    if not paths.ledger.exists():
        return 0
    expected = _expected_turn_operations()
    with closing(sqlite3.connect(paths.ledger)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT operation, project_id, conversation_id, turn_id, request_id,
                   estimated_cost_nano_usd, unpriced
            FROM usage_events
            ORDER BY id
            """
        ).fetchall()
    turn_counts: Counter[str] = Counter()
    tracked = 0
    for row in rows:
        turn_id = str(row["turn_id"] or "")
        operation = str(row["operation"] or "")
        if (
            row["request_id"] != MASTER_REQUEST_ID
            or row["project_id"] != MASTER_PROJECT_ID
            or row["conversation_id"] != MASTER_CONVERSATION_ID
            or expected.get(turn_id) != operation
            or bool(row["unpriced"])
        ):
            raise V4EvaluationError("v4 ledger contains unpriced or foreign-scope events")
        turn_counts[turn_id] += 1
        tracked += int(row["estimated_cost_nano_usd"])
    if any(count != 1 for count in turn_counts.values()):
        raise V4EvaluationError("v4 ledger contains repeated provider events for one turn")
    return tracked


def budget_state(paths: V4Paths, *, cap_nano_usd: int) -> dict[str, object]:
    _validate_attempt_registry(paths)
    expected_operations = _expected_turn_operations()
    reservations = [read_json_object(path) for path in _reservation_files(paths)]
    seen_turns: set[str] = set()
    for reservation in reservations:
        turn_id = _required_string(reservation, "turn_id")
        if (
            reservation.get("schema") != V4_RESERVATION_SCHEMA
            or reservation.get("evaluation_id") != EVALUATION_ID
            or turn_id in seen_turns
            or expected_operations.get(turn_id) is None
        ):
            raise V4EvaluationError("ambiguity reservation identity changed")
        seen_turns.add(turn_id)
        intent_path, marker_path, outcome_path = attempt_paths(paths, turn_id=turn_id)
        if not all(path.is_file() for path in (intent_path, marker_path, outcome_path)):
            raise V4EvaluationError("ambiguity reservation lost a bound artifact")
        intent = read_json_object(intent_path)
        marker = read_json_object(marker_path)
        outcome = read_json_object(outcome_path)
        projection = intent.get("request_projection")
        evidence = outcome.get("operation_evidence")
        if (
            not isinstance(projection, Mapping)
            or not isinstance(evidence, Mapping)
            or evidence.get("event_count") != 0
            or reservation.get("intent_sha256") != canonical_json_sha256(intent)
            or reservation.get("attempt_started_sha256") != sha256_file(marker_path)
            or reservation.get("outcome_sha256") != canonical_json_sha256(outcome)
            or reservation.get("request_shape_sha256")
            != projection.get("provider_request_shape_sha256")
            or reservation.get("reserved_nano_usd")
            != projection.get("projected_worst_case_nano_usd")
            or intent.get("schema") != V4_INTENT_SCHEMA
            or intent.get("evaluation_id") != EVALUATION_ID
            or intent.get("turn_id") != turn_id
            or marker.get("intent_sha256") != canonical_json_sha256(intent)
            or marker.get("schema") != V4_ATTEMPT_STARTED_SCHEMA
            or marker.get("evaluation_id") != EVALUATION_ID
            or marker.get("turn_id") != turn_id
            or marker.get("request_shape_sha256")
            != projection.get("provider_request_shape_sha256")
            or marker.get("projected_worst_case_nano_usd")
            != projection.get("projected_worst_case_nano_usd")
            or marker.get("provider_boundary_not_crossed") is True
            or reservation.get("reservation_method")
            != "sealed_exact_request_worst_case_projection"
            or reservation.get("provider_boundary_attempt_count") != 1
            or reservation.get("usage_event_count") != 0
            or reservation.get("retried") is not False
            or reservation.get("continuation_policy")
            != "automatic_manifest_predeclared_v1"
            or reservation.get("item_id") != intent.get("item_id")
            or reservation.get("phase") != intent.get("phase")
            or turn_id != f"{intent.get('phase')}:{intent.get('item_id')}"
            or reservation.get("operation") != projection.get("operation")
            or expected_operations.get(turn_id) != projection.get("operation")
            or not _reservation_path(paths, turn_id=turn_id).is_file()
            or intent.get("attempt_count") != 1
            or intent.get("automatic_retries") != 0
            or intent.get("replacement") is not False
            or outcome.get("provider_boundary_attempt_count") != 1
            or outcome.get("automatic_retries") != 0
            or outcome.get("status") not in {"technical_failure", "local_fallback"}
            or outcome.get("failure_category") != "usage_contract_failure"
            or outcome.get("evaluation_id") != EVALUATION_ID
            or outcome.get("item_id") != intent.get("item_id")
            or evidence
            != operation_evidence(
                paths,
                turn_id=turn_id,
                operation=str(projection.get("operation")),
            )
        ):
            raise V4EvaluationError("ambiguity reservation binding changed")
        current = operation_evidence(
            paths,
            turn_id=turn_id,
            operation=str(projection["operation"]),
        )
        if current.get("event_count") != 0:
            raise V4EvaluationError("reserved ambiguity now has a priced usage event")
    reserved = sum(int(value["reserved_nano_usd"]) for value in reservations)
    tracked = _tracked_spend(paths)
    accounted = tracked + reserved
    if accounted > cap_nano_usd:
        raise V4EvaluationError("tracked spend plus ambiguity reserve exceeds exact cap")
    return {
        "cap_nano_usd": cap_nano_usd,
        "tracked_spend_nano_usd": tracked,
        "ambiguity_reserved_nano_usd": reserved,
        "accounted_nano_usd": accounted,
        "remaining_nano_usd": cap_nano_usd - accounted,
        "reservation_count": len(reservations),
        "cap_usd_exact": exact_usd(cap_nano_usd),
        "tracked_spend_usd_exact": exact_usd(tracked),
        "ambiguity_reserved_usd_exact": exact_usd(reserved),
        "accounted_usd_exact": exact_usd(accounted),
        "remaining_usd_exact": exact_usd(cap_nano_usd - accounted),
    }


def require_projection_headroom(
    paths: V4Paths,
    *,
    cap_nano_usd: int,
    projected_nano_usd: int,
) -> None:
    state = budget_state(paths, cap_nano_usd=cap_nano_usd)
    if int(state["accounted_nano_usd"]) + projected_nano_usd > cap_nano_usd:
        raise V4EvaluationError("next exact request projection would exceed authorized cap")


@contextmanager
def master_usage_scope(
    paths: V4Paths,
    *,
    cap_nano_usd: int,
    turn_id: str,
) -> Iterator[UsageLedger]:
    state = budget_state(paths, cap_nano_usd=cap_nano_usd)
    effective = cap_nano_usd - int(state["ambiguity_reserved_nano_usd"])
    previous = os.environ.get("ARCHIVIST_USAGE_DB")
    os.environ["ARCHIVIST_USAGE_DB"] = str(paths.ledger)
    try:
        ledger = UsageLedger(paths.ledger)
        ledger.update_settings(
            monthly_budget_usd=Decimal(effective) / NANO_USD_PER_USD,
            warning_threshold_percent=80,
            hard_limit_enabled=True,
        )
        with usage_scope(
            project_id=MASTER_PROJECT_ID,
            conversation_id=MASTER_CONVERSATION_ID,
            turn_id=turn_id,
            request_id=MASTER_REQUEST_ID,
            enforce_budget=True,
            allow_over_budget=False,
            request_cost_ceiling_nano_usd=int(state["remaining_nano_usd"]),
        ):
            yield ledger
    finally:
        if previous is None:
            os.environ.pop("ARCHIVIST_USAGE_DB", None)
        else:
            os.environ["ARCHIVIST_USAGE_DB"] = previous


def operation_evidence(
    paths: V4Paths,
    *,
    turn_id: str,
    operation: str,
) -> dict[str, object]:
    rows: list[sqlite3.Row] = []
    if paths.ledger.exists():
        with closing(sqlite3.connect(paths.ledger)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT response_id, operation, requested_model, actual_model,
                       project_id, conversation_id, turn_id, request_id,
                       input_tokens, output_tokens, reasoning_tokens, total_tokens,
                       estimated_cost_nano_usd, unpriced
                FROM usage_events
                WHERE request_id = ? AND turn_id = ?
                ORDER BY id
                """,
                (MASTER_REQUEST_ID, turn_id),
            ).fetchall()
    events = [dict(row) for row in rows]
    scope_valid = all(
        event["project_id"] == MASTER_PROJECT_ID
        and event["conversation_id"] == MASTER_CONVERSATION_ID
        and event["turn_id"] == turn_id
        and event["request_id"] == MASTER_REQUEST_ID
        and event["operation"] == operation
        for event in events
    )
    return {
        "turn_id": turn_id,
        "operation": operation,
        "event_count": len(events),
        "exactly_one_priced_event": (
            len(events) == 1
            and scope_valid
            and not bool(events[0]["unpriced"])
        ),
        "scope_valid": scope_valid,
        "events": events,
    }


def _expected_model_for_phase(phase: str) -> str | None:
    if phase in {"generation", "social"}:
        return (
            AUTHORED_RESPONSE_SETTINGS.model
            if phase == "generation"
            else CHARACTER_CONVERSATION_SETTINGS.model
        )
    if phase == "decomposition":
        from evaluation_decomposition_v2 import DECOMPOSITION_MODEL

        return DECOMPOSITION_MODEL
    if phase == "rubric":
        from evaluation_judge import JUDGE_MODEL

        return JUDGE_MODEL
    return None


def _require_priced_event_model(
    evidence: Mapping[str, object],
    *,
    phase: str,
    label: str,
) -> None:
    if evidence.get("event_count") != 1 or evidence.get("exactly_one_priced_event") is not True:
        raise V4EvaluationError(f"{label} lacks exactly one priced event")
    events = evidence.get("events")
    if not isinstance(events, list) or len(events) != 1 or not isinstance(events[0], Mapping):
        raise V4EvaluationError(f"{label} usage evidence is malformed")
    expected = _expected_model_for_phase(phase)
    event = events[0]
    if (
        expected is None
        or event.get("requested_model") != expected
        or event.get("actual_model") != expected
        or not str(event.get("response_id") or "").strip()
    ):
        raise V4EvaluationError(f"{label} provider model or response identity changed")


def _turn_slug(turn_id: str) -> str:
    return turn_id.replace(":", "-").replace("/", "-")


def attempt_paths(paths: V4Paths, *, turn_id: str) -> tuple[Path, Path, Path]:
    phase, _, item_id = turn_id.partition(":")
    root = paths.root / "attempts" / phase / item_id
    return root / "intent.json", root / "attempt-started.json", root / "outcome.json"


def _reservation_path(paths: V4Paths, *, turn_id: str) -> Path:
    return paths.reservation_root / f"{_turn_slug(turn_id)}.json"


def build_attempt_intent(
    *,
    cohort_manifest_sha256: str,
    turn_id: str,
    item_id: str,
    phase: str,
    projection: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema": V4_INTENT_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "cohort_manifest_sha256": cohort_manifest_sha256,
        "turn_id": turn_id,
        "item_id": item_id,
        "phase": phase,
        "attempt_count": 1,
        "automatic_retries": 0,
        "replacement": False,
        "request_projection": dict(projection),
    }


def prepare_attempt(
    paths: V4Paths,
    *,
    intent: Mapping[str, object],
    cap_nano_usd: int,
) -> Callable[[], None]:
    turn_id = _required_string(intent, "turn_id")
    intent_path, started_path, outcome_path = attempt_paths(paths, turn_id=turn_id)
    projection = intent.get("request_projection")
    if not isinstance(projection, Mapping):
        raise V4EvaluationError("attempt intent lacks request projection")
    projected = int(projection["projected_worst_case_nano_usd"])
    require_projection_headroom(
        paths,
        cap_nano_usd=cap_nano_usd,
        projected_nano_usd=projected,
    )
    write_or_validate_json(intent_path, intent)
    if outcome_path.exists():
        raise V4EvaluationError(f"attempt already has an outcome: {turn_id}")
    if started_path.exists():
        raise V4EvaluationError(
            f"attempt already crossed provider boundary and may not be retried: {turn_id}"
        )

    def seal_boundary() -> None:
        atomic_seal_json(
            started_path,
            {
                "schema": V4_ATTEMPT_STARTED_SCHEMA,
                "evaluation_id": EVALUATION_ID,
                "turn_id": turn_id,
                "intent_sha256": canonical_json_sha256(intent),
                "request_shape_sha256": projection["provider_request_shape_sha256"],
                "projected_worst_case_nano_usd": projected,
            },
        )

    return seal_boundary


def reserve_zero_event(
    paths: V4Paths,
    *,
    intent: Mapping[str, object],
    outcome: Mapping[str, object],
    cap_nano_usd: int,
) -> dict[str, object]:
    turn_id = _required_string(intent, "turn_id")
    _, started_path, outcome_path = attempt_paths(paths, turn_id=turn_id)
    if not started_path.exists() or not outcome_path.exists():
        raise V4EvaluationError("zero-event reservation requires sealed boundary and outcome")
    projection = intent.get("request_projection")
    if not isinstance(projection, Mapping):
        raise V4EvaluationError("zero-event intent has no projection")
    evidence = outcome.get("operation_evidence")
    if not isinstance(evidence, Mapping) or evidence.get("event_count") != 0:
        raise V4EvaluationError("ambiguity reserve applies only to a zero-event attempt")
    reserved = int(projection["projected_worst_case_nano_usd"])
    reservation = {
        "schema": V4_RESERVATION_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "turn_id": turn_id,
        "item_id": intent["item_id"],
        "phase": intent["phase"],
        "operation": projection["operation"],
        "intent_sha256": canonical_json_sha256(intent),
        "attempt_started_sha256": sha256_file(started_path),
        "outcome_sha256": canonical_json_sha256(outcome),
        "request_shape_sha256": projection["provider_request_shape_sha256"],
        "reserved_nano_usd": reserved,
        "reservation_method": "sealed_exact_request_worst_case_projection",
        "provider_boundary_attempt_count": 1,
        "usage_event_count": 0,
        "retried": False,
        "continuation_policy": "automatic_manifest_predeclared_v1",
    }
    path = paths.reservation_root / f"{_turn_slug(turn_id)}.json"
    write_or_validate_json(path, reservation)
    budget_state(paths, cap_nano_usd=cap_nano_usd)
    return reservation


def _expected_outcome_schema(phase: str) -> str:
    schema = {
        "generation": V4_GENERATION_OUTCOME_SCHEMA,
        "decomposition": V4_DECOMPOSITION_OUTCOME_SCHEMA,
        "rubric": V4_RUBRIC_OUTCOME_SCHEMA,
        "social": V4_SOCIAL_OUTCOME_SCHEMA,
    }.get(phase)
    if schema is None:
        raise V4EvaluationError(f"unsupported attempt phase: {phase}")
    return schema


def _validate_attempt_envelope(
    *,
    intent: Mapping[str, object],
    marker: Mapping[str, object],
    outcome: Mapping[str, object],
) -> None:
    turn_id = _required_string(intent, "turn_id")
    phase = _required_string(intent, "phase")
    item_id = _required_string(intent, "item_id")
    projection = intent.get("request_projection")
    if not isinstance(projection, Mapping):
        raise V4EvaluationError("provider attempt lacks request projection")
    if (
        intent.get("schema") != V4_INTENT_SCHEMA
        or intent.get("evaluation_id") != EVALUATION_ID
        or intent.get("attempt_count") != 1
        or intent.get("automatic_retries") != 0
        or intent.get("replacement") is not False
        or turn_id != f"{phase}:{item_id}"
        or _expected_turn_operations().get(turn_id) != projection.get("operation")
        or marker.get("schema") != V4_ATTEMPT_STARTED_SCHEMA
        or marker.get("evaluation_id") != EVALUATION_ID
        or marker.get("turn_id") != turn_id
        or marker.get("intent_sha256") != canonical_json_sha256(intent)
        or marker.get("request_shape_sha256")
        != projection.get("provider_request_shape_sha256")
        or marker.get("projected_worst_case_nano_usd")
        != projection.get("projected_worst_case_nano_usd")
        or marker.get("provider_boundary_not_crossed") is True
        or outcome.get("schema") != _expected_outcome_schema(phase)
        or outcome.get("evaluation_id") != EVALUATION_ID
        or outcome.get("item_id") != item_id
        or outcome.get("intent_sha256") != canonical_json_sha256(intent)
        or outcome.get("provider_boundary_attempt_count") != 1
        or outcome.get("automatic_retries") != 0
    ):
        raise V4EvaluationError(f"attempt envelope changed: {turn_id}")


def _no_boundary_rubric_outcome(
    paths: V4Paths,
    *,
    intent: Mapping[str, object],
) -> dict[str, object]:
    turn_id = _required_string(intent, "turn_id")
    item_id = _required_string(intent, "item_id")
    if (
        intent.get("schema") != V4_INTENT_SCHEMA
        or intent.get("evaluation_id") != EVALUATION_ID
        or intent.get("phase") != "rubric"
        or turn_id != f"rubric:{item_id}"
        or intent.get("attempt_count") != 0
        or intent.get("automatic_retries") != 0
        or intent.get("replacement") is not False
        or intent.get("request_projection") is not None
    ):
        raise V4EvaluationError(f"invalid no-boundary rubric intent: {turn_id}")
    evidence = operation_evidence(
        paths,
        turn_id=turn_id,
        operation="eval_item_rubric",
    )
    if evidence["event_count"] != 0:
        raise V4EvaluationError(f"invalid no-boundary usage state: {turn_id}")
    return {
        "schema": V4_RUBRIC_OUTCOME_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "item_id": item_id,
        "status": "not_scored_decomposition_failure",
        "intent_sha256": canonical_json_sha256(intent),
        "provider_boundary_attempt_count": 0,
        "automatic_retries": 0,
        "operation_evidence": evidence,
        "timings_ms": {"rubric_boundary": None},
    }


def settle_attempt(
    paths: V4Paths,
    *,
    intent: Mapping[str, object],
    outcome: Mapping[str, object],
    cap_nano_usd: int,
) -> None:
    turn_id = _required_string(intent, "turn_id")
    _, started_path, outcome_path = attempt_paths(paths, turn_id=turn_id)
    if not started_path.exists():
        raise V4EvaluationError("provider outcome cannot precede boundary marker")
    marker = read_json_object(started_path)
    _validate_attempt_envelope(intent=intent, marker=marker, outcome=outcome)
    evidence = outcome.get("operation_evidence")
    if not isinstance(evidence, Mapping):
        raise V4EvaluationError("outcome has no operation evidence")
    projection = intent.get("request_projection")
    if not isinstance(projection, Mapping):
        raise V4EvaluationError("attempt intent lacks provider request projection")
    current = operation_evidence(
        paths,
        turn_id=turn_id,
        operation=str(projection["operation"]),
    )
    if dict(evidence) != current:
        raise V4EvaluationError("attempt usage evidence changed before outcome seal")
    count = int(evidence.get("event_count", -1))
    if count == 1:
        _require_priced_event_model(
            evidence,
            phase=_required_string(intent, "phase"),
            label=turn_id,
        )
    elif count != 0:
        raise V4EvaluationError("attempt has invalid provider usage evidence")
    write_or_validate_json(outcome_path, outcome)
    if count == 0:
        reserve_zero_event(
            paths,
            intent=intent,
            outcome=outcome,
            cap_nano_usd=cap_nano_usd,
        )
    budget_state(paths, cap_nano_usd=cap_nano_usd)


def recover_interrupted_attempts(
    paths: V4Paths,
    *,
    cap_nano_usd: int,
    cohort: PreparedV4Cohort | None = None,
) -> list[str]:
    """Fail closed after a local crash without replaying a provider boundary.

    Any boundary marker without a settled outcome is necessarily ambiguous.  A
    provider-free technical outcome and the predeclared exact reserve are
    sealed.  If an outcome exists but the process died before reserving its
    zero-event cost, only the reservation is completed.
    """

    recovered: list[str] = []
    budget_state(paths, cap_nano_usd=cap_nano_usd)
    attempts_root = paths.root / "attempts"
    if not attempts_root.exists():
        return recovered
    for intent_path in sorted(attempts_root.glob("*/*/intent.json")):
        intent = read_json_object(intent_path)
        turn_id = _required_string(intent, "turn_id")
        expected_intent, marker, outcome_path = attempt_paths(paths, turn_id=turn_id)
        if expected_intent.resolve() != intent_path.resolve():
            raise V4EvaluationError(f"attempt path does not match turn ID: {turn_id}")
        if not marker.exists():
            continue
        marker_value = read_json_object(marker)
        if (
            marker_value.get("schema") != V4_ATTEMPT_STARTED_SCHEMA
            or marker_value.get("evaluation_id") != EVALUATION_ID
            or marker_value.get("turn_id") != turn_id
            or marker_value.get("intent_sha256") != canonical_json_sha256(intent)
        ):
            raise V4EvaluationError(f"boundary marker changed: {turn_id}")
        if marker_value.get("provider_boundary_not_crossed") is True:
            expected_outcome = _no_boundary_rubric_outcome(paths, intent=intent)
            if expected_outcome["operation_evidence"]["event_count"] != 0:
                raise V4EvaluationError(f"invalid no-boundary usage state: {turn_id}")
            if outcome_path.exists():
                if read_json_object(outcome_path) != expected_outcome:
                    raise V4EvaluationError(f"invalid no-boundary disposition: {turn_id}")
            else:
                atomic_seal_json(outcome_path, expected_outcome)
                recovered.append(turn_id)
            continue
        projection = intent.get("request_projection")
        if not isinstance(projection, Mapping):
            raise V4EvaluationError(f"attempt request projection is missing: {turn_id}")
        if (
            marker_value.get("request_shape_sha256")
            != projection.get("provider_request_shape_sha256")
            or marker_value.get("projected_worst_case_nano_usd")
            != projection.get("projected_worst_case_nano_usd")
        ):
            raise V4EvaluationError(f"provider boundary projection changed: {turn_id}")
        current = operation_evidence(
            paths,
            turn_id=turn_id,
            operation=str(projection["operation"]),
        )
        count = int(current["event_count"])
        if count == 1:
            _require_priced_event_model(
                current,
                phase=_required_string(intent, "phase"),
                label=turn_id,
            )
        elif count != 0:
            raise V4EvaluationError(f"recovered attempt has invalid event count: {turn_id}")
        if not outcome_path.exists():
            phase = _required_string(intent, "phase")
            schema = {
                "generation": V4_GENERATION_OUTCOME_SCHEMA,
                "decomposition": V4_DECOMPOSITION_OUTCOME_SCHEMA,
                "rubric": V4_RUBRIC_OUTCOME_SCHEMA,
                "social": V4_SOCIAL_OUTCOME_SCHEMA,
            }.get(phase)
            if schema is None:
                raise V4EvaluationError(f"unsupported recovery phase: {phase}")
            outcome: dict[str, object] = {
                "schema": schema,
                "evaluation_id": EVALUATION_ID,
                "item_id": intent["item_id"],
                "status": "technical_failure",
                "failure_category": "usage_contract_failure",
                "failure_type": "InterruptedAfterProviderBoundary",
                "intent_sha256": canonical_json_sha256(intent),
                "provider_boundary_attempt_count": 1,
                "automatic_retries": 0,
                "operation_evidence": current,
                "timings_ms": {"unavailable_after_process_interruption": None},
            }
            if phase == "generation":
                if cohort is None:
                    raise V4EvaluationError("generation crash recovery requires cohort data")
                from retrieval_authored_v3_evaluation import _local_technical_generation_outcome

                item = next(
                    (
                        value
                        for value in cohort.items
                        if _required_string(value, "id") == intent["item_id"]
                    ),
                    None,
                )
                if item is None:
                    raise V4EvaluationError("generation crash item is outside cohort")
                outcome.update(
                    _local_technical_generation_outcome(
                        cohort.as_v3_retrieval_adapter(),
                        item=item,
                        exc=RuntimeError("interrupted_after_provider_boundary"),
                    )
                )
                outcome.update(
                    {
                        "schema": V4_GENERATION_OUTCOME_SCHEMA,
                        "evaluation_id": EVALUATION_ID,
                        "item_id": intent["item_id"],
                        "status": "technical_failure",
                        "delivered_answer_status": "essential_fallback",
                        "failure_category": "usage_contract_failure",
                        "failure_type": "InterruptedAfterProviderBoundary",
                        "intent_sha256": canonical_json_sha256(intent),
                        "provider_boundary_attempt_count": 1,
                        "automatic_retries": 0,
                        "operation_evidence": current,
                        "timings_ms": {"unavailable_after_process_interruption": None},
                    }
                )
            elif phase == "social":
                mode_value = str(intent["item_id"]).rsplit("-", 1)[0]
                mode = ArchivistMode(mode_value)
                fallback = deterministic_character_conversation_fallback(
                    mode,
                    CharacterConversationFailureCode.PROVIDER_FAILURE,
                )
                outcome.update(
                    {
                        "mode": mode.value,
                        "status": fallback.status.value,
                        "answer": fallback.answer,
                        "answer_sha256": hashlib.sha256(fallback.answer.encode()).hexdigest(),
                        "follow_up_count": len(fallback.follow_up_questions),
                        "failure_code": fallback.failure_code.value,
                    }
                )
            settle_attempt(
                paths,
                intent=intent,
                outcome=outcome,
                cap_nano_usd=cap_nano_usd,
            )
            recovered.append(turn_id)
            continue
        outcome = read_json_object(outcome_path)
        _validate_attempt_envelope(
            intent=intent,
            marker=marker_value,
            outcome=outcome,
        )
        evidence = outcome.get("operation_evidence")
        if not isinstance(evidence, Mapping):
            raise V4EvaluationError(f"recovered outcome lacks evidence: {turn_id}")
        if dict(evidence) != current:
            raise V4EvaluationError(f"recovered usage evidence changed: {turn_id}")
        reservation = _reservation_path(paths, turn_id=turn_id)
        if int(evidence.get("event_count", -1)) == 0 and not reservation.exists():
            reserve_zero_event(
                paths,
                intent=intent,
                outcome=outcome,
                cap_nano_usd=cap_nano_usd,
            )
            recovered.append(turn_id)
    budget_state(paths, cap_nano_usd=cap_nano_usd)
    return recovered


def _source_file_hashes(base_dir: Path) -> dict[str, str]:
    names = (
        "src/archivist_modes.py",
        "src/authored_response.py",
        "src/character_conversation.py",
        "src/corpus.py",
        "src/costs.py",
        "src/evidence_compiler.py",
        "src/evidence_dossier.py",
        "src/evaluation_decomposition_v2.py",
        "src/evaluation_judge.py",
        "src/model_config.py",
        "src/public_sources.py",
        "src/query_planning.py",
        "src/rag_pipeline.py",
        "src/retrieval.py",
        "src/retrieval_trace_contract.py",
        "src/web_project.py",
    )
    return {name: sha256_file(base_dir / name) for name in names}


def _product_source_hashes(base_dir: Path, *, product_commit: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in _source_file_hashes(base_dir):
        result = subprocess.run(
            ["git", "rev-parse", f"{product_commit}:{name}"],
            cwd=base_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise V4EvaluationError(f"product commit omits {name}")
        hashes[name] = result.stdout.strip()
    return hashes


def _head_source_blobs(base_dir: Path) -> dict[str, str]:
    return _product_source_hashes(base_dir, product_commit="HEAD")


def build_v4_manifest(
    *,
    base_dir: Path,
    paths: V4Paths,
    gold: object,
    cache: Mapping[str, object],
    corpus_identity: Mapping[str, object],
    index_identity: Mapping[str, object],
    cap_nano_usd: int,
    product_commit: str,
    require_clean: bool,
) -> dict[str, object]:
    if len(product_commit) != 40 or any(character not in "0123456789abcdef" for character in product_commit):
        raise V4EvaluationError("product commit must be a canonical lowercase 40-hex identity")
    if AUTHORED_RESPONSE_POLICY_VERSION != "retrieval-authored-v4":
        raise V4EvaluationError("post-timeout product policy v4 is not active")
    worktree = build_git_worktree_identity(base_dir)
    if require_clean and worktree.get("working_tree") != "clean":
        raise V4EvaluationError("v4 run-of-record manifest requires a clean tree")
    items = getattr(gold, "items")
    ids = [_required_string(item, "id") for item in items]
    if tuple(ids) != LOCKED_ITEM_IDS or tuple(ids[:10]) != SENTINEL_ITEM_IDS:
        raise V4EvaluationError("locked cohort item order changed")
    from evaluation_decomposition_v2 import decomposition_instrument_identity
    frozen_instrument = read_json_object(paths.frozen_instrument_source)
    v3_closure_path = paths.frozen_instrument_source.parent / "diagnostic-closure.json"
    v3_closure = read_json_object(v3_closure_path)
    closure_inventory = v3_closure.get("sealed_artifact_inventory")
    if (
        v3_closure.get("terminal_status") != "closed_incomplete_timeout_diagnostic"
        or not isinstance(closure_inventory, Mapping)
        or closure_inventory.get("instrument_freeze_file_sha256")
        != sha256_file(paths.frozen_instrument_source)
    ):
        raise V4EvaluationError("frozen instrument is not bound to terminal v3 closure")
    if (
        frozen_instrument.get("instrument") != decomposition_instrument_identity()
        or frozen_instrument.get("valid_item_count") != 10
        or frozen_instrument.get("failed_item_count") != 0
        or frozen_instrument.get("development_item_ids")
        != [f"G{ordinal:03d}" for ordinal in range(1, 11)]
        or not isinstance(frozen_instrument.get("outcome_sha256"), Mapping)
        or len(frozen_instrument["outcome_sha256"]) != 10
    ):
        raise V4EvaluationError("frozen G001-G010 instrument validation changed")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", product_commit, _git_commit(base_dir)],
        cwd=base_dir,
        check=False,
    )
    if ancestor.returncode != 0:
        raise V4EvaluationError("declared product commit is not a harness ancestor")

    product_hashes = _product_source_hashes(base_dir, product_commit=product_commit)
    current_product_hashes = _head_source_blobs(base_dir)
    if current_product_hashes != product_hashes:
        raise V4EvaluationError("evaluated product source differs from declared product commit")

    return {
        "schema": V4_COHORT_MANIFEST_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "classification": COHORT_CLASSIFICATION,
        "system_under_test": {
            "product_commit": product_commit,
            "harness_commit": _git_commit(base_dir),
            "rag_policy": AUTHORED_RESPONSE_POLICY_VERSION,
            "mode": ArchivistMode.PROFESSIONAL.value,
            "product_source_git_blob_oid": product_hashes,
            "current_product_source_git_blob_oid": current_product_hashes,
        },
        "working_tree": worktree,
        "locked_inputs": {
            "gold_set_sha256": getattr(gold, "gold_set_sha256"),
            "question_set_sha256": getattr(gold, "question_set_sha256"),
            "gold_provenance_sha256": sha256_file(paths.provenance),
            "question_commitment_sha256": sha256_file(paths.question_commitment),
            "corpus_manifest_sha256": corpus_identity["corpus_manifest_sha256"],
            "chunks_sha256": corpus_identity["chunks_sha256"],
            "embedding_cache_sha256": sha256_file(paths.cache),
            "provider_catalog_sha256": sha256_file(paths.catalog),
            "dependency_lock_sha256": sha256_file(paths.uv_lock),
        },
        "query_embeddings": {
            "source": "validated_cached_vectors",
            "schema": cache.get("schema"),
            "model": cache.get("model"),
            "item_count": cache.get("question_count"),
            "provider_operations": 0,
        },
        "corpus": dict(corpus_identity),
        "index": {**dict(index_identity), "identity_sha256": canonical_json_sha256(index_identity)},
        "authoring": {
            "input_schema": AUTHORED_RESPONSE_INPUT_SCHEMA,
            "output_schema": AUTHORED_RESPONSE_OUTPUT_SCHEMA,
            **authored_response_prompt_metadata(ArchivistMode.PROFESSIONAL),
            "model": AUTHORED_RESPONSE_SETTINGS.model,
            "max_output_tokens": MAX_AUTHORED_RESPONSE_OUTPUT_TOKENS,
            "total_provider_deadline_seconds": AUTHORED_TOTAL_PROVIDER_DEADLINE_SECONDS,
            "embedding_timeout_seconds": AUTHORED_EMBEDDING_TIMEOUT_SECONDS,
            "authoring_timeout_seconds": AUTHORED_AUTHORING_TIMEOUT_SECONDS,
            "attempts_per_item": 1,
            "automatic_retries": 0,
        },
        "sentinel": {
            "item_ids": list(SENTINEL_ITEM_IDS),
            "same_once_only_cohort": True,
            "repeated_by_full_phase": False,
            "blocking_checks": [
                "identity",
                "one_attempt",
                "valid_trace",
                "citation_mapping",
                "cost_safety",
            ],
            "report_only_observations": [
                "answer_quality",
                "generated_success_rate",
                "latency",
                "cost",
            ],
        },
        "phase_order": [
            "professional_sentinel_H001_H010",
            "professional_remaining_27",
            "held_out_decomposition_37",
            "exploratory_rubric",
            "separate_four_mode_social_suite",
        ],
        "decomposition": {
            **dict(decomposition_instrument_identity()),
            "frozen_before_cohort": True,
            "frozen_development_item_ids": [f"G{ordinal:03d}" for ordinal in range(1, 11)],
            "instrument_freeze_sha256": sha256_file(paths.frozen_instrument_source),
            "instrument_freeze_canonical_sha256": canonical_json_sha256(frozen_instrument),
            "v3_diagnostic_closure_file_sha256": sha256_file(v3_closure_path),
            "v3_diagnostic_closure_canonical_sha256": canonical_json_sha256(v3_closure),
            "timeout_seconds": DECOMPOSITION_TIMEOUT_SECONDS,
            "latency_recorded": True,
        },
        "social_suite": {
            "separate_from_historical_quality_cohort": True,
            "mode_values": [mode.value for mode in SOCIAL_MODES],
            "case_count": len(SOCIAL_MODES) * len(SOCIAL_QUESTIONS),
            "question_sha256": [
                normalized_question_sha256(question) for question in SOCIAL_QUESTIONS
            ],
            "input_schema": CHARACTER_CONVERSATION_INPUT_SCHEMA,
            "output_schema": CHARACTER_CONVERSATION_OUTPUT_SCHEMA,
            "production_router_validated": True,
        },
        "ambiguity_policy": {
            "version": "automatic-manifest-predeclared-v1",
            "request_intent_sealed_before_provider_boundary": True,
            "boundary_marker_sealed_immediately_before_provider_call": True,
            "zero_event_action": "reserve_exact_request_worst_case_and_continue_if_cap_allows",
            "zero_event_retry": False,
            "code_commit_per_event_required": False,
            "stop_condition": "tracked_plus_reserved_plus_next_projection_exceeds_cap",
        },
        "paid_scope": {
            "provider": "OpenAI",
            "fresh_authorization_required": True,
            "master_request_id": MASTER_REQUEST_ID,
            "maximum_total_cost_nano_usd": cap_nano_usd,
            "maximum_total_cost_usd_exact": exact_usd(cap_nano_usd),
            "automatic_retries": 0,
        },
        "items": [
            {
                "id": item_id,
                "question_sha256": normalized_question_sha256(_required_string(item, "question")),
                "stratum": _required_string(item, "stratum"),
                "expected_behavior": _required_string(item, "expected_behavior"),
            }
            for item_id, item in zip(ids, items, strict=True)
        ],
        "item_count": len(items),
        "privacy": {
            "artifact_root": "gitignored_private_runtime",
            "public_report_text_free": True,
            "gold_visible_to_generation": False,
            "gold_visible_to_decomposition": False,
        },
    }


def prepare_v4_cohort(
    *,
    base_dir: Path,
    paths: V4Paths,
    maximum_usd: Decimal,
    product_commit: str,
    collection: object | None = None,
    chunks: list[dict[str, Any]] | None = None,
    require_clean: bool = True,
    persist_manifest: bool = False,
) -> PreparedV4Cohort:
    cap_nano = _nano_usd(maximum_usd)
    for path, expected, label in (
        (paths.gold, EXPECTED_GOLD_SHA256, "gold set"),
        (paths.provenance, EXPECTED_PROVENANCE_SHA256, "gold provenance"),
        (paths.question_commitment, EXPECTED_COMMITMENT_SHA256, "question commitment"),
        (paths.corpus_manifest, EXPECTED_MANIFEST_SHA256, "corpus manifest"),
        (paths.chunks, EXPECTED_CHUNKS_SHA256, "chunks"),
        (paths.cache, EXPECTED_CACHE_SHA256, "embedding cache"),
    ):
        if sha256_file(path) != expected:
            raise V4EvaluationError(f"{label} hash changed")
    gold = load_locked_gold(paths.gold, paths.provenance)
    if (
        gold.gold_set_sha256 != EXPECTED_GOLD_SHA256
        or gold.question_set_sha256 != EXPECTED_QUESTION_SET_SHA256
        or len(gold.items) != EXPECTED_ITEM_COUNT
    ):
        raise V4EvaluationError("locked benchmark identity changed")
    cache = read_json_object(paths.cache)
    embeddings = validate_embedding_cache(cache, gold)
    manifest_payload = read_json_object(paths.corpus_manifest)
    active_chunks = get_all_chunks() if chunks is None else chunks
    if collection is None:
        import chromadb

        active_collection = chromadb.PersistentClient(path=str(paths.chroma)).get_collection(
            name=str(manifest_payload["store"]["collection_name"]),
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
        raise V4EvaluationError("active corpus/index integrity failed")
    index_identity = _index_identity(active_collection, manifest_payload)
    corpus_trace = {
        "collection_name": corpus_identity["collection_name"],
        "collection_count": int(active_collection.count()),
        "corpus_manifest_sha256": corpus_identity["corpus_manifest_sha256"],
        "chunks_sha256": corpus_identity["chunks_sha256"],
        "hnsw_space": corpus_identity["hnsw_space"],
    }
    cohort_manifest = build_v4_manifest(
        base_dir=base_dir,
        paths=paths,
        gold=gold,
        cache=cache,
        corpus_identity=corpus_identity,
        index_identity=index_identity,
        cap_nano_usd=cap_nano,
        product_commit=product_commit,
        require_clean=require_clean,
    )
    if paths.cohort_manifest.exists():
        existing = read_json_object(paths.cohort_manifest)
        if existing != cohort_manifest:
            if not paths.trace_scope_continuation.is_file():
                raise V4EvaluationError("existing v4 cohort manifest identity changed")
            continuation = read_json_object(paths.trace_scope_continuation)
            current_commit = _git_commit(base_dir)
            if (
                continuation.get("schema") != V4_TRACE_SCOPE_CONTINUATION_SCHEMA
                or continuation.get("original_harness_commit")
                != existing.get("system_under_test", {}).get("harness_commit")
                or continuation.get("recovery_harness_commit") != current_commit
            ):
                raise V4EvaluationError("trace-scope recovery harness identity changed")
            expected_continuation = _trace_scope_continuation_payload(
                paths,
                harness_commit=current_commit,
                require_h011_unattempted=False,
            )
            if continuation != expected_continuation:
                raise V4EvaluationError("trace-scope continuation binding changed")
            normalized_current = json.loads(json.dumps(cohort_manifest))
            normalized_current["system_under_test"]["harness_commit"] = existing[
                "system_under_test"
            ]["harness_commit"]
            normalized_current["working_tree"] = existing["working_tree"]
            if normalized_current != existing:
                raise V4EvaluationError("recovery changed the sealed cohort identity")
        selected = existing
    else:
        selected = cohort_manifest
        if persist_manifest:
            atomic_seal_json(paths.cohort_manifest, cohort_manifest)
    return PreparedV4Cohort(
        paths=paths,
        gold=gold,
        items=gold.items,
        embeddings=embeddings,
        collection=active_collection,
        chunks=active_chunks,
        corpus_trace=corpus_trace,
        manifest=selected,
    )


def preflight(cohort: PreparedV4Cohort) -> dict[str, object]:
    readiness = preflight_all_cached_items(cohort.as_v3_retrieval_adapter())
    return {
        "schema": V4_EVALUATION_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        **readiness,
        "sentinel_item_ids": list(SENTINEL_ITEM_IDS),
        "sentinel_quality_gate": False,
        "sentinel_latency_gate": False,
    }


def _generation_items(cohort: PreparedV4Cohort, *, sentinel: bool) -> tuple[Mapping[str, object], ...]:
    if tuple(_required_string(item, "id") for item in cohort.items) != LOCKED_ITEM_IDS:
        raise V4EvaluationError("locked generation order changed")
    selected = cohort.items[:10] if sentinel else cohort.items[10:]
    if sentinel and tuple(_required_string(item, "id") for item in selected) != SENTINEL_ITEM_IDS:
        raise V4EvaluationError("sentinel order changed")
    return tuple(selected)


def _completed_turn(paths: V4Paths, *, turn_id: str) -> bool:
    intent, started, outcome = attempt_paths(paths, turn_id=turn_id)
    if not outcome.exists():
        return False
    if not intent.exists() or not started.exists():
        raise V4EvaluationError(f"outcome is missing intent or boundary marker: {turn_id}")
    intent_value = read_json_object(intent)
    marker = read_json_object(started)
    outcome_value = read_json_object(outcome)
    phase, _, item_id = turn_id.partition(":")
    expected_schema = {
        "generation": V4_GENERATION_OUTCOME_SCHEMA,
        "decomposition": V4_DECOMPOSITION_OUTCOME_SCHEMA,
        "rubric": V4_RUBRIC_OUTCOME_SCHEMA,
        "social": V4_SOCIAL_OUTCOME_SCHEMA,
    }.get(phase)
    if (
        expected_schema is None
        or intent_value.get("schema") != V4_INTENT_SCHEMA
        or intent_value.get("evaluation_id") != EVALUATION_ID
        or intent_value.get("turn_id") != turn_id
        or intent_value.get("phase") != phase
        or intent_value.get("item_id") != item_id
        or outcome_value.get("schema") != expected_schema
        or outcome_value.get("evaluation_id") != EVALUATION_ID
        or outcome_value.get("item_id") != item_id
        or marker.get("schema") != V4_ATTEMPT_STARTED_SCHEMA
        or marker.get("evaluation_id") != EVALUATION_ID
        or marker.get("turn_id") != turn_id
    ):
        raise V4EvaluationError(f"completed attempt identity changed: {turn_id}")
    if (
        marker.get("intent_sha256") != canonical_json_sha256(intent_value)
        or outcome_value.get("intent_sha256") != canonical_json_sha256(intent_value)
    ):
        raise V4EvaluationError(f"completed attempt hash binding changed: {turn_id}")
    no_boundary = marker.get("provider_boundary_not_crossed") is True
    if no_boundary:
        expected = _no_boundary_rubric_outcome(paths, intent=intent_value)
        if (
            marker.get("projected_worst_case_nano_usd") != 0
            or outcome_value != expected
            or expected["operation_evidence"]["event_count"] != 0
        ):
            raise V4EvaluationError(f"invalid no-boundary usage state: {turn_id}")
        return True

    _validate_attempt_envelope(
        intent=intent_value,
        marker=marker,
        outcome=outcome_value,
    )
    evidence = outcome_value.get("operation_evidence")
    projection = intent_value.get("request_projection")
    if not isinstance(evidence, Mapping) or not isinstance(projection, Mapping):
        raise V4EvaluationError(f"completed attempt lacks usage evidence: {turn_id}")
    expected_operation = str(projection["operation"])
    current_evidence = operation_evidence(
        paths,
        turn_id=turn_id,
        operation=expected_operation,
    )
    if dict(evidence) != current_evidence:
        raise V4EvaluationError(f"completed attempt usage evidence changed: {turn_id}")
    if evidence.get("event_count") == 0:
        if not _reservation_path(paths, turn_id=turn_id).is_file():
            raise V4EvaluationError(f"zero-event outcome lacks reservation: {turn_id}")
    elif evidence.get("exactly_one_priced_event") is not True:
        raise V4EvaluationError(f"completed attempt lacks one priced event: {turn_id}")
    else:
        _require_priced_event_model(
            evidence,
            phase=_required_string(intent_value, "phase"),
            label=turn_id,
        )
    return True


def _require_phase_inventory(
    cohort: PreparedV4Cohort,
    *,
    phase: str,
    expected_item_ids: Sequence[str],
) -> None:
    root = cohort.paths.root / "attempts" / phase
    actual = {path.parent.name for path in root.glob("*/outcome.json")} if root.exists() else set()
    expected = set(expected_item_ids)
    if actual != expected:
        raise V4EvaluationError(f"{phase} phase inventory changed")
    for item_id in expected_item_ids:
        if not _completed_turn(cohort.paths, turn_id=f"{phase}:{item_id}"):
            raise V4EvaluationError(f"{phase} phase missing {item_id}")


def _provider_metadata_from_outcome(outcome: Mapping[str, object]) -> Mapping[str, object]:
    provider = outcome.get("provider")
    return provider if isinstance(provider, Mapping) else {}


def _validate_sentinel_mechanics(paths: V4Paths, *, item_id: str) -> None:
    turn_id = f"generation:{item_id}"
    if not _completed_turn(paths, turn_id=turn_id):
        raise V4EvaluationError(f"sentinel item is incomplete: {item_id}")
    outcome = read_json_object(attempt_paths(paths, turn_id=turn_id)[2])
    citation = outcome.get("citation_audit")
    trace = outcome.get("retrieval_trace")
    if (
        outcome.get("query_embedding_provider_operations") != 0
        or outcome.get("provider_boundary_attempt_count") != 1
        or outcome.get("automatic_retries") != 0
        or not isinstance(citation, Mapping)
        or int(citation.get("malformed_bracket_token_count", -1)) != 0
        or int(citation.get("out_of_range_reference_count", -1)) != 0
        or not isinstance(trace, Mapping)
    ):
        raise V4EvaluationError(f"sentinel mechanics changed: {item_id}")
    try:
        validate_text_free_retrieval_trace(
            _validated_trace_for_contract(paths, item_id=item_id, trace=trace)
        )
    except (TypeError, ValueError) as exc:
        raise V4EvaluationError(f"sentinel retrieval trace is invalid: {item_id}") from exc


def _trace_scope_continuation_payload(
    paths: V4Paths,
    *,
    harness_commit: str,
    require_h011_unattempted: bool = True,
) -> dict[str, object]:
    outcomes: list[dict[str, object]] = []
    for item_id in SENTINEL_ITEM_IDS:
        outcome_path = attempt_paths(paths, turn_id=f"generation:{item_id}")[2]
        if not outcome_path.is_file():
            raise V4EvaluationError(f"trace continuation requires sealed {item_id}")
        outcome = read_json_object(outcome_path)
        trace = outcome.get("retrieval_trace")
        scope = trace.get("scope") if isinstance(trace, Mapping) else None
        original_turn_id = scope.get("turn_id") if isinstance(scope, Mapping) else None
        normalized_turn_id = f"generation-{item_id}"
        if original_turn_id != f"generation:{item_id}":
            raise V4EvaluationError(f"{item_id} trace scope is outside the declared defect")
        normalized = json.loads(json.dumps(trace))
        normalized["scope"]["turn_id"] = normalized_turn_id
        validate_text_free_retrieval_trace(normalized)
        outcomes.append(
            {
                "item_id": item_id,
                "outcome_file_sha256": sha256_file(outcome_path),
                "outcome_canonical_sha256": canonical_json_sha256(outcome),
                "original_trace_sha256": canonical_json_sha256(trace),
                "original_turn_id": original_turn_id,
                "normalized_trace_sha256": canonical_json_sha256(normalized),
                "normalized_turn_id": normalized_turn_id,
                "operation_evidence_sha256": canonical_json_sha256(
                    outcome["operation_evidence"]
                ),
            }
        )
    if require_h011_unattempted:
        h011_paths = attempt_paths(paths, turn_id="generation:H011")
        if any(path.exists() for path in h011_paths) or operation_evidence(
            paths,
            turn_id="generation:H011",
            operation="answer_generation",
        )["event_count"]:
            raise V4EvaluationError("H011 was attempted before trace-scope reconciliation")
    manifest = read_json_object(paths.cohort_manifest)
    return {
        "schema": V4_TRACE_SCOPE_CONTINUATION_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "cohort_manifest_file_sha256": sha256_file(paths.cohort_manifest),
        "cohort_manifest_canonical_sha256": canonical_json_sha256(manifest),
        "original_harness_commit": manifest["system_under_test"]["harness_commit"],
        "recovery_harness_commit": harness_commit,
        "normalization": "trace_scope_turn_id_colon_to_hyphen_v1",
        "provider_calls_made": 0,
        "sentinel_outcomes_rewritten": False,
        "next_item_id": "H011",
        "next_item_unattempted_at_reconciliation": True,
        "outcomes": outcomes,
    }


def reconcile_trace_scope_continuation(
    *,
    base_dir: Path,
    paths: V4Paths,
    product_commit: str,
    maximum_usd: Decimal,
) -> dict[str, object]:
    worktree = build_git_worktree_identity(base_dir)
    if worktree.get("working_tree") != "clean":
        raise V4EvaluationError("trace-scope reconciliation requires a clean tree")
    current_commit = _git_commit(base_dir)
    manifest = read_json_object(paths.cohort_manifest)
    cap_nano_usd = _nano_usd(maximum_usd)
    if (
        manifest.get("system_under_test", {}).get("product_commit")
        != product_commit
        or manifest.get("paid_scope", {}).get("maximum_total_cost_nano_usd")
        != cap_nano_usd
    ):
        raise V4EvaluationError("trace-scope reconciliation authorization changed")
    original_commit = _required_string(
        manifest.get("system_under_test", {}),
        "harness_commit",
    )
    if current_commit == original_commit:
        raise V4EvaluationError("trace-scope recovery must use a descendant harness commit")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", original_commit, current_commit],
        cwd=base_dir,
        check=False,
    )
    if ancestor.returncode != 0:
        raise V4EvaluationError("trace-scope recovery commit is not a harness descendant")
    payload = _trace_scope_continuation_payload(
        paths,
        harness_commit=current_commit,
    )
    write_or_validate_json(paths.trace_scope_continuation, payload)
    return payload


def _validated_trace_for_contract(
    paths: V4Paths,
    *,
    item_id: str,
    trace: Mapping[str, object],
) -> Mapping[str, object]:
    try:
        validate_text_free_retrieval_trace(trace)
        return trace
    except (TypeError, ValueError):
        if not paths.trace_scope_continuation.is_file():
            raise
    continuation = read_json_object(paths.trace_scope_continuation)
    manifest = read_json_object(paths.cohort_manifest)
    if (
        continuation.get("schema") != V4_TRACE_SCOPE_CONTINUATION_SCHEMA
        or continuation.get("evaluation_id") != EVALUATION_ID
        or continuation.get("cohort_manifest_file_sha256")
        != sha256_file(paths.cohort_manifest)
        or continuation.get("cohort_manifest_canonical_sha256")
        != canonical_json_sha256(manifest)
        or continuation.get("original_harness_commit")
        != manifest["system_under_test"]["harness_commit"]
        or continuation.get("normalization")
        != "trace_scope_turn_id_colon_to_hyphen_v1"
        or continuation.get("provider_calls_made") != 0
        or continuation.get("sentinel_outcomes_rewritten") is not False
        or continuation.get("next_item_id") != "H011"
        or continuation.get("next_item_unattempted_at_reconciliation") is not True
    ):
        raise V4EvaluationError("trace-scope continuation identity changed")
    expected = _trace_scope_continuation_payload(
        paths,
        harness_commit=_required_string(continuation, "recovery_harness_commit"),
        require_h011_unattempted=False,
    )
    if continuation != expected:
        raise V4EvaluationError("trace-scope continuation binding changed")
    entries = continuation.get("outcomes")
    entry = next(
        (
            value
            for value in entries
            if isinstance(value, Mapping) and value.get("item_id") == item_id
        ),
        None,
    ) if isinstance(entries, list) else None
    if entry is None or entry.get("original_trace_sha256") != canonical_json_sha256(trace):
        raise V4EvaluationError(f"{item_id} trace is not bound to the continuation")
    normalized = json.loads(json.dumps(trace))
    normalized["scope"]["turn_id"] = entry["normalized_turn_id"]
    if canonical_json_sha256(normalized) != entry.get("normalized_trace_sha256"):
        raise V4EvaluationError(f"{item_id} normalized trace binding changed")
    return normalized


def _normalize_generation_trace_scope(
    outcome: dict[str, object],
    *,
    item_id: str,
) -> None:
    trace = outcome.get("retrieval_trace")
    scope = trace.get("scope") if isinstance(trace, dict) else None
    if not isinstance(scope, dict):
        raise V4EvaluationError(f"{item_id} generation lost retrieval trace scope")
    original = scope.get("turn_id")
    if original not in {None, f"generation:{item_id}", f"generation-{item_id}"}:
        raise V4EvaluationError(f"{item_id} generation trace scope changed")
    if scope.get("project_id") is None:
        scope["project_id"] = MASTER_PROJECT_ID
    if scope.get("conversation_id") is None:
        scope["conversation_id"] = MASTER_CONVERSATION_ID
    scope["turn_id"] = f"generation-{item_id}"
    try:
        validate_text_free_retrieval_trace(trace)
    except (TypeError, ValueError) as exc:
        raise V4EvaluationError(
            f"{item_id} normalized generation trace is invalid"
        ) from exc


def run_professional_generation(
    cohort: PreparedV4Cohort,
    *,
    client: object,
    maximum_usd: Decimal,
    sentinel: bool,
) -> None:
    cap_nano = _nano_usd(maximum_usd)
    manifest_cap = int(cohort.manifest["paid_scope"]["maximum_total_cost_nano_usd"])
    if cap_nano != manifest_cap:
        raise V4EvaluationError("paid command cap must exactly match sealed manifest")
    recover_interrupted_attempts(cohort.paths, cap_nano_usd=cap_nano, cohort=cohort)
    if not sentinel:
        for item_id in SENTINEL_ITEM_IDS:
            _validate_sentinel_mechanics(cohort.paths, item_id=item_id)
    for item in _generation_items(cohort, sentinel=sentinel):
        item_id = _required_string(item, "id")
        turn_id = f"generation:{item_id}"
        if _completed_turn(cohort.paths, turn_id=turn_id):
            continue
        projection = generation_request_projection(cohort, item=item)
        intent = build_attempt_intent(
            cohort_manifest_sha256=canonical_json_sha256(cohort.manifest),
            turn_id=turn_id,
            item_id=item_id,
            phase="generation",
            projection=projection,
        )
        seal_boundary = prepare_attempt(
            cohort.paths,
            intent=intent,
            cap_nano_usd=cap_nano,
        )
        started = perf_counter_ns()
        failure: Exception | None = None
        try:
            with master_usage_scope(cohort.paths, cap_nano_usd=cap_nano, turn_id=turn_id):
                configured_client = client.with_options(
                    max_retries=0,
                    timeout=AUTHORED_AUTHORING_TIMEOUT_SECONDS,
                )
                exact_client = ExactRequestCapturingClient(
                    configured_client,
                    expected_projection=projection,
                    seal_boundary=seal_boundary,
                )
                outcome = generate_professional_item(
                    cohort.as_v3_retrieval_adapter(),
                    item=item,
                    client=exact_client,
                    require_provider_observation=False,
                )
        except Exception as exc:
            failure = exc
            _, marker, _ = attempt_paths(cohort.paths, turn_id=turn_id)
            if not marker.exists():
                raise
            from retrieval_authored_v3_evaluation import _local_technical_generation_outcome

            outcome = _local_technical_generation_outcome(
                cohort.as_v3_retrieval_adapter(),
                item=item,
                exc=exc,
            )
        latency_ms = (perf_counter_ns() - started) / 1_000_000
        evidence = operation_evidence(
            cohort.paths,
            turn_id=turn_id,
            operation="answer_generation",
        )
        provider = _provider_metadata_from_outcome(outcome)
        _, boundary_marker, _ = attempt_paths(cohort.paths, turn_id=turn_id)
        if not boundary_marker.exists():
            raise V4EvaluationError(f"{item_id} did not cross exactly one sealed boundary")
        if int(evidence["event_count"]) > 1:
            raise V4EvaluationError(f"{item_id} recorded more than one usage event")
        if evidence["event_count"] == 0:
            from retrieval_authored_v3_evaluation import _local_technical_generation_outcome

            fallback = _local_technical_generation_outcome(
                cohort.as_v3_retrieval_adapter(),
                item=item,
                exc=failure or RuntimeError("zero_event_usage_ambiguity"),
            )
            outcome = fallback
            outcome["status"] = "technical_failure"
            outcome["delivered_answer_status"] = "essential_fallback"
        outcome.update(
            {
                "schema": V4_GENERATION_OUTCOME_SCHEMA,
                "evaluation_id": EVALUATION_ID,
                "cohort_manifest_sha256": canonical_json_sha256(cohort.manifest),
                "intent_sha256": canonical_json_sha256(intent),
                "provider_boundary_attempt_count": 1,
                "automatic_retries": 0,
                "operation_evidence": evidence,
                "failure_category": (
                    "usage_contract_failure"
                    if evidence["event_count"] == 0
                    else (
                        None
                        if outcome.get("status") == "generated"
                        else classify_failure(
                            failure,
                            failure_code=outcome.get("failure_code"),
                        )
                    )
                ),
                "timings_ms": {
                    **dict(outcome.get("timings_ms") or {}),
                    "authoring_attempt_boundary": latency_ms,
                },
            }
        )
        _normalize_generation_trace_scope(outcome, item_id=item_id)
        if outcome.get("status") == "generated" and (
            not str(provider.get("response_id") or "").strip()
            or provider.get("model") != AUTHORED_RESPONSE_SETTINGS.model
        ):
            raise V4EvaluationError(f"{item_id} generated answer lacks provider identity")
        if provider.get("model") not in (None, AUTHORED_RESPONSE_SETTINGS.model):
            raise V4EvaluationError(f"{item_id} returned an unexpected model")
        settle_attempt(
            cohort.paths,
            intent=intent,
            outcome=outcome,
            cap_nano_usd=cap_nano,
        )


def run_professional_sentinel(
    cohort: PreparedV4Cohort,
    *,
    client: object,
    maximum_usd: Decimal,
) -> None:
    run_professional_generation(
        cohort,
        client=client,
        maximum_usd=maximum_usd,
        sentinel=True,
    )
    for item_id in SENTINEL_ITEM_IDS:
        _validate_sentinel_mechanics(cohort.paths, item_id=item_id)


def run_professional_remaining(
    cohort: PreparedV4Cohort,
    *,
    client: object,
    maximum_usd: Decimal,
) -> None:
    run_professional_generation(
        cohort,
        client=client,
        maximum_usd=maximum_usd,
        sentinel=False,
    )


def require_complete_generation(cohort: PreparedV4Cohort) -> None:
    _require_phase_inventory(
        cohort,
        phase="generation",
        expected_item_ids=[_required_string(item, "id") for item in cohort.items],
    )


def run_decomposition(
    cohort: PreparedV4Cohort,
    *,
    client: object,
    maximum_usd: Decimal,
) -> None:
    from evaluation_decomposition_v2 import (
        DECOMPOSITION_OPERATION,
        decompose_answer_claims_v2,
    )

    require_complete_generation(cohort)
    cap_nano = _nano_usd(maximum_usd)
    if cap_nano != int(cohort.manifest["paid_scope"]["maximum_total_cost_nano_usd"]):
        raise V4EvaluationError("paid command cap must exactly match sealed manifest")
    recover_interrupted_attempts(cohort.paths, cap_nano_usd=cap_nano, cohort=cohort)
    for item in cohort.items:
        item_id = _required_string(item, "id")
        turn_id = f"decomposition:{item_id}"
        if _completed_turn(cohort.paths, turn_id=turn_id):
            continue
        generation_path = attempt_paths(
            cohort.paths,
            turn_id=f"generation:{item_id}",
        )[2]
        generated = read_json_object(generation_path)
        answer = _required_string(generated, "answer")
        projection = decomposition_request_projection(item_id=item_id, answer=answer)
        intent = build_attempt_intent(
            cohort_manifest_sha256=canonical_json_sha256(cohort.manifest),
            turn_id=turn_id,
            item_id=item_id,
            phase="decomposition",
            projection=projection,
        )
        seal_boundary = prepare_attempt(
            cohort.paths,
            intent=intent,
            cap_nano_usd=cap_nano,
        )
        exact = ExactRequestCapturingClient(
            client.with_options(
                max_retries=0,
                timeout=DECOMPOSITION_TIMEOUT_SECONDS,
            ),
            expected_projection=projection,
            seal_boundary=seal_boundary,
        )
        started = perf_counter_ns()
        result = None
        failure: Exception | None = None
        try:
            with master_usage_scope(cohort.paths, cap_nano_usd=cap_nano, turn_id=turn_id):
                result = decompose_answer_claims_v2(exact, answer=answer)
        except Exception as exc:
            failure = exc
            _, marker, _ = attempt_paths(cohort.paths, turn_id=turn_id)
            if not marker.exists():
                raise
        latency_ms = (perf_counter_ns() - started) / 1_000_000
        evidence = operation_evidence(
            cohort.paths,
            turn_id=turn_id,
            operation=DECOMPOSITION_OPERATION,
        )
        if result is not None:
            outcome: dict[str, object] = {
                "schema": V4_DECOMPOSITION_OUTCOME_SCHEMA,
                "status": "valid",
                "claims": [claim.model_dump(mode="json") for claim in result.parsed.claims],
                "claim_count": len(result.parsed.claims),
                "provider": asdict(result.provider),
            }
        else:
            outcome = {
                "schema": V4_DECOMPOSITION_OUTCOME_SCHEMA,
                "status": "technical_failure",
                "failure_type": type(failure).__name__ if failure else "UnknownFailure",
                "failure_category": classify_failure(failure),
                "provider": None,
            }
        outcome.update(
            {
                "evaluation_id": EVALUATION_ID,
                "item_id": item_id,
                "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
                "intent_sha256": canonical_json_sha256(intent),
                "provider_boundary_attempt_count": 1,
                "automatic_retries": 0,
                "operation_evidence": evidence,
                "timings_ms": {"decomposition_boundary": latency_ms},
                "timeout_seconds": DECOMPOSITION_TIMEOUT_SECONDS,
            }
        )
        if evidence["event_count"] == 0:
            outcome["status"] = "technical_failure"
            outcome["failure_category"] = "usage_contract_failure"
            outcome.pop("claims", None)
            outcome.pop("claim_count", None)
        settle_attempt(
            cohort.paths,
            intent=intent,
            outcome=outcome,
            cap_nano_usd=cap_nano,
        )


def require_complete_decomposition(cohort: PreparedV4Cohort) -> None:
    require_complete_generation(cohort)
    _require_phase_inventory(
        cohort,
        phase="decomposition",
        expected_item_ids=[_required_string(item, "id") for item in cohort.items],
    )


def run_rubric(
    cohort: PreparedV4Cohort,
    *,
    client: object,
    maximum_usd: Decimal,
) -> None:
    """Score only valid decompositions after all 37 dispositions are sealed."""

    from evaluation_decomposition_v2 import (
        aggregate_gold_claim_coverage,
        judge_item_rubric_v2,
    )
    from evaluation_judge import AtomicClaim, ClaimDecomposition, build_item_rubric_input

    require_complete_decomposition(cohort)
    cap_nano = _nano_usd(maximum_usd)
    if cap_nano != int(cohort.manifest["paid_scope"]["maximum_total_cost_nano_usd"]):
        raise V4EvaluationError("paid command cap must exactly match sealed manifest")
    recover_interrupted_attempts(cohort.paths, cap_nano_usd=cap_nano, cohort=cohort)
    for item in cohort.items:
        item_id = _required_string(item, "id")
        turn_id = f"rubric:{item_id}"
        if _completed_turn(cohort.paths, turn_id=turn_id):
            continue
        generation = read_json_object(
            attempt_paths(cohort.paths, turn_id=f"generation:{item_id}")[2]
        )
        decomposition = read_json_object(
            attempt_paths(cohort.paths, turn_id=f"decomposition:{item_id}")[2]
        )
        answer = _required_string(generation, "answer")
        if decomposition.get("status") != "valid":
            intent = {
                "schema": V4_INTENT_SCHEMA,
                "evaluation_id": EVALUATION_ID,
                "cohort_manifest_sha256": canonical_json_sha256(cohort.manifest),
                "turn_id": turn_id,
                "item_id": item_id,
                "phase": "rubric",
                "attempt_count": 0,
                "automatic_retries": 0,
                "replacement": False,
                "request_projection": None,
            }
            intent_path, marker_path, outcome_path = attempt_paths(
                cohort.paths,
                turn_id=turn_id,
            )
            write_or_validate_json(intent_path, intent)
            write_or_validate_json(
                marker_path,
                {
                    "schema": V4_ATTEMPT_STARTED_SCHEMA,
                    "evaluation_id": EVALUATION_ID,
                    "turn_id": turn_id,
                    "intent_sha256": canonical_json_sha256(intent),
                    "provider_boundary_not_crossed": True,
                    "projected_worst_case_nano_usd": 0,
                },
            )
            write_or_validate_json(
                outcome_path,
                _no_boundary_rubric_outcome(cohort.paths, intent=intent),
            )
            continue
        raw_claims = decomposition.get("claims")
        if not isinstance(raw_claims, list):
            raise V4EvaluationError(f"{item_id} valid decomposition lost claims")
        claims = ClaimDecomposition(
            claims=[AtomicClaim.model_validate(value) for value in raw_claims]
        )
        rubric = build_item_rubric_input(
            question=_required_string(item, "question"),
            gold_item=item,
        )
        projection = rubric_request_projection(
            item_id=item_id,
            answer=answer,
            claims=raw_claims,
            rubric=rubric,
        )
        intent = build_attempt_intent(
            cohort_manifest_sha256=canonical_json_sha256(cohort.manifest),
            turn_id=turn_id,
            item_id=item_id,
            phase="rubric",
            projection=projection,
        )
        seal_boundary = prepare_attempt(
            cohort.paths,
            intent=intent,
            cap_nano_usd=cap_nano,
        )
        exact = ExactRequestCapturingClient(
            client.with_options(max_retries=0, timeout=DECOMPOSITION_TIMEOUT_SECONDS),
            expected_projection=projection,
            seal_boundary=seal_boundary,
        )
        started = perf_counter_ns()
        result = None
        failure: Exception | None = None
        try:
            with master_usage_scope(cohort.paths, cap_nano_usd=cap_nano, turn_id=turn_id):
                result = judge_item_rubric_v2(
                    exact,
                    answer=answer,
                    decomposition=claims,
                    rubric=rubric,
                )
        except Exception as exc:
            failure = exc
            _, marker, _ = attempt_paths(cohort.paths, turn_id=turn_id)
            if not marker.exists():
                raise
        latency_ms = (perf_counter_ns() - started) / 1_000_000
        evidence = operation_evidence(
            cohort.paths,
            turn_id=turn_id,
            operation="eval_item_rubric",
        )
        if result is not None:
            coverage = aggregate_gold_claim_coverage(
                rubric=rubric,
                verdict=result.parsed,
            )
            outcome: dict[str, object] = {
                "schema": V4_RUBRIC_OUTCOME_SCHEMA,
                "status": "scored",
                "coverage": asdict(coverage),
                "verdict": result.parsed.model_dump(mode="json"),
                "provider": asdict(result.provider),
            }
        else:
            outcome = {
                "schema": V4_RUBRIC_OUTCOME_SCHEMA,
                "status": "technical_failure",
                "failure_type": type(failure).__name__ if failure else "UnknownFailure",
                "failure_category": classify_failure(failure),
            }
        if evidence["event_count"] == 0:
            outcome = {
                "schema": V4_RUBRIC_OUTCOME_SCHEMA,
                "status": "technical_failure",
                "failure_type": "UsageEventContractFailure",
                "failure_category": "usage_contract_failure",
            }
        outcome.update(
            {
                "evaluation_id": EVALUATION_ID,
                "item_id": item_id,
                "answer_sha256": generation["answer_sha256"],
                "decomposition_sha256": canonical_json_sha256(decomposition),
                "intent_sha256": canonical_json_sha256(intent),
                "provider_boundary_attempt_count": 1,
                "automatic_retries": 0,
                "operation_evidence": evidence,
                "timings_ms": {"rubric_boundary": latency_ms},
            }
        )
        settle_attempt(
            cohort.paths,
            intent=intent,
            outcome=outcome,
            cap_nano_usd=cap_nano,
        )


def require_complete_rubric(cohort: PreparedV4Cohort) -> None:
    require_complete_decomposition(cohort)
    _require_phase_inventory(
        cohort,
        phase="rubric",
        expected_item_ids=[_required_string(item, "id") for item in cohort.items],
    )


def run_social_suite(
    cohort: PreparedV4Cohort,
    *,
    client: object,
    maximum_usd: Decimal,
) -> None:
    require_complete_rubric(cohort)
    cap_nano = _nano_usd(maximum_usd)
    if cap_nano != int(cohort.manifest["paid_scope"]["maximum_total_cost_nano_usd"]):
        raise V4EvaluationError("paid command cap must exactly match sealed manifest")
    recover_interrupted_attempts(cohort.paths, cap_nano_usd=cap_nano, cohort=cohort)
    unrouted = [
        (mode.value, ordinal)
        for mode in SOCIAL_MODES
        for ordinal, question in enumerate(SOCIAL_QUESTIONS, start=1)
        if not is_character_conversation_question(question, mode)
    ]
    if unrouted:
        raise V4EvaluationError(f"social cases do not reach product character route: {unrouted}")
    for mode in SOCIAL_MODES:
        for ordinal, question in enumerate(SOCIAL_QUESTIONS, start=1):
            item_id = f"{mode.value}-{ordinal:02d}"
            turn_id = f"social:{item_id}"
            if _completed_turn(cohort.paths, turn_id=turn_id):
                continue
            projection = social_request_projection(mode=mode, question=question)
            intent = build_attempt_intent(
                cohort_manifest_sha256=canonical_json_sha256(cohort.manifest),
                turn_id=turn_id,
                item_id=item_id,
                phase="social",
                projection=projection,
            )
            seal_boundary = prepare_attempt(
                cohort.paths,
                intent=intent,
                cap_nano_usd=cap_nano,
            )
            exact = ExactRequestCapturingClient(
                client.with_options(max_retries=0, timeout=SOCIAL_TIMEOUT_SECONDS),
                expected_projection=projection,
                seal_boundary=seal_boundary,
            )
            capturing = ProviderCapturingClient(exact)
            started = perf_counter_ns()
            failure: Exception | None = None
            try:
                with master_usage_scope(cohort.paths, cap_nano_usd=cap_nano, turn_id=turn_id):
                    result = generate_character_conversation(
                        capturing,
                        question=question,
                        mode=mode,
                    )
            except Exception as exc:
                failure = exc
                _, marker, _ = attempt_paths(cohort.paths, turn_id=turn_id)
                if not marker.exists():
                    raise
                result = deterministic_character_conversation_fallback(
                    mode,
                    CharacterConversationFailureCode.PROVIDER_FAILURE,
                )
            latency_ms = (perf_counter_ns() - started) / 1_000_000
            evidence = operation_evidence(
                cohort.paths,
                turn_id=turn_id,
                operation="answer_generation",
            )
            if evidence["event_count"] == 0:
                result = deterministic_character_conversation_fallback(
                    mode,
                    CharacterConversationFailureCode.PROVIDER_FAILURE,
                )
            provider_observations = [asdict(value) for value in capturing.observations]
            if result.status is CharacterConversationStatus.GENERATED and (
                len(provider_observations) != 1
                or provider_observations[0].get("model")
                != CHARACTER_CONVERSATION_SETTINGS.model
                or not provider_observations[0].get("response_id")
            ):
                raise V4EvaluationError(f"{item_id} generated social reply lacks provider identity")
            outcome = {
                "schema": V4_SOCIAL_OUTCOME_SCHEMA,
                "evaluation_id": EVALUATION_ID,
                "item_id": item_id,
                "mode": mode.value,
                "question_sha256": normalized_question_sha256(question),
                "status": result.status.value,
                "answer": result.answer,
                "answer_sha256": hashlib.sha256(result.answer.encode()).hexdigest(),
                "follow_up_count": len(result.follow_up_questions),
                "manuscript_leading_followups_valid": (
                    bool(result.follow_up_questions)
                    and all(
                        value.endswith("?")
                        and ("manuscript" in value.casefold() or "cradle of the empire" in value.casefold())
                        for value in result.follow_up_questions
                    )
                ),
                "failure_code": result.failure_code.value if result.failure_code else None,
                "failure_category": (
                    "usage_contract_failure"
                    if evidence["event_count"] == 0
                    else (
                        None
                        if result.status is CharacterConversationStatus.GENERATED
                        else classify_failure(failure, failure_code=result.failure_code)
                    )
                ),
                "provider_observations": provider_observations,
                "intent_sha256": canonical_json_sha256(intent),
                "provider_boundary_attempt_count": 1,
                "automatic_retries": 0,
                "operation_evidence": evidence,
                "timings_ms": {"social_boundary": latency_ms},
                "timeout_seconds": SOCIAL_TIMEOUT_SECONDS,
            }
            settle_attempt(
                cohort.paths,
                intent=intent,
                outcome=outcome,
                cap_nano_usd=cap_nano,
            )


def _percentile_nearest_rank(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def _latency_summary(values: Sequence[float]) -> dict[str, object]:
    if not values:
        return {"count": 0, "mean_ms": None, "median_ms": None, "p95_ms": None}
    return {
        "count": len(values),
        "mean_ms": sum(values) / len(values),
        "median_ms": median(values),
        "p95_ms": _percentile_nearest_rank(values, 0.95),
        "minimum_ms": min(values),
        "maximum_ms": max(values),
    }


def _words(value: str) -> frozenset[str]:
    return frozenset(token.casefold() for token in _TOKEN_RE.findall(value))


def _signature_hits(value: str, mode: ArchivistMode) -> tuple[str, ...]:
    normalized = value.casefold()
    return tuple(marker for marker in PERSONA_SIGNATURES[mode] if marker in normalized)


def _jaccard(left: str, right: str) -> float:
    left_words = _words(left)
    right_words = _words(right)
    union = left_words | right_words
    return 0.0 if not union else len(left_words & right_words) / len(union)


def _social_diagnostics(social: Sequence[Mapping[str, object]]) -> dict[str, object]:
    pairs: list[dict[str, object]] = []
    per_case: list[dict[str, object]] = []
    for value in social:
        mode = ArchivistMode(str(value["mode"]))
        answer = str(value.get("answer") or "")
        own = _signature_hits(answer, mode)
        foreign = {
            other.value: list(_signature_hits(answer, other))
            for other in SOCIAL_MODES
            if other is not mode and _signature_hits(answer, other)
        }
        per_case.append(
            {
                "item_id": value["item_id"],
                "mode": mode.value,
                "answer_sha256": value.get("answer_sha256"),
                "own_signature_hits": list(own),
                "foreign_signature_hits": foreign,
                "manuscript_leading_followups_valid": value.get(
                    "manuscript_leading_followups_valid"
                ),
                "character_signal": bool(own),
            }
        )
    for ordinal in range(1, len(SOCIAL_QUESTIONS) + 1):
        selected = [
            value
            for value in social
            if str(value.get("item_id", "")).endswith(f"-{ordinal:02d}")
        ]
        for index, left in enumerate(selected):
            for right in selected[index + 1 :]:
                pairs.append(
                    {
                        "case_ordinal": ordinal,
                        "left_mode": left["mode"],
                        "right_mode": right["mode"],
                        "token_jaccard": round(
                            _jaccard(str(left.get("answer") or ""), str(right.get("answer") or "")),
                            6,
                        ),
                    }
                )
    return {
        "method": (
            "transparent mode-signature hits and same-question pairwise token Jaccard; "
            "exploratory development diagnostic, not a semantic quality judge"
        ),
        "status_counts": dict(Counter(str(value.get("status")) for value in social)),
        "manuscript_leading_followup_pass_count": sum(
            value.get("manuscript_leading_followups_valid") is True for value in social
        ),
        "character_signal_count": sum(value["character_signal"] is True for value in per_case),
        "all_answers_unique": len(
            {str(value.get("answer_sha256")) for value in social}
        ) == len(social),
        "pairwise_same_question_token_jaccard": pairs,
        "cases": per_case,
    }


def _phase_outcomes(paths: V4Paths, phase: str) -> list[dict[str, object]]:
    root = paths.root / "attempts" / phase
    if not root.exists():
        return []
    return [read_json_object(path) for path in sorted(root.glob("*/outcome.json"))]


def require_complete_social(cohort: PreparedV4Cohort) -> None:
    require_complete_rubric(cohort)
    expected = {
        f"{mode.value}-{ordinal:02d}"
        for mode in SOCIAL_MODES
        for ordinal in range(1, len(SOCIAL_QUESTIONS) + 1)
    }
    _require_phase_inventory(
        cohort,
        phase="social",
        expected_item_ids=sorted(expected),
    )


def _aggregate_retrieval_stage(
    generations: Sequence[Mapping[str, object]],
    *,
    stage: str,
    k: str | None = None,
) -> dict[str, object]:
    metrics: list[Mapping[str, object]] = []
    for value in generations:
        retrieval = value.get("retrieval")
        if not isinstance(retrieval, Mapping):
            continue
        if k is not None:
            by_k = retrieval.get("primary_by_k")
            raw = by_k.get(k) if isinstance(by_k, Mapping) else None
        else:
            raw = retrieval.get(stage)
        metric = raw.get("metrics") if isinstance(raw, Mapping) else None
        if isinstance(metric, Mapping):
            metrics.append(metric)
    recall_values = [float(value["recall"]) for value in metrics if value.get("recall") is not None]
    hit_values = [bool(value["hit"]) for value in metrics if value.get("hit") is not None]
    essential_values = [
        float(value["essential_coverage"])
        for value in metrics
        if value.get("essential_coverage") is not None
    ]
    relevant = sum(int(value.get("relevant_count", 0)) for value in metrics)
    overlap = sum(int(value.get("retrieved_relevant_count", 0)) for value in metrics)
    essential = sum(int(value.get("essential_claim_count", 0)) for value in metrics)
    essential_covered = sum(
        int(value.get("covered_essential_claim_count", 0)) for value in metrics
    )
    return {
        "applicable_item_count": len(recall_values),
        "essential_applicable_item_count": len(essential_values),
        "macro_recall": sum(recall_values) / len(recall_values) if recall_values else None,
        "micro_recall": overlap / relevant if relevant else None,
        "hit_rate": sum(hit_values) / len(hit_values) if hit_values else None,
        "macro_essential_context_coverage": (
            sum(essential_values) / len(essential_values) if essential_values else None
        ),
        "micro_essential_context_coverage": (
            essential_covered / essential if essential else None
        ),
        "retrieved_relevant_count": overlap,
        "relevant_count": relevant,
        "covered_essential_claim_count": essential_covered,
        "essential_claim_count": essential,
    }


def _retrieval_diagnostics(
    generations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    displacement: Counter[str] = Counter()
    raw_primary = 0
    fusion_pool = 0
    for value in generations:
        retrieval = value.get("retrieval")
        if not isinstance(retrieval, Mapping):
            continue
        fallbacks = retrieval.get("fallbacks")
        if isinstance(fallbacks, Mapping):
            raw_primary += fallbacks.get("raw_primary_fallback_used") is True
            fusion_pool += fallbacks.get("fusion_pool_fallback_used") is True
        counts = retrieval.get("displacement_counts")
        if isinstance(counts, Mapping):
            for cause, count in counts.items():
                displacement[str(cause)] += int(count)
    return {
        "raw_primary_fallback_item_count": raw_primary,
        "fusion_pool_fallback_item_count": fusion_pool,
        "candidate_displacement_counts": dict(sorted(displacement.items())),
    }


def _cost_breakdown(paths: V4Paths) -> dict[str, object]:
    phases = {
        phase: {
            "tracked_event_count": 0,
            "tracked_cost_nano_usd": 0,
            "reserved_attempt_count": 0,
            "reserved_cost_nano_usd": 0,
        }
        for phase in ("generation", "decomposition", "rubric", "social")
    }
    if paths.ledger.exists():
        with closing(sqlite3.connect(paths.ledger)) as connection:
            rows = connection.execute(
                """
                SELECT turn_id, estimated_cost_nano_usd
                FROM usage_events
                WHERE request_id = ?
                ORDER BY id
                """,
                (MASTER_REQUEST_ID,),
            ).fetchall()
        for turn_id, cost in rows:
            phase = str(turn_id).partition(":")[0]
            if phase not in phases:
                raise V4EvaluationError("cost breakdown contains a foreign phase")
            phases[phase]["tracked_event_count"] += 1
            phases[phase]["tracked_cost_nano_usd"] += int(cost)
    for path in _reservation_files(paths):
        reservation = read_json_object(path)
        phase = _required_string(reservation, "phase")
        if phase not in phases:
            raise V4EvaluationError("reservation cost breakdown contains a foreign phase")
        phases[phase]["reserved_attempt_count"] += 1
        phases[phase]["reserved_cost_nano_usd"] += int(
            reservation["reserved_nano_usd"]
        )
    for values in phases.values():
        values["tracked_cost_usd_exact"] = exact_usd(
            int(values["tracked_cost_nano_usd"])
        )
        values["reserved_cost_usd_exact"] = exact_usd(
            int(values["reserved_cost_nano_usd"])
        )
    return phases


def _assert_report_contains_no_private_text(
    report: Mapping[str, object],
    *,
    cohort: PreparedV4Cohort,
    generations: Sequence[Mapping[str, object]],
    social: Sequence[Mapping[str, object]],
) -> None:
    rendered = canonical_json_bytes(report).decode("utf-8")
    private_values: list[str] = [
        _required_string(item, "question") for item in cohort.items
    ]
    private_values.extend(
        str(value.get("answer") or "") for value in (*generations, *social)
    )
    for value in generations:
        dossier = value.get("dossier")
        units = dossier.get("model_visible_units") if isinstance(dossier, Mapping) else None
        if isinstance(units, list):
            private_values.extend(
                str(unit.get("text") or "")
                for unit in units
                if isinstance(unit, Mapping)
            )
    if any(value and value in rendered for value in private_values):
        raise V4EvaluationError("public report contains private evaluation text")


def build_text_free_report(
    cohort: PreparedV4Cohort,
    *,
    maximum_usd: Decimal,
) -> dict[str, object]:
    require_complete_social(cohort)
    cap_nano = _nano_usd(maximum_usd)
    generations = _phase_outcomes(cohort.paths, "generation")
    decompositions = _phase_outcomes(cohort.paths, "decomposition")
    rubrics = _phase_outcomes(cohort.paths, "rubric")
    social = _phase_outcomes(cohort.paths, "social")
    generation_latencies = [
        float(value["timings_ms"]["authoring_attempt_boundary"])
        for value in generations
        if isinstance(value.get("timings_ms"), Mapping)
        and value["timings_ms"].get("authoring_attempt_boundary") is not None
    ]
    generated_latencies = [
        float(value["timings_ms"]["authoring_attempt_boundary"])
        for value in generations
        if value.get("status") == "generated"
        and isinstance(value.get("timings_ms"), Mapping)
        and value["timings_ms"].get("authoring_attempt_boundary") is not None
    ]
    fallback_latencies = [
        float(value["timings_ms"]["authoring_attempt_boundary"])
        for value in generations
        if value.get("status") != "generated"
        and isinstance(value.get("timings_ms"), Mapping)
        and value["timings_ms"].get("authoring_attempt_boundary") is not None
    ]
    decomposition_latencies = [
        float(value["timings_ms"]["decomposition_boundary"])
        for value in decompositions
        if isinstance(value.get("timings_ms"), Mapping)
        and value["timings_ms"].get("decomposition_boundary") is not None
    ]
    citation_groups = 0
    citation_references = 0
    malformed = 0
    out_of_range = 0
    for value in generations:
        audit = value.get("citation_audit")
        if isinstance(audit, Mapping):
            citation_groups += int(audit.get("well_formed_group_count", 0))
            citation_references += int(audit.get("source_reference_count", 0))
            malformed += int(audit.get("malformed_bracket_token_count", 0))
            out_of_range += int(audit.get("out_of_range_reference_count", 0))
    valid_claims = [
        claim
        for value in decompositions
        if value.get("status") == "valid" and isinstance(value.get("claims"), list)
        for claim in value["claims"]
        if isinstance(claim, Mapping)
    ]
    claims_with_citations = sum(bool(claim.get("cited_sources")) for claim in valid_claims)
    cited_gold_matches = sum(
        int(value.get("cited_source_gold_location_matches", 0)) for value in generations
    )
    cited_gold_total = sum(
        int(value.get("cited_source_gold_location_total", 0)) for value in generations
    )
    coverage_values = [
        value["coverage"]
        for value in rubrics
        if value.get("status") == "scored" and isinstance(value.get("coverage"), Mapping)
    ]

    def coverage_total(field: str) -> int:
        return sum(int(value.get(field, 0)) for value in coverage_values)

    all_present = coverage_total("all_present")
    all_total = coverage_total("all_total")
    essential_present = coverage_total("essential_present")
    essential_total = coverage_total("essential_total")
    must_not_asserted = coverage_total("must_not_claim_asserted")
    must_not_total = coverage_total("must_not_claim_total")
    cost_state = budget_state(cohort.paths, cap_nano_usd=cap_nano)
    report = {
        "schema": V4_PUBLIC_REPORT_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "cohort_manifest_sha256": canonical_json_sha256(cohort.manifest),
        "classification": COHORT_CLASSIFICATION,
        "generation": {
            "sealed_count": len(generations),
            "expected_count": len(cohort.items),
            "generated_count": sum(value.get("status") == "generated" for value in generations),
            "fallback_or_failure_count": sum(
                value.get("status") != "generated" for value in generations
            ),
            "delivered_essential_fallback_count": sum(
                value.get("delivered_answer_status") == "essential_fallback"
                or value.get("status") == "essential_fallback"
                for value in generations
            ),
            "status_counts": dict(
                Counter(str(value.get("status")) for value in generations)
            ),
            "disposition_counts": dict(
                Counter(str(value.get("disposition")) for value in generations)
            ),
            "sentinel_sealed_count": sum(
                str(value.get("item_id")) in SENTINEL_ITEM_IDS for value in generations
            ),
            "sentinel_quality_or_latency_veto_applied": False,
            "latency_definition": (
                "authoring_attempt_boundary includes the actual v4 authoring attempt and "
                "local validation; it excludes cached-vector retrieval and excludes any "
                "later deterministic fallback reconstruction"
            ),
            "latency": {
                "all_attempts": _latency_summary(generation_latencies),
                "generated": _latency_summary(generated_latencies),
                "fallback_or_failure": _latency_summary(fallback_latencies),
                "unavailable_count": len(generations) - len(generation_latencies),
            },
            "failure_categories": {
                category: sum(value.get("failure_category") == category for value in generations)
                for category in sorted(FAILURE_CATEGORIES)
            },
        },
        "retrieval": {
            "primary_by_k": {
                k: _aggregate_retrieval_stage(generations, stage="primary", k=k)
                for k in ("1", "3", "5", "8", "10", "20")
            },
            "finalized": _aggregate_retrieval_stage(generations, stage="finalized"),
            "dossier": _aggregate_retrieval_stage(generations, stage="dossier"),
            "cited": _aggregate_retrieval_stage(generations, stage="cited"),
            "fallbacks_and_displacement": _retrieval_diagnostics(generations),
        },
        "citations": {
            "well_formed_group_count": citation_groups,
            "source_reference_count": citation_references,
            "malformed_bracket_token_count": malformed,
            "out_of_range_reference_count": out_of_range,
            "locally_resolvable_source_reference_count": (
                citation_references - out_of_range
            ),
            "all_source_references_locally_resolvable": out_of_range == 0,
            "decomposed_claim_with_citation_count": claims_with_citations,
            "decomposed_factual_claim_count": len(valid_claims),
            "citation_completeness": (
                claims_with_citations / len(valid_claims) if valid_claims else None
            ),
            "cited_source_gold_location_matches": cited_gold_matches,
            "cited_source_gold_location_total": cited_gold_total,
            "cited_source_gold_location_match_rate": (
                cited_gold_matches / cited_gold_total if cited_gold_total else None
            ),
            "semantic_entailment_measured": False,
        },
        "decomposition": {
            "sealed_count": len(decompositions),
            "valid_count": sum(value.get("status") == "valid" for value in decompositions),
            "technical_failure_count": sum(
                value.get("status") == "technical_failure" for value in decompositions
            ),
            "claim_count": sum(int(value.get("claim_count", 0)) for value in decompositions),
            "timeout_seconds": DECOMPOSITION_TIMEOUT_SECONDS,
            "latency": _latency_summary(decomposition_latencies),
        },
        "rubric": {
            "measurement_status": "exploratory_uncalibrated",
            "sealed_count": len(rubrics),
            "scored_count": sum(value.get("status") == "scored" for value in rubrics),
            "technical_failure_count": sum(
                value.get("status") == "technical_failure" for value in rubrics
            ),
            "not_scored_decomposition_failure_count": sum(
                value.get("status") == "not_scored_decomposition_failure"
                for value in rubrics
            ),
            "gold_claim_coverage": {
                "all_present": all_present,
                "all_total": all_total,
                "all_present_rate": all_present / all_total if all_total else None,
                "all_absent": coverage_total("all_absent"),
                "all_contradicted": coverage_total("all_contradicted"),
                "essential_present": essential_present,
                "essential_total": essential_total,
                "essential_present_rate": (
                    essential_present / essential_total if essential_total else None
                ),
                "essential_absent": coverage_total("essential_absent"),
                "essential_contradicted": coverage_total("essential_contradicted"),
                "must_not_claim_asserted": must_not_asserted,
                "must_not_claim_total": must_not_total,
                "must_not_claim_assertion_rate": (
                    must_not_asserted / must_not_total if must_not_total else None
                ),
            },
        },
        "social_suite": {
            "separate": True,
            "measurement_status": "exploratory_non_gold_character_diagnostics",
            "sealed_count": len(social),
            "expected_count": len(SOCIAL_MODES) * len(SOCIAL_QUESTIONS),
            "modes": [
                {
                    "mode": value.get("mode"),
                    "status": value.get("status"),
                    "answer_sha256": value.get("answer_sha256"),
                    "follow_up_count": value.get("follow_up_count"),
                    "failure_category": value.get("failure_category"),
                    "latency_ms": (
                        value.get("timings_ms", {}).get("social_boundary")
                        if isinstance(value.get("timings_ms"), Mapping)
                        else None
                    ),
                }
                for value in social
            ],
            "behavior_diagnostics": _social_diagnostics(social),
        },
        "cost": {
            **cost_state,
            "by_phase": _cost_breakdown(cohort.paths),
        },
        "privacy": {
            "contains_question_text": False,
            "contains_answer_text": False,
            "contains_manuscript_text": False,
            "contains_source_excerpt_text": False,
        },
    }
    _assert_report_contains_no_private_text(
        report,
        cohort=cohort,
        generations=generations,
        social=social,
    )
    return report


def write_text_free_report(
    cohort: PreparedV4Cohort,
    *,
    maximum_usd: Decimal,
) -> dict[str, object]:
    report = build_text_free_report(cohort, maximum_usd=maximum_usd)
    write_or_validate_json(cohort.paths.report, report)
    return report


__all__ = [
    "DECOMPOSITION_TIMEOUT_SECONDS",
    "EVALUATION_ID",
    "MAXIMUM_DESIGN_CAP_USD",
    "MASTER_REQUEST_ID",
    "PreparedV4Cohort",
    "SENTINEL_ITEM_IDS",
    "SOCIAL_MODES",
    "V4EvaluationError",
    "V4Paths",
    "atomic_seal_json",
    "budget_state",
    "build_attempt_intent",
    "build_text_free_report",
    "build_v4_manifest",
    "classify_failure",
    "default_paths",
    "operation_evidence",
    "preflight",
    "prepare_attempt",
    "prepare_v4_cohort",
    "project_request",
    "reconcile_trace_scope_continuation",
    "reserve_zero_event",
    "run_decomposition",
    "run_professional_remaining",
    "run_professional_sentinel",
    "run_social_suite",
    "settle_attempt",
    "write_text_free_report",
]
