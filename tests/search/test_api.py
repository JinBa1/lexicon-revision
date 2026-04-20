from __future__ import annotations

import httpx
import pytest
from src.access.errors import CollectionAccessDeniedError
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


class FakeAccessService:
    def __init__(
        self,
        *,
        missing_collections: set[str] | None = None,
        private_members: dict[str, set[str]] | None = None,
    ) -> None:
        self.calls: list[dict[str, str | None]] = []
        self.missing_collections = missing_collections or set()
        self.private_members = private_members or {}

    def authorize_collection(
        self,
        *,
        collection_name: str,
        user_email_header: str | None,
    ) -> None:
        self.calls.append(
            {
                "collection_name": collection_name,
                "user_email_header": user_email_header,
            }
        )
        if collection_name in self.missing_collections:
            raise CollectionNotFoundError(collection_name)

        allowed_members = self.private_members.get(collection_name)
        if allowed_members is not None and user_email_header not in allowed_members:
            raise CollectionAccessDeniedError(collection_name)


@pytest.fixture
def app() -> object:
    from src.main import create_app

    return create_app(
        search_service=FakeSearchService(),
        allow_unauthorized_test_mode=True,
    )


def test_create_app_injected_mode_requires_explicit_access_choice() -> None:
    from src.main import create_app

    with pytest.raises(ValueError, match="allow_unauthorized_test_mode"):
        create_app(search_service=FakeSearchService())


@pytest.mark.anyio
async def test_post_search_returns_200_with_results(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={"query": "binary search trees", "collection": "fixture"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["collection"] == "fixture"
    assert data["query"] == "binary search trees"
    assert data["total"] == 1
    assert data["results"][0]["media"][0]["object_key"] == MEDIA_OBJECT_KEY


@pytest.mark.anyio
async def test_post_search_accepts_schema_native_filters(app) -> None:
    service = app.state.search_service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={
                "query": "algorithms",
                "collection": "fixture",
                "filters": [
                    {"field": "year", "op": "eq", "value": 2024},
                    {"field": "paper", "op": "eq", "value": 1},
                    {"field": "marks", "op": "gte", "value": 10},
                    {"field": "has_code", "op": "eq", "value": True},
                ],
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
async def test_post_search_nonexistent_collection_returns_404() -> None:
    from src.main import create_app

    app = create_app(
        search_service=MissingCollectionSearchService(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={"query": "anything", "collection": "nonexistent"},
        )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_post_search_rejects_limit_above_rerank_cap(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={"query": "algorithms", "collection": "fixture", "limit": 51},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_post_search_invalid_metadata_filter_returns_422() -> None:
    from src.main import create_app

    app = create_app(
        search_service=InvalidFilterSearchService(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={
                "query": "algorithms",
                "collection": "fixture",
                "filters": [{"field": "topic", "op": "eq", "value": "Trees"}],
            },
        )

    assert response.status_code == 422
    assert "not declared in collection metadata schema" in response.json()["detail"]


@pytest.mark.anyio
async def test_post_search_private_collection_denied_without_header() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        access_service=FakeAccessService(
            private_members={"private-fixture": {"member@example.com"}}
        ),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={"query": "algorithms", "collection": "private-fixture"},
        )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_post_search_private_collection_allowed_for_member_header() -> None:
    from src.main import create_app

    service = FakeSearchService()
    access_service = FakeAccessService(
        private_members={"private-fixture": {"member@example.com"}}
    )
    app = create_app(search_service=service, access_service=access_service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            headers={"X-User-Email": "member@example.com"},
            json={"query": "algorithms", "collection": "private-fixture"},
        )

    assert response.status_code == 200
    assert access_service.calls == [
        {
            "collection_name": "private-fixture",
            "user_email_header": "member@example.com",
        }
    ]
    assert service.calls[0]["collection"] == "private-fixture"


@pytest.mark.anyio
async def test_post_search_private_collection_denied_for_wrong_user() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        access_service=FakeAccessService(
            private_members={"private-fixture": {"member@example.com"}}
        ),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            headers={"X-User-Email": "other@example.com"},
            json={"query": "algorithms", "collection": "private-fixture"},
        )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_post_search_forbidden_collection_short_circuits_before_search() -> None:
    from src.main import create_app

    service = InvalidFilterSearchService()
    app = create_app(
        search_service=service,
        access_service=FakeAccessService(
            private_members={"private-fixture": {"member@example.com"}}
        ),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            headers={"X-User-Email": "other@example.com"},
            json={
                "query": "algorithms",
                "collection": "private-fixture",
                "filters": [{"field": "topic", "op": "eq", "value": "Trees"}],
            },
        )

    assert response.status_code == 403
    assert service.calls == []


@pytest.mark.anyio
async def test_post_search_missing_collection_from_access_layer_returns_404() -> None:
    from src.main import create_app

    service = FakeSearchService()
    app = create_app(
        search_service=service,
        access_service=FakeAccessService(missing_collections={"missing-fixture"}),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={"query": "algorithms", "collection": "missing-fixture"},
        )

    assert response.status_code == 404
    assert service.calls == []
