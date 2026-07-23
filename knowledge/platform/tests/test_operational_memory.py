"""Operational memory contracts: contacts, mail, files, threads."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from knowledge.platform.schemas.models import (
    ACL,
    Classification,
    ClassificationLevel,
    ContactRecord,
    DocumentStatus,
    EmailMessageRecord,
    FileAssetRecord,
    ThreadRecord,
)
from knowledge.platform.security.acl import Principal, document_readable
from knowledge.platform.schemas.models import (
    DocumentFrontmatter,
    DocumentStatus,
)


TENANT = "quantum-labs"


class TestContactDirectory:
    def test_contact_requires_email_or_phone(self):
        with pytest.raises(ValidationError):
            ContactRecord(
                id="c1",
                tenant_id=TENANT,
                display_name="Ivan",
                emails=[],
                phones=[],
            )

    def test_contact_not_public(self):
        with pytest.raises(ValidationError, match="public"):
            ContactRecord(
                id="c1",
                tenant_id=TENANT,
                display_name="Ivan",
                emails=["ivan@example.com"],
                visibility="public",
            )

    def test_contact_stores_title_company_phone(self):
        c = ContactRecord(
            id="c1",
            tenant_id=TENANT,
            display_name="Ivan Petrov",
            emails=["ivan@quantumlabs.ru"],
            phones=["+79990001122"],
            title="CEO",
            company_name="Quantum Labs",
            visibility="company",
        )
        assert c.title == "CEO"
        assert c.classification.contains_personal_data is True


class TestMailIngestContracts:
    def test_inbound_and_outbound_directions(self):
        for direction in ("inbound", "outbound"):
            m = EmailMessageRecord(
                id=f"m-{direction}",
                tenant_id=TENANT,
                message_id=f"<{direction}@mail>",
                direction=direction,
                thread_id="t1",
                subject="Договор",
                from_email="a@x.ru",
                to_emails=["b@y.ru"],
                visibility="restricted",
                acl=ACL(allow_groups=["group:management"]),
                body_hash="abc",
            )
            assert m.direction == direction

    def test_email_cannot_be_public(self):
        with pytest.raises(ValidationError, match="public"):
            EmailMessageRecord(
                id="m1",
                tenant_id=TENANT,
                message_id="<1>",
                direction="inbound",
                thread_id="t1",
                subject="Hi",
                from_email="a@x.ru",
                visibility="public",
                body_hash="abc",
            )

    def test_voice_public_cannot_read_mail_doc(self):
        # Mail lives as restricted MD/doc in vault; voice-public only sees published public.
        mail_as_doc = DocumentFrontmatter(
            id="email-1",
            tenant_id=TENANT,
            title="Re: договор",
            type="email",
            visibility="restricted",
            acl=ACL(allow_groups=["group:management"]),
            classification=Classification(
                level=ClassificationLevel.CONFIDENTIAL,
                contains_personal_data=True,
            ),
            channels=[],
            status=DocumentStatus.ACTIVE,
        )
        p = Principal(principal_id="service:voice-public", tenant_id=TENANT)
        assert document_readable(mail_as_doc, p) is False


class TestFileAndThread:
    def test_server_file_not_auto_public(self):
        with pytest.raises(ValidationError, match="public"):
            FileAssetRecord(
                id="f1",
                tenant_id=TENANT,
                path="/opt/office/docs/contract.pdf",
                filename="contract.pdf",
                content_hash="deadbeef",
                source="server_root",
                visibility="public",
            )

    def test_thread_links_participants_and_topics(self):
        t = ThreadRecord(
            id="t1",
            tenant_id=TENANT,
            subject="Номинальный счёт Сбер",
            channel="email",
            project_id="proj-payouts",
            participant_contact_ids=["c1", "c2"],
            message_ids=["m1", "m2"],
            last_message_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
            visibility="restricted",
            acl=ACL(allow_groups=["group:sales"]),
            topics=["nominal-account", "sber"],
        )
        assert "nominal-account" in t.topics
        assert t.project_id == "proj-payouts"
