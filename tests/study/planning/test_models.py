from __future__ import annotations

import pytest
from pydantic import ValidationError
from src.metadata_schema.models import FilterCondition
from src.search.models import SearchResponse
from src.study.planning.models import (
    InvalidPlanError,
    PlannedRetrievalResult,
    PlanningMetadata,
    QueryPlan,
    QueryPlanDraft,
)


def test_filter_condition_rejects_invalid_operator() -> None:
    with pytest.raises(ValidationError):
        FilterCondition(field="has_code", op="contains", value=True)  # type: ignore[arg-type]


def test_filter_condition_rejects_invalid_field_name() -> None:
    with pytest.raises(ValidationError):
        FilterCondition(field="question-number", op="eq", value=4)


def test_filter_condition_accepts_scalar_values() -> None:
    condition = FilterCondition(field="year", op="eq", value=2025)
    assert condition.value == 2025


def test_query_plan_draft_rejects_empty_or_multi() -> None:
    with pytest.raises(ValidationError):
        QueryPlanDraft(semantic_queries=[])
    with pytest.raises(ValidationError):
        QueryPlanDraft(semantic_queries=["a", "b"])


def test_query_plan_server_fields_default() -> None:
    plan = QueryPlan(
        original_query="2025 paper 3 database outer join",
        semantic_queries=["database outer join relational algebra"],
    )
    assert plan.planner_version == "query_planner_v1"
    assert plan.original_query == "2025 paper 3 database outer join"


def test_planning_metadata_requires_error_category_on_fallback() -> None:
    with pytest.raises(ValidationError):
        PlanningMetadata(
            status="fallback",
            planner_version="query_planner_v1",
            original_query="q",
            semantic_queries=["q"],
            error_category=None,
            latency_ms=5,
        )


def test_planning_metadata_rejects_error_category_on_ok() -> None:
    with pytest.raises(ValidationError):
        PlanningMetadata(
            status="ok",
            planner_version="query_planner_v1",
            original_query="q",
            semantic_queries=["q"],
            error_category="provider_timeout",
            latency_ms=5,
        )


def test_planning_metadata_rejects_negative_latency() -> None:
    with pytest.raises(ValidationError):
        PlanningMetadata(
            status="ok",
            planner_version="query_planner_v1",
            original_query="q",
            semantic_queries=["q"],
            error_category=None,
            latency_ms=-1,
        )


def test_planned_retrieval_result_composes_search_response() -> None:
    result = PlannedRetrievalResult(
        search_response=SearchResponse(query="q", collection="c", results=[], total=0),
        executed_queries=["q"],
        filters_applied=[FilterCondition(field="year", op="eq", value=2024)],
    )
    assert result.executed_queries == ["q"]
    assert result.filters_applied == [
        FilterCondition(field="year", op="eq", value=2024)
    ]


def test_invalid_plan_error_is_exception() -> None:
    with pytest.raises(InvalidPlanError):
        raise InvalidPlanError("bad")
