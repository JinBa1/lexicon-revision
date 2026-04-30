"""cambridge community seed

Revision ID: 20260430_0011
Revises: 20260426_0010
Create Date: 2026-04-30

"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260430_0011"
down_revision: Union[str, None] = "20260426_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO communities (id, name, slug)
        VALUES ('cambridge', 'Cambridge', 'cambridge')
        ON CONFLICT (id) DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO community_email_domains
            (id, community_id, domain, match_mode, is_active)
        VALUES
            ('cambridge-cam-ac-uk', 'cambridge', 'cam.ac.uk', 'suffix', true)
        ON CONFLICT (community_id, domain) DO UPDATE
            SET match_mode = EXCLUDED.match_mode,
                is_active = EXCLUDED.is_active;
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM community_email_domains "
        "WHERE community_id = 'cambridge' AND domain = 'cam.ac.uk';"
    )
    op.execute("DELETE FROM communities WHERE id = 'cambridge';")
