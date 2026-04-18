from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from scripts.evaluate_planned_search import (
    compare_cases,
    load_messy_eval_spec,
)
from src.search.models import SearchResponse, SearchResult
from src.study.planning.models import QueryPlan, StudyFilters


class _FakeSearchService:
    def __init__(self, responses: dict[str, SearchResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        query: str,
        collection: str = "cam-cs-tripos",
        filters: dict[str, Any] | None = None,
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
        return self.responses.get(
            query,
            SearchResponse(query=query, collection=collection, results=[], total=0),
        )


class _FakePlanner:
    def __init__(self, plans: dict[str, QueryPlan | Exception]) -> None:
        self.plans = plans
        self.calls: list[dict[str, Any]] = []

    async def plan(
        self,
        raw_query: str,
        hard_filters: StudyFilters | None = None,
    ) -> QueryPlan:
        self.calls.append({"raw_query": raw_query, "hard_filters": hard_filters})
        res = self.plans.get(raw_query)
        if isinstance(res, Exception):
            raise res
        if res is None:
            return QueryPlan(original_query=raw_query, semantic_queries=[raw_query])
        return res


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


def test_load_messy_eval_spec(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        """
name: test_spec
cases:
  - id: "paxos-case"
    query: "What is Paxos?"
    expected:
      any_chunk_ids: ["paxos-1"]
  - id: "raft-case"
    query: "Explain Raft."
    expected:
      any_chunk_ids: ["raft-1", "raft-2"]
""",
        encoding="utf-8",
    )
    cases = load_messy_eval_spec(spec_path)
    assert len(cases) == 2
    assert cases[0]["query"] == "What is Paxos?"
    assert cases[0]["expected_chunk_ids"] == ["paxos-1"]


@pytest.mark.anyio
async def test_compare_cases() -> None:
    cases = [
        {
            "id": "p-case",
            "query": "Paxos",
            "expected_chunk_ids": ["p1"],
            "expected_topics": [],
            "filters": {},
        },
        {
            "id": "r-case",
            "query": "Raft",
            "expected_chunk_ids": ["r1"],
            "expected_topics": [],
            "filters": {},
        },
    ]

    # Baseline responses
    baseline_responses = {
        "Paxos": SearchResponse(
            query="Paxos",
            collection="test-coll",
            results=[_result("p1")],
            total=1,
        ),
        "Raft": SearchResponse(
            query="Raft",
            collection="test-coll",
            results=[_result("other")],
            total=1,
        ),
    }

    # Planned responses (Paxos is same, Raft is better)
    planned_responses = {
        "Paxos-Rewritten": SearchResponse(
            query="Paxos-Rewritten",
            collection="test-coll",
            results=[_result("p1")],
            total=1,
        ),
        "Raft-Rewritten": SearchResponse(
            query="Raft-Rewritten",
            collection="test-coll",
            results=[_result("r1")],
            total=1,
        ),
    }

    search_service = _FakeSearchService({**baseline_responses, **planned_responses})
    planner = _FakePlanner(
        {
            "Paxos": QueryPlan(
                original_query="Paxos", semantic_queries=["Paxos-Rewritten"]
            ),
            "Raft": QueryPlan(
                original_query="Raft", semantic_queries=["Raft-Rewritten"]
            ),
        }
    )

    results = await compare_cases(
        cases=cases,
        search_service=search_service,
        planner=planner,
        collection="test-coll",
        limit=5,
    )

    assert len(results) == 2

    # Paxos case: both hit
    paxos_res = next(r for r in results if r["id"] == "p-case")
    assert paxos_res["baseline_hit"] is True
    assert paxos_res["planned_hit"] is True
    assert paxos_res["status"] == "ok"

    # Raft case: baseline miss, planned hit
    raft_res = next(r for r in results if r["id"] == "r-case")
    assert raft_res["baseline_hit"] is False
    assert raft_res["planned_hit"] is True
    assert raft_res["status"] == "ok"


@pytest.mark.anyio
async def test_compare_cases_with_fallback() -> None:
    cases = [
        {
            "id": "f-case",
            "query": "FailMe",
            "expected_chunk_ids": ["f1"],
            "expected_topics": [],
            "filters": {},
        }
    ]

    search_service = _FakeSearchService(
        {
            "FailMe": SearchResponse(
                query="FailMe", collection="test-coll", results=[], total=0
            )
        }
    )
    planner = _FakePlanner({"FailMe": ValueError("LLM Error")})

    results = await compare_cases(
        cases=cases,
        search_service=search_service,
        planner=planner,
        collection="test-coll",
        limit=5,
    )

    assert len(results) == 1
    assert results[0]["status"] == "fallback"
    # Fallback should use baseline retrieval
    assert results[0]["planned_hit"] is False
    assert results[0]["baseline_hit"] is False
