from __future__ import annotations

from pydantic import TypeAdapter
from src.rendering.blocks import RenderBlock, flatten_render_blocks
from src.study.excerpt_blocks import truncate_excerpt_blocks

RENDER_BLOCKS_ADAPTER = TypeAdapter(list[RenderBlock])


def test_truncate_excerpt_blocks_keeps_whole_blocks_within_budget() -> None:
    blocks = [
        {"type": "paragraph", "runs": [{"type": "text", "text": "short"}]},
        {"type": "equation", "latex": "x = y"},
        {"type": "paragraph", "runs": [{"type": "text", "text": "too long"}]},
    ]

    assert truncate_excerpt_blocks(blocks, budget_chars=12) == blocks[:2]


def test_truncate_excerpt_blocks_includes_first_paragraph_when_over_budget() -> None:
    block = {
        "type": "paragraph",
        "runs": [{"type": "text", "text": "long paragraph beyond budget"}],
    }

    assert truncate_excerpt_blocks([block], budget_chars=5) == [block]


def test_truncate_excerpt_blocks_includes_later_paragraph_even_over_budget() -> None:
    equation = {"type": "equation", "latex": "x"}
    paragraph = {
        "type": "paragraph",
        "runs": [{"type": "text", "text": "long paragraph beyond budget"}],
    }

    assert truncate_excerpt_blocks([equation, paragraph], budget_chars=5) == [
        equation,
        paragraph,
    ]


def test_truncate_excerpt_blocks_counts_separators_in_budget() -> None:
    blocks = [
        {"type": "paragraph", "runs": [{"type": "text", "text": "aaaaa"}]},
        {"type": "paragraph", "runs": [{"type": "text", "text": "bbbbb"}]},
    ]

    result = truncate_excerpt_blocks(blocks, budget_chars=11)

    assert result == [blocks[0]]
    assert (
        len(flatten_render_blocks(RENDER_BLOCKS_ADAPTER.validate_python(result))) <= 11
    )


def test_truncate_excerpt_blocks_uses_first_block_when_no_paragraph() -> None:
    block = {"type": "image", "media_id": "image_1"}

    assert truncate_excerpt_blocks([block], budget_chars=5) == [block]


def test_truncate_excerpt_blocks_returns_empty_for_no_blocks() -> None:
    assert truncate_excerpt_blocks([], budget_chars=500) == []
