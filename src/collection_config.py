from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLLECTION_CONFIG_DIR = REPO_ROOT / "config" / "collections"


class CollectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    community_id: str | None = None


def default_collection_config_path(
    collection_name: str,
    *,
    config_dir: str | Path = DEFAULT_COLLECTION_CONFIG_DIR,
) -> Path:
    return Path(config_dir) / f"{collection_name}.collection.json"


def load_collection_config(
    collection_name: str,
    *,
    config_path: str | Path | None = None,
    config_dir: str | Path = DEFAULT_COLLECTION_CONFIG_DIR,
) -> CollectionConfig:
    path = (
        Path(config_path)
        if config_path is not None
        else default_collection_config_path(collection_name, config_dir=config_dir)
    )
    if not path.exists():
        if config_path is not None:
            raise FileNotFoundError(path)
        return CollectionConfig(name=collection_name)

    config = CollectionConfig.model_validate_json(path.read_text(encoding="utf-8"))
    if config.name != collection_name:
        raise ValueError(
            f"Collection config {path} declares name {config.name!r}, "
            f"expected {collection_name!r}"
        )
    return config
