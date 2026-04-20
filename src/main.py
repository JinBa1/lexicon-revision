from __future__ import annotations

import logging
import mimetypes
from contextlib import asynccontextmanager
from inspect import isawaitable
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request, Response
from src.access import (
    X_USER_EMAIL_HEADER,
    CollectionAccessDeniedError,
    CollectionAccessService,
)
from src.access.repository import PgCollectionAccessRepository
from src.db.config import create_database_engine, load_database_settings
from src.search.base import SearchBackend
from src.search.errors import (
    RERANK_CANDIDATE_CAP,
    CollectionNotFoundError,
    InvalidMetadataFilterError,
)
from src.search.factory import create_search_service
from src.search.models import SearchRequest, SearchResponse
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
from src.study.providers.ollama import OllamaProvider
from src.study.service import StudyService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

GENERATOR_HEALTH_STATUSES = {"ok", "unreachable", "model_missing", "error"}
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _default_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Production lifespan: load real models into app.state."""
    embedding_model: object | None = None
    reranker: object | None = None
    engine: object | None = None
    object_storage: ObjectStorage | None = None
    generation_provider: object | None = None

    try:
        provider_settings = load_retrieval_provider_settings()
        embedding_model = build_embedding_provider(provider_settings)
        reranker = build_rerank_provider(provider_settings)

        db_settings = load_database_settings()
        engine = create_database_engine(db_settings)
        object_storage = build_object_storage(load_object_storage_settings())
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
        study_settings = load_study_settings()
        generation_provider = OllamaProvider(
            base_url=study_settings.generation.base_url,
            model=study_settings.generation.model,
            max_retries=study_settings.generation.max_provider_retries,
        )
        app.state.generation_provider = generation_provider

        query_planner = LLMQueryPlanner(
            provider=generation_provider,
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
        )
        yield
    finally:
        await _aclose_if_supported(generation_provider)
        _close_if_supported(embedding_model)
        _close_if_supported(reranker)
        _close_if_supported(object_storage)
        _dispose_if_supported(engine)
        app.state.object_storage = None
        app.state.access_service = None
        app.state.search_service = None
        app.state.study_service = None
        app.state.generation_provider = None


def _close_if_supported(provider: object | None) -> None:
    if provider is None or not hasattr(provider, "close"):
        return
    try:
        provider.close()
    except Exception:
        logger.exception("Failed to close retrieval provider")


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
    allow_unauthorized_test_mode: bool = False,
) -> FastAPI:
    """Create the FastAPI app with optional injected services for testing."""
    if search_service is not None:
        if access_service is None and not allow_unauthorized_test_mode:
            raise ValueError(
                "Injected apps must provide access_service or set "
                "allow_unauthorized_test_mode=True"
            )
        application = FastAPI(title="RAG Exam Revision Tool")
        application.state.object_storage = object_storage
        application.state.access_service = access_service
        application.state.search_service = search_service
        application.state.study_service = study_service
        application.state.generation_provider = generation_provider
    else:
        application = FastAPI(
            title="RAG Exam Revision Tool",
            lifespan=_default_lifespan,
        )

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

    def authorize_collection(request: Request, *, collection_name: str) -> None:
        service: CollectionAccessService | None = getattr(
            request.app.state,
            "access_service",
            None,
        )
        if service is None:
            return

        service.authorize_collection(
            collection_name=collection_name,
            user_email_header=request.headers.get(X_USER_EMAIL_HEADER),
        )

    @application.post("/search", response_model=SearchResponse)
    async def search(request: Request, payload: SearchRequest) -> SearchResponse:
        service: SearchBackend = request.app.state.search_service
        try:
            authorize_collection(request, collection_name=payload.collection)
            if payload.rerank and payload.limit > RERANK_CANDIDATE_CAP:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "limit cannot exceed rerank candidate cap of "
                        f"{RERANK_CANDIDATE_CAP}"
                    ),
                )

            return service.search(
                query=payload.query,
                collection=payload.collection,
                filters=payload.filters or None,
                limit=payload.limit,
                rerank=payload.rerank,
            )
        except CollectionAccessDeniedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except CollectionNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Collection '{exc.collection_name}' not found",
            ) from exc
        except InvalidMetadataFilterError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/study", response_model=StudyResponse)
    async def study(request: Request, payload: StudyRequest) -> StudyResponse:
        service: StudyService | None = getattr(request.app.state, "study_service", None)
        if service is None:
            raise HTTPException(
                status_code=503,
                detail="Study service is not configured",
            )
        try:
            authorize_collection(request, collection_name=payload.scope.collection)
            return await service.orchestrate(payload)
        except CollectionAccessDeniedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except CollectionNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Collection '{exc.collection_name}' not found",
            ) from exc
        except InvalidMetadataFilterError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/health")
    async def health(request: Request) -> dict[str, str]:
        provider = getattr(request.app.state, "generation_provider", None)
        generator_status = "error"
        if provider is not None:
            health_method = getattr(provider, "health", None)
            if callable(health_method):
                try:
                    health_result = health_method()
                    if isawaitable(health_result):
                        health_result = await health_result
                    if isinstance(health_result, str):
                        normalized_status = health_result.lower()
                        if normalized_status in GENERATOR_HEALTH_STATUSES:
                            generator_status = normalized_status
                except Exception:
                    generator_status = "error"
        retrieval_status = (
            "ok"
            if getattr(request.app.state, "search_service", None) is not None
            else "error"
        )
        return {"retrieval": retrieval_status, "generator": generator_status}

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
