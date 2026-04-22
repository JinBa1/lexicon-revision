from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from src.access.auth import X_USER_EMAIL_HEADER

AuthProvider = Literal["stub_header", "clerk"]


@dataclass(frozen=True, slots=True)
class AccessAuthSettings:
    provider: AuthProvider
    stub_header_name: str
    clerk_secret_key: str | None
    clerk_authorized_parties: list[str]


def _parse_csv(value: str | None) -> list[str]:
    if value is None:
        return []

    return [item for item in (part.strip() for part in value.split(",")) if item]


def _load_stub_header_name() -> str:
    header_name = (os.getenv("ACCESS_AUTH_HEADER_NAME") or "").strip()
    return header_name or X_USER_EMAIL_HEADER


def load_access_auth_settings() -> AccessAuthSettings:
    provider = (os.getenv("ACCESS_AUTH_PROVIDER") or "stub_header").strip().lower()
    stub_header_name = _load_stub_header_name()

    if provider == "stub_header":
        return AccessAuthSettings(
            provider="stub_header",
            stub_header_name=stub_header_name,
            clerk_secret_key=None,
            clerk_authorized_parties=[],
        )

    if provider == "clerk":
        return AccessAuthSettings(
            provider="clerk",
            stub_header_name=stub_header_name,
            clerk_secret_key=os.getenv("CLERK_SECRET_KEY"),
            clerk_authorized_parties=_parse_csv(os.getenv("CLERK_AUTHORIZED_PARTIES")),
        )

    raise ValueError(f"Unknown access auth provider: {provider}")
