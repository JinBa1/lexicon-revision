from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from src.access.auth import STUB_EMAIL_IDENTITY_PROVIDER
from src.access.models import RequestIdentity
from src.access.repository import PgCollectionAccessRepository

pytestmark = pytest.mark.integration


def _engine():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for integration tests")
    return create_engine(database_url, future=True)


def _seed_collection(
    engine,
    *,
    name: str,
    community_id: str | None,
    metadata_schema: dict | None = None,
    paper_rows: int = 0,
    chunk_years: list[int] | None = None,
):
    schema = metadata_schema or {
        "version": 1,
        "fields": [
            {"key": "year", "label": "Year", "type": "integer", "operators": ["eq"]}
        ],
    }
    collection_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO collections "
                "(id, name, community_id, embedding_model_id, "
                "embedding_dimension, metadata_schema) "
                "VALUES (:id, :name, :cid, 'test-model', 3, CAST(:schema AS JSONB))"
            ),
            {
                "id": collection_id,
                "name": name,
                "cid": community_id,
                "schema": _json_dumps(schema),
            },
        )
        for idx in range(paper_rows):
            conn.execute(
                text(
                    "INSERT INTO papers (id, collection_id, source_pdf) "
                    "VALUES (:id, :cid, :pdf)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "cid": collection_id,
                    "pdf": f"paper_{idx}.pdf",
                },
            )
    if chunk_years:
        _seed_chunks_with_years(engine, collection_id=collection_id, years=chunk_years)
    return collection_id


def _seed_chunks_with_years(engine, *, collection_id: str, years: list[int]) -> None:
    with engine.begin() as conn:
        paper_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO papers (id, collection_id, source_pdf) "
                "VALUES (:id, :cid, 'year_paper.pdf')"
            ),
            {"id": paper_id, "cid": collection_id},
        )
        for idx, year in enumerate(years):
            conn.execute(
                text(
                    "INSERT INTO chunks "
                    "(id, chunk_id, collection_id, paper_id, chunk_level, text, "
                    "metadata, source_pdf) "
                    "VALUES (:id, :cid, :colid, :pid, 'question', 't', "
                    "CAST(:md AS JSONB), 'year_paper.pdf')"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "cid": f"chunk-{idx}",
                    "colid": collection_id,
                    "pid": paper_id,
                    "md": _json_dumps({"year": year}),
                },
            )


def _json_dumps(payload) -> str:
    import json

    return json.dumps(payload)


def _seed_community(engine, *, name: str, slug: str) -> str:
    community_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO communities (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": community_id, "name": name, "slug": slug},
        )
    return community_id


def _seed_membership(engine, *, user_email: str, community_id: str) -> str:
    user_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, email_verified) "
                "VALUES (:id, :email, TRUE)"
            ),
            {"id": user_id, "email": user_email},
        )
        conn.execute(
            text(
                "INSERT INTO community_memberships "
                "(id, user_id, community_id, role, status) "
                "VALUES (:id, :uid, :cid, 'member', 'active')"
            ),
            {
                "id": str(uuid.uuid4()),
                "uid": user_id,
                "cid": community_id,
            },
        )
    return user_id


def _stub_identity(email: str) -> RequestIdentity:
    return RequestIdentity(
        provider=STUB_EMAIL_IDENTITY_PROVIDER,
        external_subject=email,
        email=email,
        email_verified=False,
    )


def _clerk_identity(email: str) -> RequestIdentity:
    return RequestIdentity(
        provider="clerk",
        external_subject=f"user_{uuid.uuid4().hex}",
        email=email,
        email_verified=True,
    )


def test_list_collections_for_anonymous_marks_public_accessible_and_private_locked():
    engine = _engine()
    repository = PgCollectionAccessRepository(engine=engine)
    private_community_id = _seed_community(engine, name="Cambridge", slug="cambridge")
    _seed_collection(engine, name="a-public", community_id=None)
    _seed_collection(engine, name="b-private", community_id=private_community_id)

    rows = repository.list_collections_with_access(
        request_identity=RequestIdentity.anonymous(),
        resolved_user_id=None,
        affiliation_community_id=None,
    )

    assert [(row.collection_name, row.access_state) for row in rows] == [
        ("a-public", "accessible"),
        ("b-private", "locked_requires_signin"),
    ]
    assert rows[1].lock_reason is not None


def test_list_collections_for_authed_user_with_matching_affiliation_is_accessible():
    engine = _engine()
    repository = PgCollectionAccessRepository(engine=engine)
    cambridge_id = _seed_community(engine, name="Cambridge", slug="cambridge")
    _seed_collection(engine, name="cam-private", community_id=cambridge_id)
    user_id = _seed_membership(
        engine,
        user_email="person@cam.ac.uk",
        community_id=cambridge_id,
    )

    rows = repository.list_collections_with_access(
        request_identity=_clerk_identity("person@cam.ac.uk"),
        resolved_user_id=user_id,
        affiliation_community_id=cambridge_id,
    )

    assert len(rows) == 1
    assert rows[0].collection_name == "cam-private"
    assert rows[0].access_state == "accessible"
    assert rows[0].lock_reason is None
    assert rows[0].community_display_name == "Cambridge"


def test_list_collections_for_matching_affiliation_without_membership_is_locked():
    engine = _engine()
    repository = PgCollectionAccessRepository(engine=engine)
    cambridge_id = _seed_community(engine, name="Cambridge", slug="cambridge")
    _seed_collection(engine, name="cam-private", community_id=cambridge_id)

    rows = repository.list_collections_with_access(
        request_identity=_clerk_identity("person@cam.ac.uk"),
        resolved_user_id=str(uuid.uuid4()),
        affiliation_community_id=cambridge_id,
    )

    assert len(rows) == 1
    assert rows[0].access_state == "locked_wrong_affiliation"
    assert rows[0].lock_reason == "This collection is restricted to Cambridge members"


def test_list_collections_for_unsupported_affiliation_falls_back_to_locked() -> None:
    engine = _engine()
    repository = PgCollectionAccessRepository(engine=engine)
    cambridge_id = _seed_community(engine, name="Cambridge", slug="cambridge")
    _seed_collection(engine, name="cam-private", community_id=cambridge_id)

    rows = repository.list_collections_with_access(
        request_identity=_clerk_identity("person@example.com"),
        resolved_user_id=str(uuid.uuid4()),
        affiliation_community_id=None,
    )

    assert len(rows) == 1
    assert rows[0].access_state == "locked_wrong_affiliation"
    assert rows[0].lock_reason == "This collection is restricted to Cambridge members"


def test_list_collections_for_stub_identity_uses_membership_without_affiliation() -> (
    None
):
    engine = _engine()
    repository = PgCollectionAccessRepository(engine=engine)
    cambridge_id = _seed_community(engine, name="Cambridge", slug="cambridge")
    _seed_collection(engine, name="cam-private", community_id=cambridge_id)
    user_id = _seed_membership(
        engine,
        user_email="member@example.com",
        community_id=cambridge_id,
    )

    rows = repository.list_collections_with_access(
        request_identity=_stub_identity("member@example.com"),
        resolved_user_id=user_id,
        affiliation_community_id=None,
    )

    assert len(rows) == 1
    assert rows[0].access_state == "accessible"
    assert rows[0].lock_reason is None


def test_list_collections_uses_bulk_membership_lookup_instead_of_per_row_checks(
    monkeypatch,
):
    engine = _engine()
    repository = PgCollectionAccessRepository(engine=engine)
    cambridge_id = _seed_community(engine, name="Cambridge", slug="cambridge")
    _seed_collection(engine, name="cam-private-a", community_id=cambridge_id)
    _seed_collection(engine, name="cam-private-b", community_id=cambridge_id)
    user_id = _seed_membership(
        engine,
        user_email="member@example.com",
        community_id=cambridge_id,
    )

    def _unexpected_per_row_membership_check(
        *,
        user_id: str,
        community_id: str,
    ) -> bool:
        del user_id, community_id
        raise AssertionError(
            "list_collections_with_access should not use per-row membership checks"
        )

    monkeypatch.setattr(
        repository,
        "has_active_membership",
        _unexpected_per_row_membership_check,
    )

    rows = repository.list_collections_with_access(
        request_identity=_stub_identity("member@example.com"),
        resolved_user_id=user_id,
        affiliation_community_id=None,
    )

    assert [row.collection_name for row in rows] == [
        "cam-private-a",
        "cam-private-b",
    ]
    assert all(row.access_state == "accessible" for row in rows)


def test_list_collections_for_authed_user_with_wrong_affiliation_is_locked():
    engine = _engine()
    repository = PgCollectionAccessRepository(engine=engine)
    cambridge_id = _seed_community(engine, name="Cambridge", slug="cambridge")
    oxford_id = _seed_community(engine, name="Oxford", slug="oxford")
    _seed_collection(engine, name="ox-private", community_id=oxford_id)

    rows = repository.list_collections_with_access(
        request_identity=_clerk_identity("person@cam.ac.uk"),
        resolved_user_id=str(uuid.uuid4()),
        affiliation_community_id=cambridge_id,
    )

    assert len(rows) == 1
    assert rows[0].access_state == "locked_wrong_affiliation"
    assert rows[0].lock_reason == "This collection is restricted to Oxford members"


def test_list_collections_sorts_accessible_first_then_locked():
    engine = _engine()
    repository = PgCollectionAccessRepository(engine=engine)
    private_community_id = _seed_community(engine, name="Cambridge", slug="cambridge")
    _seed_collection(engine, name="c-public", community_id=None)
    _seed_collection(engine, name="a-private", community_id=private_community_id)
    _seed_collection(engine, name="b-public", community_id=None)

    rows = repository.list_collections_with_access(
        request_identity=RequestIdentity.anonymous(),
        resolved_user_id=None,
        affiliation_community_id=None,
    )

    assert [row.collection_name for row in rows] == [
        "b-public",
        "c-public",
        "a-private",
    ]


def test_list_collections_returns_paper_count_and_year_range():
    engine = _engine()
    repository = PgCollectionAccessRepository(engine=engine)
    _seed_collection(
        engine,
        name="algorithms-papers",
        community_id=None,
        chunk_years=[2018, 2020, 2025],
    )

    rows = repository.list_collections_with_access(
        request_identity=RequestIdentity.anonymous(),
        resolved_user_id=None,
        affiliation_community_id=None,
    )

    assert len(rows) == 1
    assert rows[0].paper_count == 1
    assert rows[0].year_start == 2018
    assert rows[0].year_end == 2025


def test_list_collections_omits_metadata_schema_for_locked_rows():
    engine = _engine()
    repository = PgCollectionAccessRepository(engine=engine)
    private_community_id = _seed_community(engine, name="Cambridge", slug="cambridge")
    _seed_collection(engine, name="cam-private", community_id=private_community_id)

    rows = repository.list_collections_with_access(
        request_identity=RequestIdentity.anonymous(),
        resolved_user_id=None,
        affiliation_community_id=None,
    )

    assert len(rows) == 1
    assert rows[0].metadata_schema is None


def test_list_collections_includes_metadata_schema_for_accessible_rows():
    engine = _engine()
    repository = PgCollectionAccessRepository(engine=engine)
    _seed_collection(engine, name="public-papers", community_id=None)

    rows = repository.list_collections_with_access(
        request_identity=RequestIdentity.anonymous(),
        resolved_user_id=None,
        affiliation_community_id=None,
    )

    assert len(rows) == 1
    assert isinstance(rows[0].metadata_schema, dict)
    assert rows[0].metadata_schema["version"] == 1


def test_list_collections_derives_display_name_from_collection_name():
    engine = _engine()
    repository = PgCollectionAccessRepository(engine=engine)
    _seed_collection(engine, name="algorithms-papers", community_id=None)

    rows = repository.list_collections_with_access(
        request_identity=RequestIdentity.anonymous(),
        resolved_user_id=None,
        affiliation_community_id=None,
    )

    assert len(rows) == 1
    assert rows[0].display_name == "Algorithms Papers"
