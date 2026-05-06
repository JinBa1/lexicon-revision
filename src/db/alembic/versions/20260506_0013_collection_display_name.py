"""collection display name

Revision ID: 20260506_0013
Revises: 20260505_0012
Create Date: 2026-05-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260506_0013"
down_revision: Union[str, None] = "20260505_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("collections", sa.Column("display_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("collections", "display_name")
