from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import evaluation_decomposition_v2
from evaluation_decomposition_v2 import (
    ClaimTextDecomposition,
    ClaimTextProposal,
    DECOMPOSITION_INPUT_SCHEMA,
    DECOMPOSITION_MAX_OUTPUT_TOKENS,
    DECOMPOSITION_MODEL,
    DECOMPOSITION_OPERATION,
    DECOMPOSITION_PROMPT,
    DECOMPOSITION_PROMPT_SHA256,
    DECOMPOSITION_SETTINGS,
    RUBRIC_MAX_OUTPUT_TOKENS,
    DecompositionValidationCode,
    DecompositionValidationError,
    aggregate_gold_claim_coverage,
    build_decomposition_input,
    decompose_answer_claims_v2,
    decomposition_instrument_identity,
    judge_item_rubric_v2,
    process_decomposition_proposal,
    serialize_decomposition_input,
)
from evaluation_judge import (
    ClaimDecomposition,
    EvaluationJudgeIncompleteResponseError,
    EvaluationJudgeModelMismatchError,
    EvaluationJudgeParseError,
    ItemRubricInput,
    ItemRubricVerdict,
)


class RetryAwareClient:
    def __init__(self) -> None:
        self.retry_options: list[int] = []

    def with_options(self, *, max_retries: int) -> "RetryAwareClient":
        self.retry_options.append(max_retries)
        return self


def _response(
    parsed: object,
    *,
    model: str = DECOMPOSITION_MODEL,
    status: str = "completed",
) -> SimpleNamespace:
    return SimpleNamespace(
        id="resp_decomp_v2_001",
        model=model,
        status=status,
        created_at=1_786_000_000,
        system_fingerprint="fp_decomp_v2",
        output_parsed=parsed,
    )


def _proposal(*claims: dict[str, object]) -> ClaimTextDecomposition:
    return ClaimTextDecomposition.model_validate(
        {
            "claims": list(claims),
        }
    )


def _claim(
    *,
    claim_id: str = "C001",
    text: str = "Fact.",
    cited_sources: list[int] | None = None,
) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "text": text,
        "cited_sources": [] if cited_sources is None else cited_sources,
    }


def test_provider_schema_has_exact_text_and_no_model_counted_offsets() -> None:
    assert set(ClaimTextProposal.model_fields) == {
        "claim_id",
        "text",
        "cited_sources",
    }
    schema = ClaimTextDecomposition.model_json_schema()
    proposal_properties = schema["$defs"]["ClaimTextProposal"]["properties"]
    assert set(proposal_properties) == {
        "claim_id",
        "text",
        "cited_sources",
    }
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["claims"]
    assert proposal_properties["text"]["type"] == "string"


def test_input_builder_is_closed_answer_only_and_deterministic() -> None:
    payload = build_decomposition_input(answer="A private answer [Source 1].")
    assert payload.schema == DECOMPOSITION_INPUT_SCHEMA
    assert json.loads(serialize_decomposition_input(payload)) == {
        "schema": DECOMPOSITION_INPUT_SCHEMA,
        "answer": "A private answer [Source 1].",
    }
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        type(payload).model_validate(
            {
                "schema": DECOMPOSITION_INPUT_SCHEMA,
                "answer": "Answer.",
                "gold": "must never enter this request",
            }
        )


@pytest.mark.parametrize("answer", ["", " \n\t"])
def test_blank_answer_is_rejected_before_provider_call(monkeypatch, answer: str) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        evaluation_decomposition_v2,
        "tracked_responses_parse",
        lambda *_args, **kwargs: calls.append(kwargs),
    )
    with pytest.raises(ValueError, match="must not be blank"):
        decompose_answer_claims_v2(object(), answer=answer)
    assert calls == []


def test_single_no_retry_call_derives_exact_canonical_text(monkeypatch) -> None:
    answer = "Sir Edwin governed [Source 2].\nHe resigned [Source 3, Source 4]."
    parsed = _proposal(
        _claim(text="Sir Edwin governed", cited_sources=[2]),
        _claim(
            claim_id="C002",
            text="He resigned",
            cited_sources=[3, 4],
        ),
    )
    calls: list[dict[str, object]] = []

    def fake_parse(client: object, *, operation: str, **request: object) -> object:
        calls.append({"client": client, "operation": operation, **request})
        return _response(parsed)

    monkeypatch.setattr(
        evaluation_decomposition_v2,
        "tracked_responses_parse",
        fake_parse,
    )
    client = RetryAwareClient()

    result = decompose_answer_claims_v2(client, answer=answer)

    assert client.retry_options == [0]
    assert len(calls) == 1
    call = calls[0]
    assert call["client"] is client
    assert call["operation"] == DECOMPOSITION_OPERATION
    assert call["instructions"] == DECOMPOSITION_PROMPT
    assert call["text_format"] is ClaimTextDecomposition
    assert call["max_output_tokens"] == DECOMPOSITION_MAX_OUTPUT_TOKENS
    assert {
        key: call[key] for key in ("model", "reasoning", "text")
    } == DECOMPOSITION_SETTINGS.responses_create_kwargs()
    assert set(json.loads(str(call["input"]))) == {"schema", "answer"}
    assert [claim.text for claim in result.parsed.claims] == [
        "Sir Edwin governed",
        "He resigned",
    ]
    assert result.parsed.claims[1].cited_sources == [3, 4]
    assert result.parsed.claims[1].char_start == answer.index("He resigned")
    assert result.parsed.claims[1].char_end == (
        answer.index("He resigned") + len("He resigned")
    )
    assert result.provider.id == "resp_decomp_v2_001"
    assert result.answer_sha256 == hashlib.sha256(answer.encode("utf-8")).hexdigest()


def test_historical_cumulative_offset_drift_is_repaired_by_local_exact_search() -> None:
    answer = (
        "First claim [Source 1].\n\n"
        "Second claim [Source 2].\n"
        "Third claim [Source 3]."
    )
    proposal = _proposal(
        _claim(text="First claim", cited_sources=[1]),
        _claim(claim_id="C002", text="Second claim", cited_sources=[2]),
        _claim(claim_id="C003", text="Third claim", cited_sources=[3]),
    )
    historical_drifted_starts = [1, answer.index("Second claim") + 2, answer.index("Third claim") + 3]

    canonical = process_decomposition_proposal(answer=answer, proposal=proposal)

    actual_starts = [claim.char_start for claim in canonical.claims]
    assert actual_starts == [
        answer.index("First claim"),
        answer.index("Second claim"),
        answer.index("Third claim"),
    ]
    assert actual_starts != historical_drifted_starts
    assert all(
        answer[claim.char_start : claim.char_end] == claim.text
        for claim in canonical.claims
    )
    assert "char_start" not in proposal.claims[0].model_dump()
    assert "char_end" not in proposal.claims[0].model_dump()


def test_ordered_search_can_disambiguate_an_occurrence_before_previous_claim() -> None:
    answer = "Repeated. Middle. Repeated."
    proposal = _proposal(
        _claim(text="Middle."),
        _claim(claim_id="C002", text="Repeated."),
    )

    canonical = process_decomposition_proposal(answer=answer, proposal=proposal)

    assert canonical.claims[1].char_start == answer.rindex("Repeated.")


def test_duplicate_eligible_exact_text_fails_closed_as_ambiguous() -> None:
    answer = "The council met. The council met."
    proposal = _proposal(_claim(text="The council met."))

    with pytest.raises(DecompositionValidationError) as exc_info:
        process_decomposition_proposal(answer=answer, proposal=proposal)

    assert (
        exc_info.value.failure_code
        is DecompositionValidationCode.AMBIGUOUS_CLAIM_TEXT
    )


@pytest.mark.parametrize(
    ("answer", "proposal", "code"),
    [
        (
            "Fact.",
            _proposal(_claim(claim_id="C002")),
            DecompositionValidationCode.SEQUENTIAL_CLAIM_IDS,
        ),
        (
            "Fact.",
            _proposal(_claim(text="Different.")),
            DecompositionValidationCode.CLAIM_TEXT_NOT_FOUND,
        ),
        (
            "Fact.  ",
            _proposal(_claim(text="  ")),
            DecompositionValidationCode.EMPTY_OR_WHITESPACE_TEXT,
        ),
        (
            "Fact [Source 1].",
            _proposal(_claim(text="Fact", cited_sources=[1, 1])),
            DecompositionValidationCode.DUPLICATE_CITED_SOURCE,
        ),
        (
            "Fact [Source 1].",
            _proposal(_claim(text="Fact", cited_sources=[2])),
            DecompositionValidationCode.CITED_SOURCE_ABSENT_FROM_ANSWER,
        ),
    ],
)
def test_local_processor_fails_closed_with_typed_codes(
    answer: str,
    proposal: ClaimTextDecomposition,
    code: DecompositionValidationCode,
) -> None:
    with pytest.raises(DecompositionValidationError) as exc_info:
        process_decomposition_proposal(answer=answer, proposal=proposal)
    assert exc_info.value.failure_code is code
    assert exc_info.value.proposal is proposal


def test_output_schema_rejects_extra_offsets_and_coerced_source_numbers() -> None:
    with pytest.raises(ValidationError):
        ClaimTextProposal.model_validate(
            {
                **_claim(),
                "char_start": 0,
            }
        )
    with pytest.raises(ValidationError):
        ClaimTextProposal.model_validate(
            {
                **_claim(),
                "cited_sources": ["1"],
            }
        )


def test_zero_factual_claims_is_a_valid_canonical_decomposition() -> None:
    canonical = process_decomposition_proposal(
        answer="Would you like to discuss the manuscript?",
        proposal=_proposal(),
    )
    assert canonical == ClaimDecomposition(claims=[])


@pytest.mark.parametrize(
    ("response", "exception"),
    [
        (_response(None), EvaluationJudgeParseError),
        (
            _response(_proposal(), status="incomplete"),
            EvaluationJudgeIncompleteResponseError,
        ),
        (
            _response(_proposal(), status="in_progress"),
            EvaluationJudgeParseError,
        ),
        (
            _response(_proposal(), model="gpt-unexpected"),
            EvaluationJudgeModelMismatchError,
        ),
    ],
)
def test_completed_response_failures_never_trigger_a_second_call(
    monkeypatch,
    response: SimpleNamespace,
    exception: type[Exception],
) -> None:
    calls: list[dict[str, object]] = []

    def fake_parse(*_args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return response

    monkeypatch.setattr(
        evaluation_decomposition_v2,
        "tracked_responses_parse",
        fake_parse,
    )
    with pytest.raises(exception):
        decompose_answer_claims_v2(RetryAwareClient(), answer="No factual claim.")
    assert len(calls) == 1


def test_rubric_wrapper_reuses_exact_claims_in_a_separate_no_retry_call(
    monkeypatch,
) -> None:
    answer = "A factual claim."
    decomposition = process_decomposition_proposal(
        answer=answer,
        proposal=_proposal(_claim(text=answer)),
    )
    rubric = ItemRubricInput.model_validate(
        {
            "question": "What happened?",
            "claims": [
                {"claim_id": "G001.1", "text": "A claim.", "essential": True}
            ],
            "must_not_claim": [],
        }
    )
    captured: list[dict[str, object]] = []
    sentinel = SimpleNamespace(
        parsed=ItemRubricVerdict.model_validate(
            {
                "gold_claims": [{"claim_id": "G001.1", "status": "present"}],
                "answer_claim_matches": [
                    {"answer_claim_id": "C001", "gold_claim_ids": ["G001.1"]}
                ],
                "must_not_claim": [],
                "response_behavior": "substantive_answer",
                "rationale": "The one claim matches.",
            }
        )
    )

    def fake_judge(client: object, **kwargs: object) -> object:
        captured.append({"client": client, **kwargs})
        return sentinel

    monkeypatch.setattr(evaluation_decomposition_v2, "_call_judge", fake_judge)
    client = RetryAwareClient()

    result = judge_item_rubric_v2(
        client,
        answer=answer,
        decomposition=decomposition,
        rubric=rubric,
    )

    assert result is sentinel
    assert client.retry_options == [0]
    assert captured[0]["client"] is client
    assert captured[0]["operation"] == "eval_item_rubric"
    assert captured[0]["max_output_tokens"] == RUBRIC_MAX_OUTPUT_TOKENS


def test_gold_claim_coverage_aggregation_is_deterministic() -> None:
    rubric = ItemRubricInput.model_validate(
        {
            "question": "What happened?",
            "claims": [
                {"claim_id": "G001.1", "text": "One.", "essential": True},
                {"claim_id": "G001.2", "text": "Two.", "essential": False},
                {"claim_id": "G001.3", "text": "Three.", "essential": True},
            ],
            "must_not_claim": ["Forbidden one.", "Forbidden two."],
        }
    )
    verdict = ItemRubricVerdict.model_validate(
        {
            "gold_claims": [
                {"claim_id": "G001.1", "status": "present"},
                {"claim_id": "G001.2", "status": "absent"},
                {"claim_id": "G001.3", "status": "contradicted"},
            ],
            "answer_claim_matches": [],
            "must_not_claim": [
                {"index": 0, "status": "asserted"},
                {"index": 1, "status": "not_asserted"},
            ],
            "response_behavior": "substantive_answer",
            "rationale": "Bounded result.",
        }
    )

    summary = aggregate_gold_claim_coverage(rubric=rubric, verdict=verdict)

    assert (summary.all_total, summary.all_present) == (3, 1)
    assert (summary.all_absent, summary.all_contradicted) == (1, 1)
    assert summary.all_present_rate == pytest.approx(1 / 3)
    assert (summary.essential_total, summary.essential_present) == (2, 1)
    assert (summary.essential_absent, summary.essential_contradicted) == (0, 1)
    assert summary.essential_present_rate == 0.5
    assert summary.must_not_claim_total == 2
    assert summary.must_not_claim_asserted == 1
    assert summary.must_not_claim_not_asserted == 1


def test_instrument_identity_binds_prompt_schema_and_exact_settings() -> None:
    identity = decomposition_instrument_identity()
    assert identity["prompt_sha256"] == hashlib.sha256(
        DECOMPOSITION_PROMPT.encode("utf-8")
    ).hexdigest()
    assert identity["prompt_sha256"] == DECOMPOSITION_PROMPT_SHA256
    assert identity["model"] == DECOMPOSITION_MODEL
    assert identity["reasoning_effort"] == "medium"
    assert identity["verbosity"] == "low"
    assert identity["max_output_tokens"] == 4_000
    assert identity["rubric_max_output_tokens"] == 3_000
    assert identity["automatic_retries"] == 0
    assert len(str(identity["output_schema_sha256"])) == 64
