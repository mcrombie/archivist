import hashlib
import json
from copy import deepcopy

import pytest

from answer_coverage import (
    CompactEvidenceCoverageAnswer,
    CompactInterpretiveEvidenceCoverageAnswer,
    EvidenceCoverageAnswer,
    InterpretiveEvidenceCoverageAnswer,
)
from retrieval_trace_contract import validate_text_free_retrieval_trace


def schema_sha256(schema_model: type[object]) -> str:
    model_json_schema = getattr(schema_model, "model_json_schema")
    canonical_json = json.dumps(
        model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compact_generation_trace(*, interpretive: bool = False) -> dict[str, object]:
    provider_schema = (
        "archivist.compact_interpretive_evidence_coverage/1"
        if interpretive
        else "archivist.compact_evidence_coverage/1"
    )
    expanded_schema = (
        "archivist.interpretive_evidence_coverage/3"
        if interpretive
        else "archivist.evidence_coverage/5"
    )
    provider_model = (
        CompactInterpretiveEvidenceCoverageAnswer if interpretive else CompactEvidenceCoverageAnswer
    )
    expanded_model = InterpretiveEvidenceCoverageAnswer if interpretive else EvidenceCoverageAnswer
    provider_schema_sha256 = schema_sha256(provider_model)
    return {
        "plan": {"policy_version": "evidence-planned-v27"},
        "generation_contract": {
            "prompt_version": "evidence-coverage-v12",
            "request_schema": "archivist.answer_request/7",
            "schema_sha256": provider_schema_sha256,
            "provider_schema": provider_schema,
            "provider_schema_sha256": provider_schema_sha256,
            "expanded_schema": expanded_schema,
            "expanded_schema_sha256": schema_sha256(expanded_model),
            "expander_version": "compact-evidence-expander/1",
        },
    }


@pytest.mark.parametrize("interpretive", [False, True])
def test_trace_contract_accepts_complete_compact_generation_identity(
    interpretive: bool,
):
    validate_text_free_retrieval_trace(compact_generation_trace(interpretive=interpretive))


def test_trace_contract_preserves_legacy_v26_generation_identity():
    validate_text_free_retrieval_trace(
        {
            "plan": {"policy_version": "evidence-planned-v26"},
            "generation_contract": {
                "prompt_version": "evidence-coverage-v11",
                "request_schema": "archivist.answer_request/6",
                "schema_sha256": "a" * 64,
            },
        }
    )


@pytest.mark.parametrize(
    "missing_field",
    [
        "provider_schema",
        "provider_schema_sha256",
        "expanded_schema",
        "expanded_schema_sha256",
        "expander_version",
    ],
)
def test_trace_contract_rejects_partial_compact_generation_identity(
    missing_field: str,
):
    trace = compact_generation_trace()
    generation = trace["generation_contract"]
    assert isinstance(generation, dict)
    generation.pop(missing_field)

    with pytest.raises(ValueError, match="metadata must be all-or-none"):
        validate_text_free_retrieval_trace(trace)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("policy_version", "evidence-planned-v26", "must use evidence-planned-v27"),
        ("prompt_version", "evidence-coverage-v11", "must use evidence-coverage-v12"),
        (
            "request_schema",
            "archivist.answer_request/6",
            "must use archivist.answer_request/7",
        ),
        (
            "expander_version",
            "compact-evidence-expander/2",
            "unsupported diagnostic value",
        ),
        (
            "expanded_schema",
            "archivist.interpretive_evidence_coverage/3",
            "invalid schema expansion pair",
        ),
        (
            "schema_sha256",
            "b" * 64,
            "must identify the provider schema",
        ),
    ],
)
def test_trace_contract_rejects_incoherent_compact_generation_identity(
    field: str,
    value: str,
    message: str,
):
    trace = deepcopy(compact_generation_trace())
    if field == "policy_version":
        plan = trace["plan"]
        assert isinstance(plan, dict)
        plan[field] = value
    else:
        generation = trace["generation_contract"]
        assert isinstance(generation, dict)
        generation[field] = value

    with pytest.raises(ValueError, match=message):
        validate_text_free_retrieval_trace(trace)


def test_trace_contract_rejects_v27_without_compact_generation_identity():
    with pytest.raises(ValueError, match="metadata must be all-or-none"):
        validate_text_free_retrieval_trace(
            {
                "plan": {"policy_version": "evidence-planned-v27"},
                "generation_contract": {
                    "prompt_version": "evidence-coverage-v12",
                    "request_schema": "archivist.answer_request/7",
                    "schema_sha256": "a" * 64,
                },
            }
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("provider_schema_sha256", "does not match the declared provider schema"),
        ("expanded_schema_sha256", "does not match the declared expanded schema"),
    ],
)
def test_trace_contract_rejects_arbitrary_well_formed_schema_hashes(
    field: str,
    message: str,
):
    trace = compact_generation_trace()
    generation = trace["generation_contract"]
    assert isinstance(generation, dict)
    generation[field] = "f" * 64
    if field == "provider_schema_sha256":
        generation["schema_sha256"] = "f" * 64

    with pytest.raises(ValueError, match=message):
        validate_text_free_retrieval_trace(trace)
