from __future__ import annotations

from sqlalchemy import Engine
from src.db.config import DatabaseSettings, create_database_engine
from src.search.base import SearchBackend
from src.search.pg_repository import PgSearchRepository
from src.search.pg_service import PgSearchService
from src.search.providers.base import EmbeddingProvider, RerankProvider
from src.storage import build_object_storage, load_object_storage_settings
from src.storage.base import ObjectStorage


def create_search_service(
    *,
    database_settings: DatabaseSettings,
    embedding_model: EmbeddingProvider,
    reranker: RerankProvider | None,
    engine: Engine | None = None,
    object_storage: ObjectStorage | None = None,
    apply_collection_thresholds: bool = True,
) -> SearchBackend:
    storage = (
        object_storage
        if object_storage is not None
        else build_object_storage(load_object_storage_settings())
    )

    pg_engine = engine or create_database_engine(database_settings)
    return PgSearchService(
        repository=PgSearchRepository(engine=pg_engine),
        embedding_model=embedding_model,
        embedding_dimension=database_settings.embedding_dimension,
        reranker=reranker,
        object_storage=storage,
        apply_collection_thresholds=apply_collection_thresholds,
    )
