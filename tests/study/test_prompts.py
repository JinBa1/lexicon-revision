from __future__ import annotations

from pathlib import Path

import pytest
from src.study.prompts import load_prompt_template


def test_load_prompt_template_and_render(tmp_path: Path) -> None:
    prompt_path = tmp_path / "study_aid_v1.yaml"
    prompt_path.write_text(
        """
version: study_aid_v1
system: "System text"
user: |
  Query: {{ query }}
  Sources:
  {{ context_blocks }}
""",
        encoding="utf-8",
    )

    template = load_prompt_template(prompt_path)
    messages = template.render(
        query="dynamic programming",
        retrieval_queries=["dynamic programming"],
        context_blocks="[SOURCE 1]",
    )

    assert template.version == "study_aid_v1"
    assert messages == [
        {"role": "system", "content": "System text"},
        {
            "role": "user",
            "content": "Query: dynamic programming\nSources:\n[SOURCE 1]".strip(),
        },
    ]


def test_prompt_template_renders_retrieval_queries(tmp_path: Path) -> None:
    prompt_path = tmp_path / "study_aid_v2.yaml"
    prompt_path.write_text(
        """
version: study_aid_v2
system: "System text"
user: |
  Q: {{ query }}
  R: {{ retrieval_queries | join('; ') }}
  C: {{ context_blocks }}
""",
        encoding="utf-8",
    )

    template = load_prompt_template(prompt_path)
    messages = template.render(
        query="dp",
        retrieval_queries=["dynamic programming recurrence"],
        context_blocks="CTX",
    )

    assert template.version == "study_aid_v2"
    assert messages == [
        {"role": "system", "content": "System text"},
        {
            "role": "user",
            "content": "Q: dp\nR: dynamic programming recurrence\nC: CTX",
        },
    ]


def test_prompt_template_requires_retrieval_queries(tmp_path: Path) -> None:
    prompt_path = tmp_path / "study_aid_v2.yaml"
    prompt_path.write_text(
        """
version: study_aid_v2
system: "System text"
user: "{{ retrieval_queries | join('; ') }}"
""",
        encoding="utf-8",
    )

    template = load_prompt_template(prompt_path)

    with pytest.raises(TypeError):
        template.render(query="dp", context_blocks="CTX")  # type: ignore[call-arg]


def test_real_study_aid_v2_template_loads_and_renders() -> None:
    template = load_prompt_template(Path("prompts/study_aid_v2.yaml"))

    messages = template.render(
        query="original dynamic programming question",
        retrieval_queries=["dynamic programming recurrence evidence"],
        context_blocks="[SOURCE 1] recurrence context",
    )

    user_message = messages[1]["content"]

    assert template.version == "study_aid_v2"
    assert "original dynamic programming question" in user_message
    assert "dynamic programming recurrence evidence" in user_message
    assert "[SOURCE 1] recurrence context" in user_message


def test_study_aid_prompt_forbids_derived_citation_ids() -> None:
    template = load_prompt_template(Path("prompts/study_aid_v1.yaml"))

    system = template.system

    assert "exact chunk_id strings" in system
    assert "Do not invent, shorten, extend, or add subpart suffixes" in system
    assert "cam-2025-p2-q7(a)(i)" in system


def test_study_aid_prompt_handles_limited_mixed_evidence() -> None:
    template = load_prompt_template(Path("prompts/study_aid_v1.yaml"))

    system = template.system

    assert "If only one or a few sources directly address the query" in system
    assert "I found limited direct evidence" in system
    assert "do not say that the sources contain no direct examples" in system
    assert "If you cite a source as directly relevant" in system
    assert 'set answer_status to "partial"' in system
    assert (
        "Never write that retrieved sources do not directly address the query" in system
    )


def test_render_includes_generation_guidance_when_present() -> None:
    template = load_prompt_template(Path("prompts/study_aid_v3.yaml"))
    messages = template.render(
        query="paging",
        retrieval_queries=["virtual memory paging"],
        context_blocks="[ctx]",
        generation_guidance="Emphasise recurring patterns.",
    )
    assert "Emphasise recurring patterns." in messages[1]["content"]


def test_render_omits_guidance_block_when_empty() -> None:
    template = load_prompt_template(Path("prompts/study_aid_v3.yaml"))
    messages = template.render(
        query="paging",
        retrieval_queries=["virtual memory paging"],
        context_blocks="[ctx]",
        generation_guidance="",
    )
    assert "Guidance for this answer" not in messages[1]["content"]
