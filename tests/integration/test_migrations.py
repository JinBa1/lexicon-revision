from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.integration


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
