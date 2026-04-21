from __future__ import annotations

import pytest
from src.runtime.readiness import DependencyReadinessProbe, readiness_status


def ok_sync() -> str:
    return "ok"


async def ok_async() -> str:
    return "ok"


@pytest.mark.anyio
async def test_readiness_handles_sync_and_async_checks() -> None:
    result = await readiness_status(
        probes=[
            DependencyReadinessProbe("database", ok_sync),
            DependencyReadinessProbe("generation", ok_async),
        ]
    )

    assert result["status"] == "ok"
    assert result["checks"] == {"database": "ok", "generation": "ok"}


@pytest.mark.anyio
async def test_readiness_fails_closed_when_any_dependency_fails() -> None:
    async def failing_generation() -> str:
        return "unreachable"

    result = await readiness_status(
        probes=[
            DependencyReadinessProbe("database", ok_sync),
            DependencyReadinessProbe("planning", ok_async),
            DependencyReadinessProbe("generation", failing_generation),
        ]
    )

    assert result["status"] == "error"
    assert result["checks"]["generation"] == "unreachable"


@pytest.mark.anyio
async def test_readiness_treats_probe_exceptions_as_errors() -> None:
    def broken_probe() -> str:
        raise AttributeError("miswired")

    result = await readiness_status(
        probes=[
            DependencyReadinessProbe("embedding", broken_probe),
        ]
    )

    assert result["status"] == "error"
    assert result["checks"] == {"embedding": "error"}
