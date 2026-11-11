"""O1 — draft onboarding documents must not be readable by widget guest principal."""

from __future__ import annotations

from datetime import datetime, timezone

from brain_platform.schemas.models import (
    ACL,
    AIProcessingPolicy,
    Classification,
    ClassificationLevel,
    DocumentFrontmatter,
    DocumentStatus,
    Publication,
    PublicationStatus,
)
from brain_platform.security.acl import Principal, document_readable


TENANT = "salon-demo"


def _guest_principal() -> Principal:
    return Principal(
        principal_id="service:text-guest",
        tenant_id=TENANT,
        groups=(),
        user_id=None,
        is_admin=False,
    )


def _draft_onboarding_doc() -> DocumentFrontmatter:
    return DocumentFrontmatter(
        id="doc-salon-demo-onboarding",
        tenant_id=TENANT,
        title="Onboarding draft",
        type="doc",
        visibility="company",
        acl=ACL(),
        classification=Classification(level=ClassificationLevel.INTERNAL),
        publication=Publication(status=PublicationStatus.UNPUBLISHED),
        channels=["office-assistant"],
        ai_processing=AIProcessingPolicy(
            external_llm_allowed=False,
            external_embedding_allowed=False,
            local_processing_required=True,
        ),
        status=DocumentStatus.DRAFT,
        version=1,
        acl_revision=1,
        source="onboarding.draft",
    )


def _published_public_doc() -> DocumentFrontmatter:
    return DocumentFrontmatter(
        id="doc-salon-demo-faq",
        tenant_id=TENANT,
        title="FAQ",
        type="faq",
        visibility="public",
        acl=ACL(),
        classification=Classification(level=ClassificationLevel.PUBLIC),
        publication=Publication(
            status=PublicationStatus.PUBLISHED,
            approved_by="user:owner",
            approved_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
            public_version=1,
        ),
        channels=["office-assistant"],
        ai_processing=AIProcessingPolicy(
            external_llm_allowed=True,
            external_embedding_allowed=True,
            local_processing_required=False,
        ),
        status=DocumentStatus.ACTIVE,
        version=1,
        acl_revision=1,
        source="onboarding.publish",
    )


def test_draft_company_doc_not_readable_by_widget_guest():
    guest = _guest_principal()
    doc = _draft_onboarding_doc()
    assert document_readable(doc, guest) is False


def test_published_public_doc_readable_by_widget_guest():
    guest = _guest_principal()
    doc = _published_public_doc()
    assert document_readable(doc, guest) is True
