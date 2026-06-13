from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from src.access.errors import CollectionAccessDeniedError, IdentityProvisioningError
from src.access.models import RequestIdentity
from src.metadata_schema.models import CollectionMetadataSchema, FilterCondition
from src.runtime.config import AppRuntimeSettings, RateLimitSettings
from src.runtime.rate_limit import RateLimitDecision
from src.runtime.telemetry import ProviderCallTelemetry, TokenUsage
from src.search.errors import CollectionNotFoundError, InvalidMetadataFilterError
from src.search.pg_service import SearchExecutionTelemetry
from src.study.config import (
    ContextSettings,
    GenerationSettings,
    PlanningSettings,
    PromptSettings,
    StudySettings,
)
from src.study.models import StudyResponse
from src.study.planning.models import PlannerExecution, QueryPlan
from src.study.service import StudyService
from tests.runtime.fakes_rate_limit import (
    FakeCostRateLimiter,
    HangingCostRateLimiter,
)


class FakeStudyService:
    def __init__(self) -> None:
        self.requests = []

    async def orchestrate(self, request, request_id=None):
        self.requests.append(request)
        return StudyResponse(
            request_id=request_id or "00000000-0000-4000-8000-000000000000",
            query=request.query,
            scope=request.scope,
            answer_status="insufficient_evidence",
            answer={"overview": "", "patterns": [], "limitations": ["No match."]},
            sources=[],
            retrieval={
                "status": "empty",
                "top_k": request.top_k,
                "returned_result_count": 0,
                "context_budget_tokens": 4000,
                "context_chunk_ids": [],
                "omitted_chunk_ids": [],
                "truncated_chunk_ids": [],
                "filters_applied": request.filters,
                "rerank": True,
            },
            generation={
                "provider": "ollama",
                "model": "qwen2.5:7b-instruct",
                "prompt_version": "study_aid_v2",
                "temperature": 0.1,
                "attempt_count": 0,
                "citation_drops": 0,
                "error_category": None,
                "latency_ms": 0,
            },
            planning={
                "status": "ok",
                "planner_version": "query_planner_v1",
                "original_query": request.query,
                "semantic_queries": [request.query],
                "error_category": None,
                "latency_ms": 0,
            },
        )


class TelemetryStudyService(FakeStudyService):
    async def orchestrate(self, request, request_id=None):
        self.requests.append(request)
        return StudyResponse(
            request_id=request_id or "00000000-0000-4000-8000-000000000001",
            query=request.query,
            scope=request.scope,
            answer_status="ok",
            answer={
                "overview": "Binary search narrows an ordered interval.",
                "patterns": [],
                "limitations": [],
            },
            sources=[],
            retrieval={
                "status": "ok",
                "top_k": request.top_k,
                "returned_result_count": 1,
                "context_budget_tokens": 4000,
                "context_chunk_ids": ["cam-1"],
                "omitted_chunk_ids": [],
                "truncated_chunk_ids": [],
                "filters_applied": request.filters,
                "rerank": True,
                "search_telemetry": SearchExecutionTelemetry(
                    embedding=ProviderCallTelemetry(
                        provider="voyage",
                        model="voyage-3",
                        latency_ms=9,
                        usage=TokenUsage(total_tokens=4),
                    ),
                    rerank=None,
                ),
            },
            generation={
                "provider": "openai_compatible",
                "model": "generator-model",
                "prompt_version": "study_aid_v2",
                "temperature": 0.1,
                "attempt_count": 1,
                "citation_drops": 0,
                "error_category": None,
                "latency_ms": 15,
                "usage": TokenUsage(total_tokens=18),
            },
            planning={
                "status": "ok",
                "planner_version": "query_planner_v1",
                "original_query": request.query,
                "semantic_queries": [request.query],
                "error_category": None,
                "latency_ms": 6,
                "telemetry": ProviderCallTelemetry(
                    provider="openai_compatible",
                    model="planner-model",
                    latency_ms=6,
                    usage=TokenUsage(total_tokens=7),
                ),
            },
        )


class RequestIdEchoStudyService(FakeStudyService):
    def __init__(self) -> None:
        super().__init__()
        self.request_ids: list[str | None] = []

    async def orchestrate(self, request, request_id=None):
        self.requests.append(request)
        self.request_ids.append(request_id)
        return StudyResponse(
            request_id=request_id or "00000000-0000-4000-8000-000000000002",
            query=request.query,
            scope=request.scope,
            answer_status="insufficient_evidence",
            answer={"overview": "", "patterns": [], "limitations": ["No match."]},
            sources=[],
            retrieval={
                "status": "empty",
                "top_k": request.top_k,
                "returned_result_count": 0,
                "context_budget_tokens": 4000,
                "context_chunk_ids": [],
                "omitted_chunk_ids": [],
                "truncated_chunk_ids": [],
                "filters_applied": request.filters,
                "rerank": True,
            },
            generation={
                "provider": "ollama",
                "model": "qwen2.5:7b-instruct",
                "prompt_version": "study_aid_v2",
                "temperature": 0.1,
                "attempt_count": 0,
                "citation_drops": 0,
                "error_category": None,
                "latency_ms": 0,
            },
            planning={
                "status": "ok",
                "planner_version": "query_planner_v1",
                "original_query": request.query,
                "semantic_queries": [request.query],
                "error_category": None,
                "latency_ms": 0,
            },
        )


class InvalidFilterStudyService(FakeStudyService):
    async def orchestrate(self, request, request_id=None):
        self.requests.append(request)
        del request_id
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


class FakeProvider:
    async def health(self):
        return "ok"


class CloseTrackingProvider:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class AsyncCloseTrackingProvider:
    def __init__(self) -> None:
        self.aclose_calls = 0

    async def aclose(self) -> None:
        self.aclose_calls += 1


class DisposableEngine:
    def __init__(self) -> None:
        self.dispose_calls = 0

    def dispose(self) -> None:
        self.dispose_calls += 1


class SyncHealthProvider:
    def health(self):
        return "ok"


class InvalidHealthProvider:
    def health(self):
        return "unknown"


class BrokenHealthProvider:
    async def health(self):
        raise RuntimeError("provider failed")


class CountingHealthProvider:
    def __init__(self, result: str) -> None:
        self.result = result
        self.calls = 0

    async def health(self) -> str:
        self.calls += 1
        return self.result


class SlowStudyService:
    async def orchestrate(self, request, request_id=None):
        del request
        del request_id
        await httpx.AsyncClient().aclose()
        await asyncio.sleep(0.05)
        raise AssertionError("timeout wrapper should trigger before completion")


class ExplodingStudyService(FakeStudyService):
    async def orchestrate(self, request, request_id=None):
        self.requests.append(request)
        del request_id
        raise RuntimeError("generation provider exploded")


class SlowStreamingStudyBody:
    async def __aiter__(self):
        yield b'{"query":"dynamic programming","scope":{"collection":"cam-cs-tripos"}}'
        await asyncio.sleep(0.05)


class FakeUsageLogRepository:
    def __init__(self, *, fail: bool = False) -> None:
        self.records = []
        self.fail = fail

    def insert(self, record) -> None:
        if self.fail:
            raise RuntimeError("usage log insert failed")
        self.records.append(record)


class FakeSearchService:
    def health(self):
        return "ok"


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


class InvalidFilterQueryPlanner:
    async def plan(self, raw_query, hard_filters):
        del hard_filters
        return PlannerExecution(
            plan=QueryPlan(
                original_query=raw_query,
                semantic_queries=[raw_query],
            ),
            telemetry=ProviderCallTelemetry(
                provider="raw_query",
                model="raw_query",
                latency_ms=0,
                usage=None,
            ),
        )


class InvalidFilterPlannedRetrieval:
    def retrieve(
        self,
        plan,
        *,
        hard_filters,
        collection,
        limit,
        rerank=True,
    ):
        del plan, hard_filters, collection, limit, rerank
        raise InvalidMetadataFilterError(
            "Filter field 'topic' is not declared in collection metadata schema"
        )


def _study_settings() -> StudySettings:
    return StudySettings(
        generation=GenerationSettings(
            request_timeout_seconds=5,
            total_generation_deadline_seconds=10,
            schema_repair_retries=1,
        ),
        context=ContextSettings(budget_tokens=4000, max_single_chunk_tokens=1200),
        prompt=PromptSettings(
            version="study_aid_v2",
            path="prompts/study_aid_v2.yaml",
        ),
        planning=PlanningSettings(
            request_timeout_seconds=5,
            total_planning_deadline_seconds=10,
            prompt_version="query_planner_v1",
            prompt_path="prompts/query_planner_v1.yaml",
        ),
    )


def _runtime_settings(
    *,
    query_max_chars: int = 2000,
    study_top_k_max: int = 20,
    study_wall_clock_timeout_seconds: float = 45,
    enable_dev_routes: bool = False,
) -> AppRuntimeSettings:
    return AppRuntimeSettings(
        environment="test",
        enable_dev_routes=enable_dev_routes,
        cors_allowed_origins=[],
        request_body_max_bytes=131072,
        query_max_chars=query_max_chars,
        search_limit_max=50,
        study_top_k_max=study_top_k_max,
        study_context_budget_tokens=4000,
        study_generation_max_output_tokens=1200,
        study_wall_clock_timeout_seconds=study_wall_clock_timeout_seconds,
        rate_limit=_rate_limit_settings(),
    )


def _rate_limit_settings() -> RateLimitSettings:
    return RateLimitSettings(
        redis_url="redis://localhost:6379/0",
        key_secret="test-secret",
        search_user="60/minute",
        search_anon="20/minute",
        study_user="10/hour",
        study_anon="3/hour",
    )


@pytest.mark.anyio
async def test_post_study_returns_response() -> None:
    study_service = FakeStudyService()

    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=study_service,
        generation_provider=FakeProvider(),
        rate_limiter=FakeCostRateLimiter(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "cam-cs-tripos"},
            },
        )

    assert response.status_code == 200
    assert response.json()["schema_version"] == "study_answer_v2"
    assert "planning" in response.json()
    assert study_service.requests[0].query == "dynamic programming"


@pytest.mark.anyio
async def test_post_study_blocked_by_cost_limiter_returns_429_and_skips_service() -> (
    None
):
    from src.main import create_app

    study_service = FakeStudyService()
    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=FakeSearchService(),
        study_service=study_service,
        generation_provider=FakeProvider(),
        usage_log_repository=repository,
        rate_limiter=FakeCostRateLimiter(
            decision=RateLimitDecision(
                allowed=False,
                endpoint="study",
                policy="study:ip",
                scope="ip",
                limit=3,
                remaining=0,
                reset_epoch_seconds=1770000042,
                retry_after_seconds=42,
            )
        ),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={"query": "dynamic programming", "scope": {"collection": "fixture"}},
        )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"
    assert response.json()["detail"]["endpoint"] == "study"
    assert study_service.requests == []
    assert repository.records[0].outcome == "rate_limited"
    assert repository.records[0].detail["rate_limit"]["policy"] == "study:ip"


@pytest.mark.anyio
async def test_post_study_limiter_unavailable_returns_503_and_skips_service() -> None:
    from src.main import create_app

    study_service = FakeStudyService()
    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=FakeSearchService(),
        study_service=study_service,
        generation_provider=FakeProvider(),
        usage_log_repository=repository,
        rate_limiter=FakeCostRateLimiter(unavailable=True),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={"query": "dynamic programming", "scope": {"collection": "fixture"}},
        )

    assert response.status_code == 503
    assert study_service.requests == []
    assert repository.records[0].outcome == "service_unavailable"
    assert repository.records[0].detail["rate_limit_error"] == "unavailable"


@pytest.mark.anyio
async def test_post_study_limiter_timeout_returns_503_and_skips_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.main as main_module

    study_service = FakeStudyService()
    repository = FakeUsageLogRepository()
    monkeypatch.setattr(main_module, "RATE_LIMIT_CHECK_TIMEOUT_SECONDS", 0.01)
    app = main_module.create_app(
        search_service=FakeSearchService(),
        study_service=study_service,
        generation_provider=FakeProvider(),
        usage_log_repository=repository,
        rate_limiter=HangingCostRateLimiter(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={"query": "dynamic programming", "scope": {"collection": "fixture"}},
        )

    assert response.status_code == 503
    assert study_service.requests == []
    assert repository.records[0].outcome == "service_unavailable"
    assert repository.records[0].detail["rate_limit_error"] == "unavailable"


@pytest.mark.anyio
async def test_post_study_validation_failure_does_not_charge_limiter() -> None:
    from src.main import create_app

    limiter = FakeCostRateLimiter()
    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=FakeProvider(),
        runtime_settings=_runtime_settings(query_max_chars=10),
        rate_limiter=limiter,
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={"query": "x" * 11, "scope": {"collection": "fixture"}},
        )

    assert response.status_code == 422
    assert limiter.calls == []


@pytest.mark.anyio
async def test_post_study_schema_filter_validation_skips_limiter_and_service() -> None:
    from src.main import create_app

    limiter = FakeCostRateLimiter()
    study_service = FakeStudyService()
    app = create_app(
        search_service=SchemaCapableSearchService(),
        study_service=study_service,
        generation_provider=FakeProvider(),
        rate_limiter=limiter,
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "fixture"},
                "filters": [{"field": "topic", "op": "eq", "value": "Trees"}],
            },
        )

    assert response.status_code == 422
    assert "not declared in collection metadata schema" in response.json()["detail"]
    assert limiter.calls == []
    assert study_service.requests == []


@pytest.mark.anyio
async def test_post_study_public_collection_stays_anonymous_after_auth_swap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study_service = FakeStudyService()
    access_service = FakeAccessService()

    import src.main as main_module

    auth_resolver = SimpleNamespace(
        calls=[],
        resolve_request_identity=lambda request: (
            auth_resolver.calls.append(request.url.path) or RequestIdentity.anonymous()
        ),
    )
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
    monkeypatch.setattr(
        main_module,
        "create_search_service",
        lambda **kwargs: FakeSearchService(),
    )
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
    monkeypatch.setattr(main_module, "load_study_settings", _study_settings)
    monkeypatch.setattr(
        main_module,
        "build_generation_providers",
        lambda settings: (FakeProvider(), FakeProvider()),
    )
    monkeypatch.setattr(main_module, "LLMQueryPlanner", lambda **kwargs: object())
    monkeypatch.setattr(
        main_module,
        "PlannedRetrievalService",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        main_module,
        "StudyService",
        lambda **kwargs: study_service,
    )
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
                "/study",
                json={
                    "query": "dynamic programming",
                    "scope": {"collection": "public-fixture"},
                },
            )

    assert response.status_code == 200
    assert auth_resolver.calls == ["/study"]
    assert access_service.calls == [
        {
            "collection_name": "public-fixture",
            "request_identity": RequestIdentity.anonymous(),
        }
    ]
    assert study_service.requests[0].scope.collection == "public-fixture"


@pytest.mark.anyio
async def test_post_study_invalid_metadata_filter_returns_422() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=StudyService(
            query_planner=InvalidFilterQueryPlanner(),
            planned_retrieval=InvalidFilterPlannedRetrieval(),
            provider=FakeProvider(),
            settings=_study_settings(),
        ),
        generation_provider=FakeProvider(),
        rate_limiter=FakeCostRateLimiter(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={
                "query": "trees",
                "scope": {"collection": "fixture"},
                "filters": [{"field": "topic", "op": "eq", "value": "Trees"}],
            },
        )

    assert response.status_code == 422
    assert "not declared in collection metadata schema" in response.json()["detail"]


@pytest.mark.anyio
async def test_post_study_rejects_bad_top_k() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=FakeProvider(),
        rate_limiter=FakeCostRateLimiter(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "cam-cs-tripos"},
                "top_k": 51,
            },
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_post_study_rejects_query_longer_than_runtime_limit() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=FakeProvider(),
        runtime_settings=_runtime_settings(query_max_chars=10),
        rate_limiter=FakeCostRateLimiter(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={
                "query": "x" * 11,
                "scope": {"collection": "cam-cs-tripos"},
            },
        )

    assert response.status_code == 422
    assert "query length" in response.json()["detail"]


@pytest.mark.anyio
async def test_post_study_rejects_top_k_above_runtime_limit() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=FakeProvider(),
        runtime_settings=_runtime_settings(study_top_k_max=5),
        rate_limiter=FakeCostRateLimiter(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "cam-cs-tripos"},
                "top_k": 6,
            },
        )

    assert response.status_code == 422
    assert "top_k cannot exceed 5" in response.json()["detail"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad_filters",
    [
        {"topic": "Trees"},  # Legacy dict shape
        [{"field": "", "op": "eq", "value": "Trees"}],
        [{"field": "topic", "op": "contains", "value": "Trees"}],
        [{"field": "topic", "value": "Trees"}],
        [{"field": "topic", "op": "eq"}],
    ],
)
async def test_post_study_rejects_invalid_filters(bad_filters: object) -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=FakeProvider(),
        rate_limiter=FakeCostRateLimiter(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={
                "query": "q",
                "scope": {"collection": "cam-cs-tripos"},
                "filters": bad_filters,
            },
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_post_study_accepts_repeated_filter_conditions() -> None:
    study_service = FakeStudyService()

    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=study_service,
        generation_provider=FakeProvider(),
        rate_limiter=FakeCostRateLimiter(),
        allow_unauthorized_test_mode=True,
    )

    filters = [
        {"field": "year", "op": "gte", "value": 2020},
        {"field": "year", "op": "lte", "value": 2024},
    ]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "cam-cs-tripos"},
                "filters": filters,
            },
        )

    assert response.status_code == 200
    assert response.json()["retrieval"]["filters_applied"] == filters
    assert study_service.requests[0].filters == [
        FilterCondition(field="year", op="gte", value=2020),
        FilterCondition(field="year", op="lte", value=2024),
    ]


@pytest.mark.anyio
async def test_post_study_private_collection_denied_without_header() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=FakeProvider(),
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
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "private-fixture"},
            },
        )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_post_study_private_collection_allowed_for_member_header() -> None:
    from src.main import create_app

    study_service = FakeStudyService()
    access_service = FakeAccessService(
        private_members={"private-fixture": {"member@example.com"}}
    )
    app = create_app(
        search_service=FakeSearchService(),
        study_service=study_service,
        generation_provider=FakeProvider(),
        access_service=access_service,
        rate_limiter=FakeCostRateLimiter(),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            headers={"X-User-Email": "member@example.com"},
            json={
                "query": "dynamic programming",
                "scope": {"collection": "private-fixture"},
            },
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
    assert study_service.requests[0].scope.collection == "private-fixture"


@pytest.mark.anyio
async def test_post_study_forbidden_collection_short_circuits_before_generation() -> (
    None
):
    from src.main import create_app

    study_service = InvalidFilterStudyService()
    app = create_app(
        search_service=FakeSearchService(),
        study_service=study_service,
        generation_provider=FakeProvider(),
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
            "/study",
            headers={"X-User-Email": "other@example.com"},
            json={
                "query": "trees",
                "scope": {"collection": "private-fixture"},
                "filters": [{"field": "topic", "op": "eq", "value": "Trees"}],
            },
        )

    assert response.status_code == 403
    assert study_service.requests == []


@pytest.mark.anyio
async def test_post_study_missing_collection_returns_404() -> None:
    from src.main import create_app

    study_service = FakeStudyService()
    app = create_app(
        search_service=FakeSearchService(),
        study_service=study_service,
        generation_provider=FakeProvider(),
        access_service=FakeAccessService(missing_collections={"missing-fixture"}),
        rate_limiter=FakeCostRateLimiter(),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "missing-fixture"},
            },
        )

    assert response.status_code == 404
    assert study_service.requests == []


@pytest.mark.anyio
async def test_post_study_identity_provisioning_failure_returns_403() -> None:
    from src.main import create_app

    class FailingAccessService:
        def authorize_collection(
            self,
            *,
            collection_name: str,
            request_identity: RequestIdentity,
        ) -> None:
            del collection_name, request_identity
            raise IdentityProvisioningError("explicit account linking")

    study_service = FakeStudyService()
    app = create_app(
        search_service=FakeSearchService(),
        study_service=study_service,
        generation_provider=FakeProvider(),
        access_service=FailingAccessService(),
        rate_limiter=FakeCostRateLimiter(),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            headers={"X-User-Email": "member@example.com"},
            json={
                "query": "dynamic programming",
                "scope": {"collection": "private-fixture"},
            },
        )

    assert response.status_code == 403
    assert "explicit account linking" in response.json()["detail"]
    assert study_service.requests == []


@pytest.mark.anyio
async def test_default_lifespan_cleans_up_resources_on_startup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.main as main_module

    embedding_provider = CloseTrackingProvider()
    rerank_provider = CloseTrackingProvider()
    generation_provider = AsyncCloseTrackingProvider()
    planning_provider = AsyncCloseTrackingProvider()
    engine = DisposableEngine()
    app = FastAPI()

    def _raise_startup_failure(**kwargs):
        del kwargs
        raise RuntimeError("startup failed")

    monkeypatch.setattr(
        main_module, "load_retrieval_provider_settings", lambda: object()
    )
    monkeypatch.setattr(
        main_module,
        "build_embedding_provider",
        lambda settings: embedding_provider,
    )
    monkeypatch.setattr(
        main_module,
        "build_rerank_provider",
        lambda settings: rerank_provider,
    )
    monkeypatch.setattr(main_module, "load_database_settings", lambda: object())
    monkeypatch.setattr(main_module, "create_database_engine", lambda settings: engine)
    monkeypatch.setattr(main_module, "load_app_runtime_settings", _runtime_settings)
    monkeypatch.setattr(main_module, "load_object_storage_settings", lambda: object())
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
    monkeypatch.setattr(main_module, "build_object_storage", lambda settings: object())
    monkeypatch.setattr(main_module, "create_search_service", lambda **kwargs: object())
    monkeypatch.setattr(
        main_module, "PgCollectionAccessRepository", lambda *, engine: object()
    )
    monkeypatch.setattr(
        main_module, "CollectionAccessService", lambda **kwargs: object()
    )
    monkeypatch.setattr(main_module, "load_study_settings", _study_settings)
    monkeypatch.setattr(
        main_module,
        "build_generation_providers",
        lambda settings: (planning_provider, generation_provider),
    )
    monkeypatch.setattr(main_module, "LLMQueryPlanner", lambda **kwargs: object())
    monkeypatch.setattr(
        main_module,
        "PlannedRetrievalService",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(main_module, "StudyService", _raise_startup_failure)

    with pytest.raises(RuntimeError, match="startup failed"):
        async with main_module._default_lifespan(app):
            pytest.fail("lifespan should fail before yielding")

    assert embedding_provider.close_calls == 1
    assert rerank_provider.close_calls == 1
    assert planning_provider.aclose_calls == 1
    assert generation_provider.aclose_calls == 1
    assert engine.dispose_calls == 1
    assert app.state.object_storage is None
    assert app.state.runtime_settings is None
    assert app.state.access_service is None
    assert app.state.search_service is None
    assert app.state.study_service is None
    assert app.state.generation_provider is None


@pytest.mark.anyio
async def test_healthz_returns_liveness_payload() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=FakeProvider(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_health_alias_matches_healthz_liveness_payload() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=FakeProvider(),
        runtime_settings=_runtime_settings(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        healthz = await client.get("/healthz")
        health = await client.get("/health")

    assert healthz.status_code == 200
    assert health.status_code == 200
    assert healthz.json() == {"status": "ok"}
    assert health.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_readyz_checks_planning_and_generation_providers_separately() -> None:
    from src.main import create_app
    from src.runtime.readiness import ReadinessDependencies

    planning = CountingHealthProvider("ok")
    generation = CountingHealthProvider("ok")
    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        readiness_dependencies=ReadinessDependencies(
            database_probe=lambda: "ok",
            embedding_provider=SyncHealthProvider(),
            rerank_provider=None,
            planning_provider=planning,
            generation_provider=generation,
            object_storage=SyncHealthProvider(),
            rate_limiter=SyncHealthProvider(),
        ),
        runtime_settings=_runtime_settings(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/readyz")

    assert response.status_code == 200
    assert planning.calls == 1
    assert generation.calls == 1
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_post_study_returns_503_when_service_unconfigured() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        allow_unauthorized_test_mode=True,
        rate_limiter=FakeCostRateLimiter(),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "cam-cs-tripos"},
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Study service is not configured"


@pytest.mark.anyio
async def test_readyz_returns_503_when_planning_provider_unhealthy() -> None:
    from src.main import create_app
    from src.runtime.readiness import ReadinessDependencies

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        readiness_dependencies=ReadinessDependencies(
            database_probe=lambda: "ok",
            embedding_provider=SyncHealthProvider(),
            rerank_provider=None,
            planning_provider=BrokenHealthProvider(),
            generation_provider=SyncHealthProvider(),
            object_storage=SyncHealthProvider(),
            rate_limiter=SyncHealthProvider(),
        ),
        runtime_settings=_runtime_settings(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "error"


@pytest.mark.anyio
async def test_readyz_returns_503_when_rate_limiter_unhealthy() -> None:
    from src.main import create_app
    from src.runtime.readiness import ReadinessDependencies

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        readiness_dependencies=ReadinessDependencies(
            database_probe=lambda: "ok",
            embedding_provider=SyncHealthProvider(),
            rerank_provider=None,
            planning_provider=SyncHealthProvider(),
            generation_provider=SyncHealthProvider(),
            object_storage=SyncHealthProvider(),
            rate_limiter=BrokenHealthProvider(),
        ),
        runtime_settings=_runtime_settings(),
        rate_limiter=FakeCostRateLimiter(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["detail"]["checks"]["rate_limiter"] == "error"


@pytest.mark.anyio
async def test_readyz_returns_503_when_dependency_is_miswired() -> None:
    from src.main import create_app
    from src.runtime.readiness import ReadinessDependencies

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        readiness_dependencies=ReadinessDependencies(
            database_probe=lambda: "ok",
            embedding_provider=object(),
            rerank_provider=None,
            planning_provider=SyncHealthProvider(),
            generation_provider=SyncHealthProvider(),
            object_storage=SyncHealthProvider(),
            rate_limiter=SyncHealthProvider(),
        ),
        runtime_settings=_runtime_settings(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["detail"]["checks"]["embedding"] == "error"


@pytest.mark.anyio
async def test_post_study_times_out_at_runtime_wall_clock_limit_and_logs_failure() -> (
    None
):
    from src.main import create_app

    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=FakeSearchService(),
        study_service=SlowStudyService(),
        generation_provider=FakeProvider(),
        runtime_settings=_runtime_settings(study_wall_clock_timeout_seconds=0.01),
        usage_log_repository=repository,
        rate_limiter=FakeCostRateLimiter(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "cam-cs-tripos"},
            },
        )

    assert response.status_code == 504
    assert len(repository.records) == 1
    assert repository.records[0].endpoint == "study"
    assert repository.records[0].outcome == "timeout"


@pytest.mark.anyio
async def test_post_study_end_to_end_timeout_includes_pre_service_work() -> None:
    from src.main import create_app

    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=FakeProvider(),
        runtime_settings=_runtime_settings(study_wall_clock_timeout_seconds=0.01),
        usage_log_repository=repository,
        rate_limiter=FakeCostRateLimiter(),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            content=SlowStreamingStudyBody(),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 504
    assert len(repository.records) == 1
    assert repository.records[0].outcome == "timeout"


@pytest.mark.anyio
async def test_post_study_logs_usage_on_success() -> None:
    from src.main import create_app

    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=FakeSearchService(),
        study_service=TelemetryStudyService(),
        generation_provider=FakeProvider(),
        runtime_settings=_runtime_settings(),
        usage_log_repository=repository,
        rate_limiter=FakeCostRateLimiter(
            decision=RateLimitDecision(
                allowed=True,
                endpoint="study",
                policy="study:ip",
                scope="ip",
                limit=3,
                remaining=2,
                reset_epoch_seconds=1770000120,
            )
        ),
        allow_unauthorized_test_mode=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "cam-cs-tripos"},
            },
        )

    assert response.status_code == 200
    assert len(repository.records) == 1
    assert repository.records[0].endpoint == "study"
    assert repository.records[0].outcome == "ok"
    assert repository.records[0].planning is not None
    assert repository.records[0].generation is not None
    assert repository.records[0].embedding is not None
    assert repository.records[0].detail["rate_limit"] == {
        "policy": "study:ip",
        "scope": "ip",
        "limit": 3,
        "remaining": 2,
        "reset_epoch_seconds": 1770000120,
    }


@pytest.mark.anyio
async def test_post_study_passes_request_id_to_service_and_usage_log() -> None:
    from src.main import create_app

    repository = FakeUsageLogRepository()
    study_service = RequestIdEchoStudyService()
    app = create_app(
        search_service=FakeSearchService(),
        study_service=study_service,
        generation_provider=FakeProvider(),
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
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "cam-cs-tripos"},
            },
        )

    assert response.status_code == 200
    response_id = response.json()["request_id"]
    assert study_service.request_ids == [response_id]
    assert repository.records[0].request_id == response_id


@pytest.mark.anyio
async def test_post_study_usage_log_failure_does_not_break_success_response() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=TelemetryStudyService(),
        generation_provider=FakeProvider(),
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
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "cam-cs-tripos"},
            },
        )

    assert response.status_code == 200


@pytest.mark.anyio
async def test_post_study_logs_request_validation_failure_once() -> None:
    from src.main import create_app

    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=FakeProvider(),
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
            "/study",
            json={"query": "dynamic programming"},
        )

    assert response.status_code == 422
    assert len(repository.records) == 1
    assert repository.records[0].endpoint == "study"
    assert repository.records[0].outcome == "invalid_request"


@pytest.mark.anyio
async def test_post_study_logs_unexpected_internal_failure() -> None:
    from src.main import create_app

    repository = FakeUsageLogRepository()
    app = create_app(
        search_service=FakeSearchService(),
        study_service=ExplodingStudyService(),
        generation_provider=FakeProvider(),
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
            "/study",
            json={
                "query": "dynamic programming",
                "scope": {"collection": "cam-cs-tripos"},
            },
        )

    assert response.status_code == 500
    assert len(repository.records) == 1
    assert repository.records[0].outcome == "internal_error"
