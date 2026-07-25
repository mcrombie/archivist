from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from uuid import uuid4

from query_planning import safe_planner_validation_code


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_USAGE_DB = BASE_DIR / "runtime" / "usage.sqlite3"
PRICING_VERSION = "2026-07-22"
CURRENCY = "USD"
NANO_USD_PER_USD = Decimal("1000000000")
TOKENS_PER_MILLION = Decimal("1000000")
ANSWER_RUN_DIAGNOSTICS_SCHEMA = "archivist.answer_run_diagnostics/2"
PLANNER_CALL_DIAGNOSTICS_SCHEMA = "archivist.planner_call_diagnostics/2"
HISTORICAL_PLANNER_CALL_DIAGNOSTICS_SCHEMA = "archivist.planner_call_diagnostics/1"
ANSWER_RUN_TIMING_KEYS = frozenset(
    {
        "preflight",
        "conversation_resolution",
        "corpus_integrity",
        "query_planning",
        "retrieval",
        "evidence_gate",
        "context_preparation",
        "answer_generation",
        "answer_validation",
        "pipeline_total",
        "total",
    }
)
ANSWER_RUN_COHORT_KEYS = frozenset(
    {
        "rag_policy_version",
        "query_planner_prompt_version",
        "coverage_prompt_version",
        "normalizer_version",
        "coverage_instructions_sha256",
        "coverage_schema_sha256",
        "generator_model",
        "generator_reasoning_effort",
        "generator_verbosity",
    }
)
ANSWER_RUN_PLANNER_V1_KEYS = frozenset(
    {
        "schema",
        "status",
        "failure_code",
        "exception_class",
        "exception_code",
    }
)
ANSWER_RUN_PLANNER_KEYS = ANSWER_RUN_PLANNER_V1_KEYS | {"planner_validation_code"}
HISTORICAL_UNKNOWN_COHORT = {key: "unknown" for key in ANSWER_RUN_COHORT_KEYS}
HISTORICAL_UNKNOWN_PLANNER = {
    "schema": HISTORICAL_PLANNER_CALL_DIAGNOSTICS_SCHEMA,
    "status": "unknown",
    "failure_code": None,
    "exception_class": None,
    "exception_code": None,
}
_HISTORICAL_UNKNOWN_COHORT_JSON = json.dumps(
    HISTORICAL_UNKNOWN_COHORT,
    sort_keys=True,
    separators=(",", ":"),
)
_HISTORICAL_UNKNOWN_PLANNER_JSON = json.dumps(
    HISTORICAL_UNKNOWN_PLANNER,
    sort_keys=True,
    separators=(",", ":"),
)
_DIAGNOSTIC_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_COHORT_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_EXCEPTION_CLASS_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_HTTP_STATUS_CODE_PATTERN = re.compile(r"^[1-5][0-9]{2}$")
SAFE_PLANNER_EXCEPTION_CODES = frozenset(
    {
        "authentication_error",
        "bad_request",
        "connection_error",
        "content_filter",
        "context_length_exceeded",
        "insufficient_quota",
        "internal_server_error",
        "invalid_api_key",
        "invalid_request_error",
        "model_not_found",
        "not_found",
        "permission_denied",
        "rate-limit/429",
        "rate_limit_exceeded",
        "request_timeout",
        "server_error",
        "service_unavailable",
    }
)
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    cache_write_multiplier: Decimal = Decimal("1")


MODEL_PRICING: dict[str, ModelPricing] = {
    "gpt-5": ModelPricing(Decimal("1.25"), Decimal("0.125"), Decimal("10")),
    "gpt-5-2025-08-07": ModelPricing(Decimal("1.25"), Decimal("0.125"), Decimal("10")),
    "gpt-5.6": ModelPricing(Decimal("5"), Decimal("0.50"), Decimal("30"), Decimal("1.25")),
    "gpt-5.6-sol": ModelPricing(Decimal("5"), Decimal("0.50"), Decimal("30"), Decimal("1.25")),
    "gpt-5.6-terra": ModelPricing(Decimal("2.50"), Decimal("0.25"), Decimal("15"), Decimal("1.25")),
    "gpt-5.6-luna": ModelPricing(Decimal("1"), Decimal("0.10"), Decimal("6"), Decimal("1.25")),
    "text-embedding-3-small": ModelPricing(Decimal("0.02"), Decimal("0.02"), Decimal("0")),
    "text-embedding-3-large": ModelPricing(Decimal("0.13"), Decimal("0.13"), Decimal("0")),
}


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class UsageContext:
    project_id: str | None = None
    conversation_id: str | None = None
    turn_id: str | None = None
    enforce_budget: bool = False
    allow_over_budget: bool = False


class CostLimitExceeded(RuntimeError):
    """Raised before an OpenAI call when the configured hard limit is reached."""

    def __init__(self, budget: Mapping[str, object]) -> None:
        self.budget = dict(budget)
        super().__init__("The local monthly OpenAI cost limit has been reached.")


_usage_context: ContextVar[UsageContext] = ContextVar(
    "archivist_usage_context",
    default=UsageContext(),
)


def current_usage_context() -> UsageContext:
    return _usage_context.get()


@contextmanager
def usage_scope(
    *,
    project_id: str | None = None,
    conversation_id: str | None = None,
    turn_id: str | None = None,
    enforce_budget: bool | None = None,
    allow_over_budget: bool | None = None,
) -> Iterator[UsageContext]:
    previous = current_usage_context()
    context = UsageContext(
        project_id=project_id if project_id is not None else previous.project_id,
        conversation_id=(
            conversation_id if conversation_id is not None else previous.conversation_id
        ),
        turn_id=turn_id if turn_id is not None else previous.turn_id,
        enforce_budget=(previous.enforce_budget if enforce_budget is None else enforce_budget),
        allow_over_budget=(
            previous.allow_over_budget if allow_over_budget is None else allow_over_budget
        ),
    )
    token = _usage_context.set(context)
    try:
        yield context
    finally:
        _usage_context.reset(token)


def usage_db_path() -> Path:
    configured = os.getenv("ARCHIVIST_USAGE_DB", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_USAGE_DB


def _value(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _first_int(value: object, *names: str) -> int | None:
    for name in names:
        candidate = _value(value, name)
        if candidate is not None:
            try:
                return max(0, int(candidate))
            except (TypeError, ValueError):
                continue
    return None


def extract_token_usage(response: object) -> TokenUsage | None:
    """Normalize Responses and Embeddings usage objects without depending on SDK classes."""
    usage = _value(response, "usage")
    if usage is None:
        return None

    input_details = _value(usage, "input_tokens_details") or {}
    output_details = _value(usage, "output_tokens_details") or {}
    raw_input_tokens = _first_int(usage, "input_tokens", "prompt_tokens")
    cached_tokens = _first_int(
        input_details,
        "cached_tokens",
        "cache_read_input_tokens",
        "cached_input_tokens",
    )
    if cached_tokens is None:
        cached_tokens = _first_int(
            usage,
            "cached_tokens",
            "cache_read_input_tokens",
            "cached_input_tokens",
        )
    cache_write_tokens = _first_int(
        input_details,
        "cache_write_tokens",
        "cache_creation_tokens",
        "cache_creation_input_tokens",
    )
    if cache_write_tokens is None:
        cache_write_tokens = _first_int(
            usage,
            "cache_write_tokens",
            "cache_creation_tokens",
            "cache_creation_input_tokens",
        )
    raw_output_tokens = _first_int(usage, "output_tokens", "completion_tokens")
    reasoning_tokens = _first_int(output_details, "reasoning_tokens")
    if reasoning_tokens is None:
        reasoning_tokens = _first_int(usage, "reasoning_tokens")
    raw_total_tokens = _first_int(usage, "total_tokens")
    if all(
        value is None
        for value in (
            raw_input_tokens,
            cached_tokens,
            cache_write_tokens,
            raw_output_tokens,
            reasoning_tokens,
            raw_total_tokens,
        )
    ):
        return None

    input_tokens = raw_input_tokens or 0
    cached_tokens = cached_tokens or 0
    cache_write_tokens = cache_write_tokens or 0
    output_tokens = raw_output_tokens or 0
    reasoning_tokens = reasoning_tokens or 0
    total_tokens = raw_total_tokens
    if total_tokens is None:
        total_tokens = input_tokens + output_tokens

    return TokenUsage(
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        cache_write_tokens=cache_write_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
    )


def pricing_for_model(model: str) -> ModelPricing | None:
    pricing = MODEL_PRICING.get(model)
    if pricing is not None:
        return pricing

    # Dated snapshots of the named 5.6 variants retain the variant's centralized rate.
    for base_model in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
        if model.startswith(f"{base_model}-"):
            return MODEL_PRICING[base_model]
    return None


def calculate_cost_nano_usd(model: str, usage: TokenUsage) -> int | None:
    pricing = pricing_for_model(model)
    if pricing is None:
        return None

    standard_input_tokens = max(
        0,
        usage.input_tokens - usage.cached_tokens - usage.cache_write_tokens,
    )
    cost_usd_per_million = (
        Decimal(standard_input_tokens) * pricing.input_usd_per_million
        + Decimal(usage.cached_tokens) * pricing.cached_input_usd_per_million
        + Decimal(usage.cache_write_tokens)
        * pricing.input_usd_per_million
        * pricing.cache_write_multiplier
        + Decimal(usage.output_tokens) * pricing.output_usd_per_million
    )
    # Reasoning tokens are a subset of output tokens and are intentionally not added here.
    # Archivist inputs are bounded below the GPT-5.6 long-context surcharge threshold.
    nano_usd = cost_usd_per_million * NANO_USD_PER_USD / TOKENS_PER_MILLION
    return int(nano_usd.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _month_key(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y-%m")


def _usd_from_nano(value: int | None) -> float | None:
    if value is None:
        return None
    return float((Decimal(value) / NANO_USD_PER_USD).quantize(Decimal("0.000000001")))


def _nano_from_usd(value: Decimal | float | int | str) -> int:
    nano = Decimal(str(value)) * NANO_USD_PER_USD
    return int(nano.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _diagnostic_code(value: object, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _DIAGNOSTIC_CODE_PATTERN.fullmatch(value) is None:
        raise ValueError("answer-run diagnostics contain an invalid code")
    return value


def safe_planner_exception_class(value: object) -> str | None:
    if not isinstance(value, str) or _EXCEPTION_CLASS_PATTERN.fullmatch(value) is None:
        return None
    return value


def safe_planner_exception_code(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    token = str(value)
    if (
        token in SAFE_PLANNER_EXCEPTION_CODES
        or _HTTP_STATUS_CODE_PATTERN.fullmatch(token) is not None
    ):
        return token
    return None


def _normalized_answer_run_diagnostics(
    diagnostics: Mapping[str, object],
) -> dict[str, object]:
    allowed_keys = {
        "schema",
        "cohort",
        "answer_status",
        "evidence_decision",
        "validation_result",
        "validation_error_code",
        "repair_applied",
        "repair_codes",
        "planner",
        "stage_timings_ms",
    }
    if set(diagnostics) != allowed_keys:
        raise ValueError("answer-run diagnostics contain unexpected fields")
    if diagnostics.get("schema") != ANSWER_RUN_DIAGNOSTICS_SCHEMA:
        raise ValueError("answer-run diagnostics use an unsupported schema")

    raw_cohort = diagnostics.get("cohort")
    if not isinstance(raw_cohort, Mapping) or set(raw_cohort) != ANSWER_RUN_COHORT_KEYS:
        raise ValueError("answer-run diagnostics contain invalid cohort fields")
    cohort: dict[str, str] = {}
    for key, value in raw_cohort.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("answer-run cohort values must be strings")
        is_sha256_field = key in {
            "coverage_instructions_sha256",
            "coverage_schema_sha256",
        }
        if is_sha256_field:
            valid_value = (
                value in {"not-applicable", "unknown"}
                or _SHA256_PATTERN.fullmatch(value) is not None
            )
        else:
            valid_value = _COHORT_VALUE_PATTERN.fullmatch(value) is not None
        if not valid_value:
            raise ValueError("answer-run diagnostics contain an invalid cohort value")
        cohort[key] = value

    raw_planner = diagnostics.get("planner")
    if not isinstance(raw_planner, Mapping):
        raise ValueError("answer-run diagnostics contain invalid planner fields")
    planner_schema = raw_planner.get("schema")
    planner_keys = set(raw_planner)
    active_planner = (
        planner_schema == PLANNER_CALL_DIAGNOSTICS_SCHEMA
        and planner_keys == ANSWER_RUN_PLANNER_KEYS
    )
    historical_planner = (
        planner_schema == HISTORICAL_PLANNER_CALL_DIAGNOSTICS_SCHEMA
        and planner_keys == ANSWER_RUN_PLANNER_V1_KEYS
    )
    if not active_planner and not historical_planner:
        raise ValueError("answer-run diagnostics contain invalid planner fields")
    planner_status = _diagnostic_code(raw_planner.get("status"))
    if planner_status not in {"unknown", "not_called", "succeeded", "failed"}:
        raise ValueError("answer-run diagnostics contain an invalid planner status")
    planner_failure_code = _diagnostic_code(
        raw_planner.get("failure_code"),
        nullable=True,
    )
    planner_validation_code = (
        safe_planner_validation_code(raw_planner.get("planner_validation_code"))
        if active_planner
        else None
    )
    if (
        active_planner
        and raw_planner.get("planner_validation_code") is not None
        and planner_validation_code is None
    ):
        raise ValueError("answer-run diagnostics contain an invalid planner validation code")
    planner_tokens: dict[str, str | None] = {}
    for key, sanitizer in (
        ("exception_class", safe_planner_exception_class),
        ("exception_code", safe_planner_exception_code),
    ):
        value = raw_planner.get(key)
        if value is not None and sanitizer(value) != value:
            raise ValueError("answer-run diagnostics contain an invalid planner token")
        planner_tokens[key] = value
    if planner_status == "failed":
        if planner_failure_code is None:
            raise ValueError("failed planner diagnostics require a failure code")
        if (
            planner_failure_code == "invalid_planner_output"
            and active_planner
            and planner_validation_code is None
        ):
            raise ValueError("invalid planner output requires a planner validation code")
        if planner_failure_code != "invalid_planner_output" and planner_validation_code is not None:
            raise ValueError("planner validation codes require invalid planner output")
    elif (
        planner_failure_code is not None
        or planner_validation_code is not None
        or planner_tokens["exception_class"] is not None
        or planner_tokens["exception_code"] is not None
    ):
        raise ValueError("non-failed planner diagnostics cannot contain failure metadata")
    planner = {
        "schema": planner_schema,
        "status": planner_status,
        "failure_code": planner_failure_code,
        **({"planner_validation_code": planner_validation_code} if active_planner else {}),
        **planner_tokens,
    }

    repair_codes_value = diagnostics.get("repair_codes")
    if not isinstance(repair_codes_value, (list, tuple)):
        raise ValueError("answer-run repair codes must be a list")
    repair_codes = tuple(dict.fromkeys(_diagnostic_code(code) for code in repair_codes_value))
    repair_applied = diagnostics.get("repair_applied")
    if not isinstance(repair_applied, bool) or repair_applied != bool(repair_codes):
        raise ValueError("answer-run repair metadata is inconsistent")

    raw_timings = diagnostics.get("stage_timings_ms")
    if not isinstance(raw_timings, Mapping):
        raise ValueError("answer-run stage timings must be an object")
    if any(key not in ANSWER_RUN_TIMING_KEYS for key in raw_timings):
        raise ValueError("answer-run diagnostics contain an unknown timing stage")
    timings: dict[str, float] = {}
    for key, value in raw_timings.items():
        if (
            not isinstance(key, str)
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise ValueError("answer-run diagnostics contain an invalid timing")
        timings[key] = round(float(value), 3)

    validation_result = _diagnostic_code(diagnostics.get("validation_result"))
    if validation_result not in {"valid", "invalid", "not_run"}:
        raise ValueError("answer-run diagnostics contain an invalid validation result")
    validation_error_code = _diagnostic_code(
        diagnostics.get("validation_error_code"),
        nullable=True,
    )
    if (validation_result == "invalid") != (validation_error_code is not None):
        raise ValueError("answer-run validation metadata is inconsistent")

    return {
        "schema": ANSWER_RUN_DIAGNOSTICS_SCHEMA,
        "cohort": cohort,
        "answer_status": _diagnostic_code(diagnostics.get("answer_status")),
        "evidence_decision": _diagnostic_code(diagnostics.get("evidence_decision")),
        "validation_result": validation_result,
        "validation_error_code": validation_error_code,
        "repair_applied": repair_applied,
        "repair_codes": repair_codes,
        "planner": planner,
        "stage_timings_ms": timings,
    }


class UsageLedger:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else usage_db_path()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        self._ensure_schema(connection)
        return connection

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                response_id TEXT NOT NULL UNIQUE,
                recorded_at TEXT NOT NULL,
                operation TEXT NOT NULL,
                project_id TEXT,
                conversation_id TEXT,
                turn_id TEXT,
                requested_model TEXT NOT NULL,
                actual_model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                cached_tokens INTEGER NOT NULL,
                cache_write_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                reasoning_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                estimated_cost_nano_usd INTEGER,
                pricing_version TEXT NOT NULL,
                unpriced INTEGER NOT NULL CHECK (unpriced IN (0, 1))
            );
            CREATE INDEX IF NOT EXISTS usage_events_recorded_at_idx
                ON usage_events(recorded_at);
            CREATE INDEX IF NOT EXISTS usage_events_scope_idx
                ON usage_events(project_id, conversation_id, turn_id);
            CREATE TABLE IF NOT EXISTS answer_run_diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                recorded_at TEXT NOT NULL,
                project_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                answer_status TEXT NOT NULL,
                evidence_decision TEXT NOT NULL,
                validation_result TEXT NOT NULL,
                validation_error_code TEXT,
                repair_applied INTEGER NOT NULL CHECK (repair_applied IN (0, 1)),
                repair_codes_json TEXT NOT NULL,
                cohort_json TEXT NOT NULL DEFAULT
                    '{_HISTORICAL_UNKNOWN_COHORT_JSON}',
                planner_json TEXT NOT NULL DEFAULT
                    '{_HISTORICAL_UNKNOWN_PLANNER_JSON}',
                stage_timings_json TEXT NOT NULL,
                UNIQUE(project_id, conversation_id, turn_id)
            );
            CREATE INDEX IF NOT EXISTS answer_run_diagnostics_scope_idx
                ON answer_run_diagnostics(project_id, conversation_id, turn_id);
            CREATE TABLE IF NOT EXISTS cost_settings (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                monthly_budget_nano_usd INTEGER,
                warning_threshold_percent INTEGER NOT NULL,
                hard_limit_enabled INTEGER NOT NULL CHECK (hard_limit_enabled IN (0, 1))
            );
            INSERT INTO cost_settings (
                singleton,
                monthly_budget_nano_usd,
                warning_threshold_percent,
                hard_limit_enabled
            ) VALUES (1, NULL, 80, 0)
            ON CONFLICT(singleton) DO NOTHING;
            """
        )
        diagnostic_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(answer_run_diagnostics)").fetchall()
        }
        if "cohort_json" not in diagnostic_columns:
            connection.execute(
                f"""
                ALTER TABLE answer_run_diagnostics
                ADD COLUMN cohort_json TEXT NOT NULL DEFAULT
                '{_HISTORICAL_UNKNOWN_COHORT_JSON}'
                """
            )
        if "planner_json" not in diagnostic_columns:
            connection.execute(
                f"""
                ALTER TABLE answer_run_diagnostics
                ADD COLUMN planner_json TEXT NOT NULL DEFAULT
                '{_HISTORICAL_UNKNOWN_PLANNER_JSON}'
                """
            )
        connection.execute(
            """
            UPDATE answer_run_diagnostics
            SET cohort_json = ?
            WHERE cohort_json = '{}'
            """,
            (_HISTORICAL_UNKNOWN_COHORT_JSON,),
        )
        connection.execute(
            """
            UPDATE answer_run_diagnostics
            SET planner_json = ?
            WHERE planner_json = '{}'
            """,
            (_HISTORICAL_UNKNOWN_PLANNER_JSON,),
        )
        connection.commit()

    def record(
        self,
        *,
        response_id: str,
        operation: str,
        requested_model: str,
        actual_model: str,
        usage: TokenUsage,
        project_id: str | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        recorded_at: str | None = None,
    ) -> bool:
        estimated_cost = calculate_cost_nano_usd(actual_model, usage)
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO usage_events (
                    response_id, recorded_at, operation,
                    project_id, conversation_id, turn_id,
                    requested_model, actual_model,
                    input_tokens, cached_tokens, cache_write_tokens,
                    output_tokens, reasoning_tokens, total_tokens,
                    estimated_cost_nano_usd, pricing_version, unpriced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(response_id) DO NOTHING
                """,
                (
                    response_id,
                    recorded_at or _utc_now(),
                    operation,
                    project_id,
                    conversation_id,
                    turn_id,
                    requested_model,
                    actual_model,
                    usage.input_tokens,
                    usage.cached_tokens,
                    usage.cache_write_tokens,
                    usage.output_tokens,
                    usage.reasoning_tokens,
                    usage.total_tokens,
                    estimated_cost,
                    PRICING_VERSION,
                    int(estimated_cost is None),
                ),
            )
        return cursor.rowcount == 1

    def record_answer_run_diagnostics(
        self,
        *,
        project_id: str | None,
        conversation_id: str | None,
        turn_id: str | None,
        diagnostics: Mapping[str, object],
        recorded_at: str | None = None,
    ) -> bool:
        """Persist one text-free post-validation outcome for a UI-addressable turn."""

        if not project_id or not conversation_id or not turn_id:
            return False
        normalized = _normalized_answer_run_diagnostics(diagnostics)
        run_id = str(uuid4())
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO answer_run_diagnostics (
                    run_id, recorded_at, project_id, conversation_id, turn_id,
                    answer_status, evidence_decision, validation_result,
                    validation_error_code, repair_applied, repair_codes_json,
                    cohort_json, planner_json, stage_timings_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, conversation_id, turn_id) DO UPDATE SET
                    run_id = excluded.run_id,
                    recorded_at = excluded.recorded_at,
                    answer_status = excluded.answer_status,
                    evidence_decision = excluded.evidence_decision,
                    validation_result = excluded.validation_result,
                    validation_error_code = excluded.validation_error_code,
                    repair_applied = excluded.repair_applied,
                    repair_codes_json = excluded.repair_codes_json,
                    cohort_json = excluded.cohort_json,
                    planner_json = excluded.planner_json,
                    stage_timings_json = excluded.stage_timings_json
                """,
                (
                    run_id,
                    recorded_at or _utc_now(),
                    project_id,
                    conversation_id,
                    turn_id,
                    normalized["answer_status"],
                    normalized["evidence_decision"],
                    normalized["validation_result"],
                    normalized["validation_error_code"],
                    int(bool(normalized["repair_applied"])),
                    json.dumps(normalized["repair_codes"], separators=(",", ":")),
                    json.dumps(
                        normalized["cohort"],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        normalized["planner"],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        normalized["stage_timings_ms"],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            )
        return cursor.rowcount == 1

    def get_answer_run_diagnostics(
        self,
        *,
        project_id: str,
        conversation_id: str,
        turn_id: str,
    ) -> dict[str, object] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT run_id, recorded_at, answer_status, evidence_decision,
                       validation_result, validation_error_code, repair_applied,
                       repair_codes_json, cohort_json, planner_json,
                       stage_timings_json
                FROM answer_run_diagnostics
                WHERE project_id = ? AND conversation_id = ? AND turn_id = ?
                """,
                (project_id, conversation_id, turn_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "schema": ANSWER_RUN_DIAGNOSTICS_SCHEMA,
            "run_id": str(row["run_id"]),
            "recorded_at": str(row["recorded_at"]),
            "answer_status": str(row["answer_status"]),
            "evidence_decision": str(row["evidence_decision"]),
            "validation_result": str(row["validation_result"]),
            "validation_error_code": (
                str(row["validation_error_code"])
                if row["validation_error_code"] is not None
                else None
            ),
            "repair_applied": bool(row["repair_applied"]),
            "repair_codes": json.loads(str(row["repair_codes_json"])),
            "cohort": json.loads(str(row["cohort_json"])),
            "planner": json.loads(str(row["planner_json"])),
            "stage_timings_ms": json.loads(str(row["stage_timings_json"])),
        }

    @staticmethod
    def _filters(
        *,
        project_id: str | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        month: str | None = None,
    ) -> tuple[str, list[object]]:
        clauses: list[str] = []
        parameters: list[object] = []
        for column, value in (
            ("project_id", project_id),
            ("conversation_id", conversation_id),
            ("turn_id", turn_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        if month is not None:
            clauses.append("substr(recorded_at, 1, 7) = ?")
            parameters.append(month)
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), parameters

    @staticmethod
    def _empty_totals() -> dict[str, object]:
        return {
            "estimated_cost_usd": 0.0,
            "input_tokens": 0,
            "cached_tokens": 0,
            "cache_write_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "event_count": 0,
            "unpriced_count": 0,
        }

    def _totals(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        month: str | None = None,
    ) -> dict[str, object]:
        where, parameters = self._filters(
            project_id=project_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            month=month,
        )
        row = connection.execute(
            f"""
            SELECT
                COALESCE(SUM(estimated_cost_nano_usd), 0) AS estimated_cost_nano_usd,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                COALESCE(SUM(cache_write_tokens), 0) AS cache_write_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COUNT(*) AS event_count,
                COALESCE(SUM(unpriced), 0) AS unpriced_count
            FROM usage_events{where}
            """,
            parameters,
        ).fetchone()
        if row is None:
            return self._empty_totals()
        return {
            "estimated_cost_usd": _usd_from_nano(int(row["estimated_cost_nano_usd"])),
            "input_tokens": int(row["input_tokens"]),
            "cached_tokens": int(row["cached_tokens"]),
            "cache_write_tokens": int(row["cache_write_tokens"]),
            "output_tokens": int(row["output_tokens"]),
            "reasoning_tokens": int(row["reasoning_tokens"]),
            "total_tokens": int(row["total_tokens"]),
            "event_count": int(row["event_count"]),
            "unpriced_count": int(row["unpriced_count"]),
        }

    @staticmethod
    def _settings_from_row(row: sqlite3.Row) -> dict[str, object]:
        budget_nano = row["monthly_budget_nano_usd"]
        return {
            "monthly_budget_usd": (
                _usd_from_nano(int(budget_nano)) if budget_nano is not None else None
            ),
            "warning_threshold_percent": int(row["warning_threshold_percent"]),
            "hard_limit_enabled": bool(row["hard_limit_enabled"]),
        }

    def get_settings(self) -> dict[str, object]:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT monthly_budget_nano_usd, warning_threshold_percent,
                       hard_limit_enabled
                FROM cost_settings WHERE singleton = ?
                """,
                (1,),
            ).fetchone()
        assert row is not None
        return self._settings_from_row(row)

    def update_settings(
        self,
        *,
        monthly_budget_usd: Decimal | float | int | str | None,
        warning_threshold_percent: int,
        hard_limit_enabled: bool,
    ) -> dict[str, object]:
        if monthly_budget_usd is not None:
            normalized_budget = Decimal(str(monthly_budget_usd))
            if not Decimal("0.01") <= normalized_budget <= Decimal("100000"):
                raise ValueError("monthly_budget_usd must be between 0.01 and 100000")
        if not 1 <= warning_threshold_percent <= 100:
            raise ValueError("warning_threshold_percent must be between 1 and 100")
        budget_nano = None if monthly_budget_usd is None else _nano_from_usd(monthly_budget_usd)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE cost_settings
                SET monthly_budget_nano_usd = ?,
                    warning_threshold_percent = ?,
                    hard_limit_enabled = ?
                WHERE singleton = ?
                """,
                (
                    budget_nano,
                    warning_threshold_percent,
                    int(hard_limit_enabled),
                    1,
                ),
            )
        return self.get_settings()

    def budget_state(self, now: datetime | None = None) -> dict[str, object]:
        with closing(self._connect()) as connection, connection:
            settings_row = connection.execute(
                """
                SELECT monthly_budget_nano_usd, warning_threshold_percent,
                       hard_limit_enabled
                FROM cost_settings WHERE singleton = ?
                """,
                (1,),
            ).fetchone()
            assert settings_row is not None
            month_where, month_parameters = self._filters(month=_month_key(now))
            month_row = connection.execute(
                f"""
                SELECT COALESCE(SUM(estimated_cost_nano_usd), 0) AS cost
                FROM usage_events{month_where}
                """,
                month_parameters,
            ).fetchone()

        settings = self._settings_from_row(settings_row)
        budget = settings["monthly_budget_usd"]
        spent_nano = int(month_row["cost"] if month_row is not None else 0)
        budget_nano = settings_row["monthly_budget_nano_usd"]
        percent_used = (
            None
            if budget_nano is None
            else float(
                (Decimal(spent_nano) * 100 / Decimal(int(budget_nano))).quantize(
                    Decimal("0.0001"),
                    rounding=ROUND_HALF_UP,
                )
            )
        )
        warning_reached = bool(
            percent_used is not None and percent_used >= int(settings["warning_threshold_percent"])
        )
        limit_reached = bool(percent_used is not None and percent_used >= 100)
        remaining = (
            None if budget_nano is None else _usd_from_nano(max(0, int(budget_nano) - spent_nano))
        )
        return {
            "monthly_budget_usd": budget,
            "warning_threshold_percent": settings["warning_threshold_percent"],
            "hard_limit_enabled": settings["hard_limit_enabled"],
            "remaining_usd": remaining,
            "percent_used": percent_used,
            "warning": warning_reached,
            "exceeded": limit_reached,
        }

    def summary(
        self,
        *,
        project_id: str | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        now: datetime | None = None,
        recent_limit: int = 20,
    ) -> dict[str, object]:
        month = _month_key(now)
        with closing(self._connect()) as connection, connection:
            tracking_row = connection.execute(
                "SELECT MIN(recorded_at) AS tracking_started_at FROM usage_events"
            ).fetchone()
            all_time = self._totals(
                connection,
            )
            month_totals = self._totals(
                connection,
                month=month,
            )
            conversation = (
                self._totals(
                    connection,
                    project_id=project_id,
                    conversation_id=conversation_id,
                )
                if conversation_id is not None
                else self._empty_totals()
            )
            turn = (
                self._totals(
                    connection,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                )
                if turn_id is not None
                else self._empty_totals()
            )

            where, parameters = self._filters(
                month=month,
            )
            operation_rows = connection.execute(
                f"""
                SELECT operation,
                       COALESCE(SUM(estimated_cost_nano_usd), 0) AS cost,
                       COALESCE(SUM(input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                       COALESCE(SUM(cache_write_tokens), 0) AS cache_write_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens,
                       COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                       COALESCE(SUM(total_tokens), 0) AS total_tokens,
                       COUNT(*) AS event_count,
                       COALESCE(SUM(unpriced), 0) AS unpriced_count
                FROM usage_events{where}
                GROUP BY operation
                ORDER BY cost DESC, operation ASC
                """,
                parameters,
            ).fetchall()
            recent_parameters = [*parameters, recent_limit]
            recent_rows = connection.execute(
                f"""
                SELECT response_id, recorded_at, operation,
                       project_id, conversation_id, turn_id,
                       requested_model, actual_model,
                       input_tokens, cached_tokens, cache_write_tokens,
                       output_tokens, reasoning_tokens, total_tokens,
                       estimated_cost_nano_usd, pricing_version, unpriced
                FROM usage_events{where}
                ORDER BY recorded_at DESC, id DESC
                LIMIT ?
                """,
                recent_parameters,
            ).fetchall()

        operations = [
            {
                "operation": str(row["operation"]),
                "calls": int(row["event_count"]),
                "tokens": int(row["total_tokens"]),
                "cost_usd": _usd_from_nano(int(row["cost"])),
            }
            for row in operation_rows
        ]
        recent_events = [
            {
                "operation": str(row["operation"]),
                "model": str(row["actual_model"]),
                "tokens": int(row["total_tokens"]),
                "cost_usd": (
                    _usd_from_nano(int(row["estimated_cost_nano_usd"]))
                    if row["estimated_cost_nano_usd"] is not None
                    else None
                ),
                "timestamp": str(row["recorded_at"]),
            }
            for row in recent_rows
        ]
        return {
            "currency": CURRENCY,
            "pricing_version": PRICING_VERSION,
            "accuracy": "estimated",
            "tracking_started_at": tracking_row["tracking_started_at"],
            "turn_usd": turn["estimated_cost_usd"],
            "conversation_usd": conversation["estimated_cost_usd"],
            "month_usd": month_totals["estimated_cost_usd"],
            "all_time_usd": all_time["estimated_cost_usd"],
            "unpriced_events": int(all_time["unpriced_count"]),
            "budget": self.budget_state(now),
            "operations": operations,
            "recent_events": recent_events,
        }


def record_openai_response(
    response: object,
    *,
    operation: str,
    requested_model: str,
    ledger: UsageLedger | None = None,
) -> bool:
    usage = extract_token_usage(response)
    if usage is None:
        return False

    response_id = _value(response, "id") or _value(response, "_request_id")
    if response_id is None:
        response_id = f"local-{uuid4()}"
    actual_model = _value(response, "model") or requested_model
    context = current_usage_context()
    return (ledger or UsageLedger()).record(
        response_id=str(response_id),
        operation=operation,
        requested_model=requested_model,
        actual_model=str(actual_model),
        usage=usage,
        project_id=context.project_id,
        conversation_id=context.conversation_id,
        turn_id=context.turn_id,
    )


def _track_without_breaking_response(
    response: object,
    *,
    operation: str,
    requested_model: str,
) -> None:
    try:
        record_openai_response(
            response,
            operation=operation,
            requested_model=requested_model,
        )
    except Exception:
        logger.exception("Could not record local OpenAI usage")


def enforce_usage_budget(ledger: UsageLedger | None = None) -> None:
    """Recheck the hard limit immediately before a tracked OpenAI operation."""

    context = current_usage_context()
    if not context.enforce_budget or context.allow_over_budget:
        return
    budget = (ledger or UsageLedger()).budget_state()
    if budget["hard_limit_enabled"] and budget["exceeded"]:
        raise CostLimitExceeded(budget)


def tracked_responses_create(client: object, *, operation: str, **request: Any) -> object:
    enforce_usage_budget()
    response = client.responses.create(**request)
    _track_without_breaking_response(
        response,
        operation=operation,
        requested_model=str(request.get("model", "")),
    )
    return response


def tracked_responses_parse(client: object, *, operation: str, **request: Any) -> object:
    """Call the structured-output helper while retaining completed-response usage.

    The OpenAI SDK applies ``text_format`` validation as a post-parser.  A
    validation error therefore prevents ``responses.parse`` from returning the
    otherwise completed response (including its usage).  Reading the SDK's raw
    response first lets us record that usage before invoking the same parser,
    without issuing another request.
    """
    enforce_usage_budget()
    requested_model = str(request.get("model", ""))
    raw_responses = getattr(client.responses, "with_raw_response", None)
    raw_parse = getattr(raw_responses, "parse", None)

    # Preserve compatibility with lightweight test doubles and older clients.
    # The installed SDK (2.46.0) takes the raw-response path below.
    if not callable(raw_parse):
        response = client.responses.parse(**request)
        _track_without_breaking_response(
            response,
            operation=operation,
            requested_model=requested_model,
        )
        return response

    raw_response = raw_parse(**request)
    completed_response: object | None = None
    json_reader = getattr(raw_response, "json", None)
    if callable(json_reader):
        try:
            completed_response = json_reader()
        except Exception:
            logger.exception("Could not inspect completed OpenAI response usage")
    else:
        # openai 2.46.0 returns LegacyAPIResponse here.  It exposes the
        # completed httpx response but not APIResponse.json().
        http_response = getattr(raw_response, "http_response", None)
        http_json_reader = getattr(http_response, "json", None)
        if callable(http_json_reader):
            try:
                completed_response = http_json_reader()
            except Exception:
                logger.exception("Could not inspect completed OpenAI response usage")

    completed_usage_available = (
        completed_response is not None and extract_token_usage(completed_response) is not None
    )
    if completed_usage_available:
        _track_without_breaking_response(
            completed_response,
            operation=operation,
            requested_model=requested_model,
        )

    # This is the SDK's normal parse step and preserves output_parsed as well
    # as its original Pydantic ValidationError behavior.
    response = raw_response.parse()
    if not completed_usage_available:
        _track_without_breaking_response(
            response,
            operation=operation,
            requested_model=requested_model,
        )
    return response


def tracked_embeddings_create(client: object, *, operation: str, **request: Any) -> object:
    enforce_usage_budget()
    response = client.embeddings.create(**request)
    _track_without_breaking_response(
        response,
        operation=operation,
        requested_model=str(request.get("model", "")),
    )
    return response
