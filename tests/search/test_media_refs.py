from __future__ import annotations

import math
from typing import Any

import pytest
from src.chunking.models import Chunk
from src.search.media_refs import (
    sanitize_db_media_refs,
    validate_media_refs_by_chunk_id,
)


def _chunk(chunk_id: str) -> Chunk:
    return Chunk(
        id=chunk_id,
        chunk_level="question",
        parent_chunk_id=None,
        text="body",
        year=2025,
        paper=1,
        question_number=1,
        topic="Algorithms",
        author=None,
        tripos_part=None,
        sub_question_label=None,
        marks=None,
        total_marks=20,
        has_code=False,
        has_figure=True,
        has_table=False,
        media=[],
        source_pdf="y2025p1q1.pdf",
        warnings=[],
    )


def _valid_ref(**overrides: Any) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "media_id": "figure_1",
        "kind": "image",
        "relation": "direct",
        "object_key": "artifacts/mineru/run-y2025p1q1/images/figure_1.png",
        "page_number": 1,
        "bbox": [10, 20.5, 300, 180],
        "owner_level": "question",
        "owner_label": None,
        "order_index": 0,
        "text_payload": None,
        "description": "diagram",
    }
    ref.update(overrides)
    return ref


def test_sanitize_db_media_refs_keeps_allowed_fields() -> None:
    refs = sanitize_db_media_refs([_valid_ref()])

    assert refs == [_valid_ref()]


@pytest.mark.parametrize("field", ["file_path", "access_url"])
def test_sanitize_db_media_refs_rejects_forbidden_fields(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        sanitize_db_media_refs([_valid_ref(**{field: "unsafe"})])


def test_sanitize_db_media_refs_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="unknown media ref fields"):
        sanitize_db_media_refs([_valid_ref(extra="value")])


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "video"},
        {"relation": "local_only"},
        {"object_key": "../figure_1.png"},
        {"bbox": [0, 1, math.inf, 3]},
        {"order_index": -1},
        {"text_payload": 12},
    ],
)
def test_sanitize_db_media_refs_rejects_invalid_shapes(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        sanitize_db_media_refs([_valid_ref(**overrides)])


def test_sanitize_db_media_refs_rejects_non_list_payload() -> None:
    with pytest.raises(ValueError, match="media refs must be a list"):
        sanitize_db_media_refs({"media_id": "figure_1"})  # type: ignore[arg-type]


def test_validate_media_refs_by_chunk_id_rejects_unknown_chunk_ids() -> None:
    with pytest.raises(ValueError, match="unknown chunk id"):
        validate_media_refs_by_chunk_id(
            chunks=[_chunk("chunk-1")],
            media_refs_by_chunk_id={"missing": []},
        )


def test_validate_media_refs_by_chunk_id_rejects_non_dict_map() -> None:
    with pytest.raises(ValueError, match="media_refs_by_chunk_id must be a dict"):
        validate_media_refs_by_chunk_id(
            chunks=[_chunk("chunk-1")],
            media_refs_by_chunk_id=[],  # type: ignore[arg-type]
        )


def test_validate_media_refs_by_chunk_id_defaults_missing_chunks_to_empty() -> None:
    refs = validate_media_refs_by_chunk_id(
        chunks=[_chunk("chunk-1"), _chunk("chunk-2")],
        media_refs_by_chunk_id={"chunk-1": [_valid_ref()]},
    )

    assert refs["chunk-1"] == [_valid_ref()]
    assert refs["chunk-2"] == []
