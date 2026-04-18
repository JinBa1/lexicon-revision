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


def test_embedding_result_preserves_vectors_and_model_id() -> None:
    result = EmbeddingResult(vectors=[[0.1, 0.2]], model_id="m")
    assert result.vectors == [[0.1, 0.2]]
    assert result.model_id == "m"


def test_rerank_result_preserves_scores_and_model_id() -> None:
    result = RerankResult(scores=[0.9, 0.1], model_id="m")
    assert result.scores == [0.9, 0.1]
    assert result.model_id == "m"


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
                vectors=[[0.0] for _ in texts], model_id=self.model_id
            )

        def embed_query(self, text):
            return EmbeddingResult(vectors=[[0.0]], model_id=self.model_id)

    class _StubReranker:
        model_id = "stub"

        def rerank(self, query, documents):
            return RerankResult(scores=[0.0] * len(documents), model_id=self.model_id)

    assert isinstance(_StubEmbedder(), EmbeddingProvider)
    assert isinstance(_StubReranker(), RerankProvider)
