from __future__ import annotations

import logging
import math
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from src.metadata_schema.models import CollectionMetadataSchema, FilterCondition
from src.runtime.telemetry import ProviderCallTelemetry
from src.search.errors import (
    DEFAULT_COLLECTION,
    RERANK_CANDIDATE_CAP,
)
from src.search.filtering import validate_filter_conditions
from src.search.media_sidecar import materialize_media_refs
from src.search.models import SearchResponse, SearchResult
from src.search.pg_repository import PgSearchRepository
from src.search.providers.base import EmbeddingProvider, RerankProvider
from src.storage.base import ObjectStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchExecutionTelemetry:
    embedding: ProviderCallTelemetry
    rerank: ProviderCallTelemetry | None


class PgSearchService:
    def __init__(
        self,
        *,
        repository: PgSearchRepository,
        embedding_model: EmbeddingProvider,
        embedding_dimension: int,
        reranker: RerankProvider | None = None,
        object_storage: ObjectStorage | None = None,
        apply_collection_thresholds: bool = True,
    ) -> None:
        self._repository = repository
        self._embedding_model = embedding_model
        self._embedding_dimension = embedding_dimension
        self._reranker = reranker
        self._object_storage = object_storage
        self._apply_collection_thresholds = apply_collection_thresholds
        self._schema_cache: dict[str, CollectionMetadataSchema] = {}
        self._last_execution_telemetry_var: ContextVar[
            SearchExecutionTelemetry | None
        ] = ContextVar(
            f"pg_search_last_execution_telemetry_{id(self)}",
            default=None,
        )

    @property
    def embedding_model_id(self) -> str:
        return self._embedding_model.model_id

    @property
    def rerank_model_id(self) -> str | None:
        if self._reranker is None:
            return None
        return self._reranker.model_id

    @property
    def search_repository(self) -> PgSearchRepository:
        return self._repository

    def get_collection_schema(self, collection: str) -> CollectionMetadataSchema:
        if collection not in self._schema_cache:
            self._schema_cache[collection] = self._repository.get_collection_schema(
                collection
            )
        return self._schema_cache[collection]

    def search(
        self,
        query: str,
        collection: str = DEFAULT_COLLECTION,
        filters: list[FilterCondition] | None = None,
        limit: int = 10,
        rerank: bool = True,
    ) -> SearchResponse:
        self._last_execution_telemetry_var.set(None)
        if limit <= 0:
            raise ValueError("limit must be positive")
        if rerank and limit > RERANK_CANDIDATE_CAP:
            raise ValueError(
                f"limit cannot exceed rerank candidate cap of {RERANK_CANDIDATE_CAP}"
            )

        n_candidates = min(limit * 3, RERANK_CANDIDATE_CAP) if rerank else limit
        collection_schema = self.get_collection_schema(collection)
        validated_filters = validate_filter_conditions(filters, collection_schema)

        embedding_result = self._embedding_model.embed_query(query)
        if len(embedding_result.vectors) != 1:
            raise RuntimeError("embedder must return exactly one query vector")
        query_vector = list(embedding_result.vectors[0])
        embedding_telemetry = ProviderCallTelemetry(
            provider=embedding_result.provider,
            model=embedding_result.model_id,
            latency_ms=embedding_result.latency_ms,
            usage=embedding_result.usage,
        )

        rows = self._repository.search(
            collection_name=collection,
            query_vector=query_vector,
            embedding_model_id=self._embedding_model.model_id,
            embedding_dimension=self._embedding_dimension,
            filters=validated_filters,
            limit=n_candidates,
        )

        if not rows:
            self._last_execution_telemetry_var.set(
                SearchExecutionTelemetry(
                    embedding=embedding_telemetry,
                    rerank=None,
                )
            )
            return SearchResponse(
                query=query,
                collection=collection,
                results=[],
                total=0,
            )

        scores = [row.score for row in rows]
        texts = [row.text for row in rows]
        rerank_telemetry: ProviderCallTelemetry | None = None

        if rerank and self._reranker is not None:
            rerank_result = self._reranker.rerank(query, texts)
            if len(rerank_result.scores) != len(texts):
                raise RuntimeError("reranker score count must match document count")
            rerank_scores = list(rerank_result.scores)
            rerank_telemetry = ProviderCallTelemetry(
                provider=rerank_result.provider,
                model=rerank_result.model_id,
                latency_ms=rerank_result.latency_ms,
                usage=rerank_result.usage,
            )

            ranked = sorted(
                zip(rows, rerank_scores, strict=True),
                key=lambda pair: pair[1],
                reverse=True,
            )
            rows = [pair[0] for pair in ranked]
            scores = [pair[1] for pair in ranked]

        min_score = None
        if self._apply_collection_thresholds:
            thresholds = self._repository.get_collection_retrieval_thresholds(
                collection
            )
            if rerank_telemetry is not None:
                raw_min_score = thresholds.rerank_min_score
                threshold_name = (
                    f"collections.retrieval_rerank_min_score for {collection!r}"
                )
            else:
                raw_min_score = thresholds.vector_min_score
                threshold_name = (
                    f"collections.retrieval_vector_min_score for {collection!r}"
                )
            min_score = _validate_optional_min_score(
                raw_min_score,
                name=threshold_name,
            )
        if min_score is not None:
            scored_rows = [
                (row, score)
                for row, score in zip(rows, scores, strict=True)
                if score >= min_score
            ]
            rows = [row for row, _score in scored_rows]
            scores = [score for _row, score in scored_rows]

        if not rows:
            self._last_execution_telemetry_var.set(
                SearchExecutionTelemetry(
                    embedding=embedding_telemetry,
                    rerank=rerank_telemetry,
                )
            )
            return SearchResponse(
                query=query,
                collection=collection,
                results=[],
                total=0,
            )

        results = []
        for row, score in zip(rows, scores, strict=True):
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
                    render_blocks=row.render_blocks,
                    media=materialize_media_refs(
                        refs=row.media_refs or [],
                        object_storage=self._object_storage,
                    ),
                )
            )
            if len(results) == limit:
                break

        self._last_execution_telemetry_var.set(
            SearchExecutionTelemetry(
                embedding=embedding_telemetry,
                rerank=rerank_telemetry,
            )
        )
        return SearchResponse(
            query=query,
            collection=collection,
            results=results,
            total=len(results),
        )

    def pop_last_execution_telemetry(self) -> SearchExecutionTelemetry | None:
        telemetry = self._last_execution_telemetry_var.get()
        self._last_execution_telemetry_var.set(None)
        return telemetry


def _is_valid_chunk_level(value: Any) -> bool:
    return value in {"question", "sub_question"}


def _validate_optional_min_score(value: float | None, *, name: str) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value
