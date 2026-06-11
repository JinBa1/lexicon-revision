from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from src.jobs.models import IngestJobMessage
from src.jobs.queue import IngestJobDecodeError, ReceivedJob

RECEIVE_WAIT_TIME_SECONDS = 20


class SqsIngestJobQueue:
    """SQS-backed ingest queue. Standard queue + DLQ redrive (Terraform)."""

    def __init__(
        self,
        *,
        queue_url: str,
        client: Any | None = None,
        region_name: str | None = None,
    ) -> None:
        if client is None:
            import boto3

            client = boto3.client("sqs", region_name=region_name)
        self._client = client
        self._queue_url = queue_url

    def enqueue(self, message: IngestJobMessage) -> None:
        self._client.send_message(
            QueueUrl=self._queue_url,
            MessageBody=message.model_dump_json(),
        )

    def receive(self) -> ReceivedJob | None:
        response = self._client.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=RECEIVE_WAIT_TIME_SECONDS,
        )
        messages = response.get("Messages", [])
        if not messages:
            return None
        raw = messages[0]
        receipt = raw["ReceiptHandle"]
        try:
            message = IngestJobMessage.model_validate_json(raw["Body"])
        except ValidationError as exc:
            raise IngestJobDecodeError(receipt, str(exc)) from exc
        return ReceivedJob(message=message, receipt=receipt)

    def delete(self, receipt: str) -> None:
        self._client.delete_message(
            QueueUrl=self._queue_url,
            ReceiptHandle=receipt,
        )

    def extend_visibility(self, receipt: str, *, seconds: int) -> None:
        self._client.change_message_visibility(
            QueueUrl=self._queue_url,
            ReceiptHandle=receipt,
            VisibilityTimeout=seconds,
        )
