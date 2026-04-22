from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HealthStatus = Literal["ok", "unreachable", "model_missing", "error"]


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ProviderCallTelemetry:
    provider: str
    model: str
    latency_ms: int
    usage: TokenUsage | None = None
