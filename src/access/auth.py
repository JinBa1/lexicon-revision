from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import httpx
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import Request
from src.access.email import normalize_email
from src.access.models import RequestIdentity

if TYPE_CHECKING:
    from src.access.config import AccessAuthSettings

X_USER_EMAIL_HEADER = "X-User-Email"
STUB_EMAIL_IDENTITY_PROVIDER = "stub_header"
CLERK_IDENTITY_PROVIDER = "clerk"


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


class ClerkRequestIdentityResolver:
    def __init__(
        self,
        settings: AccessAuthSettings,
        clerk: Clerk | None = None,
    ) -> None:
        if settings.provider != CLERK_IDENTITY_PROVIDER:
            raise ValueError("ClerkRequestIdentityResolver requires provider='clerk'")
        if not settings.clerk_secret_key:
            raise ValueError("ClerkRequestIdentityResolver requires CLERK_SECRET_KEY")

        self._settings = settings
        self._clerk = clerk or Clerk(bearer_auth=settings.clerk_secret_key)

    def resolve_request_identity(self, request: Request) -> RequestIdentity:
        request_state = self._clerk.authenticate_request(
            self._build_httpx_request(request),
            AuthenticateRequestOptions(
                secret_key=self._settings.clerk_secret_key,
                authorized_parties=self._settings.clerk_authorized_parties or None,
            ),
        )
        if not request_state.is_signed_in:
            return RequestIdentity.anonymous()

        payload = request_state.payload or {}
        external_subject = payload.get("sub")
        primary_email, email_verified = self._load_primary_email(
            external_subject=external_subject,
        )
        return RequestIdentity(
            provider=CLERK_IDENTITY_PROVIDER,
            external_subject=external_subject,
            email=primary_email,
            email_verified=email_verified,
        )

    @staticmethod
    def _build_httpx_request(request: Request) -> httpx.Request:
        forwarded_proto = request.headers.get("x-forwarded-proto")
        url = request.url
        if forwarded_proto:
            url = url.replace(scheme=forwarded_proto.split(",")[0].strip())

        return httpx.Request(
            method=request.method,
            url=str(url),
            headers=request.headers.raw,
        )

    def _load_primary_email(
        self,
        *,
        external_subject: str | None,
    ) -> tuple[str | None, bool]:
        if not external_subject:
            return None, False

        user = self._clerk.users.get(user_id=external_subject)
        primary_email_id = getattr(user, "primary_email_address_id", None)
        if primary_email_id is None:
            return None, False

        for email_address in getattr(user, "email_addresses", []):
            if getattr(email_address, "id", None) != primary_email_id:
                continue

            normalized_email = normalize_email(
                getattr(email_address, "email_address", None)
            )
            verification = getattr(email_address, "verification", None)
            verified = getattr(verification, "status", None) == "verified"
            return normalized_email, verified

        return None, False


def build_request_identity_resolver(
    settings: AccessAuthSettings,
) -> RequestIdentityResolver:
    if settings.provider == CLERK_IDENTITY_PROVIDER:
        return ClerkRequestIdentityResolver(settings)
    return HeaderEmailRequestIdentityResolver(header_name=settings.stub_header_name)
