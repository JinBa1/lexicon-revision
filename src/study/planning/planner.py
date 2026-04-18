from __future__ import annotations

from pathlib import Path
from typing import Protocol

from src.study.config import PlanningSettings
from src.study.models import GenerationRequest
from src.study.planning.models import (
    InvalidPlanError,
    QueryPlan,
    QueryPlanDraft,
    StudyFilters,
)
from src.study.planning.prompts import PlannerPromptTemplate, load_planner_prompt
from src.study.providers.base import GenerationProvider

_MAX_SEMANTIC_QUERY_WORDS = 40


class QueryPlanner(Protocol):
    async def plan(
        self,
        raw_query: str,
        hard_filters: StudyFilters | None,
    ) -> QueryPlan: ...


class LLMQueryPlanner:
    def __init__(
        self,
        provider: GenerationProvider,
        settings: PlanningSettings,
    ) -> None:
        self._provider = provider
        self._settings = settings
        self._prompt: PlannerPromptTemplate = load_planner_prompt(
            Path(settings.prompt_path)
        )

    async def plan(
        self,
        raw_query: str,
        hard_filters: StudyFilters | None,
    ) -> QueryPlan:
        messages = self._prompt.render(
            raw_query=raw_query,
            applied_filters=_filters_to_dict(hard_filters),
        )
        request = GenerationRequest(
            messages=messages,
            response_schema=(
                QueryPlanDraft.model_json_schema()
                if self._provider.capabilities.json_schema_output
                else None
            ),
            temperature=self._settings.temperature,
            max_tokens=None,
            timeout_seconds=self._settings.request_timeout_seconds,
        )

        result = await self._provider.generate(request)
        draft = QueryPlanDraft.model_validate_json(result.raw_content)
        return _build_plan(draft, raw_query)


def _build_plan(draft: QueryPlanDraft, raw_query: str) -> QueryPlan:
    semantic_queries = [query.strip() for query in draft.semantic_queries]
    for query in semantic_queries:
        if not query:
            raise InvalidPlanError("semantic query must not be empty")
        if len(query.split()) > _MAX_SEMANTIC_QUERY_WORDS:
            raise InvalidPlanError(
                f"semantic query exceeds {_MAX_SEMANTIC_QUERY_WORDS} word limit"
            )
    return QueryPlan(original_query=raw_query, semantic_queries=semantic_queries)


def _filters_to_dict(filters: StudyFilters | None) -> dict[str, object]:
    if filters is None:
        return {}
    return filters.model_dump(exclude_none=True)
