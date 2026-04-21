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
        collection_schema = None
        get_collection_schema = getattr(
            self._search_service,
            "get_collection_schema",
            None,
        )
        if callable(get_collection_schema):
            collection_schema = get_collection_schema(collection)
        search_response = self._search_service.search(
            query=plan.semantic_queries[0],
            collection=collection,
            filters=applied_filters or None,
            limit=limit,
            rerank=rerank,
        )
        search_telemetry = None
        pop_last_execution_telemetry = getattr(
            self._search_service,
            "pop_last_execution_telemetry",
            None,
        )
        if callable(pop_last_execution_telemetry):
            search_telemetry = pop_last_execution_telemetry()

        return PlannedRetrievalResult(
            search_response=search_response,
            executed_queries=list(plan.semantic_queries),
            filters_applied=applied_filters,
            collection_schema=collection_schema,
            search_telemetry=search_telemetry,
        )
