from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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
