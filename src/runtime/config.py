from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse

if TYPE_CHECKING:
    # Type-only import: validate_production_profile only annotates this type;
    # keeping it out of runtime imports is a choice, not cycle avoidance.
    from src.jobs.config import IngestQueueSettings

from limits import parse
from src.access.email import normalize_email
from src.search.providers.config import RetrievalProviderSettings
from src.storage.config import ObjectStorageSettings
from src.study.config import StudySettings

Environment = Literal["dev", "test", "prod"]

_LOCALHOST_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@dataclass(frozen=True)
class RateLimitSettings:
    redis_url: str
    key_secret: str
    search_user: str
    search_anon: str
    study_user: str
    study_anon: str


@dataclass(frozen=True)
class AppRuntimeSettings:
    environment: Environment
    enable_dev_routes: bool
    cors_allowed_origins: list[str]
    request_body_max_bytes: int
    query_max_chars: int
    search_limit_max: int
    study_top_k_max: int
    study_context_budget_tokens: int
    study_generation_max_output_tokens: int
    study_wall_clock_timeout_seconds: float
    rate_limit: RateLimitSettings
    admin_emails: frozenset[str] = frozenset()


def load_app_runtime_settings() -> AppRuntimeSettings:
    environment_raw = os.environ.get("APP_ENV", "dev").lower()
    if environment_raw not in ("dev", "test", "prod"):
        raise ValueError(f"Invalid APP_ENV: {environment_raw}")
    environment: Environment = environment_raw
    _reject_legacy_rate_limit_env()

    return AppRuntimeSettings(
        environment=environment,
        enable_dev_routes=_parse_bool(
            os.environ.get("ENABLE_DEV_ROUTES"), default=False
        ),
        cors_allowed_origins=_parse_csv(os.environ.get("CORS_ALLOWED_ORIGINS")),
        request_body_max_bytes=_parse_int(
            os.environ.get("REQUEST_BODY_MAX_BYTES"),
            default=131072,
            env_var="REQUEST_BODY_MAX_BYTES",
        ),
        query_max_chars=_parse_int(
            os.environ.get("QUERY_MAX_CHARS"),
            default=2000,
            env_var="QUERY_MAX_CHARS",
        ),
        search_limit_max=_parse_int(
            os.environ.get("SEARCH_LIMIT_MAX"),
            default=50,
            env_var="SEARCH_LIMIT_MAX",
        ),
        study_top_k_max=_parse_int(
            os.environ.get("STUDY_TOP_K_MAX"),
            default=20,
            env_var="STUDY_TOP_K_MAX",
        ),
        study_context_budget_tokens=_parse_int(
            os.environ.get("STUDY_CONTEXT_BUDGET_TOKENS"),
            default=4000,
            env_var="STUDY_CONTEXT_BUDGET_TOKENS",
        ),
        study_generation_max_output_tokens=_parse_int(
            os.environ.get("STUDY_GENERATION_MAX_OUTPUT_TOKENS"),
            default=1200,
            env_var="STUDY_GENERATION_MAX_OUTPUT_TOKENS",
        ),
        study_wall_clock_timeout_seconds=_parse_float(
            os.environ.get("STUDY_WALL_CLOCK_TIMEOUT_SECONDS"),
            default=45,
            env_var="STUDY_WALL_CLOCK_TIMEOUT_SECONDS",
        ),
        rate_limit=_load_rate_limit_settings(environment),
        admin_emails=_parse_admin_emails(os.environ.get("ADMIN_EMAILS")),
    )


def allowed_cors_origins(settings: AppRuntimeSettings) -> list[str]:
    if settings.cors_allowed_origins:
        return list(settings.cors_allowed_origins)
    if settings.environment == "dev":
        return list(_LOCALHOST_CORS_ORIGINS)
    return []


def validate_production_profile(
    runtime_settings: AppRuntimeSettings,
    retrieval_settings: RetrievalProviderSettings,
    study_settings: StudySettings,
    storage_settings: ObjectStorageSettings,
    ingest_queue_settings: "IngestQueueSettings | None" = None,
) -> None:
    if runtime_settings.environment != "prod":
        return

    violations: list[str] = []
    if runtime_settings.enable_dev_routes:
        violations.append("dev routes enabled")
    if retrieval_settings.embedding.provider == "local":
        violations.append("local embedding provider")
    if (
        retrieval_settings.rerank_enabled
        and retrieval_settings.rerank.provider == "local"
    ):
        violations.append("local rerank provider")
    if study_settings.generation.provider == "ollama":
        violations.append("local Ollama generation")
    if study_settings.planning.provider == "ollama":
        violations.append("local Ollama planning")
    if storage_settings.provider == "local":
        violations.append("local object storage")
    if ingest_queue_settings is not None and ingest_queue_settings.provider == "memory":
        violations.append("memory ingest queue")

    if violations:
        raise ValueError(
            "production profile validation failed: " + ", ".join(violations)
        )


def _parse_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_admin_emails(value: str | None) -> frozenset[str]:
    normalized = (normalize_email(item) for item in _parse_csv(value))
    return frozenset(email for email in normalized if email)


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, *, default: int, env_var: str) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{env_var} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{env_var} must be positive")
    return parsed


def _parse_float(value: str | None, *, default: float, env_var: str) -> float:
    if value is None or value == "":
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{env_var} must be a number") from exc
    if parsed <= 0:
        raise ValueError(f"{env_var} must be positive")
    return parsed


def _reject_legacy_rate_limit_env() -> None:
    legacy_env_vars = [
        env_var
        for env_var in ("RATE_LIMIT_WINDOW_SECONDS", "RATE_LIMIT_MAX_REQUESTS")
        if os.environ.get(env_var) is not None
    ]
    if not legacy_env_vars:
        return
    raise ValueError(
        ", ".join(legacy_env_vars)
        + " no longer supported; configure Redis-backed rate limiting with "
        "RATE_LIMIT_REDIS_URL, RATE_LIMIT_KEY_SECRET, RATE_LIMIT_SEARCH_USER, "
        "RATE_LIMIT_SEARCH_ANON, RATE_LIMIT_STUDY_USER, and RATE_LIMIT_STUDY_ANON"
    )


def _load_rate_limit_settings(environment: Environment) -> RateLimitSettings:
    redis_url = _parse_rate_limit_redis_url(
        _rate_limit_env(
            "RATE_LIMIT_REDIS_URL",
            environment=environment,
            default="redis://localhost:6379/0",
        )
    )
    return RateLimitSettings(
        redis_url=redis_url,
        key_secret=_rate_limit_env(
            "RATE_LIMIT_KEY_SECRET",
            environment=environment,
            default="dev-rate-limit-secret",
        ),
        search_user=_parse_rate_limit_policy(
            _rate_limit_env(
                "RATE_LIMIT_SEARCH_USER",
                environment=environment,
                default="60/minute",
            ),
            env_var="RATE_LIMIT_SEARCH_USER",
        ),
        search_anon=_parse_rate_limit_policy(
            _rate_limit_env(
                "RATE_LIMIT_SEARCH_ANON",
                environment=environment,
                default="20/minute",
            ),
            env_var="RATE_LIMIT_SEARCH_ANON",
        ),
        study_user=_parse_rate_limit_policy(
            _rate_limit_env(
                "RATE_LIMIT_STUDY_USER",
                environment=environment,
                default="10/hour",
            ),
            env_var="RATE_LIMIT_STUDY_USER",
        ),
        study_anon=_parse_rate_limit_policy(
            _rate_limit_env(
                "RATE_LIMIT_STUDY_ANON",
                environment=environment,
                default="3/hour",
            ),
            env_var="RATE_LIMIT_STUDY_ANON",
        ),
    )


def _rate_limit_env(env_var: str, *, environment: Environment, default: str) -> str:
    value = os.environ.get(env_var)
    if value is not None and value.strip():
        return value.strip()
    if environment == "prod":
        raise ValueError(f"production requires {env_var}")
    return default


def _parse_rate_limit_redis_url(value: str) -> str:
    scheme = urlparse(value).scheme
    if scheme not in {"redis", "rediss"}:
        raise ValueError("RATE_LIMIT_REDIS_URL must use redis:// or rediss://")
    return value


def _parse_rate_limit_policy(value: str, *, env_var: str) -> str:
    try:
        parse(value)
    except Exception as exc:
        raise ValueError(f"{env_var} must be a valid rate limit policy") from exc
    return value
