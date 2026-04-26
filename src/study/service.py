from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from src.metadata_schema.models import FilterCondition
from src.runtime.config import AppRuntimeSettings
from src.runtime.telemetry import ProviderCallTelemetry
from src.search.errors import InvalidMetadataFilterError
from src.search.models import SearchResponse, SearchResult
from src.search.pg_service import SearchExecutionTelemetry
from src.study.config import StudySettings
from src.study.excerpt_blocks import truncate_excerpt_blocks
from src.study.models import (
    AnswerStatus,
    ErrorCategory,
    GenerationMetadata,
    GenerationRequest,
    GenerationResult,
    RankedChunk,
    RetrievalMetadata,
    RetrievalStatus,
    StudyAnswer,
    StudyAnswerDraft,
    StudyRequest,
    StudyResponse,
    StudySource,
    ValidationResult,
)
from src.study.packing import (
    HeuristicTokenEstimator,
    dedupe_parent_child,
    format_context_blocks,
    pack_chunks,
)
from src.study.planning.models import (
    InvalidPlanError,
    PlannerExecution,
    PlanningErrorCategory,
    PlanningMetadata,
    QueryPlan,
)
from src.study.planning.planner import QueryPlanner
from src.study.planning.retrieval import PlannedRetrievalService
from src.study.prompts import load_prompt_template
from src.study.providers.base import (
    GenerationProvider,
    ModelNotAvailableError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderTimeoutError,
)
from src.study.validation import validate_citations

logger = logging.getLogger(__name__)
PROVIDER_ERRORS = (
    ProviderConnectionError,
    ProviderTimeoutError,
    ModelNotAvailableError,
    ProviderHTTPError,
)
STUDY_SOURCE_EXCERPT_CHARS = 500


class StudyService:
    def __init__(
        self,
        *,
        query_planner: QueryPlanner,
        planned_retrieval: PlannedRetrievalService,
        provider: GenerationProvider,
        settings: StudySettings,
        runtime_settings: AppRuntimeSettings | None = None,
    ) -> None:
        self.query_planner = query_planner
        self.planned_retrieval = planned_retrieval
        self.provider = provider
        self.settings = settings
        self.runtime_settings = runtime_settings
        self._prompt = load_prompt_template(Path(settings.prompt.path))

    async def orchestrate(
        self,
        request: StudyRequest,
        *,
        request_id: str | None = None,
    ) -> StudyResponse:
        request_id = request_id or str(uuid.uuid4())
        hard_filters = request.filters
        plan, planning_metadata = await self._plan(request.query, hard_filters)

        try:
            retrieval_result = self.planned_retrieval.retrieve(
                plan,
                hard_filters=hard_filters,
                collection=request.scope.collection,
                limit=request.top_k,
                rerank=True,
            )
            search_response = retrieval_result.search_response
            filters = retrieval_result.filters_applied
            collection_schema = retrieval_result.collection_schema
        except InvalidMetadataFilterError:
            raise
        except Exception:
            logger.exception(
                "study_retrieval_failed",
                extra={
                    "request_id": request_id,
                    "collection": request.scope.collection,
                    "planning_status": planning_metadata.status,
                    "planning_error_category": planning_metadata.error_category,
                    "planner_version": planning_metadata.planner_version,
                    "planning_latency_ms": planning_metadata.latency_ms,
                },
            )
            return self._empty_response(
                request=request,
                request_id=request_id,
                answer_status="retrieval_failed",
                retrieval_status="error",
                filters=list(hard_filters or []),
                planning=planning_metadata,
            )

        if not search_response.results:
            retrieval_status: RetrievalStatus = "filtered_empty" if filters else "empty"
            return self._empty_response(
                request=request,
                request_id=request_id,
                answer_status="insufficient_evidence",
                retrieval_status=retrieval_status,
                filters=filters,
                planning=planning_metadata,
                search_telemetry=retrieval_result.search_telemetry,
            )

        try:
            ranked_chunks = [
                _ranked_chunk(result) for result in search_response.results
            ]
            deduped_chunks = dedupe_parent_child(ranked_chunks)
            packing = pack_chunks(
                deduped_chunks,
                budget_tokens=self._context_budget_tokens(),
                max_single_chunk_tokens=self._max_single_chunk_tokens(),
                estimator=HeuristicTokenEstimator(),
            )
            retrieval = RetrievalMetadata(
                status="ok",
                top_k=request.top_k,
                returned_result_count=len(search_response.results),
                context_budget_tokens=self._context_budget_tokens(),
                context_chunk_ids=[packed.chunk.chunk_id for packed in packing.chunks],
                omitted_chunk_ids=packing.omitted_chunk_ids,
                truncated_chunk_ids=packing.truncated_chunk_ids,
                filters_applied=filters,
                rerank=True,
                search_telemetry=retrieval_result.search_telemetry,
            )
        except Exception:
            logger.exception(
                "study_context_build_failed",
                extra={"request_id": request_id},
            )
            retrieval = RetrievalMetadata(
                status="ok",
                top_k=request.top_k,
                returned_result_count=len(search_response.results),
                context_budget_tokens=self._context_budget_tokens(),
                context_chunk_ids=[],
                omitted_chunk_ids=[],
                truncated_chunk_ids=[],
                filters_applied=filters,
                rerank=True,
                search_telemetry=retrieval_result.search_telemetry,
            )
            return self._generation_failed_response(
                request=request,
                request_id=request_id,
                search_response=search_response,
                retrieval=retrieval,
                planning=planning_metadata,
                error_category="context_build_failed",
                attempt_count=0,
                generation_result=None,
            )

        if packing.status == "context_pack_failed":
            return self._generation_failed_response(
                request=request,
                request_id=request_id,
                search_response=search_response,
                retrieval=retrieval,
                planning=planning_metadata,
                error_category="context_pack_failed",
                attempt_count=0,
                generation_result=None,
            )

        messages = self._prompt.render(
            query=request.query,
            retrieval_queries=list(plan.semantic_queries),
            context_blocks=format_context_blocks(packing.chunks, collection_schema),
        )
        generation_request = GenerationRequest(
            messages=messages,
            response_schema=(
                StudyAnswerDraft.model_json_schema()
                if self.provider.capabilities.json_schema_output
                else None
            ),
            temperature=self.settings.generation.temperature,
            max_tokens=self._generation_max_output_tokens(),
            timeout_seconds=self.settings.generation.request_timeout_seconds,
        )

        generation_result: GenerationResult | None = None
        draft: StudyAnswerDraft
        attempt_count = 1

        try:
            async with asyncio.timeout(
                self.settings.generation.total_generation_deadline_seconds
            ):
                try:
                    generation_result = await self.provider.generate(generation_request)
                    draft = _parse_draft(generation_result.raw_content)
                except ValidationError as exc:
                    malformed_output = _raw_content_from_result(generation_result)
                    validation_error_summary = str(exc)
                    repair_result = None
                    for _ in range(self.settings.generation.schema_repair_retries):
                        attempt_count += 1
                        try:
                            repair_result = await self._try_repair(
                                request=generation_request,
                                malformed_output=malformed_output,
                                validation_error_summary=validation_error_summary,
                            )
                        except PROVIDER_ERRORS as exc:
                            return self._generation_failed_response(
                                request=request,
                                request_id=request_id,
                                search_response=search_response,
                                retrieval=retrieval,
                                planning=planning_metadata,
                                error_category=_provider_error_category(exc),
                                attempt_count=attempt_count,
                                generation_result=generation_result,
                            )
                        if repair_result is not None:
                            break
                    if repair_result is None:
                        return self._generation_failed_response(
                            request=request,
                            request_id=request_id,
                            search_response=search_response,
                            retrieval=retrieval,
                            planning=planning_metadata,
                            error_category="schema_validation_failed",
                            attempt_count=attempt_count,
                            generation_result=generation_result,
                        )
                    generation_result, draft = repair_result
                except PROVIDER_ERRORS as exc:
                    return self._generation_failed_response(
                        request=request,
                        request_id=request_id,
                        search_response=search_response,
                        retrieval=retrieval,
                        planning=planning_metadata,
                        error_category=_provider_error_category(exc),
                        attempt_count=attempt_count,
                        generation_result=generation_result,
                    )
        except TimeoutError:
            return self._generation_failed_response(
                request=request,
                request_id=request_id,
                search_response=search_response,
                retrieval=retrieval,
                planning=planning_metadata,
                error_category="provider_timeout",
                attempt_count=attempt_count,
                generation_result=generation_result,
            )

        validation = validate_citations(
            draft,
            valid_chunk_ids=set(retrieval.context_chunk_ids),
        )
        if validation.draft is None:
            return self._generation_failed_response(
                request=request,
                request_id=request_id,
                search_response=search_response,
                retrieval=retrieval,
                planning=planning_metadata,
                error_category=(
                    validation.error_category or "citation_validation_cascade_failure"
                ),
                attempt_count=attempt_count,
                citation_drops=validation.citation_drops,
                generation_result=generation_result,
            )

        response = self._success_response(
            request=request,
            request_id=request_id,
            search_response=search_response,
            retrieval=retrieval,
            planning=planning_metadata,
            generation_result=generation_result,
            validation=validation,
            attempt_count=attempt_count,
        )
        self._log_response(response)
        return response

    async def _try_repair(
        self,
        *,
        request: GenerationRequest,
        malformed_output: str,
        validation_error_summary: str,
    ) -> tuple[GenerationResult, StudyAnswerDraft] | None:
        repair_request = GenerationRequest(
            messages=[
                *request.messages,
                {
                    "role": "user",
                    "content": _repair_message(
                        malformed_output=malformed_output,
                        validation_error_summary=validation_error_summary,
                    ),
                },
            ],
            response_schema=request.response_schema,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            timeout_seconds=request.timeout_seconds,
        )
        try:
            repair_result = await self.provider.generate(repair_request)
            return repair_result, _parse_draft(repair_result.raw_content)
        except ValidationError:
            return None

    async def _plan(
        self,
        raw_query: str,
        hard_filters: list[FilterCondition] | None,
    ) -> tuple[QueryPlan, PlanningMetadata]:
        started = time.monotonic()
        try:
            async with asyncio.timeout(
                self.settings.planning.total_planning_deadline_seconds
            ):
                execution = await self.query_planner.plan(raw_query, hard_filters)
        except Exception as exc:
            fallback_plan = QueryPlan(
                original_query=raw_query,
                semantic_queries=[raw_query],
            )
            return fallback_plan, PlanningMetadata(
                status="fallback",
                planner_version=fallback_plan.planner_version,
                original_query=fallback_plan.original_query,
                semantic_queries=list(fallback_plan.semantic_queries),
                error_category=_planning_error_category(exc),
                telemetry=None,
                latency_ms=_elapsed_ms(started),
            )

        if isinstance(execution, QueryPlan):
            execution = PlannerExecution(
                plan=execution,
                telemetry=ProviderCallTelemetry(
                    provider="legacy_query_plan",
                    model="legacy_query_plan",
                    latency_ms=_elapsed_ms(started),
                    usage=None,
                ),
            )

        return execution.plan, PlanningMetadata(
            status="ok",
            planner_version=execution.plan.planner_version,
            original_query=execution.plan.original_query,
            semantic_queries=list(execution.plan.semantic_queries),
            error_category=None,
            telemetry=execution.telemetry,
            latency_ms=execution.telemetry.latency_ms,
        )

    def _empty_response(
        self,
        *,
        request: StudyRequest,
        request_id: str,
        answer_status: AnswerStatus,
        retrieval_status: RetrievalStatus,
        filters: list[FilterCondition],
        planning: PlanningMetadata,
        search_telemetry: SearchExecutionTelemetry | None = None,
    ) -> StudyResponse:
        limitation = (
            "Retrieval failed before any past questions could be selected."
            if answer_status == "retrieval_failed"
            else "No past questions matched the query."
        )
        response = StudyResponse(
            request_id=request_id,
            query=request.query,
            scope=request.scope,
            answer_status=answer_status,
            answer=StudyAnswer(
                overview="",
                patterns=[],
                limitations=[limitation],
            ),
            sources=[],
            retrieval=RetrievalMetadata(
                status=retrieval_status,
                top_k=request.top_k,
                returned_result_count=0,
                context_budget_tokens=self._context_budget_tokens(),
                context_chunk_ids=[],
                omitted_chunk_ids=[],
                truncated_chunk_ids=[],
                filters_applied=filters,
                rerank=True,
                search_telemetry=search_telemetry,
            ),
            planning=planning,
            generation=self._generation_metadata(
                attempt_count=0,
                citation_drops=0,
                error_category=None,
                generation_result=None,
            ),
        )
        self._log_response(response)
        return response

    def _generation_failed_response(
        self,
        *,
        request: StudyRequest,
        request_id: str,
        search_response: SearchResponse,
        retrieval: RetrievalMetadata,
        planning: PlanningMetadata,
        error_category: ErrorCategory,
        attempt_count: int,
        citation_drops: int = 0,
        generation_result: GenerationResult | None = None,
    ) -> StudyResponse:
        response = StudyResponse(
            request_id=request_id,
            query=request.query,
            scope=request.scope,
            answer_status="generation_failed",
            answer=StudyAnswer(
                overview="",
                patterns=[],
                limitations=["Generation failed; showing retrieved sources only."],
            ),
            sources=_fallback_sources(search_response, retrieval),
            retrieval=retrieval,
            planning=planning,
            generation=self._generation_metadata(
                attempt_count=attempt_count,
                citation_drops=citation_drops,
                error_category=error_category,
                generation_result=generation_result,
            ),
        )
        self._log_response(response)
        return response

    def _success_response(
        self,
        *,
        request: StudyRequest,
        request_id: str,
        search_response: SearchResponse,
        retrieval: RetrievalMetadata,
        planning: PlanningMetadata,
        generation_result: GenerationResult,
        validation: ValidationResult,
        attempt_count: int,
    ) -> StudyResponse:
        if validation.draft is None:
            raise ValueError("successful response requires validated draft")

        source_map = {result.chunk_id: result for result in search_response.results}
        why_by_id = {
            source.chunk_id: source.why_cited
            for source in validation.draft.cited_sources
        }
        source_ids = _ordered_unique(
            [
                chunk_id
                for pattern in validation.draft.patterns
                for chunk_id in pattern.supporting_chunk_ids
            ]
            + [source.chunk_id for source in validation.draft.cited_sources]
        )

        return StudyResponse(
            request_id=request_id,
            query=request.query,
            scope=request.scope,
            answer_status=validation.answer_status,
            answer=StudyAnswer(
                overview=validation.draft.overview,
                patterns=validation.draft.patterns,
                limitations=validation.limitations,
            ),
            sources=[
                _study_source(source_map[chunk_id], why_by_id.get(chunk_id))
                for chunk_id in source_ids
                if chunk_id in source_map
            ],
            retrieval=retrieval,
            planning=planning,
            generation=self._generation_metadata(
                attempt_count=attempt_count,
                citation_drops=validation.citation_drops,
                error_category=None,
                generation_result=generation_result,
            ),
        )

    def _log_response(self, response: StudyResponse) -> None:
        logger.info(
            "study_request",
            extra={
                "request_id": response.request_id,
                "answer_status": response.answer_status,
                "error_category": response.generation.error_category,
                "attempt_count": response.generation.attempt_count,
                "citation_drops": response.generation.citation_drops,
                "latency_ms": response.generation.latency_ms,
                "retrieval_status": response.retrieval.status,
                "packed_chunk_count": len(response.retrieval.context_chunk_ids),
                "omitted_chunk_count": len(response.retrieval.omitted_chunk_ids),
                "truncated_chunk_count": len(response.retrieval.truncated_chunk_ids),
                "planning_status": response.planning.status,
                "planning_error_category": response.planning.error_category,
                "planner_version": response.planning.planner_version,
                "planning_latency_ms": response.planning.latency_ms,
            },
        )

    def _context_budget_tokens(self) -> int:
        if self.runtime_settings is None:
            return self.settings.context.budget_tokens
        return min(
            self.settings.context.budget_tokens,
            self.runtime_settings.study_context_budget_tokens,
        )

    def _generation_max_output_tokens(self) -> int | None:
        if self.runtime_settings is None:
            return None
        return self.runtime_settings.study_generation_max_output_tokens

    def _max_single_chunk_tokens(self) -> int:
        context_budget = self._context_budget_tokens()
        # Reserve one token so truncated chunks still fit after the marker is added.
        return min(
            self.settings.context.max_single_chunk_tokens,
            max(1, context_budget - 1),
        )

    def _generation_metadata(
        self,
        *,
        attempt_count: int,
        citation_drops: int,
        error_category: ErrorCategory | None,
        generation_result: GenerationResult | None,
    ) -> GenerationMetadata:
        if generation_result is None:
            provider = self.settings.generation.provider
            model = self.settings.generation.model
            latency_ms = 0
            usage = None
        else:
            provider = generation_result.provider
            model = generation_result.model
            latency_ms = generation_result.latency_ms
            usage = generation_result.usage

        return GenerationMetadata(
            provider=provider,
            model=model,
            prompt_version=self.settings.prompt.version,
            temperature=self.settings.generation.temperature,
            attempt_count=attempt_count,
            citation_drops=citation_drops,
            error_category=error_category,
            latency_ms=latency_ms,
            usage=usage,
        )


def _ranked_chunk(result: SearchResult) -> RankedChunk:
    return RankedChunk(
        chunk_id=result.chunk_id,
        chunk_level=result.chunk_level,
        parent_chunk_id=result.parent_chunk_id,
        text=result.text,
        score=result.score,
        metadata=result.metadata,
    )


def _parse_draft(raw_content: str) -> StudyAnswerDraft:
    return StudyAnswerDraft.model_validate_json(raw_content)


def _provider_error_category(exc: Exception) -> ErrorCategory:
    if isinstance(exc, ProviderConnectionError):
        return "provider_unreachable"
    if isinstance(exc, ProviderTimeoutError):
        return "provider_timeout"
    if isinstance(exc, ModelNotAvailableError):
        return "model_not_available"
    return "provider_error"


def _planning_error_category(exc: Exception) -> PlanningErrorCategory:
    if isinstance(exc, ProviderTimeoutError):
        return "provider_timeout"
    if isinstance(exc, TimeoutError):
        return "planning_deadline_exceeded"
    if isinstance(exc, ProviderConnectionError):
        return "provider_unreachable"
    if isinstance(exc, ModelNotAvailableError):
        return "model_not_available"
    if isinstance(exc, ValidationError):
        return "schema_validation_failed"
    if isinstance(exc, InvalidPlanError):
        return "invalid_plan"
    return "provider_error"


def _fallback_sources(
    search_response: SearchResponse,
    retrieval: RetrievalMetadata,
) -> list[StudySource]:
    by_id = {result.chunk_id: result for result in search_response.results}
    chunk_ids = retrieval.context_chunk_ids
    if not chunk_ids:
        chunk_ids = [result.chunk_id for result in search_response.results[:10]]
    return [
        _study_source(by_id[chunk_id], why_cited=None)
        for chunk_id in chunk_ids
        if chunk_id in by_id
    ]


def _study_source(result: SearchResult, why_cited: str | None) -> StudySource:
    metadata = result.metadata
    return StudySource(
        chunk_id=result.chunk_id,
        chunk_level=result.chunk_level,
        parent_chunk_id=result.parent_chunk_id,
        sub_question_label=result.sub_question_label,
        score=result.score,
        excerpt=result.text[:STUDY_SOURCE_EXCERPT_CHARS],
        excerpt_blocks=(
            truncate_excerpt_blocks(result.render_blocks, STUDY_SOURCE_EXCERPT_CHARS)
            if result.render_blocks is not None
            else None
        ),
        metadata=metadata,
        why_cited=why_cited,
    )


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _repair_message(
    *,
    malformed_output: str,
    validation_error_summary: str,
) -> str:
    return (
        "Your previous response was not valid JSON for the required schema. "
        "Return only a corrected JSON object that conforms to the schema.\n\n"
        "Malformed output:\n"
        f"{malformed_output}\n\n"
        "Validation error summary:\n"
        f"{validation_error_summary}"
    )


def _raw_content_from_result(value: Any) -> str:
    if isinstance(value, GenerationResult):
        return value.raw_content
    return ""


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
