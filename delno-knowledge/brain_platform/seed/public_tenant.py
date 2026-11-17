"""Idempotent public KB seed for tenant delno-public (marketing bots / widget)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_platform.db.connection import init_db
from brain_platform.db.repository import BrainRepository
from brain_platform.ingest.vault import ingest_vault

PUBLIC_TENANT = "delno-public"
MARKER_PUBLIC = "DELNO_PUBLIC_KB_v1_2026_11_17"


def _publication() -> dict[str, Any]:
    return {
        "status": "published",
        "approved": True,
        "approved_by": "user:admin",
        "approved_at": datetime(2026, 11, 17, tzinfo=timezone.utc).isoformat(),
        "public_version": 1,
    }


def _upsert_marker(repo: BrainRepository, *, tenant_id: str) -> None:
    repo.upsert_document(
        doc_id=f"doc-{tenant_id}-public-marker",
        tenant_id=tenant_id,
        title="DELNO — публичная база (маркер)",
        doc_type="faq",
        body=(
            "DELNO — ИИ-секретарь первой линии: консультации, запись, заявки. "
            f"Публичный маркер {MARKER_PUBLIC}. "
            "Сайт https://dlno.ru, office@dlno.ru, 8 800 555-94-18."
        ),
        visibility="public",
        channels=["office-assistant"],
        index_zone="public",
        source="seed:delno-public-marker",
        classification={"level": "public"},
        ai_processing={
            "external_llm_allowed": True,
            "external_embedding_allowed": True,
            "local_processing_required": False,
        },
        publication=_publication(),
    )


def seed_public_tenant(
    repo: BrainRepository | None = None,
    *,
    tenant_id: str = PUBLIC_TENANT,
    force: bool = False,
    ingest_vault_files: bool = True,
) -> dict[str, Any]:
    """Create/refresh public KB for delno-public. Safe on every container start."""
    own_conn = repo is None
    if repo is None:
        repo = BrainRepository(init_db())

    marker_id = f"doc-{tenant_id}-public-marker"
    existing = repo.conn.execute(
        "SELECT id, body FROM documents WHERE tenant_id = ? AND id = ? AND status = 'active'",
        (tenant_id, marker_id),
    ).fetchone()
    needs_marker = force or not existing or MARKER_PUBLIC not in str(existing["body"] or "")
    if needs_marker:
        _upsert_marker(repo, tenant_id=tenant_id)

    vault_result: dict[str, Any] | None = None
    if ingest_vault_files:
        vault_path = Path(__file__).resolve().parents[2] / "vault" / tenant_id
        if vault_path.exists():
            vault_result = ingest_vault(
                repo, tenant_id=tenant_id, vault_path=vault_path, limit=100
            )

    stats = repo.stats(tenant_id)
    out: dict[str, Any] = {
        "ok": True,
        "tenant_id": tenant_id,
        "marker": MARKER_PUBLIC,
        "stats": stats,
        "marker_upserted": needs_marker,
    }
    if vault_result:
        out["vault_ingest"] = vault_result
    if own_conn:
        repo.conn.commit()
    return out
