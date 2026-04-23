from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from src.access.repository import PgCollectionAccessRepository

pytestmark = pytest.mark.integration


def _engine():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for integration tests")
    return create_engine(database_url, future=True)


def _seed_community(engine, *, name: str, slug: str, domains: list[tuple[str, str]]):
    community_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO communities (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": community_id, "name": name, "slug": slug},
        )
        for domain, match_mode in domains:
            conn.execute(
                text(
                    "INSERT INTO community_email_domains "
                    "(id, community_id, domain, match_mode, is_active) "
                    "VALUES (:id, :cid, :d, :m, TRUE)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "cid": community_id,
                    "d": domain,
                    "m": match_mode,
                },
            )
    return community_id


def test_list_supported_universities_returns_active_domains_grouped_by_community():
    engine = _engine()
    repo = PgCollectionAccessRepository(engine=engine)

    cam_id = _seed_community(
        engine,
        name="Cambridge",
        slug="cam",
        domains=[("cam.ac.uk", "exact"), ("cambridge.ac.uk", "exact")],
    )
    _seed_community(
        engine,
        name="Oxford",
        slug="ox",
        domains=[("ox.ac.uk", "exact")],
    )

    result = repo.list_supported_universities()

    by_name = {row.display_name: row for row in result}
    assert "Cambridge" in by_name
    assert by_name["Cambridge"].community_id == cam_id
    assert sorted(by_name["Cambridge"].email_domains) == [
        "cam.ac.uk",
        "cambridge.ac.uk",
    ]
    assert by_name["Oxford"].email_domains == ("ox.ac.uk",)


def test_list_supported_universities_excludes_communities_without_active_domains():
    engine = _engine()
    repo = PgCollectionAccessRepository(engine=engine)

    _seed_community(
        engine,
        name="Cambridge",
        slug="cam",
        domains=[("cam.ac.uk", "exact")],
    )
    empty_community_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO communities (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": empty_community_id, "name": "NoDomain", "slug": "nod"},
        )

    result = repo.list_supported_universities()
    names = {row.display_name for row in result}
    assert "NoDomain" not in names
    assert "Cambridge" in names


def test_list_supported_universities_excludes_inactive_domains():
    engine = _engine()
    repo = PgCollectionAccessRepository(engine=engine)

    community_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO communities (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": community_id, "name": "MixedCam", "slug": "mcam"},
        )
        conn.execute(
            text(
                "INSERT INTO community_email_domains "
                "(id, community_id, domain, match_mode, is_active) "
                "VALUES (:id, :cid, :d, 'exact', TRUE)"
            ),
            {"id": str(uuid.uuid4()), "cid": community_id, "d": "active.ac.uk"},
        )
        conn.execute(
            text(
                "INSERT INTO community_email_domains "
                "(id, community_id, domain, match_mode, is_active) "
                "VALUES (:id, :cid, :d, 'exact', FALSE)"
            ),
            {"id": str(uuid.uuid4()), "cid": community_id, "d": "dormant.ac.uk"},
        )

    result = repo.list_supported_universities()
    cam_row = next(row for row in result if row.display_name == "MixedCam")
    assert cam_row.email_domains == ("active.ac.uk",)
