from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter
from src.rendering.blocks import RenderBlock

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "test"
    / "fixtures"
    / "render-blocks"
    / "sample.json"
)


def test_sample_fixture_validates_against_render_block_schema() -> None:
    payload = json.loads(FIXTURE_PATH.read_text())

    blocks = TypeAdapter(list[RenderBlock]).validate_python(payload)
    reserialized = [block.model_dump() for block in blocks]

    assert reserialized == payload


def test_sample_fixture_covers_all_six_block_types() -> None:
    payload = json.loads(FIXTURE_PATH.read_text())

    types = {block["type"] for block in payload}

    assert types == {"paragraph", "list", "equation", "code", "table", "image"}
