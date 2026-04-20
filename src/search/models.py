from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from src.metadata_schema.models import FilterCondition


class MediaRefResponse(BaseModel):
    media_id: str
    kind: Literal["image", "table"]
    object_key: str | None
    access_url: str | None
    relation: Literal["direct", "inherited_shared", "visible_from_child"]


class SearchResult(BaseModel):
    chunk_id: str
    chunk_level: Literal["question", "sub_question"]
    parent_chunk_id: str | None
    sub_question_label: str | None
    text: str
    score: float
    metadata: dict[str, Any]
    media: list[MediaRefResponse]


class SearchResponse(BaseModel):
    query: str
    collection: str
    results: list[SearchResult]
    total: int


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    collection: str = Field(min_length=1)
    filters: list[FilterCondition] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=100)
    rerank: bool = True
