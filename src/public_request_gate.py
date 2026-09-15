"""Single-process rate and concurrency gate for the bounded public demo."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil
from threading import Lock
from time import monotonic


@dataclass(frozen=True, slots=True)
class GateDecision:
    allowed: bool
    reason: str | None = None
    retry_after_seconds: int = 1


DEFAULT_CATEGORY = "question"
FULL_CONTEXT_CATEGORY = "full_context_question"


class PublicRequestGate:
    """Coordinate one public instance; multi-instance deployments need a shared gate."""

    def __init__(
        self,
        *,
        requests_per_minute: int,
        global_requests_per_minute: int,
        max_concurrent_requests: int,
        max_concurrent_per_client: int,
        category_requests_per_minute: Mapping[str, int] | None = None,
        category_max_concurrent_requests: Mapping[str, int] | None = None,
    ):
        self.requests_per_minute = requests_per_minute
        self.global_requests_per_minute = global_requests_per_minute
        self.max_concurrent_requests = max_concurrent_requests
        self.max_concurrent_per_client = max_concurrent_per_client
        # A category is a stricter ceiling layered on top of the shared limits,
        # never a way around them: an expensive category still consumes the same
        # global rate and concurrency budget as an ordinary request.
        self.category_requests_per_minute = dict(category_requests_per_minute or {})
        self.category_max_concurrent_requests = dict(category_max_concurrent_requests or {})
        self._lock = Lock()
        self._recent_requests: deque[tuple[float, str, str]] = deque()
        self._client_timestamps: dict[str, deque[float]] = {}
        self._category_timestamps: dict[tuple[str, str], deque[float]] = {}
        self._global_active = 0
        self._client_active: dict[str, int] = {}
        self._category_active: dict[str, int] = {}
        self._active_requests: dict[tuple[str, str], int] = {}

    def _expire(self, now: float) -> None:
        """Evict each accepted request once, including clients that never return."""

        cutoff = now - 60.0
        while self._recent_requests and self._recent_requests[0][0] <= cutoff:
            _, client_id, category = self._recent_requests.popleft()
            for entries, key in (
                (self._client_timestamps, client_id),
                (self._category_timestamps, (category, client_id)),
            ):
                timestamps = entries[key]
                timestamps.popleft()
                if not timestamps:
                    del entries[key]

    def try_enter(
        self,
        client_id: str,
        *,
        now: float | None = None,
        category: str = DEFAULT_CATEGORY,
    ) -> GateDecision:
        category_rate = self.category_requests_per_minute.get(category)
        category_concurrency = self.category_max_concurrent_requests.get(category)
        with self._lock:
            checked_at = monotonic() if now is None else now
            self._expire(checked_at)
            # Rejected requests must not allocate persistent client state.
            client_timestamps = self._client_timestamps.get(client_id, ())
            category_timestamps = self._category_timestamps.get((category, client_id), ())
            if category_rate is not None and len(category_timestamps) >= category_rate:
                retry_after = max(1, ceil(60 - (checked_at - category_timestamps[0])))
                return GateDecision(False, "category_rate_limit", retry_after)
            if len(client_timestamps) >= self.requests_per_minute:
                retry_after = max(1, ceil(60 - (checked_at - client_timestamps[0])))
                return GateDecision(False, "client_rate_limit", retry_after)
            if len(self._recent_requests) >= self.global_requests_per_minute:
                retry_after = max(
                    1,
                    ceil(60 - (checked_at - self._recent_requests[0][0])),
                )
                return GateDecision(False, "global_rate_limit", retry_after)
            if (
                category_concurrency is not None
                and self._category_active.get(category, 0) >= category_concurrency
            ):
                return GateDecision(False, "category_concurrency_limit", 1)
            if self._client_active.get(client_id, 0) >= self.max_concurrent_per_client:
                return GateDecision(False, "client_concurrency_limit", 1)
            if self._global_active >= self.max_concurrent_requests:
                return GateDecision(False, "global_concurrency_limit", 1)

            self._client_timestamps.setdefault(client_id, deque()).append(checked_at)
            self._category_timestamps.setdefault((category, client_id), deque()).append(checked_at)
            self._recent_requests.append((checked_at, client_id, category))
            self._client_active[client_id] = self._client_active.get(client_id, 0) + 1
            self._category_active[category] = self._category_active.get(category, 0) + 1
            key = (category, client_id)
            self._active_requests[key] = self._active_requests.get(key, 0) + 1
            self._global_active += 1
            return GateDecision(True)

    def leave(self, client_id: str, *, category: str = DEFAULT_CATEGORY) -> None:
        with self._lock:
            key = (category, client_id)
            if self._active_requests.get(key, 0) == 0:
                return
            for entries, entry_key in (
                (self._active_requests, key),
                (self._client_active, client_id),
                (self._category_active, category),
            ):
                entries[entry_key] -= 1
                if entries[entry_key] == 0:
                    del entries[entry_key]
            self._global_active -= 1
