from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

import evaluation_judge
from evaluation_judge import (
    CLAIM_DECOMPOSITION_PROMPT,
    CLAIM_DECOMPOSITION_PROMPT_SHA256,
    CLAIM_EVIDENCE_PROMPT,
    ITEM_RUBRIC_PROMPT,
    AtomicClaim,
    ClaimDecomposition,
    ClaimEvidenceVerdict,
    EvaluationJudgeModelMismatchError,
    EvaluationJudgeParseError,
    ItemRubricInput,
    ItemRubricVerdict,
    JUDGE_MODEL,
    JUDGE_SETTINGS,
    build_item_rubric_input,
    decompose_answer_claims,
    judge_claim_evidence,
    judge_item_rubric,
)


def provider_response(parsed, *, model: str = JUDGE_MODEL):
    return SimpleNamespace(
        id="resp_eval_001",
        model=model,
        created_at=1_786_000_000,
        system_fingerprint="fp_eval",
        output_parsed=parsed,
    )


def test_decomposition_call_is_single_answer_only_and_returns_provider_metadata(monkeypatch):
    calls: list[dict] = []
    answer = "Project Lumen began in Port Delta [Source 2]."
    parsed = ClaimDecomposition(
        claims=[
            AtomicClaim(
                claim_id="C001",
                text=answer,
                char_start=0,
                char_end=len(answer),
                cited_sources=[2],
            )
        ]
    )

    def fake_parse(client, *, operation, **request):
        calls.append({"client": client, "operation": operation, **request})
        return provider_response(parsed)

    monkeypatch.setattr(evaluation_judge, "tracked_responses_parse", fake_parse)
    client = object()

    result = decompose_answer_claims(client, answer=answer)

    assert result.parsed is parsed
    assert result.provider.id == "resp_eval_001"
    assert result.provider.model == JUDGE_MODEL
    assert result.provider.created_at == 1_786_000_000
    assert result.provider.system_fingerprint == "fp_eval"
    assert len(calls) == 1
    call = calls[0]
    assert call["client"] is client
    assert call["operation"] == "eval_claim_decomposition"
    assert call["instructions"] == CLAIM_DECOMPOSITION_PROMPT
    assert call["text_format"] is ClaimDecomposition
    assert json.loads(call["input"]) == {"answer": answer}
    assert {
        key: call[key] for key in ("model", "reasoning", "text")
    } == JUDGE_SETTINGS.responses_create_kwargs()
    assert not ({"conversation", "history", "previous_response_id"} & call.keys())
    assert CLAIM_DECOMPOSITION_PROMPT_SHA256 == hashlib.sha256(
        CLAIM_DECOMPOSITION_PROMPT.encode("utf-8")
    ).hexdigest()


def test_claim_evidence_call_contains_one_claim_and_sources_but_no_gold(monkeypatch):
    calls: list[dict] = []
    claim = AtomicClaim(
        claim_id="C004",
        text="Project Lumen changed the charter.",
        char_start=12,
        char_end=48,
        cited_sources=[3, 1],
    )
    parsed = ClaimEvidenceVerdict(
        claim_id="C004",
        faithfulness="partially_supported",
        source_verdicts=[
            {"source_number": 1, "label": "supported"},
            {"source_number": 3, "label": "unsupported"},
        ],
        rationale="Source 1 supports only part of the assertion.",
    )

    def fake_parse(client, *, operation, **request):
        calls.append({"client": client, "operation": operation, **request})
        return provider_response(parsed)

    monkeypatch.setattr(evaluation_judge, "tracked_responses_parse", fake_parse)

    result = judge_claim_evidence(
        object(),
        claim=claim,
        source_texts={3: "Third private passage.", 1: "First private passage."},
    )

    assert result.parsed is parsed
    assert len(calls) == 1
    call = calls[0]
    payload = json.loads(call["input"])
    assert call["operation"] == "eval_claim_evidence"
    assert call["instructions"] == CLAIM_EVIDENCE_PROMPT
    assert call["text_format"] is ClaimEvidenceVerdict
    assert payload == {
        "claim": {
            "claim_id": "C004",
            "text": "Project Lumen changed the charter.",
        },
        "cited_source_numbers": [3, 1],
        "sources": [
            {"source_number": 1, "text": "First private passage."},
            {"source_number": 3, "text": "Third private passage."},
        ],
    }
    assert "gold" not in call["input"].lower()
    assert "claims" not in payload
    assert not ({"conversation", "history", "previous_response_id"} & call.keys())


def test_item_rubric_call_contains_answer_and_gold_but_no_source_text(monkeypatch):
    calls: list[dict] = []
    answer = "The answer contains the relevant account."
    claims = [
        AtomicClaim(
            claim_id="C001",
            text=answer,
            char_start=0,
            char_end=len(answer),
            cited_sources=[],
        )
    ]
    rubric = ItemRubricInput.model_validate({
        "question": "What happened?",
        "claims": [
            {"claim_id": "H001-C1", "text": "A rubric claim.", "essential": True}
        ],
        "must_not_claim": ["A bounded tripwire."],
    })
    parsed = ItemRubricVerdict(
        gold_claims=[{"claim_id": "H001-C1", "status": "present"}],
        answer_claim_matches=[
            {"answer_claim_id": "C001", "gold_claim_ids": ["H001-C1"]}
        ],
        must_not_claim=[{"index": 0, "status": "not_asserted"}],
        response_behavior="substantive_answer",
        rationale="The answer contains the rubric claim.",
    )

    def fake_parse(client, *, operation, **request):
        calls.append({"client": client, "operation": operation, **request})
        return provider_response(parsed)

    monkeypatch.setattr(evaluation_judge, "tracked_responses_parse", fake_parse)

    result = judge_item_rubric(
        object(),
        answer=answer,
        answer_claims=claims,
        rubric=rubric,
    )

    assert result.parsed is parsed
    assert len(calls) == 1
    call = calls[0]
    assert call["operation"] == "eval_item_rubric"
    assert call["instructions"] == ITEM_RUBRIC_PROMPT
    assert call["text_format"] is ItemRubricVerdict
    assert json.loads(call["input"]) == {
        "answer": answer,
        "answer_claims": [{"claim_id": "C001", "text": answer}],
        "rubric": rubric.model_dump(mode="json"),
    }
    assert "private passage" not in call["input"].lower()
    assert not ({"sources", "source_text", "conversation", "history"} & call.keys())


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        (
            "answer_claim_matches",
            [{"answer_claim_id": "A001", "gold_claim_ids": ["H001-C1"]}],
            "changed answer claim IDs",
        ),
        (
            "gold_claims",
            [{"claim_id": "invented", "status": "present"}],
            "changed gold claim IDs",
        ),
        (
            "must_not_claim",
            [],
            "changed must-not-claim order",
        ),
    ],
)
def test_item_rubric_rejects_changed_locked_join_keys(
    monkeypatch,
    field,
    replacement,
    message,
):
    answer = "A factual answer."
    claim = AtomicClaim(
        claim_id="C001",
        text=answer,
        char_start=0,
        char_end=len(answer),
        cited_sources=[],
    )
    payload = {
        "gold_claims": [{"claim_id": "H001-C1", "status": "present"}],
        "answer_claim_matches": [
            {"answer_claim_id": "C001", "gold_claim_ids": ["H001-C1"]}
        ],
        "must_not_claim": [{"index": 0, "status": "not_asserted"}],
        "response_behavior": "substantive_answer",
        "rationale": "A bounded rationale.",
    }
    payload[field] = replacement
    parsed = ItemRubricVerdict.model_validate(payload)
    monkeypatch.setattr(
        evaluation_judge,
        "tracked_responses_parse",
        lambda *_args, **_kwargs: provider_response(parsed),
    )

    with pytest.raises(EvaluationJudgeParseError, match=message):
        judge_item_rubric(
            object(),
            answer=answer,
            answer_claims=[claim],
            rubric=ItemRubricInput.model_validate({
                "question": "What happened?",
                "claims": [
                    {"claim_id": "H001-C1", "text": "Gold.", "essential": True}
                ],
                "must_not_claim": ["Tripwire."],
            }),
        )


def test_rubric_projection_excludes_notes_locations_and_expected_behavior():
    projected = build_item_rubric_input(
        question="Which premise should be corrected?",
        gold_item={
            "id": "H037",
            "expected_behavior": "answer",
            "claims": [
                {
                    "claim_id": "H037.1",
                    "text": "The premise is false.",
                    "essential": True,
                    "supporting_chunk_ids": ["private_chunk"],
                }
            ],
            "must_not_claim": ["The false premise is true."],
            "relevant_chunk_ids": ["private_chunk"],
            "notes": "PRIVATE OWNER NOTE",
        },
    )

    serialized = json.dumps(projected.model_dump(mode="json"))
    assert "PRIVATE OWNER NOTE" not in serialized
    assert "private_chunk" not in serialized
    assert "expected_behavior" not in serialized
    assert projected.question == "Which premise should be corrected?"


def test_item_rubric_requires_the_closed_sanitized_input_before_call(monkeypatch):
    calls = []
    monkeypatch.setattr(
        evaluation_judge,
        "tracked_responses_parse",
        lambda *_args, **kwargs: calls.append(kwargs),
    )

    with pytest.raises(TypeError, match="sanitized ItemRubricInput"):
        judge_item_rubric(
            object(),
            answer="An answer.",
            answer_claims=[],
            rubric={"claims": []},  # type: ignore[arg-type]
        )
    assert calls == []


def test_missing_parsed_output_raises_after_exactly_one_call(monkeypatch):
    calls: list[dict] = []

    def fake_parse(client, *, operation, **request):
        calls.append({"client": client, "operation": operation, **request})
        return provider_response(None)

    monkeypatch.setattr(evaluation_judge, "tracked_responses_parse", fake_parse)

    with pytest.raises(EvaluationJudgeParseError, match="returned no parsed"):
        decompose_answer_claims(object(), answer="A factual answer.")

    assert len(calls) == 1


def test_decomposition_rejects_paraphrased_claim_text(monkeypatch):
    answer = "Project Lumen began in Port Delta [Source 2]."
    parsed = ClaimDecomposition(
        claims=[
            AtomicClaim(
                claim_id="C001",
                text="Project Lumen began in Port Delta.",
                char_start=0,
                char_end=len(answer),
                cited_sources=[2],
            )
        ]
    )

    monkeypatch.setattr(
        evaluation_judge,
        "tracked_responses_parse",
        lambda *_args, **_kwargs: provider_response(parsed),
    )

    with pytest.raises(EvaluationJudgeParseError, match="exact supplied-answer substring"):
        decompose_answer_claims(object(), answer=answer)


def test_decomposition_rejects_noncanonical_claim_ids(monkeypatch):
    answer = "One claim."
    parsed = ClaimDecomposition(
        claims=[
            AtomicClaim(
                claim_id="C1",
                text=answer,
                char_start=0,
                char_end=len(answer),
                cited_sources=[],
            )
        ]
    )
    monkeypatch.setattr(
        evaluation_judge,
        "tracked_responses_parse",
        lambda *_args, **_kwargs: provider_response(parsed),
    )

    with pytest.raises(EvaluationJudgeParseError, match="sequential claim IDs"):
        decompose_answer_claims(object(), answer=answer)


def test_claim_evidence_rejects_changed_source_join_keys(monkeypatch):
    claim = AtomicClaim(
        claim_id="C001",
        text="One claim.",
        char_start=0,
        char_end=10,
        cited_sources=[1],
    )
    parsed = ClaimEvidenceVerdict(
        claim_id="C001",
        faithfulness="supported",
        source_verdicts=[{"source_number": 2, "label": "supported"}],
        rationale="A bounded rationale.",
    )
    monkeypatch.setattr(
        evaluation_judge,
        "tracked_responses_parse",
        lambda *_args, **_kwargs: provider_response(parsed),
    )

    with pytest.raises(EvaluationJudgeParseError, match="changed source numbers"):
        judge_claim_evidence(
            object(),
            claim=claim,
            source_texts={1: "First.", 2: "Second."},
        )


def test_actual_model_mismatch_raises_after_call_is_preserved(monkeypatch):
    calls: list[dict] = []
    parsed = ClaimDecomposition(claims=[])

    def fake_parse(client, *, operation, **request):
        calls.append({"client": client, "operation": operation, **request})
        return provider_response(parsed, model="gpt-unexpected")

    monkeypatch.setattr(evaluation_judge, "tracked_responses_parse", fake_parse)

    with pytest.raises(EvaluationJudgeModelMismatchError) as exc_info:
        decompose_answer_claims(object(), answer="No factual claims.")

    assert len(calls) == 1
    assert exc_info.value.requested == JUDGE_MODEL
    assert exc_info.value.actual == "gpt-unexpected"


def test_claim_evidence_rejects_a_claim_batch_before_any_provider_call(monkeypatch):
    calls: list[dict] = []

    def fake_parse(client, *, operation, **request):
        calls.append({"client": client, "operation": operation, **request})
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(evaluation_judge, "tracked_responses_parse", fake_parse)
    claim = AtomicClaim(
        claim_id="C001",
        text="One claim.",
        char_start=0,
        char_end=10,
        cited_sources=[],
    )

    with pytest.raises(TypeError, match="exactly one AtomicClaim"):
        judge_claim_evidence(
            object(),
            claim=[claim],  # type: ignore[arg-type]
            source_texts={1: "One source."},
        )

    assert calls == []
