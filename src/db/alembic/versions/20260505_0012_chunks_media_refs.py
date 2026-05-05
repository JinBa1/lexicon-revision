"""chunks media refs

Rollout note: existing chunk rows are backfilled with ``media_refs = []``. A
database upgraded with this migration must reindex collections in the same
deployment step to preserve media in search and chunk-detail API responses.

Revision ID: 20260505_0012
Revises: 20260430_0011
Create Date: 2026-05-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260505_0012"
down_revision: Union[str, None] = "20260430_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "media_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("chunks", "media_refs")
