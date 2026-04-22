from __future__ import annotations

import time
from collections import deque


class InMemoryRateLimiter:
    """Single-process sliding-window limiter with lazy per-key pruning."""

    def __init__(self, *, window_seconds: int, max_requests: int) -> None:
        self._window_seconds = window_seconds
        self._max_requests = max_requests
        self._buckets: dict[str, deque[float]] = {}

    def allow(self, key: str, *, now: float | None = None) -> tuple[bool, int]:
        current_time = time.time() if now is None else now
        bucket = self._buckets.setdefault(key, deque())
        window_start = current_time - self._window_seconds

        while bucket and bucket[0] <= window_start:
            bucket.popleft()

        if len(bucket) >= self._max_requests:
            retry_after = max(1, int(self._window_seconds - (current_time - bucket[0])))
            return False, retry_after

        bucket.append(current_time)
        return True, 0
