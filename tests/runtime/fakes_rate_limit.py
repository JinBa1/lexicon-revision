from __future__ import annotations

import asyncio

from src.runtime.rate_limit import (
    RateLimitDecision,
    RateLimitEndpoint,
    RateLimitUnavailableError,
)
from src.runtime.telemetry import HealthStatus


class FakeCostRateLimiter:
    def __init__(
        self,
        *,
        decision: RateLimitDecision | None = None,
        unavailable: bool = False,
    ) -> None:
        self.decision = decision or RateLimitDecision(
            allowed=True,
            endpoint="search",
            policy="search:ip",
            scope="ip",
            limit=20,
            remaining=19,
            reset_epoch_seconds=1770000060,
        )
        self.unavailable = unavailable
        self.calls: list[dict[str, object]] = []

    async def check(
        self,
        *,
        endpoint: RateLimitEndpoint,
        auth_context: object | None,
        fly_client_ip: str | None,
        client_host: str | None,
    ) -> RateLimitDecision:
        self.calls.append(
            {
                "endpoint": endpoint,
                "auth_context": auth_context,
                "fly_client_ip": fly_client_ip,
                "client_host": client_host,
            }
        )
        if self.unavailable:
            raise RateLimitUnavailableError("redis unavailable")
        if self.decision.endpoint != endpoint:
            return RateLimitDecision(
                allowed=self.decision.allowed,
                endpoint=endpoint,
                policy=f"{endpoint}:{self.decision.scope}",
                scope=self.decision.scope,
                limit=self.decision.limit,
                remaining=self.decision.remaining,
                reset_epoch_seconds=self.decision.reset_epoch_seconds,
                retry_after_seconds=self.decision.retry_after_seconds,
                client_host_missing=self.decision.client_host_missing,
            )
        return self.decision

    async def health(self) -> HealthStatus:
        return "ok"

    async def aclose(self) -> None:
        return None


class HangingCostRateLimiter(FakeCostRateLimiter):
    async def check(
        self,
        *,
        endpoint: RateLimitEndpoint,
        auth_context: object | None,
        fly_client_ip: str | None,
        client_host: str | None,
    ) -> RateLimitDecision:
        self.calls.append(
            {
                "endpoint": endpoint,
                "auth_context": auth_context,
                "fly_client_ip": fly_client_ip,
                "client_host": client_host,
            }
        )
        await asyncio.sleep(1)
        return self.decision
