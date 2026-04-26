"""edinburgh community seed

Revision ID: 20260426_0010
Revises: 20260426_0009
Create Date: 2026-04-26

"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260426_0010"
down_revision: Union[str, None] = "20260426_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO communities (id, name, slug)
        VALUES ('edinburgh', 'Edinburgh', 'edinburgh')
        ON CONFLICT (id) DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO community_email_domains
            (id, community_id, domain, match_mode, is_active)
        VALUES
            ('edinburgh-ed-ac-uk', 'edinburgh', 'ed.ac.uk', 'suffix', true)
        ON CONFLICT (community_id, domain) DO UPDATE
            SET match_mode = EXCLUDED.match_mode,
                is_active = EXCLUDED.is_active;
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM community_email_domains WHERE id = 'edinburgh-ed-ac-uk';")
    op.execute("DELETE FROM communities WHERE id = 'edinburgh';")
