from __future__ import annotations

from src.metadata_schema.models import CollectionMetadataSchema
from src.metadata_schema.rendering import (
    iter_renderable_metadata_fields,
    render_metadata_lines,
    render_metadata_summary,
)


def _schema() -> CollectionMetadataSchema:
    return CollectionMetadataSchema.model_validate(
        {
            "version": 1,
            "fields": [
                {
                    "key": "year",
                    "label": "Year",
                    "type": "integer",
                    "operators": ["eq"],
                    "exposed": False,
                },
                {
                    "key": "author",
                    "label": "Author",
                    "type": "string",
                    "operators": ["eq"],
                    "exposed": True,
                },
                {
                    "key": "tripos_part",
                    "label": "Tripos Part",
                    "type": "string",
                    "operators": ["eq"],
                    "exposed": True,
                },
            ],
        }
    )


def test_iter_renderable_metadata_fields_uses_exposed_schema_order() -> None:
    rendered = list(
        iter_renderable_metadata_fields(
            _schema(),
            {
                "year": 2024,
                "author": "abc123",
                "tripos_part": "Part IB",
            },
        )
    )

    assert rendered == [
        ("author", "Author", "abc123"),
        ("tripos_part", "Tripos Part", "Part IB"),
    ]


def test_render_metadata_summary_uses_schema_labels() -> None:
    rendered = render_metadata_summary(
        _schema(),
        {
            "year": 2024,
            "author": "abc123",
            "tripos_part": "Part IB",
        },
    )

    assert rendered == "Author: abc123 | Tripos Part: Part IB"


def test_render_metadata_lines_uses_schema_labels() -> None:
    rendered = render_metadata_lines(
        _schema(),
        {
            "year": 2024,
            "author": "abc123",
            "tripos_part": "Part IB",
        },
    )

    assert rendered == ["Author: abc123", "Tripos Part: Part IB"]
