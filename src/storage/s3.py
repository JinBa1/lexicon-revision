from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import botocore.exceptions
from src.storage.base import (
    ObjectNotFoundError,
    ObjectStorageAuthError,
    ObjectStorageConfigError,
    ObjectStorageError,
    PresignedUrl,
    StoredObject,
)
from src.storage.keys import validate_key


class S3ObjectStorage:
    backend = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None = None,
        region_name: str = "auto",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._bucket = bucket
        if client is not None:
            self._client = client
            return
        if not aws_access_key_id or not aws_secret_access_key:
            raise ObjectStorageConfigError(
                "S3 credentials are required when client is not provided"
            )
        import boto3

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

    def put_bytes(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str | None = None,
    ) -> StoredObject:
        validate_key(key)
        sha = hashlib.sha256(data).hexdigest()
        params: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": data,
        }
        if content_type is not None:
            params["ContentType"] = content_type
        try:
            self._client.put_object(**params)
        except botocore.exceptions.ClientError as exc:
            raise self._map_error(exc) from exc
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
        sha = hashlib.sha256(data).hexdigest()
        params: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": data,
        }
        if content_type is not None:
            params["ContentType"] = content_type
        try:
            self._client.put_object(**params)
        except botocore.exceptions.ClientError as exc:
            raise self._map_error(exc) from exc
        return StoredObject(
            key=key,
            size_bytes=len(data),
            sha256_hex=sha,
            content_type=content_type,
        )

    def get_bytes(self, key: str) -> bytes:
        validate_key(key)
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            body = resp["Body"]
            try:
                return body.read()
            finally:
                body.close()
        except botocore.exceptions.ClientError as exc:
            raise self._map_error(exc) from exc

    def exists(self, key: str) -> bool:
        validate_key(key)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except botocore.exceptions.ClientError as exc:
            code = exc.response["Error"]["Code"]
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
            if code == "404" or status == 404:
                return False
            if code in ("403", "AccessDenied") or status == 403:
                raise ObjectStorageAuthError(str(exc)) from exc
            raise ObjectStorageError(str(exc)) from exc

    def presign_get(self, key: str, *, expires_in_seconds: int) -> PresignedUrl:
        validate_key(key)
        if expires_in_seconds <= 0:
            raise ValueError("expires_in_seconds must be positive")
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in_seconds,
        )
        now = datetime.now(tz=timezone.utc)
        expires_at = now + timedelta(seconds=expires_in_seconds)
        return PresignedUrl(url=url, expires_at=expires_at, method="GET", key=key)

    def presign_put(
        self,
        key: str,
        *,
        expires_in_seconds: int,
        content_type: str | None = None,
    ) -> PresignedUrl:
        validate_key(key)
        if expires_in_seconds <= 0:
            raise ValueError("expires_in_seconds must be positive")
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
        if content_type is not None:
            params["ContentType"] = content_type
        url = self._client.generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=expires_in_seconds,
        )
        now = datetime.now(tz=timezone.utc)
        expires_at = now + timedelta(seconds=expires_in_seconds)
        return PresignedUrl(url=url, expires_at=expires_at, method="PUT", key=key)

    def health(self) -> str:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except (
            botocore.exceptions.BotoCoreError,
            botocore.exceptions.ClientError,
        ):
            return "error"
        return "ok"

    def _map_error(self, exc: botocore.exceptions.ClientError) -> ObjectStorageError:
        code = exc.response["Error"]["Code"]
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        if code in ("NoSuchKey", "NoSuchKeyNotFound") or status == 404:
            return ObjectNotFoundError(str(exc))
        if code in ("AccessDenied", "InvalidAccessKeyId") or status == 403:
            return ObjectStorageAuthError(str(exc))
        return ObjectStorageError(str(exc))
