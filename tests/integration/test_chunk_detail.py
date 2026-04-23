from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from src.search.errors import CollectionNotFoundError
from src.search.pg_repository import PgSearchRepository

pytestmark = pytest.mark.integration


def _engine():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for integration tests")
    return create_engine(database_url, future=True)


def _delete_collection_if_present(engine, *, name: str) -> None:
    with engine.begin() as conn:
        collection_row = conn.execute(
            text("SELECT id FROM collections WHERE name = :name"),
            {"name": name},
        ).first()
        if collection_row is None:
            return

        collection_id = str(collection_row.id)
        conn.execute(
            text(
                """
                DELETE FROM chunk_embeddings
                WHERE chunk_id IN (
                    SELECT id FROM chunks WHERE collection_id = :collection_id
                )
                """
            ),
            {"collection_id": collection_id},
        )
        conn.execute(
            text("DELETE FROM chunks WHERE collection_id = :collection_id"),
            {"collection_id": collection_id},
        )
        conn.execute(
            text("DELETE FROM papers WHERE collection_id = :collection_id"),
            {"collection_id": collection_id},
        )
        conn.execute(
            text("DELETE FROM collections WHERE id = :collection_id"),
            {"collection_id": collection_id},
        )


def _seed_collection(engine, *, name: str) -> str:
    schema = {
        "version": 1,
        "fields": [
            {"key": "year", "label": "Year", "type": "integer", "operators": ["eq"]}
        ],
    }
    collection_id = str(uuid.uuid4())
    _delete_collection_if_present(engine, name=name)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO collections "
                "(id, name, community_id, embedding_model_id, "
                "embedding_dimension, metadata_schema) "
                "VALUES (:id, :name, NULL, 'test-model', 3, CAST(:schema AS JSONB))"
            ),
            {"id": collection_id, "name": name, "schema": json.dumps(schema)},
        )
    return collection_id


def _seed_paper(engine, *, collection_id: str, source_pdf: str) -> str:
    paper_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO papers (id, collection_id, source_pdf) "
                "VALUES (:id, :cid, :pdf)"
            ),
            {"id": paper_id, "cid": collection_id, "pdf": source_pdf},
        )
    return paper_id


def _seed_chunk(
    engine,
    *,
    chunk_id: str,
    collection_id: str,
    paper_id: str,
    chunk_level: str,
    parent_chunk_id: str | None,
    sub_question_label: str | None,
    text_value: str,
    metadata: dict[str, object],
    source_pdf: str,
) -> None:
    chunk_row_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO chunks "
                "(id, chunk_id, collection_id, paper_id, chunk_level, "
                "parent_chunk_id, sub_question_label, text, metadata, source_pdf) "
                "VALUES ("
                ":id, :chunk_id, :collection_id, :paper_id, :chunk_level, "
                ":parent_chunk_id, :sub_question_label, :text_value, "
                "CAST(:metadata AS JSONB), :source_pdf)"
            ),
            {
                "id": chunk_row_id,
                "chunk_id": chunk_id,
                "collection_id": collection_id,
                "paper_id": paper_id,
                "chunk_level": chunk_level,
                "parent_chunk_id": parent_chunk_id,
                "sub_question_label": sub_question_label,
                "text_value": text_value,
                "metadata": json.dumps(metadata),
                "source_pdf": source_pdf,
            },
        )


def test_get_chunk_by_id_returns_question_chunk_with_schema_metadata() -> None:
    engine = _engine()
    collection_id = _seed_collection(engine, name="demo")
    paper_id = _seed_paper(engine, collection_id=collection_id, source_pdf="p.pdf")
    _seed_chunk(
        engine,
        chunk_id="q-1",
        collection_id=collection_id,
        paper_id=paper_id,
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        text_value="question text",
        metadata={"year": 2022, "unknown": "drop-me"},
        source_pdf="p.pdf",
    )

    repo = PgSearchRepository(engine=engine)
    row = repo.get_chunk_by_id(collection_name="demo", chunk_id="q-1")

    assert row is not None
    assert row.chunk_level == "question"
    assert row.parent is None
    assert row.text == "question text"
    assert row.metadata == {"year": 2022}


def test_get_chunk_by_id_returns_sub_question_with_parent_context() -> None:
    engine = _engine()
    collection_id = _seed_collection(engine, name="demo")
    paper_id = _seed_paper(engine, collection_id=collection_id, source_pdf="p.pdf")
    _seed_chunk(
        engine,
        chunk_id="q-1",
        collection_id=collection_id,
        paper_id=paper_id,
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        text_value="parent question text",
        metadata={"year": 2022, "unknown": "drop-me"},
        source_pdf="p.pdf",
    )
    _seed_chunk(
        engine,
        chunk_id="q-1-a",
        collection_id=collection_id,
        paper_id=paper_id,
        chunk_level="sub_question",
        parent_chunk_id="q-1",
        sub_question_label="(a)",
        text_value="child text",
        metadata={"year": 2022, "unknown": "drop-me"},
        source_pdf="p.pdf",
    )

    repo = PgSearchRepository(engine=engine)
    row = repo.get_chunk_by_id(collection_name="demo", chunk_id="q-1-a")

    assert row is not None
    assert row.parent is not None
    assert row.parent.text == "parent question text"
    assert row.parent.metadata == {"year": 2022}


def test_get_chunk_by_id_returns_none_when_chunk_missing() -> None:
    engine = _engine()
    collection_id = _seed_collection(engine, name="demo")
    _seed_paper(engine, collection_id=collection_id, source_pdf="p.pdf")

    repo = PgSearchRepository(engine=engine)

    assert repo.get_chunk_by_id(collection_name="demo", chunk_id="missing") is None


def test_get_chunk_by_id_raises_when_collection_missing() -> None:
    engine = _engine()
    _delete_collection_if_present(engine, name="missing-collection")
    repo = PgSearchRepository(engine=engine)

    with pytest.raises(CollectionNotFoundError, match="missing-collection"):
        repo.get_chunk_by_id(collection_name="missing-collection", chunk_id="q-1")
