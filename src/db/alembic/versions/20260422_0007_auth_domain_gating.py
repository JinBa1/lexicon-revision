"""auth domain gating

Revision ID: 20260422_0007
Revises: 20260421_0006
Create Date: 2026-04-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260422_0007"
down_revision: Union[str, None] = "20260421_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "community_email_domains",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("community_id", sa.String(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("match_mode", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "domain = lower(btrim(domain))",
            name="ck_community_email_domains_domain_lowercase",
        ),
        sa.CheckConstraint(
            "match_mode IN ('exact', 'suffix')",
            name="ck_community_email_domains_match_mode_valid",
        ),
        sa.ForeignKeyConstraint(
            ["community_id"],
            ["communities.id"],
            name="fk_community_email_domains_community_id_communities",
        ),
        sa.UniqueConstraint(
            "community_id",
            "domain",
            name="uq_community_email_domains_community_domain",
        ),
    )

    op.create_table(
        "manual_access_overrides",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("community_id", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "email = lower(btrim(email))",
            name="ck_manual_access_overrides_email_lowercase",
        ),
        sa.ForeignKeyConstraint(
            ["community_id"],
            ["communities.id"],
            name="fk_manual_access_overrides_community_id_communities",
        ),
    )
    op.create_index(
        "uq_manual_access_overrides_active_email",
        "manual_access_overrides",
        ["email"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_manual_access_overrides_active_email",
        table_name="manual_access_overrides",
    )
    op.drop_table("manual_access_overrides")
    op.drop_table("community_email_domains")
