from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gold_provenance import (  # noqa: E402
    GoldProvenanceValidationError,
    validate_gold_provenance_file,
)
from gold_set import GoldSetValidationError, validate_gold_set_file  # noqa: E402


DEFAULT_POLICY = "evidence-planned-v26"
_FULL_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

# These are the only files allowed to differ from the frozen system candidate
# when the owner locks the final gold artifact.  None is on the answer,
# planning, retrieval, prompt, model, or runtime-serving path.
ALLOWED_POST_FREEZE_PATHS = frozenset(
    {
        ".gitattributes",
        "AGENTS.md",
        "BLOGNOTES.md",
        "DEFECTS.md",
        "EVAL_CONTRACT.md",
        "README.MD",
        "ROADMAP.md",
        "docs/gold_set_authoring.md",
        "docs/gold_annotation_prompt_claude.md",
        "docs/gold_set_pilot_intake.md",
        "fixtures/development_question_registry.json",
        "fixtures/gold_set.json",
        "fixtures/gold_set.provenance.json",
        "fixtures/gold_set.provenance.template.json",
        "fixtures/gold_set.template.json",
        "fixtures/gold_questions.commitment.json",
        "scripts/audit_gold_privacy.py",
        "scripts/audit_gold_leakage.py",
        "scripts/check_gold_carryover.py",
        "scripts/create_gold_authoring_workbook.py",
        "scripts/fingerprint_gold_questions.py",
        "scripts/gold_authoring_workbench.py",
        "scripts/import_gold_review_docx.py",
        "scripts/prepare_gold_annotation_batches.py",
        "scripts/run_retrieval_benchmark.py",
        "scripts/validate_gold_holdout.py",
        "src/gold_provenance.py",
        "src/retrieval_benchmark.py",
        "tests/test_gold_holdout_cli.py",
        "tests/test_gold_annotation_preparation.py",
        "tests/test_gold_offline_tools.py",
        "tests/test_gold_provenance.py",
        "tests/test_gold_set.py",
        "tests/test_retrieval_benchmark.py",
    }
)


class CandidateLockError(ValueError):
    """Raised when the repository no longer represents a frozen candidate."""


def _run_git(
    repo_root: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def validate_candidate_lock(
    repo_root: Path,
    candidate_commit: str,
    *,
    allowed_paths: frozenset[str] = ALLOWED_POST_FREEZE_PATHS,
) -> tuple[str, ...]:
    """Prove that only evaluation artifacts changed after a clean candidate."""

    if _FULL_COMMIT_RE.fullmatch(candidate_commit) is None:
        raise CandidateLockError(
            "candidate commit must be a full lowercase 40-character Git commit"
        )

    try:
        _run_git(repo_root, "cat-file", "-e", f"{candidate_commit}^{{commit}}")
    except subprocess.CalledProcessError as exc:
        raise CandidateLockError(
            f"candidate commit {candidate_commit!r} does not exist in this repository"
        ) from exc

    ancestor = _run_git(
        repo_root,
        "merge-base",
        "--is-ancestor",
        candidate_commit,
        "HEAD",
        check=False,
    )
    if ancestor.returncode != 0:
        raise CandidateLockError(
            f"candidate commit {candidate_commit!r} is not an ancestor of HEAD"
        )

    status = _run_git(
        repo_root,
        "status",
        "--porcelain",
        "--untracked-files=all",
    ).stdout.strip()
    if status:
        raise CandidateLockError(
            "working tree must be clean before the held-out gold set is locked"
        )

    changed = tuple(
        line.strip().replace("\\", "/")
        for line in _run_git(
            repo_root,
            "diff",
            "--name-only",
            "--diff-filter=ACDMRTUXB",
            f"{candidate_commit}..HEAD",
        ).stdout.splitlines()
        if line.strip()
    )
    forbidden = tuple(path for path in changed if path not in allowed_paths)
    if forbidden:
        raise CandidateLockError(
            "system-under-test or unapproved files changed after the candidate "
            f"freeze: {list(forbidden)!r}"
        )
    return changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a final owner-designed, owner-adjudicated held-out gold set, its exact "
            "provenance bindings, and optionally the frozen-candidate Git boundary."
        )
    )
    parser.add_argument(
        "gold_set",
        nargs="?",
        type=Path,
        default=BASE_DIR / "fixtures" / "gold_set.json",
    )
    parser.add_argument(
        "--provenance",
        type=Path,
        default=BASE_DIR / "fixtures" / "gold_set.provenance.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=BASE_DIR / "fixtures" / "corpus_manifest.json",
    )
    parser.add_argument(
        "--development-registry",
        type=Path,
        default=BASE_DIR / "fixtures" / "development_question_registry.json",
    )
    parser.add_argument(
        "--question-commitment",
        type=Path,
        default=BASE_DIR / "fixtures" / "gold_questions.commitment.json",
        help="Frozen text-free commitment to ordered owner-controlled question fields.",
    )
    parser.add_argument(
        "--candidate-commit",
        required=True,
        help="Full frozen candidate commit recorded in the provenance sidecar.",
    )
    parser.add_argument(
        "--rag-policy",
        default=DEFAULT_POLICY,
        help="Frozen RAG policy recorded in the provenance sidecar.",
    )
    parser.add_argument(
        "--expected-gold-path",
        default="fixtures/gold_set.json",
        help="Normalized repository-relative gold path recorded in provenance.",
    )
    parser.add_argument(
        "--lock",
        action="store_true",
        help=(
            "Also require a clean tree, an existing candidate ancestor, and no "
            "post-freeze system-under-test changes."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        gold_summary = validate_gold_set_file(
            args.gold_set,
            args.manifest,
            mode="run-of-record",
        )
        provenance_summary = validate_gold_provenance_file(
            args.provenance,
            args.gold_set,
            args.manifest,
            args.development_registry,
            args.question_commitment,
            expected_gold_set_path=args.expected_gold_path,
            expected_candidate_commit=args.candidate_commit,
            expected_rag_policy=args.rag_policy,
            repository_root=BASE_DIR,
        )
        changed: tuple[str, ...] = ()
        if args.lock:
            changed = validate_candidate_lock(BASE_DIR, args.candidate_commit)
    except (GoldSetValidationError, GoldProvenanceValidationError, CandidateLockError) as exc:
        errors = getattr(exc, "errors", (str(exc),))
        print(f"INVALID HELD-OUT GOLD ({len(errors)} error(s)):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "VALID HELD-OUT GOLD: "
        f"{gold_summary.item_count} items, version {gold_summary.version}, "
        f"{provenance_summary.near_match_count} reviewed near-match flag(s)."
    )
    print(f"Candidate commit: {provenance_summary.candidate_commit}")
    print(f"RAG policy: {provenance_summary.candidate_rag_policy}")
    print(
        "Annotation assistance: "
        f"{provenance_summary.annotation_provider} / "
        f"{provenance_summary.annotation_model}"
    )
    print(f"Gold-set SHA-256: {provenance_summary.gold_set_sha256}")
    if args.lock:
        print(
            "LOCKED: the working tree is clean and all "
            f"{len(changed)} post-freeze changed file(s) are evaluation-only."
        )
    else:
        print(
            "Provenance is complete, but Git freeze checks were not requested. "
            "Run again with --lock from a clean committed tree before evaluation."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
