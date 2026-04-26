from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError
from src.rendering.blocks import (
    RenderBlock,
    flatten_render_blocks,
    split_inline_math,
)

ADAPTER = TypeAdapter(list[RenderBlock])


def _roundtrip(payload: list[dict]) -> list[dict]:
    parsed = ADAPTER.validate_python(payload)
    return [block.model_dump() for block in parsed]


def _dump_runs(text: str) -> list[dict]:
    return [run.model_dump() for run in split_inline_math(text)]


def test_paragraph_with_text_and_math_runs_roundtrips() -> None:
    payload = [
        {
            "type": "paragraph",
            "runs": [
                {"type": "text", "text": "Compute "},
                {"type": "math", "latex": "x^2"},
                {"type": "text", "text": "."},
            ],
        }
    ]
    assert _roundtrip(payload) == payload


def test_all_six_block_types_roundtrip() -> None:
    payload = [
        {"type": "paragraph", "runs": [{"type": "text", "text": "p"}]},
        {
            "type": "list",
            "marker": "bullet",
            "items": [[{"type": "text", "text": "i1"}]],
        },
        {"type": "equation", "latex": "a+b"},
        {"type": "code", "code": "x = 1", "language": None},
        {"type": "table", "rows": [["h"], ["c"]], "media_id": None},
        {"type": "image", "media_id": "image_3"},
    ]
    assert _roundtrip(payload) == payload


def test_unknown_block_type_rejected() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python([{"type": "blockquote", "text": "x"}])


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python([{"type": "equation", "latex": "x", "display": True}])


def test_list_marker_must_be_known() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python([{"type": "list", "marker": "roman", "items": []}])


def test_split_inline_math_returns_text_run_when_no_math() -> None:
    assert _dump_runs("plain text") == [{"type": "text", "text": "plain text"}]


def test_split_inline_math_splits_single_math_run() -> None:
    assert _dump_runs("Compute $x^2$.") == [
        {"type": "text", "text": "Compute "},
        {"type": "math", "latex": "x^2"},
        {"type": "text", "text": "."},
    ]


def test_split_inline_math_splits_multiple_math_runs() -> None:
    assert _dump_runs("$a$ plus $b$") == [
        {"type": "math", "latex": "a"},
        {"type": "text", "text": " plus "},
        {"type": "math", "latex": "b"},
    ]


def test_split_inline_math_empty_string_returns_empty_list() -> None:
    assert split_inline_math("") == []


def test_split_inline_math_treats_escaped_dollar_as_delimiter_limitation() -> None:
    assert _dump_runs(r"Cost \$x$") == [
        {"type": "text", "text": "Cost \\"},
        {"type": "math", "latex": "x"},
    ]


def test_flatten_render_blocks_paragraph_preserves_inline_math() -> None:
    blocks = ADAPTER.validate_python(
        [
            {
                "type": "paragraph",
                "runs": [
                    {"type": "text", "text": "Compute "},
                    {"type": "math", "latex": "x^2"},
                    {"type": "text", "text": "."},
                ],
            }
        ]
    )
    assert flatten_render_blocks(blocks) == "Compute $x^2$."


def test_flatten_render_blocks_list_joins_items_by_newline() -> None:
    blocks = ADAPTER.validate_python(
        [
            {
                "type": "list",
                "marker": "ordered",
                "items": [
                    [{"type": "text", "text": "first"}],
                    [
                        {"type": "text", "text": "second "},
                        {"type": "math", "latex": "n"},
                    ],
                ],
            }
        ]
    )
    assert flatten_render_blocks(blocks) == "first\nsecond $n$"


def test_flatten_render_blocks_equation_uses_bare_latex() -> None:
    blocks = ADAPTER.validate_python([{"type": "equation", "latex": "a+b"}])
    assert flatten_render_blocks(blocks) == "a+b"


def test_flatten_render_blocks_code_uses_code_field() -> None:
    blocks = ADAPTER.validate_python(
        [{"type": "code", "code": "x = 1", "language": "python"}]
    )
    assert flatten_render_blocks(blocks) == "x = 1"


def test_flatten_render_blocks_table_uses_tabs_and_newlines() -> None:
    blocks = ADAPTER.validate_python(
        [{"type": "table", "rows": [["h1", "h2"], ["c1", "c2"]], "media_id": None}]
    )
    assert flatten_render_blocks(blocks) == "h1\th2\nc1\tc2"


def test_flatten_render_blocks_image_is_empty() -> None:
    blocks = ADAPTER.validate_python([{"type": "image", "media_id": "image_1"}])
    assert flatten_render_blocks(blocks) == ""


def test_flatten_render_blocks_joins_non_empty_blocks_with_blank_lines() -> None:
    blocks = ADAPTER.validate_python(
        [
            {"type": "paragraph", "runs": [{"type": "text", "text": "one"}]},
            {"type": "image", "media_id": "image_1"},
            {"type": "equation", "latex": "two"},
        ]
    )
    assert flatten_render_blocks(blocks) == "one\n\ntwo"
