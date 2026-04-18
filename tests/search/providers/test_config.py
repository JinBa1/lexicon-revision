import os
from unittest.mock import patch

import pytest
from src.search.providers.config import (
    EmbeddingProviderSettings,
    RerankProviderSettings,
    RetrievalProviderSettings,
    build_embedding_provider,
    build_rerank_provider,
    load_retrieval_provider_settings,
)
from src.search.providers.voyage import VoyageEmbedder, VoyageReranker


@pytest.fixture
def clean_env():
    with patch.dict(os.environ, {}, clear=True):
        yield


def test_defaults_select_local_providers_and_disabled_rerank(clean_env):
    settings = load_retrieval_provider_settings()
    assert settings.embedding.provider == "local"
    assert settings.embedding.model == "BAAI/bge-base-en-v1.5"
    assert settings.rerank.provider == "local"
    assert settings.rerank.model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert settings.rerank_enabled is False
    assert settings.voyage_api_key is None


def test_env_selects_voyage_models_and_api_key(clean_env):
    os.environ["EMBEDDING_PROVIDER"] = "voyage"
    os.environ["EMBEDDING_MODEL"] = "voyage-4-lite"
    os.environ["RERANK_PROVIDER"] = "voyage"
    os.environ["RERANK_MODEL"] = "rerank-2.5-lite"
    os.environ["RERANK_ENABLED"] = "true"
    os.environ["VOYAGE_API_KEY"] = "test-key"

    settings = load_retrieval_provider_settings()
    assert settings.embedding.provider == "voyage"
    assert settings.embedding.model == "voyage-4-lite"
    assert settings.rerank.provider == "voyage"
    assert settings.rerank.model == "rerank-2.5-lite"
    assert settings.rerank_enabled is True
    assert settings.voyage_api_key == "test-key"


def test_embedding_output_dimension_parses_to_int(clean_env):
    os.environ["EMBEDDING_OUTPUT_DIMENSION"] = "512"
    settings = load_retrieval_provider_settings()
    assert settings.embedding.output_dimension == 512


def test_unknown_provider_raises_value_error(clean_env):
    os.environ["EMBEDDING_PROVIDER"] = "unknown"
    with pytest.raises(ValueError, match="Unknown embedding provider: unknown"):
        load_retrieval_provider_settings()

    os.environ["EMBEDDING_PROVIDER"] = "local"
    os.environ["RERANK_PROVIDER"] = "unknown"
    with pytest.raises(ValueError, match="Unknown rerank provider: unknown"):
        load_retrieval_provider_settings()


def test_voyage_provider_without_api_key_raises_value_error_at_build_time(clean_env):
    os.environ["EMBEDDING_PROVIDER"] = "voyage"
    settings = load_retrieval_provider_settings()
    with pytest.raises(
        ValueError, match="VOYAGE_API_KEY is required for voyage providers"
    ):
        build_embedding_provider(settings)

    os.environ["EMBEDDING_PROVIDER"] = "local"
    os.environ["RERANK_PROVIDER"] = "voyage"
    os.environ["RERANK_ENABLED"] = "true"
    settings = load_retrieval_provider_settings()
    with pytest.raises(
        ValueError, match="VOYAGE_API_KEY is required for voyage providers"
    ):
        build_rerank_provider(settings)


def test_building_voyage_embedder_does_not_perform_network_io(clean_env):
    settings = RetrievalProviderSettings(
        embedding=EmbeddingProviderSettings(
            provider="voyage", model="voyage-4-lite", output_dimension=128
        ),
        rerank=RerankProviderSettings(provider="local", model="test"),
        rerank_enabled=False,
        voyage_api_key="test-key",
    )
    with patch("httpx.Client") as mock_client:
        provider = build_embedding_provider(settings)
        assert isinstance(provider, VoyageEmbedder)
        assert provider.api_key == "test-key"
        assert provider.model_id == "voyage-4-lite"
        assert provider.output_dimension == 128
        mock_client.assert_called_once()
        mock_client.return_value.request.assert_not_called()


def test_building_voyage_reranker_does_not_perform_network_io(clean_env):
    settings = RetrievalProviderSettings(
        embedding=EmbeddingProviderSettings(provider="local", model="test"),
        rerank=RerankProviderSettings(provider="voyage", model="rerank-2.5-lite"),
        rerank_enabled=True,
        voyage_api_key="test-key",
    )
    with patch("httpx.Client") as mock_client:
        provider = build_rerank_provider(settings)
        assert isinstance(provider, VoyageReranker)
        assert provider.api_key == "test-key"
        assert provider.model_id == "rerank-2.5-lite"
        mock_client.assert_called_once()
        mock_client.return_value.request.assert_not_called()


def test_disabled_rerank_returns_none(clean_env):
    settings = RetrievalProviderSettings(
        embedding=EmbeddingProviderSettings(provider="local", model="test"),
        rerank=RerankProviderSettings(provider="voyage", model="test"),
        rerank_enabled=False,
        voyage_api_key=None,
    )
    assert build_rerank_provider(settings) is None


def test_build_embedding_provider_local_instantiates_model(clean_env):
    settings = RetrievalProviderSettings(
        embedding=EmbeddingProviderSettings(provider="local", model="test-embed-model"),
        rerank=RerankProviderSettings(provider="local", model="test"),
        rerank_enabled=False,
        voyage_api_key=None,
    )
    with (
        patch("sentence_transformers.SentenceTransformer") as mock_st,
        patch(
            "src.search.providers.local.LocalSentenceTransformerEmbedder"
        ) as mock_embedder,
    ):
        provider = build_embedding_provider(settings)

        mock_st.assert_called_once_with("test-embed-model")
        mock_embedder.assert_called_once_with(
            model=mock_st.return_value, model_id="test-embed-model"
        )
        assert provider == mock_embedder.return_value


def test_build_rerank_provider_local_instantiates_model(clean_env):
    settings = RetrievalProviderSettings(
        embedding=EmbeddingProviderSettings(provider="local", model="test"),
        rerank=RerankProviderSettings(provider="local", model="test-rerank-model"),
        rerank_enabled=True,
        voyage_api_key=None,
    )
    with (
        patch("sentence_transformers.CrossEncoder") as mock_ce,
        patch("src.search.providers.local.LocalCrossEncoderReranker") as mock_reranker,
    ):
        provider = build_rerank_provider(settings, device="cuda")

        mock_ce.assert_called_once_with("test-rerank-model", device="cuda")
        mock_reranker.assert_called_once_with(
            model=mock_ce.return_value, model_id="test-rerank-model"
        )
        assert provider == mock_reranker.return_value
