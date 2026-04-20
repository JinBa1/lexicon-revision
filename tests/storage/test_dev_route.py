from __future__ import annotations

import httpx
import pytest
from src.main import create_app
from src.storage.local import LocalObjectStorage

SECRET = b"dev-route-secret"


class _FakeSearchService:
    embedding_model_id = "fake"
    rerank_model_id = None

    def search(
        self,
        query,
        collection="cam-cs-tripos",
        filters=None,
        limit=10,
        rerank=True,
    ):
        del filters, limit, rerank
        from src.search.models import SearchResponse

        return SearchResponse(query=query, collection=collection, results=[], total=0)


@pytest.mark.anyio
async def test_dev_object_route_serves_local_presigned_get(tmp_path) -> None:
    storage = LocalObjectStorage(
        root=tmp_path / "object-store",
        dev_presign_secret=SECRET,
    )
    storage.put_bytes(
        key="artifacts/mineru/run-1/images/figure_1.png",
        data=b"png",
        content_type="image/png",
    )
    app = create_app(
        search_service=_FakeSearchService(),
        object_storage=storage,
        allow_unauthorized_test_mode=True,
    )
    presigned = storage.presign_get(
        "artifacts/mineru/run-1/images/figure_1.png",
        expires_in_seconds=60,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost:8000",
    ) as client:
        response = await client.get(presigned.url)

    assert response.status_code == 200
    assert response.content == b"png"


@pytest.mark.anyio
async def test_dev_object_route_rejects_bad_signature(tmp_path) -> None:
    storage = LocalObjectStorage(
        root=tmp_path / "object-store",
        dev_presign_secret=SECRET,
    )
    app = create_app(
        search_service=_FakeSearchService(),
        object_storage=storage,
        allow_unauthorized_test_mode=True,
    )
    bad_url = (
        "http://localhost:8000/_dev/object/GET/9999999999/"
        + "0" * 32
        + "/artifacts/mineru/run-1/images/figure_1.png"
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost:8000",
    ) as client:
        response = await client.get(bad_url)

    assert response.status_code == 403
