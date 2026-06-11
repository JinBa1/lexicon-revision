from __future__ import annotations

import httpx
import pytest
from src.access.models import RequestIdentity
from src.jobs.config import IngestQueueSettings
from src.runtime.config import AppRuntimeSettings, RateLimitSettings
from src.search.providers.config import (
    EmbeddingProviderSettings,
    RerankProviderSettings,
    RetrievalProviderSettings,
)
from src.storage.config import ObjectStorageSettings
from src.study.config import StudySettings


@pytest.mark.anyio
async def test_new_endpoints_respond_to_cors_preflight() -> None:
    from src.main import create_app

    class _FakeAccessService:
        def list_collections(self, *, request_identity):
            return []

        def list_supported_universities(self):
            return []

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
        rate_limit=RateLimitSettings(
            redis_url="rediss://default:secret@example.upstash.io:6379",
            key_secret="prod-secret",
            search_user="60/minute",
            search_anon="20/minute",
            study_user="10/hour",
            study_anon="3/hour",
        ),
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


def _make_prod_validate_args():
    """Return minimal valid settings objects for validate_production_profile."""
    from src.runtime.config import validate_production_profile

    runtime_settings = AppRuntimeSettings(
        environment="prod",
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
            redis_url="rediss://default:secret@example.upstash.io:6379",
            key_secret="prod-secret",
            search_user="60/minute",
            search_anon="20/minute",
            study_user="10/hour",
            study_anon="3/hour",
        ),
    )
    retrieval_settings = RetrievalProviderSettings(
        embedding=EmbeddingProviderSettings(provider="voyage", model="voyage-3"),
        rerank=RerankProviderSettings(provider="voyage", model="rerank-2"),
        rerank_enabled=False,
        voyage_api_key="test-key",
    )
    study_settings = StudySettings(
        generation={"provider": "anthropic"},
        planning={"provider": "anthropic"},
    )
    storage_settings = ObjectStorageSettings(provider="s3", local=None, s3=None)
    return (
        validate_production_profile,
        runtime_settings,
        retrieval_settings,
        study_settings,
        storage_settings,
    )


def test_memory_ingest_queue_fails_prod_profile_validation() -> None:
    from src.runtime.config import validate_production_profile

    _, runtime_settings, retrieval_settings, study_settings, storage_settings = (
        _make_prod_validate_args()
    )

    with pytest.raises(ValueError, match="memory ingest queue"):
        validate_production_profile(
            runtime_settings,
            retrieval_settings,
            study_settings,
            storage_settings,
            ingest_queue_settings=IngestQueueSettings(
                provider="memory", queue_url=None
            ),
        )


def test_sqs_and_none_ingest_queue_pass_prod_profile_validation() -> None:
    from src.runtime.config import validate_production_profile

    _, runtime_settings, retrieval_settings, study_settings, storage_settings = (
        _make_prod_validate_args()
    )

    # SQS provider passes
    validate_production_profile(
        runtime_settings,
        retrieval_settings,
        study_settings,
        storage_settings,
        ingest_queue_settings=IngestQueueSettings(
            provider="sqs",
            queue_url="https://sqs.eu-west-2.amazonaws.com/123/q",
        ),
    )

    # None (not provided) passes
    validate_production_profile(
        runtime_settings,
        retrieval_settings,
        study_settings,
        storage_settings,
    )
