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
from brain_platform.ingest.mail import imap_configured, ingest_mailbox
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
    return {"ok": True, "results": results, "stats": repo.stats(tenant)}


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
    }
