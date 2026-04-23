from __future__ import annotations

import pytest


def test_load_access_auth_settings_defaults_to_stub_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.access.config import load_access_auth_settings

    for key in (
        "ACCESS_AUTH_PROVIDER",
        "ACCESS_AUTH_HEADER_NAME",
        "CLERK_SECRET_KEY",
        "CLERK_AUTHORIZED_PARTIES",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = load_access_auth_settings()

    assert settings.provider == "stub_header"
    assert settings.stub_header_name == "X-User-Email"
    assert settings.clerk_secret_key is None
    assert settings.clerk_authorized_parties == []


def test_load_access_auth_settings_uses_stub_header_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.access.config import load_access_auth_settings

    monkeypatch.setenv("ACCESS_AUTH_HEADER_NAME", "X-Forwarded-User")

    settings = load_access_auth_settings()

    assert settings.stub_header_name == "X-Forwarded-User"


def test_load_access_auth_settings_ignores_blank_stub_header_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.access.config import load_access_auth_settings

    monkeypatch.setenv("ACCESS_AUTH_HEADER_NAME", "   ")

    settings = load_access_auth_settings()

    assert settings.stub_header_name == "X-User-Email"


def test_load_access_auth_settings_parses_clerk_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.access.config import load_access_auth_settings

    monkeypatch.setenv("ACCESS_AUTH_PROVIDER", "clerk")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv(
        "CLERK_AUTHORIZED_PARTIES",
        "https://example.com, https://app.example.com ",
    )

    settings = load_access_auth_settings()

    assert settings.provider == "clerk"
    assert settings.stub_header_name == "X-User-Email"
    assert settings.clerk_secret_key == "sk_test_123"
    assert settings.clerk_authorized_parties == [
        "https://example.com",
        "https://app.example.com",
    ]


def test_load_access_auth_settings_rejects_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.access.config import load_access_auth_settings

    monkeypatch.setenv("ACCESS_AUTH_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="Unknown access auth provider"):
        load_access_auth_settings()
