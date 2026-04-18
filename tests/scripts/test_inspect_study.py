from __future__ import annotations

import sys

from scripts.inspect_study import _classify_schema, parse_args, render_text


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
