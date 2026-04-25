from __future__ import annotations

import json
from pathlib import Path

from scripts.calibrate_retrieval_threshold import (
    assert_expected_models,
    create_real_search_service,
    render_markdown,
    run_calibration,
    write_outputs,
)
from scripts.search_tooling import EvalCase
from src.search.models import SearchResponse, SearchResult
from src.search.providers.config import (
    EmbeddingProviderSettings,
    RerankProviderSettings,
    RetrievalProviderSettings,
)


class FakeCalibrationSearchService:
    embedding_model_id = "voyage-4-lite"
    rerank_model_id = "rerank-2.5-lite"

    def __init__(self, responses: dict[str, SearchResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def search(
        self,
        query: str,
        collection: str,
        filters=None,
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
        return self.responses[query]


def _result(chunk_id: str, topic: str, score: float) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        text=f"{chunk_id} body",
        score=score,
        metadata={"topic": topic},
        media=[],
    )


def _response(query: str, results: list[SearchResult]) -> SearchResponse:
    return SearchResponse(
        query=query,
        collection="cam-cs-tripos-fixture",
        results=results,
        total=len(results),
    )


def test_create_real_search_service_disables_collection_thresholds(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    provider_settings = RetrievalProviderSettings(
        embedding=EmbeddingProviderSettings(provider="local", model="embed"),
        rerank=RerankProviderSettings(provider="local", model="rerank"),
        rerank_enabled=False,
        voyage_api_key=None,
    )

    monkeypatch.setattr(
        "scripts.calibrate_retrieval_threshold.load_retrieval_provider_settings",
        lambda: provider_settings,
    )
    monkeypatch.setattr(
        "scripts.calibrate_retrieval_threshold.build_embedding_provider",
        lambda settings: "embedder",
    )
    monkeypatch.setattr(
        "scripts.calibrate_retrieval_threshold.build_rerank_provider",
        lambda settings: "reranker",
    )
    monkeypatch.setattr(
        "scripts.calibrate_retrieval_threshold.load_database_settings",
        lambda: "db",
    )

    def fake_create_search_service(**kwargs):
        captured.update(kwargs)
        return "service"

    monkeypatch.setattr(
        "scripts.calibrate_retrieval_threshold.create_search_service",
        fake_create_search_service,
    )

    service = create_real_search_service(
        media_dir="media",
        rerank=True,
    )

    assert service == "service"
    assert captured["database_settings"] == "db"
    assert captured["embedding_model"] == "embedder"
    assert captured["reranker"] == "reranker"
    assert captured["media_dir"] == "media"
    assert captured["apply_collection_thresholds"] is False


def test_run_calibration_summarizes_positive_and_negative_score_gap() -> None:
    positive_query = "dynamic programming"
    negative_query = "renaissance oil painting"
    service = FakeCalibrationSearchService(
        {
            positive_query: _response(
                positive_query,
                [
                    _result("cam-1", "Algorithms 1", 0.82),
                    _result("cam-2", "Operating Systems", 0.31),
                ],
            ),
            negative_query: _response(
                negative_query,
                [_result("weak-1", "Databases", 0.24)],
            ),
        }
    )

    report = run_calibration(
        service=service,
        eval_name="fixture_calibration",
        positive_cases=[
            EvalCase(
                id="positive",
                query=positive_query,
                filters=[],
                any_chunk_ids=["cam-1"],
                any_topics=[],
                top_k=3,
            )
        ],
        collection="cam-cs-tripos-fixture",
        limit=5,
        rerank=True,
        negative_queries=[negative_query],
    )

    assert report["positive"]["passed_count"] == 1
    assert report["analysis"]["weakest_positive_score"] == 0.82
    assert report["analysis"]["strongest_negative_score"] == 0.24
    assert report["analysis"]["has_clean_gap"] is True
    assert 0.24 < report["analysis"]["suggested_rerank_min_score"] < 0.82
    assert service.calls == [
        {
            "query": positive_query,
            "collection": "cam-cs-tripos-fixture",
            "filters": [],
            "limit": 10,
            "rerank": True,
        },
        {
            "query": negative_query,
            "collection": "cam-cs-tripos-fixture",
            "filters": None,
            "limit": 10,
            "rerank": True,
        },
    ]


def test_write_outputs_logs_raw_json_and_markdown(tmp_path: Path) -> None:
    report = {
        "name": "fixture_calibration",
        "collection": "cam-cs-tripos-fixture",
        "rerank": True,
        "providers": {
            "embedding_model_id": "voyage-4-lite",
            "rerank_model_id": "rerank-2.5-lite",
        },
        "positive": {"passed_count": 1, "case_count": 1, "cases": []},
        "negative": {"case_count": 1, "cases": []},
        "analysis": {
            "weakest_positive_score": 0.82,
            "strongest_negative_score": 0.24,
            "suggested_rerank_min_score": 0.53,
            "has_clean_gap": True,
        },
    }

    paths = write_outputs(report, tmp_path)

    raw_payload = json.loads(paths["raw_json"].read_text(encoding="utf-8"))
    assert raw_payload["analysis"]["suggested_rerank_min_score"] == 0.53
    assert "Suggested `RETRIEVAL_RERANK_MIN_SCORE`: `0.53`" in paths[
        "summary"
    ].read_text(encoding="utf-8")


def test_render_markdown_reports_no_clean_gap() -> None:
    report = {
        "name": "fixture_calibration",
        "collection": "cam-cs-tripos-fixture",
        "rerank": True,
        "providers": {
            "embedding_model_id": "voyage-4-lite",
            "rerank_model_id": "rerank-2.5-lite",
        },
        "positive": {"passed_count": 1, "case_count": 1, "cases": []},
        "negative": {"case_count": 1, "cases": []},
        "analysis": {
            "weakest_positive_score": 0.2,
            "strongest_negative_score": 0.4,
            "suggested_rerank_min_score": None,
            "has_clean_gap": False,
        },
    }

    markdown = render_markdown(report)

    assert "No clean positive/negative score gap was found." in markdown


def test_assert_expected_models_rejects_wrong_reranker() -> None:
    service = FakeCalibrationSearchService({})

    try:
        assert_expected_models(
            service=service,  # type: ignore[arg-type]
            expected_embedding_model_id=None,
            expected_rerank_model_id="voyage-rerank",
        )
    except SystemExit as exc:
        assert "Expected rerank model" in str(exc)
        assert "cross-encoder" not in str(exc)
    else:
        raise AssertionError("expected model guard to fail")
