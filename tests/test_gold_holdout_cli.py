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


def test_candidate_lock_allows_only_declared_evaluation_files(monkeypatch, tmp_path):
    responses = iter(
        (
            _completed(),
            _completed(),
            _completed(),
            _completed(
                "fixtures/gold_set.json\n"
                "fixtures/gold_set.provenance.json\n"
                "src/gold_provenance.py\n"
            ),
        )
    )
    monkeypatch.setattr(
        "validate_gold_holdout._run_git",
        lambda *_args, **_kwargs: next(responses),
    )

    changed = validate_candidate_lock(tmp_path, COMMIT)

    assert changed == (
        "fixtures/gold_set.json",
        "fixtures/gold_set.provenance.json",
        "src/gold_provenance.py",
    )


def test_candidate_lock_rejects_dirty_tree(monkeypatch, tmp_path):
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
        validate_candidate_lock(tmp_path, COMMIT)


def test_candidate_lock_rejects_system_changes_after_freeze(monkeypatch, tmp_path):
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
        validate_candidate_lock(tmp_path, COMMIT)


def test_candidate_lock_requires_existing_ancestor(monkeypatch, tmp_path):
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
        validate_candidate_lock(tmp_path, COMMIT)


def test_candidate_lock_requires_full_commit(tmp_path):
    with pytest.raises(CandidateLockError, match="full lowercase"):
        validate_candidate_lock(tmp_path, "bf424c8")
