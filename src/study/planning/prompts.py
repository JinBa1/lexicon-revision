from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Template
from pydantic import BaseModel

_STRIP_FILTER_SCHEMA = {
    "year": "Exam year already applied as a hard filter.",
    "paper": "Exam paper number already applied as a hard filter.",
    "question_number": "Question number already applied as a hard filter.",
    "marks_min": "Minimum mark value already applied as a hard filter.",
    "has_code": "Whether code presence is already applied as a hard filter.",
    "has_figure": "Whether figure presence is already applied as a hard filter.",
    "has_table": "Whether table presence is already applied as a hard filter.",
}


def _describe_strip_filter_schema_keys() -> list[str]:
    return list(_STRIP_FILTER_SCHEMA.keys())


def _describe_strip_filter_schema() -> list[dict[str, str]]:
    return [
        {"name": name, "description": description}
        for name, description in _STRIP_FILTER_SCHEMA.items()
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
        system_content = Template(self.system).render(
            strip_fields=_describe_strip_filter_schema(),
            strip_field_names=_describe_strip_filter_schema_keys(),
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
