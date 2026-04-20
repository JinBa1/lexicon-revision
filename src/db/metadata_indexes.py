from __future__ import annotations

import hashlib

from sqlalchemy import Engine, text
from src.metadata_schema.models import CollectionMetadataSchema, MetadataField


def metadata_field_index_name(
    collection_name: str,
    field_key: str,
    field_type: str,
) -> str:
    digest = hashlib.sha1(
        f"{collection_name}:{field_key}:{field_type}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    collection_prefix = _collection_name_prefix(collection_name)
    return f"ix_chunks_metadata_{collection_prefix}_{digest[:10]}"


def ensure_metadata_indexes(
    engine: Engine,
    *,
    collection_name: str,
    schema: CollectionMetadataSchema,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                create index if not exists ix_chunks_metadata_gin
                on chunks using gin (metadata)
                """
            )
        )
        collection_id = conn.execute(
            text("select id from collections where name = :collection_name"),
            {"collection_name": collection_name},
        ).scalar_one_or_none()
        if collection_id is None:
            raise ValueError(f"Collection '{collection_name}' does not exist")
        for field in schema.fields:
            conn.execute(text(_drop_index_sql(collection_name, field)))
            conn.execute(text(_field_index_sql(collection_name, field, collection_id)))


def _field_index_sql(
    collection_name: str,
    field: MetadataField,
    collection_id: str,
) -> str:
    index_name = metadata_field_index_name(collection_name, field.key, field.type)
    if field.type == "integer":
        expression = f"((metadata ->> '{field.key}')::integer)"
    elif field.type == "boolean":
        expression = f"((metadata ->> '{field.key}')::boolean)"
    else:
        expression = f"(metadata ->> '{field.key}')"
    return (
        f"create index {index_name} on chunks ({expression}) "
        f"where collection_id = {_sql_string_literal(collection_id)}"
    )


def _drop_index_sql(collection_name: str, field: MetadataField) -> str:
    index_name = metadata_field_index_name(collection_name, field.key, field.type)
    return f"drop index if exists {index_name}"


def _collection_name_prefix(collection_name: str) -> str:
    normalized = "".join(
        char if char.isalnum() else "_" for char in collection_name.lower()
    ).strip("_")
    return normalized[:24] or "collection"


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
