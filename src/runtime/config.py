from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Literal

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
    rate_limit_window_seconds: int
    rate_limit_max_requests: int
    retrieval_vector_min_score: float | None = None
    retrieval_rerank_min_score: float | None = None


def load_app_runtime_settings() -> AppRuntimeSettings:
    environment_raw = os.environ.get("APP_ENV", "dev").lower()
    if environment_raw not in ("dev", "test", "prod"):
        raise ValueError(f"Invalid APP_ENV: {environment_raw}")

    return AppRuntimeSettings(
        environment=environment_raw,
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
        retrieval_vector_min_score=_parse_optional_float(
            os.environ.get("RETRIEVAL_VECTOR_MIN_SCORE"),
            env_var="RETRIEVAL_VECTOR_MIN_SCORE",
        ),
        retrieval_rerank_min_score=_parse_optional_float(
            os.environ.get("RETRIEVAL_RERANK_MIN_SCORE"),
            env_var="RETRIEVAL_RERANK_MIN_SCORE",
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
        rate_limit_window_seconds=_parse_int(
            os.environ.get("RATE_LIMIT_WINDOW_SECONDS"),
            default=60,
            env_var="RATE_LIMIT_WINDOW_SECONDS",
        ),
        rate_limit_max_requests=_parse_int(
            os.environ.get("RATE_LIMIT_MAX_REQUESTS"),
            default=30,
            env_var="RATE_LIMIT_MAX_REQUESTS",
        ),
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

    if violations:
        raise ValueError(
            "production profile validation failed: " + ", ".join(violations)
        )


def _parse_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


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


def _parse_optional_float(value: str | None, *, env_var: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{env_var} must be a finite number") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{env_var} must be a finite number")
    return parsed
