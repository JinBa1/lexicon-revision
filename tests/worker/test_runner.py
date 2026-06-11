from __future__ import annotations

from src.jobs.models import IngestJobMessage
from src.jobs.queue import InMemoryIngestJobQueue
from src.worker.runner import run_worker


def _message(key: str) -> IngestJobMessage:
    return IngestJobMessage(
        collection="cam-cs-tripos",
        paper_object_key=key,
        parser="cambridge",
        university="cam",
    )


class RecordingHandler:
    def __init__(self, fail_keys: set[str] | None = None) -> None:
        self.handled: list[str] = []
        self._fail_keys = fail_keys or set()

    def handle(self, message: IngestJobMessage) -> None:
        if message.paper_object_key in self._fail_keys:
            raise RuntimeError(f"boom: {message.paper_object_key}")
        self.handled.append(message.paper_object_key)


def test_successful_job_is_deleted() -> None:
    queue = InMemoryIngestJobQueue()
    queue.enqueue(_message("source-pdfs/c/a.pdf"))
    handler = RecordingHandler()

    run_worker(queue=queue, handler=handler, max_iterations=2)

    assert handler.handled == ["source-pdfs/c/a.pdf"]
    assert queue.in_flight_count() == 0
    assert queue.receive() is None


def test_failed_job_is_not_deleted_so_it_redelivers() -> None:
    queue = InMemoryIngestJobQueue()
    queue.enqueue(_message("source-pdfs/c/bad.pdf"))
    handler = RecordingHandler(fail_keys={"source-pdfs/c/bad.pdf"})

    run_worker(queue=queue, handler=handler, max_iterations=1)

    assert handler.handled == []
    assert queue.in_flight_count() == 1  # broker redelivers after timeout

    queue.requeue_in_flight()
    redelivered = queue.receive()
    assert redelivered is not None
    assert redelivered.message.paper_object_key == "source-pdfs/c/bad.pdf"


def test_decode_error_does_not_crash_loop() -> None:
    class PoisonQueue(InMemoryIngestJobQueue):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def receive(self):
            self.calls += 1
            if self.calls == 1:
                from src.jobs.queue import IngestJobDecodeError

                raise IngestJobDecodeError("rh-poison", "bad body")
            return super().receive()

    queue = PoisonQueue()
    queue.enqueue(_message("source-pdfs/c/good.pdf"))
    handler = RecordingHandler()

    run_worker(queue=queue, handler=handler, max_iterations=2)

    assert handler.handled == ["source-pdfs/c/good.pdf"]


def test_stop_event_exits_loop() -> None:
    import threading

    queue = InMemoryIngestJobQueue()
    handler = RecordingHandler()
    stop = threading.Event()
    stop.set()

    run_worker(queue=queue, handler=handler, stop_event=stop)  # returns at once

    assert handler.handled == []
