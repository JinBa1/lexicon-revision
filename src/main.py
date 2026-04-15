from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Query, Request
from src.search.models import SearchResponse
from src.search.service import (
    DEFAULT_CHROMA_DIR,
    DEFAULT_COLLECTION,
    EMBEDDING_MODEL_NAME,
    RERANK_CANDIDATE_CAP,
    RERANKER_MODEL_NAME,
    CollectionNotFoundError,
    SearchService,
)
from src.study.config import load_study_settings
from src.study.models import StudyRequest, StudyResponse
from src.study.providers.ollama import OllamaProvider
from src.study.service import StudyService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def _default_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Production lifespan: load real models into app.state."""
    from sentence_transformers import CrossEncoder, SentenceTransformer

    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    rerank_enabled = os.environ.get("RERANK_ENABLED", "true").lower() != "false"
    reranker = CrossEncoder(RERANKER_MODEL_NAME) if rerank_enabled else None

    app.state.search_service = SearchService(
        chroma_dir=DEFAULT_CHROMA_DIR,
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
    app.state.study_service = StudyService(
        search_service=app.state.search_service,
        provider=generation_provider,
        settings=study_settings,
    )
    yield
    if app.state.generation_provider is not None:
        await app.state.generation_provider.aclose()
    app.state.search_service = None
    app.state.study_service = None
    app.state.generation_provider = None


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
        service: StudyService = request.app.state.study_service
        return await service.orchestrate(payload)

    @application.get("/health")
    async def health(request: Request) -> dict[str, str]:
        provider = request.app.state.generation_provider
        generator_status = await provider.health()
        retrieval_status = (
            "ok" if request.app.state.search_service is not None else "error"
        )
        return {"retrieval": retrieval_status, "generator": generator_status}

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
