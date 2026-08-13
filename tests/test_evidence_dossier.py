from __future__ import annotations

import json

import pytest

from evidence_dossier import (
    DEFAULT_HARD_EVIDENCE_TOKEN_LIMIT,
    DEFAULT_MAX_DOSSIER_UNITS,
    DEFAULT_MIN_DOSSIER_UNITS,
    DEFAULT_TARGET_EVIDENCE_TOKENS,
    EvidenceDossierError,
    build_retrieval_dossier,
    derive_question_requirements,
    resolve_local_followup_question,
    serialize_retrieval_dossier,
)


def _chunk(
    number: int,
    text: str,
    *,
    source_numbers: list[int] | None = None,
) -> dict[str, object]:
    chunk: dict[str, object] = {
        "chunk_id": f"synthetic_{number:03}",
        "document": "Synthetic.md",
        "chapter_title": f"Synthetic Chapter {number}",
        "paragraph_start": number * 2,
        "paragraph_end": number * 2 + 1,
        "physical_page_start": number + 10,
        "physical_page_end": number + 11,
        "edition": {
            "edition_id": "synthetic-edition",
            "name": "Synthetic Test Edition",
        },
        "text": text,
    }
    if source_numbers is not None:
        chunk["source_numbers"] = source_numbers
    return chunk


def test_builds_rich_units_from_finalized_chunks_without_sentence_windowing() -> None:
    long_text = " ".join(f"token{index}" for index in range(90))
    chunks = [_chunk(index, f"Subject {index}. {long_text}") for index in range(1, 6)]

    dossier = build_retrieval_dossier("What happened to Subject?", chunks)

    assert [unit.chunk_id for unit in dossier.units] == [
        "synthetic_001",
        "synthetic_002",
        "synthetic_003",
        "synthetic_004",
        "synthetic_005",
    ]
    assert dossier.units[0].text == chunks[0]["text"]
    assert len(dossier.units[0].text.split()) > 32
    assert all(unit.text_scope == "full_chunk" for unit in dossier.units)
    assert dossier.diagnostics["provider_calls"] == 0
    assert dossier.diagnostics["publicly_renderable"] is False


def test_uses_four_units_then_stops_after_reaching_target() -> None:
    chunks = [_chunk(index, "Subject " + ("x" * 990)) for index in range(1, 7)]

    dossier = build_retrieval_dossier(
        "What happened to Subject?",
        chunks,
        target_tokens=800,
        hard_token_limit=1_400,
    )

    assert len(dossier.units) == DEFAULT_MIN_DOSSIER_UNITS
    assert dossier.estimated_evidence_tokens >= 800
    assert dossier.estimated_evidence_tokens <= 1_400
    assert dossier.diagnostics["target_reached"] is True


def test_uses_at_most_eight_units_when_small_chunks_do_not_reach_target() -> None:
    chunks = [_chunk(index, f"Subject evidence {index}.") for index in range(1, 11)]

    dossier = build_retrieval_dossier("What happened to Subject?", chunks)

    assert len(dossier.units) == DEFAULT_MAX_DOSSIER_UNITS
    assert dossier.diagnostics["target_reached"] is False


def test_hard_cap_may_take_complete_paragraphs_but_never_word_windows() -> None:
    base = [_chunk(index, "Subject " + (str(index) * 390)) for index in range(1, 4)]
    first_paragraph = "Subject cause " + ("a" * 280)
    second_paragraph = "Subject consequence " + ("b" * 280)
    chunks = [*base, _chunk(4, f"{first_paragraph}\n\n{second_paragraph}")]

    dossier = build_retrieval_dossier(
        "Why did Subject change?",
        chunks,
        target_tokens=400,
        hard_token_limit=400,
    )

    assert len(dossier.units) == 4
    assert dossier.estimated_evidence_tokens <= 400
    assert dossier.units[-1].text_scope == "complete_paragraph_range"
    assert dossier.units[-1].text == first_paragraph
    assert second_paragraph not in dossier.units[-1].text
    assert dossier.units[-1].unit_id.startswith("evidence:")
    assert len(dossier.units[-1].unit_id) == len("evidence:") + 24


def test_hard_cap_reserves_complete_paragraph_room_for_minimum_breadth() -> None:
    large_paragraphs = [
        f"Subject early evidence {index}. " + ("x" * 100)
        for index in range(1, 5)
    ]
    chunks = [
        _chunk(1, "\n\n".join(large_paragraphs)),
        *[_chunk(index, f"Subject later evidence {index}.") for index in range(2, 5)],
    ]

    dossier = build_retrieval_dossier(
        "What happened to Subject?",
        chunks,
        target_tokens=140,
        hard_token_limit=140,
    )

    assert [unit.chunk_id for unit in dossier.units] == [
        "synthetic_001",
        "synthetic_002",
        "synthetic_003",
        "synthetic_004",
    ]
    assert dossier.units[0].text_scope == "complete_paragraph_range"
    assert dossier.units[0].text == "\n\n".join(large_paragraphs[:3])
    assert dossier.estimated_evidence_tokens <= 140
    assert dossier.diagnostics["below_minimum_unit_count"] is False
    assert [unit.source.retrieval_rank for unit in dossier.units] == [1, 2, 3, 4]


def test_question_requirements_make_multipart_aspects_explicit() -> None:
    requirements = derive_question_requirements(
        "Who was the synthetic treasurer, and what did the treasurer change?"
    )
    dossier = build_retrieval_dossier(
        "Who was the synthetic treasurer, and what did the treasurer change?",
        [_chunk(index, "The synthetic treasurer changed the charter.") for index in range(1, 5)],
    )

    assert [(item.requirement_id, item.aspect) for item in requirements] == [
        ("requirement:who:1", "who"),
        ("requirement:what:1", "what"),
    ]
    assert dossier.aspect_tags == ("who", "what", "multipart")
    assert dossier.units[0].aspect_tags == ("who", "what", "multipart")
    assert dossier.units[0].requirement_ids == (
        "requirement:who:1",
        "requirement:what:1",
    )


def test_pronominal_what_clause_inherits_whole_question_subject_as_a_hint() -> None:
    dossier = build_retrieval_dossier(
        "Who was Edwin Sandys, and what did he do?",
        [_chunk(index, "Edwin Sandys served the company.") for index in range(1, 5)],
    )

    assert dossier.units[0].requirement_ids == (
        "requirement:who:1",
        "requirement:what:1",
    )


def test_when_and_why_require_temporal_and_causal_signals_in_unit_tags() -> None:
    question = "When did the harbor change, and why did the harbor change?"
    chunks = [
        _chunk(1, "The harbor changed in 1810."),
        _chunk(2, "The harbor changed because trade declined."),
        _chunk(3, "The harbor changed shape."),
        _chunk(4, "The harbor changed after 1820 because storms damaged it."),
    ]

    dossier = build_retrieval_dossier(question, chunks)

    assert dossier.units[0].aspect_tags == ("when",)
    assert dossier.units[1].aspect_tags == ("why",)
    assert dossier.units[2].aspect_tags == ()
    assert dossier.units[3].aspect_tags == ("when", "why", "multipart")


def test_stable_ids_and_source_metadata_survive_model_serialization() -> None:
    chunks = [
        _chunk(1, "Subject evidence.", source_numbers=[7, 8]),
        *[_chunk(index, "Subject evidence.") for index in range(2, 5)],
    ]

    dossier = build_retrieval_dossier(
        "What happened to Subject?",
        chunks,
        retrieval_query="Resolved Subject query",
    )
    payload = json.loads(serialize_retrieval_dossier(dossier))
    repeated = build_retrieval_dossier(
        "What happened to Subject?",
        chunks,
        retrieval_query="Resolved Subject query",
    )

    assert dossier.dossier_id == repeated.dossier_id
    assert dossier.retrieval_query == "Resolved Subject query"
    assert dossier.units[0].unit_id.startswith("evidence:")
    assert dossier.units[0].source_numbers == (1,)
    assert dossier.units[0].locator == "Synthetic Chapter 1, paragraphs 2-3"
    assert payload["dossier_id"] == dossier.dossier_id
    assert payload["units"][0]["source"]["chapter_title"] == "Synthetic Chapter 1"
    assert payload["units"][0]["source"]["edition_id"] == "synthetic-edition"
    assert payload["units"][0]["text"] == "Subject evidence."
    assert "source_numbers" not in serialize_retrieval_dossier(dossier)


def test_source_numbers_are_contiguous_after_input_skips() -> None:
    chunks = [
        _chunk(1, "Subject evidence."),
        _chunk(2, ""),
        _chunk(3, "Subject evidence."),
        _chunk(4, "Subject evidence."),
        _chunk(5, "Subject evidence."),
    ]

    dossier = build_retrieval_dossier("What happened to Subject?", chunks)

    assert [unit.source.retrieval_rank for unit in dossier.units] == [1, 3, 4, 5]
    assert [unit.source_numbers for unit in dossier.units] == [(1,), (2,), (3,), (4,)]


def test_dossier_id_changes_when_retrieval_identity_changes() -> None:
    chunks = [_chunk(index, "Subject evidence.") for index in range(1, 5)]
    first = build_retrieval_dossier("What happened?", chunks, retrieval_query="first")
    second = build_retrieval_dossier("What happened?", chunks, retrieval_query="second")
    changed_text = build_retrieval_dossier(
        "What happened?",
        [{**chunks[0], "text": "Changed evidence."}, *chunks[1:]],
        retrieval_query="first",
    )

    assert first.dossier_id != second.dossier_id
    assert first.dossier_id != changed_text.dossier_id


def test_reports_when_retrieval_cannot_supply_four_usable_units() -> None:
    chunks = [
        _chunk(1, "Subject evidence."),
        _chunk(2, ""),
        {**_chunk(1, "Duplicate subject evidence."), "document": "Duplicate.md"},
    ]

    dossier = build_retrieval_dossier("What happened to Subject?", chunks)

    assert len(dossier.units) == 1
    assert dossier.diagnostics["below_minimum_unit_count"] is True
    assert dossier.diagnostics["skipped_blank_chunk_count"] == 1
    assert dossier.diagnostics["skipped_duplicate_chunk_count"] == 1


def test_rejects_missing_ids_and_invalid_budget_configuration() -> None:
    with pytest.raises(EvidenceDossierError, match="stable chunk_id"):
        build_retrieval_dossier("What happened?", [{"text": "Evidence."}])

    with pytest.raises(EvidenceDossierError, match="must not exceed"):
        build_retrieval_dossier(
            "What happened?",
            [_chunk(1, "Evidence.")],
            target_tokens=101,
            hard_token_limit=100,
        )


def test_local_followup_replaces_pronoun_with_prior_question_subject() -> None:
    resolved = resolve_local_followup_question(
        "When did he live?",
        [{"question": "Who was Edwin Sandys, and what did he do?", "answer": "Ignored."}],
    )

    assert resolved == "When did Edwin Sandys live?"


def test_local_followup_scans_past_pronoun_only_turn_for_latest_subject() -> None:
    resolved = resolve_local_followup_question(
        "When did he live?",
        [
            {"question": "Who was Edwin Sandys?", "answer": "Ignored."},
            {"question": "What did he do next?", "answer": "Also ignored."},
        ],
    )

    assert resolved == "When did Edwin Sandys live?"


def test_local_followup_recovers_subject_from_prior_resolved_when_question() -> None:
    resolved = resolve_local_followup_question(
        "What else did he do?",
        [{"question": "When did Edwin Sandys live?", "answer": "Ignored."}],
    )

    assert resolved == "What else did Edwin Sandys do?"


@pytest.mark.parametrize(
    ("question", "expected"),
    (
        ("Tell me more.", "Tell me more about Edwin Sandys."),
        ("What happened next?", "What happened to Edwin Sandys next?"),
    ),
)
def test_local_followup_resolves_high_confidence_generic_continuations(
    question: str,
    expected: str,
) -> None:
    resolved = resolve_local_followup_question(
        question,
        [
            {"question": "Who was Edwin Sandys?", "answer": "Ignored."},
            {"question": "What did he do?", "answer": "Also ignored."},
        ],
    )

    assert resolved == expected


def test_local_followup_leaves_bare_affirmation_unchanged() -> None:
    resolved = resolve_local_followup_question(
        "Yes",
        [{"question": "Who was Edwin Sandys?", "answer": "Ignored."}],
    )

    assert resolved == "Yes"


def test_local_followup_does_not_concatenate_uncertain_history() -> None:
    resolved = resolve_local_followup_question(
        "Why did it happen?",
        [{"question": "Can you put that in a wider context?"}],
    )

    assert resolved == "Why did it happen?"


def test_default_budget_constants_match_rich_dossier_contract() -> None:
    assert DEFAULT_MIN_DOSSIER_UNITS == 4
    assert DEFAULT_MAX_DOSSIER_UNITS == 8
    assert DEFAULT_TARGET_EVIDENCE_TOKENS == 2_500
    assert DEFAULT_HARD_EVIDENCE_TOKEN_LIMIT == 4_500
