from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from src.metadata_schema import default_schema_path, load_collection_schema

pytestmark = pytest.mark.integration


def _expected_legacy_schema() -> dict:
    return load_collection_schema(
        default_schema_path("cam-cs-tripos-fixture")
    ).model_dump(mode="json")


def test_alembic_upgrade_creates_retrieval_tables() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for pgvector integration tests")

    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    engine = create_engine(database_url, future=True)
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        assert {"collections", "papers", "chunks", "chunk_embeddings"} <= tables
        result = conn.execute(
            text("select 1 from pg_extension where extname = 'vector'")
        ).first()
        assert result is not None


def test_alembic_cutover_backfills_metadata_and_drops_legacy_columns() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for pgvector integration tests")

    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.downgrade(config, "base")
    command.upgrade(config, "20260418_0001")

    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into collections (
                        id, name, embedding_model_id, embedding_dimension
                    ) values (
                        'collection-1', 'fixture-migration', 'fake-v1', 8
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    insert into papers (id, collection_id, source_pdf)
                    values ('paper-1', 'collection-1', '2025_paper_1.pdf')
                    """
                )
            )
            conn.execute(
                text(
                    """
                    insert into chunks (
                        id,
                        chunk_id,
                        collection_id,
                        paper_id,
                        chunk_level,
                        parent_chunk_id,
                        sub_question_label,
                        text,
                        year,
                        paper,
                        question_number,
                        topic,
                        author,
                        tripos_part,
                        marks,
                        total_marks,
                        has_code,
                        has_figure,
                        has_table,
                        source_pdf
                    ) values (
                        'chunk-1',
                        'cam-2025-p1-q1',
                        'collection-1',
                        'paper-1',
                        'question',
                        null,
                        null,
                        'Test text',
                        2025,
                        1,
                        1,
                        'Algorithms',
                        'abc123',
                        'Part IB',
                        10,
                        20,
                        true,
                        false,
                        false,
                        '2025_paper_1.pdf'
                    )
                    """
                )
            )

        command.upgrade(config, "20260419_0002")

        with engine.connect() as conn:
            columns_after_cutover = {
                column["name"] for column in inspect(conn).get_columns("chunks")
            }
            collection_columns = {
                column["name"] for column in inspect(conn).get_columns("collections")
            }
            collection_column_defaults = {
                column["name"]: column["default"]
                for column in inspect(conn).get_columns("collections")
            }
            backfilled = conn.execute(
                text(
                    """
                    select metadata, metadata_schema
                    from chunks
                    join collections on chunks.collection_id = collections.id
                    where chunks.id = 'chunk-1'
                    """
                )
            ).first()

        assert "metadata" in columns_after_cutover
        assert "year" in columns_after_cutover
        assert "metadata_schema" in collection_columns
        assert collection_column_defaults["metadata_schema"] is None
        assert backfilled is not None
        assert backfilled.metadata == {
            "year": 2025,
            "paper": 1,
            "question_number": 1,
            "topic": "Algorithms",
            "author": "abc123",
            "tripos_part": "Part IB",
            "marks": 10,
            "total_marks": 20,
            "has_code": True,
            "has_figure": False,
            "has_table": False,
        }
        assert backfilled.metadata_schema == _expected_legacy_schema()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            final_columns = {
                column["name"] for column in inspect(conn).get_columns("chunks")
            }
            final_collection_column_defaults = {
                column["name"]: column["default"]
                for column in inspect(conn).get_columns("collections")
            }
            final_row = conn.execute(
                text("select metadata from chunks where id = 'chunk-1'")
            ).first()

        assert "metadata" in final_columns
        assert "year" not in final_columns
        assert "paper" not in final_columns
        assert final_collection_column_defaults["metadata_schema"] is None
        assert final_row is not None
        assert final_row.metadata["topic"] == "Algorithms"
    finally:
        command.upgrade(config, "head")
        engine.dispose()


def test_alembic_access_model_upgrade_adds_public_private_collection_shape() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for pgvector integration tests")

    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.downgrade(config, "base")
    command.upgrade(config, "20260419_0003")

    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into collections (
                        id,
                        name,
                        embedding_model_id,
                        embedding_dimension,
                        metadata_schema
                    ) values (
                        'collection-public',
                        'fixture-public',
                        'fake-v1',
                        8,
                        '{}'::jsonb
                    )
                    """
                )
            )

        command.upgrade(config, "head")

        with engine.connect() as conn:
            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            collection_columns = {
                column["name"] for column in inspector.get_columns("collections")
            }
            community_columns = {
                column["name"] for column in inspector.get_columns("communities")
            }
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            external_identity_columns = {
                column["name"]
                for column in inspector.get_columns("user_external_identities")
            }
            community_unique_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("communities")
            }
            external_identity_unique_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints(
                    "user_external_identities"
                )
            }
            user_check_constraints = {
                constraint["name"]
                for constraint in inspector.get_check_constraints("users")
            }
            membership_check_constraints = {
                constraint["name"]
                for constraint in inspector.get_check_constraints(
                    "community_memberships"
                )
            }
            collection_row = conn.execute(
                text(
                    """
                    select id, community_id
                    from collections
                    where id = 'collection-public'
                    """
                )
            ).first()

        assert {
            "users",
            "user_external_identities",
            "communities",
            "community_memberships",
        } <= tables
        assert "community_id" in collection_columns
        assert "slug" in community_columns
        assert "email_verified" in user_columns
        assert {"provider", "external_subject", "user_id"} <= external_identity_columns
        assert "uq_communities_slug" in community_unique_constraints
        assert (
            "uq_user_external_identities_provider_subject"
            in external_identity_unique_constraints
        )
        assert "ck_users_email_lowercase" in user_check_constraints
        assert "ck_community_memberships_role_valid" in membership_check_constraints
        assert "ck_community_memberships_status_valid" in membership_check_constraints
        assert collection_row is not None
        assert collection_row.id == "collection-public"
        assert collection_row.community_id is None

        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        insert into users (id, email)
                        values ('user-mixed-case', 'MixedCase@Example.com')
                        """
                    )
                )
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        insert into users (id, email)
                        values ('user-spaced', ' member@example.com ')
                        """
                    )
                )
    finally:
        command.upgrade(config, "head")
        engine.dispose()


def test_alembic_upgrade_from_0005_adds_request_usage_logs_table() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for pgvector integration tests")

    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "20260420_0005")

    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as conn:
            inspector = inspect(conn)
            tables_before = set(inspector.get_table_names())

        assert "request_usage_logs" not in tables_before

        command.upgrade(config, "20260421_0006")

        with engine.connect() as conn:
            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            columns = {
                column["name"]: column
                for column in inspector.get_columns("request_usage_logs")
            }
            unique_constraints = {
                constraint["name"]: set(constraint["column_names"])
                for constraint in inspector.get_unique_constraints("request_usage_logs")
            }

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into request_usage_logs (
                        id,
                        request_id,
                        endpoint,
                        collection_name,
                        app_user_id,
                        outcome,
                        latency_ms,
                        detail
                    ) values (
                        'usage-log-1',
                        'req-migration-1',
                        'search',
                        'fixture-public',
                        null,
                        'ok',
                        10,
                        '{}'::jsonb
                    )
                    """
                )
            )

        assert "request_usage_logs" in tables
        assert {"embedding", "rerank", "planning", "generation", "detail"} <= set(
            columns
        )
        assert isinstance(columns["embedding"]["type"], JSONB)
        assert isinstance(columns["rerank"]["type"], JSONB)
        assert isinstance(columns["planning"]["type"], JSONB)
        assert isinstance(columns["generation"]["type"], JSONB)
        assert isinstance(columns["detail"]["type"], JSONB)
        assert columns["created_at"]["nullable"] is False
        assert unique_constraints["uq_request_usage_logs_request_id"] == {"request_id"}

        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        insert into request_usage_logs (
                            id,
                            request_id,
                            endpoint,
                            collection_name,
                            app_user_id,
                            outcome,
                            latency_ms,
                            detail
                        ) values (
                            'usage-log-2',
                            'req-migration-1',
                            'study',
                            'fixture-public',
                            null,
                            'provider_error',
                            12,
                            '{}'::jsonb
                        )
                        """
                    )
                )
    finally:
        command.upgrade(config, "head")
        engine.dispose()


def test_alembic_upgrade_from_0006_adds_auth_domain_gating_tables() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for pgvector integration tests")

    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "20260421_0006")

    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as conn:
            inspector = inspect(conn)
            tables_before = set(inspector.get_table_names())

        assert "community_email_domains" not in tables_before
        assert "manual_access_overrides" not in tables_before

        command.upgrade(config, "head")

        with engine.connect() as conn:
            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            community_email_domain_columns = {
                column["name"]
                for column in inspector.get_columns("community_email_domains")
            }
            manual_access_override_columns = {
                column["name"]
                for column in inspector.get_columns("manual_access_overrides")
            }
            community_email_domain_unique_constraints = {
                constraint["name"]: set(constraint["column_names"])
                for constraint in inspector.get_unique_constraints(
                    "community_email_domains"
                )
            }
            community_email_domain_check_constraints = {
                constraint["name"]
                for constraint in inspector.get_check_constraints(
                    "community_email_domains"
                )
            }
            manual_access_override_check_constraints = {
                constraint["name"]
                for constraint in inspector.get_check_constraints(
                    "manual_access_overrides"
                )
            }
            manual_access_override_active_email_index = conn.execute(
                text(
                    """
                    select indexdef
                    from pg_indexes
                    where schemaname = current_schema()
                      and tablename = 'manual_access_overrides'
                      and indexname = 'uq_manual_access_overrides_active_email'
                    """
                )
            ).scalar_one()

        assert {"community_email_domains", "manual_access_overrides"} <= tables
        assert {
            "community_id",
            "domain",
            "match_mode",
            "is_active",
        } <= community_email_domain_columns
        assert {
            "email",
            "community_id",
            "is_active",
            "expires_at",
        } <= manual_access_override_columns
        assert community_email_domain_unique_constraints[
            "uq_community_email_domains_community_domain"
        ] == {"community_id", "domain"}
        assert (
            "ck_community_email_domains_match_mode_valid"
            in community_email_domain_check_constraints
        )
        assert (
            "ck_community_email_domains_domain_lowercase"
            in community_email_domain_check_constraints
        )
        assert (
            "ck_manual_access_overrides_email_lowercase"
            in manual_access_override_check_constraints
        )
        assert "CREATE UNIQUE INDEX" in manual_access_override_active_email_index
        assert (
            "ON public.manual_access_overrides USING btree (email)"
            in manual_access_override_active_email_index
        )
        assert "WHERE is_active" in manual_access_override_active_email_index

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into communities (id, name, slug)
                    values
                        (
                            'community-domain-1',
                            'Community Domain 1',
                            'community-domain-1'
                        ),
                        (
                            'community-domain-2',
                            'Community Domain 2',
                            'community-domain-2'
                        )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    insert into manual_access_overrides (
                        id,
                        email,
                        community_id,
                        note,
                        is_active
                    ) values (
                        'manual-override-active-1',
                        'member@example.com',
                        'community-domain-1',
                        'active access',
                        true
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    insert into manual_access_overrides (
                        id,
                        email,
                        community_id,
                        note,
                        is_active
                    ) values (
                        'manual-override-inactive-1',
                        'member@example.com',
                        'community-domain-2',
                        'inactive duplicate allowed',
                        false
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    insert into community_email_domains (
                        id,
                        community_id,
                        domain,
                        match_mode,
                        is_active
                    ) values (
                        'community-domain-rule-1',
                        'community-domain-1',
                        'example.edu',
                        'suffix',
                        true
                    )
                    """
                )
            )

        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        insert into manual_access_overrides (
                            id,
                            email,
                            community_id,
                            note,
                            is_active
                        ) values (
                            'manual-override-active-2',
                            'member@example.com',
                            'community-domain-2',
                            'second active duplicate should fail',
                            true
                        )
                        """
                    )
                )

        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        insert into manual_access_overrides (
                            id,
                            email,
                            community_id,
                            note,
                            is_active
                        ) values (
                            'manual-override-invalid-email',
                            'Member@Example.com',
                            'community-domain-1',
                            'mixed-case email should fail',
                            true
                        )
                        """
                    )
                )

        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        insert into community_email_domains (
                            id,
                            community_id,
                            domain,
                            match_mode,
                            is_active
                        ) values (
                            'community-domain-rule-invalid',
                            'community-domain-1',
                            'Example.edu',
                            'prefix',
                            true
                        )
                        """
                    )
                )
    finally:
        command.upgrade(config, "head")
        engine.dispose()


def test_alembic_0008_adds_collection_retrieval_thresholds() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for pgvector integration tests")

    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "20260422_0007")

    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as conn:
            inspector = inspect(conn)
            columns_before = {
                column["name"] for column in inspector.get_columns("collections")
            }

        assert "retrieval_vector_min_score" not in columns_before
        assert "retrieval_rerank_min_score" not in columns_before

        command.upgrade(config, "head")

        with engine.connect() as conn:
            inspector = inspect(conn)
            columns = {
                column["name"]: column
                for column in inspector.get_columns("collections")
            }

        assert columns["retrieval_vector_min_score"]["nullable"] is True
        assert columns["retrieval_rerank_min_score"]["nullable"] is True
    finally:
        engine.dispose()
