from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from pydantic import ValidationError
from src.metadata_schema.models import FilterCondition
from src.runtime.config import AppRuntimeSettings, RateLimitSettings
from src.runtime.telemetry import HealthStatus, ProviderCallTelemetry, TokenUsage
from src.search.models import SearchResponse, SearchResult
from src.search.pg_service import SearchExecutionTelemetry
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
    PlannerExecution,
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
        self,
        plan: PlannerExecution
        | QueryPlan
        | Exception
        | list[PlannerExecution | QueryPlan | Exception],
    ) -> None:
        self.plan_results = plan if isinstance(plan, list) else [plan]
        self.calls: list[dict[str, Any]] = []
        self.delay: float = 0

    async def plan(
        self,
        raw_query: str,
        hard_filters: list[FilterCondition] | None,
    ) -> PlannerExecution:
        self.calls.append({"raw_query": raw_query, "hard_filters": hard_filters})
        if self.delay:
            await asyncio.sleep(self.delay)
        result = self.plan_results.pop(0)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, QueryPlan):
            return planner_execution(result)
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

    async def stream_generate(self, request: GenerationRequest):
        yield

    async def health(self) -> HealthStatus:
        return "ok"


def search_result(
    chunk_id: str = "a",
    text: str = "dynamic programming recurrence",
    *,
    chunk_level: str = "question",
    parent_chunk_id: str | None = None,
    sub_question_label: str | None = None,
    render_blocks: list[dict[str, Any]] | None = None,
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
        render_blocks=render_blocks,
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
            version="study_aid_v3",
            path="prompts/study_aid_v3.yaml",
        ),
        planning=PlanningSettings(
            request_timeout_seconds=5,
            total_planning_deadline_seconds=10,
            prompt_version="query_planner_v1",
            prompt_path="prompts/query_planner_v1.yaml",
        ),
    )


def runtime_settings(
    *,
    study_context_budget_tokens: int = 4000,
    study_generation_max_output_tokens: int = 1200,
) -> AppRuntimeSettings:
    return AppRuntimeSettings(
        environment="test",
        enable_dev_routes=False,
        cors_allowed_origins=[],
        request_body_max_bytes=131072,
        query_max_chars=2000,
        search_limit_max=50,
        study_top_k_max=20,
        study_context_budget_tokens=study_context_budget_tokens,
        study_generation_max_output_tokens=study_generation_max_output_tokens,
        study_wall_clock_timeout_seconds=45,
        rate_limit=rate_limit_settings(),
    )


def rate_limit_settings() -> RateLimitSettings:
    return RateLimitSettings(
        redis_url="redis://localhost:6379/0",
        key_secret="test-rate-limit-secret",
        search_user="60/minute",
        search_anon="20/minute",
        study_user="10/hour",
        study_anon="3/hour",
    )


def planner_execution(plan: QueryPlan) -> PlannerExecution:
    return PlannerExecution(
        plan=plan,
        telemetry=ProviderCallTelemetry(
            provider="openai_compatible",
            model="planner-model",
            latency_ms=9,
            usage=TokenUsage(input_tokens=11, output_tokens=7, total_tokens=18),
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
        usage=TokenUsage(input_tokens=14, output_tokens=9, total_tokens=23),
    )


def make_service(
    *,
    query_planner: FakeQueryPlanner,
    planned_retrieval: FakePlannedRetrieval,
    provider: FakeProvider,
    settings: StudySettings | None = None,
    runtime: AppRuntimeSettings | None = None,
) -> StudyService:
    return StudyService(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
        settings=settings or study_settings(),
        runtime_settings=runtime,
    )


@pytest.mark.anyio
async def test_orchestrate_happy_path_records_planning_and_uses_planned_query() -> None:
    plan = QueryPlan(
        original_query="2025 dp",
        semantic_queries=["dynamic programming recurrence"],
    )
    query_planner = FakeQueryPlanner(planner_execution(plan))
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
            search_telemetry=SearchExecutionTelemetry(
                embedding=ProviderCallTelemetry(
                    provider="voyage",
                    model="voyage-4-lite",
                    latency_ms=12,
                    usage=None,
                ),
                rerank=None,
            ),
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
    assert response.planning.telemetry is not None
    assert response.planning.telemetry.provider == "openai_compatible"
    assert response.planning.telemetry.model == "planner-model"
    assert response.planning.telemetry.usage is not None
    assert response.retrieval.search_telemetry is not None
    assert response.retrieval.search_telemetry.embedding.provider == "voyage"
    assert response.retrieval.search_telemetry.rerank is None
    assert response.generation.error_category is None
    assert response.generation.usage is not None
    assert response.generation.usage.total_tokens == 23
    assert response.generation.latency_ms == 10
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
async def test_orchestrate_uses_provided_request_id() -> None:
    plan = QueryPlan(
        original_query="2025 dp",
        semantic_queries=["dynamic programming recurrence"],
    )
    query_planner = FakeQueryPlanner(planner_execution(plan))
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
        StudyRequest(query="2025 dp", scope={"collection": "cam-cs-tripos"}),
        request_id="req-study-123",
    )

    assert response.request_id == "req-study-123"


@pytest.mark.anyio
async def test_orchestrate_preserves_sub_question_label_on_sources() -> None:
    query_planner = FakeQueryPlanner(
        planner_execution(
            QueryPlan(original_query="q", semantic_queries=["dynamic programming"])
        )
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
async def test_orchestrate_builds_excerpt_blocks_from_search_result_blocks() -> None:
    render_blocks = [
        {"type": "paragraph", "runs": [{"type": "text", "text": "A" * 400}]},
        {"type": "paragraph", "runs": [{"type": "text", "text": "B" * 200}]},
    ]
    query_planner = FakeQueryPlanner(
        planner_execution(
            QueryPlan(original_query="q", semantic_queries=["dynamic programming"])
        )
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="dynamic programming",
                collection="cam-cs-tripos",
                results=[
                    search_result("a", text="A" * 600, render_blocks=render_blocks)
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

    assert response.sources[0].excerpt == "A" * 500
    assert response.sources[0].model_dump(mode="json")["excerpt_blocks"] == [
        render_blocks[0]
    ]


@pytest.mark.anyio
async def test_orchestrate_empty_retrieval_skips_generation() -> None:
    query_planner = FakeQueryPlanner(
        planner_execution(
            QueryPlan(original_query="missing", semantic_queries=["missing"])
        )
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="missing", collection="cam-cs-tripos", results=[], total=0
            ),
            executed_queries=["missing"],
            filters_applied=[],
            search_telemetry=SearchExecutionTelemetry(
                embedding=ProviderCallTelemetry(
                    provider="voyage",
                    model="voyage-4-lite",
                    latency_ms=12,
                    usage=None,
                ),
                rerank=None,
            ),
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
    assert response.retrieval.search_telemetry is not None
    assert response.retrieval.search_telemetry.embedding.provider == "voyage"
    assert response.generation.usage is None
    assert response.generation.latency_ms == 0
    assert len(provider.calls) == 0


@pytest.mark.anyio
async def test_orchestrate_filtered_empty_retrieval() -> None:
    query_planner = FakeQueryPlanner(
        planner_execution(
            QueryPlan(original_query="filtered", semantic_queries=["filtered"])
        )
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
        planner_execution(QueryPlan(original_query="err", semantic_queries=["err"]))
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
        planner_execution(QueryPlan(original_query="fail", semantic_queries=["fail"]))
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
        planner_execution(QueryPlan(original_query="fail", semantic_queries=["fail"]))
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
        planner_execution(
            QueryPlan(original_query="repair", semantic_queries=["repair"])
        )
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
        planner_execution(
            QueryPlan(original_query="repair", semantic_queries=["repair"])
        )
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
        planner_execution(
            QueryPlan(original_query="repair", semantic_queries=["repair"])
        )
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
        planner_execution(QueryPlan(original_query="slow", semantic_queries=["slow"]))
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
        planner_execution(
            QueryPlan(original_query="bad_cite", semantic_queries=["bad_cite"])
        )
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
        planner_execution(QueryPlan(original_query="slow", semantic_queries=["slow"]))
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
        planner_execution(QueryPlan(original_query="cat", semantic_queries=["cat"]))
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


def _plan() -> QueryPlan:
    return QueryPlan(
        original_query="2025 dp",
        semantic_queries=["dynamic programming recurrence"],
    )


def _retrieval_with_results() -> PlannedRetrievalResult:
    return PlannedRetrievalResult(
        search_response=SearchResponse(
            query="dynamic programming recurrence",
            collection="c",
            results=[search_result("a")],
            total=1,
        ),
        executed_queries=["dynamic programming recurrence"],
        filters_applied=[],
    )


@pytest.mark.anyio
async def test_orchestrate_surfaces_plan_intent_in_planning_metadata() -> None:
    plan = QueryPlan(
        original_query="2025 dp",
        semantic_queries=["dynamic programming recurrence"],
        intent="content_retrieval",
        generation_guidance="emphasise patterns",
    )
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(plan)),
        planned_retrieval=FakePlannedRetrieval(_retrieval_with_results()),
        provider=FakeProvider(valid_generation_result(chunk_id="a")),
    )
    response = await service.orchestrate(
        StudyRequest(query="2025 dp", scope={"collection": "c"})
    )
    assert response.planning.intent == "content_retrieval"


@pytest.mark.anyio
async def test_log_response_includes_intent(caplog) -> None:
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(_plan())),
        planned_retrieval=FakePlannedRetrieval(_retrieval_with_results()),
        provider=FakeProvider(valid_generation_result(chunk_id="a")),
    )
    with caplog.at_level("INFO"):
        await service.orchestrate(
            StudyRequest(query="2025 dp", scope={"collection": "c"})
        )
    record = next(r for r in caplog.records if r.message == "study_request")
    assert getattr(record, "intent", None) == "content_retrieval"


@pytest.mark.anyio
async def test_orchestrate_enforces_runtime_context_and_output_caps() -> None:
    query_planner = FakeQueryPlanner(
        planner_execution(QueryPlan(original_query="caps", semantic_queries=["caps"]))
    )
    planned_retrieval = FakePlannedRetrieval(
        PlannedRetrievalResult(
            search_response=SearchResponse(
                query="caps",
                collection="cam-cs-tripos",
                results=[search_result("a", text="x " * 200)],
                total=1,
            ),
            executed_queries=["caps"],
            filters_applied=[],
        )
    )
    provider = FakeProvider(valid_generation_result(chunk_id="a"))
    settings = study_settings()
    settings.context.budget_tokens = 4000
    service = make_service(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
        settings=settings,
        runtime=runtime_settings(
            study_context_budget_tokens=40,
            study_generation_max_output_tokens=120,
        ),
    )

    response = await service.orchestrate(
        StudyRequest(query="caps", scope={"collection": "cam-cs-tripos"})
    )

    assert response.retrieval.context_budget_tokens == 40
    assert provider.calls[0].max_tokens == 120


@pytest.mark.parametrize(
    "intent,kind_fragment",
    [
        ("corpus_analytics", "statistics"),
        ("ambiguous", "a bit broad"),
        ("out_of_scope", "outside this past-paper collection"),
    ],
)
@pytest.mark.anyio
async def test_direct_response_intents_short_circuit(intent, kind_fragment) -> None:
    plan = QueryPlan(original_query="x", semantic_queries=["x"], intent=intent)
    retrieval = FakePlannedRetrieval(_retrieval_with_results())
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(plan)),
        planned_retrieval=retrieval,
        provider=FakeProvider(valid_generation_result(chunk_id="a")),
    )
    response = await service.orchestrate(
        StudyRequest(query="x", scope={"collection": "c"})
    )

    assert response.answer_status == "no_corpus_answer"
    assert response.retrieval.status == "skipped"
    assert response.planning.intent == intent
    assert kind_fragment in response.answer.overview
    # retrieval + generation are skipped entirely
    assert retrieval.calls == []
    assert service.provider.calls == []  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_content_retrieval_routes_through_retrieval_workflow() -> None:
    # Misrouting guard (routing-deterministic half): content_retrieval must run
    # retrieval/generation and never produce no_corpus_answer.
    plan = QueryPlan(
        original_query="2025 dp", semantic_queries=["dynamic programming recurrence"]
    )
    retrieval = FakePlannedRetrieval(_retrieval_with_results())
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(plan)),
        planned_retrieval=retrieval,
        provider=FakeProvider(valid_generation_result(chunk_id="a")),
    )
    response = await service.orchestrate(
        StudyRequest(query="2025 dp", scope={"collection": "c"})
    )
    assert response.answer_status != "no_corpus_answer"
    assert retrieval.calls  # retrieval actually ran


@pytest.mark.anyio
async def test_generation_guidance_reaches_the_prompt() -> None:
    plan = QueryPlan(
        original_query="paging",
        semantic_queries=["virtual memory paging"],
        intent="content_retrieval",
        generation_guidance="Emphasise recurring patterns.",
    )
    provider = FakeProvider(valid_generation_result(chunk_id="a"))
    service = make_service(
        query_planner=FakeQueryPlanner(planner_execution(plan)),
        planned_retrieval=FakePlannedRetrieval(_retrieval_with_results()),
        provider=provider,
    )
    await service.orchestrate(StudyRequest(query="paging", scope={"collection": "c"}))
    user_msg = provider.calls[0].messages[1]["content"]
    assert "Emphasise recurring patterns." in user_msg


@pytest.mark.anyio
async def test_empty_guidance_adds_no_guidance_block() -> None:
    provider = FakeProvider(valid_generation_result(chunk_id="a"))
    service = make_service(
        query_planner=FakeQueryPlanner(
            planner_execution(_plan())
        ),  # guidance defaults ""
        planned_retrieval=FakePlannedRetrieval(_retrieval_with_results()),
        provider=provider,
    )
    await service.orchestrate(StudyRequest(query="2025 dp", scope={"collection": "c"}))
    assert "Guidance for this answer" not in provider.calls[0].messages[1]["content"]
