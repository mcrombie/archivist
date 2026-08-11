#!/usr/bin/env python3
"""Prepare, run, and report Archivist's closed production performance cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

import httpx


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from costs import UsageLedger  # noqa: E402
from production_performance import (  # noqa: E402
    ATTEMPT_INTENT_SCHEMA,
    ATTEMPT_OUTCOME_SCHEMA,
    MINIMUM_START_INTERVAL_SECONDS,
    MAX_NEXT_ATTEMPT_COST_USD,
    PLANNED_ATTEMPT_COUNT,
    PRIVATE_SUMMARY_SCHEMA,
    PUBLIC_SUMMARY_SCHEMA,
    RUNTIME_SESSION_SCHEMA,
    REQUEST_TIMEOUT_SECONDS,
    ProductionPerformanceError,
    aggregate_summaries,
    build_attempt_intent,
    build_attempt_outcome,
    build_ambiguous_transport_outcome,
    build_prepared_manifest,
    build_runtime_session,
    load_prepared_manifest,
    normalize_usage_totals,
    parse_server_timing,
    public_report_markdown,
    read_json,
    request_payload,
    response_contract_projection,
    sealed_artifact,
    selected_items_from_manifest,
    validate_runtime_identity,
    validate_sealed_artifact,
    write_json_no_overwrite,
)


AUTHORIZATION_SCHEMA = "archivist.production_performance_authorization/2"
CANONICAL_GOLD_PATH = BASE_DIR / "fixtures" / "gold_set.json"
CANONICAL_PROVENANCE_PATH = BASE_DIR / "fixtures" / "gold_set.provenance.json"
CANONICAL_CORPUS_MANIFEST_PATH = BASE_DIR / "fixtures" / "corpus_manifest.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Closed, no-retry production performance cohort. No command makes a provider call "
            "unless the run subcommand receives the explicit authorization flag."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Create the offline prepared manifest.")
    _common_paths(prepare)
    prepare.add_argument("--run-root", type=Path, required=True)
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument(
        "--base-url",
        default="https://archivist.mcrombie.com",
        help="Canonical deployed HTTPS origin with no trailing slash.",
    )

    run = subparsers.add_parser(
        "run",
        help="Execute only untouched attempts against the deployed Complete endpoint.",
    )
    _common_paths(run)
    run.add_argument("--run-root", type=Path, required=True)
    run.add_argument("--usage-db", type=Path, required=True)
    run.add_argument(
        "--authorize-production-performance",
        action="store_true",
        help="Required acknowledgement that this subcommand makes paid production requests.",
    )
    run.add_argument(
        "--max-cost-usd",
        type=float,
        required=True,
        help="Finite positive owner-authorized ceiling for this cohort's request-scoped ledger.",
    )

    report = subparsers.add_parser(
        "report",
        help="Build private and public text-free reports entirely offline.",
    )
    _common_paths(report)
    report.add_argument("--run-root", type=Path, required=True)
    report.add_argument("--usage-db", type=Path, required=True)
    return parser


def _common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--gold", type=Path, default=CANONICAL_GOLD_PATH)
    parser.add_argument(
        "--provenance",
        type=Path,
        default=CANONICAL_PROVENANCE_PATH,
    )
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        default=CANONICAL_CORPUS_MANIFEST_PATH,
    )


def _validate_canonical_fixture_paths(args: argparse.Namespace) -> None:
    for label, observed, canonical in (
        ("gold set", args.gold, CANONICAL_GOLD_PATH),
        ("gold provenance", args.provenance, CANONICAL_PROVENANCE_PATH),
        ("corpus manifest", args.corpus_manifest, CANONICAL_CORPUS_MANIFEST_PATH),
    ):
        if observed.resolve() != canonical.resolve():
            raise ProductionPerformanceError(
                f"production performance requires the canonical committed {label}"
            )


def _manifest_path(run_root: Path) -> Path:
    return run_root / "prepared-manifest.json"


def _session_path(run_root: Path) -> Path:
    return run_root / "runtime-session.json"


def _authorization_path(run_root: Path) -> Path:
    return run_root / "authorization.json"


def _item_root(run_root: Path, ordinal: int) -> Path:
    return run_root / "attempts" / f"{ordinal:02d}"


def _intent_path(run_root: Path, ordinal: int) -> Path:
    return _item_root(run_root, ordinal) / "intent.json"


def _outcome_path(run_root: Path, ordinal: int) -> Path:
    return _item_root(run_root, ordinal) / "outcome.json"


def _load_intent(path: Path) -> dict[str, object]:
    return validate_sealed_artifact(
        read_json(path, label="attempt intent"),
        schema=ATTEMPT_INTENT_SCHEMA,
        label="attempt intent",
    )


def _load_outcome(path: Path) -> dict[str, object]:
    return validate_sealed_artifact(
        read_json(path, label="attempt outcome"),
        schema=ATTEMPT_OUTCOME_SCHEMA,
        label="attempt outcome",
    )


def _load_session(path: Path) -> dict[str, object]:
    return validate_sealed_artifact(
        read_json(path, label="runtime session"),
        schema=RUNTIME_SESSION_SCHEMA,
        label="runtime session",
    )


def _load_authorization(path: Path) -> dict[str, object]:
    return validate_sealed_artifact(
        read_json(path, label="authorization record"),
        schema=AUTHORIZATION_SCHEMA,
        label="authorization record",
    )


def _validate_authorization_binding(
    authorization: Mapping[str, object],
    *,
    manifest: Mapping[str, object],
) -> None:
    cost_contract = manifest.get("cost_contract")
    if not isinstance(cost_contract, Mapping):
        raise ProductionPerformanceError("prepared cost contract is unavailable")
    expected_next = cost_contract.get("max_next_attempt_cost_usd")
    expected_nano = cost_contract.get("public_rag_request_cost_ceiling_nano_usd")
    expected_version = cost_contract.get("public_rag_request_cost_ceiling_version")
    expected_enforcement = cost_contract.get("ceiling_enforcement")
    if (
        authorization.get("run_id") != manifest.get("run_id")
        or authorization.get("manifest_sha256") != manifest.get("artifact_sha256")
        or authorization.get("max_next_attempt_cost_usd") != expected_next
        or authorization.get("max_next_attempt_cost_nano_usd") != expected_nano
        or authorization.get("request_cost_ceiling_version") != expected_version
        or authorization.get("cost_ceiling_enforcement") != expected_enforcement
    ):
        raise ProductionPerformanceError("authorization does not bind this exact prepared cohort")
    maximum = authorization.get("max_cost_usd")
    if (
        not isinstance(maximum, (int, float))
        or isinstance(maximum, bool)
        or not math.isfinite(float(maximum))
        or not isinstance(expected_next, (int, float))
        or isinstance(expected_next, bool)
        or not math.isfinite(float(expected_next))
        or float(expected_next) != MAX_NEXT_ATTEMPT_COST_USD
        or float(maximum) < float(expected_next)
    ):
        raise ProductionPerformanceError("authorization cost ceiling is invalid")


def _validate_usage_db(path: Path) -> None:
    if not path.is_file():
        raise ProductionPerformanceError(
            "--usage-db must name the readable live production SQLite ledger; "
            "run this command where the Render disk is mounted"
        )
    try:
        with path.open("rb") as handle:
            handle.read(16)
    except OSError as exc:
        raise ProductionPerformanceError("production usage ledger is not readable") from exc


def _authorization(
    *,
    run_root: Path,
    manifest: Mapping[str, object],
    maximum: float,
) -> dict[str, object]:
    if not math.isfinite(maximum) or maximum <= 0:
        raise ProductionPerformanceError("--max-cost-usd must be a finite positive number")
    cost_contract = manifest.get("cost_contract")
    if not isinstance(cost_contract, Mapping):
        raise ProductionPerformanceError("prepared cost contract is unavailable")
    maximum_next = cost_contract.get("max_next_attempt_cost_usd")
    maximum_next_nano = cost_contract.get("public_rag_request_cost_ceiling_nano_usd")
    ceiling_version = cost_contract.get("public_rag_request_cost_ceiling_version")
    enforcement = cost_contract.get("ceiling_enforcement")
    if (
        not isinstance(maximum_next, (int, float))
        or isinstance(maximum_next, bool)
        or float(maximum_next) != MAX_NEXT_ATTEMPT_COST_USD
        or not isinstance(maximum_next_nano, int)
        or isinstance(maximum_next_nano, bool)
        or maximum_next_nano <= 0
        or not isinstance(ceiling_version, str)
        or not ceiling_version
        or not isinstance(enforcement, str)
        or not enforcement
    ):
        raise ProductionPerformanceError("prepared request-cost ceiling contract is invalid")
    if maximum < float(maximum_next):
        raise ProductionPerformanceError(
            f"--max-cost-usd must be at least the server-enforced ${float(maximum_next):.2f} "
            "maximum for one next attempt"
        )
    expected = sealed_artifact(
        {
            "schema": AUTHORIZATION_SCHEMA,
            "run_id": manifest["run_id"],
            "manifest_sha256": manifest["artifact_sha256"],
            "max_cost_usd": round(maximum, 9),
            "max_next_attempt_cost_usd": float(maximum_next),
            "max_next_attempt_cost_nano_usd": maximum_next_nano,
            "request_cost_ceiling_version": ceiling_version,
            "cost_ceiling_enforcement": enforcement,
            "operation_scope": (
                "exactly one Complete public POST for each still-untouched planned item; "
                "no retries or replacements"
            ),
        }
    )
    path = _authorization_path(run_root)
    if path.exists():
        observed = _load_authorization(path)
        if observed != expected:
            raise ProductionPerformanceError(
                "authorization ceiling or scope changed after the cohort began"
            )
        _validate_authorization_binding(observed, manifest=manifest)
        return observed
    write_json_no_overwrite(path, expected)
    _validate_authorization_binding(expected, manifest=manifest)
    return expected


def prepare(args: argparse.Namespace) -> int:
    _validate_canonical_fixture_paths(args)
    run_root = args.run_root.resolve()
    if run_root.exists() and any(run_root.iterdir()):
        raise ProductionPerformanceError("prepare requires an absent or empty run root")
    manifest, _items = build_prepared_manifest(
        repository_root=BASE_DIR,
        run_id=args.run_id,
        base_url=args.base_url,
        gold_path=args.gold.resolve(),
        provenance_path=args.provenance.resolve(),
        corpus_manifest_path=args.corpus_manifest.resolve(),
    )
    write_json_no_overwrite(_manifest_path(run_root), manifest)
    print(f"Prepared closed {PLANNED_ATTEMPT_COUNT}-attempt cohort: {_manifest_path(run_root)}")
    print("No network request or paid provider operation was made.")
    return 0


def _header(response: httpx.Response, name: str) -> str | None:
    value = response.headers.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _json_or_none(response: httpx.Response) -> object:
    try:
        return response.json()
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None


def _health_observation(response: httpx.Response) -> dict[str, object]:
    payload = _json_or_none(response)
    body_status = payload.get("status") if isinstance(payload, Mapping) else None
    return {
        "status": response.status_code,
        "body_status": body_status,
        "deployment_commit": _header(response, "X-Archivist-Commit"),
        "process_epoch": _header(response, "X-Archivist-Process-Epoch"),
    }


def _establish_session(
    *,
    client: httpx.Client,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    base_url = str(manifest["base_url"])
    health_responses = [
        client.get(base_url + str(manifest["health_path"])),
        client.get(base_url + str(manifest["health_path"])),
    ]
    version_response = client.get(base_url + str(manifest["version_path"]))
    if version_response.status_code != 200:
        raise ProductionPerformanceError("/api/version was not available on the deployment")
    identity = validate_runtime_identity(_json_or_none(version_response), manifest=manifest)
    version_epoch = _header(version_response, "X-Archivist-Process-Epoch")
    version_commit = _header(version_response, "X-Archivist-Commit")
    if version_epoch != identity["process_epoch"] or version_commit != identity["deployment_commit"]:
        raise ProductionPerformanceError("version response headers do not bind its identity body")
    observations = [_health_observation(response) for response in health_responses]
    return build_runtime_session(
        manifest=manifest,
        identity=identity,
        health_observations=observations,
    )


def _scoped_usage(
    ledger: UsageLedger,
    outcomes: Sequence[Mapping[str, object]],
) -> tuple[float, int, int]:
    cost = 0.0
    events = 0
    unavailable = 0
    seen: set[str] = set()
    for outcome in outcomes:
        measurement_status = outcome.get("usage_measurement_status")
        request_id = outcome.get("request_id")
        if measurement_status == "unavailable_ambiguous_transport":
            if request_id is not None or outcome.get("usage_totals") is not None:
                raise ProductionPerformanceError(
                    "ambiguous outcome makes an unsupported zero-usage assertion"
                )
            unavailable += 1
            continue
        if measurement_status != "recorded":
            raise ProductionPerformanceError("terminal outcome has unknown usage status")
        if not isinstance(request_id, str) or not request_id or request_id in seen:
            raise ProductionPerformanceError("terminal outcomes have invalid request correlation")
        seen.add(request_id)
        totals = normalize_usage_totals(ledger.request_usage_totals(request_id))
        if totals["unpriced_event_count"]:
            raise ProductionPerformanceError("cohort contains an unpriced usage event")
        persisted = outcome.get("usage_totals")
        if persisted != totals:
            raise ProductionPerformanceError("request-scoped usage changed after it was sealed")
        cost += float(totals["estimated_cost_usd"])
        events += int(totals["event_count"])
    return cost, events, unavailable


def _authorization_accounted_usage(
    ledger: UsageLedger,
    outcomes: Sequence[Mapping[str, object]],
    *,
    authorization: Mapping[str, object],
) -> tuple[float, float, int, int]:
    """Return recorded and conservative cap-accounted cohort usage.

    A terminal ambiguous transport outcome has no request ID and therefore no
    defensible exact spend measurement.  It permanently consumes the public
    application's enforced per-request maximum in authorization accounting.
    """

    recorded, events, unavailable = _scoped_usage(ledger, outcomes)
    maximum_next = authorization.get("max_next_attempt_cost_usd")
    maximum = authorization.get("max_cost_usd")
    if (
        not isinstance(maximum_next, (int, float))
        or isinstance(maximum_next, bool)
        or not math.isfinite(float(maximum_next))
        or float(maximum_next) <= 0
        or not isinstance(maximum, (int, float))
        or isinstance(maximum, bool)
        or not math.isfinite(float(maximum))
        or float(maximum) <= 0
    ):
        raise ProductionPerformanceError("authorization cost contract is invalid")
    for outcome in outcomes:
        usage = outcome.get("usage_totals")
        if not isinstance(usage, Mapping):
            continue
        cost = usage.get("estimated_cost_usd")
        if (
            not isinstance(cost, (int, float))
            or isinstance(cost, bool)
            or float(cost) > float(maximum_next) + 1e-12
        ):
            raise ProductionPerformanceError(
                "recorded request spend exceeds the deployed per-request ceiling"
            )
    accounted = recorded + unavailable * float(maximum_next)
    if accounted > float(maximum) + 1e-12:
        raise ProductionPerformanceError(
            "conservative cohort cost accounting exceeds authorization"
        )
    return recorded, accounted, events, unavailable


def _require_next_attempt_capacity(
    *,
    recorded_cost_usd: float,
    accounted_cost_usd: float,
    unavailable_attempts: int,
    authorization: Mapping[str, object],
) -> None:
    maximum = float(authorization["max_cost_usd"])
    maximum_next = float(authorization["max_next_attempt_cost_usd"])
    if accounted_cost_usd + maximum_next > maximum + 1e-12:
        raise ProductionPerformanceError(
            f"next attempt requires the server-enforced ${maximum_next:.2f} maximum; "
            f"conservative accounted spend is ${accounted_cost_usd:.6f} "
            f"(${recorded_cost_usd:.6f} recorded; {unavailable_attempts} unknown) "
            f"against ${maximum:.2f}"
        )


def _validate_observation(
    observation: object,
    *,
    intent: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(observation, Mapping):
        raise ProductionPerformanceError("terminal server observation is unavailable")
    value = dict(observation)
    required = {
        "schema",
        "request_id",
        "recorded_at",
        "deployment_commit",
        "process_epoch",
        "render_instance_id",
        "route",
        "delivery",
        "conversation_id",
        "turn_id",
        "archivist_mode",
        "answer_strategy",
        "http_status",
        "duration_ms",
    }
    if set(value) != required or value.get("schema") != "archivist.public_request_observation/1":
        raise ProductionPerformanceError("server observation uses an unsupported schema")
    request_id = value.get("request_id")
    if (
        not isinstance(request_id, str)
        or len(request_id) != 32
        or any(character not in "0123456789abcdef" for character in request_id)
    ):
        raise ProductionPerformanceError("server observation request ID is invalid")
    if value.get("conversation_id") != intent.get("conversation_id"):
        raise ProductionPerformanceError("server observation conversation binding changed")
    if value.get("turn_id") != intent.get("turn_id"):
        raise ProductionPerformanceError("server observation turn binding changed")
    recorded_at = value.get("recorded_at")
    started_at = intent.get("started_at")
    try:
        recorded_time = datetime.fromisoformat(str(recorded_at))
        started_time = datetime.fromisoformat(str(started_at))
    except ValueError as exc:
        raise ProductionPerformanceError("server observation timestamp is invalid") from exc
    if recorded_time.tzinfo is None or started_time.tzinfo is None:
        raise ProductionPerformanceError("server observation timestamp has no timezone")
    if recorded_time.astimezone(timezone.utc) < started_time.astimezone(timezone.utc):
        raise ProductionPerformanceError("server observation predates the persisted intent")
    if (
        value.get("route") != "question"
        or value.get("delivery") != "complete"
        or value.get("answer_strategy") != "rag"
    ):
        raise ProductionPerformanceError("server observation did not measure Complete RAG")
    if value.get("archivist_mode") != "essential":
        raise ProductionPerformanceError("server observation did not measure Essential mode")
    status = value.get("http_status")
    duration = value.get("duration_ms")
    if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
        raise ProductionPerformanceError("server observation HTTP status is invalid")
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or not math.isfinite(float(duration))
        or float(duration) < 0
    ):
        raise ProductionPerformanceError("server observation duration is invalid")
    return value


def _wait_for_observation(
    ledger: UsageLedger,
    *,
    request_id: str | None = None,
    conversation_id: str | None = None,
    turn_id: str | None = None,
    recorded_at_gte: str | None = None,
    attempts: int = 10,
    delay_seconds: float = 0.1,
) -> dict[str, object] | None:
    """Poll only the local SQLite ledger; this never repeats a public request."""

    for index in range(attempts):
        if request_id is not None:
            value = ledger.get_public_request_observation(request_id)
        elif conversation_id is not None and turn_id is not None:
            value = ledger.find_public_request_observation(
                conversation_id=conversation_id,
                turn_id=turn_id,
                recorded_at_gte=recorded_at_gte,
            )
        else:
            raise ValueError("observation lookup requires request or scope identity")
        if value is not None:
            return value
        if index + 1 < attempts:
            time.sleep(delay_seconds)
    return None


def _recover_intent(
    *,
    run_root: Path,
    manifest: Mapping[str, object],
    session: Mapping[str, object],
    intent: Mapping[str, object],
    ledger: UsageLedger,
    ambiguous_failure_code: str = "missing_server_observation",
    client_duration_ms: float | None = None,
) -> dict[str, object]:
    observation = _wait_for_observation(
        ledger,
        conversation_id=str(intent["conversation_id"]),
        turn_id=str(intent["turn_id"]),
        recorded_at_gte=str(intent["started_at"]),
    )
    if observation is None:
        stale = ledger.find_public_request_observation(
            conversation_id=str(intent["conversation_id"]),
            turn_id=str(intent["turn_id"]),
        )
        outcome = build_ambiguous_transport_outcome(
            manifest=manifest,
            session=session,
            intent=intent,
            failure_code=(
                "stale_scope_observation" if stale is not None else ambiguous_failure_code
            ),
            client_duration_ms=client_duration_ms,
        )
        write_json_no_overwrite(
            _outcome_path(run_root, int(intent["ordinal"])),
            outcome,
        )
        raise ProductionPerformanceError(
            "ambiguous client transport outcome was sealed without a zero-spend claim or "
            "replay; this invocation stopped before any later POST"
        )
    observation = _validate_observation(observation, intent=intent)
    request_id = str(observation["request_id"])
    diagnostics = ledger.get_answer_run_diagnostics_by_request_id(request_id)
    totals = normalize_usage_totals(ledger.request_usage_totals(request_id))
    outcome = build_attempt_outcome(
        manifest=manifest,
        intent=intent,
        request_id=request_id,
        http_status=int(observation["http_status"]),
        response_contract_valid=False,
        response_error_code="client_completion_unobserved",
        answer_status=(
            str(diagnostics.get("answer_status"))
            if isinstance(diagnostics, Mapping) and diagnostics.get("answer_status") is not None
            else None
        ),
        response_payload_sha256=None,
        client_duration_ms=client_duration_ms,
        header_duration_ms=None,
        header_commit=(
            str(observation["deployment_commit"])
            if observation.get("deployment_commit") is not None
            else None
        ),
        header_process_epoch=str(observation["process_epoch"]),
        observation=observation,
        diagnostics=diagnostics,
        usage_totals=totals,
        recovered_without_replay=True,
    )
    write_json_no_overwrite(
        _outcome_path(run_root, int(intent["ordinal"])),
        outcome,
    )
    return outcome


def _terminal_state(
    *,
    run_root: Path,
    manifest: Mapping[str, object],
    session: Mapping[str, object] | None,
    ledger: UsageLedger,
) -> list[dict[str, object]]:
    unresolved = [
        ordinal
        for ordinal in range(1, PLANNED_ATTEMPT_COUNT + 1)
        if _intent_path(run_root, ordinal).exists()
        and not _outcome_path(run_root, ordinal).exists()
    ]
    if len(unresolved) > 1:
        raise ProductionPerformanceError(
            "multiple unresolved intents violate sequential no-retry execution"
        )
    outcomes: list[dict[str, object]] = []
    found_untouched = False
    for ordinal in range(1, PLANNED_ATTEMPT_COUNT + 1):
        outcome_path = _outcome_path(run_root, ordinal)
        intent_path = _intent_path(run_root, ordinal)
        if outcome_path.exists():
            if found_untouched:
                raise ProductionPerformanceError(
                    "terminal outcomes are not a contiguous sequential prefix"
                )
            outcome = _load_outcome(outcome_path)
            if not intent_path.exists():
                raise ProductionPerformanceError("outcome exists without its earlier intent")
            intent = _load_intent(intent_path)
            if outcome.get("intent_sha256") != intent.get("artifact_sha256"):
                raise ProductionPerformanceError("outcome no longer binds its attempt intent")
            outcomes.append(outcome)
            continue
        if intent_path.exists():
            if found_untouched:
                raise ProductionPerformanceError(
                    "attempt intent appears after an untouched earlier ordinal"
                )
            if session is None:
                raise ProductionPerformanceError("attempt intent exists without a runtime session")
            intent = _load_intent(intent_path)
            outcomes.append(
                _recover_intent(
                    run_root=run_root,
                    manifest=manifest,
                    session=session,
                    intent=intent,
                    ledger=ledger,
                )
            )
            # Sequential execution means a later intent is impossible until this
            # one is reconciled. Continue only after it is sealed without replay.
            continue
        found_untouched = True
    return outcomes


def _assert_session_boundary(
    outcomes: Sequence[Mapping[str, object]],
    *,
    session: Mapping[str, object] | None,
) -> None:
    if outcomes and session is None:
        raise ProductionPerformanceError("terminal attempts exist without a runtime session")
    if session is None:
        return
    for outcome in outcomes:
        failures = outcome.get("instrumentation_failures")
        failure_codes = set(failures) if isinstance(failures, list) else set()
        if (
            outcome.get("process_epoch") != session.get("process_epoch")
            or outcome.get("deployment_commit") != session.get("deployment_commit")
            or "process_epoch_header_mismatch" in failure_codes
            or "deployment_commit_header_mismatch" in failure_codes
        ):
            raise ProductionPerformanceError(
                "a sealed attempt crossed the warmed process/deploy boundary; cohort stopped"
            )


def _seconds_until_start_allowed(run_root: Path) -> float:
    started: list[datetime] = []
    for path in sorted((run_root / "attempts").glob("*/intent.json")):
        intent = _load_intent(path)
        raw = intent.get("started_at")
        if not isinstance(raw, str):
            raise ProductionPerformanceError("attempt intent has no start timestamp")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ProductionPerformanceError("attempt intent start timestamp is invalid") from exc
        if parsed.tzinfo is None:
            raise ProductionPerformanceError("attempt intent start timestamp has no timezone")
        started.append(parsed.astimezone(timezone.utc))
    if not started:
        return 0.0
    elapsed = (datetime.now(timezone.utc) - max(started)).total_seconds()
    return max(0.0, MINIMUM_START_INTERVAL_SECONDS - elapsed)


def _transport_failure_code(error: httpx.HTTPError) -> str:
    """Map a client exception to one closed, text-free operational code."""

    if isinstance(error, httpx.TimeoutException):
        return "client_timeout"
    if isinstance(error, httpx.ConnectError):
        return "client_connect_error"
    if isinstance(error, (httpx.LocalProtocolError, httpx.RemoteProtocolError)):
        return "client_protocol_error"
    if isinstance(error, httpx.TransportError):
        return "client_transport_error"
    return "client_transport_error"


def _post_one(
    *,
    client: httpx.Client,
    run_root: Path,
    manifest: Mapping[str, object],
    session: Mapping[str, object],
    item,
    ledger: UsageLedger,
) -> dict[str, object]:
    remaining_wait = _seconds_until_start_allowed(run_root)
    if remaining_wait:
        time.sleep(remaining_wait)
    stale_observation = ledger.find_public_request_observation(
        conversation_id=item.conversation_id,
        turn_id=item.turn_id,
    )
    if stale_observation is not None:
        raise ProductionPerformanceError(
            "the prepared conversation/turn scope already exists in the production ledger; "
            "no intent or POST was created"
        )
    intent = build_attempt_intent(manifest=manifest, item=item)
    write_json_no_overwrite(_intent_path(run_root, item.ordinal), intent)

    started_ns = time.perf_counter_ns()
    try:
        response = client.post(
            str(manifest["base_url"]) + str(manifest["question_path"]),
            json=request_payload(item),
        )
    except httpx.HTTPError as exc:
        client_ms = round(max(0, time.perf_counter_ns() - started_ns) / 1_000_000, 3)
        return _recover_intent(
            run_root=run_root,
            manifest=manifest,
            session=session,
            intent=intent,
            ledger=ledger,
            ambiguous_failure_code=_transport_failure_code(exc),
            client_duration_ms=client_ms,
        )
    client_ms = round(max(0, time.perf_counter_ns() - started_ns) / 1_000_000, 3)

    request_id = _header(response, "X-Request-ID")
    if request_id is None:
        return _recover_intent(
            run_root=run_root,
            manifest=manifest,
            session=session,
            intent=intent,
            ledger=ledger,
            ambiguous_failure_code="missing_request_correlation",
            client_duration_ms=client_ms,
        )
    observation = _wait_for_observation(ledger, request_id=request_id)
    if observation is None:
        return _recover_intent(
            run_root=run_root,
            manifest=manifest,
            session=session,
            intent=intent,
            ledger=ledger,
            ambiguous_failure_code="missing_server_observation",
            client_duration_ms=client_ms,
        )
    observation = _validate_observation(observation, intent=intent)
    diagnostics = ledger.get_answer_run_diagnostics_by_request_id(request_id)
    totals = normalize_usage_totals(ledger.request_usage_totals(request_id))
    payload = _json_or_none(response)
    contract_valid, error_code, answer_status = response_contract_projection(
        http_status=response.status_code,
        payload=payload,
    )
    outcome = build_attempt_outcome(
        manifest=manifest,
        intent=intent,
        request_id=request_id,
        http_status=response.status_code,
        response_contract_valid=contract_valid,
        response_error_code=error_code,
        answer_status=answer_status,
        response_payload_sha256=hashlib.sha256(response.content).hexdigest(),
        client_duration_ms=client_ms,
        header_duration_ms=parse_server_timing(_header(response, "Server-Timing")),
        header_commit=_header(response, "X-Archivist-Commit"),
        header_process_epoch=_header(response, "X-Archivist-Process-Epoch"),
        observation=observation,
        diagnostics=diagnostics,
        usage_totals=totals,
    )
    write_json_no_overwrite(_outcome_path(run_root, item.ordinal), outcome)
    return outcome


def run(
    args: argparse.Namespace,
    *,
    client_factory: Callable[..., httpx.Client] = httpx.Client,
) -> int:
    if not args.authorize_production_performance:
        raise ProductionPerformanceError(
            "run requires --authorize-production-performance because it makes paid live requests"
        )
    _validate_canonical_fixture_paths(args)
    _validate_usage_db(args.usage_db)
    manifest = load_prepared_manifest(_manifest_path(args.run_root))
    items = selected_items_from_manifest(
        manifest,
        gold_path=args.gold,
        provenance_path=args.provenance,
        corpus_manifest_path=args.corpus_manifest,
    )
    authorization = _authorization(
        run_root=args.run_root,
        manifest=manifest,
        maximum=args.max_cost_usd,
    )
    ledger = UsageLedger(args.usage_db)
    session = _load_session(_session_path(args.run_root)) if _session_path(args.run_root).exists() else None
    outcomes = _terminal_state(
        run_root=args.run_root,
        manifest=manifest,
        session=session,
        ledger=ledger,
    )
    _assert_session_boundary(outcomes, session=session)
    if len(outcomes) == PLANNED_ATTEMPT_COUNT:
        _authorization_accounted_usage(
            ledger,
            outcomes,
            authorization=authorization,
        )
        print("All 33 planned attempts are already sealed; no network request was made.")
        return 0

    timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
    with client_factory(timeout=timeout, follow_redirects=False) as client:
        observed_session = _establish_session(client=client, manifest=manifest)
        if session is None:
            write_json_no_overwrite(_session_path(args.run_root), observed_session)
            session = observed_session
        elif (
            session.get("deployment_commit") != observed_session.get("deployment_commit")
            or session.get("process_epoch") != observed_session.get("process_epoch")
        ):
            raise ProductionPerformanceError(
                "resume crossed the prepared deployment or process epoch; no POST was made"
            )

        by_ordinal = {int(value["ordinal"]): value for value in outcomes}
        for item in items:
            if item.ordinal in by_ordinal:
                continue
            spend, accounted, _event_count, unavailable = _authorization_accounted_usage(
                ledger,
                list(by_ordinal.values()),
                authorization=authorization,
            )
            _require_next_attempt_capacity(
                recorded_cost_usd=spend,
                accounted_cost_usd=accounted,
                unavailable_attempts=unavailable,
                authorization=authorization,
            )
            outcome = _post_one(
                client=client,
                run_root=args.run_root,
                manifest=manifest,
                session=session,
                item=item,
                ledger=ledger,
            )
            by_ordinal[item.ordinal] = outcome
            _recorded, _accounted, _event_count, _unavailable = (
                _authorization_accounted_usage(
                    ledger,
                    list(by_ordinal.values()),
                    authorization=authorization,
                )
            )
            if (
                outcome.get("process_epoch") != session.get("process_epoch")
                or outcome.get("deployment_commit") != session.get("deployment_commit")
                or "process_epoch_header_mismatch"
                in outcome.get("instrumentation_failures", [])
                or "deployment_commit_header_mismatch"
                in outcome.get("instrumentation_failures", [])
            ):
                raise ProductionPerformanceError(
                    "attempt was sealed across a process/deploy boundary; cohort stopped"
                )

    print(f"Sealed {PLANNED_ATTEMPT_COUNT} sequential production attempts with no retries.")
    print("Run the report subcommand to emit text-free aggregate artifacts.")
    return 0


def _write_or_validate_json(
    path: Path,
    *,
    expected: Mapping[str, object],
    schema: str,
    label: str,
) -> None:
    if path.exists():
        observed = validate_sealed_artifact(
            read_json(path, label=label),
            schema=schema,
            label=label,
        )
        if observed != expected:
            raise ProductionPerformanceError(f"existing {label} differs from exact recomputation")
        return
    write_json_no_overwrite(path, expected)


def _write_or_validate_text(path: Path, *, expected: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != expected:
            raise ProductionPerformanceError("existing public report differs from recomputation")
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(expected)
    except FileExistsError as exc:
        raise ProductionPerformanceError("refusing to overwrite public report") from exc


def report(args: argparse.Namespace) -> int:
    _validate_canonical_fixture_paths(args)
    _validate_usage_db(args.usage_db)
    manifest = load_prepared_manifest(_manifest_path(args.run_root))
    # Revalidate the locked selection, but never send or print any item text.
    selected_items_from_manifest(
        manifest,
        gold_path=args.gold,
        provenance_path=args.provenance,
        corpus_manifest_path=args.corpus_manifest,
    )
    session = _load_session(_session_path(args.run_root))
    authorization = _load_authorization(_authorization_path(args.run_root))
    _validate_authorization_binding(authorization, manifest=manifest)
    outcomes = [
        _load_outcome(_outcome_path(args.run_root, ordinal))
        for ordinal in range(1, PLANNED_ATTEMPT_COUNT + 1)
    ]
    ledger = UsageLedger(args.usage_db)
    _authorization_accounted_usage(
        ledger,
        outcomes,
        authorization=authorization,
    )
    private, public = aggregate_summaries(
        manifest=manifest,
        session=session,
        authorization=authorization,
        outcomes=outcomes,
    )
    private_path = args.run_root / "private-summary.json"
    public_path = args.run_root / "public-summary.json"
    report_path = args.run_root / "public-report.md"
    _write_or_validate_json(
        private_path,
        expected=private,
        schema=PRIVATE_SUMMARY_SCHEMA,
        label="private summary",
    )
    _write_or_validate_json(
        public_path,
        expected=public,
        schema=PUBLIC_SUMMARY_SCHEMA,
        label="public summary",
    )
    markdown = public_report_markdown(public)
    _write_or_validate_text(report_path, expected=markdown)
    print(f"Private text-free summary: {private_path}")
    print(f"Public text-free summary: {public_path}")
    print(f"Public text-free report: {report_path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            return prepare(args)
        if args.command == "run":
            return run(args)
        if args.command == "report":
            return report(args)
    except ProductionPerformanceError as exc:
        print(f"Production performance protocol error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
