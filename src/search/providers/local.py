from __future__ import annotations

from typing import Any

from src.search.providers.base import EmbeddingResult, RerankResult


def _to_float_list(value: Any) -> list[float]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(item) for item in value]


def _to_float_rows(value: Any) -> list[list[float]]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [_to_float_list(row) for row in value]


class LocalSentenceTransformerEmbedder:
    def __init__(self, *, model: object, model_id: str) -> None:
        self.model = model
        self.model_id = model_id

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], model_id=self.model_id)
        vectors = _to_float_rows(self.model.encode(texts, show_progress_bar=False))
        return EmbeddingResult(vectors=vectors, model_id=self.model_id)

    def embed_query(self, text: str) -> EmbeddingResult:
        vector = _to_float_list(self.model.encode(text))
        return EmbeddingResult(vectors=[vector], model_id=self.model_id)


class LocalCrossEncoderReranker:
    def __init__(self, *, model: object, model_id: str) -> None:
        self.model = model
        self.model_id = model_id

    def rerank(self, query: str, documents: list[str]) -> RerankResult:
        if not documents:
            return RerankResult(scores=[], model_id=self.model_id)
        pairs = [(query, doc) for doc in documents]
        scores = _to_float_list(self.model.predict(pairs))
        return RerankResult(scores=scores, model_id=self.model_id)
