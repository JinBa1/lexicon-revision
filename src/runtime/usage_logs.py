from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from sqlalchemy import Engine, insert
from src.db.schema import request_usage_logs
from src.runtime.telemetry import ProviderCallTelemetry

Endpoint = Literal[
    "search",
    "study",
    "collections",
    "supported_universities",
    "chunk_detail",
]


@dataclass(frozen=True)
class RequestUsageLogRecord:
    request_id: str
    endpoint: Endpoint
    collection_name: str
    app_user_id: str | None
    outcome: str
    latency_ms: int
    embedding: ProviderCallTelemetry | None
    rerank: ProviderCallTelemetry | None
    planning: ProviderCallTelemetry | None
    generation: ProviderCallTelemetry | None
    detail: dict[str, Any]

    def to_insert_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "endpoint": self.endpoint,
            "collection_name": self.collection_name,
            "app_user_id": self.app_user_id,
            "outcome": self.outcome,
            "latency_ms": self.latency_ms,
            "embedding": _telemetry_dict(self.embedding),
            "rerank": _telemetry_dict(self.rerank),
            "planning": _telemetry_dict(self.planning),
            "generation": _telemetry_dict(self.generation),
            "detail": self.detail,
        }


class PgRequestUsageLogRepository:
    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def insert(self, record: RequestUsageLogRecord) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                insert(request_usage_logs).values(record.to_insert_dict())
            )


def _telemetry_dict(
    telemetry: ProviderCallTelemetry | None,
) -> dict[str, Any] | None:
    if telemetry is None:
        return None
    return asdict(telemetry)
