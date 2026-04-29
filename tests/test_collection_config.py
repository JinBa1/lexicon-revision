from __future__ import annotations

from pathlib import Path

from src.collection_config import load_collection_config


def test_load_collection_config_returns_defaults_when_missing(tmp_path: Path) -> None:
    config = load_collection_config("cam-cs-tripos", config_dir=tmp_path)

    assert config.name == "cam-cs-tripos"
    assert config.community_id is None


def test_load_collection_config_reads_private_community(tmp_path: Path) -> None:
    path = tmp_path / "uoe-mece10017.collection.json"
    path.write_text(
        '{"name": "uoe-mece10017", "community_id": "edinburgh"}',
        encoding="utf-8",
    )

    config = load_collection_config("uoe-mece10017", config_dir=tmp_path)

    assert config.name == "uoe-mece10017"
    assert config.community_id == "edinburgh"
