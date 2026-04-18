from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Engine, create_engine

DEFAULT_DATABASE_URL = "postgresql+psycopg://rag_exam:rag_exam@localhost:5434/rag_exam"
DEFAULT_EMBEDDING_MODEL_ID = "BAAI/bge-base-en-v1.5"
DEFAULT_EMBEDDING_DIMENSION = 768

RetrievalBackend = Literal["chroma", "postgres"]


@dataclass(frozen=True)
class DatabaseSettings:
    database_url: str
    retrieval_backend: RetrievalBackend
    embedding_model_id: str
    embedding_dimension: int


def load_database_settings() -> DatabaseSettings:
    backend = os.environ.get("RETRIEVAL_BACKEND", "postgres").lower()
    if backend not in ("chroma", "postgres"):
        raise ValueError("RETRIEVAL_BACKEND must be 'chroma' or 'postgres'")
    dimension = _positive_int(
        os.environ.get("EMBEDDING_DIMENSION"),
        default=DEFAULT_EMBEDDING_DIMENSION,
        env_var="EMBEDDING_DIMENSION",
    )
    return DatabaseSettings(
        database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        retrieval_backend=backend,
        embedding_model_id=os.environ.get(
            "EMBEDDING_MODEL_ID",
            DEFAULT_EMBEDDING_MODEL_ID,
        ),
        embedding_dimension=dimension,
    )


def create_database_engine(settings: DatabaseSettings | None = None) -> Engine:
    settings = settings or load_database_settings()
    return create_engine(settings.database_url, future=True)


def _positive_int(value: str | None, *, default: int, env_var: str) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{env_var} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{env_var} must be a positive integer")
    return parsed
