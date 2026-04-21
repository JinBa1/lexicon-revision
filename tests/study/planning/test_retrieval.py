from __future__ import annotations

from typing import Any

from src.metadata_schema.models import FilterCondition
from src.runtime.telemetry import ProviderCallTelemetry
from src.search.models import SearchResponse
from src.search.pg_service import SearchExecutionTelemetry
from src.study.planning.models import QueryPlan
from src.study.planning.retrieval import PlannedRetrievalService


class FakeSearchService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.telemetry: SearchExecutionTelemetry | None = SearchExecutionTelemetry(
            embedding=ProviderCallTelemetry(
                provider="voyage",
                model="voyage-4-lite",
                latency_ms=12,
                usage=None,
            ),
            rerank=None,
        )

    def search(
        self,
        *,
        query: str,
        collection: str,
        filters: list[FilterCondition] | None,
        limit: int,
        rerank: bool,
    ) -> SearchResponse:
        self.calls.append(
            {
                "query": query,
                "collection": collection,
                "filters": filters,
                "limit": limit,
                "rerank": rerank,
            }
        )
        return SearchResponse(query=query, collection=collection, results=[], total=0)

    def pop_last_execution_telemetry(self) -> SearchExecutionTelemetry | None:
        telemetry = self.telemetry
        self.telemetry = None
        return telemetry


def _plan() -> QueryPlan:
    return QueryPlan(
        original_query="Find 2025 paper 3 questions about dynamic programming",
        semantic_queries=["dynamic programming exam questions"],
    )


def test_retrieve_calls_search_with_semantic_query_and_filters() -> None:
    search_service = FakeSearchService()
    service = PlannedRetrievalService(search_service=search_service)
    filters = [
        FilterCondition(field="year", op="eq", value=2025),
        FilterCondition(field="paper", op="eq", value=3),
    ]

    result = service.retrieve(
        _plan(),
        hard_filters=filters,
        collection="cam",
        limit=15,
        rerank=True,
    )

    assert search_service.calls == [
        {
            "query": "dynamic programming exam questions",
            "collection": "cam",
            "filters": [
                FilterCondition(field="year", op="eq", value=2025),
                FilterCondition(field="paper", op="eq", value=3),
            ],
            "limit": 15,
            "rerank": True,
        }
    ]
    assert result.executed_queries == ["dynamic programming exam questions"]
    assert result.filters_applied == filters


def test_retrieve_passes_none_when_no_filters() -> None:
    search_service = FakeSearchService()
    service = PlannedRetrievalService(search_service=search_service)

    result = service.retrieve(
        _plan(),
        hard_filters=None,
        collection="cam",
        limit=10,
    )

    assert search_service.calls[0]["filters"] is None
    assert result.filters_applied == []


def test_retrieve_preserves_repeated_filter_conditions() -> None:
    search_service = FakeSearchService()
    service = PlannedRetrievalService(search_service=search_service)
    filters = [
        FilterCondition(field="year", op="gte", value=2020),
        FilterCondition(field="year", op="lte", value=2024),
    ]

    result = service.retrieve(
        _plan(),
        hard_filters=filters,
        collection="cam",
        limit=10,
    )

    assert search_service.calls[0]["filters"] == filters
    assert result.filters_applied == [
        FilterCondition(field="year", op="gte", value=2020),
        FilterCondition(field="year", op="lte", value=2024),
    ]


def test_retrieve_carries_search_telemetry_from_search_service_hook() -> None:
    search_service = FakeSearchService()
    service = PlannedRetrievalService(search_service=search_service)

    result = service.retrieve(
        _plan(),
        hard_filters=None,
        collection="cam",
        limit=10,
    )

    assert result.search_telemetry is not None
    assert result.search_telemetry.embedding.provider == "voyage"
    assert result.search_telemetry.rerank is None
