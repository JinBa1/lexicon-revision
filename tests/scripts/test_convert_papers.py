from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock

import scripts.convert_papers as convert_papers
from src.storage.local import LocalObjectStorage
from src.storage.manifest import ArtifactManifest

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET = b"convert-papers-secret"

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
    exception_mock.assert_called_once_with(
        "Storage upload unavailable; leaving converted outputs in place"
    )


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
