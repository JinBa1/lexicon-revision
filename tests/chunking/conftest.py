from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo_path(relative_path: str) -> str:
    return str(REPO_ROOT / relative_path)


@pytest.fixture
def sample_pdf_q1() -> str:
    return _repo_path("data/papers/2025/y2025p1q1.pdf")


@pytest.fixture
def sample_pdf_q3() -> str:
    return _repo_path("data/papers/2025/y2025p1q3.pdf")


@pytest.fixture
def sample_pdf_q7() -> str:
    return _repo_path("data/papers/2025/y2025p1q7.pdf")


@pytest.fixture
def real_pdf_code_2018_q3() -> str:
    return _repo_path("tests/data/code/y2018p1q3.pdf")


@pytest.fixture
def real_pdf_formula_2018_q8() -> str:
    return _repo_path("tests/data/formula/y2018p6q8.pdf")


@pytest.fixture
def real_pdf_media_2018_q4() -> str:
    return _repo_path("tests/data/media/y2018p1q4.pdf")


@pytest.fixture
def real_pdf_media_2018_q7() -> str:
    return _repo_path("tests/data/media/y2018p5q7.pdf")


@pytest.fixture
def real_pdf_media_2019_q4() -> str:
    return _repo_path("tests/data/media/y2019p8q4.pdf")


@pytest.fixture
def real_pdf_media_2019_q5() -> str:
    return _repo_path("tests/data/media/y2019p9q5.pdf")


@pytest.fixture
def real_pdf_media_2019_q9() -> str:
    return _repo_path("tests/data/media/y2019p9q9.pdf")


@pytest.fixture
def real_pdf_table_2018_q7() -> str:
    return _repo_path("tests/data/table/y2018p8q7.pdf")


@pytest.fixture
def real_pdf_table_2019_q5() -> str:
    return _repo_path("tests/data/table/y2019p8q5.pdf")


@pytest.fixture
def real_pdf_tiers_2018_q1() -> str:
    return _repo_path("tests/data/tiers/y2018p1q1.pdf")


@pytest.fixture
def real_pdf_tiers_2018_q2() -> str:
    return _repo_path("tests/data/tiers/y2018p7q2.pdf")


@pytest.fixture
def real_pdf_tiers_2019_q1() -> str:
    return _repo_path("tests/data/tiers/y2019p1q1.pdf")


@pytest.fixture
def real_pdf_tiers_2019_q11() -> str:
    return _repo_path("tests/data/tiers/y2019p9q11.pdf")
