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

    validated_blocks = RENDER_BLOCKS_ADAPTER.validate_python(blocks)
    block_texts = [flatten_render_blocks([block]) for block in validated_blocks]
    has_paragraph = any(_block_type(block) == "paragraph" for block in blocks)
    selected: list[RenderBlock] = []
    included_paragraph = False
    flattened_chars = 0
    for index, block in enumerate(blocks):
        is_paragraph = _block_type(block) == "paragraph"
        candidate_chars = _candidate_flattened_length(
            flattened_chars,
            block_texts[index],
        )
        if candidate_chars > budget_chars:
            if is_paragraph and not included_paragraph:
                selected.append(block)
                included_paragraph = True
            if selected or has_paragraph:
                break
            return [blocks[0]]
        selected.append(block)
        flattened_chars = candidate_chars
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


def _candidate_flattened_length(current_chars: int, block_text: str) -> int:
    if not block_text:
        return current_chars
    if current_chars == 0:
        return len(block_text)
    return current_chars + 2 + len(block_text)
