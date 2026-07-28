from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from edition_locators import (
    LOCATOR_SCHEMA,
    EditionLocatorError,
    NormalizedPdf,
    eligible_chunks,
    locate_chunk,
    sampled_anchors,
    typeset_page_label,
    validate_text_free_artifact,
)


def prose(prefix: str, count: int = 90) -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


def test_page_labels_cross_from_roman_front_matter_to_arabic_body():
    assert typeset_page_label(11) == "xi"
    assert typeset_page_label(18) == "xviii"
    assert typeset_page_label(19) == "1"
    assert typeset_page_label(51) == "33"


def test_sampled_anchors_include_both_ends_and_are_deterministic():
    text = prose("token")
    first = sampled_anchors(text)
    second = sampled_anchors(text)

    assert first == second
    assert len(first) == 6
    assert first[0].token_start == 0
    assert first[-1].text.endswith("token89")


def test_locator_handles_an_anchor_that_crosses_a_physical_page_boundary():
    tokens = [f"word{index}" for index in range(90)]
    pdf = NormalizedPdf(
        [
            " ".join(tokens[:35]),
            " ".join(tokens[35:70]),
            " ".join(tokens[70:]),
        ]
    )

    locator = locate_chunk(
        " ".join(tokens),
        pdf,
        minimum_physical_page=1,
    )

    assert locator.physical_page_start == 1
    assert locator.physical_page_end == 3
    assert locator.matched_anchor_count == 6


def test_repeated_anchor_is_resolved_by_monotonic_page_floor():
    repeated = prose("repeat")
    unique_tail = prose("later")
    chunk = f"{repeated} {unique_tail}"
    pdf = NormalizedPdf(
        [
            repeated,
            "unrelated page",
            repeated,
            unique_tail,
        ]
    )

    locator = locate_chunk(
        chunk,
        pdf,
        minimum_physical_page=3,
    )

    assert locator.physical_page_start == 3
    assert locator.physical_page_end == 4
    assert locator.repeated_anchor_count >= 1


def test_locator_rejects_insufficient_exact_evidence():
    pdf = NormalizedPdf([prose("other")])

    with pytest.raises(EditionLocatorError, match="no exact anchor cluster"):
        locate_chunk(prose("chunk"), pdf, minimum_physical_page=1)


def test_private_chunks_are_hash_checked_and_filtered_without_exporting_text():
    text = prose("eligible")
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    skipped_text = prose("skipped")
    skipped_hash = hashlib.sha256(skipped_text.encode()).hexdigest()
    chunks = [
        {"chunk_id": "05_Introduction_001", "document": "05_Introduction.md", "text": text},
        {
            "chunk_id": "32_Bibliography_001",
            "document": "32_Bibliography.md",
            "text": skipped_text,
        },
    ]
    manifest = {
        "chunks": [
            {
                "chunk_id": chunks[0]["chunk_id"],
                "document": chunks[0]["document"],
                "text_sha256": text_hash,
            },
            {
                "chunk_id": chunks[1]["chunk_id"],
                "document": chunks[1]["document"],
                "text_sha256": skipped_hash,
            },
        ],
        "ingest": {"skip_files": ["32_Bibliography.md"]},
        "extraction": {"searchable_chunk_count": 1},
    }

    result = eligible_chunks(chunks, manifest)

    assert [item["chunk_id"] for item in result] == ["05_Introduction_001"]


def test_text_free_fixture_shape_rejects_unallowlisted_prose_field():
    artifact = {
        "schema": LOCATOR_SCHEMA,
        "edition": {
            "edition_id": "typeset_pdf_0706",
            "display_name": "Typeset PDF (July 6, 2026)",
            "locator_kind": "page",
            "source_asset_sha256": "a" * 64,
            "corpus_manifest_sha256": "b" * 64,
            "mapping_version": "1.0.0",
            "status": "verified",
            "physical_page_count": 594,
        },
        "locators": [
            {
                "chunk_id": "05_Introduction_001",
                "edition_id": "typeset_pdf_0706",
                "label_start": "xi",
                "label_end": "xii",
                "physical_page_start": 11,
                "physical_page_end": 12,
                "confidence": "high",
                "method": "six_exact_12_token_anchors_dense_boundaries_monotonic_v1",
                "matched_anchor_count": 6,
                "sampled_anchor_count": 6,
                "repeated_anchor_count": 0,
                "text": "private prose must never enter this artifact",
            }
        ],
    }

    with pytest.raises(EditionLocatorError, match="fields are not allowlisted"):
        validate_text_free_artifact(
            artifact,
            expected_chunk_ids=["05_Introduction_001"],
        )


def test_committed_locator_fixture_is_complete_monotonic_and_text_free():
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "edition_locators"
        / "typeset_pdf_0706.json"
    )
    artifact = json.loads(fixture_path.read_text(encoding="utf-8"))
    locators = artifact["locators"]

    assert len(locators) == 481
    validate_text_free_artifact(
        artifact,
        expected_chunk_ids=[item["chunk_id"] for item in locators],
    )
    forbidden_keys = {"text", "excerpt", "quote", "content", "passage"}
    assert not any(forbidden_keys.intersection(item) for item in locators)
