from __future__ import annotations

import os
import uuid

import pytest
from src.runtime.config import RateLimitSettings
from src.runtime.rate_limit import RedisCostRateLimiter


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_redis_cost_rate_limiter_blocks_across_instances() -> None:
    redis_url = os.environ.get("TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("TEST_REDIS_URL is not configured")

    suffix = uuid.uuid4().hex
    settings = RateLimitSettings(
        redis_url=redis_url,
        key_secret=f"test-secret-{suffix}",
        search_user="1/minute",
        search_anon="1/minute",
        study_user="1/minute",
        study_anon="1/minute",
    )
    limiter_a = RedisCostRateLimiter(settings=settings, namespace=f"test:{suffix}")
    limiter_b = RedisCostRateLimiter(settings=settings, namespace=f"test:{suffix}")
    try:
        first = await limiter_a.check(
            endpoint="search",
            auth_context=None,
            fly_client_ip=f"203.0.113.{int(suffix[:2], 16)}",
            client_host=None,
        )
        second = await limiter_b.check(
            endpoint="search",
            auth_context=None,
            fly_client_ip=f"203.0.113.{int(suffix[:2], 16)}",
            client_host=None,
        )
    finally:
        await limiter_a.aclose()
        await limiter_b.aclose()

    assert first.allowed is True
    assert second.allowed is False
