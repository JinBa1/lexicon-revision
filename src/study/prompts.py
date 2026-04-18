from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Template
from pydantic import BaseModel


class PromptTemplate(BaseModel):
    version: str
    system: str
    user: str

    def render(self, **kwargs: Any) -> list[dict[str, str]]:
        system_content = Template(self.system).render(**kwargs)
        user_content = Template(self.user).render(**kwargs)
        return [
            {"role": "system", "content": system_content.strip()},
            {"role": "user", "content": user_content.strip()},
        ]


def load_prompt_template(path: Path) -> PromptTemplate:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return PromptTemplate.model_validate(loaded)
