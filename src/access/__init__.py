from __future__ import annotations

from src.access.affiliation import (
    AffiliationDecision,
    AffiliationRepository,
    CommunityAffiliationResolver,
    CommunityDomainMatch,
    ManualAccessOverride,
)
from src.access.auth import (
    STUB_EMAIL_IDENTITY_PROVIDER,
    X_USER_EMAIL_HEADER,
    HeaderEmailRequestIdentityResolver,
    RequestIdentityResolver,
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
    "CommunityDomainMatch",
    "HeaderEmailRequestIdentityResolver",
    "IdentityProvisioningError",
    "ManualAccessOverride",
    "RequestIdentity",
    "RequestIdentityResolver",
    "ResolvedIdentity",
    "STUB_EMAIL_IDENTITY_PROVIDER",
    "load_access_auth_settings",
    "X_USER_EMAIL_HEADER",
]
