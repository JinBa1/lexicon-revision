from __future__ import annotations

from src.metadata_schema.models import FilterCondition
from src.search.base import SearchBackend
from src.study.planning.models import PlannedRetrievalResult, QueryPlan


class PlannedRetrievalService:
    def __init__(self, *, search_service: SearchBackend) -> None:
        self._search_service = search_service

    def retrieve(
        self,
        plan: QueryPlan,
        *,
        hard_filters: list[FilterCondition] | None,
        collection: str,
        limit: int,
        rerank: bool = True,
    ) -> PlannedRetrievalResult:
        applied_filters = list(hard_filters or [])
        search_response = self._search_service.search(
            query=plan.semantic_queries[0],
            collection=collection,
            filters=applied_filters or None,
            limit=limit,
            rerank=rerank,
        )

        return PlannedRetrievalResult(
            search_response=search_response,
            executed_queries=list(plan.semantic_queries),
            filters_applied=applied_filters,
        )
