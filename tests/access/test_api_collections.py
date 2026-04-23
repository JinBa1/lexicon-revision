from __future__ import annotations

import httpx
import pytest
from src.access.errors import IdentityProvisioningError
from src.access.models import CollectionAccessListing, RequestIdentity


class _FakeAccessService:
    def __init__(
        self,
        listings: list[CollectionAccessListing],
        *,
        error: Exception | None = None,
    ) -> None:
        self._listings = listings
        self._error = error
        self.received_identity: RequestIdentity | None = None

    def list_collections(
        self, *, request_identity: RequestIdentity
    ) -> list[CollectionAccessListing]:
        self.received_identity = request_identity
        if self._error is not None:
            raise self._error
        return list(self._listings)


class _FakeIdentityResolver:
    def __init__(self, identity: RequestIdentity) -> None:
        self._identity = identity

    def resolve_request_identity(self, request) -> RequestIdentity:
        return self._identity


def _listing(
    name: str,
    *,
    community_id: str | None = None,
    access_state: str = "accessible",
    metadata_schema: dict | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
) -> CollectionAccessListing:
    return CollectionAccessListing(
        collection_name=name,
        display_name=name,
        community_id=community_id,
        community_display_name="Cambridge" if community_id else None,
        paper_count=10,
        year_start=year_start,
        year_end=year_end,
        access_state=access_state,
        lock_reason=(
            None
            if access_state == "accessible"
            else "Sign in as a member of Cambridge to unlock"
        ),
        metadata_schema=metadata_schema,
    )


@pytest.mark.anyio
async def test_get_collections_returns_listing_payload_for_anonymous() -> None:
    from src.main import create_app

    service = _FakeAccessService(
        listings=[
            _listing("public-demo", metadata_schema={"version": 1, "fields": []}),
            _listing(
                "cam-cs-tripos",
                community_id="c-cam",
                access_state="locked_requires_signin",
            ),
        ]
    )
    app = create_app(
        search_service=object(),
        access_service=service,
        auth_resolver=_FakeIdentityResolver(RequestIdentity.anonymous()),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/collections")

    assert response.status_code == 200
    payload = response.json()
    assert [row["name"] for row in payload] == ["public-demo", "cam-cs-tripos"]
    public, locked = payload
    assert public["access_state"] == "accessible"
    assert public["metadata_schema"] == {"version": 1, "fields": []}
    assert locked["access_state"] == "locked_requires_signin"
    assert locked["metadata_schema"] is None
    assert locked["community"] == {"id": "c-cam", "display_name": "Cambridge"}
    assert locked["lock_reason"].startswith("Sign in")


@pytest.mark.anyio
async def test_get_collections_passes_identity_through_to_service() -> None:
    from src.main import create_app

    service = _FakeAccessService(listings=[])
    identity = RequestIdentity(
        provider="clerk",
        external_subject="sub-1",
        email="a@cam.ac.uk",
        email_verified=True,
    )
    app = create_app(
        search_service=object(),
        access_service=service,
        auth_resolver=_FakeIdentityResolver(identity),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/collections")

    assert service.received_identity == identity


@pytest.mark.anyio
async def test_get_collections_returns_empty_list_when_no_collections() -> None:
    from src.main import create_app

    service = _FakeAccessService(listings=[])
    app = create_app(
        search_service=object(),
        access_service=service,
        auth_resolver=_FakeIdentityResolver(RequestIdentity.anonymous()),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/collections")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_get_collections_returns_403_when_identity_provisioning_fails() -> None:
    from src.main import create_app

    service = _FakeAccessService(
        listings=[],
        error=IdentityProvisioningError("verified email is required"),
    )
    app = create_app(
        search_service=object(),
        access_service=service,
        auth_resolver=_FakeIdentityResolver(RequestIdentity.anonymous()),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/collections")

    assert response.status_code == 403
    assert response.json() == {"detail": "verified email is required"}


@pytest.mark.anyio
async def test_get_collections_logs_usage_on_success() -> None:
    from src.main import create_app
    from src.runtime.usage_logs import RequestUsageLogRecord

    class _FakeUsageRepo:
        def __init__(self) -> None:
            self.records: list[RequestUsageLogRecord] = []

        def insert(self, record: RequestUsageLogRecord) -> None:
            self.records.append(record)

    usage_repo = _FakeUsageRepo()
    service = _FakeAccessService(listings=[])

    app = create_app(
        search_service=object(),
        access_service=service,
        auth_resolver=_FakeIdentityResolver(RequestIdentity.anonymous()),
        usage_log_repository=usage_repo,
        allow_unauthorized_test_mode=True,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/collections")

    assert response.status_code == 200
    assert len(usage_repo.records) == 1
    record = usage_repo.records[0]
    assert record.endpoint == "collections"
    assert record.outcome == "ok"
