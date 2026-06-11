from __future__ import annotations

import json

import pytest
from src.jobs.models import IngestJobMessage
from src.jobs.queue import IngestJobDecodeError
from src.jobs.sqs import SqsIngestJobQueue

QUEUE_URL = "https://sqs.eu-west-2.amazonaws.com/123456789012/lexicon-ingest"


class FakeSqsClient:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.deleted: list[dict] = []
        self.visibility_changes: list[dict] = []
        self.receive_payload: dict = {}

    def send_message(self, *, QueueUrl: str, MessageBody: str) -> dict:
        self.sent.append({"QueueUrl": QueueUrl, "MessageBody": MessageBody})
        return {"MessageId": "m-1"}

    def receive_message(self, **kwargs) -> dict:
        self.receive_kwargs = kwargs
        return self.receive_payload

    def delete_message(self, *, QueueUrl: str, ReceiptHandle: str) -> dict:
        self.deleted.append({"QueueUrl": QueueUrl, "ReceiptHandle": ReceiptHandle})
        return {}

    def change_message_visibility(
        self, *, QueueUrl: str, ReceiptHandle: str, VisibilityTimeout: int
    ) -> dict:
        self.visibility_changes.append(
            {
                "QueueUrl": QueueUrl,
                "ReceiptHandle": ReceiptHandle,
                "VisibilityTimeout": VisibilityTimeout,
            }
        )
        return {}


def _message() -> IngestJobMessage:
    return IngestJobMessage(
        collection="cam-cs-tripos",
        paper_object_key="source-pdfs/cam-cs-tripos/y2023p7q8.pdf",
        parser="cambridge",
        university="cam",
    )


def test_enqueue_sends_json_body() -> None:
    client = FakeSqsClient()
    queue = SqsIngestJobQueue(queue_url=QUEUE_URL, client=client)
    message = _message()

    queue.enqueue(message)

    assert client.sent[0]["QueueUrl"] == QUEUE_URL
    body = json.loads(client.sent[0]["MessageBody"])
    assert body["job_id"] == message.job_id
    assert body["schema_version"] == "ingest_job_v1"


def test_receive_parses_message_and_uses_long_polling() -> None:
    client = FakeSqsClient()
    message = _message()
    client.receive_payload = {
        "Messages": [{"Body": message.model_dump_json(), "ReceiptHandle": "rh-1"}]
    }
    queue = SqsIngestJobQueue(queue_url=QUEUE_URL, client=client)

    received = queue.receive()

    assert received is not None
    assert received.message == message
    assert received.receipt == "rh-1"
    assert client.receive_kwargs["WaitTimeSeconds"] == 20
    assert client.receive_kwargs["MaxNumberOfMessages"] == 1


def test_receive_empty_returns_none() -> None:
    client = FakeSqsClient()
    client.receive_payload = {}
    queue = SqsIngestJobQueue(queue_url=QUEUE_URL, client=client)
    assert queue.receive() is None


def test_receive_malformed_body_raises_decode_error_with_receipt() -> None:
    client = FakeSqsClient()
    client.receive_payload = {
        "Messages": [{"Body": "{not json", "ReceiptHandle": "rh-poison"}]
    }
    queue = SqsIngestJobQueue(queue_url=QUEUE_URL, client=client)

    with pytest.raises(IngestJobDecodeError) as excinfo:
        queue.receive()
    assert excinfo.value.receipt == "rh-poison"
    assert client.deleted == []  # poison stays for redrive -> DLQ


def test_delete_and_extend_visibility_pass_through() -> None:
    client = FakeSqsClient()
    queue = SqsIngestJobQueue(queue_url=QUEUE_URL, client=client)

    queue.delete("rh-1")
    queue.extend_visibility("rh-1", seconds=900)

    assert client.deleted[0]["ReceiptHandle"] == "rh-1"
    assert client.visibility_changes[0]["VisibilityTimeout"] == 900
