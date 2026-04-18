from __future__ import annotations

import os

import pytest
from scripts.index_chunks import build_embedding_text
from sqlalchemy import create_engine
from src.chunking.pipeline import run_pipeline
from src.search.pg_repository import PgIndexRepository, PgSearchRepository
from src.search.service import CollectionNotFoundError

pytestmark = pytest.mark.integration

MINERU_FIXTURES = "tests/data/mineru_fixtures"


def _engine():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for pgvector integration tests")
    return create_engine(database_url, future=True)


def _vectors(count: int, dimension: int) -> list[list[float]]:
    return [[1.0] + [0.0] * (dimension - 1) for _ in range(count)]


def test_index_repository_indexes_fixture_chunks() -> None:
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")
    inputs = [build_embedding_text(chunk) for chunk in chunks]
    vectors = _vectors(len(inputs), 8)

    repo = PgIndexRepository(
        engine=engine, embedding_model_id="fake-v1", embedding_dimension=8
    )
    repo.recreate_collection("fixture-pg")
    repo.index_chunks(collection_name="fixture-pg", chunks=chunks, vectors=vectors)

    search_repo = PgSearchRepository(engine=engine)
    results = search_repo.search(
        collection_name="fixture-pg",
        query_vector=[1.0] + [0.0] * 7,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
        filters={},
        limit=3,
    )

    assert len(results) == 3
    assert all(result.chunk_id.startswith("cam-") for result in results)


def test_index_repository_rejects_dimension_mismatch() -> None:
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")[:1]
    repo = PgIndexRepository(
        engine=engine, embedding_model_id="fake-v1", embedding_dimension=8
    )
    repo.recreate_collection("bad-dim")

    with pytest.raises(ValueError, match="embedding dimension"):
        repo.index_chunks(
            collection_name="bad-dim", chunks=chunks, vectors=[[1.0, 0.0]]
        )


def test_search_repository_raises_for_missing_collection() -> None:
    engine = _engine()
    repo = PgSearchRepository(engine=engine)

    with pytest.raises(CollectionNotFoundError, match="missing-collection"):
        repo.search(
            collection_name="missing-collection",
            query_vector=[1.0] + [0.0] * 7,
            embedding_model_id="fake-v1",
            embedding_dimension=8,
            filters={},
            limit=3,
        )


def test_search_repository_returns_full_metadata_shape() -> None:
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")
    inputs = [build_embedding_text(chunk) for chunk in chunks]
    vectors = _vectors(len(inputs), 8)

    repo = PgIndexRepository(
        engine=engine, embedding_model_id="fake-v1", embedding_dimension=8
    )
    repo.recreate_collection("fixture-metadata")
    repo.index_chunks(
        collection_name="fixture-metadata",
        chunks=chunks,
        vectors=vectors,
    )

    search_repo = PgSearchRepository(engine=engine)
    result = search_repo.search(
        collection_name="fixture-metadata",
        query_vector=[1.0] + [0.0] * 7,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
        filters={},
        limit=1,
    )[0]

    expected_keys = {
        "year",
        "paper",
        "question_number",
        "topic",
        "author",
        "tripos_part",
        "chunk_level",
        "parent_chunk_id",
        "sub_question_label",
        "marks",
        "total_marks",
        "has_code",
        "has_figure",
        "has_table",
        "source_pdf",
    }
    assert set(result.metadata.keys()) == expected_keys


def test_index_repository_allows_same_chunk_ids_in_multiple_collections() -> None:
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")[:1]
    repo = PgIndexRepository(
        engine=engine, embedding_model_id="fake-v1", embedding_dimension=8
    )

    repo.recreate_collection("fixture-a")
    repo.recreate_collection("fixture-b")
    repo.index_chunks(
        collection_name="fixture-a",
        chunks=chunks,
        vectors=_vectors(len(chunks), 8),
    )
    repo.index_chunks(
        collection_name="fixture-b",
        chunks=chunks,
        vectors=_vectors(len(chunks), 8),
    )

    search_repo = PgSearchRepository(engine=engine)
    result_a = search_repo.search(
        collection_name="fixture-a",
        query_vector=[1.0] + [0.0] * 7,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
        filters={},
        limit=1,
    )
    result_b = search_repo.search(
        collection_name="fixture-b",
        query_vector=[1.0] + [0.0] * 7,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
        filters={},
        limit=1,
    )

    assert result_a[0].chunk_id == chunks[0].id
    assert result_b[0].chunk_id == chunks[0].id


def test_index_repository_replaces_existing_chunk_ids_within_collection() -> None:
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")[:1]
    repo = PgIndexRepository(
        engine=engine, embedding_model_id="fake-v1", embedding_dimension=8
    )

    repo.recreate_collection("fixture-upsert")
    repo.index_chunks(
        collection_name="fixture-upsert",
        chunks=chunks,
        vectors=_vectors(len(chunks), 8),
    )
    repo.index_chunks(
        collection_name="fixture-upsert",
        chunks=chunks,
        vectors=_vectors(len(chunks), 8),
    )

    search_repo = PgSearchRepository(engine=engine)
    results = search_repo.search(
        collection_name="fixture-upsert",
        query_vector=[1.0] + [0.0] * 7,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
        filters={},
        limit=5,
    )

    assert [result.chunk_id for result in results] == [chunks[0].id]
