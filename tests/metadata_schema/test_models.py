from pathlib import Path

import pytest
from src.metadata_schema.loader import default_schema_path, load_collection_schema
from src.metadata_schema.models import CollectionMetadataSchema, FilterCondition


def test_load_collection_schema_reads_repo_owned_json(tmp_path: Path) -> None:
    path = tmp_path / "fixture.metadata-schema.json"
    path.write_text(
        """
        {
          "version": 1,
          "fields": [
            {
              "key": "year",
              "label": "Year",
              "type": "integer",
              "operators": ["eq", "gte", "lte"],
              "exposed": true,
              "source": "chunk.year"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    schema = load_collection_schema(path)

    assert schema.version == 1
    assert schema.field("year").source == "chunk.year"


def test_collection_schema_rejects_duplicate_field_keys() -> None:
    with pytest.raises(ValueError, match="duplicate metadata field key"):
        CollectionMetadataSchema.model_validate(
            {
                "version": 1,
                "fields": [
                    {
                        "key": "year",
                        "label": "Year",
                        "type": "integer",
                        "operators": ["eq"],
                        "exposed": True,
                    },
                    {
                        "key": "year",
                        "label": "Duplicate Year",
                        "type": "integer",
                        "operators": ["eq"],
                        "exposed": True,
                    },
                ],
            }
        )


def test_filter_condition_accepts_repeated_range_filters() -> None:
    filters = [
        FilterCondition(field="year", op="gte", value=2020),
        FilterCondition(field="year", op="lte", value=2024),
    ]

    assert [item.model_dump() for item in filters] == [
        {"field": "year", "op": "gte", "value": 2020},
        {"field": "year", "op": "lte", "value": 2024},
    ]


def test_default_schema_path_uses_collection_name() -> None:
    path = default_schema_path("cam-cs-tripos-fixture")
    assert str(path).endswith(
        "config/collections/cam-cs-tripos-fixture.metadata-schema.json"
    )
