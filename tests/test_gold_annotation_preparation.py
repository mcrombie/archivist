from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPOSITORY_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from fingerprint_gold_questions import fingerprint_json
from import_gold_review_docx import W, finalize_document_xml
from prepare_gold_annotation_batches import prepare_batches


def _paragraph(text: str, style: str = "Normal") -> ET.Element:
    paragraph = ET.Element(f"{W}p")
    props = ET.SubElement(paragraph, f"{W}pPr")
    style_element = ET.SubElement(props, f"{W}pStyle")
    style_element.set(f"{W}val", style)
    run = ET.SubElement(paragraph, f"{W}r")
    node = ET.SubElement(run, f"{W}t")
    node.text = text
    return paragraph


def _document_xml(paragraphs: list[ET.Element]) -> bytes:
    root = ET.Element(f"{W}document")
    body = ET.SubElement(root, f"{W}body")
    body.extend(paragraphs)
    ET.SubElement(body, f"{W}sectPr")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def test_finalizer_removes_only_excluded_item_and_updates_status() -> None:
    payload = _document_xml(
        [
            _paragraph("Owner-adjudicated edition  ·  38 held-out questions"),
            _paragraph("H038  ·  Adversarial premise", "QuestionID"),
            _paragraph("retained private synthetic row"),
            _paragraph("H039  ·  Adversarial premise", "QuestionID"),
            _paragraph("excluded private synthetic row"),
        ]
    )

    finalized = finalize_document_xml(payload, excluded_ids={"H039"})
    text = " ".join(
        node.text or "" for node in ET.fromstring(finalized).findall(f".//{W}t")
    )

    assert "37 held-out questions" in text
    assert "H038" in text
    assert "retained private synthetic row" in text
    assert "H039" not in text
    assert "excluded private synthetic row" not in text


def _manifest() -> dict[str, object]:
    text = "synthetic private corpus text"
    return {
        "manifest_schema": "archivist.corpus_manifest/1",
        "documents": [],
        "chunks": [
            {
                "chunk_id": "synthetic_001",
                "document": "synthetic.md",
                "paragraph_start": 1,
                "paragraph_end": 4,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "char_count": len(text),
            }
        ],
        "ingest": {
            "paragraphs_per_chunk": 4,
            "paragraph_overlap": 1,
            "ingest_commit": "a" * 40,
            "skip_files": [],
        },
        "store": {},
        "chunks_sha256": "b" * 64,
    }


def _gold(manifest_hash: str) -> dict[str, object]:
    strata = [
        *("focused_biographical" for _ in range(8)),
        *("focused_analytical" for _ in range(8)),
        *("conceptual" for _ in range(5)),
        *("broad_thematic" for _ in range(10)),
        *("out_of_corpus" for _ in range(4)),
        *("adversarial_premise" for _ in range(2)),
    ]
    retained_numbers = [number for number in range(1, 39) if number != 20]
    items = []
    for number, stratum in zip(retained_numbers, strata, strict=True):
        item_id = f"H{number:03d}"
        items.append(
            {
                "id": item_id,
                "question": f"Synthetic owner question {item_id}?",
                "stratum": stratum,
                "expected_behavior": "answer",
                "claims": [
                    {
                        "claim_id": f"{item_id}.1",
                        "text": "Synthetic owner annotation.",
                        "essential": True,
                        "supporting_chunk_ids": ["synthetic_001"],
                    }
                ],
                "relevant_chunk_ids": ["synthetic_001"],
                "must_not_claim": [],
                "notes": "",
            }
        )
    return {
        "schema": "archivist.gold/1",
        "version": "1.0.0",
        "authored_against_corpus": manifest_hash,
        "items": items,
    }


def test_noncontiguous_ids_can_be_committed_and_batched_without_annotations(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    gold = _gold(manifest_hash)
    commitment = fingerprint_json(gold)
    assert commitment["question_count"] == 37
    assert [item["id"] for item in gold["items"]][19:22] == ["H021", "H022", "H023"]

    gold_path = tmp_path / "gold.json"
    commitment_path = tmp_path / "commitment.json"
    chunks_path = tmp_path / "chunks.json"
    prompt_path = tmp_path / "prompt.md"
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    commitment_path.write_text(json.dumps(commitment), encoding="utf-8")
    chunks_path.write_text("[]", encoding="utf-8")
    prompt_path.write_text("synthetic canonical prompt", encoding="utf-8")

    packet = prepare_batches(
        gold_path=gold_path,
        commitment_path=commitment_path,
        manifest_path=manifest_path,
        chunks_path=chunks_path,
        prompt_path=prompt_path,
        output_dir=tmp_path / "packet",
        candidate_commit="c" * 40,
        rag_policy="evidence-planned-v26",
    )

    assert packet["question_count"] == 37
    assert len(packet["batches"]) == 8
    assert packet["batches"][3]["item_ids"] == ["H016", "H017", "H018", "H019", "H021"]
    batch_text = (tmp_path / "packet" / "batch_01_questions.md").read_text()
    assert "**Claims:**" not in batch_text
    assert "Synthetic owner annotation" not in batch_text
    assert packet["candidate_outputs_included"] is False
    assert packet["retrieval_or_trace_material_included"] is False
