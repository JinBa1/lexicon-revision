from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from scripts.evaluate_planned_search import (
    compare_cases,
    load_messy_eval_spec,
    main,
    parse_args,
    render_report,
)
from src.metadata_schema.models import FilterCondition
from src.runtime.telemetry import ProviderCallTelemetry
from src.search.models import SearchResponse, SearchResult
from src.study.planning.models import PlannerExecution, QueryPlan


class _FakeSearchService:
    embedding_model_id = "tool-test-embedding"
    rerank_model_id = None

    def __init__(self, responses: dict[str, SearchResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> SearchResponse:
        self.calls.append(kwargs)
        return self.responses[kwargs["query"]]


class _FakePlanner:
    def __init__(self, plans: dict[str, QueryPlan | Exception]) -> None:
        self.plans = plans
        self.calls: list[dict[str, Any]] = []

    async def plan(
        self,
        raw_query: str,
        hard_filters: list[FilterCondition] | None,
    ) -> PlannerExecution:
        self.calls.append({"raw_query": raw_query, "hard_filters": hard_filters})
        outcome = self.plans[raw_query]
        if isinstance(outcome, Exception):
            raise outcome
        return PlannerExecution(
            plan=outcome,
            telemetry=ProviderCallTelemetry(
                provider="fake", model="fake", latency_ms=0, usage=None
            ),
        )


def _result(chunk_id: str, topic: str | None = None) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        text="",
        score=0.9,
        metadata={"year": 2025, "topic": topic},
        media=[],
    )


def test_load_messy_eval_spec_accepts_query_planner_messy_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "messy.yaml"
    path.write_text(
        """
name: planner_ab
collection: cam
cases:
  - id: concept-vm
    filters:
      - field: paper
        op: eq
        value: 2
    expected:
      any_chunk_ids:
        - chunk-1
      any_topics:
        - Operating Systems
    variants:
      - id: messy
        query: vm paging PTE stuff
""",
        encoding="utf-8",
    )

    spec = load_messy_eval_spec(path)

    assert spec.name == "planner_ab"
    assert spec.collection == "cam"
    assert spec.cases[0].id == "concept-vm"
    assert spec.cases[0].filters == [FilterCondition(field="paper", op="eq", value=2)]
    assert spec.cases[0].any_chunk_ids == ["chunk-1"]
    assert spec.cases[0].any_topics == ["Operating Systems"]
    assert spec.cases[0].variants[0].query == "vm paging PTE stuff"


@pytest.mark.anyio
async def test_compare_cases_reports_hit_at_k_delta_and_fallback(
    tmp_path: Path,
) -> None:
    spec = load_messy_eval_spec(
        _write(
            tmp_path,
            """
name: planner_ab
collection: cam
cases:
  - id: ok-case
    expected:
      any_chunk_ids:
        - wanted-1
    variants:
      - id: messy
        query: messy one
  - id: fallback-case
    expected:
      any_chunk_ids:
        - wanted-2
    variants:
      - id: messy
        query: messy two
""",
        )
    )
    search = _FakeSearchService(
        {
            "messy one": SearchResponse(
                query="messy one",
                collection="cam",
                results=[_result("noise"), _result("wanted-1")],
                total=2,
            ),
            "planned one": SearchResponse(
                query="planned one",
                collection="cam",
                results=[_result("wanted-1")],
                total=1,
            ),
            "messy two": SearchResponse(
                query="messy two",
                collection="cam",
                results=[_result("wanted-2")],
                total=1,
            ),
        }
    )
    planner = _FakePlanner(
        {
            "messy one": QueryPlan(
                original_query="messy one",
                semantic_queries=["planned one"],
            ),
            "messy two": RuntimeError("planner down"),
        }
    )

    report = await compare_cases(
        spec=spec,
        collection="cam",
        top_k=5,
        planner=planner,
        search_service=search,
    )

    by_id = {case["id"]: case for case in report["cases"]}
    assert by_id["ok-case/messy"]["raw"]["hit"] is True
    assert by_id["ok-case/messy"]["planned"]["hit"] is True
    assert by_id["ok-case/messy"]["planned"]["planning_status"] == "ok"
    assert by_id["fallback-case/messy"]["planned"]["planning_status"] == "fallback"
    assert by_id["fallback-case/messy"]["planned"]["hit"] is True
    assert by_id["fallback-case/messy"]["planned"]["query"] == "messy two"
    assert report["providers"] == {
        "embedding_model_id": "tool-test-embedding",
        "rerank_model_id": None,
    }
    assert report["aggregate"]["fallback_rate"] == pytest.approx(0.5)
    assert report["aggregate"]["hit_delta_sum"] == 0
    assert planner.calls[0]["hard_filters"] == []


@pytest.mark.anyio
async def test_compare_cases_evaluates_all_variants_and_topics(
    tmp_path: Path,
) -> None:
    spec = load_messy_eval_spec(
        _write(
            tmp_path,
            """
name: planner_ab
collection: cam
cases:
  - id: topic-case
    expected:
      any_topics:
        - Databases
    variants:
      - id: terse
        query: db joins
      - id: messy
        query: past questions on databases joins
""",
        )
    )
    search = _FakeSearchService(
        {
            "db joins": SearchResponse(
                query="db joins",
                collection="cam",
                results=[_result("noise", topic="Algorithms")],
                total=1,
            ),
            "database joins": SearchResponse(
                query="database joins",
                collection="cam",
                results=[_result("wanted", topic="Databases")],
                total=1,
            ),
            "past questions on databases joins": SearchResponse(
                query="past questions on databases joins",
                collection="cam",
                results=[_result("wanted", topic="Databases")],
                total=1,
            ),
            "databases joins": SearchResponse(
                query="databases joins",
                collection="cam",
                results=[_result("wanted", topic="Databases")],
                total=1,
            ),
        }
    )
    planner = _FakePlanner(
        {
            "db joins": QueryPlan(
                original_query="db joins",
                semantic_queries=["database joins"],
            ),
            "past questions on databases joins": QueryPlan(
                original_query="past questions on databases joins",
                semantic_queries=["databases joins"],
            ),
        }
    )

    report = await compare_cases(
        spec=spec,
        collection="cam",
        top_k=5,
        planner=planner,
        search_service=search,
    )

    assert [case["id"] for case in report["cases"]] == [
        "topic-case/terse",
        "topic-case/messy",
    ]
    assert all(case["planned"]["hit"] for case in report["cases"])
    assert report["aggregate"]["hit_delta_sum"] == 1


def test_parse_args_defaults_to_no_rerank(tmp_path: Path, monkeypatch) -> None:
    eval_path = tmp_path / "messy.yaml"
    eval_path.write_text("name: x\ncases: []\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["evaluate_planned_search.py", str(eval_path)])
    assert parse_args().rerank is False

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_planned_search.py",
            str(eval_path),
            "--rerank",
            "--reranker-device",
            "cpu",
        ],
    )
    args = parse_args()
    assert args.rerank is True
    assert args.reranker_device == "cpu"


@pytest.mark.anyio
async def test_compare_cases_forwards_rerank_flag(tmp_path: Path) -> None:
    spec = load_messy_eval_spec(
        _write(
            tmp_path,
            """
name: planner_ab
collection: cam
cases:
  - id: case-a
    filters:
      - field: year
        op: eq
        value: 2025
    expected:
      any_chunk_ids:
        - wanted
    variants:
      - id: messy
        query: messy one
""",
        )
    )
    search = _FakeSearchService(
        {
            "messy one": SearchResponse(
                query="messy one",
                collection="cam",
                results=[_result("wanted")],
                total=1,
            ),
            "planned one": SearchResponse(
                query="planned one",
                collection="cam",
                results=[_result("wanted")],
                total=1,
            ),
        }
    )
    from src.study.planning.models import QueryPlan

    planner = _FakePlanner(
        {
            "messy one": QueryPlan(
                original_query="messy one",
                semantic_queries=["planned one"],
            ),
        }
    )

    await compare_cases(
        spec=spec,
        collection="cam",
        top_k=5,
        planner=planner,
        search_service=search,
        rerank=False,
    )

    assert search.calls, "expected search_service.search to be invoked"
    assert all(call["rerank"] is False for call in search.calls)
    assert search.calls[0]["filters"] == [
        FilterCondition(field="year", op="eq", value=2025)
    ]


def test_render_report_summarizes_aggregate_and_cases() -> None:
    rendered = render_report(
        {
            "name": "planner_ab",
            "collection": "cam",
            "top_k": 5,
            "aggregate": {
                "variant_count": 1,
                "fallback_rate": 0.0,
                "hit_delta_sum": 1,
            },
            "cases": [
                {
                    "id": "ok-case/messy",
                    "raw": {"query": "messy", "hit": False, "top_ids": ["noise"]},
                    "planned": {
                        "query": "planned",
                        "hit": True,
                        "planning_status": "ok",
                        "planning_error": None,
                        "top_ids": ["wanted"],
                    },
                }
            ],
        }
    )

    assert "fallback_rate=0.00" in rendered
    assert "hit_delta_sum=1" in rendered
    assert "ok-case/messy" in rendered
    assert "planned hit=True" in rendered


def test_main_reports_invalid_authored_filter_without_traceback(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    eval_path = _write(
        tmp_path,
        """
name: planner_ab
collection: cam
cases:
  - id: bad-filter
    filters:
      - field: year
        op: gte
        value: "2024"
    expected:
      any_chunk_ids:
        - wanted
    variants:
      - id: messy
        query: messy one
""",
    )
    monkeypatch.setattr(sys, "argv", ["evaluate_planned_search.py", str(eval_path)])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    assert "Planner eval case 'bad-filter' filter #1" in capsys.readouterr().err


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "messy.yaml"
    path.write_text(body, encoding="utf-8")
    return path
