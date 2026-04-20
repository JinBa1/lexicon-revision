from __future__ import annotations

from typing import Protocol

from src.access.errors import CollectionAccessDeniedError, IdentityProvisioningError
from src.access.models import (
    AuthenticatedUser,
    AuthorizationContext,
    CollectionAccess,
    RequestIdentity,
    ResolvedIdentity,
)
from src.search.errors import CollectionNotFoundError


class CollectionAccessRepository(Protocol):
    def get_collection_access(
        self,
        collection_name: str,
    ) -> CollectionAccess | None: ...

    def get_or_create_user_for_identity(
        self,
        identity: RequestIdentity,
    ) -> AuthenticatedUser: ...

    def has_active_membership(self, *, user_id: str, community_id: str) -> bool: ...


class CollectionAccessService:
    def __init__(self, *, repository: CollectionAccessRepository) -> None:
        self.repository = repository

    def resolve_identity(self, request_identity: RequestIdentity) -> ResolvedIdentity:
        if request_identity.is_anonymous:
            return ResolvedIdentity(request_identity=request_identity, user=None)
        try:
            user = self.repository.get_or_create_user_for_identity(request_identity)
        except ValueError as exc:
            raise IdentityProvisioningError(str(exc)) from exc
        return ResolvedIdentity(request_identity=request_identity, user=user)

    def authorize_collection(
        self,
        *,
        collection_name: str,
        request_identity: RequestIdentity,
    ) -> AuthorizationContext:
        collection = self.repository.get_collection_access(collection_name)
        if collection is None:
            raise CollectionNotFoundError(collection_name)

        identity = self.resolve_identity(request_identity)
        if collection.community_id is not None:
            user = identity.user
            if user is None or not self.repository.has_active_membership(
                user_id=user.user_id,
                community_id=collection.community_id,
            ):
                raise CollectionAccessDeniedError(collection_name)

        return AuthorizationContext(collection=collection, identity=identity)
