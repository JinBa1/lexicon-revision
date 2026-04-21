from __future__ import annotations

import time
from typing import Any

import httpx
from src.runtime.telemetry import TokenUsage
from src.search.providers.base import (
    EmbeddingResult,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderResponseError,
    ProviderTimeoutError,
    RerankResult,
)

_HEALTH_TIMEOUT_SECONDS = 1.0


def _handle_request(
    client: httpx.Client,
    method: str,
    url: str,
    headers: dict[str, str],
    json_data: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        response = client.request(
            method=method,
            url=url,
            headers=headers,
            json=json_data,
            timeout=timeout_seconds,
        )
        if response.status_code in (401, 403):
            raise ProviderAuthError(f"Authentication failed: {response.text}")
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException as e:
        raise ProviderTimeoutError(f"Request timed out: {e}") from e
    except httpx.ConnectError as e:
        raise ProviderConnectionError(f"Connection error: {e}") from e
    except httpx.HTTPStatusError as e:
        raise ProviderHTTPError(
            f"HTTP error {e.response.status_code}: {e.response.text}"
        ) from e
    except ValueError as e:
        raise ProviderResponseError(f"Invalid JSON response: {e}") from e


def _as_float_vector(value: Any) -> list[float]:
    if not isinstance(value, list):
        raise ProviderResponseError("embedding must be a list")
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError("embedding contains non-numeric values") from exc


class VoyageEmbedder:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "voyage-4-lite",
        base_url: str = "https://api.voyageai.com/v1",
        timeout_seconds: float = 30.0,
        output_dimension: int | None = None,
        truncation: bool = True,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.model_id = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.output_dimension = output_dimension
        self.truncation = truncation
        self._owns_client = client is None
        self._client = client or httpx.Client()

    def _embed(self, texts: list[str], input_type: str) -> EmbeddingResult:
        started = time.perf_counter()
        if not texts:
            return EmbeddingResult(
                vectors=[],
                model_id=self.model_id,
                provider="voyage",
                latency_ms=0,
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model_id,
            "input": texts,
            "input_type": input_type,
            "truncation": self.truncation,
        }
        if self.output_dimension is not None:
            payload["output_dimension"] = self.output_dimension

        data = _handle_request(
            client=self._client,
            method="POST",
            url=f"{self.base_url}/embeddings",
            headers=headers,
            json_data=payload,
            timeout_seconds=self.timeout_seconds,
        )

        rows = data.get("data")
        if not isinstance(rows, list):
            raise ProviderResponseError("embedding response missing data list")
        if len(rows) != len(texts):
            raise ProviderResponseError(
                f"Expected {len(texts)} vectors, got {len(rows)}"
            )

        if all(isinstance(row, dict) and "index" in row for row in rows):
            seen_indices: set[int] = set()
            ordered_rows: list[dict[str, Any] | None] = [None] * len(texts)
            for row in rows:
                index = row.get("index")
                if not isinstance(index, int) or not 0 <= index < len(texts):
                    raise ProviderResponseError("embedding index out of range")
                if index in seen_indices:
                    raise ProviderResponseError("duplicate embedding index")
                seen_indices.add(index)
                ordered_rows[index] = row
            sorted_rows = [row for row in ordered_rows if row is not None]
        else:
            sorted_rows = rows

        vectors: list[list[float]] = []
        for row in sorted_rows:
            if not isinstance(row, dict) or "embedding" not in row:
                raise ProviderResponseError("embedding row missing embedding")
            vectors.append(_as_float_vector(row["embedding"]))

        model = data.get("model", self.model_id)
        return EmbeddingResult(
            vectors=vectors,
            model_id=str(model),
            provider="voyage",
            latency_ms=_elapsed_ms(started),
            usage=_usage_from_payload(data.get("usage")),
        )

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        return self._embed(texts, input_type="document")

    def embed_query(self, text: str) -> EmbeddingResult:
        result = self._embed([text], input_type="query")
        return result

    def health(self) -> str:
        try:
            self._probe_health()
        except (ProviderConnectionError, ProviderTimeoutError):
            return "unreachable"
        except ProviderHTTPError:
            return "error"
        return "ok"

    def _probe_health(self) -> None:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model_id,
            "input": ["healthcheck"],
            "input_type": "query",
            "truncation": self.truncation,
        }
        if self.output_dimension is not None:
            payload["output_dimension"] = self.output_dimension
        _handle_request(
            client=self._client,
            method="POST",
            url=f"{self.base_url}/embeddings",
            headers=headers,
            json_data=payload,
            timeout_seconds=_health_timeout_seconds(self.timeout_seconds),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class VoyageReranker:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "rerank-2.5-lite",
        base_url: str = "https://api.voyageai.com/v1",
        timeout_seconds: float = 30.0,
        truncation: bool = True,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.model_id = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.truncation = truncation
        self._owns_client = client is None
        self._client = client or httpx.Client()

    def rerank(self, query: str, documents: list[str]) -> RerankResult:
        started = time.perf_counter()
        if not documents:
            return RerankResult(
                scores=[],
                model_id=self.model_id,
                provider="voyage",
                latency_ms=0,
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model_id,
            "query": query,
            "documents": documents,
            "return_documents": False,
            "truncation": self.truncation,
        }

        data = _handle_request(
            client=self._client,
            method="POST",
            url=f"{self.base_url}/rerank",
            headers=headers,
            json_data=payload,
            timeout_seconds=self.timeout_seconds,
        )

        rows = data.get("data")
        if not isinstance(rows, list):
            raise ProviderResponseError("rerank response missing data list")

        scores = [0.0] * len(documents)
        seen_indices: set[int] = set()

        for row in rows:
            if not isinstance(row, dict):
                raise ProviderResponseError("rerank row must be an object")
            index = row.get("index")
            if not isinstance(index, int) or not 0 <= index < len(documents):
                raise ProviderResponseError("rerank index out of range")
            if index in seen_indices:
                raise ProviderResponseError("duplicate rerank index")
            score = row.get("relevance_score")
            if not isinstance(score, int | float):
                raise ProviderResponseError("rerank score must be numeric")
            scores[index] = float(score)
            seen_indices.add(index)

        if len(seen_indices) != len(documents):
            raise ProviderResponseError(
                f"Expected {len(documents)} scores, got {len(seen_indices)}"
            )

        model = data.get("model", self.model_id)
        return RerankResult(
            scores=scores,
            model_id=str(model),
            provider="voyage",
            latency_ms=_elapsed_ms(started),
            usage=_usage_from_payload(data.get("usage")),
        )

    def health(self) -> str:
        try:
            self._probe_health()
        except (ProviderConnectionError, ProviderTimeoutError):
            return "unreachable"
        except ProviderHTTPError:
            return "error"
        return "ok"

    def _probe_health(self) -> None:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model_id,
            "query": "healthcheck",
            "documents": ["healthcheck"],
            "return_documents": False,
            "truncation": self.truncation,
        }
        _handle_request(
            client=self._client,
            method="POST",
            url=f"{self.base_url}/rerank",
            headers=headers,
            json_data=payload,
            timeout_seconds=_health_timeout_seconds(self.timeout_seconds),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _health_timeout_seconds(timeout_seconds: float) -> float:
    return min(timeout_seconds, _HEALTH_TIMEOUT_SECONDS)


def _usage_from_payload(payload: Any) -> TokenUsage | None:
    if not isinstance(payload, dict):
        return None
    input_tokens = payload.get("input_tokens")
    output_tokens = payload.get("output_tokens")
    total_tokens = payload.get("total_tokens")
    if not any(
        value is not None for value in (input_tokens, output_tokens, total_tokens)
    ):
        return None
    return TokenUsage(
        input_tokens=_as_int_or_none(input_tokens),
        output_tokens=_as_int_or_none(output_tokens),
        total_tokens=_as_int_or_none(total_tokens),
    )


def _as_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise ProviderResponseError("usage values must be integers")
    return value
