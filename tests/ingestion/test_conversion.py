from __future__ import annotations

from pathlib import Path

import pytest
from src.ingestion import conversion
from src.ingestion.conversion import ConversionFailedError, convert_single_pdf


class _ManifestStub:
    paper_id = "y2023p7q8"


def test_convert_single_pdf_runs_mineru_and_uploads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "y2023p7q8.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 stub")
    output_dir = tmp_path / "out"
    calls: dict = {}

    def fake_run(pdf_paths, out, method, backend, lang):
        calls["mineru"] = {
            "pdfs": list(pdf_paths),
            "out": out,
            "backend": backend,
        }
        return True

    def fake_upload(*, pdf_paths, output_dir, storage, mineru_version, strict):
        calls["upload"] = {"pdfs": list(pdf_paths), "strict": strict}
        return [_ManifestStub()]

    monkeypatch.setattr(conversion, "run_mineru_batch", fake_run)
    monkeypatch.setattr(conversion, "upload_batch_artifacts", fake_upload)

    manifest = convert_single_pdf(
        pdf_path=pdf_path,
        output_dir=output_dir,
        storage=object(),
        backend="pipeline",
    )

    assert calls["mineru"]["pdfs"] == [pdf_path]
    assert calls["mineru"]["backend"] == "pipeline"
    assert calls["upload"]["strict"] is True
    assert manifest.paper_id == "y2023p7q8"


def test_convert_single_pdf_raises_on_mineru_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "y2023p7q8.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 stub")
    monkeypatch.setattr(conversion, "run_mineru_batch", lambda *args, **kwargs: False)

    with pytest.raises(ConversionFailedError):
        convert_single_pdf(
            pdf_path=pdf_path,
            output_dir=tmp_path / "out",
            storage=object(),
        )


def test_convert_single_pdf_raises_when_upload_yields_no_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "y2023p7q8.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 stub")
    monkeypatch.setattr(conversion, "run_mineru_batch", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        conversion,
        "upload_batch_artifacts",
        lambda **kwargs: [],
    )

    with pytest.raises(ConversionFailedError, match="no manifest"):
        convert_single_pdf(
            pdf_path=pdf_path,
            output_dir=tmp_path / "out",
            storage=object(),
        )
