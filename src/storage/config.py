from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src.storage.base import ObjectStorage, ObjectStorageConfigError


@dataclass(frozen=True)
class LocalStorageConfig:
    root: Path
    dev_presign_base_url: str
    dev_presign_secret: bytes


@dataclass(frozen=True)
class S3StorageConfig:
    bucket: str
    endpoint_url: str | None
    region_name: str
    access_key_id: str
    secret_access_key: str


@dataclass(frozen=True)
class ObjectStorageSettings:
    provider: Literal["local", "s3"]
    local: LocalStorageConfig | None
    s3: S3StorageConfig | None


def load_object_storage_settings() -> ObjectStorageSettings:
    provider = os.environ.get("OBJECT_STORAGE_PROVIDER", "local")
    if provider not in ("local", "s3"):
        raise ObjectStorageConfigError(f"unknown provider: {provider!r}")
    local: LocalStorageConfig | None = None
    s3: S3StorageConfig | None = None
    if provider == "local":
        root = Path(os.environ.get("OBJECT_STORAGE_LOCAL_ROOT", "./data/object-store"))
        base_url = os.environ.get(
            "OBJECT_STORAGE_DEV_PRESIGN_BASE_URL",
            "http://localhost:8000/_dev/object",
        )
        secret = os.environ.get("OBJECT_STORAGE_DEV_PRESIGN_SECRET", "")
        local = LocalStorageConfig(
            root=root,
            dev_presign_base_url=base_url,
            dev_presign_secret=secret.encode() if secret else b"",
        )
    elif provider == "s3":
        bucket = os.environ.get("OBJECT_STORAGE_BUCKET", "")
        if not bucket:
            raise ObjectStorageConfigError(
                "OBJECT_STORAGE_BUCKET is required for s3 provider"
            )
        endpoint_url = os.environ.get("OBJECT_STORAGE_ENDPOINT_URL") or None
        region_name = os.environ.get("OBJECT_STORAGE_REGION", "auto")
        access_key_id = os.environ.get("OBJECT_STORAGE_ACCESS_KEY_ID", "")
        secret_access_key = os.environ.get("OBJECT_STORAGE_SECRET_ACCESS_KEY", "")
        if not access_key_id:
            raise ObjectStorageConfigError(
                "OBJECT_STORAGE_ACCESS_KEY_ID is required for s3 provider"
            )
        if not secret_access_key:
            raise ObjectStorageConfigError(
                "OBJECT_STORAGE_SECRET_ACCESS_KEY is required for s3 provider"
            )
        s3 = S3StorageConfig(
            bucket=bucket,
            endpoint_url=endpoint_url,
            region_name=region_name,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )
    return ObjectStorageSettings(provider=provider, local=local, s3=s3)


def build_object_storage(
    settings: ObjectStorageSettings,
) -> ObjectStorage:
    if settings.provider == "local":
        if settings.local is None:
            raise ObjectStorageConfigError("local config missing")
        if not settings.local.dev_presign_secret:
            raise ObjectStorageConfigError(
                "OBJECT_STORAGE_DEV_PRESIGN_SECRET is required for local provider"
            )
        from src.storage.local import LocalObjectStorage

        return LocalObjectStorage(
            root=settings.local.root,
            dev_presign_base_url=settings.local.dev_presign_base_url,
            dev_presign_secret=settings.local.dev_presign_secret,
        )
    if settings.provider == "s3":
        if settings.s3 is None:
            raise ObjectStorageConfigError("s3 config missing")
        from src.storage.s3 import S3ObjectStorage

        return S3ObjectStorage(
            bucket=settings.s3.bucket,
            endpoint_url=settings.s3.endpoint_url,
            region_name=settings.s3.region_name,
            aws_access_key_id=settings.s3.access_key_id,
            aws_secret_access_key=settings.s3.secret_access_key,
        )
    raise ObjectStorageConfigError(f"unknown provider: {settings.provider!r}")
