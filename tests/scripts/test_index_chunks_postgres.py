from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
from scripts.index_chunks_postgres import index_collection_postgres, parse_args
from src.metadata_schema import CollectionMetadataSchema
from src.search.providers.base import EmbeddingResult

REPO_ROOT = Path(__file__).resolve().parents[2]
MINERU_FIXTURES = str(REPO_ROOT / "tests" / "data" / "mineru_fixtures")


class _FakeEmbedder:
    model_id = "fake-embed-v1"

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[[0.0, 0.0] for _ in texts],
            model_id=self.model_id,
        )


def _fixture_copy_with_manifests(tmp_path: Path) -> str:
    fixture_copy = tmp_path / "mineru_fixtures"
    shutil.copytree(MINERU_FIXTURES, fixture_copy)
    for content_list in fixture_copy.glob("**/*_content_list.json"):
        stem = content_list.stem.replace("_content_list", "")
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
                    "sha256_hex": "b" * 64,
                    "size_bytes": 3,
                }
                for image in sorted((content_list.parent / "images").glob("*"))
                if image.is_file()
            ],
        }
        (content_list.parent / f"{stem}_artifact_manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
    return str(fixture_copy)


def test_parse_args_defaults(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "index_chunks_postgres.py",
            "--input",
            "tests/data/mineru_fixtures",
            "--collection",
            "fixture",
        ],
    )

    args = parse_args()

    assert args.input == "tests/data/mineru_fixtures"
    assert args.collection == "fixture"
    assert args.metadata_schema is None
    assert args.recreate_collection is False


def test_parse_args_supports_recreate(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "index_chunks_postgres.py",
            "--input",
            "tests/data/mineru_fixtures",
            "--collection",
            "fixture",
            "--recreate-collection",
        ],
    )

    assert parse_args().recreate_collection is True


def test_parse_args_supports_metadata_schema(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "index_chunks_postgres.py",
            "--input",
            "tests/data/mineru_fixtures",
            "--collection",
            "fixture",
            "--metadata-schema",
            "config/collections/cam-cs-tripos-fixture.metadata-schema.json",
        ],
    )

    assert parse_args().metadata_schema.endswith(".metadata-schema.json")


def test_index_collection_postgres_writes_storage_backed_sidecar(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture_dir = _fixture_copy_with_manifests(tmp_path)
    media_dir = tmp_path / "media"
    calls: dict[str, object] = {}

    class _FakeRepo:
        def __init__(
            self,
            *,
            engine,
            embedding_model_id: str,
            embedding_dimension: int,
        ) -> None:
            calls["engine"] = engine
            calls["embedding_model_id"] = embedding_model_id
            calls["embedding_dimension"] = embedding_dimension

        def recreate_collection(self, collection_name: str) -> None:
            calls["recreated"] = collection_name

        def index_chunks(
            self,
            *,
            collection_name: str,
            chunks,
            vectors,
            metadata_schema: CollectionMetadataSchema,
        ) -> None:
            calls["indexed_collection"] = collection_name
            calls["chunk_count"] = len(chunks)
            calls["vector_count"] = len(vectors)
            calls["metadata_schema"] = metadata_schema.model_dump(mode="json")

    monkeypatch.setattr("scripts.index_chunks_postgres.PgIndexRepository", _FakeRepo)
    monkeypatch.setattr(
        "scripts.index_chunks_postgres.DEFAULT_CHROMA_DIR",
        str(media_dir),
    )
    monkeypatch.setattr(
        "scripts.index_chunks_postgres.ensure_metadata_indexes",
        lambda engine, *, collection_name, schema: calls.update(
            {
                "indexed_engine": engine,
                "indexed_collection_name": collection_name,
                "indexed_schema": schema.model_dump(mode="json"),
            }
        ),
    )

    index_collection_postgres(
        mineru_output_dir=fixture_dir,
        collection_name="cam-cs-tripos-fixture",
        engine=object(),
        embedding_model=_FakeEmbedder(),
        embedding_dimension=2,
        recreate_collection=True,
    )

    sidecar_path = media_dir / "cam-cs-tripos-fixture_media_map.json"
    media_map = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sample_ref = next(iter(media_map.values()))[0]

    assert calls["recreated"] == "cam-cs-tripos-fixture"
    assert calls["indexed_collection"] == "cam-cs-tripos-fixture"
    assert calls["chunk_count"] == calls["vector_count"]
    assert calls["indexed_collection_name"] == "cam-cs-tripos-fixture"
    assert calls["metadata_schema"] == calls["indexed_schema"]
    assert calls["metadata_schema"]["fields"][0]["key"] == "year"
    assert sample_ref["object_key"].startswith("artifacts/mineru/run-")
    assert "file_path" not in sample_ref


def test_index_collection_postgres_missing_manifest_raises_before_indexing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture_copy = tmp_path / "mineru_fixtures"
    shutil.copytree(MINERU_FIXTURES, fixture_copy)
    calls: dict[str, object] = {}

    class _FakeRepo:
        def __init__(
            self,
            *,
            engine,
            embedding_model_id: str,
            embedding_dimension: int,
        ) -> None:
            del engine, embedding_model_id, embedding_dimension

        def recreate_collection(self, collection_name: str) -> None:
            calls["recreated"] = collection_name

        def index_chunks(
            self,
            *,
            collection_name: str,
            chunks,
            vectors,
            metadata_schema: CollectionMetadataSchema,
        ) -> None:
            del collection_name, chunks, vectors
            del metadata_schema
            calls["indexed"] = True

    monkeypatch.setattr("scripts.index_chunks_postgres.PgIndexRepository", _FakeRepo)
    monkeypatch.setattr(
        "scripts.index_chunks_postgres.ensure_metadata_indexes",
        lambda engine, *, collection_name, schema: None,
    )

    with pytest.raises(FileNotFoundError):
        index_collection_postgres(
            mineru_output_dir=str(fixture_copy),
            collection_name="cam-cs-tripos-fixture",
            engine=object(),
            embedding_model=_FakeEmbedder(),
            embedding_dimension=2,
            recreate_collection=True,
        )

    assert "recreated" not in calls
    assert "indexed" not in calls
