from __future__ import annotations

from dataclasses import dataclass

import pytest
from src.access.affiliation import AffiliationDecision
from src.access.errors import IdentityProvisioningError
from src.access.models import (
    AuthenticatedUser,
    CollectionAccessListing,
    RequestIdentity,
    SupportedUniversityRecord,
)
from src.access.service import CollectionAccessService


@dataclass
class _FakeAffiliationResolver:
    decision: AffiliationDecision

    def resolve_verified_email(self, email: str) -> AffiliationDecision:
        return self.decision


class _FakeAccessRepository:
    def __init__(self, listings: list[CollectionAccessListing]) -> None:
        self._listings = listings
        self._universities = [
            SupportedUniversityRecord(
                community_id="c-cam",
                display_name="Cambridge",
                email_domains=("cam.ac.uk",),
            )
        ]
        self.user = AuthenticatedUser(user_id="user-1", email="a@cam.ac.uk")
        self.received_identity: RequestIdentity | None = None
        self.received_user_id: str | None = None
        self.received_affiliation: str | None = None

    def list_collections_with_access(
        self,
        *,
        request_identity: RequestIdentity,
        resolved_user_id: str | None,
        affiliation_community_id: str | None,
    ) -> list[CollectionAccessListing]:
        self.received_identity = request_identity
        self.received_user_id = resolved_user_id
        self.received_affiliation = affiliation_community_id
        return list(self._listings)

    def list_supported_universities(self) -> list[SupportedUniversityRecord]:
        return list(self._universities)

    def get_or_create_user_for_identity(self, identity):
        return self.user

    def ensure_active_membership(self, *, user_id: str, community_id: str) -> None:
        pass

    def has_active_membership(self, *, user_id: str, community_id: str) -> bool:
        return True

    def get_collection_access(self, collection_name: str):
        return None


def _listing(name: str, access_state: str) -> CollectionAccessListing:
    return CollectionAccessListing(
        collection_name=name,
        display_name=name,
        community_id=None,
        community_display_name=None,
        paper_count=0,
        year_start=None,
        year_end=None,
        access_state=access_state,
        lock_reason=None,
        metadata_schema=None,
    )


def test_list_collections_anonymous_passes_nones_to_repository():
    repo = _FakeAccessRepository(listings=[_listing("x", "accessible")])
    service = CollectionAccessService(repository=repo, affiliation_resolver=None)

    result = service.list_collections(request_identity=RequestIdentity.anonymous())

    assert [row.collection_name for row in result] == ["x"]
    assert repo.received_user_id is None
    assert repo.received_affiliation is None


def test_list_collections_authed_resolves_user_and_affiliation():
    repo = _FakeAccessRepository(listings=[])
    resolver = _FakeAffiliationResolver(
        decision=AffiliationDecision(
            community_id="c-cam",
            deny_reason=None,
        )
    )
    service = CollectionAccessService(
        repository=repo,
        affiliation_resolver=resolver,
    )
    identity = RequestIdentity(
        provider="clerk",
        external_subject="sub-1",
        email="a@cam.ac.uk",
        email_verified=True,
    )

    service.list_collections(request_identity=identity)

    assert repo.received_user_id == "user-1"
    assert repo.received_affiliation == "c-cam"


def test_list_collections_for_unsupported_authenticated_identity_returns_locked_context(  # noqa: E501
):
    repo = _FakeAccessRepository(
        listings=[_listing("locked", "locked_wrong_affiliation")]
    )
    resolver = _FakeAffiliationResolver(
        decision=AffiliationDecision(
            community_id=None,
            deny_reason="unsupported_email_domain",
        )
    )
    service = CollectionAccessService(
        repository=repo,
        affiliation_resolver=resolver,
    )
    identity = RequestIdentity(
        provider="clerk",
        external_subject="sub-2",
        email="user@example.com",
        email_verified=True,
    )

    result = service.list_collections(request_identity=identity)

    assert [row.collection_name for row in result] == ["locked"]
    assert repo.received_identity == identity
    assert repo.received_user_id is None
    assert repo.received_affiliation is None


def test_list_collections_reraises_non_fallback_provisioning_errors() -> None:
    repo = _FakeAccessRepository(
        listings=[_listing("locked", "locked_wrong_affiliation")]
    )
    service = CollectionAccessService(
        repository=repo,
        affiliation_resolver=None,
    )
    identity = RequestIdentity(
        provider="clerk",
        external_subject="sub-3",
        email="user@example.com",
        email_verified=False,
    )

    with pytest.raises(
        IdentityProvisioningError,
        match="verified email is required",
    ):
        service.list_collections(request_identity=identity)

    assert repo.received_identity is None
    assert repo.received_user_id is None
    assert repo.received_affiliation is None


def test_list_collections_falls_back_by_error_code_not_message() -> None:
    repo = _FakeAccessRepository(
        listings=[_listing("locked", "locked_wrong_affiliation")]
    )
    service = CollectionAccessService(
        repository=repo,
        affiliation_resolver=None,
    )
    identity = RequestIdentity(
        provider="clerk",
        external_subject="sub-4",
        email="user@example.com",
        email_verified=True,
    )

    def _raise_typed_error(
        request_identity: RequestIdentity,
    ) -> tuple[object, object]:
        del request_identity
        raise IdentityProvisioningError(
            "viewer is not eligible for automatic affiliation",
            code="unsupported_email_domain",
        )

    service._resolve_identity_with_affiliation = _raise_typed_error  # type: ignore[method-assign]

    result = service.list_collections(request_identity=identity)

    assert [row.collection_name for row in result] == ["locked"]
    assert repo.received_identity == identity
    assert repo.received_user_id is None
    assert repo.received_affiliation is None


def test_list_supported_universities_delegates_to_repository() -> None:
    repo = _FakeAccessRepository(listings=[])
    service = CollectionAccessService(repository=repo, affiliation_resolver=None)

    result = service.list_supported_universities()

    assert result == repo.list_supported_universities()
