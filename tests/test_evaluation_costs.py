from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from evaluation_costs import (
    DEVELOPMENT_COST_LINEAGE_SCHEMA,
    EvaluationCostError,
    build_development_cost_lineage,
    render_development_cost_markdown,
)


def _write_run(
    root: Path,
    name: str,
    *,
    response_prefix: str,
    costs: tuple[int, ...],
    tokens: tuple[int, ...],
    operations: tuple[str, ...],
    commit: str = "a" * 40,
) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True)
    connection = sqlite3.connect(run_dir / "usage.sqlite3")
    connection.execute(
        """
        CREATE TABLE usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            response_id TEXT NOT NULL UNIQUE,
            operation TEXT NOT NULL,
            total_tokens INTEGER NOT NULL,
            estimated_cost_nano_usd INTEGER,
            unpriced INTEGER NOT NULL
        )
        """
    )
    for index, (cost, token_count, operation) in enumerate(
        zip(costs, tokens, operations, strict=True),
        start=1,
    ):
        connection.execute(
            """
            INSERT INTO usage_events (
                response_id, operation, total_tokens,
                estimated_cost_nano_usd, unpriced
            ) VALUES (?, ?, ?, ?, 0)
            """,
            (
                f"{response_prefix}-{index}",
                operation,
                token_count,
                cost,
            ),
        )
    connection.commit()
    connection.close()
    (run_dir / "run_summary.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "authorized_max_usd": "0.50",
                "automatic_retries": 0,
                "formal_run_of_record": False,
                "run_identity": {
                    "git_commit": commit,
                    "working_tree": "clean",
                },
                "items": [
                    {
                        "item_id": "G007",
                        "elapsed_ms": 12_345,
                        "private_answer": "must not reach the report",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def test_builds_text_free_version_and_cumulative_totals(tmp_path: Path) -> None:
    root = tmp_path / "evaluations"
    _write_run(
        root,
        "evidence-planned-v18-clean-1",
        response_prefix="v18",
        costs=(100_000_000, 20_000_000),
        tokens=(1000, 200),
        operations=("answer_generation", "query_planning"),
    )
    _write_run(
        root,
        "evidence-planned-v19-confirm-1",
        response_prefix="v19a",
        costs=(50_000_000,),
        tokens=(500,),
        operations=("answer_generation",),
    )
    _write_run(
        root,
        "evidence-planned-v19-continuation-1",
        response_prefix="v19b",
        costs=(10_000,),
        tokens=(50,),
        operations=("query_embedding",),
    )

    report = build_development_cost_lineage(
        root,
        min_version=18,
        max_version=19,
    )

    assert report["schema"] == DEVELOPMENT_COST_LINEAGE_SCHEMA
    assert report["total"] == {
        "run_count": 3,
        "calls": 4,
        "tokens": 1750,
        "estimated_cost_usd": "0.170010000",
        "unpriced_events": 0,
        "operations": [
            {
                "operation": "answer_generation",
                "calls": 2,
                "tokens": 1500,
                "estimated_cost_usd": "0.150000000",
                "unpriced_events": 0,
            },
            {
                "operation": "query_embedding",
                "calls": 1,
                "tokens": 50,
                "estimated_cost_usd": "0.000010000",
                "unpriced_events": 0,
            },
            {
                "operation": "query_planning",
                "calls": 1,
                "tokens": 200,
                "estimated_cost_usd": "0.020000000",
                "unpriced_events": 0,
            },
        ],
    }
    assert [row["run_count"] for row in report["versions"]] == [1, 2]
    assert report["runs"][0]["item_ids"] == ["G007"]
    assert report["runs"][0]["total_elapsed_ms"] == 12_345
    serialized = json.dumps(report)
    markdown = render_development_cost_markdown(report)
    assert "must not reach the report" not in serialized
    assert "must not reach the report" not in markdown
    assert "$0.170010000" in markdown


def test_rejects_duplicate_provider_response_ids(tmp_path: Path) -> None:
    root = tmp_path / "evaluations"
    _write_run(
        root,
        "evidence-planned-v18-clean-1",
        response_prefix="duplicate",
        costs=(1,),
        tokens=(1,),
        operations=("query_embedding",),
    )
    _write_run(
        root,
        "evidence-planned-v19-clean-1",
        response_prefix="duplicate",
        costs=(1,),
        tokens=(1,),
        operations=("query_embedding",),
    )

    with pytest.raises(EvaluationCostError, match="more than one evaluation ledger"):
        build_development_cost_lineage(
            root,
            min_version=18,
            max_version=19,
        )


def test_ignores_versions_outside_requested_range(tmp_path: Path) -> None:
    root = tmp_path / "evaluations"
    _write_run(
        root,
        "evidence-planned-v17-clean-1",
        response_prefix="v17",
        costs=(900_000_000,),
        tokens=(900,),
        operations=("answer_generation",),
    )
    _write_run(
        root,
        "evidence-planned-v18-clean-1",
        response_prefix="v18",
        costs=(100_000_000,),
        tokens=(100,),
        operations=("answer_generation",),
    )

    report = build_development_cost_lineage(
        root,
        min_version=18,
        max_version=18,
    )

    assert report["total"]["run_count"] == 1
    assert report["total"]["estimated_cost_usd"] == "0.100000000"
