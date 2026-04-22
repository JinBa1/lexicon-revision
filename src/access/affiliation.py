from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.access.email import require_normalized_email


@dataclass(frozen=True)
class ManualAccessOverride:
    email: str
    community_id: str
    note: str | None = None


@dataclass(frozen=True)
class CommunityDomainMatch:
    community_id: str
    domain: str
    match_mode: str


@dataclass(frozen=True)
class AffiliationDecision:
    community_id: str | None
    deny_reason: str | None = None

    @property
    def is_allowed(self) -> bool:
        return self.community_id is not None


class AffiliationRepository(Protocol):
    def get_manual_access_override(self, email: str) -> ManualAccessOverride | None: ...

    def list_matching_communities_for_email_domain(
        self, email: str
    ) -> list[CommunityDomainMatch]: ...


class CommunityAffiliationResolver:
    def __init__(self, *, repository: AffiliationRepository) -> None:
        self.repository = repository

    def resolve_verified_email(self, email: str) -> AffiliationDecision:
        normalized_email = require_normalized_email(email)

        manual_override = self.repository.get_manual_access_override(normalized_email)
        if manual_override is not None:
            return AffiliationDecision(community_id=manual_override.community_id)

        domain_matches = self.repository.list_matching_communities_for_email_domain(
            normalized_email
        )
        if not domain_matches:
            return AffiliationDecision(
                community_id=None,
                deny_reason="unsupported_email_domain",
            )

        community_ids = {match.community_id for match in domain_matches}
        if len(community_ids) > 1:
            return AffiliationDecision(
                community_id=None,
                deny_reason="ambiguous_email_domain",
            )

        return AffiliationDecision(community_id=next(iter(community_ids)))
