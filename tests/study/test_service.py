from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from src.search.models import SearchResponse, SearchResult
from src.study.config import (
    ContextSettings,
    GenerationSettings,
    PromptSettings,
    StudySettings,
)
from src.study.models import GenerationRequest, GenerationResult, StudyRequest
from src.study.providers.base import (
    ModelNotAvailableError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderTimeoutError,
)
from src.study.service import StudyService


class FakeSearchService:
    def __init__(self, response: SearchResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> SearchResponse:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeProvider:
    capabilities = type(
        "Capabilities",
        (),
        {"json_schema_output": True, "json_mode": True, "max_context_tokens": 32768},
    )()

    def __init__(self, result: GenerationResult | Exception) -> None:
        self.result = result
        self.calls: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def health(self) -> str:
        return "ok"


def search_result(
    chunk_id: str,
    text: str = "dynamic programming recurrence",
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        text=text,
        score=0.9,
        metadata={
            "year": 2023,
            "paper": 2,
            "question_number": 4,
            "topic": "Algorithms",
            "chunk_level": "question",
            "parent_chunk_id": None,
            "sub_question_label": None,
        },
        media=[],
    )


def study_settings() -> StudySettings:
    return StudySettings(
        generation=GenerationSettings(request_timeout_seconds=5),
        context=ContextSettings(budget_tokens=4000, max_single_chunk_tokens=1200),
        prompt=PromptSettings(version="study_aid_v1", path="prompts/study_aid_v1.yaml"),
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
                "overview": "Recovered.",
                "patterns": [],
                "cited_sources": [
                    {
                        "chunk_id": chunk_id,
                        "why_cited": "Recovered citation.",
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


@pytest.mark.anyio
async def test_orchestrate_empty_retrieval_skips_generation() -> None:
    search = FakeSearchService(
        SearchResponse(query="dp", collection="cam-cs-tripos", results=[], total=0)
    )
    provider = FakeProvider(
        GenerationResult(
            raw_content="{}",
            model="m",
            provider="p",
            finish_reason="stop",
            latency_ms=1,
        )
    )
    service = StudyService(
        search_service=search,
        provider=provider,
        settings=study_settings(),
    )

    response = await service.orchestrate(
        StudyRequest(query="dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "insufficient_evidence"
    assert response.retrieval.status == "empty"
    assert response.sources == []
    assert provider.calls == []
    assert search.calls == [
        {
            "query": "dp",
            "collection": "cam-cs-tripos",
            "filters": None,
            "limit": 15,
            "rerank": True,
        }
    ]


@pytest.mark.anyio
async def test_orchestrate_happy_path_uses_union_sources() -> None:
    draft = {
        "answer_status": "ok",
        "overview": "In the retrieved questions, DP appears as recurrence design.",
        "patterns": [
            {
                "label": "Recurrence design",
                "summary": "Questions ask for a recurrence.",
                "supporting_chunk_ids": ["a"],
            }
        ],
        "cited_sources": [
            {"chunk_id": "b", "why_cited": "Related table-filling variant."}
        ],
        "limitations": [],
    }
    search = FakeSearchService(
        SearchResponse(
            query="dp",
            collection="cam-cs-tripos",
            results=[search_result("a"), search_result("b", "table filling DP")],
            total=2,
        )
    )
    provider = FakeProvider(
        GenerationResult(
            raw_content=json.dumps(draft),
            model="qwen2.5:7b-instruct",
            provider="ollama",
            finish_reason="stop",
            latency_ms=12,
        )
    )
    service = StudyService(
        search_service=search,
        provider=provider,
        settings=study_settings(),
    )

    response = await service.orchestrate(
        StudyRequest(query="dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "ok"
    assert response.generation.error_category is None
    assert response.answer.patterns[0].supporting_chunk_ids == ["a"]
    assert {source.chunk_id for source in response.sources} == {"a", "b"}
    by_chunk_id = {source.chunk_id: source for source in response.sources}
    assert by_chunk_id["a"].why_cited is None
    assert by_chunk_id["b"].why_cited == "Related table-filling variant."
    assert by_chunk_id["a"].question_ref == "Q4"
    assert provider.calls[0].response_schema is not None


@pytest.mark.anyio
async def test_orchestrate_provider_failure_returns_fallback_sources() -> None:
    provider = FakeProvider(ProviderConnectionError("offline"))
    service = StudyService(
        search_service=FakeSearchService(
            SearchResponse(
                query="dp",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            )
        ),
        provider=provider,
        settings=study_settings(),
    )

    response = await service.orchestrate(
        StudyRequest(query="dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "provider_unreachable"
    assert response.generation.attempt_count == 1
    assert response.sources[0].chunk_id == "a"
    assert response.sources[0].why_cited is None
    assert len(provider.calls) == 1


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
    provider = FakeProvider(provider_error)
    service = StudyService(
        search_service=FakeSearchService(
            SearchResponse(
                query="dp",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            )
        ),
        provider=provider,
        settings=study_settings(),
    )

    response = await service.orchestrate(
        StudyRequest(query="dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == expected_category
    assert response.sources[0].chunk_id == "a"
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_orchestrate_retrieval_error_returns_retrieval_failed() -> None:
    provider = FakeProvider(valid_generation_result())
    service = StudyService(
        search_service=FakeSearchService(RuntimeError("chroma offline")),
        provider=provider,
        settings=study_settings(),
    )

    response = await service.orchestrate(
        StudyRequest(query="dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "retrieval_failed"
    assert response.retrieval.status == "error"
    assert response.sources == []
    assert provider.calls == []


@pytest.mark.anyio
async def test_orchestrate_filtered_empty_reports_filtered_empty() -> None:
    service = StudyService(
        search_service=FakeSearchService(
            SearchResponse(query="dp", collection="cam-cs-tripos", results=[], total=0)
        ),
        provider=FakeProvider(valid_generation_result()),
        settings=study_settings(),
    )

    response = await service.orchestrate(
        StudyRequest(
            query="dp",
            scope={"collection": "cam-cs-tripos"},
            filters={"year": 2023},
        )
    )

    assert response.answer_status == "insufficient_evidence"
    assert response.retrieval.status == "filtered_empty"
    assert response.retrieval.filters_applied == {"year": 2023}


@pytest.mark.anyio
async def test_orchestrate_empty_retrieval_ignores_null_filters() -> None:
    search = FakeSearchService(
        SearchResponse(query="dp", collection="cam-cs-tripos", results=[], total=0)
    )
    service = StudyService(
        search_service=search,
        provider=FakeProvider(valid_generation_result()),
        settings=study_settings(),
    )

    response = await service.orchestrate(
        StudyRequest(
            query="dp",
            scope={"collection": "cam-cs-tripos"},
            filters={"year": None},
        )
    )

    assert response.answer_status == "insufficient_evidence"
    assert response.retrieval.status == "empty"
    assert response.retrieval.filters_applied == {}
    assert search.calls[0]["filters"] is None


@pytest.mark.anyio
async def test_orchestrate_repairs_schema_validation_once() -> None:
    class RepairProvider(FakeProvider):
        async def generate(self, request: GenerationRequest) -> GenerationResult:
            self.calls.append(request)
            if len(self.calls) == 1:
                return GenerationResult(
                    raw_content='{"answer_status": "ok"',
                    model="qwen2.5:7b-instruct",
                    provider="ollama",
                    finish_reason="length",
                    latency_ms=10,
                )
            return valid_generation_result()

    provider = RepairProvider(
        GenerationResult(
            raw_content="",
            model="m",
            provider="p",
            finish_reason="stop",
            latency_ms=1,
        )
    )
    service = StudyService(
        search_service=FakeSearchService(
            SearchResponse(
                query="dp",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            )
        ),
        provider=provider,
        settings=study_settings(),
    )

    response = await service.orchestrate(
        StudyRequest(query="dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "ok"
    assert response.sources[0].why_cited == "Recovered citation."
    assert response.generation.attempt_count == 2
    assert len(provider.calls) == 2
    assert provider.calls[1].messages[-1]["role"] == "user"
    assert '{"answer_status": "ok"' in provider.calls[1].messages[-1]["content"]
    assert "validation error" in provider.calls[1].messages[-1]["content"].lower()


@pytest.mark.anyio
async def test_orchestrate_repairs_when_retry_count_is_positive() -> None:
    class RepairProvider(FakeProvider):
        async def generate(self, request: GenerationRequest) -> GenerationResult:
            self.calls.append(request)
            if len(self.calls) == 1:
                return GenerationResult(
                    raw_content='{"answer_status": "ok"',
                    model="qwen2.5:7b-instruct",
                    provider="ollama",
                    finish_reason="length",
                    latency_ms=10,
                )
            return valid_generation_result()

    settings = study_settings()
    settings.generation.schema_repair_retries = 2
    provider = RepairProvider(valid_generation_result())
    service = StudyService(
        search_service=FakeSearchService(
            SearchResponse(
                query="dp",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            )
        ),
        provider=provider,
        settings=settings,
    )

    response = await service.orchestrate(
        StudyRequest(query="dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "ok"
    assert response.generation.attempt_count == 2
    assert len(provider.calls) == 2


@pytest.mark.anyio
async def test_orchestrate_does_not_repair_when_retry_count_is_zero() -> None:
    settings = study_settings()
    settings.generation.schema_repair_retries = 0
    provider = FakeProvider(
        GenerationResult(
            raw_content='{"answer_status": "ok"',
            model="qwen2.5:7b-instruct",
            provider="ollama",
            finish_reason="length",
            latency_ms=10,
        )
    )
    service = StudyService(
        search_service=FakeSearchService(
            SearchResponse(
                query="dp",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            )
        ),
        provider=provider,
        settings=settings,
    )

    response = await service.orchestrate(
        StudyRequest(query="dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "schema_validation_failed"
    assert response.generation.attempt_count == 1
    assert response.sources[0].chunk_id == "a"
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_orchestrate_schema_repair_failure_returns_fallback_sources() -> None:
    class BrokenProvider(FakeProvider):
        async def generate(self, request: GenerationRequest) -> GenerationResult:
            self.calls.append(request)
            return GenerationResult(
                raw_content='{"answer_status": "ok"',
                model="qwen2.5:7b-instruct",
                provider="ollama",
                finish_reason="length",
                latency_ms=10,
            )

    provider = BrokenProvider(valid_generation_result())
    service = StudyService(
        search_service=FakeSearchService(
            SearchResponse(
                query="dp",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            )
        ),
        provider=provider,
        settings=study_settings(),
    )

    response = await service.orchestrate(
        StudyRequest(query="dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "schema_validation_failed"
    assert response.sources[0].chunk_id == "a"
    assert response.sources[0].why_cited is None
    assert len(provider.calls) == 2


@pytest.mark.anyio
async def test_orchestrate_total_generation_deadline_returns_timeout_fallback() -> None:
    class SlowProvider(FakeProvider):
        async def generate(self, request: GenerationRequest) -> GenerationResult:
            self.calls.append(request)
            await asyncio.sleep(0.05)
            return valid_generation_result()

    settings = study_settings()
    settings.generation.total_generation_deadline_seconds = 0.01
    provider = SlowProvider(valid_generation_result())
    service = StudyService(
        search_service=FakeSearchService(
            SearchResponse(
                query="dp",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            )
        ),
        provider=provider,
        settings=settings,
    )

    response = await service.orchestrate(
        StudyRequest(query="dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "provider_timeout"
    assert response.generation.attempt_count == 1
    assert response.sources[0].chunk_id == "a"
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_orchestrate_repair_provider_failure_returns_fallback_sources() -> None:
    class TimeoutOnRepairProvider(FakeProvider):
        async def generate(self, request: GenerationRequest) -> GenerationResult:
            self.calls.append(request)
            if len(self.calls) == 1:
                return GenerationResult(
                    raw_content='{"answer_status": "ok"',
                    model="qwen2.5:7b-instruct",
                    provider="ollama",
                    finish_reason="length",
                    latency_ms=10,
                )
            raise ProviderTimeoutError("repair timed out")

    provider = TimeoutOnRepairProvider(valid_generation_result())
    service = StudyService(
        search_service=FakeSearchService(
            SearchResponse(
                query="dp",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            )
        ),
        provider=provider,
        settings=study_settings(),
    )

    response = await service.orchestrate(
        StudyRequest(query="dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "provider_timeout"
    assert response.generation.attempt_count == 2
    assert response.sources[0].chunk_id == "a"
    assert len(provider.calls) == 2


@pytest.mark.anyio
async def test_orchestrate_all_invalid_citations_returns_fallback_sources() -> None:
    provider = FakeProvider(
        GenerationResult(
            raw_content=json.dumps(
                {
                    "answer_status": "ok",
                    "overview": "Ungrounded.",
                    "patterns": [
                        {
                            "label": "Invalid",
                            "summary": "Invalid support.",
                            "supporting_chunk_ids": ["missing"],
                        }
                    ],
                    "cited_sources": [
                        {"chunk_id": "also-missing", "why_cited": "Bad citation."}
                    ],
                    "limitations": [],
                }
            ),
            model="qwen2.5:7b-instruct",
            provider="ollama",
            finish_reason="stop",
            latency_ms=10,
        )
    )
    service = StudyService(
        search_service=FakeSearchService(
            SearchResponse(
                query="dp",
                collection="cam-cs-tripos",
                results=[search_result("a")],
                total=1,
            )
        ),
        provider=provider,
        settings=study_settings(),
    )

    response = await service.orchestrate(
        StudyRequest(query="dp", scope={"collection": "cam-cs-tripos"})
    )

    assert response.answer_status == "generation_failed"
    assert response.generation.error_category == "citation_validation_cascade_failure"
    assert response.generation.citation_drops == 2
    assert response.sources[0].chunk_id == "a"
    assert response.sources[0].why_cited is None
