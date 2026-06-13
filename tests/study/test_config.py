from __future__ import annotations

from pathlib import Path

from src.study.config import _env_overrides, load_study_settings


def test_load_study_settings_uses_defaults_when_files_missing(tmp_path: Path) -> None:
    settings = load_study_settings(config_dir=tmp_path)

    assert settings.generation.provider == "ollama"
    assert settings.generation.model == "qwen2.5:7b-instruct"
    assert settings.generation.request_timeout_seconds == 60
    assert settings.context.retrieval_top_k_default == 15
    assert settings.context.budget_tokens == 4000
    assert settings.prompt.version == "study_aid_v2"
    assert settings.prompt.path == "prompts/study_aid_v2.yaml"


def test_load_study_settings_merges_yaml_then_local_then_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "study.yaml").write_text(
        """
generation:
  model: yaml-model
  temperature: 0.2
context:
  budget_tokens: 3000
""",
        encoding="utf-8",
    )
    (tmp_path / "study.local.yaml").write_text(
        """
generation:
  model: local-model
context:
  max_single_chunk_tokens: 900
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GENERATION__MODEL", "env-model")

    settings = load_study_settings(config_dir=tmp_path)

    assert settings.generation.model == "env-model"
    assert settings.generation.temperature == 0.2
    assert settings.context.budget_tokens == 3000
    assert settings.context.max_single_chunk_tokens == 900


def test_load_study_settings_ignores_unknown_env_namespaces(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OTHER_SERVICE__GENERATION__MODEL", "wrong-model")
    monkeypatch.setenv("CONTEXT__BUDGET_TOKENS", "2500")

    settings = load_study_settings(config_dir=tmp_path)

    assert settings.generation.model == "qwen2.5:7b-instruct"
    assert settings.context.budget_tokens == 2500


def test_load_study_settings_has_planning_defaults(tmp_path: Path) -> None:
    settings = load_study_settings(config_dir=tmp_path)

    assert settings.planning.temperature == 0.0
    assert settings.planning.request_timeout_seconds == 15
    assert settings.planning.total_planning_deadline_seconds == 20
    assert settings.planning.prompt_version == "query_planner_v2"
    assert settings.planning.prompt_path == "prompts/query_planner_v2.yaml"


def test_load_study_settings_applies_planning_env_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLANNING__REQUEST_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("PLANNING__PROMPT_VERSION", "query_planner_v1_custom")

    settings = load_study_settings(config_dir=tmp_path)

    assert settings.planning.request_timeout_seconds == 5
    assert settings.planning.prompt_version == "query_planner_v1_custom"


def test_load_study_settings_applies_planning_connection_env_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLANNING__PROVIDER", "openai_compatible")
    monkeypatch.setenv("PLANNING__BASE_URL", "https://planner.example.com/v1")
    monkeypatch.setenv("PLANNING__API_KEY", "planner-key")
    monkeypatch.setenv("GENERATION__BASE_URL", "https://generator.example.com/v1")
    monkeypatch.setenv("GENERATION__API_KEY", "generator-key")

    settings = load_study_settings(config_dir=tmp_path)

    assert settings.planning.provider == "openai_compatible"
    assert settings.planning.base_url == "https://planner.example.com/v1"
    assert settings.planning.api_key == "planner-key"
    assert settings.generation.base_url == "https://generator.example.com/v1"
    assert settings.generation.api_key == "generator-key"


def test_env_overrides_keeps_only_known_settings_namespaces(monkeypatch) -> None:
    monkeypatch.setenv("OTHER_SERVICE__GENERATION__MODEL", "wrong-model")
    monkeypatch.setenv("GENERATION__MODEL", "env-model")

    overrides = _env_overrides()

    assert overrides == {"generation": {"model": "env-model"}}
