from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from evaluation_artifacts import (
    RETRIEVAL_DIAGNOSTICS_DIR_ENV,
    RETRIEVAL_DIAGNOSTICS_ENV,
    SMOKE_ARTIFACT_SCHEMA,
    SmokeArtifactRecorder,
    build_git_worktree_identity,
    validate_smoke_summary_artifacts,
)
from retrieval import FileTraceSink, RETRIEVAL_TRACE_SCHEMA

RUNNER_SHA256 = "f" * 64


def _git(project_root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _write_clean_project(project_root: Path) -> tuple[Path, Path]:
    project_root.mkdir()
    _git(project_root, "init", "--quiet")
    _git(project_root, "config", "user.email", "tests@example.invalid")
    _git(project_root, "config", "user.name", "Archivist Tests")
    _git(project_root, "config", "core.autocrlf", "false")

    (project_root / ".gitignore").write_text("runtime/\n", encoding="utf-8")
    (project_root / "uv.lock").write_text("synthetic lock\n", encoding="utf-8")
    (project_root / "tracked.txt").write_text("tracked baseline\n", encoding="utf-8")
    fixtures = project_root / "fixtures"
    output = project_root / "output"
    fixtures.mkdir()
    output.mkdir()
    chunks_path = output / "chunks.json"
    private_marker = "synthetic private corpus text"
    chunks_path.write_text(
        json.dumps([{"chunk_id": "synthetic_001", "text": private_marker}]),
        encoding="utf-8",
    )
    chunks_sha256 = hashlib.sha256(chunks_path.read_bytes()).hexdigest()
    manifest_path = fixtures / "corpus_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_schema": "archivist.corpus_manifest/1",
                "chunks_sha256": chunks_sha256,
                "chunks": [
                    {
                        "chunk_id": "synthetic_001",
                        "text_sha256": hashlib.sha256(
                            private_marker.encode("utf-8")
                        ).hexdigest(),
                    }
                ],
                "store": {
                    "collection_name": "synthetic",
                    "hnsw_space": "l2",
                    "embedding_model": "text-embedding-3-small",
                    "embedded_chunk_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    _git(project_root, "add", ".")
    _git(project_root, "commit", "--quiet", "-m", "synthetic baseline")
    return manifest_path, chunks_path


def _trace(
    recorder: SmokeArtifactRecorder,
    *,
    trace_id: str,
    query_sha256: str,
) -> dict[str, object]:
    corpus = recorder.corpus_identity
    return {
        "schema": RETRIEVAL_TRACE_SCHEMA,
        "trace_id": trace_id,
        "created_at": "2026-01-01T00:00:00+00:00",
        "retrieval_version": "faceted-hybrid-rrf-v2",
        "query": {
            "sha256": query_sha256,
            "char_count": 12,
            "mode": "standard",
        },
        "corpus": {
            "corpus_manifest_sha256": corpus["corpus_manifest_sha256"],
            "chunks_sha256": corpus["chunks_sha256"],
            "collection_name": corpus["collection_name"],
            "collection_count": corpus["embedded_chunk_count"],
            "hnsw_space": corpus["hnsw_space"],
        },
        "parameters": {},
        "candidates": {},
        "selection": {},
        "scope": {},
        "plan": {},
        "lanes": [],
        "evidence": {},
        "generation_contract": {},
    }


def test_full_smoke_summary_binds_corpus_identity_and_each_trace(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    manifest_path, chunks_path = _write_clean_project(project_root)
    run_root = project_root / "runtime" / "smoke"
    recorder = SmokeArtifactRecorder(
        run_root=run_root,
        project_root=project_root,
        manifest_path=manifest_path,
        chunks_path=chunks_path,
    )
    previous_enabled = os.environ.get(RETRIEVAL_DIAGNOSTICS_ENV)
    previous_root = os.environ.get(RETRIEVAL_DIAGNOSTICS_DIR_ENV)

    with recorder.capture_turn(1):
        assert os.environ[RETRIEVAL_DIAGNOSTICS_ENV] == "1"
        assert os.environ[RETRIEVAL_DIAGNOSTICS_DIR_ENV] == str(
            recorder.trace_root
        )
        FileTraceSink()(
            _trace(
                recorder,
                trace_id="a" * 32,
                query_sha256="1" * 64,
            )
        )

    assert os.environ.get(RETRIEVAL_DIAGNOSTICS_ENV) == previous_enabled
    assert os.environ.get(RETRIEVAL_DIAGNOSTICS_DIR_ENV) == previous_root
    summary_path = run_root / "summary.json"
    completed = recorder.write_summary(
        summary_path,
        {
            "schema": "archivist.smoke_run/1",
            "git_commit": recorder.run_identity["git_commit"],
            "runner_sha256": RUNNER_SHA256,
        },
        expected_turn_numbers=(1,),
    )

    artifacts = completed["artifacts"]
    assert artifacts["schema"] == SMOKE_ARTIFACT_SCHEMA
    assert artifacts["retrieval_trace_requirement"] == "required"
    assert artifacts["trace_count"] == 1
    assert artifacts["corpus"] == recorder.corpus_identity
    reference = artifacts["turns"][0]["retrieval_traces"][0]
    assert reference["trace_id"] == "a" * 32
    assert reference["query_sha256"] == "1" * 64
    assert reference["path"].startswith("retrieval-traces/")
    assert completed["run_identity"]["working_tree"] == "clean"
    assert completed["run_identity"]["dirty_fingerprint"] is None
    validate_smoke_summary_artifacts(
        json.loads(summary_path.read_text(encoding="utf-8")),
        run_root=run_root,
        expected_turn_numbers=(1,),
    )
    assert "synthetic private corpus text" not in summary_path.read_text(
        encoding="utf-8"
    )
    escaping = json.loads(json.dumps(completed))
    escaping["artifacts"]["turns"][0]["retrieval_traces"][0]["path"] = (
        "../escape.json"
    )
    with pytest.raises(ValueError, match="escapes the run directory"):
        validate_smoke_summary_artifacts(escaping, run_root=run_root)


def test_continuation_merges_prior_trace_without_recapturing_it(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    manifest_path, chunks_path = _write_clean_project(project_root)
    run_root = project_root / "runtime" / "smoke"
    first = SmokeArtifactRecorder(
        run_root=run_root,
        project_root=project_root,
        manifest_path=manifest_path,
        chunks_path=chunks_path,
    )
    with first.capture_turn(1):
        FileTraceSink()(
            _trace(first, trace_id="a" * 32, query_sha256="1" * 64)
        )
    partial = first.attach_to_summary(
        {
            "schema": "archivist.smoke_run/1",
            "runner_sha256": RUNNER_SHA256,
        },
        expected_turn_numbers=(1,),
    )

    continuation = SmokeArtifactRecorder(
        run_root=run_root,
        project_root=project_root,
        manifest_path=manifest_path,
        chunks_path=chunks_path,
    )
    with continuation.capture_turn(2):
        FileTraceSink()(
            _trace(
                continuation,
                trace_id="b" * 32,
                query_sha256="2" * 64,
            )
        )
    completed = continuation.attach_to_summary(
        partial,
        expected_turn_numbers=(1, 2),
    )

    assert completed["artifacts"]["trace_count"] == 2
    assert [
        turn["turn_number"] for turn in completed["artifacts"]["turns"]
    ] == [1, 2]


def test_resolver_only_summary_explicitly_allows_zero_traces(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    manifest_path, chunks_path = _write_clean_project(project_root)
    run_root = project_root / "runtime" / "resolver-smoke"
    recorder = SmokeArtifactRecorder(
        run_root=run_root,
        project_root=project_root,
        manifest_path=manifest_path,
        chunks_path=chunks_path,
    )

    completed = recorder.attach_to_summary(
        {
            "schema": "archivist.resolver_smoke/1",
            "runner_sha256": RUNNER_SHA256,
        },
        expected_turn_numbers=(),
        require_retrieval_traces=False,
    )

    assert completed["artifacts"]["retrieval_trace_requirement"] == "not_applicable"
    assert completed["artifacts"]["trace_count"] == 0
    assert completed["artifacts"]["turns"] == []
    validate_smoke_summary_artifacts(
        completed,
        run_root=run_root,
        expected_turn_numbers=(),
    )


@pytest.mark.parametrize(
    ("field", "invalid_value", "message"),
    [
        ("runner_sha256", None, "runner_sha256"),
        ("manifest_chunk_count", None, "manifest_chunk_count"),
        ("embedded_chunk_count", 2, "embedded_chunk_count"),
        ("collection_name", None, "collection_name"),
        ("hnsw_space", None, "hnsw_space"),
        ("embedding_model", None, "embedding_model"),
    ],
)
def test_smoke_summary_requires_complete_reproducibility_identity(
    tmp_path: Path,
    field: str,
    invalid_value: object,
    message: str,
) -> None:
    project_root = tmp_path / "project"
    manifest_path, chunks_path = _write_clean_project(project_root)
    run_root = project_root / "runtime" / "resolver-smoke"
    recorder = SmokeArtifactRecorder(
        run_root=run_root,
        project_root=project_root,
        manifest_path=manifest_path,
        chunks_path=chunks_path,
    )
    completed = recorder.attach_to_summary(
        {
            "schema": "archivist.resolver_smoke/1",
            "runner_sha256": RUNNER_SHA256,
        },
        expected_turn_numbers=(),
        require_retrieval_traces=False,
    )
    invalid = json.loads(json.dumps(completed))
    if field == "runner_sha256":
        invalid[field] = invalid_value
    else:
        invalid["artifacts"]["corpus"][field] = invalid_value

    with pytest.raises(ValueError, match=message):
        validate_smoke_summary_artifacts(
            invalid,
            run_root=run_root,
            expected_turn_numbers=(),
        )


def test_completed_full_turn_without_trace_is_a_hard_artifact_failure(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    manifest_path, chunks_path = _write_clean_project(project_root)
    recorder = SmokeArtifactRecorder(
        run_root=project_root / "runtime" / "smoke",
        project_root=project_root,
        manifest_path=manifest_path,
        chunks_path=chunks_path,
    )

    with pytest.raises(RuntimeError, match="completed without a retrieval trace"):
        with recorder.capture_turn(1):
            pass


def test_artifact_recorder_rejects_a_trace_containing_private_text(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    manifest_path, chunks_path = _write_clean_project(project_root)
    recorder = SmokeArtifactRecorder(
        run_root=project_root / "runtime" / "smoke",
        project_root=project_root,
        manifest_path=manifest_path,
        chunks_path=chunks_path,
    )

    with pytest.raises(ValueError, match="forbidden field"):
        with recorder.capture_turn(1):
            malicious = _trace(
                recorder,
                trace_id="a" * 32,
                query_sha256="1" * 64,
            )
            malicious["text"] = "synthetic private corpus text"
            target = recorder.trace_root / "malicious.json"
            target.write_text(json.dumps(malicious), encoding="utf-8")


def test_artifact_recorder_rejects_private_text_under_unknown_nested_key(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    manifest_path, chunks_path = _write_clean_project(project_root)
    recorder = SmokeArtifactRecorder(
        run_root=project_root / "runtime" / "smoke",
        project_root=project_root,
        manifest_path=manifest_path,
        chunks_path=chunks_path,
    )

    with pytest.raises(ValueError, match="unsupported field.*body"):
        with recorder.capture_turn(1):
            malicious = _trace(
                recorder,
                trace_id="a" * 32,
                query_sha256="1" * 64,
            )
            malicious["selection"] = {
                "context": [
                    {
                        "chunk_id": "synthetic_001",
                        "body": "synthetic private corpus text",
                    }
                ]
            }
            target = recorder.trace_root / "malicious.json"
            target.write_text(json.dumps(malicious), encoding="utf-8")


def test_artifact_recorder_rejects_prose_in_hash_labeled_field(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    manifest_path, chunks_path = _write_clean_project(project_root)
    recorder = SmokeArtifactRecorder(
        run_root=project_root / "runtime" / "smoke",
        project_root=project_root,
        manifest_path=manifest_path,
        chunks_path=chunks_path,
    )

    with pytest.raises(ValueError, match="must be a SHA-256"):
        with recorder.capture_turn(1):
            malicious = _trace(
                recorder,
                trace_id="a" * 32,
                query_sha256="1" * 64,
            )
            malicious["generation_contract"] = {
                "instructions_sha256": "synthetic private generation prompt"
            }
            target = recorder.trace_root / "malicious.json"
            target.write_text(json.dumps(malicious), encoding="utf-8")


def test_dirty_fingerprint_hashes_diff_then_untracked_files_in_status_order(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_clean_project(project_root)
    clean = build_git_worktree_identity(project_root)
    assert clean["working_tree"] == "clean"
    assert clean["dirty_fingerprint"] is None

    (project_root / "tracked.txt").write_bytes(b"tracked change\n")
    second = project_root / "z-untracked.bin"
    first = project_root / "a-untracked.bin"
    second.write_bytes(b"second")
    first.write_bytes(b"first")
    ignored = project_root / "runtime" / "ignored.bin"
    ignored.parent.mkdir()
    ignored.write_bytes(b"ignored")

    expected = hashlib.sha256()
    expected.update(_git(project_root, "diff", "--binary", "HEAD", "--"))
    expected.update(first.read_bytes())
    expected.update(second.read_bytes())
    dirty = build_git_worktree_identity(project_root)

    assert dirty["working_tree"] == "dirty"
    assert dirty["dirty_fingerprint"] == expected.hexdigest()
