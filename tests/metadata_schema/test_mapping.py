import pytest
from src.chunking.models import Chunk
from src.metadata_schema.mapping import build_chunk_metadata
from src.metadata_schema.models import CollectionMetadataSchema


def _schema() -> CollectionMetadataSchema:
    return CollectionMetadataSchema.model_validate(
        {
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
                    "key": "has_code",
                    "label": "Has Code",
                    "type": "boolean",
                    "operators": ["eq"],
                    "exposed": True,
                    "source": "chunk.has_code",
                },
                {
                    "key": "topic",
                    "label": "Topic",
                    "type": "string",
                    "operators": ["eq"],
                    "exposed": True,
                    "source": "chunk.topic",
                },
            ],
        }
    )


def _chunk() -> Chunk:
    return Chunk(
        id="cam-2024-p2-q5",
        chunk_level="question",
        parent_chunk_id=None,
        text="Binary search trees support efficient lookup.",
        year=2024,
        paper=2,
        question_number=5,
        topic="Algorithms",
        author="abc123",
        tripos_part="Part IB",
        sub_question_label=None,
        marks=10,
        total_marks=20,
        has_code=True,
        has_figure=False,
        has_table=False,
        media=[],
        source_pdf="y2024p2.pdf",
        warnings=[],
    )


def test_build_chunk_metadata_uses_schema_sources() -> None:
    metadata = build_chunk_metadata(_chunk(), _schema())

    assert metadata == {
        "year": 2024,
        "has_code": True,
        "topic": "Algorithms",
    }


def test_build_chunk_metadata_rejects_type_mismatch() -> None:
    chunk = _chunk()
    chunk.topic = 123  # type: ignore[assignment]

    with pytest.raises(ValueError, match="topic"):
        build_chunk_metadata(chunk, _schema())


def test_build_chunk_metadata_reads_generic_metadata_source() -> None:
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
    chunk = _chunk()
    chunk.metadata = {"course_code": "MECE10017"}

    assert build_chunk_metadata(chunk, schema) == {"course_code": "MECE10017"}


def test_build_chunk_metadata_omits_missing_generic_metadata_source() -> None:
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

    assert build_chunk_metadata(_chunk(), schema) == {}


def test_build_chunk_metadata_rejects_generic_metadata_type_mismatch() -> None:
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
    chunk = _chunk()
    chunk.metadata = {"course_code": 10017}

    with pytest.raises(ValueError, match="course_code"):
        build_chunk_metadata(chunk, schema)
