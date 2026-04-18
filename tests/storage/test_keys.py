from __future__ import annotations

import pytest
from src.storage.base import InvalidKeyError
from src.storage.keys import mineru_artifact_key, sha256_blob_key, validate_key


def test_sha256_blob_key_shape() -> None:
    h = "a" * 64
    assert (
        sha256_blob_key(sha256_hex=h, extension="pdf") == f"blobs/sha256/aa/aa/{h}.pdf"
    )


def test_sha256_blob_key_rejects_short_hash() -> None:
    with pytest.raises(InvalidKeyError):
        sha256_blob_key(sha256_hex="abc", extension="pdf")


def test_sha256_blob_key_rejects_uppercase_hash() -> None:
    with pytest.raises(InvalidKeyError):
        sha256_blob_key(sha256_hex="A" * 64, extension="pdf")


def test_sha256_blob_key_rejects_bad_extension() -> None:
    with pytest.raises(InvalidKeyError):
        sha256_blob_key(sha256_hex="a" * 64, extension=".pdf")
    with pytest.raises(InvalidKeyError):
        sha256_blob_key(sha256_hex="a" * 64, extension="p/df")


def test_mineru_artifact_key_canonical_forms() -> None:
    run = "run-123"
    assert (
        mineru_artifact_key(conversion_run_id=run, kind="content_list", filename="")
        == "artifacts/mineru/run-123/content_list.json"
    )
    assert (
        mineru_artifact_key(conversion_run_id=run, kind="markdown", filename="")
        == "artifacts/mineru/run-123/document.md"
    )
    assert (
        mineru_artifact_key(conversion_run_id=run, kind="image", filename="fig_001.png")
        == "artifacts/mineru/run-123/images/fig_001.png"
    )
    assert (
        mineru_artifact_key(conversion_run_id=run, kind="manifest", filename="")
        == "artifacts/mineru/run-123/manifest.json"
    )


def test_mineru_artifact_key_rejects_filename_for_canonical_kinds() -> None:
    for kind in ("content_list", "markdown", "manifest"):
        with pytest.raises(InvalidKeyError):
            mineru_artifact_key(
                conversion_run_id="run-123",
                kind=kind,
                filename="unexpected.txt",
            )


def test_mineru_artifact_key_rejects_traversal_in_image_filename() -> None:
    with pytest.raises(InvalidKeyError):
        mineru_artifact_key(conversion_run_id="r", kind="image", filename="../evil.png")
    with pytest.raises(InvalidKeyError):
        mineru_artifact_key(conversion_run_id="r", kind="image", filename="sub/dir.png")
    with pytest.raises(InvalidKeyError):
        mineru_artifact_key(
            conversion_run_id="r", kind="image", filename="bad?name.png"
        )
    with pytest.raises(InvalidKeyError):
        mineru_artifact_key(
            conversion_run_id="r", kind="image", filename="bad#name.png"
        )


def test_mineru_artifact_key_rejects_bad_run_id() -> None:
    with pytest.raises(InvalidKeyError):
        mineru_artifact_key(conversion_run_id="Run Id", kind="markdown", filename="")
    with pytest.raises(InvalidKeyError):
        mineru_artifact_key(conversion_run_id="", kind="markdown", filename="")


def test_validate_key_accepts_normal_keys() -> None:
    validate_key("blobs/sha256/aa/aa/" + "a" * 64 + ".pdf")
    validate_key("artifacts/mineru/run-1/images/x.png")


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "/leading-slash",
        "./leading-dot",
        "has..dots",
        "has\\backslash",
        "has space",
        "has\tnewline",
        "has?query",
        "has#fragment",
        "has\x00null",
        "a" * 1025,
    ],
)
def test_validate_key_rejects_bad_keys(bad: str) -> None:
    with pytest.raises(InvalidKeyError):
        validate_key(bad)
