from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

import web_api
import web_project
from archivist_modes import ArchivistMode
from costs import CostLimitExceeded, UsageLedger, current_usage_context
from exposure_profile import ExposureConfigurationError, ExposureSettings
from public_request_gate import (
    DEFAULT_CATEGORY,
    FULL_CONTEXT_CATEGORY,
    PublicRequestGate,
)
from public_telemetry import validated_deployment_commit
from public_sources import (
    MAX_EXCERPT_CHARACTERS,
    MAX_EXCERPT_SOURCES,
    MAX_TOTAL_EXCERPT_CHARACTERS,
    answer_has_extended_verbatim_overlap,
    public_source_payload,
)
from perspectives import AnswerVoice, HistoriographicalLens, Worldview
from web_project import source_payload


BASE_DIR = Path(__file__).resolve().parents[1]
LOCATOR_PATH = BASE_DIR / "fixtures" / "edition_locators" / "typeset_pdf_0706.json"
MANIFEST_PATH = BASE_DIR / "fixtures" / "corpus_manifest.json"


@pytest.fixture(autouse=True)
def isolated_public_usage_ledger(request, monkeypatch):
    directory = Path("runtime") / "test-public-ledgers"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{request.node.name}.sqlite3"
    related_paths = [path, Path(f"{path}-wal"), Path(f"{path}-shm")]
    for related in related_paths:
        related.unlink(missing_ok=True)
    monkeypatch.setenv("ARCHIVIST_USAGE_DB", str(path))
    yield
    for related in related_paths:
        related.unlink(missing_ok=True)
    try:
        directory.rmdir()
    except OSError:
        pass


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
        return set(value) | {key for child in value.values() for key in all_keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in all_keys(child)}
    return set()


def test_public_profile_requires_a_server_budget():
    try:
        ExposureSettings.from_env({"ARCHIVIST_EXPOSURE_PROFILE": "public_demo"})
    except ExposureConfigurationError as exc:
        assert "ARCHIVIST_PUBLIC_MONTHLY_BUDGET_USD" in str(exc)
    else:
        raise AssertionError("public mode started without a server budget")


def test_deployment_commit_validation_never_masks_render_identity():
    assert (
        validated_deployment_commit(
            {
                "ARCHIVIST_DEPLOY_COMMIT": "invalid-local-override",
                "RENDER_GIT_COMMIT": "A" * 40,
            }
        )
        == "a" * 40
    )
    assert (
        validated_deployment_commit(
            {
                "ARCHIVIST_DEPLOY_COMMIT": "b" * 40,
                "RENDER_GIT_COMMIT": "c" * 40,
            }
        )
        == "c" * 40
    )
    assert (
        validated_deployment_commit(
            {
                "ARCHIVIST_DEPLOY_COMMIT": "d" * 40,
                "RENDER_GIT_COMMIT": "not-a-sha",
            }
        )
        is None
    )
    assert validated_deployment_commit({"ARCHIVIST_DEPLOY_COMMIT": "E" * 40}) == "e" * 40


def test_public_app_exposes_only_the_allowlisted_api(monkeypatch):
    monkeypatch.setattr(web_api, "_public_project_config", lambda _settings: ready_config())
    monkeypatch.setattr(
        web_api,
        "_run_public_question",
        lambda _request, _settings, **_kwargs: {
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


def test_public_complete_request_has_one_correlated_identity_and_observation(
    monkeypatch,
):
    deploy_commit = "a" * 40
    captured: dict[str, object] = {}
    monkeypatch.setenv("ARCHIVIST_DEPLOY_COMMIT", deploy_commit)
    monkeypatch.setattr(web_api, "_public_project_config", lambda _settings: ready_config())

    def fake_question(_request, _settings, **kwargs):
        captured.update(kwargs)
        captured["request_id"] = web_api._PUBLIC_REQUEST_ID.get()
        return {
            "answer": "Synthetic answer.",
            "answer_status": "answered",
            "source_schema": "archivist.public_sources/1",
            "sources": [],
        }

    monkeypatch.setattr(web_api, "_run_public_question", fake_question)
    client = TestClient(web_api.create_app(public_settings()))
    response = client.post(
        "/api/projects/current/question",
        json={
            "question": "What happened?",
            "conversation_id": "cohort-001",
            "turn_id": "turn-001",
            "archivist_mode": "essential",
            "answer_strategy": "rag",
        },
    )

    request_id = response.headers["x-request-id"]
    assert response.status_code == 200
    assert len(request_id) == 32
    assert captured["request_id"] == request_id
    assert response.headers["x-archivist-commit"] == deploy_commit
    assert response.headers["x-archivist-process-epoch"] == web_api.PROCESS_EPOCH
    assert response.headers["server-timing"].startswith("app;dur=")
    observation = UsageLedger().get_public_request_observation(request_id)
    assert observation is not None
    assert observation["conversation_id"] == "cohort-001"
    assert observation["turn_id"] == "turn-001"
    assert observation["delivery"] == "complete"
    assert observation["http_status"] == 200


def test_public_progressive_header_is_correlated_but_marked_ineligible(monkeypatch):
    observed: list[str | None] = []

    def fake_preflight(_request, _settings):
        observed.append(web_api._PUBLIC_REQUEST_ID.get())

    def fake_question(_request, _settings, **_kwargs):
        observed.append(web_api._PUBLIC_REQUEST_ID.get())
        return {
            "answer": "Synthetic answer.",
            "answer_status": "answered",
            "source_schema": "archivist.public_sources/1",
            "sources": [],
        }

    monkeypatch.setattr(web_api, "_preflight_public_progressive_question", fake_preflight)
    monkeypatch.setattr(web_api, "_run_public_question", fake_question)
    response = TestClient(web_api.create_app(public_settings())).post(
        "/api/projects/current/question/progressive",
        json={
            "question": "What happened?",
            "conversation_id": "progressive-conversation",
            "turn_id": "progressive-turn",
        },
    )

    request_id = response.headers["x-request-id"]
    assert response.status_code == 200
    assert observed == [request_id, request_id]
    assert response.headers["server-timing"].startswith("app_header;dur=")
    observation = UsageLedger().get_public_request_observation(request_id)
    assert observation is not None
    assert observation["route"] == "question_progressive"
    assert observation["delivery"] == "progressive_header"


def test_public_version_is_closed_text_free_and_bound_to_frozen_candidate(monkeypatch):
    monkeypatch.setenv("ARCHIVIST_DEPLOY_COMMIT", "b" * 40)
    monkeypatch.setattr(web_api, "_public_project_config", lambda _settings: ready_config())
    client = TestClient(web_api.create_app(public_settings()))

    response = client.get("/api/version")
    health = client.get("/api/health")
    payload = response.json()

    assert response.status_code == 200
    assert set(payload) == {
        "schema",
        "deployment_commit",
        "process_epoch",
        "answer_policy_version",
        "evidence_retrieval_kind",
        "embedding_model",
        "generated_prose_model",
        "corpus_manifest_sha256",
        "frozen_candidate_commit",
        "frozen_candidate_rag_policy",
        "public_rag_request_cost_ceiling_version",
        "public_rag_request_cost_ceiling_nano_usd",
    }
    assert payload["schema"] == "archivist.public_runtime_identity/4"
    assert payload["deployment_commit"] == "b" * 40
    assert payload["process_epoch"] == web_api.PROCESS_EPOCH
    assert payload["answer_policy_version"] == "retrieval-authored-v5"
    assert payload["evidence_retrieval_kind"] == "hybrid_bm25_rrf"
    assert payload["embedding_model"] == "text-embedding-3-small"
    assert payload["generated_prose_model"] == "gpt-5.6-sol"
    assert payload["public_rag_request_cost_ceiling_version"] == "public-rag-request-ceiling-v1"
    assert payload["public_rag_request_cost_ceiling_nano_usd"] == 2_000_000_000
    assert len(payload["corpus_manifest_sha256"]) == 64
    for identity_response in (response, health):
        assert identity_response.headers["x-archivist-commit"] == "b" * 40
        assert identity_response.headers["x-archivist-process-epoch"] == web_api.PROCESS_EPOCH
    assert not {
        "question",
        "answer",
        "source",
        "history",
        "passage",
    }.intersection(all_keys(payload))


def test_public_rag_reserves_full_request_before_answer_pipeline(monkeypatch):
    observed: list[tuple[int, str | None]] = []

    def reject_reservation(projected_cost_nano_usd, _ledger):
        observed.append((projected_cost_nano_usd, current_usage_context().request_id))
        raise CostLimitExceeded(
            {
                "hard_limit_enabled": True,
                "exceeded": False,
                "projected_exceeds_remaining": True,
            }
        )

    monkeypatch.setattr(web_api, "enforce_projected_usage_budget", reject_reservation)
    monkeypatch.setattr(
        web_api,
        "answer_project_question_result",
        lambda *_args, **_kwargs: pytest.fail("answer pipeline must not begin"),
    )
    request_id = "e" * 32
    with pytest.raises(HTTPException) as exc_info:
        web_api._run_public_question(
            web_api.PublicQuestionRequest(
                question="What happened?",
                archivist_mode="professional",
            ),
            public_settings(),
            request_id=request_id,
        )

    assert exc_info.value.status_code == 503
    assert observed == [(2_000_000_000, request_id)]


def test_public_essential_compiler_uses_budget_and_request_reservation(monkeypatch):
    chunks = synthetic_chunks(1)
    captured: dict[str, object] = {}
    reservations: list[int] = []

    class BudgetLedger:
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

    def fake_answer(*_args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            answer="Alpha evidence 1 supports this answer. [Source 1]",
            final_chunks=chunks,
            status="application_compiled",
        )

    monkeypatch.setattr(web_api, "UsageLedger", BudgetLedger)
    monkeypatch.setattr(
        web_api,
        "enforce_projected_usage_budget",
        lambda projected, _ledger: reservations.append(projected),
    )
    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    monkeypatch.setattr(web_api, "answer_run_diagnostics", lambda _result: {})

    response = web_api._run_public_question(
        web_api.PublicQuestionRequest(question="What happened?"),
        public_settings(),
    )

    assert response["answer_status"] == "application_compiled"
    assert captured["application_compiled"] is True
    assert reservations == [2_000_000_000]


def test_public_progressive_preflight_checks_budget_for_essential_compiler(monkeypatch):
    observed: list[str] = []

    class BudgetLedger:
        def get_settings(self):
            observed.append("settings")
            return {
                "monthly_budget_usd": 5.0,
                "warning_threshold_percent": 80,
                "hard_limit_enabled": True,
            }

        def budget_state(self):
            observed.append("budget")
            return {"exceeded": False}

    monkeypatch.setattr(web_api, "UsageLedger", BudgetLedger)

    web_api._preflight_public_progressive_question(
        web_api.PublicQuestionRequest(question="What happened?"),
        public_settings(),
    )

    assert observed == ["settings", "budget"]


def test_public_complete_validation_error_is_correlated_and_persisted(monkeypatch):
    monkeypatch.setenv("ARCHIVIST_DEPLOY_COMMIT", "c" * 40)
    client = TestClient(web_api.create_app(public_settings()))

    response = client.post(
        "/api/projects/current/question",
        json={
            "question": "What happened?",
            "conversation_id": "cohort-error",
            "turn_id": "turn-error",
            "n_results": 12,
        },
    )

    request_id = response.headers["x-request-id"]
    assert response.status_code == 422
    assert response.headers["x-archivist-commit"] == "c" * 40
    assert response.headers["x-archivist-process-epoch"] == web_api.PROCESS_EPOCH
    assert response.headers["server-timing"].startswith("app;dur=")
    observation = UsageLedger().find_public_request_observation(
        conversation_id="cohort-error",
        turn_id="turn-error",
    )
    assert observation is not None
    assert observation["request_id"] == request_id
    assert observation["http_status"] == 422


def test_public_observation_persistence_failure_never_breaks_response(monkeypatch):
    class BrokenLedger:
        def record_public_request_observation(self, **_kwargs):
            raise OSError("synthetic persistence failure")

    monkeypatch.setattr(web_api, "UsageLedger", BrokenLedger)
    monkeypatch.setattr(
        web_api,
        "_run_public_question",
        lambda _request, _settings, **_kwargs: {
            "answer": "Synthetic answer.",
            "answer_status": "answered",
            "source_schema": "archivist.public_sources/1",
            "sources": [],
        },
    )
    response = TestClient(web_api.create_app(public_settings())).post(
        "/api/projects/current/question",
        json={"question": "What happened?"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Synthetic answer."
    assert len(response.headers["x-request-id"]) == 32


def test_public_request_rejects_client_tuning_and_budget_bypass(monkeypatch):
    monkeypatch.setattr(web_api, "_public_project_config", lambda _settings: ready_config())
    client = TestClient(web_api.create_app(public_settings()))

    for forbidden in (
        {"allow_over_budget": True},
        {"n_results": 12},
        {"rag_policy_version": web_api.COMPACT_RAG_POLICY_VERSION},
    ):
        response = client.post(
            "/api/projects/current/question",
            json={"question": "What happened?", **forbidden},
        )
        assert response.status_code == 422

    with pytest.raises(ValidationError):
        web_api.PublicQuestionRequest.model_validate(
            {
                "question": "What happened?",
                "rag_policy_version": web_api.COMPACT_RAG_POLICY_VERSION,
            }
        )


@pytest.mark.parametrize("mode", ("forest", "cromb_coo_coo", "cosmic_almanac"))
def test_public_request_rejects_temporarily_hidden_modes(mode):
    with pytest.raises(ValidationError, match="temporarily unavailable"):
        web_api.PublicQuestionRequest(question="What happened?", archivist_mode=mode)


@pytest.mark.parametrize(
    "mode",
    (
        "essential",
        "professional",
        "pretty_pink_princess",
        "baleful_black_baron",
        "ember_and_ink",
    ),
)
def test_public_request_accepts_current_modes(mode):
    assert (
        web_api.PublicQuestionRequest(question="What happened?", archivist_mode=mode)
        .archivist_mode.value
        == mode
    )


def test_public_essential_rejects_prose_only_overrides():
    with pytest.raises(ValidationError, match="does not use prose settings"):
        web_api.PublicQuestionRequest(
            question="What happened?",
            archivist_mode="essential",
            worldview="pious",
        )


@pytest.mark.parametrize("request_model", (web_api.QuestionRequest, web_api.PublicQuestionRequest))
def test_essential_rejects_generative_full_context_scope(request_model):
    with pytest.raises(ValidationError, match="direct-evidence RAG mode"):
        request_model(
            question="What happened?",
            archivist_mode="essential",
            answer_strategy="full_context",
        )


def test_public_request_size_is_enforced_when_content_length_lies(monkeypatch):
    monkeypatch.setattr(web_api, "_public_project_config", lambda _settings: ready_config())
    client = TestClient(web_api.create_app(public_settings(max_request_bytes=400)))

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
    assert response.json()["detail"]["request_id"] == response.headers["x-request-id"]
    assert response.headers["server-timing"].startswith("app;dur=")
    assert (
        UsageLedger().get_public_request_observation(response.headers["x-request-id"])[
            "http_status"
        ]
        == 413
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_public_source_payload_preserves_numbers_and_bounds_excerpts():
    chunks = synthetic_chunks(5)
    answer = " ".join(
        f"Alpha evidence {number} supports this claim. [Source {number}]" for number in range(1, 6)
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
    observed_request_ids: list[str | None] = []

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

    def fake_answer(*_args, **_kwargs):
        observed_request_ids.append(current_usage_context().request_id)
        return SimpleNamespace(
            answer=(
                "Alpha evidence 1 directly supports the requested historical claim. [Source 1]"
            ),
            final_chunks=chunks,
            status="answered",
        )

    monkeypatch.setattr(web_api, "answer_project_question_result", fake_answer)
    request_id = "d" * 32
    response = web_api._run_public_question(
        web_api.PublicQuestionRequest(question="What happened?"),
        public_settings(),
        request_id=request_id,
    )

    assert response["answer_status"] == "answered"
    assert observed_request_ids == [request_id]
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


def test_public_character_conversation_releases_without_manuscript_sources(monkeypatch):
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

    answer = (
        "My imaginary palace is wonderfully busy today.\n\n"
        "Would you like to meet someone from the manuscript?"
    )
    monkeypatch.setattr(web_api, "UsageLedger", FakeLedger)
    monkeypatch.setattr(web_api, "answer_run_diagnostics", lambda _result: {})
    monkeypatch.setattr(
        web_api,
        "answer_project_question_result",
        lambda *_args, **_kwargs: SimpleNamespace(
            answer=answer,
            final_chunks=[],
            status="character_conversation",
            answer_strategy="rag",
            answer_strategy_version="retrieval-authored-v5",
            evidence_decision="indeterminate",
        ),
    )

    response = web_api._run_public_question(
        web_api.PublicQuestionRequest(
            question="How are you?",
            archivist_mode="pretty_pink_princess",
        ),
        public_settings(),
    )

    assert response["answer"] == answer
    assert response["answer_status"] == "character_conversation"
    assert response["sources"] == []
    assert response["source_schema"] == "archivist.public_sources/1"
    assert response["prose_renderer_version"] == "character-conversation-renderer-v1"


def test_public_product_help_has_no_model_renderer_metadata():
    metadata = web_api._answer_mode_metadata(
        archivist_mode=ArchivistMode.PROFESSIONAL,
        historiographical_lens=HistoriographicalLens.EVIDENCE_FIRST,
        voice=AnswerVoice.PLAINSPOKEN,
        worldview=Worldview.SECULAR_HUMANIST,
        application_compiled=True,
        answer_status="product_help",
    )

    assert metadata["prose_renderer_version"] is None
    assert metadata["prose_renderer_prompt_sha256"] is None
    assert metadata["prose_renderer_mode_instruction_sha256"] is None
    assert metadata["prose_renderer_influence_prompt_sha256"] is None


@pytest.mark.parametrize(
    "question",
    (
        pytest.param("What do you do?", id="exact"),
        pytest.param("How can you helpe me?", id="one-insertion"),
        pytest.param("what dop youd do>?", id="reported-two-typo-question"),
    ),
)
def test_public_product_help_releases_without_corpus_provider_or_sources(
    monkeypatch,
    question,
):
    def unexpected(*_args, **_kwargs):
        pytest.fail("provider-free product help must not load corpus or reserve provider spend")

    monkeypatch.setattr(web_project, "chroma_client", unexpected)
    monkeypatch.setattr(web_project, "openai_client", unexpected)
    monkeypatch.setattr(web_api, "UsageLedger", unexpected)
    monkeypatch.setattr(web_api, "enforce_projected_usage_budget", unexpected)
    monkeypatch.setattr(web_api, "public_source_payload", unexpected)
    stages = []

    response = web_api._run_public_question(
        web_api.PublicQuestionRequest(question=question),
        public_settings(),
        progress_callback=stages.append,
    )

    assert response["answer_status"] == "product_help"
    assert response["sources"] == []
    assert response["prose_renderer_version"] is None
    assert "not the open web" in response["answer"]
    assert stages == [
        web_api.AnswerProgressStage.GENERATING_ANSWER,
        web_api.AnswerProgressStage.VALIDATING_ANSWER,
        web_api.AnswerProgressStage.CHECKING_RELEASE,
    ]


@pytest.mark.parametrize(
    "question",
    (
        pytest.param("What do you do?", id="exact"),
        pytest.param("How can you helpe me?", id="one-insertion"),
        pytest.param("what dop youd do>?", id="reported-two-typo-question"),
    ),
)
def test_public_progressive_product_help_skips_spend_preflight(monkeypatch, question):
    monkeypatch.setattr(
        web_api,
        "UsageLedger",
        lambda: pytest.fail("provider-free product help must not inspect the spend ledger"),
    )

    web_api._preflight_public_progressive_question(
        web_api.PublicQuestionRequest(question=question),
        public_settings(),
    )


@pytest.mark.parametrize(
    "status",
    ("generation_contract_failed", "corpus_integrity_failed", "retrieval_unavailable"),
)
def test_public_question_withholds_fail_closed_answer_statuses(monkeypatch, status):
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
            answer="This internal failure message must not be released.",
            final_chunks=[],
            status=status,
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        web_api._run_public_question(
            web_api.PublicQuestionRequest(question="What happened?"),
            public_settings(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "public_answer_unavailable"


def test_public_answer_overlap_guard_detects_long_reproduction():
    repeated = " ".join(f"word{index}" for index in range(55))
    chunks = [{"text": repeated}]

    assert answer_has_extended_verbatim_overlap(repeated, chunks)
    assert not answer_has_extended_verbatim_overlap(
        "A short paraphrase of the evidence.",
        chunks,
    )


def test_public_full_context_rejects_long_reproduction_from_uncited_chunk(monkeypatch):
    cited_chunks = synthetic_chunks(1)
    copied_text = " ".join(f"privateword{index}" for index in range(55))
    uncited_chunk = {
        "chunk_id": "uncited_private_chunk",
        "document": "Private Manuscript.md",
        "chapter_title": "Private Manuscript",
        "text": copied_text,
    }

    class FakeLedger:
        def get_settings(self):
            return {
                "monthly_budget_usd": 5.0,
                "warning_threshold_percent": 80,
                "hard_limit_enabled": True,
            }

        def budget_state(self):
            return {"exceeded": False}

    monkeypatch.setattr(web_api, "UsageLedger", FakeLedger)
    monkeypatch.setattr(
        web_api,
        "answer_project_question_result",
        lambda *_args, **_kwargs: SimpleNamespace(
            answer=f"{copied_text} [Source 1]",
            final_chunks=cited_chunks,
            status="answered",
        ),
    )
    monkeypatch.setattr(
        web_api,
        "load_project_chunks",
        lambda _project_id: [*cited_chunks, uncited_chunk],
    )

    try:
        web_api._run_public_question(
            web_api.PublicQuestionRequest(
                question="What happened?",
                archivist_mode="professional",
                answer_strategy="full_context",
            ),
            public_settings(
                full_context_enabled=True,
                public_full_context_enabled=True,
            ),
        )
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.detail["code"] == "public_answer_unavailable"
    else:
        raise AssertionError("uncited private prose escaped the public overlap guard")


def test_public_rag_overlap_guard_still_uses_only_final_chunks(monkeypatch):
    final_chunks = synthetic_chunks(1)
    audited_chunks: list[object] = []

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
            answer="A concise answer grounded in the selected evidence. [Source 1]",
            final_chunks=final_chunks,
            status="answered",
        ),
    )

    def fail_if_full_corpus_is_loaded(_project_id):
        raise AssertionError("ordinary RAG must not load the full corpus for this guard")

    def capture_overlap_scope(_answer, chunks):
        audited_chunks.append(chunks)
        return False

    monkeypatch.setattr(web_api, "load_project_chunks", fail_if_full_corpus_is_loaded)
    monkeypatch.setattr(
        web_api,
        "answer_has_extended_verbatim_overlap",
        capture_overlap_scope,
    )

    response = web_api._run_public_question(
        web_api.PublicQuestionRequest(question="What happened?"),
        public_settings(),
    )

    assert response["answer_status"] == "answered"
    assert audited_chunks == [final_chunks]
    assert audited_chunks[0] is final_chunks


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


def test_public_full_context_request_is_rejected_when_the_server_disables_it():
    settings = public_settings()
    assert settings.full_context_available is False

    try:
        web_api._run_public_question(
            web_api.PublicQuestionRequest(
                question="What happened?",
                archivist_mode="professional",
                answer_strategy="full_context",
            ),
            settings,
        )
    except HTTPException as exc:
        # Explicit rejection, never a quiet retrieval answer wearing the same shape.
        assert exc.status_code == 503
        assert exc.detail["code"] == "full_context_disabled"
    else:
        raise AssertionError("a disabled strategy must not be answered")


def test_public_full_context_needs_both_switches_and_is_off_by_default():
    assert public_settings().full_context_available is False
    assert public_settings(full_context_enabled=True).full_context_available is False
    assert public_settings(public_full_context_enabled=True).full_context_available is False
    assert (
        public_settings(
            full_context_enabled=True,
            public_full_context_enabled=True,
        ).full_context_available
        is True
    )


def test_public_config_reports_full_context_availability_for_its_own_profile():
    disabled = web_api._feature_flags(web_api.ExposureProfile.PUBLIC_DEMO, public_settings())
    enabled = web_api._feature_flags(
        web_api.ExposureProfile.PUBLIC_DEMO,
        public_settings(full_context_enabled=True, public_full_context_enabled=True),
    )

    assert disabled["full_context_answers"] is False
    assert enabled["full_context_answers"] is True


def test_full_context_category_is_limited_without_starving_ordinary_questions():
    gate = PublicRequestGate(
        requests_per_minute=6,
        global_requests_per_minute=20,
        max_concurrent_requests=4,
        max_concurrent_per_client=4,
        category_requests_per_minute={FULL_CONTEXT_CATEGORY: 1},
        category_max_concurrent_requests={FULL_CONTEXT_CATEGORY: 1},
    )

    assert gate.try_enter("reader-a", now=100, category=FULL_CONTEXT_CATEGORY).allowed
    # A second full-context request inside the window is refused by the stricter
    # category rate, which is checked before the shared client and global limits.
    assert (
        gate.try_enter("reader-a", now=101, category=FULL_CONTEXT_CATEGORY).reason
        == "category_rate_limit"
    )
    # An ordinary question from the same reader is unaffected by that ceiling.
    assert gate.try_enter("reader-a", now=101, category=DEFAULT_CATEGORY).allowed
    # The rate window is per client, so once the in-flight request finishes,
    # another reader still gets their own allowance inside the same minute.
    gate.leave("reader-a", category=FULL_CONTEXT_CATEGORY)
    assert gate.try_enter("reader-b", now=101, category=FULL_CONTEXT_CATEGORY).allowed


def test_full_context_concurrency_ceiling_is_enforced_separately_from_its_rate():
    gate = PublicRequestGate(
        requests_per_minute=6,
        global_requests_per_minute=20,
        max_concurrent_requests=4,
        max_concurrent_per_client=4,
        category_requests_per_minute={FULL_CONTEXT_CATEGORY: 6},
        category_max_concurrent_requests={FULL_CONTEXT_CATEGORY: 1},
    )

    assert gate.try_enter("reader-a", now=100, category=FULL_CONTEXT_CATEGORY).allowed
    # Concurrency is global for the category: a different reader is still blocked
    # while one expensive request is in flight.
    assert (
        gate.try_enter("reader-b", now=100, category=FULL_CONTEXT_CATEGORY).reason
        == "category_concurrency_limit"
    )
    assert gate.try_enter("reader-b", now=100, category=DEFAULT_CATEGORY).allowed
    gate.leave("reader-a", category=FULL_CONTEXT_CATEGORY)
    assert gate.try_enter("reader-b", now=100, category=FULL_CONTEXT_CATEGORY).allowed


def test_development_endpoint_rejects_a_disabled_full_context_request(monkeypatch):
    from exposure_profile import ExposureProfile

    monkeypatch.setattr(
        web_api,
        "EXPOSURE_SETTINGS",
        ExposureSettings.development(full_context_enabled=False),
    )
    called: list[str] = []
    monkeypatch.setattr(
        web_api,
        "answer_project_question_result",
        lambda *_args, **_kwargs: called.append("answered"),
    )

    try:
        web_api.question(
            "current",
            web_api.QuestionRequest(
                question="What happened?",
                archivist_mode="professional",
                answer_strategy="full_context",
            ),
        )
    except HTTPException as exc:
        assert exc.status_code == 422
        assert exc.detail["code"] == "full_context_disabled"
    else:
        raise AssertionError("a disabled strategy must not be answered")

    # Rejected before any pipeline work, so nothing was spent.
    assert called == []
    assert (
        web_api._feature_flags(
            ExposureProfile.DEVELOPMENT,
            ExposureSettings.development(full_context_enabled=True),
        )["full_context_answers"]
        is True
    )
