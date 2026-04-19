from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, TypedDict

from src.chunking.models import Chunk
from src.search.models import MediaRefResponse
from src.storage.base import ObjectStorage
from src.storage.keys import validate_key
from src.storage.manifest import ArtifactManifest

SUPPORTED_MEDIA_KINDS = {"image", "table"}
SUPPORTED_MEDIA_RELATIONS = {
    "direct",
    "inherited_shared",
    "visible_from_child",
}


class StoredMediaRef(TypedDict, total=False):
    media_id: str
    kind: str
    relation: str
    object_key: str | None
    access_url: str | None
    page_number: int | None
    bbox: list[float] | None
    owner_level: str
    owner_label: str | None
    order_index: int
    text_payload: str | None
    description: str | None


def build_storage_media_map(
    *,
    chunks: list[Chunk],
    manifests: dict[str, ArtifactManifest],
) -> dict[str, list[StoredMediaRef]]:
    media_map: dict[str, list[StoredMediaRef]] = {}
    manifest_indexes: dict[str, dict[str, str]] = {}

    for chunk in chunks:
        if not chunk.media:
            continue

        refs: list[StoredMediaRef] = []
        for ref in chunk.media:
            object_key: str | None = None
            if ref.file_path is not None:
                manifest = manifests.get(chunk.source_pdf)
                if manifest is None:
                    raise ValueError(
                        f"missing object key manifest for {chunk.source_pdf}"
                    )
                basename_to_key = manifest_indexes.get(chunk.source_pdf)
                if basename_to_key is None:
                    basename_to_key = _build_artifact_basename_index(manifest)
                    manifest_indexes[chunk.source_pdf] = basename_to_key
                object_key = basename_to_key.get(Path(ref.file_path).name)
                if object_key is None:
                    raise ValueError(
                        f"missing object key mapping for {chunk.source_pdf}: "
                        f"{ref.file_path}"
                    )

            refs.append(
                {
                    "media_id": ref.media_id,
                    "kind": ref.kind,
                    "relation": ref.relation,
                    "object_key": object_key,
                    "page_number": ref.page_number,
                    "bbox": list(ref.bbox) if ref.bbox is not None else None,
                    "owner_level": ref.owner_level,
                    "owner_label": ref.owner_label,
                    "order_index": ref.order_index,
                    "text_payload": ref.text_payload,
                    "description": ref.description,
                }
            )

        media_map[chunk.id] = refs

    return media_map


def write_storage_media_map(
    *,
    output_path: Path,
    media_map: dict[str, list[StoredMediaRef]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_json = json.dumps(media_map, indent=2, ensure_ascii=False)

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=output_path.parent,
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as handle:
            handle.write(sidecar_json)
            tmp_path = Path(handle.name)
        tmp_path.replace(output_path)
    except OSError:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def load_storage_media_map(path: Path) -> dict[str, list[StoredMediaRef]]:
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}

    validated = validate_storage_media_map(payload)
    if validated is None:
        return {}
    return validated


def validate_storage_media_map(
    payload: Any,
) -> dict[str, list[StoredMediaRef]] | None:
    if not isinstance(payload, dict):
        return None

    media_map: dict[str, list[StoredMediaRef]] = {}
    for chunk_id, refs in payload.items():
        if not isinstance(chunk_id, str) or not isinstance(refs, list):
            return None
        validated_refs: list[StoredMediaRef] = []
        for ref in refs:
            if not isinstance(ref, dict):
                return None
            validated = _validate_stored_media_ref(ref)
            if validated is None:
                return None
            validated_refs.append(validated)
        media_map[chunk_id] = validated_refs
    return media_map


def materialize_media_refs(
    *,
    refs: list[dict[str, Any]],
    object_storage: ObjectStorage | None,
    expires_in_seconds: int = 900,
) -> list[MediaRefResponse]:
    materialized: list[MediaRefResponse] = []
    for ref in refs:
        validated = _validate_stored_media_ref(ref)
        if validated is None:
            continue
        access_url: str | None = None
        object_key = validated.get("object_key")
        if object_key is not None and object_storage is not None:
            try:
                access_url = object_storage.presign_get(
                    object_key,
                    expires_in_seconds=expires_in_seconds,
                ).url
            except Exception:
                access_url = None
        materialized.append(
            MediaRefResponse(
                media_id=validated.get("media_id", ""),
                kind=validated.get("kind", ""),
                object_key=object_key,
                access_url=access_url,
                relation=validated.get("relation", ""),
            )
        )
    return materialized


def _build_artifact_basename_index(manifest: ArtifactManifest) -> dict[str, str]:
    basename_to_key: dict[str, str] = {}
    for artifact in manifest.artifacts:
        if artifact.kind != "image":
            continue
        basename = Path(artifact.key).name
        if basename in basename_to_key:
            raise ValueError(
                f"duplicate image artifact basename in manifest for "
                f"{manifest.paper_id}: {basename}"
            )
        basename_to_key[basename] = artifact.key
    return basename_to_key


def _validate_stored_media_ref(ref: dict[str, Any]) -> StoredMediaRef | None:
    if "file_path" in ref:
        return None

    media_id = ref.get("media_id")
    kind = ref.get("kind")
    relation = ref.get("relation")
    object_key = ref.get("object_key")

    if (
        type(media_id) is not str
        or not media_id
        or kind not in SUPPORTED_MEDIA_KINDS
        or relation not in SUPPORTED_MEDIA_RELATIONS
    ):
        return None

    if object_key is not None:
        if not isinstance(object_key, str):
            return None
        try:
            validate_key(object_key)
        except Exception:
            return None

    return dict(ref)
