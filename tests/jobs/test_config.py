from __future__ import annotations

import pytest
from src.jobs.config import (
    build_ingest_job_queue,
    load_ingest_queue_settings,
)
from src.jobs.queue import InMemoryIngestJobQueue
from src.jobs.sqs import SqsIngestJobQueue


def test_defaults_to_none_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INGEST_QUEUE_PROVIDER", raising=False)
    monkeypatch.delenv("INGEST_QUEUE_URL", raising=False)
    settings = load_ingest_queue_settings()
    assert settings.provider == "none"
    assert build_ingest_job_queue(settings) is None


def test_memory_provider_builds_in_memory_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INGEST_QUEUE_PROVIDER", "memory")
    settings = load_ingest_queue_settings()
    assert isinstance(build_ingest_job_queue(settings), InMemoryIngestJobQueue)


def test_sqs_provider_requires_queue_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INGEST_QUEUE_PROVIDER", "sqs")
    monkeypatch.delenv("INGEST_QUEUE_URL", raising=False)
    with pytest.raises(ValueError, match="INGEST_QUEUE_URL"):
        load_ingest_queue_settings()


def test_sqs_provider_builds_sqs_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INGEST_QUEUE_PROVIDER", "sqs")
    monkeypatch.setenv(
        "INGEST_QUEUE_URL",
        "https://sqs.eu-west-2.amazonaws.com/123456789012/lexicon-ingest",
    )
    settings = load_ingest_queue_settings()
    queue = build_ingest_job_queue(settings, sqs_client=object())
    assert isinstance(queue, SqsIngestJobQueue)


def test_invalid_provider_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INGEST_QUEUE_PROVIDER", "kafka")
    with pytest.raises(ValueError, match="INGEST_QUEUE_PROVIDER"):
        load_ingest_queue_settings()
