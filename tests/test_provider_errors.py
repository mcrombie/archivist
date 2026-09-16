import httpx
import openai

from provider_errors import INSUFFICIENT_QUOTA_CODE, is_insufficient_quota_error


def rate_limit_error(code):
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    return openai.RateLimitError(
        "synthetic rate limit",
        response=httpx.Response(429, request=request),
        body={"code": code, "type": code, "message": "synthetic"},
    )


def test_openai_insufficient_quota_is_recognized():
    assert is_insufficient_quota_error(rate_limit_error(INSUFFICIENT_QUOTA_CODE)) is True


def test_an_ordinary_rate_limit_is_not_exhausted_credits():
    assert is_insufficient_quota_error(rate_limit_error("rate_limit_exceeded")) is False


def test_a_wrapped_quota_error_is_recognized_through_its_cause():
    try:
        try:
            raise rate_limit_error(INSUFFICIENT_QUOTA_CODE)
        except openai.RateLimitError as exc:
            raise RuntimeError("embedding failed") from exc
    except RuntimeError as wrapped:
        assert is_insufficient_quota_error(wrapped) is True


def test_a_nested_error_body_is_recognized():
    class ProviderFailure(Exception):
        body = {"error": {"code": INSUFFICIENT_QUOTA_CODE, "message": "synthetic"}}

    assert is_insufficient_quota_error(ProviderFailure()) is True


def test_unrelated_failures_are_not_exhausted_credits():
    assert is_insufficient_quota_error(RuntimeError("synthetic failure")) is False
    assert is_insufficient_quota_error(None) is False
