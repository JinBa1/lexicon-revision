"""Shared helpers for local search inspection and evaluation scripts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from src.metadata_schema.models import FilterCondition
from src.search.media_sidecar import load_storage_media_map

SUPPORTED_FILTER_KEYS = {
    "year",
    "paper",
    "topic",
    "question_number",
    "marks_min",
    "has_code",
    "has_figure",
    "has_table",
}


@dataclass(frozen=True)
class EvalCase:
    id: str
    query: str
    filters: dict[str, Any]
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
        "marks_min": marks_min,
        "has_code": has_code,
        "has_figure": has_figure,
        "has_table": has_table,
    }
    filters: list[FilterCondition] = []
    for key, value in raw_filters.items():
        if value is None:
            continue
        if key == "marks_min":
            filters.append(FilterCondition(field="marks", op="gte", value=value))
            continue
        filters.append(FilterCondition(field=key, op="eq", value=value))
    return filters


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

    if "filters" not in raw_case or raw_case["filters"] is None:
        filters = {}
    else:
        filters = raw_case["filters"]
    if not isinstance(filters, dict):
        raise ValueError(f"Eval case '{case_id}' filters must be a mapping")
    unknown_filters = set(filters) - (SUPPORTED_FILTER_KEYS | {"question"})
    if unknown_filters:
        unknown = ", ".join(sorted(unknown_filters))
        raise ValueError(f"Eval case '{case_id}' has unsupported filters: {unknown}")

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

    filters = _parse_case_filters(case_id, filters)
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


def _parse_case_filters(case_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    if "question" in filters and "question_number" in filters:
        raise ValueError(
            f"Eval case '{case_id}' cannot set both 'question' and 'question_number'"
        )

    parsed_filters: dict[str, Any] = {}
    for filter_name, value in filters.items():
        if value is None:
            continue
        normalized_name = (
            "question_number" if filter_name == "question" else filter_name
        )
        if normalized_name in {"year", "paper", "question_number", "marks_min"}:
            if type(value) is not int:
                raise ValueError(
                    f"Eval case '{case_id}' filter '{normalized_name}' must be an "
                    "integer"
                )
        elif normalized_name in {"has_code", "has_figure", "has_table"}:
            if type(value) is not bool:
                raise ValueError(
                    f"Eval case '{case_id}' filter '{normalized_name}' must be a "
                    "boolean"
                )
        elif normalized_name == "topic":
            if type(value) is not str or not value:
                raise ValueError(
                    f"Eval case '{case_id}' filter '{normalized_name}' "
                    "must be a non-empty string"
                )
        else:
            raise ValueError(
                f"Eval case '{case_id}' has unsupported filters: {filter_name}"
            )
        parsed_filters[normalized_name] = value
    return parsed_filters
