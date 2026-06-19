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
from src.study.reflection import QueryReformulationDraft, RelevanceGradingDraft
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
    # On a reflection re-query, swap in the reformulated query via an ephemeral
    # plan (state.plan is never mutated). Sync retrieve is kept as-is (parity);
    # an async/cancellable retrieve is the "Async database access" backlog item.
    effective_plan = state.plan
    if state.requery_semantic is not None:
        assert len(state.requery_semantic) == 1, (
            "PR3 single-query invariant: requery_semantic must hold exactly one "
            "query (PR4 must raise QueryPlan.semantic_queries max_length first)"
        )
        effective_plan = QueryPlan(
            planner_version=state.plan.planner_version,
            original_query=state.plan.original_query,
            semantic_queries=list(state.requery_semantic),
            intent=state.plan.intent,
            generation_guidance=state.plan.generation_guidance,
        )
    try:
        # Synchronous, matching the imperative orchestrate() exactly (parity).
        retrieval_result = deps.planned_retrieval.retrieve(
            effective_plan,
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


_GRADER_EXCERPT_CHARS = 200
_MAX_REQUERY_WORDS = 40
_REFLECTION_ABSTAIN_LIMITATION = (
    "No retrieved questions were sufficiently relevant to your query. "
    "Try rephrasing or broadening your topic."
)


def _remaining_budget(state: StudyGraphState) -> float | None:
    if state.deadline_monotonic is None:
        return None
    return state.deadline_monotonic - asyncio.get_running_loop().time()


def _reflection_abstain(
    state: StudyGraphState, deps: StudyService, *, critique: str = ""
) -> StudyResponse:
    return deps._empty_response(
        request=state.request,
        request_id=state.request_id,
        answer_status="insufficient_evidence",
        retrieval_status="low_relevance",
        filters=list(state.filters_applied),
        planning=state.planning_metadata,
        search_telemetry=state.search_telemetry,
        limitations=[_REFLECTION_ABSTAIN_LIMITATION],
        reflection_graded=True,
        requery_attempted=state.requery_count > 0,
        graded_chunk_count=0,
        reflection_critique=critique or state.critique,
    )


async def _grade_node(state: StudyGraphState, deps: StudyService) -> dict:
    """LLM-grade retrieved chunks: prune, re-query (via reflect), or abstain."""
    settings = deps.settings.reflection
    results = state.search_response.results

    # Kill switch: accept everything, no grader call.
    if not settings.enabled:
        return {
            "graded_chunks": [_ranked_chunk(r) for r in results],
            "reflection_graded": False,
        }

    remaining = _remaining_budget(state)

    # No-new-evidence guard (second pass only): if the re-query surfaced no
    # unseen chunks, abstain without spending a second grade call.
    if state.requery_count == 1:
        seen = set(state.seen_chunk_ids)
        if all(r.chunk_id in seen for r in results):
            return {"response": _reflection_abstain(state, deps)}

    step_cap = settings.step_timeout_seconds
    if remaining is not None:
        step_cap = min(step_cap, max(remaining, 0.0))

    chunks = [
        {"chunk_id": r.chunk_id, "excerpt": r.text[:_GRADER_EXCERPT_CHARS]}
        for r in results
    ]
    grader_request = GenerationRequest(
        messages=deps._grading_prompt.render(query=state.request.query, chunks=chunks),
        response_schema=(
            RelevanceGradingDraft.model_json_schema()
            if deps.provider.capabilities.json_schema_output
            else None
        ),
        temperature=0.0,
        max_tokens=None,
        timeout_seconds=step_cap,
    )
    try:
        async with asyncio.timeout(step_cap):
            grade_result = await deps.provider.generate(grader_request)
        draft = RelevanceGradingDraft.model_validate_json(grade_result.raw_content)
    except (TimeoutError, ValidationError, *PROVIDER_ERRORS):
        logger.warning("study_grade_failed", extra={"request_id": state.request_id})
        # Fail safe: accept all chunks and proceed exactly as pre-PR3.
        return {
            "graded_chunks": [_ranked_chunk(r) for r in results],
            "reflection_graded": False,
        }

    valid_ids = {r.chunk_id for r in results}
    accepted = {cid for cid in draft.accepted_chunk_ids if cid in valid_ids}
    graded = [_ranked_chunk(r) for r in results if r.chunk_id in accepted]

    if graded:
        return {"graded_chunks": graded, "reflection_graded": True}

    can_requery = state.requery_count == 0 and (
        remaining is None or remaining >= settings.requery_min_remaining_seconds
    )
    if can_requery:
        # Hand the failure to the reflect node (routing keys on requery_semantic
        # still being None here). seen_chunk_ids arms the no-new-evidence guard.
        return {
            "critique": draft.critique.strip()
            or "Retrieved chunks did not address the query.",
            "requery_count": 1,
            "reflection_graded": True,
            "seen_chunk_ids": [r.chunk_id for r in results],
        }
    return {
        "response": _reflection_abstain(state, deps, critique=draft.critique.strip())
    }


async def _reflect_node(state: StudyGraphState, deps: StudyService) -> dict:
    """Design one different retrieval query from the grader critique, or abstain."""
    settings = deps.settings.reflection
    remaining = _remaining_budget(state)
    if remaining is not None and remaining < settings.requery_min_remaining_seconds:
        return {"response": _reflection_abstain(state, deps)}

    step_cap = settings.step_timeout_seconds
    if remaining is not None:
        step_cap = min(step_cap, max(remaining, 0.0))

    reflect_request = GenerationRequest(
        messages=deps._reflect_prompt.render(
            query=state.plan.original_query,
            critique=state.critique,
        ),
        response_schema=(
            QueryReformulationDraft.model_json_schema()
            if deps.provider.capabilities.json_schema_output
            else None
        ),
        temperature=0.0,
        max_tokens=None,
        timeout_seconds=step_cap,
    )
    try:
        async with asyncio.timeout(step_cap):
            reflect_result = await deps.provider.generate(reflect_request)
        draft = QueryReformulationDraft.model_validate_json(reflect_result.raw_content)
    except (TimeoutError, ValidationError, *PROVIDER_ERRORS):
        logger.warning("study_reflect_failed", extra={"request_id": state.request_id})
        # No chunks to fall back to -> abstain honestly (unlike grade).
        return {"response": _reflection_abstain(state, deps)}

    reformulated = " ".join(draft.reformulated_query.split()[:_MAX_REQUERY_WORDS])
    original = state.plan.original_query.strip().lower()
    if not reformulated or reformulated.strip().lower() == original:
        # Declined or trivially identical -> abstain (chunk-set guard is backstop).
        return {"response": _reflection_abstain(state, deps)}
    return {"requery_semantic": [reformulated]}


async def _pack_node(state: StudyGraphState, deps: StudyService) -> dict:
    request = state.request
    search_response = state.search_response
    filters = state.filters_applied
    planning = state.planning_metadata
    budget_tokens = deps._context_budget_tokens()

    # Source the grader's pruned set when it ran; else all retrieved chunks.
    if state.graded_chunks is not None:
        ranked_chunks = state.graded_chunks
    else:
        ranked_chunks = [_ranked_chunk(result) for result in search_response.results]
    graded_ids = {chunk.chunk_id for chunk in ranked_chunks}
    pruned_ids = [
        r.chunk_id for r in search_response.results if r.chunk_id not in graded_ids
    ]
    reflection_fields: dict = {
        "reflection_graded": state.reflection_graded,
        "requery_attempted": state.requery_count > 0,
        "graded_chunk_count": len(ranked_chunks)
        if state.graded_chunks is not None
        else 0,
        "grader_pruned_chunk_ids": pruned_ids,
        "reflection_critique": state.critique,
    }
    # The answer LLM should see the query that actually retrieved these chunks.
    effective_queries = state.requery_semantic or list(state.plan.semantic_queries)

    try:
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
            **reflection_fields,
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
            **reflection_fields,
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
        retrieval_queries=effective_queries,
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
    return "respond" if state.response is not None else "grade"


def _route_after_grade(state: StudyGraphState) -> str:
    # LangGraph merges the node's returned dict into state BEFORE the router
    # runs, so these read the just-updated state. Timing-independent: routing
    # keys on WHICH fields grade wrote, not on a counter's transient value.
    if state.response is not None:  # abstain/fail terminal already written
        return "respond"
    if state.graded_chunks is not None:  # >=1 accepted (or fail-safe accept-all)
        return "pack"
    if state.requery_semantic is None:  # grade chose to reflect; reflect not run
        return "reflect"
    return "pack"  # safety net (unreachable)


def _route_after_reflect(state: StudyGraphState) -> str:
    return "respond" if state.response is not None else "retrieve"


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
    builder.add_node("grade", _bind(_grade_node, deps))
    builder.add_node("reflect", _bind(_reflect_node, deps))
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
        "retrieve", _route_after_retrieve, {"grade": "grade", "respond": "respond"}
    )
    builder.add_conditional_edges(
        "grade",
        _route_after_grade,
        {"pack": "pack", "reflect": "reflect", "respond": "respond"},
    )
    builder.add_conditional_edges(
        "reflect",
        _route_after_reflect,
        {"retrieve": "retrieve", "respond": "respond"},
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
