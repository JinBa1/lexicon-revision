"""collection access model

Revision ID: 20260420_0004
Revises: 20260419_0003
Create Date: 2026-04-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260420_0004"
down_revision: Union[str, None] = "20260419_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "communities",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_communities_name"),
    )

    op.create_table(
        "community_memberships",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("community_id", sa.String(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["community_id"],
            ["communities.id"],
            name="fk_community_memberships_community_id_communities",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_community_memberships_user_id_users",
        ),
        sa.UniqueConstraint(
            "user_id",
            "community_id",
            name="uq_community_memberships_user_community",
        ),
    )

    op.add_column(
        "collections",
        sa.Column("community_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_collections_community_id_communities",
        "collections",
        "communities",
        ["community_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_collections_community_id_communities",
        "collections",
        type_="foreignkey",
    )
    op.drop_column("collections", "community_id")
    op.drop_table("community_memberships")
    op.drop_table("communities")
    op.drop_table("users")
