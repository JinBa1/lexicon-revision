from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.runtime.telemetry import HealthStatus, TokenUsage


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model_id: str
    provider: str = ""
    latency_ms: int = 0
    usage: TokenUsage | None = None


@dataclass(frozen=True)
class RerankResult:
    scores: list[float]
    model_id: str
    provider: str = ""
    latency_ms: int = 0
    usage: TokenUsage | None = None


@runtime_checkable
class EmbeddingProvider(Protocol):
    model_id: str

    def embed_documents(self, texts: list[str]) -> EmbeddingResult: ...

    def embed_query(self, text: str) -> EmbeddingResult: ...

    def health(self) -> HealthStatus: ...


@runtime_checkable
class RerankProvider(Protocol):
    model_id: str

    def rerank(self, query: str, documents: list[str]) -> RerankResult: ...

    def health(self) -> HealthStatus: ...


class EmbeddingProviderError(Exception): ...


class RerankProviderError(Exception): ...


class ProviderConnectionError(EmbeddingProviderError, RerankProviderError): ...


class ProviderTimeoutError(EmbeddingProviderError, RerankProviderError): ...


class ProviderHTTPError(EmbeddingProviderError, RerankProviderError): ...


class ProviderAuthError(ProviderHTTPError): ...


class ProviderResponseError(ProviderHTTPError): ...
