from __future__ import annotations

from src.access.affiliation import (
    AffiliationDecision,
    CommunityAffiliationResolver,
    CommunityDomainMatch,
    ManualAccessOverride,
)


class FakeAffiliationRepository:
    def __init__(
        self,
        *,
        manual_override: ManualAccessOverride | None = None,
        domain_matches: list[CommunityDomainMatch] | None = None,
    ) -> None:
        self.manual_override = manual_override
        self.domain_matches = list(domain_matches or [])
        self.manual_override_emails: list[str] = []
        self.domain_match_emails: list[str] = []

    def get_manual_access_override(self, email: str) -> ManualAccessOverride | None:
        assert email == email.strip().lower()
        self.manual_override_emails.append(email)
        return self.manual_override

    def list_matching_communities_for_email_domain(
        self, email: str
    ) -> list[CommunityDomainMatch]:
        assert email == email.strip().lower()
        self.domain_match_emails.append(email)
        return list(self.domain_matches)


def test_affiliation_resolver_prefers_manual_override() -> None:
    repository = FakeAffiliationRepository(
        manual_override=ManualAccessOverride(
            email="student@sub.example.edu",
            community_id="community-manual",
        ),
        domain_matches=[
            CommunityDomainMatch(
                community_id="community-domain",
                domain="example.edu",
                match_mode="suffix",
            )
        ],
    )
    resolver = CommunityAffiliationResolver(repository=repository)

    decision = resolver.resolve_verified_email(" Student@Sub.Example.edu ")

    assert decision == AffiliationDecision(community_id="community-manual")
    assert decision.is_allowed
    assert repository.manual_override_emails == ["student@sub.example.edu"]
    assert repository.domain_match_emails == []


def test_affiliation_resolver_denies_unsupported_email() -> None:
    repository = FakeAffiliationRepository()
    resolver = CommunityAffiliationResolver(repository=repository)

    decision = resolver.resolve_verified_email(" Student@Example.com ")

    assert decision == AffiliationDecision(
        community_id=None,
        deny_reason="unsupported_email_domain",
    )
    assert not decision.is_allowed
    assert repository.manual_override_emails == ["student@example.com"]
    assert repository.domain_match_emails == ["student@example.com"]


def test_affiliation_resolver_denies_ambiguous_match() -> None:
    repository = FakeAffiliationRepository(
        domain_matches=[
            CommunityDomainMatch(
                community_id="community-1",
                domain="example.edu",
                match_mode="suffix",
            ),
            CommunityDomainMatch(
                community_id="community-2",
                domain="cs.example.edu",
                match_mode="exact",
            ),
        ]
    )
    resolver = CommunityAffiliationResolver(repository=repository)

    decision = resolver.resolve_verified_email(" Student@Cs.Example.edu ")

    assert decision == AffiliationDecision(
        community_id=None,
        deny_reason="ambiguous_email_domain",
    )
    assert not decision.is_allowed
    assert repository.manual_override_emails == ["student@cs.example.edu"]
    assert repository.domain_match_emails == ["student@cs.example.edu"]


def test_affiliation_resolver_allows_duplicate_rules_for_same_community() -> None:
    repository = FakeAffiliationRepository(
        domain_matches=[
            CommunityDomainMatch(
                community_id="community-1",
                domain="example.edu",
                match_mode="suffix",
            ),
            CommunityDomainMatch(
                community_id="community-1",
                domain="cs.example.edu",
                match_mode="exact",
            ),
        ]
    )
    resolver = CommunityAffiliationResolver(repository=repository)

    decision = resolver.resolve_verified_email(" Student@Cs.Example.edu ")

    assert decision == AffiliationDecision(community_id="community-1")
    assert decision.is_allowed
    assert repository.manual_override_emails == ["student@cs.example.edu"]
    assert repository.domain_match_emails == ["student@cs.example.edu"]
