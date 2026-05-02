from __future__ import annotations

import httpx
import pytest
from src.runtime.config import (
    AppRuntimeSettings,
    RateLimitSettings,
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
    monkeypatch.delenv("STUDY_TOP_K_MAX", raising=False)
    monkeypatch.delenv("STUDY_CONTEXT_BUDGET_TOKENS", raising=False)
    monkeypatch.delenv("STUDY_GENERATION_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("STUDY_WALL_CLOCK_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("RATE_LIMIT_REDIS_URL", raising=False)
    monkeypatch.delenv("RATE_LIMIT_KEY_SECRET", raising=False)
    monkeypatch.delenv("RATE_LIMIT_SEARCH_USER", raising=False)
    monkeypatch.delenv("RATE_LIMIT_SEARCH_ANON", raising=False)
    monkeypatch.delenv("RATE_LIMIT_STUDY_USER", raising=False)
    monkeypatch.delenv("RATE_LIMIT_STUDY_ANON", raising=False)

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
    assert settings.study_top_k_max == 20
    assert settings.study_context_budget_tokens == 4000
    assert settings.study_generation_max_output_tokens == 1200
    assert settings.study_wall_clock_timeout_seconds == 45
    assert settings.rate_limit.redis_url == "redis://localhost:6379/0"
    assert settings.rate_limit.key_secret == "dev-rate-limit-secret"
    assert settings.rate_limit.search_user == "60/minute"
    assert settings.rate_limit.search_anon == "20/minute"
    assert settings.rate_limit.study_user == "10/hour"
    assert settings.rate_limit.study_anon == "3/hour"


def test_rate_limit_settings_accept_rediss_and_policy_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(
        "RATE_LIMIT_REDIS_URL", "rediss://default:secret@example.upstash.io:6379"
    )
    monkeypatch.setenv("RATE_LIMIT_KEY_SECRET", "local-secret")
    monkeypatch.setenv("RATE_LIMIT_SEARCH_USER", "12/minute")
    monkeypatch.setenv("RATE_LIMIT_SEARCH_ANON", "5/minute")
    monkeypatch.setenv("RATE_LIMIT_STUDY_USER", "4/hour")
    monkeypatch.setenv("RATE_LIMIT_STUDY_ANON", "1/hour")

    settings = load_app_runtime_settings()

    assert (
        settings.rate_limit.redis_url
        == "rediss://default:secret@example.upstash.io:6379"
    )
    assert settings.rate_limit.search_user == "12/minute"
    assert settings.rate_limit.study_anon == "1/hour"


def test_zero_rate_limit_policy_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("RATE_LIMIT_SEARCH_USER", "0/minute")

    settings = load_app_runtime_settings()

    assert settings.rate_limit.search_user == "0/minute"


def test_rate_limit_response_headers_are_exported_for_cors() -> None:
    from src.runtime.rate_limit import RATE_LIMIT_RESPONSE_HEADERS

    assert RATE_LIMIT_RESPONSE_HEADERS == [
        "Retry-After",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ]


@pytest.mark.anyio
async def test_cors_exposes_rate_limit_response_headers() -> None:
    from src.main import create_app

    app = create_app(
        runtime_settings=AppRuntimeSettings(
            environment="test",
            enable_dev_routes=False,
            cors_allowed_origins=["https://frontend.example"],
            request_body_max_bytes=131072,
            query_max_chars=2000,
            search_limit_max=50,
            study_top_k_max=20,
            study_context_budget_tokens=4000,
            study_generation_max_output_tokens=1200,
            study_wall_clock_timeout_seconds=45,
            rate_limit=RateLimitSettings(
                redis_url="redis://localhost:6379/0",
                key_secret="test-secret",
                search_user="60/minute",
                search_anon="20/minute",
                study_user="10/hour",
                study_anon="3/hour",
            ),
        )
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/healthz",
            headers={"Origin": "https://frontend.example"},
        )

    exposed_headers = {
        header.strip()
        for header in response.headers["access-control-expose-headers"].split(",")
    }
    assert "Retry-After" in exposed_headers
    assert "X-RateLimit-Limit" in exposed_headers
    assert "X-RateLimit-Remaining" in exposed_headers
    assert "X-RateLimit-Reset" in exposed_headers


@pytest.mark.parametrize(
    "legacy_env_var",
    ["RATE_LIMIT_WINDOW_SECONDS", "RATE_LIMIT_MAX_REQUESTS"],
)
def test_legacy_in_memory_rate_limit_env_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    legacy_env_var: str,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(legacy_env_var, "7")

    with pytest.raises(
        ValueError,
        match=(
            f"{legacy_env_var}.*RATE_LIMIT_REDIS_URL.*RATE_LIMIT_KEY_SECRET"
            ".*RATE_LIMIT_SEARCH_USER.*RATE_LIMIT_SEARCH_ANON"
            ".*RATE_LIMIT_STUDY_USER.*RATE_LIMIT_STUDY_ANON"
        ),
    ):
        load_app_runtime_settings()


def test_test_profile_defaults_to_local_rate_limit_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("RATE_LIMIT_REDIS_URL", raising=False)
    monkeypatch.delenv("RATE_LIMIT_KEY_SECRET", raising=False)
    monkeypatch.delenv("RATE_LIMIT_SEARCH_USER", raising=False)
    monkeypatch.delenv("RATE_LIMIT_SEARCH_ANON", raising=False)
    monkeypatch.delenv("RATE_LIMIT_STUDY_USER", raising=False)
    monkeypatch.delenv("RATE_LIMIT_STUDY_ANON", raising=False)

    settings = load_app_runtime_settings()

    assert settings.environment == "test"
    assert settings.rate_limit.redis_url == "redis://localhost:6379/0"
    assert settings.rate_limit.key_secret == "dev-rate-limit-secret"
    assert settings.rate_limit.search_user == "60/minute"
    assert settings.rate_limit.search_anon == "20/minute"
    assert settings.rate_limit.study_user == "10/hour"
    assert settings.rate_limit.study_anon == "3/hour"


@pytest.mark.parametrize(
    "missing_env_var",
    [
        "RATE_LIMIT_REDIS_URL",
        "RATE_LIMIT_KEY_SECRET",
        "RATE_LIMIT_SEARCH_USER",
        "RATE_LIMIT_SEARCH_ANON",
        "RATE_LIMIT_STUDY_USER",
        "RATE_LIMIT_STUDY_ANON",
    ],
)
def test_prod_rate_limit_settings_are_required(
    monkeypatch: pytest.MonkeyPatch,
    missing_env_var: str,
) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    _set_valid_prod_rate_limit_env(monkeypatch)
    monkeypatch.delenv(missing_env_var, raising=False)

    with pytest.raises(ValueError, match=f"production requires {missing_env_var}"):
        load_app_runtime_settings()


def test_invalid_rate_limit_policy_fails_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("RATE_LIMIT_SEARCH_USER", "not-a-limit")

    with pytest.raises(ValueError, match="RATE_LIMIT_SEARCH_USER"):
        load_app_runtime_settings()


def test_invalid_rate_limit_redis_scheme_fails_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", "https://example.com")

    with pytest.raises(ValueError, match="RATE_LIMIT_REDIS_URL"):
        load_app_runtime_settings()


def _set_valid_prod_rate_limit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RATE_LIMIT_REDIS_URL", "rediss://default:secret@example.upstash.io:6379"
    )
    monkeypatch.setenv("RATE_LIMIT_KEY_SECRET", "prod-secret")
    monkeypatch.setenv("RATE_LIMIT_SEARCH_USER", "60/minute")
    monkeypatch.setenv("RATE_LIMIT_SEARCH_ANON", "20/minute")
    monkeypatch.setenv("RATE_LIMIT_STUDY_USER", "10/hour")
    monkeypatch.setenv("RATE_LIMIT_STUDY_ANON", "3/hour")


def test_prod_profile_defaults_to_no_cors_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    _set_valid_prod_rate_limit_env(monkeypatch)

    settings = load_app_runtime_settings()

    assert settings.environment == "prod"
    assert allowed_cors_origins(settings) == []


def test_runtime_settings_do_not_expose_global_retrieval_thresholds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("RETRIEVAL_VECTOR_MIN_SCORE", "0.72")
    monkeypatch.setenv("RETRIEVAL_RERANK_MIN_SCORE", "0.18")

    settings = load_app_runtime_settings()

    assert not hasattr(settings, "retrieval_vector_min_score")
    assert not hasattr(settings, "retrieval_rerank_min_score")


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
    _set_valid_prod_rate_limit_env(monkeypatch)

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
