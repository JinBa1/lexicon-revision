from __future__ import annotations

import json

import httpx
import pytest
from src.runtime.telemetry import TokenUsage
from src.study.models import GenerationRequest
from src.study.providers.http_openai import OpenAICompatibleProvider


def test_token_usage_fields_default_to_none() -> None:
    usage = TokenUsage()

    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None


@pytest.mark.anyio
async def test_openai_compatible_provider_generate_posts_chat_completions() -> None:
    seen_payload = {}
    seen_headers = {}
    seen_path = ""

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_path
        seen_path = request.url.path
        seen_headers.update(request.headers)
        seen_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "generation-model",
                "choices": [
                    {
                        "message": {"content": '{"answer_status":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://example.test/v1",
        api_key="secret-key",
        model="generation-model",
        request_timeout_seconds=30,
        client=client,
    )

    result = await provider.generate(
        GenerationRequest(
            messages=[{"role": "user", "content": "hello"}],
            response_schema=None,
            temperature=0.3,
            max_tokens=120,
            timeout_seconds=10,
        )
    )

    assert seen_path == "/v1/chat/completions"
    assert seen_headers["authorization"] == "Bearer secret-key"
    assert seen_payload["model"] == "generation-model"
    assert seen_payload["messages"] == [{"role": "user", "content": "hello"}]
    assert seen_payload["temperature"] == 0.3
    assert seen_payload["max_tokens"] == 120
    assert result.provider == "openai_compatible"
    assert result.model == "generation-model"
    assert result.finish_reason == "stop"
    assert result.raw_content == '{"answer_status":"ok"}'
    assert result.usage is not None
    assert result.usage.total_tokens == 18
    await client.aclose()


@pytest.mark.anyio
async def test_openai_compatible_provider_health_checks_models() -> None:
    seen_path = ""

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_path
        seen_path = request.url.path
        return httpx.Response(200, json={"data": [{"id": "generation-model"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://example.test/v1",
        api_key="secret-key",
        model="generation-model",
        request_timeout_seconds=30,
        client=client,
    )

    assert await provider.health() == "ok"
    assert seen_path == "/v1/models"
    await client.aclose()
