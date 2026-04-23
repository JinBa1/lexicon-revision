from __future__ import annotations

import httpx
import pytest
from src.access.models import SupportedUniversityRecord


class FakeAccessRepoWithUniversities:
    def __init__(self, universities: list[SupportedUniversityRecord]) -> None:
        self._universities = universities

    def list_supported_universities(self) -> list[SupportedUniversityRecord]:
        return list(self._universities)


@pytest.mark.anyio
async def test_get_supported_universities_returns_list() -> None:
    from src.main import create_app

    records = [
        SupportedUniversityRecord(
            community_id="c-cam",
            display_name="Cambridge",
            email_domains=("cam.ac.uk",),
        ),
        SupportedUniversityRecord(
            community_id="c-ox",
            display_name="Oxford",
            email_domains=("ox.ac.uk",),
        ),
    ]

    app = create_app(
        search_service=object(),
        access_service=_FakeAccessServiceWithRepo(
            FakeAccessRepoWithUniversities(records)
        ),
        allow_unauthorized_test_mode=True,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/supported-universities")

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {"id": "c-cam", "display_name": "Cambridge", "email_domains": ["cam.ac.uk"]},
        {"id": "c-ox", "display_name": "Oxford", "email_domains": ["ox.ac.uk"]},
    ]


class _FakeAccessServiceWithRepo:
    def __init__(self, repository) -> None:
        self.repository = repository

    def list_supported_universities(self) -> list[SupportedUniversityRecord]:
        return self.repository.list_supported_universities()


@pytest.mark.anyio
async def test_get_supported_universities_empty_list_returns_empty_array() -> None:
    from src.main import create_app

    app = create_app(
        search_service=object(),
        access_service=_FakeAccessServiceWithRepo(FakeAccessRepoWithUniversities([])),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/supported-universities")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_get_supported_universities_logs_usage_on_success() -> None:
    from src.main import create_app
    from src.runtime.usage_logs import RequestUsageLogRecord

    class _FakeUsageRepo:
        def __init__(self) -> None:
            self.records: list[RequestUsageLogRecord] = []

        def insert(self, record: RequestUsageLogRecord) -> None:
            self.records.append(record)

    usage_repo = _FakeUsageRepo()
    app = create_app(
        search_service=object(),
        access_service=_FakeAccessServiceWithRepo(FakeAccessRepoWithUniversities([])),
        usage_log_repository=usage_repo,
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/supported-universities")

    assert response.status_code == 200
    assert len(usage_repo.records) == 1
    record = usage_repo.records[0]
    assert record.endpoint == "supported_universities"
    assert record.outcome == "ok"


@pytest.mark.anyio
async def test_get_supported_universities_sets_cache_control_header() -> None:
    from src.main import create_app

    app = create_app(
        search_service=object(),
        access_service=_FakeAccessServiceWithRepo(FakeAccessRepoWithUniversities([])),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/supported-universities")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=3600"


@pytest.mark.anyio
async def test_get_supported_universities_uses_service_method() -> None:
    from src.main import create_app

    records = [
        SupportedUniversityRecord(
            community_id="c-cam",
            display_name="Cambridge",
            email_domains=("cam.ac.uk",),
        )
    ]

    class _FakeAccessService:
        def list_supported_universities(self) -> list[SupportedUniversityRecord]:
            return list(records)

        @property
        def repository(self):
            raise AssertionError(
                "route should not reach into access_service.repository"
            )

    app = create_app(
        search_service=object(),
        access_service=_FakeAccessService(),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/supported-universities")

    assert response.status_code == 200
    assert response.json() == [
        {"id": "c-cam", "display_name": "Cambridge", "email_domains": ["cam.ac.uk"]}
    ]
