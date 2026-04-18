from __future__ import annotations

from pathlib import Path

import yaml
from jinja2 import Template
from pydantic import BaseModel


class PromptTemplate(BaseModel):
    version: str
    system: str
    user: str

    def render(
        self,
        *,
        query: str,
        retrieval_queries: list[str],
        context_blocks: str,
    ) -> list[dict[str, str]]:
        user_content = Template(self.user).render(
            query=query,
            retrieval_queries=retrieval_queries,
            context_blocks=context_blocks,
        )
        return [
            {"role": "system", "content": self.system.strip()},
            {"role": "user", "content": user_content.strip()},
        ]


def load_prompt_template(path: Path) -> PromptTemplate:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return PromptTemplate.model_validate(loaded)
