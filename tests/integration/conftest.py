from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text


@pytest.fixture(autouse=True)
def _clean_pg(request: pytest.FixtureRequest) -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        return
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as conn:
            existing = set(inspect(conn).get_table_names())
            for table in (
                "chunk_embeddings",
                "chunks",
                "papers",
                "community_memberships",
                "collections",
                "user_external_identities",
                "users",
                "communities",
            ):
                if table in existing:
                    conn.execute(text(f"DELETE FROM {table}"))
            conn.commit()
    finally:
        engine.dispose()
