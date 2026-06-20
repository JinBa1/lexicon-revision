"""Node + orchestrate tests for the PR3 reflection loop (grade / reflect).

The broad parity suite (tests/study/test_service.py, test_graph.py) runs with
reflection DISABLED. These tests explicitly ENABLE it and drive the grade and
reflect nodes directly, plus a few orchestrate() end-to-end paths.
"""

from __future__ import annotations

import json

import pytest
from src.study.config import ReflectionSettings
from src.study.graph import (
    StudyGraphState,
    _grade_node,
    _reflect_node,
    _route_after_grade,
    _route_after_reflect,
    _route_after_retrieve,
)
from src.study.models import GenerationResult, StudyRequest
from src.study.planning.models import PlanningMetadata, QueryPlan
from src.study.providers.base import ProviderConnectionError
from tests.study.test_graph import _retrieval_with_results
from tests.study.test_service import (
    FakePlannedRetrieval,
    FakeProvider,
    FakeQueryPlanner,
    make_service,
    planner_execution,
    search_result,
    study_settings,
    valid_generation_result,
)

pytestmark = pytest.mark.anyio


def _on(**kw) -> ReflectionSettings:
    return ReflectionSettings(enabled=True, **kw)


def _grade_json(accepted: list[str], critique: str = "") -> GenerationResult:
    return GenerationResult(
        raw_content=json.dumps({"accepted_chunk_ids": accepted, "critique": critique}),
        model="grader",
        provider="openai_compatible",
        finish_reason="stop",
        latency_ms=3,
    )


def _reflect_json(query: str) -> GenerationResult:
    return GenerationResult(
        raw_content=json.dumps({"reformulated_query": query}),
        model="reflect",
        provider="openai_compatible",
        finish_reason="stop",
        latency_ms=3,
    )


def _plan() -> QueryPlan:
    return QueryPlan(
        original_query="binary search trees",
        semantic_queries=["binary search trees"],
    )


def _service(provider: FakeProvider, *, reflection: ReflectionSettings | None = None):
    return make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=FakePlannedRetrieval(_retrieval_with_results()),
        provider=provider,
        settings=study_settings(reflection=reflection or _on()),
    )


def _state(*, results=("a", "b"), **overrides) -> StudyGraphState:
    base = dict(
        request=StudyRequest(query="binary search trees", scope={"collection": "c"}),
        request_id="req-1",
        plan=_plan(),
        planning_metadata=PlanningMetadata(
            planner_version="query_planner_v2",
            original_query="binary search trees",
            semantic_queries=["binary search trees"],
            latency_ms=1,
        ),
        search_response=_retrieval_with_results().search_response.model_copy(
            update={"results": [search_result(c) for c in results]}
        ),
        filters_applied=[],
    )
    base.update(overrides)
    return StudyGraphState(**base)


# --- grade node -----------------------------------------------------------


async def test_grade_accepts_all_routes_to_pack() -> None:
    provider = FakeProvider(_grade_json(["a", "b"]))
    out = await _grade_node(_state(), _service(provider))
    assert {c.chunk_id for c in out["graded_chunks"]} == {"a", "b"}
    assert out["reflection_graded"] is True
    assert _route_after_grade(_state(**out)) == "pack"


async def test_grade_prunes_subset() -> None:
    provider = FakeProvider(_grade_json(["a"]))
    out = await _grade_node(_state(), _service(provider))
    assert [c.chunk_id for c in out["graded_chunks"]] == ["a"]


async def test_grade_hallucination_guard_drops_phantom_id() -> None:
    provider = FakeProvider(_grade_json(["a", "ghost"]))
    out = await _grade_node(_state(), _service(provider))
    assert [c.chunk_id for c in out["graded_chunks"]] == ["a"]


async def test_grade_zero_with_budget_routes_to_reflect() -> None:
    provider = FakeProvider(_grade_json([], critique="all about hashing"))
    out = await _grade_node(_state(), _service(provider))
    assert out["requery_count"] == 1
    assert out["critique"] == "all about hashing"
    assert out["seen_chunk_ids"] == ["a", "b"]
    assert "graded_chunks" not in out and "response" not in out
    assert _route_after_grade(_state(**out)) == "reflect"


async def test_grade_zero_second_pass_abstains() -> None:
    provider = FakeProvider(_grade_json([], critique="still nothing"))
    state = _state(
        requery_count=1, requery_semantic=["bst balancing"], seen_chunk_ids=["x"]
    )
    out = await _grade_node(state, _service(provider))
    assert out["response"].answer_status == "insufficient_evidence"
    assert out["response"].retrieval.status == "low_relevance"


async def test_grade_no_new_evidence_abstains_without_calling_provider() -> None:
    provider = FakeProvider(_grade_json(["a"]))  # would accept if called
    state = _state(results=("a", "b"), requery_count=1, seen_chunk_ids=["a", "b"])
    out = await _grade_node(state, _service(provider))
    assert out["response"].retrieval.status == "low_relevance"
    assert provider.calls == []  # the grader was never invoked


async def test_grade_timeout_fails_safe_accept_all() -> None:
    provider = FakeProvider(ProviderConnectionError("boom"))
    out = await _grade_node(_state(), _service(provider))
    assert {c.chunk_id for c in out["graded_chunks"]} == {"a", "b"}
    assert out["reflection_graded"] is False
    assert "response" not in out


async def test_grade_malformed_output_fails_safe_accept_all() -> None:
    # A generation-shaped payload is not a RelevanceGradingDraft -> ValidationError.
    provider = FakeProvider(valid_generation_result(chunk_id="a"))
    out = await _grade_node(_state(), _service(provider))
    assert {c.chunk_id for c in out["graded_chunks"]} == {"a", "b"}
    assert out["reflection_graded"] is False


async def test_grade_kill_switch_accepts_all_no_call() -> None:
    provider = FakeProvider(_grade_json([]))
    out = await _grade_node(
        _state(), _service(provider, reflection=ReflectionSettings(enabled=False))
    )
    assert {c.chunk_id for c in out["graded_chunks"]} == {"a", "b"}
    assert out["reflection_graded"] is False
    assert provider.calls == []


async def test_grade_zero_no_budget_abstains_without_reflect() -> None:
    import asyncio

    provider = FakeProvider(_grade_json([], critique="off topic"))
    # deadline already (nearly) expired -> below requery_min_remaining_seconds.
    state = _state(deadline_monotonic=asyncio.get_running_loop().time() + 1.0)
    out = await _grade_node(
        state, _service(provider, reflection=_on(requery_min_remaining_seconds=28.0))
    )
    assert out["response"].retrieval.status == "low_relevance"


# --- reflect node ---------------------------------------------------------


async def test_reflect_produces_query_routes_to_retrieve() -> None:
    provider = FakeProvider(_reflect_json("AVL red-black tree balancing rotations"))
    state = _state(critique="got hashing", requery_count=1)
    out = await _reflect_node(state, _service(provider))
    assert out["requery_semantic"] == ["AVL red-black tree balancing rotations"]
    assert _route_after_reflect(_state(**out)) == "retrieve"


async def test_reflect_declines_empty_abstains() -> None:
    provider = FakeProvider(_reflect_json(""))
    state = _state(critique="off domain", requery_count=1)
    out = await _reflect_node(state, _service(provider))
    assert out["response"].retrieval.status == "low_relevance"
    assert _route_after_reflect(_state(**out)) == "respond"


async def test_reflect_duplicate_of_original_abstains() -> None:
    provider = FakeProvider(
        _reflect_json("Binary Search Trees")
    )  # == original (case-insensitive)
    state = _state(critique="x", requery_count=1)
    out = await _reflect_node(state, _service(provider))
    assert out["response"].retrieval.status == "low_relevance"


async def test_reflect_failure_abstains() -> None:
    provider = FakeProvider(ProviderConnectionError("boom"))
    state = _state(critique="x", requery_count=1)
    out = await _reflect_node(state, _service(provider))
    assert out["response"].retrieval.status == "low_relevance"


# --- routing --------------------------------------------------------------


async def test_route_after_retrieve_goes_to_grade() -> None:
    assert _route_after_retrieve(_state()) == "grade"


async def test_route_after_grade_pack_when_graded() -> None:
    state = _state(graded_chunks=[])  # set (not None) -> pack
    assert _route_after_grade(state) == "pack"


# --- orchestrate end-to-end (reflection on) -------------------------------


async def test_orchestrate_prune_then_answer() -> None:
    # grade keeps "a" only, then generation succeeds.
    provider = FakeProvider([_grade_json(["a"]), valid_generation_result(chunk_id="a")])
    service = _service(provider)
    response = await service.orchestrate(
        StudyRequest(query="binary search trees", scope={"collection": "c"})
    )
    assert response.answer_status == "ok"
    assert response.retrieval.reflection_graded is True
    assert response.retrieval.graded_chunk_count == 1


async def test_orchestrate_abstains_when_grade_rejects_and_reflect_declines() -> None:
    from src.main import _study_outcome

    provider = FakeProvider([_grade_json([], critique="off topic"), _reflect_json("")])
    service = _service(provider)
    response = await service.orchestrate(
        StudyRequest(query="capital of France", scope={"collection": "c"})
    )
    assert response.answer_status == "insufficient_evidence"
    assert response.retrieval.status == "low_relevance"
    assert response.retrieval.requery_attempted is True
    # Ordering in _study_outcome is load-bearing: low_relevance must win over the
    # insufficient_evidence -> "ok" mapping.
    assert _study_outcome(response) == "reflection_abstained"


async def test_orchestrate_requery_then_answer() -> None:
    # pass1 returns "a" (rejected) -> reflect -> pass2 returns the UNSEEN "b"
    # (so the no-new-evidence guard does not fire) -> grade accepts "b" -> answer.
    pass1 = _retrieval_with_results()
    pass2 = pass1.model_copy(
        update={
            "search_response": pass1.search_response.model_copy(
                update={"results": [search_result("b")]}
            )
        }
    )
    provider = FakeProvider(
        [
            _grade_json([], critique="too narrow"),
            _reflect_json("balanced search tree rotations"),
            _grade_json(["b"]),
            valid_generation_result(chunk_id="b"),
        ]
    )
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=FakePlannedRetrieval([pass1, pass2]),
        provider=provider,
        settings=study_settings(reflection=_on()),
    )
    response = await service.orchestrate(
        StudyRequest(query="binary search trees", scope={"collection": "c"})
    )
    assert response.answer_status == "ok"
    assert response.retrieval.requery_attempted is True
    assert response.retrieval.reflection_reformulated_query == (
        "balanced search tree rotations"
    )


async def test_orchestrate_requery_logs_response_exactly_once(monkeypatch) -> None:
    # The re-query path traverses retrieve->grade->reflect->retrieve->grade->...
    # but must still log exactly once at the single respond sink.
    pass1 = _retrieval_with_results()
    pass2 = pass1.model_copy(
        update={
            "search_response": pass1.search_response.model_copy(
                update={"results": [search_result("b")]}
            )
        }
    )
    provider = FakeProvider(
        [
            _grade_json([], critique="too narrow"),
            _reflect_json("balanced search tree rotations"),
            _grade_json(["b"]),
            valid_generation_result(chunk_id="b"),
        ]
    )
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=FakePlannedRetrieval([pass1, pass2]),
        provider=provider,
        settings=study_settings(reflection=_on()),
    )
    calls: list[object] = []
    original = service._log_response
    monkeypatch.setattr(
        service, "_log_response", lambda r: (calls.append(r), original(r))[1]
    )
    await service.orchestrate(
        StudyRequest(query="binary search trees", scope={"collection": "c"})
    )
    assert len(calls) == 1


async def test_orchestrate_budget_gate_skips_requery() -> None:
    # With an effectively-expired deadline, grade rejects but the budget gate
    # blocks the re-query -> abstain, requery never attempted.
    import asyncio

    provider = FakeProvider([_grade_json([], critique="off topic")])
    service = _service(provider, reflection=_on(requery_min_remaining_seconds=28.0))
    response = await service.orchestrate(
        StudyRequest(query="binary search trees", scope={"collection": "c"}),
        deadline_monotonic=asyncio.get_running_loop().time() + 1.0,
    )
    assert response.retrieval.status == "low_relevance"
    assert response.retrieval.requery_attempted is False
    assert provider.calls and len(provider.calls) == 1  # grade only, no reflect
