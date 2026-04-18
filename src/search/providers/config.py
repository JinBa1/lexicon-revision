from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from src.search.providers.base import EmbeddingProvider, RerankProvider


@dataclass(frozen=True)
class EmbeddingProviderSettings:
    provider: Literal["local", "voyage"]
    model: str
    output_dimension: int | None = None


@dataclass(frozen=True)
class RerankProviderSettings:
    provider: Literal["local", "voyage"]
    model: str


@dataclass(frozen=True)
class RetrievalProviderSettings:
    embedding: EmbeddingProviderSettings
    rerank: RerankProviderSettings
    rerank_enabled: bool
    voyage_api_key: str | None


def load_retrieval_provider_settings() -> RetrievalProviderSettings:
    embedding_provider_raw = os.environ.get("EMBEDDING_PROVIDER", "local").lower()
    if embedding_provider_raw not in ("local", "voyage"):
        raise ValueError(f"Unknown embedding provider: {embedding_provider_raw}")
    embedding_provider = _provider_name(embedding_provider_raw, role="embedding")

    embedding_model = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")

    embedding_dim_str = os.environ.get("EMBEDDING_OUTPUT_DIMENSION")
    embedding_dim = _parse_optional_int(
        embedding_dim_str,
        env_var="EMBEDDING_OUTPUT_DIMENSION",
    )

    rerank_provider_raw = os.environ.get("RERANK_PROVIDER", "local").lower()
    if rerank_provider_raw not in ("local", "voyage"):
        raise ValueError(f"Unknown rerank provider: {rerank_provider_raw}")
    rerank_provider = _provider_name(rerank_provider_raw, role="rerank")

    rerank_model = os.environ.get(
        "RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
    )
    rerank_enabled = os.environ.get("RERANK_ENABLED", "false").lower() == "true"

    voyage_api_key = os.environ.get("VOYAGE_API_KEY")

    return RetrievalProviderSettings(
        embedding=EmbeddingProviderSettings(
            provider=embedding_provider,
            model=embedding_model,
            output_dimension=embedding_dim,
        ),
        rerank=RerankProviderSettings(
            provider=rerank_provider,
            model=rerank_model,
        ),
        rerank_enabled=rerank_enabled,
        voyage_api_key=voyage_api_key,
    )


def build_embedding_provider(settings: RetrievalProviderSettings) -> EmbeddingProvider:
    if settings.embedding.provider == "local":
        from sentence_transformers import SentenceTransformer
        from src.search.providers.local import LocalSentenceTransformerEmbedder

        model = SentenceTransformer(settings.embedding.model)
        return LocalSentenceTransformerEmbedder(
            model=model,
            model_id=settings.embedding.model,
        )
    if settings.embedding.provider == "voyage":
        if not settings.voyage_api_key:
            raise ValueError("VOYAGE_API_KEY is required for voyage providers")
        from src.search.providers.voyage import VoyageEmbedder

        return VoyageEmbedder(
            api_key=settings.voyage_api_key,
            model=settings.embedding.model,
            output_dimension=settings.embedding.output_dimension,
        )
    raise ValueError(f"Unknown embedding provider: {settings.embedding.provider}")


def build_rerank_provider(
    settings: RetrievalProviderSettings,
    *,
    device: str | None = None,
) -> RerankProvider | None:
    if not settings.rerank_enabled:
        return None

    if settings.rerank.provider == "local":
        from sentence_transformers import CrossEncoder
        from src.search.providers.local import LocalCrossEncoderReranker

        kwargs = {}
        if device is not None:
            kwargs["device"] = device
        model = CrossEncoder(settings.rerank.model, **kwargs)

        return LocalCrossEncoderReranker(model=model, model_id=settings.rerank.model)
    if settings.rerank.provider == "voyage":
        if not settings.voyage_api_key:
            raise ValueError("VOYAGE_API_KEY is required for voyage providers")
        from src.search.providers.voyage import VoyageReranker

        return VoyageReranker(
            api_key=settings.voyage_api_key,
            model=settings.rerank.model,
        )
    raise ValueError(f"Unknown rerank provider: {settings.rerank.provider}")


def _provider_name(value: str, *, role: str) -> Literal["local", "voyage"]:
    if value == "local":
        return "local"
    if value == "voyage":
        return "voyage"
    raise ValueError(f"Unknown {role} provider: {value}")


def _parse_optional_int(value: str | None, *, env_var: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{env_var} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{env_var} must be positive")
    return parsed
