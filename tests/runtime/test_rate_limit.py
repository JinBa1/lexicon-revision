from __future__ import annotations

from src.runtime.rate_limit import InMemoryRateLimiter


def test_rate_limiter_blocks_after_quota_within_window() -> None:
    limiter = InMemoryRateLimiter(window_seconds=60, max_requests=2)

    assert limiter.allow("client-1", now=0.0) == (True, 0)
    assert limiter.allow("client-1", now=1.0) == (True, 0)

    allowed, retry_after = limiter.allow("client-1", now=2.0)

    assert allowed is False
    assert retry_after == 58


def test_rate_limiter_prunes_expired_entries_on_next_access() -> None:
    limiter = InMemoryRateLimiter(window_seconds=10, max_requests=1)

    assert limiter.allow("client-1", now=0.0) == (True, 0)
    assert limiter.allow("client-1", now=11.0) == (True, 0)
