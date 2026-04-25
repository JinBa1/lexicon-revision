from __future__ import annotations

import pytest
from src.runtime.config import (
    allowed_cors_origins,
    load_app_runtime_settings,
    validate_production_profile,
)
from src.search.providers.config import load_retrieval_provider_settings
from src.storage.config import load_object_storage_settings
from src.study.config import load_study_settings


def test_dev_profile_defaults_to_localhost_cors_and_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("ENABLE_DEV_ROUTES", raising=False)
    monkeypatch.delenv("REQUEST_BODY_MAX_BYTES", raising=False)
    monkeypatch.delenv("QUERY_MAX_CHARS", raising=False)
    monkeypatch.delenv("SEARCH_LIMIT_MAX", raising=False)
    monkeypatch.delenv("RETRIEVAL_VECTOR_MIN_SCORE", raising=False)
    monkeypatch.delenv("RETRIEVAL_RERANK_MIN_SCORE", raising=False)
    monkeypatch.delenv("STUDY_TOP_K_MAX", raising=False)
    monkeypatch.delenv("STUDY_CONTEXT_BUDGET_TOKENS", raising=False)
    monkeypatch.delenv("STUDY_GENERATION_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("STUDY_WALL_CLOCK_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("RATE_LIMIT_WINDOW_SECONDS", raising=False)
    monkeypatch.delenv("RATE_LIMIT_MAX_REQUESTS", raising=False)

    settings = load_app_runtime_settings()

    assert settings.environment == "dev"
    assert allowed_cors_origins(settings) == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    assert settings.request_body_max_bytes == 131072
    assert settings.query_max_chars == 2000
    assert settings.search_limit_max == 50
    assert settings.retrieval_vector_min_score is None
    assert settings.retrieval_rerank_min_score is None
    assert settings.study_top_k_max == 20
    assert settings.study_context_budget_tokens == 4000
    assert settings.study_generation_max_output_tokens == 1200
    assert settings.study_wall_clock_timeout_seconds == 45
    assert settings.rate_limit_window_seconds == 60
    assert settings.rate_limit_max_requests == 30


def test_prod_profile_defaults_to_no_cors_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    settings = load_app_runtime_settings()

    assert settings.environment == "prod"
    assert allowed_cors_origins(settings) == []


def test_retrieval_min_scores_parse_optional_floats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RETRIEVAL_VECTOR_MIN_SCORE", "0.72")
    monkeypatch.setenv("RETRIEVAL_RERANK_MIN_SCORE", "0.18")

    settings = load_app_runtime_settings()

    assert settings.retrieval_vector_min_score == 0.72
    assert settings.retrieval_rerank_min_score == 0.18


def test_retrieval_min_scores_treat_empty_strings_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RETRIEVAL_VECTOR_MIN_SCORE", "")
    monkeypatch.setenv("RETRIEVAL_RERANK_MIN_SCORE", "")

    settings = load_app_runtime_settings()

    assert settings.retrieval_vector_min_score is None
    assert settings.retrieval_rerank_min_score is None


@pytest.mark.parametrize(
    ("env_var", "value"),
    [
        ("RETRIEVAL_VECTOR_MIN_SCORE", "not-a-number"),
        ("RETRIEVAL_VECTOR_MIN_SCORE", "nan"),
        ("RETRIEVAL_VECTOR_MIN_SCORE", "inf"),
        ("RETRIEVAL_RERANK_MIN_SCORE", "not-a-number"),
        ("RETRIEVAL_RERANK_MIN_SCORE", "nan"),
        ("RETRIEVAL_RERANK_MIN_SCORE", "inf"),
    ],
)
def test_retrieval_min_scores_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    env_var: str,
    value: str,
) -> None:
    monkeypatch.setenv(env_var, value)

    with pytest.raises(ValueError, match=env_var):
        load_app_runtime_settings()


def test_production_profile_validation_rejects_local_runtime_shapes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("ENABLE_DEV_ROUTES", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("RERANK_PROVIDER", "local")
    monkeypatch.setenv("RERANK_ENABLED", "true")
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", "devsecret")

    runtime_settings = load_app_runtime_settings()
    retrieval_settings = load_retrieval_provider_settings()
    study_settings = load_study_settings(config_dir=tmp_path)
    storage_settings = load_object_storage_settings()

    with pytest.raises(ValueError, match="production profile"):
        validate_production_profile(
            runtime_settings,
            retrieval_settings,
            study_settings,
            storage_settings,
        )
