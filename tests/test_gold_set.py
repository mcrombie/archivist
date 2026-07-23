import hashlib
import json
from copy import deepcopy

import pytest

from gold_set import GoldSetValidationError, validate_gold_set, validate_gold_set_file


STRATA = (
    "focused_biographical",
    "focused_analytical",
    "conceptual",
    "broad_thematic",
    "out_of_corpus",
    "adversarial_premise",
)


def _manifest(chunk_ids=("synthetic_001", "synthetic_002")):
    return {
        "manifest_schema": "archivist.corpus_manifest/1",
        "ingest": {"skip_files": ["00_Structural.md"]},
        "chunks": [
            {
                "chunk_id": chunk_id,
                "document": "01_Introduction.md",
            }
            for chunk_id in chunk_ids
        ],
    }


def _answer_item(number, stratum, chunk_id="synthetic_001"):
    item_id = f"G{number:03d}"
    return {
        "id": item_id,
        "question": f"Owner-authored synthetic question {number}?",
        "stratum": stratum,
        "expected_behavior": "answer",
        "claims": [
            {
                "claim_id": f"{item_id}.1",
                "text": f"Owner-authored synthetic claim {number}.",
                "essential": True,
                "supporting_chunk_ids": [chunk_id],
            }
        ],
        "relevant_chunk_ids": [chunk_id],
        "must_not_claim": [],
        "notes": "",
    }


def _abstain_item(number, stratum="out_of_corpus"):
    item = _answer_item(number, stratum)
    item["expected_behavior"] = "abstain"
    item["claims"] = []
    item["relevant_chunk_ids"] = []
    return item


def _pilot(digest="a" * 64):
    strata = (
        "focused_biographical",
        "focused_analytical",
        "conceptual",
        "broad_thematic",
        "out_of_corpus",
        "adversarial_premise",
        "broad_thematic",
        "focused_biographical",
        "focused_analytical",
        "conceptual",
    )
    items = [
        _abstain_item(index, stratum)
        if stratum == "out_of_corpus"
        else _answer_item(index, stratum)
        for index, stratum in enumerate(strata, start=1)
    ]
    return {
        "schema": "archivist.gold/1",
        "version": "0.1.0-pilot",
        "authored_against_corpus": digest,
        "items": items,
    }


def _full_set(digest="a" * 64):
    minimum_counts = {
        "focused_biographical": 7,
        "focused_analytical": 7,
        "conceptual": 5,
        "broad_thematic": 9,
        "out_of_corpus": 4,
        "adversarial_premise": 2,
    }
    items = []
    number = 1
    for stratum, count in minimum_counts.items():
        for _ in range(count):
            if stratum == "out_of_corpus":
                items.append(_abstain_item(number))
            else:
                items.append(_answer_item(number, stratum))
            number += 1
    return {
        "schema": "archivist.gold/1",
        "version": "1.0.0",
        "authored_against_corpus": digest,
        "items": items,
    }


def _error_text(gold_set, *, mode="pilot", manifest=None, digest="a" * 64):
    with pytest.raises(GoldSetValidationError) as caught:
        validate_gold_set(
            gold_set,
            manifest or _manifest(),
            corpus_manifest_sha256=digest,
            mode=mode,
        )
    return "\n".join(caught.value.errors)


def test_valid_pilot_is_explicitly_not_run_of_record():
    summary = validate_gold_set(
        _pilot(),
        _manifest(),
        corpus_manifest_sha256="a" * 64,
        mode="pilot",
    )

    assert summary.item_count == 10
    assert sum(count > 0 for count in summary.stratum_counts.values()) == 6
    assert summary.eligible_for_run_of_record is False


def test_valid_full_set_enforces_locked_minimum_composition():
    summary = validate_gold_set(
        _full_set(),
        _manifest(),
        corpus_manifest_sha256="a" * 64,
        mode="run-of-record",
    )

    assert summary.item_count == 34
    assert summary.eligible_for_run_of_record is True
    assert summary.stratum_counts["broad_thematic"] == 9


def test_pilot_cannot_pass_run_of_record_mode():
    errors = _error_text(_pilot(), mode="run-of-record")

    assert "requires a stable version" in errors
    assert "requires 7\u20139 items" in errors
    assert "requires 9\u201311 items" in errors


def test_location_and_behavior_invariants_are_checked_together():
    gold_set = _pilot()
    item = gold_set["items"][0]
    item["claims"][0]["claim_id"] = "OTHER.1"
    item["claims"][0]["supporting_chunk_ids"] = ["missing_001"]
    item["relevant_chunk_ids"] = ["synthetic_001"]
    abstain = gold_set["items"][4]
    abstain["claims"] = [
        {
            "claim_id": f"{abstain['id']}.1",
            "text": "A claim that makes this abstention item invalid.",
            "essential": True,
            "supporting_chunk_ids": ["synthetic_002"],
        }
    ]
    abstain["relevant_chunk_ids"] = ["synthetic_002"]

    errors = _error_text(gold_set)

    assert "must be prefixed by 'G001' plus '.'" in errors
    assert "chunk ID 'missing_001' is absent" in errors
    assert "missing ['missing_001']" in errors
    assert "must be empty when expected_behavior is 'abstain'" in errors


def test_answer_requires_essential_claim_and_supporting_locations():
    gold_set = _pilot()
    item = gold_set["items"][0]
    item["claims"][0]["essential"] = False
    item["claims"][0]["supporting_chunk_ids"] = []
    item["relevant_chunk_ids"] = []

    errors = _error_text(gold_set)

    assert "must contain at least one chunk ID" in errors
    assert "must have at least one essential claim" in errors


def test_ids_questions_and_list_members_must_be_unique():
    gold_set = _pilot()
    second = gold_set["items"][1]
    second["id"] = gold_set["items"][0]["id"]
    second["question"] = f"  {gold_set['items'][0]['question'].upper()}  "
    second["claims"][0]["claim_id"] = gold_set["items"][0]["claims"][0]["claim_id"]
    second["claims"][0]["supporting_chunk_ids"] = ["synthetic_001", "synthetic_001"]
    second["relevant_chunk_ids"] = ["synthetic_001", "synthetic_001"]
    second["must_not_claim"] = ["Synthetic falsehood.", "Synthetic falsehood."]

    errors = _error_text(gold_set)

    assert "duplicate item ID" in errors
    assert "duplicates the normalized question" in errors
    assert "duplicate claim ID" in errors
    assert errors.count("duplicate value") == 3


def test_manifest_hash_schema_and_chunk_identity_are_bound():
    gold_set = _pilot()
    gold_set["authored_against_corpus"] = "b" * 64
    manifest = _manifest(("synthetic_001", "synthetic_001"))
    manifest["manifest_schema"] = "archivist.corpus_manifest/2"

    errors = _error_text(gold_set, manifest=manifest)

    assert "does not match the exact corpus manifest" in errors
    assert "must be exactly 'archivist.corpus_manifest/1'" in errors
    assert "duplicate corpus chunk ID" in errors


def test_gold_locations_must_be_retrieval_eligible():
    gold_set = _pilot()
    gold_set["items"][0]["claims"][0]["supporting_chunk_ids"] = ["structural_001"]
    gold_set["items"][0]["relevant_chunk_ids"] = ["structural_001"]
    manifest = _manifest()
    manifest["chunks"].append(
        {
            "chunk_id": "structural_001",
            "document": "00_Structural.md",
        }
    )

    errors = _error_text(gold_set, manifest=manifest)

    assert errors.count("is not retrieval-eligible") == 2


def test_invalid_strata_and_pilot_composition_are_rejected():
    gold_set = _pilot()
    for item in gold_set["items"]:
        item["stratum"] = "not_a_stratum"
    gold_set["items"].pop()

    errors = _error_text(gold_set)

    assert "must be one of" in errors
    assert "pilot must contain exactly 10 items; found 9" in errors
    assert "pilot must span at least 4 valid strata; found 0" in errors


def test_unhashable_json_values_are_reported_instead_of_crashing():
    gold_set = _pilot()
    gold_set["items"][0]["stratum"] = []
    gold_set["items"][0]["expected_behavior"] = {}

    errors = _error_text(gold_set)

    assert ".stratum: must be one of" in errors
    assert ".expected_behavior: must be 'answer' or 'abstain'" in errors


def test_current_empty_template_is_safe_and_deliberately_invalid():
    template_path = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "fixtures"
        / "gold_set.pilot.template.json"
    )
    manifest_path = template_path.with_name("corpus_manifest.json")
    template = json.loads(template_path.read_text(encoding="utf-8"))

    assert template == {
        "schema": "archivist.gold/1",
        "version": "0.1.0-pilot",
        "authored_against_corpus": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "items": [],
    }
    with pytest.raises(GoldSetValidationError, match="pilot must contain exactly 10 items"):
        validate_gold_set_file(template_path, manifest_path, mode="pilot")


def test_unexpected_fields_are_rejected_by_locked_schema():
    gold_set = deepcopy(_pilot())
    gold_set["items"][0]["paragraph_number"] = 12

    errors = _error_text(gold_set)

    assert "unexpected fields ['paragraph_number']" in errors
