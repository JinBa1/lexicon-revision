from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Boolean, Integer, cast
from src.db.schema import chunks as chunks_table
from src.metadata_schema.models import CollectionMetadataSchema, FilterCondition
from src.search.errors import InvalidMetadataFilterError

_STRUCTURAL_FILTER_FIELDS: dict[str, dict[str, Any]] = {
    "source_pdf": {
        "type": "string",
        "operators": {"eq"},
        "expression": chunks_table.c.source_pdf,
    },
    "chunk_level": {
        "type": "string",
        "operators": {"eq"},
        "expression": chunks_table.c.chunk_level,
    },
}


def validate_filter_conditions(
    filters: list[FilterCondition] | None,
    schema: CollectionMetadataSchema,
) -> list[FilterCondition]:
    normalized = filters or []
    for item in normalized:
        structural_field = _STRUCTURAL_FILTER_FIELDS.get(item.field)
        if structural_field is not None:
            if item.op not in structural_field["operators"]:
                raise InvalidMetadataFilterError(
                    f"Filter field '{item.field}' does not allow operator {item.op!r}"
                )
            _validate_value_type(item, structural_field["type"])
            continue
        try:
            field = schema.field(item.field)
        except KeyError as exc:
            raise InvalidMetadataFilterError(
                "Filter field "
                f"'{item.field}' is not declared in collection metadata schema"
            ) from exc
        if item.op not in field.operators:
            raise InvalidMetadataFilterError(
                f"Filter field '{item.field}' does not allow operator {item.op!r}"
            )
        _validate_value_type(item, field.type)
    return normalized


def build_pg_conditions(filters: list[FilterCondition]) -> list[Any]:
    conditions: list[Any] = []
    for item in filters:
        structural_field = _STRUCTURAL_FILTER_FIELDS.get(item.field)
        if structural_field is not None:
            typed_expr = structural_field["expression"]
        else:
            value_expr = chunks_table.c.metadata.op("->>")(item.field)
            typed_expr = _typed_expression(value_expr, item.value)

        if item.op == "eq":
            conditions.append(typed_expr == item.value)
        elif item.op == "gte":
            conditions.append(typed_expr >= item.value)
        elif item.op == "lte":
            conditions.append(typed_expr <= item.value)
    return conditions


def filter_conditions_from_mapping(
    filters: Mapping[str, Any] | None,
) -> list[FilterCondition]:
    if not filters:
        return []

    conditions: list[FilterCondition] = []
    for key, value in filters.items():
        if value is None:
            continue
        if key == "marks_min":
            conditions.append(FilterCondition(field="marks", op="gte", value=value))
            continue
        if key == "question":
            conditions.append(
                FilterCondition(field="question_number", op="eq", value=value)
            )
            continue
        conditions.append(FilterCondition(field=key, op="eq", value=value))
    return conditions


def _validate_value_type(item: FilterCondition, field_type: str) -> None:
    if field_type == "boolean" and type(item.value) is not bool:
        raise InvalidMetadataFilterError(f"{item.field!r} requires a boolean value")
    if field_type == "integer" and type(item.value) is not int:
        raise InvalidMetadataFilterError(f"{item.field!r} requires an integer value")
    if field_type == "string" and type(item.value) is not str:
        raise InvalidMetadataFilterError(f"{item.field!r} requires a string value")


def _typed_expression(value_expr: Any, value: object) -> Any:
    if type(value) is bool:
        return cast(value_expr, Boolean)
    if type(value) is int:
        return cast(value_expr, Integer)
    return value_expr
