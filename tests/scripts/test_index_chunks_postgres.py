from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
from scripts.index_chunks_postgres import (
    build_embedding_text,
    index_collection_postgres,
    parse_args,
)
from src.chunking.models import Chunk
from src.metadata_schema import CollectionMetadataSchema, build_chunk_metadata
from src.search.providers.base import EmbeddingResult

REPO_ROOT = Path(__file__).resolve().parents[2]
MINERU_FIXTURES = str(REPO_ROOT / "tests" / "fixtures" / "mineru" / "cambridge")
UOE_MINERU_FIXTURES = str(REPO_ROOT / "tests" / "fixtures" / "mineru" / "uoe")


class _FakeEmbedder:
    model_id = "fake-embed-v1"

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        self.last_texts = texts
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


def _uoe_fixture_copy_with_manifest(tmp_path: Path) -> str:
    fixture_copy = tmp_path / "uoe_mineru_fixtures"
    shutil.copytree(UOE_MINERU_FIXTURES, fixture_copy)
    stem = "2019937_MECE10017"
    manifest = {
        "conversion_run_id": "run-2019937-mece10017",
        "paper_id": stem,
        "source_pdf_key": "blobs/sha256/aa/aa/" + "a" * 64 + ".pdf",
        "mineru_version": "test-mineru",
        "created_at": "2026-04-18T12:00:00+00:00",
        "artifacts": [
            {
                "kind": "image",
                "key": "artifacts/mineru/run-2019937-mece10017/images/fig_001.png",
                "content_type": "image/png",
                "sha256_hex": "b" * 64,
                "size_bytes": 3,
            }
        ],
    }
    (fixture_copy / stem / "hybrid_auto" / f"{stem}_artifact_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return str(fixture_copy)


def test_parse_args_defaults(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "index_chunks_postgres.py",
            "--input",
            "tests/fixtures/mineru/cambridge",
            "--collection",
            "fixture",
        ],
    )

    args = parse_args()

    assert args.input == "tests/fixtures/mineru/cambridge"
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
            "tests/fixtures/mineru/cambridge",
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
            "tests/fixtures/mineru/cambridge",
            "--collection",
            "fixture",
            "--metadata-schema",
            "config/collections/cam-cs-tripos-fixture.metadata-schema.json",
        ],
    )

    assert parse_args().metadata_schema.endswith(".metadata-schema.json")


def test_parse_args_supports_collection_config(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "index_chunks_postgres.py",
            "--input",
            "tests/fixtures/mineru/cambridge",
            "--collection",
            "fixture",
            "--collection-config",
            "config/collections/uoe-mece10017.collection.json",
        ],
    )

    assert parse_args().collection_config.endswith(".collection.json")


def test_build_embedding_text_uses_schema_rendering() -> None:
    schema = CollectionMetadataSchema.model_validate(
        {
            "version": 1,
            "fields": [
                {
                    "key": "year",
                    "label": "Year",
                    "type": "integer",
                    "operators": ["eq"],
                    "exposed": False,
                    "source": "chunk.year",
                },
                {
                    "key": "author",
                    "label": "Author",
                    "type": "string",
                    "operators": ["eq"],
                    "exposed": True,
                    "source": "chunk.author",
                },
                {
                    "key": "tripos_part",
                    "label": "Tripos Part",
                    "type": "string",
                    "operators": ["eq"],
                    "exposed": True,
                    "source": "chunk.tripos_part",
                },
            ],
        }
    )
    chunk = Chunk(
        id="cam-2024-p2-q5",
        chunk_level="question",
        parent_chunk_id=None,
        text="Binary search trees support efficient lookup.",
        year=2024,
        paper=2,
        question_number=5,
        topic="Algorithms",
        author="abc123",
        tripos_part="Part IB",
        sub_question_label=None,
        marks=10,
        total_marks=20,
        has_code=True,
        has_figure=False,
        has_table=False,
        media=[],
        source_pdf="y2024p2.pdf",
        warnings=[],
    )

    rendered = build_embedding_text(
        chunk,
        schema=schema,
        metadata=build_chunk_metadata(chunk, schema),
    )

    assert "Author: abc123" in rendered
    assert "Tripos Part: Part IB" in rendered
    assert "Year:" not in rendered


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
            community_id: str | None = None,
        ) -> None:
            calls["indexed_collection"] = collection_name
            calls["chunk_count"] = len(chunks)
            calls["vector_count"] = len(vectors)
            calls["metadata_schema"] = metadata_schema.model_dump(mode="json")
            calls["community_id"] = community_id

    monkeypatch.setattr("scripts.index_chunks_postgres.PgIndexRepository", _FakeRepo)
    monkeypatch.setattr(
        "scripts.index_chunks_postgres.DEFAULT_MEDIA_DIR",
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
    assert calls["community_id"] is None
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
            community_id: str | None = None,
        ) -> None:
            del collection_name, chunks, vectors
            del metadata_schema, community_id
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


def test_index_collection_postgres_passes_configured_community(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture_dir = _fixture_copy_with_manifests(tmp_path)
    media_dir = tmp_path / "media"
    collection_config_path = tmp_path / "uoe-mece10017.collection.json"
    collection_config_path.write_text(
        '{"name": "uoe-mece10017", "community_id": "edinburgh"}',
        encoding="utf-8",
    )
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
            community_id: str | None,
        ) -> None:
            calls["indexed_collection"] = collection_name
            calls["chunk_count"] = len(chunks)
            calls["vector_count"] = len(vectors)
            calls["metadata_schema"] = metadata_schema.model_dump(mode="json")
            calls["community_id"] = community_id

    monkeypatch.setattr("scripts.index_chunks_postgres.PgIndexRepository", _FakeRepo)
    monkeypatch.setattr(
        "scripts.index_chunks_postgres.DEFAULT_MEDIA_DIR",
        str(media_dir),
    )
    monkeypatch.setattr(
        "scripts.index_chunks_postgres.ensure_metadata_indexes",
        lambda engine, *, collection_name, schema: None,
    )

    index_collection_postgres(
        mineru_output_dir=fixture_dir,
        collection_name="uoe-mece10017",
        engine=object(),
        embedding_model=_FakeEmbedder(),
        embedding_dimension=2,
        collection_config_path=str(collection_config_path),
    )

    assert calls["indexed_collection"] == "uoe-mece10017"
    assert calls["chunk_count"] == calls["vector_count"]
    assert calls["metadata_schema"]["fields"][0]["key"] == "year"
    assert calls["community_id"] == "edinburgh"


def test_index_collection_postgres_indexes_uoe_fixture_with_private_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture_dir = _uoe_fixture_copy_with_manifest(tmp_path)
    media_dir = tmp_path / "media"
    calls: dict[str, object] = {}
    embedder = _FakeEmbedder()

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
            community_id: str | None,
        ) -> None:
            calls["indexed_collection"] = collection_name
            calls["chunks"] = chunks
            calls["vector_count"] = len(vectors)
            calls["metadata_schema"] = metadata_schema.model_dump(mode="json")
            calls["community_id"] = community_id

    monkeypatch.setattr("scripts.index_chunks_postgres.PgIndexRepository", _FakeRepo)
    monkeypatch.setattr(
        "scripts.index_chunks_postgres.DEFAULT_MEDIA_DIR",
        str(media_dir),
    )
    monkeypatch.setattr(
        "scripts.index_chunks_postgres.ensure_metadata_indexes",
        lambda engine, *, collection_name, schema: None,
    )

    index_collection_postgres(
        mineru_output_dir=fixture_dir,
        collection_name="uoe-mece10017",
        engine=object(),
        embedding_model=embedder,
        embedding_dimension=2,
        university="uoe",
        parser_name="uoe",
    )

    chunks = calls["chunks"]
    sidecar_path = media_dir / "uoe-mece10017_media_map.json"
    media_map = json.loads(sidecar_path.read_text(encoding="utf-8"))
    schema_keys = {field["key"] for field in calls["metadata_schema"]["fields"]}

    assert calls["indexed_collection"] == "uoe-mece10017"
    assert calls["community_id"] == "edinburgh"
    assert len(chunks) == calls["vector_count"]
    assert {"course_code", "course_title", "document_id"}.issubset(schema_keys)
    assert any("Course Code: MECE10017" in text for text in embedder.last_texts)
    assert any(
        "Course Title: DESIGN OF SURGICAL TOOLS AND IMPLANTED MEDICAL DEVICES MSC"
        in text
        for text in embedder.last_texts
    )
    sample_ref = next(iter(media_map.values()))[0]
    assert sample_ref["object_key"].startswith(
        "artifacts/mineru/run-2019937-mece10017/"
    )
