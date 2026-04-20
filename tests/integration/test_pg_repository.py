from __future__ import annotations

import os

import pytest
from scripts.index_chunks_postgres import build_embedding_text
from sqlalchemy import create_engine, text
from src.chunking.pipeline import run_pipeline
from src.db.metadata_indexes import ensure_metadata_indexes
from src.metadata_schema import (
    CollectionMetadataSchema,
    FilterCondition,
    default_schema_path,
    load_collection_schema,
)
from src.search.errors import CollectionNotFoundError, InvalidMetadataFilterError
from src.search.pg_repository import PgIndexRepository, PgSearchRepository

pytestmark = pytest.mark.integration

MINERU_FIXTURES = "tests/data/mineru_fixtures"


def _engine():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for pgvector integration tests")
    return create_engine(database_url, future=True)


def _vectors(count: int, dimension: int) -> list[list[float]]:
    return [[1.0] + [0.0] * (dimension - 1) for _ in range(count)]


def _schema():
    return load_collection_schema(default_schema_path("cam-cs-tripos-fixture"))


def _schema_with_field(*, key: str, field_type: str) -> CollectionMetadataSchema:
    return CollectionMetadataSchema.model_validate(
        {
            "version": 1,
            "fields": [
                {
                    "key": key,
                    "label": key.replace("_", " ").title(),
                    "type": field_type,
                    "operators": ["eq"],
                    "exposed": True,
                }
            ],
        }
    )


def _schema_with_custom_field(
    *,
    key: str,
    field_type: str,
    operators: list[str],
) -> CollectionMetadataSchema:
    return CollectionMetadataSchema.model_validate(
        {
            "version": 1,
            "fields": [
                {
                    "key": key,
                    "label": key.replace("_", " ").title(),
                    "type": field_type,
                    "operators": operators,
                    "exposed": True,
                    "source": f"chunk.{key}",
                }
            ],
        }
    )


def test_index_repository_indexes_fixture_chunks() -> None:
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")
    inputs = [build_embedding_text(chunk) for chunk in chunks]
    vectors = _vectors(len(inputs), 8)

    repo = PgIndexRepository(
        engine=engine, embedding_model_id="fake-v1", embedding_dimension=8
    )
    repo.recreate_collection("fixture-pg")
    repo.index_chunks(
        collection_name="fixture-pg",
        chunks=chunks,
        vectors=vectors,
        metadata_schema=_schema(),
    )

    search_repo = PgSearchRepository(engine=engine)
    results = search_repo.search(
        collection_name="fixture-pg",
        query_vector=[1.0] + [0.0] * 7,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
        filters=[],
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
            collection_name="bad-dim",
            chunks=chunks,
            vectors=[[1.0, 0.0]],
            metadata_schema=_schema(),
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
            filters=[],
            limit=3,
        )


def test_search_repository_rejects_invalid_collection_schema() -> None:
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into collections (
                    id,
                    name,
                    embedding_model_id,
                    embedding_dimension,
                    metadata_schema
                ) values (
                    'collection-invalid-schema',
                    'invalid-schema',
                    'fake-v1',
                    8,
                    '{}'::jsonb
                )
                """
            )
        )
        conn.execute(
            text(
                """
                insert into papers (id, collection_id, source_pdf)
                values (
                    'paper-invalid-schema',
                    'collection-invalid-schema',
                    'fixture.pdf'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                insert into chunks (
                    id,
                    chunk_id,
                    collection_id,
                    paper_id,
                    chunk_level,
                    parent_chunk_id,
                    sub_question_label,
                    text,
                    metadata,
                    source_pdf
                ) values (
                    'chunk-invalid-schema',
                    'cam-invalid',
                    'collection-invalid-schema',
                    'paper-invalid-schema',
                    'question',
                    null,
                    null,
                    'Invalid schema test',
                    '{"year": 2025}'::jsonb,
                    'fixture.pdf'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                insert into chunk_embeddings (chunk_id, embedding_model_id, embedding)
                values ('chunk-invalid-schema', 'fake-v1', '[1,0,0,0,0,0,0,0]')
                """
            )
        )

    repo = PgSearchRepository(engine=engine)
    with pytest.raises(InvalidMetadataFilterError, match="invalid metadata schema"):
        repo.search(
            collection_name="invalid-schema",
            query_vector=[1.0] + [0.0] * 7,
            embedding_model_id="fake-v1",
            embedding_dimension=8,
            filters=[],
            limit=3,
        )


def test_index_repository_persists_collection_schema_and_chunk_metadata() -> None:
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")
    inputs = [build_embedding_text(chunk) for chunk in chunks]
    vectors = _vectors(len(inputs), 8)
    metadata_schema = _schema()

    repo = PgIndexRepository(
        engine=engine, embedding_model_id="fake-v1", embedding_dimension=8
    )
    repo.recreate_collection("fixture-metadata")
    repo.index_chunks(
        collection_name="fixture-metadata",
        chunks=chunks,
        vectors=vectors,
        metadata_schema=metadata_schema,
    )

    with engine.connect() as conn:
        collection_row = conn.execute(
            text(
                """
                select metadata_schema
                from collections
                where name = :collection_name
                """
            ),
            {"collection_name": "fixture-metadata"},
        ).first()
        chunk_row = conn.execute(
            text(
                """
                select metadata
                from chunks
                where collection_id = (
                    select id from collections where name = :collection_name
                )
                order by chunk_id
                limit 1
                """
            ),
            {"collection_name": "fixture-metadata"},
        ).first()

    assert collection_row is not None
    assert chunk_row is not None
    assert collection_row.metadata_schema == metadata_schema.model_dump(mode="json")
    assert "year" in chunk_row.metadata
    assert "source_pdf" not in chunk_row.metadata


def test_search_repository_returns_metadata_from_canonical_storage() -> None:
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")
    inputs = [build_embedding_text(chunk) for chunk in chunks]
    vectors = _vectors(len(inputs), 8)

    repo = PgIndexRepository(
        engine=engine, embedding_model_id="fake-v1", embedding_dimension=8
    )
    repo.recreate_collection("fixture-search-metadata")
    repo.index_chunks(
        collection_name="fixture-search-metadata",
        chunks=chunks,
        vectors=vectors,
        metadata_schema=_schema(),
    )

    search_repo = PgSearchRepository(engine=engine)
    result = search_repo.search(
        collection_name="fixture-search-metadata",
        query_vector=[1.0] + [0.0] * 7,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
        filters=[],
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
    assert result.metadata["year"] is not None
    assert result.metadata["source_pdf"].endswith(".pdf")


def test_search_repository_filters_using_canonical_chunk_metadata() -> None:
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")
    inputs = [build_embedding_text(chunk) for chunk in chunks]
    vectors = _vectors(len(inputs), 8)

    repo = PgIndexRepository(
        engine=engine, embedding_model_id="fake-v1", embedding_dimension=8
    )
    repo.recreate_collection("fixture-filter-metadata")
    repo.index_chunks(
        collection_name="fixture-filter-metadata",
        chunks=chunks,
        vectors=vectors,
        metadata_schema=_schema(),
    )

    search_repo = PgSearchRepository(engine=engine)
    results = search_repo.search(
        collection_name="fixture-filter-metadata",
        query_vector=[1.0] + [0.0] * 7,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
        filters=[
            FilterCondition(field="year", op="eq", value=2025),
            FilterCondition(field="has_code", op="eq", value=True),
        ],
        limit=10,
    )

    assert results
    assert all(result.metadata["year"] == 2025 for result in results)
    assert all(result.metadata["has_code"] is True for result in results)


def test_search_repository_rejects_filter_field_absent_from_collection_schema() -> None:
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")
    vectors = _vectors(1, 8)
    schema = _schema_with_field(key="year", field_type="integer")

    repo = PgIndexRepository(
        engine=engine,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
    )
    repo.recreate_collection("fixture-filter-validation")
    repo.index_chunks(
        collection_name="fixture-filter-validation",
        chunks=chunks[:1],
        vectors=vectors,
        metadata_schema=schema,
    )

    search_repo = PgSearchRepository(engine=engine)
    with pytest.raises(
        InvalidMetadataFilterError,
        match="not declared in collection metadata schema",
    ):
        search_repo.search(
            collection_name="fixture-filter-validation",
            query_vector=[1.0] + [0.0] * 7,
            embedding_model_id="fake-v1",
            embedding_dimension=8,
            filters=[FilterCondition(field="topic", op="eq", value="Algorithms")],
            limit=10,
        )


def test_search_repository_rejects_filter_operator_absent_from_collection_schema() -> (
    None
):
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")
    vectors = _vectors(1, 8)
    schema = _schema_with_custom_field(
        key="marks",
        field_type="integer",
        operators=["eq"],
    )

    repo = PgIndexRepository(
        engine=engine,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
    )
    repo.recreate_collection("fixture-filter-operator-validation")
    repo.index_chunks(
        collection_name="fixture-filter-operator-validation",
        chunks=chunks[:1],
        vectors=vectors,
        metadata_schema=schema,
    )

    search_repo = PgSearchRepository(engine=engine)
    with pytest.raises(
        InvalidMetadataFilterError,
        match="does not allow operator 'gte'",
    ):
        search_repo.search(
            collection_name="fixture-filter-operator-validation",
            query_vector=[1.0] + [0.0] * 7,
            embedding_model_id="fake-v1",
            embedding_dimension=8,
            filters=[FilterCondition(field="marks", op="gte", value=5)],
            limit=10,
        )


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
        metadata_schema=_schema(),
    )
    repo.index_chunks(
        collection_name="fixture-b",
        chunks=chunks,
        vectors=_vectors(len(chunks), 8),
        metadata_schema=_schema(),
    )

    search_repo = PgSearchRepository(engine=engine)
    result_a = search_repo.search(
        collection_name="fixture-a",
        query_vector=[1.0] + [0.0] * 7,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
        filters=[],
        limit=1,
    )
    result_b = search_repo.search(
        collection_name="fixture-b",
        query_vector=[1.0] + [0.0] * 7,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
        filters=[],
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
        metadata_schema=_schema(),
    )
    repo.index_chunks(
        collection_name="fixture-upsert",
        chunks=chunks,
        vectors=_vectors(len(chunks), 8),
        metadata_schema=_schema(),
    )

    search_repo = PgSearchRepository(engine=engine)
    results = search_repo.search(
        collection_name="fixture-upsert",
        query_vector=[1.0] + [0.0] * 7,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
        filters=[],
        limit=5,
    )

    assert [result.chunk_id for result in results] == [chunks[0].id]


def test_index_repository_rejects_schema_change_without_recreate() -> None:
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")[:1]
    original_schema = _schema_with_custom_field(
        key="year",
        field_type="integer",
        operators=["eq"],
    )
    changed_schema = CollectionMetadataSchema.model_validate(
        {
            "version": 1,
            "fields": [
                {
                    "key": "year",
                    "label": "Year",
                    "type": "integer",
                    "operators": ["eq", "gte"],
                    "exposed": True,
                    "source": "chunk.year",
                }
            ],
        }
    )

    repo = PgIndexRepository(
        engine=engine,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
    )
    repo.recreate_collection("fixture-schema-drift")
    repo.index_chunks(
        collection_name="fixture-schema-drift",
        chunks=chunks,
        vectors=_vectors(1, 8),
        metadata_schema=original_schema,
    )

    with pytest.raises(ValueError, match="recreate-collection"):
        repo.index_chunks(
            collection_name="fixture-schema-drift",
            chunks=chunks,
            vectors=_vectors(1, 8),
            metadata_schema=changed_schema,
        )

    with engine.connect() as conn:
        stored_schema = conn.execute(
            text(
                """
                select metadata_schema
                from collections
                where name = 'fixture-schema-drift'
                """
            )
        ).scalar_one()

    assert stored_schema == original_schema.model_dump(mode="json")


def test_metadata_indexes_are_collection_scoped_for_conflicting_schemas() -> None:
    engine = _engine()
    schema_int = _schema_with_field(key="difficulty", field_type="integer")
    schema_str = _schema_with_field(key="difficulty", field_type="string")

    repo = PgIndexRepository(
        engine=engine,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
    )
    repo.recreate_collection("fixture-index-int")
    repo.recreate_collection("fixture-index-str")
    repo.index_chunks(
        collection_name="fixture-index-int",
        chunks=run_pipeline(MINERU_FIXTURES, university="cam")[:1],
        vectors=_vectors(1, 8),
        metadata_schema=schema_int,
    )
    repo.index_chunks(
        collection_name="fixture-index-str",
        chunks=run_pipeline(MINERU_FIXTURES, university="cam")[:1],
        vectors=_vectors(1, 8),
        metadata_schema=schema_str,
    )

    ensure_metadata_indexes(
        engine,
        collection_name="fixture-index-int",
        schema=schema_int,
    )
    ensure_metadata_indexes(
        engine,
        collection_name="fixture-index-str",
        schema=schema_str,
    )

    with engine.connect() as conn:
        matching_indexes = conn.execute(
            text(
                """
                select indexname, indexdef
                from pg_indexes
                where schemaname = current_schema()
                  and tablename = 'chunks'
                  and indexname like 'ix_chunks_metadata_fixture_%'
                order by indexname
                """
            )
        ).fetchall()

    assert len(matching_indexes) >= 2
    assert any("::integer" in row.indexdef for row in matching_indexes)
    assert any("->> 'difficulty'" in row.indexdef for row in matching_indexes)
    assert all(" where " in row.indexdef.lower() for row in matching_indexes)


def test_metadata_indexes_rebuild_for_recreated_collection_name() -> None:
    engine = _engine()
    chunks = run_pipeline(MINERU_FIXTURES, university="cam")[:1]
    schema = _schema()

    repo = PgIndexRepository(
        engine=engine,
        embedding_model_id="fake-v1",
        embedding_dimension=8,
    )
    repo.recreate_collection("fixture-recreate-indexes")
    repo.index_chunks(
        collection_name="fixture-recreate-indexes",
        chunks=chunks,
        vectors=_vectors(1, 8),
        metadata_schema=schema,
    )
    ensure_metadata_indexes(
        engine,
        collection_name="fixture-recreate-indexes",
        schema=schema,
    )

    with engine.connect() as conn:
        first_collection_id = conn.execute(
            text("select id from collections where name = 'fixture-recreate-indexes'")
        ).scalar_one()

    repo.recreate_collection("fixture-recreate-indexes")
    repo.index_chunks(
        collection_name="fixture-recreate-indexes",
        chunks=chunks,
        vectors=_vectors(1, 8),
        metadata_schema=schema,
    )
    ensure_metadata_indexes(
        engine,
        collection_name="fixture-recreate-indexes",
        schema=schema,
    )

    with engine.connect() as conn:
        second_collection_id = conn.execute(
            text("select id from collections where name = 'fixture-recreate-indexes'")
        ).scalar_one()
        year_index_name = conn.execute(
            text(
                """
                select indexname
                from pg_indexes
                where schemaname = current_schema()
                  and tablename = 'chunks'
                  and indexdef like '%->> ''year''%'
                  and indexname like 'ix_chunks_metadata_fixture_recreate_indexe_%'
                """
            )
        ).scalar_one()
        year_index_def = conn.execute(
            text(
                """
                select indexdef
                from pg_indexes
                where schemaname = current_schema()
                  and tablename = 'chunks'
                  and indexname = :index_name
                """
            ),
            {"index_name": year_index_name},
        ).scalar_one()

    assert first_collection_id != second_collection_id
    assert second_collection_id in year_index_def
    assert first_collection_id not in year_index_def
