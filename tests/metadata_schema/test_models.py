from pathlib import Path

import pytest
from pydantic import TypeAdapter
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
    filters = TypeAdapter(list[FilterCondition]).validate_python(
        [
            {"field": "year", "op": "gte", "value": 2020},
            {"field": "year", "op": "lte", "value": 2024},
        ]
    )

    assert [item.field for item in filters] == ["year", "year"]
    assert [item.op for item in filters] == ["gte", "lte"]
    assert [item.model_dump() for item in filters] == [
        {"field": "year", "op": "gte", "value": 2020},
        {"field": "year", "op": "lte", "value": 2024},
    ]


def test_default_schema_path_uses_collection_name() -> None:
    path = default_schema_path("cam-cs-tripos-fixture")
    assert path.is_file()

    schema = load_collection_schema(path)

    assert schema.version == 1
    assert [field.key for field in schema.fields] == [
        "year",
        "paper",
        "question_number",
        "topic",
        "author",
        "tripos_part",
        "marks",
        "total_marks",
        "has_code",
        "has_figure",
        "has_table",
    ]


def test_collection_schema_rejects_invalid_source_paths() -> None:
    with pytest.raises(ValueError, match="invalid chunk source path"):
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
                        "source": "chunk.typo",
                    }
                ],
            }
        )


def test_collection_schema_accepts_generic_metadata_source_paths() -> None:
    schema = CollectionMetadataSchema.model_validate(
        {
            "version": 1,
            "fields": [
                {
                    "key": "course_code",
                    "label": "Course Code",
                    "type": "string",
                    "operators": ["eq"],
                    "exposed": True,
                    "source": "chunk.metadata.course_code",
                }
            ],
        }
    )

    assert schema.field("course_code").source == "chunk.metadata.course_code"


def test_collection_schema_rejects_malformed_metadata_source_path() -> None:
    with pytest.raises(ValueError):
        CollectionMetadataSchema.model_validate(
            {
                "version": 1,
                "fields": [
                    {
                        "key": "course_code",
                        "label": "Course Code",
                        "type": "string",
                        "operators": ["eq"],
                        "exposed": True,
                        "source": "chunk.metadata.CourseCode",
                    }
                ],
            }
        )


def test_load_collection_schema_rejects_incompatible_source_types(
    tmp_path: Path,
) -> None:
    path = tmp_path / "broken.metadata-schema.json"
    path.write_text(
        """
        {
          "version": 1,
          "fields": [
            {
              "key": "topic",
              "label": "Topic",
              "type": "integer",
              "operators": ["eq"],
              "exposed": true,
              "source": "chunk.topic"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid chunk source/type combination"):
        load_collection_schema(path)
