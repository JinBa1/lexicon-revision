"""Tests for search tooling helpers.

These are infrastructure tests for CLI tooling only. They do not test product
search quality, real embeddings, or real reranking.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.search_tooling import (
    SUPPORTED_FILTER_KEYS,
    EvalCase,
    EvalSpec,
    build_filters,
    load_eval_spec,
    load_media_map,
    truncate_text,
)


def test_truncate_text_compacts_whitespace_and_truncates() -> None:
    """Infrastructure test for readable CLI previews only."""
    text = "alpha\n\n beta   gamma delta"

    assert truncate_text(text, 14) == "alpha beta..."


def test_build_filters_omits_none_values() -> None:
    """Infrastructure test for CLI filter construction only."""
    filters = build_filters(
        year=2025,
        paper=None,
        topic="Algorithms",
        question=None,
        marks_min=None,
        has_code=False,
        has_figure=None,
        has_table=True,
    )

    assert filters == {
        "year": 2025,
        "topic": "Algorithms",
        "has_code": False,
        "has_table": True,
    }


def test_build_filters_includes_full_supported_filter_set() -> None:
    """Infrastructure test for CLI filter construction only."""
    filters = build_filters(
        year=2025,
        paper=3,
        topic="Algorithms",
        question=7,
        marks_min=10,
        has_code=True,
        has_figure=False,
        has_table=True,
    )

    assert set(filters) == SUPPORTED_FILTER_KEYS
    assert filters["question_number"] == 7


def test_build_filters_maps_question_to_question_number() -> None:
    """Infrastructure test for CLI filter construction only."""
    assert build_filters(question=7) == {"question_number": 7}


def test_load_eval_spec_normalizes_question_filter_to_question_number(
    tmp_path: Path,
) -> None:
    """Infrastructure test for eval schema validation only."""
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text(
        """
name: tool_test
cases:
  - id: case-1
    query: algorithms practice
    filters:
      question: 3
      paper: 1
    expected:
      any_topics:
        - Algorithms
""",
        encoding="utf-8",
    )

    spec = load_eval_spec(eval_path)

    assert spec.cases[0].filters == {"question_number": 3, "paper": 1}


def test_load_eval_spec_rejects_question_and_question_number_conflict(
    tmp_path: Path,
) -> None:
    """Infrastructure test for eval schema validation only."""
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text(
        """
name: tool_test
cases:
  - id: case-1
    query: algorithms practice
    filters:
      question: 3
      question_number: 4
    expected:
      any_topics:
        - Algorithms
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="question.*question_number"):
        load_eval_spec(eval_path)


def test_load_media_map_returns_empty_for_missing_file(tmp_path: Path) -> None:
    """Infrastructure test for sidecar handling only."""
    assert load_media_map(tmp_path, "missing") == {}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("not json", {}),
        (json.dumps(["chunk-1"]), {}),
    ],
)
def test_load_media_map_returns_empty_for_invalid_or_non_mapping_json(
    tmp_path: Path,
    payload: str,
    expected: dict[str, list[dict[str, object]]],
) -> None:
    """Infrastructure test for sidecar handling only."""
    sidecar = tmp_path / "test_media_map.json"
    sidecar.write_text(payload, encoding="utf-8")

    assert load_media_map(tmp_path, "test") == expected


def test_load_media_map_reads_valid_sidecar(tmp_path: Path) -> None:
    """Infrastructure test for sidecar handling only."""
    sidecar = tmp_path / "test_media_map.json"
    sidecar.write_text(
        json.dumps(
            {
                "chunk-1": [
                    {
                        "media_id": "fig-1",
                        "kind": "image",
                        "file_path": "fig.png",
                        "relation": "direct",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    media_map = load_media_map(tmp_path, "test")

    assert media_map["chunk-1"][0]["media_id"] == "fig-1"
    assert media_map["chunk-1"][0] == {
        "media_id": "fig-1",
        "kind": "image",
        "file_path": "fig.png",
        "relation": "direct",
    }


def test_load_eval_spec_accepts_valid_yaml(tmp_path: Path) -> None:
    """Infrastructure test for eval YAML parsing only."""
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text(
        """
name: tool_test
collection: test-collection
default_top_k: 3
cases:
  - id: case-1
    query: algorithms practice
    filters:
      paper: 1
    expected:
      any_topics:
        - Algorithms
""",
        encoding="utf-8",
    )

    spec = load_eval_spec(eval_path)

    assert isinstance(spec, EvalSpec)
    assert spec.name == "tool_test"
    assert spec.description is None
    assert spec.cases[0] == EvalCase(
        id="case-1",
        query="algorithms practice",
        filters={"paper": 1},
        any_chunk_ids=[],
        any_topics=["Algorithms"],
        top_k=3,
        notes=None,
    )


def test_load_eval_spec_allows_null_optional_strings(tmp_path: Path) -> None:
    """Infrastructure test for eval schema validation only."""
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text(
        """
name: tool_test
description: null
collection: null
cases:
  - id: case-1
    query: algorithms practice
    notes: null
    expected:
      any_topics:
        - Algorithms
""",
        encoding="utf-8",
    )

    spec = load_eval_spec(eval_path)

    assert spec.description is None
    assert spec.collection is None
    assert spec.cases[0].notes is None


def test_load_eval_spec_omits_null_filter_values(tmp_path: Path) -> None:
    """Infrastructure test for eval schema validation only."""
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text(
        """
name: tool_test
cases:
  - id: case-1
    query: algorithms practice
    filters:
      paper: null
      has_code: null
    expected:
      any_topics:
        - Algorithms
""",
        encoding="utf-8",
    )

    spec = load_eval_spec(eval_path)

    assert spec.cases[0].filters == {}


@pytest.mark.parametrize(
    ("yaml_text", "message"),
    [
        ("- not-a-mapping\n", "top level"),
        (
            """
name: ""
cases:
  - id: case-1
    query: question
    expected:
      any_chunk_ids:
        - chunk-1
""",
            "non-empty string field 'name'",
        ),
        (
            """
name: valid
default_top_k: 0
cases:
  - id: case-1
    query: question
    expected:
      any_chunk_ids:
        - chunk-1
""",
            "default_top_k",
        ),
        (
            """
name: valid
default_top_k: true
cases:
  - id: case-1
    query: question
    expected:
      any_chunk_ids:
        - chunk-1
""",
            "default_top_k",
        ),
        (
            """
name: valid
""",
            "non-empty list field 'cases'",
        ),
        (
            """
name: valid
cases: []
""",
            "non-empty list field 'cases'",
        ),
        (
            """
name: valid
default_top_k: 0
cases:
  - id: case-1
    query: question
    expected:
      any_chunk_ids:
        - chunk-1
""",
            "default_top_k",
        ),
    ],
)
def test_load_eval_spec_validates_top_level_structure(
    tmp_path: Path,
    yaml_text: str,
    message: str | None,
) -> None:
    """Infrastructure test for eval schema validation only."""
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_eval_spec(eval_path)


@pytest.mark.parametrize(
    ("yaml_text", "message"),
    [
        (
            """
name: valid
description: []
cases:
  - id: case-1
    query: question
    expected:
      any_chunk_ids:
        - chunk-1
""",
            "description",
        ),
        (
            """
name: valid
collection: false
cases:
  - id: case-1
    query: question
    expected:
      any_chunk_ids:
        - chunk-1
""",
            "collection",
        ),
        (
            """
name: valid
cases:
  - id: case-1
    query: question
    notes: []
    expected:
      any_chunk_ids:
        - chunk-1
""",
            "notes",
        ),
        (
            """
name: valid
cases:
  - id: case-1
    query: question
    notes: ""
    expected:
      any_chunk_ids:
        - chunk-1
""",
            "notes",
        ),
    ],
)
def test_load_eval_spec_validates_optional_string_fields(
    tmp_path: Path,
    yaml_text: str,
    message: str,
) -> None:
    """Infrastructure test for eval schema validation only."""
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_eval_spec(eval_path)


@pytest.mark.parametrize(
    ("raw_case", "message"),
    [
        (["not", "a", "mapping"], "must be a mapping"),
        ({"id": "", "query": "question", "expected": {"any_chunk_ids": ["c"]}}, "id"),
        ({"id": "case-1", "query": "", "expected": {"any_chunk_ids": ["c"]}}, "query"),
        (
            {
                "id": "case-1",
                "query": "question",
                "filters": ["not", "a", "mapping"],
                "expected": {"any_chunk_ids": ["c"]},
            },
            "filters must be a mapping",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "filters": False,
                "expected": {"any_chunk_ids": ["c"]},
            },
            "filters must be a mapping",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "filters": {"unknown": True},
                "expected": {"any_chunk_ids": ["c"]},
            },
            "unsupported filters",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "filters": {"paper": False},
                "expected": {"any_chunk_ids": ["c"]},
            },
            "filter 'paper'",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "filters": {"year": True},
                "expected": {"any_chunk_ids": ["c"]},
            },
            "filter 'year'",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "filters": {"marks_min": False},
                "expected": {"any_chunk_ids": ["c"]},
            },
            "filter 'marks_min'",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "filters": {"topic": ""},
                "expected": {"any_chunk_ids": ["c"]},
            },
            "filter 'topic'",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "filters": {"has_code": "false"},
                "expected": {"any_chunk_ids": ["c"]},
            },
            "filter 'has_code'",
        ),
        (
            {"id": "case-1", "query": "question", "expected": ["not", "a", "mapping"]},
            "requires expected mapping",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "expected": {"any_chunk_ids": False, "any_topics": ["Algorithms"]},
            },
            "any_chunk_ids must be a list of strings",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "expected": {"any_chunk_ids": ["c"], "any_topics": False},
            },
            "any_topics must be a list of strings",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "expected": {"any_chunk_ids": "not-a-list"},
            },
            "any_chunk_ids must be a list of strings",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "expected": {"any_topics": "not-a-list"},
            },
            "any_topics must be a list of strings",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "expected": {},
            },
            "requires any_chunk_ids or any_topics",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "expected": {"any_chunk_ids": ["c"], "top_k": 0},
            },
            "top_k must be a positive integer",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "expected": {"any_chunk_ids": ["c"], "top_k": True},
            },
            "top_k must be a positive integer",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "expected": {"any_chunk_ids": ["c"]},
                "notes": [],
            },
            "notes",
        ),
        (
            {
                "id": "case-1",
                "query": "question",
                "expected": {"any_chunk_ids": ["c"]},
                "notes": "",
            },
            "notes",
        ),
    ],
)
def test_parse_case_and_eval_spec_validate_case_shapes(
    tmp_path: Path,
    raw_case: object,
    message: str,
) -> None:
    """Infrastructure test for eval schema validation only, not search quality."""
    eval_path = tmp_path / "eval.yaml"
    payload = {"name": "valid", "cases": [raw_case]}
    eval_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_eval_spec(eval_path)


@pytest.mark.parametrize(
    ("ref", "message"),
    [
        ([{"kind": "image", "relation": "direct"}], "media_id"),
        (
            [{"media_id": "fig-1", "kind": "diagram", "relation": "direct"}],
            "kind",
        ),
        (
            [{"media_id": "fig-1", "kind": "image", "relation": "local_only"}],
            "relation",
        ),
        (
            [
                {
                    "media_id": "fig-1",
                    "kind": "image",
                    "file_path": {"path": "fig.png"},
                    "relation": "direct",
                }
            ],
            "file_path",
        ),
    ],
)
def test_load_media_map_rejects_invalid_refs(
    tmp_path: Path,
    ref: list[dict[str, object]],
    message: str,
) -> None:
    """Infrastructure test for sidecar handling only."""
    sidecar = tmp_path / "test_media_map.json"
    sidecar.write_text(json.dumps({"chunk-1": ref}), encoding="utf-8")

    assert load_media_map(tmp_path, "test") == {}


def test_load_media_map_preserves_valid_ref_dicts(tmp_path: Path) -> None:
    """Infrastructure test for sidecar handling only."""
    sidecar = tmp_path / "test_media_map.json"
    sidecar.write_text(
        json.dumps(
            {
                "chunk-1": [
                    {
                        "media_id": "fig-1",
                        "kind": "image",
                        "file_path": "fig.png",
                        "relation": "direct",
                        "caption": "Figure 1",
                    },
                    {
                        "media_id": "table-1",
                        "kind": "table",
                        "file_path": "table.csv",
                        "relation": "visible_from_child",
                        "extra": {"rows": 12},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    media_map = load_media_map(tmp_path, "test")

    assert media_map == {
        "chunk-1": [
            {
                "media_id": "fig-1",
                "kind": "image",
                "file_path": "fig.png",
                "relation": "direct",
                "caption": "Figure 1",
            },
            {
                "media_id": "table-1",
                "kind": "table",
                "file_path": "table.csv",
                "relation": "visible_from_child",
                "extra": {"rows": 12},
            },
        ]
    }
