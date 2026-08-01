from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


DEVELOPMENT_COST_LINEAGE_SCHEMA = "archivist.development_cost_lineage/2"
_LEGACY_DEVELOPMENT_COST_LINEAGE_SCHEMA = "archivist.development_cost_lineage/1"
_RAG_RUN_PATTERN = re.compile(r"^evidence-planned-v(?P<version>[0-9]+)(?:-|$)")
_FULL_CONTEXT_RUN_PATTERN = re.compile(
    r"^full-context-v(?P<version>[0-9]+)(?:-|$)"
)
_ITEM_PATTERN = re.compile(r"^G[0-9]{3}\.json$")
_NANO_USD_PER_USD = Decimal("1000000000")
_REQUIRED_USAGE_COLUMNS = {
    "response_id",
    "operation",
    "total_tokens",
    "estimated_cost_nano_usd",
    "unpriced",
}


class EvaluationCostError(RuntimeError):
    """Raised when isolated evaluation ledgers cannot be aggregated safely."""


@dataclass(frozen=True)
class _StrategyRunIdentity:
    answer_strategy: str
    answer_strategy_version: str
    version_number: int

    @property
    def aggregate_key(self) -> tuple[str, str]:
        # The strategy is intentionally part of the key. A future RAG V1 and
        # full-context V1 are different systems, not two runs of one policy.
        return self.answer_strategy, self.answer_strategy_version


def _strategy_run_identity(
    run_id: str,
    *,
    min_rag_version: int,
    max_rag_version: int,
) -> _StrategyRunIdentity | None:
    rag_match = _RAG_RUN_PATTERN.match(run_id)
    if rag_match is not None:
        version = int(rag_match.group("version"))
        if not min_rag_version <= version <= max_rag_version:
            return None
        return _StrategyRunIdentity(
            answer_strategy="rag",
            answer_strategy_version=f"evidence-planned-v{version}",
            version_number=version,
        )

    full_context_match = _FULL_CONTEXT_RUN_PATTERN.match(run_id)
    if full_context_match is not None:
        version = int(full_context_match.group("version"))
        return _StrategyRunIdentity(
            answer_strategy="full_context",
            answer_strategy_version=f"full-context-v{version}",
            version_number=version,
        )
    return None


def _display_strategy(row: Mapping[str, object]) -> str:
    strategy = _safe_string(row.get("answer_strategy"))
    if strategy is not None:
        return strategy
    # Reports generated before full-context existed did not carry the field.
    # Every evidence-planned run was RAG, so this display-only backfill is a
    # historical fact rather than an inferred quality judgment.
    policy_version = _safe_string(row.get("policy_version"))
    if policy_version is not None and policy_version.startswith("evidence-planned-v"):
        return "rag"
    if policy_version is not None and policy_version.startswith("full-context-v"):
        return "full_context"
    return "unknown"


def _display_strategy_version(row: Mapping[str, object]) -> str:
    return (
        _safe_string(row.get("answer_strategy_version"))
        or _safe_string(row.get("policy_version"))
        or "unknown"
    )


def _usd_string(nano_usd: int) -> str:
    value = Decimal(nano_usd) / _NANO_USD_PER_USD
    return f"{value:.9f}"


def _load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationCostError(f"Could not read JSON metadata: {path}") from exc
    if not isinstance(value, dict):
        raise EvaluationCostError(f"Expected a JSON object: {path}")
    return value


def _safe_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _summary_items(
    run_dir: Path,
    summary: Mapping[str, object] | None,
) -> tuple[list[str], int | None]:
    raw_items = summary.get("items") if summary is not None else None
    if isinstance(raw_items, list):
        ids: list[str] = []
        elapsed_ms = 0
        elapsed_complete = True
        for item in raw_items:
            if not isinstance(item, Mapping):
                continue
            item_id = _safe_string(item.get("item_id"))
            if item_id is not None:
                ids.append(item_id)
            elapsed = _safe_nonnegative_int(item.get("elapsed_ms"))
            if elapsed is None:
                elapsed_complete = False
            else:
                elapsed_ms += elapsed
        return sorted(set(ids)), elapsed_ms if elapsed_complete else None

    ids = []
    elapsed_ms = 0
    elapsed_complete = True
    for path in sorted(run_dir.glob("G[0-9][0-9][0-9].json")):
        if _ITEM_PATTERN.fullmatch(path.name) is None:
            continue
        item = _load_json_object(path)
        assert item is not None
        item_id = _safe_string(item.get("item_id")) or path.stem
        ids.append(item_id)
        elapsed = _safe_nonnegative_int(item.get("elapsed_ms"))
        if elapsed is None:
            elapsed_complete = False
        else:
            elapsed_ms += elapsed
    if not ids:
        return [], None
    return sorted(set(ids)), elapsed_ms if elapsed_complete else None


def _run_metadata(run_dir: Path) -> dict[str, object]:
    summary = _load_json_object(run_dir / "run_summary.json")
    preflight = _load_json_object(run_dir / "preflight.json")
    attempt = _load_json_object(run_dir / "attempt.json")
    item_ids, elapsed_ms = _summary_items(run_dir, summary)

    run_identity = summary.get("run_identity") if summary is not None else None
    if not isinstance(run_identity, Mapping) and preflight is not None:
        worktree = preflight.get("worktree")
        run_identity = worktree if isinstance(worktree, Mapping) else None

    cost_estimate = preflight.get("cost_estimate") if preflight is not None else None
    operational_hard_cap = (
        _safe_string(summary.get("authorized_max_usd"))
        if summary is not None
        else None
    )
    if operational_hard_cap is None and attempt is not None:
        operational_hard_cap = _safe_string(attempt.get("authorized_max_usd"))
    if operational_hard_cap is None and isinstance(cost_estimate, Mapping):
        operational_hard_cap = _safe_string(
            cost_estimate.get("proposed_hard_cap_usd")
        )
    owner_authorized_max = (
        _safe_string(cost_estimate.get("owner_authorized_max_usd"))
        if isinstance(cost_estimate, Mapping)
        else None
    )

    retries = (
        _safe_nonnegative_int(summary.get("automatic_retries"))
        if summary is not None
        else None
    )
    if retries is None and attempt is not None:
        retries = _safe_nonnegative_int(attempt.get("automatic_retries"))
    if retries is None and preflight is not None:
        for key in (
            "mechanical_sentinel",
            "development_cohort",
            "confirmation_gate",
            "focused_gate",
            "integrated_gate",
        ):
            gate = preflight.get(key)
            if isinstance(gate, Mapping):
                retries = _safe_nonnegative_int(gate.get("automatic_retries"))
                if retries is not None:
                    break

    attempt_status = (
        _safe_string(attempt.get("status")) if attempt is not None else None
    )
    return {
        "status": (
            _safe_string(summary.get("status"))
            if summary is not None
            else (attempt_status or ("partial" if item_ids else "metadata_only"))
        ),
        "git_commit": (
            _safe_string(run_identity.get("git_commit"))
            if isinstance(run_identity, Mapping)
            else None
        ),
        "working_tree": (
            _safe_string(run_identity.get("working_tree"))
            if isinstance(run_identity, Mapping)
            else None
        ),
        "formal_run_of_record": (
            summary.get("formal_run_of_record")
            if summary is not None
            and isinstance(summary.get("formal_run_of_record"), bool)
            else False
        ),
        "authorized_max_usd": operational_hard_cap,
        "operational_hard_cap_usd": operational_hard_cap,
        "owner_authorized_max_usd": owner_authorized_max,
        "automatic_retries": retries,
        "item_ids": item_ids,
        "item_count": len(item_ids),
        "total_elapsed_ms": elapsed_ms,
    }


def _read_usage_events(run_dir: Path) -> list[dict[str, object]]:
    ledger_path = run_dir / "usage.sqlite3"
    if not ledger_path.is_file():
        raise EvaluationCostError(f"Evaluation run has no usage ledger: {run_dir.name}")
    uri = f"{ledger_path.resolve().as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise EvaluationCostError(f"Could not open usage ledger: {ledger_path}") from exc
    try:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(usage_events)").fetchall()
        }
        if not _REQUIRED_USAGE_COLUMNS.issubset(columns):
            missing = sorted(_REQUIRED_USAGE_COLUMNS - columns)
            raise EvaluationCostError(
                f"Usage ledger {ledger_path} is missing columns: {', '.join(missing)}"
            )
        rows = connection.execute(
            """
            SELECT response_id, operation, total_tokens,
                   estimated_cost_nano_usd, unpriced
            FROM usage_events
            ORDER BY id
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise EvaluationCostError(f"Could not query usage ledger: {ledger_path}") from exc
    finally:
        connection.close()

    events: list[dict[str, object]] = []
    for response_id, operation, tokens, cost, unpriced in rows:
        if not isinstance(response_id, str) or not response_id:
            raise EvaluationCostError(f"Usage ledger has an invalid response ID: {ledger_path}")
        if not isinstance(operation, str) or not operation:
            raise EvaluationCostError(f"Usage ledger has an invalid operation: {ledger_path}")
        if not isinstance(tokens, int) or tokens < 0:
            raise EvaluationCostError(f"Usage ledger has an invalid token count: {ledger_path}")
        if cost is not None and (not isinstance(cost, int) or cost < 0):
            raise EvaluationCostError(f"Usage ledger has an invalid cost: {ledger_path}")
        if unpriced not in (0, 1):
            raise EvaluationCostError(f"Usage ledger has an invalid unpriced flag: {ledger_path}")
        events.append(
            {
                "response_id": response_id,
                "operation": operation,
                "tokens": tokens,
                "cost_nano_usd": cost,
                "unpriced": bool(unpriced),
            }
        )
    return events


def _totals(events: Sequence[Mapping[str, object]]) -> dict[str, object]:
    operations: dict[str, dict[str, int]] = defaultdict(
        lambda: {"calls": 0, "tokens": 0, "cost_nano_usd": 0, "unpriced_events": 0}
    )
    total_cost = 0
    total_tokens = 0
    unpriced_events = 0
    for event in events:
        operation = str(event["operation"])
        tokens = int(event["tokens"])
        raw_cost = event["cost_nano_usd"]
        cost = int(raw_cost) if isinstance(raw_cost, int) else 0
        unpriced = bool(event["unpriced"])
        row = operations[operation]
        row["calls"] += 1
        row["tokens"] += tokens
        row["cost_nano_usd"] += cost
        row["unpriced_events"] += int(unpriced)
        total_tokens += tokens
        total_cost += cost
        unpriced_events += int(unpriced)
    return {
        "calls": len(events),
        "tokens": total_tokens,
        "estimated_cost_usd": _usd_string(total_cost),
        "unpriced_events": unpriced_events,
        "operations": [
            {
                "operation": operation,
                "calls": values["calls"],
                "tokens": values["tokens"],
                "estimated_cost_usd": _usd_string(values["cost_nano_usd"]),
                "unpriced_events": values["unpriced_events"],
            }
            for operation, values in sorted(operations.items())
        ],
    }


def build_development_cost_lineage(
    evaluations_root: Path,
    *,
    min_version: int,
    max_version: int,
) -> dict[str, object]:
    """Aggregate isolated text-free evaluation usage ledgers without double-counting.

    ``min_version`` and ``max_version`` retain their original meaning: they
    select the evidence-planned RAG lineage. Full-context versions use an
    independent version namespace and all discovered ``full-context-vN-*``
    ledgers are included. Keeping those namespaces separate prevents, for
    example, RAG V1 and full-context V1 from being combined as one policy.
    """

    if min_version < 1 or max_version < min_version:
        raise ValueError("Invalid evidence-planned version range")
    if not evaluations_root.is_dir():
        raise EvaluationCostError(f"Evaluations directory does not exist: {evaluations_root}")

    matched: list[tuple[_StrategyRunIdentity, Path]] = []
    for path in evaluations_root.iterdir():
        if not path.is_dir():
            continue
        identity = _strategy_run_identity(
            path.name,
            min_rag_version=min_version,
            max_rag_version=max_version,
        )
        if identity is None:
            continue
        if (path / "usage.sqlite3").is_file():
            matched.append((identity, path))
    strategy_order = {"rag": 0, "full_context": 1}
    matched.sort(
        key=lambda item: (
            strategy_order.get(item[0].answer_strategy, 99),
            item[0].version_number,
            item[1].name,
        )
    )
    if not matched:
        raise EvaluationCostError("No matching evaluation usage ledgers were found")

    seen_response_ids: dict[str, str] = {}
    runs: list[dict[str, object]] = []
    strategy_version_events: dict[
        tuple[str, str], list[dict[str, object]]
    ] = defaultdict(list)
    all_events: list[dict[str, object]] = []
    strategy_identities: dict[tuple[str, str], _StrategyRunIdentity] = {}
    for strategy_identity, run_dir in matched:
        events = _read_usage_events(run_dir)
        for event in events:
            response_id = str(event["response_id"])
            prior = seen_response_ids.get(response_id)
            if prior is not None:
                raise EvaluationCostError(
                    "Provider response ID appears in more than one evaluation ledger: "
                    f"{response_id} ({prior}, {run_dir.name})"
                )
            seen_response_ids[response_id] = run_dir.name
        metadata = _run_metadata(run_dir)
        totals = _totals(events)
        run_identity = {
            "run_id": run_dir.name,
            "answer_strategy": strategy_identity.answer_strategy,
            "answer_strategy_version": strategy_identity.answer_strategy_version,
            "git_commit": metadata.get("git_commit"),
            "working_tree": metadata.get("working_tree"),
        }
        runs.append(
            {
                "run_id": run_dir.name,
                # policy_version remains as an alias for existing report
                # consumers. New consumers should use the explicit pair.
                "policy_version": strategy_identity.answer_strategy_version,
                "answer_strategy": strategy_identity.answer_strategy,
                "answer_strategy_version": (
                    strategy_identity.answer_strategy_version
                ),
                "run_identity": run_identity,
                **metadata,
                **totals,
            }
        )
        aggregate_key = strategy_identity.aggregate_key
        strategy_identities[aggregate_key] = strategy_identity
        strategy_version_events[aggregate_key].extend(events)
        all_events.extend(events)

    ordered_strategy_keys = sorted(
        strategy_version_events,
        key=lambda key: (
            strategy_order.get(key[0], 99),
            strategy_identities[key].version_number,
            key[1],
        ),
    )
    included_strategies: list[dict[str, object]] = []
    for strategy in ("rag", "full_context"):
        included_versions = [
            strategy_identities[key].version_number
            for key in ordered_strategy_keys
            if key[0] == strategy
        ]
        if included_versions:
            included_strategies.append(
                {
                    "answer_strategy": strategy,
                    "minimum_version": min(included_versions),
                    "maximum_version": max(included_versions),
                }
            )

    return {
        "schema": DEVELOPMENT_COST_LINEAGE_SCHEMA,
        "source": "isolated read-only runtime evaluation ledgers",
        "privacy": "text-free; no questions, answers, sources, or manuscript passages",
        "version_range": {
            "minimum": min_version,
            "maximum": max_version,
        },
        "included_strategies": included_strategies,
        "runs": runs,
        "versions": [
            {
                "policy_version": strategy_version,
                "answer_strategy": answer_strategy,
                "answer_strategy_version": strategy_version,
                "run_count": sum(
                    1
                    for run in runs
                    if run["answer_strategy"] == answer_strategy
                    and run["answer_strategy_version"] == strategy_version
                ),
                **_totals(strategy_version_events[(answer_strategy, strategy_version)]),
            }
            for answer_strategy, strategy_version in ordered_strategy_keys
        ],
        "total": {
            "run_count": len(runs),
            **_totals(all_events),
        },
    }


def render_development_cost_markdown(report: Mapping[str, object]) -> str:
    if report.get("schema") not in {
        DEVELOPMENT_COST_LINEAGE_SCHEMA,
        _LEGACY_DEVELOPMENT_COST_LINEAGE_SCHEMA,
    }:
        raise EvaluationCostError("Unsupported development cost lineage schema")
    version_range = report.get("version_range")
    runs = report.get("runs")
    versions = report.get("versions")
    total = report.get("total")
    if (
        not isinstance(version_range, Mapping)
        or not isinstance(runs, list)
        or not isinstance(versions, list)
        or not isinstance(total, Mapping)
    ):
        raise EvaluationCostError("Development cost lineage report is incomplete")

    lines = [
        "# Archivist development API cost lineage",
        "",
        "Generated from isolated local evaluation ledgers. This artifact is text-free: it contains",
        "no questions, answers, source passages, or manuscript text.",
        "",
        (
            f"RAG selection window: V{version_range['minimum']}–"
            f"V{version_range['maximum']}; matching RAG ledgers and all discovered "
            "full-context ledgers are included in separate strategy namespaces."
        ),
        "",
        "## Strategy-version totals",
        "",
        (
            "| Strategy | Policy | Runs | Calls | Tokens | Estimated USD | "
            "Unpriced events |"
        ),
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for version in versions:
        if not isinstance(version, Mapping):
            raise EvaluationCostError("Invalid version row in cost lineage report")
        lines.append(
            (
                "| {strategy} | {policy} | {runs} | {calls} | {tokens} | "
                "${cost} | {unpriced} |"
            ).format(
                strategy=_display_strategy(version),
                policy=_display_strategy_version(version),
                runs=version["run_count"],
                calls=version["calls"],
                tokens=version["tokens"],
                cost=version["estimated_cost_usd"],
                unpriced=version["unpriced_events"],
            )
        )
    lines.extend(
        [
            "",
            "## Run details",
            "",
            (
                "| Run | Strategy | Policy | Commit | Status | Items | Retries | "
                "Latency (s) | Operational cap | Calls | Tokens | Estimated USD |"
            ),
            "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for run in runs:
        if not isinstance(run, Mapping):
            raise EvaluationCostError("Invalid run row in cost lineage report")
        elapsed = run.get("total_elapsed_ms")
        elapsed_seconds = (
            f"{int(elapsed) / 1000:.3f}" if isinstance(elapsed, int) else "—"
        )
        retries = run.get("automatic_retries")
        operational_cap = run.get("operational_hard_cap_usd")
        commit = run.get("git_commit")
        lines.append(
            "| {run_id} | {strategy} | {policy} | {commit} | {status} | {items} | "
            "{retries} | {elapsed} | {authorized} | {calls} | {tokens} | ${cost} |".format(
                run_id=run["run_id"],
                strategy=_display_strategy(run),
                policy=_display_strategy_version(run),
                commit=str(commit)[:12] if isinstance(commit, str) else "—",
                status=run.get("status") or "—",
                items=run.get("item_count", 0),
                retries=retries if isinstance(retries, int) else "—",
                elapsed=elapsed_seconds,
                authorized=(
                    f"${operational_cap}"
                    if isinstance(operational_cap, str)
                    else "—"
                ),
                calls=run["calls"],
                tokens=run["tokens"],
                cost=run["estimated_cost_usd"],
            )
        )
    lines.extend(
        [
            "",
            "## Cumulative total",
            "",
            f"- Runs: **{total['run_count']}**",
            f"- API operations: **{total['calls']}**",
            f"- Priced tokens: **{total['tokens']}**",
            f"- Estimated API cost: **${total['estimated_cost_usd']}**",
            f"- Unpriced events: **{total['unpriced_events']}**",
            "",
            (
                "These are application estimates reconstructed from returned token usage. "
                "The provider invoice remains authoritative."
            ),
            "",
        ]
    )
    return "\n".join(lines)
