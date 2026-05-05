from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from src.chunking.models import Chunk, MediaRef
from src.search.media_sidecar import (
    build_storage_media_map,
    load_storage_media_map,
    materialize_media_refs,
    write_storage_media_map,
)
from src.storage.local import LocalObjectStorage
from src.storage.manifest import ArtifactManifest, ManifestArtifact

SECRET = b"media-sidecar-secret"


def _chunk_with_media(file_path: str | None) -> Chunk:
    return Chunk(
        id="cam-2025-p1-q1",
        chunk_level="question",
        parent_chunk_id=None,
        text="body",
        year=2025,
        paper=1,
        question_number=1,
        topic="Algorithms",
        author=None,
        tripos_part=None,
        sub_question_label=None,
        marks=None,
        total_marks=20,
        has_code=False,
        has_figure=True,
        has_table=False,
        media=[
            MediaRef(
                media_id="figure_1",
                kind="image",
                file_path=file_path,
                page_number=1,
                bbox=None,
                chunk_id="cam-2025-p1-q1",
                relation="direct",
                owner_level="question",
                owner_label=None,
                order_index=0,
                text_payload=None,
                description=None,
            )
        ],
        source_pdf="y2025p1q1.pdf",
        warnings=[],
    )


def _manifest() -> ArtifactManifest:
    return ArtifactManifest(
        conversion_run_id="run-y2025p1q1",
        paper_id="y2025p1q1",
        source_pdf_key="blobs/sha256/aa/aa/" + "a" * 64 + ".pdf",
        mineru_version="test-mineru",
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        artifacts=(
            ManifestArtifact(
                kind="image",
                key="artifacts/mineru/run-y2025p1q1/images/figure_1.png",
                content_type="image/png",
                sha256_hex=(
                    "8f8cbb7dcf46e0bc7d53265749a6c17d116093a6ba95e442764060c76fd4a86c"
                ),
                size_bytes=3,
            ),
        ),
    )


def test_build_storage_media_map_uses_manifest_object_keys() -> None:
    media_map = build_storage_media_map(
        chunks=[_chunk_with_media("/tmp/images/figure_1.png")],
        manifests={"y2025p1q1.pdf": _manifest()},
    )

    ref = media_map["cam-2025-p1-q1"][0]
    assert ref["object_key"] == "artifacts/mineru/run-y2025p1q1/images/figure_1.png"
    assert "file_path" not in ref


def test_build_storage_media_map_rejects_missing_manifest_mapping() -> None:
    with pytest.raises(ValueError, match="object key"):
        build_storage_media_map(
            chunks=[_chunk_with_media("/tmp/images/figure_1.png")],
            manifests={},
        )


def test_build_storage_media_map_verifies_manifest_hash_and_size(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "figure_1.png"
    local_path.write_bytes(b"png")

    media_map = build_storage_media_map(
        chunks=[_chunk_with_media(str(local_path))],
        manifests={"y2025p1q1.pdf": _manifest()},
        verify_local_files=True,
    )

    assert media_map["cam-2025-p1-q1"][0]["object_key"].endswith("figure_1.png")


def test_build_storage_media_map_rejects_stale_manifest_hash(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "figure_1.png"
    local_path.write_bytes(b"different")

    with pytest.raises(ValueError, match="manifest hash mismatch"):
        build_storage_media_map(
            chunks=[_chunk_with_media(str(local_path))],
            manifests={"y2025p1q1.pdf": _manifest()},
            verify_local_files=True,
        )


def test_build_storage_media_map_rejects_stale_manifest_size(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "figure_1.png"
    local_path.write_bytes(b"png")
    manifest = ArtifactManifest(
        conversion_run_id="run-y2025p1q1",
        paper_id="y2025p1q1",
        source_pdf_key="blobs/sha256/aa/aa/" + "a" * 64 + ".pdf",
        mineru_version="test-mineru",
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        artifacts=(
            ManifestArtifact(
                kind="image",
                key="artifacts/mineru/run-y2025p1q1/images/figure_1.png",
                content_type="image/png",
                sha256_hex=(
                    "8f8cbb7dcf46e0bc7d53265749a6c17d116093a6ba95e442764060c76fd4a86c"
                ),
                size_bytes=4,
            ),
        ),
    )

    with pytest.raises(ValueError, match="manifest size mismatch"):
        build_storage_media_map(
            chunks=[_chunk_with_media(str(local_path))],
            manifests={"y2025p1q1.pdf": manifest},
            verify_local_files=True,
        )


def test_write_storage_media_map_round_trips_valid_sidecar(tmp_path: Path) -> None:
    output_path = tmp_path / "test_media_map.json"
    media_map = build_storage_media_map(
        chunks=[_chunk_with_media("/tmp/images/figure_1.png")],
        manifests={"y2025p1q1.pdf": _manifest()},
    )

    write_storage_media_map(output_path=output_path, media_map=media_map)

    assert load_storage_media_map(output_path) == media_map


def test_materialize_media_refs_presigns_access_urls(tmp_path: Path) -> None:
    storage = LocalObjectStorage(
        root=tmp_path / "object-store",
        dev_presign_secret=SECRET,
    )
    storage.put_bytes(
        key="artifacts/mineru/run-y2025p1q1/images/figure_1.png",
        data=b"png",
        content_type="image/png",
    )

    refs = materialize_media_refs(
        refs=[
            {
                "media_id": "figure_1",
                "kind": "image",
                "relation": "direct",
                "object_key": "artifacts/mineru/run-y2025p1q1/images/figure_1.png",
            }
        ],
        object_storage=storage,
    )

    assert refs[0].object_key == "artifacts/mineru/run-y2025p1q1/images/figure_1.png"
    assert refs[0].access_url is not None


def test_materialize_media_refs_rejects_persisted_access_url() -> None:
    refs = materialize_media_refs(
        refs=[
            {
                "media_id": "figure_1",
                "kind": "image",
                "relation": "direct",
                "object_key": "artifacts/mineru/run-y2025p1q1/images/figure_1.png",
                "access_url": "https://example.com/signed-url",
            }
        ],
        object_storage=None,
    )

    assert refs == []


def test_load_storage_media_map_rejects_old_file_path_shape(tmp_path: Path) -> None:
    sidecar_path = tmp_path / "test_media_map.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "chunk-1": [
                    {
                        "media_id": "fig-1",
                        "kind": "image",
                        "file_path": "/tmp/fig.png",
                        "relation": "direct",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert load_storage_media_map(sidecar_path) == {}
