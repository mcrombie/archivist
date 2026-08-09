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
    emitted: list[tuple[int, int]] = []

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runner, "UsageLedger", _ZeroCostLedger)
    monkeypatch.setattr(runner, "_require_private_run_root", lambda path: path)
    monkeypatch.setattr(Path, "mkdir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(Path, "is_file", lambda _path: False)
    monkeypatch.setattr(runner, "sha256_file", lambda _path: "f" * 64)
    monkeypatch.setattr(runner, "_create_openai_client", lambda _key: object())
    cohort = SimpleNamespace(
        items=tuple(SimpleNamespace(item_id=str(item["id"])) for item in context.gold_items)
    )
    monkeypatch.setattr(
        runner,
        "_load_or_write_cohort_manifest",
        lambda *_args, **_kwargs: (cohort, "c" * 64),
    )

    def generate(*, item, **_kwargs):
        item_id = str(item["id"])
        generation_calls.append(item_id)
        return generated_by_id[item_id]

    def decompose(*, generated, repetition, **_kwargs):
        decomposition_calls.append((generated.item_id, repetition))
        return {
            "item_id": generated.item_id,
            "repetition": repetition,
            "decomposition": _decomposition_for(generated).model_dump(mode="json"),
        }

    monkeypatch.setattr(runner, "_run_one_generated_item", generate)
    monkeypatch.setattr(runner, "_decomposition_checkpoint", decompose)
    monkeypatch.setattr(
        runner,
        "_validate_decomposition_checkpoint_payload",
        lambda payload, *, generated, **_kwargs: _decomposition_for(generated),
    )

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
    monkeypatch.setattr(
        runner,
        "PrivateDecompositionCheckpoint",
        SimpleNamespace(
            model_validate=lambda _payload: SimpleNamespace(usage_event=object())
        ),
    )
    monkeypatch.setattr(runner, "_baseline_generation_fields", lambda **_kwargs: {})
    monkeypatch.setattr(runner, "_baseline_decomposition_fields", lambda **_kwargs: {})
    monkeypatch.setattr(runner, "_sealed_artifact", lambda fields: fields)
    monkeypatch.setattr(runner, "write_json_atomic_no_overwrite", lambda *_a, **_k: "e" * 64)
    monkeypatch.setattr(
        runner,
        "_emit_precalibration_results",
        lambda *, generated_items, decompositions, **_kwargs: (
            emitted.append((len(generated_items), len(decompositions)))
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
    assert emitted == [(37, 37)]


def test_completed_run_37_resumes_without_provider_calls_or_overwrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    generated = tuple(
        _generated_item(item, sequence)
        for sequence, item in enumerate(context.gold_items, start=1)
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


def test_retired_calibration_generate_cannot_make_paid_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner, "_build_context", lambda *_a, **_k: object())
    monkeypatch.setattr(
        runner,
        "_create_openai_client",
        lambda _key: pytest.fail("retired command constructed a provider client"),
    )
    assert runner.main(
        [
            "calibration-generate",
            "--authorize-openai-calibration-generation",
            "--max-cost-usd",
            "4",
        ]
    ) == 1


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
        items=tuple(
            SimpleNamespace(item_id=item_id) for item_id in context.calibration_ids
        )
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
        item
        for item in context.gold_items
        if item["id"] not in context.calibration_ids
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
    assert client.observations == [
        runner._ProviderObservation("resp_raw", runner.JUDGE_MODEL)
    ]


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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("owner label is incomplete")
        ),
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
        client.observations.append(
            runner._ProviderObservation(response_id, runner.JUDGE_MODEL)
        )
        evidence_inputs.append((claim, dict(source_texts)))
        return SimpleNamespace(
            parsed=runner.ClaimEvidenceVerdict.model_validate(
                {
                    "claim_id": claim.claim_id,
                    "faithfulness": "supported",
                    "source_verdicts": [
                        {"source_number": 1, "label": "supported"}
                    ],
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
        client.observations.append(
            runner._ProviderObservation(response_id, runner.JUDGE_MODEL)
        )
        rubric_inputs.append(rubric)
        return SimpleNamespace(
            parsed=runner.ItemRubricVerdict.model_validate(
                {
                    "gold_claims": [
                        {"claim_id": item.claim_id, "status": "absent"}
                        for item in rubric.claims
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
    assert next(
        item for item in lock.dimensions if item.dimension.value == "claim_mapping"
    ).scoring_mode.value == "manual"
    assert lock.baseline_next_action == runner.NEXT_ACTION_BASELINE
    assert (
        f"OPTIONAL SCORING ACTION: {runner.NEXT_ACTION_BASELINE}"
        in capsys.readouterr().out
    )


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
        _generated_item(item, sequence)
        for sequence, item in enumerate(context.gold_items, start=1)
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
    calibration_generated = tuple(
        generated_by_id[item_id] for item_id in context.calibration_ids
    )
    calibration_decomposed = tuple(
        decomposed_by_id[item_id] for item_id in context.calibration_ids
    )
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
                SimpleNamespace(response_id=f"decomposition-{item.item_id}")
                for item in generated
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
        lambda *, decomposition, **_kwargs: SimpleNamespace(
            item_id=decomposition.item_id
        ),
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
        _generated_item(item, sequence)
        for sequence, item in enumerate(context.gold_items, start=1)
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
            tuple(
                item for item in generated if item.item_id in context.calibration_ids
            ),
            tuple(
                item
                for item in decompositions
                if item.item_id in context.calibration_ids
            ),
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
