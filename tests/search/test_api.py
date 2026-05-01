from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import Request
from src.access.errors import CollectionAccessDeniedError, IdentityProvisioningError
from src.access.models import RequestIdentity
from src.metadata_schema.models import FilterCondition
from src.runtime.config import AppRuntimeSettings, RateLimitSettings
from src.runtime.telemetry import ProviderCallTelemetry, TokenUsage
from src.search.errors import CollectionNotFoundError, InvalidMetadataFilterError
from src.search.models import MediaRefResponse, SearchResponse, SearchResult
from src.search.pg_service import SearchExecutionTelemetry

MEDIA_OBJECT_KEY = "artifacts/mineru/run-y2023p2q5/images/fig1.png"


class FakeSearchService:
    embedding_model_id = "test-embedding"
    rerank_model_id = None

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self._telemetry = SearchExecutionTelemetry(
            embedding=ProviderCallTelemetry(
                provider="voyage",
                model="voyage-3",
                latency_ms=12,
                usage=TokenUsage(total_tokens=5),
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

    def pop_last_execution_telemetry(self) -> SearchExecutionTelemetry | None:
        telemetry = self._telemetry
        self._telemetry = None
        return telemetry


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


class ExplodingSearchService(FakeSearchService):
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
        raise RuntimeError("embedding provider exploded")


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
        request_identity: RequestIdentity,
    ) -> None:
        self.calls.append(
            {
                "collection_name": collection_name,
                "request_identity": request_identity,
            }
        )
        if collection_name in self.missing_collections:
            raise CollectionNotFoundError(collection_name)

        allowed_members = self.private_members.get(collection_name)
        if (
            allowed_members is not None
            and request_identity.email not in allowed_members
        ):
            raise CollectionAccessDeniedError(collection_name)


class FakeAuthResolver:
    def __init__(self, identity: RequestIdentity) -> None:
        self.identity = identity
        self.calls: list[str] = []

    def resolve_request_identity(self, request: Request) -> RequestIdentity:
        self.calls.append(request.url.path)
        return self.identity


class FakeUsageLogRepository:
    def __init__(self, *, fail: bool = False) -> None:
        self.records = []
        self.fail = fail

    def insert(self, record) -> None:
        if self.fail:
            raise RuntimeError("usage log insert failed")
        self.records.append(record)


class GuardedStreamingBody:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self._index = 0

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk


class SentinelStreamingBody:
    def __init__(self) -> None:
        self.read_chunks = 0

    async def __aiter__(self):
        raise AssertionError("request body should not be consumed")


def _runtime_settings(
    *,
    request_body_max_bytes: int = 131072,
    query_max_chars: int = 2000,
    search_limit_max: int = 50,
    rate_limit_window_seconds: int = 60,
    rate_limit_max_requests: int = 30,
    enable_dev_routes: bool = False,
) -> AppRuntimeSettings:
    return AppRuntimeSettings(
        environment="test",
        enable_dev_routes=enable_dev_routes,
        cors_allowed_origins=[],
        request_body_max_bytes=request_body_max_bytes,
        query_max_chars=query_max_chars,
        search_limit_max=search_limit_max,
        study_top_k_max=20,
        study_context_budget_tokens=4000,
        study_generation_max_output_tokens=1200,
        study_wall_clock_timeout_seconds=45,
        rate_limit=_rate_limit_settings(),
        rate_limit_window_seconds=rate_limit_window_seconds,
        rate_limit_max_requests=rate_limit_max_requests,
    )


def _rate_limit_settings() -> RateLimitSettings:
    return RateLimitSettings(
        redis_url="redis://localhost:6379/0",
        key_secret="test-rate-limit-secret",
        search_user="60/minute",
        search_anon="20/minute",
        study_user="10/hour",
        study_anon="3/hour",
    )


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


def test_install_body_limit_receive_wrapper_requires_starlette_receive() -> None:
    from src.main import _install_body_limit_receive_wrapper

    with pytest.raises(
        RuntimeError,
        match="requires Starlette Request._receive",
    ):
        _install_body_limit_receive_wrapper(
            SimpleNamespace(),
            max_bytes=16,
        )


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
async def test_post_search_rejects_query_longer_than_runtime_limit() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        runtime_settings=_runtime_settings(query_max_chars=10),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={
                "query": "x" * 11,
                "collection": "fixture",
                "filters": [],
                "limit": 10,
                "rerank": False,
            },
        )

    assert response.status_code == 422
    assert "query length" in response.json()["detail"]


@pytest.mark.anyio
async def test_post_search_rejects_limit_above_runtime_limit() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        runtime_settings=_runtime_settings(search_limit_max=5),
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
                "limit": 6,
                "rerank": False,
            },
        )

    assert response.status_code == 422
    assert "limit cannot exceed 5" in response.json()["detail"]


@pytest.mark.anyio
async def test_post_search_rejects_request_body_over_runtime_limit() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        runtime_settings=_runtime_settings(request_body_max_bytes=32),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            content=(
                '{"query":"'
                + ("x" * 80)
                + '","collection":"fixture","filters":[],"limit":1,"rerank":false}'
            ),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413


@pytest.mark.anyio
async def test_post_search_rejects_over_limit_stream_before_full_read() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        runtime_settings=_runtime_settings(request_body_max_bytes=20),
        allow_unauthorized_test_mode=True,
    )
    body = SentinelStreamingBody()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            content=body,
            headers={
                "content-type": "application/json",
                "content-length": "999",
            },
        )

    assert response.status_code == 413
    assert body.read_chunks == 0


@pytest.mark.anyio
async def test_post_search_rate_limits_requests_and_sets_retry_after() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        runtime_settings=_runtime_settings(
            rate_limit_window_seconds=60,
            rate_limit_max_requests=1,
        ),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/search",
            json={"query": "algorithms", "collection": "fixture", "rerank": False},
        )
        second = await client.post(
            "/search",
            json={"query": "algorithms", "collection": "fixture", "rerank": False},
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1


@pytest.mark.anyio
async def test_post_search_rate_limit_ignores_spoofed_x_forwarded_for() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        runtime_settings=_runtime_settings(
            rate_limit_window_seconds=60,
            rate_limit_max_requests=1,
        ),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/search",
            headers={"X-Forwarded-For": "203.0.113.10"},
            json={"query": "algorithms", "collection": "fixture", "rerank": False},
        )
        second = await client.post(
            "/search",
            headers={"X-Forwarded-For": "198.51.100.77"},
            json={"query": "algorithms", "collection": "fixture", "rerank": False},
        )

    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.anyio
async def test_post_search_logs_usage_on_success() -> None:
    from src.main import create_app

    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=FakeSearchService(),
        runtime_settings=_runtime_settings(),
        usage_log_repository=repository,
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={"query": "algorithms", "collection": "fixture", "rerank": False},
        )

    assert response.status_code == 200
    assert len(repository.records) == 1
    assert repository.records[0].endpoint == "search"
    assert repository.records[0].outcome == "ok"
    assert repository.records[0].collection_name == "fixture"
    assert repository.records[0].embedding is not None
    assert repository.records[0].embedding.provider == "voyage"


@pytest.mark.anyio
async def test_post_search_usage_log_failure_does_not_break_success_response() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        runtime_settings=_runtime_settings(),
        usage_log_repository=FakeUsageLogRepository(fail=True),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={"query": "algorithms", "collection": "fixture", "rerank": False},
        )

    assert response.status_code == 200


@pytest.mark.anyio
async def test_post_search_logs_request_validation_failure_once() -> None:
    from src.main import create_app

    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=FakeSearchService(),
        runtime_settings=_runtime_settings(),
        usage_log_repository=repository,
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={"query": "algorithms"},
        )

    assert response.status_code == 422
    assert len(repository.records) == 1
    assert repository.records[0].endpoint == "search"
    assert repository.records[0].outcome == "invalid_request"


@pytest.mark.anyio
async def test_post_search_logs_unexpected_internal_failure() -> None:
    from src.main import create_app

    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=ExplodingSearchService(),
        runtime_settings=_runtime_settings(),
        usage_log_repository=repository,
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={"query": "algorithms", "collection": "fixture", "rerank": False},
        )

    assert response.status_code == 500
    assert len(repository.records) == 1
    assert repository.records[0].outcome == "internal_error"
    assert repository.records[0].collection_name == "fixture"


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
async def test_post_search_public_collection_stays_anonymous_after_auth_swap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.main as main_module

    service = FakeSearchService()
    access_service = FakeAccessService()
    auth_resolver = FakeAuthResolver(RequestIdentity.anonymous())
    app = main_module.create_app()

    monkeypatch.setattr(
        main_module, "load_retrieval_provider_settings", lambda: object()
    )
    monkeypatch.setattr(
        main_module,
        "build_embedding_provider",
        lambda settings: object(),
    )
    monkeypatch.setattr(main_module, "build_rerank_provider", lambda settings: None)
    monkeypatch.setattr(main_module, "load_database_settings", lambda: object())
    monkeypatch.setattr(
        main_module,
        "create_database_engine",
        lambda settings: object(),
    )
    monkeypatch.setattr(main_module, "load_object_storage_settings", lambda: object())
    monkeypatch.setattr(main_module, "build_object_storage", lambda settings: object())
    monkeypatch.setattr(main_module, "create_search_service", lambda **kwargs: service)
    monkeypatch.setattr(
        main_module,
        "PgCollectionAccessRepository",
        lambda *, engine: object(),
    )
    monkeypatch.setattr(
        main_module,
        "CommunityAffiliationResolver",
        lambda *, repository: object(),
        raising=False,
    )
    monkeypatch.setattr(
        main_module,
        "CollectionAccessService",
        lambda **kwargs: access_service,
    )
    monkeypatch.setattr(
        main_module,
        "load_access_auth_settings",
        lambda: SimpleNamespace(
            provider="clerk",
            clerk_secret_key="sk_test_123",
            clerk_authorized_parties=["https://example.com"],
            stub_header_name="X-User-Email",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        main_module,
        "build_request_identity_resolver",
        lambda settings: auth_resolver,
        raising=False,
    )
    monkeypatch.setattr(
        main_module,
        "load_study_settings",
        lambda: SimpleNamespace(planning=object()),
    )
    monkeypatch.setattr(
        main_module,
        "build_generation_providers",
        lambda settings: (object(), object()),
    )
    monkeypatch.setattr(main_module, "LLMQueryPlanner", lambda **kwargs: object())
    monkeypatch.setattr(
        main_module,
        "PlannedRetrievalService",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(main_module, "StudyService", lambda **kwargs: object())
    monkeypatch.setattr(
        main_module,
        "validate_production_profile",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        main_module,
        "PgRequestUsageLogRepository",
        lambda engine: FakeUsageLogRepository(),
    )

    async with main_module._default_lifespan(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/search",
                json={"query": "algorithms", "collection": "public-fixture"},
            )

    assert response.status_code == 200
    assert auth_resolver.calls == ["/search"]
    assert access_service.calls == [
        {
            "collection_name": "public-fixture",
            "request_identity": RequestIdentity.anonymous(),
        }
    ]
    assert service.calls[0]["collection"] == "public-fixture"


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
            "request_identity": RequestIdentity(
                provider="stub_header",
                external_subject="member@example.com",
                email="member@example.com",
                email_verified=False,
            ),
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


@pytest.mark.anyio
async def test_post_search_identity_provisioning_failure_returns_403() -> None:
    from src.main import create_app

    class FailingAccessService:
        def authorize_collection(
            self,
            *,
            collection_name: str,
            request_identity: RequestIdentity,
        ) -> None:
            del collection_name, request_identity
            raise IdentityProvisioningError("verified email is required")

    service = FakeSearchService()
    app = create_app(
        search_service=service,
        access_service=FailingAccessService(),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            headers={"X-User-Email": "member@example.com"},
            json={"query": "algorithms", "collection": "private-fixture"},
        )

    assert response.status_code == 403
    assert "verified email is required" in response.json()["detail"]
    assert service.calls == []


@pytest.mark.anyio
async def test_post_search_uses_custom_auth_resolver() -> None:
    from src.main import create_app

    service = FakeSearchService()
    access_service = FakeAccessService(
        private_members={"private-fixture": {"member@example.com"}}
    )
    auth_resolver = FakeAuthResolver(
        RequestIdentity(
            provider="clerk",
            external_subject="user_123",
            email="member@example.com",
            email_verified=True,
        )
    )
    app = create_app(
        search_service=service,
        access_service=access_service,
        auth_resolver=auth_resolver,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={"query": "algorithms", "collection": "private-fixture"},
        )

    assert response.status_code == 200
    assert auth_resolver.calls == ["/search"]
    assert access_service.calls == [
        {
            "collection_name": "private-fixture",
            "request_identity": RequestIdentity(
                provider="clerk",
                external_subject="user_123",
                email="member@example.com",
                email_verified=True,
            ),
        }
    ]
