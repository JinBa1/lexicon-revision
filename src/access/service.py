from __future__ import annotations

from typing import Protocol

from src.access.email import normalize_email
from src.access.errors import CollectionAccessDeniedError
from src.access.models import (
    AuthenticatedUser,
    AuthorizationContext,
    CollectionAccess,
    ResolvedIdentity,
)
from src.search.errors import CollectionNotFoundError

X_USER_EMAIL_HEADER = "X-User-Email"


class CollectionAccessRepository(Protocol):
    def get_collection_access(
        self,
        collection_name: str,
    ) -> CollectionAccess | None: ...

    def get_or_create_user(self, email: str) -> AuthenticatedUser: ...

    def has_active_membership(self, *, user_id: str, community_id: str) -> bool: ...


class CollectionAccessService:
    def __init__(self, *, repository: CollectionAccessRepository) -> None:
        self.repository = repository

    def resolve_identity(self, user_email_header: str | None) -> ResolvedIdentity:
        normalized_email = normalize_email(user_email_header)
        if normalized_email is None:
            return ResolvedIdentity(email=None, user=None)
        user = self.repository.get_or_create_user(normalized_email)
        return ResolvedIdentity(email=normalized_email, user=user)

    def authorize_collection(
        self,
        *,
        collection_name: str,
        user_email_header: str | None,
    ) -> AuthorizationContext:
        collection = self.repository.get_collection_access(collection_name)
        if collection is None:
            raise CollectionNotFoundError(collection_name)

        identity = self.resolve_identity(user_email_header)
        if collection.community_id is not None:
            user = identity.user
            if user is None or not self.repository.has_active_membership(
                user_id=user.user_id,
                community_id=collection.community_id,
            ):
                raise CollectionAccessDeniedError(collection_name)

        return AuthorizationContext(collection=collection, identity=identity)
