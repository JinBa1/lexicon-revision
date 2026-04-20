from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from pydantic import ValidationError
from src.metadata_schema.models import FilterCondition
from src.search.models import SearchResponse, SearchResult
from src.study.config import (
    ContextSettings,
    GenerationSettings,
    PlanningSettings,
    PromptSettings,
    StudySettings,
)
from src.study.models import GenerationRequest, GenerationResult, StudyRequest
from src.study.planning.models import (
    InvalidPlanError,
    PlannedRetrievalResult,
    QueryPlan,
)
from src.study.providers.base import (
    ModelNotAvailableError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderTimeoutError,
)
from src.study.service import StudyService


class FakeQueryPlanner:
    def __init__(
        self, plan: QueryPlan | Exception | list[QueryPlan | Exception]
    ) -> None:
        self.plan_results = plan if isinstance(plan, list) else [plan]
        self.calls: list[dict[str, Any]] = []
        self.delay: float = 0

    async def plan(
        self,
        raw_query: str,
        hard_filters: list[FilterCondition] | None,
    ) -> QueryPlan:
        self.calls.append({"raw_query": raw_query, "hard_filters": hard_filters})
        if self.delay:
            await asyncio.sleep(self.delay)
        result = self.plan_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakePlannedRetrieval:
    def __init__(
        self,
        result: PlannedRetrievalResult
        | Exception
        | list[PlannedRetrievalResult | Exception],
    ) -> None:
        self.results = result if isinstance(result, list) else [result]
        self.calls: list[dict[str, Any]] = []

    def retrieve(
        self,
        plan: QueryPlan,
        *,
        hard_filters: list[FilterCondition] | None,
        collection: str,
        limit: int,
        rerank: bool = True,
    ) -> PlannedRetrievalResult:
        self.calls.append(
            {
                "plan": plan,
                "hard_filters": hard_filters,
                "collection": collection,
                "limit": limit,
                "rerank": rerank,
            }
        )
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeProvider:
    capabilities = type(
        "Capabilities",
        (),
        {"json_schema_output": True, "json_mode": True, "max_context_tokens": 32768},
    )()

    def __init__(
        self,
        result: GenerationResult | Exception | list[GenerationResult | Exception],
    ) -> None:
        self.results = result if isinstance(result, list) else [result]
        self.calls: list[GenerationRequest] = []
        self.delay: float = 0

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def health(self) -> str:
        return "ok"


def search_result(
    chunk_id: str = "a",
    text: str = "dynamic programming recurrence",
    *,
    chunk_level: str = "question",
    parent_chunk_id: str | None = None,
    sub_question_label: str | None = None,
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        chunk_level=chunk_level,
        parent_chunk_id=parent_chunk_id,
        sub_question_label=sub_question_label,
        text=text,
        score=0.9,
        metadata={
            "year": 2025,
            "paper": 2,
            "question_number": 4,
            "topic": "Algorithms",
        },
        media=[],
    )


def study_settings() -> StudySettings:
    return StudySettings(
        generation=GenerationSettings(
            request_timeout_seconds=5,
            total_generation_deadline_seconds=10,
            schema_repair_retries=1,
        ),
        context=ContextSettings(budget_tokens=4000, max_single_chunk_tokens=1200),
        prompt=PromptSettings(
            version="study_aid_v2",
            path="prompts/study_aid_v2.yaml",
        ),
        planning=PlanningSettings(
            request_timeout_seconds=5,
            total_planning_deadline_seconds=10,
            prompt_version="query_planner_v1",
            prompt_path="prompts/query_planner_v1.yaml",
        ),
    )


def valid_generation_result(
    *,
    chunk_id: str = "a",
    latency_ms: int = 10,
) -> GenerationResult:
    return GenerationResult(
        raw_content=json.dumps(
            {
                "answer_status": "ok",
                "overview": "Dynamic programming is examined through recurrences.",
                "patterns": [
                    {
                        "label": "Recurrence setup",
                        "summary": "Questions ask candidates to define a recurrence.",
                        "supporting_chunk_ids": [chunk_id],
                    }
                ],
                "cited_sources": [
                    {
                        "chunk_id": chunk_id,
                        "why_cited": "It asks for a recurrence.",
                    }
                ],
                "limitations": [],
            }
        ),
        model="qwen2.5:7b-instruct",
        provider="ollama",
        finish_reason="stop",
        latency_ms=latency_ms,
    )


def make_service(
    *,
    query_planner: FakeQueryPlanner,
    planned_retrieval: FakePlannedRetrieval,
    provider: FakeProvider,
    settings: StudySettings | None = None,
) -> StudyService:
    return StudyService(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
        settings=settings or study_settings(),
    )


@pytest.mark.anyio
async def test_orchestrate_happy_path_records_planning_and_uses_planned_query() -> None:
    plan = QueryPlan(
        original_query="2025 dp",
        semantic_queries=["dynamic programming recurrence"],
    )
    query_planner = FakeQueryPlanner(plan)
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="dynamic programming recurrence",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["dynamic programming recurrence"],
            filters_applied=[],
        )
    )
    provider = FakeProvider(valid_generation_result(chunk_id="a"))
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="2025 dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.schema_version == "study_answer_v2"
    assert response.answer_status == "ok"
    assert response.query == "2025 dp"
    assert response.planning.status == "ok"
    assert response.planning.original_query == "2025 dp"
    assert response.planning.semantic_queries == ["dynamic programming recurrence"]
    assert response.planning.error_category is None
    assert response.generation.error_category is None
    assert response.sources[0].metadata == {
        "year": 2025,
        "paper": 2,
        "question_number": 4,
        "topic": "Algorithms",
    }
    assert response.sources[0].sub_question_label is None

    assert planned_retrieval.calls[0]["plan"] is plan
    assert planned_retrieval.calls[0] == {
        "plan": plan,
        "hard_filters": [],
        "collection": "cam-cs-tripos",
        "limit": 15,
        "rerank": True,
    }

    user_prompt = provider.calls[0].messages[1]["content"]
    assert "Original student query: 2025 dp" in user_prompt
    assert "dynamic programming recurrence" in user_prompt


@pytest.mark.anyio
async def test_orchestrate_preserves_sub_question_label_on_sources() -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="q", semantic_queries=["dynamic programming"])
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="dynamic programming",
                collection="cam-cs-tripos",
                results=[
                    search_result(
                        "a",
                        chunk_level="sub_question",
                        parent_chunk_id="parent-1",
                        sub_question_label="b",
                    )
                ],
                total=1,
            ),
            executed_queries=["dynamic programming"],
            filters_applied=[],
        )
    )
    provider = FakeProvider(valid_generation_result(chunk_id="a"))
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="q", scope={"collection": "cam-cs-tripos"})
    )

    assert response.sources[0].chunk_level == "sub_question"
    assert response.sources[0].parent_chunk_id == "parent-1"
    assert response.sources[0].sub_question_label == "b"


@pytest.mark.anyio
async def test_orchestrate_empty_retrieval_skips_generation() -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="missing", semantic_queries=["missing"])
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="missing", collection="cam-cs-tripos", results=[], total=0
            ),
            executed_queries=["missing"],
            filters_applied=[],
        )
    )
    provider = FakeProvider([])
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="missing", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "insufficient_evidence"
    assert response.retrieval.status == "empty"
    assert len(provider.calls) == 0


@pytest.mark.anyio
async def test_orchestrate_filtered_empty_retrieval() -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="filtered", semantic_queries=["filtered"])
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="filtered", collection="cam-cs-tripos", results=[], total=0
            ),
            executed_queries=["filtered"],
            filters_applied=[FilterCondition(field="year", op="eq", value=2025)],
        )
    )
    provider = FakeProvider([])
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="filtered", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "insufficient_evidence"
    assert response.retrieval.status == "filtered_empty"
    assert response.retrieval.filters_applied == [
        FilterCondition(field="year", op="eq", value=2025)
    ]


@pytest.mark.anyio
async def test_orchestrate_retrieval_error() -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="err", semantic_queries=["err"])
    )
    planned_retrieval = FakePlannedRetrieval(RuntimeError("search failed"))
    provider = FakeProvider([])
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="err", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "retrieval_failed"
    assert response.retrieval.status == "error"


@pytest.mark.anyio
async def test_orchestrate_provider_failure_returns_fallback_sources() -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="fail", semantic_queries=["fail"])
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="fail",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["fail"],
            filters_applied=[],
        )
    )
    provider = FakeProvider(ProviderConnectionError("llm down"))
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="fail", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "provider_unreachable"
    assert len(response.sources) == 1
    assert response.sources[0].chunk_id == "a"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_error", "expected_category"),
    [
        (ProviderTimeoutError("slow"), "provider_timeout"),
        (ModelNotAvailableError("missing"), "model_not_available"),
        (ProviderHTTPError("upstream"), "provider_error"),
    ],
)
async def test_orchestrate_maps_provider_failures(
    provider_error: Exception,
    expected_category: str,
) -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="fail", semantic_queries=["fail"])
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="fail",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["fail"],
            filters_applied=[],
        )
    )
    provider = FakeProvider(provider_error)
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="fail", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == expected_category
    assert response.sources[0].chunk_id == "a"
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_orchestrate_schema_repair_success() -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="repair", semantic_queries=["repair"])
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="repair",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["repair"],
            filters_applied=[],
        )
    )

    # First call returns garbage, second call returns valid JSON
    provider = FakeProvider(
        [
            GenerationResult(
                raw_content="not json",
                model="qwen",
                provider="ollama",
                finish_reason="stop",
                latency_ms=10,
            ),
            valid_generation_result(chunk_id="a"),
        ]
    )

    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="repair", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "ok"
    assert response.generation.attempt_count == 2
    assert len(provider.calls) == 2
    assert (
        "Your previous response was not valid JSON"
        in provider.calls[1].messages[-1]["content"]
    )


@pytest.mark.anyio
async def test_orchestrate_does_not_repair_when_retry_count_is_zero() -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="repair", semantic_queries=["repair"])
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="repair",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["repair"],
            filters_applied=[],
        )
    )
    provider = FakeProvider(
        GenerationResult(
            raw_content='{"answer_status": "ok"',
            model="qwen",
            provider="ollama",
            finish_reason="stop",
            latency_ms=10,
        )
    )
    settings = study_settings()
    settings.generation.schema_repair_retries = 0
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
        settings=settings,
    )

    response = await service.orchestrate(
        StudyRequest(query="repair", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "schema_validation_failed"
    assert response.generation.attempt_count == 1
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_orchestrate_schema_repair_failure_returns_fallback_sources() -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="repair", semantic_queries=["repair"])
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="repair",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["repair"],
            filters_applied=[],
        )
    )
    provider = FakeProvider(
        [
            GenerationResult(
                raw_content='{"answer_status": "ok"',
                model="qwen",
                provider="ollama",
                finish_reason="stop",
                latency_ms=10,
            ),
            GenerationResult(
                raw_content='{"answer_status": "ok"',
                model="qwen",
                provider="ollama",
                finish_reason="stop",
                latency_ms=10,
            ),
        ]
    )
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="repair", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "schema_validation_failed"
    assert response.sources[0].chunk_id == "a"
    assert len(provider.calls) == 2


@pytest.mark.anyio
async def test_orchestrate_generation_timeout() -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="slow", semantic_queries=["slow"])
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="slow",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["slow"],
            filters_applied=[],
        )
    )

    provider = FakeProvider(valid_generation_result())
    provider.delay = 0.2  # Shorter than real timeout for test speed

    settings = study_settings()
    settings.generation.total_generation_deadline_seconds = 0.1

    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
        settings=settings,
    )

    response = await service.orchestrate(
        StudyRequest(query="slow", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "provider_timeout"


@pytest.mark.anyio
async def test_orchestrate_citation_cascade_failure() -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="bad_cite", semantic_queries=["bad_cite"])
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="bad_cite",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["bad_cite"],
            filters_applied=[],
        )
    )

    # Returns citation to "b" which wasn't in context
    provider = FakeProvider(valid_generation_result(chunk_id="b"))
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="bad_cite", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "citation_validation_cascade_failure"


@pytest.mark.anyio
async def test_orchestrate_planner_fallback_on_error() -> None:
    query_planner = FakeQueryPlanner(ProviderConnectionError("planner failed"))
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="orig",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["orig"],
            filters_applied=[],
        )
    )
    provider = FakeProvider(valid_generation_result(chunk_id="a"))
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="orig", scope={"collection": "cam-cs-tripos"})
    )

    assert response.planning.status == "fallback"
    assert response.planning.error_category == "provider_unreachable"
    assert response.planning.semantic_queries == ["orig"]
    # Verify retrieval used the fallback query
    assert planned_retrieval.calls[0]["plan"].semantic_queries == ["orig"]


@pytest.mark.anyio
async def test_orchestrate_planner_fallback_on_unexpected_error() -> None:
    query_planner = FakeQueryPlanner(RuntimeError("prompt rendering bug"))
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="orig",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["orig"],
            filters_applied=[],
        )
    )
    provider = FakeProvider(valid_generation_result(chunk_id="a"))
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="orig", scope={"collection": "cam-cs-tripos"})
    )

    assert response.planning.status == "fallback"
    assert response.planning.error_category == "provider_error"
    assert response.planning.semantic_queries == ["orig"]
    assert planned_retrieval.calls[0]["plan"].semantic_queries == ["orig"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("planner_error", "expected_category"),
    [
        (ProviderTimeoutError("slow"), "provider_timeout"),
        (ModelNotAvailableError("missing"), "model_not_available"),
        (ProviderHTTPError("upstream"), "provider_error"),
        (InvalidPlanError("bad"), "invalid_plan"),
        (ValidationError.from_exception_data("x", []), "schema_validation_failed"),
    ],
)
async def test_orchestrate_planner_error_categories(
    planner_error: Exception,
    expected_category: str,
) -> None:
    query_planner = FakeQueryPlanner(planner_error)
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="orig",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["orig"],
            filters_applied=[],
        )
    )
    provider = FakeProvider(valid_generation_result(chunk_id="a"))
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    response = await service.orchestrate(
        StudyRequest(query="orig", scope={"collection": "cam-cs-tripos"})
    )

    assert response.planning.status == "fallback"
    assert response.planning.error_category == expected_category


@pytest.mark.anyio
async def test_orchestrate_planner_deadline_exceeded() -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="slow", semantic_queries=["slow"])
    )
    query_planner.delay = 0.2

    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="slow",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["slow"],
            filters_applied=[],
        )
    )
    provider = FakeProvider(valid_generation_result(chunk_id="a"))

    settings = study_settings()
    settings.planning.total_planning_deadline_seconds = 0.1

    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
        settings=settings,
    )

    response = await service.orchestrate(
        StudyRequest(query="slow", scope={"collection": "cam-cs-tripos"})
    )

    assert response.planning.status == "fallback"
    assert response.planning.error_category == "planning_deadline_exceeded"


@pytest.mark.anyio
async def test_orchestrate_category_filtering_passed_to_planner_and_retrieval() -> None:
    query_planner = FakeQueryPlanner(
        QueryPlan(original_query="cat", semantic_queries=["cat"])
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="cat",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            ),
            executed_queries=["cat"],
            filters_applied=[
                FilterCondition(field="topic", op="eq", value="Algorithms")
            ],
        )
    )
    provider = FakeProvider(valid_generation_result(chunk_id="a"))
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
    )

    filters = [FilterCondition(field="topic", op="eq", value="Algorithms")]
    response = await service.orchestrate(
        StudyRequest(
            query="cat", scope={"collection": "cam-cs-tripos"}, filters=filters
        )
    )

    assert query_planner.calls[0]["hard_filters"] == filters
    assert planned_retrieval.calls[0]["hard_filters"] == filters
    assert response.retrieval.filters_applied == filters
