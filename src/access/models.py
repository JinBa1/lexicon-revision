from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    user_id: str
    email: str


@dataclass(frozen=True, slots=True)
class RequestIdentity:
    provider: str | None
    external_subject: str | None
    email: str | None
    email_verified: bool = False

    @classmethod
    def anonymous(cls) -> "RequestIdentity":
        return cls(
            provider=None,
            external_subject=None,
            email=None,
            email_verified=False,
        )

    @property
    def is_authenticated(self) -> bool:
        return (
            self.provider is not None
            or self.external_subject is not None
            or self.email is not None
        )

    @property
    def is_anonymous(self) -> bool:
        return not self.is_authenticated


@dataclass(frozen=True, slots=True)
class CollectionAccess:
    collection_id: str
    collection_name: str
    community_id: str | None


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    request_identity: RequestIdentity
    user: AuthenticatedUser | None

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None

    @property
    def is_anonymous(self) -> bool:
        return self.user is None

    @property
    def provider(self) -> str | None:
        return self.request_identity.provider

    @property
    def external_subject(self) -> str | None:
        return self.request_identity.external_subject

    @property
    def email(self) -> str | None:
        return self.request_identity.email

    @property
    def email_verified(self) -> bool:
        return self.request_identity.email_verified


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    collection: CollectionAccess
    identity: ResolvedIdentity
