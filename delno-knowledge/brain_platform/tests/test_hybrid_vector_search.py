"""Hybrid vector + keyword search tests (local embeddings, no OpenAI)."""

from __future__ import annotations

import os

import pytest

from brain_platform.db.connection import init_db
from brain_platform.db.repository import BrainRepository
from brain_platform.embeddings import LocalHashEmbedder, cosine_similarity
from brain_platform.search.engine import BrainSearch
from brain_platform.security.acl import Principal
from brain_platform.vector import rrf_fuse


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setenv("BRAIN_EMBED_PROVIDER", "local")
    monkeypatch.setenv("BRAIN_SEARCH_MODE", "hybrid")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    conn = init_db(str(tmp_path / "brain.db"))
    return BrainRepository(conn)


def test_local_embed_and_cosine():
    emb = LocalHashEmbedder(dim=64)
    a, b, c = emb.embed(
        [
            "ломбард положительная разница после реализации залога",
            "ломбард возврат разницы заемщику",
            "тарифы комиссии СБП для выплат",
        ]
    )
    assert cosine_similarity(a, b) > cosine_similarity(a, c)


def test_rrf_fuse_prefers_agreement():
    a = [{"chunk_id": "1", "text": "a"}, {"chunk_id": "2", "text": "b"}]
    b = [{"chunk_id": "2", "text": "b"}, {"chunk_id": "3", "text": "c"}]
    fused = rrf_fuse([a, b], limit=3)
    assert fused[0]["chunk_id"] == "2"


def test_hybrid_retrieve_embeds_on_ingest(repo):
    repo.upsert_document(
        doc_id="doc-pawn",
        tenant_id="quantum-labs",
        title="Ломбарды",
        doc_type="faq",
        visibility="company",
        body="# Ломбарды\n\nВозврат положительной разницы после реализации невостребованного залога.\n",
        acl={"allow_services": ["service:text-secretary", "service:cursor-admin"]},
        channels=["office-assistant"],
        index_zone="private",
        embed=True,
        ai_processing={"external_embedding_allowed": False, "local_processing_required": True},
    )
    repo.upsert_document(
        doc_id="doc-sbp",
        tenant_id="quantum-labs",
        title="СБП",
        doc_type="faq",
        visibility="company",
        body="# СБП\n\nВыплаты через СБП на телефон за минуту.\n",
        acl={"allow_services": ["service:text-secretary", "service:cursor-admin"]},
        channels=["office-assistant"],
        index_zone="private",
        embed=True,
        ai_processing={"external_embedding_allowed": False, "local_processing_required": True},
    )

    # embedding_json filled
    row = repo.conn.execute(
        "SELECT embedding_json FROM chunks WHERE document_id='doc-pawn' LIMIT 1"
    ).fetchone()
    assert row and row["embedding_json"] != "[]"

    principal = Principal(
        principal_id="service:cursor-admin",
        tenant_id="quantum-labs",
        is_admin=True,
        user_id="test",
    )
    out = BrainSearch(repo).retrieve(
        principal,
        "как вернуть положительную разницу ломбарду",
        mode="hybrid",
        limit=4,
    )
    assert out["ok"] is True
    assert out["search_mode"] == "hybrid"
    assert out["matches"]
    titles = " ".join(m.get("title") or "" for m in out["matches"]).lower()
    text = (out.get("text") or "").lower()
    assert "ломбард" in titles or "ломбард" in text or "разниц" in text
