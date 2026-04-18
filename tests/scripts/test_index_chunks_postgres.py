from __future__ import annotations

import sys

from scripts.index_chunks_postgres import parse_args


def test_parse_args_defaults(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "index_chunks_postgres.py",
            "--input",
            "tests/data/mineru_fixtures",
            "--collection",
            "fixture",
        ],
    )

    args = parse_args()

    assert args.input == "tests/data/mineru_fixtures"
    assert args.collection == "fixture"
    assert args.recreate_collection is False


def test_parse_args_supports_recreate(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "index_chunks_postgres.py",
            "--input",
            "tests/data/mineru_fixtures",
            "--collection",
            "fixture",
            "--recreate-collection",
        ],
    )

    assert parse_args().recreate_collection is True
