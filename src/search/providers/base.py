from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model_id: str


@dataclass(frozen=True)
class RerankResult:
    scores: list[float]
    model_id: str


@runtime_checkable
class EmbeddingProvider(Protocol):
    model_id: str

    def embed_documents(self, texts: list[str]) -> EmbeddingResult: ...

    def embed_query(self, text: str) -> EmbeddingResult: ...


@runtime_checkable
class RerankProvider(Protocol):
    model_id: str

    def rerank(self, query: str, documents: list[str]) -> RerankResult: ...


class EmbeddingProviderError(Exception): ...


class RerankProviderError(Exception): ...


class ProviderConnectionError(EmbeddingProviderError, RerankProviderError): ...


class ProviderTimeoutError(EmbeddingProviderError, RerankProviderError): ...


class ProviderHTTPError(EmbeddingProviderError, RerankProviderError): ...


class ProviderAuthError(ProviderHTTPError): ...


class ProviderResponseError(ProviderHTTPError): ...
