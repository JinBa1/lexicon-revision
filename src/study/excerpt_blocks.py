from __future__ import annotations

from pydantic import TypeAdapter
from src.rendering.blocks import RenderBlock, flatten_render_blocks

RENDER_BLOCKS_ADAPTER = TypeAdapter(list[RenderBlock])


def truncate_excerpt_blocks(
    blocks: list[RenderBlock],
    budget_chars: int,
) -> list[RenderBlock]:
    """Return whole render blocks for an excerpt.

    The first selected paragraph, or the first block when no paragraph exists, may
    exceed ``budget_chars``. That preserves the render-block contract: never split
    blocks, and always return at least one usable block when input is non-empty.
    """
    if not blocks:
        return []

    has_paragraph = any(_block_type(block) == "paragraph" for block in blocks)
    selected: list[RenderBlock] = []
    included_paragraph = False
    for block in blocks:
        is_paragraph = _block_type(block) == "paragraph"
        candidate = [*selected, block]
        candidate_chars = len(_flatten_blocks(candidate))
        if candidate_chars > budget_chars:
            if is_paragraph and not included_paragraph:
                selected.append(block)
                included_paragraph = True
            if selected or has_paragraph:
                break
            return [blocks[0]]
        selected.append(block)
        included_paragraph = included_paragraph or is_paragraph

    if selected and (included_paragraph or not has_paragraph):
        return selected

    first_paragraph = next(
        (block for block in blocks if _block_type(block) == "paragraph"),
        None,
    )
    if first_paragraph is not None:
        if selected:
            return [*selected, first_paragraph]
        return [first_paragraph]
    return [blocks[0]]


def _block_type(block: RenderBlock) -> str | None:
    if isinstance(block, dict):
        return block.get("type")
    return block.type


def _flatten_blocks(blocks: list[RenderBlock]) -> str:
    validated_blocks = RENDER_BLOCKS_ADAPTER.validate_python(blocks)
    return flatten_render_blocks(validated_blocks)
