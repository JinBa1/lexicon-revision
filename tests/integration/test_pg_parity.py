from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from scripts.index_chunks import index_collection as index_chroma
from scripts.index_chunks_postgres import index_collection_postgres
from sqlalchemy import create_engine, text
from src.search.pg_repository import PgSearchRepository
from src.search.pg_service import PgSearchService
from src.search.providers.base import EmbeddingResult
from src.search.service import SearchService

MINERU_FIXTURES = "tests/data/mineru_fixtures"


class _FakeEmbedder:
    model_id = "fake-v1"

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[self._vector(text) for text in texts],
            model_id=self.model_id,
        )

    def embed_query(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(vectors=[self._vector(text)], model_id=self.model_id)

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = []
        for idx in range(0, 32, 4):
            raw = int.from_bytes(digest[idx : idx + 4], "big")
            values.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
        return values


def _clean_db(engine: object) -> None:
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM chunk_embeddings"))
        conn.execute(text("DELETE FROM chunks"))
        conn.execute(text("DELETE FROM papers"))
        conn.execute(text("DELETE FROM collections"))
        conn.commit()


@pytest.mark.integration
def test_postgres_matches_chroma_top_k_id_set(tmp_path: Path) -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for pgvector integration tests")

    engine = create_engine(database_url, future=True)
    _clean_db(engine)

    embedder = _FakeEmbedder()
    collection = "fixture-parity"
    chroma_dir = str(tmp_path / "chroma")

    index_chroma(
        mineru_output_dir=MINERU_FIXTURES,
        collection_name=collection,
        chroma_dir=chroma_dir,
        embedding_model=embedder,
        recreate_collection=True,
    )
    index_collection_postgres(
        mineru_output_dir=MINERU_FIXTURES,
        collection_name=collection,
        engine=engine,
        embedding_model=embedder,
        embedding_dimension=8,
        recreate_collection=True,
    )

    chroma = SearchService(embedding_model=embedder, chroma_dir=chroma_dir)
    pg = PgSearchService(
        repository=PgSearchRepository(engine=engine),
        embedding_model=embedder,
        embedding_dimension=8,
    )

    query = "binary search"
    chroma_ids = {
        result.chunk_id
        for result in chroma.search(
            query, collection=collection, limit=5, rerank=False
        ).results
    }
    pg_ids = {
        result.chunk_id
        for result in pg.search(
            query, collection=collection, limit=5, rerank=False
        ).results
    }
    assert pg_ids == chroma_ids
