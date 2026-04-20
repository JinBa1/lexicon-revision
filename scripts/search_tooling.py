"""Shared helpers for local search inspection and evaluation scripts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from src.metadata_schema.models import FilterCondition
from src.search.media_sidecar import load_storage_media_map


@dataclass(frozen=True)
class EvalCase:
    id: str
    query: str
    filters: list[FilterCondition]
    any_chunk_ids: list[str]
    any_topics: list[str]
    top_k: int
    notes: str | None = None


@dataclass(frozen=True)
class EvalSpec:
    name: str
    description: str | None
    collection: str | None
    default_top_k: int
    cases: list[EvalCase]


def truncate_text(text: str, max_chars: int) -> str:
    """Compact whitespace and truncate text for readable CLI output."""
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    if max_chars <= 3:
        return "." * max_chars
    return f"{compact[: max_chars - 3].rstrip()}..."


def build_filters(
    *,
    year: int | None = None,
    paper: int | None = None,
    topic: str | None = None,
    question: int | None = None,
    marks_min: int | None = None,
    has_code: bool | None = None,
    has_figure: bool | None = None,
    has_table: bool | None = None,
) -> list[FilterCondition]:
    """Build ordered filter conditions from optional CLI values."""
    raw_filters = {
        "year": year,
        "paper": paper,
        "topic": topic,
        "question_number": question,
        "marks": marks_min,
        "has_code": has_code,
        "has_figure": has_figure,
        "has_table": has_table,
    }
    filters: list[FilterCondition] = []
    for key, value in raw_filters.items():
        if value is None:
            continue
        if key == "marks":
            filters.append(FilterCondition(field="marks", op="gte", value=value))
            continue
        filters.append(FilterCondition(field=key, op="eq", value=value))
    return filters


def parse_filter_conditions(raw_filters: list[str]) -> list[FilterCondition]:
    """Parse repeatable CLI filters of the form field:op:value."""
    parsed: list[FilterCondition] = []
    for raw_filter in raw_filters:
        parts = raw_filter.split(":", 2)
        if len(parts) != 3:
            raise ValueError(
                f"CLI filters must use field:op:value form, got {raw_filter!r}"
            )
        field, op, raw_value = parts
        try:
            condition = FilterCondition.model_validate(
                {
                    "field": field,
                    "op": op,
                    "value": _parse_scalar(raw_value),
                }
            )
        except ValidationError as exc:
            raise ValueError(
                _format_filter_validation_error(
                    context=f"CLI filter {raw_filter!r}",
                    exc=exc,
                )
            ) from exc
        _validate_generic_filter_condition(
            condition,
            context=f"CLI filter {raw_filter!r}",
        )
        parsed.append(condition)
    return parsed


def dump_filters(filters: list[FilterCondition]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in filters]


def load_media_map(
    chroma_dir: str | Path,
    collection: str,
) -> dict[str, list[dict[str, Any]]]:
    """Load a collection media sidecar if present and minimally valid."""
    sidecar_path = Path(chroma_dir) / f"{collection}_media_map.json"
    return load_storage_media_map(sidecar_path)


def load_eval_spec(path: str | Path) -> EvalSpec:
    """Load and validate a human-authored YAML search eval file."""
    eval_path = Path(path)
    payload = yaml.safe_load(eval_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Eval file must contain a mapping at the top level")

    name = payload.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("Eval file requires non-empty string field 'name'")

    default_top_k = payload.get("default_top_k", 5)
    if type(default_top_k) is not int or default_top_k <= 0:
        raise ValueError("default_top_k must be a positive integer")

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Eval file requires non-empty list field 'cases'")

    cases = [_parse_case(raw_case, default_top_k) for raw_case in raw_cases]
    description = payload.get("description")
    collection = payload.get("collection")

    return EvalSpec(
        name=name,
        description=_parse_optional_string_field(
            description, "Eval file 'description'"
        ),
        collection=_parse_optional_string_field(collection, "Eval file 'collection'"),
        default_top_k=default_top_k,
        cases=cases,
    )


def _parse_case(raw_case: Any, default_top_k: int) -> EvalCase:
    if not isinstance(raw_case, dict):
        raise ValueError("Each eval case must be a mapping")

    case_id = raw_case.get("id")
    query = raw_case.get("query")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("Each eval case requires non-empty string field 'id'")
    if not isinstance(query, str) or not query:
        raise ValueError(
            f"Eval case '{case_id}' requires non-empty string field 'query'"
        )

    filters = parse_authored_filters(
        raw_case.get("filters"),
        context=f"Eval case '{case_id}'",
    )

    expected = raw_case.get("expected")
    if not isinstance(expected, dict):
        raise ValueError(f"Eval case '{case_id}' requires expected mapping")

    if "any_chunk_ids" not in expected or expected["any_chunk_ids"] is None:
        any_chunk_ids = []
    else:
        any_chunk_ids = expected["any_chunk_ids"]
    if "any_topics" not in expected or expected["any_topics"] is None:
        any_topics = []
    else:
        any_topics = expected["any_topics"]
    if not isinstance(any_chunk_ids, list) or not all(
        isinstance(item, str) for item in any_chunk_ids
    ):
        raise ValueError(
            f"Eval case '{case_id}' any_chunk_ids must be a list of strings"
        )
    if not isinstance(any_topics, list) or not all(
        isinstance(item, str) for item in any_topics
    ):
        raise ValueError(f"Eval case '{case_id}' any_topics must be a list of strings")
    if not any_chunk_ids and not any_topics:
        raise ValueError(f"Eval case '{case_id}' requires any_chunk_ids or any_topics")

    top_k = expected.get("top_k", default_top_k)
    if type(top_k) is not int or top_k <= 0:
        raise ValueError(f"Eval case '{case_id}' top_k must be a positive integer")

    notes = raw_case.get("notes")
    if "notes" not in raw_case or notes is None:
        parsed_notes = None
    else:
        parsed_notes = _parse_optional_string_field(
            notes, f"Eval case '{case_id}' notes"
        )

    return EvalCase(
        id=case_id,
        query=query,
        filters=filters,
        any_chunk_ids=any_chunk_ids,
        any_topics=any_topics,
        top_k=top_k,
        notes=parsed_notes,
    )


def _parse_optional_string_field(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def parse_authored_filters(
    raw_filters: Any,
    *,
    context: str,
) -> list[FilterCondition]:
    if raw_filters is None:
        return []
    if not isinstance(raw_filters, list):
        raise ValueError(f"{context} filters must be a list")

    parsed: list[FilterCondition] = []
    for index, raw_filter in enumerate(raw_filters, start=1):
        if not isinstance(raw_filter, dict):
            raise ValueError(f"{context} filters must be a list of mappings")
        try:
            condition = FilterCondition.model_validate(raw_filter)
        except ValidationError as exc:
            raise ValueError(
                _format_filter_validation_error(
                    context=f"{context} filter #{index}",
                    exc=exc,
                )
            ) from exc
        _validate_generic_filter_condition(
            condition,
            context=f"{context} filter #{index}",
        )
        parsed.append(condition)
    return parsed


def _parse_scalar(raw_value: str) -> Any:
    lowered = raw_value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(raw_value)
    except ValueError:
        return raw_value


def _validate_generic_filter_condition(
    condition: FilterCondition,
    *,
    context: str,
) -> None:
    if condition.op in {"gte", "lte"} and type(condition.value) is not int:
        raise ValueError(
            f"{context} field '{condition.field}' uses op '{condition.op}', "
            "which requires an integer value"
        )
    if type(condition.value) is str and not condition.value:
        raise ValueError(f"{context} field '{condition.field}' must not be empty")


def _format_filter_validation_error(*, context: str, exc: ValidationError) -> str:
    details = "; ".join(
        f"{'.'.join(str(item) for item in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    )
    return f"{context} is invalid: {details}"
