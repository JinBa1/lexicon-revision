from __future__ import annotations

from typing import Any

from src.metadata_schema.models import FilterCondition
from src.search.base import SearchBackend
from src.search.filtering import filter_conditions_from_mapping
from src.study.planning.models import PlannedRetrievalResult, QueryPlan, StudyFilters


class PlannedRetrievalService:
    def __init__(self, *, search_service: SearchBackend) -> None:
        self._search_service = search_service

    def retrieve(
        self,
        plan: QueryPlan,
        *,
        hard_filters: StudyFilters | None,
        collection: str,
        limit: int,
        rerank: bool = True,
    ) -> PlannedRetrievalResult:
        filter_dict = _filters_to_dict(hard_filters)
        filter_conditions = _filters_to_conditions(hard_filters)
        search_response = self._search_service.search(
            query=plan.semantic_queries[0],
            collection=collection,
            filters=filter_conditions or None,
            limit=limit,
            rerank=rerank,
        )

        return PlannedRetrievalResult(
            search_response=search_response,
            executed_queries=list(plan.semantic_queries),
            filters_applied=filter_dict,
        )


def _filters_to_dict(filters: StudyFilters | None) -> dict[str, Any]:
    if filters is None:
        return {}
    return filters.model_dump(exclude_none=True)


def _filters_to_conditions(filters: StudyFilters | None) -> list[FilterCondition]:
    return filter_conditions_from_mapping(_filters_to_dict(filters))
