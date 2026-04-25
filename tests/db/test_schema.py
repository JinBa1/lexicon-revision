from __future__ import annotations

from sqlalchemy import CheckConstraint, Float, String
from sqlalchemy.dialects.postgresql import JSONB
from src.db.schema import (
    chunk_embeddings,
    chunks,
    collections,
    communities,
    community_memberships,
    metadata,
    papers,
    request_usage_logs,
    user_external_identities,
    users,
)


def test_schema_has_expected_tables() -> None:
    assert set(metadata.tables) == {
        "collections",
        "papers",
        "chunks",
        "chunk_embeddings",
        "users",
        "user_external_identities",
        "communities",
        "community_memberships",
        "community_email_domains",
        "manual_access_overrides",
        "request_usage_logs",
    }


def test_collections_embedding_columns() -> None:
    assert "embedding_model_id" in collections.c
    assert "embedding_dimension" in collections.c
    assert "metadata_schema" in collections.c
    assert "community_id" in collections.c
    assert "retrieval_vector_min_score" in collections.c
    assert "retrieval_rerank_min_score" in collections.c
    assert isinstance(collections.c.metadata_schema.type, JSONB)
    assert isinstance(collections.c.retrieval_vector_min_score.type, Float)
    assert isinstance(collections.c.retrieval_rerank_min_score.type, Float)
    assert collections.c.metadata_schema.server_default is None
    assert collections.c.community_id.nullable is True
    assert collections.c.retrieval_vector_min_score.nullable is True
    assert collections.c.retrieval_rerank_min_score.nullable is True

    foreign_keys = {
        fk.target_fullname for fk in collections.c.community_id.foreign_keys
    }
    assert foreign_keys == {"communities.id"}


def test_chunks_use_canonical_metadata_jsonb_column() -> None:
    assert "metadata" in chunks.c
    assert isinstance(chunks.c.metadata.type, JSONB)


def test_chunks_drop_legacy_filter_columns() -> None:
    for name in (
        "year",
        "paper",
        "question_number",
        "topic",
        "author",
        "tripos_part",
        "marks",
        "total_marks",
        "has_code",
        "has_figure",
        "has_table",
    ):
        assert name not in chunks.c


def test_chunks_use_internal_primary_key_with_collection_scoped_chunk_ids() -> None:
    pk_columns = {column.name for column in chunks.primary_key.columns}
    assert pk_columns == {"id"}

    unique_constraints = {
        constraint.name: {column.name for column in constraint.columns}
        for constraint in chunks.constraints
        if constraint.name is not None
    }
    assert unique_constraints["uq_chunks_collection_chunk_id"] == {
        "collection_id",
        "chunk_id",
    }


def test_chunk_embeddings_primary_key() -> None:
    pk_columns = {column.name for column in chunk_embeddings.primary_key.columns}
    assert pk_columns == {"chunk_id", "embedding_model_id"}


def test_chunk_embeddings_chunk_id_matches_chunks_id_type() -> None:
    assert type(chunk_embeddings.c.chunk_id.type) is String


def test_papers_unique_collection_source_pdf_constraint() -> None:
    constraints = {constraint.name for constraint in papers.constraints}
    assert "uq_papers_collection_source_pdf" in constraints


def test_users_email_is_unique() -> None:
    constraints = {constraint.name for constraint in users.constraints}
    assert "uq_users_email" in constraints
    assert "ck_users_email_lowercase" in constraints
    assert "email_verified" in users.c
    assert users.c.email_verified.nullable is False

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in users.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name is not None
    }
    assert checks["ck_users_email_lowercase"] == "email = lower(btrim(email))"


def test_request_usage_logs_has_expected_columns() -> None:
    assert {"request_id", "endpoint", "collection_name", "outcome", "latency_ms"} <= {
        column.name for column in request_usage_logs.columns
    }
    unique_constraints = {
        constraint.name: {column.name for column in constraint.columns}
        for constraint in request_usage_logs.constraints
        if constraint.name is not None
    }
    assert isinstance(request_usage_logs.c.embedding.type, JSONB)
    assert isinstance(request_usage_logs.c.rerank.type, JSONB)
    assert isinstance(request_usage_logs.c.planning.type, JSONB)
    assert isinstance(request_usage_logs.c.generation.type, JSONB)
    assert isinstance(request_usage_logs.c.detail.type, JSONB)
    assert request_usage_logs.c.app_user_id.nullable is True
    assert request_usage_logs.c.created_at.nullable is False
    assert unique_constraints["uq_request_usage_logs_request_id"] == {"request_id"}


def test_user_external_identities_are_unique_per_provider_subject() -> None:
    assert "provider" in user_external_identities.c
    assert "external_subject" in user_external_identities.c

    unique_constraints = {
        constraint.name: {column.name for column in constraint.columns}
        for constraint in user_external_identities.constraints
        if constraint.name is not None
    }
    assert unique_constraints["uq_user_external_identities_provider_subject"] == {
        "provider",
        "external_subject",
    }

    foreign_keys = {
        fk.target_fullname for fk in user_external_identities.c.user_id.foreign_keys
    }
    assert foreign_keys == {"users.id"}


def test_communities_name_is_unique() -> None:
    constraints = {constraint.name for constraint in communities.constraints}
    assert "uq_communities_name" in constraints
    assert "uq_communities_slug" in constraints


def test_communities_include_slug_column() -> None:
    assert "slug" in communities.c
    assert communities.c.slug.nullable is False


def test_community_memberships_are_unique_per_user_community_pair() -> None:
    assert "role" in community_memberships.c
    assert "status" in community_memberships.c

    constraints = {constraint.name for constraint in community_memberships.constraints}
    assert "ck_community_memberships_role_valid" in constraints
    assert "ck_community_memberships_status_valid" in constraints

    unique_constraints = {
        constraint.name: {column.name for column in constraint.columns}
        for constraint in community_memberships.constraints
        if constraint.name is not None
    }
    assert unique_constraints["uq_community_memberships_user_community"] == {
        "user_id",
        "community_id",
    }

    foreign_keys = {
        column.name: {fk.target_fullname for fk in column.foreign_keys}
        for column in (
            community_memberships.c.user_id,
            community_memberships.c.community_id,
        )
    }
    assert foreign_keys["user_id"] == {"users.id"}
    assert foreign_keys["community_id"] == {"communities.id"}

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in community_memberships.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name is not None
    }
    assert checks["ck_community_memberships_role_valid"] == (
        "role IN ('member', 'admin')"
    )
    assert checks["ck_community_memberships_status_valid"] == (
        "status IN ('active', 'inactive')"
    )
