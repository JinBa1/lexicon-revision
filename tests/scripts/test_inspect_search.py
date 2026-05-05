"""Infrastructure tests for inspect_search.py."""

from __future__ import annotations

import json
import sys

import pytest
from scripts.inspect_search import (
    build_search_payload,
    create_real_search_service,
    main,
    parse_args,
    render_json,
    render_text,
)
from src.metadata_schema.models import FilterCondition
from src.search.errors import CollectionNotFoundError
from src.search.models import SearchResponse, SearchResult
from src.search.providers.config import (
    EmbeddingProviderSettings,
    RerankProviderSettings,
    RetrievalProviderSettings,
)

MEDIA_OBJECT_KEY = "artifacts/mineru/run-y2025p1q1/images/fig-1.png"


class ToolTestFakeSearchService:
    embedding_model_id = "tool-test-embedding"
    rerank_model_id = None

    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def search(
        self,
        query: str,
        collection: str,
        filters: list[FilterCondition] | None = None,
        limit: int = 10,
        rerank: bool = True,
    ) -> SearchResponse:
        self.calls.append(
            {
                "query": query,
                "collection": collection,
                "filters": filters,
                "limit": limit,
                "rerank": rerank,
            }
        )
        return self.response


class ToolTestMissingCollectionService:
    def search(
        self,
        query: str,
        collection: str,
        filters: list[FilterCondition] | None = None,
        limit: int = 10,
        rerank: bool = True,
    ) -> SearchResponse:
        del query, filters, limit, rerank
        raise CollectionNotFoundError(collection)


def _build_fake_response() -> SearchResponse:
    return SearchResponse(
        query="binary search trees",
        collection="tool-test-collection",
        total=1,
        results=[
            SearchResult(
                chunk_id="chunk-1",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="Binary search trees support logarithmic lookup.",
                score=0.8123,
                metadata={
                    "year": 2025,
                    "paper": 1,
                    "question_number": 1,
                    "topic": "Algorithms",
                    "chunk_level": "question",
                    "source_pdf": "y2025p1q1.pdf",
                },
                media=[],
            )
        ],
    )


def test_build_search_payload_passes_filters_to_service() -> None:
    fake_service = ToolTestFakeSearchService(_build_fake_response())
    filters = [
        FilterCondition(field="year", op="eq", value=2025),
        FilterCondition(field="topic", op="eq", value="Algorithms"),
        FilterCondition(field="has_code", op="eq", value=True),
    ]

    payload = build_search_payload(
        service=fake_service,  # type: ignore[arg-type]
        query="binary search trees",
        collection="tool-test-collection",
        filters=filters,
        limit=3,
        rerank=False,
        show_media=False,
        max_text_chars=32,
    )

    assert fake_service.calls == [
        {
            "query": "binary search trees",
            "collection": "tool-test-collection",
            "filters": filters,
            "limit": 3,
            "rerank": False,
        }
    ]
    assert payload["filters"] == [item.model_dump() for item in filters]
    assert payload["providers"] == {
        "embedding_model_id": "tool-test-embedding",
        "rerank_model_id": None,
    }


def test_render_text_includes_filter_and_metadata_output() -> None:
    payload = {
        "query": "binary search trees",
        "collection": "tool-test-collection",
        "filters": [
            {"field": "year", "op": "eq", "value": 2025},
            {"field": "topic", "op": "eq", "value": "Algorithms"},
        ],
        "limit": 3,
        "rerank": False,
        "show_media": True,
        "total": 1,
        "results": [
            {
                "chunk_id": "chunk-1",
                "chunk_level": "question",
                "parent_chunk_id": None,
                "sub_question_label": None,
                "score": 0.8123,
                "metadata": {
                    "year": 2025,
                    "paper": 1,
                    "question_number": 1,
                    "topic": "Algorithms",
                },
                "text": "Binary search trees support logarithmic lookup.",
                "text_preview": "Binary search trees support logarithmic lookup.",
                "media": [
                    {
                        "media_id": "fig-1",
                        "kind": "image",
                        "object_key": MEDIA_OBJECT_KEY,
                        "access_url": "http://localhost:8000/_dev/object/GET/...",
                        "relation": "direct",
                    }
                ],
            }
        ],
    }

    output = render_text(payload)

    assert "Filters: year eq 2025; topic eq Algorithms" in output
    assert "metadata: paper=1 question_number=1 topic=Algorithms year=2025" in output
    assert f"object_key={MEDIA_OBJECT_KEY}" in output


def test_render_json_is_parseable() -> None:
    payload = {
        "query": "binary search trees",
        "collection": "tool-test-collection",
        "filters": [],
        "limit": 3,
        "rerank": False,
        "show_media": False,
        "total": 1,
        "results": [
            {
                "chunk_id": "chunk-1",
                "chunk_level": "question",
                "parent_chunk_id": None,
                "sub_question_label": None,
                "score": 0.8123,
                "metadata": {"topic": "Algorithms"},
                "text": "Binary search trees support logarithmic lookup.",
                "text_preview": "Binary search trees support logarithmic lookup.",
                "media": [],
            }
        ],
    }

    parsed = json.loads(render_json(payload))
    assert parsed["results"][0]["chunk_id"] == "chunk-1"


def test_parse_args_supports_no_rerank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_search.py",
            "binary search trees",
            "--collection",
            "tool-test-collection",
            "--no-rerank",
        ],
    )

    args = parse_args()

    assert args.rerank is False


def test_parse_args_collects_repeatable_filter_conditions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_search.py",
            "binary search trees",
            "--filter",
            "tripos_part:eq:II",
            "--filter",
            "year:gte:2020",
        ],
    )

    args = parse_args()

    assert args.filters == ["tripos_part:eq:II", "year:gte:2020"]


def test_parse_args_rejects_legacy_fixed_filter_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["inspect_search.py", "binary search trees", "--year", "2024"],
    )

    with pytest.raises(SystemExit):
        parse_args()


def test_create_real_search_service_enables_collection_thresholds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    provider_settings = RetrievalProviderSettings(
        embedding=EmbeddingProviderSettings(provider="local", model="embed"),
        rerank=RerankProviderSettings(provider="local", model="rerank"),
        rerank_enabled=False,
        voyage_api_key=None,
    )

    monkeypatch.setattr(
        "scripts.inspect_search.load_retrieval_provider_settings",
        lambda: provider_settings,
    )
    monkeypatch.setattr(
        "scripts.inspect_search.build_embedding_provider",
        lambda settings: "embedder",
    )
    monkeypatch.setattr(
        "scripts.inspect_search.build_rerank_provider",
        lambda settings, device=None: "reranker",
    )
    monkeypatch.setattr("scripts.inspect_search.load_database_settings", lambda: "db")

    def fake_create_search_service(**kwargs):
        captured.update(kwargs)
        return "service"

    monkeypatch.setattr(
        "scripts.inspect_search.create_search_service",
        fake_create_search_service,
    )

    service = create_real_search_service(rerank=True)

    assert service == "service"
    assert captured["database_settings"] == "db"
    assert captured["embedding_model"] == "embedder"
    assert captured["reranker"] == "reranker"
    assert captured["apply_collection_thresholds"] is True
    assert "retrieval_vector_min_score" not in captured
    assert "retrieval_rerank_min_score" not in captured


def test_main_forwards_repeatable_filter_conditions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = ToolTestFakeSearchService(_build_fake_response())
    monkeypatch.setattr(
        "scripts.inspect_search.create_real_search_service",
        lambda rerank, reranker_device=None: service,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_search.py",
            "binary search trees",
            "--collection",
            "tool-test-collection",
            "--filter",
            "tripos_part:eq:II",
            "--filter",
            "year:gte:2020",
            "--format",
            "json",
        ],
    )

    main()

    parsed = json.loads(capsys.readouterr().out)
    assert service.calls[0]["filters"] == [
        FilterCondition(field="tripos_part", op="eq", value="II"),
        FilterCondition(field="year", op="gte", value=2020),
    ]
    assert parsed["filters"] == [
        {"field": "tripos_part", "op": "eq", "value": "II"},
        {"field": "year", "op": "gte", "value": 2020},
    ]


def test_main_reports_missing_collection_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "scripts.inspect_search.create_real_search_service",
        lambda rerank, reranker_device=None: ToolTestMissingCollectionService(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_search.py",
            "binary search trees",
            "--collection",
            "missing",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "Collection 'missing' not found." in err
    assert "index_chunks_postgres.py" in err


def test_render_text_hides_media_when_not_requested() -> None:
    payload = {
        "query": "binary search trees",
        "collection": "tool-test-collection",
        "filters": [],
        "limit": 3,
        "rerank": False,
        "show_media": False,
        "total": 1,
        "results": [
            {
                "chunk_id": "chunk-1",
                "chunk_level": "question",
                "parent_chunk_id": None,
                "sub_question_label": None,
                "score": 0.8123,
                "metadata": {"topic": "Algorithms"},
                "text": "Binary search trees support logarithmic lookup.",
                "text_preview": "Binary search trees support logarithmic lookup.",
                "media": [
                    {
                        "media_id": "fig-1",
                        "kind": "image",
                        "object_key": MEDIA_OBJECT_KEY,
                        "access_url": "http://localhost:8000/_dev/object/GET/...",
                        "relation": "direct",
                    }
                ],
            }
        ],
    }

    output = render_text(payload)

    assert "   media:" not in output
    assert "media_id=fig-1" not in output
