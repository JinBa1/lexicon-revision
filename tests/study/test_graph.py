"""Node-level tests for the LangGraph study port (Track A, PR 1).

These cover routing decisions and parity traps that the existing
``tests/study`` suite does not exercise: the ``context_build_failed`` branch,
log-exactly-once across terminals, in-graph filter-error propagation, the
generation-deadline breach, and the dict-return access path. The broad
behavioral parity is covered by ``tests/study/test_service.py`` running
unchanged through the graph-backed ``orchestrate()``.
"""

from __future__ import annotations

import pytest
from src.search.errors import InvalidMetadataFilterError
from src.search.models import SearchResponse
from src.search.pg_service import SearchExecutionTelemetry
from src.study.config import (
    ContextSettings,
    GenerationSettings,
    PlanningSettings,
    PromptSettings,
    StudySettings,
)
from src.study.models import PackingResult, StudyRequest, StudyResponse
from src.study.planning.models import PlannedRetrievalResult, QueryPlan
from src.study.providers.base import ProviderConnectionError
from tests.study.test_service import (
    FakePlannedRetrieval,
    FakeProvider,
    FakeQueryPlanner,
    make_service,
    planner_execution,
    search_result,
    valid_generation_result,
)

pytestmark = pytest.mark.anyio


def _plan() -> QueryPlan:
    return QueryPlan(
        original_query="2025 dp",
        semantic_queries=["dynamic programming recurrence"],
    )


def _retrieval_with_results(
    *, search_telemetry: SearchExecutionTelemetry | None = None
) -> PlannedRetrievalResult:
    return PlannedRetrievalResult(
        search_response=SearchResponse(
            query="dynamic programming recurrence",
            collection="cam-cs-tripos",
            results=[search_result("a")],
            total=1,
        ),
        executed_queries=["dynamic programming recurrence"],
        filters_applied=[],
        search_telemetry=search_telemetry,
    )


def _request():
    return {"query": "2025 dp", "scope": {"collection": "cam-cs-tripos"}}


def _raise(*args, **kwargs):
    raise RuntimeError("pack exploded")


async def test_orchestrate_returns_studyresponse_from_ainvoke_dict() -> None:
    # ainvoke returns a plain dict for a pydantic state; orchestrate must read
    # result["response"] and hand back the StudyResponse.
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=FakePlannedRetrieval(_retrieval_with_results()),
        provider=FakeProvider(valid_generation_result(chunk_id="a")),
    )
    response = await service.orchestrate(StudyRequest(**_request()))
    assert isinstance(response, StudyResponse)
    assert response.answer_status == "ok"


async def test_context_build_failed_yields_degraded_metadata(monkeypatch) -> None:
    # An exception while building context (here: pack_chunks) must terminate as
    # generation_failed / context_build_failed with degraded (empty-id)
    # RetrievalMetadata, distinct from context_pack_failed.
    def _boom(*args, **kwargs):
        raise RuntimeError("pack exploded")

    monkeypatch.setattr("src.study.graph.pack_chunks", _boom)

    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=FakePlannedRetrieval(_retrieval_with_results()),
        provider=FakeProvider(valid_generation_result(chunk_id="a")),
    )
    response = await service.orchestrate(StudyRequest(**_request()))

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "context_build_failed"
    assert response.retrieval.status == "ok"
    assert response.retrieval.context_chunk_ids == []
    assert response.retrieval.omitted_chunk_ids == []
    assert response.retrieval.truncated_chunk_ids == []
    # The provider is never called when context build fails.
    assert service.provider.calls == []  # type: ignore[attr-defined]


async def test_context_build_failed_logs_at_failure_site(monkeypatch, caplog) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("pack exploded")

    monkeypatch.setattr("src.study.graph.pack_chunks", _boom)
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=FakePlannedRetrieval(_retrieval_with_results()),
        provider=FakeProvider(valid_generation_result(chunk_id="a")),
    )
    with caplog.at_level("ERROR"):
        await service.orchestrate(StudyRequest(**_request()))
    matches = [r for r in caplog.records if r.message == "study_context_build_failed"]
    assert matches
    assert getattr(matches[0], "request_id", None)


async def test_context_pack_failed_uses_nondegraded_metadata(monkeypatch) -> None:
    # context_pack_failed is distinct from context_build_failed: it keeps the
    # real (non-degraded) RetrievalMetadata from the attempted packing.
    def _pack_failed(*args, **kwargs):
        return PackingResult(
            chunks=[],
            omitted_chunk_ids=["a"],
            truncated_chunk_ids=[],
            status="context_pack_failed",
        )

    monkeypatch.setattr("src.study.graph.pack_chunks", _pack_failed)
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=FakePlannedRetrieval(_retrieval_with_results()),
        provider=FakeProvider(valid_generation_result(chunk_id="a")),
    )
    response = await service.orchestrate(StudyRequest(**_request()))

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "context_pack_failed"
    assert response.retrieval.status == "ok"
    # Non-degraded: omitted ids reflect the real packing output, unlike the
    # empty-list degraded metadata of context_build_failed.
    assert response.retrieval.omitted_chunk_ids == ["a"]
    assert service.provider.calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "insufficient_evidence",
        "retrieval_failed",
        "provider_error",
        "context_build_failed",
    ],
)
async def test_log_response_called_exactly_once(monkeypatch, scenario) -> None:
    # Covers all three terminal-builder families so a self-logging builder
    # (double-log) or a missing respond-sink log (zero-log) is caught.
    provider = FakeProvider(valid_generation_result(chunk_id="a"))
    if scenario == "success":
        retrieval = FakePlannedRetrieval(_retrieval_with_results())
    elif scenario == "insufficient_evidence":
        retrieval = FakePlannedRetrieval(
            PlannedRetrievalResult(
                search_response=SearchResponse(
                    query="dynamic programming recurrence",
                    collection="cam-cs-tripos",
                    results=[],
                    total=0,
                ),
                executed_queries=["dynamic programming recurrence"],
                filters_applied=[],
            )
        )
    elif scenario == "retrieval_failed":
        retrieval = FakePlannedRetrieval(RuntimeError("db down"))
    elif scenario == "provider_error":  # generation_failed terminal
        retrieval = FakePlannedRetrieval(_retrieval_with_results())
        provider = FakeProvider(ProviderConnectionError("boom"))
    else:  # context_build_failed -> generation_failed terminal
        retrieval = FakePlannedRetrieval(_retrieval_with_results())
        monkeypatch.setattr("src.study.graph.pack_chunks", _raise)

    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=retrieval,
        provider=provider,
    )

    calls: list[StudyResponse] = []
    original = service._log_response

    def spy(response: StudyResponse) -> None:
        calls.append(response)
        original(response)

    monkeypatch.setattr(service, "_log_response", spy)
    await service.orchestrate(StudyRequest(**_request()))
    assert len(calls) == 1


async def test_invalid_metadata_filter_propagates_out_of_graph(caplog) -> None:
    # InvalidMetadataFilterError must NOT become a terminal response; it raises
    # out of ainvoke/orchestrate so the route maps it to 422, and no terminal
    # study_request log is emitted.
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=FakePlannedRetrieval(
            InvalidMetadataFilterError("bad filter")
        ),
        provider=FakeProvider(valid_generation_result(chunk_id="a")),
    )
    with caplog.at_level("INFO"), pytest.raises(InvalidMetadataFilterError):
        await service.orchestrate(StudyRequest(**_request()))
    assert not any(r.message == "study_request" for r in caplog.records)


async def test_retrieval_failure_omits_search_telemetry() -> None:
    # On the retrieval_failed (exception) path, no search telemetry is attached.
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=FakePlannedRetrieval(RuntimeError("db down")),
        provider=FakeProvider(valid_generation_result(chunk_id="a")),
    )
    response = await service.orchestrate(StudyRequest(**_request()))
    assert response.answer_status == "retrieval_failed"
    assert response.retrieval.search_telemetry is None


async def test_generation_deadline_breach_returns_provider_timeout() -> None:
    # The single generate node preserves the original asyncio.timeout block:
    # a provider slower than total_generation_deadline_seconds terminates as
    # generation_failed / provider_timeout.
    settings = StudySettings(
        generation=GenerationSettings(
            request_timeout_seconds=5,
            total_generation_deadline_seconds=0.1,
            schema_repair_retries=1,
        ),
        context=ContextSettings(budget_tokens=4000, max_single_chunk_tokens=1200),
        prompt=PromptSettings(version="study_aid_v2", path="prompts/study_aid_v2.yaml"),
        planning=PlanningSettings(
            request_timeout_seconds=5,
            total_planning_deadline_seconds=10,
            prompt_version="query_planner_v1",
            prompt_path="prompts/query_planner_v1.yaml",
        ),
    )
    provider = FakeProvider(valid_generation_result(chunk_id="a"))
    provider.delay = 0.5
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=FakePlannedRetrieval(_retrieval_with_results()),
        provider=provider,
        settings=settings,
    )
    response = await service.orchestrate(StudyRequest(**_request()))
    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "provider_timeout"


async def test_provider_error_returns_generation_failed() -> None:
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=FakePlannedRetrieval(_retrieval_with_results()),
        provider=FakeProvider(ProviderConnectionError("unreachable")),
    )
    response = await service.orchestrate(StudyRequest(**_request()))
    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "provider_unreachable"
