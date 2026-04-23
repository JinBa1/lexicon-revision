from __future__ import annotations

from typing import Protocol

from src.access.affiliation import AffiliationDecision
from src.access.auth import STUB_EMAIL_IDENTITY_PROVIDER
from src.access.errors import CollectionAccessDeniedError, IdentityProvisioningError
from src.access.models import (
    AuthenticatedUser,
    AuthorizationContext,
    CollectionAccess,
    CollectionAccessListing,
    RequestIdentity,
    ResolvedIdentity,
    SupportedUniversityRecord,
)
from src.search.errors import CollectionNotFoundError


class CollectionAccessRepository(Protocol):
    def list_collections_with_access(
        self,
        *,
        request_identity: RequestIdentity,
        resolved_user_id: str | None,
        affiliation_community_id: str | None,
    ) -> list[CollectionAccessListing]: ...

    def list_supported_universities(self) -> list[SupportedUniversityRecord]: ...

    def get_collection_access(
        self,
        collection_name: str,
    ) -> CollectionAccess | None: ...

    def get_or_create_user_for_identity(
        self,
        identity: RequestIdentity,
    ) -> AuthenticatedUser: ...

    def ensure_active_membership(self, *, user_id: str, community_id: str) -> None: ...

    def has_active_membership(self, *, user_id: str, community_id: str) -> bool: ...


class AffiliationResolver(Protocol):
    def resolve_verified_email(self, email: str) -> AffiliationDecision: ...


class CollectionAccessService:
    def __init__(
        self,
        *,
        repository: CollectionAccessRepository,
        affiliation_resolver: AffiliationResolver | None = None,
    ) -> None:
        self.repository = repository
        self.affiliation_resolver = affiliation_resolver

    def resolve_identity(self, request_identity: RequestIdentity) -> ResolvedIdentity:
        identity, _ = self._resolve_identity_with_affiliation(request_identity)
        return identity

    def list_supported_universities(self) -> list[SupportedUniversityRecord]:
        return self.repository.list_supported_universities()

    def list_collections(
        self,
        *,
        request_identity: RequestIdentity,
    ) -> list[CollectionAccessListing]:
        if request_identity.is_anonymous:
            return self.repository.list_collections_with_access(
                request_identity=request_identity,
                resolved_user_id=None,
                affiliation_community_id=None,
            )
        try:
            identity, affiliation = self._resolve_identity_with_affiliation(
                request_identity
            )
        except IdentityProvisioningError as exc:
            if exc.code not in {
                "unsupported_email_domain",
                "ambiguous_email_domain",
            }:
                raise
            return self.repository.list_collections_with_access(
                request_identity=request_identity,
                resolved_user_id=None,
                affiliation_community_id=None,
            )
        resolved_user_id = identity.user.user_id if identity.user is not None else None
        affiliation_community_id = (
            affiliation.community_id if affiliation is not None else None
        )
        return self.repository.list_collections_with_access(
            request_identity=request_identity,
            resolved_user_id=resolved_user_id,
            affiliation_community_id=affiliation_community_id,
        )

    def _resolve_identity_with_affiliation(
        self,
        request_identity: RequestIdentity,
    ) -> tuple[ResolvedIdentity, AffiliationDecision | None]:
        if request_identity.is_anonymous:
            return ResolvedIdentity(request_identity=request_identity, user=None), None

        affiliation = self._resolve_affiliation(request_identity)
        try:
            user = self.repository.get_or_create_user_for_identity(request_identity)
        except ValueError as exc:
            raise IdentityProvisioningError(str(exc)) from exc

        if affiliation is not None and affiliation.community_id is not None:
            self.repository.ensure_active_membership(
                user_id=user.user_id,
                community_id=affiliation.community_id,
            )
        return ResolvedIdentity(
            request_identity=request_identity, user=user
        ), affiliation

    def _resolve_affiliation(
        self, request_identity: RequestIdentity
    ) -> AffiliationDecision | None:
        if request_identity.is_anonymous:
            return None
        if request_identity.provider == STUB_EMAIL_IDENTITY_PROVIDER:
            return None
        if not request_identity.email_verified or not request_identity.email:
            raise IdentityProvisioningError(
                "verified email is required for external identity provisioning"
            )
        if self.affiliation_resolver is None:
            raise IdentityProvisioningError(
                "affiliation_resolver is required for authenticated external identities"
            )

        try:
            decision = self.affiliation_resolver.resolve_verified_email(
                request_identity.email
            )
        except ValueError as exc:
            raise IdentityProvisioningError(str(exc)) from exc

        if not decision.is_allowed:
            raise IdentityProvisioningError(
                decision.deny_reason or "unsupported_authenticated_identity",
                code=decision.deny_reason,
            )
        return decision

    def authorize_collection(
        self,
        *,
        collection_name: str,
        request_identity: RequestIdentity,
    ) -> AuthorizationContext:
        collection = self.repository.get_collection_access(collection_name)
        if collection is None:
            raise CollectionNotFoundError(collection_name)

        identity, affiliation = self._resolve_identity_with_affiliation(
            request_identity
        )
        if collection.community_id is not None:
            user = identity.user
            if user is None:
                raise CollectionAccessDeniedError(collection_name)
            if (
                affiliation is not None
                and affiliation.community_id != collection.community_id
            ):
                raise CollectionAccessDeniedError(collection_name)
            if not self.repository.has_active_membership(
                user_id=user.user_id,
                community_id=collection.community_id,
            ):
                raise CollectionAccessDeniedError(collection_name)

        return AuthorizationContext(collection=collection, identity=identity)
