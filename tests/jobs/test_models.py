from __future__ import annotations

import pytest
from pydantic import ValidationError
from src.jobs.models import IngestJobMessage


def test_message_round_trip() -> None:
    message = IngestJobMessage(
        collection="cam-cs-tripos",
        paper_object_key="source-pdfs/cam-cs-tripos/y2023p7q8.pdf",
        parser="cambridge",
        university="cam",
    )
    decoded = IngestJobMessage.model_validate_json(message.model_dump_json())
    assert decoded == message
    assert decoded.schema_version == "ingest_job_v1"
    assert decoded.job_id  # uuid4 default populated


def test_message_rejects_unknown_parser() -> None:
    with pytest.raises(ValidationError):
        IngestJobMessage(
            collection="cam-cs-tripos",
            paper_object_key="source-pdfs/cam-cs-tripos/y2023p7q8.pdf",
            parser="mit",
            university="cam",
        )


def test_message_rejects_empty_object_key() -> None:
    with pytest.raises(ValidationError):
        IngestJobMessage(
            collection="cam-cs-tripos",
            paper_object_key="",
            parser="cambridge",
            university="cam",
        )


def test_two_messages_get_distinct_job_ids() -> None:
    kwargs = dict(
        collection="cam-cs-tripos",
        paper_object_key="source-pdfs/cam-cs-tripos/y2023p7q8.pdf",
        parser="cambridge",
        university="cam",
    )
    assert IngestJobMessage(**kwargs).job_id != IngestJobMessage(**kwargs).job_id


def test_message_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        IngestJobMessage(
            collection="cam-cs-tripos",
            paper_object_key="source-pdfs/cam-cs-tripos/y2023p7q8.pdf",
            parser="cambridge",
            university="cam",
            evil="x",
        )
