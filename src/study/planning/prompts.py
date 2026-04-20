from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Template
from pydantic import BaseModel


def _describe_strip_filter_schema_keys(
    applied_filters: list[dict[str, Any]],
) -> list[str]:
    seen: set[str] = set()
    ordered_keys: list[str] = []
    for condition in applied_filters:
        field = condition.get("field")
        if not isinstance(field, str) or field in seen:
            continue
        seen.add(field)
        ordered_keys.append(field)
    return ordered_keys


def _describe_strip_filter_schema(
    applied_filters: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "name": field,
            "description": "This field is already applied as a hard filter.",
        }
        for field in _describe_strip_filter_schema_keys(applied_filters)
    ]


class PlannerPromptTemplate(BaseModel):
    version: str
    system: str
    user: str

    def render(
        self,
        *,
        raw_query: str,
        applied_filters: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        strip_fields = _describe_strip_filter_schema(applied_filters)
        system_content = Template(self.system).render(
            strip_fields=strip_fields,
            strip_field_names=[field["name"] for field in strip_fields],
        )
        user_content = Template(self.user).render(
            raw_query=raw_query,
            applied_filters=applied_filters,
        )
        return [
            {"role": "system", "content": system_content.strip()},
            {"role": "user", "content": user_content.strip()},
        ]


def load_planner_prompt(path: Path) -> PlannerPromptTemplate:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return PlannerPromptTemplate.model_validate(loaded)
