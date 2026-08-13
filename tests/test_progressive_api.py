from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import web_api
from answer_progress import (
    ANSWER_STREAM_SCHEMA,
    AnswerProgressStage,
    CheckedClaimCandidate,
    IncrementalJSONArrayItems,
    MAX_PROGRESSIVE_LEAD_CHARACTERS,
    MAX_PROGRESSIVE_LEAD_WORDS,
    validate_progressive_lead,
    ProviderStreamMilestone,
)
from exposure_profile import ExposureSettings


def _frames(response) -> list[dict[str, object]]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


class _FakeDevelopmentLedger:
    def budget_state(self):
        return {
            "hard_limit_enabled": False,
            "exceeded": False,
        }

    def record_answer_run_diagnostics(self, **_kwargs):
        return None

    def summary(self, **_kwargs):
        return {"currency": "USD", "turn_usd": 0.01}


def test_progressive_heartbeat_interval_supports_visible_activity():
    assert 0 < web_api._STREAM_HEARTBEAT_SECONDS <= 3.0


def test_incremental_array_reader_never_yields_partial_members():
    reader = IncrementalJSONArrayItems("answer_units")
    payload = {
        "answer_units": [
            {"unit_id": "u1", "text": "First complete claim."},
            {"unit_id": "u2", "text": "Second complete claim."},
        ],
        "interpretive_coda": "Withheld until complete.",
    }
    encoded = json.dumps(payload)
    split_points = (
        encoded.index("First complete") + 5,
        encoded.index("Second complete") + 7,
        encoded.index("interpretive_coda") - 3,
    )

    emitted: list[object] = []
    start = 0
    for stop in split_points:
        emitted.extend(reader.feed(encoded[start:stop]))
        start = stop
    emitted.extend(reader.feed(encoded[start:]))

    assert emitted == payload["answer_units"]
    assert reader.done is True


def test_incremental_array_reader_handles_every_character_split_and_escaped_json():
    reader = IncrementalJSONArrayItems("answer_units")
    payload = {
        "metadata": {
            "answer_units": [{"unit_id": "nested-decoy"}],
            "scale": 1.25e-12,
        },
        "note": 'A string containing "answer_units": [{"decoy": true}] and \\.',
        "not_answer_units": [{"unit_id": "wrong-key-decoy"}],
        "answer_units": [
            {
                "unit_id": 'u"1',
                "text": "Escaped \\ path, closing ] and emoji \U0001f4da.",
            },
            {
                "unit_id": "u2",
                "text": "A newline\nplus a literal comma, and brace }.",
            },
        ],
    }
    encoded = json.dumps(payload)

    emitted: list[object] = []
    emission_delimiters: list[str] = []
    for character in encoded:
        values = reader.feed(character)
        if values:
            emitted.extend(values)
            emission_delimiters.append(character)

    assert emitted == payload["answer_units"]
    assert emission_delimiters == [",", "]"]
    assert reader.done is True


def test_incremental_array_reader_handles_every_character_split_json_numbers():
    reader = IncrementalJSONArrayItems("answer_units")
    payload = {
        "metadata_number": 1.25e-12,
        "answer_units": [1.25e-12, -350.5, 0],
    }

    emitted = [item for character in json.dumps(payload) for item in reader.feed(character)]

    assert emitted == payload["answer_units"]
    assert reader.done is True


@pytest.mark.parametrize(
    "truncated",
    [
        '{"answer_units":[{"text":"complete value"}',
        '{"answer_units":[{"text":"escaped \\"quote',
    ],
)
def test_incremental_array_reader_withholds_truncated_members(truncated):
    reader = IncrementalJSONArrayItems("answer_units")

    assert reader.feed(truncated) == ()
    assert reader.done is False


def test_incremental_array_reader_emits_only_delimited_member_before_truncation():
    reader = IncrementalJSONArrayItems("answer_units")

    assert reader.feed('{"answer_units":[{"text":"value"}, {"text":') == ({"text": "value"},)
    assert reader.done is False


def test_incremental_array_reader_waits_for_membership_delimiter():
    reader = IncrementalJSONArrayItems("answer_units")
    item = {"unit_id": "u1", "text": "Decoded but not delimited."}
    encoded_item = json.dumps(item)

    assert reader.feed('{"answer_units":[' + encoded_item) == ()
    assert reader.done is False
    assert reader.feed("]}") == (item,)
    assert reader.done is True


def test_incremental_array_reader_rejects_missing_member_comma_without_emitting():
    reader = IncrementalJSONArrayItems("answer_units")

    assert reader.feed('{"answer_units":[{"unit_id":"u1"}') == ()
    with pytest.raises(ValueError, match="expected ',' between members"):
        reader.feed('{"unit_id":"u2"}]}')


def test_incremental_array_reader_rejects_trailing_comma():
    reader = IncrementalJSONArrayItems("answer_units")
    item = {"unit_id": "u1"}

    assert reader.feed('{"answer_units":[' + json.dumps(item) + ",") == (item,)
    with pytest.raises(ValueError, match="trailing comma"):
        reader.feed("]}")


@pytest.mark.parametrize(
    "malformed",
    [
        '{"answer_units":[,]}',
        '{"answer_units":[{"unit_id":"u1"},,',
    ],
)
def test_incremental_array_reader_rejects_unexpected_array_comma(malformed):
    reader = IncrementalJSONArrayItems("answer_units")

    with pytest.raises(ValueError, match="unexpected comma"):
        reader.feed(malformed)


def test_incremental_array_reader_ignores_nested_string_and_similar_key_matches():
    reader = IncrementalJSONArrayItems("answer_units")
    decoys = {
        "wrapper": {"answer_units": [{"unit_id": "nested"}]},
        "note": 'literal "answer_units": [{"unit_id":"string"}]',
        "not_answer_units": [{"unit_id": "similar"}],
    }

    with pytest.raises(ValueError, match="no top-level 'answer_units' field"):
        reader.feed(json.dumps(decoys))


def test_incremental_array_reader_finds_escaped_top_level_key_after_decoys():
    field_name = 'answer"units'
    reader = IncrementalJSONArrayItems(field_name)
    expected = [{"unit_id": "real"}]
    payload = {
        "wrapper": {field_name: [{"unit_id": "nested"}]},
        field_name: expected,
    }

    emitted = [item for character in json.dumps(payload) for item in reader.feed(character)]

    assert emitted == expected
    assert reader.done is True


def test_incremental_array_reader_rejects_wrong_field_shape():
    reader = IncrementalJSONArrayItems("answer_units")

    with pytest.raises(ValueError, match="claim field is not an array"):
        reader.feed('{"answer_units":{"unit_id":"u1"}}')


def test_incremental_array_reader_rejects_missing_top_level_field_comma():
    reader = IncrementalJSONArrayItems("answer_units")

    with pytest.raises(ValueError, match="expected ',' between object fields"):
        reader.feed('{"metadata": 1 "answer_units": []}')


def test_incremental_array_reader_enforces_inclusive_buffer_bound():
    payload = '{"answer_units":[{"unit_id":"u1"}]}'
    within_bound = IncrementalJSONArrayItems("answer_units", maximum_characters=len(payload))
    over_bound = IncrementalJSONArrayItems("answer_units", maximum_characters=len(payload) - 1)

    assert within_bound.feed(payload) == ({"unit_id": "u1"},)
    assert within_bound.done is True
    with pytest.raises(ValueError, match="incremental buffer limit"):
        over_bound.feed(payload)


def test_incremental_array_reader_validates_buffer_configuration():
    with pytest.raises(ValueError, match="maximum_characters must be positive"):
        IncrementalJSONArrayItems("answer_units", maximum_characters=0)


def test_progressive_lead_accepts_short_cited_answer_naming_question_subject():
    validate_progressive_lead(
        "Project Lumen established a durable institution [Source 1].",
        question_anchors=("Project Lumen",),
    )


@pytest.mark.parametrize(
    "text",
    [
        "x" * (MAX_PROGRESSIVE_LEAD_CHARACTERS + 1) + ".",
        " ".join(["word"] * (MAX_PROGRESSIVE_LEAD_WORDS + 1)) + ".",
        "An unrelated institution established a durable practice [Source 1].",
    ],
)
def test_progressive_lead_rejects_long_or_off_subject_answer(text):
    with pytest.raises(ValueError, match="progressive lead"):
        validate_progressive_lead(text, question_anchors=("Project Lumen",))


def test_development_progressive_endpoint_delivers_checked_claim_during_generation(
    monkeypatch,
):
    answer = "A validated answer with a citation. [Source 1]"
    chunks = [
        {
            "chunk_id": "synthetic-1",
            "document": "Synthetic.md",
            "chapter_title": "Synthetic",
            "paragraph_start": 1,
            "paragraph_end": 2,
            "text": "Development-only source text.",
        }
    ]

    def fake_answer(
        *_args,
        progress_callback=None,
        checked_claim_callback=None,
        stream_milestone_callback=None,
        **kwargs,
    ):
        assert kwargs["rag_policy"] is web_api.V27_COMPACT_CANDIDATE_POLICY
        assert "application_compiled" not in kwargs
        assert progress_callback is not None
        assert checked_claim_callback is not None
        assert stream_milestone_callback is not None
        for stage in (
            AnswerProgressStage.CHECKING_CORPUS,
            AnswerProgressStage.RESOLVING_QUESTION,
            AnswerProgressStage.PLANNING_SEARCH,
            AnswerProgressStage.RETRIEVING_SOURCES,
            AnswerProgressStage.CHECKING_EVIDENCE,
            AnswerProgressStage.PREPARING_CONTEXT,
            AnswerProgressStage.GENERATING_ANSWER,
        ):
            progress_callback(stage)
        stream_milestone_callback(ProviderStreamMilestone.FIRST_DELTA)
        checked_claim_callback(
            CheckedClaimCandidate(
                paragraph=1,
                text=answer,
                source_chunks=tuple(chunks),
                audit_chunks=tuple(chunks),
            )
        )
        stream_milestone_callback(ProviderStreamMilestone.TERMINAL)
        progress_callback(AnswerProgressStage.VALIDATING_ANSWER)
        return SimpleNamespace(
            answer=answer,
            final_chunks=chunks,
            status="answered",
            evidence_decision="direct_answer",
            diagnostics={},
            resolved_question="Resolved synthetic question?",
        )

    monkeypatch.setattr(web_api, "UsageLedger", _FakeDevelopmentLedger)
    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    monkeypatch.setattr(
        web_api,
        "answer_run_diagnostics",
        lambda _result: {"schema": "archivist.answer_run_diagnostics/3"},
    )

    response = TestClient(web_api.app).post(
        "/api/projects/current/question/progressive",
        json={
            "question": "What happened?",
            "rag_policy_version": web_api.COMPACT_RAG_POLICY_VERSION,
        },
    )
    frames = _frames(response)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["cache-control"] == "no-store, no-transform"
    assert response.headers["cdn-cache-control"] == "no-store"
    assert response.headers["surrogate-control"] == "no-store"
    assert response.headers["vary"] == "Accept"
    assert response.headers["x-accel-buffering"] == "no"
    assert all(frame["schema"] == ANSWER_STREAM_SCHEMA for frame in frames)
    assert [frame["sequence"] for frame in frames] == list(range(1, len(frames) + 1))
    assert frames[0]["type"] == "stage"
    assert frames[0]["stage"] == "accepted"
    validation_index = next(
        index for index, frame in enumerate(frames) if frame.get("stage") == "validating_answer"
    )
    claim_indexes = [
        index for index, frame in enumerate(frames) if frame["type"] == "checked_claim"
    ]
    assert len(claim_indexes) == 1
    assert claim_indexes[0] < validation_index
    assert frames[claim_indexes[0]] == {
        "schema": ANSWER_STREAM_SCHEMA,
        "type": "checked_claim",
        "sequence": claim_indexes[0] + 1,
        "claim_index": 1,
        "paragraph": 1,
        "text": answer,
    }
    assert not any(frame["type"] == "answer_delta" for frame in frames)
    assert frames[-1]["type"] == "complete"
    result = frames[-1]["result"]
    assert result["answer"] == answer
    # The terminal development result remains at parity with the complete JSON
    # endpoint; provisional frames expose only already-checked claim prose.
    assert result["resolved_query"] == "Resolved synthetic question?"
    assert result["run_diagnostics"]["schema"] == "archivist.answer_run_diagnostics/3"
    assert result["sources"][0]["text"] == "Development-only source text."
    for frame in frames[:-1]:
        if frame["type"] == "checked_claim":
            continue
        assert not {
            "plan",
            "query",
            "resolved_query",
            "sources",
            "diagnostics",
            "exception",
            "prompt",
        }.intersection(frame)


def test_progressive_timing_log_is_text_free_and_waits_for_both_lifecycles(caplog):
    tick = 0

    def clock_ns():
        nonlocal tick
        tick += 1_000_000
        return tick

    caplog.set_level(logging.INFO, logger="web_api")
    timing = web_api._ProgressiveDeliveryTiming(
        public=True,
        clock_ns=clock_ns,
        wall_clock=lambda: datetime(2026, 8, 5, 12, 30, tzinfo=timezone.utc),
        trace_id="safe-trace-id",
    )
    timing.mark_stage(AnswerProgressStage.CHECKING_CORPUS)
    timing.mark_stage(AnswerProgressStage.GENERATING_ANSWER)
    timing.mark_provider(ProviderStreamMilestone.FIRST_DELTA)
    timing.mark_first_checked_claim()
    timing.mark_provider(ProviderStreamMilestone.TERMINAL)
    timing.mark_terminal("complete")
    timing.worker_finished()

    assert not [
        record
        for record in caplog.records
        if record.getMessage().startswith("progressive_delivery_timing ")
    ]

    timing.stream_finished("complete")
    records = [
        record
        for record in caplog.records
        if record.getMessage().startswith("progressive_delivery_timing ")
    ]
    assert len(records) == 1
    payload = json.loads(records[0].getMessage().split(" ", 1)[1])
    assert payload["schema"] == "archivist.progressive_delivery_timing/1"
    assert payload["trace_id"] == "safe-trace-id"
    assert payload["public"] is True
    assert payload["accepted_at_utc"] == "2026-08-05T12:30:00.000+00:00"
    assert payload["outcome"] == "complete"
    assert set(payload["milestones_ms"]) == {
        "accepted",
        "stage_checking_corpus",
        "stage_generating_answer",
        "first_provider_delta",
        "first_checked_claim",
        "provider_terminal",
        "terminal_complete",
        "worker_finished",
        "stream_finished",
    }
    assert list(payload) == [
        "accepted_at_utc",
        "milestones_ms",
        "outcome",
        "public",
        "schema",
        "total_ms",
        "trace_id",
    ]
    assert "question" not in payload
    assert "answer" not in payload
    assert "sources" not in payload


def _public_settings(**overrides) -> ExposureSettings:
    values = {
        "monthly_budget_usd": "5.00",
        "locator_artifact": (
            web_api.BASE_DIR / "fixtures" / "edition_locators" / "typeset_pdf_0706.json"
        ),
    }
    values.update(overrides)
    return ExposureSettings.public_demo(**values)


def test_public_progressive_endpoint_keeps_safe_terminal_shape(monkeypatch):
    result = {
        "answer": "A public-safe answer. [Source 1]",
        "answer_status": "answered",
        "historiographical_lens": "evidence_first",
        "voice": "scholarly",
        "worldview": "none",
        "source_schema": "archivist.public_sources/1",
        "sources": [
            {
                "kind": "public_locator",
                "source_number": 1,
                "citation_label": "Typeset PDF, p. 1",
            }
        ],
    }

    def fake_public(
        _request,
        _settings,
        *,
        progress_callback=None,
        checked_claim_callback=None,
        stream_milestone_callback=None,
    ):
        assert progress_callback is not None
        assert checked_claim_callback is not None
        assert stream_milestone_callback is not None
        progress_callback(AnswerProgressStage.GENERATING_ANSWER)
        stream_milestone_callback(ProviderStreamMilestone.FIRST_DELTA)
        checked_claim_callback(
            CheckedClaimCandidate(
                paragraph=1,
                text=result["answer"],
                source_chunks=(
                    {
                        "chunk_id": "private-source-id",
                        "text": "private manuscript body",
                    },
                ),
                audit_chunks=(),
            )
        )
        stream_milestone_callback(ProviderStreamMilestone.TERMINAL)
        progress_callback(AnswerProgressStage.VALIDATING_ANSWER)
        progress_callback(AnswerProgressStage.CHECKING_RELEASE)
        return result

    monkeypatch.setattr(
        web_api,
        "_preflight_public_progressive_question",
        lambda _request, _settings: None,
    )
    monkeypatch.setattr(web_api, "_run_public_question", fake_public)
    response = TestClient(web_api.create_app(_public_settings())).post(
        "/api/projects/current/question/progressive",
        json={"question": "What happened?"},
    )
    frames = _frames(response)

    assert response.status_code == 200
    release_index = next(
        index for index, frame in enumerate(frames) if frame.get("stage") == "checking_release"
    )
    first_claim = next(
        index for index, frame in enumerate(frames) if frame["type"] == "checked_claim"
    )
    assert first_claim < release_index
    assert frames[first_claim]["text"] == result["answer"]
    assert frames[first_claim]["claim_index"] == 1
    assert frames[-1] == {
        "schema": ANSWER_STREAM_SCHEMA,
        "type": "complete",
        "sequence": len(frames),
        "result": result,
    }
    assert response.headers["x-content-type-options"] == "nosniff"
    serialized = json.dumps(frames)
    for forbidden in (
        "run_diagnostics",
        "resolved_query",
        "chunk_id",
        "private-source-id",
        "private manuscript body",
        "progressive_delivery_timing",
        "accepted_at_utc",
        "milestones_ms",
    ):
        assert forbidden not in serialized


def test_late_global_failure_retracts_provisional_claims_with_terminal_error(
    monkeypatch,
):
    answer = "A locally checked but globally incomplete claim. [Source 1]"
    chunks = (
        {
            "chunk_id": "synthetic-1",
            "document": "Synthetic.md",
            "chapter_title": "Synthetic",
            "paragraph_start": 1,
            "paragraph_end": 1,
            "text": "Private evidence.",
        },
    )

    def fake_answer(
        *_args,
        progress_callback=None,
        checked_claim_callback=None,
        **_kwargs,
    ):
        assert progress_callback is not None
        assert checked_claim_callback is not None
        progress_callback(AnswerProgressStage.GENERATING_ANSWER)
        checked_claim_callback(
            CheckedClaimCandidate(
                paragraph=1,
                text=answer,
                source_chunks=chunks,
                audit_chunks=chunks,
            )
        )
        progress_callback(AnswerProgressStage.VALIDATING_ANSWER)
        return SimpleNamespace(
            answer=answer,
            final_chunks=list(chunks),
            status="generation_contract_failed",
            evidence_decision="direct_answer",
            diagnostics={},
            resolved_question="Resolved synthetic question?",
        )

    monkeypatch.setattr(web_api, "UsageLedger", _FakeDevelopmentLedger)
    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    monkeypatch.setattr(
        web_api,
        "answer_run_diagnostics",
        lambda _result: {"schema": "archivist.answer_run_diagnostics/3"},
    )

    frames = _frames(
        TestClient(web_api.app).post(
            "/api/projects/current/question/progressive",
            json={"question": "What happened?"},
        )
    )

    assert any(frame["type"] == "checked_claim" for frame in frames)
    assert frames[-1]["type"] == "error"
    assert frames[-1]["error"]["code"] == "question_unavailable"
    assert not any(frame["type"] == "complete" for frame in frames)


def test_public_release_gate_withholds_provisional_claim_that_fails_verbatim_guard(
    monkeypatch,
):
    source = {
        "chunk_id": "private-source-id",
        "document": "Synthetic.md",
        "chapter_title": "Synthetic",
        "paragraph_start": 1,
        "paragraph_end": 1,
        "text": "A private manuscript passage that must not cross the boundary.",
    }

    def fake_answer(
        *_args,
        progress_callback=None,
        checked_claim_callback=None,
        **_kwargs,
    ):
        assert checked_claim_callback is not None
        if progress_callback is not None:
            progress_callback(AnswerProgressStage.GENERATING_ANSWER)
        checked_claim_callback(
            CheckedClaimCandidate(
                paragraph=1,
                text="A provisional checked claim. [Source 1]",
                source_chunks=(source,),
                audit_chunks=(source,),
            )
        )
        return SimpleNamespace(
            answer="A final answer. [Source 1]",
            final_chunks=[source],
            status="answered",
            content_outcome=None,
            answer_strategy="rag",
            answer_strategy_version="test",
            evidence_decision="direct_answer",
            diagnostics={},
        )

    monkeypatch.setattr(
        web_api,
        "_preflight_public_progressive_question",
        lambda _request, _settings: None,
    )
    monkeypatch.setattr(web_api, "UsageLedger", _FakeDevelopmentLedger)
    monkeypatch.setattr(web_api, "_configure_public_budget", lambda *_args: None)
    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    monkeypatch.setattr(
        web_api,
        "answer_has_extended_verbatim_overlap",
        lambda *_args, **_kwargs: True,
    )

    frames = _frames(
        TestClient(web_api.create_app(_public_settings())).post(
            "/api/projects/current/question/progressive",
            json={"question": "What happened?"},
        )
    )

    assert not any(frame["type"] == "checked_claim" for frame in frames)
    assert frames[-1]["type"] == "error"
    assert frames[-1]["error"]["code"] == "public_answer_unavailable"
    assert "private manuscript passage" not in json.dumps(frames)


def _install_public_progressive_release_harness(
    monkeypatch,
    *,
    candidates: tuple[CheckedClaimCandidate, ...],
    final_answer: str,
):
    final_chunks = list(candidates[-1].source_chunks) if candidates else []

    def fake_answer(
        *_args,
        progress_callback=None,
        checked_claim_callback=None,
        **_kwargs,
    ):
        assert checked_claim_callback is not None
        if progress_callback is not None:
            progress_callback(AnswerProgressStage.GENERATING_ANSWER)
        for candidate in candidates:
            checked_claim_callback(candidate)
        if progress_callback is not None:
            progress_callback(AnswerProgressStage.VALIDATING_ANSWER)
        return SimpleNamespace(
            answer=final_answer,
            final_chunks=final_chunks,
            status="answered",
            content_outcome=None,
            answer_strategy="rag",
            answer_strategy_version="test",
            evidence_decision="direct_answer",
            diagnostics={},
        )

    monkeypatch.setattr(
        web_api,
        "_preflight_public_progressive_question",
        lambda _request, _settings: None,
    )
    monkeypatch.setattr(web_api, "UsageLedger", _FakeDevelopmentLedger)
    monkeypatch.setattr(web_api, "_configure_public_budget", lambda *_args: None)
    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    monkeypatch.setattr(web_api, "answer_run_diagnostics", lambda _result: {})


def test_public_progressive_locator_gate_runs_before_claim_release(monkeypatch):
    private_chunk = {
        "chunk_id": "private-source-id",
        "document": "Synthetic.md",
        "chapter_title": "Synthetic",
        "paragraph_start": 1,
        "paragraph_end": 1,
        "text": "Private manuscript body.",
    }
    claim = CheckedClaimCandidate(
        paragraph=1,
        text="A public-safe checked claim [Source 1].",
        source_chunks=(private_chunk,),
        audit_chunks=(private_chunk,),
    )
    _install_public_progressive_release_harness(
        monkeypatch,
        candidates=(claim,),
        final_answer=claim.text,
    )
    calls: list[str] = []

    def safe_sources(answer, *_args, **_kwargs):
        calls.append(answer)
        return {
            "source_schema": "archivist.public_sources/1",
            "sources": [{"kind": "public_locator", "source_number": 1}],
        }

    monkeypatch.setattr(
        web_api,
        "answer_has_extended_verbatim_overlap",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(web_api, "public_source_payload", safe_sources)

    frames = _frames(
        TestClient(web_api.create_app(_public_settings())).post(
            "/api/projects/current/question/progressive",
            json={"question": "What happened?"},
        )
    )

    assert [frame["type"] for frame in frames].count("checked_claim") == 1
    assert frames[-1]["type"] == "complete"
    # The first call admits the provisional claim; the second constructs the
    # canonical terminal source payload.
    assert calls == [claim.text, claim.text]
    serialized = json.dumps(frames)
    assert "private-source-id" not in serialized
    assert "Private manuscript body" not in serialized


def test_public_progressive_rolls_prior_claims_into_verbatim_gate(monkeypatch):
    private_chunk = {
        "chunk_id": "private-source-id",
        "document": "Synthetic.md",
        "chapter_title": "Synthetic",
        "paragraph_start": 1,
        "paragraph_end": 1,
        "text": "Private manuscript body.",
    }
    first = CheckedClaimCandidate(
        paragraph=1,
        text="First checked claim [Source 1].",
        source_chunks=(private_chunk,),
        audit_chunks=(private_chunk,),
    )
    second = CheckedClaimCandidate(
        paragraph=1,
        text="Second checked claim [Source 1].",
        source_chunks=(private_chunk,),
        audit_chunks=(private_chunk,),
    )
    _install_public_progressive_release_harness(
        monkeypatch,
        candidates=(first, second),
        final_answer=f"{first.text} {second.text}",
    )
    audited: list[str] = []

    def rolling_overlap(answer, *_args, **_kwargs):
        audited.append(answer)
        return len(audited) == 2

    monkeypatch.setattr(web_api, "answer_has_extended_verbatim_overlap", rolling_overlap)
    monkeypatch.setattr(
        web_api,
        "public_source_payload",
        lambda *_args, **_kwargs: {
            "source_schema": "archivist.public_sources/1",
            "sources": [],
        },
    )

    frames = _frames(
        TestClient(web_api.create_app(_public_settings())).post(
            "/api/projects/current/question/progressive",
            json={"question": "What happened?"},
        )
    )

    assert audited == [first.text, f"{first.text} {second.text}"]
    released = [frame for frame in frames if frame["type"] == "checked_claim"]
    assert [frame["text"] for frame in released] == [first.text]
    assert frames[-1]["type"] == "error"
    assert frames[-1]["error"]["code"] == "public_answer_unavailable"


@pytest.mark.parametrize("failure", [FileNotFoundError("missing locator"), RuntimeError("boom")])
def test_public_progressive_unexpected_or_missing_locator_failure_denies_claim(
    monkeypatch,
    failure,
):
    private_chunk = {
        "chunk_id": "private-source-id",
        "document": "Synthetic.md",
        "chapter_title": "Synthetic",
        "paragraph_start": 1,
        "paragraph_end": 1,
        "text": "Private manuscript body.",
    }
    claim = CheckedClaimCandidate(
        paragraph=1,
        text="A checked claim [Source 1].",
        source_chunks=(private_chunk,),
        audit_chunks=(private_chunk,),
    )
    _install_public_progressive_release_harness(
        monkeypatch,
        candidates=(claim,),
        final_answer=claim.text,
    )
    monkeypatch.setattr(
        web_api,
        "answer_has_extended_verbatim_overlap",
        lambda *_args, **_kwargs: False,
    )

    def fail_sources(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(web_api, "public_source_payload", fail_sources)

    frames = _frames(
        TestClient(web_api.create_app(_public_settings())).post(
            "/api/projects/current/question/progressive",
            json={"question": "What happened?"},
        )
    )

    assert not any(frame["type"] == "checked_claim" for frame in frames)
    assert frames[-1]["type"] == "error"
    assert frames[-1]["error"]["code"] == "public_answer_unavailable"
    serialized = json.dumps(frames)
    assert "private-source-id" not in serialized
    assert "Private manuscript body" not in serialized


def test_public_progressive_error_never_exposes_exception_text(monkeypatch):
    secret = "private manuscript phrase and provider stack trace"

    def fail(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(
        web_api,
        "_preflight_public_progressive_question",
        lambda _request, _settings: None,
    )
    monkeypatch.setattr(web_api, "_run_public_question", fail)
    response = TestClient(web_api.create_app(_public_settings())).post(
        "/api/projects/current/question/progressive",
        json={"question": "What happened?"},
    )
    frames = _frames(response)

    assert response.status_code == 200
    assert frames[-1]["type"] == "error"
    assert frames[-1]["error"] == {
        "code": "public_request_failed",
        "message": "Archivist could not complete this request.",
    }
    assert not any(frame["type"] in {"checked_claim", "complete"} for frame in frames)
    assert secret not in response.text


def test_progressive_preflights_remain_http_errors_and_release_public_gate(monkeypatch):
    monkeypatch.setattr(
        web_api,
        "EXPOSURE_SETTINGS",
        ExposureSettings.development(full_context_enabled=False),
    )
    development = TestClient(web_api.app).post(
        "/api/projects/current/question/progressive",
        json={
            "question": "What happened?",
            "archivist_mode": "professional",
            "answer_strategy": "full_context",
        },
    )
    assert development.status_code == 422
    assert development.headers["content-type"].startswith("application/json")
    assert development.json()["detail"]["code"] == "full_context_disabled"

    # A rejected progressive request must return its concurrency lease. With a
    # one-request ceiling, two sequential preflight failures both reach the
    # route instead of the second being misreported as a 429.
    settings = _public_settings(
        max_concurrent_requests=1,
        max_concurrent_per_client=1,
        full_context_requests_per_minute=6,
    )
    public_client = TestClient(web_api.create_app(settings))
    for _ in range(2):
        public = public_client.post(
            "/api/projects/current/question/progressive",
            json={
                "question": "What happened?",
                "archivist_mode": "professional",
                "answer_strategy": "full_context",
            },
        )
        assert public.status_code == 503
        assert public.headers["content-type"].startswith("application/json")
        assert public.json()["detail"]["code"] == "full_context_disabled"


def test_public_size_limit_covers_progressive_path():
    client = TestClient(web_api.create_app(_public_settings(max_request_bytes=300)))
    response = client.post(
        "/api/projects/current/question/progressive",
        content=json.dumps({"question": "x" * 500}),
        headers={"content-type": "application/json", "content-length": "1"},
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_too_large"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_stream_gate_lifecycle_releases_once_after_both_sides_finish():
    releases: list[str] = []
    lease = web_api._GateLease(lambda: releases.append("released"))
    lifecycle = web_api._StreamGateLifecycle(lease)

    lifecycle.stream_finished()
    assert releases == []
    lifecycle.worker_finished()
    assert releases == ["released"]
    lifecycle.worker_finished()
    lifecycle.stream_finished()
    assert releases == ["released"]


def test_progressive_answer_feature_is_advertised_for_both_profiles():
    development = web_api._feature_flags(web_api.ExposureProfile.DEVELOPMENT)
    public = web_api._feature_flags(
        web_api.ExposureProfile.PUBLIC_DEMO,
        _public_settings(),
    )

    assert development["progressive_answers"] is True
    assert public["progressive_answers"] is True
    assert development["experimental_compact_rag"] is False
    assert public["experimental_compact_rag"] is False
