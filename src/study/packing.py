from __future__ import annotations

import re
from typing import Protocol

from src.study.models import PackedChunk, PackingResult, RankedChunk

TRUNCATION_MARKER = "[...truncated for context budget]"


class TokenEstimator(Protocol):
    def estimate(self, text: str) -> int: ...


class HeuristicTokenEstimator:
    def estimate(self, text: str) -> int:
        return max(1, len(text) // 4)


def dedupe_parent_child(chunks: list[RankedChunk]) -> list[RankedChunk]:
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    removed: set[str] = set()

    for chunk in chunks:
        parent_id = chunk.parent_chunk_id
        if chunk.chunk_level != "sub_question" or parent_id is None:
            continue

        parent = by_id.get(parent_id)
        if parent is None:
            continue

        if chunk.score > parent.score:
            removed.add(parent.chunk_id)
        else:
            removed.add(chunk.chunk_id)

    return [chunk for chunk in chunks if chunk.chunk_id not in removed]


def pack_chunks(
    chunks: list[RankedChunk],
    *,
    budget_tokens: int,
    max_single_chunk_tokens: int,
    estimator: TokenEstimator,
) -> PackingResult:
    packed: list[PackedChunk] = []
    omitted: list[str] = []
    truncated: list[str] = []
    used_tokens = 0

    for chunk in chunks:
        text = chunk.text
        estimated = estimator.estimate(text)
        was_truncated = False

        if estimated > max_single_chunk_tokens:
            text = _truncate_to_token_budget(text, max_single_chunk_tokens, estimator)
            estimated = estimator.estimate(text)
            was_truncated = True
            truncated.append(chunk.chunk_id)

        if used_tokens + estimated > budget_tokens:
            omitted.append(chunk.chunk_id)
            continue

        packed.append(
            PackedChunk(
                chunk=chunk,
                text=text,
                estimated_tokens=estimated,
                truncated=was_truncated,
            )
        )
        used_tokens += estimated

    if not packed and chunks:
        return PackingResult(
            chunks=[],
            omitted_chunk_ids=[chunk.chunk_id for chunk in chunks],
            truncated_chunk_ids=truncated,
            status="context_pack_failed",
        )

    return PackingResult(
        chunks=packed,
        omitted_chunk_ids=omitted,
        truncated_chunk_ids=truncated,
    )


def format_context_blocks(chunks: list[PackedChunk]) -> str:
    blocks = []
    for index, packed in enumerate(chunks, start=1):
        metadata = packed.chunk.metadata
        blocks.append(
            "\n".join(
                [
                    f"[SOURCE {index}]",
                    f"chunk_id: {packed.chunk.chunk_id}",
                    f"year: {metadata.get('year')}",
                    f"paper: {metadata.get('paper')}",
                    f"question: {metadata.get('question_number')}",
                    f"chunk_level: {packed.chunk.chunk_level}",
                    f"topic: {metadata.get('topic')}",
                    f"score: {packed.chunk.score:.4f}",
                    "",
                    "text:",
                    packed.text,
                ]
            )
        )
    return "\n\n".join(blocks)


def _truncate_to_token_budget(
    text: str,
    max_tokens: int,
    estimator: TokenEstimator,
) -> str:
    marker_budget = estimator.estimate(TRUNCATION_MARKER)
    target = max(1, max_tokens - marker_budget)
    words = re.findall(r"\S+", text)
    current: list[str] = []

    for word in words:
        candidate = " ".join([*current, word])
        if estimator.estimate(candidate) > target:
            break
        current.append(word)

    if not current:
        current = [text[: max(1, target * 4)]]

    return f"{' '.join(current).rstrip()} {TRUNCATION_MARKER}"
