from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column("email", Text, nullable=False),
    Column(
        "email_verified",
        Boolean,
        nullable=False,
        server_default=sql_text("false"),
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(
        "email = lower(btrim(email))",
        name="ck_users_email_lowercase",
    ),
    UniqueConstraint("email", name="uq_users_email"),
)

user_external_identities = Table(
    "user_external_identities",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column("user_id", String, ForeignKey("users.id"), nullable=False),
    Column("provider", Text, nullable=False),
    Column("external_subject", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint(
        "provider",
        "external_subject",
        name="uq_user_external_identities_provider_subject",
    ),
)

communities = Table(
    "communities",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column("name", Text, nullable=False),
    Column("slug", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint("name", name="uq_communities_name"),
    UniqueConstraint("slug", name="uq_communities_slug"),
)

community_memberships = Table(
    "community_memberships",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id"),
        nullable=False,
    ),
    Column(
        "community_id",
        String,
        ForeignKey("communities.id"),
        nullable=False,
    ),
    Column("role", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(
        "role IN ('member', 'admin')",
        name="ck_community_memberships_role_valid",
    ),
    CheckConstraint(
        "status IN ('active', 'inactive')",
        name="ck_community_memberships_status_valid",
    ),
    UniqueConstraint(
        "user_id",
        "community_id",
        name="uq_community_memberships_user_community",
    ),
)

community_email_domains = Table(
    "community_email_domains",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column(
        "community_id",
        String,
        ForeignKey("communities.id"),
        nullable=False,
    ),
    Column("domain", Text, nullable=False),
    Column("match_mode", Text, nullable=False),
    Column(
        "is_active",
        Boolean,
        nullable=False,
        server_default=sql_text("true"),
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(
        "domain = lower(btrim(domain))",
        name="ck_community_email_domains_domain_lowercase",
    ),
    CheckConstraint(
        "match_mode IN ('exact', 'suffix')",
        name="ck_community_email_domains_match_mode_valid",
    ),
    UniqueConstraint(
        "community_id",
        "domain",
        name="uq_community_email_domains_community_domain",
    ),
)

manual_access_overrides = Table(
    "manual_access_overrides",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column("email", Text, nullable=False),
    Column(
        "community_id",
        String,
        ForeignKey("communities.id"),
        nullable=False,
    ),
    Column("note", Text, nullable=True),
    Column(
        "is_active",
        Boolean,
        nullable=False,
        server_default=sql_text("true"),
    ),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(
        "email = lower(btrim(email))",
        name="ck_manual_access_overrides_email_lowercase",
    ),
    Index(
        "uq_manual_access_overrides_active_email",
        "email",
        unique=True,
        postgresql_where=sql_text("is_active"),
    ),
)

collections = Table(
    "collections",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column("name", Text, nullable=False, unique=True),
    Column("community_id", String, ForeignKey("communities.id"), nullable=True),
    Column("embedding_model_id", Text, nullable=False),
    Column("embedding_dimension", Integer, nullable=False),
    Column(
        "metadata_schema",
        JSONB,
        nullable=False,
    ),
    Column("retrieval_vector_min_score", Float, nullable=True),
    Column("retrieval_rerank_min_score", Float, nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint(
        "embedding_dimension > 0",
        name="ck_collections_embedding_dimension_positive",
    ),
)

papers = Table(
    "papers",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column(
        "collection_id",
        String,
        ForeignKey("collections.id"),
        nullable=False,
    ),
    Column("source_pdf", Text, nullable=False),
    Column("title", Text, nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint(
        "collection_id",
        "source_pdf",
        name="uq_papers_collection_source_pdf",
    ),
)

chunks = Table(
    "chunks",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column("chunk_id", Text, nullable=False),
    Column(
        "collection_id",
        String,
        ForeignKey("collections.id"),
        nullable=False,
    ),
    Column("paper_id", String, ForeignKey("papers.id"), nullable=False),
    Column("chunk_level", Text, nullable=False),
    Column("parent_chunk_id", Text, nullable=True),
    Column("sub_question_label", Text, nullable=True),
    Column("text", Text, nullable=False),
    Column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=sql_text("'{}'::jsonb"),
    ),
    Column("render_blocks", JSONB, nullable=True),
    Column("source_pdf", Text, nullable=False),
    UniqueConstraint(
        "collection_id",
        "chunk_id",
        name="uq_chunks_collection_chunk_id",
    ),
)

chunk_embeddings = Table(
    "chunk_embeddings",
    metadata,
    Column(
        "chunk_id",
        String,
        ForeignKey("chunks.id"),
        nullable=False,
    ),
    Column("embedding_model_id", Text, nullable=False),
    # Column is unsized so collections with different embedding dimensions can
    # coexist; the canonical dimension lives in collections.embedding_dimension
    # and is enforced by the indexing/search paths.
    Column("embedding", Vector(), nullable=False),
    PrimaryKeyConstraint("chunk_id", "embedding_model_id"),
)

request_usage_logs = Table(
    "request_usage_logs",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column("request_id", Text, nullable=False),
    Column("endpoint", Text, nullable=False),
    Column("collection_name", Text, nullable=False),
    Column("app_user_id", String, ForeignKey("users.id"), nullable=True),
    Column("outcome", Text, nullable=False),
    Column("latency_ms", Integer, nullable=False),
    Column("embedding", JSONB, nullable=True),
    Column("rerank", JSONB, nullable=True),
    Column("planning", JSONB, nullable=True),
    Column("generation", JSONB, nullable=True),
    Column(
        "detail",
        JSONB,
        nullable=False,
        server_default=sql_text("'{}'::jsonb"),
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint("request_id", name="uq_request_usage_logs_request_id"),
)
