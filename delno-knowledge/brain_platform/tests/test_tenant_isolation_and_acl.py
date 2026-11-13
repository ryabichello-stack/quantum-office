"""E0.13 + E1.3 — cross-tenant isolation and guest vs owner ACL smoke tests."""

from __future__ import annotations

from brain_platform.db.repository import BrainRepository
from brain_platform.search.engine import BrainSearch
from brain_platform.security.acl import Principal

from brain_platform.tests.conftest import (
    MARKER_A,
    MARKER_B,
    PUBLIC_MARKER_A,
    PUBLIC_MARKER_B,
    TENANT_A,
    TENANT_B,
    dual_tenant_repo,
    seed_company_secret,
)


def _owner(tenant_id: str) -> Principal:
    return Principal(principal_id="service:text-owner", tenant_id=tenant_id)


def _guest(tenant_id: str) -> Principal:
    return Principal(principal_id="service:text-guest", tenant_id=tenant_id)


def _search_text(repo: BrainRepository, principal: Principal, query: str) -> str:
    result = BrainSearch(repo).retrieve(principal, query, mode="keyword")
    return result.get("text") or ""


class TestCrossTenantIsolation:
    def test_owner_sees_only_own_tenant_company_docs(self, dual_tenant_repo: BrainRepository):
        owner_a = _owner(TENANT_A)
        owner_b = _owner(TENANT_B)

        text_a = _search_text(dual_tenant_repo, owner_a, MARKER_A)
        text_b = _search_text(dual_tenant_repo, owner_b, MARKER_B)

        assert MARKER_A in text_a
        assert MARKER_B not in text_a
        assert MARKER_B in text_b
        assert MARKER_A not in text_b

    def test_cross_tenant_search_returns_empty_for_foreign_marker(
        self, dual_tenant_repo: BrainRepository
    ):
        owner_a = _owner(TENANT_A)
        cross = _search_text(dual_tenant_repo, owner_a, MARKER_B)
        assert MARKER_B not in cross

    def test_tenant_b_cannot_read_tenant_a_chunks_via_search(
        self, dual_tenant_repo: BrainRepository
    ):
        owner_b = _owner(TENANT_B)
        leaked = _search_text(dual_tenant_repo, owner_b, f"Confidential company knowledge {MARKER_A}")
        assert MARKER_A not in leaked


class TestACLGuestVsOwner:
    def test_owner_reads_company_content(self, dual_tenant_repo: BrainRepository):
        owner = _owner(TENANT_A)
        text = _search_text(dual_tenant_repo, owner, MARKER_A)
        assert MARKER_A in text

    def test_guest_denied_company_content(self, dual_tenant_repo: BrainRepository):
        guest = _guest(TENANT_A)
        text = _search_text(dual_tenant_repo, guest, MARKER_A)
        assert MARKER_A not in text

    def test_guest_reads_published_public_faq(self, dual_tenant_repo: BrainRepository):
        guest = _guest(TENANT_A)
        text = _search_text(dual_tenant_repo, guest, PUBLIC_MARKER_A)
        assert PUBLIC_MARKER_A in text

    def test_guest_cannot_read_other_tenant_public_faq(
        self, dual_tenant_repo: BrainRepository
    ):
        guest_a = _guest(TENANT_A)
        text = _search_text(dual_tenant_repo, guest_a, PUBLIC_MARKER_B)
        assert PUBLIC_MARKER_B not in text

    def test_owner_sees_both_company_and_public(self, dual_tenant_repo: BrainRepository):
        owner = _owner(TENANT_A)
        company = _search_text(dual_tenant_repo, owner, MARKER_A)
        public = _search_text(dual_tenant_repo, owner, PUBLIC_MARKER_A)
        assert MARKER_A in company
        assert PUBLIC_MARKER_A in public


class TestPrincipalContext:
    def test_unknown_principal_denied_even_in_own_tenant(self, repo: BrainRepository):
        seed_company_secret(repo, tenant_id=TENANT_A, marker=MARKER_A)
        unknown = Principal(principal_id="service:delno-widget-guest", tenant_id=TENANT_A)
        text = _search_text(repo, unknown, MARKER_A)
        assert MARKER_A not in text
