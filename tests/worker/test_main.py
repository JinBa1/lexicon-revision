from __future__ import annotations

import pytest
from src.worker.__main__ import main


def test_memory_queue_rejected_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("INGEST_QUEUE_PROVIDER", "memory")

    with pytest.raises(SystemExit, match="memory ingest queue"):
        main()


def test_none_provider_exits_with_guard_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("INGEST_QUEUE_PROVIDER", "none")

    with pytest.raises(SystemExit, match="INGEST_QUEUE_PROVIDER=sqs"):
        main()


def test_local_embedding_rejected_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("INGEST_QUEUE_PROVIDER", "sqs")
    monkeypatch.setenv(
        "INGEST_QUEUE_URL",
        "https://sqs.eu-west-2.amazonaws.com/123456789012/lexicon-ingest",
    )
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")

    with pytest.raises(SystemExit, match="local embedding provider"):
        main()
