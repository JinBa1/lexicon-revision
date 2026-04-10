"""Unit tests for SearchService retrieve-and-rerank logic.

These tests seed an isolated temporary ChromaDB collection with known chunks
and verify filtering, ranking, media joining, and rerank toggling. They
validate indexing and search contracts, not retrieval quality.

Tests use a FakeEmbedder (deterministic hash-based vectors) and a
FakeReranker. No real sentence-transformer model is loaded.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from src.search.service import CollectionNotFoundError, SearchService

EMBED_DIM = 8


class FakeEmbedder:
    """Deterministic embedder that hashes text into a unit vector."""

    def encode(self, text: str | list[str]) -> np.ndarray:
        if isinstance(text, str):
            return self._hash_to_vector(text)
        return np.array([self._hash_to_vector(t) for t in text])

    def _hash_to_vector(self, text: str) -> np.ndarray:
        digest = hashlib.sha256(text.encode()).digest()
        vec = np.frombuffer(digest[:EMBED_DIM], dtype=np.uint8).astype(np.float32) + 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec


class FakeReranker:
    """Deterministic reranker that scores candidate docs from a fixed map."""

    def __init__(self, score_map: dict[str, float]) -> None:
        self.score_map = score_map

    def predict(self, pairs: list[tuple[str, str]]) -> np.ndarray:
        return np.array([self.score_map[doc] for _, doc in pairs], dtype=np.float32)


@pytest.fixture(scope="module")
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture()
def service_with_chunks(tmp_path: Path, fake_embedder: FakeEmbedder):
    """Seed a temporary ChromaDB collection with known chunks and media."""
    import chromadb

    chroma_dir = str(tmp_path / "chroma")
    collection_name = "test-collection"

    client = chromadb.PersistentClient(path=chroma_dir)
    col = client.get_or_create_collection(
        collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    chunks_data = [
        {
            "id": "cam-2023-p2-q5",
            "text": "Binary search trees support O(log n) lookup.",
            "metadata": {
                "year": 2023,
                "paper": 2,
                "question_number": 5,
                "topic": "Algorithms",
                "chunk_level": "question",
                "has_code": False,
                "has_figure": False,
                "has_table": False,
                "source_pdf": "y2023p2q5.pdf",
                "total_marks": 20,
            },
        },
        {
            "id": "cam-2023-p2-q5-a",
            "text": "Explain the difference between AVL and red-black trees.",
            "metadata": {
                "year": 2023,
                "paper": 2,
                "question_number": 5,
                "topic": "Algorithms",
                "chunk_level": "sub_question",
                "parent_chunk_id": "cam-2023-p2-q5",
                "sub_question_label": "a",
                "marks": 8,
                "has_code": False,
                "has_figure": False,
                "has_table": False,
                "source_pdf": "y2023p2q5.pdf",
                "total_marks": 20,
            },
        },
        {
            "id": "cam-2024-p1-q3",
            "text": "Relational databases use SQL for querying structured data.",
            "metadata": {
                "year": 2024,
                "paper": 1,
                "question_number": 3,
                "topic": "Databases",
                "chunk_level": "question",
                "has_code": True,
                "has_figure": False,
                "has_table": True,
                "source_pdf": "y2024p1q3.pdf",
                "total_marks": 15,
            },
        },
    ]

    col.upsert(
        ids=[chunk["id"] for chunk in chunks_data],
        documents=[chunk["text"] for chunk in chunks_data],
        embeddings=fake_embedder.encode(
            [chunk["text"] for chunk in chunks_data]
        ).tolist(),
        metadatas=[chunk["metadata"] for chunk in chunks_data],
    )

    media_map = {
        "cam-2023-p2-q5": [
            {
                "media_id": "cam-2023-p2-q5-figure_1",
                "kind": "image",
                "file_path": "/media/figure_1.png",
                "relation": "direct",
            }
        ],
        "cam-2023-p2-q5-a": [],
        "cam-2024-p1-q3": [],
    }
    sidecar_path = Path(chroma_dir) / f"{collection_name}_media_map.json"
    sidecar_path.write_text(json.dumps(media_map), encoding="utf-8")

    service = SearchService(
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
        reranker=None,
    )
    return service, collection_name


def test_search_returns_results(service_with_chunks) -> None:
    """Basic semantic search returns matching chunks."""
    service, collection = service_with_chunks

    response = service.search(
        query="binary search trees",
        collection=collection,
        limit=10,
    )

    assert len(response.results) > 0
    assert response.query == "binary search trees"
    assert response.collection == collection


def test_search_returns_raw_text_not_embedding_input(service_with_chunks) -> None:
    """Returned text is raw chunk text, not footer-appended embedding input."""
    service, collection = service_with_chunks

    response = service.search(
        query="binary search trees",
        collection=collection,
        limit=10,
    )

    for result in response.results:
        assert "Year:" not in result.text
        assert "Paper:" not in result.text
        assert "Topic:" not in result.text


def test_search_metadata_has_stable_keys(service_with_chunks) -> None:
    """Response metadata contains all spec-defined keys, including missing Nones."""
    service, collection = service_with_chunks

    response = service.search(
        query="binary search trees",
        collection=collection,
        limit=10,
    )

    expected_keys = {
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
    }
    for result in response.results:
        assert set(result.metadata.keys()) == expected_keys


def test_search_metadata_filter_by_year(service_with_chunks) -> None:
    """Year filter narrows results to matching year only."""
    service, collection = service_with_chunks

    response = service.search(
        query="data structures",
        collection=collection,
        filters={"year": 2024},
        limit=10,
    )

    for result in response.results:
        assert result.metadata["year"] == 2024


def test_search_metadata_filter_by_topic(service_with_chunks) -> None:
    """Topic filter narrows results to matching topic only."""
    service, collection = service_with_chunks

    response = service.search(
        query="querying data",
        collection=collection,
        filters={"topic": "Databases"},
        limit=10,
    )

    assert len(response.results) > 0
    for result in response.results:
        assert result.metadata["topic"] == "Databases"


def test_search_metadata_filter_has_code(service_with_chunks) -> None:
    """Boolean filter narrows results correctly."""
    service, collection = service_with_chunks

    response = service.search(
        query="programming",
        collection=collection,
        filters={"has_code": True},
        limit=10,
    )

    for result in response.results:
        assert result.metadata["has_code"] is True


def test_search_metadata_filter_marks_min(service_with_chunks) -> None:
    """marks_min maps to a Chroma gte filter on part marks."""
    service, collection = service_with_chunks

    response = service.search(
        query="AVL trees",
        collection=collection,
        filters={"marks_min": 8},
        limit=10,
    )

    assert [result.chunk_id for result in response.results] == ["cam-2023-p2-q5-a"]


def test_search_metadata_filters_combine_with_and(service_with_chunks) -> None:
    """Multiple filters narrow results with AND semantics."""
    service, collection = service_with_chunks

    response = service.search(
        query="structured data",
        collection=collection,
        filters={"year": 2024, "topic": "Databases", "has_table": True},
        limit=10,
    )

    assert [result.chunk_id for result in response.results] == ["cam-2024-p1-q3"]


def test_search_joins_media_from_sidecar(service_with_chunks) -> None:
    """Results include media refs from the sidecar file."""
    service, collection = service_with_chunks

    response = service.search(
        query="binary search trees",
        collection=collection,
        limit=10,
    )

    q5 = next(
        (result for result in response.results if result.chunk_id == "cam-2023-p2-q5"),
        None,
    )
    assert q5 is not None
    assert len(q5.media) == 1
    assert q5.media[0].media_id == "cam-2023-p2-q5-figure_1"


def test_search_nonexistent_collection(service_with_chunks) -> None:
    """Searching a nonexistent collection raises CollectionNotFoundError."""
    service, _ = service_with_chunks

    with pytest.raises(CollectionNotFoundError) as exc_info:
        service.search(
            query="anything",
            collection="nonexistent-collection",
            limit=10,
        )

    assert exc_info.value.collection_name == "nonexistent-collection"


def test_search_missing_sidecar_returns_empty_media(
    tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    """Missing media sidecar results in empty media arrays, not errors."""
    import chromadb

    chroma_dir = str(tmp_path / "chroma_no_sidecar")
    collection_name = "no-sidecar"

    client = chromadb.PersistentClient(path=chroma_dir)
    col = client.get_or_create_collection(
        collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    doc = "A test document about algorithms."
    col.upsert(
        ids=["test-1"],
        documents=[doc],
        embeddings=[fake_embedder.encode(doc).tolist()],
        metadatas=[
            {
                "chunk_level": "question",
                "has_code": False,
                "has_figure": False,
                "has_table": False,
                "source_pdf": "test.pdf",
            }
        ],
    )

    service = SearchService(
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
        reranker=None,
    )
    response = service.search(
        query="algorithms",
        collection=collection_name,
        limit=10,
    )

    assert response is not None
    assert len(response.results) > 0
    for result in response.results:
        assert result.media == []


def test_search_invalid_sidecar_shape_returns_empty_media(
    tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    """Malformed but parseable sidecars are rejected and treated as empty."""
    import chromadb

    chroma_dir = str(tmp_path / "chroma_invalid_sidecar")
    collection_name = "invalid-sidecar"

    client = chromadb.PersistentClient(path=chroma_dir)
    col = client.get_or_create_collection(
        collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    doc = "A test document about algorithms."
    col.upsert(
        ids=["test-1"],
        documents=[doc],
        embeddings=[fake_embedder.encode(doc).tolist()],
        metadatas=[
            {
                "chunk_level": "question",
                "has_code": False,
                "has_figure": False,
                "has_table": False,
                "source_pdf": "test.pdf",
            }
        ],
    )

    sidecar_path = Path(chroma_dir) / f"{collection_name}_media_map.json"
    sidecar_path.write_text(json.dumps({"test-1": ["bad-ref"]}), encoding="utf-8")

    service = SearchService(
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
        reranker=None,
    )
    response = service.search(
        query="algorithms",
        collection=collection_name,
        limit=10,
    )

    assert len(response.results) == 1
    assert response.results[0].media == []


def test_search_limit_caps_results(service_with_chunks) -> None:
    """Limit parameter caps the number of returned results."""
    service, collection = service_with_chunks

    response = service.search(
        query="data structures and databases",
        collection=collection,
        limit=1,
    )

    assert len(response.results) == 1


def test_search_rejects_non_positive_limit(service_with_chunks) -> None:
    """The service rejects invalid limit values before reaching ChromaDB."""
    service, collection = service_with_chunks

    with pytest.raises(ValueError, match="limit must be positive"):
        service.search(
            query="binary search trees",
            collection=collection,
            limit=0,
        )


def test_search_rejects_limit_above_rerank_cap(service_with_chunks) -> None:
    """The rerank candidate cap applies only when reranking is enabled."""
    service, collection = service_with_chunks

    with pytest.raises(ValueError, match="limit cannot exceed rerank candidate cap"):
        service.search(
            query="binary search trees",
            collection=collection,
            limit=51,
            rerank=True,
        )


def test_search_allows_limit_above_rerank_cap_when_rerank_disabled(
    tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    """Direct retrieval can request more than 50 results when reranking is off."""
    import chromadb

    chroma_dir = str(tmp_path / "chroma_many_no_rerank")
    collection_name = "many-results-no-rerank"
    client = chromadb.PersistentClient(path=chroma_dir)
    col = client.get_or_create_collection(
        collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    count = 55
    documents = [f"Algorithms document {idx}" for idx in range(count)]
    col.upsert(
        ids=[f"doc-{idx}" for idx in range(count)],
        documents=documents,
        embeddings=fake_embedder.encode(documents).tolist(),
        metadatas=[
            {
                "chunk_level": "question",
                "has_code": False,
                "has_figure": False,
                "has_table": False,
                "source_pdf": f"doc-{idx}.pdf",
            }
            for idx in range(count)
        ],
    )

    service = SearchService(
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
        reranker=None,
    )
    response = service.search(
        query="Algorithms",
        collection=collection_name,
        limit=count,
        rerank=False,
    )

    assert len(response.results) == count
    assert len({result.chunk_id for result in response.results}) == count
    assert response.total == count


class FixedQueryEmbedder:
    """Embedder with a fixed query vector for deterministic ranking tests."""

    def encode(self, text: str | list[str]) -> np.ndarray:
        query_vector = np.array([1.0, 0.0], dtype=np.float32)
        if isinstance(text, str):
            return query_vector
        return np.array([query_vector for _ in text], dtype=np.float32)


def test_search_rerank_toggle_uses_vector_order_when_disabled(tmp_path: Path) -> None:
    """Disabling rerank preserves deterministic vector-search order."""
    import chromadb

    chroma_dir = str(tmp_path / "chroma_rerank_toggle")
    collection_name = "rerank-toggle"
    client = chromadb.PersistentClient(path=chroma_dir)
    col = client.get_or_create_collection(
        collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    first_doc = "Graphs and trees are central data structures."
    second_doc = "SQL queries operate on relational tables."
    col.upsert(
        ids=["doc-1", "doc-2"],
        documents=[first_doc, second_doc],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadatas=[
            {
                "chunk_level": "question",
                "has_code": False,
                "has_figure": False,
                "has_table": False,
                "source_pdf": "doc-1.pdf",
            },
            {
                "chunk_level": "question",
                "has_code": False,
                "has_figure": False,
                "has_table": False,
                "source_pdf": "doc-2.pdf",
            },
        ],
    )

    service = SearchService(
        chroma_dir=chroma_dir,
        embedding_model=FixedQueryEmbedder(),
        reranker=FakeReranker({first_doc: -1.0, second_doc: 1.0}),
    )

    without_rerank = service.search(
        query="data structures",
        collection=collection_name,
        limit=2,
        rerank=False,
    )
    with_rerank = service.search(
        query="data structures",
        collection=collection_name,
        limit=2,
        rerank=True,
    )

    assert [result.chunk_id for result in without_rerank.results] == ["doc-1", "doc-2"]
    assert [result.chunk_id for result in with_rerank.results] == ["doc-2", "doc-1"]


def test_search_reranker_changes_ranking_order(
    tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    """Reranking can change the returned order of candidates."""
    import chromadb

    chroma_dir = str(tmp_path / "chroma_rerank")
    collection_name = "rerank-collection"
    client = chromadb.PersistentClient(path=chroma_dir)
    col = client.get_or_create_collection(
        collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    first_doc = "Binary search trees support logarithmic search."
    second_doc = "AVL trees rebalance more aggressively than red-black trees."
    col.upsert(
        ids=["doc-1", "doc-2"],
        documents=[first_doc, second_doc],
        embeddings=fake_embedder.encode([first_doc, second_doc]).tolist(),
        metadatas=[
            {
                "chunk_level": "question",
                "has_code": False,
                "has_figure": False,
                "has_table": False,
                "source_pdf": "doc-1.pdf",
            },
            {
                "chunk_level": "question",
                "has_code": False,
                "has_figure": False,
                "has_table": False,
                "source_pdf": "doc-2.pdf",
            },
        ],
    )

    no_rerank_service = SearchService(
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
        reranker=None,
    )
    baseline = no_rerank_service.search(
        query="tree balancing and search",
        collection=collection_name,
        limit=2,
        rerank=False,
    )

    target_top_doc = baseline.results[-1].text
    reranker = FakeReranker(
        {
            first_doc: 0.1 if first_doc != target_top_doc else 0.9,
            second_doc: 0.1 if second_doc != target_top_doc else 0.9,
        }
    )
    reranked_service = SearchService(
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
        reranker=reranker,
    )
    reranked = reranked_service.search(
        query="tree balancing and search",
        collection=collection_name,
        limit=2,
        rerank=True,
    )

    assert [result.chunk_id for result in baseline.results] != [
        result.chunk_id for result in reranked.results
    ]
    assert reranked.results[0].text == target_top_doc
    assert reranked.results[0].score > reranked.results[1].score


def test_search_surfaces_sub_question_fields(service_with_chunks) -> None:
    """Sub-question results expose linkage and label fields."""
    service, collection = service_with_chunks

    response = service.search(
        query="AVL trees red-black trees differences",
        collection=collection,
        limit=10,
    )

    sub_results = [
        result for result in response.results if result.chunk_level == "sub_question"
    ]
    assert sub_results
    sub = sub_results[0]
    assert sub.parent_chunk_id == "cam-2023-p2-q5"
    assert sub.sub_question_label == "a"
