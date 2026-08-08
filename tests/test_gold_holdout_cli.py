from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_gold_holdout import CandidateLockError, validate_candidate_lock


COMMIT = "a" * 40
PROJECT_ROOT = Path("synthetic-project")
ANSWER_EVALUATION_PATHS = (
    "fixtures/evaluation_model_catalog.json",
    "scripts/run_answer_evaluation.py",
    "src/answer_evaluation.py",
    "src/evaluation_judge.py",
    "src/evaluation_reporting.py",
    "src/evaluation_results.py",
    "src/evaluation_scoring.py",
    "tests/test_answer_evaluation.py",
    "tests/test_answer_evaluation_cli.py",
    "tests/test_evaluation_judge.py",
    "tests/test_evaluation_reporting.py",
    "tests/test_evaluation_results.py",
    "tests/test_evaluation_scoring.py",
)


def _completed(
    stdout: str = "",
    *,
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"],
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def test_candidate_lock_allows_only_declared_evaluation_files(monkeypatch):
    responses = iter(
        (
            _completed(),
            _completed(),
            _completed(),
            _completed(
                "fixtures/gold_set.json\n"
                "fixtures/gold_set.provenance.json\n"
                "docs/gold_annotation_prompt_claude.md\n"
                "src/gold_provenance.py\n"
            ),
        )
    )
    monkeypatch.setattr(
        "validate_gold_holdout._run_git",
        lambda *_args, **_kwargs: next(responses),
    )

    changed = validate_candidate_lock(PROJECT_ROOT, COMMIT)

    assert changed == (
        "fixtures/gold_set.json",
        "fixtures/gold_set.provenance.json",
        "docs/gold_annotation_prompt_claude.md",
        "src/gold_provenance.py",
    )


def test_candidate_lock_allows_exact_answer_evaluation_files(monkeypatch):
    responses = iter(
        (
            _completed(),
            _completed(),
            _completed(),
            _completed("\n".join(ANSWER_EVALUATION_PATHS) + "\n"),
        )
    )
    monkeypatch.setattr(
        "validate_gold_holdout._run_git",
        lambda *_args, **_kwargs: next(responses),
    )

    assert validate_candidate_lock(PROJECT_ROOT, COMMIT) == ANSWER_EVALUATION_PATHS


@pytest.mark.parametrize(
    "path",
    [
        "fixtures/evaluation_model_catalog.local.json",
        "scripts/run_answer_evaluation_local.py",
        "src/answer_evaluation_helpers.py",
        "src/evaluation_judge/prompt.py",
        "src/evaluation_scoring_helpers.py",
        "tests/test_answer_evaluation_extra.py",
    ],
)
def test_candidate_lock_rejects_neighboring_or_broad_evaluation_paths(
    monkeypatch,
    path,
):
    responses = iter(
        (
            _completed(),
            _completed(),
            _completed(),
            _completed(f"{path}\n"),
        )
    )
    monkeypatch.setattr(
        "validate_gold_holdout._run_git",
        lambda *_args, **_kwargs: next(responses),
    )

    with pytest.raises(CandidateLockError, match=path.replace(".", r"\.")):
        validate_candidate_lock(PROJECT_ROOT, COMMIT)


def test_candidate_lock_rejects_dirty_tree(monkeypatch):
    responses = iter(
        (
            _completed(),
            _completed(),
            _completed("?? runtime-draft.json\n"),
        )
    )
    monkeypatch.setattr(
        "validate_gold_holdout._run_git",
        lambda *_args, **_kwargs: next(responses),
    )

    with pytest.raises(CandidateLockError, match="working tree must be clean"):
        validate_candidate_lock(PROJECT_ROOT, COMMIT)


def test_candidate_lock_rejects_system_changes_after_freeze(monkeypatch):
    responses = iter(
        (
            _completed(),
            _completed(),
            _completed(),
            _completed("src/retrieval.py\nfixtures/gold_set.json\n"),
        )
    )
    monkeypatch.setattr(
        "validate_gold_holdout._run_git",
        lambda *_args, **_kwargs: next(responses),
    )

    with pytest.raises(CandidateLockError, match="src/retrieval.py"):
        validate_candidate_lock(PROJECT_ROOT, COMMIT)


def test_candidate_lock_requires_existing_ancestor(monkeypatch):
    responses = iter(
        (
            _completed(),
            _completed(returncode=1),
        )
    )
    monkeypatch.setattr(
        "validate_gold_holdout._run_git",
        lambda *_args, **_kwargs: next(responses),
    )

    with pytest.raises(CandidateLockError, match="not an ancestor"):
        validate_candidate_lock(PROJECT_ROOT, COMMIT)


def test_candidate_lock_requires_full_commit():
    with pytest.raises(CandidateLockError, match="full lowercase"):
        validate_candidate_lock(PROJECT_ROOT, "bf424c8")
