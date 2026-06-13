from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_OVERRIDE_NAMESPACES = {"generation", "context", "prompt", "planning"}


class GenerationSettings(BaseModel):
    provider: str = "ollama"
    model: str = "qwen2.5:7b-instruct"
    temperature: float = 0.1
    base_url: str = "http://localhost:11434"
    api_key: str | None = None
    request_timeout_seconds: float = 60
    max_provider_retries: int = 1
    total_generation_deadline_seconds: float = 75
    schema_repair_retries: int = 1


class ContextSettings(BaseModel):
    retrieval_top_k_default: int = 15
    budget_tokens: int = 4000
    max_single_chunk_tokens: int = 1200


class PromptSettings(BaseModel):
    version: str = "study_aid_v2"
    path: str = "prompts/study_aid_v2.yaml"


class PlanningSettings(BaseModel):
    provider: str = "ollama"
    model: str = "qwen2.5:7b-instruct"
    base_url: str = "http://localhost:11434"
    api_key: str | None = None
    temperature: float = 0.0
    request_timeout_seconds: float = 15
    total_planning_deadline_seconds: float = 20
    prompt_version: str = "query_planner_v2"
    prompt_path: str = "prompts/query_planner_v2.yaml"


class StudySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_prefix="",
        extra="ignore",
    )

    generation: GenerationSettings = Field(default_factory=GenerationSettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    prompt: PromptSettings = Field(default_factory=PromptSettings)
    planning: PlanningSettings = Field(default_factory=PlanningSettings)


def load_study_settings(config_dir: Path = Path("config")) -> StudySettings:
    """Load study settings from defaults, YAML files, then environment."""
    merged: dict[str, Any] = {}
    for filename in ("study.yaml", "study.local.yaml"):
        merged = _deep_merge(merged, _read_yaml(config_dir / filename))
    merged = _deep_merge(merged, _env_overrides())
    return StudySettings.model_validate(merged)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return loaded


def _env_overrides() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in os.environ.items():
        if "__" not in key:
            continue
        parts = [part.lower() for part in key.split("__")]
        if parts[0] not in ENV_OVERRIDE_NAMESPACES:
            continue
        cursor = result
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value
    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
