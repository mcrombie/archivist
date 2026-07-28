from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import web_api
from exposure_profile import ExposureConfigurationError, ExposureSettings
from public_request_gate import PublicRequestGate
from public_sources import (
    MAX_EXCERPT_CHARACTERS,
    MAX_EXCERPT_SOURCES,
    MAX_TOTAL_EXCERPT_CHARACTERS,
    answer_has_extended_verbatim_overlap,
    public_source_payload,
)
from web_project import source_payload


BASE_DIR = Path(__file__).resolve().parents[1]
LOCATOR_PATH = (
    BASE_DIR / "fixtures" / "edition_locators" / "typeset_pdf_0706.json"
)
MANIFEST_PATH = BASE_DIR / "fixtures" / "corpus_manifest.json"


def public_settings(**overrides) -> ExposureSettings:
    values = {
        "monthly_budget_usd": "5.00",
        "locator_artifact": LOCATOR_PATH,
    }
    values.update(overrides)
    return ExposureSettings.public_demo(**values)


def ready_config() -> dict[str, object]:
    return {
        "exposure_profile": "public_demo",
        "project": {
            "id": "current",
            "name": "Cradle of the Empire",
            "embedded": True,
            "embedded_chunks": 481,
        },
        "features": {
            "cost_ledger": False,
            "full_source_text": False,
            "local_tools": False,
            "public_page_locators": True,
        },
    }


def fixture_chunk_ids(count: int) -> list[str]:
    artifact = json.loads(LOCATOR_PATH.read_text(encoding="utf-8"))
    return [item["chunk_id"] for item in artifact["locators"][:count]]


def synthetic_chunks(count: int) -> list[dict[str, object]]:
    return [
        {
            "chunk_id": chunk_id,
            "chapter_title": f"Synthetic Chapter {index}",
            "text": (
                f"Alpha evidence {index} directly supports the requested historical claim. "
                f"Beta context {index} explains a related consequence without private prose."
            ),
        }
        for index, chunk_id in enumerate(fixture_chunk_ids(count), start=1)
    ]


def all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key
            for child in value.values()
            for key in all_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in all_keys(child)}
    return set()


def test_public_profile_requires_a_server_budget():
    try:
        ExposureSettings.from_env(
            {"ARCHIVIST_EXPOSURE_PROFILE": "public_demo"}
        )
    except ExposureConfigurationError as exc:
        assert "ARCHIVIST_PUBLIC_MONTHLY_BUDGET_USD" in str(exc)
    else:
        raise AssertionError("public mode started without a server budget")


def test_public_app_exposes_only_the_allowlisted_api(monkeypatch):
    monkeypatch.setattr(web_api, "_public_project_config", lambda _settings: ready_config())
    monkeypatch.setattr(
        web_api,
        "_run_public_question",
        lambda _request, _settings: {
            "answer": "Synthetic answer.",
            "answer_status": "answered",
            "historiographical_lens": "evidence_first",
            "voice": "scholarly",
            "worldview": "none",
            "source_schema": "archivist.public_sources/1",
            "sources": [],
        },
    )
    client = TestClient(web_api.create_app(public_settings()))

    assert client.get("/api/live").status_code == 200
    assert client.get("/api/health").status_code == 200
    config = client.get("/api/config")
    assert config.status_code == 200
    assert config.json()["features"]["full_source_text"] is False
    question_response = client.post(
        "/api/projects/current/question",
        json={"question": "What happened?"},
    )
    assert question_response.status_code == 200
    assert question_response.json()["answer"] == "Synthetic answer."
    assert "run_diagnostics" not in question_response.json()

    blocked = [
        ("GET", "/docs"),
        ("GET", "/redoc"),
        ("GET", "/openapi.json"),
        ("GET", "/api/projects"),
        ("GET", "/api/projects/current"),
        ("POST", "/api/projects"),
        ("POST", "/api/projects/current/embed"),
        ("POST", "/api/projects/current/index/entry"),
        ("GET", "/api/projects/current/index/search?term=test"),
        ("GET", "/api/projects/current/sources"),
        ("GET", "/api/projects/current/source-file/private.pdf"),
        ("GET", "/api/costs/summary"),
        ("PUT", "/api/costs/settings"),
        ("POST", "/api/projects/custom/question"),
        ("GET", "/api/not-a-route"),
    ]
    for method, path in blocked:
        assert client.request(method, path).status_code == 404, (method, path)


def test_public_request_rejects_client_tuning_and_budget_bypass(monkeypatch):
    monkeypatch.setattr(web_api, "_public_project_config", lambda _settings: ready_config())
    client = TestClient(web_api.create_app(public_settings()))

    for forbidden in ({"allow_over_budget": True}, {"n_results": 12}):
        response = client.post(
            "/api/projects/current/question",
            json={"question": "What happened?", **forbidden},
        )
        assert response.status_code == 422


def test_public_request_size_is_enforced_when_content_length_lies(monkeypatch):
    monkeypatch.setattr(web_api, "_public_project_config", lambda _settings: ready_config())
    client = TestClient(
        web_api.create_app(public_settings(max_request_bytes=400))
    )

    response = client.post(
        "/api/projects/current/question",
        content=json.dumps({"question": "x" * 500}),
        headers={
            "content-type": "application/json",
            "content-length": "1",
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_too_large"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_public_source_payload_preserves_numbers_and_bounds_excerpts():
    chunks = synthetic_chunks(5)
    answer = " ".join(
        f"Alpha evidence {number} supports this claim. [Source {number}]"
        for number in range(1, 6)
    )

    payload = public_source_payload(
        answer,
        chunks,
        locator_path=LOCATOR_PATH,
        manifest_path=MANIFEST_PATH,
    )
    sources = payload["sources"]

    assert [source["source_number"] for source in sources] == [1, 2, 3, 4, 5]
    assert sum("excerpt" in source for source in sources) == MAX_EXCERPT_SOURCES
    excerpts = [source["excerpt"] for source in sources if "excerpt" in source]
    assert all(len(excerpt) <= MAX_EXCERPT_CHARACTERS for excerpt in excerpts)
    assert sum(map(len, excerpts)) <= MAX_TOTAL_EXCERPT_CHARACTERS
    assert all(source["edition"]["name"].startswith("Typeset PDF") for source in sources)
    assert not {
        "text",
        "display_groups",
        "chunk_id",
        "chunk_ids",
        "paragraph_start",
        "paragraph_end",
        "physical_page_start",
        "physical_page_end",
    }.intersection(all_keys(payload))


def test_public_question_response_omits_internal_diagnostics_and_costs(monkeypatch):
    chunks = synthetic_chunks(2)

    class FakeLedger:
        def get_settings(self):
            return {
                "monthly_budget_usd": 5.0,
                "warning_threshold_percent": 80,
                "hard_limit_enabled": True,
            }

        def budget_state(self):
            return {"exceeded": False}

        def record_answer_run_diagnostics(self, **_kwargs):
            return None

    monkeypatch.setattr(web_api, "UsageLedger", FakeLedger)
    monkeypatch.setattr(web_api, "answer_run_diagnostics", lambda _result: {})
    monkeypatch.setattr(
        web_api,
        "answer_project_question_result",
        lambda *_args, **_kwargs: SimpleNamespace(
            answer=(
                "Alpha evidence 1 directly supports the requested historical claim. "
                "[Source 1]"
            ),
            final_chunks=chunks,
            status="answered",
        ),
    )
    response = web_api._run_public_question(
        web_api.PublicQuestionRequest(question="What happened?"),
        public_settings(),
    )

    assert response["answer_status"] == "answered"
    assert not {
        "text",
        "display_groups",
        "chunk_id",
        "chunk_ids",
        "run_diagnostics",
        "resolved_query",
        "costs",
        "budget",
    }.intersection(all_keys(response))


def test_public_answer_overlap_guard_detects_long_reproduction():
    repeated = " ".join(f"word{index}" for index in range(55))
    chunks = [{"text": repeated}]

    assert answer_has_extended_verbatim_overlap(repeated, chunks)
    assert not answer_has_extended_verbatim_overlap(
        "A short paraphrase of the evidence.",
        chunks,
    )


def test_public_gate_enforces_rate_and_concurrency_without_waiting():
    gate = PublicRequestGate(
        requests_per_minute=2,
        global_requests_per_minute=3,
        max_concurrent_requests=2,
        max_concurrent_per_client=1,
    )

    assert gate.try_enter("reader-a", now=100).allowed
    assert gate.try_enter("reader-a", now=101).reason == "client_concurrency_limit"
    assert gate.try_enter("reader-b", now=101).allowed
    assert gate.try_enter("reader-c", now=101).reason == "global_concurrency_limit"
    gate.leave("reader-a")
    gate.leave("reader-b")
    assert gate.try_enter("reader-a", now=102).allowed
    gate.leave("reader-a")
    assert gate.try_enter("reader-a", now=103).reason == "client_rate_limit"
    assert gate.try_enter("reader-c", now=161).allowed


def test_development_source_payload_still_contains_diagnostic_text():
    payload = source_payload(
        [
            {
                "chunk_id": "synthetic_001",
                "document": "Synthetic.md",
                "chapter_title": "Synthetic",
                "paragraph_start": 1,
                "paragraph_end": 4,
                "text": "Synthetic diagnostic text.",
            }
        ]
    )

    assert payload["sources"][0]["text"] == "Synthetic diagnostic text."
    assert payload["display_groups"][0]["text"] == "Synthetic diagnostic text."
