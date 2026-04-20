from __future__ import annotations

from src.access.auth import (
    STUB_EMAIL_IDENTITY_PROVIDER,
    X_USER_EMAIL_HEADER,
    HeaderEmailRequestIdentityResolver,
    RequestIdentityResolver,
)
from src.access.errors import CollectionAccessDeniedError, IdentityProvisioningError
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
    "CollectionAccess",
    "CollectionAccessDeniedError",
    "CollectionAccessRepository",
    "CollectionAccessService",
    "HeaderEmailRequestIdentityResolver",
    "IdentityProvisioningError",
    "RequestIdentity",
    "RequestIdentityResolver",
    "ResolvedIdentity",
    "STUB_EMAIL_IDENTITY_PROVIDER",
    "X_USER_EMAIL_HEADER",
]
