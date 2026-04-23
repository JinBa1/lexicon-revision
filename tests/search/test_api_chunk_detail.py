from __future__ import annotations

import httpx
import pytest
from src.access.errors import (
    CollectionAccessDeniedError,
    IdentityProvisioningError,
)
from src.access.models import (
    AuthorizationContext,
    CollectionAccess,
    RequestIdentity,
    ResolvedIdentity,
)
from src.search.errors import CollectionNotFoundError
from src.search.pg_repository import ChunkDetailRow, ChunkParentRow


class _FakeChunkRepo:
    def __init__(
        self,
        *,
        chunks: dict[tuple[str, str], ChunkDetailRow | None] | None = None,
        raise_missing: set[str] | None = None,
    ) -> None:
        self._chunks = chunks or {}
        self._raise_missing = raise_missing or set()

    def get_chunk_by_id(
        self, *, collection_name: str, chunk_id: str
    ) -> ChunkDetailRow | None:
        if collection_name in self._raise_missing:
            raise CollectionNotFoundError(collection_name)
        return self._chunks.get((collection_name, chunk_id))


class _FakeAccessServiceWithAuthorize:
    def __init__(
        self,
        *,
        allowed: bool = True,
        provisioning_error: str | None = None,
    ) -> None:
        self.allowed = allowed
        self.provisioning_error = provisioning_error

    def authorize_collection(
        self,
        *,
        collection_name: str,
        request_identity: RequestIdentity,
    ) -> AuthorizationContext:
        if self.provisioning_error is not None:
            raise IdentityProvisioningError(self.provisioning_error)
        if not self.allowed:
            raise CollectionAccessDeniedError(collection_name)
        return AuthorizationContext(
            collection=CollectionAccess(
                collection_id="col-id",
                collection_name=collection_name,
                community_id=None,
            ),
            identity=ResolvedIdentity(request_identity=request_identity, user=None),
        )


class _FakeIdentityResolver:
    def resolve_request_identity(self, request) -> RequestIdentity:
        return RequestIdentity.anonymous()


class _FakeSearchServiceWithMedia:
    def __init__(self, *, repo, media_map: dict[str, list[dict]]) -> None:
        self.search_repository = repo
        self._media_map = media_map

    def get_media_refs(self, *, collection: str, chunk_id: str) -> list[dict]:
        return list(self._media_map.get(chunk_id, []))


def _row() -> ChunkDetailRow:
    return ChunkDetailRow(
        chunk_id="q-1",
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        text="body",
        metadata={"year": 2022},
        parent=None,
    )


@pytest.mark.anyio
async def test_get_chunk_detail_returns_payload_when_accessible() -> None:
    from src.main import create_app

    repo = _FakeChunkRepo(chunks={("demo", "q-1"): _row()})

    class _Service:
        search_repository = repo

    app = create_app(
        search_service=_Service(),
        access_service=_FakeAccessServiceWithAuthorize(allowed=True),
        auth_resolver=_FakeIdentityResolver(),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/collections/demo/chunks/q-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["chunk_id"] == "q-1"
    assert payload["collection"] == "demo"
    assert payload["metadata"] == {"year": 2022}
    assert payload["parent"] is None
    assert payload["media"] == []


@pytest.mark.anyio
async def test_get_chunk_detail_returns_parent_context_for_sub_question() -> None:
    from src.main import create_app

    sub_row = ChunkDetailRow(
        chunk_id="q-1-a",
        chunk_level="sub_question",
        parent_chunk_id="q-1",
        sub_question_label="(a)",
        text="sub",
        metadata={"year": 2022},
        parent=ChunkParentRow(text="parent", metadata={"year": 2022}),
    )
    repo = _FakeChunkRepo(chunks={("demo", "q-1-a"): sub_row})

    class _Service:
        search_repository = repo

    app = create_app(
        search_service=_Service(),
        access_service=_FakeAccessServiceWithAuthorize(allowed=True),
        auth_resolver=_FakeIdentityResolver(),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/collections/demo/chunks/q-1-a")

    assert response.status_code == 200
    payload = response.json()
    assert payload["parent"]["text"] == "parent"
    assert payload["parent_chunk_id"] == "q-1"
    assert payload["sub_question_label"] == "(a)"


@pytest.mark.anyio
async def test_get_chunk_detail_returns_media_refs_with_presigned_urls() -> None:
    from src.main import create_app

    row = ChunkDetailRow(
        chunk_id="q-1",
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        text="t",
        metadata={},
        parent=None,
    )
    repo = _FakeChunkRepo(chunks={("demo", "q-1"): row})
    service = _FakeSearchServiceWithMedia(
        repo=repo,
        media_map={
            "q-1": [
                {
                    "media_id": "fig1",
                    "kind": "image",
                    "object_key": "artifacts/demo/fig1.png",
                    "relation": "direct",
                }
            ]
        },
    )

    class _FakeStorage:
        def presign_get(self, key, *, expires_in_seconds):
            class _P:
                url = f"https://signed/{key}?exp={expires_in_seconds}"

            return _P()

    app = create_app(
        search_service=service,
        access_service=_FakeAccessServiceWithAuthorize(allowed=True),
        auth_resolver=_FakeIdentityResolver(),
        object_storage=_FakeStorage(),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/collections/demo/chunks/q-1")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["media"]) == 1
    media = payload["media"][0]
    assert media["media_id"] == "fig1"
    assert media["kind"] == "image"
    assert media["object_key"] == "artifacts/demo/fig1.png"
    assert media["access_url"].startswith("https://signed/")


@pytest.mark.anyio
async def test_get_chunk_detail_returns_404_when_chunk_missing() -> None:
    from src.main import create_app

    repo = _FakeChunkRepo(chunks={})

    class _Service:
        search_repository = repo

    app = create_app(
        search_service=_Service(),
        access_service=_FakeAccessServiceWithAuthorize(allowed=True),
        auth_resolver=_FakeIdentityResolver(),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/collections/demo/chunks/missing")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_get_chunk_detail_returns_404_when_collection_missing() -> None:
    from src.main import create_app

    repo = _FakeChunkRepo(raise_missing={"nope"})

    class _Service:
        search_repository = repo

    app = create_app(
        search_service=_Service(),
        access_service=_FakeAccessServiceWithAuthorize(allowed=True),
        auth_resolver=_FakeIdentityResolver(),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/collections/nope/chunks/q-1")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_get_chunk_detail_returns_403_when_collection_access_denied() -> None:
    from src.main import create_app

    repo = _FakeChunkRepo(chunks={("demo", "q-1"): _row()})

    class _Service:
        search_repository = repo

    app = create_app(
        search_service=_Service(),
        access_service=_FakeAccessServiceWithAuthorize(allowed=False),
        auth_resolver=_FakeIdentityResolver(),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/collections/demo/chunks/q-1")

    assert response.status_code == 403


@pytest.mark.anyio
async def test_get_chunk_detail_returns_403_when_identity_provisioning_fails() -> None:
    from src.main import create_app

    repo = _FakeChunkRepo(chunks={("demo", "q-1"): _row()})

    class _Service:
        search_repository = repo

    app = create_app(
        search_service=_Service(),
        access_service=_FakeAccessServiceWithAuthorize(
            provisioning_error="verified email is required"
        ),
        auth_resolver=_FakeIdentityResolver(),
        allow_unauthorized_test_mode=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/collections/demo/chunks/q-1")

    assert response.status_code == 403
