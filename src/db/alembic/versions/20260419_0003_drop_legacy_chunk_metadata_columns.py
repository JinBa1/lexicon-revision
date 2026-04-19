"""drop legacy chunk metadata columns

Revision ID: 20260419_0003
Revises: 20260419_0002
Create Date: 2026-04-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260419_0003"
down_revision: Union[str, None] = "20260419_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_METADATA_COLUMNS = (
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
)


def upgrade() -> None:
    op.drop_index("ix_chunks_collection_year", table_name="chunks")
    for column_name in LEGACY_METADATA_COLUMNS:
        op.drop_column("chunks", column_name)


def downgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "has_table", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "has_figure", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "has_code", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column("chunks", sa.Column("total_marks", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("marks", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("tripos_part", sa.Text(), nullable=True))
    op.add_column("chunks", sa.Column("author", sa.Text(), nullable=True))
    op.add_column("chunks", sa.Column("topic", sa.Text(), nullable=True))
    op.add_column("chunks", sa.Column("question_number", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("paper", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("year", sa.Integer(), nullable=True))
    op.execute(
        """
        update chunks
        set
            year = (metadata ->> 'year')::integer,
            paper = (metadata ->> 'paper')::integer,
            question_number = (metadata ->> 'question_number')::integer,
            topic = metadata ->> 'topic',
            author = metadata ->> 'author',
            tripos_part = metadata ->> 'tripos_part',
            marks = (metadata ->> 'marks')::integer,
            total_marks = (metadata ->> 'total_marks')::integer,
            has_code = coalesce((metadata ->> 'has_code')::boolean, false),
            has_figure = coalesce((metadata ->> 'has_figure')::boolean, false),
            has_table = coalesce((metadata ->> 'has_table')::boolean, false)
        """
    )
    op.alter_column("chunks", "has_code", server_default=None)
    op.alter_column("chunks", "has_figure", server_default=None)
    op.alter_column("chunks", "has_table", server_default=None)
    op.create_index("ix_chunks_collection_year", "chunks", ["collection_id", "year"])
