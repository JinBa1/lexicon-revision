from __future__ import annotations

from unittest.mock import Mock

import pytest
from src.db.config import DatabaseSettings
from src.search.factory import create_search_service
from src.search.service import SearchService


def _settings(backend: str) -> DatabaseSettings:
    return DatabaseSettings(
        database_url="postgresql+psycopg://u:p@localhost/db",
        retrieval_backend=backend,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
    )


def test_factory_returns_chroma_service_for_chroma_backend(tmp_path) -> None:
    service = create_search_service(
        database_settings=_settings("chroma"),
        chroma_dir=str(tmp_path),
        embedding_model=Mock(model_id="fake-v1"),
        reranker=None,
    )

    assert isinstance(service, SearchService)


def test_factory_rejects_unknown_backend(tmp_path) -> None:
    with pytest.raises(ValueError, match="retrieval backend"):
        create_search_service(
            database_settings=DatabaseSettings(
                database_url="postgresql+psycopg://u:p@localhost/db",
                retrieval_backend="other",  # type: ignore[arg-type]
                embedding_model_id="fake-v1",
                embedding_dimension=8,
            ),
            chroma_dir=str(tmp_path),
            embedding_model=Mock(model_id="fake-v1"),
            reranker=None,
        )


def test_factory_returns_postgres_service_for_postgres_backend(tmp_path) -> None:
    from src.search.pg_service import PgSearchService

    service = create_search_service(
        database_settings=_settings("postgres"),
        chroma_dir=str(tmp_path),
        embedding_model=Mock(model_id="fake-v1"),
        reranker=None,
        engine=Mock(),
    )

    assert isinstance(service, PgSearchService)
