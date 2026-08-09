from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from answer_evaluation import (
    BaselineRunStatus,
    DecompositionFailureCode,
    EvaluationStratum,
    MetricAvailability,
    PublicCost,
    PublicEvaluationSummary,
    PublicLatency,
    PublicLimitationId,
    PublicMetric,
    PublicMetricId,
    PublicStratumSummary,
    ScoringDimension,
    ScoringMode,
    build_decomposed_claim,
    build_decomposed_pilot_item,
    build_private_decomposition_checkpoint,
    build_private_decomposition_failure_checkpoint,
    build_private_generated_item,
    build_private_source,
    build_private_usage_event,
    canonical_json_sha256,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_answer_evaluation.py"
SPEC = importlib.util.spec_from_file_location("run_answer_evaluation", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _gold_items() -> tuple[dict[str, object], ...]:
    payload = json.loads(runner.DEFAULT_GOLD.read_text(encoding="utf-8"))
    return tuple(payload["items"])


def _context() -> SimpleNamespace:
    items = _gold_items()
    calibration_ids, calibration_items, remaining_ids = runner._partition_gold_items(items)
    return SimpleNamespace(
        gold=SimpleNamespace(
            candidate_commit="8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e",
            candidate_rag_policy="evidence-planned-v26",
            gold_set_sha256="a" * 64,
            question_set_sha256="b" * 64,
            corpus_manifest_sha256="c" * 64,
        ),
        gold_items=items,
        calibration_ids=calibration_ids,
        calibration_items=calibration_items,
        remaining_ids=remaining_ids,
        model_catalog_sha256="d" * 64,
        corpus_identity={"embedded_chunk_count": 481, "hnsw_space": "l2"},
        run_identity={
            "git_commit": "8d3c6c9c0e7175ff6bd248ee3e9f2863793f700e",
            "working_tree": "clean",
            "dirty_fingerprint": None,
            "uv_lock_sha256": "e" * 64,
        },
    )


def _generated_item(item: dict[str, object], sequence: int):
    item_id = str(item["id"])
    answer = f"A source-grounded answer for {item_id} [1]."
    source = build_private_source(
        source_number=1,
        chunk_id=f"chunk_{item_id}",
        text=f"Private source text for {item_id}.",
        metadata={"chapter": sequence},
    )
    usage = build_private_usage_event(
        sequence=1,
        response_id=f"resp_{item_id}",
        recorded_at="2026-08-07T12:00:00+00:00",
        operation="answer_generation",
        requested_model="gpt-5.6-sol",
        actual_model="gpt-5.6-sol",
        input_tokens=100,
        cached_tokens=0,
        cache_write_tokens=0,
        output_tokens=20,
        reasoning_tokens=5,
        total_tokens=120,
        estimated_cost_nano_usd=1000,
        pricing_version="test-v1",
        unpriced=False,
    )
    trace = {
        "sequence": 1,
        "schema_id": "archivist.retrieval_trace/1",
        "trace_id": f"{sequence:032x}",
        "path": f"retrieval-traces/{item_id}.json",
        "sha256": f"{sequence:064x}",
        "query_sha256": f"{sequence + 100:064x}",
        "retrieval_version": "faceted-hybrid-rrf-v2",
    }
    return build_private_generated_item(
        item_id=item_id,
        question=str(item["question"]),
        stratum=str(item["stratum"]),
        expected_behavior=str(item["expected_behavior"]),
        answer=answer,
        status="answered",
        evidence_decision="direct_answer",
        diagnostics={"validation_result": "valid"},
        sources=(source,),
        elapsed_seconds=1.0,
        usage_events=(usage,),
        trace_references=(trace,),
    )


def test_preflight_constructs_no_openai_client(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(runner, "_build_context", lambda *_args, **_kwargs: sentinel)
    monkeypatch.setattr(runner, "_print_preflight", lambda context: None)
    monkeypatch.setattr(
        runner,
        "_create_openai_client",
        lambda _key: pytest.fail("preflight constructed an OpenAI client"),
    )

    assert runner.main(["preflight"]) == 0


def test_preflight_names_full_37_scope_and_exact_authorized_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner._print_preflight(_context())
    output = capsys.readouterr().out
    assert "37 frozen V26 RAG turns" in output
    assert "37 decomposition calls total" in output
    assert "semantic verdicts" in output
    assert (
        "python scripts/run_answer_evaluation.py run-37 "
        "--authorize-openai-full-evaluation --max-cost-usd 20"
    ) in output
    assert "cannot block generation" in output


def test_frozen_gold_partition_is_exact_and_rejects_duplicate_ids() -> None:
    items = _gold_items()
    calibration_ids, _, remaining_ids = runner._partition_gold_items(items)
    assert calibration_ids == runner.FIXED_CALIBRATION_IDS
    assert len(remaining_ids) == 27

    duplicate = [dict(item) for item in items]
    duplicate[-1]["id"] = duplicate[0]["id"]
    with pytest.raises(runner.AnswerEvaluationError, match="not unique"):
        runner._partition_gold_items(tuple(duplicate))


@pytest.mark.parametrize(
    ("authorized", "maximum"),
    ((False, 4.0), (True, None), (True, 0.0), (True, float("nan"))),
)
def test_paid_authorization_and_cost_ceiling_fail_closed(
    authorized: bool,
    maximum: float | None,
) -> None:
    args = argparse.Namespace(
        authorize_openai_full_evaluation=authorized,
        max_cost_usd=maximum,
    )
    with pytest.raises(runner.AnswerEvaluationError):
        runner._require_paid_authorization(
            args,
            flag_name="authorize_openai_full_evaluation",
        )


class _ZeroCostLedger:
    def __init__(self, _path: Path) -> None:
        pass

    def update_settings(self, **_kwargs: object) -> None:
        pass

    def summary(self) -> dict[str, float]:
        return {"all_time_usd": 0.0}


def _decomposition_for(generated):
    return build_decomposed_pilot_item(
        item_id=generated.item_id,
        answer_sha256=generated.answer_sha256,
        claims=(
            build_decomposed_claim(
                claim_id="C001",
                text=generated.answer,
                char_start=0,
                char_end=len(generated.answer),
                cited_source_numbers=(1,),
            ),
        ),
    )


def _decomposition_failure_for(generated, *, cohort_manifest_sha256: str):
    usage = build_private_usage_event(
        sequence=1,
        response_id=runner.DECOMPOSITION_FAILURE_RESPONSE_ID,
        recorded_at="2026-08-09T12:00:00+00:00",
        operation="eval_claim_decomposition",
        requested_model=runner.JUDGE_MODEL,
        actual_model=runner.JUDGE_MODEL,
        input_tokens=495,
        cached_tokens=0,
        cache_write_tokens=0,
        output_tokens=3688,
        reasoning_tokens=3374,
        total_tokens=4183,
        estimated_cost_nano_usd=56_557_500,
        pricing_version="2026-07-22",
        unpriced=False,
    )
    return build_private_decomposition_failure_checkpoint(
        cohort_manifest_sha256=cohort_manifest_sha256,
        item_id=generated.item_id,
        answer_sha256=generated.answer_sha256,
        repetition=1,
        prompt_version=runner.CLAIM_DECOMPOSITION_PROMPT_VERSION,
        prompt_sha256=runner.CLAIM_DECOMPOSITION_PROMPT_SHA256,
        judge_model=runner.JUDGE_MODEL,
        judge_settings={
            "reasoning_effort": runner.JUDGE_SETTINGS.reasoning_effort,
            "verbosity": runner.JUDGE_SETTINGS.verbosity,
        },
        provider={
            "id": runner.DECOMPOSITION_FAILURE_RESPONSE_ID,
            "model": runner.JUDGE_MODEL,
            "created_at": 1786285152.0,
            "system_fingerprint": None,
        },
        usage_event=usage,
        failure_code=DecompositionFailureCode.EXACT_SPAN_MISMATCH,
        provider_response_snapshot_sha256=(runner.DECOMPOSITION_FAILURE_RESPONSE_SNAPSHOT_SHA256),
    )


def test_run_37_makes_37_generation_and_37_decomposition_calls_without_semantic_judging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    generated_by_id = {
        str(item["id"]): _generated_item(item, sequence)
        for sequence, item in enumerate(context.gold_items, start=1)
    }
    generation_calls: list[str] = []
    decomposition_calls: list[tuple[str, int]] = []
    calibration_subsets: list[tuple[str, ...]] = []
    emitted: list[tuple[int, int, str | None, tuple[str, ...]]] = []
    call_order: list[str] = []

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runner, "UsageLedger", _ZeroCostLedger)
    monkeypatch.setattr(runner, "_require_private_run_root", lambda path: path)
    monkeypatch.setattr(Path, "mkdir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(Path, "is_file", lambda _path: False)
    monkeypatch.setattr(runner, "sha256_file", lambda _path: "f" * 64)
    monkeypatch.setattr(
        runner,
        "_create_openai_client",
        lambda _key: call_order.append("client") or object(),
    )
    cohort = SimpleNamespace(
        items=tuple(SimpleNamespace(item_id=str(item["id"])) for item in context.gold_items)
    )
    monkeypatch.setattr(
        runner,
        "_load_or_write_cohort_manifest",
        lambda *_args, **_kwargs: (cohort, "c" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_validated_recovery_reporting_binding",
        lambda **_kwargs: call_order.append("recovery-binding") or ("9" * 64, ("H003",)),
    )

    def generate(*, item, **_kwargs):
        item_id = str(item["id"])
        generation_calls.append(item_id)
        return generated_by_id[item_id]

    def decompose(*, generated, repetition, **_kwargs):
        decomposition_calls.append((generated.item_id, repetition))
        usage = build_private_usage_event(
            sequence=1,
            response_id=f"resp_decomposition_{generated.item_id}",
            recorded_at="2026-08-09T12:00:00+00:00",
            operation="eval_claim_decomposition",
            requested_model=runner.JUDGE_MODEL,
            actual_model=runner.JUDGE_MODEL,
            input_tokens=100,
            cached_tokens=0,
            cache_write_tokens=0,
            output_tokens=20,
            reasoning_tokens=5,
            total_tokens=120,
            estimated_cost_nano_usd=1000,
            pricing_version="test-v1",
            unpriced=False,
        )
        checkpoint = build_private_decomposition_checkpoint(
            cohort_manifest_sha256="c" * 64,
            item_id=generated.item_id,
            answer_sha256=generated.answer_sha256,
            repetition=repetition,
            prompt_version=runner.CLAIM_DECOMPOSITION_PROMPT_VERSION,
            prompt_sha256=runner.CLAIM_DECOMPOSITION_PROMPT_SHA256,
            judge_model=runner.JUDGE_MODEL,
            judge_settings={
                "reasoning_effort": runner.JUDGE_SETTINGS.reasoning_effort,
                "verbosity": runner.JUDGE_SETTINGS.verbosity,
            },
            provider={
                "id": f"resp_decomposition_{generated.item_id}",
                "model": runner.JUDGE_MODEL,
                "created_at": None,
                "system_fingerprint": None,
            },
            usage_event=usage,
            decomposition=_decomposition_for(generated),
        )
        return checkpoint.model_dump(mode="json")

    monkeypatch.setattr(runner, "_run_one_generated_item", generate)
    monkeypatch.setattr(runner, "_decomposition_checkpoint", decompose)

    def calibration_generation_subset(*, generated_items, **_kwargs):
        assert len(generated_items) == 37
        by_id = {item.item_id: item for item in generated_items}
        subset = tuple(by_id[item_id] for item_id in context.calibration_ids)
        calibration_subsets.append(tuple(item.item_id for item in subset))
        return subset, "a" * 64

    monkeypatch.setattr(
        runner,
        "_write_or_validate_calibration_generation_subset",
        calibration_generation_subset,
    )
    monkeypatch.setattr(runner, "_baseline_generation_fields", lambda **_kwargs: {})
    monkeypatch.setattr(runner, "_baseline_decomposition_fields", lambda **_kwargs: {})
    monkeypatch.setattr(runner, "_sealed_artifact", lambda fields: fields)
    monkeypatch.setattr(runner, "write_json_atomic_no_overwrite", lambda *_a, **_k: "e" * 64)
    monkeypatch.setattr(
        runner,
        "_emit_precalibration_results",
        lambda *, generated_items, decompositions, migration_artifact_sha256, recovered_item_ids, **_kwargs: (
            emitted.append(
                (
                    len(generated_items),
                    len(decompositions),
                    migration_artifact_sha256,
                    tuple(recovered_item_ids),
                )
            )
            or (Path("private.json"), Path("public.json"), Path("public.md"))
        ),
    )
    monkeypatch.setattr(
        runner,
        "judge_claim_evidence",
        lambda *_a, **_k: pytest.fail("run-37 requested a semantic evidence verdict"),
    )
    monkeypatch.setattr(
        runner,
        "judge_item_rubric",
        lambda *_a, **_k: pytest.fail("run-37 requested a semantic rubric verdict"),
    )

    runner._run_37(
        argparse.Namespace(
            authorize_openai_full_evaluation=True,
            max_cost_usd=20.0,
            run_root=runner.DEFAULT_RUN_ROOT / "exact-37-call-count",
            labels=runner.DEFAULT_LABELS,
        ),
        context,
    )

    expected_ids = [str(item["id"]) for item in context.gold_items]
    assert generation_calls == expected_ids
    assert decomposition_calls == [(item_id, 1) for item_id in expected_ids]
    assert calibration_subsets == [context.calibration_ids]
    assert emitted == [(37, 37, "9" * 64, ("H003",))]
    assert call_order[:2] == ["recovery-binding", "client"]


def test_completed_run_37_resumes_without_provider_calls_or_overwrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    generated = tuple(
        _generated_item(item, sequence) for sequence, item in enumerate(context.gold_items, start=1)
    )
    by_id = {item.item_id: item for item in generated}
    calibration_generated = tuple(by_id[item_id] for item_id in context.calibration_ids)
    decompositions = tuple(_decomposition_for(item) for item in generated)

    monkeypatch.setattr(runner, "UsageLedger", _ZeroCostLedger)
    monkeypatch.setattr(runner, "_require_private_run_root", lambda path: path)
    monkeypatch.setattr(Path, "mkdir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(Path, "is_file", lambda _path: True)
    monkeypatch.setattr(runner, "sha256_file", lambda _path: "f" * 64)
    cohort = SimpleNamespace(
        items=tuple(SimpleNamespace(item_id=item.item_id) for item in generated)
    )
    monkeypatch.setattr(
        runner,
        "_load_or_write_cohort_manifest",
        lambda *_args, **_kwargs: (cohort, "c" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_validated_recovery_reporting_binding",
        lambda **_kwargs: (None, ()),
    )
    monkeypatch.setattr(
        runner,
        "_load_generated_checkpoint",
        lambda _path, *, item, **_kwargs: by_id[str(item["id"])],
    )
    monkeypatch.setattr(
        runner,
        "_write_or_validate_calibration_generation_subset",
        lambda **_kwargs: (calibration_generated, "a" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_validate_baseline_generation_artifact",
        lambda *_args, **_kwargs: (generated, "d" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_validate_baseline_decomposition_artifact",
        lambda *_args, **_kwargs: (decompositions, tuple(), "e" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_emit_precalibration_results",
        lambda **_kwargs: (Path("private.json"), Path("public.json"), Path("public.md")),
    )
    monkeypatch.setattr(
        runner,
        "_create_openai_client",
        lambda _key: pytest.fail("completed run constructed a provider client"),
    )
    monkeypatch.setattr(
        runner,
        "_run_one_generated_item",
        lambda **_kwargs: pytest.fail("completed answer was regenerated"),
    )
    monkeypatch.setattr(
        runner,
        "_decomposition_checkpoint",
        lambda **_kwargs: pytest.fail("completed decomposition was repeated"),
    )
    monkeypatch.setattr(
        runner,
        "write_json_atomic_no_overwrite",
        lambda *_args, **_kwargs: pytest.fail("completed artifact was overwritten"),
    )

    runner._run_37(
        argparse.Namespace(
            authorize_openai_full_evaluation=True,
            max_cost_usd=20.0,
            run_root=runner.DEFAULT_RUN_ROOT / "resume-37",
            labels=runner.DEFAULT_LABELS,
        ),
        context,
    )


def test_run_37_preserves_h001_technical_failure_and_calls_only_remaining_36(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    generated = tuple(
        _generated_item(item, sequence) for sequence, item in enumerate(context.gold_items, start=1)
    )
    by_id = {item.item_id: item for item in generated}
    calibration_generated = tuple(by_id[item_id] for item_id in context.calibration_ids)
    provider_clients: list[tuple[str, object | None]] = []
    emitted: list[tuple[int, int]] = []
    client = object()

    def is_preserved(path: Path) -> bool:
        if path.name in {"baseline-generated.json", "calibration-generated.json"}:
            return True
        return path.name == "decomposition-1.json" and path.parent.name == "H001"

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runner, "UsageLedger", _ZeroCostLedger)
    monkeypatch.setattr(runner, "_require_private_run_root", lambda path: path)
    monkeypatch.setattr(Path, "mkdir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(Path, "is_file", is_preserved)
    monkeypatch.setattr(runner, "sha256_file", lambda _path: "f" * 64)
    monkeypatch.setattr(runner, "_create_openai_client", lambda _key: client)
    cohort = SimpleNamespace(
        items=tuple(SimpleNamespace(item_id=item.item_id) for item in generated)
    )
    monkeypatch.setattr(
        runner,
        "_load_or_write_cohort_manifest",
        lambda *_args, **_kwargs: (cohort, "c" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_validated_recovery_reporting_binding",
        lambda **_kwargs: ("9" * 64, ("H003",)),
    )
    monkeypatch.setattr(
        runner,
        "_load_generated_checkpoint",
        lambda _path, *, item, **_kwargs: by_id[str(item["id"])],
    )
    monkeypatch.setattr(
        runner,
        "_write_or_validate_calibration_generation_subset",
        lambda **_kwargs: (calibration_generated, "a" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_validate_baseline_generation_artifact",
        lambda *_args, **_kwargs: (generated, "b" * 64),
    )

    def decomposition_checkpoint(*, generated, client, **_kwargs):
        provider_clients.append((generated.item_id, client))
        if generated.item_id == "H001":
            return _decomposition_failure_for(
                generated,
                cohort_manifest_sha256="c" * 64,
            ).model_dump(mode="json")
        decomposition = _decomposition_for(generated)
        usage = build_private_usage_event(
            sequence=1,
            response_id=f"resp_decomposition_{generated.item_id}",
            recorded_at="2026-08-09T12:00:00+00:00",
            operation="eval_claim_decomposition",
            requested_model=runner.JUDGE_MODEL,
            actual_model=runner.JUDGE_MODEL,
            input_tokens=100,
            cached_tokens=0,
            cache_write_tokens=0,
            output_tokens=20,
            reasoning_tokens=5,
            total_tokens=120,
            estimated_cost_nano_usd=1000,
            pricing_version="test-v1",
            unpriced=False,
        )
        return build_private_decomposition_checkpoint(
            cohort_manifest_sha256="c" * 64,
            item_id=generated.item_id,
            answer_sha256=generated.answer_sha256,
            repetition=1,
            prompt_version=runner.CLAIM_DECOMPOSITION_PROMPT_VERSION,
            prompt_sha256=runner.CLAIM_DECOMPOSITION_PROMPT_SHA256,
            judge_model=runner.JUDGE_MODEL,
            judge_settings={
                "reasoning_effort": runner.JUDGE_SETTINGS.reasoning_effort,
                "verbosity": runner.JUDGE_SETTINGS.verbosity,
            },
            provider={
                "id": f"resp_decomposition_{generated.item_id}",
                "model": runner.JUDGE_MODEL,
                "created_at": None,
                "system_fingerprint": None,
            },
            usage_event=usage,
            decomposition=decomposition,
        ).model_dump(mode="json")

    monkeypatch.setattr(runner, "_decomposition_checkpoint", decomposition_checkpoint)
    monkeypatch.setattr(runner, "_baseline_decomposition_fields", lambda **_kwargs: {})
    monkeypatch.setattr(runner, "_sealed_artifact", lambda fields: fields)
    monkeypatch.setattr(runner, "write_json_atomic_no_overwrite", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner,
        "_emit_precalibration_results",
        lambda *, generated_items, decompositions, **_kwargs: (
            emitted.append((len(generated_items), len(decompositions)))
            or (Path("private.json"), Path("public.json"), Path("public.md"))
        ),
    )

    runner._run_37(
        argparse.Namespace(
            authorize_openai_full_evaluation=True,
            max_cost_usd=20.0,
            run_root=runner.DEFAULT_RUN_ROOT / "technical-failure-resume",
            labels=runner.DEFAULT_LABELS,
        ),
        context,
    )

    assert provider_clients[0] == ("H001", None)
    assert [item_id for item_id, value in provider_clients if value is client] == [
        item.item_id for item in generated[1:]
    ]
    assert len([value for _, value in provider_clients if value is client]) == 36
    assert emitted == [(37, 36)]


def test_retired_calibration_generate_cannot_make_paid_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner, "_build_context", lambda *_a, **_k: object())
    monkeypatch.setattr(
        runner,
        "_create_openai_client",
        lambda _key: pytest.fail("retired command constructed a provider client"),
    )
    assert (
        runner.main(
            [
                "calibration-generate",
                "--authorize-openai-calibration-generation",
                "--max-cost-usd",
                "4",
            ]
        )
        == 1
    )


def test_openai_client_disables_sdk_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_client_type(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(runner, "_openai_client_type", lambda: fake_client_type)
    runner._create_openai_client("secret")
    assert captured == {"api_key": "secret", "max_retries": 0}


def test_completed_calibration_is_validated_and_reused_without_calls_or_overwrite(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    context = _context()
    generated = tuple(
        _generated_item(item, sequence)
        for sequence, item in enumerate(context.calibration_items, start=1)
    )
    decomposed = tuple(
        build_decomposed_pilot_item(
            item_id=item.item_id,
            answer_sha256=item.answer_sha256,
            claims=(
                build_decomposed_claim(
                    claim_id="C001",
                    text=item.answer,
                    char_start=0,
                    char_end=len(item.answer),
                    cited_source_numbers=(1,),
                ),
            ),
        )
        for item in generated
    )
    run_root = runner.DEFAULT_RUN_ROOT
    validated: list[str] = []
    real_is_file = Path.is_file

    def completed_artifact_is_file(path: Path) -> bool:
        if path.name in {
            "baseline-generated.json",
            "baseline-decompositions.json",
            "calibration-generated.json",
            "calibration-decompositions.json",
            "calibration-labels.template.json",
        }:
            return True
        return real_is_file(path)

    monkeypatch.setattr(Path, "is_file", completed_artifact_is_file)
    monkeypatch.setattr(Path, "mkdir", lambda *_args, **_kwargs: None)
    cohort = SimpleNamespace(
        items=tuple(SimpleNamespace(item_id=item_id) for item_id in context.calibration_ids)
    )
    monkeypatch.setattr(
        runner,
        "_load_or_write_cohort_manifest",
        lambda *_args, **_kwargs: (cohort, "c" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_validate_generation_artifact",
        lambda *_args, **_kwargs: (validated.append("generation") or generated, "a" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_validate_decomposition_artifact",
        lambda *_args, **_kwargs: (
            validated.append("decomposition") or decomposed,
            "b" * 64,
        ),
    )
    monkeypatch.setattr(
        runner,
        "_load_or_write_label_template",
        lambda *_args, **_kwargs: validated.append("template"),
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        runner,
        "_create_openai_client",
        lambda _key: pytest.fail("completed calibration constructed a provider client"),
    )
    monkeypatch.setattr(
        runner,
        "_run_one_generated_item",
        lambda **_kwargs: pytest.fail("completed answer was regenerated"),
    )
    monkeypatch.setattr(
        runner,
        "_decomposition_checkpoint",
        lambda **_kwargs: pytest.fail("completed decomposition was regenerated"),
    )
    monkeypatch.setattr(
        runner,
        "write_json_atomic_no_overwrite",
        lambda *_args, **_kwargs: pytest.fail("completed artifact was overwritten"),
    )
    args = argparse.Namespace(
        authorize_openai_calibration_generation=True,
        max_cost_usd=4.0,
        run_root=run_root,
        labels=run_root / "calibration-labels.json",
    )

    runner._calibration_generate(args, context)

    assert validated == ["generation", "decomposition", "template"]
    assert f"NEXT ACTION: {runner.NEXT_ACTION_OWNER_LABELS}" in capsys.readouterr().out


def test_existing_decomposition_checkpoint_is_strictly_bound() -> None:
    generated = _generated_item(_context().calibration_items[0], 1)
    decomposition = build_decomposed_pilot_item(
        item_id=generated.item_id,
        answer_sha256=generated.answer_sha256,
        claims=(
            build_decomposed_claim(
                claim_id="C001",
                text=generated.answer,
                char_start=0,
                char_end=len(generated.answer),
                cited_source_numbers=(1,),
            ),
        ),
    )
    usage = build_private_usage_event(
        sequence=1,
        response_id="resp_decomp",
        recorded_at="2026-08-07T12:01:00+00:00",
        operation="eval_claim_decomposition",
        requested_model=runner.JUDGE_MODEL,
        actual_model=runner.JUDGE_MODEL,
        input_tokens=100,
        cached_tokens=0,
        cache_write_tokens=0,
        output_tokens=20,
        reasoning_tokens=5,
        total_tokens=120,
        estimated_cost_nano_usd=1000,
        pricing_version="test-v1",
        unpriced=False,
    )
    checkpoint = build_private_decomposition_checkpoint(
        cohort_manifest_sha256="c" * 64,
        item_id=generated.item_id,
        answer_sha256=generated.answer_sha256,
        repetition=1,
        prompt_version=runner.CLAIM_DECOMPOSITION_PROMPT_VERSION,
        prompt_sha256=runner.CLAIM_DECOMPOSITION_PROMPT_SHA256,
        judge_model=runner.JUDGE_MODEL,
        judge_settings={
            "reasoning_effort": runner.JUDGE_SETTINGS.reasoning_effort,
            "verbosity": runner.JUDGE_SETTINGS.verbosity,
        },
        provider={
            "id": "resp_decomp",
            "model": runner.JUDGE_MODEL,
            "created_at": None,
            "system_fingerprint": None,
        },
        usage_event=usage,
        decomposition=decomposition,
    )
    payload = checkpoint.model_dump(mode="json")

    assert (
        runner._validate_decomposition_checkpoint_payload(
            payload,
            generated=generated,
            repetition=1,
            cohort_manifest_sha256="c" * 64,
        )
        == decomposition
    )
    corrupted = json.loads(json.dumps(payload))
    corrupted["cohort_manifest_sha256"] = "d" * 64
    corrupted.pop("checkpoint_sha256")
    corrupted["checkpoint_sha256"] = canonical_json_sha256(corrupted)
    with pytest.raises(ValueError, match="cohort_manifest_sha256 changed"):
        runner._validate_decomposition_checkpoint_payload(
            corrupted,
            generated=generated,
            repetition=1,
            cohort_manifest_sha256="c" * 64,
        )


def test_run_root_must_be_below_private_evaluation_root() -> None:
    assert runner._require_private_run_root(runner.DEFAULT_RUN_ROOT) == (
        runner.DEFAULT_RUN_ROOT.resolve()
    )
    with pytest.raises(runner.AnswerEvaluationError, match="runtime/evaluations"):
        runner._require_private_run_root(ROOT / "public-evaluation")


def test_orphan_usage_refuses_a_repeat_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "_usage_rows_if_any", lambda *_args, **_kwargs: [{}])
    with pytest.raises(runner.AnswerEvaluationError, match="refusing a repeat call"):
        runner._require_no_orphan_usage(Path("usage.sqlite3"), turn_id="H001")


def test_retrieved_h001_snapshot_proves_exact_span_failure_without_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated = _generated_item(_context().gold_items[0], 1)
    usage_event = _decomposition_failure_for(
        generated,
        cohort_manifest_sha256="c" * 64,
    ).usage_events[0]
    output = {
        "claims": [
            {
                "claim_id": "C001",
                "text": generated.answer[:5],
                "char_start": 1,
                "char_end": 6,
                "cited_sources": [1],
            }
        ]
    }
    snapshot = {
        "schema": "archivist.answer_evaluation.retrieved_provider_response/1",
        "retrieval_kind": "responses.retrieve",
        "response_id": runner.DECOMPOSITION_FAILURE_RESPONSE_ID,
        "model": runner.JUDGE_MODEL,
        "created_at": 1786285152.0,
        "status": "completed",
        "output_text": json.dumps(output),
        "usage": {
            "input_tokens": 495,
            "input_tokens_details": {
                "cache_write_tokens": 0,
                "cached_tokens": 0,
            },
            "output_tokens": 3688,
            "output_tokens_details": {"reasoning_tokens": 3374},
            "total_tokens": 4183,
        },
    }
    monkeypatch.setattr(
        runner,
        "sha256_file",
        lambda _path: runner.DECOMPOSITION_FAILURE_RESPONSE_SNAPSHOT_SHA256,
    )
    monkeypatch.setattr(runner, "_load_json_object", lambda *_a, **_k: snapshot)
    monkeypatch.setattr(
        runner,
        "_private_usage_events",
        lambda *_a, **_k: (usage_event,),
    )
    monkeypatch.setattr(
        runner,
        "_create_openai_client",
        lambda _key: pytest.fail("snapshot proof constructed a provider client"),
    )

    provider, observed_usage, candidate = runner._prove_h001_decomposition_failure(
        snapshot_path=Path("private-response.json"),
        generated=generated,
        usage_db=Path("usage.sqlite3"),
    )

    assert provider["id"] == runner.DECOMPOSITION_FAILURE_RESPONSE_ID
    assert observed_usage == usage_event
    assert candidate.item_id == "H001"
    output["claims"][0]["text"] = generated.answer[2:6]
    output["claims"][0]["char_start"] = 2
    snapshot["output_text"] = json.dumps(output)
    with pytest.raises(runner.AnswerEvaluationError, match="no longer proves"):
        runner._prove_h001_decomposition_failure(
            snapshot_path=Path("private-response.json"),
            generated=generated,
            usage_db=Path("usage.sqlite3"),
        )


def test_decomposition_failure_recovery_is_provider_free_sealed_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context()
    context.corpus_identity = {
        "chunks_sha256": "6" * 64,
        "hnsw_space": "l2",
        "collection_name": "test-collection",
    }
    context.collection = SimpleNamespace(count=lambda: 481)
    private_root = tmp_path / "private-evaluations"
    source_root = private_root / "source-recovery-01"
    destination_root = private_root / "source-recovery-02"
    source_root.mkdir(parents=True)
    source_runner_sha = "7" * 64
    source_manifest = runner._expected_cohort_manifest(
        context,
        runner_sha256=source_runner_sha,
    )
    source_manifest_path = source_root / "cohort-manifest.json"
    runner.write_json_atomic_no_overwrite(source_manifest_path, source_manifest)
    real_sha256_file = runner.sha256_file
    source_manifest_sha = real_sha256_file(source_manifest_path)
    generated = tuple(
        _generated_item(item, sequence) for sequence, item in enumerate(context.gold_items, start=1)
    )
    trace_hashes: dict[str, str] = {}
    for item in generated:
        item_root = source_root / "items" / item.item_id
        checkpoint = runner.build_private_generation_checkpoint(
            cohort_manifest_sha256=source_manifest_sha,
            item=item,
        )
        runner.write_json_atomic_no_overwrite(item_root / "generated.json", checkpoint)
        trace = item.trace_references[0]
        trace_path = item_root / trace.path
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(f"sealed trace for {item.item_id}\n", encoding="utf-8")
        trace_hashes[item.item_id] = trace.sha256

    calibration_path = source_root / "calibration-generated.json"
    baseline_path = source_root / "baseline-generated.json"
    prior_migration_path = source_root / "migration-audit.json"
    usage_path = source_root / "full-evaluation-usage.sqlite3"
    calibration_path.write_text(
        json.dumps({"run_identity": context.run_identity}), encoding="utf-8"
    )
    baseline_path.write_text("{}", encoding="utf-8")
    prior_migration_path.write_text("{}", encoding="utf-8")
    usage_path.write_bytes(b"sealed logical ledger\n")
    snapshot_path = tmp_path / "H001-response.json"
    snapshot_path.write_bytes(b"sealed provider response\n")
    source_file_bytes = {
        path.relative_to(source_root).as_posix(): path.read_bytes()
        for path in source_root.rglob("*")
        if path.is_file()
    }
    turn_ids = tuple(
        sorted(
            [
                *(str(item["id"]) for item in context.gold_items),
                "H001:decomposition:1",
            ]
        )
    )
    logical_events = tuple(
        {"sequence": sequence, "response_id": f"resp-{sequence:03d}"} for sequence in range(1, 90)
    )
    calibration_ids = set(context.calibration_ids)
    calibration = tuple(item for item in generated if item.item_id in calibration_ids)
    h001 = generated[0]
    failure_usage = _decomposition_failure_for(
        h001,
        cohort_manifest_sha256="8" * 64,
    ).usage_events[0]
    validation_calls: list[Path] = []

    def bound_sha256_file(path: Path) -> str:
        candidate = Path(path)
        if "retrieval-traces" in candidate.parts:
            return trace_hashes[candidate.name.removesuffix(".json")]
        return real_sha256_file(candidate)

    def validate_migration(**kwargs: object) -> tuple[str, tuple[str, ...]]:
        run_root = Path(kwargs["run_root"])
        assert (run_root / "migration-audit.json").is_file()
        validation_calls.append(run_root)
        return "9" * 64, ("H003",)

    monkeypatch.setattr(runner, "PRIVATE_EVALUATION_ROOT", private_root)
    monkeypatch.setattr(runner, "DEFAULT_RECOVERY_ROOT", source_root)
    monkeypatch.setattr(
        runner,
        "DEFAULT_DECOMPOSITION_FAILURE_RECOVERY_ROOT",
        destination_root,
    )
    monkeypatch.setattr(
        runner,
        "DEFAULT_DECOMPOSITION_FAILURE_RESPONSE_SNAPSHOT",
        snapshot_path,
    )
    monkeypatch.setattr(runner, "DECOMPOSITION_FAILURE_SOURCE_RUNNER_SHA256", source_runner_sha)
    monkeypatch.setattr(
        runner,
        "DECOMPOSITION_FAILURE_SOURCE_COHORT_FILE_SHA256",
        source_manifest_sha,
    )
    monkeypatch.setattr(
        runner,
        "DECOMPOSITION_FAILURE_SOURCE_MIGRATION_FILE_SHA256",
        real_sha256_file(prior_migration_path),
    )
    monkeypatch.setattr(
        runner,
        "DECOMPOSITION_FAILURE_SOURCE_CALIBRATION_GENERATION_SHA256",
        real_sha256_file(calibration_path),
    )
    monkeypatch.setattr(
        runner,
        "DECOMPOSITION_FAILURE_SOURCE_BASELINE_GENERATION_SHA256",
        real_sha256_file(baseline_path),
    )
    monkeypatch.setattr(
        runner,
        "DECOMPOSITION_FAILURE_SOURCE_LEDGER_SHA256",
        real_sha256_file(usage_path),
    )
    monkeypatch.setattr(
        runner,
        "DECOMPOSITION_FAILURE_RESPONSE_SNAPSHOT_SHA256",
        real_sha256_file(snapshot_path),
    )
    monkeypatch.setattr(runner, "sha256_file", bound_sha256_file)
    monkeypatch.setattr(runner, "_usage_turn_ids", lambda _path: turn_ids)
    monkeypatch.setattr(runner, "_logical_usage_bindings", lambda _path: logical_events)
    monkeypatch.setattr(
        runner,
        "_validated_recovery_reporting_binding",
        lambda **_kwargs: ("a" * 64, ("H003",)),
    )
    monkeypatch.setattr(
        runner,
        "_validate_generation_artifact",
        lambda path, **_kwargs: (calibration, bound_sha256_file(path)),
    )
    monkeypatch.setattr(
        runner,
        "_validate_baseline_generation_artifact",
        lambda path, **_kwargs: (generated, bound_sha256_file(path)),
    )
    monkeypatch.setattr(
        runner,
        "replace",
        lambda value, **changes: SimpleNamespace(**{**vars(value), **changes}),
    )
    monkeypatch.setattr(
        runner,
        "_prove_h001_decomposition_failure",
        lambda **_kwargs: (
            {
                "id": runner.DECOMPOSITION_FAILURE_RESPONSE_ID,
                "model": runner.JUDGE_MODEL,
                "created_at": 1786285152.0,
                "system_fingerprint": None,
            },
            failure_usage,
            _decomposition_for(h001),
        ),
    )
    monkeypatch.setattr(
        runner,
        "_validate_decomposition_failure_migration_binding",
        validate_migration,
    )
    monkeypatch.setattr(
        runner,
        "_create_openai_client",
        lambda _key: pytest.fail("recovery constructed a provider client"),
    )
    args = argparse.Namespace(source_run_root=source_root, run_root=destination_root)

    runner._recover_decomposition_failure(args, context)

    failure_path = destination_root / "items" / "H001" / "decomposition-1.json"
    failure_payload = json.loads(failure_path.read_text(encoding="utf-8"))
    assert failure_payload["failure_code"] == "exact_span_mismatch"
    assert not list((destination_root / "items").glob("H00[2-9]/decomposition-1.json"))
    assert usage_path.read_bytes() == source_file_bytes["full-evaluation-usage.sqlite3"]
    assert tuple(runner._logical_usage_bindings(usage_path)) == logical_events
    assert {
        path.relative_to(source_root).as_posix(): path.read_bytes()
        for path in source_root.rglob("*")
        if path.is_file()
    } == source_file_bytes
    destination_bytes = {
        path.relative_to(destination_root).as_posix(): path.read_bytes()
        for path in destination_root.rglob("*")
        if path.is_file()
    }

    runner._recover_decomposition_failure(args, context)

    assert {
        path.relative_to(destination_root).as_posix(): path.read_bytes()
        for path in destination_root.rglob("*")
        if path.is_file()
    } == destination_bytes
    assert len(validation_calls) == 2


def _early_release_row() -> dict[str, object]:
    return {
        "response_id": "req_embedding_H003",
        "recorded_at": "2026-08-09T13:09:36+00:00",
        "operation": "query_embedding",
        "requested_model": runner.EMBEDDING_MODEL,
        "actual_model": runner.EMBEDDING_MODEL,
        "input_tokens": 45,
        "cached_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 45,
        "estimated_cost_nano_usd": 160,
        "pricing_version": "test-v1",
        "unpriced": False,
    }


def _clean_abstention_trace(question: str) -> dict[str, object]:
    plan = runner.build_question_plan(
        runner.ResolvedTurn(
            standalone_question=question,
            trusted_user_texts=(question,),
        )
    )
    target = plan.targets[0].query_surface_span
    return {
        "schema": "archivist.retrieval_trace/13",
        "trace_id": "1" * 32,
        "created_at": "2026-08-09T13:09:37+00:00",
        "retrieval_version": "faceted-hybrid-rrf-v15",
        "query": {"sha256": runner.hashlib.sha256(question.encode("utf-8")).hexdigest()},
        "plan": {
            "planner_used": False,
            "policy_version": runner.RAG_POLICY_VERSION,
            "planner_call": {"status": "not_called"},
        },
        "evidence": {
            "decision": {
                "value": "clean_abstention",
                "skip_answer_generation": True,
                "allowed_source_numbers": [],
                "rules_fired": ["certified_direct_absence", "no_safe_related_material"],
            },
            "targets": [
                {
                    "target_character_count": len(target),
                    "target_sha256": runner.hashlib.sha256(
                        " ".join(runner.tokenize_anchor(target)).encode("utf-8")
                    ).hexdigest(),
                }
            ],
        },
        "generation_contract": {
            "status": "clean_abstention",
            "structured_generation_called": False,
        },
    }


def test_trace_proven_local_release_accepts_embedding_only_and_rejects_unproven_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = "Discuss Thomas Jefferson's role as president."
    item_root = Path("private-run/items/H003")
    reference = runner.PrivateTraceReference(
        sequence=1,
        schema_id="archivist.retrieval_trace/13",
        trace_id="1" * 32,
        path="retrieval-traces/2026-08-09/trace.json",
        sha256="a" * 64,
        query_sha256=runner.hashlib.sha256(question.encode()).hexdigest(),
        retrieval_version="faceted-hybrid-rrf-v15",
    )
    row = _early_release_row()
    monkeypatch.setattr(runner, "_usage_rows", lambda *_a, **_k: [row])
    monkeypatch.setattr(runner, "sha256_file", lambda _path: "a" * 64)
    monkeypatch.setattr(
        runner,
        "_load_json_object",
        lambda _path, **_kwargs: _clean_abstention_trace(question),
    )

    proof = runner._prove_local_early_release(
        item_root=item_root,
        question=question,
        trace_reference=reference,
        usage_db=Path("usage.sqlite3"),
    )
    assert proof.status == "clean_abstention"
    assert proof.answer == runner._clean_abstention("Discuss Thomas Jefferson's")
    events = runner._private_usage_events(
        Path("usage.sqlite3"),
        turn_id="H003",
        phase="generation",
        local_release_proven=True,
        audited_ledger_recovery=True,
    )
    assert [event.operation for event in events] == ["query_embedding"]
    with pytest.raises(runner.AnswerEvaluationError, match="exactly one"):
        runner._private_usage_events(
            Path("usage.sqlite3"),
            turn_id="H003",
            phase="generation",
            audited_ledger_recovery=True,
        )


def test_orphaned_local_release_is_recovered_without_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold = next(item for item in _gold_items() if item["id"] == "H003")
    run_root = Path("private-run")
    item_root = run_root / "items" / "H003"
    row = _early_release_row()
    monkeypatch.setattr(runner, "_usage_rows_if_any", lambda *_a, **_k: [row])
    monkeypatch.setattr(runner, "_usage_rows", lambda *_a, **_k: [row])
    monkeypatch.setattr(Path, "is_file", lambda _path: False)
    monkeypatch.setattr(
        Path,
        "glob",
        lambda _path, _pattern: iter([item_root / "retrieval-traces/2026-08-09/trace.json"]),
    )
    reference = runner.PrivateTraceReference(
        sequence=1,
        schema_id="archivist.retrieval_trace/13",
        trace_id="1" * 32,
        path="retrieval-traces/2026-08-09/trace.json",
        sha256="a" * 64,
        query_sha256=runner.hashlib.sha256(str(gold["question"]).encode()).hexdigest(),
        retrieval_version="faceted-hybrid-rrf-v15",
    )
    monkeypatch.setattr(runner, "_trace_reference_from_path", lambda *_a, **_k: reference)
    proof = runner._LocalReleaseProof(
        answer=runner._clean_abstention("Discuss Thomas Jefferson's"),
        status="clean_abstention",
        evidence_decision="clean_abstention",
        diagnostics={"offline_recovery": {"full_turn_latency_recovered": False}},
        trace_reference=reference,
        elapsed_seconds=0.0,
    )
    monkeypatch.setattr(runner, "_prove_local_early_release", lambda **_k: proof)
    monkeypatch.setattr(
        runner,
        "_private_usage_events",
        lambda *_a, **_k: (
            build_private_usage_event(
                sequence=1,
                response_id="req_embedding_H003",
                recorded_at="2026-08-09T13:09:36+00:00",
                operation="query_embedding",
                requested_model=runner.EMBEDDING_MODEL,
                actual_model=runner.EMBEDDING_MODEL,
                input_tokens=45,
                cached_tokens=0,
                cache_write_tokens=0,
                output_tokens=0,
                reasoning_tokens=0,
                total_tokens=45,
                estimated_cost_nano_usd=160,
                pricing_version="test-v1",
                unpriced=False,
            ),
        ),
    )
    writes: list[Path] = []
    monkeypatch.setattr(
        runner,
        "write_json_atomic_no_overwrite",
        lambda path, _value: writes.append(path),
    )
    monkeypatch.setattr(
        runner,
        "run_evidence_planned_answer",
        lambda **_k: pytest.fail("recovery repeated the V26/provider path"),
    )
    args = argparse.Namespace(run_root=run_root, manifest=Path("unused"), chunks=Path("unused"))
    cohort_item = SimpleNamespace(
        item_id="H003",
        question_sha256=runner.hashlib.sha256(str(gold["question"]).encode()).hexdigest(),
    )
    generated = runner._run_one_generated_item(
        args=args,
        context=SimpleNamespace(),
        item=gold,
        client=None,
        usage_db=run_root / "usage.sqlite3",
        runner_sha256="a" * 64,
        cohort_manifest_sha256="b" * 64,
        cohort_item=cohort_item,
    )
    assert generated.item_id == "H003"
    assert generated.sources == ()
    assert item_root / "generated.json" in writes
    assert item_root / "local-release-recovery-audit.json" in writes


def test_existing_calibration_semantic_aggregate_requires_all_call_checkpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated = _generated_item(_context().calibration_items[0], 1)
    decomposition = build_decomposed_pilot_item(
        item_id=generated.item_id,
        answer_sha256=generated.answer_sha256,
        claims=(
            build_decomposed_claim(
                claim_id="C001",
                text=generated.answer,
                char_start=0,
                char_end=len(generated.answer),
                cited_source_numbers=(1,),
            ),
        ),
    )
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda path: path.name != "claim-evidence-C001-2.json",
    )

    with pytest.raises(runner.AnswerEvaluationError, match="refusing a repeat call"):
        runner._require_calibration_semantic_checkpoints(
            runner.DEFAULT_RUN_ROOT,
            generated=(generated,),
            decomposed=(decomposition,),
        )


def test_existing_baseline_semantic_aggregate_requires_active_lane_checkpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    calibration = _generated_item(context.calibration_items[0], 1)
    remaining_item = next(
        item for item in context.gold_items if item["id"] not in context.calibration_ids
    )
    remaining = _generated_item(remaining_item, 2)
    decompositions = tuple(
        build_decomposed_pilot_item(
            item_id=item.item_id,
            answer_sha256=item.answer_sha256,
            claims=(
                build_decomposed_claim(
                    claim_id="C001",
                    text=item.answer,
                    char_start=0,
                    char_end=len(item.answer),
                    cited_source_numbers=(1,),
                ),
            ),
        )
        for item in (calibration, remaining)
    )
    monkeypatch.setattr(Path, "is_file", lambda _path: False)

    with pytest.raises(runner.AnswerEvaluationError, match="refusing a repeat call"):
        runner._require_baseline_semantic_checkpoints(
            runner.DEFAULT_RUN_ROOT,
            generated=(calibration, remaining),
            decomposed=decompositions,
            calibration_item_ids=context.calibration_ids,
            evidence_active=True,
            rubric_active=False,
        )


def test_generation_usage_cardinality_and_order_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {"operation": "query_embedding"},
        {"operation": "answer_generation"},
        {"operation": "answer_generation"},
    ]
    monkeypatch.setattr(runner, "_usage_rows", lambda *_args, **_kwargs: rows)
    with pytest.raises(runner.AnswerEvaluationError, match="exactly one"):
        runner._private_usage_events(
            Path("usage.sqlite3"),
            turn_id="H001",
            phase="generation",
        )


def test_prospective_cost_reserve_fails_before_a_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner, "_ledger_total_cost", lambda _ledger: 3.30)
    with pytest.raises(runner.AnswerEvaluationError, match="prospective reserve"):
        runner._require_cost_reserve(
            object(),
            4.0,
            reserve_usd=runner.GENERATION_ITEM_COST_RESERVE_USD,
            label="generation item H001",
        )


def test_provider_capture_preserves_embedding_request_identity() -> None:
    response = SimpleNamespace(_request_id="req_embedding", model=runner.EMBEDDING_MODEL)
    raw_client = SimpleNamespace(
        embeddings=SimpleNamespace(create=lambda **_kwargs: response),
        responses=SimpleNamespace(),
    )
    client = runner._ProviderCapturingClient(raw_client)

    assert client.embeddings.create(model=runner.EMBEDDING_MODEL, input="query") is response
    assert client.observations == [
        runner._ProviderObservation("req_embedding", runner.EMBEDDING_MODEL)
    ]


def test_provider_capture_preserves_with_raw_response_path() -> None:
    payload = {"id": "resp_raw", "model": runner.JUDGE_MODEL}
    parsed = SimpleNamespace(id="resp_raw", model=runner.JUDGE_MODEL)
    legacy = SimpleNamespace(
        http_response=SimpleNamespace(json=lambda: payload),
        parse=lambda: parsed,
    )
    raw_client = SimpleNamespace(
        responses=SimpleNamespace(
            with_raw_response=SimpleNamespace(parse=lambda **_kwargs: legacy)
        ),
        embeddings=SimpleNamespace(),
    )
    client = runner._ProviderCapturingClient(raw_client)

    raw = client.responses.with_raw_response.parse(model=runner.JUDGE_MODEL)
    assert raw.http_response.json() == payload
    assert raw.parse() is parsed
    assert client.observations == [runner._ProviderObservation("resp_raw", runner.JUDGE_MODEL)]


def _semantic_usage_row(response_id: str, operation: str) -> dict[str, object]:
    return {
        "response_id": response_id,
        "recorded_at": "2026-08-07T13:00:00+00:00",
        "operation": operation,
        "requested_model": runner.JUDGE_MODEL,
        "actual_model": runner.JUDGE_MODEL,
        "input_tokens": 80,
        "cached_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 20,
        "reasoning_tokens": 5,
        "total_tokens": 100,
        "estimated_cost_nano_usd": 10_000,
        "pricing_version": "test-v1",
        "unpriced": False,
    }


def _two_source_semantic_item():
    gold_item = _context().calibration_items[0]
    base = _generated_item(gold_item, 1)
    second = build_private_source(
        source_number=2,
        chunk_id="chunk_H001_context",
        text="Uncited but supplied context for H001.",
        metadata={"chapter": 2},
    )
    generated = build_private_generated_item(
        item_id=base.item_id,
        question=base.question,
        stratum=base.stratum,
        expected_behavior=base.expected_behavior,
        answer=base.answer,
        status=base.status,
        evidence_decision=base.evidence_decision,
        diagnostics=base.diagnostics,
        sources=(*base.sources, second),
        elapsed_seconds=base.elapsed_seconds,
        usage_events=base.usage_events,
        trace_references=base.trace_references,
    )
    claim = build_decomposed_claim(
        claim_id="C001",
        text=generated.answer,
        char_start=0,
        char_end=len(generated.answer),
        cited_source_numbers=(1,),
    )
    decomposition = build_decomposed_pilot_item(
        item_id=generated.item_id,
        answer_sha256=generated.answer_sha256,
        claims=(claim,),
    )
    return gold_item, generated, decomposition, claim


def test_calibration_judge_fails_before_client_on_auth_or_label_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    monkeypatch.setattr(
        runner,
        "_create_openai_client",
        lambda _key: pytest.fail("invalid calibration constructed a provider client"),
    )
    unauthorized = argparse.Namespace(
        authorize_openai_calibration_judge=False,
        max_cost_usd=1.0,
        run_root=runner.DEFAULT_RUN_ROOT,
    )
    with pytest.raises(runner.AnswerEvaluationError, match="explicit"):
        runner._calibration_judge(unauthorized, context)

    monkeypatch.setattr(
        runner,
        "_load_validated_calibration_inputs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("owner label is incomplete")),
    )
    invalid_labels = argparse.Namespace(
        authorize_openai_calibration_judge=True,
        max_cost_usd=1.0,
        run_root=runner.DEFAULT_RUN_ROOT,
    )
    with pytest.raises(ValueError, match="owner label"):
        runner._calibration_judge(invalid_labels, context)


def test_semantic_calls_keep_evidence_and_rubric_lanes_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold_item, generated, decomposition, claim = _two_source_semantic_item()
    test_root = runner.DEFAULT_RUN_ROOT / "test-semantic-lanes-no-write"
    response_ids: list[str] = []
    evidence_inputs: list[tuple[object, dict[int, str]]] = []
    rubric_inputs: list[object] = []

    def fake_evidence(client: object, *, claim: object, source_texts: object):
        response_id = f"resp_evidence_{len(response_ids) + 1}"
        response_ids.append(response_id)
        client.observations.append(runner._ProviderObservation(response_id, runner.JUDGE_MODEL))
        evidence_inputs.append((claim, dict(source_texts)))
        return SimpleNamespace(
            parsed=runner.ClaimEvidenceVerdict.model_validate(
                {
                    "claim_id": claim.claim_id,
                    "faithfulness": "supported",
                    "source_verdicts": [{"source_number": 1, "label": "supported"}],
                    "rationale": "Supported by the supplied evidence.",
                }
            ),
            provider=SimpleNamespace(
                id=response_id,
                model=runner.JUDGE_MODEL,
                created_at=1,
                system_fingerprint="fp_test",
            ),
        )

    def fake_rubric(client: object, *, answer: str, answer_claims: object, rubric: object):
        response_id = "resp_rubric_1"
        response_ids.append(response_id)
        client.observations.append(runner._ProviderObservation(response_id, runner.JUDGE_MODEL))
        rubric_inputs.append(rubric)
        return SimpleNamespace(
            parsed=runner.ItemRubricVerdict.model_validate(
                {
                    "gold_claims": [
                        {"claim_id": item.claim_id, "status": "absent"} for item in rubric.claims
                    ],
                    "answer_claim_matches": [
                        {"answer_claim_id": item.claim_id, "gold_claim_ids": []}
                        for item in answer_claims
                    ],
                    "must_not_claim": [
                        {"index": index, "status": "not_asserted"}
                        for index, _ in enumerate(rubric.must_not_claim)
                    ],
                    "response_behavior": "substantive_answer",
                    "rationale": "Compared only with the sanitized rubric.",
                }
            ),
            provider=SimpleNamespace(
                id=response_id,
                model=runner.JUDGE_MODEL,
                created_at=1,
                system_fingerprint="fp_test",
            ),
        )

    monkeypatch.setattr(runner, "judge_claim_evidence", fake_evidence)
    monkeypatch.setattr(runner, "judge_item_rubric", fake_rubric)
    monkeypatch.setattr(runner, "_ledger_total_cost", lambda _ledger: 0.0)
    monkeypatch.setattr(
        runner,
        "_usage_rows",
        lambda _path, *, turn_id: [
            _semantic_usage_row(
                response_ids[-1],
                "eval_item_rubric" if turn_id.endswith("item-rubric") else "eval_claim_evidence",
            )
        ],
    )
    monkeypatch.setattr(runner, "write_json_atomic_no_overwrite", lambda *_args: "x" * 64)
    args = argparse.Namespace(run_root=test_root)

    first = runner._claim_evidence_checkpoint(
        args=args,
        generated=generated,
        decomposition=decomposition,
        claim=claim,
        call_ordinal=1,
        client=object(),
        ledger=object(),
        maximum=1.0,
        usage_db=test_root / "usage.sqlite3",
        cohort_manifest_sha256="c" * 64,
    )
    repeat = runner._claim_evidence_checkpoint(
        args=args,
        generated=generated,
        decomposition=decomposition,
        claim=claim,
        call_ordinal=2,
        client=object(),
        ledger=object(),
        maximum=1.0,
        usage_db=test_root / "usage.sqlite3",
        cohort_manifest_sha256="c" * 64,
    )
    rubric_result = runner._item_rubric_checkpoint(
        args=args,
        generated=generated,
        decomposition=decomposition,
        gold_item=gold_item,
        client=object(),
        ledger=object(),
        maximum=1.0,
        usage_db=test_root / "usage.sqlite3",
        cohort_manifest_sha256="c" * 64,
    )

    assert first.call_ordinal == 1 and repeat.call_ordinal == 2
    assert first.provider.response_id != repeat.provider.response_id
    assert len(evidence_inputs) == 2
    assert evidence_inputs[0] == evidence_inputs[1]
    assert list(evidence_inputs[0][1]) == [1, 2]
    assert [entry.source_number for entry in first.verdict.source_verdicts] == [1]
    assert len(rubric_inputs) == 1
    sanitized = rubric_inputs[0].model_dump(mode="json")
    assert "supporting_chunk_ids" not in json.dumps(sanitized)
    assert "relevant_chunk_ids" not in json.dumps(sanitized)
    assert str(gold_item["notes"]) not in json.dumps(sanitized)
    assert generated.sources[0].text not in json.dumps(sanitized)
    assert rubric_result.item_id == generated.item_id


def test_semantic_parse_failure_leaves_orphan_that_blocks_repeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, generated, decomposition, claim = _two_source_semantic_item()
    test_root = runner.DEFAULT_RUN_ROOT / "test-semantic-orphan-no-write"
    calls = 0
    orphaned = False

    def fail_after_completed_call(*_args: object, **_kwargs: object):
        nonlocal calls, orphaned
        calls += 1
        orphaned = True
        raise RuntimeError("structured parse failed after usage was retained")

    monkeypatch.setattr(runner, "judge_claim_evidence", fail_after_completed_call)
    monkeypatch.setattr(runner, "_ledger_total_cost", lambda _ledger: 0.0)
    monkeypatch.setattr(
        runner,
        "_usage_rows_if_any",
        lambda *_args, **_kwargs: [{}] if orphaned else [],
    )
    args = argparse.Namespace(run_root=test_root)
    values = {
        "args": args,
        "generated": generated,
        "decomposition": decomposition,
        "claim": claim,
        "call_ordinal": 1,
        "client": object(),
        "ledger": object(),
        "maximum": 1.0,
        "usage_db": test_root / "usage.sqlite3",
        "cohort_manifest_sha256": "c" * 64,
    }
    with pytest.raises(RuntimeError, match="parse failed"):
        runner._claim_evidence_checkpoint(**values)
    with pytest.raises(runner.AnswerEvaluationError, match="refusing a repeat call"):
        runner._claim_evidence_checkpoint(**values)
    assert calls == 1


def test_lock_instrument_is_offline_and_preserves_mixed_fallback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    context = _context()
    dimensions = tuple(
        SimpleNamespace(
            dimension=dimension,
            agreement_rate=0.70 if dimension.value == "claim_mapping" else 0.95,
            denominator=10,
        )
        for dimension in runner.ScoringDimension
    )
    projection = SimpleNamespace(
        pooled_exact_agreement=SimpleNamespace(agreement_rate=(5 * 0.95 + 0.70) / 6),
        repeat_agreement=SimpleNamespace(agreement_rate=0.95),
        dimensions=dimensions,
    )
    aggregate = SimpleNamespace(aggregate_sha256="a" * 64)
    monkeypatch.setattr(
        runner,
        "_load_semantic_inputs_offline",
        lambda *_args, **_kwargs: (
            aggregate,
            projection,
            "b" * 64,
            "c" * 64,
            "d" * 64,
            object(),
        ),
    )
    monkeypatch.setattr(
        runner,
        "_load_calibration_artifacts",
        lambda *_args, **_kwargs: ((), (), "b" * 64, "c" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_load_or_write_decomposition_stability",
        lambda *_args, **_kwargs: SimpleNamespace(stability_sha256="e" * 64),
    )
    monkeypatch.setattr(runner, "sha256_file", lambda _path: "f" * 64)
    written: list[object] = []
    monkeypatch.setattr(
        runner,
        "write_json_atomic_no_overwrite",
        lambda _path, payload: written.append(payload) or "0" * 64,
    )
    monkeypatch.setattr(
        runner,
        "_create_openai_client",
        lambda _key: pytest.fail("offline lock constructed a provider client"),
    )
    args = argparse.Namespace(
        owner_ratifies_scoring_lock=True,
        run_root=runner.DEFAULT_RUN_ROOT / "test-lock-instrument",
        labels=runner.DEFAULT_LABELS,
    )

    runner._lock_instrument(args, context)

    assert len(written) == 1
    lock = written[0]
    assert lock.scoring_mode.value == "mixed"
    assert (
        next(
            item for item in lock.dimensions if item.dimension.value == "claim_mapping"
        ).scoring_mode.value
        == "manual"
    )
    assert lock.baseline_next_action == runner.NEXT_ACTION_BASELINE
    assert f"OPTIONAL SCORING ACTION: {runner.NEXT_ACTION_BASELINE}" in capsys.readouterr().out


def _all_manual_instrument() -> SimpleNamespace:
    return SimpleNamespace(
        dimensions=tuple(
            SimpleNamespace(dimension=dimension, scoring_mode=ScoringMode.MANUAL)
            for dimension in ScoringDimension
        ),
        instrument_sha256="1" * 64,
    )


def test_semantic_baseline_reuses_all_37_generation_and_decomposition_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    generated = tuple(
        _generated_item(item, sequence) for sequence, item in enumerate(context.gold_items, start=1)
    )
    generated_by_id = {item.item_id: item for item in generated}
    decomposed = tuple(
        SimpleNamespace(
            item_id=item.item_id,
            answer_sha256=item.answer_sha256,
            decomposition_sha256=f"{sequence + 1000:064x}",
            claims=(),
        )
        for sequence, item in enumerate(generated, start=1)
    )
    decomposed_by_id = {item.item_id: item for item in decomposed}
    instrument = _all_manual_instrument()
    calibration_semantic = SimpleNamespace(
        items=tuple(
            SimpleNamespace(
                item_id=item_id,
                repeat_first_claim_evidence=None,
            )
            for item_id in context.calibration_ids
        )
    )
    calibration_generated = tuple(generated_by_id[item_id] for item_id in context.calibration_ids)
    calibration_decomposed = tuple(decomposed_by_id[item_id] for item_id in context.calibration_ids)
    cohort = SimpleNamespace(
        items=tuple(SimpleNamespace(item_id=item.item_id) for item in generated)
    )
    root = runner.DEFAULT_RUN_ROOT / "baseline-exact-call-count"
    required = {
        "cohort-manifest.json",
        "calibration-generated.json",
        "calibration-decompositions.json",
        "calibration-semantic-results.json",
        "calibration-agreement-projection.json",
        "instrument-lock.json",
        "baseline-generated.json",
        "baseline-decompositions.json",
    }

    def is_file(path: Path) -> bool:
        if path.name in required:
            return True
        if path.name == "generated.json":
            return path.parent.name in context.calibration_ids
        if path.name == "decomposition-1.json":
            return path.parent.name in context.calibration_ids
        return False

    monkeypatch.setattr(Path, "is_file", is_file)
    monkeypatch.setattr(Path, "mkdir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runner,
        "_load_locked_instrument",
        lambda *_args, **_kwargs: (
            instrument,
            calibration_semantic,
            object(),
            "2" * 64,
            "3" * 64,
            "4" * 64,
            SimpleNamespace(items=()),
        ),
    )
    monkeypatch.setattr(
        runner,
        "_load_calibration_artifacts",
        lambda *_args, **_kwargs: (
            calibration_generated,
            calibration_decomposed,
            "2" * 64,
            "3" * 64,
        ),
    )
    monkeypatch.setattr(
        runner,
        "_load_or_write_cohort_manifest",
        lambda *_args, **_kwargs: (cohort, "4" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_validate_baseline_generation_artifact",
        lambda *_args, **_kwargs: (generated, "5" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_validate_baseline_decomposition_artifact",
        lambda *_args, **_kwargs: (
            decomposed,
            tuple(
                SimpleNamespace(response_id=f"decomposition-{item.item_id}") for item in generated
            ),
            "6" * 64,
        ),
    )
    monkeypatch.setattr(runner, "sha256_file", lambda _path: "5" * 64)
    calls = {"client": 0, "generation": [], "decomposition": []}

    def client(_key: str) -> object:
        calls["client"] += 1
        return object()

    monkeypatch.setattr(runner, "_create_openai_client", client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeLedger:
        def __init__(self, _path: Path) -> None:
            pass

        def update_settings(self, **_kwargs: object) -> None:
            pass

    monkeypatch.setattr(runner, "UsageLedger", FakeLedger)
    monkeypatch.setattr(runner, "_ledger_total_cost", lambda _ledger: 0.0)

    def generate(**values: object):
        item = values["item"]
        item_id = str(item["id"])
        calls["generation"].append(item_id)
        return generated_by_id[item_id]

    monkeypatch.setattr(runner, "_run_one_generated_item", generate)
    calibration_checkpoint = {"kind": "calibration"}
    monkeypatch.setattr(
        runner,
        "_load_json_object",
        lambda *_args, **_kwargs: calibration_checkpoint,
    )

    def decompose(**values: object) -> dict[str, object]:
        item_id = values["generated"].item_id
        calls["decomposition"].append(item_id)
        return {"kind": item_id}

    monkeypatch.setattr(runner, "_decomposition_checkpoint", decompose)
    monkeypatch.setattr(
        runner,
        "_validate_decomposition_checkpoint_payload",
        lambda payload, *, generated, **_kwargs: decomposed_by_id[generated.item_id],
    )
    monkeypatch.setattr(
        runner,
        "PrivateDecompositionCheckpoint",
        SimpleNamespace(
            model_validate=lambda payload: SimpleNamespace(
                usage_event=SimpleNamespace(response_id=str(payload))
            )
        ),
    )
    monkeypatch.setattr(
        runner,
        "build_baseline_semantic_item_from_calibration",
        lambda item, **_kwargs: SimpleNamespace(item_id=item.item_id),
    )
    monkeypatch.setattr(
        runner,
        "build_baseline_semantic_item",
        lambda *, decomposition, **_kwargs: SimpleNamespace(item_id=decomposition.item_id),
    )
    semantic = SimpleNamespace(items=(), aggregate_sha256="6" * 64)
    monkeypatch.setattr(
        runner,
        "build_baseline_semantic_aggregate",
        lambda **_kwargs: semantic,
    )
    monkeypatch.setattr(
        runner,
        "_validate_or_write_baseline_semantic",
        lambda _path, *, expected, **_kwargs: expected,
    )
    monkeypatch.setattr(runner, "_load_or_write_manual_template", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "_load_optional_manual_scoring", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner,
        "_calibration_decomposition_usage_events",
        lambda *_args, **_kwargs: (),
    )
    full = SimpleNamespace(artifact_sha256="7" * 64)
    monkeypatch.setattr(
        runner,
        "build_private_full_run_artifact",
        lambda **_kwargs: full,
    )
    monkeypatch.setattr(
        runner,
        "_load_or_write_private_full_run",
        lambda _path, *, expected, **_kwargs: expected,
    )
    monkeypatch.setattr(
        runner,
        "write_json_atomic_no_overwrite",
        lambda *_args, **_kwargs: "8" * 64,
    )
    monkeypatch.setattr(
        runner,
        "_claim_evidence_checkpoint",
        lambda **_kwargs: pytest.fail("manual-only evidence lane called a judge"),
    )
    monkeypatch.setattr(
        runner,
        "_item_rubric_checkpoint",
        lambda **_kwargs: pytest.fail("manual-only rubric lane called a judge"),
    )
    args = argparse.Namespace(
        authorize_openai_remaining_baseline=True,
        max_cost_usd=30.0,
        run_root=root,
    )

    runner._baseline(args, context)

    assert calls["client"] == 0
    assert calls["generation"] == []
    assert calls["decomposition"] == []


def test_completed_baseline_resume_makes_no_calls_and_overwrites_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    generated = tuple(
        _generated_item(item, sequence) for sequence, item in enumerate(context.gold_items, start=1)
    )
    decompositions = tuple(
        SimpleNamespace(
            item_id=item.item_id,
            answer_sha256=item.answer_sha256,
            decomposition_sha256=f"{sequence + 2000:064x}",
            claims=(),
        )
        for sequence, item in enumerate(generated, start=1)
    )
    instrument = _all_manual_instrument()
    calibration_semantic = SimpleNamespace(
        items=tuple(
            SimpleNamespace(item_id=item_id, repeat_first_claim_evidence=None)
            for item_id in context.calibration_ids
        )
    )
    cohort = SimpleNamespace(
        items=tuple(SimpleNamespace(item_id=item.item_id) for item in generated)
    )
    root = runner.DEFAULT_RUN_ROOT / "baseline-resume-no-call"

    def is_file(path: Path) -> bool:
        return path.name not in {
            "manual-scoring.json",
            "private-full-run.manual.json",
        }

    monkeypatch.setattr(Path, "is_file", is_file)
    monkeypatch.setattr(Path, "mkdir", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner,
        "_load_locked_instrument",
        lambda *_a, **_k: (
            instrument,
            calibration_semantic,
            object(),
            "2" * 64,
            "3" * 64,
            "4" * 64,
            SimpleNamespace(items=()),
        ),
    )
    monkeypatch.setattr(
        runner,
        "_load_calibration_artifacts",
        lambda *_a, **_k: (
            tuple(item for item in generated if item.item_id in context.calibration_ids),
            tuple(item for item in decompositions if item.item_id in context.calibration_ids),
            "2" * 64,
            "3" * 64,
        ),
    )
    monkeypatch.setattr(
        runner,
        "_load_or_write_cohort_manifest",
        lambda *_a, **_k: (cohort, "4" * 64),
    )
    monkeypatch.setattr(runner, "sha256_file", lambda _path: "5" * 64)
    monkeypatch.setattr(
        runner,
        "_validate_baseline_generation_artifact",
        lambda *_a, **_k: (generated, "6" * 64),
    )
    monkeypatch.setattr(
        runner,
        "_validate_baseline_decomposition_artifact",
        lambda *_a, **_k: (decompositions, tuple(object() for _ in generated), "7" * 64),
    )
    monkeypatch.setattr(
        runner,
        "build_baseline_semantic_item_from_calibration",
        lambda item, **_k: SimpleNamespace(item_id=item.item_id),
    )
    monkeypatch.setattr(
        runner,
        "build_baseline_semantic_item",
        lambda *, decomposition, **_k: SimpleNamespace(item_id=decomposition.item_id),
    )
    semantic = SimpleNamespace(items=(), aggregate_sha256="8" * 64)
    monkeypatch.setattr(
        runner,
        "build_baseline_semantic_aggregate",
        lambda **_k: semantic,
    )
    monkeypatch.setattr(
        runner,
        "_validate_or_write_baseline_semantic",
        lambda _path, *, expected, **_k: expected,
    )
    monkeypatch.setattr(runner, "_load_or_write_manual_template", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "_load_optional_manual_scoring", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner,
        "_calibration_decomposition_usage_events",
        lambda *_a, **_k: (),
    )
    full = SimpleNamespace(artifact_sha256="9" * 64)
    monkeypatch.setattr(
        runner,
        "build_private_full_run_artifact",
        lambda **_k: full,
    )
    monkeypatch.setattr(
        runner,
        "_load_or_write_private_full_run",
        lambda _path, *, expected, **_k: expected,
    )
    monkeypatch.setattr(
        runner,
        "UsageLedger",
        lambda _path: pytest.fail("resume constructed a usage ledger"),
    )
    monkeypatch.setattr(
        runner,
        "_create_openai_client",
        lambda _key: pytest.fail("resume constructed an OpenAI client"),
    )
    monkeypatch.setattr(
        runner,
        "_run_one_generated_item",
        lambda **_k: pytest.fail("resume regenerated an answer"),
    )
    monkeypatch.setattr(
        runner,
        "_decomposition_checkpoint",
        lambda **_k: pytest.fail("resume repeated a decomposition"),
    )
    monkeypatch.setattr(
        runner,
        "_claim_evidence_checkpoint",
        lambda **_k: pytest.fail("resume repeated an evidence judgment"),
    )
    monkeypatch.setattr(
        runner,
        "_item_rubric_checkpoint",
        lambda **_k: pytest.fail("resume repeated a rubric judgment"),
    )
    monkeypatch.setattr(
        runner,
        "write_json_atomic_no_overwrite",
        lambda *_a, **_k: pytest.fail("resume overwrote an artifact"),
    )

    runner._baseline(
        argparse.Namespace(
            authorize_openai_remaining_baseline=True,
            max_cost_usd=30.0,
            run_root=root,
        ),
        context,
    )


def _public_summary_fixture() -> PublicEvaluationSummary:
    metrics = tuple(
        PublicMetric(
            metric_id=metric_id,
            availability=MetricAvailability.AVAILABLE,
            numerator=1,
            denominator=1,
            value=1.0,
        )
        for metric_id in PublicMetricId
    )
    stratum_counts = {
        EvaluationStratum.FOCUSED_BIOGRAPHICAL: 8,
        EvaluationStratum.FOCUSED_ANALYTICAL: 8,
        EvaluationStratum.CONCEPTUAL: 5,
        EvaluationStratum.BROAD_THEMATIC: 10,
        EvaluationStratum.OUT_OF_CORPUS: 4,
        EvaluationStratum.ADVERSARIAL_PREMISE: 2,
    }
    return PublicEvaluationSummary(
        evaluation_id="v26-held-out-answer-quality-2026-08-07",
        candidate_id="evidence-planned-v26",
        candidate_commit="a" * 40,
        rag_policy="evidence-planned-v26",
        cohort_manifest_sha256="1" * 64,
        corpus_manifest_sha256="2" * 64,
        chunks_sha256="3" * 64,
        question_set_sha256="4" * 64,
        model_catalog_sha256="5" * 64,
        runner_sha256="6" * 64,
        planner_model_id="gpt-5.6-sol",
        generator_model_id="gpt-5.6-sol",
        judge_model_id="gpt-5.6-terra",
        embedding_model_id="text-embedding-3-small",
        private_artifact_sha256="7" * 64,
        instrument_lock_sha256="8" * 64,
        gold_set_sha256="9" * 64,
        limitation_ids=(
            PublicLimitationId.CANONICAL_MODEL_ID_MUTABILITY,
            PublicLimitationId.GENERATOR_SPREAD_UNMEASURED,
            PublicLimitationId.DESCRIPTIVE_NOT_GATE,
        ),
        run_status=BaselineRunStatus.COMPLETE,
        scoring_mode=ScoringMode.JUDGE,
        item_count=37,
        source_count=100,
        claim_count=80,
        citation_count=60,
        error_count=0,
        metrics=metrics,
        strata=tuple(
            PublicStratumSummary(stratum=stratum, item_count=count, metrics=metrics)
            for stratum, count in stratum_counts.items()
        ),
        cost=PublicCost(
            estimated_cost_usd=1.25,
            priced_event_count=100,
            unpriced_event_count=0,
        ),
        latency=PublicLatency(
            total_seconds=370.0,
            mean_seconds=10.0,
            p50_seconds=8.0,
            p95_seconds=20.0,
            maximum_seconds=30.0,
        ),
    )


def test_public_markdown_uses_closed_summary_and_contains_no_private_text() -> None:
    summary = _public_summary_fixture()
    report = runner._public_report_markdown(
        summary,
        public_summary_sha256="f" * 64,
    )
    assert "Public summary JSON SHA-256: `" + "f" * 64 + "`" in report
    for private_text in (
        "SENTINEL PRIVATE QUESTION",
        "SENTINEL PRIVATE ANSWER",
        "SENTINEL PRIVATE SOURCE",
        "chunk_H001",
    ):
        assert private_text not in report


def test_report_command_never_constructs_an_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    summary = _public_summary_fixture()
    completed = SimpleNamespace(
        cohort_manifest=object(),
        instrument=object(),
        calibration_semantic=object(),
        generated_items=(),
        decompositions=(),
        semantic=object(),
        additional_usage_events=(),
        manual=None,
        base_full=object(),
        manual_full=None,
    )
    monkeypatch.setattr(runner, "_load_completed_baseline", lambda *_a, **_k: completed)
    monkeypatch.setattr(
        runner,
        "build_public_evaluation_summary",
        lambda **_kwargs: summary,
    )
    monkeypatch.setattr(
        runner,
        "_load_or_write_public_summary",
        lambda *_a, **_k: "f" * 64,
    )
    monkeypatch.setattr(runner, "_load_or_write_public_report", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner,
        "_create_openai_client",
        lambda _key: pytest.fail("offline report constructed an OpenAI client"),
    )
    runner._report(
        argparse.Namespace(run_root=runner.DEFAULT_RUN_ROOT / "report-no-client"),
        context,
    )
