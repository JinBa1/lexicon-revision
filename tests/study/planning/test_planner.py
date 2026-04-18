from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from src.study.config import PlanningSettings
from src.study.models import GenerationRequest, GenerationResult, ProviderCapabilities
from src.study.planning.models import InvalidPlanError, QueryPlanDraft, StudyFilters
from src.study.planning.planner import LLMQueryPlanner, RawQueryPlanner
from src.study.providers.base import GeneratorHealth


class FakeProvider:
    capabilities = ProviderCapabilities(
        json_schema_output=True,
        json_mode=True,
        max_context_tokens=32768,
    )

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls.append(request)
        if isinstance(self.payload, GenerationResult):
            return self.payload
        return _result(self.payload)

    async def health(self) -> GeneratorHealth:
        return "ok"


def _result(payload: object) -> GenerationResult:
    return GenerationResult(
        raw_content=json.dumps(payload),
        model="qwen2.5:7b-instruct",
        provider="ollama",
        finish_reason="stop",
        latency_ms=7,
    )


def _settings() -> PlanningSettings:
    return PlanningSettings(prompt_path="prompts/query_planner_v1.yaml")


@pytest.mark.anyio
async def test_happy_path_builds_server_owned_plan() -> None:
    provider = FakeProvider(
        {"semantic_queries": ["  binary search invariant proofs  "]}
    )
    planner = LLMQueryPlanner(provider, _settings())

    plan = await planner.plan(
        "  2024 paper 2 binary search invariant proofs  ",
        StudyFilters(year=2024, paper=2),
    )

    assert plan.planner_version == "query_planner_v1"
    assert plan.original_query == "  2024 paper 2 binary search invariant proofs  "
    assert plan.semantic_queries == ["binary search invariant proofs"]
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_sends_draft_schema_when_provider_supports_json_schema() -> None:
    provider = FakeProvider({"semantic_queries": ["recursion trees"]})
    planner = LLMQueryPlanner(provider, _settings())

    await planner.plan("recursion trees", None)

    assert provider.calls[0].response_schema == QueryPlanDraft.model_json_schema()


@pytest.mark.anyio
async def test_invalid_json_raises_validation_error() -> None:
    provider = FakeProvider(
        GenerationResult(
            raw_content="{not json",
            model="qwen2.5:7b-instruct",
            provider="ollama",
            finish_reason="stop",
            latency_ms=7,
        )
    )
    planner = LLMQueryPlanner(provider, _settings())

    with pytest.raises(ValidationError):
        await planner.plan("recursion", None)


@pytest.mark.anyio
async def test_empty_semantic_query_raises_invalid_plan_error() -> None:
    provider = FakeProvider({"semantic_queries": ["   "]})
    planner = LLMQueryPlanner(provider, _settings())

    with pytest.raises(InvalidPlanError):
        await planner.plan("2024 paper 1", StudyFilters(year=2024, paper=1))


@pytest.mark.anyio
async def test_over_40_word_semantic_query_raises_invalid_plan_error() -> None:
    provider = FakeProvider(
        {"semantic_queries": [" ".join(f"word{i}" for i in range(41))]}
    )
    planner = LLMQueryPlanner(provider, _settings())

    with pytest.raises(InvalidPlanError):
        await planner.plan("long query", None)


@pytest.mark.anyio
async def test_request_uses_settings_temperature_and_timeout() -> None:
    settings = PlanningSettings(
        prompt_path="prompts/query_planner_v1.yaml",
        temperature=0.25,
        request_timeout_seconds=3.5,
    )
    provider = FakeProvider({"semantic_queries": ["graph search"]})
    planner = LLMQueryPlanner(provider, settings)

    await planner.plan("graph search", None)

    request = provider.calls[0]
    assert request.temperature == 0.25
    assert request.timeout_seconds == 3.5
    assert request.max_tokens is None


@pytest.mark.anyio
async def test_prompt_messages_include_raw_query_and_filters() -> None:
    raw_query = "2025 Databases paper 3 relational algebra joins"
    provider = FakeProvider({"semantic_queries": ["relational algebra joins"]})
    planner = LLMQueryPlanner(provider, _settings())

    await planner.plan(raw_query, StudyFilters(year=2025, topic="Databases"))

    messages = provider.calls[0].messages
    system = messages[0]["content"]
    user = messages[1]["content"]

    assert messages[0]["role"] == "system"
    assert "year" in system
    assert "- topic:" not in system
    assert raw_query in user
    assert "Databases" in user


@pytest.mark.anyio
async def test_raw_query_planner_returns_raw_query_without_provider_call() -> None:
    provider = FakeProvider({"semantic_queries": ["unused"]})
    planner = RawQueryPlanner()

    plan = await planner.plan("messy original query", StudyFilters(year=2025))

    assert plan.original_query == "messy original query"
    assert plan.semantic_queries == ["messy original query"]
    assert provider.calls == []
