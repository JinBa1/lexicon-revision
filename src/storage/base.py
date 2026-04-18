from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable


class ObjectStorageError(Exception):
    pass


class ObjectNotFoundError(ObjectStorageError):
    pass


class ObjectStorageAuthError(ObjectStorageError):
    pass


class ObjectStorageConfigError(ObjectStorageError):
    pass


class InvalidKeyError(ObjectStorageError):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    sha256_hex: str
    content_type: str | None = None


@dataclass(frozen=True)
class PresignedUrl:
    url: str
    expires_at: datetime
    method: Literal["GET", "PUT"]
    key: str

    def __post_init__(self) -> None:
        if self.method not in ("GET", "PUT"):
            raise ValueError(f"method must be GET or PUT, got {self.method!r}")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")


@runtime_checkable
class ObjectStorage(Protocol):
    backend: Literal["local", "s3"]

    def put_bytes(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str | None = None,
    ) -> StoredObject: ...

    def put_file(
        self,
        *,
        key: str,
        path: Path,
        content_type: str | None = None,
    ) -> StoredObject: ...

    def get_bytes(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def presign_get(self, key: str, *, expires_in_seconds: int) -> PresignedUrl: ...

    def presign_put(
        self,
        key: str,
        *,
        expires_in_seconds: int,
        content_type: str | None = None,
    ) -> PresignedUrl: ...
