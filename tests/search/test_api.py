from __future__ import annotations

import httpx
import pytest
from src.metadata_schema.models import FilterCondition
from src.search.errors import CollectionNotFoundError, InvalidMetadataFilterError
from src.search.models import MediaRefResponse, SearchResponse, SearchResult

MEDIA_OBJECT_KEY = "artifacts/mineru/run-y2023p2q5/images/fig1.png"


class FakeSearchService:
    embedding_model_id = "test-embedding"
    rerank_model_id = None

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

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
        return SearchResponse(
            query=query,
            collection=collection,
            total=1,
            results=[
                SearchResult(
                    chunk_id="cam-2023-p2-q5",
                    chunk_level="question",
                    parent_chunk_id=None,
                    sub_question_label=None,
                    text="Binary search trees support efficient lookup and insertion.",
                    score=0.9,
                    metadata={
                        "year": 2023,
                        "paper": 2,
                        "question_number": 5,
                        "topic": "Algorithms",
                        "chunk_level": "question",
                        "has_code": False,
                        "has_figure": False,
                        "has_table": False,
                        "source_pdf": "y2023p2q5.pdf",
                        "total_marks": 20,
                    },
                    media=[
                        MediaRefResponse(
                            media_id="fig1",
                            kind="image",
                            object_key=MEDIA_OBJECT_KEY,
                            access_url="http://localhost:8000/_dev/object/GET/...",
                            relation="direct",
                        )
                    ],
                )
            ],
        )


class MissingCollectionSearchService(FakeSearchService):
    def search(
        self,
        *,
        query: str,
        collection: str,
        filters: list[FilterCondition] | None,
        limit: int,
        rerank: bool,
    ) -> SearchResponse:
        del query, filters, limit, rerank
        raise CollectionNotFoundError(collection)


class InvalidFilterSearchService(FakeSearchService):
    def search(
        self,
        *,
        query: str,
        collection: str,
        filters: list[FilterCondition] | None,
        limit: int,
        rerank: bool,
    ) -> SearchResponse:
        del query, collection, filters, limit, rerank
        raise InvalidMetadataFilterError(
            "Filter field 'topic' is not declared in collection metadata schema"
        )


@pytest.fixture
def app() -> object:
    from src.main import create_app

    return create_app(search_service=FakeSearchService())


@pytest.mark.anyio
async def test_search_returns_200_with_results(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={"q": "binary search trees", "collection": "fixture"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["collection"] == "fixture"
    assert data["query"] == "binary search trees"
    assert data["total"] == 1
    assert data["results"][0]["media"][0]["object_key"] == MEDIA_OBJECT_KEY


@pytest.mark.anyio
async def test_search_converts_query_filters_to_filter_conditions(app) -> None:
    service = app.state.search_service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={
                "q": "algorithms",
                "collection": "fixture",
                "year": 2024,
                "paper": 1,
                "marks_min": 10,
                "has_code": True,
            },
        )

    assert response.status_code == 200
    assert service.calls[0]["filters"] == [
        FilterCondition(field="year", op="eq", value=2024),
        FilterCondition(field="paper", op="eq", value=1),
        FilterCondition(field="marks", op="gte", value=10),
        FilterCondition(field="has_code", op="eq", value=True),
    ]


@pytest.mark.anyio
async def test_search_nonexistent_collection_returns_404() -> None:
    from src.main import create_app

    app = create_app(search_service=MissingCollectionSearchService())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={"q": "anything", "collection": "nonexistent"},
        )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_search_rejects_limit_above_rerank_cap(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={"q": "algorithms", "collection": "fixture", "limit": 51},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_search_invalid_metadata_filter_returns_422() -> None:
    from src.main import create_app

    app = create_app(search_service=InvalidFilterSearchService())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={"q": "algorithms", "collection": "fixture", "topic": "Trees"},
        )

    assert response.status_code == 422
    assert "not declared in collection metadata schema" in response.json()["detail"]
