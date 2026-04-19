"""metadata schema cutover

Revision ID: 20260419_0002
Revises: 20260418_0001
Create Date: 2026-04-19

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260419_0002"
down_revision: Union[str, None] = "20260418_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_ACADEMIC_METADATA_SCHEMA = {
    "version": 1,
    "fields": [
        {
            "key": "year",
            "label": "Year",
            "type": "integer",
            "operators": ["eq", "gte", "lte"],
            "exposed": True,
            "source": "chunk.year",
        },
        {
            "key": "paper",
            "label": "Paper",
            "type": "integer",
            "operators": ["eq", "gte", "lte"],
            "exposed": True,
            "source": "chunk.paper",
        },
        {
            "key": "question_number",
            "label": "Question",
            "type": "integer",
            "operators": ["eq", "gte", "lte"],
            "exposed": True,
            "source": "chunk.question_number",
        },
        {
            "key": "topic",
            "label": "Topic",
            "type": "string",
            "operators": ["eq"],
            "exposed": True,
            "source": "chunk.topic",
        },
        {
            "key": "author",
            "label": "Author",
            "type": "string",
            "operators": ["eq"],
            "exposed": False,
            "source": "chunk.author",
        },
        {
            "key": "tripos_part",
            "label": "Tripos Part",
            "type": "string",
            "operators": ["eq"],
            "exposed": True,
            "source": "chunk.tripos_part",
        },
        {
            "key": "marks",
            "label": "Marks",
            "type": "integer",
            "operators": ["eq", "gte", "lte"],
            "exposed": True,
            "source": "chunk.marks",
        },
        {
            "key": "total_marks",
            "label": "Total Marks",
            "type": "integer",
            "operators": ["eq", "gte", "lte"],
            "exposed": False,
            "source": "chunk.total_marks",
        },
        {
            "key": "has_code",
            "label": "Has Code",
            "type": "boolean",
            "operators": ["eq"],
            "exposed": True,
            "source": "chunk.has_code",
        },
        {
            "key": "has_figure",
            "label": "Has Figure",
            "type": "boolean",
            "operators": ["eq"],
            "exposed": True,
            "source": "chunk.has_figure",
        },
        {
            "key": "has_table",
            "label": "Has Table",
            "type": "boolean",
            "operators": ["eq"],
            "exposed": True,
            "source": "chunk.has_table",
        },
    ],
}


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
        sa.text(
            """
            update collections
            set metadata_schema = cast(:metadata_schema as jsonb)
            """
        ).bindparams(
            metadata_schema=json.dumps(
                LEGACY_ACADEMIC_METADATA_SCHEMA,
                separators=(",", ":"),
            )
        )
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
