"""Tests for G3 graph-in-retrieve, S3 eval loader, V2 vault shard/ingest."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from brain_platform.db.connection import init_db
from brain_platform.db.repository import BrainRepository
from brain_platform.eval.runner import load_cases, run_eval
from brain_platform.graph.rebuild import rebuild_graph_from_corpus
from brain_platform.ingest.legacy_faq import ingest_legacy_faq
from brain_platform.ingest.shard_vault import shard_monolith
from brain_platform.ingest.vault import ingest_vault
from brain_platform.search.engine import BrainSearch
from brain_platform.security.acl import Principal


@pytest.fixture()
def repo(tmp_path: Path):
    db = tmp_path / "brain.db"
    os.environ["BRAIN_DB_PATH"] = str(db)
    os.environ["BRAIN_GRAPH_IN_RETRIEVE"] = "true"
    conn = init_db(db)
    return BrainRepository(conn)


def test_cases_yaml_loads():
    cases = load_cases()
    assert len(cases) >= 10
    assert all(c.get("id") and c.get("query") is not None or c.get("expect_denied") for c in cases)


def test_graph_in_retrieve_adds_related_block(repo: BrainRepository, tmp_path: Path):
    md = tmp_path / "faq.md"
    md.write_text(
        "## Комиссия\n\nКомиссия 1%.\n\n## Альфа-Банк\n\nКомплаенс Альфа-Банк номинальный счёт.\n",
        encoding="utf-8",
    )
    ingest_legacy_faq(repo, tenant_id="quantum-labs", path=md)
    repo.upsert_contact(
        tenant_id="quantum-labs",
        display_name="Юля Парцуф",
        emails=["yulia@alfabank.ru"],
        company_name="Альфа-Банк",
        source="test",
    )
    rebuild_graph_from_corpus(repo, tenant_id="quantum-labs")

    admin = Principal(
        principal_id="service:cursor-admin",
        tenant_id="quantum-labs",
        is_admin=True,
        user_id="denis",
    )
    out = BrainSearch(repo).retrieve(admin, "Парцуф", mode="keyword")
    assert out["ok"]
    assert out.get("graph")
    assert out["graph"].get("entities") or out["graph"].get("summary")
    assert out.get("citations")


def test_shard_and_ingest_vault(repo: BrainRepository, tmp_path: Path):
    src = Path("/workspace/knowledge/content/quantum_labs.md")
    if not src.exists():
        pytest.skip("monolith missing")
    vault = tmp_path / "quantum-brain"
    out = shard_monolith(source=src, vault_root=vault)
    assert out["ok"]
    assert len(out["shards"]) == 4
    for s in out["shards"]:
        assert (vault / s["path"]).exists()

    os.environ["BRAIN_VAULT_PATH"] = str(vault)
    ing = ingest_vault(repo, tenant_id="quantum-labs", vault_path=vault)
    assert ing["ok"]
    assert ing["files"] >= 3

    admin = Principal(
        principal_id="service:cursor-admin",
        tenant_id="quantum-labs",
        is_admin=True,
        user_id="denis",
    )
    hits = BrainSearch(repo).retrieve(admin, "ломбард 196-ФЗ", mode="keyword")
    assert hits["chars"] > 0


def test_eval_offline_smoke(repo: BrainRepository, tmp_path: Path):
    md = tmp_path / "faq.md"
    md.write_text(
        "## Комиссия\n\nКомиссия за СБП составляет 1%.\n\n"
        "## Что делает Quantum Payouts?\n\nМассовые выплаты Quantum Payouts.\n",
        encoding="utf-8",
    )
    ingest_legacy_faq(repo, tenant_id="quantum-labs", path=md)
    # Minimal cases file
    cases = tmp_path / "cases.yaml"
    cases.write_text(
        """
cases:
  - id: t1
    query: "комиссия"
    principal: service:cursor-admin
    mode: keyword
    min_chars: 10
    expect_any: ["комисси", "1%"]
    require_citation: true
  - id: voice-empty
    query: "комиссия"
    principal: service:voice-public
    expect_empty: true
""",
        encoding="utf-8",
    )
    out = run_eval(repo, cases_path=cases)
    assert out["total"] == 2
    assert out["passed"] >= 1
