"""Non-gold evaluation harness for generated-mode social conversation.

This module deliberately exercises only ``character_conversation``.  It never
loads the corpus, embeds a question, retrieves a passage, or sends manuscript
material to the provider.  Live execution is owned by the companion CLI and
requires an explicit authorization flag; unit tests inject a provider-free
generator.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from archivist_modes import (
    ArchivistMode,
    archivist_mode_definition,
    supported_generated_modes,
)
from character_conversation import (
    CHARACTER_CONVERSATION_OUTPUT_SCHEMA,
    CHARACTER_CONVERSATION_POLICY_VERSION,
    CHARACTER_CONVERSATION_RENDERER_VERSION,
    CHARACTER_CONVERSATION_SETTINGS,
    MAX_CHARACTER_CONVERSATION_OUTPUT_TOKENS,
    CharacterConversationResponse,
    CharacterConversationResult,
    CharacterConversationStatus,
    build_character_conversation_input,
    build_character_conversation_instructions,
    character_conversation_prompt_metadata,
    generate_character_conversation,
    is_character_conversation_question,
)
from costs import (
    UsageLedger,
    projected_provider_operation_cost_nano_usd,
    usage_scope,
)
from retrieval_authored_v3_evaluation import (
    EVALUATION_ID,
    MASTER_COST_CAP_NANO_USD,
    MASTER_COST_CAP_USD,
    MASTER_PROJECT_ID,
    MASTER_REQUEST_ID,
    default_paths,
)


PERSONA_EVALUATION_SCHEMA = "archivist.persona_evaluation_manifest/1"
PERSONA_AUTHORIZATION_SCHEMA = "archivist.persona_evaluation_authorization/1"
PERSONA_INTENT_SCHEMA = "archivist.persona_evaluation_intent/1"
PERSONA_OUTCOME_SCHEMA = "archivist.persona_evaluation_outcome/1"
PERSONA_REPORT_SCHEMA = "archivist.persona_evaluation_report/1"
PERSONA_EVALUATION_VERSION = "persona-conversation-evaluation-v1"

BASE_DIR = Path(__file__).resolve().parent.parent
SHARED_EVALUATION_ROOT = default_paths(BASE_DIR).root
DEFAULT_RUN_ROOT = SHARED_EVALUATION_ROOT / "conversational-persona"
DEFAULT_USAGE_DB = default_paths(BASE_DIR).ledger
PERSONA_CONVERSATION_ID = f"{EVALUATION_ID}-persona-evaluation"
MASTER_COST_CEILING_NANO_USD = MASTER_COST_CAP_NANO_USD
MASTER_COST_CEILING_USD = MASTER_COST_CAP_USD

_MANUSCRIPT_LEAD_RE = re.compile(
    r"\b(?:the\s+manuscript|cradle\s+of\s+the\s+empire)\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?", re.IGNORECASE)


class PersonaEvaluationError(RuntimeError):
    """The evaluator can no longer prove its fixed-call or artifact contract."""


@dataclass(frozen=True, slots=True)
class PersonaEvaluationCase:
    mode: ArchivistMode
    question: str


# Every item intentionally uses the same classifier-approved personal question.
# Keeping the wording identical makes cross-mode character distinctness easier
# to interpret. Do not turn these into historical prompts: this cohort measures
# the evidence-free character route, not RAG or factual answer quality.
PERSONA_EVALUATION_CASES = (
    PersonaEvaluationCase(
        mode=ArchivistMode.PROFESSIONAL,
        question="How are you?",
    ),
    PersonaEvaluationCase(
        mode=ArchivistMode.PRETTY_PINK_PRINCESS,
        question="How are you?",
    ),
    PersonaEvaluationCase(
        mode=ArchivistMode.BALEFUL_BLACK_BARON,
        question="How are you?",
    ),
    PersonaEvaluationCase(
        mode=ArchivistMode.EMBER_AND_INK,
        question="How are you?",
    ),
)

# These lexicons are transparent development diagnostics, not a gold rubric or
# semantic judge.  They report whether each reply contains at least one plainly
# mode-specific signal and whether all four replies remain lexically distinct.
PERSONA_SIGNATURES: Mapping[ArchivistMode, tuple[str, ...]] = {
    ArchivistMode.PROFESSIONAL: (
        "archive",
        "attentive",
        "curious",
        "historian",
        "research",
    ),
    ArchivistMode.PRETTY_PINK_PRINCESS: (
        "palace",
        "pink",
        "prince",
        "princess",
        "ribbon",
        "sparkle",
    ),
    ArchivistMode.BALEFUL_BLACK_BARON: (
        "baron",
        "bleak",
        "candle",
        "keep",
        "miserable",
        "raven",
    ),
    ArchivistMode.EMBER_AND_INK: (
        "alliance",
        "incentive",
        "leverage",
        "negotiat",
        "operational",
        "strategy",
        "timing",
        "tradeoff",
    ),
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sealed(value: Mapping[str, object]) -> dict[str, object]:
    payload = dict(value)
    payload.pop("artifact_sha256", None)
    payload["artifact_sha256"] = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return payload


def _validate_sealed(
    value: object,
    *,
    schema: str,
    label: str,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise PersonaEvaluationError(f"{label} must be a JSON object")
    payload = dict(value)
    if payload.get("schema") != schema:
        raise PersonaEvaluationError(f"{label} uses an unsupported schema")
    observed = payload.pop("artifact_sha256", None)
    expected = hashlib.sha256(_canonical_json(payload)).hexdigest()
    if observed != expected:
        raise PersonaEvaluationError(f"{label} hash no longer binds its contents")
    payload["artifact_sha256"] = observed
    return payload


def _read_json(path: Path, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PersonaEvaluationError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise PersonaEvaluationError(f"{label} must be a JSON object")
    return value


def _write_json_no_overwrite(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
    except FileExistsError as exc:
        raise PersonaEvaluationError(f"refusing to overwrite artifact: {path}") from exc


def _manifest_path(run_root: Path) -> Path:
    return run_root / "prepared-manifest.json"


def _authorization_path(run_root: Path) -> Path:
    return run_root / "authorization.json"


def _report_path(run_root: Path) -> Path:
    return run_root / "diagnostics-report.json"


def _item_root(run_root: Path, ordinal: int, mode: ArchivistMode) -> Path:
    return run_root / "attempts" / f"{ordinal:02d}-{mode.value}"


def _intent_path(run_root: Path, ordinal: int, mode: ArchivistMode) -> Path:
    return _item_root(run_root, ordinal, mode) / "intent.json"


def _outcome_path(run_root: Path, ordinal: int, mode: ArchivistMode) -> Path:
    return _item_root(run_root, ordinal, mode) / "outcome.json"


def _validate_paths(
    *,
    run_root: Path,
    usage_db: Path,
    evaluation_root: Path,
) -> tuple[Path, Path, Path]:
    selected_root = evaluation_root.resolve()
    selected_run = run_root.resolve()
    selected_usage = usage_db.resolve()
    if selected_run == selected_root or selected_root not in selected_run.parents:
        raise PersonaEvaluationError("run root must be a child of the shared evaluation root")
    if selected_usage != (selected_root / "usage.sqlite3").resolve():
        raise PersonaEvaluationError(
            "persona evaluation must use the shared retrieval-authored-v3 usage.sqlite3"
        )
    return selected_run, selected_usage, selected_root


def _provider_request(case: PersonaEvaluationCase) -> dict[str, object]:
    return {
        "instructions": build_character_conversation_instructions(case.mode),
        "input": build_character_conversation_input(
            question=case.question,
            mode=case.mode,
        ),
        "text_format": CharacterConversationResponse,
        "max_output_tokens": MAX_CHARACTER_CONVERSATION_OUTPUT_TOKENS,
        **CHARACTER_CONVERSATION_SETTINGS.responses_create_kwargs(),
    }


def build_prepared_manifest(
    *,
    run_root: Path = DEFAULT_RUN_ROOT,
    usage_db: Path = DEFAULT_USAGE_DB,
    evaluation_root: Path = SHARED_EVALUATION_ROOT,
) -> dict[str, object]:
    """Build a deterministic, provider-free manifest for the four fixed items."""

    selected_run, selected_usage, _selected_root = _validate_paths(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    expected_modes = tuple(case.mode for case in PERSONA_EVALUATION_CASES)
    if len(expected_modes) != len(set(expected_modes)):
        raise PersonaEvaluationError("persona evaluation contains a duplicate mode")
    if set(expected_modes) != set(supported_generated_modes()):
        raise PersonaEvaluationError(
            "persona evaluation cases must exactly cover the current generated-mode registry"
        )
    if set(PERSONA_SIGNATURES) != set(expected_modes):
        raise PersonaEvaluationError("persona signature diagnostics do not cover every item")

    items: list[dict[str, object]] = []
    for ordinal, case in enumerate(PERSONA_EVALUATION_CASES, start=1):
        if not is_character_conversation_question(case.question, case.mode):
            raise PersonaEvaluationError(
                f"{case.mode.value} prompt is not a high-confidence character-route turn"
            )
        request = _provider_request(case)
        projection = projected_provider_operation_cost_nano_usd(
            provider_kind="responses",
            request=request,
        )
        if projection <= 0 or projection > MASTER_COST_CEILING_NANO_USD:
            raise PersonaEvaluationError("persona call projection is outside the master cap")
        metadata = character_conversation_prompt_metadata(case.mode)
        items.append(
            {
                "ordinal": ordinal,
                "mode": case.mode.value,
                "mode_label": archivist_mode_definition(case.mode).label,
                "question": case.question,
                "question_sha256": _sha256_text(case.question),
                "turn_id": f"persona-{ordinal:02d}-{case.mode.value}",
                "route_classifier_eligible": True,
                "projected_cost_nano_usd": projection,
                "prompt_metadata": metadata,
            }
        )

    return _sealed(
        {
            "schema": PERSONA_EVALUATION_SCHEMA,
            "evaluation_version": PERSONA_EVALUATION_VERSION,
            "master_evaluation_id": EVALUATION_ID,
            "cohort_kind": "non_gold_conversational_persona",
            "formal_gold_or_rag_evidence": False,
            "run_root": str(selected_run),
            "usage_db": str(selected_usage),
            "master_request_id": MASTER_REQUEST_ID,
            "project_id": MASTER_PROJECT_ID,
            "conversation_id": PERSONA_CONVERSATION_ID,
            "master_cost_ceiling_nano_usd": MASTER_COST_CEILING_NANO_USD,
            "master_cost_ceiling_usd": f"{MASTER_COST_CEILING_USD:.2f}",
            "character_policy_version": CHARACTER_CONVERSATION_POLICY_VERSION,
            "renderer_version": CHARACTER_CONVERSATION_RENDERER_VERSION,
            "output_schema": CHARACTER_CONVERSATION_OUTPUT_SCHEMA,
            "model": CHARACTER_CONVERSATION_SETTINGS.model,
            "reasoning_effort": CHARACTER_CONVERSATION_SETTINGS.reasoning_effort,
            "verbosity": CHARACTER_CONVERSATION_SETTINGS.verbosity,
            "max_output_tokens": MAX_CHARACTER_CONVERSATION_OUTPUT_TOKENS,
            "expected_provider_calls": len(items),
            "automatic_retry_count": 0,
            "input_boundary": {
                "question_and_character_instructions_only": True,
                "history": False,
                "embedding": False,
                "retrieval": False,
                "manuscript": False,
                "evidence_dossier": False,
                "sources": False,
            },
            "items": items,
        }
    )


def prepare_evaluation(
    *,
    run_root: Path = DEFAULT_RUN_ROOT,
    usage_db: Path = DEFAULT_USAGE_DB,
    evaluation_root: Path = SHARED_EVALUATION_ROOT,
) -> dict[str, object]:
    expected = build_prepared_manifest(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    path = _manifest_path(run_root.resolve())
    if path.exists():
        observed = _validate_sealed(
            _read_json(path, label="prepared manifest"),
            schema=PERSONA_EVALUATION_SCHEMA,
            label="prepared manifest",
        )
        if observed != expected:
            raise PersonaEvaluationError("prepared manifest no longer matches current contracts")
        return observed
    if run_root.exists() and any(run_root.iterdir()):
        raise PersonaEvaluationError("prepare requires an absent or empty persona run root")
    _write_json_no_overwrite(path, expected)
    return expected


def load_prepared_manifest(
    *,
    run_root: Path = DEFAULT_RUN_ROOT,
    usage_db: Path = DEFAULT_USAGE_DB,
    evaluation_root: Path = SHARED_EVALUATION_ROOT,
) -> dict[str, object]:
    expected = build_prepared_manifest(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    observed = _validate_sealed(
        _read_json(_manifest_path(run_root.resolve()), label="prepared manifest"),
        schema=PERSONA_EVALUATION_SCHEMA,
        label="prepared manifest",
    )
    if observed != expected:
        raise PersonaEvaluationError("prepared manifest no longer matches current contracts")
    return observed


def _authorization(
    *,
    run_root: Path,
    manifest: Mapping[str, object],
    maximum_usd: Decimal,
) -> dict[str, object]:
    if maximum_usd != MASTER_COST_CEILING_USD:
        raise PersonaEvaluationError("--max-cost-usd must be exactly the shared $7.00 cap")
    expected = _sealed(
        {
            "schema": PERSONA_AUTHORIZATION_SCHEMA,
            "evaluation_version": PERSONA_EVALUATION_VERSION,
            "manifest_sha256": manifest["artifact_sha256"],
            "master_request_id": MASTER_REQUEST_ID,
            "shared_usage_db": manifest["usage_db"],
            "max_cost_usd": f"{maximum_usd:.2f}",
            "max_cost_nano_usd": MASTER_COST_CEILING_NANO_USD,
            "operation_scope": (
                "one no-retry gpt-5.6-sol character-conversation call for each untouched "
                "fixed persona item; no embeddings, retrieval, manuscript, or retries"
            ),
        }
    )
    path = _authorization_path(run_root)
    if path.exists():
        observed = _validate_sealed(
            _read_json(path, label="persona authorization"),
            schema=PERSONA_AUTHORIZATION_SCHEMA,
            label="persona authorization",
        )
        if observed != expected:
            raise PersonaEvaluationError("persona authorization changed after preparation")
        return observed
    _write_json_no_overwrite(path, expected)
    return expected


@contextmanager
def _shared_usage_database(path: Path) -> Iterator[None]:
    previous = os.environ.get("ARCHIVIST_USAGE_DB")
    os.environ["ARCHIVIST_USAGE_DB"] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("ARCHIVIST_USAGE_DB", None)
        else:
            os.environ["ARCHIVIST_USAGE_DB"] = previous


def _item_ledger_state(
    usage_db: Path,
    *,
    turn_id: str,
) -> dict[str, object]:
    with sqlite3.connect(usage_db) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT COUNT(*) AS event_count,
                   COALESCE(SUM(unpriced), 0) AS unpriced_count,
                   COALESCE(SUM(estimated_cost_nano_usd), 0) AS estimated_cost_nano_usd,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM usage_events
            WHERE request_id = ? AND project_id = ? AND conversation_id = ? AND turn_id = ?
            """,
            (
                MASTER_REQUEST_ID,
                MASTER_PROJECT_ID,
                PERSONA_CONVERSATION_ID,
                turn_id,
            ),
        ).fetchone()
        operation_rows = connection.execute(
            """
            SELECT operation, COUNT(*) AS event_count
            FROM usage_events
            WHERE request_id = ? AND project_id = ? AND conversation_id = ? AND turn_id = ?
            GROUP BY operation ORDER BY operation
            """,
            (
                MASTER_REQUEST_ID,
                MASTER_PROJECT_ID,
                PERSONA_CONVERSATION_ID,
                turn_id,
            ),
        ).fetchall()
    assert row is not None
    return {
        "event_count": int(row["event_count"]),
        "unpriced_count": int(row["unpriced_count"]),
        "estimated_cost_nano_usd": int(row["estimated_cost_nano_usd"]),
        "estimated_cost_usd_exact": (
            f"{Decimal(int(row['estimated_cost_nano_usd'])) / Decimal('1000000000'):.9f}"
        ),
        "input_tokens": int(row["input_tokens"]),
        "output_tokens": int(row["output_tokens"]),
        "reasoning_tokens": int(row["reasoning_tokens"]),
        "total_tokens": int(row["total_tokens"]),
        "operation_event_counts": {
            str(operation["operation"]): int(operation["event_count"])
            for operation in operation_rows
        },
    }


def _usage_is_one_character_call(value: Mapping[str, object]) -> bool:
    return (
        value.get("event_count") == 1
        and value.get("unpriced_count") == 0
        and value.get("operation_event_counts") == {"answer_generation": 1}
    )


def _manifest_items(manifest: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = manifest.get("items")
    if not isinstance(raw, list) or len(raw) != len(PERSONA_EVALUATION_CASES):
        raise PersonaEvaluationError("prepared manifest has an invalid item list")
    if not all(isinstance(item, Mapping) for item in raw):
        raise PersonaEvaluationError("prepared manifest items must be objects")
    return tuple(raw)  # type: ignore[return-value]


def _load_intent(path: Path) -> dict[str, object]:
    return _validate_sealed(
        _read_json(path, label="persona attempt intent"),
        schema=PERSONA_INTENT_SCHEMA,
        label="persona attempt intent",
    )


def _load_outcome(path: Path) -> dict[str, object]:
    return _validate_sealed(
        _read_json(path, label="persona attempt outcome"),
        schema=PERSONA_OUTCOME_SCHEMA,
        label="persona attempt outcome",
    )


def _validate_item_artifacts(
    *,
    manifest: Mapping[str, object],
    item: Mapping[str, object],
    intent: Mapping[str, object],
    outcome: Mapping[str, object] | None,
) -> None:
    shared = {
        "manifest_sha256": manifest["artifact_sha256"],
        "ordinal": item["ordinal"],
        "mode": item["mode"],
        "question_sha256": item["question_sha256"],
        "turn_id": item["turn_id"],
        "master_request_id": MASTER_REQUEST_ID,
    }
    if any(intent.get(key) != value for key, value in shared.items()):
        raise PersonaEvaluationError("persona intent no longer binds its prepared item")
    if outcome is not None:
        if any(outcome.get(key) != value for key, value in shared.items()):
            raise PersonaEvaluationError("persona outcome no longer binds its prepared item")
        if outcome.get("intent_sha256") != intent.get("artifact_sha256"):
            raise PersonaEvaluationError("persona outcome no longer binds its intent")


def _intent(
    *,
    manifest: Mapping[str, object],
    item: Mapping[str, object],
    master_state_before: Mapping[str, object],
) -> dict[str, object]:
    return _sealed(
        {
            "schema": PERSONA_INTENT_SCHEMA,
            "evaluation_version": PERSONA_EVALUATION_VERSION,
            "manifest_sha256": manifest["artifact_sha256"],
            "ordinal": item["ordinal"],
            "mode": item["mode"],
            "question_sha256": item["question_sha256"],
            "turn_id": item["turn_id"],
            "master_request_id": MASTER_REQUEST_ID,
            "projected_cost_nano_usd": item["projected_cost_nano_usd"],
            "master_cost_before_nano_usd": master_state_before[
                "estimated_cost_nano_usd"
            ],
            "automatic_retry_allowed": False,
        }
    )


def _followup_diagnostics(questions: Sequence[str]) -> dict[str, object]:
    individual = [
        {
            "ends_with_question_mark": question.endswith("?"),
            "mentions_manuscript": _MANUSCRIPT_LEAD_RE.search(question) is not None,
            "sha256": _sha256_text(question),
        }
        for question in questions
    ]
    return {
        "count": len(individual),
        "all_lead_to_manuscript": bool(individual)
        and all(
            value["ends_with_question_mark"] and value["mentions_manuscript"]
            for value in individual
        ),
        "questions": individual,
    }


def _outcome(
    *,
    manifest: Mapping[str, object],
    item: Mapping[str, object],
    intent: Mapping[str, object],
    status: str,
    latency_ms: float,
    usage: Mapping[str, object],
    result: CharacterConversationResult | None = None,
    error_class: str | None = None,
) -> dict[str, object]:
    failure_code = None
    if result is not None and result.failure_code is not None:
        failure_code = result.failure_code.value
    questions = () if result is None else result.follow_up_questions
    return _sealed(
        {
            "schema": PERSONA_OUTCOME_SCHEMA,
            "evaluation_version": PERSONA_EVALUATION_VERSION,
            "manifest_sha256": manifest["artifact_sha256"],
            "intent_sha256": intent["artifact_sha256"],
            "ordinal": item["ordinal"],
            "mode": item["mode"],
            "question_sha256": item["question_sha256"],
            "turn_id": item["turn_id"],
            "master_request_id": MASTER_REQUEST_ID,
            "status": status,
            "latency_ms": round(max(0.0, latency_ms), 3),
            "automatic_retry_count": 0,
            "usage": dict(usage),
            "failure_code": failure_code,
            "error_class": error_class,
            "answer": None if result is None else result.answer,
            "persona_reply": None if result is None else result.persona_reply,
            "follow_up_questions": list(questions),
            "follow_up_to_manuscript": _followup_diagnostics(questions),
        }
    )


def _words(value: str) -> frozenset[str]:
    return frozenset(token.casefold() for token in _TOKEN_RE.findall(value))


def _signature_hits(value: str, mode: ArchivistMode) -> tuple[str, ...]:
    normalized = value.casefold()
    return tuple(marker for marker in PERSONA_SIGNATURES[mode] if marker in normalized)


def _jaccard(left: str, right: str) -> float:
    left_words = _words(left)
    right_words = _words(right)
    union = left_words | right_words
    return 0.0 if not union else len(left_words & right_words) / len(union)


def build_diagnostics_report(
    *,
    manifest: Mapping[str, object],
    outcomes: Sequence[Mapping[str, object]],
    master_state: Mapping[str, object],
) -> dict[str, object]:
    if len(outcomes) != len(PERSONA_EVALUATION_CASES):
        raise PersonaEvaluationError("persona diagnostics require all four preserved outcomes")
    ordered = sorted(outcomes, key=lambda value: int(value["ordinal"]))
    replies = {
        ArchivistMode(str(outcome["mode"])): str(outcome.get("persona_reply") or "")
        for outcome in ordered
    }
    pairwise: list[dict[str, object]] = []
    max_similarity: dict[ArchivistMode, float] = {
        mode: 0.0 for mode in replies
    }
    reply_items = list(replies.items())
    for index, (left_mode, left_reply) in enumerate(reply_items):
        for right_mode, right_reply in reply_items[index + 1 :]:
            similarity = round(_jaccard(left_reply, right_reply), 6)
            pairwise.append(
                {
                    "left_mode": left_mode.value,
                    "right_mode": right_mode.value,
                    "token_jaccard": similarity,
                }
            )
            max_similarity[left_mode] = max(max_similarity[left_mode], similarity)
            max_similarity[right_mode] = max(max_similarity[right_mode], similarity)

    per_mode: list[dict[str, object]] = []
    for outcome in ordered:
        mode = ArchivistMode(str(outcome["mode"]))
        reply = replies[mode]
        own_hits = _signature_hits(reply, mode)
        foreign_hits = {
            foreign_mode.value: list(_signature_hits(reply, foreign_mode))
            for foreign_mode in PERSONA_SIGNATURES
            if foreign_mode is not mode and _signature_hits(reply, foreign_mode)
        }
        followup = outcome.get("follow_up_to_manuscript")
        followup_pass = bool(
            isinstance(followup, Mapping)
            and followup.get("all_lead_to_manuscript") is True
        )
        per_mode.append(
            {
                "ordinal": outcome["ordinal"],
                "mode": mode.value,
                "status": outcome["status"],
                "latency_ms": outcome["latency_ms"],
                "cost_nano_usd": outcome["usage"]["estimated_cost_nano_usd"],
                "cost_usd_exact": outcome["usage"]["estimated_cost_usd_exact"],
                "follow_up_to_manuscript": followup_pass,
                "own_signature_hits": list(own_hits),
                "foreign_signature_hits": foreign_hits,
                "max_pairwise_token_jaccard": max_similarity[mode],
                "persona_reply_sha256": _sha256_text(reply) if reply else None,
                "character_distinctness_signal": (
                    bool(own_hits) and max_similarity[mode] < 0.8
                ),
            }
        )

    status_counts = Counter(str(outcome["status"]) for outcome in ordered)
    latencies = [float(outcome["latency_ms"]) for outcome in ordered]
    cohort_cost = sum(
        int(outcome["usage"]["estimated_cost_nano_usd"]) for outcome in ordered
    )
    return _sealed(
        {
            "schema": PERSONA_REPORT_SCHEMA,
            "evaluation_version": PERSONA_EVALUATION_VERSION,
            "cohort_kind": "non_gold_conversational_persona",
            "formal_gold_or_rag_evidence": False,
            "manifest_sha256": manifest["artifact_sha256"],
            "master_request_id": MASTER_REQUEST_ID,
            "attempt_count": len(ordered),
            "automatic_retry_count": 0,
            "status_counts": dict(sorted(status_counts.items())),
            "latency_ms": {
                "median": round(median(latencies), 3),
                "maximum": round(max(latencies), 3),
            },
            "cohort_cost_nano_usd": cohort_cost,
            "cohort_cost_usd_exact": (
                f"{Decimal(cohort_cost) / Decimal('1000000000'):.9f}"
            ),
            "master_ledger_cost_nano_usd_at_report": master_state[
                "estimated_cost_nano_usd"
            ],
            "master_cost_ceiling_nano_usd": MASTER_COST_CEILING_NANO_USD,
            "follow_up_to_manuscript_pass_count": sum(
                bool(value["follow_up_to_manuscript"]) for value in per_mode
            ),
            "all_persona_replies_unique": (
                len({_sha256_text(reply) for reply in replies.values() if reply})
                == len(replies)
                and all(bool(reply) for reply in replies.values())
            ),
            "character_distinctness_method": (
                "transparent mode-signature hits plus pairwise reply-token Jaccard; "
                "development diagnostic only, not a semantic judge or quality score"
            ),
            "character_distinctness_pass_count": sum(
                bool(value["character_distinctness_signal"]) for value in per_mode
            ),
            "pairwise_token_jaccard": pairwise,
            "modes": per_mode,
            "outcome_artifact_sha256": [
                outcome["artifact_sha256"] for outcome in ordered
            ],
        }
    )


def _load_completed_outcomes(
    *,
    run_root: Path,
    manifest: Mapping[str, object],
    usage_db: Path,
) -> list[dict[str, object]]:
    outcomes: list[dict[str, object]] = []
    for item in _manifest_items(manifest):
        mode = ArchivistMode(str(item["mode"]))
        intent_path = _intent_path(run_root, int(item["ordinal"]), mode)
        outcome_path = _outcome_path(run_root, int(item["ordinal"]), mode)
        if not intent_path.exists() and outcome_path.exists():
            raise PersonaEvaluationError("persona outcome exists without its earlier intent")
        if not outcome_path.exists():
            continue
        intent = _load_intent(intent_path)
        outcome = _load_outcome(outcome_path)
        _validate_item_artifacts(
            manifest=manifest,
            item=item,
            intent=intent,
            outcome=outcome,
        )
        if outcome.get("status") == "ambiguous_usage":
            raise PersonaEvaluationError(
                "an earlier persona attempt has unresolved usage; no later call is safe"
            )
        current_usage = _item_ledger_state(usage_db, turn_id=str(item["turn_id"]))
        if current_usage != outcome.get("usage"):
            raise PersonaEvaluationError("persona outcome no longer matches the shared ledger")
        outcomes.append(outcome)
    return outcomes


def run_evaluation(
    *,
    authorized: bool,
    maximum_usd: Decimal,
    client_factory: Callable[[], object],
    generator: Callable[..., CharacterConversationResult] = generate_character_conversation,
    run_root: Path = DEFAULT_RUN_ROOT,
    usage_db: Path = DEFAULT_USAGE_DB,
    evaluation_root: Path = SHARED_EVALUATION_ROOT,
) -> dict[str, object]:
    """Run only untouched persona items, never retrying or replaying an intent."""

    if not authorized:
        raise PersonaEvaluationError(
            "live persona evaluation requires --authorize-live-persona-evaluation"
        )
    if not isinstance(maximum_usd, Decimal) or not maximum_usd.is_finite():
        raise PersonaEvaluationError("--max-cost-usd must be a finite decimal")
    selected_run, selected_usage, _selected_root = _validate_paths(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    manifest = load_prepared_manifest(
        run_root=selected_run,
        usage_db=selected_usage,
        evaluation_root=evaluation_root,
    )
    _authorization(
        run_root=selected_run,
        manifest=manifest,
        maximum_usd=maximum_usd,
    )

    with _shared_usage_database(selected_usage):
        ledger = UsageLedger(selected_usage)
        outcomes = _load_completed_outcomes(
            run_root=selected_run,
            manifest=manifest,
            usage_db=selected_usage,
        )
        completed_ordinals = {int(outcome["ordinal"]) for outcome in outcomes}
        client: object | None = None

        for item in _manifest_items(manifest):
            ordinal = int(item["ordinal"])
            mode = ArchivistMode(str(item["mode"]))
            if ordinal in completed_ordinals:
                continue
            intent_path = _intent_path(selected_run, ordinal, mode)
            outcome_path = _outcome_path(selected_run, ordinal, mode)
            if intent_path.exists():
                intent = _load_intent(intent_path)
                _validate_item_artifacts(
                    manifest=manifest,
                    item=item,
                    intent=intent,
                    outcome=None,
                )
                raise PersonaEvaluationError(
                    f"{mode.value} has an unresolved intent; automatic replay is forbidden"
                )
            if outcome_path.exists():
                raise PersonaEvaluationError("persona outcome exists without its earlier intent")

            master_state = ledger.request_usage_cost_state(MASTER_REQUEST_ID)
            if int(master_state["unpriced_count"]) != 0:
                raise PersonaEvaluationError("shared master request contains unpriced usage")
            projected = int(item["projected_cost_nano_usd"])
            if (
                int(master_state["estimated_cost_nano_usd"]) + projected
                > MASTER_COST_CEILING_NANO_USD
            ):
                raise PersonaEvaluationError(
                    f"shared $7.00 cap has insufficient capacity for untouched {mode.value}"
                )

            intent = _intent(
                manifest=manifest,
                item=item,
                master_state_before=master_state,
            )
            _write_json_no_overwrite(intent_path, intent)
            if client is None:
                client = client_factory()

            started_ns = perf_counter_ns()
            result: CharacterConversationResult | None = None
            error: Exception | None = None
            try:
                with usage_scope(
                    project_id=MASTER_PROJECT_ID,
                    conversation_id=PERSONA_CONVERSATION_ID,
                    turn_id=str(item["turn_id"]),
                    request_id=MASTER_REQUEST_ID,
                    enforce_budget=True,
                    allow_over_budget=False,
                    request_cost_ceiling_nano_usd=MASTER_COST_CEILING_NANO_USD,
                ):
                    result = generator(
                        client,
                        question=str(item["question"]),
                        mode=mode,
                    )
            except Exception as exc:  # sealed below; never retried
                error = exc
            latency_ms = max(0, perf_counter_ns() - started_ns) / 1_000_000
            usage = _item_ledger_state(selected_usage, turn_id=str(item["turn_id"]))

            if not _usage_is_one_character_call(usage):
                outcome = _outcome(
                    manifest=manifest,
                    item=item,
                    intent=intent,
                    status="ambiguous_usage",
                    latency_ms=latency_ms,
                    usage=usage,
                    result=result,
                    error_class=type(error).__name__ if error is not None else None,
                )
                _write_json_no_overwrite(outcome_path, outcome)
                raise PersonaEvaluationError(
                    f"{mode.value} lacks exactly one priced answer_generation event; "
                    "no retry or later call was made"
                )

            if error is not None:
                outcome = _outcome(
                    manifest=manifest,
                    item=item,
                    intent=intent,
                    status="technical_failure",
                    latency_ms=latency_ms,
                    usage=usage,
                    error_class=type(error).__name__,
                )
            else:
                if not isinstance(result, CharacterConversationResult) or result.mode is not mode:
                    raise PersonaEvaluationError(
                        "character generator returned an incompatible local result"
                    )
                status = (
                    "generated"
                    if result.status is CharacterConversationStatus.GENERATED
                    else "local_fallback"
                )
                outcome = _outcome(
                    manifest=manifest,
                    item=item,
                    intent=intent,
                    status=status,
                    latency_ms=latency_ms,
                    usage=usage,
                    result=result,
                )
            _write_json_no_overwrite(outcome_path, outcome)
            outcomes.append(outcome)

        if len(outcomes) != len(PERSONA_EVALUATION_CASES):
            raise PersonaEvaluationError("persona evaluation did not preserve all four outcomes")
        master_state = ledger.request_usage_cost_state(MASTER_REQUEST_ID)
        report = build_diagnostics_report(
            manifest=manifest,
            outcomes=outcomes,
            master_state=master_state,
        )
        report_path = _report_path(selected_run)
        if report_path.exists():
            observed = _validate_sealed(
                _read_json(report_path, label="persona diagnostics report"),
                schema=PERSONA_REPORT_SCHEMA,
                label="persona diagnostics report",
            )
            # A shared ledger can acquire later events under the same master request.
            # The sealed report remains immutable; item-ledger bindings above still
            # prove the persona cohort's exact calls and costs.
            if observed.get("outcome_artifact_sha256") != report.get(
                "outcome_artifact_sha256"
            ):
                raise PersonaEvaluationError("persona report no longer binds its outcomes")
            return observed
        _write_json_no_overwrite(report_path, report)
        return report


def load_diagnostics_report(
    *,
    run_root: Path = DEFAULT_RUN_ROOT,
    usage_db: Path = DEFAULT_USAGE_DB,
    evaluation_root: Path = SHARED_EVALUATION_ROOT,
) -> dict[str, object]:
    selected_run, selected_usage, _selected_root = _validate_paths(
        run_root=run_root,
        usage_db=usage_db,
        evaluation_root=evaluation_root,
    )
    manifest = load_prepared_manifest(
        run_root=selected_run,
        usage_db=selected_usage,
        evaluation_root=evaluation_root,
    )
    outcomes = _load_completed_outcomes(
        run_root=selected_run,
        manifest=manifest,
        usage_db=selected_usage,
    )
    if len(outcomes) != len(PERSONA_EVALUATION_CASES):
        raise PersonaEvaluationError("persona evaluation is incomplete")
    report = _validate_sealed(
        _read_json(_report_path(selected_run), label="persona diagnostics report"),
        schema=PERSONA_REPORT_SCHEMA,
        label="persona diagnostics report",
    )
    if report.get("outcome_artifact_sha256") != [
        outcome["artifact_sha256"]
        for outcome in sorted(outcomes, key=lambda value: int(value["ordinal"]))
    ]:
        raise PersonaEvaluationError("persona report no longer binds its outcomes")
    return report


__all__ = [
    "DEFAULT_RUN_ROOT",
    "DEFAULT_USAGE_DB",
    "MASTER_COST_CEILING_NANO_USD",
    "MASTER_COST_CEILING_USD",
    "MASTER_PROJECT_ID",
    "MASTER_REQUEST_ID",
    "PERSONA_CONVERSATION_ID",
    "PERSONA_EVALUATION_CASES",
    "PERSONA_EVALUATION_SCHEMA",
    "PERSONA_EVALUATION_VERSION",
    "PERSONA_REPORT_SCHEMA",
    "SHARED_EVALUATION_ROOT",
    "PersonaEvaluationCase",
    "PersonaEvaluationError",
    "build_diagnostics_report",
    "build_prepared_manifest",
    "load_diagnostics_report",
    "load_prepared_manifest",
    "prepare_evaluation",
    "run_evaluation",
]
