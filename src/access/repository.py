from __future__ import annotations

import uuid

from sqlalchemy import Engine, Integer, bindparam, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from src.access.affiliation import CommunityDomainMatch, ManualAccessOverride
from src.access.auth import STUB_EMAIL_IDENTITY_PROVIDER
from src.access.email import email_domain, require_normalized_email
from src.access.models import (
    AuthenticatedUser,
    CollectionAccess,
    CollectionAccessListing,
    CollectionAccessState,
    RequestIdentity,
    SupportedUniversityRecord,
)
from src.db.schema import (
    chunks,
    collections,
    communities,
    community_email_domains,
    community_memberships,
    manual_access_overrides,
    papers,
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
                    | (manual_access_overrides.c.expires_at > func.now())
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

    def list_supported_universities(self) -> list[SupportedUniversityRecord]:
        stmt = (
            select(
                communities.c.id,
                communities.c.name,
                community_email_domains.c.domain,
            )
            .select_from(
                communities.join(
                    community_email_domains,
                    community_email_domains.c.community_id == communities.c.id,
                )
            )
            .where(community_email_domains.c.is_active.is_(True))
            .order_by(communities.c.name, community_email_domains.c.domain)
        )
        with Session(self.engine) as session:
            rows = session.execute(stmt).all()

        grouped: dict[str, tuple[str, list[str]]] = {}
        for row in rows:
            entry = grouped.get(str(row.id))
            if entry is None:
                grouped[str(row.id)] = (str(row.name), [str(row.domain)])
            else:
                entry[1].append(str(row.domain))

        return [
            SupportedUniversityRecord(
                community_id=community_id,
                display_name=name,
                email_domains=tuple(domains),
            )
            for community_id, (name, domains) in grouped.items()
        ]

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

    def list_collections_with_access(
        self,
        *,
        request_identity: RequestIdentity,
        resolved_user_id: str | None,
        affiliation_community_id: str | None,
    ) -> list[CollectionAccessListing]:
        paper_count_sq = (
            select(
                papers.c.collection_id.label("collection_id"),
                func.count(papers.c.id).label("paper_count"),
            )
            .group_by(papers.c.collection_id)
            .subquery()
        )
        year_range_sq = (
            select(
                chunks.c.collection_id.label("collection_id"),
                func.min(func.cast(chunks.c.metadata["year"].astext, Integer)).label(
                    "year_start"
                ),
                func.max(func.cast(chunks.c.metadata["year"].astext, Integer)).label(
                    "year_end"
                ),
            )
            .where(chunks.c.metadata.has_key("year"))  # noqa: W601
            .group_by(chunks.c.collection_id)
            .subquery()
        )
        stmt = (
            select(
                collections.c.name,
                collections.c.community_id,
                collections.c.metadata_schema,
                communities.c.name.label("community_name"),
                paper_count_sq.c.paper_count,
                year_range_sq.c.year_start,
                year_range_sq.c.year_end,
            )
            .select_from(
                collections.outerjoin(
                    communities,
                    communities.c.id == collections.c.community_id,
                )
                .outerjoin(
                    paper_count_sq,
                    paper_count_sq.c.collection_id == collections.c.id,
                )
                .outerjoin(
                    year_range_sq,
                    year_range_sq.c.collection_id == collections.c.id,
                )
            )
            .order_by(collections.c.name)
        )
        with Session(self.engine) as session:
            active_membership_community_ids = (
                self._list_active_membership_community_ids(
                    session,
                    user_id=resolved_user_id,
                )
                if resolved_user_id is not None
                else set()
            )
            rows = session.execute(stmt).all()

        listings: list[CollectionAccessListing] = []
        for row in rows:
            community_id = (
                str(row.community_id) if row.community_id is not None else None
            )
            community_name = (
                str(row.community_name) if row.community_name is not None else None
            )
            access_state, lock_reason = self._compute_access_state(
                request_identity=request_identity,
                collection_community_id=community_id,
                collection_community_name=community_name,
                affiliation_community_id=affiliation_community_id,
                active_membership_community_ids=active_membership_community_ids,
            )
            listings.append(
                CollectionAccessListing(
                    collection_name=str(row.name),
                    display_name=self._derive_collection_display_name(str(row.name)),
                    community_id=community_id,
                    community_display_name=community_name,
                    paper_count=int(row.paper_count or 0),
                    year_start=(
                        int(row.year_start) if row.year_start is not None else None
                    ),
                    year_end=int(row.year_end) if row.year_end is not None else None,
                    access_state=access_state,
                    lock_reason=lock_reason,
                    metadata_schema=(
                        dict(row.metadata_schema)
                        if row.metadata_schema is not None
                        and access_state == "accessible"
                        else None
                    ),
                )
            )

        listings.sort(
            key=lambda row: (
                0 if row.access_state == "accessible" else 1,
                row.collection_name,
            )
        )
        return listings

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
        is_verified_external_identity = (
            identity.provider not in (None, STUB_EMAIL_IDENTITY_PROVIDER)
            and identity.email_verified
        )

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
        lookup_provider_identity_for_user_stmt = select(
            user_external_identities.c.external_subject
        ).where(
            user_external_identities.c.user_id == bindparam("user_id"),
            user_external_identities.c.provider == bindparam("provider"),
        )

        with Session(self.engine) as session:

            def _has_conflicting_provider_subjects(user_id: str) -> bool:
                existing_provider_subjects = (
                    session.execute(
                        lookup_provider_identity_for_user_stmt,
                        {
                            "user_id": user_id,
                            "provider": identity.provider,
                        },
                    )
                    .scalars()
                    .all()
                )
                return any(
                    existing_subject != identity.external_subject
                    for existing_subject in existing_provider_subjects
                )

            self._lock_external_identity(
                session,
                provider=identity.provider,
                external_subject=identity.external_subject,
            )
            if is_verified_external_identity:
                self._lock_email(session, normalized_email)
            row = None
            if identity.provider is not None and identity.external_subject is not None:
                row = session.execute(lookup_by_external_identity_stmt).first()
                if row is not None and _has_conflicting_provider_subjects(str(row.id)):
                    raise ValueError(
                        "external identity email collision requires "
                        "explicit account linking"
                    )

            if row is None:
                if is_verified_external_identity:
                    row = session.execute(lookup_by_email_stmt).first()
                    if row is not None and _has_conflicting_provider_subjects(
                        str(row.id)
                    ):
                        raise ValueError(
                            "external identity email collision requires "
                            "explicit account linking"
                        )

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
                        row = session.execute(lookup_by_email_stmt).first()
                        if row is None:
                            row = session.execute(
                                lookup_by_external_identity_stmt
                            ).first()
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

    def ensure_active_membership(self, *, user_id: str, community_id: str) -> None:
        with Session(self.engine) as session:
            session.execute(
                pg_insert(community_memberships)
                .values(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    community_id=community_id,
                    role="member",
                    status="active",
                )
                .on_conflict_do_update(
                    index_elements=[
                        community_memberships.c.user_id,
                        community_memberships.c.community_id,
                    ],
                    set_={"status": "active"},
                )
            )
            session.commit()

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

    def _lock_email(self, session: Session, email: str) -> None:
        session.execute(
            text(
                """
                select pg_advisory_xact_lock(
                    (('x' || substr(md5(:lock_key), 1, 16))::bit(64)::bigint)
                )
                """
            ),
            {"lock_key": f"email:{email}"},
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

    def _compute_access_state(
        self,
        *,
        request_identity: RequestIdentity,
        collection_community_id: str | None,
        collection_community_name: str | None,
        affiliation_community_id: str | None,
        active_membership_community_ids: set[str],
    ) -> tuple[CollectionAccessState, str | None]:
        if collection_community_id is None:
            return "accessible", None

        if request_identity.is_anonymous:
            return "locked_requires_signin", "Sign in to access this collection"

        if (
            affiliation_community_id is not None
            and affiliation_community_id != collection_community_id
        ):
            return (
                "locked_wrong_affiliation",
                self._restricted_members_lock_reason(collection_community_name),
            )

        if collection_community_id in active_membership_community_ids:
            return "accessible", None

        return (
            "locked_wrong_affiliation",
            self._restricted_members_lock_reason(collection_community_name),
        )

    def _list_active_membership_community_ids(
        self,
        session: Session,
        *,
        user_id: str,
    ) -> set[str]:
        stmt = select(community_memberships.c.community_id).where(
            community_memberships.c.user_id == user_id,
            community_memberships.c.status == "active",
        )
        return {
            str(community_id)
            for community_id in session.execute(stmt).scalars()
            if community_id is not None
        }

    def _restricted_members_lock_reason(
        self, community_display_name: str | None
    ) -> str:
        if community_display_name:
            return f"This collection is restricted to {community_display_name} members"
        return "This collection is restricted to members of this community"

    def _derive_collection_display_name(self, collection_name: str) -> str:
        parts = collection_name.replace("-", " ").replace("_", " ").split()
        if not parts:
            return collection_name
        return " ".join(
            part if part.isupper() else part[:1].upper() + part[1:].lower()
            for part in parts
        )
