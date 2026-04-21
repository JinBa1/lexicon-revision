from __future__ import annotations

import time
from typing import Any

import httpx
from src.runtime.telemetry import HealthStatus, TokenUsage
from src.study.models import (
    GenerationEvent,
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
)
from src.study.providers.base import (
    ModelNotAvailableError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderTimeoutError,
)


class OpenAICompatibleProvider:
    capabilities = ProviderCapabilities(
        json_schema_output=True,
        json_mode=True,
        max_context_tokens=None,
    )

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        request_timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._request_timeout_seconds = request_timeout_seconds
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient()

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": request.messages,
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": request.response_schema,
                },
            }
        elif self.capabilities.json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=_auth_headers(self._api_key),
                timeout=request.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc)) from exc
        except httpx.TransportError as exc:
            raise ProviderConnectionError(str(exc)) from exc

        if response.status_code == 404:
            raise ModelNotAvailableError(response.text)
        if response.status_code >= 400:
            raise ProviderHTTPError(response.text)

        data = _json_dict(response)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderHTTPError("provider returned invalid JSON")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ProviderHTTPError("provider returned invalid JSON")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ProviderHTTPError("provider returned invalid JSON")

        return GenerationResult(
            raw_content=_message_content(message),
            model=_string_or_default(data.get("model"), self._model),
            provider="openai_compatible",
            finish_reason=_string_or_default(choice.get("finish_reason"), "unknown"),
            latency_ms=int((time.monotonic() - started) * 1000),
            usage=_openai_usage(data.get("usage")),
        )

    async def stream_generate(self, request: GenerationRequest):
        result = await self.generate(request)
        if result.raw_content:
            yield GenerationEvent(type="token", text=result.raw_content)
        yield GenerationEvent(type="done")

    async def health(self) -> HealthStatus:
        try:
            response = await self._client.get(
                f"{self._base_url}/models",
                headers=_auth_headers(self._api_key),
                timeout=self._request_timeout_seconds,
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            return "unreachable"
        except httpx.HTTPError:
            return "error"

        if response.status_code == 404:
            return "unreachable"
        if response.status_code >= 500:
            return "error"
        if response.status_code >= 400:
            return "error"

        data = _json_dict(response)
        models = data.get("data")
        if not isinstance(models, list):
            return "error"
        for model in models:
            if isinstance(model, dict) and model.get("id") == self._model:
                return "ok"
        return "model_missing"

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def close(self) -> None:
        await self.aclose()


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _json_dict(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderHTTPError("provider returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ProviderHTTPError("provider returned invalid JSON")
    return data


def _message_content(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    raise ProviderHTTPError("provider returned invalid JSON")


def _string_or_default(value: Any, default: str) -> str:
    return value if isinstance(value, str) else default


def _openai_usage(usage: Any) -> TokenUsage | None:
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    if not all(
        isinstance(value, int) for value in (input_tokens, output_tokens, total_tokens)
    ):
        return None
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
