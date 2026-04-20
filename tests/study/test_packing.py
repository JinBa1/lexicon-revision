from __future__ import annotations

from src.metadata_schema.models import CollectionMetadataSchema
from src.study.models import RankedChunk
from src.study.packing import (
    HeuristicTokenEstimator,
    dedupe_parent_child,
    format_context_blocks,
    pack_chunks,
)


def _schema() -> CollectionMetadataSchema:
    return CollectionMetadataSchema.model_validate(
        {
            "version": 1,
            "fields": [
                {
                    "key": "year",
                    "label": "Year",
                    "type": "integer",
                    "operators": ["eq"],
                    "exposed": False,
                },
                {
                    "key": "author",
                    "label": "Author",
                    "type": "string",
                    "operators": ["eq"],
                    "exposed": True,
                },
                {
                    "key": "tripos_part",
                    "label": "Tripos Part",
                    "type": "string",
                    "operators": ["eq"],
                    "exposed": True,
                },
            ],
        }
    )


def chunk(
    chunk_id: str,
    *,
    level: str = "question",
    parent: str | None = None,
    score: float = 1.0,
    text: str = "alpha beta gamma",
) -> RankedChunk:
    return RankedChunk(
        chunk_id=chunk_id,
        chunk_level=level,
        parent_chunk_id=parent,
        text=text,
        score=score,
        metadata={
            "year": 2023,
            "author": "abc123",
            "tripos_part": "Part IB",
        },
    )


def test_dedupe_parent_child_keeps_higher_ranked_parent() -> None:
    parent = chunk("parent", score=0.95)
    child = chunk("child", level="sub_question", parent="parent", score=0.9)

    result = dedupe_parent_child([parent, child])

    assert [item.chunk_id for item in result] == ["parent"]


def test_dedupe_parent_child_keeps_higher_ranked_child() -> None:
    child = chunk("child", level="sub_question", parent="parent", score=0.95)
    parent = chunk("parent", score=0.9)

    result = dedupe_parent_child([child, parent])

    assert [item.chunk_id for item in result] == ["child"]


def test_pack_chunks_omits_items_that_do_not_fit_budget() -> None:
    chunks = [
        chunk("a", text="a" * 40),
        chunk("b", text="b" * 40),
        chunk("c", text="c" * 40),
    ]

    result = pack_chunks(
        chunks,
        budget_tokens=20,
        max_single_chunk_tokens=20,
        estimator=HeuristicTokenEstimator(),
    )

    assert [packed.chunk.chunk_id for packed in result.chunks] == ["a", "b"]
    assert result.omitted_chunk_ids == ["c"]


def test_pack_chunks_truncates_oversized_item() -> None:
    result = pack_chunks(
        [chunk("large", text="x" * 100)],
        budget_tokens=20,
        max_single_chunk_tokens=10,
        estimator=HeuristicTokenEstimator(),
    )

    assert result.status == "ok"
    assert result.truncated_chunk_ids == ["large"]
    assert result.chunks[0].truncated is True
    assert result.chunks[0].text.endswith("[...truncated for context budget]")


def test_format_context_blocks_includes_stable_metadata() -> None:
    packed = pack_chunks(
        [chunk("cam-2023-p2-q4", text="recurrence text")],
        budget_tokens=100,
        max_single_chunk_tokens=100,
        estimator=HeuristicTokenEstimator(),
    )

    rendered = format_context_blocks(packed.chunks, _schema())

    assert "[SOURCE 1]" in rendered
    assert "chunk_id: cam-2023-p2-q4" in rendered
    assert "year:" not in rendered.lower()
    assert "Author: abc123" in rendered
    assert "Tripos Part: Part IB" in rendered
    assert "text:\nrecurrence text" in rendered
