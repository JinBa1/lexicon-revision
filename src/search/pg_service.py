from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.search.models import MediaRefResponse, SearchResponse, SearchResult
from src.search.pg_repository import PgSearchRepository
from src.search.providers.base import EmbeddingProvider, RerankProvider
from src.search.service import (
    DEFAULT_CHROMA_DIR,
    DEFAULT_COLLECTION,
    RERANK_CANDIDATE_CAP,
    _is_valid_chunk_level,
)

logger = logging.getLogger(__name__)


class PgSearchService:
    def __init__(
        self,
        *,
        repository: PgSearchRepository,
        embedding_model: EmbeddingProvider,
        embedding_dimension: int,
        reranker: RerankProvider | None = None,
        media_dir: str = DEFAULT_CHROMA_DIR,
    ) -> None:
        self._repository = repository
        self._embedding_model = embedding_model
        self._embedding_dimension = embedding_dimension
        self._reranker = reranker
        self._media_dir = media_dir
        self._media_cache: dict[str, dict[str, list[dict[str, Any]]]] = {}

    @property
    def embedding_model_id(self) -> str:
        return self._embedding_model.model_id

    @property
    def rerank_model_id(self) -> str | None:
        if self._reranker is None:
            return None
        return self._reranker.model_id

    def search(
        self,
        query: str,
        collection: str = DEFAULT_COLLECTION,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
        rerank: bool = True,
    ) -> SearchResponse:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if rerank and limit > RERANK_CANDIDATE_CAP:
            raise ValueError(
                f"limit cannot exceed rerank candidate cap of {RERANK_CANDIDATE_CAP}"
            )

        n_candidates = min(limit * 3, RERANK_CANDIDATE_CAP) if rerank else limit

        embedding_result = self._embedding_model.embed_query(query)
        if len(embedding_result.vectors) != 1:
            raise RuntimeError("embedder must return exactly one query vector")
        query_vector = list(embedding_result.vectors[0])

        rows = self._repository.search(
            collection_name=collection,
            query_vector=query_vector,
            embedding_model_id=self._embedding_model.model_id,
            embedding_dimension=self._embedding_dimension,
            filters=filters or {},
            limit=n_candidates,
        )

        if not rows:
            return SearchResponse(
                query=query,
                collection=collection,
                results=[],
                total=0,
            )

        scores = [row.score for row in rows]
        texts = [row.text for row in rows]

        if rerank and self._reranker is not None:
            rerank_result = self._reranker.rerank(query, texts)
            if len(rerank_result.scores) != len(texts):
                raise RuntimeError("reranker score count must match document count")
            rerank_scores = list(rerank_result.scores)

            ranked = sorted(
                zip(rows, rerank_scores, strict=True),
                key=lambda pair: pair[1],
                reverse=True,
            )
            rows = [pair[0] for pair in ranked]
            scores = [pair[1] for pair in ranked]

        media_map = self._load_media_map(collection)
        results = []
        for row, score in zip(rows[:limit], scores[:limit], strict=True):
            if not _is_valid_chunk_level(row.chunk_level):
                logger.warning(
                    "Skipping chunk %s in collection %s due to invalid chunk_level %r",
                    row.chunk_id,
                    collection,
                    row.chunk_level,
                )
                continue
            results.append(
                SearchResult(
                    chunk_id=row.chunk_id,
                    chunk_level=row.chunk_level,
                    parent_chunk_id=row.parent_chunk_id,
                    sub_question_label=row.sub_question_label,
                    text=row.text,
                    score=score,
                    metadata=row.metadata,
                    media=[
                        MediaRefResponse(
                            media_id=media_ref.get("media_id", ""),
                            kind=media_ref.get("kind", ""),
                            file_path=media_ref.get("file_path"),
                            relation=media_ref.get("relation", ""),
                        )
                        for media_ref in media_map.get(row.chunk_id, [])
                    ],
                )
            )

        return SearchResponse(
            query=query,
            collection=collection,
            results=results,
            total=len(results),
        )

    def _load_media_map(self, collection: str) -> dict[str, list[dict[str, Any]]]:
        if collection in self._media_cache:
            return self._media_cache[collection]

        sidecar_path = Path(self._media_dir) / f"{collection}_media_map.json"
        if not sidecar_path.exists():
            self._media_cache[collection] = {}
            return self._media_cache[collection]

        try:
            media_map = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning(
                "Failed to load media sidecar at %s; returning empty media lists",
                sidecar_path,
            )
            self._media_cache[collection] = {}
            return self._media_cache[collection]

        if not _is_valid_media_map(media_map):
            logger.warning(
                "Media sidecar at %s has invalid shape; returning empty media lists",
                sidecar_path,
            )
            self._media_cache[collection] = {}
            return self._media_cache[collection]

        self._media_cache[collection] = media_map
        return media_map


def _is_valid_media_map(value: Any) -> bool:
    if not isinstance(value, dict):
        return False

    for chunk_id, refs in value.items():
        if not isinstance(chunk_id, str) or not isinstance(refs, list):
            return False
        for ref in refs:
            if not isinstance(ref, dict):
                return False
            if not isinstance(ref.get("media_id"), str):
                return False
            if ref.get("kind") not in {"image", "table"}:
                return False
            file_path = ref.get("file_path")
            if file_path is not None and not isinstance(file_path, str):
                return False
            if ref.get("relation") not in {
                "direct",
                "inherited_shared",
                "visible_from_child",
            }:
                return False

    return True
