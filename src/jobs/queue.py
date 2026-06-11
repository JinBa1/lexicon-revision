from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass
from typing import Protocol

from src.jobs.models import IngestJobMessage


class IngestQueueError(Exception):
    """Base error for ingest queue operations."""


class IngestJobDecodeError(IngestQueueError):
    """Received message body is not a valid IngestJobMessage.

    Carries the receipt so the caller can decide redelivery (do not delete:
    after maxReceiveCount the broker moves the poison message to the DLQ).
    """

    def __init__(self, receipt: str, detail: str) -> None:
        super().__init__(detail)
        self.receipt = receipt


@dataclass(frozen=True)
class ReceivedJob:
    message: IngestJobMessage
    receipt: str


class IngestJobQueue(Protocol):
    def enqueue(self, message: IngestJobMessage) -> None: ...

    def receive(self) -> ReceivedJob | None: ...

    def delete(self, receipt: str) -> None: ...

    def extend_visibility(self, receipt: str, *, seconds: int) -> None: ...


class InMemoryIngestJobQueue:
    """Test/dev queue. Single-consumer semantics, explicit redelivery."""

    def __init__(self) -> None:
        self._pending: deque[IngestJobMessage] = deque()
        self._in_flight: dict[str, IngestJobMessage] = {}

    def enqueue(self, message: IngestJobMessage) -> None:
        self._pending.append(message)

    def receive(self) -> ReceivedJob | None:
        if not self._pending:
            return None
        message = self._pending.popleft()
        receipt = str(uuid.uuid4())
        self._in_flight[receipt] = message
        return ReceivedJob(message=message, receipt=receipt)

    def delete(self, receipt: str) -> None:
        self._in_flight.pop(receipt, None)

    def extend_visibility(self, receipt: str, *, seconds: int) -> None:
        return None

    def requeue_in_flight(self) -> None:
        """Test helper: simulate visibility-timeout expiry for all in-flight."""
        for message in self._in_flight.values():
            self._pending.append(message)
        self._in_flight.clear()

    def in_flight_count(self) -> int:
        return len(self._in_flight)
