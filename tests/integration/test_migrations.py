from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text
from src.metadata_schema import default_schema_path, load_collection_schema

pytestmark = pytest.mark.integration


def _expected_legacy_schema() -> dict:
    return load_collection_schema(
        default_schema_path("cam-cs-tripos-fixture")
    ).model_dump(mode="json")


def test_alembic_upgrade_creates_retrieval_tables() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for pgvector integration tests")

    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    engine = create_engine(database_url, future=True)
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        assert {"collections", "papers", "chunks", "chunk_embeddings"} <= tables
        result = conn.execute(
            text("select 1 from pg_extension where extname = 'vector'")
        ).first()
        assert result is not None


def test_alembic_cutover_backfills_metadata_and_drops_legacy_columns() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for pgvector integration tests")

    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.downgrade(config, "base")
    command.upgrade(config, "20260418_0001")

    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into collections (
                        id, name, embedding_model_id, embedding_dimension
                    ) values (
                        'collection-1', 'fixture-migration', 'fake-v1', 8
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    insert into papers (id, collection_id, source_pdf)
                    values ('paper-1', 'collection-1', '2025_paper_1.pdf')
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
                        year,
                        paper,
                        question_number,
                        topic,
                        author,
                        tripos_part,
                        marks,
                        total_marks,
                        has_code,
                        has_figure,
                        has_table,
                        source_pdf
                    ) values (
                        'chunk-1',
                        'cam-2025-p1-q1',
                        'collection-1',
                        'paper-1',
                        'question',
                        null,
                        null,
                        'Test text',
                        2025,
                        1,
                        1,
                        'Algorithms',
                        'abc123',
                        'Part IB',
                        10,
                        20,
                        true,
                        false,
                        false,
                        '2025_paper_1.pdf'
                    )
                    """
                )
            )

        command.upgrade(config, "20260419_0002")

        with engine.connect() as conn:
            columns_after_cutover = {
                column["name"] for column in inspect(conn).get_columns("chunks")
            }
            collection_columns = {
                column["name"] for column in inspect(conn).get_columns("collections")
            }
            backfilled = conn.execute(
                text(
                    """
                    select metadata, metadata_schema
                    from chunks
                    join collections on chunks.collection_id = collections.id
                    where chunks.id = 'chunk-1'
                    """
                )
            ).first()

        assert "metadata" in columns_after_cutover
        assert "year" in columns_after_cutover
        assert "metadata_schema" in collection_columns
        assert backfilled is not None
        assert backfilled.metadata == {
            "year": 2025,
            "paper": 1,
            "question_number": 1,
            "topic": "Algorithms",
            "author": "abc123",
            "tripos_part": "Part IB",
            "marks": 10,
            "total_marks": 20,
            "has_code": True,
            "has_figure": False,
            "has_table": False,
        }
        assert backfilled.metadata_schema == _expected_legacy_schema()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            final_columns = {
                column["name"] for column in inspect(conn).get_columns("chunks")
            }
            final_row = conn.execute(
                text("select metadata from chunks where id = 'chunk-1'")
            ).first()

        assert "metadata" in final_columns
        assert "year" not in final_columns
        assert "paper" not in final_columns
        assert final_row is not None
        assert final_row.metadata["topic"] == "Algorithms"
    finally:
        command.upgrade(config, "head")
        engine.dispose()
