"""Graph + citations + zone guard tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from brain_platform.db.connection import init_db
from brain_platform.db.repository import BrainRepository
from brain_platform.graph.rebuild import rebuild_graph_from_corpus
from brain_platform.graph.store import GraphStore
from brain_platform.search.engine import BrainSearch, format_citation
from brain_platform.security.acl import Principal
from brain_platform.security.zones import coerce_index_zone


@pytest.fixture()
def repo(tmp_path: Path):
    db = tmp_path / "brain.db"
    os.environ["BRAIN_DB_PATH"] = str(db)
    conn = init_db(db)
    return BrainRepository(conn)


def test_zone_guard_blocks_mail_public():
    assert (
        coerce_index_zone(doc_type="email", visibility="restricted", index_zone="public")
        == "private"
    )
    assert (
        coerce_index_zone(
            doc_type="faq",
            visibility="public",
            index_zone="public",
            publication={"manual_approve": True},
        )
        == "public"
    )
    assert (
        coerce_index_zone(doc_type="faq", visibility="public", index_zone="public")
        == "private"
    )


def test_email_upsert_forced_private_zone(repo: BrainRepository):
    repo.upsert_email_message(
        tenant_id="quantum-labs",
        message_id="z1@mail",
        direction="inbound",
        subject="Секретный договор",
        from_email="a@b.ru",
        to_emails=["office@quantumlabs.ru"],
        body_text="PII and contract details",
    )
    row = repo.conn.execute(
        "SELECT index_zone, type FROM documents WHERE type='email' LIMIT 1"
    ).fetchone()
    assert row["index_zone"] == "private"


def test_graph_rebuild_and_expand(repo: BrainRepository):
    repo.upsert_contact(
        tenant_id="quantum-labs",
        display_name="Юля Парцуф",
        emails=["yulia@example.com"],
        company_name="НордСервис",
        source="test",
    )
    repo.upsert_email_message(
        tenant_id="quantum-labs",
        message_id="t1@mail",
        direction="inbound",
        subject="НордСервис договор",
        from_email="yulia@example.com",
        to_emails=["office@quantumlabs.ru"],
        body_text="Обсуждаем условия",
        from_name="Юля Парцуф",
    )
    stats = rebuild_graph_from_corpus(repo, tenant_id="quantum-labs")
    assert stats["ok"]
    assert stats["persons"] >= 1
    assert stats["companies"] >= 1

    admin = Principal(
        principal_id="service:cursor-admin",
        tenant_id="quantum-labs",
        is_admin=True,
        user_id="denis",
    )
    out = GraphStore(repo.conn).expand(admin, q="Парцуф", depth=1)
    assert out["ok"]
    assert out["entities"]
    kinds = {e["kind"] for e in out["entities"]}
    assert "person" in kinds
    assert "company" in kinds or any(
        e.get("relation_type") == "works_at" for e in out["edges"]
    )

    voice = Principal(principal_id="service:voice-public", tenant_id="quantum-labs")
    denied = GraphStore(repo.conn).expand(voice, q="Парцуф")
    assert denied.get("denied") or not denied.get("entities")


def test_search_returns_citations(repo: BrainRepository, tmp_path: Path):
    md = tmp_path / "faq.md"
    md.write_text("## Тарифы\n\nКомиссия 1%.\n", encoding="utf-8")
    from brain_platform.ingest.legacy_faq import ingest_legacy_faq

    ingest_legacy_faq(repo, tenant_id="quantum-labs", path=md)
    admin = Principal(
        principal_id="service:cursor-admin",
        tenant_id="quantum-labs",
        is_admin=True,
        user_id="denis",
    )
    hits = BrainSearch(repo).retrieve(admin, "тарифы комиссия", mode="keyword")
    assert hits["ok"]
    assert hits.get("citations")
    assert hits["matches"]
    assert hits["matches"][0].get("citation")
    assert "doc=" in hits["matches"][0]["citation"]
    assert format_citation(hits["matches"][0]).startswith("[")
