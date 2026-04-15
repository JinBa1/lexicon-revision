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
