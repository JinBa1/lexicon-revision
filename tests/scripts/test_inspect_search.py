"""Infrastructure tests for inspect_search.py.

These tests exercise the CLI plumbing only. They do not measure product search
quality, real embeddings, or real reranking.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import chromadb
import numpy as np
import pytest
import scripts.inspect_search as inspect_search
from scripts.inspect_search import (
    build_search_payload,
    main,
    parse_args,
    render_json,
    render_text,
)
from src.search.models import SearchResponse, SearchResult
from src.search.providers.base import EmbeddingResult
from src.search.service import METADATA_KEYS, CollectionNotFoundError, SearchService

EMBED_DIM = 8


class ToolTestFakeEmbedder:
    """Deterministic embedder for temporary Chroma integration tests."""

    model_id = "tool-test-embedding"

    def embed_query(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[self._hash_to_vector(text).tolist()],
            model_id=self.model_id,
        )

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[self._hash_to_vector(item).tolist() for item in texts],
            model_id=self.model_id,
        )

    def encode(self, text: str | list[str]) -> np.ndarray:
        if isinstance(text, str):
            return self._hash_to_vector(text)
        return np.array([self._hash_to_vector(item) for item in text])

    def _hash_to_vector(self, text: str) -> np.ndarray:
        digest = hashlib.sha256(text.encode()).digest()
        vec = np.frombuffer(digest[:EMBED_DIM], dtype=np.uint8).astype(np.float32) + 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec


class ToolTestFakeSearchService:
    """Recording search service for CLI rendering and option tests."""

    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def search(
        self,
        query: str,
        collection: str,
        filters: dict[str, object] | None = None,
        limit: int = 10,
        rerank: bool = True,
    ) -> SearchResponse:
        self.calls.append(
            {
                "query": query,
                "collection": collection,
                "filters": filters,
                "limit": limit,
                "rerank": rerank,
            }
        )
        return self.response


class ToolTestMissingCollectionService:
    """Search service stub that always raises a collection lookup error."""

    def search(
        self,
        query: str,
        collection: str,
        filters: dict[str, object] | None = None,
        limit: int = 10,
        rerank: bool = True,
    ) -> SearchResponse:
        raise CollectionNotFoundError(collection)


def _seed_chroma(chroma_dir: Path, embedder: ToolTestFakeEmbedder) -> str:
    collection_name = "tool-test-search"
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(
        collection_name,
        metadata={"hnsw:space": "cosine", "embedding_model_id": embedder.model_id},
    )

    text = "Binary search trees support logarithmic lookup."
    collection.upsert(
        ids=["chunk-1"],
        documents=[text],
        embeddings=[embedder.encode(text).tolist()],
        metadatas=[
            {
                "year": 2025,
                "paper": 1,
                "question_number": 1,
                "topic": "Algorithms",
                "chunk_level": "question",
                "has_code": False,
                "has_figure": False,
                "has_table": False,
                "source_pdf": "y2025p1q1.pdf",
                "total_marks": 20,
            }
        ],
    )

    sidecar = chroma_dir / f"{collection_name}_media_map.json"
    sidecar.write_text(
        json.dumps(
            {
                "chunk-1": [
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
    return collection_name


def _build_fake_response() -> SearchResponse:
    return SearchResponse(
        query="binary search trees",
        collection="tool-test-collection",
        total=1,
        results=[
            SearchResult(
                chunk_id="chunk-1",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="Binary search trees support logarithmic lookup.",
                score=0.8123,
                metadata={
                    "year": 2025,
                    "paper": 1,
                    "question_number": 1,
                    "topic": "Algorithms",
                    "author": None,
                    "tripos_part": None,
                    "chunk_level": "question",
                    "parent_chunk_id": None,
                    "sub_question_label": None,
                    "marks": None,
                    "total_marks": 20,
                    "has_code": False,
                    "has_figure": False,
                    "has_table": False,
                    "source_pdf": "y2025p1q1.pdf",
                },
                media=[],
            )
        ],
    )


def test_build_search_payload_passes_filters_to_service() -> None:
    """Infrastructure test for search CLI plumbing only."""
    fake_service = ToolTestFakeSearchService(_build_fake_response())

    payload = build_search_payload(
        service=fake_service,  # type: ignore[arg-type]
        query="binary search trees",
        collection="tool-test-collection",
        filters={
            "year": 2025,
            "paper": 1,
            "topic": "Algorithms",
            "has_code": True,
        },
        limit=3,
        rerank=False,
        show_media=False,
        max_text_chars=32,
    )

    assert fake_service.calls == [
        {
            "query": "binary search trees",
            "collection": "tool-test-collection",
            "filters": {
                "year": 2025,
                "paper": 1,
                "topic": "Algorithms",
                "has_code": True,
            },
            "limit": 3,
            "rerank": False,
        }
    ]
    assert payload["filters"]["topic"] == "Algorithms"
    assert payload["providers"] == {
        "embedding_model_id": None,
        "rerank_model_id": None,
    }
    assert payload["rerank"] is False


def test_build_search_payload_queries_temporary_chroma(
    tmp_path: Path,
) -> None:
    """Infrastructure test for temporary Chroma search behavior only."""
    embedder = ToolTestFakeEmbedder()
    collection_name = _seed_chroma(tmp_path, embedder)
    service = SearchService(
        chroma_dir=str(tmp_path),
        embedding_model=embedder,
        reranker=None,
    )

    payload = build_search_payload(
        service=service,
        query="binary search trees",
        collection=collection_name,
        filters={},
        limit=5,
        rerank=False,
        show_media=True,
        max_text_chars=80,
    )

    assert payload["query"] == "binary search trees"
    assert payload["collection"] == collection_name
    assert payload["providers"] == {
        "embedding_model_id": "tool-test-embedding",
        "rerank_model_id": None,
    }
    assert payload["total"] == 1
    assert payload["results"][0]["chunk_id"] == "chunk-1"
    assert payload["results"][0]["text"] == (
        "Binary search trees support logarithmic lookup."
    )
    assert payload["results"][0]["text_preview"] == (
        "Binary search trees support logarithmic lookup."
    )
    assert payload["results"][0]["media"][0]["media_id"] == "fig-1"


def test_render_text_includes_query_collection_score_chunk_id_metadata_preview() -> (
    None
):
    """Infrastructure test for readable CLI output only."""
    payload = {
        "query": "binary search trees",
        "collection": "tool-test-collection",
        "filters": {"year": 2025, "paper": 1},
        "limit": 3,
        "rerank": False,
        "show_media": True,
        "total": 1,
        "results": [
            {
                "chunk_id": "chunk-1",
                "chunk_level": "question",
                "parent_chunk_id": None,
                "sub_question_label": None,
                "score": 0.8123,
                "metadata": {
                    "year": 2025,
                    "paper": 1,
                    "question_number": 1,
                    "topic": "Algorithms",
                    "author": None,
                    "tripos_part": None,
                    "chunk_level": "question",
                    "parent_chunk_id": None,
                    "sub_question_label": None,
                    "marks": None,
                    "total_marks": 20,
                    "has_code": False,
                    "has_figure": False,
                    "has_table": False,
                    "source_pdf": "y2025p1q1.pdf",
                },
                "text": "Binary search trees support logarithmic lookup.",
                "text_preview": "Binary search trees support logarithmic lookup.",
                "media": [
                    {
                        "media_id": "fig-1",
                        "kind": "image",
                        "file_path": "/media/fig-1.png",
                        "relation": "direct",
                    }
                ],
            }
        ],
    }

    output = render_text(payload)

    assert "Query: binary search trees" in output
    assert "Collection: tool-test-collection" in output
    assert "chunk-1" in output
    assert "score: 0.8123" in output
    assert "topic=Algorithms" in output
    assert "preview: Binary search trees support logarithmic lookup." in output
    assert "media_id=fig-1" in output


def test_render_json_is_parseable() -> None:
    """Infrastructure test for machine-readable CLI output only."""
    payload = {
        "query": "binary search trees",
        "collection": "tool-test-collection",
        "filters": {},
        "limit": 3,
        "rerank": False,
        "show_media": False,
        "total": 1,
        "results": [
            {
                "chunk_id": "chunk-1",
                "chunk_level": "question",
                "parent_chunk_id": None,
                "sub_question_label": None,
                "score": 0.8123,
                "metadata": {
                    "year": 2025,
                    "paper": 1,
                    "question_number": 1,
                    "topic": "Algorithms",
                    "author": None,
                    "tripos_part": None,
                    "chunk_level": "question",
                    "parent_chunk_id": None,
                    "sub_question_label": None,
                    "marks": None,
                    "total_marks": 20,
                    "has_code": False,
                    "has_figure": False,
                    "has_table": False,
                    "source_pdf": "y2025p1q1.pdf",
                },
                "text": "Binary search trees support logarithmic lookup.",
                "text_preview": "Binary search trees support logarithmic lookup.",
                "media": [
                    {
                        "media_id": "fig-1",
                        "kind": "image",
                        "file_path": "/media/fig-1.png",
                        "relation": "direct",
                    }
                ],
            }
        ],
    }

    parsed = json.loads(render_json(payload))

    assert parsed["collection"] == "tool-test-collection"
    assert parsed["results"][0]["chunk_id"] == "chunk-1"
    assert parsed["results"][0]["text"] == (
        "Binary search trees support logarithmic lookup."
    )
    assert parsed["results"][0]["text_preview"] == (
        "Binary search trees support logarithmic lookup."
    )
    assert parsed["results"][0]["media"][0]["media_id"] == "fig-1"


def test_render_text_hides_media_when_not_requested() -> None:
    """Infrastructure test for readable CLI output only."""
    payload = {
        "query": "binary search trees",
        "collection": "tool-test-collection",
        "filters": {},
        "limit": 3,
        "rerank": False,
        "show_media": False,
        "total": 1,
        "results": [
            {
                "chunk_id": "chunk-1",
                "chunk_level": "question",
                "parent_chunk_id": None,
                "sub_question_label": None,
                "score": 0.8123,
                "metadata": {
                    "year": 2025,
                    "paper": 1,
                    "question_number": 1,
                    "topic": "Algorithms",
                    "author": None,
                    "tripos_part": None,
                    "chunk_level": "question",
                    "parent_chunk_id": None,
                    "sub_question_label": None,
                    "marks": None,
                    "total_marks": 20,
                    "has_code": False,
                    "has_figure": False,
                    "has_table": False,
                    "source_pdf": "y2025p1q1.pdf",
                },
                "text": "Binary search trees support logarithmic lookup.",
                "text_preview": "Binary search trees support logarithmic lookup.",
                "media": [
                    {
                        "media_id": "fig-1",
                        "kind": "image",
                        "file_path": "/media/fig-1.png",
                        "relation": "direct",
                    }
                ],
            }
        ],
    }

    output = render_text(payload)

    assert "   media:" not in output
    assert "media_id=fig-1" not in output


def test_render_text_uses_canonical_metadata_key_order() -> None:
    """The CLI should reuse the search-layer metadata key contract directly."""
    assert inspect_search.METADATA_KEYS is METADATA_KEYS

    metadata_output = render_text(
        {
            "query": "binary search trees",
            "collection": "tool-test-collection",
            "filters": {},
            "limit": 3,
            "rerank": False,
            "show_media": False,
            "total": 1,
            "results": [
                {
                    "chunk_id": "chunk-1",
                    "chunk_level": "question",
                    "parent_chunk_id": None,
                    "sub_question_label": None,
                    "score": 0.8123,
                    "metadata": {
                        key: f"value-{index}" for index, key in enumerate(METADATA_KEYS)
                    },
                    "text": "Binary search trees support logarithmic lookup.",
                    "text_preview": "Binary search trees support logarithmic lookup.",
                    "media": [],
                }
            ],
        }
    )

    assert METADATA_KEYS[0] == "year"
    assert (
        "metadata: "
        + " ".join(f"{key}=value-{index}" for index, key in enumerate(METADATA_KEYS))
        in metadata_output
    )


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--limit", "-1"),
        ("--max-text-chars", "0"),
    ],
)
def test_parse_args_rejects_non_positive_integers(
    monkeypatch,
    capsys,
    flag: str,
    value: str,
) -> None:
    """Infrastructure test for CLI argument validation only."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_search.py",
            "binary search trees",
            "--collection",
            "tool-test-collection",
            flag,
            value,
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        parse_args()

    assert excinfo.value.code == 2
    assert "positive integer" in capsys.readouterr().err


def test_parse_args_supports_no_rerank(
    monkeypatch,
) -> None:
    """Infrastructure test for CLI option parsing only."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_search.py",
            "binary search trees",
            "--collection",
            "tool-test-collection",
            "--no-rerank",
        ],
    )

    args = parse_args()

    assert args.rerank is False


def test_main_reports_missing_collection_without_traceback(
    monkeypatch,
    capsys,
) -> None:
    """Infrastructure test for CLI error handling only."""
    monkeypatch.setattr(
        "scripts.inspect_search.create_real_search_service",
        lambda chroma_dir, rerank: ToolTestMissingCollectionService(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_search.py",
            "binary search trees",
            "--collection",
            "missing",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "Collection 'missing' not found." in err
    assert "inspect_chroma.py --list-collections" in err
