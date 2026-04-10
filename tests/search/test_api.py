"""Integration tests for the GET /search endpoint.

These tests exercise the FastAPI app in-process via ``httpx.ASGITransport``
with a temporary ChromaDB collection seeded with known data. They verify
response shape, filter behavior, and error handling.

Tests use a FakeEmbedder — no real model downloads needed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import chromadb
import httpx
import numpy as np
import pytest
from src.search.service import SearchService

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


@pytest.fixture(scope="module")
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture(scope="module")
def seeded_chroma(tmp_path_factory, fake_embedder: FakeEmbedder):
    """Create and seed a temporary ChromaDB for the test module."""
    tmp_dir = tmp_path_factory.mktemp("chroma_api")
    chroma_dir = str(tmp_dir)
    collection_name = "test-api"

    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_or_create_collection(
        collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    chunks = [
        {
            "id": "cam-2023-p2-q5",
            "text": "Binary search trees support efficient lookup and insertion.",
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
            "id": "cam-2024-p1-q3",
            "text": "SQL databases use relational algebra for query optimization.",
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

    collection.upsert(
        ids=[chunk["id"] for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        embeddings=fake_embedder.encode([chunk["text"] for chunk in chunks]).tolist(),
        metadatas=[chunk["metadata"] for chunk in chunks],
    )

    media_map = {
        "cam-2023-p2-q5": [
            {
                "media_id": "fig1",
                "kind": "image",
                "file_path": "/media/fig1.png",
                "relation": "direct",
            }
        ]
    }
    sidecar_path = Path(chroma_dir) / f"{collection_name}_media_map.json"
    sidecar_path.write_text(json.dumps(media_map), encoding="utf-8")

    return chroma_dir, collection_name


@pytest.fixture(scope="module")
def app(seeded_chroma, fake_embedder: FakeEmbedder):
    """Create an app with SearchService injected via app.state."""
    chroma_dir, _ = seeded_chroma

    service = SearchService(
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
        reranker=None,
    )

    from src.main import create_app

    return create_app(search_service=service)


@pytest.mark.anyio
async def test_search_returns_200_with_results(app, seeded_chroma) -> None:
    _, collection = seeded_chroma

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={"q": "binary search trees", "collection": collection},
        )

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "query" in data
    assert "collection" in data
    assert "total" in data
    assert len(data["results"]) > 0


@pytest.mark.anyio
async def test_search_result_shape(app, seeded_chroma) -> None:
    _, collection = seeded_chroma

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={"q": "algorithms", "collection": collection},
        )

    results = response.json()["results"]
    assert results
    result = results[0]
    assert "chunk_id" in result
    assert "chunk_level" in result
    assert "parent_chunk_id" in result
    assert "sub_question_label" in result
    assert "text" in result
    assert "score" in result
    assert "metadata" in result
    assert "media" in result


@pytest.mark.anyio
async def test_search_result_text_has_no_footer(app, seeded_chroma) -> None:
    """Returned text is raw chunk text, not footer-appended embedding input."""
    _, collection = seeded_chroma

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={"q": "algorithms", "collection": collection},
        )

    for result in response.json()["results"]:
        assert "Year:" not in result["text"]
        assert "| Topic:" not in result["text"]


@pytest.mark.anyio
async def test_search_result_metadata_has_stable_keys(app, seeded_chroma) -> None:
    """Response metadata contains all spec-defined keys."""
    _, collection = seeded_chroma

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={"q": "algorithms", "collection": collection},
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

    for result in response.json()["results"]:
        assert set(result["metadata"].keys()) == expected_keys


@pytest.mark.anyio
async def test_search_filter_by_year(app, seeded_chroma) -> None:
    _, collection = seeded_chroma

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={"q": "data", "collection": collection, "year": 2024},
        )

    for result in response.json()["results"]:
        assert result["metadata"].get("year") == 2024


@pytest.mark.anyio
async def test_search_nonexistent_collection_returns_404(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={"q": "anything", "collection": "nonexistent"},
        )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_search_includes_media(app, seeded_chroma) -> None:
    _, collection = seeded_chroma

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={"q": "binary search trees", "collection": collection},
        )

    q5 = next(
        (
            result
            for result in response.json()["results"]
            if result["chunk_id"] == "cam-2023-p2-q5"
        ),
        None,
    )

    assert q5 is not None
    assert len(q5["media"]) == 1
    assert q5["media"][0]["media_id"] == "fig1"


@pytest.mark.anyio
async def test_search_requires_query_param(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/search")

    assert response.status_code == 422


@pytest.mark.anyio
async def test_search_rejects_limit_above_rerank_cap(app, seeded_chroma) -> None:
    """HTTP layer translates rerank cap violations into a client error."""
    _, collection = seeded_chroma

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/search",
            params={"q": "algorithms", "collection": collection, "limit": 51},
        )

    assert response.status_code == 422
