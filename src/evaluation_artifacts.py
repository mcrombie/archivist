from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from retrieval_trace_contract import (
    RETRIEVAL_TRACE_SCHEMA,
    validate_text_free_retrieval_trace,
)

SMOKE_ARTIFACT_SCHEMA = "archivist.smoke_artifacts/1"
RETRIEVAL_DIAGNOSTICS_ENV = "ARCHIVIST_RETRIEVAL_DIAGNOSTICS"
RETRIEVAL_DIAGNOSTICS_DIR_ENV = "ARCHIVIST_RETRIEVAL_DIAGNOSTICS_DIR"

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_GIT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_TRACE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class _TurnCapture:
    turn_number: int
    known_paths: frozenset[Path]


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_git_worktree_identity(project_root: Path) -> dict[str, object]:
    """Return the commit and exact clean/dirty identity required by AGENTS.md."""
    project_root = project_root.resolve()
    commit = _git_output(
        project_root,
        "rev-parse",
        "HEAD",
    ).decode("ascii").strip()
    if not _GIT_COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeError("git rev-parse HEAD did not return a valid object ID")

    status = _git_output(
        project_root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    working_tree = "dirty" if status else "clean"
    dirty_fingerprint: str | None = None
    if status:
        digest = hashlib.sha256()
        digest.update(_git_output(project_root, "diff", "--binary", "HEAD", "--"))
        for record in status.split(b"\0"):
            if not record or record[:2] != b"??":
                continue
            if len(record) < 4 or record[2:3] != b" ":
                raise RuntimeError("Could not parse git porcelain status")
            relative_name = os.fsdecode(record[3:])
            untracked_path = (project_root / relative_name).resolve()
            try:
                untracked_path.relative_to(project_root)
            except ValueError as exc:
                raise RuntimeError(
                    "Untracked git path escaped the project root"
                ) from exc
            if not untracked_path.is_file():
                raise RuntimeError(
                    f"Untracked git path is not a readable file: {relative_name}"
                )
            digest.update(untracked_path.read_bytes())
        dirty_fingerprint = digest.hexdigest()

    lock_path = project_root / "uv.lock"
    return {
        "git_commit": commit,
        "working_tree": working_tree,
        "dirty_fingerprint": dirty_fingerprint,
        "dependency_lock_sha256": (
            sha256_file(lock_path) if lock_path.is_file() else None
        ),
    }


def _git_output(project_root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=project_root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(arguments)} failed: {stderr}")
    return completed.stdout


def build_corpus_identity(
    *,
    manifest_path: Path,
    chunks_path: Path,
) -> dict[str, object]:
    """Build the text-free corpus identity required by a smoke summary."""
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Corpus manifest is not valid JSON: {manifest_path}") from exc
    if not isinstance(manifest, Mapping):
        raise ValueError("Corpus manifest must be a JSON object")

    manifest_schema = manifest.get("manifest_schema")
    if not isinstance(manifest_schema, str) or not manifest_schema:
        raise ValueError("Corpus manifest is missing manifest_schema")
    chunks = manifest.get("chunks")
    if not isinstance(chunks, list) or not all(
        isinstance(chunk, Mapping) for chunk in chunks
    ):
        raise ValueError("Corpus manifest chunks must be a list of objects")
    if any(
        any(str(key).casefold() == "text" for key in chunk)
        for chunk in chunks
    ):
        raise ValueError("Corpus manifest must not contain manuscript chunk text")

    actual_chunks_sha256 = sha256_file(chunks_path)
    declared_chunks_sha256 = manifest.get("chunks_sha256")
    if (
        not isinstance(declared_chunks_sha256, str)
        or not _SHA256_PATTERN.fullmatch(declared_chunks_sha256)
    ):
        raise ValueError("Corpus manifest is missing a valid chunks_sha256")
    if declared_chunks_sha256 != actual_chunks_sha256:
        raise ValueError(
            "Corpus manifest chunks_sha256 does not match the active chunks file"
        )

    store = manifest.get("store")
    if not isinstance(store, Mapping):
        raise ValueError("Corpus manifest is missing store identity")
    embedded_chunk_count = store.get("embedded_chunk_count")
    if not isinstance(embedded_chunk_count, int) or embedded_chunk_count < 0:
        raise ValueError("Corpus manifest has an invalid embedded_chunk_count")

    return {
        "manifest_schema": manifest_schema,
        "corpus_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "chunks_sha256": actual_chunks_sha256,
        "manifest_chunk_count": len(chunks),
        "embedded_chunk_count": embedded_chunk_count,
        "collection_name": _required_nonempty_string(store, "collection_name"),
        "hnsw_space": _required_nonempty_string(store, "hnsw_space"),
        "embedding_model": _required_nonempty_string(store, "embedding_model"),
    }


def _required_nonempty_string(value: Mapping[str, object], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise ValueError(f"Corpus manifest store is missing {field}")
    return result


def _validate_trace_payload(
    trace: object,
    corpus_identity: Mapping[str, object],
) -> Mapping[str, object]:
    if not isinstance(trace, Mapping):
        raise ValueError("Retrieval trace must be a JSON object")
    if trace.get("schema") != RETRIEVAL_TRACE_SCHEMA:
        raise ValueError("Retrieval trace schema is missing or unsupported")
    validate_text_free_retrieval_trace(trace)

    trace_id = trace.get("trace_id")
    if not isinstance(trace_id, str) or not _TRACE_ID_PATTERN.fullmatch(trace_id):
        raise ValueError("Retrieval trace has an invalid trace_id")
    query = trace.get("query")
    if not isinstance(query, Mapping):
        raise ValueError("Retrieval trace is missing hashed query diagnostics")
    query_sha256 = query.get("sha256")
    if not isinstance(query_sha256, str) or not _SHA256_PATTERN.fullmatch(
        query_sha256
    ):
        raise ValueError("Retrieval trace query is missing a valid SHA-256")

    corpus = trace.get("corpus")
    if not isinstance(corpus, Mapping):
        raise ValueError("Retrieval trace is missing corpus identity")
    for field in ("corpus_manifest_sha256", "chunks_sha256"):
        if corpus.get(field) != corpus_identity.get(field):
            raise ValueError(
                f"Retrieval trace {field} does not match the smoke corpus identity"
            )
    for field in ("collection_name", "hnsw_space"):
        actual = corpus.get(field)
        if actual is not None and actual != corpus_identity.get(field):
            raise ValueError(
                f"Retrieval trace {field} does not match the smoke corpus identity"
            )
    collection_count = corpus.get("collection_count")
    if (
        collection_count is not None
        and collection_count != corpus_identity.get("embedded_chunk_count")
    ):
        raise ValueError(
            "Retrieval trace collection_count does not match the smoke corpus identity"
        )
    return trace


def _trace_reference(
    *,
    trace_path: Path,
    run_root: Path,
    corpus_identity: Mapping[str, object],
) -> dict[str, object]:
    try:
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Retrieval trace is not valid JSON: {trace_path}") from exc
    validated = _validate_trace_payload(trace, corpus_identity)
    query = validated["query"]
    assert isinstance(query, Mapping)
    relative_path = trace_path.resolve().relative_to(run_root.resolve())
    return {
        "schema": RETRIEVAL_TRACE_SCHEMA,
        "trace_id": validated["trace_id"],
        "path": relative_path.as_posix(),
        "sha256": sha256_file(trace_path),
        "query_sha256": query["sha256"],
        "retrieval_version": str(validated.get("retrieval_version") or ""),
    }


class SmokeArtifactRecorder:
    """Bind each paid smoke turn to its text-free retrieval trace and corpus."""

    def __init__(
        self,
        *,
        run_root: Path,
        project_root: Path,
        manifest_path: Path,
        chunks_path: Path,
    ) -> None:
        self.run_root = run_root.resolve()
        self.trace_root = self.run_root / "retrieval-traces"
        self.run_identity = build_git_worktree_identity(project_root)
        self.corpus_identity = build_corpus_identity(
            manifest_path=manifest_path,
            chunks_path=chunks_path,
        )
        self._turns: dict[int, list[dict[str, object]]] = {}
        self._capture_active = False

    def environment_overrides(self) -> dict[str, str]:
        """Return the environment required to direct traces into this run."""
        return {
            RETRIEVAL_DIAGNOSTICS_ENV: "1",
            RETRIEVAL_DIAGNOSTICS_DIR_ENV: str(self.trace_root),
        }

    @contextmanager
    def capture_turn(self, turn_number: int) -> Iterator[None]:
        """Require and bind every new retrieval trace emitted by one turn."""
        if not isinstance(turn_number, int) or isinstance(turn_number, bool):
            raise TypeError("turn_number must be an integer")
        if turn_number <= 0:
            raise ValueError("turn_number must be greater than zero")
        if self._capture_active:
            raise RuntimeError("Smoke retrieval-trace captures cannot be nested")
        if turn_number in self._turns:
            raise RuntimeError(f"Turn {turn_number} already has retrieval traces")

        self.trace_root.mkdir(parents=True, exist_ok=True)
        capture = _TurnCapture(
            turn_number=turn_number,
            known_paths=frozenset(self._trace_paths()),
        )
        previous = {
            key: os.environ.get(key) for key in self.environment_overrides()
        }
        os.environ.update(self.environment_overrides())
        self._capture_active = True
        completed = False
        try:
            yield
            completed = True
        finally:
            try:
                if completed:
                    self._finish_capture(capture)
            finally:
                self._capture_active = False
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def _trace_paths(self) -> set[Path]:
        if not self.trace_root.is_dir():
            return set()
        return {
            path.resolve()
            for path in self.trace_root.rglob("*.json")
            if path.is_file()
        }

    def _finish_capture(self, capture: _TurnCapture) -> None:
        new_paths = sorted(
            self._trace_paths() - set(capture.known_paths),
            key=lambda path: path.as_posix(),
        )
        if not new_paths:
            raise RuntimeError(
                f"Turn {capture.turn_number} completed without a retrieval trace"
            )
        references = [
            _trace_reference(
                trace_path=path,
                run_root=self.run_root,
                corpus_identity=self.corpus_identity,
            )
            for path in new_paths
        ]
        trace_ids = [str(reference["trace_id"]) for reference in references]
        if len(trace_ids) != len(set(trace_ids)):
            raise ValueError("A smoke turn emitted duplicate retrieval trace IDs")
        self._turns[capture.turn_number] = references

    def attach_to_summary(
        self,
        summary: Mapping[str, object],
        *,
        expected_turn_numbers: Sequence[int],
        require_retrieval_traces: bool = True,
    ) -> dict[str, object]:
        """Return a summary containing a complete, validated artifact contract."""
        expected = _normalized_turn_numbers(
            expected_turn_numbers,
            allow_empty=not require_retrieval_traces,
        )
        if not require_retrieval_traces and expected:
            raise ValueError(
                "A trace-not-applicable smoke summary cannot name traced turns"
            )
        turns = self._merged_turns(summary)
        if set(turns) != set(expected):
            missing = sorted(set(expected) - set(turns))
            unexpected = sorted(set(turns) - set(expected))
            raise ValueError(
                "Smoke artifact turns do not match the expected turns "
                f"(missing={missing}, unexpected={unexpected})"
            )

        artifact_turns = [
            {
                "turn_number": turn_number,
                "retrieval_traces": turns[turn_number],
            }
            for turn_number in expected
        ]
        trace_count = sum(
            len(turn["retrieval_traces"]) for turn in artifact_turns
        )
        result = dict(summary)
        existing_identity = result.get("run_identity")
        if existing_identity is not None and existing_identity != self.run_identity:
            raise ValueError(
                "Existing smoke summary uses a different git worktree identity"
            )
        existing_commit = result.get("git_commit")
        if (
            existing_commit is not None
            and existing_commit != self.run_identity["git_commit"]
        ):
            raise ValueError(
                "Smoke summary git_commit does not match its worktree identity"
            )
        result["run_identity"] = dict(self.run_identity)
        result["artifacts"] = {
            "schema": SMOKE_ARTIFACT_SCHEMA,
            "corpus": dict(self.corpus_identity),
            "retrieval_trace_requirement": (
                "required" if require_retrieval_traces else "not_applicable"
            ),
            "trace_count": trace_count,
            "turns": artifact_turns,
        }
        validate_smoke_summary_artifacts(
            result,
            run_root=self.run_root,
            expected_turn_numbers=expected,
        )
        return result

    def _merged_turns(
        self,
        summary: Mapping[str, object],
    ) -> dict[int, list[dict[str, object]]]:
        merged: dict[int, list[dict[str, object]]] = {}
        if "artifacts" in summary:
            validate_smoke_summary_artifacts(summary, run_root=self.run_root)
            artifacts = summary["artifacts"]
            assert isinstance(artifacts, Mapping)
            if artifacts.get("corpus") != self.corpus_identity:
                raise ValueError(
                    "Existing smoke summary uses a different corpus identity"
                )
            raw_turns = artifacts["turns"]
            assert isinstance(raw_turns, list)
            for turn in raw_turns:
                assert isinstance(turn, Mapping)
                turn_number = turn["turn_number"]
                traces = turn["retrieval_traces"]
                assert isinstance(turn_number, int)
                assert isinstance(traces, list)
                merged[turn_number] = [dict(trace) for trace in traces]

        for turn_number, traces in self._turns.items():
            existing = merged.get(turn_number)
            if existing is not None and existing != traces:
                raise ValueError(
                    f"Turn {turn_number} has conflicting retrieval trace artifacts"
                )
            merged[turn_number] = [dict(trace) for trace in traces]
        return merged

    def write_summary(
        self,
        path: Path,
        summary: Mapping[str, object],
        *,
        expected_turn_numbers: Sequence[int],
        require_retrieval_traces: bool = True,
    ) -> dict[str, object]:
        """Attach the contract, atomically persist it, and verify it from disk."""
        completed = self.attach_to_summary(
            summary,
            expected_turn_numbers=expected_turn_numbers,
            require_retrieval_traces=require_retrieval_traces,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(
                completed,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        reloaded = json.loads(path.read_text(encoding="utf-8"))
        validate_smoke_summary_artifacts(
            reloaded,
            run_root=self.run_root,
            expected_turn_numbers=expected_turn_numbers,
        )
        return completed


def _normalized_turn_numbers(
    values: Sequence[int],
    *,
    allow_empty: bool = False,
) -> tuple[int, ...]:
    result = tuple(values)
    if not result and not allow_empty:
        raise ValueError("At least one expected turn number is required")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0
        for value in result
    ):
        raise ValueError("Expected turn numbers must be positive integers")
    if len(result) != len(set(result)):
        raise ValueError("Expected turn numbers must be unique")
    return result


def validate_smoke_summary_artifacts(
    summary: Mapping[str, object],
    *,
    run_root: Path,
    expected_turn_numbers: Sequence[int] | None = None,
) -> None:
    """Validate corpus identity and every trace referenced by a smoke summary."""
    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("Smoke summary is missing its artifacts object")
    if artifacts.get("schema") != SMOKE_ARTIFACT_SCHEMA:
        raise ValueError("Smoke summary artifact schema is missing or unsupported")
    runner_sha256 = summary.get("runner_sha256")
    if (
        not isinstance(runner_sha256, str)
        or not _SHA256_PATTERN.fullmatch(runner_sha256)
    ):
        raise ValueError("Smoke summary is missing a valid runner_sha256")
    run_identity = summary.get("run_identity")
    _validate_git_worktree_identity(run_identity)
    corpus = artifacts.get("corpus")
    if not isinstance(corpus, Mapping):
        raise ValueError("Smoke summary is missing corpus identity")
    for field in ("corpus_manifest_sha256", "chunks_sha256"):
        value = corpus.get(field)
        if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
            raise ValueError(f"Smoke summary corpus {field} is invalid")
    manifest_schema = corpus.get("manifest_schema")
    if not isinstance(manifest_schema, str) or not manifest_schema:
        raise ValueError("Smoke summary corpus manifest_schema is invalid")
    manifest_chunk_count = corpus.get("manifest_chunk_count")
    embedded_chunk_count = corpus.get("embedded_chunk_count")
    if (
        not isinstance(manifest_chunk_count, int)
        or isinstance(manifest_chunk_count, bool)
        or manifest_chunk_count < 0
    ):
        raise ValueError("Smoke summary corpus manifest_chunk_count is invalid")
    if (
        not isinstance(embedded_chunk_count, int)
        or isinstance(embedded_chunk_count, bool)
        or embedded_chunk_count < 0
        or embedded_chunk_count > manifest_chunk_count
    ):
        raise ValueError("Smoke summary corpus embedded_chunk_count is invalid")
    for field in ("collection_name", "hnsw_space", "embedding_model"):
        value = corpus.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Smoke summary corpus {field} is invalid")

    raw_turns = artifacts.get("turns")
    trace_requirement = artifacts.get("retrieval_trace_requirement")
    if trace_requirement not in {"required", "not_applicable"}:
        raise ValueError("Smoke summary has an invalid retrieval trace requirement")
    if not isinstance(raw_turns, list):
        raise ValueError("Smoke summary artifact turns must be a list")
    if trace_requirement == "required" and not raw_turns:
        raise ValueError("Smoke summary must reference at least one traced turn")
    if trace_requirement == "not_applicable" and raw_turns:
        raise ValueError(
            "A trace-not-applicable smoke summary cannot reference traced turns"
        )
    seen_turns: set[int] = set()
    seen_trace_ids: set[str] = set()
    trace_count = 0
    resolved_root = run_root.resolve()
    for raw_turn in raw_turns:
        if not isinstance(raw_turn, Mapping):
            raise ValueError("Smoke summary artifact turns must be objects")
        turn_number = raw_turn.get("turn_number")
        if (
            not isinstance(turn_number, int)
            or isinstance(turn_number, bool)
            or turn_number <= 0
            or turn_number in seen_turns
        ):
            raise ValueError("Smoke summary has an invalid or duplicate turn number")
        seen_turns.add(turn_number)
        traces = raw_turn.get("retrieval_traces")
        if not isinstance(traces, list) or not traces:
            raise ValueError(
                f"Smoke summary turn {turn_number} has no retrieval traces"
            )
        for reference in traces:
            if not isinstance(reference, Mapping):
                raise ValueError("Smoke retrieval trace references must be objects")
            relative_name = reference.get("path")
            if not isinstance(relative_name, str) or not relative_name:
                raise ValueError("Smoke retrieval trace reference is missing its path")
            candidate = (resolved_root / relative_name).resolve()
            try:
                candidate.relative_to(resolved_root)
            except ValueError as exc:
                raise ValueError(
                    "Smoke retrieval trace path escapes the run directory"
                ) from exc
            if not candidate.is_file():
                raise ValueError(
                    f"Smoke retrieval trace artifact is missing: {relative_name}"
                )
            expected_sha256 = reference.get("sha256")
            if sha256_file(candidate) != expected_sha256:
                raise ValueError(
                    f"Smoke retrieval trace SHA-256 changed: {relative_name}"
                )
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Smoke retrieval trace is not valid JSON: {relative_name}"
                ) from exc
            validated = _validate_trace_payload(payload, corpus)
            trace_id = validated["trace_id"]
            if trace_id != reference.get("trace_id"):
                raise ValueError(
                    f"Smoke retrieval trace ID changed: {relative_name}"
                )
            if trace_id in seen_trace_ids:
                raise ValueError("Smoke summary references a trace more than once")
            seen_trace_ids.add(str(trace_id))
            query = validated["query"]
            assert isinstance(query, Mapping)
            if query["sha256"] != reference.get("query_sha256"):
                raise ValueError(
                    f"Smoke retrieval query SHA-256 changed: {relative_name}"
                )
            trace_count += 1

    if artifacts.get("trace_count") != trace_count:
        raise ValueError("Smoke summary trace_count does not match its references")
    if trace_requirement == "not_applicable" and trace_count != 0:
        raise ValueError("A trace-not-applicable smoke summary must have zero traces")
    if expected_turn_numbers is not None:
        expected = set(
            _normalized_turn_numbers(
                expected_turn_numbers,
                allow_empty=trace_requirement == "not_applicable",
            )
        )
        if seen_turns != expected:
            raise ValueError(
                "Smoke summary traced turns do not match the expected turns"
            )


def _validate_git_worktree_identity(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("Smoke summary is missing its git worktree identity")
    commit = value.get("git_commit")
    if not isinstance(commit, str) or not _GIT_COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("Smoke summary run identity has an invalid git_commit")
    working_tree = value.get("working_tree")
    fingerprint = value.get("dirty_fingerprint")
    if working_tree == "clean":
        if fingerprint is not None:
            raise ValueError("A clean smoke run cannot have a dirty fingerprint")
    elif working_tree == "dirty":
        if (
            not isinstance(fingerprint, str)
            or not _SHA256_PATTERN.fullmatch(fingerprint)
        ):
            raise ValueError("A dirty smoke run requires a valid dirty fingerprint")
    else:
        raise ValueError("Smoke summary run identity has invalid working_tree state")
    lock_sha256 = value.get("dependency_lock_sha256")
    if lock_sha256 is not None and (
        not isinstance(lock_sha256, str)
        or not _SHA256_PATTERN.fullmatch(lock_sha256)
    ):
        raise ValueError("Smoke summary run identity has an invalid lockfile hash")
