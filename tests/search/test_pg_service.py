from __future__ import annotations

import json
from pathlib import Path

import pytest
from src.search.models import SearchResponse
from src.search.pg_repository import PgChunkRow
from src.search.pg_service import PgSearchService
from src.search.providers.base import EmbeddingResult, RerankResult
from src.search.service import CollectionNotFoundError


class _Embedder:
    model_id = "fake-v1"

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[[1.0, 0.0] for _ in texts], model_id=self.model_id
        )

    def embed_query(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(vectors=[[1.0, 0.0]], model_id=self.model_id)


class _Repo:
    def __init__(self) -> None:
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return [
            PgChunkRow(
                chunk_id="cam-1",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="body",
                score=0.9,
                metadata={
                    "chunk_level": "question",
                    "source_pdf": "x.pdf",
                    "has_code": False,
                    "has_figure": False,
                    "has_table": False,
                },
            )
        ]


def test_pg_search_service_returns_search_response() -> None:
    repo = _Repo()
    service = PgSearchService(
        repository=repo,
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )

    response = service.search(
        "q", collection="fixture", filters={}, limit=3, rerank=False
    )

    assert isinstance(response, SearchResponse)
    assert response.results[0].chunk_id == "cam-1"
    assert repo.calls[0]["embedding_model_id"] == "fake-v1"
    assert repo.calls[0]["embedding_dimension"] == 2


def test_pg_search_service_joins_media_from_sidecar(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "fixture_media_map.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "cam-1": [
                    {
                        "media_id": "fig-1",
                        "kind": "image",
                        "file_path": "/media/fig-1.png",
                        "relation": "direct",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    repo = _Repo()
    service = PgSearchService(
        repository=repo,
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
        media_dir=str(tmp_path),
    )

    response = service.search(
        "q", collection="fixture", filters={}, limit=3, rerank=False
    )

    assert response.results[0].media[0].media_id == "fig-1"


class _Reranker:
    model_id = "fake-rerank"

    def rerank(self, query: str, documents: list[str]) -> RerankResult:
        return RerankResult(scores=[2.0, 1.0], model_id=self.model_id)


class _TwoRowRepo:
    def search(self, **kwargs):
        return [
            PgChunkRow(
                chunk_id="cam-1",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="first",
                score=0.1,
                metadata={
                    "chunk_level": "question",
                    "source_pdf": "x.pdf",
                },
            ),
            PgChunkRow(
                chunk_id="cam-2",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="second",
                score=0.2,
                metadata={
                    "chunk_level": "question",
                    "source_pdf": "y.pdf",
                },
            ),
        ]


def test_pg_search_service_applies_rerank_order() -> None:
    service = PgSearchService(
        repository=_TwoRowRepo(),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=_Reranker(),
    )

    response = service.search(
        "q", collection="fixture", filters={}, limit=2, rerank=True
    )

    assert [result.chunk_id for result in response.results] == ["cam-1", "cam-2"]
    assert response.results[0].score == 2.0


class _MissingCollectionRepo:
    def search(self, **kwargs):
        raise CollectionNotFoundError("missing")


def test_pg_search_service_propagates_missing_collection() -> None:
    service = PgSearchService(
        repository=_MissingCollectionRepo(),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )

    with pytest.raises(CollectionNotFoundError, match="missing"):
        service.search("q", collection="missing", filters={}, limit=2, rerank=False)
