from __future__ import annotations

from dataclasses import fields as dataclass_fields
from functools import lru_cache
from typing import Annotated, Literal, get_args, get_origin, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from src.chunking.models import Chunk

MetadataType = Literal["string", "integer", "boolean"]
MetadataOperator = Literal["eq", "gte", "lte"]
MetadataScalar = int | bool | str
MetadataKey = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", min_length=1, strict=True),
]
SourcePath = Annotated[
    str,
    StringConstraints(pattern=r"^chunk\.[a-z_]+$", min_length=1, strict=True),
]


class MetadataField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: MetadataKey
    label: Annotated[str, StringConstraints(min_length=1, strict=True)]
    type: MetadataType
    operators: list[MetadataOperator] = Field(min_length=1)
    exposed: bool = True
    source: SourcePath | None = None


class CollectionMetadataSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    fields: list[MetadataField] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unique_keys(self) -> "CollectionMetadataSchema":
        seen: set[str] = set()
        for field in self.fields:
            if field.key in seen:
                raise ValueError(f"duplicate metadata field key: {field.key}")
            if field.source is not None:
                source_name = field.source.removeprefix("chunk.")
                source_type = _chunk_source_type(source_name)
                if source_type is None:
                    raise ValueError(
                        f"invalid chunk source path for {field.key}: {field.source}"
                    )
                if field.type != source_type:
                    raise ValueError(
                        "invalid chunk source/type combination for "
                        f"{field.key}: {field.type} does not match {field.source}"
                    )
            seen.add(field.key)
        return self

    def field(self, key: str) -> MetadataField:
        for field in self.fields:
            if field.key == key:
                return field
        raise KeyError(key)


class FilterCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: MetadataKey
    op: MetadataOperator
    value: MetadataScalar


@lru_cache(maxsize=1)
def _chunk_source_types() -> dict[str, MetadataType]:
    hints = get_type_hints(Chunk)
    source_types: dict[str, MetadataType] = {}
    for field in dataclass_fields(Chunk):
        metadata_type = _metadata_type_from_annotation(hints[field.name])
        if metadata_type is not None:
            source_types[field.name] = metadata_type
    return source_types


def _chunk_source_type(source_name: str) -> MetadataType | None:
    return _chunk_source_types().get(source_name)


def _metadata_type_from_annotation(annotation: object) -> MetadataType | None:
    if annotation is int:
        return "integer"
    if annotation is bool:
        return "boolean"
    if annotation is str:
        return "string"

    origin = get_origin(annotation)
    if origin is None:
        return None

    args = [arg for arg in get_args(annotation) if arg is not type(None)]
    if len(args) != 1:
        return None
    return _metadata_type_from_annotation(args[0])
