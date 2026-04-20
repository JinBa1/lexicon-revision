from __future__ import annotations

from sqlalchemy import Engine
from src.db.config import DatabaseSettings, create_database_engine
from src.search.base import SearchBackend
from src.search.errors import DEFAULT_CHROMA_DIR
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
    chroma_dir: str = DEFAULT_CHROMA_DIR,
    engine: Engine | None = None,
    object_storage: ObjectStorage | None = None,
) -> SearchBackend:
    if database_settings.retrieval_backend not in {"chroma", "postgres"}:
        raise ValueError(
            f"unsupported retrieval backend: {database_settings.retrieval_backend!r}"
        )

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
        media_dir=chroma_dir,
        object_storage=storage,
    )
