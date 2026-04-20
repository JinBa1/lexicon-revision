from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    user_id: str
    email: str


@dataclass(frozen=True, slots=True)
class CollectionAccess:
    collection_id: str
    collection_name: str
    community_id: str | None


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    email: str | None
    user: AuthenticatedUser | None

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None

    @property
    def is_anonymous(self) -> bool:
        return self.user is None


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    collection: CollectionAccess
    identity: ResolvedIdentity
