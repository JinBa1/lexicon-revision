from __future__ import annotations

from pathlib import Path

import pytest
from src.jobs.models import IngestJobMessage
from src.worker import handler as handler_module
from src.worker.handler import IngestJobHandler


class FakeStorage:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self._blobs = blobs
        self.requested: list[str] = []

    def get_bytes(self, key: str) -> bytes:
        self.requested.append(key)
        return self._blobs[key]


def _message() -> IngestJobMessage:
    return IngestJobMessage(
        collection="cam-cs-tripos",
        paper_object_key="source-pdfs/cam-cs-tripos/y2023p7q8.pdf",
        parser="cambridge",
        university="cam",
    )


def test_handle_converts_then_indexes(monkeypatch: pytest.MonkeyPatch) -> None:
    message = _message()
    storage = FakeStorage({message.paper_object_key: b"%PDF-1.4 stub"})
    calls: dict = {}

    def fake_convert(*, pdf_path: Path, output_dir: Path, storage, **kwargs):
        calls["convert"] = {"pdf_name": pdf_path.name, "output_dir": output_dir}
        assert pdf_path.read_bytes() == b"%PDF-1.4 stub"
        return object()

    def fake_index(**kwargs):
        calls["index"] = kwargs

    monkeypatch.setattr(handler_module, "convert_single_pdf", fake_convert)
    monkeypatch.setattr(handler_module, "index_collection_postgres", fake_index)

    handler = IngestJobHandler(
        storage=storage,
        engine=object(),
        embedding_model=object(),
        embedding_dimension=1024,
    )
    handler.handle(message)

    # PDF staged under its original filename so the conversion run id
    # derived from the stem stays stable
    assert calls["convert"]["pdf_name"] == "y2023p7q8.pdf"
    assert calls["index"]["collection_name"] == "cam-cs-tripos"
    assert calls["index"]["parser_name"] == "cambridge"
    assert calls["index"]["university"] == "cam"
    assert calls["index"]["mineru_output_dir"] == str(calls["convert"]["output_dir"])
    assert storage.requested == [message.paper_object_key]


def test_handle_propagates_conversion_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _message()
    storage = FakeStorage({message.paper_object_key: b"%PDF-1.4 stub"})

    def boom(**kwargs):
        raise RuntimeError("mineru exploded")

    monkeypatch.setattr(handler_module, "convert_single_pdf", boom)
    handler = IngestJobHandler(
        storage=storage,
        engine=object(),
        embedding_model=object(),
        embedding_dimension=1024,
    )
    with pytest.raises(RuntimeError, match="mineru exploded"):
        handler.handle(message)


def test_handle_rejects_object_key_without_pdf_name() -> None:
    handler = IngestJobHandler(
        storage=FakeStorage({}),
        engine=object(),
        embedding_model=object(),
        embedding_dimension=1024,
    )
    bad = _message().model_copy(update={"paper_object_key": "weird/"})
    with pytest.raises(ValueError, match="paper_object_key"):
        handler.handle(bad)
