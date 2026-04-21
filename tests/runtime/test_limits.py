from __future__ import annotations

import pytest
from fastapi import HTTPException
from src.runtime.limits import (
    content_length_exceeds_limit,
    enforce_query_length,
    enforce_search_limit,
    enforce_study_top_k,
)


def test_enforce_query_length_allows_query_within_limit() -> None:
    enforce_query_length("binary search", max_chars=20)


def test_enforce_query_length_rejects_query_over_limit() -> None:
    with pytest.raises(HTTPException, match="query length exceeds 5 characters"):
        enforce_query_length("binary search", max_chars=5)


def test_enforce_search_limit_allows_limit_within_runtime_cap() -> None:
    enforce_search_limit(10, max_limit=10)


def test_enforce_search_limit_rejects_limit_over_runtime_cap() -> None:
    with pytest.raises(HTTPException, match="limit cannot exceed 5"):
        enforce_search_limit(6, max_limit=5)


def test_enforce_study_top_k_allows_top_k_within_runtime_cap() -> None:
    enforce_study_top_k(5, max_top_k=5)


def test_enforce_study_top_k_rejects_top_k_over_runtime_cap() -> None:
    with pytest.raises(HTTPException, match="top_k cannot exceed 4"):
        enforce_study_top_k(5, max_top_k=4)


def test_content_length_exceeds_limit_rejects_large_declared_bodies() -> None:
    assert content_length_exceeds_limit("129", max_bytes=128) is True


def test_content_length_exceeds_limit_ignores_missing_or_invalid_header() -> None:
    assert content_length_exceeds_limit(None, max_bytes=128) is False
    assert content_length_exceeds_limit("not-an-int", max_bytes=128) is False
