from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
import scripts.convert_papers as convert_papers
from src.storage import conversion_run_id_from_stem, mineru_artifact_key
from src.storage.local import LocalObjectStorage
from src.storage.manifest import ArtifactManifest, ManifestArtifact

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET = b"convert-papers-secret"
SAMPLE_SOURCE_PDF_KEY = "blobs/sha256/aa/aa/" + "a" * 64 + ".pdf"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _write_converted_paper_fixture(
    tmp_path: Path,
    *,
    stem: str,
) -> tuple[Path, Path]:
    pdf_path = tmp_path / "papers" / f"{stem}.pdf"
    output_dir = tmp_path / "output"
    content_list_dir = output_dir / stem / "hybrid_auto"
    images_dir = content_list_dir / "images"

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    content_list_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    pdf_path.write_bytes(b"pdf-bytes")
    (content_list_dir / f"{stem}_content_list.json").write_text("[]", encoding="utf-8")
    (content_list_dir / f"{stem}.md").write_text("# heading", encoding="utf-8")
    (images_dir / "fig_a.png").write_bytes(b"image-a")

    return pdf_path, output_dir


def _write_mineru_outputs(output_dir: Path, *, stem: str) -> None:
    content_list_dir = output_dir / stem / "hybrid_auto"
    images_dir = content_list_dir / "images"
    content_list_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    (content_list_dir / f"{stem}_content_list.json").write_text("[]", encoding="utf-8")
    (content_list_dir / f"{stem}.md").write_text("# heading", encoding="utf-8")
    (images_dir / "fig_a.png").write_bytes(b"image-a")


def _write_manifest(
    output_dir: Path,
    *,
    stem: str,
    paper_id: str,
    conversion_run_id: str | None = None,
    content_list_key: str | None = None,
    include_all_outputs: bool = True,
) -> Path:
    if conversion_run_id is None:
        conversion_run_id = conversion_run_id_from_stem(stem)
    if content_list_key is None:
        content_list_key = mineru_artifact_key(
            conversion_run_id=conversion_run_id,
            kind="content_list",
            filename="",
        )
    artifacts = [
        ManifestArtifact(
            kind="content_list",
            key=content_list_key,
            content_type="application/json",
            sha256_hex="b" * 64,
            size_bytes=2,
        ),
    ]
    if include_all_outputs:
        content_list_dir = output_dir / stem / "hybrid_auto"
        if (content_list_dir / f"{stem}.md").is_file():
            artifacts.append(
                ManifestArtifact(
                    kind="markdown",
                    key=mineru_artifact_key(
                        conversion_run_id=conversion_run_id,
                        kind="markdown",
                        filename="",
                    ),
                    content_type="text/markdown",
                    sha256_hex="c" * 64,
                    size_bytes=9,
                )
            )
        images_dir = content_list_dir / "images"
        image_paths = sorted(path for path in images_dir.glob("**/*") if path.is_file())
        for image_path in image_paths:
            artifacts.append(
                ManifestArtifact(
                    kind="image",
                    key=mineru_artifact_key(
                        conversion_run_id=conversion_run_id,
                        kind="image",
                        filename=image_path.name,
                    ),
                    content_type="image/png",
                    sha256_hex="d" * 64,
                    size_bytes=7,
                )
            )
    manifest = ArtifactManifest(
        conversion_run_id=conversion_run_id,
        paper_id=paper_id,
        source_pdf_key=SAMPLE_SOURCE_PDF_KEY,
        mineru_version="mineru-cli",
        created_at=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
        artifacts=tuple(artifacts),
    )
    manifest_path = output_dir / stem / "hybrid_auto" / f"{stem}_artifact_manifest.json"
    manifest_path.write_text(manifest.to_json() + "\n", encoding="utf-8")
    return manifest_path


def _expected_mineru_artifact_keys(stem: str) -> set[str]:
    run_id = conversion_run_id_from_stem(stem)
    return {
        mineru_artifact_key(
            conversion_run_id=run_id,
            kind="content_list",
            filename="",
        ),
        mineru_artifact_key(
            conversion_run_id=run_id,
            kind="markdown",
            filename="",
        ),
        mineru_artifact_key(
            conversion_run_id=run_id,
            kind="image",
            filename="fig_a.png",
        ),
    }


def test_upload_batch_artifacts_writes_local_manifest_and_storage_objects(
    tmp_path: Path,
) -> None:
    pdf_path, output_dir = _write_converted_paper_fixture(tmp_path, stem="y2025p1q7")
    storage = LocalObjectStorage(root=tmp_path / "store", dev_presign_secret=SECRET)

    manifests = convert_papers.upload_batch_artifacts(
        pdf_paths=[pdf_path],
        output_dir=output_dir,
        storage=storage,
        mineru_version="mineru-cli",
    )

    assert len(manifests) == 1
    manifest = manifests[0]
    assert isinstance(manifest, ArtifactManifest)
    assert manifest.paper_id == "y2025p1q7"
    assert storage.exists(manifest.source_pdf_key)
    assert all(storage.exists(artifact.key) for artifact in manifest.artifacts)

    manifest_path = (
        output_dir / "y2025p1q7" / "hybrid_auto" / "y2025p1q7_artifact_manifest.json"
    )
    assert manifest_path.read_text(encoding="utf-8") == manifest.to_json() + "\n"


def test_upload_batch_artifacts_sanitizes_uoe_run_id(tmp_path: Path) -> None:
    pdf_path, output_dir = _write_converted_paper_fixture(
        tmp_path,
        stem="2019937_MECE10017",
    )
    storage = LocalObjectStorage(root=tmp_path / "store", dev_presign_secret=SECRET)

    manifests = convert_papers.upload_batch_artifacts(
        pdf_paths=[pdf_path],
        output_dir=output_dir,
        storage=storage,
        mineru_version="mineru-cli",
    )

    assert len(manifests) == 1
    manifest = manifests[0]
    assert manifest.conversion_run_id == "run-2019937-mece10017"
    assert {artifact.key for artifact in manifest.artifacts} == {
        "artifacts/mineru/run-2019937-mece10017/content_list.json",
        "artifacts/mineru/run-2019937-mece10017/document.md",
        "artifacts/mineru/run-2019937-mece10017/images/fig_a.png",
    }

    manifest_path = (
        output_dir
        / "2019937_MECE10017"
        / "hybrid_auto"
        / "2019937_MECE10017_artifact_manifest.json"
    )
    assert (
        ArtifactManifest.from_json(
            manifest_path.read_text(encoding="utf-8")
        ).conversion_run_id
        == "run-2019937-mece10017"
    )


def test_upload_batch_artifacts_continues_after_one_pdf_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    exception_mock = Mock()
    monkeypatch.setattr(convert_papers.logger, "exception", exception_mock)
    success_pdf, output_dir = _write_converted_paper_fixture(tmp_path, stem="y2025p1q7")
    failed_pdf = tmp_path / "papers" / "y2025p1q8.pdf"
    failed_pdf.write_bytes(b"pdf-bytes")
    storage = LocalObjectStorage(root=tmp_path / "store", dev_presign_secret=SECRET)

    manifests = convert_papers.upload_batch_artifacts(
        pdf_paths=[failed_pdf, success_pdf],
        output_dir=output_dir,
        storage=storage,
        mineru_version="mineru-cli",
    )

    assert [manifest.paper_id for manifest in manifests] == ["y2025p1q7"]
    exception_mock.assert_called_once_with(
        "Failed to upload converted artifacts for %s",
        failed_pdf.name,
    )

    manifest_path = (
        output_dir / "y2025p1q7" / "hybrid_auto" / "y2025p1q7_artifact_manifest.json"
    )
    assert manifest_path.is_file()


def test_upload_batch_artifacts_strict_raises_after_uploading_successes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    exception_mock = Mock()
    monkeypatch.setattr(convert_papers.logger, "exception", exception_mock)
    success_pdf, output_dir = _write_converted_paper_fixture(tmp_path, stem="y2025p1q7")
    failed_pdf = tmp_path / "papers" / "y2025p1q8.pdf"
    failed_pdf.write_bytes(b"pdf-bytes")
    storage = LocalObjectStorage(root=tmp_path / "store", dev_presign_secret=SECRET)

    with pytest.raises(RuntimeError) as exc_info:
        convert_papers.upload_batch_artifacts(
            pdf_paths=[failed_pdf, success_pdf],
            output_dir=output_dir,
            storage=storage,
            mineru_version="mineru-cli",
            strict=True,
        )

    assert str(exc_info.value) == "artifact upload failed for 1 PDF(s): y2025p1q8.pdf"
    assert isinstance(exc_info.value.__cause__, FileNotFoundError)
    exception_mock.assert_called_once_with(
        "Failed to upload converted artifacts for %s",
        failed_pdf.name,
    )

    manifest_path = (
        output_dir / "y2025p1q7" / "hybrid_auto" / "y2025p1q7_artifact_manifest.json"
    )
    assert manifest_path.is_file()
    manifest = ArtifactManifest.from_json(manifest_path.read_text(encoding="utf-8"))
    assert manifest.paper_id == "y2025p1q7"


def test_write_manifest_atomic_preserves_original_and_cleans_temp_on_to_json_error(
    tmp_path: Path,
) -> None:
    class BrokenManifest:
        def to_json(self) -> str:
            raise ValueError("cannot serialize manifest")

    manifest_path = tmp_path / "paper_artifact_manifest.json"
    manifest_path.write_text("original\n", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot serialize manifest"):
        convert_papers.write_manifest_atomic(manifest_path, BrokenManifest())

    assert manifest_path.read_text(encoding="utf-8") == "original\n"
    assert list(tmp_path.glob(f".{manifest_path.name}.*")) == []


def test_main_continues_when_storage_is_misconfigured_after_conversion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_dir = tmp_path / "papers"
    output_dir = tmp_path / "output"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / "y2025p1q7.pdf"
    pdf_path.write_bytes(b"pdf-bytes")
    info_mock = Mock()
    exception_mock = Mock()
    warning_mock = Mock()

    def fake_run_mineru_batch(
        pdf_paths: list[Path],
        output_dir: Path,
        method: str = "auto",
        backend: str = "hybrid-auto-engine",
        lang: str = "en",
    ) -> bool:
        del method, backend, lang
        for path in pdf_paths:
            _write_mineru_outputs(output_dir, stem=path.stem)
        return True

    monkeypatch.setattr(convert_papers, "run_mineru_batch", fake_run_mineru_batch)
    monkeypatch.setattr(convert_papers.logger, "info", info_mock)
    monkeypatch.setattr(convert_papers.logger, "exception", exception_mock)
    monkeypatch.setattr(convert_papers.logger, "warning", warning_mock)
    monkeypatch.delenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", raising=False)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "store"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["convert_papers.py", str(pdf_dir), str(output_dir)],
    )

    convert_papers.main()

    content_list_path = (
        output_dir / "y2025p1q7" / "hybrid_auto" / "y2025p1q7_content_list.json"
    )

    assert content_list_path.is_file()
    assert not any(
        call.args[:2] == ("Uploaded artifacts for %d PDFs", 1)
        for call in info_mock.call_args_list
    )
    assert any(
        call.args
        == (
            "Done: %d converted, %d skipped, %d failed, %d uploaded (of %d total)",
            1,
            0,
            0,
            0,
            1,
        )
        for call in info_mock.call_args_list
    )
    warning_mock.assert_called_once()
    assert warning_mock.call_args.args[0].startswith("Storage upload skipped:")
    assert "OBJECT_STORAGE_DEV_PRESIGN_SECRET" in str(warning_mock.call_args.args[1])
    exception_mock.assert_not_called()


def test_main_strict_upload_exits_before_mineru_when_storage_misconfigured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_dir = tmp_path / "papers"
    output_dir = tmp_path / "output"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / "y2025p1q7.pdf"
    pdf_path.write_bytes(b"pdf-bytes")
    error_mock = Mock()
    run_mineru_mock = Mock()

    monkeypatch.setattr(convert_papers, "run_mineru_batch", run_mineru_mock)
    monkeypatch.setattr(convert_papers.logger, "error", error_mock)
    monkeypatch.delenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", raising=False)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "store"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["convert_papers.py", str(pdf_dir), str(output_dir), "--strict-upload"],
    )

    with pytest.raises(SystemExit) as exc_info:
        convert_papers.main()

    assert exc_info.value.code == 1
    run_mineru_mock.assert_not_called()
    assert not (
        output_dir / "y2025p1q7" / "hybrid_auto" / "y2025p1q7_content_list.json"
    ).exists()
    error_mock.assert_called_once()
    assert error_mock.call_args.args[0].startswith("Storage upload required")


def test_main_strict_upload_exits_after_uploading_successes_when_conversion_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_dir = tmp_path / "papers"
    output_dir = tmp_path / "output"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    success_pdf = pdf_dir / "y2025p1q7.pdf"
    failed_pdf = pdf_dir / "y2025p1q8.pdf"
    success_pdf.write_bytes(b"pdf-bytes")
    failed_pdf.write_bytes(b"pdf-bytes")

    def fake_run_mineru_batch(
        pdf_paths: list[Path],
        output_dir: Path,
        method: str = "auto",
        backend: str = "hybrid-auto-engine",
        lang: str = "en",
    ) -> bool:
        del pdf_paths, method, backend, lang
        _write_mineru_outputs(output_dir, stem=success_pdf.stem)
        return True

    monkeypatch.setattr(convert_papers, "run_mineru_batch", fake_run_mineru_batch)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", "dev-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        ["convert_papers.py", str(pdf_dir), str(output_dir), "--strict-upload"],
    )

    with pytest.raises(SystemExit) as exc_info:
        convert_papers.main()

    assert exc_info.value.code == 1
    manifest_path = (
        output_dir / "y2025p1q7" / "hybrid_auto" / "y2025p1q7_artifact_manifest.json"
    )
    assert manifest_path.is_file()
    assert (
        ArtifactManifest.from_json(manifest_path.read_text(encoding="utf-8")).paper_id
        == success_pdf.stem
    )


def test_main_strict_force_does_not_upload_stale_outputs_when_mineru_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_dir = tmp_path / "papers"
    output_dir = tmp_path / "output"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / "y2025p1q7.pdf"
    pdf_path.write_bytes(b"pdf-bytes")
    _write_mineru_outputs(output_dir, stem=pdf_path.stem)
    manifest_path = (
        output_dir
        / pdf_path.stem
        / "hybrid_auto"
        / f"{pdf_path.stem}_artifact_manifest.json"
    )

    def fake_run_mineru_batch(
        pdf_paths: list[Path],
        output_dir: Path,
        method: str = "auto",
        backend: str = "hybrid-auto-engine",
        lang: str = "en",
    ) -> bool:
        del pdf_paths, output_dir, method, backend, lang
        return False

    monkeypatch.setattr(convert_papers, "run_mineru_batch", fake_run_mineru_batch)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", "dev-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "convert_papers.py",
            str(pdf_dir),
            str(output_dir),
            "--strict-upload",
            "--force",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        convert_papers.main()

    assert exc_info.value.code == 1
    assert not manifest_path.exists()
    assert list((tmp_path / "store").glob("**/*")) == []


def test_main_uploads_only_successfully_converted_pdfs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_dir = tmp_path / "papers"
    output_dir = tmp_path / "output"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    success_pdf = pdf_dir / "y2025p1q7.pdf"
    failed_pdf = pdf_dir / "y2025p1q8.pdf"
    success_pdf.write_bytes(b"pdf-bytes")
    failed_pdf.write_bytes(b"pdf-bytes")
    info_mock = Mock()
    exception_mock = Mock()

    def fake_run_mineru_batch(
        pdf_paths: list[Path],
        output_dir: Path,
        method: str = "auto",
        backend: str = "hybrid-auto-engine",
        lang: str = "en",
    ) -> bool:
        del method, backend, lang
        for path in pdf_paths:
            if path.stem == success_pdf.stem:
                _write_mineru_outputs(output_dir, stem=path.stem)
        return True

    monkeypatch.setattr(convert_papers, "run_mineru_batch", fake_run_mineru_batch)
    monkeypatch.setattr(convert_papers.logger, "info", info_mock)
    monkeypatch.setattr(convert_papers.logger, "exception", exception_mock)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", "dev-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        ["convert_papers.py", str(pdf_dir), str(output_dir)],
    )

    convert_papers.main()

    assert not any(
        call.args[:2]
        == ("Failed to upload converted artifacts for %s", failed_pdf.name)
        for call in exception_mock.call_args_list
    )
    assert any(
        call.args == ("Uploaded artifacts for %d PDFs", 1)
        for call in info_mock.call_args_list
    )
    assert any(
        call.args
        == (
            "Done: %d converted, %d skipped, %d failed, %d uploaded (of %d total)",
            1,
            0,
            1,
            1,
            2,
        )
        for call in info_mock.call_args_list
    )


def test_main_strict_upload_uploads_converted_pdf_missing_manifest_without_mineru(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_dir = tmp_path / "papers"
    output_dir = tmp_path / "output"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / "y2025p1q7.pdf"
    pdf_path.write_bytes(b"pdf-bytes")
    _write_mineru_outputs(output_dir, stem=pdf_path.stem)
    run_mineru_mock = Mock()

    monkeypatch.setattr(convert_papers, "run_mineru_batch", run_mineru_mock)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", "dev-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        ["convert_papers.py", str(pdf_dir), str(output_dir), "--strict-upload"],
    )

    convert_papers.main()

    run_mineru_mock.assert_not_called()
    manifest_path = (
        output_dir / "y2025p1q7" / "hybrid_auto" / "y2025p1q7_artifact_manifest.json"
    )
    assert manifest_path.is_file()
    manifest = ArtifactManifest.from_json(manifest_path.read_text(encoding="utf-8"))
    assert manifest.paper_id == "y2025p1q7"


@pytest.mark.parametrize(
    ("manifest_kwargs", "expected_warning_fragment"),
    [
        (
            {"conversion_run_id": "run-old-y2025p1q7"},
            "conversion_run_id",
        ),
        (
            {
                "content_list_key": ("artifacts/mineru/run-other/content_list.json"),
            },
            "content_list",
        ),
    ],
)
def test_main_strict_upload_reuploads_wrong_run_or_namespace_without_mineru(
    tmp_path: Path,
    monkeypatch,
    manifest_kwargs: dict[str, str],
    expected_warning_fragment: str,
) -> None:
    pdf_dir = tmp_path / "papers"
    output_dir = tmp_path / "output"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / "y2025p1q7.pdf"
    pdf_path.write_bytes(b"pdf-bytes")
    _write_mineru_outputs(output_dir, stem=pdf_path.stem)
    manifest_path = _write_manifest(
        output_dir,
        stem=pdf_path.stem,
        paper_id=pdf_path.stem,
        **manifest_kwargs,
    )
    run_mineru_mock = Mock()
    warning_mock = Mock()

    monkeypatch.setattr(convert_papers, "run_mineru_batch", run_mineru_mock)
    monkeypatch.setattr(convert_papers.logger, "warning", warning_mock)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", "dev-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        ["convert_papers.py", str(pdf_dir), str(output_dir), "--strict-upload"],
    )

    convert_papers.main()

    run_mineru_mock.assert_not_called()
    manifest = ArtifactManifest.from_json(manifest_path.read_text(encoding="utf-8"))
    assert manifest.paper_id == pdf_path.stem
    assert manifest.conversion_run_id == conversion_run_id_from_stem(pdf_path.stem)
    assert any(
        artifact.key
        == mineru_artifact_key(
            conversion_run_id=manifest.conversion_run_id,
            kind="content_list",
            filename="",
        )
        for artifact in manifest.artifacts
    )
    assert any(
        expected_warning_fragment in str(call.args)
        for call in warning_mock.call_args_list
    )


def test_main_strict_upload_reuploads_incomplete_manifest_without_mineru(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_dir = tmp_path / "papers"
    output_dir = tmp_path / "output"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / "y2025p1q7.pdf"
    pdf_path.write_bytes(b"pdf-bytes")
    _write_mineru_outputs(output_dir, stem=pdf_path.stem)
    manifest_path = _write_manifest(
        output_dir,
        stem=pdf_path.stem,
        paper_id=pdf_path.stem,
        include_all_outputs=False,
    )
    run_mineru_mock = Mock()

    monkeypatch.setattr(convert_papers, "run_mineru_batch", run_mineru_mock)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", "dev-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        ["convert_papers.py", str(pdf_dir), str(output_dir), "--strict-upload"],
    )

    convert_papers.main()

    run_mineru_mock.assert_not_called()
    manifest = ArtifactManifest.from_json(manifest_path.read_text(encoding="utf-8"))
    assert {artifact.key for artifact in manifest.artifacts} == (
        _expected_mineru_artifact_keys(pdf_path.stem)
    )


def test_main_strict_upload_validates_storage_with_nothing_to_upload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_dir = tmp_path / "papers"
    output_dir = tmp_path / "output"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / "y2025p1q7.pdf"
    pdf_path.write_bytes(b"pdf-bytes")
    _write_mineru_outputs(output_dir, stem=pdf_path.stem)
    _write_manifest(
        output_dir,
        stem=pdf_path.stem,
        paper_id=pdf_path.stem,
    )
    run_mineru_mock = Mock()

    monkeypatch.setattr(convert_papers, "run_mineru_batch", run_mineru_mock)
    monkeypatch.delenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", raising=False)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "store"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["convert_papers.py", str(pdf_dir), str(output_dir), "--strict-upload"],
    )

    with pytest.raises(SystemExit) as exc_info:
        convert_papers.main()

    assert exc_info.value.code == 1
    run_mineru_mock.assert_not_called()


def test_main_strict_upload_rejects_duplicate_content_lists_despite_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_dir = tmp_path / "papers"
    output_dir = tmp_path / "output"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / "y2025p1q7.pdf"
    pdf_path.write_bytes(b"pdf-bytes")
    _write_mineru_outputs(output_dir, stem=pdf_path.stem)
    _write_manifest(output_dir, stem=pdf_path.stem, paper_id=pdf_path.stem)

    duplicate_dir = output_dir / pdf_path.stem / "zz_duplicate"
    duplicate_dir.mkdir(parents=True, exist_ok=True)
    (duplicate_dir / f"{pdf_path.stem}_content_list.json").write_text(
        "[]",
        encoding="utf-8",
    )

    run_mineru_mock = Mock()
    exception_mock = Mock()

    monkeypatch.setattr(convert_papers, "run_mineru_batch", run_mineru_mock)
    monkeypatch.setattr(convert_papers.logger, "exception", exception_mock)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", "dev-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        ["convert_papers.py", str(pdf_dir), str(output_dir), "--strict-upload"],
    )

    with pytest.raises(SystemExit) as exc_info:
        convert_papers.main()

    assert exc_info.value.code == 1
    run_mineru_mock.assert_not_called()
    assert any(
        call.args == ("Failed to upload converted artifacts for %s", pdf_path.name)
        for call in exception_mock.call_args_list
    )


def test_main_strict_upload_exits_on_duplicate_conversion_run_ids(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_dir = tmp_path / "papers"
    output_dir = tmp_path / "output"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    first_pdf = pdf_dir / "paper_a.pdf"
    duplicate_pdf = pdf_dir / "paper-a.pdf"
    first_pdf.write_bytes(b"pdf-a")
    duplicate_pdf.write_bytes(b"pdf-b")
    run_mineru_mock = Mock()
    error_mock = Mock()

    monkeypatch.setattr(convert_papers, "run_mineru_batch", run_mineru_mock)
    monkeypatch.setattr(convert_papers.logger, "error", error_mock)
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", "dev-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        ["convert_papers.py", str(pdf_dir), str(output_dir), "--strict-upload"],
    )

    with pytest.raises(SystemExit) as exc_info:
        convert_papers.main()

    assert exc_info.value.code == 1
    run_mineru_mock.assert_not_called()
    assert error_mock.call_count == 1
    assert error_mock.call_args.args[0].startswith(
        "Duplicate conversion run ID for strict upload"
    )
    assert error_mock.call_args.args[1] == "run-paper-a"
    assert set(error_mock.call_args.args[2:]) == {first_pdf, duplicate_pdf}
