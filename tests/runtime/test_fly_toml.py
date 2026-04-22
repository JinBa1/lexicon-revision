from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_fly_toml() -> dict[str, object]:
    return tomllib.loads((REPO_ROOT / "fly.toml").read_text(encoding="utf-8"))


def test_fly_toml_uses_prod_build_target_key() -> None:
    config = _load_fly_toml()
    build = config.get("build")

    assert isinstance(build, dict)
    assert build.get("build-target") == "prod"
    assert "target" not in build
