from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Request
from src.access.errors import CollectionAccessDeniedError, IdentityProvisioningError
from src.access.models import (
    AuthenticatedUser,
    AuthorizationContext,
    CollectionAccess,
    RequestIdentity,
    ResolvedIdentity,
)
from src.metadata_schema.models import CollectionMetadataSchema, FilterCondition
from src.runtime.config import AppRuntimeSettings, RateLimitSettings
from src.runtime.rate_limit import RateLimitDecision, RateLimitUnavailableError
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


class SchemaCapableSearchService(FakeSearchService):
    def get_collection_schema(self, collection: str) -> CollectionMetadataSchema:
        del collection
        return CollectionMetadataSchema.model_validate(
            {
                "version": 1,
                "fields": [
                    {
                        "key": "year",
                        "label": "Year",
                        "type": "integer",
                        "operators": ["eq", "gte", "lte"],
                    }
                ],
            }
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


class SignedInAccessService(FakeAccessService):
    def authorize_collection(
        self,
        *,
        collection_name: str,
        request_identity: RequestIdentity,
    ) -> AuthorizationContext:
        super().authorize_collection(
            collection_name=collection_name,
            request_identity=request_identity,
        )
        return AuthorizationContext(
            collection=CollectionAccess(
                collection_id="collection-1",
                collection_name=collection_name,
                community_id=None,
            ),
            identity=ResolvedIdentity(
                request_identity=request_identity,
                user=AuthenticatedUser(
                    user_id="app-user-1",
                    email=request_identity.email or "student@example.com",
                ),
            ),
        )


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


class FakeCostRateLimiter:
    def __init__(
        self,
        *,
        decision: RateLimitDecision | None = None,
        unavailable: bool = False,
    ) -> None:
        self.decision = decision or RateLimitDecision(
            allowed=True,
            endpoint="search",
            policy="search:ip",
            scope="ip",
            limit=20,
            remaining=19,
            reset_epoch_seconds=1770000060,
        )
        self.unavailable = unavailable
        self.calls: list[dict[str, object]] = []

    async def check(
        self,
        *,
        endpoint: str,
        auth_context: object | None,
        fly_client_ip: str | None,
        client_host: str | None,
    ) -> RateLimitDecision:
        self.calls.append(
            {
                "endpoint": endpoint,
                "auth_context": auth_context,
                "fly_client_ip": fly_client_ip,
                "client_host": client_host,
            }
        )
        if self.unavailable:
            raise RateLimitUnavailableError("redis unavailable")
        if self.decision.endpoint != endpoint:
            return RateLimitDecision(
                allowed=self.decision.allowed,
                endpoint=endpoint,
                policy=f"{endpoint}:{self.decision.scope}",
                scope=self.decision.scope,
                limit=self.decision.limit,
                remaining=self.decision.remaining,
                reset_epoch_seconds=self.decision.reset_epoch_seconds,
                retry_after_seconds=self.decision.retry_after_seconds,
                client_host_missing=self.decision.client_host_missing,
            )
        return self.decision

    async def health(self) -> str:
        return "ok"

    async def aclose(self) -> None:
        return None


class HangingCostRateLimiter(FakeCostRateLimiter):
    async def check(
        self,
        *,
        endpoint: str,
        auth_context: object | None,
        fly_client_ip: str | None,
        client_host: str | None,
    ) -> RateLimitDecision:
        self.calls.append(
            {
                "endpoint": endpoint,
                "auth_context": auth_context,
                "fly_client_ip": fly_client_ip,
                "client_host": client_host,
            }
        )
        await asyncio.sleep(1)
        return self.decision


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
        rate_limit=RateLimitSettings(
            redis_url="redis://localhost:6379/0",
            key_secret="test-secret",
            search_user="60/minute",
            search_anon="20/minute",
            study_user="10/hour",
            study_anon="3/hour",
        ),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
async def test_post_search_blocked_by_cost_limiter_returns_429_and_skips_service() -> (
    None
):
    from src.main import create_app

    service = FakeSearchService()
    repository = FakeUsageLogRepository()
    limiter = FakeCostRateLimiter(
        decision=RateLimitDecision(
            allowed=False,
            endpoint="search",
            policy="search:user",
            scope="user",
            limit=60,
            remaining=0,
            reset_epoch_seconds=1770000042,
            retry_after_seconds=42,
        )
    )
    app = create_app(
        search_service=service,
        access_service=SignedInAccessService(),
        auth_resolver=FakeAuthResolver(
            RequestIdentity(
                provider="stub_header",
                external_subject="student@example.com",
                email="student@example.com",
            )
        ),
        usage_log_repository=repository,
        rate_limiter=limiter,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/search",
            json={"query": "algorithms", "collection": "fixture", "rerank": False},
        )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"
    assert response.headers["X-RateLimit-Limit"] == "60"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["X-RateLimit-Reset"] == "1770000042"
    assert response.json()["detail"] == {
        "code": "rate_limited",
        "message": "Too many requests. Try again later.",
        "endpoint": "search",
        "scope": "user",
        "retry_after_seconds": 42,
    }
    assert service.calls == []
    assert len(limiter.calls) == 1
    assert len(repository.records) == 1
    assert repository.records[0].outcome == "rate_limited"
    assert repository.records[0].app_user_id == "app-user-1"
    assert repository.records[0].detail["rate_limit"]["policy"] == "search:user"


@pytest.mark.anyio
async def test_post_search_limiter_unavailable_returns_503_and_skips_service() -> None:
    from src.main import create_app

    service = FakeSearchService()
    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=service,
        usage_log_repository=repository,
        rate_limiter=FakeCostRateLimiter(unavailable=True),
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

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "rate_limit_unavailable",
        "message": "Request limits are temporarily unavailable. Try again later.",
    }
    assert service.calls == []
    assert repository.records[0].outcome == "service_unavailable"
    assert repository.records[0].detail == {
        "status_code": 503,
        "rate_limit_error": "unavailable",
    }


@pytest.mark.anyio
async def test_post_search_limiter_timeout_returns_503_and_skips_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.main as main_module

    service = FakeSearchService()
    repository = FakeUsageLogRepository()
    monkeypatch.setattr(main_module, "RATE_LIMIT_CHECK_TIMEOUT_SECONDS", 0.01)
    app = main_module.create_app(
        search_service=service,
        usage_log_repository=repository,
        rate_limiter=HangingCostRateLimiter(),
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

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "rate_limit_unavailable",
        "message": "Request limits are temporarily unavailable. Try again later.",
    }
    assert service.calls == []
    assert repository.records[0].outcome == "service_unavailable"
    assert repository.records[0].detail == {
        "status_code": 503,
        "rate_limit_error": "unavailable",
    }


@pytest.mark.anyio
async def test_post_search_validation_failure_does_not_charge_limiter() -> None:
    from src.main import create_app

    limiter = FakeCostRateLimiter()
    app = create_app(
        search_service=FakeSearchService(),
        runtime_settings=_runtime_settings(query_max_chars=10),
        rate_limiter=limiter,
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
                "limit": 10,
                "rerank": False,
            },
        )

    assert response.status_code == 422
    assert limiter.calls == []


@pytest.mark.anyio
async def test_post_search_schema_filter_validation_skips_limiter_and_service() -> None:
    from src.main import create_app

    limiter = FakeCostRateLimiter()
    service = SchemaCapableSearchService()
    app = create_app(
        search_service=service,
        rate_limiter=limiter,
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
                "rerank": False,
            },
        )

    assert response.status_code == 422
    assert "not declared in collection metadata schema" in response.json()["detail"]
    assert limiter.calls == []
    assert service.calls == []


@pytest.mark.anyio
async def test_post_search_allowed_usage_log_includes_rate_limit_metadata() -> None:
    from src.main import create_app

    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=FakeSearchService(),
        usage_log_repository=repository,
        rate_limiter=FakeCostRateLimiter(
            decision=RateLimitDecision(
                allowed=True,
                endpoint="search",
                policy="search:ip",
                scope="ip",
                limit=20,
                remaining=19,
                reset_epoch_seconds=1770000060,
            )
        ),
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
    assert repository.records[0].detail["rate_limit"] == {
        "policy": "search:ip",
        "scope": "ip",
        "limit": 20,
        "remaining": 19,
        "reset_epoch_seconds": 1770000060,
    }


@pytest.mark.anyio
async def test_post_search_logs_usage_on_success() -> None:
    from src.main import create_app

    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=FakeSearchService(),
        runtime_settings=_runtime_settings(),
        usage_log_repository=repository,
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
    rate_limiter = FakeCostRateLimiter()
    app = main_module.create_app(rate_limiter=rate_limiter)

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
        "RedisCostRateLimiter",
        lambda *, settings: FakeCostRateLimiter(),
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
    assert len(rate_limiter.calls) == 1
    assert rate_limiter.calls[0]["endpoint"] == "search"
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
    app = create_app(
        search_service=service,
        access_service=access_service,
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
        rate_limiter=FakeCostRateLimiter(),
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
