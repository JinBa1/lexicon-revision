from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from src.db.schema import chunk_embeddings, chunks, collections, metadata, papers


def test_schema_has_expected_tables() -> None:
    assert set(metadata.tables) == {
        "collections",
        "papers",
        "chunks",
        "chunk_embeddings",
    }


def test_collections_embedding_columns() -> None:
    assert "embedding_model_id" in collections.c
    assert "embedding_dimension" in collections.c
    assert "metadata_schema" in collections.c
    assert isinstance(collections.c.metadata_schema.type, JSONB)
    assert collections.c.metadata_schema.server_default is None


def test_chunks_use_canonical_metadata_jsonb_column() -> None:
    assert "metadata" in chunks.c
    assert isinstance(chunks.c.metadata.type, JSONB)


def test_chunks_drop_legacy_filter_columns() -> None:
    for name in (
        "year",
        "paper",
        "question_number",
        "topic",
        "author",
        "tripos_part",
        "marks",
        "total_marks",
        "has_code",
        "has_figure",
        "has_table",
    ):
        assert name not in chunks.c


def test_chunks_use_internal_primary_key_with_collection_scoped_chunk_ids() -> None:
    pk_columns = {column.name for column in chunks.primary_key.columns}
    assert pk_columns == {"id"}

    unique_constraints = {
        constraint.name: {column.name for column in constraint.columns}
        for constraint in chunks.constraints
        if constraint.name is not None
    }
    assert unique_constraints["uq_chunks_collection_chunk_id"] == {
        "collection_id",
        "chunk_id",
    }


def test_chunk_embeddings_primary_key() -> None:
    pk_columns = {column.name for column in chunk_embeddings.primary_key.columns}
    assert pk_columns == {"chunk_id", "embedding_model_id"}


def test_chunk_embeddings_chunk_id_matches_chunks_id_type() -> None:
    assert type(chunk_embeddings.c.chunk_id.type) is String


def test_papers_unique_collection_source_pdf_constraint() -> None:
    constraints = {constraint.name for constraint in papers.constraints}
    assert "uq_papers_collection_source_pdf" in constraints
