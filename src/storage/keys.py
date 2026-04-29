from __future__ import annotations

import re
from typing import Literal

from src.storage.base import InvalidKeyError

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_RUN_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_EXT_RE = re.compile(r"[a-z0-9]+")
_RUN_ID_SLUG_RE = re.compile(r"[^a-z0-9]+")


def validate_key(key: str) -> None:
    if not key or len(key) > 1024:
        raise InvalidKeyError(key)
    if ".." in key:
        raise InvalidKeyError(key)
    if key.startswith("/") or key.startswith("./"):
        raise InvalidKeyError(key)
    if "\\" in key or "\x00" in key:
        raise InvalidKeyError(key)
    if "//" in key or "/./" in key or key.endswith("/"):
        raise InvalidKeyError(key)
    if re.search(r"\s", key):
        raise InvalidKeyError(key)
    if "?" in key or "#" in key:
        raise InvalidKeyError(key)


def sha256_blob_key(*, sha256_hex: str, extension: str) -> str:
    if _SHA256_RE.fullmatch(sha256_hex) is None:
        raise InvalidKeyError(sha256_hex)
    if _EXT_RE.fullmatch(extension) is None:
        raise InvalidKeyError(extension)
    prefix = sha256_hex[:2]
    group = sha256_hex[2:4]
    key = f"blobs/sha256/{prefix}/{group}/{sha256_hex}.{extension}"
    validate_key(key)
    return key


def conversion_run_id_from_stem(stem: str) -> str:
    slug = _RUN_ID_SLUG_RE.sub("-", stem.lower()).strip("-")
    if not slug:
        raise InvalidKeyError(stem)
    run_id = f"run-{slug}"
    if _RUN_ID_RE.fullmatch(run_id) is None:
        raise InvalidKeyError(stem)
    return run_id


def mineru_artifact_key(
    *,
    conversion_run_id: str,
    kind: Literal["content_list", "markdown", "image", "manifest"],
    filename: str,
) -> str:
    if _RUN_ID_RE.fullmatch(conversion_run_id) is None:
        raise InvalidKeyError(conversion_run_id)
    if kind == "image":
        if not filename or "/" in filename or ".." in filename:
            raise InvalidKeyError(filename)
    else:
        if filename:
            raise InvalidKeyError(filename)
    _CANONICAL: dict[str, str] = {
        "content_list": "content_list.json",
        "markdown": "document.md",
        "manifest": "manifest.json",
    }
    if kind == "image":
        key = f"artifacts/mineru/{conversion_run_id}/images/{filename}"
    else:
        key = f"artifacts/mineru/{conversion_run_id}/{_CANONICAL[kind]}"
    validate_key(key)
    return key
