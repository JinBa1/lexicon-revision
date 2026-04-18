from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

metadata = MetaData()

collections = Table(
    "collections",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column("name", Text, nullable=False, unique=True),
    Column("embedding_model_id", Text, nullable=False),
    Column("embedding_dimension", Integer, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(
        "embedding_dimension > 0",
        name="ck_collections_embedding_dimension_positive",
    ),
)

papers = Table(
    "papers",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column(
        "collection_id",
        String,
        ForeignKey("collections.id"),
        nullable=False,
    ),
    Column("source_pdf", Text, nullable=False),
    Column("title", Text, nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint(
        "collection_id",
        "source_pdf",
        name="uq_papers_collection_source_pdf",
    ),
)

chunks = Table(
    "chunks",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column("chunk_id", Text, nullable=False),
    Column(
        "collection_id",
        String,
        ForeignKey("collections.id"),
        nullable=False,
    ),
    Column("paper_id", String, ForeignKey("papers.id"), nullable=False),
    Column("chunk_level", Text, nullable=False),
    Column("parent_chunk_id", Text, nullable=True),
    Column("sub_question_label", Text, nullable=True),
    Column("text", Text, nullable=False),
    Column("year", Integer, nullable=True),
    Column("paper", Integer, nullable=True),
    Column("question_number", Integer, nullable=True),
    Column("topic", Text, nullable=True),
    Column("author", Text, nullable=True),
    Column("tripos_part", Text, nullable=True),
    Column("marks", Integer, nullable=True),
    Column("total_marks", Integer, nullable=True),
    Column("has_code", Boolean, nullable=False),
    Column("has_figure", Boolean, nullable=False),
    Column("has_table", Boolean, nullable=False),
    Column("source_pdf", Text, nullable=False),
    UniqueConstraint(
        "collection_id",
        "chunk_id",
        name="uq_chunks_collection_chunk_id",
    ),
)

Index("ix_chunks_collection_year", chunks.c.collection_id, chunks.c.year)

chunk_embeddings = Table(
    "chunk_embeddings",
    metadata,
    Column(
        "chunk_id",
        Text,
        ForeignKey("chunks.id"),
        nullable=False,
    ),
    Column("embedding_model_id", Text, nullable=False),
    # Column is unsized so collections with different embedding dimensions can
    # coexist; the canonical dimension lives in collections.embedding_dimension
    # and is enforced by the indexing/search paths.
    Column("embedding", Vector(), nullable=False),
    PrimaryKeyConstraint("chunk_id", "embedding_model_id"),
)
