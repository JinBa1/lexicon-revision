from __future__ import annotations

from typing import Any

from src.search.service import SearchService
from src.study.planning.models import PlannedRetrievalResult, QueryPlan, StudyFilters


class PlannedRetrievalService:
    def __init__(self, *, search_service: SearchService) -> None:
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
        search_response = self._search_service.search(
            query=plan.semantic_queries[0],
            collection=collection,
            filters=filter_dict or None,
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
