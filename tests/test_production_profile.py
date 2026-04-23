from __future__ import annotations

import httpx
import pytest
from src.access.models import RequestIdentity
from src.runtime.config import AppRuntimeSettings


@pytest.mark.anyio
async def test_new_endpoints_respond_to_cors_preflight() -> None:
    from src.main import create_app

    class _FakeAccessService:
        def list_collections(self, *, request_identity):
            return []

        @property
        def repository(self):
            class _Repo:
                def list_supported_universities(self):
                    return []

            return _Repo()

        def authorize_collection(self, *, collection_name, request_identity):
            from src.access.models import (
                AuthorizationContext,
                CollectionAccess,
                ResolvedIdentity,
            )

            return AuthorizationContext(
                collection=CollectionAccess(
                    collection_id="x",
                    collection_name=collection_name,
                    community_id=None,
                ),
                identity=ResolvedIdentity(request_identity=request_identity, user=None),
            )

    class _FakeResolver:
        def resolve_request_identity(self, request):
            return RequestIdentity.anonymous()

    class _Service:
        search_repository = None

    runtime_settings = AppRuntimeSettings(
        environment="test",
        enable_dev_routes=False,
        cors_allowed_origins=["http://frontend.test"],
        request_body_max_bytes=131072,
        query_max_chars=2000,
        search_limit_max=50,
        study_top_k_max=20,
        study_context_budget_tokens=4000,
        study_generation_max_output_tokens=1200,
        study_wall_clock_timeout_seconds=45,
        rate_limit_window_seconds=60,
        rate_limit_max_requests=30,
    )

    app = create_app(
        search_service=_Service(),
        access_service=_FakeAccessService(),
        auth_resolver=_FakeResolver(),
        runtime_settings=runtime_settings,
        allow_unauthorized_test_mode=True,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in (
            "/collections",
            "/supported-universities",
            "/collections/demo/chunks/q-1",
        ):
            response = await client.options(
                path,
                headers={
                    "Origin": "http://frontend.test",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert response.status_code in {200, 204}, path
            assert (
                response.headers["access-control-allow-origin"]
                == "http://frontend.test"
            )
            assert "GET" in response.headers["access-control-allow-methods"]
