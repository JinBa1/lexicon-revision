from __future__ import annotations

import importlib
import importlib.util
import os

import pytest
from sqlalchemy import create_engine, text
from src.access.errors import CollectionAccessDeniedError
from src.access.models import RequestIdentity
from src.access.service import CollectionAccessService
from src.search.errors import CollectionNotFoundError

pytestmark = pytest.mark.integration


def _engine():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for integration tests")
    return create_engine(database_url, future=True)


def _repository_module():
    spec = importlib.util.find_spec("src.access.repository")
    assert spec is not None, "src.access.repository module should exist"
    return importlib.import_module("src.access.repository")


def _repository(engine):
    module = _repository_module()
    return module.PgCollectionAccessRepository(engine=engine)


def test_get_or_create_user_for_stub_identity_reuses_existing_row() -> None:
    engine = _engine()
    repository = _repository(engine)

    first_user = repository.get_or_create_user_for_identity(
        RequestIdentity(
            provider="stub_header",
            external_subject="member@example.com",
            email="member@example.com",
            email_verified=False,
        )
    )
    second_user = repository.get_or_create_user_for_identity(
        RequestIdentity(
            provider="stub_header",
            external_subject="member@example.com",
            email="member@example.com",
            email_verified=False,
        )
    )

    assert first_user == second_user
    assert first_user.email == "member@example.com"

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select id, email, email_verified
                from users
                order by created_at asc
                """
            )
        ).all()
        linked_identities = conn.execute(
            text(
                """
                select provider, external_subject, user_id
                from user_external_identities
                order by created_at asc
                """
            )
        ).all()

    assert rows == [(first_user.user_id, "member@example.com", False)]
    assert linked_identities == [
        ("stub_header", "member@example.com", first_user.user_id)
    ]


def test_get_or_create_user_for_external_identity_reuses_provider_subject_mapping() -> (
    None
):
    engine = _engine()
    repository = _repository(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into users (id, email, email_verified)
                values ('user-1', 'member@example.com', true)
                """
            )
        )
        conn.execute(
            text(
                """
                insert into user_external_identities (
                    id,
                    user_id,
                    provider,
                    external_subject
                ) values (
                    'identity-1',
                    'user-1',
                    'clerk',
                    'user_123'
                )
                """
            )
        )

    user = repository.get_or_create_user_for_identity(
        RequestIdentity(
            provider="clerk",
            external_subject="user_123",
            email="member@example.com",
            email_verified=True,
        )
    )

    assert user.user_id == "user-1"
    assert user.email == "member@example.com"


def test_get_or_create_user_for_verified_external_identity_creates_new_mapping() -> (
    None
):
    engine = _engine()
    repository = _repository(engine)

    user = repository.get_or_create_user_for_identity(
        RequestIdentity(
            provider="clerk",
            external_subject="user_123",
            email="member@example.com",
            email_verified=True,
        )
    )

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select id, email, email_verified
                from users
                order by created_at asc
                """
            )
        ).all()
        linked_identities = conn.execute(
            text(
                """
                select provider, external_subject, user_id
                from user_external_identities
                order by created_at asc
                """
            )
        ).all()

    assert rows == [(user.user_id, "member@example.com", True)]
    assert linked_identities == [("clerk", "user_123", user.user_id)]


def test_verified_external_identity_rejects_email_collision() -> None:
    engine = _engine()
    repository = _repository(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into users (id, email, email_verified)
                values ('user-1', 'member@example.com', false)
                """
            )
        )

    with pytest.raises(ValueError, match="account linking"):
        repository.get_or_create_user_for_identity(
            RequestIdentity(
                provider="clerk",
                external_subject="user_123",
                email="member@example.com",
                email_verified=True,
            )
        )


def test_get_or_create_user_for_unverified_external_identity_fails_closed() -> None:
    engine = _engine()
    repository = _repository(engine)

    with pytest.raises(ValueError, match="verified email"):
        repository.get_or_create_user_for_identity(
            RequestIdentity(
                provider="clerk",
                external_subject="user_123",
                email="member@example.com",
                email_verified=False,
            )
        )


def test_partial_external_identity_fails_closed() -> None:
    engine = _engine()
    repository = _repository(engine)

    with pytest.raises(ValueError, match="provider and external_subject"):
        repository.get_or_create_user_for_identity(
            RequestIdentity(
                provider="clerk",
                external_subject=None,
                email="member@example.com",
                email_verified=True,
            )
        )


def test_get_collection_access_returns_public_collection_without_community() -> None:
    engine = _engine()
    repository = _repository(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into collections (
                    id,
                    name,
                    community_id,
                    embedding_model_id,
                    embedding_dimension,
                    metadata_schema
                ) values (
                    'collection-public',
                    'public-collection',
                    null,
                    'fake-v1',
                    8,
                    '{}'::jsonb
                )
                """
            )
        )

    collection = repository.get_collection_access("public-collection")

    assert collection is not None
    assert collection.collection_id == "collection-public"
    assert collection.collection_name == "public-collection"
    assert collection.community_id is None


def test_has_active_membership_rejects_inactive_membership() -> None:
    engine = _engine()
    repository = _repository(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into communities (id, name, slug)
                values ('community-1', 'Community One', 'community-one')
                """
            )
        )
        conn.execute(
            text(
                """
                insert into users (id, email)
                values ('user-1', 'member@example.com')
                """
            )
        )
        conn.execute(
            text(
                """
                insert into community_memberships (
                    id,
                    user_id,
                    community_id,
                    role,
                    status
                ) values (
                    'membership-1',
                    'user-1',
                    'community-1',
                    'member',
                    'inactive'
                )
                """
            )
        )

    assert not repository.has_active_membership(
        user_id="user-1",
        community_id="community-1",
    )


def test_service_allows_public_collection_without_header() -> None:
    engine = _engine()
    repository = _repository(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into collections (
                    id,
                    name,
                    community_id,
                    embedding_model_id,
                    embedding_dimension,
                    metadata_schema
                ) values (
                    'collection-public',
                    'public-collection',
                    null,
                    'fake-v1',
                    8,
                    '{}'::jsonb
                )
                """
            )
        )

    service = CollectionAccessService(repository=repository)

    context = service.authorize_collection(
        collection_name="public-collection",
        request_identity=RequestIdentity.anonymous(),
    )

    assert context.collection.collection_id == "collection-public"
    assert context.collection.collection_name == "public-collection"
    assert context.collection.community_id is None
    assert context.identity.email is None
    assert context.identity.user is None


def test_service_denies_anonymous_private_collection_without_header() -> None:
    engine = _engine()
    repository = _repository(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into communities (id, name, slug)
                values ('community-1', 'Community One', 'community-one')
                """
            )
        )
        conn.execute(
            text(
                """
                insert into collections (
                    id,
                    name,
                    community_id,
                    embedding_model_id,
                    embedding_dimension,
                    metadata_schema
                ) values (
                    'collection-1',
                    'private-collection',
                    'community-1',
                    'fake-v1',
                    8,
                    '{}'::jsonb
                )
                """
            )
        )

    service = CollectionAccessService(repository=repository)

    with pytest.raises(CollectionAccessDeniedError, match="private-collection"):
        service.authorize_collection(
            collection_name="private-collection",
            request_identity=RequestIdentity.anonymous(),
        )


def test_service_allows_active_membership_for_private_collection() -> None:
    engine = _engine()
    repository = _repository(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into communities (id, name, slug)
                values ('community-1', 'Community One', 'community-one')
                """
            )
        )
        conn.execute(
            text(
                """
                insert into users (id, email)
                values ('user-1', 'member@example.com')
                """
            )
        )
        conn.execute(
            text(
                """
                insert into community_memberships (
                    id,
                    user_id,
                    community_id,
                    role,
                    status
                ) values (
                    'membership-1',
                    'user-1',
                    'community-1',
                    'member',
                    'active'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                insert into collections (
                    id,
                    name,
                    community_id,
                    embedding_model_id,
                    embedding_dimension,
                    metadata_schema
                ) values (
                    'collection-1',
                    'private-collection',
                    'community-1',
                    'fake-v1',
                    8,
                    '{}'::jsonb
                )
                """
            )
        )

    service = CollectionAccessService(repository=repository)

    context = service.authorize_collection(
        collection_name="private-collection",
        request_identity=RequestIdentity(
            provider="stub_header",
            external_subject="member@example.com",
            email="member@example.com",
            email_verified=False,
        ),
    )

    assert context.collection.collection_id == "collection-1"
    assert context.collection.collection_name == "private-collection"
    assert context.collection.community_id == "community-1"
    assert context.identity.email == "member@example.com"
    assert context.identity.user is not None
    assert context.identity.user.user_id == "user-1"


def test_service_denies_wrong_user_for_private_collection() -> None:
    engine = _engine()
    repository = _repository(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into communities (id, name, slug)
                values ('community-1', 'Community One', 'community-one')
                """
            )
        )
        conn.execute(
            text(
                """
                insert into collections (
                    id,
                    name,
                    community_id,
                    embedding_model_id,
                    embedding_dimension,
                    metadata_schema
                ) values (
                    'collection-1',
                    'private-collection',
                    'community-1',
                    'fake-v1',
                    8,
                    '{}'::jsonb
                )
                """
            )
        )

    service = CollectionAccessService(repository=repository)

    with pytest.raises(CollectionAccessDeniedError, match="private-collection"):
        service.authorize_collection(
            collection_name="private-collection",
            request_identity=RequestIdentity(
                provider="stub_header",
                external_subject="other@example.com",
                email="other@example.com",
                email_verified=False,
            ),
        )


def test_service_returns_not_found_for_missing_collection() -> None:
    engine = _engine()
    repository = _repository(engine)
    service = CollectionAccessService(repository=repository)

    with pytest.raises(CollectionNotFoundError, match="missing-collection"):
        service.authorize_collection(
            collection_name="missing-collection",
            request_identity=RequestIdentity(
                provider="stub_header",
                external_subject="member@example.com",
                email="member@example.com",
                email_verified=False,
            ),
        )
