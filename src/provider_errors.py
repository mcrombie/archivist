"""Recognize provider failures whose cause a reader or operator can act on."""

from __future__ import annotations

from collections.abc import Mapping

INSUFFICIENT_QUOTA_CODE = "insufficient_quota"
PROVIDER_CREDITS_EXHAUSTED_STATUS = "provider_credits_exhausted"
PROVIDER_CREDITS_EXHAUSTED_MESSAGE = (
    "Archivist can't answer right now because its OpenAI usage credits have run out. "
    "The developer needs to add more credits before Archivist can answer again."
)


def _body_names_insufficient_quota(body: object) -> bool:
    if not isinstance(body, Mapping):
        return False
    error = body.get("error", body)
    return isinstance(error, Mapping) and INSUFFICIENT_QUOTA_CODE in (
        error.get("code"),
        error.get("type"),
    )


def is_insufficient_quota_error(exc: BaseException | None) -> bool:
    """Return whether a failure, or anything that caused it, is an exhausted OpenAI balance.

    OpenAI reports an empty prepaid balance as HTTP 429 with the code ``insufficient_quota``.
    Unlike an ordinary rate limit it does not clear on retry, so callers can say so plainly.
    """

    seen: set[int] = set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if INSUFFICIENT_QUOTA_CODE in (
            getattr(current, "code", None),
            getattr(current, "type", None),
        ):
            return True
        if _body_names_insufficient_quota(getattr(current, "body", None)):
            return True
        current = current.__cause__ or current.__context__
    return False


__all__ = [
    "INSUFFICIENT_QUOTA_CODE",
    "PROVIDER_CREDITS_EXHAUSTED_MESSAGE",
    "PROVIDER_CREDITS_EXHAUSTED_STATUS",
    "is_insufficient_quota_error",
]
