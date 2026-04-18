from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from src.storage.keys import validate_key

_ALLOWED_KINDS = {"content_list", "markdown", "image", "manifest"}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class ManifestArtifact:
    kind: str
    key: str
    content_type: str
    sha256_hex: str
    size_bytes: int


@dataclass(frozen=True)
class ArtifactManifest:
    conversion_run_id: str
    paper_id: str
    source_pdf_key: str
    mineru_version: str
    created_at: datetime
    artifacts: tuple[ManifestArtifact, ...]

    def to_json(self) -> str:
        _validate_artifacts(self.artifacts)
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        try:
            validate_key(self.source_pdf_key)
        except Exception as e:
            raise ValueError(f"invalid source_pdf_key: {e}") from e
        data = {
            "conversion_run_id": self.conversion_run_id,
            "paper_id": self.paper_id,
            "source_pdf_key": self.source_pdf_key,
            "mineru_version": self.mineru_version,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "artifacts": [
                {
                    "kind": a.kind,
                    "key": a.key,
                    "content_type": a.content_type,
                    "sha256_hex": a.sha256_hex,
                    "size_bytes": a.size_bytes,
                }
                for a in self.artifacts
            ],
        }
        return json.dumps(data, sort_keys=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> ArtifactManifest:
        data = json.loads(raw)
        for field in (
            "conversion_run_id",
            "paper_id",
            "source_pdf_key",
            "mineru_version",
            "created_at",
            "artifacts",
        ):
            if field not in data:
                raise ValueError(f"missing field: {field}")
        artifacts = tuple(_parse_artifact(a) for a in data["artifacts"])
        source_pdf_key = data["source_pdf_key"]
        try:
            validate_key(source_pdf_key)
        except Exception as e:
            raise ValueError(f"invalid source_pdf_key: {e}") from e
        created_at = datetime.fromisoformat(data["created_at"])
        if created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        created_at = created_at.astimezone(timezone.utc)
        return cls(
            conversion_run_id=data["conversion_run_id"],
            paper_id=data["paper_id"],
            source_pdf_key=source_pdf_key,
            mineru_version=data["mineru_version"],
            created_at=created_at,
            artifacts=artifacts,
        )


def _validate_artifacts(artifacts: tuple[ManifestArtifact, ...]) -> None:
    for a in artifacts:
        if a.kind not in _ALLOWED_KINDS:
            raise ValueError(f"invalid kind: {a.kind}")
        try:
            validate_key(a.key)
        except Exception as e:
            raise ValueError(str(e)) from e
        if _SHA256_RE.fullmatch(a.sha256_hex) is None:
            raise ValueError(f"invalid sha256_hex: {a.sha256_hex}")
        if a.size_bytes < 0:
            raise ValueError(f"negative size_bytes: {a.size_bytes}")


def _parse_artifact(data: dict) -> ManifestArtifact:
    for field in ("kind", "key", "content_type", "sha256_hex", "size_bytes"):
        if field not in data:
            raise ValueError(f"missing artifact field: {field}")
    artifact = ManifestArtifact(
        kind=data["kind"],
        key=data["key"],
        content_type=data["content_type"],
        sha256_hex=data["sha256_hex"],
        size_bytes=data["size_bytes"],
    )
    if artifact.kind not in _ALLOWED_KINDS:
        raise ValueError(f"invalid kind: {artifact.kind}")
    try:
        validate_key(artifact.key)
    except Exception as e:
        raise ValueError(str(e)) from e
    if _SHA256_RE.fullmatch(artifact.sha256_hex) is None:
        raise ValueError(f"invalid sha256_hex: {artifact.sha256_hex}")
    if artifact.size_bytes < 0:
        raise ValueError(f"negative size_bytes: {artifact.size_bytes}")
    return artifact
