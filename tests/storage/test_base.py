from __future__ import annotations

from datetime import datetime, timezone

import pytest
from src.storage.base import (
    InvalidKeyError,
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageAuthError,
    ObjectStorageConfigError,
    ObjectStorageError,
    PresignedUrl,
    StoredObject,
)


def test_stored_object_preserves_fields() -> None:
    obj = StoredObject(
        key="k",
        size_bytes=12,
        sha256_hex="deadbeef",
        content_type="text/plain",
    )
    assert obj.key == "k"
    assert obj.size_bytes == 12
    assert obj.sha256_hex == "deadbeef"
    assert obj.content_type == "text/plain"


def test_presigned_url_preserves_fields() -> None:
    when = datetime(2026, 4, 18, tzinfo=timezone.utc)
    url = PresignedUrl(url="https://x/y", expires_at=when, method="GET", key="k")
    assert url.method == "GET"
    assert url.key == "k"


def test_error_hierarchy() -> None:
    for cls in (
        ObjectNotFoundError,
        ObjectStorageAuthError,
        ObjectStorageConfigError,
        InvalidKeyError,
    ):
        assert issubclass(cls, ObjectStorageError)


def test_object_storage_is_runtime_checkable() -> None:
    class _Stub:
        backend = "local"

        def put_bytes(self, *, key, data, content_type=None):
            return StoredObject(
                key=key,
                size_bytes=len(data),
                sha256_hex="",
                content_type=content_type,
            )

        def put_file(self, *, key, path, content_type=None):
            return StoredObject(
                key=key,
                size_bytes=0,
                sha256_hex="",
                content_type=content_type,
            )

        def get_bytes(self, key):
            return b""

        def exists(self, key):
            return False

        def presign_get(self, key, *, expires_in_seconds):
            return PresignedUrl(
                url="http://x",
                expires_at=datetime.now(timezone.utc),
                method="GET",
                key=key,
            )

        def presign_put(self, key, *, expires_in_seconds, content_type=None):
            return PresignedUrl(
                url="http://x",
                expires_at=datetime.now(timezone.utc),
                method="PUT",
                key=key,
            )

    assert isinstance(_Stub(), ObjectStorage)


def test_presigned_url_rejects_invalid_method_type() -> None:
    with pytest.raises(ValueError):
        PresignedUrl(
            url="https://x/y",
            expires_at=datetime.now(timezone.utc),
            method="POST",  # type: ignore[arg-type]
            key="k",
        )
