from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.search.models import SearchResponse


@runtime_checkable
class SearchBackend(Protocol):
    @property
    def embedding_model_id(self) -> str | None: ...

    @property
    def rerank_model_id(self) -> str | None: ...

    def search(
        self,
        query: str,
        collection: str = ...,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
        rerank: bool = True,
    ) -> SearchResponse: ...
