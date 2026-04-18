"""Contract tests for the indexing script.

These tests verify that chunks are indexed, metadata is stored, the media
sidecar is written, and re-running is idempotent. They do NOT test
embedding quality or retrieval relevance.

Tests inject a FakeEmbedder for speed and CI portability. Real embedding-model
coverage belongs in explicit smoke or integration tests.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import chromadb
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MINERU_FIXTURES = str(REPO_ROOT / "tests" / "data" / "mineru_fixtures")

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.index_chunks import index_collection  # noqa: E402
from src.search.providers.base import EmbeddingResult  # noqa: E402

EMBED_DIM = 8


class _FakeEmbedder:
    model_id = "fake-embed-v1"

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[[0.0] * EMBED_DIM for _ in texts], model_id=self.model_id
        )

    def embed_query(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(vectors=[[0.0] * EMBED_DIM], model_id=self.model_id)


class _ClosableFakeEmbedder(_FakeEmbedder):
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeEmbedder:
    """Deterministic embedder that hashes text into a unit vector."""

    def encode(
        self, text: str | list[str], show_progress_bar: bool = False
    ) -> np.ndarray:
        del show_progress_bar
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


@pytest.fixture(scope="module")
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


def test_index_creates_collection_and_sidecar(
    tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    """Indexing fixtures creates a ChromaDB collection and media sidecar."""
    chroma_dir = str(tmp_path / "chroma")
    collection_name = "test-index"

    index_collection(
        mineru_output_dir=MINERU_FIXTURES,
        collection_name=collection_name,
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
    )

    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_collection(collection_name)
    assert collection.count() > 0

    sidecar_path = Path(chroma_dir) / f"{collection_name}_media_map.json"
    assert sidecar_path.exists()
    media_map = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert isinstance(media_map, dict)
    assert len(media_map) > 0


def test_index_stores_raw_text_not_embedding_input(
    tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    """ChromaDB documents contain raw text, not footer-appended embedding input."""
    chroma_dir = str(tmp_path / "chroma")
    collection_name = "test-text"

    index_collection(
        mineru_output_dir=MINERU_FIXTURES,
        collection_name=collection_name,
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
    )

    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_collection(collection_name)

    result = collection.get(ids=["cam-2025-p1-q1"], include=["documents"])
    assert len(result["ids"]) == 1

    document = result["documents"][0]
    assert "Year:" not in document
    assert "Paper:" not in document
    assert "| Topic:" not in document


def test_index_stores_metadata_correctly(
    tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    """Indexed chunks carry the expected metadata fields."""
    chroma_dir = str(tmp_path / "chroma")
    collection_name = "test-meta"

    index_collection(
        mineru_output_dir=MINERU_FIXTURES,
        collection_name=collection_name,
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
    )

    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_collection(collection_name)

    result = collection.get(ids=["cam-2025-p1-q1"], include=["metadatas"])
    assert len(result["ids"]) == 1

    metadata = result["metadatas"][0]
    assert metadata["year"] == 2025
    assert metadata["paper"] == 1
    assert metadata["question_number"] == 1
    assert metadata["chunk_level"] == "question"
    assert "source_pdf" in metadata


def test_index_chunk_ids_match_pipeline_output(
    tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    """Every chunk ID from the pipeline is present in the ChromaDB collection."""
    from src.chunking.pipeline import run_pipeline

    chroma_dir = str(tmp_path / "chroma")
    collection_name = "test-ids"

    chunks = run_pipeline(mineru_output_dir=MINERU_FIXTURES, university="cam")
    expected_ids = {chunk.id for chunk in chunks}

    index_collection(
        mineru_output_dir=MINERU_FIXTURES,
        collection_name=collection_name,
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
    )

    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_collection(collection_name)

    stored = collection.get(include=[])
    stored_ids = set(stored["ids"])
    assert stored_ids == expected_ids


def test_index_is_idempotent(tmp_path: Path, fake_embedder: FakeEmbedder) -> None:
    """Re-running indexing on the same input produces the same count and IDs."""
    chroma_dir = str(tmp_path / "chroma")
    collection_name = "test-idempotent"

    index_collection(
        mineru_output_dir=MINERU_FIXTURES,
        collection_name=collection_name,
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
    )

    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_collection(collection_name)
    count_first = collection.count()
    ids_first = set(collection.get(include=[])["ids"])

    index_collection(
        mineru_output_dir=MINERU_FIXTURES,
        collection_name=collection_name,
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
    )

    client_second = chromadb.PersistentClient(path=chroma_dir)
    collection_second = client_second.get_collection(collection_name)
    count_second = collection_second.count()
    ids_second = set(collection_second.get(include=[])["ids"])

    assert count_second == count_first
    assert ids_second == ids_first


def test_index_media_sidecar_has_correct_keys(
    tmp_path: Path, fake_embedder: FakeEmbedder
) -> None:
    """Media sidecar preserves representative media payload fields."""
    from src.chunking.pipeline import run_pipeline

    chroma_dir = str(tmp_path / "chroma")
    collection_name = "test-sidecar-keys"

    chunks = run_pipeline(mineru_output_dir=MINERU_FIXTURES, university="cam")
    chunks_with_media = {chunk.id for chunk in chunks if chunk.media}

    index_collection(
        mineru_output_dir=MINERU_FIXTURES,
        collection_name=collection_name,
        chroma_dir=chroma_dir,
        embedding_model=fake_embedder,
    )

    sidecar_path = Path(chroma_dir) / f"{collection_name}_media_map.json"
    media_map = json.loads(sidecar_path.read_text(encoding="utf-8"))

    for chunk_id in chunks_with_media:
        assert chunk_id in media_map, f"Missing sidecar entry for {chunk_id}"
        assert len(media_map[chunk_id]) > 0

    sample_chunk_id = next(iter(chunks_with_media))
    sample_ref = media_map[sample_chunk_id][0]
    assert sample_ref["relation"] in {
        "direct",
        "inherited_shared",
        "visible_from_child",
    }
    assert sample_ref["owner_level"] in {"question", "sub_question"}
    assert (
        isinstance(sample_ref["page_number"], int) or sample_ref["page_number"] is None
    )
    if sample_ref["bbox"] is not None:
        assert isinstance(sample_ref["bbox"], list)
        assert len(sample_ref["bbox"]) == 4


def test_new_collection_stamps_embedding_model_id(tmp_path: Path) -> None:
    index_collection(
        mineru_output_dir=MINERU_FIXTURES,
        chroma_dir=str(tmp_path / "chroma"),
        collection_name="test-coll",
        embedding_model=_FakeEmbedder(),
    )
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    collection = client.get_collection("test-coll")
    assert collection.metadata.get("embedding_model_id") == "fake-embed-v1"


def test_legacy_collection_without_metadata_is_upgraded(tmp_path: Path) -> None:
    chroma_dir = str(tmp_path / "chroma")
    client = chromadb.PersistentClient(path=chroma_dir)
    client.create_collection(name="test-coll", metadata={"hnsw:space": "cosine"})
    index_collection(
        mineru_output_dir=MINERU_FIXTURES,
        chroma_dir=chroma_dir,
        collection_name="test-coll",
        embedding_model=_FakeEmbedder(),
    )
    collection = client.get_collection("test-coll")
    assert collection.metadata.get("embedding_model_id") == "fake-embed-v1"


def test_mismatched_existing_model_raises_without_flag(tmp_path: Path) -> None:
    chroma_dir = str(tmp_path / "chroma")
    client = chromadb.PersistentClient(path=chroma_dir)
    client.create_collection(
        name="test-coll", metadata={"embedding_model_id": "other-model"}
    )
    with pytest.raises(ValueError, match="embedding_model_id"):
        index_collection(
            mineru_output_dir=MINERU_FIXTURES,
            chroma_dir=chroma_dir,
            collection_name="test-coll",
            embedding_model=_FakeEmbedder(),
            recreate_collection=False,
        )


def test_recreate_flag_overwrites_collection_with_new_model_id(tmp_path: Path) -> None:
    chroma_dir = str(tmp_path / "chroma")
    client = chromadb.PersistentClient(path=chroma_dir)
    client.create_collection(
        name="test-coll", metadata={"embedding_model_id": "other-model"}
    )
    index_collection(
        mineru_output_dir=MINERU_FIXTURES,
        chroma_dir=chroma_dir,
        collection_name="test-coll",
        embedding_model=_FakeEmbedder(),
        recreate_collection=True,
    )
    collection = client.get_collection("test-coll")
    assert collection.metadata.get("embedding_model_id") == "fake-embed-v1"


def test_index_collection_does_not_close_caller_owned_embedding_model(
    tmp_path: Path,
) -> None:
    embedder = _ClosableFakeEmbedder()

    index_collection(
        mineru_output_dir=MINERU_FIXTURES,
        chroma_dir=str(tmp_path / "chroma"),
        collection_name="test-coll",
        embedding_model=embedder,
    )

    assert embedder.closed is False


def test_index_collection_closes_owned_embedding_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedder = _ClosableFakeEmbedder()

    monkeypatch.setattr(
        "scripts.index_chunks.load_retrieval_provider_settings",
        lambda: object(),
    )
    monkeypatch.setattr(
        "scripts.index_chunks.build_embedding_provider",
        lambda settings: embedder,
    )

    index_collection(
        mineru_output_dir=MINERU_FIXTURES,
        chroma_dir=str(tmp_path / "chroma"),
        collection_name="test-coll",
    )

    assert embedder.closed is True
