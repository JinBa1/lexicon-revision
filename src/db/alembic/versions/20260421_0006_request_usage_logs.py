"""request usage logs

Revision ID: 20260421_0006
Revises: 20260420_0005
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260421_0006"
down_revision: Union[str, None] = "20260420_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "request_usage_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("collection_name", sa.Text(), nullable=False),
        sa.Column("app_user_id", sa.String(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rerank", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("planning", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "generation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["users.id"],
            name="fk_request_usage_logs_app_user_id_users",
        ),
        sa.UniqueConstraint(
            "request_id",
            name="uq_request_usage_logs_request_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("request_usage_logs")
