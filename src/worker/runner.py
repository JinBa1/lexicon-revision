from __future__ import annotations

import logging
import signal
import threading
from typing import Protocol

from src.jobs.models import IngestJobMessage
from src.jobs.queue import IngestJobDecodeError, IngestJobQueue

logger = logging.getLogger(__name__)


class JobHandler(Protocol):
    def handle(self, message: IngestJobMessage) -> None: ...


def run_worker(
    *,
    queue: IngestJobQueue,
    handler: JobHandler,
    stop_event: threading.Event | None = None,
    max_iterations: int | None = None,
    idle_wait_seconds: float = 1.0,
) -> None:
    """Poll the queue and process jobs until stopped.

    Success deletes the message. Failure leaves it for visibility-timeout
    redelivery; the broker's redrive policy moves repeat offenders to the
    DLQ. `max_iterations` bounds the loop for tests. `idle_wait_seconds`
    paces the loop on empty receives — SQS already long-polls, but queue
    implementations that return immediately (in-memory) would hot-spin
    without it.
    """
    stop = stop_event or threading.Event()
    iterations = 0
    while not stop.is_set():
        if max_iterations is not None and iterations >= max_iterations:
            return
        iterations += 1
        try:
            received = queue.receive()
        except IngestJobDecodeError as exc:
            logger.error(
                "poison ingest message; leaving for DLQ redrive",
                extra={"receipt": exc.receipt, "detail": str(exc)},
            )
            continue
        if received is None:
            stop.wait(idle_wait_seconds)
            continue
        try:
            handler.handle(received.message)
        except Exception:
            logger.exception(
                "ingest job failed; leaving for redelivery",
                extra={
                    "job_id": received.message.job_id,
                    "collection": received.message.collection,
                },
            )
            continue
        try:
            queue.delete(received.receipt)
        except Exception:
            logger.exception(
                "failed to delete completed job; redelivery will re-run it",
                extra={
                    "job_id": received.message.job_id,
                    "collection": received.message.collection,
                },
            )


def install_sigterm_handler(stop_event: threading.Event) -> None:
    def _handle(signum: int, frame: object) -> None:
        logger.info("received signal %s; stopping after current job", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
