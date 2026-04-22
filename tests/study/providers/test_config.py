from __future__ import annotations

import pytest
from src.study.config import load_study_settings
from src.study.providers.config import build_generation_providers
from src.study.providers.http_openai import OpenAICompatibleProvider
from src.study.providers.ollama import OllamaProvider


@pytest.mark.anyio
async def test_build_generation_providers_keeps_planner_and_generator_separate(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLANNING__PROVIDER", "openai_compatible")
    monkeypatch.setenv("PLANNING__BASE_URL", "https://planner.example.com/v1")
    monkeypatch.setenv("PLANNING__API_KEY", "planner-key")
    monkeypatch.setenv("PLANNING__MODEL", "planner-model")
    monkeypatch.setenv("GENERATION__PROVIDER", "ollama")
    monkeypatch.setenv("GENERATION__BASE_URL", "http://ollama.example.com")
    monkeypatch.setenv("GENERATION__MODEL", "generator-model")

    settings = load_study_settings(config_dir=tmp_path)

    planner_provider, generation_provider = build_generation_providers(settings)

    assert isinstance(planner_provider, OpenAICompatibleProvider)
    assert isinstance(generation_provider, OllamaProvider)
    assert planner_provider is not generation_provider
    assert planner_provider.model_name == "planner-model"
    assert generation_provider.model_name == "generator-model"

    await planner_provider.aclose()
    await generation_provider.aclose()


@pytest.mark.anyio
async def test_build_generation_providers_supports_default_ollama_settings() -> None:
    planner_provider, generation_provider = build_generation_providers(
        load_study_settings()
    )

    assert isinstance(planner_provider, OllamaProvider)
    assert isinstance(generation_provider, OllamaProvider)
    assert planner_provider is not generation_provider
    assert planner_provider.model_name == "qwen2.5:7b-instruct"
    assert generation_provider.model_name == "qwen2.5:7b-instruct"

    await planner_provider.aclose()
    await generation_provider.aclose()


def test_build_generation_providers_reports_missing_planning_api_key(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLANNING__PROVIDER", "openai_compatible")
    monkeypatch.setenv("PLANNING__BASE_URL", "https://planner.example.com/v1")
    monkeypatch.setenv("PLANNING__MODEL", "planner-model")

    settings = load_study_settings(config_dir=tmp_path)

    with pytest.raises(
        ValueError,
        match="planning openai_compatible provider requires api_key",
    ):
        build_generation_providers(settings)


def test_build_generation_providers_reports_missing_generation_api_key(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLANNING__PROVIDER", "openai_compatible")
    monkeypatch.setenv("PLANNING__BASE_URL", "https://planner.example.com/v1")
    monkeypatch.setenv("PLANNING__API_KEY", "planner-key")
    monkeypatch.setenv("PLANNING__MODEL", "planner-model")
    monkeypatch.setenv("GENERATION__PROVIDER", "openai_compatible")
    monkeypatch.setenv("GENERATION__BASE_URL", "https://generator.example.com/v1")
    monkeypatch.setenv("GENERATION__MODEL", "generator-model")

    settings = load_study_settings(config_dir=tmp_path)

    with pytest.raises(
        ValueError,
        match="generation openai_compatible provider requires api_key",
    ):
        build_generation_providers(settings)
