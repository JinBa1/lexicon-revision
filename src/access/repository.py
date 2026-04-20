from __future__ import annotations

import uuid

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from src.access.models import AuthenticatedUser, CollectionAccess
from src.db.schema import collections, community_memberships, users


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized:
        raise ValueError("email must not be blank")
    return normalized


class PgCollectionAccessRepository:
    def __init__(self, *, engine: Engine) -> None:
        self.engine = engine

    def get_collection_access(
        self,
        collection_name: str,
    ) -> CollectionAccess | None:
        stmt = (
            select(
                collections.c.id,
                collections.c.name,
                collections.c.community_id,
            )
            .where(collections.c.name == collection_name)
            .limit(1)
        )
        with Session(self.engine) as session:
            row = session.execute(stmt).first()

        if row is None:
            return None

        return CollectionAccess(
            collection_id=str(row.id),
            collection_name=str(row.name),
            community_id=(
                str(row.community_id) if row.community_id is not None else None
            ),
        )

    def get_or_create_user(self, email: str) -> AuthenticatedUser:
        normalized_email = _normalize_email(email)

        stmt = (
            pg_insert(users)
            .values(
                id=str(uuid.uuid4()),
                email=normalized_email,
            )
            .on_conflict_do_nothing(index_elements=[users.c.email])
        )
        lookup_stmt = (
            select(users.c.id, users.c.email)
            .where(users.c.email == normalized_email)
            .limit(1)
        )

        with Session(self.engine) as session:
            session.execute(stmt)
            row = session.execute(lookup_stmt).one()
            session.commit()

        return AuthenticatedUser(
            user_id=str(row.id),
            email=str(row.email),
        )

    def has_active_membership(self, *, user_id: str, community_id: str) -> bool:
        stmt = (
            select(community_memberships.c.id)
            .where(
                community_memberships.c.user_id == user_id,
                community_memberships.c.community_id == community_id,
                community_memberships.c.status == "active",
            )
            .limit(1)
        )
        with Session(self.engine) as session:
            row = session.execute(stmt).first()
        return row is not None
