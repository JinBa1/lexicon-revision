from __future__ import annotations

import httpx
import pytest
from src.study.models import StudyResponse


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
                "filters_applied": request.filters or {},
                "rerank": True,
            },
            generation={
                "provider": "ollama",
                "model": "qwen2.5:7b-instruct",
                "prompt_version": "study_aid_v1",
                "temperature": 0.1,
                "attempt_count": 0,
                "citation_drops": 0,
                "error_category": None,
                "latency_ms": 0,
            },
        )


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
    assert response.json()["schema_version"] == "study_answer_v1"
    assert study_service.requests[0].query == "dynamic programming"


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
