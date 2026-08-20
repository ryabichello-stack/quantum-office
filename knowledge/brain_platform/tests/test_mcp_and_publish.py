"""Tests for MCP tools, kb.get ACL, and publish bundle."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from brain_platform.db.connection import init_db
from brain_platform.db.repository import BrainRepository
from brain_platform.ingest.legacy_faq import ingest_legacy_faq
from brain_platform.mcp.server import TOOLS, call_tool, _handle
from brain_platform.publish.bundle import build_bundle
from brain_platform.security.acl import Principal


@pytest.fixture()
def repo(tmp_path: Path):
    db = tmp_path / "brain.db"
    os.environ["BRAIN_DB_PATH"] = str(db)
    return BrainRepository(init_db(db))


def test_mcp_tools_registered():
    names = {t["name"] for t in TOOLS}
    assert {"kb.search", "kb.get", "kb.related", "kb.ingest_status"} <= names


def test_mcp_initialize_and_list_tools():
    init = _handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "quantum-brain"
    listed = _handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert len(listed["result"]["tools"]) >= 4


def test_get_document_acl(repo: BrainRepository, tmp_path: Path, monkeypatch):
    md = tmp_path / "faq.md"
    md.write_text("## Комиссия\n\nКомиссия 1%.\n", encoding="utf-8")
    ingest_legacy_faq(repo, tenant_id="quantum-labs", path=md)
    admin = Principal(
        principal_id="service:cursor-admin",
        tenant_id="quantum-labs",
        is_admin=True,
        user_id="denis",
    )
    # find a doc id
    row = repo.conn.execute("SELECT id FROM documents WHERE type='faq' LIMIT 1").fetchone()
    got = repo.get_document(admin, document_id=row["id"])
    assert got and got["ok"]
    assert "1%" in got["text"] or got["chars"] > 0

    voice = Principal(principal_id="service:voice-public", tenant_id="quantum-labs")
    denied = repo.get_document(voice, document_id=row["id"])
    assert denied is None


def test_mcp_call_tool_search_against_mock(monkeypatch):
    def fake_request(method, path, body=None, timeout=60.0):
        assert path == "/api/brain/search"
        return {"ok": True, "text": "hi", "citations": ["c1"]}

    monkeypatch.setattr("brain_platform.mcp.server.brain_request", fake_request)
    out = call_tool("kb.search", {"query": "комиссия"})
    payload = json.loads(out["content"][0]["text"])
    assert payload["ok"] is True


def test_publish_bundle(tmp_path: Path):
    vault = Path("/workspace/knowledge/vault/quantum-brain")
    if not vault.exists():
        pytest.skip("vault missing")
    out = build_bundle(vault=vault, out_dir=tmp_path / "dist")
    assert out["ok"] is True
    assert Path(out["bundle"]).exists()
    assert out["manifest"]["vault_files"] >= 4
