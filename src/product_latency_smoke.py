"""A three-question, provider-safe latency smoke for the current product path.

The smoke is deliberately separate from answer-quality evaluation.  It sends
three already-registered development questions through Professional as fresh
first turns, records operational measurements without answer or manuscript
text, and never retries or resumes an ambiguous provider attempt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from uuid import uuid4

from archivist_modes import ArchivistMode
from authored_response import (
    AUTHORED_ANSWER_LENGTH_POLICY_VERSION,
    AUTHORED_RESPONSE_INPUT_SCHEMA,
    AUTHORED_RESPONSE_OUTPUT_SCHEMA,
    AUTHORED_RESPONSE_POLICY_VERSION,
    AUTHORED_RESPONSE_SETTINGS,
    authored_response_prompt_metadata,
)
from costs import (
    PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD,
    PUBLIC_RAG_REQUEST_COST_CEILING_VERSION,
    UsageLedger,
    usage_scope,
)
from gold_provenance import (
    normalized_question_sha256,
    validate_development_registry,
)
from evidence_dossier import (
    DEFAULT_HARD_EVIDENCE_TOKEN_LIMIT,
    DEFAULT_MAX_DOSSIER_UNITS,
    DEFAULT_MIN_DOSSIER_UNITS,
    DEFAULT_TARGET_EVIDENCE_TOKENS,
)
from public_telemetry import PUBLIC_EMBEDDING_MODEL, PUBLIC_EVIDENCE_RETRIEVAL_KIND
from query_planning import RouteTrait, route_question


BASE_DIR = Path(__file__).resolve().parent.parent
QUESTION_FIXTURE = BASE_DIR / "fixtures" / "product_latency_smoke_questions.json"
DEVELOPMENT_REGISTRY = BASE_DIR / "fixtures" / "development_question_registry.json"
CORPUS_MANIFEST = BASE_DIR / "fixtures" / "corpus_manifest.json"
SMOKE_ROOT = BASE_DIR / "runtime" / "evaluations" / "product-latency-smoke-v1"

PROTOCOL_VERSION = "product-latency-smoke-v1"
QUESTION_FIXTURE_SCHEMA = "archivist.product_latency_smoke_questions/1"
PREPARED_SCHEMA = "archivist.product_latency_smoke_manifest/1"
ATTEMPT_INTENT_SCHEMA = "archivist.product_latency_smoke_attempt_intent/1"
ATTEMPT_OUTCOME_SCHEMA = "archivist.product_latency_smoke_attempt_outcome/1"
REPORT_SCHEMA = "archivist.product_latency_smoke_report/1"
EXPECTED_QUESTION_COUNT = 3
EXPECTED_PROFILE_COUNTS = {"ordinary": 2, "broad": 1}
EXPECTED_PROVIDER_OPERATIONS = {
    "answer_generation": 1,
    "query_embedding": 1,
}
PER_ATTEMPT_COST_CEILING_NANO_USD = PUBLIC_RAG_REQUEST_COST_CEILING_NANO_USD
AGGREGATE_HARD_CEILING_NANO_USD = (
    EXPECTED_QUESTION_COUNT * PER_ATTEMPT_COST_CEILING_NANO_USD
)


class ProductLatencySmokeError(RuntimeError):
    """The latency smoke could no longer prove its closed execution contract."""


@dataclass(frozen=True, slots=True)
class LatencyQuestion:
    ordinal: int
    item_id: str
    question: str
    question_sha256: str
    expected_profile: str

    def text_free_binding(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "item_id": self.item_id,
            "question_sha256": self.question_sha256,
            "expected_answer_length_profile": self.expected_profile,
        }


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _sealed(value: Mapping[str, object]) -> dict[str, object]:
    payload = dict(value)
    payload.pop("artifact_sha256", None)
    payload["artifact_sha256"] = hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()
    return payload


def _write_json_no_overwrite(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
    except FileExistsError as exc:
        raise ProductLatencySmokeError(
            f"refusing to overwrite latency-smoke artifact: {path.name}"
        ) from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _usd_string(nano_usd: int) -> str:
    return f"{Decimal(nano_usd) / Decimal('1000000000'):.9f}"


def _nano_from_usd(value: Decimal) -> int:
    return int((value * Decimal("1000000000")).to_integral_exact())


def validate_authorization(*, authorized: bool, maximum_usd: Decimal) -> int:
    """Validate the explicit, exact worst-case authorization before local setup."""

    if not authorized:
        raise ProductLatencySmokeError(
            "live latency smoke requires --authorize-openai-latency-smoke"
        )
    if not maximum_usd.is_finite() or maximum_usd.as_tuple().exponent < -9:
        raise ProductLatencySmokeError(
            "--max-total-cost-usd must be finite with at most 9 decimals"
        )
    try:
        maximum_nano = _nano_from_usd(maximum_usd)
    except (InvalidOperation, ValueError) as exc:
        raise ProductLatencySmokeError("invalid --max-total-cost-usd") from exc
    if maximum_nano < AGGREGATE_HARD_CEILING_NANO_USD:
        raise ProductLatencySmokeError(
            "--max-total-cost-usd must cover three fixed public request ceilings ($6.00)"
        )
    if maximum_nano > AGGREGATE_HARD_CEILING_NANO_USD:
        raise ProductLatencySmokeError(
            "--max-total-cost-usd cannot exceed this smoke's fixed $6.00 ceiling"
        )
    return maximum_nano


def _validated_run_root(path: Path, *, smoke_root: Path) -> Path:
    resolved = path.resolve()
    allowed = smoke_root.resolve()
    if resolved == allowed or allowed not in resolved.parents:
        raise ProductLatencySmokeError(
            "--run-root must be a new child of runtime/evaluations/product-latency-smoke-v1"
        )
    if resolved.exists():
        raise ProductLatencySmokeError(
            "--run-root already exists; ambiguous attempts are never resumed or replayed"
        )
    return resolved


def _read_json(path: Path, *, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductLatencySmokeError(f"could not read {label}") from exc


def load_latency_questions(
    *,
    question_fixture: Path = QUESTION_FIXTURE,
    development_registry: Path = DEVELOPMENT_REGISTRY,
) -> tuple[LatencyQuestion, ...]:
    """Bind the three prompts to the validated non-held-out development registry."""

    registry_value = _read_json(development_registry, label="development registry")
    registry = validate_development_registry(registry_value)
    registry_by_id = {item.question_id: item for item in registry.questions}

    fixture = _read_json(question_fixture, label="latency question fixture")
    if not isinstance(fixture, Mapping):
        raise ProductLatencySmokeError("latency question fixture must be an object")
    if set(fixture) != {"schema", "development_registry_version", "questions"}:
        raise ProductLatencySmokeError("latency question fixture fields changed")
    if fixture.get("schema") != QUESTION_FIXTURE_SCHEMA:
        raise ProductLatencySmokeError("latency question fixture schema changed")
    if fixture.get("development_registry_version") != registry.version:
        raise ProductLatencySmokeError("latency fixture registry version does not match")
    raw_questions = fixture.get("questions")
    if not isinstance(raw_questions, list) or len(raw_questions) != EXPECTED_QUESTION_COUNT:
        raise ProductLatencySmokeError("latency fixture must contain exactly three questions")

    selected: list[LatencyQuestion] = []
    seen_ids: set[str] = set()
    for ordinal, raw in enumerate(raw_questions, start=1):
        if not isinstance(raw, Mapping) or set(raw) != {
            "id",
            "question",
            "normalized_sha256",
            "expected_answer_length_profile",
        }:
            raise ProductLatencySmokeError("latency question fields changed")
        item_id = raw.get("id")
        question = raw.get("question")
        digest = raw.get("normalized_sha256")
        expected_profile = raw.get("expected_answer_length_profile")
        if not isinstance(item_id, str) or not isinstance(question, str):
            raise ProductLatencySmokeError("latency question ID and text must be strings")
        if item_id.startswith("H") or item_id in seen_ids:
            raise ProductLatencySmokeError("held-out or duplicate latency question ID")
        seen_ids.add(item_id)
        registry_item = registry_by_id.get(item_id)
        if (
            registry_item is None
            or registry_item.question != question
            or registry_item.normalized_sha256 != digest
            or normalized_question_sha256(question) != digest
        ):
            raise ProductLatencySmokeError(
                f"latency question {item_id} is not exactly registry-bound"
            )
        routed_profile = (
            "broad"
            if RouteTrait.BROAD_SYNTHESIS in route_question(question)
            else "ordinary"
        )
        if expected_profile != routed_profile:
            raise ProductLatencySmokeError(
                f"latency question {item_id} no longer routes to its frozen profile"
            )
        selected.append(
            LatencyQuestion(
                ordinal=ordinal,
                item_id=item_id,
                question=question,
                question_sha256=str(digest),
                expected_profile=routed_profile,
            )
        )
    if Counter(item.expected_profile for item in selected) != EXPECTED_PROFILE_COUNTS:
        raise ProductLatencySmokeError("latency fixture must remain two ordinary and one broad")
    return tuple(selected)


def clean_git_identity(*, base_dir: Path = BASE_DIR) -> dict[str, str]:
    """Return the clean committed identity required for an interpretable smoke."""

    def git(*args: str) -> str:
        try:
            return subprocess.check_output(
                ["git", *args],
                cwd=base_dir,
                text=True,
                encoding="utf-8",
                stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ProductLatencySmokeError("could not bind git identity") from exc

    commit = git("rev-parse", "HEAD")
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise ProductLatencySmokeError("git HEAD is not a full commit hash")
    if git("status", "--porcelain", "--untracked-files=all"):
        raise ProductLatencySmokeError(
            "latency smoke requires a clean committed working tree"
        )
    return {"commit": commit, "working_tree": "clean"}


def _prepared_manifest(
    *,
    questions: Sequence[LatencyQuestion],
    maximum_nano: int,
    identity: Mapping[str, str],
    question_fixture: Path,
    development_registry: Path,
) -> dict[str, object]:
    return _sealed(
        {
            "schema": PREPARED_SCHEMA,
            "protocol_version": PROTOCOL_VERSION,
            "system_identity": {
                **dict(identity),
                "answer_policy_version": AUTHORED_RESPONSE_POLICY_VERSION,
                "authored_response_input_schema": AUTHORED_RESPONSE_INPUT_SCHEMA,
                "answer_length_policy_version": AUTHORED_ANSWER_LENGTH_POLICY_VERSION,
                "requested_model": AUTHORED_RESPONSE_SETTINGS.model,
                "reasoning_effort": AUTHORED_RESPONSE_SETTINGS.reasoning_effort,
                "verbosity": AUTHORED_RESPONSE_SETTINGS.verbosity,
                "mode": ArchivistMode.PROFESSIONAL.value,
                "turn_context": "fresh_first_turn",
                "authored_response_output_schema": AUTHORED_RESPONSE_OUTPUT_SCHEMA,
                "authored_response_prompt": authored_response_prompt_metadata(
                    ArchivistMode.PROFESSIONAL
                ),
                "evidence_retrieval_kind": PUBLIC_EVIDENCE_RETRIEVAL_KIND,
                "embedding_model": PUBLIC_EMBEDDING_MODEL,
                "retrieval_dossier": {
                    "minimum_units": DEFAULT_MIN_DOSSIER_UNITS,
                    "maximum_units": DEFAULT_MAX_DOSSIER_UNITS,
                    "target_evidence_tokens": DEFAULT_TARGET_EVIDENCE_TOKENS,
                    "hard_evidence_token_limit": DEFAULT_HARD_EVIDENCE_TOKEN_LIMIT,
                },
                "question_fixture_sha256": _sha256_file(question_fixture),
                "development_registry_sha256": _sha256_file(development_registry),
                "corpus_manifest_sha256": _sha256_file(CORPUS_MANIFEST),
                "dependency_lock_sha256": _sha256_file(BASE_DIR / "uv.lock"),
            },
            "execution_contract": {
                "attempt_count": EXPECTED_QUESTION_COUNT,
                "automatic_retries": 0,
                "resume_allowed": False,
                "expected_provider_operations_per_attempt": dict(
                    EXPECTED_PROVIDER_OPERATIONS
                ),
                "request_cost_ceiling_version": (
                    PUBLIC_RAG_REQUEST_COST_CEILING_VERSION
                ),
                "per_attempt_cost_ceiling_nano_usd": (
                    PER_ATTEMPT_COST_CEILING_NANO_USD
                ),
                "aggregate_hard_ceiling_nano_usd": (
                    AGGREGATE_HARD_CEILING_NANO_USD
                ),
                "authorized_cost_nano_usd": maximum_nano,
                "authorized_cost_usd": _usd_string(maximum_nano),
            },
            "questions": [question.text_free_binding() for question in questions],
        }
    )


@contextmanager
def _isolated_usage_database(path: Path):
    previous = os.environ.get("ARCHIVIST_USAGE_DB")
    os.environ["ARCHIVIST_USAGE_DB"] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("ARCHIVIST_USAGE_DB", None)
        else:
            os.environ["ARCHIVIST_USAGE_DB"] = previous


def _default_answer_runner(
    question: str,
    *,
    archivist_mode: ArchivistMode,
    history: Sequence[Mapping[str, object]],
    application_compiled: bool,
) -> object:
    # Import lazily so authorization, fixture validation, identity validation,
    # and the immutable prepared checkpoint all precede product/client setup.
    from web_project import answer_project_question_result

    return answer_project_question_result(
        "current",
        question,
        archivist_mode=archivist_mode,
        history=history,
        application_compiled=application_compiled,
    )


def _usage_snapshot(
    ledger: UsageLedger,
    request_id: str,
) -> tuple[dict[str, object], dict[str, int]]:
    try:
        totals = ledger.request_usage_totals(request_id)
        state = ledger.request_usage_cost_state(request_id)
    except Exception as exc:
        raise ProductLatencySmokeError("usage ledger could not be read") from exc
    return dict(totals), dict(state)


def _safe_generation_trace(result: object) -> dict[str, object]:
    diagnostics = getattr(result, "diagnostics", None)
    if not isinstance(diagnostics, Mapping):
        return {}
    generation = diagnostics.get("generation")
    return dict(generation) if isinstance(generation, Mapping) else {}


def _safe_stage_timings(result: object) -> dict[str, float]:
    diagnostics = getattr(result, "diagnostics", None)
    raw = diagnostics.get("stage_timings_ms") if isinstance(diagnostics, Mapping) else None
    if not isinstance(raw, Mapping):
        return {}
    timings: dict[str, float] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, (int, float)) and value >= 0:
            timings[key] = round(float(value), 3)
    return timings


def _outcome(
    *,
    question: LatencyQuestion,
    request_id: str,
    measurement_status: str,
    wall_latency_ms: float,
    usage: Mapping[str, object],
    state: Mapping[str, int] | None,
    result: object | None = None,
    error_class: str | None = None,
) -> dict[str, object]:
    generation = _safe_generation_trace(result) if result is not None else {}
    answer = getattr(result, "answer", None) if result is not None else None
    final_chunks = getattr(result, "final_chunks", ()) if result is not None else ()
    source_count = len(final_chunks) if isinstance(final_chunks, Sequence) else 0
    product_status = getattr(result, "status", None) if result is not None else None
    answer_text = answer if isinstance(answer, str) else ""
    cost_nano = int(state.get("estimated_cost_nano_usd", 0)) if state else 0
    return _sealed(
        {
            "schema": ATTEMPT_OUTCOME_SCHEMA,
            "ordinal": question.ordinal,
            "item_id": question.item_id,
            "question_sha256": question.question_sha256,
            "request_id": request_id,
            "measurement_status": measurement_status,
            "product_status": product_status,
            "fallback_code": generation.get("fallback_code"),
            "expected_answer_length_profile": question.expected_profile,
            "observed_answer_length_profile": generation.get(
                "answer_length_profile"
            ),
            "wall_latency_ms": round(max(0.0, wall_latency_ms), 3),
            "stage_timings_ms": _safe_stage_timings(result) if result is not None else {},
            "source_count": source_count,
            "answer_sha256": (
                hashlib.sha256(answer_text.encode("utf-8")).hexdigest()
                if answer_text
                else None
            ),
            "answer_character_count": len(answer_text),
            "usage": {
                **dict(usage),
                "estimated_cost_nano_usd": cost_nano,
                "estimated_cost_usd_exact": _usd_string(cost_nano),
            },
            "error_class": error_class,
            "automatic_retry_count": 0,
        }
    )


def _metric_summary(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "minimum_ms": None, "median_ms": None, "maximum_ms": None}
    return {
        "count": len(values),
        "minimum_ms": round(min(values), 3),
        "median_ms": round(float(median(values)), 3),
        "maximum_ms": round(max(values), 3),
    }


def build_report(outcomes: Sequence[Mapping[str, object]]) -> dict[str, object]:
    if len(outcomes) != EXPECTED_QUESTION_COUNT:
        raise ProductLatencySmokeError("report requires exactly three completed outcomes")
    latencies = [float(item["wall_latency_ms"]) for item in outcomes]
    profile_latencies = {
        profile: [
            float(item["wall_latency_ms"])
            for item in outcomes
            if item.get("expected_answer_length_profile") == profile
        ]
        for profile in EXPECTED_PROFILE_COUNTS
    }
    statuses = Counter(str(item.get("product_status")) for item in outcomes)
    fallback_codes = Counter(
        str(item.get("fallback_code"))
        for item in outcomes
        if item.get("fallback_code") is not None
    )
    fallback_count = sum(
        1 for item in outcomes if "fallback" in str(item.get("product_status") or "")
    )
    operation_counts: Counter[str] = Counter()
    total_cost_nano = 0
    total_output_tokens = 0
    for item in outcomes:
        usage = item.get("usage")
        if not isinstance(usage, Mapping):
            continue
        raw_operations = usage.get("operation_event_counts")
        if isinstance(raw_operations, Mapping):
            operation_counts.update(
                {str(key): int(value) for key, value in raw_operations.items()}
            )
        total_cost_nano += int(usage.get("estimated_cost_nano_usd", 0))
        total_output_tokens += int(usage.get("output_tokens", 0))
    return _sealed(
        {
            "schema": REPORT_SCHEMA,
            "protocol_version": PROTOCOL_VERSION,
            "attempt_count": len(outcomes),
            "automatic_retries": 0,
            "latency_ms": _metric_summary(latencies),
            "latency_by_expected_profile_ms": {
                profile: _metric_summary(values)
                for profile, values in profile_latencies.items()
            },
            "status_counts": dict(sorted(statuses.items())),
            "fallback_count": fallback_count,
            "fallback_code_counts": dict(sorted(fallback_codes.items())),
            "provider_operation_event_counts": dict(sorted(operation_counts.items())),
            "total_output_tokens": total_output_tokens,
            "recorded_cost_nano_usd": total_cost_nano,
            "recorded_cost_usd_exact": _usd_string(total_cost_nano),
            "aggregate_hard_ceiling_nano_usd": AGGREGATE_HARD_CEILING_NANO_USD,
            "items": [
                {
                    "ordinal": item.get("ordinal"),
                    "item_id": item.get("item_id"),
                    "question_sha256": item.get("question_sha256"),
                    "product_status": item.get("product_status"),
                    "fallback_code": item.get("fallback_code"),
                    "answer_length_profile": item.get(
                        "observed_answer_length_profile"
                    ),
                    "wall_latency_ms": item.get("wall_latency_ms"),
                    "stage_timings_ms": item.get("stage_timings_ms"),
                    "source_count": item.get("source_count"),
                    "output_tokens": (
                        item.get("usage", {}).get("output_tokens", 0)
                        if isinstance(item.get("usage"), Mapping)
                        else 0
                    ),
                }
                for item in outcomes
            ],
        }
    )


def _render_report_markdown(report: Mapping[str, object]) -> str:
    latency = report["latency_ms"]
    assert isinstance(latency, Mapping)
    profile_latency = report["latency_by_expected_profile_ms"]
    assert isinstance(profile_latency, Mapping)
    lines = [
        "# Product latency smoke",
        "",
        f"- Protocol: `{report['protocol_version']}`",
        f"- Attempts: {report['attempt_count']} (automatic retries: 0)",
        (
            "- End-to-end latency: "
            f"min {latency['minimum_ms']} ms, median {latency['median_ms']} ms, "
            f"max {latency['maximum_ms']} ms"
        ),
        f"- Status counts: `{json.dumps(report['status_counts'], sort_keys=True)}`",
        f"- Fallbacks: {report['fallback_count']}",
        (
            "- Provider operations: "
            f"`{json.dumps(report['provider_operation_event_counts'], sort_keys=True)}`"
        ),
        f"- Total output tokens: {report['total_output_tokens']}",
        f"- Recorded cost: ${report['recorded_cost_usd_exact']}",
        "",
        "## Latency by adaptive profile",
        "",
    ]
    for profile in ("ordinary", "broad"):
        metrics = profile_latency[profile]
        assert isinstance(metrics, Mapping)
        lines.append(
            f"- {profile}: min {metrics['minimum_ms']} ms, "
            f"median {metrics['median_ms']} ms, max {metrics['maximum_ms']} ms "
            f"(n={metrics['count']})"
        )
    lines.extend(
        [
            "",
            "This latency-only smoke reports min/median/max. With n=3 it does not report p95.",
            "No question, answer, source, manuscript, or provider-error text is stored here.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_latency_smoke(
    *,
    run_root: Path,
    maximum_usd: Decimal,
    authorized: bool,
    smoke_root: Path = SMOKE_ROOT,
    question_fixture: Path = QUESTION_FIXTURE,
    development_registry: Path = DEVELOPMENT_REGISTRY,
    identity_provider: Callable[[], Mapping[str, str]] = clean_git_identity,
    answer_runner: Callable[..., object] = _default_answer_runner,
    ledger_factory: Callable[[], UsageLedger] = UsageLedger,
) -> dict[str, object]:
    maximum_nano = validate_authorization(
        authorized=authorized,
        maximum_usd=maximum_usd,
    )
    target = _validated_run_root(run_root, smoke_root=smoke_root)
    questions = load_latency_questions(
        question_fixture=question_fixture,
        development_registry=development_registry,
    )
    identity = dict(identity_provider())
    manifest = _prepared_manifest(
        questions=questions,
        maximum_nano=maximum_nano,
        identity=identity,
        question_fixture=question_fixture,
        development_registry=development_registry,
    )

    target.mkdir(parents=True, exist_ok=False)
    _write_json_no_overwrite(target / "prepared.json", manifest)
    usage_db = target / "usage.sqlite3"
    outcomes: list[dict[str, object]] = []
    cumulative_cost_nano = 0

    with _isolated_usage_database(usage_db):
        ledger = ledger_factory()
        ledger.update_settings(
            monthly_budget_usd=maximum_usd,
            warning_threshold_percent=80,
            hard_limit_enabled=True,
        )
        for question in questions:
            remaining_attempts = EXPECTED_QUESTION_COUNT - question.ordinal + 1
            if (
                cumulative_cost_nano
                + remaining_attempts * PER_ATTEMPT_COST_CEILING_NANO_USD
                > maximum_nano
            ):
                raise ProductLatencySmokeError(
                    "remaining worst-case requests exceed the authorized aggregate cap"
                )
            request_id = uuid4().hex
            attempt_root = target / "attempts" / f"{question.ordinal:02d}-{question.item_id}"
            _write_json_no_overwrite(
                attempt_root / "intent.json",
                _sealed(
                    {
                        "schema": ATTEMPT_INTENT_SCHEMA,
                        **question.text_free_binding(),
                        "request_id": request_id,
                        "mode": ArchivistMode.PROFESSIONAL.value,
                        "fresh_first_turn": True,
                        "automatic_retry_allowed": False,
                        "request_cost_ceiling_nano_usd": (
                            PER_ATTEMPT_COST_CEILING_NANO_USD
                        ),
                    }
                ),
            )

            started_ns = perf_counter_ns()
            try:
                with usage_scope(
                    project_id="current",
                    conversation_id=target.name,
                    turn_id=question.item_id,
                    request_id=request_id,
                    enforce_budget=True,
                    allow_over_budget=False,
                    request_cost_ceiling_nano_usd=(
                        PER_ATTEMPT_COST_CEILING_NANO_USD
                    ),
                ):
                    result = answer_runner(
                        question.question,
                        archivist_mode=ArchivistMode.PROFESSIONAL,
                        history=(),
                        application_compiled=True,
                    )
            except Exception as exc:
                wall_ms = max(0, perf_counter_ns() - started_ns) / 1_000_000
                try:
                    usage, state = _usage_snapshot(ledger, request_id)
                except ProductLatencySmokeError:
                    usage, state = {"measurement_status": "unavailable"}, None
                sealed = _outcome(
                    question=question,
                    request_id=request_id,
                    measurement_status="ambiguous_exception",
                    wall_latency_ms=wall_ms,
                    usage=usage,
                    state=state,
                    error_class=type(exc).__name__,
                )
                _write_json_no_overwrite(attempt_root / "outcome.json", sealed)
                raise ProductLatencySmokeError(
                    f"{question.item_id} ended ambiguously; no retry or later call was made"
                ) from exc

            wall_ms = max(0, perf_counter_ns() - started_ns) / 1_000_000
            try:
                usage, state = _usage_snapshot(ledger, request_id)
            except ProductLatencySmokeError as exc:
                sealed = _outcome(
                    question=question,
                    request_id=request_id,
                    measurement_status="ambiguous_ledger",
                    wall_latency_ms=wall_ms,
                    usage={"measurement_status": "unavailable"},
                    state=None,
                    result=result,
                    error_class=type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__,
                )
                _write_json_no_overwrite(attempt_root / "outcome.json", sealed)
                raise ProductLatencySmokeError(
                    f"{question.item_id} usage is ambiguous; no retry or later call was made"
                ) from exc

            operation_counts = usage.get("operation_event_counts")
            observed_profile = _safe_generation_trace(result).get(
                "answer_length_profile"
            )
            usage_valid = (
                state.get("event_count") == sum(EXPECTED_PROVIDER_OPERATIONS.values())
                and state.get("unpriced_count") == 0
                and state.get("estimated_cost_nano_usd", 0)
                <= PER_ATTEMPT_COST_CEILING_NANO_USD
                and operation_counts == EXPECTED_PROVIDER_OPERATIONS
            )
            profile_valid = observed_profile == question.expected_profile
            product_status = getattr(result, "status", None)
            product_status_valid = product_status in {
                "retrieval_authored",
                "retrieval_authored_fallback",
            }
            measurement_status = (
                "complete"
                if usage_valid and profile_valid and product_status_valid
                else (
                    "ambiguous_usage"
                    if not usage_valid
                    else (
                        "profile_mismatch"
                        if not profile_valid
                        else "product_status_mismatch"
                    )
                )
            )
            sealed = _outcome(
                question=question,
                request_id=request_id,
                measurement_status=measurement_status,
                wall_latency_ms=wall_ms,
                usage=usage,
                state=state,
                result=result,
                error_class=(
                    None
                    if measurement_status == "complete"
                    else (
                        "AnswerLengthProfileMismatch"
                        if measurement_status == "profile_mismatch"
                        else (
                            "ProductStatusMismatch"
                            if measurement_status == "product_status_mismatch"
                            else "UsageContractError"
                        )
                    )
                ),
            )
            _write_json_no_overwrite(attempt_root / "outcome.json", sealed)
            if measurement_status != "complete":
                raise ProductLatencySmokeError(
                    f"{question.item_id} measurement is {measurement_status}; "
                    "no retry or later call was made"
                )
            cumulative_cost_nano += int(state["estimated_cost_nano_usd"])
            outcomes.append(sealed)

    report = build_report(outcomes)
    _write_json_no_overwrite(target / "report.json", report)
    try:
        with (target / "report.md").open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(_render_report_markdown(report))
    except FileExistsError as exc:
        raise ProductLatencySmokeError("refusing to overwrite latency report") from exc
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run exactly three no-retry Professional first turns through the current "
            "local product path and write text-free latency artifacts."
        )
    )
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--max-total-cost-usd", type=Decimal, required=True)
    parser.add_argument(
        "--authorize-openai-latency-smoke",
        action="store_true",
        help=(
            "Authorize three query embeddings plus three authored-response attempts "
            "against private manuscript evidence, with no retries."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = execute_latency_smoke(
        run_root=args.run_root,
        maximum_usd=args.max_total_cost_usd,
        authorized=args.authorize_openai_latency_smoke,
    )
    latency = report["latency_ms"]
    assert isinstance(latency, Mapping)
    print(
        "Product latency smoke complete: "
        f"min {latency['minimum_ms']} ms; median {latency['median_ms']} ms; "
        f"max {latency['maximum_ms']} ms; "
        f"fallbacks {report['fallback_count']}; "
        f"cost ${report['recorded_cost_usd_exact']}"
    )
    print(f"Text-free report: {args.run_root / 'report.md'}")
    return 0


__all__ = [
    "AGGREGATE_HARD_CEILING_NANO_USD",
    "EXPECTED_PROVIDER_OPERATIONS",
    "LatencyQuestion",
    "ProductLatencySmokeError",
    "build_report",
    "execute_latency_smoke",
    "load_latency_questions",
    "main",
    "validate_authorization",
]
