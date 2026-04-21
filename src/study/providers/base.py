from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator, Protocol

from src.runtime.telemetry import HealthStatus

if TYPE_CHECKING:
    from src.study.models import (
        GenerationEvent,
        GenerationRequest,
        GenerationResult,
        ProviderCapabilities,
    )

GeneratorHealth = HealthStatus


class GenerationProvider(Protocol):
    capabilities: "ProviderCapabilities"
    model_name: str

    async def generate(self, request: "GenerationRequest") -> "GenerationResult": ...

    async def stream_generate(
        self,
        request: "GenerationRequest",
    ) -> AsyncIterator["GenerationEvent"]: ...

    async def health(self) -> HealthStatus: ...


class ProviderError(Exception):
    """Base provider failure."""


class ProviderConnectionError(ProviderError):
    """Provider cannot be reached."""


class ProviderTimeoutError(ProviderError):
    """Provider request timed out."""


class ProviderHTTPError(ProviderError):
    """Provider returned an HTTP error response."""


class ModelNotAvailableError(ProviderError):
    """Configured model is missing or unavailable."""
