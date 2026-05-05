from __future__ import annotations

import math
from typing import Any

from src.chunking.models import Chunk
from src.search.media_sidecar import (
    SUPPORTED_MEDIA_KINDS,
    SUPPORTED_MEDIA_RELATIONS,
    StoredMediaRef,
)
from src.storage.keys import validate_key

DB_MEDIA_REF_FORBIDDEN_KEYS = frozenset({"file_path", "access_url"})
DB_MEDIA_REF_ALLOWED_KEYS = frozenset(
    {
        "media_id",
        "kind",
        "relation",
        "object_key",
        "page_number",
        "bbox",
        "owner_level",
        "owner_label",
        "order_index",
        "text_payload",
        "description",
    }
)


def validate_media_refs_by_chunk_id(
    *,
    chunks: list[Chunk],
    media_refs_by_chunk_id: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, list[StoredMediaRef]]:
    chunk_ids = {chunk.id for chunk in chunks}
    if media_refs_by_chunk_id is None:
        media_refs_by_chunk_id = {}
    if not isinstance(media_refs_by_chunk_id, dict):
        raise ValueError("media_refs_by_chunk_id must be a dict")

    unknown_chunk_ids = set(media_refs_by_chunk_id) - chunk_ids
    if unknown_chunk_ids:
        unknown = sorted(unknown_chunk_ids)[0]
        raise ValueError(f"unknown chunk id in media refs: {unknown}")

    return {
        chunk.id: sanitize_db_media_refs(media_refs_by_chunk_id.get(chunk.id, []))
        for chunk in chunks
    }


def sanitize_db_media_refs(refs: list[dict[str, Any]]) -> list[StoredMediaRef]:
    if not isinstance(refs, list):
        raise ValueError("media refs must be a list")

    sanitized: list[StoredMediaRef] = []
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            raise ValueError(f"media ref {index} must be an object")
        sanitized.append(_sanitize_db_media_ref(ref))
    return sanitized


def _sanitize_db_media_ref(ref: dict[str, Any]) -> StoredMediaRef:
    for field in DB_MEDIA_REF_FORBIDDEN_KEYS:
        if field in ref:
            raise ValueError(f"media ref field is forbidden: {field}")

    unknown_fields = set(ref) - DB_MEDIA_REF_ALLOWED_KEYS
    if unknown_fields:
        fields = ", ".join(sorted(unknown_fields))
        raise ValueError(f"unknown media ref fields: {fields}")

    media_id = ref.get("media_id")
    if type(media_id) is not str or not media_id:
        raise ValueError("media ref media_id must be a non-empty string")

    kind = ref.get("kind")
    if kind not in SUPPORTED_MEDIA_KINDS:
        raise ValueError(f"unsupported media ref kind: {kind}")

    relation = ref.get("relation")
    if relation not in SUPPORTED_MEDIA_RELATIONS:
        raise ValueError(f"unsupported media ref relation: {relation}")

    object_key = ref.get("object_key")
    if object_key is not None:
        if type(object_key) is not str:
            raise ValueError("media ref object_key must be a string or null")
        try:
            validate_key(object_key)
        except Exception as e:
            raise ValueError(f"invalid media ref object_key: {object_key}") from e

    sanitized: StoredMediaRef = {
        "media_id": media_id,
        "kind": kind,
        "relation": relation,
    }

    if "object_key" in ref:
        sanitized["object_key"] = object_key
    if "page_number" in ref:
        sanitized["page_number"] = _validate_optional_page_number(ref["page_number"])
    if "bbox" in ref:
        sanitized["bbox"] = _validate_optional_bbox(ref["bbox"])
    if "owner_level" in ref:
        sanitized["owner_level"] = _validate_optional_owner_level(ref["owner_level"])
    if "owner_label" in ref:
        sanitized["owner_label"] = _validate_optional_string_or_none(
            "owner_label",
            ref["owner_label"],
        )
    if "order_index" in ref:
        sanitized["order_index"] = _validate_optional_order_index(ref["order_index"])
    if "text_payload" in ref:
        sanitized["text_payload"] = _validate_optional_string_or_none(
            "text_payload",
            ref["text_payload"],
        )
    if "description" in ref:
        sanitized["description"] = _validate_optional_string_or_none(
            "description",
            ref["description"],
        )

    return sanitized


def _validate_optional_page_number(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 1:
        raise ValueError("media ref page_number must be an integer >= 1 or null")
    return value


def _validate_optional_bbox(value: Any) -> list[float] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("media ref bbox must be a list of 4 finite numbers or null")
    for coordinate in value:
        if type(coordinate) not in (int, float) or not math.isfinite(coordinate):
            raise ValueError(
                "media ref bbox must be a list of 4 finite numbers or null"
            )
    return value


def _validate_optional_owner_level(value: Any) -> str:
    if type(value) is not str or not value:
        raise ValueError("media ref owner_level must be a non-empty string")
    return value


def _validate_optional_string_or_none(field: str, value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError(f"media ref {field} must be a string or null")
    return value


def _validate_optional_order_index(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError("media ref order_index must be an integer >= 0 or null")
    return value
