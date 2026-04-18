from __future__ import annotations

from pathlib import Path

from src.study.planning.models import StudyFilters
from src.study.planning.prompts import (
    _describe_strip_filter_schema_keys,
    load_planner_prompt,
)


def test_strip_filter_schema_keys_exclude_topic_but_cover_others() -> None:
    schema_keys = set(_describe_strip_filter_schema_keys())

    assert "topic" not in schema_keys
    assert schema_keys | {"topic"} == set(StudyFilters.model_fields.keys())


def test_planner_prompt_renders_raw_query_and_applied_filters(tmp_path: Path) -> None:
    prompt_path = tmp_path / "query_planner_v1.yaml"
    prompt_path.write_text(
        """
version: query_planner_v1
system: |
  Strip fields:
  {% for field in strip_fields %}
  - {{ field.name }}: {{ field.description }}
  {% endfor %}
  Names: {{ strip_field_names | join(", ") }}
user: |
  Raw: {{ raw_query }}
  Applied: {{ applied_filters | tojson }}
""",
        encoding="utf-8",
    )

    template = load_planner_prompt(prompt_path)
    messages = template.render(
        raw_query="paper 3 recursion in 2023",
        applied_filters={"paper": 3},
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "year" in messages[0]["content"]
    assert "paper" in messages[0]["content"]
    assert "topic" not in messages[0]["content"]
    assert "paper 3 recursion in 2023" in messages[1]["content"]
    assert '"paper": 3' in messages[1]["content"]


def test_planner_prompt_render_accepts_no_applied_filters(tmp_path: Path) -> None:
    prompt_path = tmp_path / "query_planner_v1.yaml"
    prompt_path.write_text(
        """
version: query_planner_v1
system: "System"
user: |
  Raw: {{ raw_query }}
  Applied:
  {% if applied_filters %}{{ applied_filters | tojson }}{% else %}none{% endif %}
""",
        encoding="utf-8",
    )

    template = load_planner_prompt(prompt_path)
    messages = template.render(raw_query="recursion", applied_filters={})

    assert "Applied:\nnone" in messages[1]["content"]


def test_real_planner_prompt_loads() -> None:
    template = load_planner_prompt(Path("prompts/query_planner_v1.yaml"))

    messages = template.render(
        raw_query="paper 2 dynamic programming tables",
        applied_filters={"paper": 2},
    )
    system = messages[0]["content"]
    user = messages[1]["content"]

    assert template.version == "query_planner_v1"
    assert "year" in system
    assert "paper" in system
    assert "question_number" in system
    assert "marks_min" in system
    assert "has_code" in system
    assert "has_figure" in system
    assert "has_table" in system
    assert "semantic_queries" in system
    assert "40 words" in system
    assert "paper 2 dynamic programming tables" in user
