from __future__ import annotations

from typing import Any

from src.search.models import SearchResponse
from src.study.planning.models import QueryPlan, StudyFilters
from src.study.planning.retrieval import PlannedRetrievalService, _filters_to_dict


class FakeSearchService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        *,
        query: str,
        collection: str,
        filters: dict[str, Any] | None,
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


def _plan() -> QueryPlan:
    return QueryPlan(
        original_query="Find 2025 paper 3 questions about dynamic programming",
        semantic_queries=["dynamic programming exam questions"],
    )


def test_retrieve_calls_search_with_semantic_query_and_filters() -> None:
    search_service = FakeSearchService()
    service = PlannedRetrievalService(search_service=search_service)

    result = service.retrieve(
        _plan(),
        hard_filters=StudyFilters(year=2025, paper=3),
        collection="cam",
        limit=15,
        rerank=True,
    )

    assert search_service.calls == [
        {
            "query": "dynamic programming exam questions",
            "collection": "cam",
            "filters": {"year": 2025, "paper": 3},
            "limit": 15,
            "rerank": True,
        }
    ]
    assert result.executed_queries == ["dynamic programming exam questions"]
    assert result.filters_applied == {"year": 2025, "paper": 3}


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
    assert result.filters_applied == {}


def test_retrieve_passes_none_when_all_filters_are_none() -> None:
    search_service = FakeSearchService()
    service = PlannedRetrievalService(search_service=search_service)

    service.retrieve(
        _plan(),
        hard_filters=StudyFilters(),
        collection="cam",
        limit=10,
    )

    assert search_service.calls[0]["filters"] is None


def test_filters_to_dict_drops_none_values() -> None:
    assert _filters_to_dict(None) == {}
    assert _filters_to_dict(StudyFilters()) == {}
    assert _filters_to_dict(StudyFilters(year=2025)) == {"year": 2025}
    assert _filters_to_dict(
        StudyFilters(year=2025, topic="Databases", has_code=True)
    ) == {"year": 2025, "topic": "Databases", "has_code": True}
