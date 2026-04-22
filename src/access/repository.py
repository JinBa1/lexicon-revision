from __future__ import annotations

import uuid

from sqlalchemy import Engine, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from src.access.affiliation import CommunityDomainMatch, ManualAccessOverride
from src.access.auth import STUB_EMAIL_IDENTITY_PROVIDER
from src.access.email import email_domain, require_normalized_email
from src.access.models import AuthenticatedUser, CollectionAccess, RequestIdentity
from src.db.schema import (
    collections,
    community_email_domains,
    community_memberships,
    manual_access_overrides,
    user_external_identities,
    users,
)


class PgCollectionAccessRepository:
    def __init__(self, *, engine: Engine) -> None:
        self.engine = engine

    def get_manual_access_override(self, email: str) -> ManualAccessOverride | None:
        normalized_email = require_normalized_email(email)
        stmt = (
            select(
                manual_access_overrides.c.email,
                manual_access_overrides.c.community_id,
                manual_access_overrides.c.note,
            )
            .where(
                manual_access_overrides.c.email == normalized_email,
                manual_access_overrides.c.is_active.is_(True),
                (
                    manual_access_overrides.c.expires_at.is_(None)
                    | (manual_access_overrides.c.expires_at > text("now()"))
                ),
            )
            .limit(1)
        )
        with Session(self.engine) as session:
            row = session.execute(stmt).first()

        if row is None:
            return None

        return ManualAccessOverride(
            email=str(row.email),
            community_id=str(row.community_id),
            note=row.note,
        )

    def list_matching_communities_for_email_domain(
        self, email: str
    ) -> list[CommunityDomainMatch]:
        normalized_domain = email_domain(email)
        stmt = select(
            community_email_domains.c.community_id,
            community_email_domains.c.domain,
            community_email_domains.c.match_mode,
        ).where(community_email_domains.c.is_active.is_(True))
        with Session(self.engine) as session:
            rows = session.execute(stmt).all()

        matches: list[CommunityDomainMatch] = []
        for row in rows:
            if self._domain_rule_matches(
                email_domain=normalized_domain,
                rule_domain=str(row.domain),
                match_mode=str(row.match_mode),
            ):
                matches.append(
                    CommunityDomainMatch(
                        community_id=str(row.community_id),
                        domain=str(row.domain),
                        match_mode=str(row.match_mode),
                    )
                )
        return matches

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

    def get_or_create_user_for_identity(
        self,
        identity: RequestIdentity,
    ) -> AuthenticatedUser:
        if identity.provider is None or identity.external_subject is None:
            raise ValueError(
                "external identities require both provider and external_subject"
            )
        if (
            identity.provider not in (None, STUB_EMAIL_IDENTITY_PROVIDER)
            and not identity.email_verified
        ):
            raise ValueError(
                "verified email is required for external identity provisioning"
            )

        normalized_email = require_normalized_email(identity.email)

        lookup_by_external_identity_stmt = (
            select(
                users.c.id,
                users.c.email,
            )
            .join(
                user_external_identities,
                user_external_identities.c.user_id == users.c.id,
            )
            .where(
                user_external_identities.c.provider == identity.provider,
                user_external_identities.c.external_subject
                == identity.external_subject,
            )
            .limit(1)
        )
        lookup_by_email_stmt = (
            select(users.c.id, users.c.email)
            .where(users.c.email == normalized_email)
            .limit(1)
        )

        with Session(self.engine) as session:
            self._lock_external_identity(
                session,
                provider=identity.provider,
                external_subject=identity.external_subject,
            )
            row = None
            if identity.provider is not None and identity.external_subject is not None:
                row = session.execute(lookup_by_external_identity_stmt).first()

            if row is None:
                insert_user_stmt = (
                    pg_insert(users)
                    .values(
                        id=str(uuid.uuid4()),
                        email=normalized_email,
                        email_verified=identity.email_verified,
                    )
                    .on_conflict_do_nothing(index_elements=[users.c.email])
                    .returning(users.c.id, users.c.email)
                )
                row = session.execute(insert_user_stmt).first()

                if row is None:
                    if identity.provider in (None, STUB_EMAIL_IDENTITY_PROVIDER):
                        row = session.execute(lookup_by_email_stmt).one()
                    else:
                        row = session.execute(lookup_by_external_identity_stmt).first()
                        if row is None:
                            raise ValueError(
                                "external identity email collision requires "
                                "explicit account linking"
                            )

            if identity.provider is not None and identity.external_subject is not None:
                session.execute(
                    pg_insert(user_external_identities)
                    .values(
                        id=str(uuid.uuid4()),
                        user_id=str(row.id),
                        provider=identity.provider,
                        external_subject=identity.external_subject,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            user_external_identities.c.provider,
                            user_external_identities.c.external_subject,
                        ]
                    )
                )
                row = session.execute(lookup_by_external_identity_stmt).one()

            if identity.email_verified:
                session.execute(
                    users.update()
                    .where(users.c.id == str(row.id))
                    .values(email_verified=True)
                )

            session.commit()

        return AuthenticatedUser(
            user_id=str(row.id),
            email=str(row.email),
        )

    def _lock_external_identity(
        self,
        session: Session,
        *,
        provider: str | None,
        external_subject: str | None,
    ) -> None:
        if provider is None or external_subject is None:
            return

        session.execute(
            text(
                """
                select pg_advisory_xact_lock(
                    (('x' || substr(md5(:lock_key), 1, 16))::bit(64)::bigint)
                )
                """
            ),
            {"lock_key": f"{provider}:{external_subject}"},
        )

    def _domain_rule_matches(
        self,
        *,
        email_domain: str,
        rule_domain: str,
        match_mode: str,
    ) -> bool:
        if match_mode == "exact":
            return email_domain == rule_domain
        if match_mode == "suffix":
            return email_domain == rule_domain or email_domain.endswith(
                f".{rule_domain}"
            )
        raise ValueError(f"Unknown community email-domain match_mode: {match_mode}")

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
