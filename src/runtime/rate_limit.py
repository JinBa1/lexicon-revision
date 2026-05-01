from __future__ import annotations

import hashlib
import hmac
import math
import time
from collections import deque
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any, Callable, Literal, Protocol
from urllib.parse import urlparse

from limits import parse
from limits.aio.strategies import SlidingWindowCounterRateLimiter
from limits.storage import storage_from_string
from src.runtime.config import RateLimitSettings
from src.runtime.telemetry import HealthStatus

RateLimitEndpoint = Literal["search", "study"]
RateLimitScope = Literal["user", "ip"]

RATE_LIMIT_NAMESPACE = "rag-exam:rate-limit"
RATE_LIMIT_RESPONSE_HEADERS = [
    "Retry-After",
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
]


class RateLimitUnavailableError(Exception):
    """Raised when rate-limit state cannot be checked."""


class InMemoryRateLimiter:
    """Temporary compatibility for pre-route-limiter wiring in src.main."""

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


@dataclass(frozen=True)
class RateLimitIdentity:
    scope: RateLimitScope
    identifier: str
    client_host_missing: bool = False


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    raw: str
    item: Any

    @property
    def limit(self) -> int:
        amount = getattr(self.item, "amount", None)
        return int(amount) if isinstance(amount, int) else 0


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    endpoint: RateLimitEndpoint
    policy: str
    scope: RateLimitScope
    limit: int
    remaining: int
    reset_epoch_seconds: int
    retry_after_seconds: int = 0
    client_host_missing: bool = False


class CostRateLimiter(Protocol):
    async def check(
        self,
        *,
        endpoint: RateLimitEndpoint,
        auth_context: object | None,
        fly_client_ip: str | None,
        client_host: str | None,
    ) -> RateLimitDecision: ...

    async def health(self) -> HealthStatus: ...

    async def aclose(self) -> None: ...


class RedisCostRateLimiter:
    def __init__(
        self,
        *,
        settings: RateLimitSettings,
        namespace: str = RATE_LIMIT_NAMESPACE,
        storage: Any | None = None,
        strategy: Any | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._namespace = namespace
        self._clock = clock
        self._storage = storage or storage_from_string(
            _limits_async_redis_uri(settings.redis_url)
        )
        self._strategy = strategy or SlidingWindowCounterRateLimiter(self._storage)
        self._policies: dict[
            tuple[RateLimitEndpoint, RateLimitScope], RateLimitPolicy
        ] = {
            ("search", "user"): RateLimitPolicy(
                "search:user", settings.search_user, parse(settings.search_user)
            ),
            ("search", "ip"): RateLimitPolicy(
                "search:ip", settings.search_anon, parse(settings.search_anon)
            ),
            ("study", "user"): RateLimitPolicy(
                "study:user", settings.study_user, parse(settings.study_user)
            ),
            ("study", "ip"): RateLimitPolicy(
                "study:ip", settings.study_anon, parse(settings.study_anon)
            ),
        }

    async def check(
        self,
        *,
        endpoint: RateLimitEndpoint,
        auth_context: object | None,
        fly_client_ip: str | None,
        client_host: str | None,
    ) -> RateLimitDecision:
        identity = resolve_rate_limit_identity(
            auth_context=auth_context,
            fly_client_ip=fly_client_ip,
            client_host=client_host,
        )
        policy = self._policies[(endpoint, identity.scope)]
        hashed_identifier = hash_rate_limit_identifier(
            self._settings.key_secret,
            identity.identifier,
        )
        identifiers = (
            self._namespace,
            policy.name,
            identity.scope,
            hashed_identifier,
        )
        try:
            allowed = await self._strategy.hit(policy.item, *identifiers)
            stats = await self._strategy.get_window_stats(policy.item, *identifiers)
        except Exception as exc:
            raise RateLimitUnavailableError("rate limit backend unavailable") from exc

        reset_epoch_seconds = int(math.ceil(float(stats.reset_time)))
        retry_after_seconds = (
            0
            if allowed
            else max(1, int(math.ceil(float(stats.reset_time) - self._clock())))
        )
        return RateLimitDecision(
            allowed=bool(allowed),
            endpoint=endpoint,
            policy=policy.name,
            scope=identity.scope,
            limit=policy.limit,
            remaining=max(0, int(stats.remaining)),
            reset_epoch_seconds=reset_epoch_seconds,
            retry_after_seconds=retry_after_seconds,
            client_host_missing=identity.client_host_missing,
        )

    async def health(self) -> HealthStatus:
        check = getattr(self._storage, "check", None)
        if not callable(check):
            return "error"
        try:
            result = check()
            if isawaitable(result):
                result = await result
        except Exception:
            return "error"
        return "ok" if result else "error"

    async def aclose(self) -> None:
        bridge_storage = getattr(
            getattr(self._storage, "bridge", None), "storage", None
        )
        connection_pool = getattr(bridge_storage, "connection_pool", None)
        close_hooks = (
            (self._storage, "aclose"),
            (self._storage, "close"),
            (bridge_storage, "aclose"),
            (bridge_storage, "close"),
            (connection_pool, "disconnect"),
        )
        for target, method_name in close_hooks:
            close = getattr(target, method_name, None)
            if not callable(close):
                continue
            result = close()
            if isawaitable(result):
                await result
            return


def _limits_async_redis_uri(redis_url: str) -> str:
    parsed = urlparse(redis_url)
    if parsed.scheme == "redis":
        return "async+redis://" + redis_url[len("redis://") :]
    if parsed.scheme == "rediss":
        return "async+rediss://" + redis_url[len("rediss://") :]
    raise ValueError("RATE_LIMIT_REDIS_URL must use redis:// or rediss://")


def resolve_rate_limit_identity(
    *,
    auth_context: object | None,
    fly_client_ip: str | None,
    client_host: str | None,
) -> RateLimitIdentity:
    app_user_id = _app_user_id_from_auth_context(auth_context)
    if app_user_id is not None:
        return RateLimitIdentity(scope="user", identifier=app_user_id)

    trusted_fly_ip = _clean_identifier(fly_client_ip)
    if trusted_fly_ip is not None:
        return RateLimitIdentity(scope="ip", identifier=trusted_fly_ip)

    trusted_client_host = _clean_identifier(client_host)
    if trusted_client_host is not None:
        return RateLimitIdentity(scope="ip", identifier=trusted_client_host)

    return RateLimitIdentity(
        scope="ip",
        identifier="unknown-client",
        client_host_missing=True,
    )


def hash_rate_limit_identifier(secret: str, identifier: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        identifier.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _app_user_id_from_auth_context(auth_context: object | None) -> str | None:
    identity = getattr(auth_context, "identity", None)
    user = getattr(identity, "user", None)
    user_id = getattr(user, "user_id", None)
    return user_id if isinstance(user_id, str) and user_id else None


def _clean_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
