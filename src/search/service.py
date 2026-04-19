"""Search service: embed, query ChromaDB, rerank, and join media."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import chromadb
from src.search.media_sidecar import (
    materialize_media_refs,
    validate_storage_media_map,
)
from src.search.models import SearchResponse, SearchResult
from src.search.providers.base import EmbeddingProvider, RerankProvider
from src.storage.base import ObjectStorage

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = "BAAI/bge-base-en-v1.5"
RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_CHROMA_DIR = "./chroma_data"
DEFAULT_COLLECTION = "cam-cs-tripos"
RERANK_CANDIDATE_CAP = 50

METADATA_KEYS = [
    "year",
    "paper",
    "question_number",
    "topic",
    "author",
    "tripos_part",
    "chunk_level",
    "parent_chunk_id",
    "sub_question_label",
    "marks",
    "total_marks",
    "has_code",
    "has_figure",
    "has_table",
    "source_pdf",
]


class CollectionNotFoundError(Exception):
    """Raised when a ChromaDB collection does not exist."""

    def __init__(self, collection_name: str) -> None:
        self.collection_name = collection_name
        super().__init__(f"Collection '{collection_name}' not found")


class EmbeddingModelMismatchError(Exception):
    """Raised when the collection's embedding model ID differs from the provider's."""

    def __init__(self, *, collection: str, expected: str, actual: str) -> None:
        self.collection = collection
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Collection '{collection}' was indexed with embedding model "
            f"{actual!r} but the configured query embedder is {expected!r}"
        )


class SearchService:
    """Retrieve and rerank chunks from a ChromaDB collection."""

    def __init__(
        self,
        embedding_model: EmbeddingProvider,
        chroma_dir: str = DEFAULT_CHROMA_DIR,
        reranker: RerankProvider | None = None,
        object_storage: ObjectStorage | None = None,
    ) -> None:
        self._chroma_dir = chroma_dir
        self._client = chromadb.PersistentClient(path=chroma_dir)
        self._embedding_model = embedding_model
        self._reranker = reranker
        self._object_storage = object_storage
        self._media_cache: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self._metadata_warning_collections: set[str] = set()

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
        """Run vector search with optional filtering and reranking."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        if rerank and limit > RERANK_CANDIDATE_CAP:
            raise ValueError(
                f"limit cannot exceed rerank candidate cap of {RERANK_CANDIDATE_CAP}"
            )

        try:
            search_collection = self._client.get_collection(collection)
        except chromadb.errors.NotFoundError as exc:
            raise CollectionNotFoundError(collection) from exc

        # Collection metadata guard
        coll_metadata = search_collection.metadata
        expected_model_id = self._embedding_model.model_id
        actual_model_id = (coll_metadata or {}).get("embedding_model_id")

        if actual_model_id is None:
            if collection not in self._metadata_warning_collections:
                logger.warning(
                    "Collection '%s' has no 'embedding_model_id' in metadata; "
                    "proceeding without validation",
                    collection,
                )
                self._metadata_warning_collections.add(collection)
        elif actual_model_id != expected_model_id:
            raise EmbeddingModelMismatchError(
                collection=collection,
                expected=expected_model_id,
                actual=str(actual_model_id),
            )

        where = _build_where_clause(filters or {})
        n_candidates = min(limit * 3, RERANK_CANDIDATE_CAP) if rerank else limit

        embedding_result = self._embedding_model.embed_query(query)
        if len(embedding_result.vectors) != 1:
            raise RuntimeError("embedder must return exactly one query vector")
        query_embedding = list(embedding_result.vectors[0])

        query_kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_candidates,
            "include": ["documents", "metadatas", "distances"],
        }
        if where is not None:
            query_kwargs["where"] = where

        raw_results = search_collection.query(**query_kwargs)
        ids = raw_results["ids"][0]
        documents = raw_results["documents"][0]
        metadatas = raw_results["metadatas"][0]
        distances = raw_results["distances"][0]

        if not ids:
            return SearchResponse(
                query=query,
                collection=collection,
                results=[],
                total=0,
            )

        scores = [1.0 - distance for distance in distances]
        if rerank and self._reranker is not None:
            rerank_result = self._reranker.rerank(query, list(documents))
            if len(rerank_result.scores) != len(documents):
                raise RuntimeError("reranker score count must match document count")
            rerank_scores = list(rerank_result.scores)

            ranked = sorted(
                zip(ids, documents, metadatas, rerank_scores, strict=True),
                key=lambda row: row[3],
                reverse=True,
            )
            ids = [row[0] for row in ranked]
            documents = [row[1] for row in ranked]
            metadatas = [row[2] for row in ranked]
            scores = [row[3] for row in ranked]

        media_map = self._load_media_map(collection)
        results = []
        for chunk_id, document, metadata, score in zip(
            ids[:limit],
            documents[:limit],
            metadatas[:limit],
            scores[:limit],
            strict=True,
        ):
            normalized_metadata = _normalize_metadata(metadata)
            chunk_level = normalized_metadata["chunk_level"]
            if not _is_valid_chunk_level(chunk_level):
                logger.warning(
                    "Skipping chunk %s in collection %s due to invalid chunk_level %r",
                    chunk_id,
                    collection,
                    chunk_level,
                )
                continue

            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    chunk_level=chunk_level,
                    parent_chunk_id=normalized_metadata["parent_chunk_id"],
                    sub_question_label=normalized_metadata["sub_question_label"],
                    text=document,
                    score=score,
                    metadata=normalized_metadata,
                    media=materialize_media_refs(
                        refs=media_map.get(chunk_id, []),
                        object_storage=self._object_storage,
                    ),
                )
            )

        return SearchResponse(
            query=query,
            collection=collection,
            results=results,
            total=len(results),
        )

    def _load_media_map(self, collection: str) -> dict[str, list[dict[str, Any]]]:
        """Load and cache the media sidecar for a collection."""
        if collection in self._media_cache:
            return self._media_cache[collection]

        sidecar_path = Path(self._chroma_dir) / f"{collection}_media_map.json"
        if not sidecar_path.exists():
            logger.debug(
                "Media sidecar not found at %s; returning empty media lists",
                sidecar_path,
            )
            self._media_cache[collection] = {}
            return self._media_cache[collection]

        try:
            raw_payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            logger.warning(
                "Failed to load media sidecar at %s; returning empty media lists",
                sidecar_path,
            )
            self._media_cache[collection] = {}
            return self._media_cache[collection]

        media_map = validate_storage_media_map(raw_payload)
        if media_map is None:
            logger.warning(
                "Media sidecar at %s has invalid shape; returning empty media lists",
                sidecar_path,
            )
            self._media_cache[collection] = {}
            return self._media_cache[collection]

        self._media_cache[collection] = media_map
        return media_map


def _normalize_metadata(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Ensure all spec-defined metadata keys are always present."""
    raw = raw or {}
    return {key: raw.get(key) for key in METADATA_KEYS}


def _build_where_clause(filters: dict[str, Any]) -> dict[str, Any] | None:
    """Convert flat filters into a ChromaDB where clause."""
    conditions: list[dict[str, Any]] = []
    for key, value in filters.items():
        if value is None:
            continue
        if key == "marks_min":
            conditions.append({"marks": {"$gte": value}})
        else:
            conditions.append({key: value})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _is_valid_chunk_level(value: Any) -> bool:
    """Accept only chunk levels the response model can represent."""
    return value in {"question", "sub_question"}
