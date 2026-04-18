from __future__ import annotations

import pytest
from src.storage.base import ObjectStorageConfigError
from src.storage.config import (
    build_object_storage,
    load_object_storage_settings,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in [
        "OBJECT_STORAGE_PROVIDER",
        "OBJECT_STORAGE_BUCKET",
        "OBJECT_STORAGE_ENDPOINT_URL",
        "OBJECT_STORAGE_REGION",
        "OBJECT_STORAGE_ACCESS_KEY_ID",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "OBJECT_STORAGE_LOCAL_ROOT",
        "OBJECT_STORAGE_DEV_PRESIGN_BASE_URL",
        "OBJECT_STORAGE_DEV_PRESIGN_SECRET",
    ]:
        monkeypatch.delenv(var, raising=False)


def test_default_provider_is_local(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", "devsecret")
    settings = load_object_storage_settings()
    assert settings.provider == "local"
    assert settings.local is not None
    assert settings.local.root == tmp_path
    assert settings.s3 is None


def test_local_missing_presign_secret_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path))
    settings = load_object_storage_settings()
    with pytest.raises(ObjectStorageConfigError, match="DEV_PRESIGN_SECRET"):
        build_object_storage(settings)


def test_s3_reads_all_fields(monkeypatch) -> None:
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "my-bucket")
    monkeypatch.setenv("OBJECT_STORAGE_ENDPOINT_URL", "https://r2.example.com")
    monkeypatch.setenv("OBJECT_STORAGE_REGION", "auto")
    monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", "s")
    settings = load_object_storage_settings()
    assert settings.provider == "s3"
    assert settings.s3 is not None
    assert settings.s3.bucket == "my-bucket"
    assert settings.s3.endpoint_url == "https://r2.example.com"


def test_s3_missing_bucket_rejected(monkeypatch) -> None:
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", "s")
    with pytest.raises(ObjectStorageConfigError, match="BUCKET"):
        load_object_storage_settings()


def test_unknown_provider_rejected(monkeypatch) -> None:
    monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "gcs")
    with pytest.raises(ObjectStorageConfigError, match="provider"):
        load_object_storage_settings()


def test_build_local_storage_instance(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OBJECT_STORAGE_DEV_PRESIGN_SECRET", "devsecret")
    settings = load_object_storage_settings()
    storage = build_object_storage(settings)
    assert storage.backend == "local"
