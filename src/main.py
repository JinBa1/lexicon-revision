from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from inspect import isawaitable
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Query, Request
from src.db.config import load_database_settings
from src.search.factory import create_search_service
from src.search.models import SearchResponse
from src.search.providers.config import (
    build_embedding_provider,
    build_rerank_provider,
    load_retrieval_provider_settings,
)
from src.search.service import (
    DEFAULT_COLLECTION,
    RERANK_CANDIDATE_CAP,
    CollectionNotFoundError,
    SearchService,
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
    provider_settings = load_retrieval_provider_settings()
    embedding_model = build_embedding_provider(provider_settings)
    reranker = build_rerank_provider(provider_settings)

    db_settings = load_database_settings()
    app.state.search_service = create_search_service(
        database_settings=db_settings,
        embedding_model=embedding_model,
        reranker=reranker,
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
    if app.state.generation_provider is not None:
        await app.state.generation_provider.aclose()
    _close_if_supported(embedding_model)
    _close_if_supported(reranker)
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


def create_app(
    search_service: SearchService | None = None,
    study_service: StudyService | None = None,
    generation_provider: object | None = None,
) -> FastAPI:
    """Create the FastAPI app with optional injected services for testing."""
    if search_service is not None:
        application = FastAPI(title="RAG Exam Revision Tool")
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

    @application.get("/search", response_model=SearchResponse)
    async def search(
        request: Request,
        q: str = Query(..., description="Search query text"),
        collection: str = Query(
            DEFAULT_COLLECTION,
            description="Target collection",
        ),
        year: int | None = Query(None, description="Filter by year"),
        paper: int | None = Query(None, description="Filter by paper"),
        topic: str | None = Query(None, description="Filter by topic"),
        question_number: int | None = Query(
            None,
            description="Filter by question number",
        ),
        marks_min: int | None = Query(None, description="Minimum marks filter"),
        has_code: bool | None = Query(
            None,
            description="Filter for code questions",
        ),
        has_figure: bool | None = Query(
            None,
            description="Filter for figure questions",
        ),
        has_table: bool | None = Query(
            None,
            description="Filter for table questions",
        ),
        limit: int = Query(10, ge=1, le=100, description="Max results"),
        rerank: bool = Query(True, description="Apply cross-encoder reranking"),
    ) -> SearchResponse:
        filters: dict[str, object] = {}
        if year is not None:
            filters["year"] = year
        if paper is not None:
            filters["paper"] = paper
        if topic is not None:
            filters["topic"] = topic
        if question_number is not None:
            filters["question_number"] = question_number
        if marks_min is not None:
            filters["marks_min"] = marks_min
        if has_code is not None:
            filters["has_code"] = has_code
        if has_figure is not None:
            filters["has_figure"] = has_figure
        if has_table is not None:
            filters["has_table"] = has_table

        service: SearchService = request.app.state.search_service
        if rerank and limit > RERANK_CANDIDATE_CAP:
            raise HTTPException(
                status_code=422,
                detail=(
                    "limit cannot exceed rerank candidate cap of "
                    f"{RERANK_CANDIDATE_CAP}"
                ),
            )

        try:
            return service.search(
                query=q,
                collection=collection,
                filters=filters or None,
                limit=limit,
                rerank=rerank,
            )
        except CollectionNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Collection '{exc.collection_name}' not found",
            ) from exc

    @application.post("/study", response_model=StudyResponse)
    async def study(request: Request, payload: StudyRequest) -> StudyResponse:
        service: StudyService | None = getattr(request.app.state, "study_service", None)
        if service is None:
            raise HTTPException(
                status_code=503,
                detail="Study service is not configured",
            )
        return await service.orchestrate(payload)

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
