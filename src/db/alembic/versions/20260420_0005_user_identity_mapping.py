"""user identity mapping

Revision ID: 20260420_0005
Revises: 20260420_0004
Create Date: 2026-04-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260420_0005"
down_revision: Union[str, None] = "20260420_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_table(
        "user_external_identities",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_subject", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_external_identities_user_id_users",
        ),
        sa.UniqueConstraint(
            "provider",
            "external_subject",
            name="uq_user_external_identities_provider_subject",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_external_identities")
    op.drop_column("users", "email_verified")
