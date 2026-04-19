"""metadata schema cutover

Revision ID: 20260419_0002
Revises: 20260418_0001
Create Date: 2026-04-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260419_0002"
down_revision: Union[str, None] = "20260418_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column(
            "metadata_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        """
        update chunks
        set metadata = jsonb_strip_nulls(
            jsonb_build_object(
                'year', year,
                'paper', paper,
                'question_number', question_number,
                'topic', topic,
                'author', author,
                'tripos_part', tripos_part,
                'marks', marks,
                'total_marks', total_marks,
                'has_code', has_code,
                'has_figure', has_figure,
                'has_table', has_table
            )
        )
        """
    )


def downgrade() -> None:
    op.drop_column("chunks", "metadata")
    op.drop_column("collections", "metadata_schema")
