from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

from src.jobs.queue import IngestJobQueue, InMemoryIngestJobQueue
from src.jobs.sqs import SqsIngestJobQueue

IngestQueueProvider = Literal["none", "memory", "sqs"]


@dataclass(frozen=True)
class IngestQueueSettings:
    provider: IngestQueueProvider
    queue_url: str | None
    region_name: str | None = None


def load_ingest_queue_settings() -> IngestQueueSettings:
    provider_raw = os.environ.get("INGEST_QUEUE_PROVIDER", "none").lower()
    if provider_raw not in ("none", "memory", "sqs"):
        raise ValueError(f"Invalid INGEST_QUEUE_PROVIDER: {provider_raw}")
    provider: IngestQueueProvider = provider_raw

    queue_url = os.environ.get("INGEST_QUEUE_URL") or None
    if provider == "sqs" and not queue_url:
        raise ValueError("INGEST_QUEUE_PROVIDER=sqs requires INGEST_QUEUE_URL")

    return IngestQueueSettings(
        provider=provider,
        queue_url=queue_url,
        region_name=os.environ.get("AWS_REGION") or None,
    )


def build_ingest_job_queue(
    settings: IngestQueueSettings,
    *,
    sqs_client: Any | None = None,
) -> IngestJobQueue | None:
    if settings.provider == "none":
        return None
    if settings.provider == "memory":
        return InMemoryIngestJobQueue()
    assert settings.queue_url is not None  # enforced at load time
    return SqsIngestJobQueue(
        queue_url=settings.queue_url,
        client=sqs_client,
        region_name=settings.region_name,
    )
