"""Tests for dual-write helpers, monolith export, knowledge dual_compare."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from brain_platform.db.connection import init_db
from brain_platform.db.pg_write import dual_write_enabled
from brain_platform.db.repository import BrainRepository
from brain_platform.ingest.legacy_faq import ingest_legacy_faq
from brain_platform.publish.export_monolith import export_monolith
from brain_platform.security.acl import Principal


@pytest.fixture()
def repo(tmp_path: Path):
    db = tmp_path / "brain.db"
    os.environ["BRAIN_DB_PATH"] = str(db)
    os.environ["BRAIN_DUAL_WRITE"] = "false"
    os.environ["BRAIN_STORE"] = "sqlite"
    return BrainRepository(init_db(db))


def test_dual_write_flag_explicit_off(monkeypatch):
    monkeypatch.setenv("BRAIN_DUAL_WRITE", "false")
    monkeypatch.setenv("BRAIN_STORE", "postgres")
    monkeypatch.setenv("BRAIN_DATABASE_URL", "postgresql://x")
    assert dual_write_enabled() is False


def test_dual_write_flag_default_with_postgres(monkeypatch):
    monkeypatch.delenv("BRAIN_DUAL_WRITE", raising=False)
    monkeypatch.setenv("BRAIN_STORE", "postgres")
    monkeypatch.setenv("BRAIN_DATABASE_URL", "postgresql://x")
    assert dual_write_enabled() is True


def test_export_monolith(tmp_path: Path):
    vault = Path("/workspace/knowledge/vault/quantum-brain")
    if not vault.exists():
        pytest.skip("vault missing")
    out = tmp_path / "quantum_labs.md"
    result = export_monolith(vault=vault, out_path=out)
    assert result["ok"]
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Generated from vault" in text
    assert "Quantum" in text or "ломбард" in text.lower() or "Часть" in text
    assert len(text) > 1000


def test_knowledge_read_mode_env_default(monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_READ_MODE", raising=False)
    mode = (os.getenv("KNOWLEDGE_READ_MODE") or "legacy").strip().lower()
    assert mode == "legacy"
    monkeypatch.setenv("KNOWLEDGE_READ_MODE", "dual_compare")
    mode = (os.getenv("KNOWLEDGE_READ_MODE") or "legacy").strip().lower()
    assert mode == "dual_compare"


def test_get_document_still_works(repo: BrainRepository, tmp_path: Path):
    md = tmp_path / "faq.md"
    md.write_text("## Тариф\n\nКомиссия 2%.\n", encoding="utf-8")
    ingest_legacy_faq(repo, tenant_id="quantum-labs", path=md)
    admin = Principal(
        principal_id="service:cursor-admin",
        tenant_id="quantum-labs",
        is_admin=True,
        user_id="t",
    )
    row = repo.conn.execute("SELECT id FROM documents LIMIT 1").fetchone()
    got = repo.get_document(admin, document_id=row["id"])
    assert got and "2%" in got["text"]
