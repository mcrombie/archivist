from types import SimpleNamespace

import pytest

import ask
import index_mode
import web_project
from model_config import (
    FOLLOWUP_RESOLVER_SETTINGS,
    GENERATOR_SETTINGS,
    GPT_5_6_SOL_MODEL,
    is_dated_model_snapshot,
    require_dated_model_snapshot,
)


def test_active_generation_roles_use_explicit_sol_defaults():
    assert GENERATOR_SETTINGS is not FOLLOWUP_RESOLVER_SETTINGS
    for settings in (GENERATOR_SETTINGS, FOLLOWUP_RESOLVER_SETTINGS):
        assert settings.model == GPT_5_6_SOL_MODEL == "gpt-5.6-sol"
        assert settings.responses_create_kwargs() == {
            "model": "gpt-5.6-sol",
            "reasoning": {"effort": "medium"},
            "text": {"verbosity": "medium"},
        }


def test_response_request_fragments_are_not_shared_mutable_state():
    first = GENERATOR_SETTINGS.responses_create_kwargs()
    first["reasoning"]["effort"] = "low"

    assert GENERATOR_SETTINGS.responses_create_kwargs()["reasoning"] == {"effort": "medium"}


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-5-2025-08-07", True),
        ("gpt-5.6-sol", False),
        ("gpt-5.6", False),
        ("gpt-5", False),
        ("gpt-5-2026-13-40", False),
        ("gpt-5-2025-08-07-preview", False),
    ],
)
def test_dated_snapshot_detection(model, expected):
    assert is_dated_model_snapshot(model) is expected


def test_active_named_model_is_not_misrepresented_as_a_run_of_record_pin():
    assert not GENERATOR_SETTINGS.run_of_record_eligible
    with pytest.raises(ValueError, match="formal runs of record require"):
        GENERATOR_SETTINGS.require_run_of_record_snapshot()
    assert require_dated_model_snapshot(
        "gpt-5-2025-08-07",
        role="generator",
    ) == "gpt-5-2025-08-07"


def test_cli_answer_generation_uses_central_generator_settings(monkeypatch):
    captured = {}
    chunks = [{"chunk_id": "synthetic_001", "text": "Synthetic evidence."}]

    class FakeResponses:
        def create(self, **request):
            captured.update(request)
            return SimpleNamespace(output_text="Synthetic answer [Source 1].")

    monkeypatch.setattr(ask, "retrieve", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(ask, "finalize_context_chunks", lambda _results: chunks)
    monkeypatch.setattr(
        ask,
        "default_openai_client",
        lambda: SimpleNamespace(responses=FakeResponses()),
    )

    answer, returned_chunks = ask.answer_question("What happened?")

    assert answer == "Synthetic answer [Source 1]."
    assert returned_chunks == chunks
    assert {
        key: captured[key] for key in ("model", "reasoning", "text")
    } == GENERATOR_SETTINGS.responses_create_kwargs()


def test_index_generation_uses_central_generator_settings(monkeypatch):
    captured = {}

    class FakeResponses:
        def create(self, **request):
            captured.update(request)
            return SimpleNamespace(output_text="Synthetic index entry.")

    monkeypatch.setattr(
        index_mode,
        "default_openai_client",
        lambda: SimpleNamespace(responses=FakeResponses()),
    )

    output = index_mode.generate_index_entry("Example", [])

    assert output == "Synthetic index entry."
    assert {
        key: captured[key] for key in ("model", "reasoning", "text")
    } == GENERATOR_SETTINGS.responses_create_kwargs()


def test_web_index_generation_uses_central_generator_settings(monkeypatch):
    captured = {}

    class FakeResponses:
        def create(self, **request):
            captured.update(request)
            return SimpleNamespace(output_text="Synthetic web index entry.")

    monkeypatch.setattr(web_project, "retrieve_project", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(web_project, "load_project_chunks", lambda _project_id: [])
    monkeypatch.setattr(
        web_project,
        "finalize_index_context",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        web_project,
        "openai_client",
        lambda: SimpleNamespace(responses=FakeResponses()),
    )

    output, final_chunks, existing_index = web_project.generate_index_entry(
        "current",
        "Example",
        consult_existing_index=False,
    )

    assert output == "Synthetic web index entry."
    assert final_chunks == existing_index == []
    assert {
        key: captured[key] for key in ("model", "reasoning", "text")
    } == GENERATOR_SETTINGS.responses_create_kwargs()
