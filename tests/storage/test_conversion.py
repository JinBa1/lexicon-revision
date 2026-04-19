from __future__ import annotations

import hashlib
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

import pytest
import src.storage as storage_module
from src.storage import (
    ConvertedPaperArtifacts,
    discover_converted_paper_artifacts,
    load_local_manifests,
    local_manifest_path,
    upload_converted_paper_artifacts,
)
from src.storage.keys import sha256_blob_key
from src.storage.local import LocalObjectStorage
from src.storage.manifest import ArtifactManifest

SECRET = b"test-secret-0123456789"


def _write_converted_paper_fixture(
    tmp_path: Path,
    *,
    with_markdown: bool = True,
) -> tuple[Path, Path, Path, tuple[Path, ...]]:
    pdf_path = tmp_path / "papers" / "y2025p1q7.pdf"
    output_dir = tmp_path / "output"
    content_list_dir = output_dir / "y2025p1q7" / "hybrid_auto"
    images_dir = content_list_dir / "images"

    pdf_path.parent.mkdir(parents=True)
    content_list_dir.mkdir(parents=True)
    images_dir.mkdir(parents=True)

    pdf_path.write_bytes(b"pdf-bytes")
    content_list_path = content_list_dir / "y2025p1q7_content_list.json"
    markdown_path = content_list_dir / "y2025p1q7.md"
    image_1 = images_dir / "fig_a.png"
    image_2 = images_dir / "fig_b.jpg"

    content_list_path.write_text("[]", encoding="utf-8")
    if with_markdown:
        markdown_path.write_text("# heading", encoding="utf-8")
    image_1.write_bytes(b"image-a")
    image_2.write_bytes(b"image-b")

    return pdf_path, output_dir, content_list_path, (image_1, image_2)


def test_discover_converted_paper_artifacts_finds_expected_files(
    tmp_path: Path,
) -> None:
    pdf_path, output_dir, content_list_path, images = _write_converted_paper_fixture(
        tmp_path
    )

    discovered = discover_converted_paper_artifacts(pdf_path, output_dir)

    assert [field.name for field in fields(ConvertedPaperArtifacts)] == [
        "paper_id",
        "pdf_path",
        "content_list_path",
        "markdown_path",
        "image_paths",
        "manifest_local_path",
    ]
    assert discovered == ConvertedPaperArtifacts(
        paper_id="y2025p1q7",
        pdf_path=pdf_path,
        content_list_path=content_list_path,
        markdown_path=content_list_path.with_name("y2025p1q7.md"),
        image_paths=images,
        manifest_local_path=content_list_path.with_name(
            "y2025p1q7_artifact_manifest.json"
        ),
    )


def test_discover_converted_paper_artifacts_missing_content_list_raises(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "papers" / "y2025p1q7.pdf"
    output_dir = tmp_path / "output"
    pdf_path.parent.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    pdf_path.write_bytes(b"pdf-bytes")

    with pytest.raises(FileNotFoundError, match="y2025p1q7"):
        discover_converted_paper_artifacts(pdf_path, output_dir)


def test_discover_converted_paper_artifacts_missing_markdown_returns_none(
    tmp_path: Path,
) -> None:
    pdf_path, output_dir, content_list_path, images = _write_converted_paper_fixture(
        tmp_path,
        with_markdown=False,
    )

    discovered = discover_converted_paper_artifacts(pdf_path, output_dir)

    assert discovered == ConvertedPaperArtifacts(
        paper_id="y2025p1q7",
        pdf_path=pdf_path,
        content_list_path=content_list_path,
        markdown_path=None,
        image_paths=images,
        manifest_local_path=content_list_path.with_name(
            "y2025p1q7_artifact_manifest.json"
        ),
    )


def test_discover_converted_paper_artifacts_duplicate_content_lists_raise(
    tmp_path: Path,
) -> None:
    pdf_path, output_dir, content_list_path, _ = _write_converted_paper_fixture(
        tmp_path
    )
    duplicate_dir = output_dir / "duplicate" / "hybrid_auto"
    duplicate_dir.mkdir(parents=True)
    duplicate_path = duplicate_dir / content_list_path.name
    duplicate_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="multiple.*y2025p1q7"):
        discover_converted_paper_artifacts(pdf_path, output_dir)


def test_upload_converted_paper_artifacts_uploads_manifest_and_files(
    tmp_path: Path,
) -> None:
    pdf_path, output_dir, content_list_path, images = _write_converted_paper_fixture(
        tmp_path
    )
    storage = LocalObjectStorage(root=tmp_path / "store", dev_presign_secret=SECRET)
    artifacts = discover_converted_paper_artifacts(pdf_path, output_dir)

    created_at = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    manifest = upload_converted_paper_artifacts(
        storage,
        artifacts,
        conversion_run_id="run-1",
        mineru_version="2.1.0",
        created_at=created_at,
    )

    pdf_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    source_pdf_key = sha256_blob_key(sha256_hex=pdf_sha, extension="pdf")
    content_list_key = "artifacts/mineru/run-1/content_list.json"
    markdown_key = "artifacts/mineru/run-1/document.md"
    image_keys = [
        "artifacts/mineru/run-1/images/fig_a.png",
        "artifacts/mineru/run-1/images/fig_b.jpg",
    ]
    manifest_key = "artifacts/mineru/run-1/manifest.json"

    assert storage.get_bytes(source_pdf_key) == pdf_path.read_bytes()
    assert storage.get_bytes(content_list_key) == content_list_path.read_bytes()
    assert (
        storage.get_bytes(markdown_key)
        == content_list_path.with_name("y2025p1q7.md").read_bytes()
    )
    assert storage.get_bytes(image_keys[0]) == images[0].read_bytes()
    assert storage.get_bytes(image_keys[1]) == images[1].read_bytes()
    manifest_json = storage.get_bytes(manifest_key).decode()
    assert manifest == ArtifactManifest.from_json(manifest_json)
    assert manifest.source_pdf_key == source_pdf_key
    assert [artifact.kind for artifact in manifest.artifacts] == [
        "content_list",
        "markdown",
        "image",
        "image",
    ]


def test_load_local_manifests_returns_pdf_stem_to_manifest_path(
    tmp_path: Path,
) -> None:
    pdf_path, output_dir, content_list_path, _ = _write_converted_paper_fixture(
        tmp_path
    )
    expected = local_manifest_path(content_list_path, pdf_stem=pdf_path.stem)
    expected.write_text("{}", encoding="utf-8")

    assert load_local_manifests(output_dir) == {pdf_path.name: expected}


def test_load_local_manifests_duplicate_pdf_names_raise(tmp_path: Path) -> None:
    _, output_dir, content_list_path, _ = _write_converted_paper_fixture(tmp_path)
    duplicate_dir = output_dir / "duplicate" / "hybrid_auto"
    duplicate_dir.mkdir(parents=True)
    duplicate_path = duplicate_dir / content_list_path.name
    duplicate_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate.*y2025p1q7\\.pdf"):
        load_local_manifests(output_dir)


def test_local_manifest_path_uses_pdf_stem(tmp_path: Path) -> None:
    content_list_path = (
        tmp_path / "output" / "paper" / "hybrid_auto" / "paper_content_list.json"
    )

    assert local_manifest_path(
        content_list_path, pdf_stem="paper"
    ) == content_list_path.with_name("paper_artifact_manifest.json")


def test_storage_package_exports_s3objectstorage_name() -> None:
    assert "S3ObjectStorage" in storage_module.__all__
