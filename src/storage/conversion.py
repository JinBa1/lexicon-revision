from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.storage.base import ObjectStorage
from src.storage.keys import mineru_artifact_key, sha256_blob_key
from src.storage.manifest import ArtifactManifest, ManifestArtifact

_CONTENT_LIST_SUFFIX = "_content_list.json"
_MARKDOWN_SUFFIX = ".md"
_IMAGES_DIR_NAME = "images"
_MANIFEST_SUFFIX = "_artifact_manifest.json"


@dataclass(frozen=True)
class ConvertedPaperArtifacts:
    paper_id: str
    pdf_path: Path
    content_list_path: Path
    markdown_path: Path | None
    image_paths: tuple[Path, ...]
    manifest_local_path: Path


def discover_converted_paper_artifacts(
    pdf_path: Path,
    output_dir: Path,
) -> ConvertedPaperArtifacts:
    """Locate the converted paper artifacts for a source PDF."""
    pdf_stem = pdf_path.stem
    candidates = sorted(output_dir.glob(f"**/{pdf_stem}{_CONTENT_LIST_SUFFIX}"))
    if not candidates:
        raise FileNotFoundError(f"content_list.json not found for {pdf_stem}")
    if len(candidates) > 1:
        raise ValueError(
            f"multiple content_list.json files found for {pdf_stem}: "
            + ", ".join(str(path) for path in candidates)
        )

    content_list_path = candidates[0]
    markdown_path = content_list_path.with_name(f"{pdf_stem}{_MARKDOWN_SUFFIX}")
    if not markdown_path.is_file():
        markdown_path = None

    images_dir = content_list_path.parent / _IMAGES_DIR_NAME
    image_paths = tuple(
        sorted(path for path in images_dir.glob("**/*") if path.is_file())
    )

    return ConvertedPaperArtifacts(
        paper_id=pdf_stem,
        pdf_path=pdf_path,
        content_list_path=content_list_path,
        markdown_path=markdown_path,
        image_paths=image_paths,
        manifest_local_path=local_manifest_path(content_list_path, pdf_stem=pdf_stem),
    )


def upload_converted_paper_artifacts(
    storage: ObjectStorage,
    artifacts: ConvertedPaperArtifacts,
    conversion_run_id: str,
    mineru_version: str,
    created_at: datetime | None = None,
) -> ArtifactManifest:
    """Upload a converted paper and its manifest to object storage."""
    if created_at is None:
        created_at = datetime.now(tz=timezone.utc)
    if created_at.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")

    source_pdf_bytes = artifacts.pdf_path.read_bytes()
    source_pdf_key = sha256_blob_key(
        sha256_hex=hashlib.sha256(source_pdf_bytes).hexdigest(),
        extension="pdf",
    )
    storage.put_bytes(
        key=source_pdf_key,
        data=source_pdf_bytes,
        content_type="application/pdf",
    )

    uploaded_artifacts: list[ManifestArtifact] = []

    content_list_object = storage.put_file(
        key=mineru_artifact_key(
            conversion_run_id=conversion_run_id,
            kind="content_list",
            filename="",
        ),
        path=artifacts.content_list_path,
        content_type="application/json",
    )
    uploaded_artifacts.append(
        ManifestArtifact(
            kind="content_list",
            key=content_list_object.key,
            content_type=content_list_object.content_type or "application/json",
            sha256_hex=content_list_object.sha256_hex,
            size_bytes=content_list_object.size_bytes,
        )
    )

    if artifacts.markdown_path is not None:
        markdown_object = storage.put_file(
            key=mineru_artifact_key(
                conversion_run_id=conversion_run_id,
                kind="markdown",
                filename="",
            ),
            path=artifacts.markdown_path,
            content_type="text/markdown",
        )
        uploaded_artifacts.append(
            ManifestArtifact(
                kind="markdown",
                key=markdown_object.key,
                content_type=markdown_object.content_type or "text/markdown",
                sha256_hex=markdown_object.sha256_hex,
                size_bytes=markdown_object.size_bytes,
            )
        )

    for image_path in artifacts.image_paths:
        content_type, _ = mimetypes.guess_type(image_path.name)
        image_object = storage.put_file(
            key=mineru_artifact_key(
                conversion_run_id=conversion_run_id,
                kind="image",
                filename=image_path.name,
            ),
            path=image_path,
            content_type=content_type,
        )
        uploaded_artifacts.append(
            ManifestArtifact(
                kind="image",
                key=image_object.key,
                content_type=image_object.content_type
                or content_type
                or "application/octet-stream",
                sha256_hex=image_object.sha256_hex,
                size_bytes=image_object.size_bytes,
            )
        )

    manifest = ArtifactManifest(
        conversion_run_id=conversion_run_id,
        paper_id=artifacts.paper_id,
        source_pdf_key=source_pdf_key,
        mineru_version=mineru_version,
        created_at=created_at.astimezone(timezone.utc),
        artifacts=tuple(uploaded_artifacts),
    )

    manifest_bytes = manifest.to_json().encode("utf-8")
    storage.put_bytes(
        key=mineru_artifact_key(
            conversion_run_id=conversion_run_id,
            kind="manifest",
            filename="",
        ),
        data=manifest_bytes,
        content_type="application/json",
    )
    return manifest


def local_manifest_path(content_list_path: Path, *, pdf_stem: str) -> Path:
    """Return the local manifest path corresponding to a content list."""
    if content_list_path.name != f"{pdf_stem}{_CONTENT_LIST_SUFFIX}":
        raise ValueError("content_list_path does not match pdf_stem")
    return content_list_path.with_name(f"{pdf_stem}{_MANIFEST_SUFFIX}")


def load_local_manifests(output_dir: Path) -> dict[str, Path]:
    """Map each discovered source PDF filename to its local manifest path."""
    manifests: dict[str, Path] = {}
    for content_list_path in sorted(output_dir.glob(f"**/*{_CONTENT_LIST_SUFFIX}")):
        if content_list_path.name.endswith("_v2.json"):
            continue
        pdf_stem = content_list_path.name[: -len(_CONTENT_LIST_SUFFIX)]
        pdf_filename = f"{pdf_stem}.pdf"
        if pdf_filename in manifests:
            raise ValueError(
                f"duplicate local manifests found for {pdf_filename}: "
                f"{manifests[pdf_filename]}, {content_list_path}"
            )
        manifests[pdf_filename] = local_manifest_path(
            content_list_path,
            pdf_stem=pdf_stem,
        )
    return manifests
