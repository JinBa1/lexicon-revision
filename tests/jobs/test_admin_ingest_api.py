from __future__ import annotations

import httpx
import pytest
from src.jobs.queue import InMemoryIngestJobQueue
from src.main import create_app

pytestmark = pytest.mark.anyio

ADMIN = "owner@example.com"


def _runtime_settings():
    from src.runtime.config import AppRuntimeSettings, RateLimitSettings

    return AppRuntimeSettings(
        environment="test",
        enable_dev_routes=False,
        cors_allowed_origins=[],
        request_body_max_bytes=131072,
        query_max_chars=2000,
        search_limit_max=50,
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
        admin_emails=frozenset({ADMIN}),
    )


def _build_app(queue=None):
    from tests.search.test_api import FakeSearchService

    return create_app(
        search_service=FakeSearchService(),
        allow_unauthorized_test_mode=True,
        runtime_settings=_runtime_settings(),
        ingest_queue=queue,
    )


def _payload() -> dict:
    return {
        "collection": "cam-cs-tripos",
        "paper_object_key": "source-pdfs/cam-cs-tripos/y2023p7q8.pdf",
        "parser": "cambridge",
        "university": "cam",
    }


async def _post(app, *, headers=None, json=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/admin/ingest", headers=headers, json=json)


async def test_anonymous_is_401() -> None:
    response = await _post(_build_app(InMemoryIngestJobQueue()), json=_payload())
    assert response.status_code == 401


async def test_non_admin_is_403() -> None:
    response = await _post(
        _build_app(InMemoryIngestJobQueue()),
        headers={"X-User-Email": "student@example.com"},
        json=_payload(),
    )
    assert response.status_code == 403


async def test_admin_enqueues_and_returns_202() -> None:
    queue = InMemoryIngestJobQueue()
    response = await _post(
        _build_app(queue),
        headers={"X-User-Email": ADMIN},
        json=_payload(),
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    received = queue.receive()
    assert received is not None
    assert received.message.job_id == job_id
    assert received.message.collection == "cam-cs-tripos"
    assert received.message.parser == "cambridge"


async def test_no_queue_is_503_fail_closed() -> None:
    response = await _post(
        _build_app(queue=None),
        headers={"X-User-Email": ADMIN},
        json=_payload(),
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ingest_queue_unavailable"


async def test_unknown_parser_is_422() -> None:
    payload = _payload() | {"parser": "mit"}
    response = await _post(
        _build_app(InMemoryIngestJobQueue()),
        headers={"X-User-Email": ADMIN},
        json=payload,
    )
    assert response.status_code == 422


async def test_traversal_object_key_is_422() -> None:
    payload = _payload() | {"paper_object_key": "../secrets/creds.pdf"}
    response = await _post(
        _build_app(InMemoryIngestJobQueue()),
        headers={"X-User-Email": ADMIN},
        json=payload,
    )
    assert response.status_code == 422


def _settings_with_env(environment: str):
    settings = _runtime_settings()
    from dataclasses import replace

    return replace(settings, environment=environment)


def test_verified_clerk_admin_passes_gate() -> None:
    from src.access.models import RequestIdentity
    from src.main import _is_admin_identity

    identity = RequestIdentity(
        provider="clerk",
        external_subject="user_123",
        email=ADMIN,
        email_verified=True,
    )
    assert _is_admin_identity(identity, _settings_with_env("prod")) is True


def test_unverified_stub_admin_rejected_in_prod() -> None:
    from src.access.models import RequestIdentity
    from src.main import _is_admin_identity

    identity = RequestIdentity(
        provider="stub_header",
        external_subject=ADMIN,
        email=ADMIN,
        email_verified=False,
    )
    assert _is_admin_identity(identity, _settings_with_env("prod")) is False
    assert _is_admin_identity(identity, _settings_with_env("test")) is True


def test_verified_non_admin_email_rejected() -> None:
    from src.access.models import RequestIdentity
    from src.main import _is_admin_identity

    identity = RequestIdentity(
        provider="clerk",
        external_subject="user_456",
        email="student@example.com",
        email_verified=True,
    )
    assert _is_admin_identity(identity, _settings_with_env("prod")) is False
