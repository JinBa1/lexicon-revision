from __future__ import annotations

from src.study.config import GenerationSettings, PlanningSettings, StudySettings
from src.study.providers.base import GenerationProvider
from src.study.providers.http_openai import OpenAICompatibleProvider
from src.study.providers.ollama import OllamaProvider


def build_study_providers(
    settings: StudySettings,
) -> tuple[GenerationProvider, GenerationProvider]:
    return build_generation_providers(settings)


def build_generation_providers(
    settings: StudySettings,
) -> tuple[GenerationProvider, GenerationProvider]:
    planner_provider = build_generation_provider(settings.planning, role="planning")
    generation_provider = build_generation_provider(
        settings.generation,
        role="generation",
    )
    return planner_provider, generation_provider


def build_generation_provider(
    settings: GenerationSettings | PlanningSettings,
    *,
    role: str = "generation",
) -> GenerationProvider:
    if settings.provider == "ollama":
        return OllamaProvider(
            base_url=settings.base_url,
            model=settings.model,
            max_retries=getattr(settings, "max_provider_retries", 1),
        )
    if settings.provider == "openai_compatible":
        if not settings.api_key:
            raise ValueError(f"{role} openai_compatible provider requires api_key")
        return OpenAICompatibleProvider(
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
            request_timeout_seconds=settings.request_timeout_seconds,
        )
    raise ValueError(f"Unsupported generation provider: {settings.provider}")
