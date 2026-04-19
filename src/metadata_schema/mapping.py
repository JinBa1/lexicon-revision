from __future__ import annotations

from typing import Any

from src.chunking.models import Chunk
from src.metadata_schema.models import CollectionMetadataSchema


def build_chunk_metadata(
    chunk: Chunk,
    schema: CollectionMetadataSchema,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for field in schema.fields:
        if field.source is None:
            continue
        attr_name = field.source.removeprefix("chunk.")
        value = getattr(chunk, attr_name)
        if value is None:
            continue
        _validate_value_type(field.key, field.type, value)
        metadata[field.key] = value
    return metadata


def _validate_value_type(key: str, expected_type: str, value: Any) -> None:
    if expected_type == "integer" and type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    if expected_type == "boolean" and type(value) is not bool:
        raise ValueError(f"{key} must be a boolean")
    if expected_type == "string" and type(value) is not str:
        raise ValueError(f"{key} must be a string")
