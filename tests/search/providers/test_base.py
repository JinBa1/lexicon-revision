from src.runtime.telemetry import TokenUsage
from src.search.providers.base import (
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingResult,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderResponseError,
    ProviderTimeoutError,
    RerankProvider,
    RerankProviderError,
    RerankResult,
)


def test_embedding_result_preserves_provider_latency_and_usage() -> None:
    result = EmbeddingResult(
        vectors=[[0.1, 0.2]],
        model_id="m",
        provider="voyage",
        latency_ms=7,
        usage=TokenUsage(total_tokens=5),
    )
    assert result.vectors == [[0.1, 0.2]]
    assert result.model_id == "m"
    assert result.provider == "voyage"
    assert result.latency_ms == 7
    assert result.usage == TokenUsage(total_tokens=5)


def test_rerank_result_preserves_provider_latency_and_usage() -> None:
    result = RerankResult(
        scores=[0.9, 0.1],
        model_id="m",
        provider="voyage",
        latency_ms=11,
        usage=TokenUsage(total_tokens=5),
    )
    assert result.scores == [0.9, 0.1]
    assert result.model_id == "m"
    assert result.provider == "voyage"
    assert result.latency_ms == 11
    assert result.usage == TokenUsage(total_tokens=5)


def test_result_types_accept_legacy_constructor_shape() -> None:
    embedding = EmbeddingResult(vectors=[[0.1, 0.2]], model_id="m")
    rerank = RerankResult(scores=[0.9, 0.1], model_id="m")

    assert embedding.provider == ""
    assert embedding.latency_ms == 0
    assert embedding.usage is None
    assert rerank.provider == ""
    assert rerank.latency_ms == 0
    assert rerank.usage is None


def test_error_hierarchy_is_correct() -> None:
    # Check inheritance from base exceptions
    assert issubclass(EmbeddingProviderError, Exception)
    assert issubclass(RerankProviderError, Exception)

    # Check multiple inheritance for common provider errors
    for error_cls in [ProviderConnectionError, ProviderTimeoutError, ProviderHTTPError]:
        assert issubclass(error_cls, EmbeddingProviderError)
        assert issubclass(error_cls, RerankProviderError)

    # Check HTTP specific errors
    assert issubclass(ProviderAuthError, ProviderHTTPError)
    assert issubclass(ProviderResponseError, ProviderHTTPError)


def test_protocols_are_runtime_checkable() -> None:
    class _StubEmbedder:
        model_id = "stub"

        def embed_documents(self, texts):
            return EmbeddingResult(
                vectors=[[0.0] for _ in texts],
                model_id=self.model_id,
                provider="local",
                latency_ms=0,
            )

        def embed_query(self, text):
            return EmbeddingResult(
                vectors=[[0.0]],
                model_id=self.model_id,
                provider="local",
                latency_ms=0,
            )

        def health(self):
            return "ok"

    class _StubReranker:
        model_id = "stub"

        def rerank(self, query, documents):
            return RerankResult(
                scores=[0.0] * len(documents),
                model_id=self.model_id,
                provider="local",
                latency_ms=0,
            )

        def health(self):
            return "ok"

    assert isinstance(_StubEmbedder(), EmbeddingProvider)
    assert isinstance(_StubReranker(), RerankProvider)
