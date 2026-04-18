from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from src.storage.manifest import ArtifactManifest, ManifestArtifact


def _sample() -> ArtifactManifest:
    return ArtifactManifest(
        conversion_run_id="run-1",
        paper_id="cam-2024-p3",
        source_pdf_key="blobs/sha256/aa/aa/" + "a" * 64 + ".pdf",
        mineru_version="2.1.0",
        created_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        artifacts=(
            ManifestArtifact(
                kind="content_list",
                key="artifacts/mineru/run-1/content_list.json",
                content_type="application/json",
                sha256_hex="b" * 64,
                size_bytes=1024,
            ),
            ManifestArtifact(
                kind="markdown",
                key="artifacts/mineru/run-1/document.md",
                content_type="text/markdown",
                sha256_hex="c" * 64,
                size_bytes=2048,
            ),
        ),
    )


def test_manifest_roundtrips_through_json() -> None:
    manifest = _sample()
    reloaded = ArtifactManifest.from_json(manifest.to_json())
    assert reloaded == manifest


def test_manifest_to_json_is_deterministic() -> None:
    m = _sample()
    assert m.to_json() == m.to_json()


def test_manifest_to_json_preserves_artifact_order() -> None:
    m = _sample()
    payload = json.loads(m.to_json())
    assert [a["kind"] for a in payload["artifacts"]] == [
        "content_list",
        "markdown",
    ]


def test_manifest_from_json_rejects_short_sha() -> None:
    raw = _sample().to_json()
    broken = raw.replace("b" * 64, "bb")
    with pytest.raises(ValueError):
        ArtifactManifest.from_json(broken)


def test_manifest_from_json_rejects_invalid_key() -> None:
    raw = json.loads(_sample().to_json())
    raw["artifacts"][0]["key"] = "../bad"
    with pytest.raises(ValueError):
        ArtifactManifest.from_json(json.dumps(raw))


def test_manifest_from_json_rejects_unknown_kind() -> None:
    raw = json.loads(_sample().to_json())
    raw["artifacts"][0]["kind"] = "other"
    with pytest.raises(ValueError):
        ArtifactManifest.from_json(json.dumps(raw))


def test_manifest_from_json_rejects_negative_size() -> None:
    raw = json.loads(_sample().to_json())
    raw["artifacts"][0]["size_bytes"] = -1
    with pytest.raises(ValueError):
        ArtifactManifest.from_json(json.dumps(raw))


def test_manifest_from_json_rejects_missing_field() -> None:
    raw = json.loads(_sample().to_json())
    raw.pop("source_pdf_key")
    with pytest.raises(ValueError):
        ArtifactManifest.from_json(json.dumps(raw))


def test_manifest_to_json_rejects_invalid_source_pdf_key() -> None:
    manifest = ArtifactManifest(
        conversion_run_id="run-1",
        paper_id="p",
        source_pdf_key="../bad/path.pdf",
        mineru_version="1.0",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        artifacts=(),
    )
    with pytest.raises(ValueError, match="source_pdf_key"):
        manifest.to_json()


def test_manifest_from_json_rejects_invalid_source_pdf_key() -> None:
    raw = json.loads(_sample().to_json())
    raw["source_pdf_key"] = "../bad"
    with pytest.raises(ValueError):
        ArtifactManifest.from_json(json.dumps(raw))


def test_manifest_from_json_normalizes_created_at_to_utc() -> None:
    from datetime import timedelta

    manifest = _sample()
    payload = json.loads(manifest.to_json())
    payload["created_at"] = "2026-04-18T13:00:00+01:00"
    reloaded = ArtifactManifest.from_json(json.dumps(payload))
    assert reloaded.created_at.utcoffset() == timedelta(0)
    assert reloaded.created_at.hour == 12


def test_created_at_is_serialized_with_utc_suffix() -> None:
    payload = json.loads(_sample().to_json())
    assert payload["created_at"].endswith("+00:00")


def test_created_at_is_normalized_to_utc() -> None:
    manifest = _sample()
    shifted = ArtifactManifest(
        conversion_run_id=manifest.conversion_run_id,
        paper_id=manifest.paper_id,
        source_pdf_key=manifest.source_pdf_key,
        mineru_version=manifest.mineru_version,
        created_at=manifest.created_at.astimezone(timezone.utc),
        artifacts=manifest.artifacts,
    )
    payload = json.loads(shifted.to_json())
    assert payload["created_at"] == "2026-04-18T12:00:00+00:00"
