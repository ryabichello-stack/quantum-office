"""Ingest must swallow new files, skip SoT/dups, and not leave stale FAQ copies."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain_platform.db.connection import init_db
from brain_platform.db.repository import BrainRepository
from brain_platform.ingest.files import ingest_files
from brain_platform.ingest.legacy_faq import ingest_legacy_faq


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setenv("BRAIN_EMBED_PROVIDER", "local")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    conn = init_db(str(tmp_path / "brain.db"))
    return BrainRepository(conn)


def test_faq_stable_id_update_and_prune(repo, tmp_path):
    md = tmp_path / "quantum_labs.md"
    md.write_text("## Alpha\n\none\n\n## Beta\n\ntwo\n", encoding="utf-8")
    r1 = ingest_legacy_faq(repo, tenant_id="quantum-labs", path=md)
    assert r1["sections"] == 2
    assert r1["deprecated"] == 0

    # edit Alpha, remove Beta, add Gamma
    md.write_text("## Alpha\n\nONE-updated\n\n## Gamma\n\nthree\n", encoding="utf-8")
    r2 = ingest_legacy_faq(repo, tenant_id="quantum-labs", path=md)
    assert r2["sections"] == 2
    assert r2["deprecated"] >= 1

    active = repo.conn.execute(
        "SELECT title, status FROM documents WHERE type='faq' ORDER BY title"
    ).fetchall()
    active_titles = {r["title"] for r in active if r["status"] == "active"}
    deprecated = {r["title"] for r in active if r["status"] == "deprecated"}
    assert "Alpha" in active_titles
    assert "Gamma" in active_titles
    assert "Beta" in deprecated

    # unchanged re-ingest
    r3 = ingest_legacy_faq(repo, tenant_id="quantum-labs", path=md)
    assert r3["unchanged"] == 2


def test_files_skip_sot_and_duplicate_and_ingest_new(repo, tmp_path, monkeypatch):
    root = tmp_path / "content"
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    sot = root / "quantum_labs.md"
    sot.write_text("## Product\n\nFAQ body\n", encoding="utf-8")
    monkeypatch.setenv("KNOWLEDGE_QUANTUM_LABS_PATH", str(sot))

    # SoT also via faq
    ingest_legacy_faq(repo, tenant_id="quantum-labs", path=sot)

    new_file = inbox / "pawn_note.md"
    new_file.write_text("# Note\n\nUnique lombard note about positive difference.\n", encoding="utf-8")

    # duplicate content under another name
    dup = inbox / "pawn_note_copy.md"
    dup.write_text(new_file.read_text(encoding="utf-8"), encoding="utf-8")

    r = ingest_files(repo, tenant_id="quantum-labs", roots=[root], limit=100)
    assert r["skipped_faq_sot"] >= 1
    assert r["created"] >= 1
    assert r["skipped_duplicate_content"] >= 1

    # second pass → unchanged
    r2 = ingest_files(repo, tenant_id="quantum-labs", roots=[root], limit=100)
    assert r2["unchanged"] >= 1
    assert r2["created"] == 0
