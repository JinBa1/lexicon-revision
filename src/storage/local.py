from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote

from src.storage.base import (
    InvalidKeyError,
    ObjectNotFoundError,
    ObjectStorageAuthError,
    ObjectStorageError,
    PresignedUrl,
    StoredObject,
)
from src.storage.keys import validate_key


class LocalObjectStorage:
    backend = "local"

    def __init__(
        self,
        *,
        root: Path,
        dev_presign_base_url: str = "http://localhost:8000/_dev/object",
        dev_presign_secret: bytes,
    ) -> None:
        self._root = root.resolve(strict=False)
        self._base_url = dev_presign_base_url.rstrip("/")
        self._secret = dev_presign_secret

    def put_bytes(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str | None = None,
    ) -> StoredObject:
        validate_key(key)
        dest = self._resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        return StoredObject(
            key=key,
            size_bytes=len(data),
            sha256_hex=sha,
            content_type=content_type,
        )

    def put_file(
        self,
        *,
        key: str,
        path: Path,
        content_type: str | None = None,
    ) -> StoredObject:
        validate_key(key)
        data = path.read_bytes()
        dest = self._resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        return StoredObject(
            key=key,
            size_bytes=len(data),
            sha256_hex=sha,
            content_type=content_type,
        )

    def get_bytes(self, key: str) -> bytes:
        validate_key(key)
        dest = self._resolve(key)
        if not dest.is_file():
            raise ObjectNotFoundError(key)
        return dest.read_bytes()

    def exists(self, key: str) -> bool:
        validate_key(key)
        dest = self._resolve(key)
        return dest.is_file()

    def presign_get(self, key: str, *, expires_in_seconds: int) -> PresignedUrl:
        validate_key(key)
        if expires_in_seconds <= 0:
            raise ValueError("expires_in_seconds must be positive")
        return self._presign("GET", key, expires_in_seconds)

    def presign_put(
        self,
        key: str,
        *,
        expires_in_seconds: int,
        content_type: str | None = None,
    ) -> PresignedUrl:
        # content_type is accepted for ObjectStorage protocol compatibility.
        # Local signed URLs are a dev-only URL-shape stub and do not bind
        # content_type until the dev upload route exists (9B territory).
        validate_key(key)
        if expires_in_seconds <= 0:
            raise ValueError("expires_in_seconds must be positive")
        return self._presign("PUT", key, expires_in_seconds)

    def health(self) -> str:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            probe_path = self._root / ".storage-healthcheck"
            probe_path.write_bytes(b"ok")
            probe_path.unlink()
        except OSError:
            return "error"
        return "ok"

    def _resolve(self, key: str) -> Path:
        resolved = (self._root / key).resolve(strict=False)
        if not resolved.is_relative_to(self._root):
            raise InvalidKeyError(key)
        return resolved

    def _presign(self, method: str, key: str, expires_in_seconds: int) -> PresignedUrl:
        now = time.time()
        expires_unix = int(now + expires_in_seconds)
        encoded_key = quote(key, safe="/")
        message = f"{method}:{expires_unix}:{encoded_key}"
        sig = hmac.new(self._secret, message.encode(), hashlib.sha256).hexdigest()[:32]
        url = f"{self._base_url}/{method}/{expires_unix}/{sig}/{encoded_key}"
        expires_at = datetime.fromtimestamp(expires_unix, tz=timezone.utc)
        return PresignedUrl(url=url, expires_at=expires_at, method=method, key=key)

    @property
    def dev_presign_base_url(self) -> str:
        return self._base_url

    @property
    def dev_presign_secret(self) -> bytes:
        return self._secret


def validate_local_presigned_url(
    url: str,
    *,
    secret: bytes,
    now: float | None = None,
    base_url: str = "http://localhost:8000/_dev/object",
) -> tuple[str, str]:
    if now is None:
        now = time.time()
    try:
        prefix = f"{base_url.rstrip('/')}/"
        if not url.startswith(prefix):
            raise ObjectStorageAuthError("invalid presigned URL")
        rest = url[len(prefix) :]
        parts = rest.split("/", 3)
        if len(parts) < 4:
            raise ObjectStorageAuthError("invalid presigned URL format")
        method, expires_str, sig, encoded_key = parts
        if method not in {"GET", "PUT"}:
            raise ObjectStorageAuthError("invalid presigned URL method")
    except (ValueError, IndexError) as exc:
        raise ObjectStorageAuthError("malformed URL") from exc
    try:
        expires_unix = int(expires_str)
    except ValueError as exc:
        raise ObjectStorageAuthError("invalid expiry") from exc
    if expires_unix <= now:
        raise ObjectStorageError("presigned URL has expired")
    message = f"{method}:{expires_unix}:{encoded_key}"
    expected = hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        raise ObjectStorageAuthError("bad HMAC")
    key = unquote(encoded_key)
    validate_key(key)
    return method, key
