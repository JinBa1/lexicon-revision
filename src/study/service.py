from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from src.search.models import SearchResponse, SearchResult
from src.search.service import SearchService
from src.study.config import StudySettings
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


class StudyService:
    def __init__(
        self,
        *,
        search_service: SearchService,
        provider: GenerationProvider,
        settings: StudySettings,
    ) -> None:
        self.search_service = search_service
        self.provider = provider
        self.settings = settings
        self._prompt = load_prompt_template(Path(settings.prompt.path))

    async def orchestrate(self, request: StudyRequest) -> StudyResponse:
        started = time.monotonic()
        request_id = str(uuid.uuid4())
        filters = _effective_filters(request.filters)

        try:
            search_response = self.search_service.search(
                query=request.query,
                collection=request.scope.collection,
                filters=filters or None,
                limit=request.top_k,
                rerank=True,
            )
        except Exception:
            logger.exception(
                "study_retrieval_failed",
                extra={
                    "request_id": request_id,
                    "collection": request.scope.collection,
                },
            )
            return self._empty_response(
                request=request,
                request_id=request_id,
                answer_status="retrieval_failed",
                retrieval_status="error",
                filters=filters,
                latency_ms=_elapsed_ms(started),
            )

        if not search_response.results:
            retrieval_status: RetrievalStatus = "filtered_empty" if filters else "empty"
            return self._empty_response(
                request=request,
                request_id=request_id,
                answer_status="insufficient_evidence",
                retrieval_status=retrieval_status,
                filters=filters,
                latency_ms=_elapsed_ms(started),
            )

        try:
            ranked_chunks = [
                _ranked_chunk(result) for result in search_response.results
            ]
            deduped_chunks = dedupe_parent_child(ranked_chunks)
            packing = pack_chunks(
                deduped_chunks,
                budget_tokens=self.settings.context.budget_tokens,
                max_single_chunk_tokens=self.settings.context.max_single_chunk_tokens,
                estimator=HeuristicTokenEstimator(),
            )
            retrieval = RetrievalMetadata(
                status="ok",
                top_k=request.top_k,
                returned_result_count=len(search_response.results),
                context_budget_tokens=self.settings.context.budget_tokens,
                context_chunk_ids=[packed.chunk.chunk_id for packed in packing.chunks],
                omitted_chunk_ids=packing.omitted_chunk_ids,
                truncated_chunk_ids=packing.truncated_chunk_ids,
                filters_applied=filters,
                rerank=True,
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
                context_budget_tokens=self.settings.context.budget_tokens,
                context_chunk_ids=[],
                omitted_chunk_ids=[],
                truncated_chunk_ids=[],
                filters_applied=filters,
                rerank=True,
            )
            return self._generation_failed_response(
                request=request,
                request_id=request_id,
                search_response=search_response,
                retrieval=retrieval,
                error_category="context_build_failed",
                attempt_count=0,
                latency_ms=_elapsed_ms(started),
            )

        if packing.status == "context_pack_failed":
            return self._generation_failed_response(
                request=request,
                request_id=request_id,
                search_response=search_response,
                retrieval=retrieval,
                error_category="context_pack_failed",
                attempt_count=0,
                latency_ms=_elapsed_ms(started),
            )

        messages = self._prompt.render(
            query=request.query,
            context_blocks=format_context_blocks(packing.chunks),
        )
        generation_request = GenerationRequest(
            messages=messages,
            response_schema=(
                StudyAnswerDraft.model_json_schema()
                if self.provider.capabilities.json_schema_output
                else None
            ),
            temperature=self.settings.generation.temperature,
            max_tokens=None,
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
                                error_category=_provider_error_category(exc),
                                attempt_count=attempt_count,
                                latency_ms=_elapsed_ms(started),
                            )
                        if repair_result is not None:
                            break
                    if repair_result is None:
                        return self._generation_failed_response(
                            request=request,
                            request_id=request_id,
                            search_response=search_response,
                            retrieval=retrieval,
                            error_category="schema_validation_failed",
                            attempt_count=attempt_count,
                            latency_ms=_elapsed_ms(started),
                        )
                    generation_result, draft = repair_result
                except PROVIDER_ERRORS as exc:
                    return self._generation_failed_response(
                        request=request,
                        request_id=request_id,
                        search_response=search_response,
                        retrieval=retrieval,
                        error_category=_provider_error_category(exc),
                        attempt_count=attempt_count,
                        latency_ms=_elapsed_ms(started),
                    )
        except TimeoutError:
            return self._generation_failed_response(
                request=request,
                request_id=request_id,
                search_response=search_response,
                retrieval=retrieval,
                error_category="provider_timeout",
                attempt_count=attempt_count,
                latency_ms=_elapsed_ms(started),
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
                error_category=(
                    validation.error_category or "citation_validation_cascade_failure"
                ),
                attempt_count=attempt_count,
                citation_drops=validation.citation_drops,
                latency_ms=generation_result.latency_ms,
            )

        response = self._success_response(
            request=request,
            request_id=request_id,
            search_response=search_response,
            retrieval=retrieval,
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

    def _empty_response(
        self,
        *,
        request: StudyRequest,
        request_id: str,
        answer_status: AnswerStatus,
        retrieval_status: RetrievalStatus,
        filters: dict[str, Any],
        latency_ms: int,
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
                context_budget_tokens=self.settings.context.budget_tokens,
                context_chunk_ids=[],
                omitted_chunk_ids=[],
                truncated_chunk_ids=[],
                filters_applied=filters,
                rerank=True,
            ),
            generation=GenerationMetadata(
                provider=self.settings.generation.provider,
                model=self.settings.generation.model,
                prompt_version=self.settings.prompt.version,
                temperature=self.settings.generation.temperature,
                attempt_count=0,
                citation_drops=0,
                error_category=None,
                latency_ms=latency_ms,
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
        error_category: ErrorCategory,
        attempt_count: int,
        latency_ms: int,
        citation_drops: int = 0,
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
            generation=GenerationMetadata(
                provider=self.settings.generation.provider,
                model=self.settings.generation.model,
                prompt_version=self.settings.prompt.version,
                temperature=self.settings.generation.temperature,
                attempt_count=attempt_count,
                citation_drops=citation_drops,
                error_category=error_category,
                latency_ms=latency_ms,
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
            generation=GenerationMetadata(
                provider=generation_result.provider,
                model=generation_result.model,
                prompt_version=self.settings.prompt.version,
                temperature=self.settings.generation.temperature,
                attempt_count=attempt_count,
                citation_drops=validation.citation_drops,
                error_category=None,
                latency_ms=generation_result.latency_ms,
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
            },
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


def _effective_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    if not filters:
        return {}
    return {key: value for key, value in filters.items() if value is not None}


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
        year=metadata.get("year"),
        paper=metadata.get("paper"),
        question_ref=_question_ref(
            question_number=metadata.get("question_number"),
            sub_question_label=metadata.get("sub_question_label"),
        ),
        chunk_level=result.chunk_level,
        topic=metadata.get("topic"),
        score=result.score,
        excerpt=result.text[:500],
        why_cited=why_cited,
    )


def _question_ref(
    *,
    question_number: Any,
    sub_question_label: Any,
) -> str | None:
    if question_number is None:
        return None
    question_ref = f"Q{question_number}"
    if sub_question_label:
        question_ref = f"{question_ref}{sub_question_label}"
    return question_ref


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
