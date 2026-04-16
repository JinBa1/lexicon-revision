from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from src.study.models import (
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
)
from src.study.providers.base import (
    GeneratorHealth,
    ModelNotAvailableError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderTimeoutError,
)


class OllamaProvider:
    capabilities = ProviderCapabilities(
        json_schema_output=True,
        json_mode=True,
        max_context_tokens=32768,
    )

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        max_retries: int = 1,
        retry_backoff_seconds: float = 2,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient()

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": request.messages,
            "stream": False,
            "options": {"temperature": request.temperature},
        }
        if request.response_schema is not None:
            payload["format"] = request.response_schema
        elif self.capabilities.json_mode:
            payload["format"] = "json"
        if request.max_tokens is not None:
            payload["options"]["num_predict"] = request.max_tokens

        started = time.monotonic()
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            try:
                response = await self._client.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                    timeout=request.timeout_seconds,
                )
                if response.status_code == 404:
                    raise ModelNotAvailableError(response.text)
                if response.status_code >= 500:
                    if attempt == attempts - 1:
                        raise ProviderHTTPError(response.text)
                    await self._sleep_before_retry()
                    continue
                if response.status_code >= 400:
                    raise ProviderHTTPError(response.text)
                try:
                    data = response.json()
                except ValueError as exc:
                    raise ProviderHTTPError("provider returned invalid JSON") from exc
                if not isinstance(data, dict):
                    raise ProviderHTTPError("provider returned invalid JSON")
                message = data.get("message", {})
                if not isinstance(message, dict):
                    raise ProviderHTTPError("provider returned invalid JSON")
                return GenerationResult(
                    raw_content=message.get("content", ""),
                    model=data.get("model", self._model),
                    provider="ollama",
                    finish_reason=data.get("done_reason", "unknown"),
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
            except httpx.TimeoutException as exc:
                if attempt == attempts - 1:
                    raise ProviderTimeoutError(str(exc)) from exc
            except httpx.TransportError as exc:
                if attempt == attempts - 1:
                    raise ProviderConnectionError(str(exc)) from exc
            except httpx.HTTPStatusError as exc:
                raise ProviderHTTPError(str(exc)) from exc
            await self._sleep_before_retry()

        raise ProviderHTTPError("provider request failed")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def close(self) -> None:
        await self.aclose()

    async def _sleep_before_retry(self) -> None:
        if self._retry_backoff_seconds > 0:
            await asyncio.sleep(self._retry_backoff_seconds)

    async def health(self) -> GeneratorHealth:
        try:
            response = await self._client.get(f"{self._base_url}/api/tags", timeout=5)
        except (httpx.ConnectError, httpx.TimeoutException):
            return "unreachable"
        except httpx.HTTPError:
            return "error"
        if response.status_code >= 500:
            return "error"
        if response.status_code == 404:
            return "unreachable"
        try:
            data = response.json()
        except ValueError:
            return "error"
        if not isinstance(data, dict):
            return "error"
        models = data.get("models", [])
        if not isinstance(models, list):
            return "error"
        if not all(isinstance(model, dict) for model in models):
            return "error"
        names = {model.get("name") for model in models}
        return "ok" if self._model in names else "model_missing"
