from __future__ import annotations

from typing import Literal, Protocol

from src.study.models import GenerationRequest, GenerationResult, ProviderCapabilities

GeneratorHealth = Literal["ok", "unreachable", "model_missing", "error"]


class GenerationProvider(Protocol):
    capabilities: ProviderCapabilities

    async def generate(self, request: GenerationRequest) -> GenerationResult: ...

    async def health(self) -> GeneratorHealth: ...


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
