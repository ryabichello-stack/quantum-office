"""Integration tests for brain store, ACL search, FAQ ingest (offline)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from brain_platform.db.connection import init_db
from brain_platform.db.repository import BrainRepository
from brain_platform.ingest.legacy_faq import ingest_legacy_faq
from brain_platform.search.engine import BrainSearch
from brain_platform.security.acl import Principal


@pytest.fixture()
def repo(tmp_path: Path):
    db = tmp_path / "brain.db"
    os.environ["BRAIN_DB_PATH"] = str(db)
    conn = init_db(db)
    return BrainRepository(conn)


def test_faq_ingest_and_office_search(repo: BrainRepository, tmp_path: Path):
    md = tmp_path / "faq.md"
    md.write_text(
        "## Комиссия СБП\n\nКомиссия за СБП составляет 1%.\n\n## Контакты\n\nПишите на office@quantumlabs.ru\n",
        encoding="utf-8",
    )
    result = ingest_legacy_faq(repo, tenant_id="quantum-labs", path=md)
    assert result["ok"] is True
    assert result["sections"] >= 2

    admin = Principal(
        principal_id="service:cursor-admin",
        tenant_id="quantum-labs",
        is_admin=True,
        user_id="denis",
    )
    hits = BrainSearch(repo).retrieve(admin, "комиссия СБП")
    assert hits["ok"]
    assert "1%" in hits["text"] or hits["chars"] > 0

    voice_public = Principal(principal_id="service:voice-public", tenant_id="quantum-labs")
    denied = BrainSearch(repo).retrieve(voice_public, "комиссия СБП")
    # FAQ is company/private — voice-public must not see it
    assert denied["chars"] == 0 or denied.get("denied")


def test_mail_message_creates_contact_and_hidden_from_voice(repo: BrainRepository):
    repo.upsert_email_message(
        tenant_id="quantum-labs",
        message_id="abc123@mail",
        direction="inbound",
        subject="Договор номинального счёта",
        from_email="client@bank.ru",
        to_emails=["office@quantumlabs.ru"],
        body_text="Обсуждаем условия договора по номинальному счёту.",
    )
    secretary = Principal(principal_id="service:text-secretary", tenant_id="quantum-labs")
    contacts = repo.find_contacts(secretary, email="client@bank.ru")
    assert len(contacts) >= 1

    voice = Principal(principal_id="service:voice-public", tenant_id="quantum-labs")
    assert repo.find_contacts(voice, email="client@bank.ru") == []

    admin = Principal(
        principal_id="service:cursor-admin",
        tenant_id="quantum-labs",
        is_admin=True,
        user_id="denis",
    )
    threads = repo.list_threads(admin, q="номинального")
    assert any("номинального" in t["subject"].lower() or "Договор" in t["subject"] for t in threads)


def test_file_ingest_indexes_text(repo: BrainRepository, tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    f = root / "spec.txt"
    f.write_text("Техническая спецификация API выплат Quantum Payouts", encoding="utf-8")
    from brain_platform.ingest.files import ingest_files

    out = ingest_files(repo, tenant_id="quantum-labs", roots=[root], limit=10)
    assert out["ok"]
    assert out["created"] >= 1

    admin = Principal(
        principal_id="service:cursor-admin",
        tenant_id="quantum-labs",
        is_admin=True,
        user_id="denis",
    )
    res = BrainSearch(repo).retrieve(admin, "спецификация API")
    assert res["chars"] > 0


def test_unknown_principal_empty(repo: BrainRepository):
    repo.upsert_document(
        doc_id="d1",
        tenant_id="quantum-labs",
        title="Secret note",
        doc_type="doc",
        body="секретная информация про банк",
        visibility="restricted",
        acl={"allow_users": ["user:denis"], "allow_groups": [], "allow_services": []},
        index_zone="private",
    )
    unknown = Principal(principal_id="service:unknown-bot", tenant_id="quantum-labs")
    res = BrainSearch(repo).retrieve(unknown, "банк")
    assert res["chars"] == 0
