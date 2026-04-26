"""Render block schema and text compatibility helpers."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class TextRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text"]
    text: str


class MathRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["math"]
    latex: str


InlineRun = Annotated[TextRun | MathRun, Field(discriminator="type")]


class ParagraphBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["paragraph"]
    runs: list[InlineRun]


class ListBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["list"]
    marker: Literal["bullet", "ordered", "plain"]
    items: list[list[InlineRun]]


class EquationBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["equation"]
    latex: str


class CodeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["code"]
    code: str
    language: str | None


class TableBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["table"]
    rows: list[list[str]]
    media_id: str | None


class ImageBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["image"]
    media_id: str


RenderBlock = Annotated[
    ParagraphBlock | ListBlock | EquationBlock | CodeBlock | TableBlock | ImageBlock,
    Field(discriminator="type"),
]


INLINE_MATH_RE = re.compile(r"\$([^$\n]+?)\$")


def split_inline_math(text: str) -> list[InlineRun]:
    """Split inline ``$latex$`` spans into text and math runs.

    Limitation: a backslash-dollar sequence is still treated as a delimiter.
    """
    if text == "":
        return []

    runs: list[InlineRun] = []
    position = 0
    for match in INLINE_MATH_RE.finditer(text):
        if match.start() > position:
            runs.append(TextRun(type="text", text=text[position : match.start()]))
        runs.append(MathRun(type="math", latex=match.group(1)))
        position = match.end()

    if position < len(text):
        runs.append(TextRun(type="text", text=text[position:]))

    return runs


def flatten_render_blocks(blocks: list[RenderBlock]) -> str:
    """Flatten structured render blocks back to the legacy text payload."""
    flattened = [_flatten_block(block) for block in blocks]
    return "\n\n".join(part for part in flattened if part)


def _flatten_block(block: RenderBlock) -> str:
    match block.type:
        case "paragraph":
            return _flatten_runs(block.runs)
        case "list":
            return "\n".join(_flatten_runs(item) for item in block.items)
        case "equation":
            return block.latex
        case "code":
            return block.code
        case "table":
            return "\n".join("\t".join(row) for row in block.rows)
        case "image":
            return ""


def _flatten_runs(runs: list[InlineRun]) -> str:
    parts: list[str] = []
    for run in runs:
        match run.type:
            case "text":
                parts.append(run.text)
            case "math":
                parts.append(f"${run.latex}$")
    return "".join(parts)
