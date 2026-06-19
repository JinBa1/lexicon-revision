"""LangGraph re-hosting of the study orchestration pipeline.

Behavior-neutral port of ``StudyService.orchestrate()`` (Track A, PR 1). The
graph mirrors the imperative flow one-to-one:

    plan -> retrieve -> pack -> generate -> validate -> respond

Failure branches short-circuit to ``respond`` (the single terminal sink that
logs each request exactly once). Nodes return partial-dict state updates
(LangGraph merges them with the default overwrite reducer); they never mutate
the state model in place. ``graph.ainvoke()`` returns a plain dict for a
pydantic state schema, so the facade reads ``result["response"]``.

Deps are the owning ``StudyService`` instance, passed in at construction;
nodes call its existing (now non-logging) response builders and helpers, so the
ported logic is reused verbatim rather than reimplemented.

Deliberate deviation from the design doc, for parity safety: ``generate`` and
``repair`` are a single node that runs the original ``asyncio.timeout`` block
unchanged, instead of two nodes with a converted deadline. This preserves the
exact generation-budget semantics (one block covering generate + repair) and
keeps ``attempt_count`` / repair-message threading internal to that node.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, ValidationError
from src.metadata_schema.models import CollectionMetadataSchema, FilterCondition
from src.search.errors import InvalidMetadataFilterError
from src.search.models import SearchResponse
from src.search.pg_service import SearchExecutionTelemetry
from src.study.models import (
    GenerationRequest,
    GenerationResult,
    RankedChunk,
    RetrievalMetadata,
    RetrievalStatus,
    StudyAnswerDraft,
    StudyRequest,
    StudyResponse,
    ValidationResult,
)
from src.study.packing import (
    HeuristicTokenEstimator,
    dedupe_parent_child,
    format_context_blocks,
    pack_chunks,
)
from src.study.planning.intent import INTENT_REGISTRY
from src.study.planning.models import PlanningMetadata, QueryPlan
from src.study.service import (
    PROVIDER_ERRORS,
    _parse_draft,
    _provider_error_category,
    _ranked_chunk,
    _raw_content_from_result,
)
from src.study.validation import validate_citations

if TYPE_CHECKING:
    from src.study.service import StudyService

logger = logging.getLogger(__name__)


class StudyGraphState(BaseModel):
    """State threaded through the study graph.

    Carries every intermediate the imperative ``orchestrate()`` threaded.
    ``response`` is the terminal value: a terminal-reaching node builds the
    (unlogged) ``StudyResponse`` and the ``respond`` sink logs it once.

    NOTE: ``arbitrary_types_allowed`` lets fields hold non-pydantic objects
    (e.g. ``SearchExecutionTelemetry``) and the graph compiles with no
    checkpointer, so state is never serialised today. A later LangGraph
    checkpointer (e.g. the reflection-loop PR's interrupt/HITL state)
    serialises this state on every step -- verify all fields round-trip
    then, or swap heavy objects for IDs plus a side-channel store.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    # inputs (set at init)
    request: StudyRequest
    request_id: str
    hard_filters: list[FilterCondition] = []

    # planning
    plan: QueryPlan | None = None
    planning_metadata: PlanningMetadata | None = None

    # retrieval
    search_response: SearchResponse | None = None
    filters_applied: list[FilterCondition] = []
    collection_schema: CollectionMetadataSchema | None = None
    search_telemetry: SearchExecutionTelemetry | None = None
    retrieval_metadata: RetrievalMetadata | None = None

    # generation
    generation_request: GenerationRequest | None = None
    draft: StudyAnswerDraft | None = None
    generation_result: GenerationResult | None = None
    attempt_count: int = 0

    # PR3 reflection loop
    graded_chunks: list[RankedChunk] | None = None
    reflection_graded: bool = False
    critique: str = ""
    requery_semantic: list[str] | None = None
    requery_count: int = 0
    seen_chunk_ids: list[str] = []
    # Absolute wall-clock deadline (loop.time()); threaded from main.py. None in
    # unit tests / eval -> grade & reflect skip their budget gates.
    deadline_monotonic: float | None = None

    # validation + terminal
    validation: ValidationResult | None = None
    response: StudyResponse | None = None


async def _plan_node(state: StudyGraphState, deps: StudyService) -> dict:
    plan, planning_metadata = await deps._plan(state.request.query, state.hard_filters)
    return {"plan": plan, "planning_metadata": planning_metadata}


async def _direct_response_node(state: StudyGraphState, deps: StudyService) -> dict:
    # Defensive: _route_after_plan already coerces a None plan to
    # content_retrieval (-> retrieve), so direct_response is unreachable with a
    # None plan today. The guard hardens this node against the larger routing
    # surface PR3 adds, since _direct_response dereferences plan.intent.
    plan = state.plan or QueryPlan(
        original_query=state.request.query,
        semantic_queries=[state.request.query],
    )
    return {
        "response": deps._direct_response(
            request=state.request,
            request_id=state.request_id,
            plan=plan,
            planning=state.planning_metadata,
        )
    }


def _route_after_plan(state: StudyGraphState) -> str:
    intent = state.plan.intent if state.plan is not None else "content_retrieval"
    workflow = INTENT_REGISTRY[intent].workflow
    return "retrieve" if workflow == "retrieval" else "direct_response"


async def _retrieve_node(state: StudyGraphState, deps: StudyService) -> dict:
    request = state.request
    planning = state.planning_metadata
    try:
        # Synchronous, matching the imperative orchestrate() exactly (parity).
        retrieval_result = deps.planned_retrieval.retrieve(
            state.plan,
            hard_filters=state.hard_filters,
            collection=request.scope.collection,
            limit=request.top_k,
            rerank=True,
        )
    except InvalidMetadataFilterError:
        raise
    except Exception:
        logger.exception(
            "study_retrieval_failed",
            extra={
                "request_id": state.request_id,
                "collection": request.scope.collection,
                "planning_status": planning.status,
                "planning_error_category": planning.error_category,
                "planner_version": planning.planner_version,
                "planning_latency_ms": planning.latency_ms,
            },
        )
        return {
            "response": deps._empty_response(
                request=request,
                request_id=state.request_id,
                answer_status="retrieval_failed",
                retrieval_status="error",
                filters=list(state.hard_filters or []),
                planning=planning,
            )
        }

    search_response = retrieval_result.search_response
    filters = retrieval_result.filters_applied

    if not search_response.results:
        retrieval_status: RetrievalStatus = "filtered_empty" if filters else "empty"
        return {
            "response": deps._empty_response(
                request=request,
                request_id=state.request_id,
                answer_status="insufficient_evidence",
                retrieval_status=retrieval_status,
                filters=filters,
                planning=planning,
                search_telemetry=retrieval_result.search_telemetry,
            )
        }

    return {
        "search_response": search_response,
        "filters_applied": filters,
        "collection_schema": retrieval_result.collection_schema,
        "search_telemetry": retrieval_result.search_telemetry,
    }


async def _pack_node(state: StudyGraphState, deps: StudyService) -> dict:
    request = state.request
    search_response = state.search_response
    filters = state.filters_applied
    planning = state.planning_metadata
    budget_tokens = deps._context_budget_tokens()

    try:
        ranked_chunks = [_ranked_chunk(result) for result in search_response.results]
        deduped_chunks = dedupe_parent_child(ranked_chunks)
        packing = pack_chunks(
            deduped_chunks,
            budget_tokens=budget_tokens,
            max_single_chunk_tokens=deps._max_single_chunk_tokens(),
            estimator=HeuristicTokenEstimator(),
        )
        retrieval = RetrievalMetadata(
            status="ok",
            top_k=request.top_k,
            returned_result_count=len(search_response.results),
            context_budget_tokens=budget_tokens,
            context_chunk_ids=[packed.chunk.chunk_id for packed in packing.chunks],
            omitted_chunk_ids=packing.omitted_chunk_ids,
            truncated_chunk_ids=packing.truncated_chunk_ids,
            filters_applied=filters,
            rerank=True,
            search_telemetry=state.search_telemetry,
        )
    except Exception:
        logger.exception(
            "study_context_build_failed",
            extra={"request_id": state.request_id},
        )
        degraded = RetrievalMetadata(
            status="ok",
            top_k=request.top_k,
            returned_result_count=len(search_response.results),
            context_budget_tokens=budget_tokens,
            context_chunk_ids=[],
            omitted_chunk_ids=[],
            truncated_chunk_ids=[],
            filters_applied=filters,
            rerank=True,
            search_telemetry=state.search_telemetry,
        )
        return {
            "retrieval_metadata": degraded,
            "response": deps._generation_failed_response(
                request=request,
                request_id=state.request_id,
                search_response=search_response,
                retrieval=degraded,
                planning=planning,
                error_category="context_build_failed",
                attempt_count=0,
                generation_result=None,
            ),
        }

    if packing.status == "context_pack_failed":
        return {
            "retrieval_metadata": retrieval,
            "response": deps._generation_failed_response(
                request=request,
                request_id=state.request_id,
                search_response=search_response,
                retrieval=retrieval,
                planning=planning,
                error_category="context_pack_failed",
                attempt_count=0,
                generation_result=None,
            ),
        }

    messages = deps._prompt.render(
        query=request.query,
        retrieval_queries=list(state.plan.semantic_queries),
        context_blocks=format_context_blocks(packing.chunks, state.collection_schema),
        generation_guidance=state.plan.generation_guidance,
    )
    generation_request = GenerationRequest(
        messages=messages,
        response_schema=(
            StudyAnswerDraft.model_json_schema()
            if deps.provider.capabilities.json_schema_output
            else None
        ),
        temperature=deps.settings.generation.temperature,
        max_tokens=deps._generation_max_output_tokens(),
        timeout_seconds=deps.settings.generation.request_timeout_seconds,
    )
    return {"retrieval_metadata": retrieval, "generation_request": generation_request}


async def _generate_node(state: StudyGraphState, deps: StudyService) -> dict:
    request = state.request
    search_response = state.search_response
    retrieval = state.retrieval_metadata
    planning = state.planning_metadata
    generation_request = state.generation_request

    generation_result: GenerationResult | None = None
    draft: StudyAnswerDraft
    attempt_count = 1

    def fail(error_category, attempt, gen_result):
        return deps._generation_failed_response(
            request=request,
            request_id=state.request_id,
            search_response=search_response,
            retrieval=retrieval,
            planning=planning,
            error_category=error_category,
            attempt_count=attempt,
            generation_result=gen_result,
        )

    try:
        async with asyncio.timeout(
            deps.settings.generation.total_generation_deadline_seconds
        ):
            try:
                generation_result = await deps.provider.generate(generation_request)
                draft = _parse_draft(generation_result.raw_content)
            except ValidationError as exc:
                malformed_output = _raw_content_from_result(generation_result)
                validation_error_summary = str(exc)
                repair_result = None
                for _ in range(deps.settings.generation.schema_repair_retries):
                    attempt_count += 1
                    try:
                        repair_result = await deps._try_repair(
                            request=generation_request,
                            malformed_output=malformed_output,
                            validation_error_summary=validation_error_summary,
                        )
                    except PROVIDER_ERRORS as exc:
                        return {
                            "response": fail(
                                _provider_error_category(exc),
                                attempt_count,
                                generation_result,
                            )
                        }
                    if repair_result is not None:
                        break
                if repair_result is None:
                    return {
                        "response": fail(
                            "schema_validation_failed",
                            attempt_count,
                            generation_result,
                        )
                    }
                generation_result, draft = repair_result
            except PROVIDER_ERRORS as exc:
                return {
                    "response": fail(
                        _provider_error_category(exc),
                        attempt_count,
                        generation_result,
                    )
                }
    except TimeoutError:
        return {"response": fail("provider_timeout", attempt_count, generation_result)}

    return {
        "draft": draft,
        "generation_result": generation_result,
        "attempt_count": attempt_count,
    }


async def _validate_node(state: StudyGraphState, deps: StudyService) -> dict:
    retrieval = state.retrieval_metadata
    validation = validate_citations(
        state.draft,
        valid_chunk_ids=set(retrieval.context_chunk_ids),
    )
    if validation.draft is None:
        return {
            "validation": validation,
            "response": deps._generation_failed_response(
                request=state.request,
                request_id=state.request_id,
                search_response=state.search_response,
                retrieval=retrieval,
                planning=state.planning_metadata,
                error_category=(
                    validation.error_category or "citation_validation_cascade_failure"
                ),
                attempt_count=state.attempt_count,
                citation_drops=validation.citation_drops,
                generation_result=state.generation_result,
            ),
        }

    return {
        "validation": validation,
        "response": deps._success_response(
            request=state.request,
            request_id=state.request_id,
            search_response=state.search_response,
            retrieval=retrieval,
            planning=state.planning_metadata,
            generation_result=state.generation_result,
            validation=validation,
            attempt_count=state.attempt_count,
        ),
    }


async def _respond_node(state: StudyGraphState, deps: StudyService) -> dict:
    deps._log_response(state.response)
    return {}


def _route_after_retrieve(state: StudyGraphState) -> str:
    return "respond" if state.response is not None else "pack"


def _route_after_pack(state: StudyGraphState) -> str:
    return "respond" if state.response is not None else "generate"


def _route_after_generate(state: StudyGraphState) -> str:
    return "respond" if state.response is not None else "validate"


def _bind(fn, deps: StudyService):
    async def node(state: StudyGraphState) -> dict:
        return await fn(state, deps)

    return node


def build_study_graph(deps: StudyService):
    """Compile the study graph bound to a ``StudyService`` (its deps)."""
    builder = StateGraph(StudyGraphState)
    builder.add_node("plan", _bind(_plan_node, deps))
    builder.add_node("direct_response", _bind(_direct_response_node, deps))
    builder.add_node("retrieve", _bind(_retrieve_node, deps))
    builder.add_node("pack", _bind(_pack_node, deps))
    builder.add_node("generate", _bind(_generate_node, deps))
    builder.add_node("validate", _bind(_validate_node, deps))
    builder.add_node("respond", _bind(_respond_node, deps))

    builder.add_edge(START, "plan")
    builder.add_conditional_edges(
        "plan",
        _route_after_plan,
        {"retrieve": "retrieve", "direct_response": "direct_response"},
    )
    builder.add_edge("direct_response", "respond")
    builder.add_conditional_edges(
        "retrieve", _route_after_retrieve, {"pack": "pack", "respond": "respond"}
    )
    builder.add_conditional_edges(
        "pack", _route_after_pack, {"generate": "generate", "respond": "respond"}
    )
    builder.add_conditional_edges(
        "generate",
        _route_after_generate,
        {"validate": "validate", "respond": "respond"},
    )
    builder.add_edge("validate", "respond")
    builder.add_edge("respond", END)
    return builder.compile()
