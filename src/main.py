from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import time
import uuid
from contextlib import asynccontextmanager
from inspect import isawaitable
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text
from src.access import (
    AuthorizationContext,
    CollectionAccessDeniedError,
    CollectionAccessService,
    HeaderEmailRequestIdentityResolver,
    IdentityProvisioningError,
    RequestIdentityResolver,
)
from src.access.repository import PgCollectionAccessRepository
from src.db.config import create_database_engine, load_database_settings
from src.runtime import (
    AppRuntimeSettings,
    DependencyReadinessProbe,
    InMemoryRateLimiter,
    ReadinessDependencies,
    RequestBodyTooLargeError,
    allowed_cors_origins,
    content_length_exceeds_limit,
    enforce_query_length,
    enforce_search_limit,
    enforce_study_top_k,
    load_app_runtime_settings,
    readiness_status,
    validate_production_profile,
)
from src.runtime.usage_logs import PgRequestUsageLogRepository, RequestUsageLogRecord
from src.search.base import SearchBackend
from src.search.errors import (
    RERANK_CANDIDATE_CAP,
    CollectionNotFoundError,
    InvalidMetadataFilterError,
)
from src.search.factory import create_search_service
from src.search.models import SearchRequest, SearchResponse
from src.search.pg_service import SearchExecutionTelemetry
from src.search.providers.config import (
    build_embedding_provider,
    build_rerank_provider,
    load_retrieval_provider_settings,
)
from src.storage import (
    LocalObjectStorage,
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageAuthError,
    ObjectStorageError,
    build_object_storage,
    load_object_storage_settings,
    validate_local_presigned_url,
)
from src.study.config import load_study_settings
from src.study.models import StudyRequest, StudyResponse
from src.study.planning.planner import LLMQueryPlanner
from src.study.planning.retrieval import PlannedRetrievalService
from src.study.providers.config import build_generation_providers
from src.study.service import StudyService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
logger = logging.getLogger(__name__)
OPERATIONS_ENDPOINTS = {"/search": "search", "/study": "study"}
UNKNOWN_COLLECTION_NAME = "<unknown>"


@asynccontextmanager
async def _default_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Production lifespan: load real models into app.state."""
    embedding_model: object | None = None
    reranker: object | None = None
    engine: object | None = None
    object_storage: ObjectStorage | None = None
    planner_provider: object | None = None
    generation_provider: object | None = None

    try:
        runtime_settings: AppRuntimeSettings = getattr(
            app.state,
            "runtime_settings",
            load_app_runtime_settings(),
        )
        provider_settings = load_retrieval_provider_settings()
        storage_settings = load_object_storage_settings()
        study_settings = load_study_settings()
        validate_production_profile(
            runtime_settings=runtime_settings,
            retrieval_settings=provider_settings,
            study_settings=study_settings,
            storage_settings=storage_settings,
        )
        embedding_model = build_embedding_provider(provider_settings)
        reranker = build_rerank_provider(provider_settings)

        db_settings = load_database_settings()
        engine = create_database_engine(db_settings)
        object_storage = build_object_storage(storage_settings)
        app.state.object_storage = object_storage
        app.state.search_service = create_search_service(
            database_settings=db_settings,
            embedding_model=embedding_model,
            reranker=reranker,
            engine=engine,
            object_storage=object_storage,
        )
        app.state.access_service = CollectionAccessService(
            repository=PgCollectionAccessRepository(engine=engine)
        )
        app.state.auth_resolver = HeaderEmailRequestIdentityResolver()
        planner_provider, generation_provider = build_generation_providers(
            study_settings
        )
        app.state.runtime_settings = runtime_settings
        app.state.rate_limiter = InMemoryRateLimiter(
            window_seconds=runtime_settings.rate_limit_window_seconds,
            max_requests=runtime_settings.rate_limit_max_requests,
        )
        app.state.usage_log_repository = PgRequestUsageLogRepository(engine=engine)
        app.state.readiness_dependencies = ReadinessDependencies(
            database_probe=lambda: _database_probe(engine),
            embedding_provider=embedding_model,
            rerank_provider=reranker,
            planning_provider=planner_provider,
            generation_provider=generation_provider,
            object_storage=object_storage,
        )
        app.state.planning_provider = planner_provider
        app.state.generation_provider = generation_provider

        query_planner = LLMQueryPlanner(
            provider=planner_provider,
            settings=study_settings.planning,
        )
        planned_retrieval = PlannedRetrievalService(
            search_service=app.state.search_service,
        )
        app.state.study_service = StudyService(
            query_planner=query_planner,
            planned_retrieval=planned_retrieval,
            provider=generation_provider,
            settings=study_settings,
            runtime_settings=runtime_settings,
        )
        yield
    finally:
        await _aclose_if_supported(planner_provider)
        await _aclose_if_supported(generation_provider)
        _close_if_supported(embedding_model)
        _close_if_supported(reranker)
        _close_if_supported(object_storage)
        _dispose_if_supported(engine)
        app.state.runtime_settings = None
        app.state.rate_limiter = None
        app.state.usage_log_repository = None
        app.state.readiness_dependencies = None
        app.state.object_storage = None
        app.state.access_service = None
        app.state.auth_resolver = None
        app.state.search_service = None
        app.state.study_service = None
        app.state.planning_provider = None
        app.state.generation_provider = None


def _close_if_supported(provider: object | None) -> None:
    if provider is None or not hasattr(provider, "close"):
        return
    try:
        provider.close()
    except Exception:
        logger.exception(
            "Failed to close resource",
            extra={"resource_type": type(provider).__name__},
        )


async def _aclose_if_supported(provider: object | None) -> None:
    if provider is None or not hasattr(provider, "aclose"):
        return
    try:
        close_result = provider.aclose()
        if isawaitable(close_result):
            await close_result
    except Exception:
        logger.exception("Failed to close async provider")


def _dispose_if_supported(resource: object | None) -> None:
    if resource is None or not hasattr(resource, "dispose"):
        return
    try:
        resource.dispose()
    except Exception:
        logger.exception("Failed to dispose resource")


def create_app(
    search_service: SearchBackend | None = None,
    study_service: StudyService | None = None,
    generation_provider: object | None = None,
    object_storage: ObjectStorage | None = None,
    access_service: CollectionAccessService | None = None,
    auth_resolver: RequestIdentityResolver | None = None,
    runtime_settings: AppRuntimeSettings | None = None,
    readiness_dependencies: ReadinessDependencies | None = None,
    usage_log_repository: PgRequestUsageLogRepository | None = None,
    allow_unauthorized_test_mode: bool = False,
) -> FastAPI:
    """Create the FastAPI app with optional injected services for testing."""
    runtime_settings = runtime_settings or load_app_runtime_settings()
    if search_service is not None:
        if access_service is None and not allow_unauthorized_test_mode:
            raise ValueError(
                "Injected apps must provide access_service or set "
                "allow_unauthorized_test_mode=True"
            )
        application = FastAPI(title="RAG Exam Revision Tool")
        _configure_runtime_state(
            application,
            runtime_settings=runtime_settings,
            readiness_dependencies=readiness_dependencies,
            usage_log_repository=usage_log_repository,
        )
        application.state.object_storage = object_storage
        application.state.access_service = access_service
        application.state.auth_resolver = (
            auth_resolver or HeaderEmailRequestIdentityResolver()
        )
        application.state.search_service = search_service
        application.state.study_service = study_service
        application.state.generation_provider = generation_provider
    else:
        application = FastAPI(
            title="RAG Exam Revision Tool",
            lifespan=_default_lifespan,
        )
        _configure_runtime_state(
            application,
            runtime_settings=runtime_settings,
            readiness_dependencies=readiness_dependencies,
            usage_log_repository=usage_log_repository,
        )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_cors_origins(runtime_settings),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> Response:
        await _cache_request_json(request)
        endpoint = _operation_endpoint(request)
        if endpoint is not None:
            _log_usage_best_effort(
                request,
                endpoint=endpoint,
                collection_name=_collection_name_from_request(request),
                outcome="invalid_request",
                detail={"status_code": 422},
            )
        return await request_validation_exception_handler(request, exc)

    @application.exception_handler(Exception)
    async def unexpected_exception_handler(
        request: Request,
        exc: Exception,
    ) -> Response:
        await _cache_request_json(request)
        endpoint = _operation_endpoint(request)
        if endpoint is not None:
            _log_usage_best_effort(
                request,
                endpoint=endpoint,
                collection_name=_collection_name_from_request(request),
                outcome="internal_error",
                detail={
                    "status_code": 500,
                    "exception_type": type(exc).__name__,
                },
            )
        logger.exception("Unhandled application error")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error"},
        )

    @application.middleware("http")
    async def runtime_middleware(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        request.state.request_started_at = time.monotonic()
        request.state.usage_log_attempted = False
        request.state.request_json = None

        endpoint = _operation_endpoint(request)
        if endpoint is not None:
            if content_length_exceeds_limit(
                request.headers.get("content-length"),
                max_bytes=runtime_settings.request_body_max_bytes,
            ):
                _log_usage_best_effort(
                    request,
                    endpoint=endpoint,
                    collection_name=_collection_name_from_request(request),
                    outcome="request_too_large",
                    detail={"status_code": 413},
                )
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body exceeds configured size limit"},
                )

            if endpoint == "study":
                request.state.study_deadline = (
                    asyncio.get_running_loop().time()
                    + runtime_settings.study_wall_clock_timeout_seconds
                )

            _install_body_limit_receive_wrapper(
                request,
                max_bytes=runtime_settings.request_body_max_bytes,
            )

            rate_limiter: InMemoryRateLimiter = request.app.state.rate_limiter
            allowed, retry_after = rate_limiter.allow(_rate_limit_key(request))
            if not allowed:
                _log_usage_best_effort(
                    request,
                    endpoint=endpoint,
                    collection_name=_collection_name_from_request(request),
                    outcome="rate_limited",
                    detail={"status_code": 429},
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests"},
                    headers={"Retry-After": str(retry_after)},
                )

            try:
                if endpoint == "study":
                    async with asyncio.timeout(
                        runtime_settings.study_wall_clock_timeout_seconds
                    ):
                        return await call_next(request)
                return await call_next(request)
            except RequestBodyTooLargeError:
                _log_usage_best_effort(
                    request,
                    endpoint=endpoint,
                    collection_name=_collection_name_from_request(request),
                    outcome="request_too_large",
                    detail={"status_code": 413},
                )
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body exceeds configured size limit"},
                )
            except TimeoutError:
                _log_usage_best_effort(
                    request,
                    endpoint=endpoint,
                    collection_name=_collection_name_from_request(request),
                    outcome="timeout",
                    detail={"status_code": 504},
                )
                return JSONResponse(
                    status_code=504,
                    content={"detail": "Study request exceeded runtime timeout"},
                )

        return await call_next(request)

    @application.get("/")
    async def root() -> dict[str, str]:
        return {"message": "Backend is running. Add your endpoints here."}

    @application.get("/_dev/object/{method}/{expires}/{sig}/{key:path}")
    async def dev_get_object(
        request: Request,
        method: str,
        expires: str,
        sig: str,
        key: str,
    ) -> Response:
        del method, expires, sig, key
        if not request.app.state.runtime_settings.enable_dev_routes:
            raise HTTPException(status_code=404, detail="Not found")
        storage = getattr(request.app.state, "object_storage", None)
        if not isinstance(storage, LocalObjectStorage):
            raise HTTPException(status_code=404, detail="Not found")

        try:
            validated_method, validated_key = validate_local_presigned_url(
                str(request.url),
                secret=storage.dev_presign_secret,
                base_url=storage.dev_presign_base_url,
            )
        except ObjectStorageAuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ObjectStorageError as exc:
            raise HTTPException(status_code=410, detail=str(exc)) from exc

        if validated_method != "GET":
            raise HTTPException(status_code=405, detail="Method not allowed")

        try:
            payload = storage.get_bytes(validated_key)
        except ObjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        media_type = (
            mimetypes.guess_type(validated_key)[0] or "application/octet-stream"
        )
        return Response(content=payload, media_type=media_type)

    def authorize_collection(
        request: Request,
        *,
        collection_name: str,
    ) -> AuthorizationContext | None:
        service: CollectionAccessService | None = getattr(
            request.app.state,
            "access_service",
            None,
        )
        if service is None:
            return None

        resolver: RequestIdentityResolver = request.app.state.auth_resolver
        return service.authorize_collection(
            collection_name=collection_name,
            request_identity=resolver.resolve_request_identity(request),
        )

    @application.post("/search", response_model=SearchResponse)
    async def search(request: Request, payload: SearchRequest) -> SearchResponse:
        service: SearchBackend = request.app.state.search_service
        auth_context: AuthorizationContext | None = None
        request.state.request_json = {
            "query": payload.query,
            "collection": payload.collection,
        }
        try:
            auth_context = authorize_collection(
                request,
                collection_name=payload.collection,
            )
            enforce_query_length(
                payload.query,
                max_chars=runtime_settings.query_max_chars,
            )
            enforce_search_limit(
                payload.limit,
                max_limit=runtime_settings.search_limit_max,
            )
            if payload.rerank and payload.limit > RERANK_CANDIDATE_CAP:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "limit cannot exceed rerank candidate cap of "
                        f"{RERANK_CANDIDATE_CAP}"
                    ),
                )

            response = service.search(
                query=payload.query,
                collection=payload.collection,
                filters=payload.filters or None,
                limit=payload.limit,
                rerank=payload.rerank,
            )
            telemetry = _pop_last_search_execution_telemetry(service)
            _log_usage_best_effort(
                request,
                endpoint="search",
                collection_name=payload.collection,
                outcome="ok",
                app_user_id=_app_user_id(auth_context),
                embedding=telemetry.embedding if telemetry is not None else None,
                rerank=telemetry.rerank if telemetry is not None else None,
                detail={
                    "result_count": response.total,
                    "rerank": payload.rerank,
                },
            )
            return response
        except HTTPException as exc:
            _log_usage_best_effort(
                request,
                endpoint="search",
                collection_name=payload.collection,
                outcome=_http_exception_outcome(exc),
                app_user_id=_app_user_id(auth_context),
                detail={"status_code": exc.status_code},
            )
            raise
        except CollectionAccessDeniedError as exc:
            _log_usage_best_effort(
                request,
                endpoint="search",
                collection_name=payload.collection,
                outcome="forbidden",
                app_user_id=_app_user_id(auth_context),
                detail={"status_code": 403},
            )
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except IdentityProvisioningError as exc:
            _log_usage_best_effort(
                request,
                endpoint="search",
                collection_name=payload.collection,
                outcome="forbidden",
                app_user_id=_app_user_id(auth_context),
                detail={"status_code": 403},
            )
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except CollectionNotFoundError as exc:
            _log_usage_best_effort(
                request,
                endpoint="search",
                collection_name=payload.collection,
                outcome="not_found",
                app_user_id=_app_user_id(auth_context),
                detail={"status_code": 404},
            )
            raise HTTPException(
                status_code=404,
                detail=f"Collection '{exc.collection_name}' not found",
            ) from exc
        except InvalidMetadataFilterError as exc:
            _log_usage_best_effort(
                request,
                endpoint="search",
                collection_name=payload.collection,
                outcome="invalid_request",
                app_user_id=_app_user_id(auth_context),
                detail={"status_code": 422},
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/study", response_model=StudyResponse)
    async def study(request: Request, payload: StudyRequest) -> StudyResponse:
        service: StudyService | None = getattr(request.app.state, "study_service", None)
        auth_context: AuthorizationContext | None = None
        request.state.request_json = {
            "query": payload.query,
            "scope": {"collection": payload.scope.collection},
        }
        if service is None:
            _log_usage_best_effort(
                request,
                endpoint="study",
                collection_name=payload.scope.collection,
                outcome="service_unavailable",
                detail={"status_code": 503},
            )
            raise HTTPException(
                status_code=503,
                detail="Study service is not configured",
            )
        try:
            deadline = getattr(request.state, "study_deadline", None)
            timeout_context = (
                asyncio.timeout_at(deadline)
                if isinstance(deadline, float)
                else asyncio.timeout(runtime_settings.study_wall_clock_timeout_seconds)
            )
            async with timeout_context:
                auth_context = authorize_collection(
                    request,
                    collection_name=payload.scope.collection,
                )
                enforce_query_length(
                    payload.query,
                    max_chars=runtime_settings.query_max_chars,
                )
                enforce_study_top_k(
                    payload.top_k,
                    max_top_k=runtime_settings.study_top_k_max,
                )
                response = await service.orchestrate(
                    payload,
                    request_id=_request_id(request),
                )
            _log_usage_best_effort(
                request,
                endpoint="study",
                collection_name=payload.scope.collection,
                outcome=_study_outcome(response),
                app_user_id=_app_user_id(auth_context),
                request_id=response.request_id,
                embedding=(
                    response.retrieval.search_telemetry.embedding
                    if response.retrieval.search_telemetry is not None
                    else None
                ),
                rerank=(
                    response.retrieval.search_telemetry.rerank
                    if response.retrieval.search_telemetry is not None
                    else None
                ),
                planning=response.planning.telemetry,
                generation=_generation_telemetry(response),
                detail={"answer_status": response.answer_status},
            )
            return response
        except TimeoutError as exc:
            _log_usage_best_effort(
                request,
                endpoint="study",
                collection_name=payload.scope.collection,
                outcome="timeout",
                app_user_id=_app_user_id(auth_context),
                detail={"status_code": 504},
            )
            raise HTTPException(
                status_code=504,
                detail="Study request exceeded runtime timeout",
            ) from exc
        except HTTPException as exc:
            _log_usage_best_effort(
                request,
                endpoint="study",
                collection_name=payload.scope.collection,
                outcome=_http_exception_outcome(exc),
                app_user_id=_app_user_id(auth_context),
                detail={"status_code": exc.status_code},
            )
            raise
        except CollectionAccessDeniedError as exc:
            _log_usage_best_effort(
                request,
                endpoint="study",
                collection_name=payload.scope.collection,
                outcome="forbidden",
                app_user_id=_app_user_id(auth_context),
                detail={"status_code": 403},
            )
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except IdentityProvisioningError as exc:
            _log_usage_best_effort(
                request,
                endpoint="study",
                collection_name=payload.scope.collection,
                outcome="forbidden",
                app_user_id=_app_user_id(auth_context),
                detail={"status_code": 403},
            )
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except CollectionNotFoundError as exc:
            _log_usage_best_effort(
                request,
                endpoint="study",
                collection_name=payload.scope.collection,
                outcome="not_found",
                app_user_id=_app_user_id(auth_context),
                detail={"status_code": 404},
            )
            raise HTTPException(
                status_code=404,
                detail=f"Collection '{exc.collection_name}' not found",
            ) from exc
        except InvalidMetadataFilterError as exc:
            _log_usage_best_effort(
                request,
                endpoint="study",
                collection_name=payload.scope.collection,
                outcome="invalid_request",
                app_user_id=_app_user_id(auth_context),
                detail={"status_code": 422},
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/readyz")
    async def readyz(request: Request) -> dict[str, object]:
        deps: ReadinessDependencies | None = getattr(
            request.app.state,
            "readiness_dependencies",
            None,
        )
        if deps is None:
            raise HTTPException(
                status_code=503,
                detail={"status": "error", "checks": {"runtime": "error"}},
            )

        probes = [
            DependencyReadinessProbe("database", deps.database_probe),
            DependencyReadinessProbe(
                "embedding",
                _health_probe(deps.embedding_provider),
            ),
            DependencyReadinessProbe(
                "planning",
                _health_probe(deps.planning_provider),
            ),
            DependencyReadinessProbe(
                "generation",
                _health_probe(deps.generation_provider),
            ),
            DependencyReadinessProbe(
                "object_storage",
                _health_probe(deps.object_storage),
            ),
        ]
        if deps.rerank_provider is not None:
            probes.append(
                DependencyReadinessProbe(
                    "rerank",
                    _health_probe(deps.rerank_provider),
                )
            )

        payload = await readiness_status(probes=probes)
        if payload["status"] != "ok":
            raise HTTPException(status_code=503, detail=payload)
        return payload

    return application


def _configure_runtime_state(
    application: FastAPI,
    *,
    runtime_settings: AppRuntimeSettings,
    readiness_dependencies: ReadinessDependencies | None,
    usage_log_repository: PgRequestUsageLogRepository | None,
) -> None:
    application.state.runtime_settings = runtime_settings
    application.state.rate_limiter = InMemoryRateLimiter(
        window_seconds=runtime_settings.rate_limit_window_seconds,
        max_requests=runtime_settings.rate_limit_max_requests,
    )
    application.state.usage_log_repository = usage_log_repository
    application.state.readiness_dependencies = readiness_dependencies
    application.state.planning_provider = None
    application.state.object_storage = None
    application.state.access_service = None
    application.state.auth_resolver = HeaderEmailRequestIdentityResolver()
    application.state.search_service = None
    application.state.study_service = None
    application.state.generation_provider = None


def _database_probe(engine: Engine) -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
    except Exception:
        return "error"
    return "ok"


def _parse_request_json(request: Request, body: bytes) -> dict[str, object] | None:
    if not body:
        return None
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


async def _cache_request_json(request: Request) -> None:
    if getattr(request.state, "request_json", None) is not None:
        return
    try:
        body = await request.body()
    except Exception:
        return
    request.state.request_json = _parse_request_json(request, body)


def _collection_name_from_request(request: Request) -> str:
    payload = getattr(request.state, "request_json", None)
    if not isinstance(payload, dict):
        return UNKNOWN_COLLECTION_NAME

    if "collection" in payload and isinstance(payload["collection"], str):
        return payload["collection"]

    scope = payload.get("scope")
    if isinstance(scope, dict) and isinstance(scope.get("collection"), str):
        return scope["collection"]

    return UNKNOWN_COLLECTION_NAME


def _operation_endpoint(request: Request) -> str | None:
    return OPERATIONS_ENDPOINTS.get(request.url.path)


def _rate_limit_key(request: Request) -> str:
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown-client"


def _install_body_limit_receive_wrapper(
    request: Request,
    *,
    max_bytes: int,
) -> None:
    # This currently depends on Starlette's private Request._receive attribute.
    # If Starlette changes that internal contract, fail clearly instead of
    # silently disabling the body-size guard. A proper ASGI middleware wrapper
    # remains the longer-term fix.
    original_receive = getattr(request, "_receive", None)
    if not callable(original_receive):
        raise RuntimeError(
            "request body limit wrapper requires Starlette Request._receive"
        )
    total_bytes = 0

    async def limited_receive():
        nonlocal total_bytes
        message = await original_receive()
        if message["type"] == "http.request":
            total_bytes += len(message.get("body", b""))
            if total_bytes > max_bytes:
                raise RequestBodyTooLargeError()
        return message

    request._receive = limited_receive


def _health_probe(dependency: object):
    def probe():
        health = getattr(dependency, "health", None)
        if not callable(health):
            return "error"
        return health()

    return probe


def _app_user_id(auth_context: AuthorizationContext | None) -> str | None:
    if auth_context is None or auth_context.identity.user is None:
        return None
    return auth_context.identity.user.user_id


def _request_latency_ms(request: Request) -> int:
    started = getattr(request.state, "request_started_at", None)
    if not isinstance(started, float):
        return 0
    return max(0, int((time.monotonic() - started) * 1000))


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    generated = str(uuid.uuid4())
    request.state.request_id = generated
    return generated


def _pop_last_search_execution_telemetry(
    service: SearchBackend,
) -> SearchExecutionTelemetry | None:
    pop_last_execution_telemetry = getattr(
        service,
        "pop_last_execution_telemetry",
        None,
    )
    if not callable(pop_last_execution_telemetry):
        return None
    return pop_last_execution_telemetry()


def _generation_telemetry(response: StudyResponse):
    if response.generation.provider == "" or response.generation.model == "":
        return None
    from src.runtime.telemetry import ProviderCallTelemetry

    return ProviderCallTelemetry(
        provider=response.generation.provider,
        model=response.generation.model,
        latency_ms=response.generation.latency_ms,
        usage=response.generation.usage,
    )


def _study_outcome(response: StudyResponse) -> str:
    if response.answer_status in {"ok", "partial", "insufficient_evidence"}:
        return "ok"
    if response.answer_status == "generation_failed":
        return response.generation.error_category or "generation_failed"
    if response.answer_status == "retrieval_failed":
        return "retrieval_failed"
    return response.answer_status


def _http_exception_outcome(exc: HTTPException) -> str:
    if exc.status_code == 413:
        return "request_too_large"
    if exc.status_code == 429:
        return "rate_limited"
    if exc.status_code == 504:
        return "timeout"
    if exc.status_code == 503:
        return "service_unavailable"
    if exc.status_code == 404:
        return "not_found"
    if exc.status_code == 403:
        return "forbidden"
    if exc.status_code == 422:
        return "invalid_request"
    return "error"


def _log_usage_best_effort(
    request: Request,
    *,
    endpoint: str,
    collection_name: str,
    outcome: str,
    app_user_id: str | None = None,
    request_id: str | None = None,
    embedding=None,
    rerank=None,
    planning=None,
    generation=None,
    detail: dict[str, object] | None = None,
) -> None:
    repository: PgRequestUsageLogRepository | None = getattr(
        request.app.state,
        "usage_log_repository",
        None,
    )
    if repository is None:
        return
    if getattr(request.state, "usage_log_attempted", False):
        return
    request.state.usage_log_attempted = True

    record = RequestUsageLogRecord(
        request_id=request_id or _request_id(request),
        endpoint=endpoint,
        collection_name=collection_name,
        app_user_id=app_user_id,
        outcome=outcome,
        latency_ms=_request_latency_ms(request),
        embedding=embedding,
        rerank=rerank,
        planning=planning,
        generation=generation,
        detail=detail or {},
    )
    try:
        repository.insert(record)
    except Exception:
        logger.exception(
            "Failed to persist request usage log",
            extra={
                "request_id": record.request_id,
                "endpoint": endpoint,
                "outcome": outcome,
            },
        )


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
