from __future__ import annotations

import logging
import os
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


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_USAGE_DB = BASE_DIR / "runtime" / "usage.sqlite3"
PRICING_VERSION = "2026-07-22"
CURRENCY = "USD"
NANO_USD_PER_USD = Decimal("1000000000")
TOKENS_PER_MILLION = Decimal("1000000")

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    cache_write_multiplier: Decimal = Decimal("1")


MODEL_PRICING: dict[str, ModelPricing] = {
    "gpt-5": ModelPricing(Decimal("1.25"), Decimal("0.125"), Decimal("10")),
    "gpt-5-2025-08-07": ModelPricing(
        Decimal("1.25"), Decimal("0.125"), Decimal("10")
    ),
    "gpt-5.6": ModelPricing(
        Decimal("5"), Decimal("0.50"), Decimal("30"), Decimal("1.25")
    ),
    "gpt-5.6-sol": ModelPricing(
        Decimal("5"), Decimal("0.50"), Decimal("30"), Decimal("1.25")
    ),
    "gpt-5.6-terra": ModelPricing(
        Decimal("2.50"), Decimal("0.25"), Decimal("15"), Decimal("1.25")
    ),
    "gpt-5.6-luna": ModelPricing(
        Decimal("1"), Decimal("0.10"), Decimal("6"), Decimal("1.25")
    ),
    "text-embedding-3-small": ModelPricing(
        Decimal("0.02"), Decimal("0.02"), Decimal("0")
    ),
    "text-embedding-3-large": ModelPricing(
        Decimal("0.13"), Decimal("0.13"), Decimal("0")
    ),
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
        super().__init__(
            "The local monthly OpenAI cost limit has been reached."
        )


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
        enforce_budget=(
            previous.enforce_budget
            if enforce_budget is None
            else enforce_budget
        ),
        allow_over_budget=(
            previous.allow_over_budget
            if allow_over_budget is None
            else allow_over_budget
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
            """
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
        budget_nano = (
            None if monthly_budget_usd is None else _nano_from_usd(monthly_budget_usd)
        )
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
            percent_used is not None
            and percent_used >= int(settings["warning_threshold_percent"])
        )
        limit_reached = bool(percent_used is not None and percent_used >= 100)
        remaining = (
            None
            if budget_nano is None
            else _usd_from_nano(max(0, int(budget_nano) - spent_nano))
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
    """Call the Responses structured-output helper without bypassing usage tracking."""
    enforce_usage_budget()
    response = client.responses.parse(**request)
    _track_without_breaking_response(
        response,
        operation=operation,
        requested_model=str(request.get("model", "")),
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
