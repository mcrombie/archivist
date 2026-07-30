from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any


DEVELOPMENT_COST_LINEAGE_SCHEMA = "archivist.development_cost_lineage/1"
_RUN_PATTERN = re.compile(r"^evidence-planned-v(?P<version>[0-9]+)(?:-|$)")
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
    """Aggregate isolated text-free evaluation usage ledgers without double-counting."""

    if min_version < 1 or max_version < min_version:
        raise ValueError("Invalid evidence-planned version range")
    if not evaluations_root.is_dir():
        raise EvaluationCostError(f"Evaluations directory does not exist: {evaluations_root}")

    matched: list[tuple[int, Path]] = []
    for path in evaluations_root.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_PATTERN.match(path.name)
        if match is None:
            continue
        version = int(match.group("version"))
        if min_version <= version <= max_version and (path / "usage.sqlite3").is_file():
            matched.append((version, path))
    matched.sort(key=lambda item: (item[0], item[1].name))
    if not matched:
        raise EvaluationCostError("No matching evaluation usage ledgers were found")

    seen_response_ids: dict[str, str] = {}
    runs: list[dict[str, object]] = []
    version_events: dict[int, list[dict[str, object]]] = defaultdict(list)
    all_events: list[dict[str, object]] = []
    for version, run_dir in matched:
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
        runs.append(
            {
                "run_id": run_dir.name,
                "policy_version": f"evidence-planned-v{version}",
                **metadata,
                **totals,
            }
        )
        version_events[version].extend(events)
        all_events.extend(events)

    return {
        "schema": DEVELOPMENT_COST_LINEAGE_SCHEMA,
        "source": "isolated read-only runtime evaluation ledgers",
        "privacy": "text-free; no questions, answers, sources, or manuscript passages",
        "version_range": {
            "minimum": min_version,
            "maximum": max_version,
        },
        "runs": runs,
        "versions": [
            {
                "policy_version": f"evidence-planned-v{version}",
                "run_count": sum(
                    1
                    for run in runs
                    if run["policy_version"] == f"evidence-planned-v{version}"
                ),
                **_totals(version_events[version]),
            }
            for version in sorted(version_events)
        ],
        "total": {
            "run_count": len(runs),
            **_totals(all_events),
        },
    }


def render_development_cost_markdown(report: Mapping[str, object]) -> str:
    if report.get("schema") != DEVELOPMENT_COST_LINEAGE_SCHEMA:
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
            f"Included policy versions: V{version_range['minimum']}–"
            f"V{version_range['maximum']}."
        ),
        "",
        "## Version totals",
        "",
        "| Policy | Runs | Calls | Tokens | Estimated USD | Unpriced events |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for version in versions:
        if not isinstance(version, Mapping):
            raise EvaluationCostError("Invalid version row in cost lineage report")
        lines.append(
            "| {policy} | {runs} | {calls} | {tokens} | ${cost} | {unpriced} |".format(
                policy=version["policy_version"],
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
                "| Run | Commit | Status | Items | Retries | Latency (s) | "
                "Operational cap | Calls | Tokens | Estimated USD |"
            ),
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
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
            "| {run_id} | {commit} | {status} | {items} | {retries} | {elapsed} | "
            "{authorized} | {calls} | {tokens} | ${cost} |".format(
                run_id=run["run_id"],
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
