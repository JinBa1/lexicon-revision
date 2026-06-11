from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

INGEST_JOB_SCHEMA_VERSION = "ingest_job_v1"

ParserName = Literal["cambridge", "uoe"]


def _new_job_id() -> str:
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IngestJobMessage(BaseModel):
    """One per-paper ingestion job. Carries object keys, never local paths."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ingest_job_v1"] = INGEST_JOB_SCHEMA_VERSION
    job_id: str = Field(default_factory=_new_job_id)
    collection: str = Field(min_length=1)
    paper_object_key: str = Field(min_length=1)
    parser: ParserName
    university: str = Field(min_length=1)
    enqueued_at: datetime = Field(default_factory=_utc_now)


class IngestSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: str = Field(min_length=1)
    paper_object_key: str = Field(min_length=1)
    parser: ParserName
    university: str = Field(min_length=1, default="cam")


class IngestSubmissionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
