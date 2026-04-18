import json
from typing import Callable

import httpx
import pytest
from src.search.providers.base import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from src.search.providers.voyage import VoyageEmbedder, VoyageReranker


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_embed_documents_sends_document_input_type() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2]},
                    {"index": 1, "embedding": [0.3, 0.4]},
                ],
                "model": "voyage-4-lite",
            },
        )

    embedder = VoyageEmbedder(
        api_key="k", model="voyage-4-lite", client=_client(handler)
    )
    result = embedder.embed_documents(["a", "b"])

    assert result.vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert result.model_id == "voyage-4-lite"
    assert captured["auth"] == "Bearer k"
    assert captured["body"]["input_type"] == "document"
    assert captured["body"]["model"] == "voyage-4-lite"
    assert captured["body"]["truncation"] is True


def test_embed_query_sends_query_input_type() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [0.1, 0.2]}],
                "model": "voyage-4-lite",
            },
        )

    embedder = VoyageEmbedder(api_key="k", client=_client(handler))
    embedder.embed_query("q")

    assert captured["body"]["input_type"] == "query"


def test_embed_empty_documents_returns_empty() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    embedder = VoyageEmbedder(api_key="k", client=_client(handler))
    result = embedder.embed_documents([])

    assert not called
    assert result.vectors == []


def test_embed_rows_sorted_by_index() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ],
                "model": "voyage-4-lite",
            },
        )

    embedder = VoyageEmbedder(api_key="k", client=_client(handler))
    result = embedder.embed_documents(["a", "b"])

    assert result.vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_documents_wrong_vector_count_raises_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [0.1, 0.2]}],
                "model": "voyage-4-lite",
            },
        )

    embedder = VoyageEmbedder(api_key="k", client=_client(handler))
    with pytest.raises(ProviderResponseError):
        embedder.embed_documents(["a", "b"])


def test_rerank_sends_correct_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "relevance_score": 0.8},
                    {"index": 1, "relevance_score": 0.2},
                ],
                "model": "rerank-2.5-lite",
            },
        )

    reranker = VoyageReranker(
        api_key="k", model="rerank-2.5-lite", client=_client(handler)
    )
    reranker.rerank("q", ["d1", "d2"])

    assert captured["auth"] == "Bearer k"
    assert captured["body"]["model"] == "rerank-2.5-lite"
    assert captured["body"]["query"] == "q"
    assert captured["body"]["documents"] == ["d1", "d2"]
    assert captured["body"]["return_documents"] is False
    assert captured["body"]["truncation"] is True


def test_rerank_maps_scores_back_to_input_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 2, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.1},
                    {"index": 1, "relevance_score": 0.5},
                ],
                "model": "rerank-2.5-lite",
            },
        )

    reranker = VoyageReranker(
        api_key="k", model="rerank-2.5-lite", client=_client(handler)
    )
    result = reranker.rerank("q", ["d0", "d1", "d2"])

    assert result.scores == [0.1, 0.5, 0.9]
    assert result.model_id == "rerank-2.5-lite"


def test_rerank_missing_score_raises_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "relevance_score": 0.5}]},
        )

    reranker = VoyageReranker(
        api_key="k", model="rerank-2.5-lite", client=_client(handler)
    )
    with pytest.raises(ProviderResponseError):
        reranker.rerank("q", ["d0", "d1"])


def test_http_errors_map_correctly() -> None:
    def handler_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad key")

    with pytest.raises(ProviderAuthError):
        VoyageEmbedder(api_key="k", client=_client(handler_401)).embed_documents(["a"])

    def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    with pytest.raises(ProviderHTTPError):
        VoyageEmbedder(api_key="k", client=_client(handler_500)).embed_documents(["a"])

    def handler_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    with pytest.raises(ProviderTimeoutError):
        embedder = VoyageEmbedder(api_key="k", client=_client(handler_timeout))
        embedder.embed_documents(["a"])

    def handler_connect(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connect")

    with pytest.raises(ProviderConnectionError):
        embedder = VoyageEmbedder(api_key="k", client=_client(handler_connect))
        embedder.embed_documents(["a"])
