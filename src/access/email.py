from __future__ import annotations


def normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    normalized = email.strip().lower()
    return normalized or None


def require_normalized_email(email: str) -> str:
    normalized = normalize_email(email)
    if normalized is None:
        raise ValueError("email must not be blank")
    return normalized
