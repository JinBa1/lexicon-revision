from __future__ import annotations

from sqlalchemy import Engine
from src.db.config import DatabaseSettings, create_database_engine
from src.search.base import SearchBackend
from src.search.pg_repository import PgSearchRepository
from src.search.pg_service import PgSearchService
from src.search.providers.base import EmbeddingProvider, RerankProvider
from src.search.service import DEFAULT_CHROMA_DIR, SearchService
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
    if database_settings.retrieval_backend == "chroma":
        storage = object_storage or build_object_storage(load_object_storage_settings())
        return SearchService(
            embedding_model=embedding_model,
            chroma_dir=chroma_dir,
            reranker=reranker,
            object_storage=storage,
        )
    if database_settings.retrieval_backend == "postgres":
        pg_engine = engine or create_database_engine(database_settings)
        storage = object_storage or build_object_storage(load_object_storage_settings())
        return PgSearchService(
            repository=PgSearchRepository(engine=pg_engine),
            embedding_model=embedding_model,
            embedding_dimension=database_settings.embedding_dimension,
            reranker=reranker,
            media_dir=chroma_dir,
            object_storage=storage,
        )
    raise ValueError(
        f"unsupported retrieval backend: {database_settings.retrieval_backend!r}"
    )
