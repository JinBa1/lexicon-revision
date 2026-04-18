"""pgvector retrieval tables

Revision ID: 20260418_0001
Revises: None
Create Date: 2026-04-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260418_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "collections",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("embedding_model_id", sa.Text, nullable=False),
        sa.Column("embedding_dimension", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "embedding_dimension > 0",
            name="ck_collections_embedding_dimension_positive",
        ),
    )

    op.create_table(
        "papers",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column(
            "collection_id",
            sa.String,
            sa.ForeignKey("collections.id"),
            nullable=False,
        ),
        sa.Column("source_pdf", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "collection_id",
            "source_pdf",
            name="uq_papers_collection_source_pdf",
        ),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("chunk_id", sa.Text, nullable=False),
        sa.Column(
            "collection_id",
            sa.String,
            sa.ForeignKey("collections.id"),
            nullable=False,
        ),
        sa.Column(
            "paper_id",
            sa.String,
            sa.ForeignKey("papers.id"),
            nullable=False,
        ),
        sa.Column("chunk_level", sa.Text, nullable=False),
        sa.Column("parent_chunk_id", sa.Text, nullable=True),
        sa.Column("sub_question_label", sa.Text, nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("paper", sa.Integer, nullable=True),
        sa.Column("question_number", sa.Integer, nullable=True),
        sa.Column("topic", sa.Text, nullable=True),
        sa.Column("author", sa.Text, nullable=True),
        sa.Column("tripos_part", sa.Text, nullable=True),
        sa.Column("marks", sa.Integer, nullable=True),
        sa.Column("total_marks", sa.Integer, nullable=True),
        sa.Column("has_code", sa.Boolean, nullable=False),
        sa.Column("has_figure", sa.Boolean, nullable=False),
        sa.Column("has_table", sa.Boolean, nullable=False),
        sa.Column("source_pdf", sa.Text, nullable=False),
        sa.UniqueConstraint(
            "collection_id",
            "chunk_id",
            name="uq_chunks_collection_chunk_id",
        ),
    )

    op.create_index(
        "ix_chunks_collection_year",
        "chunks",
        ["collection_id", "year"],
    )

    op.create_table(
        "chunk_embeddings",
        sa.Column(
            "chunk_id",
            sa.String,
            sa.ForeignKey("chunks.id"),
            nullable=False,
        ),
        sa.Column("embedding_model_id", sa.Text, nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.PrimaryKeyConstraint("chunk_id", "embedding_model_id"),
    )


def downgrade() -> None:
    op.drop_table("chunk_embeddings")
    op.drop_index("ix_chunks_collection_year", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("papers")
    op.drop_table("collections")
