from __future__ import annotations

from src.jobs.models import IngestJobMessage
from src.jobs.queue import InMemoryIngestJobQueue


def _message(key: str = "source-pdfs/cam-cs-tripos/y2023p7q8.pdf") -> IngestJobMessage:
    return IngestJobMessage(
        collection="cam-cs-tripos",
        paper_object_key=key,
        parser="cambridge",
        university="cam",
    )


def test_enqueue_receive_delete() -> None:
    queue = InMemoryIngestJobQueue()
    sent = _message()
    queue.enqueue(sent)

    received = queue.receive()
    assert received is not None
    assert received.message == sent

    queue.delete(received.receipt)
    assert queue.receive() is None
    assert queue.in_flight_count() == 0


def test_receive_on_empty_queue_returns_none() -> None:
    assert InMemoryIngestJobQueue().receive() is None


def test_undeleted_message_can_be_requeued_for_redelivery() -> None:
    queue = InMemoryIngestJobQueue()
    queue.enqueue(_message())
    received = queue.receive()
    assert received is not None

    # simulate visibility timeout expiry
    queue.requeue_in_flight()

    redelivered = queue.receive()
    assert redelivered is not None
    assert redelivered.message == received.message


def test_receive_is_fifo_per_enqueue_order() -> None:
    queue = InMemoryIngestJobQueue()
    first = _message("source-pdfs/cam-cs-tripos/a.pdf")
    second = _message("source-pdfs/cam-cs-tripos/b.pdf")
    queue.enqueue(first)
    queue.enqueue(second)
    got1 = queue.receive()
    got2 = queue.receive()
    assert got1 is not None and got1.message == first
    assert got2 is not None and got2.message == second


def test_extend_visibility_is_a_noop_in_memory() -> None:
    queue = InMemoryIngestJobQueue()
    queue.enqueue(_message())
    received = queue.receive()
    assert received is not None
    queue.extend_visibility(received.receipt, seconds=600)  # must not raise
