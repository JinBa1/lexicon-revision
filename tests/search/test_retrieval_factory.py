from __future__ import annotations

import inspect
from unittest.mock import Mock

import pytest
from src.db.config import DatabaseSettings
from src.search.base import SearchBackend
from src.search.factory import create_search_service
from src.search.pg_service import PgSearchService


def _settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_url="postgresql+psycopg://u:p@localhost/db",
        embedding_model_id="fake-v1",
        embedding_dimension=8,
    )


class _FalseyStorage:
    backend = "local"

    def __bool__(self) -> bool:
        return False


def test_create_search_service_returns_postgres_backend_only(tmp_path) -> None:
    service = create_search_service(
        database_settings=_settings(),
        media_dir=str(tmp_path),
        embedding_model=Mock(model_id="fake-v1"),
        reranker=None,
        engine=Mock(),
        object_storage=Mock(),
    )

    assert isinstance(service, PgSearchService)
    assert isinstance(service, SearchBackend)


def test_factory_returns_postgres_service_for_postgres_backend(tmp_path) -> None:
    from src.search.pg_service import PgSearchService

    service = create_search_service(
        database_settings=_settings(),
        media_dir=str(tmp_path),
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
        database_settings=_settings(),
        media_dir=str(tmp_path),
        embedding_model=Mock(model_id="fake-v1"),
        reranker=None,
        engine=Mock(),
        object_storage=storage,  # type: ignore[arg-type]
    )

    assert isinstance(service, PgSearchService)
    assert service._object_storage is storage  # type: ignore[attr-defined]


def test_factory_exposes_collection_threshold_toggle() -> None:
    signature = inspect.signature(create_search_service)

    assert "retrieval_vector_min_score" not in signature.parameters
    assert "retrieval_rerank_min_score" not in signature.parameters
    assert signature.parameters["apply_collection_thresholds"].default is True


def test_factory_passes_collection_threshold_toggle_to_postgres_service(
    tmp_path,
) -> None:
    service = create_search_service(
        database_settings=_settings(),
        media_dir=str(tmp_path),
        embedding_model=Mock(model_id="fake-v1"),
        reranker=None,
        engine=Mock(),
        object_storage=Mock(),
        apply_collection_thresholds=False,
    )

    assert isinstance(service, PgSearchService)
    assert service._apply_collection_thresholds is False  # type: ignore[attr-defined]
