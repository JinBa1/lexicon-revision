from __future__ import annotations

import json

import httpx
import pytest
from src.study.models import GenerationRequest
from src.study.providers.base import (
    ModelNotAvailableError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderTimeoutError,
)
from src.study.providers.ollama import OllamaProvider


@pytest.mark.anyio
async def test_ollama_provider_posts_schema_format() -> None:
    seen_payload = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"answer_status":"ok","overview":"x"}'},
                "model": "qwen2.5:7b-instruct",
                "done_reason": "stop",
                "prompt_eval_count": 12,
                "eval_count": 6,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="qwen2.5:7b-instruct",
        client=client,
    )

    result = await provider.generate(
        GenerationRequest(
            messages=[{"role": "user", "content": "hello"}],
            response_schema={"type": "object"},
            temperature=0.1,
            max_tokens=None,
            timeout_seconds=10,
        )
    )

    assert seen_payload["model"] == "qwen2.5:7b-instruct"
    assert seen_payload["stream"] is False
    assert seen_payload["format"] == {"type": "object"}
    assert result.raw_content.startswith("{")
    assert result.usage is not None
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 6
    assert result.usage.total_tokens == 18
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_provider_uses_json_format_without_schema() -> None:
    seen_payload = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"message": {"content": "{}"}, "model": "m", "done_reason": "stop"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(base_url="http://ollama.test", model="m", client=client)

    await provider.generate(
        GenerationRequest(
            messages=[],
            response_schema=None,
            temperature=0.1,
            max_tokens=None,
            timeout_seconds=10,
        )
    )

    assert seen_payload["format"] == "json"
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_provider_maps_max_tokens_to_num_predict() -> None:
    seen_payload = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"message": {"content": "{}"}, "model": "m", "done_reason": "stop"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(base_url="http://ollama.test", model="m", client=client)

    await provider.generate(
        GenerationRequest(
            messages=[],
            response_schema=None,
            temperature=0.1,
            max_tokens=128,
            timeout_seconds=10,
        )
    )

    assert seen_payload["options"]["num_predict"] == 128
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_provider_stream_generate_yields_token_and_done() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"content": "{}"}, "model": "m", "done_reason": "stop"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(base_url="http://ollama.test", model="m", client=client)

    events = [
        event
        async for event in provider.stream_generate(
            GenerationRequest(
                messages=[],
                response_schema=None,
                temperature=0.1,
                max_tokens=None,
                timeout_seconds=10,
            )
        )
    ]

    assert [event.type for event in events] == ["token", "done"]
    assert events[0].text == "{}"
    assert events[1].text is None
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_provider_raises_model_not_available() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="missing",
        client=client,
    )

    with pytest.raises(ModelNotAvailableError):
        await provider.generate(
            GenerationRequest(
                messages=[],
                response_schema=None,
                temperature=0.1,
                max_tokens=None,
                timeout_seconds=10,
            )
        )
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_provider_maps_other_http_errors() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(base_url="http://ollama.test", model="m", client=client)

    with pytest.raises(ProviderHTTPError):
        await provider.generate(
            GenerationRequest(
                messages=[],
                response_schema=None,
                temperature=0.1,
                max_tokens=None,
                timeout_seconds=10,
            )
        )
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_provider_maps_http_status_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        response = httpx.Response(418, request=request, json={"error": "teapot"})
        raise httpx.HTTPStatusError("teapot", request=request, response=response)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(base_url="http://ollama.test", model="m", client=client)

    with pytest.raises(ProviderHTTPError):
        await provider.generate(
            GenerationRequest(
                messages=[],
                response_schema=None,
                temperature=0.1,
                max_tokens=None,
                timeout_seconds=10,
            )
        )
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_provider_retries_transient_error() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(
            200,
            json={"message": {"content": "{}"}, "model": "m", "done_reason": "stop"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="m",
        max_retries=1,
        retry_backoff_seconds=0,
        client=client,
    )

    await provider.generate(
        GenerationRequest(
            messages=[],
            response_schema=None,
            temperature=0.1,
            max_tokens=None,
            timeout_seconds=10,
        )
    )

    assert calls == 2
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_provider_timeout_raises_provider_timeout() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timed out")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="m",
        max_retries=1,
        retry_backoff_seconds=0,
        client=client,
    )

    with pytest.raises(ProviderTimeoutError):
        await provider.generate(
            GenerationRequest(
                messages=[],
                response_schema=None,
                temperature=0.1,
                max_tokens=None,
                timeout_seconds=10,
            )
        )

    assert calls == 2
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_provider_transport_error_raises_provider_connection() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connection refused")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="m",
        max_retries=1,
        retry_backoff_seconds=0,
        client=client,
    )

    with pytest.raises(ProviderConnectionError):
        await provider.generate(
            GenerationRequest(
                messages=[],
                response_schema=None,
                temperature=0.1,
                max_tokens=None,
                timeout_seconds=10,
            )
        )

    assert calls == 2
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_provider_invalid_json_response_raises_provider_http_error() -> (
    None
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(base_url="http://ollama.test", model="m", client=client)

    with pytest.raises(ProviderHTTPError):
        await provider.generate(
            GenerationRequest(
                messages=[],
                response_schema=None,
                temperature=0.1,
                max_tokens=None,
                timeout_seconds=10,
            )
        )
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_provider_aclose_leaves_injected_client_open() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: None))
    provider = OllamaProvider(base_url="http://ollama.test", model="m", client=client)

    await provider.aclose()

    assert not client.is_closed
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_health_reports_model_missing() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "other-model"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="wanted",
        client=client,
    )

    assert await provider.health() == "model_missing"
    await client.aclose()


@pytest.mark.anyio
async def test_ollama_health_reports_error_for_unexpected_json_shape() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [None]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="wanted",
        client=client,
    )

    assert await provider.health() == "error"
    await client.aclose()
