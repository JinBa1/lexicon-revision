from __future__ import annotations

from pydantic import ValidationError
from src.metadata_schema.models import FilterCondition
from src.study.models import (
    CitedSource,
    GenerationMetadata,
    PackedChunk,
    PackingResult,
    ProviderCapabilities,
    RankedChunk,
    RetrievalMetadata,
    StudyAnswer,
    StudyAnswerDraft,
    StudyPattern,
    StudyRequest,
    StudyResponse,
    StudyScope,
    StudySource,
    ValidationResult,
)
from src.study.planning.models import PlanningMetadata


def test_study_request_defaults_and_scope_shape() -> None:
    request = StudyRequest(
        query="dynamic programming",
        scope={"collection": "cam-cs-tripos"},
        filters=[
            {"field": "year", "op": "eq", "value": 2023},
            {"field": "paper", "op": "eq", "value": 2},
        ],
    )

    assert request.top_k == 15
    assert request.scope == StudyScope(collection="cam-cs-tripos")
    assert request.filters == [
        FilterCondition(field="year", op="eq", value=2023),
        FilterCondition(field="paper", op="eq", value=2),
    ]


def test_study_request_accepts_filter_condition_lists() -> None:
    request = StudyRequest(
        query="dynamic programming",
        scope=StudyScope(collection="cam-cs-tripos"),
        filters=[
            FilterCondition(field="year", op="eq", value=2024),
            FilterCondition(field="has_code", op="eq", value=True),
        ],
    )

    assert request.filters == [
        FilterCondition(field="year", op="eq", value=2024),
        FilterCondition(field="has_code", op="eq", value=True),
    ]


def test_study_request_coerces_payload_to_filter_conditions() -> None:
    request = StudyRequest.model_validate(
        {
            "query": "q",
            "scope": {"collection": "c"},
            "filters": [{"field": "year", "op": "eq", "value": 2024}],
        }
    )

    assert request.filters == [FilterCondition(field="year", op="eq", value=2024)]


def test_study_request_rejects_legacy_filter_dict_shape() -> None:
    try:
        StudyRequest.model_validate(
            {
                "query": "q",
                "scope": {"collection": "c"},
                "filters": {"question": 4},
            }
        )
    except ValidationError:
        return
    raise AssertionError("legacy filter dict shape should have been rejected")


def test_study_request_preserves_repeated_filter_conditions() -> None:
    request = StudyRequest.model_validate(
        {
            "query": "q",
            "scope": {"collection": "c"},
            "filters": [
                {"field": "year", "op": "gte", "value": 2020},
                {"field": "year", "op": "lte", "value": 2024},
            ],
        }
    )

    assert request.filters == [
        FilterCondition(field="year", op="gte", value=2020),
        FilterCondition(field="year", op="lte", value=2024),
    ]


def test_study_request_rejects_top_k_out_of_range() -> None:
    for top_k in (0, 51):
        try:
            StudyRequest(
                query="dynamic programming",
                scope={"collection": "cam-cs-tripos"},
                top_k=top_k,
            )
        except ValidationError:
            continue
        raise AssertionError(f"top_k={top_k} should have been rejected")


def test_study_answer_draft_enforces_schema_bounds() -> None:
    schema = StudyAnswerDraft.model_json_schema()
    assert schema["properties"]["overview"]["maxLength"] == 1200
    assert schema["properties"]["patterns"]["maxItems"] == 5
    assert schema["properties"]["cited_sources"]["maxItems"] == 10

    base_draft = StudyAnswerDraft(
        answer_status="ok",
        overview="Valid overview.",
        patterns=[
            StudyPattern(
                label="Recurrence design",
                summary="Questions ask students to derive a recurrence.",
                supporting_chunk_ids=["cam-2023-p2-q4"],
            )
        ],
        cited_sources=[
            CitedSource(
                chunk_id="cam-2023-p2-q4",
                why_cited="The question directly asks for a recurrence.",
            )
        ],
        limitations=["Valid limitation."],
    )
    assert base_draft.overview == "Valid overview."

    invalid_payloads = [
        {"overview": "x" * 1201},
        {
            "patterns": [
                {
                    "label": "x" * 81,
                    "summary": "ok",
                    "supporting_chunk_ids": ["a"],
                }
            ]
        },
        {
            "patterns": [
                {
                    "label": "ok",
                    "summary": "x" * 501,
                    "supporting_chunk_ids": ["a"],
                }
            ]
        },
        {"patterns": [{"label": "ok", "summary": "ok", "supporting_chunk_ids": []}]},
        {
            "patterns": [
                {
                    "label": "ok",
                    "summary": "ok",
                    "supporting_chunk_ids": ["a"] * 6,
                }
            ]
        },
        {"patterns": [{} for _ in range(6)]},
        {
            "cited_sources": [
                {"chunk_id": f"chunk-{i}", "why_cited": "ok"} for i in range(11)
            ]
        },
        {"limitations": ["x" for _ in range(6)]},
    ]

    for mutation in invalid_payloads:
        payload = base_draft.model_dump()
        payload.update(mutation)
        try:
            StudyAnswerDraft.model_validate(payload)
        except ValidationError:
            continue
        raise AssertionError(f"payload should have been rejected: {mutation}")


def test_cited_source_rejects_none_why_cited() -> None:
    try:
        CitedSource(chunk_id="cam-2023-p2-q4", why_cited=None)  # type: ignore[arg-type]
    except ValidationError:
        return
    raise AssertionError("why_cited=None should have been rejected")


def test_study_source_uses_metadata_bag() -> None:
    source = StudySource.model_validate(
        {
            "chunk_id": "cam-2024-p2-q5",
            "chunk_level": "question",
            "parent_chunk_id": None,
            "sub_question_label": None,
            "score": 0.91,
            "excerpt": "Binary search trees support efficient lookup.",
            "metadata": {"year": 2024, "paper": 2, "topic": "Algorithms"},
            "why_cited": "Introduces balanced tree lookup costs.",
        }
    )

    assert source.metadata["paper"] == 2


def test_final_study_response_allows_null_why_cited() -> None:
    nullable_source = StudySource(
        chunk_id="cam-2023-p2-q4",
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        score=0.82,
        excerpt="Consider a dynamic programming recurrence.",
        metadata={},
        why_cited=None,
    )

    response = StudyResponse(
        schema_version="study_answer_v2",
        request_id="8c6f3d2f-4f95-4d64-9c5e-8f75b5e4ce9d",
        query="dynamic programming",
        scope=StudyScope(collection="cam-cs-tripos"),
        answer_status="ok",
        answer=StudyAnswer(
            overview="Valid overview.",
            patterns=[],
            limitations=[],
        ),
        sources=[nullable_source],
        retrieval=RetrievalMetadata(
            status="ok",
            top_k=15,
            returned_result_count=1,
            context_budget_tokens=4000,
            context_chunk_ids=["cam-2023-p2-q4"],
            omitted_chunk_ids=[],
            truncated_chunk_ids=[],
            filters_applied=[FilterCondition(field="year", op="eq", value=2023)],
            rerank=True,
        ),
        planning=PlanningMetadata(
            status="ok",
            planner_version="query_planner_v1",
            original_query="dynamic programming",
            semantic_queries=["dynamic programming"],
            error_category=None,
            latency_ms=0,
        ),
        generation=GenerationMetadata(
            provider="ollama",
            model="qwen2.5:7b-instruct",
            prompt_version="study_aid_v1",
            temperature=0.1,
            attempt_count=1,
            citation_drops=0,
            error_category=None,
            latency_ms=4213,
        ),
    )

    assert response.sources[0].why_cited is None
    assert response.sources[0].metadata == {}


def test_study_response_defaults_to_schema_version_v2() -> None:
    response = StudyResponse(
        request_id="8c6f3d2f-4f95-4d64-9c5e-8f75b5e4ce9d",
        query="q",
        scope=StudyScope(collection="c"),
        answer_status="ok",
        answer=StudyAnswer(
            overview="Valid overview.",
            patterns=[],
            limitations=[],
        ),
        sources=[],
        retrieval=RetrievalMetadata(
            status="ok",
            top_k=15,
            returned_result_count=0,
            context_budget_tokens=4000,
            context_chunk_ids=[],
            omitted_chunk_ids=[],
            truncated_chunk_ids=[],
            filters_applied=[],
            rerank=True,
        ),
        planning=PlanningMetadata(
            status="ok",
            planner_version="query_planner_v1",
            original_query="q",
            semantic_queries=["q"],
            error_category=None,
            latency_ms=0,
        ),
        generation=GenerationMetadata(
            provider="ollama",
            model="qwen2.5:7b-instruct",
            prompt_version="study_aid_v1",
            temperature=0.1,
            attempt_count=1,
            citation_drops=0,
            error_category=None,
            latency_ms=4213,
        ),
    )

    assert response.schema_version == "study_answer_v2"


def test_study_response_requires_planning_field() -> None:
    response_payload = {
        "request_id": "8c6f3d2f-4f95-4d64-9c5e-8f75b5e4ce9d",
        "query": "q",
        "scope": {"collection": "c"},
        "answer_status": "ok",
        "answer": {
            "overview": "Valid overview.",
            "patterns": [],
            "limitations": [],
        },
        "sources": [],
        "retrieval": {
            "status": "ok",
            "top_k": 15,
            "returned_result_count": 0,
            "context_budget_tokens": 4000,
            "context_chunk_ids": [],
            "omitted_chunk_ids": [],
            "truncated_chunk_ids": [],
            "filters_applied": [],
            "rerank": True,
        },
        "generation": {
            "provider": "ollama",
            "model": "qwen2.5:7b-instruct",
            "prompt_version": "study_aid_v1",
            "temperature": 0.1,
            "attempt_count": 1,
            "citation_drops": 0,
            "error_category": None,
            "latency_ms": 4213,
        },
    }

    try:
        StudyResponse.model_validate(response_payload)
    except ValidationError:
        return
    raise AssertionError("planning field should be required")


def test_support_models_are_constructible() -> None:
    ranked = RankedChunk(
        chunk_id="cam-2023-p2-q4",
        chunk_level="question",
        parent_chunk_id=None,
        text="Question text",
        score=0.82,
        metadata={},
    )
    packed = PackedChunk(
        chunk=ranked,
        text="Question text",
        estimated_tokens=42,
        truncated=False,
    )
    packing_result = PackingResult(
        chunks=[packed],
        omitted_chunk_ids=[],
        truncated_chunk_ids=[],
        status="ok",
    )
    capabilities = ProviderCapabilities(
        json_schema_output=True,
        json_mode=True,
        max_context_tokens=32768,
    )
    validation_result = ValidationResult(
        draft=None,
        answer_status="ok",
        error_category=None,
    )
    assert packing_result.chunks[0].estimated_tokens == 42
    assert capabilities.json_schema_output is True
    assert validation_result.answer_status == "ok"
