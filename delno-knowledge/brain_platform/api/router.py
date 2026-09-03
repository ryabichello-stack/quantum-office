"""Second Brain HTTP API — does NOT replace legacy /api/knowledge/*."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from brain_platform.auth import DEFAULT_TENANT, principal_from_headers, require_brain_enabled
from brain_platform.db.factory import get_brain_repo, reset_repo_singleton
from brain_platform.ingest.files import ingest_files
from brain_platform.ingest.legacy_faq import ingest_legacy_faq
from brain_platform.ingest.mail import (
    imap_account_usernames,
    imap_configured,
    ingest_mailbox,
)
from brain_platform.search.engine import BrainSearch

router = APIRouter(prefix="/api/brain", tags=["second-brain"])

_repo = None
_search: BrainSearch | None = None


def get_repo():
    global _repo, _search
    if _repo is None:
        reset_repo_singleton()
        _repo = get_brain_repo()
        _search = BrainSearch(_repo)
    return _repo


def get_search() -> BrainSearch:
    get_repo()
    assert _search is not None
    return _search


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(default=8, ge=1, le=20)
    max_chars: int = Field(default=6000, ge=500, le=20000)
    mode: str = Field(default="hybrid", description="keyword | semantic | hybrid")
    tenant_id: Optional[str] = None  # ignored unless matches token; mismatch → 403


class GetRequest(BaseModel):
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    max_chars: int = Field(default=12000, ge=200, le=50000)
    tenant_id: Optional[str] = None


class ContactQuery(BaseModel):
    q: str = ""
    email: str = ""
    phone: str = ""
    company: str = ""
    limit: int = Field(default=20, ge=1, le=100)
    tenant_id: Optional[str] = None


class ThreadsQuery(BaseModel):
    q: str = ""
    since: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)
    tenant_id: Optional[str] = None


class IngestRequest(BaseModel):
    sources: list[str] = Field(default_factory=lambda: ["faq", "files", "mail"])
    mail_limit: int = Field(default=100, ge=1, le=1000)
    file_limit: int = Field(default=500, ge=1, le=5000)
    embed_backfill: int = Field(default=0, ge=0, le=5000)
    tenant_id: Optional[str] = None


class GraphExpandRequest(BaseModel):
    q: str = ""
    entity_id: Optional[str] = None
    depth: int = Field(default=1, ge=1, le=2)
    limit: int = Field(default=40, ge=1, le=100)
    tenant_id: Optional[str] = None


class GraphRebuildRequest(BaseModel):
    tenant_id: Optional[str] = None


class TenantSettingsSyncRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    tenant_name: str = Field(..., min_length=1, max_length=255)
    settings: dict = Field(default_factory=dict)
    assistant_name: str = Field(default="DELNO", max_length=64)


class DocumentUpsertRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    document_id: str = Field(..., min_length=4, max_length=120)
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=20, max_length=50000)
    visibility: str = Field(default="public", max_length=32)
    channels: list[str] = Field(default_factory=lambda: ["office-assistant"])
    source: str = Field(default="tenant:document", max_length=120)


def _principal(
    x_principal_id: Optional[str],
    x_tenant_id: Optional[str],
    x_groups: Optional[str],
    x_user_id: Optional[str],
    x_admin: Optional[str],
    body_tenant: Optional[str],
):
    return principal_from_headers(
        x_principal_id=x_principal_id,
        x_tenant_id=x_tenant_id,
        x_groups=x_groups,
        x_user_id=x_user_id,
        x_admin=x_admin,
        body_tenant_id=body_tenant,
    )


@router.get("/health")
def brain_health():
    require_brain_enabled()
    repo = get_repo()
    tenant = DEFAULT_TENANT
    return {
        "ok": True,
        "service": "second-brain",
        "tenant_default": tenant,
        "imap_configured": imap_configured(),
        "imap_accounts": imap_account_usernames(),
        "stats": repo.stats(tenant),
        "legacy_knowledge_untouched": True,
    }


@router.post("/search")
def brain_search(
    req: SearchRequest,
    x_principal_id: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
    x_groups: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_admin: Optional[str] = Header(None),
):
    require_brain_enabled()
    principal = _principal(
        x_principal_id, x_tenant_id, x_groups, x_user_id, x_admin, req.tenant_id
    )
    return get_search().retrieve(
        principal,
        req.query,
        limit=req.limit,
        max_chars=req.max_chars,
        mode=req.mode,
    )


@router.post("/get")
def brain_get(
    req: GetRequest,
    x_principal_id: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
    x_groups: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_admin: Optional[str] = Header(None),
):
    require_brain_enabled()
    if not req.document_id and not req.chunk_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="document_id_or_chunk_id_required")
    principal = _principal(
        x_principal_id, x_tenant_id, x_groups, x_user_id, x_admin, req.tenant_id
    )
    # Prefer SQLite for get (authoritative write store); HybridBrainRepo exposes it
    repo = get_repo()
    sqlite_repo = getattr(repo, "sqlite", repo)
    doc = sqlite_repo.get_document(
        principal,
        document_id=req.document_id,
        chunk_id=req.chunk_id,
        max_chars=req.max_chars,
    )
    if not doc:
        return {"ok": False, "denied_or_missing": True}
    return doc


@router.post("/contacts/find")
def brain_find_contacts(
    req: ContactQuery,
    x_principal_id: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
    x_groups: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_admin: Optional[str] = Header(None),
):
    require_brain_enabled()
    principal = _principal(
        x_principal_id, x_tenant_id, x_groups, x_user_id, x_admin, req.tenant_id
    )
    contacts = get_repo().find_contacts(
        principal,
        q=req.q,
        email=req.email,
        phone=req.phone,
        company=req.company,
        limit=req.limit,
    )
    return {"ok": True, "count": len(contacts), "contacts": contacts}


@router.post("/threads/list")
def brain_list_threads(
    req: ThreadsQuery,
    x_principal_id: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
    x_groups: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_admin: Optional[str] = Header(None),
):
    require_brain_enabled()
    principal = _principal(
        x_principal_id, x_tenant_id, x_groups, x_user_id, x_admin, req.tenant_id
    )
    threads = get_repo().list_threads(
        principal, q=req.q, since=req.since, limit=req.limit
    )
    return {"ok": True, "count": len(threads), "threads": threads}


@router.post("/ingest/run")
def brain_ingest_run(
    req: IngestRequest,
    x_principal_id: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
    x_groups: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_admin: Optional[str] = Header(None),
):
    """Run ingest jobs. Requires cursor-admin + personal admin auth (or local unprotected lab)."""
    require_brain_enabled()
    principal = _principal(
        x_principal_id, x_tenant_id, x_groups, x_user_id, x_admin, req.tenant_id
    )
    allow_unauth_local = os.getenv("BRAIN_ALLOW_LOCAL_INGEST", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    if not (
        (principal.principal_id == "service:cursor-admin" and principal.is_admin)
        or allow_unauth_local
    ):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="ingest_forbidden")

    tenant = principal.tenant_id
    repo = get_repo()
    results = {}
    if "faq" in req.sources:
        results["faq"] = ingest_legacy_faq(repo, tenant_id=tenant)
    if "vault" in req.sources:
        from brain_platform.ingest.vault import ingest_vault

        sqlite_repo = getattr(repo, "sqlite", repo)
        results["vault"] = ingest_vault(sqlite_repo, tenant_id=tenant)
    if "files" in req.sources:
        results["files"] = ingest_files(repo, tenant_id=tenant, limit=req.file_limit)
    if "mail" in req.sources:
        results["mail"] = ingest_mailbox(
            repo, tenant_id=tenant, direction="both", limit=req.mail_limit
        )
    if req.embed_backfill > 0:
        results["embed_backfill"] = repo.backfill_embeddings(
            tenant_id=tenant, limit=req.embed_backfill, only_missing=True
        )
    # Keep Postgres search index fresh when dual-write may have gaps / batch jobs
    if (os.getenv("BRAIN_DATABASE_URL") or "").strip():
        try:
            from brain_platform.db.connection import default_db_path
            from brain_platform.db.migrate_sqlite_to_pg import migrate
            from brain_platform.db.pg import database_url

            results["sync_pg"] = migrate(str(default_db_path()), database_url(), truncate=True)
        except Exception as exc:  # noqa: BLE001
            results["sync_pg"] = {"ok": False, "error": str(exc)}
    return {"ok": True, "results": results, "stats": repo.stats(tenant)}


@router.post("/tenant/settings-sync")
def brain_tenant_settings_sync(
    req: TenantSettingsSyncRequest,
    x_principal_id: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
    x_groups: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_admin: Optional[str] = Header(None),
):
    """E1.8 — upsert office-assistant KB doc from tenant cabinet settings."""
    require_brain_enabled()
    principal = _principal(
        x_principal_id, x_tenant_id, x_groups, x_user_id, x_admin, req.tenant_id
    )
    allow_service = os.getenv("BRAIN_ALLOW_SERVICE_INGEST", "true").lower() in ("1", "true", "yes")
    allowed = principal.principal_id in (
        "service:cursor-admin",
        "service:delno-admin",
        "service:delno-api",
    ) or allow_service
    if not allowed:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="settings_sync_forbidden")

    tenant = req.tenant_id
    legal = req.settings.get("legal") if isinstance(req.settings, dict) else {}
    legal = legal if isinstance(legal, dict) else {}
    lines = [
        f"# {req.tenant_name}",
        "",
        f"ИИ-ассистент: **{req.assistant_name}**",
        "",
        "## Профиль компании",
    ]
    if legal.get("name"):
        lines.append(f"- Наименование: {legal.get('name')}")
    if legal.get("inn"):
        lines.append(f"- ИНН: {legal.get('inn')}")
    if legal.get("ogrn"):
        lines.append(f"- ОГРН: {legal.get('ogrn')}")
    if legal.get("address"):
        lines.append(f"- Адрес: {legal.get('address')}")
    if legal.get("management"):
        lines.append(f"- Руководитель: {legal.get('management')}")
    locale = req.settings.get("locale") if isinstance(req.settings, dict) else None
    if locale:
        lines.append(f"- Локаль: {locale}")
    body = "\n".join(lines).strip()
    if len(body) < 40:
        body += "\n\nНастройки tenant синхронизированы из кабинета DELNO (office-assistant)."

    repo = get_repo()
    doc_id = f"doc-{tenant}-tenant-settings"
    result = repo.upsert_document(
        doc_id=doc_id,
        tenant_id=tenant,
        title=f"{req.tenant_name} — настройки кабинета",
        doc_type="settings",
        body=body,
        visibility="company",
        channels=["office-assistant"],
        index_zone="private",
        source="tenant:settings-sync",
    )
    repo.conn.commit()
    return {"ok": True, "document_id": doc_id, "upsert": result, "stats": repo.stats(tenant)}


@router.post("/documents/upsert")
def brain_document_upsert(
    req: DocumentUpsertRequest,
    x_principal_id: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
    x_groups: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_admin: Optional[str] = Header(None),
):
    """P2.2 — upsert tenant KB document (public or company visibility)."""
    require_brain_enabled()
    principal = _principal(
        x_principal_id, x_tenant_id, x_groups, x_user_id, x_admin, req.tenant_id
    )
    allow_service = os.getenv("BRAIN_ALLOW_SERVICE_INGEST", "true").lower() in ("1", "true", "yes")
    allowed = principal.principal_id in (
        "service:cursor-admin",
        "service:delno-admin",
        "service:delno-api",
    ) or allow_service
    if not allowed:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="document_upsert_forbidden")

    tenant = req.tenant_id
    visibility = req.visibility if req.visibility in ("public", "company", "team") else "company"
    index_zone = "public" if visibility == "public" else "private"
    repo = get_repo()
    result = repo.upsert_document(
        doc_id=req.document_id,
        tenant_id=tenant,
        title=req.title,
        doc_type="doc",
        body=req.body.strip(),
        visibility=visibility,
        channels=req.channels,
        index_zone=index_zone,
        source=req.source,
    )
    repo.conn.commit()
    return {"ok": True, "document_id": req.document_id, "upsert": result, "stats": repo.stats(tenant)}


@router.get("/ingest/status")
def brain_ingest_status(
    x_principal_id: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
):
    require_brain_enabled()
    repo = get_repo()
    keys = ["faq:last", "files:last", "mail:both:last", "mail:inbound:last", "mail:outbound:last"]
    state = {k: repo.get_ingest_state(k) for k in keys}
    return {
        "ok": True,
        "state": state,
        "stats": repo.stats(DEFAULT_TENANT),
        "imap_configured": imap_configured(),
        "imap_accounts": imap_account_usernames(),
    }


@router.post("/graph/expand")
def brain_graph_expand(
    req: GraphExpandRequest,
    x_principal_id: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
    x_groups: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_admin: Optional[str] = Header(None),
):
    require_brain_enabled()
    principal = _principal(
        x_principal_id, x_tenant_id, x_groups, x_user_id, x_admin, req.tenant_id
    )
    from brain_platform.graph.store import GraphStore

    # Graph writes/reads live on SQLite (sync-pg copies to Postgres)
    sqlite_repo = get_repo()
    conn = getattr(sqlite_repo, "sqlite", sqlite_repo).conn if hasattr(sqlite_repo, "sqlite") else sqlite_repo.conn
    return GraphStore(conn).expand(
        principal,
        entity_id=req.entity_id,
        q=req.q,
        depth=req.depth,
        limit=req.limit,
    )


@router.post("/graph/rebuild")
def brain_graph_rebuild(
    req: GraphRebuildRequest,
    x_principal_id: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
    x_groups: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_admin: Optional[str] = Header(None),
):
    require_brain_enabled()
    principal = _principal(
        x_principal_id, x_tenant_id, x_groups, x_user_id, x_admin, req.tenant_id
    )
    allow_unauth_local = os.getenv("BRAIN_ALLOW_LOCAL_INGEST", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    if not (
        (principal.principal_id == "service:cursor-admin" and principal.is_admin)
        or allow_unauth_local
    ):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="graph_rebuild_forbidden")

    from brain_platform.graph.rebuild import rebuild_graph_from_corpus

    repo = get_repo()
    sqlite_repo = getattr(repo, "sqlite", repo)
    out = rebuild_graph_from_corpus(sqlite_repo, tenant_id=principal.tenant_id)
    # refresh Postgres graph copy when configured
    if (os.getenv("BRAIN_DATABASE_URL") or "").strip():
        try:
            from brain_platform.db.connection import default_db_path
            from brain_platform.db.migrate_sqlite_to_pg import migrate
            from brain_platform.db.pg import database_url

            out["sync_pg"] = migrate(str(default_db_path()), database_url(), truncate=True)
        except Exception as exc:  # noqa: BLE001
            out["sync_pg"] = {"ok": False, "error": str(exc)}
    return {"ok": True, "graph": out}
