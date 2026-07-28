"""Single-process rate and concurrency gate for the bounded public demo."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True, slots=True)
class GateDecision:
    allowed: bool
    reason: str | None = None
    retry_after_seconds: int = 1


class PublicRequestGate:
    """Coordinate one public instance; multi-instance deployments need a shared gate."""

    def __init__(
        self,
        *,
        requests_per_minute: int,
        global_requests_per_minute: int,
        max_concurrent_requests: int,
        max_concurrent_per_client: int,
    ):
        self.requests_per_minute = requests_per_minute
        self.global_requests_per_minute = global_requests_per_minute
        self.max_concurrent_requests = max_concurrent_requests
        self.max_concurrent_per_client = max_concurrent_per_client
        self._lock = Lock()
        self._global_timestamps: deque[float] = deque()
        self._client_timestamps: dict[str, deque[float]] = defaultdict(deque)
        self._global_active = 0
        self._client_active: dict[str, int] = defaultdict(int)

    @staticmethod
    def _expire(timestamps: deque[float], now: float) -> None:
        cutoff = now - 60.0
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()

    def try_enter(self, client_id: str, *, now: float | None = None) -> GateDecision:
        checked_at = monotonic() if now is None else now
        with self._lock:
            self._expire(self._global_timestamps, checked_at)
            client_timestamps = self._client_timestamps[client_id]
            self._expire(client_timestamps, checked_at)
            if len(client_timestamps) >= self.requests_per_minute:
                retry_after = max(1, round(60 - (checked_at - client_timestamps[0])))
                return GateDecision(False, "client_rate_limit", retry_after)
            if len(self._global_timestamps) >= self.global_requests_per_minute:
                retry_after = max(
                    1,
                    round(60 - (checked_at - self._global_timestamps[0])),
                )
                return GateDecision(False, "global_rate_limit", retry_after)
            if self._client_active[client_id] >= self.max_concurrent_per_client:
                return GateDecision(False, "client_concurrency_limit", 1)
            if self._global_active >= self.max_concurrent_requests:
                return GateDecision(False, "global_concurrency_limit", 1)

            client_timestamps.append(checked_at)
            self._global_timestamps.append(checked_at)
            self._client_active[client_id] += 1
            self._global_active += 1
            return GateDecision(True)

    def leave(self, client_id: str) -> None:
        with self._lock:
            if self._client_active.get(client_id, 0) > 0:
                self._client_active[client_id] -= 1
            if self._global_active > 0:
                self._global_active -= 1
