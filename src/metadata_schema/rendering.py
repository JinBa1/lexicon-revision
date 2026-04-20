from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from src.metadata_schema.models import CollectionMetadataSchema


def iter_renderable_metadata_fields(
    schema: CollectionMetadataSchema,
    metadata: dict[str, Any],
) -> Iterator[tuple[str, str, str]]:
    for field in schema.fields:
        if not field.exposed:
            continue
        value = metadata.get(field.key)
        if value is None:
            continue
        yield field.key, field.label, _stringify_metadata_value(value)


def render_metadata_summary(
    schema: CollectionMetadataSchema,
    metadata: dict[str, Any],
) -> str:
    return " | ".join(
        f"{label}: {value}"
        for _, label, value in iter_renderable_metadata_fields(schema, metadata)
    )


def render_metadata_lines(
    schema: CollectionMetadataSchema,
    metadata: dict[str, Any],
) -> list[str]:
    return [
        f"{label}: {value}"
        for _, label, value in iter_renderable_metadata_fields(schema, metadata)
    ]


def _stringify_metadata_value(value: Any) -> str:
    if type(value) is bool:
        return "true" if value else "false"
    return str(value)
