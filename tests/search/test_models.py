"""Contract tests for the search response Pydantic models."""

import pytest
from pydantic import ValidationError
from src.search.models import (
    MediaRefResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)


def test_search_result_construction():
    """SearchResult holds chunk data, score, metadata, and media."""
    result = SearchResult(
        chunk_id="cam-2023-p2-q5",
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        text="Consider the following BST...",
        score=0.87,
        metadata={
            "year": 2023,
            "paper": 2,
            "question_number": 5,
            "topic": "Algorithms",
            "author": "avsm2",
            "tripos_part": "Part IA",
            "marks": None,
            "total_marks": 20,
            "source_pdf": "y2023p2q5.pdf",
            "has_code": True,
            "has_figure": False,
            "has_table": False,
        },
        media=[],
    )
    assert result.chunk_id == "cam-2023-p2-q5"
    assert result.score == 0.87
    assert result.metadata["year"] == 2023
    assert result.media == []


def test_search_result_with_media():
    """SearchResult can carry MediaRefResponse entries."""
    media = MediaRefResponse(
        media_id="cam-2023-p2-q5-figure_1",
        kind="image",
        object_key="artifacts/mineru/run-y2023p2q5/images/figure_1.png",
        access_url="http://localhost:8000/_dev/object/GET/...",
        relation="direct",
    )
    result = SearchResult(
        chunk_id="cam-2023-p2-q5",
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        text="Consider the following BST...",
        score=0.87,
        metadata={},
        media=[media],
    )
    assert len(result.media) == 1
    assert result.media[0].media_id == "cam-2023-p2-q5-figure_1"
    assert result.media[0].object_key.endswith("figure_1.png")
    assert result.media[0].access_url is not None


def test_search_result_accepts_render_blocks_and_serializes_legacy_null() -> None:
    result = SearchResult(
        chunk_id="cam-2023-p2-q5",
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        text="Consider the following BST...",
        score=0.87,
        metadata={},
        media=[],
        render_blocks=None,
    )
    payload = result.model_dump(mode="json")
    assert payload["render_blocks"] is None

    result_with_blocks = SearchResult(
        chunk_id="cam-2023-p2-q5",
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        text="Consider the following BST...",
        score=0.87,
        metadata={},
        media=[],
        render_blocks=[
            {"type": "paragraph", "runs": [{"type": "text", "text": "Consider"}]}
        ],
    )
    assert result_with_blocks.model_dump(mode="json")["render_blocks"] == [
        {"type": "paragraph", "runs": [{"type": "text", "text": "Consider"}]}
    ]


def test_search_result_sub_question():
    """Sub-question results surface label and parent linkage."""
    result = SearchResult(
        chunk_id="cam-2023-p2-q5-a",
        chunk_level="sub_question",
        parent_chunk_id="cam-2023-p2-q5",
        sub_question_label="a",
        text="Part (a) text...",
        score=0.65,
        metadata={},
        media=[],
    )
    assert result.chunk_level == "sub_question"
    assert result.parent_chunk_id == "cam-2023-p2-q5"
    assert result.sub_question_label == "a"


def test_search_response_construction():
    """SearchResponse wraps query context and result list."""
    response = SearchResponse(
        query="binary search trees",
        collection="cam-cs-tripos",
        results=[],
        total=0,
    )
    assert response.query == "binary search trees"
    assert response.collection == "cam-cs-tripos"
    assert response.total == 0


def test_search_result_rejects_invalid_chunk_level():
    """Chunk-level values stay constrained to the two supported result types."""
    with pytest.raises(ValidationError):
        SearchResult(
            chunk_id="cam-2023-p2-q5",
            chunk_level="part",
            parent_chunk_id=None,
            sub_question_label=None,
            text="Question text",
            score=0.87,
            metadata={},
            media=[],
        )


def test_media_ref_rejects_invalid_relation():
    """Media relation values stay aligned with the chunking media model."""
    with pytest.raises(ValidationError):
        MediaRefResponse(
            media_id="cam-2023-p2-q5-figure_1",
            kind="image",
            object_key="artifacts/mineru/run-y2023p2q5/images/figure_1.png",
            access_url="http://localhost:8000/_dev/object/GET/...",
            relation="local_only",
        )


def test_search_request_accepts_repeated_filter_conditions() -> None:
    request = SearchRequest.model_validate(
        {
            "query": "binary search",
            "collection": "cam-cs-tripos-fixture",
            "filters": [
                {"field": "year", "op": "gte", "value": 2020},
                {"field": "year", "op": "lte", "value": 2024},
            ],
            "limit": 10,
            "rerank": False,
        }
    )

    assert [item.model_dump() for item in request.filters] == [
        {"field": "year", "op": "gte", "value": 2020},
        {"field": "year", "op": "lte", "value": 2024},
    ]
