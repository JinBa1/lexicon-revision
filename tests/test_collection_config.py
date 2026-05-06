from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from src.collection_config import load_collection_config


def test_load_collection_config_returns_defaults_when_missing(tmp_path: Path) -> None:
    config = load_collection_config("cam-cs-tripos", config_dir=tmp_path)

    assert config.name == "cam-cs-tripos"
    assert config.community_id is None
    assert config.display_name is None


def test_load_collection_config_reads_private_community_and_display_name(
    tmp_path: Path,
) -> None:
    path = tmp_path / "uoe-mece10017.collection.json"
    path.write_text(
        (
            '{"name": "uoe-mece10017", '
            '"community_id": "edinburgh", '
            '"display_name": "Edinburgh MECE10017"}'
        ),
        encoding="utf-8",
    )

    config = load_collection_config("uoe-mece10017", config_dir=tmp_path)

    assert config.name == "uoe-mece10017"
    assert config.community_id == "edinburgh"
    assert config.display_name == "Edinburgh MECE10017"


@pytest.mark.parametrize("display_name", ["", "   "])
def test_load_collection_config_rejects_blank_display_name(
    tmp_path: Path,
    display_name: str,
) -> None:
    path = tmp_path / "uoe-mece10017.collection.json"
    path.write_text(
        json.dumps(
            {
                "name": "uoe-mece10017",
                "community_id": "edinburgh",
                "display_name": display_name,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="display_name"):
        load_collection_config("uoe-mece10017", config_dir=tmp_path)


def test_cambridge_fixture_collection_config_is_restricted_to_cambridge() -> None:
    config = load_collection_config("cam-cs-tripos-fixture")

    assert config.name == "cam-cs-tripos-fixture"
    assert config.community_id == "cambridge"
    assert config.display_name == "Cambridge CS Tripos"
