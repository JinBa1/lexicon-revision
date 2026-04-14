from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class MediaRefResponse(BaseModel):
    media_id: str
    kind: Literal["image", "table"]
    file_path: str | None
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
