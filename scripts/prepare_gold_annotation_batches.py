"""Prepare private, blinded annotation batches after the question commitment.

This command performs no network activity.  It emits only the selected held-out
question fields in each batch; it does not include existing owner annotations,
candidate answers, retrieval output, traces, or scores.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gold_provenance import gold_question_set_sha256  # noqa: E402
from gold_set import GoldSetValidationError, load_json_object, sha256_file, validate_gold_set  # noqa: E402


DEFAULT_GOLD = BASE_DIR / "runtime" / "gold-authoring" / "gold_set.draft.json"
DEFAULT_COMMITMENT = BASE_DIR / "fixtures" / "gold_questions.commitment.json"
DEFAULT_MANIFEST = BASE_DIR / "fixtures" / "corpus_manifest.json"
DEFAULT_CHUNKS = BASE_DIR / "output" / "chunks.json"
DEFAULT_PROMPT = BASE_DIR / "docs" / "gold_annotation_prompt_claude.md"
DEFAULT_OUTPUT = BASE_DIR / "runtime" / "gold-authoring" / "annotation-ready"

DESCRIPTIONS = {
    "focused_biographical": "A person, their arc, mostly contiguous in the text.",
    "focused_analytical": "A specific institution, event, or mechanism.",
    "conceptual": "An idea traced within a bounded region of the book.",
    "broad_thematic": "A theme spanning many chapters and centuries.",
    "out_of_corpus": (
        "Answerable-sounding, but not covered. Behavior is NOT automatically abstain - "
        "a qualified answer is permitted. Corpus-wide absence conditions belong in Notes, "
        "never as unsupported positive claims."
    ),
    "adversarial_premise": (
        "Contains a false presupposition the corpus contradicts. Behavior is NOT automatically "
        "abstain - premise-correction is scored separately as the best outcome "
        "(EVAL_CONTRACT 7.1)."
    ),
}


class AnnotationBatchError(ValueError):
    """Raised when a blinded packet cannot be prepared safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path, *, label: str) -> dict[str, object]:
    try:
        return load_json_object(path, label=label)
    except GoldSetValidationError as exc:
        raise AnnotationBatchError(str(exc)) from exc


def verify_commitment(gold: dict[str, object], commitment: dict[str, object]) -> None:
    items = gold.get("items")
    if not isinstance(items, list):
        raise AnnotationBatchError("gold set has no items array")
    counts = dict(sorted(Counter(str(item.get("stratum")) for item in items).items()))
    expected = {
        "schema": "archivist.gold_question_commitment/1",
        "question_count": len(items),
        "stratum_counts": counts,
        "question_set_sha256": gold_question_set_sha256(gold),
    }
    if commitment != expected:
        raise AnnotationBatchError(
            "question commitment does not match the private canonical question projection"
        )


def _batch_markdown(items: list[dict[str, object]]) -> str:
    rows = [
        "# Blinded held-out annotation batch",
        "",
        "Only the owner-controlled fields below are supplied. Existing annotations and all ",
        "candidate-system material are deliberately absent.",
        "",
    ]
    for item in items:
        stratum = str(item["stratum"])
        rows.extend(
            [
                f"## {item['id']} · {stratum}",
                "",
                f"> {DESCRIPTIONS[stratum]}",
                "",
                f"**Q:** {item['question']}",
                "",
                f"**Behavior:** {item['expected_behavior']}",
                "",
            ]
        )
    return "\n".join(rows).rstrip() + "\n"


def prepare_batches(
    *,
    gold_path: Path,
    commitment_path: Path,
    manifest_path: Path,
    chunks_path: Path,
    prompt_path: Path,
    output_dir: Path,
    candidate_commit: str,
    rag_policy: str,
    batch_size: int = 5,
    force: bool = False,
) -> dict[str, object]:
    if len(candidate_commit) != 40 or any(ch not in "0123456789abcdef" for ch in candidate_commit):
        raise AnnotationBatchError("candidate commit must be a full lowercase Git commit hash")
    if batch_size < 1:
        raise AnnotationBatchError("batch size must be positive")
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        raise AnnotationBatchError(f"refusing to overwrite nonempty packet directory: {output_dir}")

    gold = _json(gold_path, label="private gold set")
    manifest = _json(manifest_path, label="corpus manifest")
    commitment = _json(commitment_path, label="question commitment")
    manifest_hash = sha256_file(manifest_path)
    try:
        validate_gold_set(
            gold,
            manifest,
            corpus_manifest_sha256=manifest_hash,
            mode="run-of-record",
        )
    except GoldSetValidationError as exc:
        raise AnnotationBatchError(
            f"private gold set is not run-of-record valid ({len(exc.errors)} errors)"
        ) from exc
    verify_commitment(gold, commitment)
    if not chunks_path.is_file():
        raise AnnotationBatchError(f"private corpus payload is missing: {chunks_path}")
    if not prompt_path.is_file():
        raise AnnotationBatchError(f"canonical prompt is missing: {prompt_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    items = gold["items"]
    assert isinstance(items, list)
    batch_records: list[dict[str, object]] = []
    for offset in range(0, len(items), batch_size):
        batch_items = items[offset : offset + batch_size]
        number = offset // batch_size + 1
        batch_path = output_dir / f"batch_{number:02d}_questions.md"
        batch_path.write_text(
            _batch_markdown(batch_items), encoding="utf-8", newline="\n"
        )
        ids = [str(item["id"]) for item in batch_items]
        batch_records.append(
            {
                "batch": number,
                "item_ids": ids,
                "declared_batch": ", ".join(ids),
                "question_file": batch_path.name,
                "question_file_sha256": _sha256(batch_path),
                "raw_response_status": "not_requested",
            }
        )

    packet: dict[str, object] = {
        "schema": "archivist.gold_annotation_packet/1",
        "candidate_commit": candidate_commit,
        "candidate_rag_policy": rag_policy,
        "question_commitment_sha256": str(commitment["question_set_sha256"]),
        "question_count": len(items),
        "corpus_manifest_path": "fixtures/corpus_manifest.json",
        "corpus_manifest_sha256": manifest_hash,
        "private_chunks_path": "output/chunks.json",
        "private_chunks_sha256": _sha256(chunks_path),
        "prompt_template_path": "docs/gold_annotation_prompt_claude.md",
        "prompt_template_sha256": _sha256(prompt_path),
        "candidate_outputs_included": False,
        "retrieval_or_trace_material_included": False,
        "external_annotation_status": "not_started_owner_action_required",
        "batches": batch_records,
    }
    manifest_output = output_dir / "annotation_manifest.json"
    manifest_output.write_text(
        json.dumps(packet, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    ledger = output_dir / "claude_annotation_drafts.md"
    ledger.write_text(
        "# Fresh blinded Claude annotation drafts\n\n"
        "Append each raw response here without editing it. Record the exact displayed model "
        "label and interface for every batch. No external request has yet been made.\n",
        encoding="utf-8",
        newline="\n",
    )
    handoff = output_dir / "ANNOTATION_HANDOFF.md"
    handoff.write_text(
        _handoff_text(packet), encoding="utf-8", newline="\n"
    )
    return packet


def _handoff_text(packet: dict[str, object]) -> str:
    batches = packet["batches"]
    assert isinstance(batches, list)
    rows = [
        "# Owner annotation handoff",
        "",
        "The 37 owner-controlled questions are frozen and hash-committed. This packet was ",
        "prepared offline; **no question has been sent to Archivist or Claude**.",
        "",
        "## Before starting",
        "",
        "- Use a fresh isolated Claude conversation for each batch.",
        "- Turn off web/browsing and do not provide any Archivist answer, retrieval, trace, score, ",
        "  development failure, or candidate output.",
        "- The commercial manuscript in `output/chunks.json` is private. Uploading it is an ",
        "  owner-controlled external disclosure; proceed only under data controls you accept.",
        "- Attach only the current batch file, `output/chunks.json`, ",
        "  `fixtures/corpus_manifest.json`, and `docs/gold_annotation_prompt_claude.md`.",
        "",
        "## Repeat for each batch",
        "",
        "1. Start a fresh Claude chat.",
        "2. Attach the four allowed files listed above, substituting the one batch file.",
        "3. First send: `Work only on <exact IDs listed below>.`",
        "4. Then send the canonical prompt verbatim.",
        "5. Confirm Claude's manifest says candidate outputs seen `NO` and external sources `NO`.",
        "6. Append the entire unedited response to `claude_annotation_drafts.md`.",
        "7. Record the exact displayed model label and Claude surface; never infer a snapshot name.",
        "",
        "## Batch order",
        "",
    ]
    for batch in batches:
        assert isinstance(batch, dict)
        rows.append(
            f"- [ ] Batch {batch['batch']}: `{batch['question_file']}` — "
            f"{batch['declared_batch']}"
        )
    rows.extend(
        [
            "",
            "## Stop conditions",
            "",
            "Stop the affected batch if Claude changes an owner-controlled field, reports web or ",
            "candidate-output use, sees candidate material, cannot verify the supplied corpus, or ",
            "returns manuscript quotations. Do not silently repair the raw response.",
            "",
            "After all eight raw batches are captured, return the ledger for owner adjudication. ",
            "The drafts are aids, not ground truth; no held-out evaluation can run until final ",
            "owner verification, privacy/leakage re-audits, provenance lock, and a clean lock check.",
            "",
        ]
    )
    return "\n".join(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare private five-item blinded annotation packets without network calls."
    )
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--commitment", type=Path, default=DEFAULT_COMMITMENT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--rag-policy", default="evidence-planned-v26")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        packet = prepare_batches(
            gold_path=args.gold,
            commitment_path=args.commitment,
            manifest_path=args.manifest,
            chunks_path=args.chunks,
            prompt_path=args.prompt,
            output_dir=args.output_dir,
            candidate_commit=args.candidate_commit,
            rag_policy=args.rag_policy,
            batch_size=args.batch_size,
            force=args.force,
        )
    except (OSError, AnnotationBatchError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        "Prepared blinded annotation handoff: "
        f"{packet['question_count']} items in {len(packet['batches'])} batches; "
        "no network or candidate-system call made."
    )
    print(f"Private packet: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
