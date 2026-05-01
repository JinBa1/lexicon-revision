from __future__ import annotations

from dataclasses import dataclass

import pytest
from src.access.models import (
    AuthenticatedUser,
    AuthorizationContext,
    CollectionAccess,
    RequestIdentity,
    ResolvedIdentity,
)
from src.runtime.config import RateLimitSettings
from src.runtime.rate_limit import (
    RATE_LIMIT_NAMESPACE,
    RateLimitUnavailableError,
    RedisCostRateLimiter,
    _limits_async_redis_uri,
    hash_rate_limit_identifier,
    resolve_rate_limit_identity,
)


@dataclass(frozen=True)
class FakeWindowStats:
    remaining: int
    reset_time: float


class FakeStrategy:
    def __init__(self, *, allowed: bool, stats: FakeWindowStats) -> None:
        self.allowed = allowed
        self.stats = stats
        self.hit_calls: list[tuple[object, tuple[str, ...]]] = []
        self.stats_calls: list[tuple[object, tuple[str, ...]]] = []

    async def hit(self, item: object, *identifiers: str) -> bool:
        self.hit_calls.append((item, identifiers))
        return self.allowed

    async def get_window_stats(
        self, item: object, *identifiers: str
    ) -> FakeWindowStats:
        self.stats_calls.append((item, identifiers))
        return self.stats


class ExplodingStrategy:
    async def hit(self, item: object, *identifiers: str) -> bool:
        raise RuntimeError("redis unavailable")


class FakeStorage:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.closed = False

    async def check(self) -> bool:
        return self.healthy

    async def aclose(self) -> None:
        self.closed = True


class FakeSyncCloseStorage:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeConnectionPool:
    def __init__(self) -> None:
        self.disconnected = False

    def disconnect(self) -> None:
        self.disconnected = True


class FakeBridgeRedisClient:
    def __init__(self, connection_pool: FakeConnectionPool) -> None:
        self.connection_pool = connection_pool


class FakeBridge:
    def __init__(self, storage: FakeBridgeRedisClient) -> None:
        self.storage = storage


class FakeBridgeOnlyStorage:
    def __init__(self, connection_pool: FakeConnectionPool) -> None:
        self.bridge = FakeBridge(FakeBridgeRedisClient(connection_pool))


def _settings() -> RateLimitSettings:
    return RateLimitSettings(
        redis_url="redis://localhost:6379/0",
        key_secret="test-secret",
        search_user="2/minute",
        search_anon="1/minute",
        study_user="3/hour",
        study_anon="1/hour",
    )


def _auth_context(user_id: str) -> AuthorizationContext:
    return AuthorizationContext(
        collection=CollectionAccess(
            collection_id="collection-1",
            collection_name="fixture",
            community_id=None,
        ),
        identity=ResolvedIdentity(
            request_identity=RequestIdentity(
                provider="stub_header",
                external_subject="student@example.com",
                email="student@example.com",
            ),
            user=AuthenticatedUser(user_id=user_id, email="student@example.com"),
        ),
    )


def test_limits_async_redis_uri_translates_supported_urls() -> None:
    assert (
        _limits_async_redis_uri("redis://localhost:6379/0")
        == "async+redis://localhost:6379/0"
    )
    assert (
        _limits_async_redis_uri("rediss://default:secret@example.upstash.io:6379")
        == "async+rediss://default:secret@example.upstash.io:6379"
    )


def test_limits_async_redis_uri_rejects_unsupported_scheme() -> None:
    with pytest.raises(ValueError, match="redis:// or rediss://"):
        _limits_async_redis_uri("https://example.com")


def test_resolve_rate_limit_identity_prefers_signed_in_user() -> None:
    identity = resolve_rate_limit_identity(
        auth_context=_auth_context("user_123"),
        fly_client_ip="203.0.113.10",
        client_host="198.51.100.20",
    )

    assert identity.scope == "user"
    assert identity.identifier == "user_123"
    assert identity.client_host_missing is False


def test_resolve_rate_limit_identity_prefers_fly_client_ip_for_anonymous() -> None:
    identity = resolve_rate_limit_identity(
        auth_context=None,
        fly_client_ip="203.0.113.10",
        client_host="198.51.100.20",
    )

    assert identity.scope == "ip"
    assert identity.identifier == "203.0.113.10"


def test_resolve_rate_limit_identity_falls_back_to_client_host() -> None:
    identity = resolve_rate_limit_identity(
        auth_context=None,
        fly_client_ip=None,
        client_host="198.51.100.20",
    )

    assert identity.scope == "ip"
    assert identity.identifier == "198.51.100.20"


def test_resolve_rate_limit_identity_marks_missing_client_host() -> None:
    identity = resolve_rate_limit_identity(
        auth_context=None,
        fly_client_ip=None,
        client_host=None,
    )

    assert identity.scope == "ip"
    assert identity.identifier == "unknown-client"
    assert identity.client_host_missing is True


def test_hash_rate_limit_identifier_does_not_expose_raw_identifier() -> None:
    hashed = hash_rate_limit_identifier("secret", "user_123")

    assert "user_123" not in hashed
    assert hashed == hash_rate_limit_identifier("secret", "user_123")
    assert hashed != hash_rate_limit_identifier("other-secret", "user_123")


@pytest.mark.anyio
async def test_redis_cost_rate_limiter_allowed_decision_includes_metadata() -> None:
    strategy = FakeStrategy(
        allowed=True,
        stats=FakeWindowStats(remaining=1, reset_time=1770000042.3),
    )
    limiter = RedisCostRateLimiter(
        settings=_settings(),
        storage=FakeStorage(),
        strategy=strategy,
        clock=lambda: 1770000000.0,
    )

    decision = await limiter.check(
        endpoint="search",
        auth_context=_auth_context("user_123"),
        fly_client_ip=None,
        client_host="198.51.100.20",
    )

    assert decision.allowed is True
    assert decision.endpoint == "search"
    assert decision.policy == "search:user"
    assert decision.scope == "user"
    assert decision.limit == 2
    assert decision.remaining == 1
    assert decision.reset_epoch_seconds == 1770000043
    assert decision.retry_after_seconds == 0
    identifiers = strategy.hit_calls[0][1]
    assert identifiers[0] == RATE_LIMIT_NAMESPACE
    assert identifiers[1] == "search:user"
    assert identifiers[2] == "user"
    assert "user_123" not in identifiers[3]


@pytest.mark.anyio
async def test_redis_cost_rate_limiter_blocked_decision_includes_retry() -> None:
    strategy = FakeStrategy(
        allowed=False,
        stats=FakeWindowStats(remaining=0, reset_time=1770000042.3),
    )
    limiter = RedisCostRateLimiter(
        settings=_settings(),
        storage=FakeStorage(),
        strategy=strategy,
        clock=lambda: 1770000000.0,
    )

    decision = await limiter.check(
        endpoint="study",
        auth_context=None,
        fly_client_ip="203.0.113.10",
        client_host="198.51.100.20",
    )

    assert decision.allowed is False
    assert decision.policy == "study:ip"
    assert decision.scope == "ip"
    assert decision.limit == 1
    assert decision.retry_after_seconds == 43
    identifiers = strategy.hit_calls[0][1]
    assert all("203.0.113.10" not in identifier for identifier in identifiers)


@pytest.mark.anyio
async def test_redis_cost_rate_limiter_maps_backend_error_to_unavailable() -> None:
    limiter = RedisCostRateLimiter(
        settings=_settings(),
        storage=FakeStorage(),
        strategy=ExplodingStrategy(),
        clock=lambda: 1770000000.0,
    )

    with pytest.raises(RateLimitUnavailableError):
        await limiter.check(
            endpoint="search",
            auth_context=None,
            fly_client_ip=None,
            client_host="198.51.100.20",
        )


@pytest.mark.anyio
async def test_redis_cost_rate_limiter_health_and_close_delegate_to_storage() -> None:
    storage = FakeStorage(healthy=True)
    limiter = RedisCostRateLimiter(
        settings=_settings(),
        storage=storage,
        strategy=FakeStrategy(
            allowed=True,
            stats=FakeWindowStats(remaining=1, reset_time=1770000042.0),
        ),
    )

    assert await limiter.health() == "ok"
    await limiter.aclose()
    assert storage.closed is True


@pytest.mark.anyio
async def test_redis_cost_rate_limiter_close_uses_sync_storage_close() -> None:
    storage = FakeSyncCloseStorage()
    limiter = RedisCostRateLimiter(
        settings=_settings(),
        storage=storage,
        strategy=FakeStrategy(
            allowed=True,
            stats=FakeWindowStats(remaining=1, reset_time=1770000042.0),
        ),
    )

    await limiter.aclose()

    assert storage.closed is True


@pytest.mark.anyio
async def test_redis_cost_rate_limiter_close_uses_nested_connection_pool() -> None:
    connection_pool = FakeConnectionPool()
    storage = FakeBridgeOnlyStorage(connection_pool)
    limiter = RedisCostRateLimiter(
        settings=_settings(),
        storage=storage,
        strategy=FakeStrategy(
            allowed=True,
            stats=FakeWindowStats(remaining=1, reset_time=1770000042.0),
        ),
    )

    await limiter.aclose()

    assert connection_pool.disconnected is True
