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


def email_domain(email: str) -> str:
    normalized = require_normalized_email(email)
    local_part, separator, domain = normalized.partition("@")
    if separator != "@" or not local_part or not domain:
        raise ValueError("email must include local-part and domain")
    return domain
