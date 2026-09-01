"""Idempotent demo vault seed for DELNO staging/prod (tenant delno-demo)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brain_platform.db.connection import init_db
from brain_platform.db.repository import BrainRepository
from brain_platform.ingest.vault import ingest_vault
from brain_platform.search.engine import BrainSearch
from brain_platform.security.acl import Principal

DEMO_TENANT = "delno-demo"
DOC_COMPANY_ID = "doc-delno-demo-company"
DOC_PUBLIC_ID = "doc-delno-demo-public-faq"
MARKER_COMPANY = "DELNO_DEMO_COMPANY_k7m2"
MARKER_PUBLIC = "DELNO_DEMO_PUBLIC_f3n9"


def _upsert_company_doc(repo: BrainRepository, *, tenant_id: str) -> None:
    repo.upsert_document(
        doc_id=DOC_COMPANY_ID,
        tenant_id=tenant_id,
        title="DELNO — внутренняя база компании",
        doc_type="doc",
        body=(
            "DELNO — ИИ-сотрудник первой линии для бизнеса. "
            f"Внутренний маркер {MARKER_COMPANY}. "
            "Этот документ доступен только владельцу tenant."
        ),
        visibility="company",
        source="seed:demo-company",
    )


def _upsert_public_faq(repo: BrainRepository, *, tenant_id: str) -> None:
    repo.upsert_document(
        doc_id=DOC_PUBLIC_ID,
        tenant_id=tenant_id,
        title="DELNO — FAQ для клиентов",
        doc_type="faq",
        body=(
            "DELNO отвечает клиентам на сайте, по телефону и в мессенджерах. "
            f"Публичный маркер {MARKER_PUBLIC}."
        ),
        visibility="public",
        channels=["office-assistant"],
        index_zone="public",
        source="seed:demo-public-faq",
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


def seed_demo_vault(
    repo: BrainRepository | None = None,
    *,
    tenant_id: str = DEMO_TENANT,
    force: bool = False,
    ingest_vault_files: bool = True,
) -> dict[str, Any]:
    """Create demo KB for delno-demo tenant. Safe to run on every container start."""
    own_conn = repo is None
    if repo is None:
        repo = BrainRepository(init_db())

    existing = repo.conn.execute(
        "SELECT id FROM documents WHERE tenant_id = ? AND id = ? AND status = 'active'",
        (tenant_id, DOC_COMPANY_ID),
    ).fetchone()

    if existing and not force:
        stats = repo.stats(tenant_id)
        return {
            "ok": True,
            "skipped": True,
            "tenant_id": tenant_id,
            "stats": stats,
        }

    _upsert_company_doc(repo, tenant_id=tenant_id)
    _upsert_public_faq(repo, tenant_id=tenant_id)

    vault_result: dict[str, Any] | None = None
    if ingest_vault_files:
        from pathlib import Path

        vault_path = Path(__file__).resolve().parents[2] / "vault" / "delno-demo"
        if vault_path.exists():
            vault_result = ingest_vault(repo, tenant_id=tenant_id, vault_path=vault_path, limit=50)

    stats = repo.stats(tenant_id)
    out: dict[str, Any] = {
        "ok": True,
        "seeded": True,
        "tenant_id": tenant_id,
        "markers": {"company": MARKER_COMPANY, "public": MARKER_PUBLIC},
        "stats": stats,
    }
    if vault_result:
        out["vault_ingest"] = vault_result
    if own_conn:
        repo.conn.commit()
    return out


def verify_demo_search(repo: BrainRepository, *, tenant_id: str = DEMO_TENANT) -> dict[str, Any]:
    """Smoke: owner sees company; guest sees public only; provenance present."""
    owner = Principal(principal_id="service:text-owner", tenant_id=tenant_id)
    guest = Principal(principal_id="service:text-guest", tenant_id=tenant_id)
    search = BrainSearch(repo)

    owner_company = search.retrieve(owner, MARKER_COMPANY, mode="keyword")
    owner_public = search.retrieve(owner, MARKER_PUBLIC, mode="keyword")
    guest_company = search.retrieve(guest, MARKER_COMPANY, mode="keyword")
    guest_public = search.retrieve(guest, MARKER_PUBLIC, mode="keyword")

    def _has_marker(result: dict[str, Any], marker: str) -> bool:
        return marker in (result.get("text") or "")

    def _provenance_ok(result: dict[str, Any]) -> bool:
        matches = result.get("matches") or []
        if not matches:
            return False
        first = matches[0]
        return bool(first.get("source")) and bool(first.get("document_id"))

    return {
        "ok": True,
        "owner_company": _has_marker(owner_company, MARKER_COMPANY),
        "owner_public": _has_marker(owner_public, MARKER_PUBLIC),
        "guest_company_denied": not _has_marker(guest_company, MARKER_COMPANY),
        "guest_public": _has_marker(guest_public, MARKER_PUBLIC),
        "provenance": _provenance_ok(owner_company),
    }
