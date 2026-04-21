from __future__ import annotations

import time
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
        started = time.perf_counter()
        if not texts:
            return EmbeddingResult(
                vectors=[],
                model_id=self.model_id,
                provider="local",
                latency_ms=0,
            )
        vectors = _to_float_rows(self.model.encode(texts, show_progress_bar=False))
        return EmbeddingResult(
            vectors=vectors,
            model_id=self.model_id,
            provider="local",
            latency_ms=_elapsed_ms(started),
        )

    def embed_query(self, text: str) -> EmbeddingResult:
        started = time.perf_counter()
        vector = _to_float_list(self.model.encode(text))
        return EmbeddingResult(
            vectors=[vector],
            model_id=self.model_id,
            provider="local",
            latency_ms=_elapsed_ms(started),
        )

    def health(self) -> str:
        return "ok"


class LocalCrossEncoderReranker:
    def __init__(self, *, model: object, model_id: str) -> None:
        self.model = model
        self.model_id = model_id

    def rerank(self, query: str, documents: list[str]) -> RerankResult:
        started = time.perf_counter()
        if not documents:
            return RerankResult(
                scores=[],
                model_id=self.model_id,
                provider="local",
                latency_ms=0,
            )
        pairs = [(query, doc) for doc in documents]
        scores = _to_float_list(self.model.predict(pairs))
        return RerankResult(
            scores=scores,
            model_id=self.model_id,
            provider="local",
            latency_ms=_elapsed_ms(started),
        )

    def health(self) -> str:
        return "ok"


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))
