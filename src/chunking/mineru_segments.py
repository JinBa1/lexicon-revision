from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LogicalSegment:
    label: str | None
    blocks: list[dict[str, Any]]


def insert_label_prefix(blocks: list[dict[str, Any]], label: str) -> None:
    prefix = f"({label}) "
    for block in blocks:
        if block.get("type") == "paragraph":
            if _insert_prefix_into_runs(block.get("runs", []), prefix):
                return
        elif block.get("type") == "list":
            for item in block.get("items", []):
                if _insert_prefix_into_runs(item, prefix):
                    return
    blocks.insert(0, {"type": "paragraph", "runs": [{"type": "text", "text": prefix}]})


def _insert_prefix_into_runs(runs: list[dict[str, Any]], prefix: str) -> bool:
    for run in runs:
        if run.get("type") == "text":
            run["text"] = f"{prefix}{run.get('text', '')}"
            return True
    if runs:
        runs.insert(0, {"type": "text", "text": prefix})
        return True
    return False
