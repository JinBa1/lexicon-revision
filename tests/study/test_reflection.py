from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from src.study.reflection import (
    QueryReformulationDraft,
    RelevanceGradingDraft,
    load_grading_prompt,
    load_reformulation_prompt,
)


def test_real_grader_prompt_loads() -> None:
    template = load_grading_prompt(Path("prompts/relevance_grader_v1.yaml"))
    assert template.version == "relevance_grader_v1"
    assert template.system.strip()
    assert template.user.strip()


def test_real_reflect_prompt_loads() -> None:
    template = load_reformulation_prompt(Path("prompts/reflect_query_v1.yaml"))
    assert template.version == "reflect_query_v1"
    assert template.system.strip()
    assert template.user.strip()


def test_grading_prompt_render_lists_chunks(tmp_path: Path) -> None:
    prompt_path = tmp_path / "grader.yaml"
    prompt_path.write_text(
        'version: grader_custom\nsystem: "Grade chunks."\n'
        'user: "Q: {{ query }}\\n{% for c in chunks %}{{ c.chunk_id }}: '
        '{{ c.excerpt }}\\n{% endfor %}"\n',
        encoding="utf-8",
    )
    template = load_grading_prompt(prompt_path)
    messages = template.render(
        query="binary search",
        chunks=[{"chunk_id": "c1", "excerpt": "bst excerpt"}],
    )
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "binary search" in messages[1]["content"]
    assert "c1" in messages[1]["content"]
    assert "bst excerpt" in messages[1]["content"]


def test_reflect_prompt_render_includes_query_and_critique(tmp_path: Path) -> None:
    prompt_path = tmp_path / "reflect.yaml"
    prompt_path.write_text(
        'version: reflect_custom\nsystem: "Reformulate."\n'
        'user: "orig {{ query }} crit {{ critique }}"\n',
        encoding="utf-8",
    )
    template = load_reformulation_prompt(prompt_path)
    messages = template.render(query="bst rotations", critique="got hashing")
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "bst rotations" in messages[1]["content"]
    assert "got hashing" in messages[1]["content"]


def test_load_grading_prompt_rejects_non_mapping(tmp_path: Path) -> None:
    prompt_path = tmp_path / "bad.yaml"
    prompt_path.write_text("- not\n- a mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a YAML mapping"):
        load_grading_prompt(prompt_path)


def test_relevance_grading_draft_defaults_and_forbids_extra() -> None:
    draft = RelevanceGradingDraft.model_validate({"accepted_chunk_ids": ["a"]})
    assert draft.accepted_chunk_ids == ["a"]
    assert draft.critique == ""
    with pytest.raises(ValidationError):
        RelevanceGradingDraft.model_validate({"accepted_chunk_ids": [], "surprise": 1})


def test_query_reformulation_draft_defaults_and_forbids_extra() -> None:
    assert QueryReformulationDraft.model_validate({}).reformulated_query == ""
    with pytest.raises(ValidationError):
        QueryReformulationDraft.model_validate({"reformulated_query": "x", "y": 1})
