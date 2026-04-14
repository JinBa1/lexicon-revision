"""Search service: embed, query ChromaDB, rerank, and join media."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol

import chromadb
from src.search.models import MediaRefResponse, SearchResponse, SearchResult

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


class Embedder(Protocol):
    """Minimal embedding-model protocol used by the service."""

    def encode(self, text: str | list[str]) -> Any: ...


class Reranker(Protocol):
    """Minimal reranker protocol used by the service."""

    def predict(self, pairs: list[tuple[str, str]]) -> Any: ...


class CollectionNotFoundError(Exception):
    """Raised when a ChromaDB collection does not exist."""

    def __init__(self, collection_name: str) -> None:
        self.collection_name = collection_name
        super().__init__(f"Collection '{collection_name}' not found")


class SearchService:
    """Retrieve and rerank chunks from a ChromaDB collection."""

    def __init__(
        self,
        embedding_model: Embedder,
        chroma_dir: str = DEFAULT_CHROMA_DIR,
        reranker: Reranker | None = None,
    ) -> None:
        self._chroma_dir = chroma_dir
        self._client = chromadb.PersistentClient(path=chroma_dir)
        self._embedding_model = embedding_model
        self._reranker = reranker
        self._media_cache: dict[str, dict[str, list[dict[str, Any]]]] = {}

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

        where = _build_where_clause(filters or {})
        n_candidates = min(limit * 3, RERANK_CANDIDATE_CAP) if rerank else limit
        query_embedding = _to_list(self._embedding_model.encode(query))

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
            pairs = list(zip([query] * len(documents), documents, strict=True))
            rerank_scores = _to_list(self._reranker.predict(pairs))
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
                    media=[
                        MediaRefResponse(
                            media_id=media_ref.get("media_id", ""),
                            kind=media_ref.get("kind", ""),
                            file_path=media_ref.get("file_path"),
                            relation=media_ref.get("relation", ""),
                        )
                        for media_ref in media_map.get(chunk_id, [])
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


def _to_list(value: Any) -> list[Any]:
    """Convert ndarray-like outputs from models into plain Python lists."""
    if hasattr(value, "tolist"):
        return value.tolist()
    return list(value)


def _is_valid_media_map(value: Any) -> bool:
    """Validate the minimal expected sidecar shape before caching."""
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


def _is_valid_chunk_level(value: Any) -> bool:
    """Accept only chunk levels the response model can represent."""
    return value in {"question", "sub_question"}
