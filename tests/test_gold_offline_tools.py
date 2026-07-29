from __future__ import annotations

from collections import Counter
from io import StringIO
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from gold_set import GoldSetValidationError, validate_gold_set_file


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = REPOSITORY_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


privacy_audit = _load_script("audit_gold_privacy")
carryover = _load_script("check_gold_carryover")
workbook = _load_script("create_gold_authoring_workbook")
workbench = _load_script("gold_authoring_workbench")

PrivacyAuditError = privacy_audit.PrivacyAuditError
audit_gold_privacy = privacy_audit.audit_gold_privacy
CarryoverError = carryover.CarryoverError
check_carryover = carryover.check_carryover
DEFAULT_OUTPUT = workbook.DEFAULT_OUTPUT
WorkbookCreationError = workbook.WorkbookCreationError
create_workbook = workbook.create_workbook
WorkbenchError = workbench.WorkbenchError
chunk_rows = workbench.chunk_rows
document_rows = workbench.document_rows
workbench_main = workbench.main
verified_requested_chunks = workbench.verified_requested_chunks


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest(
    chunks: list[dict[str, object]],
    *,
    skip_files: list[str] | None = None,
) -> dict[str, object]:
    documents: list[dict[str, object]] = []
    document_names = list(dict.fromkeys(str(chunk["document"]) for chunk in chunks))
    for document in document_names:
        documents.append(
            {
                "filename": document,
                "sha256": "a" * 64,
                "paragraph_count": 4,
                "chunk_count": sum(chunk["document"] == document for chunk in chunks),
                "chapter_title": document.removesuffix(".md"),
            }
        )
    return {
        "manifest_schema": "archivist.corpus_manifest/1",
        "documents": documents,
        "chunks": chunks,
        "ingest": {
            "paragraphs_per_chunk": 4,
            "paragraph_overlap": 1,
            "ingest_commit": "b" * 40,
            "skip_files": skip_files or [],
        },
        "store": {},
        "chunks_sha256": "c" * 64,
    }


def _chunk(chunk_id: str, document: str, text: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document": document,
        "paragraph_start": 1,
        "paragraph_end": 4,
        "text_sha256": _sha256_text(text),
        "char_count": len(text),
    }


def _payload(chunk_id: str, document: str, text: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document": document,
        "chapter_title": "Synthetic",
        "paragraph_start": 1,
        "paragraph_end": 4,
        "text": text,
    }


def _gold_item(
    item_id: str,
    *,
    relevant: list[str],
    supporting: list[str],
    claim_text: str = "An owner-written synthetic claim.",
) -> dict[str, object]:
    return {
        "id": item_id,
        "question": f"Synthetic owner question {item_id}?",
        "stratum": "focused_analytical",
        "expected_behavior": "answer",
        "claims": [
            {
                "claim_id": f"{item_id}.1",
                "text": claim_text,
                "essential": True,
                "supporting_chunk_ids": supporting,
            }
        ],
        "relevant_chunk_ids": relevant,
        "must_not_claim": [],
        "notes": "",
    }


def test_final_gold_template_is_empty_stable_and_bound_to_current_manifest() -> None:
    template_path = REPOSITORY_ROOT / "fixtures" / "gold_set.template.json"
    manifest_path = REPOSITORY_ROOT / "fixtures" / "corpus_manifest.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))

    assert template == {
        "schema": "archivist.gold/1",
        "version": "1.0.0",
        "authored_against_corpus": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "items": [],
    }
    with pytest.raises(GoldSetValidationError):
        validate_gold_set_file(template_path, manifest_path, mode="run-of-record")


def test_workbook_has_balanced_blank_slots_and_refuses_overwrite(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest([_chunk("chapter_001", "chapter.md", "synthetic")])),
        encoding="utf-8",
    )
    output_path = tmp_path / "runtime" / "gold-authoring" / "gold_set.draft.json"

    created = create_workbook(manifest_path=manifest_path, output_path=output_path)
    workbook = json.loads(created.read_text(encoding="utf-8"))

    assert created == output_path
    assert len(workbook["items"]) == 40
    assert Counter(item["stratum"] for item in workbook["items"]) == {
        "focused_biographical": 8,
        "focused_analytical": 8,
        "conceptual": 6,
        "broad_thematic": 10,
        "out_of_corpus": 5,
        "adversarial_premise": 3,
    }
    assert [item["id"] for item in workbook["items"]] == [
        f"H{number:03d}" for number in range(1, 41)
    ]
    assert all(
        item["question"] == ""
        and item["expected_behavior"] == ""
        and item["claims"] == []
        and item["relevant_chunk_ids"] == []
        for item in workbook["items"]
    )
    assert workbook["authored_against_corpus"] == hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    assert "runtime" in DEFAULT_OUTPUT.parts

    with pytest.raises(WorkbookCreationError, match="refusing to overwrite"):
        create_workbook(manifest_path=manifest_path, output_path=output_path)

    output_path.write_text("replace me", encoding="utf-8")
    create_workbook(manifest_path=manifest_path, output_path=output_path, force=True)
    assert json.loads(output_path.read_text(encoding="utf-8"))["items"][0]["id"] == "H001"


def test_workbench_lists_metadata_without_text_and_shows_only_requested_chunk(
    tmp_path: Path,
) -> None:
    first_text = "synthetic private first chunk"
    second_text = "synthetic private second chunk"
    manifest = _manifest(
        [
            _chunk("chapter_001", "chapter.md", first_text),
            _chunk("chapter_002", "chapter.md", second_text),
        ]
    )
    payload = [
        _payload("chapter_001", "chapter.md", first_text),
        _payload("chapter_002", "chapter.md", second_text),
    ]

    assert all("text" not in row for row in document_rows(manifest))
    assert all("text" not in row for row in chunk_rows(manifest))
    shown = verified_requested_chunks(manifest, payload, ["chapter_002"])
    assert [chunk["chunk_id"] for chunk in shown] == ["chapter_002"]
    assert shown[0]["text"] == second_text

    manifest_path = tmp_path / "manifest.json"
    chunks_path = tmp_path / "chunks.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    chunks_path.write_text(json.dumps(payload), encoding="utf-8")
    output = StringIO()
    result = workbench_main(
        [
            "--manifest",
            str(manifest_path),
            "--chunks",
            str(chunks_path),
            "--list-chunks",
        ],
        output=output,
    )
    assert result == 0
    assert first_text not in output.getvalue()
    assert second_text not in output.getvalue()

    output = StringIO()
    result = workbench_main(
        [
            "--manifest",
            str(manifest_path),
            "--chunks",
            str(chunks_path),
            "--show",
            "chapter_002",
        ],
        output=output,
    )
    assert result == 0
    assert second_text in output.getvalue()
    assert first_text not in output.getvalue()


def test_workbench_refuses_to_display_unverified_chunk_text() -> None:
    manifest = _manifest([_chunk("chapter_001", "chapter.md", "expected text")])
    payload = [_payload("chapter_001", "chapter.md", "tampered text")]

    with pytest.raises(WorkbenchError, match="text-hash verification"):
        verified_requested_chunks(manifest, payload, ["chapter_001"])


def test_carryover_quarantines_whole_items_for_each_contract_failure() -> None:
    old_manifest_hash = "1" * 64
    old_manifest = _manifest(
        [
            _chunk("stable_001", "stable.md", "stable synthetic text"),
            _chunk("changed_001", "changed.md", "old synthetic text"),
            _chunk("missing_001", "missing.md", "soon absent synthetic text"),
            _chunk("skipped_001", "later-skipped.md", "later skipped synthetic text"),
        ]
    )
    new_manifest = _manifest(
        [
            _chunk("stable_001", "stable.md", "stable synthetic text"),
            _chunk("changed_001", "changed.md", "new synthetic text"),
            _chunk("skipped_001", "later-skipped.md", "later skipped synthetic text"),
        ],
        skip_files=["later-skipped.md"],
    )
    gold = {
        "schema": "archivist.gold/1",
        "version": "1.0.0",
        "authored_against_corpus": old_manifest_hash,
        "items": [
            _gold_item(
                "H001",
                relevant=["stable_001"],
                supporting=["stable_001"],
            ),
            _gold_item(
                "H002",
                relevant=["stable_001", "changed_001"],
                supporting=["stable_001", "changed_001"],
            ),
            _gold_item(
                "H003",
                relevant=["missing_001"],
                supporting=["missing_001"],
            ),
            _gold_item(
                "H004",
                relevant=["skipped_001"],
                supporting=["skipped_001"],
            ),
        ],
    }

    report = check_carryover(
        gold_set=gold,
        old_manifest=old_manifest,
        new_manifest=new_manifest,
        old_manifest_sha256=old_manifest_hash,
        new_manifest_sha256="2" * 64,
    )

    assert report["verified_item_ids"] == ["H001"]
    assert report["quarantined_item_ids"] == ["H002", "H003", "H004"]
    by_id = {item["item_id"]: item for item in report["items"]}
    assert {location["status"] for location in by_id["H002"]["locations"]} == {
        "unchanged",
        "changed_hash",
    }
    assert by_id["H002"]["status"] == "quarantined"
    assert by_id["H003"]["locations"][0]["status"] == "missing"
    assert by_id["H004"]["locations"][0]["status"] == "newly_skipped"
    assert "text" not in json.dumps(report)


def test_carryover_rejects_gold_bound_to_a_different_manifest() -> None:
    manifest = _manifest([_chunk("chapter_001", "chapter.md", "synthetic")])
    gold = {
        "schema": "archivist.gold/1",
        "version": "1.0.0",
        "authored_against_corpus": "a" * 64,
        "items": [],
    }
    with pytest.raises(CarryoverError, match="does not match"):
        check_carryover(
            gold_set=gold,
            old_manifest=manifest,
            new_manifest=manifest,
            old_manifest_sha256="b" * 64,
            new_manifest_sha256="b" * 64,
        )


def test_privacy_audit_flags_exact_run_without_emitting_matching_words() -> None:
    quoted = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    safe = "completely different owner phrasing with no copied sequence at all"
    manifest = _manifest([_chunk("chapter_001", "chapter.md", f"before {quoted} after")])
    payload = [_payload("chapter_001", "chapter.md", f"before {quoted} after")]
    gold = {
        "schema": "archivist.gold/1",
        "version": "1.0.0",
        "authored_against_corpus": "a" * 64,
        "items": [
            _gold_item(
                "H001",
                relevant=["chapter_001"],
                supporting=["chapter_001"],
                claim_text=quoted,
            ),
            _gold_item(
                "H002",
                relevant=["chapter_001"],
                supporting=["chapter_001"],
                claim_text=safe,
            ),
        ],
    }

    report = audit_gold_privacy(
        gold_set=gold,
        manifest=manifest,
        chunk_payload=payload,
        minimum_run_tokens=10,
    )

    assert report["flag_count"] == 1
    assert report["flags"] == [
        {
            "item_id": "H001",
            "claim_id": "H001.1",
            "chunk_id": "chapter_001",
            "matched_token_count": 11,
        }
    ]
    serialized = json.dumps(report)
    assert "alpha" not in serialized
    assert "lambda" not in serialized
    assert safe not in serialized


def test_privacy_audit_requires_complete_hash_verified_local_corpus() -> None:
    manifest = _manifest([_chunk("chapter_001", "chapter.md", "expected synthetic text")])
    empty_gold = {
        "schema": "archivist.gold/1",
        "version": "1.0.0",
        "authored_against_corpus": "a" * 64,
        "items": [],
    }

    with pytest.raises(PrivacyAuditError, match="missing 1 manifest chunks"):
        audit_gold_privacy(
            gold_set=empty_gold,
            manifest=manifest,
            chunk_payload=[],
        )
    with pytest.raises(PrivacyAuditError, match="text-hash verification"):
        audit_gold_privacy(
            gold_set=empty_gold,
            manifest=manifest,
            chunk_payload=[
                _payload("chapter_001", "chapter.md", "tampered synthetic text")
            ],
        )
