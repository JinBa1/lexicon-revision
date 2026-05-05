from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
from scripts.index_chunks_postgres import index_collection_postgres
from sqlalchemy import create_engine, text
from src.metadata_schema import default_schema_path
from src.search.pg_repository import PgSearchRepository
from src.search.pg_service import PgSearchService
from src.search.providers.base import EmbeddingResult
from src.storage.local import LocalObjectStorage

pytestmark = pytest.mark.integration

MINERU_FIXTURES = Path("tests/fixtures/mineru/cambridge")


class _Embedder:
    model_id = "fake-v1"

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[self._vector(text) for text in texts],
            model_id=self.model_id,
        )

    def embed_query(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(vectors=[self._vector(text)], model_id=self.model_id)

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = []
        for idx in range(0, 32, 4):
            raw = int.from_bytes(digest[idx : idx + 4], "big")
            values.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
        return values


def _fixture_copy_with_manifests(tmp_path: Path) -> Path:
    target = tmp_path / "mineru_fixtures"
    shutil.copytree(MINERU_FIXTURES, target)
    for content_list in target.glob("**/*_content_list.json"):
        stem = content_list.stem.replace("_content_list", "")
        images = sorted((content_list.parent / "images").glob("*"))
        manifest = {
            "conversion_run_id": f"run-{stem}",
            "paper_id": stem,
            "source_pdf_key": "blobs/sha256/aa/aa/" + "a" * 64 + ".pdf",
            "mineru_version": "test-mineru",
            "created_at": "2026-04-18T12:00:00+00:00",
            "artifacts": [
                {
                    "kind": "image",
                    "key": f"artifacts/mineru/run-{stem}/images/{image.name}",
                    "content_type": "image/png",
                    "sha256_hex": hashlib.sha256(image.read_bytes()).hexdigest(),
                    "size_bytes": image.stat().st_size,
                }
                for image in images
                if image.is_file()
            ],
        }
        (content_list.parent / f"{stem}_artifact_manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
    return target


def test_pg_search_returns_object_key_and_access_url(
    tmp_path: Path,
) -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for pgvector integration tests")

    fixture_dir = _fixture_copy_with_manifests(tmp_path)
    storage = LocalObjectStorage(
        root=tmp_path / "object-store",
        dev_presign_secret=b"secret",
    )

    engine = create_engine(database_url, future=True)
    embedder = _Embedder()
    collection = "fixture-storage"

    index_collection_postgres(
        mineru_output_dir=str(fixture_dir),
        collection_name=collection,
        engine=engine,
        embedding_model=embedder,
        embedding_dimension=8,
        metadata_schema_path=str(default_schema_path("cam-cs-tripos-fixture")),
        recreate_collection=True,
    )

    assert not (tmp_path / "media").exists()

    with engine.connect() as conn:
        media_row = conn.execute(
            text(
                """
                select chunk_id, text
                from chunks
                where collection_id = (
                    select id from collections where name = :collection
                )
                  and jsonb_array_length(media_refs) > 0
                order by chunk_id
                limit 1
                """
            ),
            {"collection": collection},
        ).one()
        media_chunk_id = media_row.chunk_id
        query_text = media_row.text
        assert media_chunk_id

    service = PgSearchService(
        repository=PgSearchRepository(engine=engine),
        embedding_model=embedder,
        embedding_dimension=8,
        object_storage=storage,
    )
    response = service.search(
        query_text,
        collection=collection,
        limit=5,
        rerank=False,
    )

    refs = [ref for result in response.results for ref in result.media]
    assert refs
    assert refs[0].object_key is not None
    assert refs[0].access_url is not None
