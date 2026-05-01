from __future__ import annotations

from dataclasses import dataclass
from inspect import isawaitable
from typing import Awaitable, Callable

from src.runtime.telemetry import HealthStatus

ReadinessCheck = Callable[[], HealthStatus | Awaitable[HealthStatus]]


@dataclass(frozen=True)
class DependencyReadinessProbe:
    name: str
    check: ReadinessCheck


@dataclass(frozen=True)
class ReadinessDependencies:
    database_probe: ReadinessCheck
    embedding_provider: object
    rerank_provider: object | None
    planning_provider: object
    generation_provider: object
    object_storage: object
    rate_limiter: object | None = None


async def _run_probe(check: ReadinessCheck) -> HealthStatus:
    try:
        result = check()
        if isawaitable(result):
            result = await result
    except Exception:
        return "error"
    return result


async def readiness_status(
    *,
    probes: list[DependencyReadinessProbe],
) -> dict[str, object]:
    checks: dict[str, HealthStatus] = {}
    overall: str = "ok"

    for probe in probes:
        result = await _run_probe(probe.check)
        checks[probe.name] = result
        if result != "ok":
            overall = "error"

    return {"status": overall, "checks": checks}
