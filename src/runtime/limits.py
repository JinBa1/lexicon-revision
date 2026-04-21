from __future__ import annotations

from fastapi import HTTPException


class RequestBodyTooLargeError(Exception):
    pass


def enforce_query_length(query: str, *, max_chars: int) -> None:
    if len(query) > max_chars:
        raise HTTPException(
            status_code=422,
            detail=f"query length exceeds {max_chars} characters",
        )


def enforce_search_limit(limit: int, *, max_limit: int) -> None:
    if limit > max_limit:
        raise HTTPException(status_code=422, detail=f"limit cannot exceed {max_limit}")


def enforce_study_top_k(top_k: int, *, max_top_k: int) -> None:
    if top_k > max_top_k:
        raise HTTPException(
            status_code=422,
            detail=f"top_k cannot exceed {max_top_k}",
        )


def content_length_exceeds_limit(
    content_length: str | None,
    *,
    max_bytes: int,
) -> bool:
    if content_length is None or content_length == "":
        return False
    try:
        return int(content_length) > max_bytes
    except ValueError:
        return False
