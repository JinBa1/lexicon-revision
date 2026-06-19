"""Reflection loop assets (Track A, PR 3).

Two single-purpose LLM steps that wrap the retrieval result:

- the **grader** judges which retrieved chunks genuinely answer the query and,
  when it rejects everything, emits a short ``critique`` of what was missing;
- the **reflect/reformulation** step reads ``{original query + critique}`` and
  designs one genuinely different retrieval query (or declines).

Both prompt templates mirror ``PlannerPromptTemplate`` (planning/prompts.py):
a versioned ``system``/``user`` pair rendered through Jinja. The provider draft
schemas are ``extra="forbid"`` Pydantic models so a malformed provider response
raises ``ValidationError`` (the node fail-safes handle it).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Template
from pydantic import BaseModel, ConfigDict


class RelevanceGradingDraft(BaseModel):
    """Grader LLM output. ``title`` is used by inspect_study schema routing."""

    model_config = ConfigDict(extra="forbid")

    accepted_chunk_ids: list[str]
    critique: str = ""


class QueryReformulationDraft(BaseModel):
    """Reflect LLM output. ``reformulated_query`` empty == decline to re-query."""

    model_config = ConfigDict(extra="forbid")

    reformulated_query: str = ""


class GradingPromptTemplate(BaseModel):
    version: str
    system: str
    user: str

    def render(
        self,
        *,
        query: str,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        system_content = Template(self.system).render()
        user_content = Template(self.user).render(query=query, chunks=chunks)
        return [
            {"role": "system", "content": system_content.strip()},
            {"role": "user", "content": user_content.strip()},
        ]


class ReformulationPromptTemplate(BaseModel):
    version: str
    system: str
    user: str

    def render(
        self,
        *,
        query: str,
        critique: str,
    ) -> list[dict[str, str]]:
        system_content = Template(self.system).render()
        user_content = Template(self.user).render(query=query, critique=critique)
        return [
            {"role": "system", "content": system_content.strip()},
            {"role": "user", "content": user_content.strip()},
        ]


def load_grading_prompt(path: Path) -> GradingPromptTemplate:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return GradingPromptTemplate.model_validate(loaded)


def load_reformulation_prompt(path: Path) -> ReformulationPromptTemplate:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return ReformulationPromptTemplate.model_validate(loaded)
