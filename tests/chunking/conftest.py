from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# --- MinerU content_list.json fixtures ---

MINERU_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "mineru" / "cambridge"


def _mineru_path(stem: str) -> str:
    return str(MINERU_FIXTURES / stem / "hybrid_auto" / f"{stem}_content_list.json")


@pytest.fixture
def content_list_q1() -> str:
    return _mineru_path("y2025p1q1")


@pytest.fixture
def content_list_q3() -> str:
    return _mineru_path("y2025p1q3")


@pytest.fixture
def content_list_q7() -> str:
    return _mineru_path("y2025p1q7")


@pytest.fixture
def content_list_code_2018_q3() -> str:
    return _mineru_path("y2018p1q3")


@pytest.fixture
def content_list_formula_2018_q8() -> str:
    return _mineru_path("y2018p6q8")


@pytest.fixture
def content_list_media_2018_q4() -> str:
    return _mineru_path("y2018p1q4")


@pytest.fixture
def content_list_table_2018_q7() -> str:
    return _mineru_path("y2018p8q7")


@pytest.fixture
def content_list_tiers_2018_q1() -> str:
    return _mineru_path("y2018p1q1")


@pytest.fixture
def content_list_y2018p5q7() -> str:
    return _mineru_path("y2018p5q7")
