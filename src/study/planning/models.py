from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from src.metadata_schema.models import FilterCondition
from src.search.models import SearchResponse

PlanningStatus = Literal["ok", "fallback"]
PlanningErrorCategory = Literal[
    "provider_unreachable",
    "provider_timeout",
    "planning_deadline_exceeded",
    "provider_error",
    "model_not_available",
    "schema_validation_failed",
    "invalid_plan",
]


class QueryPlanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_queries: list[str] = Field(min_length=1, max_length=1)


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner_version: str = Field(default="query_planner_v1", min_length=1)
    original_query: str = Field(min_length=1)
    semantic_queries: list[str] = Field(min_length=1, max_length=1)


class PlanningMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PlanningStatus = "ok"
    planner_version: str = Field(min_length=1)
    original_query: str = Field(min_length=1)
    semantic_queries: list[str] = Field(min_length=1)
    error_category: PlanningErrorCategory | None = None
    latency_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_status_error_consistency(self) -> "PlanningMetadata":
        if self.status == "fallback" and self.error_category is None:
            raise ValueError("fallback planning requires an error_category")
        if self.status == "ok" and self.error_category is not None:
            raise ValueError("ok planning rejects an error_category")
        return self


class PlannedRetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_response: SearchResponse
    executed_queries: list[str]
    filters_applied: list[FilterCondition]


class InvalidPlanError(Exception):
    pass
