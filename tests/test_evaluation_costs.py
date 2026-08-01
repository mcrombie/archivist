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


def test_mixed_strategies_keep_independent_version_namespaces(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evaluations"
    _write_run(
        root,
        "evidence-planned-v1-clean-1",
        response_prefix="rag-v1",
        costs=(100_000_000,),
        tokens=(100,),
        operations=("answer_generation",),
    )
    _write_run(
        root,
        "evidence-planned-v18-clean-1",
        response_prefix="rag-v18",
        costs=(200_000_000,),
        tokens=(200,),
        operations=("answer_generation",),
    )
    _write_run(
        root,
        "full-context-v1-g007-1",
        response_prefix="full-context-v1",
        costs=(300_000_000,),
        tokens=(300,),
        operations=("answer_generation",),
    )

    report = build_development_cost_lineage(
        root,
        min_version=1,
        max_version=18,
    )

    assert [
        (row["answer_strategy"], row["answer_strategy_version"])
        for row in report["versions"]
    ] == [
        ("rag", "evidence-planned-v1"),
        ("rag", "evidence-planned-v18"),
        ("full_context", "full-context-v1"),
    ]
    assert [
        (run["answer_strategy"], run["answer_strategy_version"])
        for run in report["runs"]
    ] == [
        ("rag", "evidence-planned-v1"),
        ("rag", "evidence-planned-v18"),
        ("full_context", "full-context-v1"),
    ]
    assert report["runs"][2]["run_identity"] == {
        "run_id": "full-context-v1-g007-1",
        "answer_strategy": "full_context",
        "answer_strategy_version": "full-context-v1",
        "git_commit": "a" * 40,
        "working_tree": "clean",
    }
    assert report["included_strategies"] == [
        {
            "answer_strategy": "rag",
            "minimum_version": 1,
            "maximum_version": 18,
        },
        {
            "answer_strategy": "full_context",
            "minimum_version": 1,
            "maximum_version": 1,
        },
    ]
    assert report["total"]["run_count"] == 3
    assert report["total"]["estimated_cost_usd"] == "0.600000000"


def test_full_context_is_included_outside_the_requested_rag_version_range(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evaluations"
    _write_run(
        root,
        "evidence-planned-v18-clean-1",
        response_prefix="rag-v18",
        costs=(100_000_000,),
        tokens=(100,),
        operations=("answer_generation",),
    )
    _write_run(
        root,
        "full-context-v1-g007-1",
        response_prefix="full-context-v1",
        costs=(200_000_000,),
        tokens=(200,),
        operations=("answer_generation",),
    )

    report = build_development_cost_lineage(
        root,
        min_version=18,
        max_version=18,
    )

    assert [run["run_id"] for run in report["runs"]] == [
        "evidence-planned-v18-clean-1",
        "full-context-v1-g007-1",
    ]
    assert report["total"]["estimated_cost_usd"] == "0.300000000"


def test_rejects_duplicate_provider_response_ids_across_strategies(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evaluations"
    _write_run(
        root,
        "evidence-planned-v18-clean-1",
        response_prefix="same-provider-response",
        costs=(1,),
        tokens=(1,),
        operations=("answer_generation",),
    )
    _write_run(
        root,
        "full-context-v1-g007-1",
        response_prefix="same-provider-response",
        costs=(1,),
        tokens=(1,),
        operations=("answer_generation",),
    )

    with pytest.raises(EvaluationCostError, match="more than one evaluation ledger"):
        build_development_cost_lineage(
            root,
            min_version=18,
            max_version=18,
        )


def test_mixed_strategy_json_and_markdown_remain_text_free(tmp_path: Path) -> None:
    root = tmp_path / "evaluations"
    _write_run(
        root,
        "evidence-planned-v18-clean-1",
        response_prefix="rag",
        costs=(1,),
        tokens=(1,),
        operations=("answer_generation",),
    )
    _write_run(
        root,
        "full-context-v1-g007-1",
        response_prefix="full-context",
        costs=(1,),
        tokens=(1,),
        operations=("answer_generation",),
    )

    report = build_development_cost_lineage(
        root,
        min_version=18,
        max_version=18,
    )
    serialized = json.dumps(report)
    markdown = render_development_cost_markdown(report)

    assert "must not reach the report" not in serialized
    assert "must not reach the report" not in markdown
    assert "full_context" in serialized
    assert "full_context" in markdown


def test_markdown_renderer_accepts_pre_strategy_lineage_reports(tmp_path: Path) -> None:
    root = tmp_path / "evaluations"
    _write_run(
        root,
        "evidence-planned-v18-clean-1",
        response_prefix="rag",
        costs=(1,),
        tokens=(1,),
        operations=("answer_generation",),
    )
    report = build_development_cost_lineage(
        root,
        min_version=18,
        max_version=18,
    )
    legacy_report = json.loads(json.dumps(report))
    legacy_report["schema"] = "archivist.development_cost_lineage/1"
    legacy_report.pop("included_strategies")
    for row in legacy_report["runs"]:
        row.pop("answer_strategy")
        row.pop("answer_strategy_version")
        row.pop("run_identity")
    for row in legacy_report["versions"]:
        row.pop("answer_strategy")
        row.pop("answer_strategy_version")

    markdown = render_development_cost_markdown(legacy_report)

    assert "| rag | evidence-planned-v18 |" in markdown


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


def test_reports_failed_attempt_status_cap_and_retry_policy(tmp_path: Path) -> None:
    root = tmp_path / "evaluations"
    run_dir = _write_run(
        root,
        "evidence-planned-v24-clean-1",
        response_prefix="unused",
        costs=(),
        tokens=(),
        operations=(),
    )
    (run_dir / "run_summary.json").unlink()
    (run_dir / "attempt.json").write_text(
        json.dumps(
            {
                "status": "error",
                "authorized_max_usd": "3.00",
                "automatic_retries": 0,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "preflight.json").write_text(
        json.dumps(
            {
                "worktree": {
                    "git_commit": "b" * 40,
                    "working_tree": "clean",
                },
                "cost_estimate": {
                    "proposed_hard_cap_usd": "3.00",
                    "owner_authorized_max_usd": "10.00",
                },
                "development_cohort": {"automatic_retries": 0},
            }
        ),
        encoding="utf-8",
    )

    report = build_development_cost_lineage(
        root,
        min_version=24,
        max_version=24,
    )

    run = report["runs"][0]
    assert run["status"] == "error"
    assert run["operational_hard_cap_usd"] == "3.00"
    assert run["owner_authorized_max_usd"] == "10.00"
    assert run["authorized_max_usd"] == "3.00"
    assert run["automatic_retries"] == 0
