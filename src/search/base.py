from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.metadata_schema.models import CollectionMetadataSchema, FilterCondition
from src.search.models import SearchResponse


@runtime_checkable
class SearchBackend(Protocol):
    @property
    def embedding_model_id(self) -> str | None: ...

    @property
    def rerank_model_id(self) -> str | None: ...

    def get_collection_schema(
        self,
        collection: str,
    ) -> CollectionMetadataSchema: ...

    def search(
        self,
        query: str,
        collection: str = ...,
        filters: list[FilterCondition] | None = None,
        limit: int = 10,
        rerank: bool = True,
    ) -> SearchResponse: ...
