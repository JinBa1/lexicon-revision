from __future__ import annotations

from unittest.mock import Mock

import pytest
from src.db.config import DatabaseSettings
from src.search.base import SearchBackend
from src.search.factory import create_search_service
from src.search.pg_service import PgSearchService


def _settings(backend: str) -> DatabaseSettings:
    return DatabaseSettings(
        database_url="postgresql+psycopg://u:p@localhost/db",
        retrieval_backend=backend,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
    )


class _FalseyStorage:
    backend = "local"

    def __bool__(self) -> bool:
        return False


def test_create_search_service_returns_postgres_backend_only(tmp_path) -> None:
    service = create_search_service(
        database_settings=_settings("postgres"),
        chroma_dir=str(tmp_path),
        embedding_model=Mock(model_id="fake-v1"),
        reranker=None,
        engine=Mock(),
        object_storage=Mock(),
    )

    assert isinstance(service, PgSearchService)
    assert isinstance(service, SearchBackend)


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
            object_storage=Mock(),
        )


def test_factory_returns_postgres_service_for_postgres_backend(tmp_path) -> None:
    from src.search.pg_service import PgSearchService

    service = create_search_service(
        database_settings=_settings("postgres"),
        chroma_dir=str(tmp_path),
        embedding_model=Mock(model_id="fake-v1"),
        reranker=None,
        engine=Mock(),
        object_storage=Mock(),
    )

    assert isinstance(service, PgSearchService)
    assert isinstance(service, SearchBackend)


def test_factory_preserves_falsey_injected_storage_for_postgres(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FalseyStorage()
    monkeypatch.setattr(
        "src.search.factory.build_object_storage",
        lambda settings: (_ for _ in ()).throw(AssertionError("should not build")),
    )

    service = create_search_service(
        database_settings=_settings("postgres"),
        chroma_dir=str(tmp_path),
        embedding_model=Mock(model_id="fake-v1"),
        reranker=None,
        engine=Mock(),
        object_storage=storage,  # type: ignore[arg-type]
    )

    assert isinstance(service, PgSearchService)
    assert service._object_storage is storage  # type: ignore[attr-defined]
