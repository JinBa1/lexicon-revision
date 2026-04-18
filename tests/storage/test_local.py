from __future__ import annotations

import time
from datetime import timezone
from pathlib import Path

import pytest
from src.storage.base import (
    InvalidKeyError,
    ObjectNotFoundError,
    ObjectStorageAuthError,
    ObjectStorageError,
)
from src.storage.local import LocalObjectStorage, validate_local_presigned_url

SECRET = b"test-secret-0123456789"


def _storage(tmp_path: Path) -> LocalObjectStorage:
    return LocalObjectStorage(root=tmp_path, dev_presign_secret=SECRET)


def test_put_and_get_bytes_roundtrip(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    stored = storage.put_bytes(
        key="blobs/sha256/aa/aa/" + "a" * 64 + ".pdf", data=b"hello"
    )
    assert stored.size_bytes == 5
    assert (
        stored.sha256_hex
        == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )
    assert storage.get_bytes(stored.key) == b"hello"


def test_put_file_computes_hash(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    src = tmp_path / "in.bin"
    src.write_bytes(b"abc")
    stored = storage.put_file(key="blobs/sha256/aa/aa/" + "a" * 64 + ".bin", path=src)
    assert (
        stored.sha256_hex
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_get_bytes_raises_not_found(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with pytest.raises(ObjectNotFoundError):
        storage.get_bytes("missing/key")


def test_public_methods_reject_invalid_keys(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with pytest.raises(InvalidKeyError):
        storage.put_bytes(key="../bad", data=b"x")
    with pytest.raises(InvalidKeyError):
        storage.get_bytes("bad?query")
    with pytest.raises(InvalidKeyError):
        storage.exists("bad#fragment")
    with pytest.raises(InvalidKeyError):
        storage.presign_get("bad key", expires_in_seconds=60)


def test_exists_matches_put(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    key = "blobs/sha256/aa/aa/" + "a" * 64 + ".pdf"
    assert not storage.exists(key)
    storage.put_bytes(key=key, data=b"x")
    assert storage.exists(key)


def test_traversal_rejected_even_with_symlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    storage_root = tmp_path / "root"
    storage_root.mkdir()
    (storage_root / "escape").symlink_to(outside)
    storage = LocalObjectStorage(root=storage_root, dev_presign_secret=SECRET)
    with pytest.raises(InvalidKeyError):
        storage.put_bytes(key="escape/pwned.txt", data=b"x")


def test_presign_get_url_shape(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    key = "blobs/sha256/aa/aa/" + "a" * 64 + ".pdf"
    url = storage.presign_get(key, expires_in_seconds=60)
    assert url.method == "GET"
    assert url.key == key
    assert url.url.startswith("http://localhost:8000/_dev/object/GET/")
    assert url.expires_at.tzinfo is timezone.utc


def test_validate_local_presigned_url_roundtrips(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    key = "blobs/sha256/aa/aa/" + "a" * 64 + ".pdf"
    url = storage.presign_get(key, expires_in_seconds=60)
    method, extracted = validate_local_presigned_url(url.url, secret=SECRET)
    assert method == "GET"
    assert extracted == key


def test_validate_local_presigned_url_rejects_bad_hmac(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    url = storage.presign_get(
        "blobs/sha256/aa/aa/" + "a" * 64 + ".pdf", expires_in_seconds=60
    )
    parts = url.url.split("/")
    hmac_index = parts.index("GET") + 2
    parts[hmac_index] = "0" * 32
    tampered = "/".join(parts)
    with pytest.raises(ObjectStorageAuthError):
        validate_local_presigned_url(tampered, secret=SECRET)


def test_validate_local_presigned_url_rejects_tampered_key(
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path)
    url = storage.presign_get(
        "blobs/sha256/aa/aa/" + "a" * 64 + ".pdf", expires_in_seconds=60
    )
    tampered = url.url.replace(".pdf", ".txt")
    with pytest.raises(ObjectStorageAuthError):
        validate_local_presigned_url(tampered, secret=SECRET)


def test_validate_local_presigned_url_rejects_expired(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    url = storage.presign_get("k", expires_in_seconds=1)
    future = time.time() + 3600
    with pytest.raises(ObjectStorageError):
        validate_local_presigned_url(url.url, secret=SECRET, now=future)
