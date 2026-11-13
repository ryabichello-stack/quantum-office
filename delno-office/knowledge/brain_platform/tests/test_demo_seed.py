"""E1.2 — demo vault seed, tenant-scoped search, restart-safe state."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from brain_platform.db.connection import init_db
from brain_platform.db.repository import BrainRepository
from brain_platform.seed.demo import (
    DEMO_TENANT,
    MARKER_COMPANY,
    MARKER_PUBLIC,
    seed_demo_vault,
    verify_demo_search,
)


@pytest.fixture()
def repo(tmp_path: Path):
    db = tmp_path / "brain.db"
    os.environ["BRAIN_DB_PATH"] = str(db)
    conn = init_db(db)
    return BrainRepository(conn)


def test_seed_demo_creates_documents(repo: BrainRepository):
    result = seed_demo_vault(repo, ingest_vault_files=False)
    assert result["ok"] is True
    assert result["seeded"] is True
    stats = repo.stats(DEMO_TENANT)
    assert stats["documents"] >= 2


def test_seed_demo_idempotent(repo: BrainRepository):
    first = seed_demo_vault(repo, ingest_vault_files=False)
    second = seed_demo_vault(repo, ingest_vault_files=False)
    assert first["seeded"] is True
    assert second["skipped"] is True


def test_demo_tenant_scoped_search_and_acl(repo: BrainRepository):
    seed_demo_vault(repo, ingest_vault_files=False)
    check = verify_demo_search(repo)
    assert check["owner_company"] is True
    assert check["owner_public"] is True
    assert check["guest_company_denied"] is True
    assert check["guest_public"] is True
    assert check["provenance"] is True


def test_restart_preserves_demo_state(tmp_path: Path):
    db = tmp_path / "brain-restart.db"
    os.environ["BRAIN_DB_PATH"] = str(db)

    seed_demo_vault(BrainRepository(init_db(db)), ingest_vault_files=False)

    repo2 = BrainRepository(init_db(db))
    check = verify_demo_search(repo2)
    assert check["owner_company"] is True
    assert check["guest_public"] is True
