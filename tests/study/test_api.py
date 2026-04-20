from __future__ import annotations

import httpx
import pytest
from src.access.errors import CollectionAccessDeniedError
from src.metadata_schema.models import FilterCondition
from src.search.errors import CollectionNotFoundError, InvalidMetadataFilterError
from src.study.config import (
    ContextSettings,
    GenerationSettings,
    PlanningSettings,
    PromptSettings,
    StudySettings,
)
from src.study.models import StudyResponse
from src.study.planning.models import QueryPlan
from src.study.service import StudyService


class FakeStudyService:
    def __init__(self) -> None:
        self.requests = []

    async def orchestrate(self, request):
        self.requests.append(request)
        return StudyResponse(
            request_id="00000000-0000-4000-8000-000000000000",
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
    async def orchestrate(self, request):
        self.requests.append(request)
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


class FakeProvider:
    async def health(self):
        return "ok"


class SyncHealthProvider:
    def health(self):
        return "ok"


class InvalidHealthProvider:
    def health(self):
        return "unknown"


class BrokenHealthProvider:
    async def health(self):
        raise RuntimeError("provider failed")


class FakeSearchService:
    def health(self):
        return "ok"


class InvalidFilterQueryPlanner:
    async def plan(self, raw_query, hard_filters):
        del hard_filters
        return QueryPlan(
            original_query=raw_query,
            semantic_queries=[raw_query],
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


@pytest.mark.anyio
async def test_post_study_returns_response() -> None:
    study_service = FakeStudyService()

    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=study_service,
        generation_provider=FakeProvider(),
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
            "user_email_header": "member@example.com",
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
async def test_health_reports_generator() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=FakeProvider(),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"retrieval": "ok", "generator": "ok"}


@pytest.mark.anyio
async def test_health_accepts_sync_generator_health() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=SyncHealthProvider(),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"retrieval": "ok", "generator": "ok"}


@pytest.mark.anyio
async def test_health_reports_error_for_unknown_generator_status() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=InvalidHealthProvider(),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"retrieval": "ok", "generator": "error"}


@pytest.mark.anyio
async def test_post_study_returns_503_when_service_unconfigured() -> None:
    from src.main import create_app

    app = create_app(search_service=FakeSearchService())

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
async def test_health_reports_error_when_generator_unconfigured() -> None:
    from src.main import create_app

    app = create_app(search_service=FakeSearchService())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"retrieval": "ok", "generator": "error"}


@pytest.mark.anyio
async def test_health_reports_error_when_generator_health_fails() -> None:
    from src.main import create_app

    app = create_app(
        search_service=FakeSearchService(),
        study_service=FakeStudyService(),
        generation_provider=BrokenHealthProvider(),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"retrieval": "ok", "generator": "error"}
