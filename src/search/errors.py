from __future__ import annotations

DEFAULT_COLLECTION = "cam-cs-tripos-fixture"
DEFAULT_MEDIA_DIR = "./chroma_data"
RERANK_CANDIDATE_CAP = 50


class CollectionNotFoundError(Exception):
    def __init__(self, collection_name: str) -> None:
        self.collection_name = collection_name
        super().__init__(f"Collection '{collection_name}' not found")


class EmbeddingModelMismatchError(Exception):
    def __init__(self, *, collection: str, expected: str, actual: str) -> None:
        self.collection = collection
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Collection '{collection}' was indexed with embedding model "
            f"{actual!r} but the configured query embedder is {expected!r}"
        )


class InvalidMetadataFilterError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
