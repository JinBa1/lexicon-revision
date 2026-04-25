"""collection retrieval thresholds

Revision ID: 20260425_0008
Revises: 20260422_0007
Create Date: 2026-04-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260425_0008"
down_revision: Union[str, None] = "20260422_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("retrieval_vector_min_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "collections",
        sa.Column("retrieval_rerank_min_score", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("collections", "retrieval_rerank_min_score")
    op.drop_column("collections", "retrieval_vector_min_score")
