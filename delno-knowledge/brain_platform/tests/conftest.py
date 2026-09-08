"""Shared fixtures for brain_platform security and isolation tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from brain_platform.db.connection import init_db
from brain_platform.db.repository import BrainRepository


TENANT_A = "tenant-alpha"
TENANT_B = "tenant-beta"
MARKER_A = "TENANT_ALPHA_SECRET_7f3a"
MARKER_B = "TENANT_BETA_SECRET_9c2e"
PUBLIC_MARKER_A = "PUBLIC_FAQ_ALPHA_k9m1"
PUBLIC_MARKER_B = "PUBLIC_FAQ_BETA_p4n8"


@pytest.fixture()
def repo(tmp_path: Path):
    db = tmp_path / "brain.db"
    os.environ["BRAIN_DB_PATH"] = str(db)
    conn = init_db(db)
    return BrainRepository(conn)


def seed_company_secret(repo: BrainRepository, *, tenant_id: str, marker: str) -> None:
    repo.upsert_document(
        doc_id=f"doc-{tenant_id}-company",
        tenant_id=tenant_id,
        title=f"Internal policy {tenant_id}",
        doc_type="doc",
        body=f"Confidential company knowledge. Unique marker {marker}.",
        visibility="company",
    )


def seed_public_faq(repo: BrainRepository, *, tenant_id: str, marker: str) -> None:
    repo.upsert_document(
        doc_id=f"doc-{tenant_id}-public",
        tenant_id=tenant_id,
        title=f"Customer FAQ {tenant_id}",
        doc_type="faq",
        body=f"Published customer answer. Unique marker {marker}.",
        visibility="public",
        channels=["office-assistant"],
        index_zone="public",
        classification={"level": "public"},
        ai_processing={
            "external_llm_allowed": True,
            "external_embedding_allowed": True,
            "local_processing_required": False,
        },
        publication={
            "status": "published",
            "approved": True,
            "approved_by": "user:admin",
            "approved_at": datetime(2026, 7, 23, tzinfo=timezone.utc).isoformat(),
            "public_version": 1,
        },
    )


@pytest.fixture()
def dual_tenant_repo(repo: BrainRepository):
    seed_company_secret(repo, tenant_id=TENANT_A, marker=MARKER_A)
    seed_company_secret(repo, tenant_id=TENANT_B, marker=MARKER_B)
    seed_public_faq(repo, tenant_id=TENANT_A, marker=PUBLIC_MARKER_A)
    seed_public_faq(repo, tenant_id=TENANT_B, marker=PUBLIC_MARKER_B)
    return repo
