from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from src.runtime.telemetry import ProviderCallTelemetry, TokenUsage
from src.runtime.usage_logs import (
    PgRequestUsageLogRepository,
    RequestUsageLogRecord,
)


def test_request_usage_log_record_serializes_optional_provider_sections() -> None:
    record = RequestUsageLogRecord(
        request_id="req-1",
        endpoint="study",
        collection_name="cam-fixture",
        app_user_id="user-1",
        outcome="ok",
        latency_ms=321,
        embedding=None,
        rerank=None,
        planning=ProviderCallTelemetry(
            provider="openai_compatible",
            model="planner-model",
            latency_ms=20,
            usage=TokenUsage(input_tokens=10, output_tokens=2, total_tokens=12),
        ),
        generation=None,
        detail={"status": "ok"},
    )

    payload = record.to_insert_dict()

    assert payload["request_id"] == "req-1"
    assert payload["endpoint"] == "study"
    assert payload["planning"] == {
        "provider": "openai_compatible",
        "model": "planner-model",
        "latency_ms": 20,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 2,
            "total_tokens": 12,
        },
    }
    assert payload["embedding"] is None
    assert payload["detail"] == {"status": "ok"}


@pytest.mark.integration
def test_pg_request_usage_log_repository_inserts_serialized_record() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for usage-log integration tests")

    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    engine = create_engine(database_url, future=True)
    repository = PgRequestUsageLogRepository(engine=engine)
    record = RequestUsageLogRecord(
        request_id="req-runtime-usage-log",
        endpoint="search",
        collection_name="cam-fixture",
        app_user_id=None,
        outcome="provider_error",
        latency_ms=98,
        embedding=ProviderCallTelemetry(
            provider="voyage",
            model="voyage-3",
            latency_ms=12,
        ),
        rerank=None,
        planning=None,
        generation=None,
        detail={"error_type": "timeout"},
    )

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    delete from request_usage_logs
                    where request_id = :request_id
                    """
                ),
                {"request_id": record.request_id},
            )

        repository.insert(record)

        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    select
                        request_id,
                        endpoint,
                        collection_name,
                        app_user_id,
                        outcome,
                        latency_ms,
                        embedding,
                        detail
                    from request_usage_logs
                    where request_id = :request_id
                    """
                ),
                {"request_id": record.request_id},
            ).first()

        assert row is not None
        assert row.request_id == record.request_id
        assert row.endpoint == "search"
        assert row.collection_name == "cam-fixture"
        assert row.app_user_id is None
        assert row.outcome == "provider_error"
        assert row.latency_ms == 98
        assert row.embedding == {
            "provider": "voyage",
            "model": "voyage-3",
            "latency_ms": 12,
            "usage": None,
        }
        assert row.detail == {"error_type": "timeout"}

        with pytest.raises(IntegrityError):
            repository.insert(record)
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    delete from request_usage_logs
                    where request_id = :request_id
                    """
                ),
                {"request_id": record.request_id},
            )
        engine.dispose()
