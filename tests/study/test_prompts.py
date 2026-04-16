from __future__ import annotations

from pathlib import Path

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
