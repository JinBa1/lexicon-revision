from __future__ import annotations

import hashlib

from sqlalchemy import Engine, text
from src.metadata_schema.models import CollectionMetadataSchema, MetadataField


def metadata_field_index_name(field_key: str) -> str:
    digest = hashlib.sha1(
        field_key.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    return f"ix_chunks_metadata_{digest[:10]}"


def ensure_metadata_indexes(engine: Engine, schema: CollectionMetadataSchema) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                create index if not exists ix_chunks_metadata_gin
                on chunks using gin (metadata)
                """
            )
        )
        for field in schema.fields:
            conn.execute(text(_field_index_sql(field)))


def _field_index_sql(field: MetadataField) -> str:
    index_name = metadata_field_index_name(field.key)
    if field.type == "integer":
        expression = f"((metadata ->> '{field.key}')::integer)"
    elif field.type == "boolean":
        expression = f"((metadata ->> '{field.key}')::boolean)"
    else:
        expression = f"(metadata ->> '{field.key}')"
    return f"create index if not exists {index_name} on chunks ({expression})"
