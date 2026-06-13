from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from src.metadata_schema.models import FilterCondition
from src.runtime.telemetry import HealthStatus, TokenUsage
from src.study.config import PlanningSettings
from src.study.models import GenerationRequest, GenerationResult, ProviderCapabilities
from src.study.planning.models import InvalidPlanError, QueryPlanDraft
from src.study.planning.planner import LLMQueryPlanner, RawQueryPlanner


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

    async def stream_generate(self, request: GenerationRequest):
        yield

    async def health(self) -> HealthStatus:
        return "ok"


def _result(payload: object) -> GenerationResult:
    return GenerationResult(
        raw_content=json.dumps(payload),
        model="planner-model",
        provider="openai_compatible",
        finish_reason="stop",
        latency_ms=7,
        usage=TokenUsage(input_tokens=11, output_tokens=7, total_tokens=18),
    )


def _settings() -> PlanningSettings:
    return PlanningSettings(prompt_path="prompts/query_planner_v1.yaml")


@pytest.mark.anyio
async def test_happy_path_builds_server_owned_plan() -> None:
    provider = FakeProvider(
        {"semantic_queries": ["  binary search  "], "intent": "content_retrieval"}
    )
    planner = LLMQueryPlanner(provider, _settings())

    result = await planner.plan(
        "  2024 paper 2 binary search invariant proofs  ",
        [
            FilterCondition(field="year", op="eq", value=2024),
            FilterCondition(field="paper", op="eq", value=2),
        ],
    )

    assert result.plan.planner_version == "query_planner_v1"
    assert (
        result.plan.original_query == "  2024 paper 2 binary search invariant proofs  "
    )
    assert result.plan.semantic_queries == ["binary search"]
    assert result.telemetry.provider == "openai_compatible"
    assert result.telemetry.model == "planner-model"
    assert result.telemetry.usage is not None
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_plan_uses_configured_prompt_version_when_prompt_matches(
    tmp_path,
) -> None:
    prompt_path = tmp_path / "query_planner_custom.yaml"
    prompt_path.write_text(
        """
version: query_planner_custom
system: Plan one query.
user: "{{ raw_query }}"
""",
        encoding="utf-8",
    )
    settings = PlanningSettings(
        prompt_version="query_planner_custom",
        prompt_path=str(prompt_path),
    )
    provider = FakeProvider(
        {"semantic_queries": ["binary trees"], "intent": "content_retrieval"}
    )
    planner = LLMQueryPlanner(provider, settings)

    result = await planner.plan("binary trees", None)

    assert result.plan.planner_version == "query_planner_custom"


def test_prompt_version_must_match_loaded_prompt_template(tmp_path) -> None:
    prompt_path = tmp_path / "query_planner_custom.yaml"
    prompt_path.write_text(
        """
version: query_planner_custom
system: Plan one query.
user: "{{ raw_query }}"
""",
        encoding="utf-8",
    )
    settings = PlanningSettings(
        prompt_version="query_planner_wrong",
        prompt_path=str(prompt_path),
    )
    provider = FakeProvider(
        {"semantic_queries": ["binary trees"], "intent": "content_retrieval"}
    )

    with pytest.raises(ValueError, match="planning.prompt_version must match"):
        LLMQueryPlanner(provider, settings)


@pytest.mark.anyio
async def test_sends_draft_schema_when_provider_supports_json_schema() -> None:
    provider = FakeProvider(
        {"semantic_queries": ["recursion trees"], "intent": "content_retrieval"}
    )
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
    provider = FakeProvider(
        {"semantic_queries": ["   "], "intent": "content_retrieval"}
    )
    planner = LLMQueryPlanner(provider, _settings())

    with pytest.raises(InvalidPlanError):
        await planner.plan(
            "2024 paper 1",
            [
                FilterCondition(field="year", op="eq", value=2024),
                FilterCondition(field="paper", op="eq", value=1),
            ],
        )


@pytest.mark.anyio
async def test_over_40_word_semantic_query_raises_invalid_plan_error() -> None:
    provider = FakeProvider(
        {
            "semantic_queries": [" ".join(f"word{i}" for i in range(41))],
            "intent": "content_retrieval",
        }
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
    provider = FakeProvider(
        {"semantic_queries": ["graph search"], "intent": "content_retrieval"}
    )
    planner = LLMQueryPlanner(provider, settings)

    await planner.plan("graph search", None)

    request = provider.calls[0]
    assert request.temperature == 0.25
    assert request.timeout_seconds == 3.5
    assert request.max_tokens is None


@pytest.mark.anyio
async def test_prompt_messages_include_raw_query_and_filters() -> None:
    raw_query = "2025 Databases paper 3 relational algebra joins"
    provider = FakeProvider(
        {
            "semantic_queries": ["relational algebra joins"],
            "intent": "content_retrieval",
        }
    )
    planner = LLMQueryPlanner(provider, _settings())

    await planner.plan(
        raw_query,
        [
            FilterCondition(field="year", op="eq", value=2025),
            FilterCondition(field="topic", op="eq", value="Databases"),
            FilterCondition(field="marks", op="gte", value=10),
            FilterCondition(field="difficulty_band", op="eq", value="hard"),
        ],
    )

    messages = provider.calls[0].messages
    system = messages[0]["content"]
    user = messages[1]["content"]

    assert messages[0]["role"] == "system"
    assert "year" in system
    assert "topic" in system
    assert "difficulty_band" in system
    assert raw_query in user
    assert '"field": "topic"' in user
    assert '"op": "gte"' in user
    assert '"field": "marks"' in user
    assert '"field": "difficulty_band"' in user


@pytest.mark.anyio
async def test_raw_query_planner_returns_raw_query_without_provider_call() -> None:
    provider = FakeProvider(
        {"semantic_queries": ["unused"], "intent": "content_retrieval"}
    )
    planner = RawQueryPlanner()

    result = await planner.plan(
        "messy original query",
        [FilterCondition(field="year", op="eq", value=2025)],
    )

    assert result.plan.original_query == "messy original query"
    assert result.plan.semantic_queries == ["messy original query"]
    assert provider.calls == []


def _draft_payload(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "semantic_queries": ["binary search"],
        "intent": "content_retrieval",
        "generation_guidance": "",
    }
    base.update(over)
    return base


@pytest.mark.anyio
async def test_build_plan_propagates_intent_and_guidance() -> None:
    provider = FakeProvider(
        _draft_payload(intent="corpus_analytics", generation_guidance="be concise")
    )
    planner = LLMQueryPlanner(provider, _settings())

    result = await planner.plan("how many db questions since 2019", None)

    assert result.plan.intent == "corpus_analytics"
    assert result.plan.generation_guidance == "be concise"


@pytest.mark.anyio
async def test_build_plan_rejects_overlong_guidance() -> None:
    provider = FakeProvider(
        _draft_payload(generation_guidance=" ".join(f"w{i}" for i in range(101)))
    )
    planner = LLMQueryPlanner(provider, _settings())

    with pytest.raises(InvalidPlanError):
        await planner.plan("q", None)


@pytest.mark.anyio
async def test_raw_query_planner_defaults_intent() -> None:
    result = await RawQueryPlanner().plan("messy query", None)
    assert result.plan.intent == "content_retrieval"
    assert result.plan.generation_guidance == ""
