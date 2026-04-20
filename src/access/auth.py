from __future__ import annotations

from typing import Protocol

from fastapi import Request
from src.access.email import normalize_email
from src.access.models import RequestIdentity

X_USER_EMAIL_HEADER = "X-User-Email"
STUB_EMAIL_IDENTITY_PROVIDER = "stub_header"


class RequestIdentityResolver(Protocol):
    def resolve_request_identity(self, request: Request) -> RequestIdentity: ...


class HeaderEmailRequestIdentityResolver:
    def __init__(self, *, header_name: str = X_USER_EMAIL_HEADER) -> None:
        self.header_name = header_name

    def resolve_request_identity(self, request: Request) -> RequestIdentity:
        normalized_email = normalize_email(request.headers.get(self.header_name))
        if normalized_email is None:
            return RequestIdentity.anonymous()
        return RequestIdentity(
            provider=STUB_EMAIL_IDENTITY_PROVIDER,
            external_subject=normalized_email,
            email=normalized_email,
            email_verified=False,
        )
