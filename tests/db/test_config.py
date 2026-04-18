from __future__ import annotations

import pytest
from src.db.config import (
    DatabaseSettings,
    load_database_settings,
)


def test_load_database_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DATABASE_URL",
        "RETRIEVAL_BACKEND",
        "EMBEDDING_MODEL_ID",
        "EMBEDDING_DIMENSION",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = load_database_settings()

    assert (
        settings.database_url
        == "postgresql+psycopg://rag_exam:rag_exam@localhost:5434/rag_exam"
    )
    assert settings.retrieval_backend == "postgres"
    assert settings.embedding_model_id == "BAAI/bge-base-en-v1.5"
    assert settings.embedding_dimension == 768


def test_load_database_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/app")
    monkeypatch.setenv("RETRIEVAL_BACKEND", "postgres")
    monkeypatch.setenv("EMBEDDING_MODEL_ID", "voyage-4-lite")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "1024")

    settings = load_database_settings()

    assert settings == DatabaseSettings(
        database_url="postgresql+psycopg://u:p@db:5432/app",
        retrieval_backend="postgres",
        embedding_model_id="voyage-4-lite",
        embedding_dimension=1024,
    )


def test_load_database_settings_rejects_bad_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RETRIEVAL_BACKEND", "sqlite")

    with pytest.raises(ValueError, match="RETRIEVAL_BACKEND"):
        load_database_settings()


def test_load_database_settings_rejects_bad_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_DIMENSION", "0")

    with pytest.raises(ValueError, match="EMBEDDING_DIMENSION"):
        load_database_settings()
