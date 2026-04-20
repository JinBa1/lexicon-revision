from __future__ import annotations

import json
from pathlib import Path

from src.metadata_schema.models import CollectionMetadataSchema

REPO_ROOT = Path(__file__).resolve().parents[2]


def default_schema_path(collection_name: str) -> Path:
    return (
        REPO_ROOT / "config" / "collections" / f"{collection_name}.metadata-schema.json"
    )


def load_collection_schema(path: str | Path) -> CollectionMetadataSchema:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return CollectionMetadataSchema.model_validate(payload)
