from __future__ import annotations

from types import SimpleNamespace

import pytest
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


def test_build_request_identity_resolver_returns_stub_resolver_for_stub_provider() -> (
    None
):
    from src.access.auth import (
        HeaderEmailRequestIdentityResolver,
        build_request_identity_resolver,
    )
    from src.access.config import AccessAuthSettings

    resolver = build_request_identity_resolver(
        AccessAuthSettings(
            provider="stub_header",
            stub_header_name="X-Test-User",
            clerk_secret_key=None,
            clerk_authorized_parties=[],
        )
    )

    assert isinstance(resolver, HeaderEmailRequestIdentityResolver)
    assert resolver.header_name == "X-Test-User"


def test_build_request_identity_resolver_returns_clerk_resolver_for_clerk_provider() -> (  # noqa: E501
    None
):
    from src.access.auth import (
        ClerkRequestIdentityResolver,
        build_request_identity_resolver,
    )
    from src.access.config import AccessAuthSettings

    resolver = build_request_identity_resolver(
        AccessAuthSettings(
            provider="clerk",
            stub_header_name="X-Ignored",
            clerk_secret_key="sk_test_123",
            clerk_authorized_parties=["https://example.com"],
        )
    )

    assert isinstance(resolver, ClerkRequestIdentityResolver)


def test_clerk_request_identity_resolver_returns_anonymous_for_unsigned_request() -> (
    None
):
    from src.access.auth import ClerkRequestIdentityResolver
    from src.access.config import AccessAuthSettings
    from src.access.models import RequestIdentity

    clerk = SimpleNamespace(
        authenticate_request=lambda request, options: SimpleNamespace(
            is_signed_in=False,
            payload=None,
        )
    )
    resolver = ClerkRequestIdentityResolver(
        AccessAuthSettings(
            provider="clerk",
            stub_header_name="X-User-Email",
            clerk_secret_key="sk_test_123",
            clerk_authorized_parties=["https://example.com"],
        ),
        clerk=clerk,
    )

    identity = resolver.resolve_request_identity(_request_with_headers([]))

    assert identity == RequestIdentity.anonymous()


def test_clerk_request_identity_resolver_returns_verified_primary_email() -> None:
    from src.access.auth import CLERK_IDENTITY_PROVIDER, ClerkRequestIdentityResolver
    from src.access.config import AccessAuthSettings
    from src.access.models import RequestIdentity

    captured: dict[str, object] = {}

    def _authenticate_request(request, options):
        captured["request"] = request
        captured["options"] = options
        return SimpleNamespace(
            is_signed_in=True,
            payload={"sub": "user_123"},
        )

    clerk = SimpleNamespace(
        authenticate_request=_authenticate_request,
        users=SimpleNamespace(
            get=lambda *, user_id: SimpleNamespace(
                primary_email_address_id="email_primary",
                email_addresses=[
                    SimpleNamespace(
                        id="email_secondary",
                        email_address="other@example.com",
                        verification=SimpleNamespace(status="verified"),
                    ),
                    SimpleNamespace(
                        id="email_primary",
                        email_address="  Member@Example.com  ",
                        verification=SimpleNamespace(status="verified"),
                    ),
                ],
            )
        ),
    )
    resolver = ClerkRequestIdentityResolver(
        AccessAuthSettings(
            provider="clerk",
            stub_header_name="X-User-Email",
            clerk_secret_key="sk_test_123",
            clerk_authorized_parties=["https://example.com", "https://app.example.com"],
        ),
        clerk=clerk,
    )

    identity = resolver.resolve_request_identity(
        _request_with_headers(
            [
                (b"host", b"testserver"),
                (b"authorization", b"Bearer test-token"),
                (b"x-forwarded-proto", b"https"),
            ]
        )
    )

    assert identity == RequestIdentity(
        provider=CLERK_IDENTITY_PROVIDER,
        external_subject="user_123",
        email="member@example.com",
        email_verified=True,
    )
    assert str(captured["request"].url) == "https://testserver/search"
    assert captured["options"].secret_key == "sk_test_123"
    assert captured["options"].authorized_parties == [
        "https://example.com",
        "https://app.example.com",
    ]


def test_clerk_request_identity_resolver_omits_authorized_parties_when_unset() -> None:
    from src.access.auth import ClerkRequestIdentityResolver
    from src.access.config import AccessAuthSettings

    captured: dict[str, object] = {}

    def _authenticate_request(request, options):
        del request
        captured["options"] = options
        return SimpleNamespace(
            is_signed_in=False,
            payload=None,
        )

    clerk = SimpleNamespace(authenticate_request=_authenticate_request)
    resolver = ClerkRequestIdentityResolver(
        AccessAuthSettings(
            provider="clerk",
            stub_header_name="X-User-Email",
            clerk_secret_key="sk_test_123",
            clerk_authorized_parties=[],
        ),
        clerk=clerk,
    )

    resolver.resolve_request_identity(
        _request_with_headers(
            [
                (b"host", b"testserver"),
                (b"authorization", b"Bearer test-token"),
            ]
        )
    )

    assert captured["options"].authorized_parties is None


def test_clerk_request_identity_resolver_rejects_non_clerk_provider() -> None:
    from src.access.auth import ClerkRequestIdentityResolver
    from src.access.config import AccessAuthSettings

    with pytest.raises(ValueError, match="provider='clerk'"):
        ClerkRequestIdentityResolver(
            AccessAuthSettings(
                provider="stub_header",
                stub_header_name="X-User-Email",
                clerk_secret_key=None,
                clerk_authorized_parties=[],
            )
        )


def test_clerk_request_identity_resolver_requires_secret_key() -> None:
    from src.access.auth import ClerkRequestIdentityResolver
    from src.access.config import AccessAuthSettings

    with pytest.raises(ValueError, match="CLERK_SECRET_KEY"):
        ClerkRequestIdentityResolver(
            AccessAuthSettings(
                provider="clerk",
                stub_header_name="X-User-Email",
                clerk_secret_key=None,
                clerk_authorized_parties=[],
            )
        )
