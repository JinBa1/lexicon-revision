from __future__ import annotations

import httpx
import pytest
from src.main import create_app
from src.runtime.config import AppRuntimeSettings, RateLimitSettings
from src.storage.local import LocalObjectStorage

SECRET = b"dev-route-secret"


class _FakeSearchService:
    embedding_model_id = "fake"
    rerank_model_id = None

    def search(
        self,
        query,
        collection="cam-cs-tripos",
        filters=None,
        limit=10,
        rerank=True,
    ):
        del filters, limit, rerank
        from src.search.models import SearchResponse

        return SearchResponse(query=query, collection=collection, results=[], total=0)


def _runtime_settings(*, enable_dev_routes: bool) -> AppRuntimeSettings:
    return AppRuntimeSettings(
        environment="test",
        enable_dev_routes=enable_dev_routes,
        cors_allowed_origins=[],
        request_body_max_bytes=131072,
        query_max_chars=2000,
        search_limit_max=50,
        study_top_k_max=20,
        study_context_budget_tokens=4000,
        study_generation_max_output_tokens=1200,
        study_wall_clock_timeout_seconds=45,
        rate_limit=_rate_limit_settings(),
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


@pytest.mark.anyio
async def test_dev_object_route_serves_local_presigned_get(tmp_path) -> None:
    storage = LocalObjectStorage(
        root=tmp_path / "object-store",
        dev_presign_secret=SECRET,
    )
    storage.put_bytes(
        key="artifacts/mineru/run-1/images/figure_1.png",
        data=b"png",
        content_type="image/png",
    )
    app = create_app(
        search_service=_FakeSearchService(),
        object_storage=storage,
        runtime_settings=_runtime_settings(enable_dev_routes=True),
        allow_unauthorized_test_mode=True,
    )
    presigned = storage.presign_get(
        "artifacts/mineru/run-1/images/figure_1.png",
        expires_in_seconds=60,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost:8000",
    ) as client:
        response = await client.get(presigned.url)

    assert response.status_code == 200
    assert response.content == b"png"


@pytest.mark.anyio
async def test_dev_object_route_returns_404_when_dev_routes_disabled(tmp_path) -> None:
    storage = LocalObjectStorage(
        root=tmp_path / "object-store",
        dev_presign_secret=SECRET,
    )
    storage.put_bytes(
        key="artifacts/mineru/run-1/images/figure_1.png",
        data=b"png",
        content_type="image/png",
    )
    app = create_app(
        search_service=_FakeSearchService(),
        object_storage=storage,
        runtime_settings=_runtime_settings(enable_dev_routes=False),
        allow_unauthorized_test_mode=True,
    )
    presigned = storage.presign_get(
        "artifacts/mineru/run-1/images/figure_1.png",
        expires_in_seconds=60,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost:8000",
    ) as client:
        response = await client.get(presigned.url)

    assert response.status_code == 404


@pytest.mark.anyio
async def test_dev_object_route_rejects_bad_signature(tmp_path) -> None:
    storage = LocalObjectStorage(
        root=tmp_path / "object-store",
        dev_presign_secret=SECRET,
    )
    app = create_app(
        search_service=_FakeSearchService(),
        object_storage=storage,
        runtime_settings=_runtime_settings(enable_dev_routes=True),
        allow_unauthorized_test_mode=True,
    )
    bad_url = (
        "http://localhost:8000/_dev/object/GET/9999999999/"
        + "0" * 32
        + "/artifacts/mineru/run-1/images/figure_1.png"
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost:8000",
    ) as client:
        response = await client.get(bad_url)

    assert response.status_code == 403
