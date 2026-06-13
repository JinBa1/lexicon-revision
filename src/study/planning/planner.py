from __future__ import annotations

from pathlib import Path
from typing import Protocol

from src.metadata_schema.models import FilterCondition
from src.runtime.telemetry import ProviderCallTelemetry
from src.study.config import PlanningSettings
from src.study.models import GenerationRequest
from src.study.planning.models import (
    InvalidPlanError,
    PlannerExecution,
    QueryPlan,
    QueryPlanDraft,
)
from src.study.planning.prompts import PlannerPromptTemplate, load_planner_prompt
from src.study.providers.base import GenerationProvider

_MAX_SEMANTIC_QUERY_WORDS = 40
_MAX_GUIDANCE_WORDS = 100


class QueryPlanner(Protocol):
    async def plan(
        self,
        raw_query: str,
        hard_filters: list[FilterCondition] | None,
    ) -> PlannerExecution: ...


class RawQueryPlanner:
    async def plan(
        self,
        raw_query: str,
        hard_filters: list[FilterCondition] | None,
    ) -> PlannerExecution:
        return PlannerExecution(
            plan=QueryPlan(original_query=raw_query, semantic_queries=[raw_query]),
            telemetry=ProviderCallTelemetry(
                provider="raw_query",
                model="raw_query",
                latency_ms=0,
                usage=None,
            ),
        )


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
        if self._prompt.version != settings.prompt_version:
            raise ValueError(
                "planning.prompt_version must match planner prompt template "
                f"version: {settings.prompt_version!r} != {self._prompt.version!r}"
            )

    async def plan(
        self,
        raw_query: str,
        hard_filters: list[FilterCondition] | None,
    ) -> PlannerExecution:
        messages = self._prompt.render(
            raw_query=raw_query,
            applied_filters=[
                condition.model_dump(mode="json") for condition in hard_filters or []
            ],
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
        return PlannerExecution(
            plan=_build_plan(
                draft,
                raw_query,
                planner_version=self._settings.prompt_version,
            ),
            telemetry=ProviderCallTelemetry(
                provider=result.provider,
                model=result.model,
                latency_ms=result.latency_ms,
                usage=result.usage,
            ),
        )


def _build_plan(
    draft: QueryPlanDraft,
    raw_query: str,
    *,
    planner_version: str,
) -> QueryPlan:
    semantic_queries = [query.strip() for query in draft.semantic_queries]
    for query in semantic_queries:
        if not query:
            raise InvalidPlanError("semantic query must not be empty")
        if len(query.split()) > _MAX_SEMANTIC_QUERY_WORDS:
            raise InvalidPlanError(
                f"semantic query exceeds {_MAX_SEMANTIC_QUERY_WORDS} word limit"
            )
    guidance = draft.generation_guidance.strip()
    if len(guidance.split()) > _MAX_GUIDANCE_WORDS:
        raise InvalidPlanError(
            f"generation_guidance exceeds {_MAX_GUIDANCE_WORDS} word limit"
        )
    return QueryPlan(
        planner_version=planner_version,
        original_query=raw_query,
        semantic_queries=semantic_queries,
        intent=draft.intent,
        generation_guidance=guidance,
    )
