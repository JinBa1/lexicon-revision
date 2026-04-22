from __future__ import annotations

from src.access.affiliation import (
    AffiliationDecision,
    AffiliationRepository,
    CommunityAffiliationResolver,
    CommunityDomainMatch,
    ManualAccessOverride,
)
from src.access.auth import (
    CLERK_IDENTITY_PROVIDER,
    STUB_EMAIL_IDENTITY_PROVIDER,
    X_USER_EMAIL_HEADER,
    ClerkRequestIdentityResolver,
    HeaderEmailRequestIdentityResolver,
    RequestIdentityResolver,
    build_request_identity_resolver,
)
from src.access.config import AccessAuthSettings, load_access_auth_settings
from src.access.errors import (
    CollectionAccessDeniedError,
    IdentityProvisioningError,
)
from src.access.models import (
    AuthenticatedUser,
    AuthorizationContext,
    CollectionAccess,
    RequestIdentity,
    ResolvedIdentity,
)
from src.access.service import CollectionAccessRepository, CollectionAccessService

__all__ = [
    "AuthenticatedUser",
    "AuthorizationContext",
    "AccessAuthSettings",
    "AffiliationDecision",
    "AffiliationRepository",
    "CollectionAccess",
    "CollectionAccessDeniedError",
    "CollectionAccessRepository",
    "CollectionAccessService",
    "CommunityAffiliationResolver",
    "ClerkRequestIdentityResolver",
    "CommunityDomainMatch",
    "CLERK_IDENTITY_PROVIDER",
    "HeaderEmailRequestIdentityResolver",
    "IdentityProvisioningError",
    "ManualAccessOverride",
    "RequestIdentity",
    "RequestIdentityResolver",
    "ResolvedIdentity",
    "STUB_EMAIL_IDENTITY_PROVIDER",
    "build_request_identity_resolver",
    "load_access_auth_settings",
    "X_USER_EMAIL_HEADER",
]
