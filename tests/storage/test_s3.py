from __future__ import annotations

from datetime import timezone

import boto3
import pytest
from botocore.stub import Stubber
from src.storage.base import (
    InvalidKeyError,
    ObjectNotFoundError,
    ObjectStorageAuthError,
    StoredObject,
)
from src.storage.s3 import S3ObjectStorage


def _make_storage() -> tuple[S3ObjectStorage, Stubber]:
    client = boto3.client(
        "s3",
        region_name="auto",
        aws_access_key_id="k",
        aws_secret_access_key="s",
        endpoint_url="https://example-r2.cloudflarestorage.com",
    )
    stubber = Stubber(client)
    storage = S3ObjectStorage(
        bucket="b",
        endpoint_url="https://example-r2.cloudflarestorage.com",
        aws_access_key_id="k",
        aws_secret_access_key="s",
        client=client,
    )
    return storage, stubber


def test_put_bytes_calls_put_object_and_returns_hash() -> None:
    storage, stubber = _make_storage()
    stubber.add_response(
        "put_object",
        expected_params={
            "Bucket": "b",
            "Key": "k",
            "Body": b"hi",
            "ContentType": "text/plain",
        },
        service_response={},
    )
    with stubber:
        stored = storage.put_bytes(key="k", data=b"hi", content_type="text/plain")
    assert isinstance(stored, StoredObject)
    assert stored.size_bytes == 2
    assert (
        stored.sha256_hex
        == "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4"
    )


def test_public_methods_reject_invalid_keys() -> None:
    storage, stubber = _make_storage()
    with stubber:
        with pytest.raises(InvalidKeyError):
            storage.put_bytes(key="../bad", data=b"x")
        with pytest.raises(InvalidKeyError):
            storage.get_bytes("bad?query")
        with pytest.raises(InvalidKeyError):
            storage.exists("bad#fragment")
        with pytest.raises(InvalidKeyError):
            storage.presign_get("bad key", expires_in_seconds=60)


def test_put_file_reads_file_bytes_and_returns_hash(tmp_path) -> None:
    storage, stubber = _make_storage()
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"pdf-bytes")
    stubber.add_response(
        "put_object",
        expected_params={
            "Bucket": "b",
            "Key": "k",
            "Body": b"pdf-bytes",
            "ContentType": "application/pdf",
        },
        service_response={},
    )
    with stubber:
        stored = storage.put_file(key="k", path=src, content_type="application/pdf")
    assert stored.size_bytes == 9


def test_get_bytes_returns_body() -> None:
    storage, stubber = _make_storage()
    stubber.add_response(
        "get_object",
        expected_params={"Bucket": "b", "Key": "k"},
        service_response={"Body": _BodyStub(b"hello")},
    )
    with stubber:
        assert storage.get_bytes("k") == b"hello"


def test_get_bytes_raises_not_found_on_nosuchkey() -> None:
    storage, stubber = _make_storage()
    stubber.add_client_error(
        "get_object",
        service_error_code="NoSuchKey",
        http_status_code=404,
    )
    with stubber, pytest.raises(ObjectNotFoundError):
        storage.get_bytes("missing")


def test_get_bytes_maps_403_to_auth_error() -> None:
    storage, stubber = _make_storage()
    stubber.add_client_error(
        "get_object",
        service_error_code="AccessDenied",
        http_status_code=403,
    )
    with stubber, pytest.raises(ObjectStorageAuthError):
        storage.get_bytes("k")


def test_exists_true_when_head_succeeds() -> None:
    storage, stubber = _make_storage()
    stubber.add_response(
        "head_object",
        expected_params={"Bucket": "b", "Key": "k"},
        service_response={},
    )
    with stubber:
        assert storage.exists("k") is True


def test_exists_false_on_404() -> None:
    storage, stubber = _make_storage()
    stubber.add_client_error(
        "head_object",
        service_error_code="404",
        http_status_code=404,
    )
    with stubber:
        assert storage.exists("k") is False


def test_presign_get_builds_url_with_expires() -> None:
    storage, stubber = _make_storage()
    with stubber:
        url = storage.presign_get("k", expires_in_seconds=60)
    assert url.method == "GET"
    assert url.key == "k"
    assert "example-r2.cloudflarestorage.com" in url.url
    assert url.expires_at.tzinfo is timezone.utc


def test_presign_put_includes_content_type() -> None:
    storage, stubber = _make_storage()
    with stubber:
        url = storage.presign_put(
            "k", expires_in_seconds=60, content_type="application/pdf"
        )
    assert url.method == "PUT"
    assert "example-r2.cloudflarestorage.com" in url.url


class _BodyStub:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data
