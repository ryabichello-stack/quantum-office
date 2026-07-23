"""Contract + negative-security tests for ADR-0001 Phase 0.

These tests do not start the production FastAPI app and do not change :8017 behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from knowledge.platform.schemas.models import (
    ACL,
    AIProcessingPolicy,
    CacheKeyParts,
    Classification,
    ClassificationLevel,
    DocumentFrontmatter,
    DocumentStatus,
    Publication,
    PublicationStatus,
)
from knowledge.platform.security.acl import (
    Principal,
    build_backend_query,
    build_cache_key,
    chunk_inherits_document,
    document_readable,
    forbid_query_only_cache_key,
    make_audit_record,
    redact_query_preview,
    reject_client_supplied_tenant,
    resolve_principal_policy,
)
from knowledge.platform.security.safety import decide_index_action, scan_document_text


TENANT = "quantum-labs"


def _doc(**overrides):
    base = dict(
        id="doc-1",
        tenant_id=TENANT,
        title="Test",
        type="faq",
        visibility="company",
        acl=ACL(),
        classification=Classification(level=ClassificationLevel.INTERNAL),
        publication=Publication(status=PublicationStatus.UNPUBLISHED),
        channels=[],
        ai_processing=AIProcessingPolicy(
            external_llm_allowed=False,
            external_embedding_allowed=False,
            local_processing_required=True,
        ),
        status=DocumentStatus.ACTIVE,
        version=1,
        acl_revision=1,
    )
    base.update(overrides)
    return DocumentFrontmatter(**base)


class TestTenantIsolation:
    def test_tenant_id_required(self):
        with pytest.raises(ValidationError):
            _doc(tenant_id="")

    def test_client_tenant_mismatch_rejected(self):
        claims = {"tenant_id": TENANT}
        with pytest.raises(PermissionError):
            reject_client_supplied_tenant({"tenant_id": "other-co"}, claims)

    def test_tenant_taken_from_token(self):
        assert reject_client_supplied_tenant({}, {"tenant_id": TENANT}) == TENANT


class TestACLModel:
    def test_restricted_without_allow_list_forbidden(self):
        with pytest.raises(ValidationError, match="restricted"):
            _doc(visibility="restricted", acl=ACL())

    def test_restricted_with_allow_group_ok(self):
        doc = _doc(
            visibility="restricted",
            acl=ACL(allow_groups=["group:legal"]),
            classification=Classification(level=ClassificationLevel.CONFIDENTIAL),
        )
        assert doc.visibility == "restricted"

    def test_public_without_publish_forbidden(self):
        with pytest.raises(ValidationError, match="published"):
            _doc(visibility="public")

    def test_public_requires_manual_approval_fields(self):
        doc = _doc(
            visibility="public",
            publication=Publication(
                status=PublicationStatus.PUBLISHED,
                approved_by="user:denis",
                approved_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
                public_version=1,
            ),
            classification=Classification(level=ClassificationLevel.PUBLIC),
            ai_processing=AIProcessingPolicy(
                external_llm_allowed=True,
                external_embedding_allowed=True,
                local_processing_required=False,
            ),
        )
        assert doc.is_publishable_to_public_index()

    def test_credentials_force_quarantine(self):
        with pytest.raises(ValidationError, match="quarantine"):
            _doc(
                classification=Classification(
                    level=ClassificationLevel.SECRET,
                    contains_credentials=True,
                )
            )


class TestAIProcessingPolicy:
    def test_restricted_cannot_use_external_embedding(self):
        with pytest.raises(ValidationError, match="external"):
            _doc(
                visibility="restricted",
                acl=ACL(allow_users=["user:denis"]),
                classification=Classification(level=ClassificationLevel.CONFIDENTIAL),
                ai_processing=AIProcessingPolicy(
                    external_embedding_allowed=True,
                    external_llm_allowed=False,
                    local_processing_required=True,
                ),
            )


class TestInQueryACL:
    def test_post_filter_only_forbidden(self):
        p = Principal(principal_id="service:voice-public", tenant_id=TENANT)
        with pytest.raises(PermissionError, match="post-filter"):
            build_backend_query("keyword", p, "комиссия", post_filter_only=True)

    def test_backend_query_embeds_tenant_and_acl(self):
        p = Principal(principal_id="service:voice-public", tenant_id=TENANT)
        plan = build_backend_query("vector", p, "комиссия")
        assert "tenant_id = 'quantum-labs'" in plan["acl_filter"]
        assert plan["post_filter_defense_in_depth"] is True
        assert plan["backend"] == "vector"


class TestServicePrincipals:
    def test_unknown_principal_deny_all(self):
        p = Principal(principal_id="service:unknown-bot", tenant_id=TENANT)
        filt = resolve_principal_policy(p)
        assert filt.deny_all is True

    def test_voice_public_only_public(self):
        p = Principal(principal_id="service:voice-public", tenant_id=TENANT)
        public = _doc(
            visibility="public",
            publication=Publication(
                status=PublicationStatus.PUBLISHED,
                approved_by="user:denis",
                approved_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
                public_version=1,
            ),
            classification=Classification(level=ClassificationLevel.PUBLIC),
            ai_processing=AIProcessingPolicy(
                external_llm_allowed=True,
                external_embedding_allowed=True,
                local_processing_required=False,
            ),
        )
        company = _doc(visibility="company")
        assert document_readable(public, p) is True
        assert document_readable(company, p) is False

    def test_voice_office_public_plus_assistant_safe_only(self):
        p = Principal(principal_id="service:voice-office", tenant_id=TENANT)
        public = _doc(
            id="pub",
            visibility="public",
            publication=Publication(
                status=PublicationStatus.PUBLISHED,
                approved_by="user:denis",
                approved_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
                public_version=1,
            ),
            classification=Classification(level=ClassificationLevel.PUBLIC),
            channels=[],
            ai_processing=AIProcessingPolicy(
                external_llm_allowed=True,
                external_embedding_allowed=True,
                local_processing_required=False,
            ),
        )
        assistant_safe = _doc(
            id="safe",
            visibility="company",
            channels=["office-assistant"],
        )
        company_no_channel = _doc(visibility="company", channels=[])
        assert document_readable(public, p) is True
        assert document_readable(assistant_safe, p) is True
        assert document_readable(company_no_channel, p) is False

    def test_cursor_admin_without_personal_auth_denied(self):
        p = Principal(principal_id="service:cursor-admin", tenant_id=TENANT, is_admin=False)
        assert resolve_principal_policy(p).deny_all is True

    def test_no_blanket_company_for_text_secretary(self):
        p = Principal(principal_id="service:text-secretary", tenant_id=TENANT)
        company = _doc(visibility="company", channels=[])
        assert document_readable(company, p) is False
        curated = _doc(visibility="company", channels=["office-assistant"])
        assert document_readable(curated, p) is True


class TestChunkInheritance:
    def test_chunk_inherits_acl_tenant_revision(self):
        doc = _doc(
            visibility="restricted",
            acl=ACL(allow_groups=["group:sales"]),
            classification=Classification(level=ClassificationLevel.CONFIDENTIAL),
            acl_revision=4,
            version=3,
        )
        chunk = chunk_inherits_document(doc, "doc-1:chunk-04")
        assert chunk.tenant_id == TENANT
        assert chunk.document_id == "doc-1"
        assert chunk.acl_revision == 4
        assert chunk.document_version == 3
        assert chunk.allowed_group_ids == ["sales"]
        assert chunk.visibility == "restricted"


class TestCacheIsolation:
    def test_query_only_cache_forbidden(self):
        with pytest.raises(PermissionError, match="cache_key"):
            forbid_query_only_cache_key("комиссия СБП")

    def test_cache_key_includes_security_context(self):
        a = build_cache_key(
            CacheKeyParts(
                tenant_id=TENANT,
                principal_id="service:voice-public",
                groups=[],
                permission_revision=1,
                query="комиссия",
                search_mode="hybrid",
                index_revision=10,
            )
        )
        b = build_cache_key(
            CacheKeyParts(
                tenant_id=TENANT,
                principal_id="service:voice-office",
                groups=[],
                permission_revision=1,
                query="комиссия",
                search_mode="hybrid",
                index_revision=10,
            )
        )
        assert a != b


class TestAuditRedaction:
    def test_audit_has_hash_not_full_secret_query(self):
        p = Principal(principal_id="user:denis", tenant_id=TENANT)
        q = "покажи договор token: sk-abcdefghijklmnopqrstuvwxyz1234 для клиента"
        rec = make_audit_record(
            principal=p,
            query=q,
            retrieved_doc_ids=["doc-1"],
            denied_doc_count=2,
            purpose="assistant-query",
            request_id="req-1",
            timestamp=datetime(2026, 7, 23, tzinfo=timezone.utc),
        )
        assert rec.query_hash
        assert "sk-abcdefghijklmnopqrstuvwxyz1234" not in rec.query_preview_redacted
        assert not hasattr(rec, "query") or "query" not in rec.model_fields
        dumped = rec.model_dump()
        assert "query" not in dumped
        assert "[REDACTED]" in redact_query_preview(q)


class TestSafetyPipeline:
    def test_api_key_goes_to_quarantine(self):
        report = scan_document_text("API key: sk-abcdefghijklmnopqrstuvwxyz123456")
        assert report.has_credentials
        assert decide_index_action(report) == "quarantine"

    def test_private_key_quarantine(self):
        report = scan_document_text("-----BEGIN RSA PRIVATE KEY-----\nMIIE")
        assert decide_index_action(report) == "quarantine"

    def test_clean_faq_indexes(self):
        report = scan_document_text("Комиссия за СБП составляет X%.")
        assert decide_index_action(report) == "index"
