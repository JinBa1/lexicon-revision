from __future__ import annotations

import pytest
from src.access.affiliation import AffiliationDecision
from src.access.errors import CollectionAccessDeniedError, IdentityProvisioningError
from src.access.models import AuthenticatedUser, CollectionAccess, RequestIdentity
from src.access.service import CollectionAccessService
from src.search.errors import CollectionNotFoundError


class FakeCollectionAccessRepository:
    def __init__(
        self,
        collections: dict[str, CollectionAccess],
        *,
        events: list[str] | None = None,
    ) -> None:
        self.collections = collections
        self.users: dict[str, AuthenticatedUser] = {}
        self.identity_users: dict[tuple[str | None, str | None], AuthenticatedUser] = {}
        self.memberships: set[tuple[str, str]] = set()
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.events = events

    def get_collection_access(self, collection_name: str) -> CollectionAccess | None:
        self.calls.append(("get_collection_access", (collection_name,)))
        if self.events is not None:
            self.events.append(f"repository:get_collection_access:{collection_name}")
        return self.collections.get(collection_name)

    def get_or_create_user_for_identity(
        self, identity: RequestIdentity
    ) -> AuthenticatedUser:
        self.calls.append(
            (
                "get_or_create_user_for_identity",
                (
                    identity.provider,
                    identity.external_subject,
                    identity.email,
                    identity.email_verified,
                ),
            )
        )
        if self.events is not None:
            self.events.append("repository:get_or_create_user_for_identity")
        assert identity.email is not None
        identity_key = (identity.provider, identity.external_subject)
        user = self.identity_users.get(identity_key)
        if user is None:
            user = self.users.get(identity.email)
        if user is None:
            user = AuthenticatedUser(
                user_id=f"user-{len(self.users) + 1}",
                email=identity.email,
            )
        self.users[identity.email] = user
        self.identity_users[identity_key] = user
        return user

    def has_active_membership(self, *, user_id: str, community_id: str) -> bool:
        self.calls.append(("has_active_membership", (user_id, community_id)))
        if self.events is not None:
            self.events.append("repository:has_active_membership")
        return (user_id, community_id) in self.memberships

    def ensure_active_membership(self, *, user_id: str, community_id: str) -> None:
        self.calls.append(("ensure_active_membership", (user_id, community_id)))
        if self.events is not None:
            self.events.append("repository:ensure_active_membership")
        self.memberships.add((user_id, community_id))


class FakeAffiliationResolver:
    def __init__(
        self, decision: AffiliationDecision, *, events: list[str] | None = None
    ) -> None:
        self.decision = decision
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.events = events

    def resolve_verified_email(self, email: str) -> AffiliationDecision:
        self.calls.append(("resolve_verified_email", (email,)))
        if self.events is not None:
            self.events.append("resolver:resolve_verified_email")
        return self.decision


def test_collection_access_service_allows_anonymous_public_access() -> None:
    repository = FakeCollectionAccessRepository(
        collections={
            "public": CollectionAccess(
                collection_id="collection-public",
                collection_name="public",
                community_id=None,
            )
        }
    )
    service = CollectionAccessService(repository=repository)

    context = service.authorize_collection(
        collection_name="public",
        request_identity=RequestIdentity.anonymous(),
    )

    assert context.collection == repository.collections["public"]
    assert context.identity.email is None
    assert context.identity.user is None
    assert context.identity.is_anonymous
    assert repository.calls == [("get_collection_access", ("public",))]


def test_collection_access_service_denies_anonymous_private_access() -> None:
    repository = FakeCollectionAccessRepository(
        collections={
            "private": CollectionAccess(
                collection_id="collection-private",
                collection_name="private",
                community_id="community-1",
            )
        }
    )
    service = CollectionAccessService(repository=repository)

    with pytest.raises(CollectionAccessDeniedError, match="private"):
        service.authorize_collection(
            collection_name="private",
            request_identity=RequestIdentity.anonymous(),
        )

    assert repository.calls == [("get_collection_access", ("private",))]


def test_collection_access_service_allows_active_member_on_private_collection() -> None:
    repository = FakeCollectionAccessRepository(
        collections={
            "private": CollectionAccess(
                collection_id="collection-private",
                collection_name="private",
                community_id="community-1",
            )
        }
    )
    user = AuthenticatedUser(user_id="user-1", email="member@example.com")
    repository.users[user.email] = user
    repository.memberships.add(("user-1", "community-1"))
    resolver = FakeAffiliationResolver(AffiliationDecision(community_id="community-1"))
    service = CollectionAccessService(
        repository=repository,
        affiliation_resolver=resolver,
    )

    context = service.authorize_collection(
        collection_name="private",
        request_identity=RequestIdentity(
            provider="clerk",
            external_subject="user_123",
            email="member@example.com",
            email_verified=True,
        ),
    )

    assert context.collection == repository.collections["private"]
    assert context.identity.email == "member@example.com"
    assert context.identity.provider == "clerk"
    assert context.identity.external_subject == "user_123"
    assert context.identity.user == user
    assert context.identity.is_authenticated
    assert resolver.calls == [("resolve_verified_email", ("member@example.com",))]
    assert repository.calls == [
        ("get_collection_access", ("private",)),
        (
            "get_or_create_user_for_identity",
            ("clerk", "user_123", "member@example.com", True),
        ),
        ("ensure_active_membership", ("user-1", "community-1")),
        ("has_active_membership", ("user-1", "community-1")),
    ]


def test_collection_access_service_bootstraps_membership_for_allowed_clerk_identity(  # noqa: E501
) -> None:
    events: list[str] = []
    repository = FakeCollectionAccessRepository(
        collections={
            "private": CollectionAccess(
                collection_id="collection-private",
                collection_name="private",
                community_id="community-1",
            )
        },
        events=events,
    )
    resolver = FakeAffiliationResolver(
        AffiliationDecision(community_id="community-1"),
        events=events,
    )
    service = CollectionAccessService(
        repository=repository,
        affiliation_resolver=resolver,
    )

    context = service.authorize_collection(
        collection_name="private",
        request_identity=RequestIdentity(
            provider="clerk",
            external_subject="user_123",
            email="member@example.com",
            email_verified=True,
        ),
    )

    assert context.identity.user == AuthenticatedUser(
        user_id="user-1",
        email="member@example.com",
    )
    assert resolver.calls == [("resolve_verified_email", ("member@example.com",))]
    assert repository.calls == [
        ("get_collection_access", ("private",)),
        (
            "get_or_create_user_for_identity",
            ("clerk", "user_123", "member@example.com", True),
        ),
        ("ensure_active_membership", ("user-1", "community-1")),
        ("has_active_membership", ("user-1", "community-1")),
    ]
    assert events == [
        "repository:get_collection_access:private",
        "resolver:resolve_verified_email",
        "repository:get_or_create_user_for_identity",
        "repository:ensure_active_membership",
        "repository:has_active_membership",
    ]


def test_collection_access_service_denies_unsupported_authenticated_identity_before_user_creation(  # noqa: E501
) -> None:
    events: list[str] = []
    repository = FakeCollectionAccessRepository(
        collections={
            "private": CollectionAccess(
                collection_id="collection-private",
                collection_name="private",
                community_id="community-1",
            )
        },
        events=events,
    )
    resolver = FakeAffiliationResolver(
        AffiliationDecision(
            community_id=None,
            deny_reason="unsupported_email_domain",
        ),
        events=events,
    )
    service = CollectionAccessService(
        repository=repository,
        affiliation_resolver=resolver,
    )

    with pytest.raises(IdentityProvisioningError, match="unsupported_email_domain"):
        service.authorize_collection(
            collection_name="private",
            request_identity=RequestIdentity(
                provider="clerk",
                external_subject="user_123",
                email="member@example.com",
                email_verified=True,
            ),
        )

    assert resolver.calls == [("resolve_verified_email", ("member@example.com",))]
    assert repository.calls == [("get_collection_access", ("private",))]
    assert events == [
        "repository:get_collection_access:private",
        "resolver:resolve_verified_email",
    ]


def test_collection_access_service_denies_wrong_user_for_private_collection() -> None:
    repository = FakeCollectionAccessRepository(
        collections={
            "private": CollectionAccess(
                collection_id="collection-private",
                collection_name="private",
                community_id="community-1",
            )
        }
    )
    repository.users["other@example.com"] = AuthenticatedUser(
        user_id="user-2",
        email="other@example.com",
    )
    resolver = FakeAffiliationResolver(AffiliationDecision(community_id="community-1"))
    service = CollectionAccessService(
        repository=repository,
        affiliation_resolver=resolver,
    )

    with pytest.raises(CollectionAccessDeniedError, match="private"):
        service.authorize_collection(
            collection_name="private",
            request_identity=RequestIdentity(
                provider="stub_header",
                external_subject="other@example.com",
                email="other@example.com",
                email_verified=False,
            ),
        )

    assert repository.calls == [
        ("get_collection_access", ("private",)),
        (
            "get_or_create_user_for_identity",
            ("stub_header", "other@example.com", "other@example.com", False),
        ),
        ("has_active_membership", ("user-2", "community-1")),
    ]


def test_service_denies_stale_clerk_membership_for_private_collection() -> None:
    repository = FakeCollectionAccessRepository(
        collections={
            "private": CollectionAccess(
                collection_id="collection-private",
                collection_name="private",
                community_id="community-1",
            )
        }
    )
    user = AuthenticatedUser(user_id="user-1", email="member@old.example.edu")
    repository.users[user.email] = user
    repository.identity_users[("clerk", "user_123")] = user
    repository.memberships.add((user.user_id, "community-1"))
    resolver = FakeAffiliationResolver(AffiliationDecision(community_id="community-2"))
    service = CollectionAccessService(
        repository=repository,
        affiliation_resolver=resolver,
    )

    with pytest.raises(CollectionAccessDeniedError, match="private"):
        service.authorize_collection(
            collection_name="private",
            request_identity=RequestIdentity(
                provider="clerk",
                external_subject="user_123",
                email="member@new.example.edu",
                email_verified=True,
            ),
        )

    assert repository.calls == [
        ("get_collection_access", ("private",)),
        (
            "get_or_create_user_for_identity",
            ("clerk", "user_123", "member@new.example.edu", True),
        ),
        ("ensure_active_membership", ("user-1", "community-2")),
    ]


def test_collection_access_service_raises_not_found_before_auth_logic() -> None:
    repository = FakeCollectionAccessRepository(collections={})
    service = CollectionAccessService(repository=repository)

    with pytest.raises(CollectionNotFoundError, match="missing"):
        service.authorize_collection(
            collection_name="missing",
            request_identity=RequestIdentity(
                provider="stub_header",
                external_subject="other@example.com",
                email="other@example.com",
                email_verified=False,
            ),
        )

    assert repository.calls == [("get_collection_access", ("missing",))]


def test_collection_access_service_resolves_authenticated_request_identity() -> None:
    repository = FakeCollectionAccessRepository(
        collections={
            "public": CollectionAccess(
                collection_id="collection-public",
                collection_name="public",
                community_id=None,
            )
        }
    )
    resolver = FakeAffiliationResolver(AffiliationDecision(community_id="community-1"))
    service = CollectionAccessService(
        repository=repository,
        affiliation_resolver=resolver,
    )

    identity = service.resolve_identity(
        RequestIdentity(
            provider="clerk",
            external_subject="user_123",
            email="user@example.com",
            email_verified=True,
        )
    )

    assert identity.email == "user@example.com"
    assert identity.provider == "clerk"
    assert identity.external_subject == "user_123"
    assert identity.user == AuthenticatedUser(
        user_id="user-1",
        email="user@example.com",
    )
    assert identity.is_authenticated
    assert resolver.calls == [("resolve_verified_email", ("user@example.com",))]
    assert repository.calls == [
        (
            "get_or_create_user_for_identity",
            ("clerk", "user_123", "user@example.com", True),
        ),
        ("ensure_active_membership", ("user-1", "community-1")),
    ]


def test_service_raises_domain_error_for_identity_provisioning_failure() -> None:
    repository = FakeCollectionAccessRepository(
        collections={
            "private": CollectionAccess(
                collection_id="collection-private",
                collection_name="private",
                community_id="community-1",
            )
        }
    )

    def _raise_for_identity(identity: RequestIdentity) -> AuthenticatedUser:
        del identity
        raise ValueError("verified email is required")

    repository.get_or_create_user_for_identity = _raise_for_identity  # type: ignore[method-assign]
    resolver = FakeAffiliationResolver(AffiliationDecision(community_id="community-1"))
    service = CollectionAccessService(
        repository=repository,
        affiliation_resolver=resolver,
    )

    with pytest.raises(IdentityProvisioningError, match="verified email is required"):
        service.authorize_collection(
            collection_name="private",
            request_identity=RequestIdentity(
                provider="clerk",
                external_subject="user_123",
                email="member@example.com",
                email_verified=False,
            ),
        )
