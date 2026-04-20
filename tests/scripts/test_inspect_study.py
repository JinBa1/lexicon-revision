from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from scripts.inspect_study import _classify_schema, main, parse_args, render_text
from src.metadata_schema.models import FilterCondition


def test_classify_schema_identifies_planner_calls() -> None:
    assert _classify_schema({"title": "QueryPlanDraft"}) == "planner"
    assert _classify_schema({}) == "generation"


def test_parse_args_accepts_no_planning(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["inspect_study.py", "raw query", "--no-planning"],
    )

    args = parse_args()

    assert args.no_planning is True


def test_parse_args_rerank_defaults_and_flags(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["inspect_study.py", "q"])
    assert parse_args().rerank is True

    monkeypatch.setattr(
        sys,
        "argv",
        ["inspect_study.py", "q", "--no-rerank", "--reranker-device", "cpu"],
    )
    args = parse_args()
    assert args.rerank is False
    assert args.reranker_device == "cpu"


def test_parse_args_collects_repeatable_filter_conditions(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_study.py",
            "q",
            "--filter",
            "tripos_part:eq:II",
            "--filter",
            "year:gte:2020",
        ],
    )

    args = parse_args()

    assert args.filters == ["tripos_part:eq:II", "year:gte:2020"]


def test_main_forwards_repeatable_filter_conditions(
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    class _FakeSearchService:
        embedding_model_id = "tool-test-embedding"
        rerank_model_id = None

    class _FakeProvider:
        capabilities = SimpleNamespace()

    async def _fake_run_orchestration(service, provider, request):
        del service, provider
        captured["filters"] = request.filters
        return object()

    def _fake_build_payload(**kwargs):
        filters = kwargs["filters"]
        return {
            "filters": [item.model_dump(mode="json") for item in filters],
            "query": kwargs["query"],
            "collection": kwargs["collection"],
        }

    monkeypatch.setattr(
        "scripts.inspect_study.load_study_settings",
        lambda path=None: SimpleNamespace(
            context=SimpleNamespace(retrieval_top_k_default=15),
            generation=SimpleNamespace(
                base_url="http://localhost:11434",
                model="qwen2.5:7b-instruct",
                max_provider_retries=1,
            ),
            prompt=SimpleNamespace(version="study_aid_v2"),
        ),
    )
    monkeypatch.setattr(
        "scripts.inspect_study.create_real_search_service",
        lambda media_dir, rerank, reranker_device=None: _FakeSearchService(),
    )
    monkeypatch.setattr(
        "scripts.inspect_study.OllamaProvider",
        lambda **kwargs: _FakeProvider(),
    )
    monkeypatch.setattr(
        "scripts.inspect_study.StudyService",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "scripts.inspect_study._run_orchestration", _fake_run_orchestration
    )
    monkeypatch.setattr("scripts.inspect_study.build_payload", _fake_build_payload)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_study.py",
            "page table questions",
            "--collection",
            "cam",
            "--no-planning",
            "--filter",
            "tripos_part:eq:II",
            "--filter",
            "year:gte:2020",
            "--format",
            "json",
        ],
    )

    main()

    assert captured["filters"] == [
        FilterCondition(field="tripos_part", op="eq", value="II"),
        FilterCondition(field="year", op="gte", value=2020),
    ]
    assert json.loads(capsys.readouterr().out)["filters"] == [
        {"field": "tripos_part", "op": "eq", "value": "II"},
        {"field": "year", "op": "gte", "value": 2020},
    ]


def test_main_reports_invalid_filter_without_traceback(
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_study.py",
            "page table questions",
            "--filter",
            "year:gte:not-an-int",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    assert "requires an integer value" in capsys.readouterr().err


def test_render_text_includes_planning_original_query() -> None:
    rendered = render_text(
        {
            "query": "2025 paper 3 databases",
            "collection": "cam",
            "filters": {},
            "top_k": 15,
            "retrieval": {
                "status": "ok",
                "returned_result_count": 1,
                "context_chunk_ids": [],
                "omitted_chunk_ids": [],
                "truncated_chunk_ids": [],
            },
            "planning": {
                "status": "ok",
                "planner_version": "query_planner_v1",
                "original_query": "2025 paper 3 databases",
                "semantic_queries": ["databases"],
                "latency_ms": 12,
                "attempts": [],
            },
            "prompt": {"version": "study_aid_v2", "messages": []},
            "generation": {
                "provider": "ollama",
                "model": "qwen2.5:7b-instruct",
                "temperature": 0.1,
                "attempt_count": 1,
                "attempts": [],
                "error_category": None,
                "latency_ms": 20,
            },
            "validation": {
                "answer_status": "ok",
                "citation_drops": 0,
                "dropped_chunk_ids": [],
            },
            "answer": {"overview": "", "patterns": [], "limitations": []},
            "sources": [],
        },
        show_prompt=False,
        show_raw=False,
        show_context=False,
        max_text_chars=200,
    )

    assert "original_query: 2025 paper 3 databases" in rendered
