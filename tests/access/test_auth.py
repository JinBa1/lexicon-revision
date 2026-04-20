from __future__ import annotations

from fastapi import Request


def _request_with_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/search",
            "headers": headers,
        }
    )


def test_header_email_request_identity_resolver_returns_anonymous_when_missing() -> (
    None
):
    from src.access.auth import HeaderEmailRequestIdentityResolver
    from src.access.models import RequestIdentity

    resolver = HeaderEmailRequestIdentityResolver()

    identity = resolver.resolve_request_identity(_request_with_headers([]))

    assert identity == RequestIdentity.anonymous()


def test_header_email_request_identity_resolver_normalizes_stub_identity() -> None:
    from src.access.auth import (
        STUB_EMAIL_IDENTITY_PROVIDER,
        HeaderEmailRequestIdentityResolver,
    )
    from src.access.models import RequestIdentity

    resolver = HeaderEmailRequestIdentityResolver()

    identity = resolver.resolve_request_identity(
        _request_with_headers([(b"x-user-email", b"  Member@Example.com  ")])
    )

    assert identity == RequestIdentity(
        provider=STUB_EMAIL_IDENTITY_PROVIDER,
        external_subject="member@example.com",
        email="member@example.com",
        email_verified=False,
    )
