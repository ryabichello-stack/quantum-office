"""Short-lived scoped capability tokens for Hermes → DELNO MCP calls.

Long-lived tenant mcp_api_key must NOT be handed to the model for Nous runs.
Tokens are stored in tenant.settings["hermes_nous"]["run_tokens"] (hashed).
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.tenant import Tenant

TOKEN_PREFIX = "dnrt_"
DEFAULT_TTL_SEC = 30 * 60
MAX_TOOL_IDS = 128


@dataclass
class IssueRunTokenResult:
    token: str
    run_id: str
    expires_at: int
    tool_ids: list[str]
    knowledge_scopes: list[str]


def _settings(tenant: Tenant) -> dict[str, Any]:
    return dict(tenant.settings) if isinstance(tenant.settings, dict) else {}


def _nous_blob(tenant: Tenant) -> dict[str, Any]:
    settings = _settings(tenant)
    blob = settings.get("hermes_nous")
    return dict(blob) if isinstance(blob, dict) else {}


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_run_token(
    db: Session,
    ctx: TenantContext,
    *,
    run_id: str | None = None,
    tool_ids: list[str] | None = None,
    knowledge_scopes: list[str] | None = None,
    agent_id: str | None = None,
    ttl_sec: int = DEFAULT_TTL_SEC,
) -> IssueRunTokenResult:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    rid = (run_id or f"run_{secrets.token_hex(8)}").strip()
    tools = [t.strip() for t in (tool_ids or []) if str(t).strip()][:MAX_TOOL_IDS]
    scopes = [s.strip() for s in (knowledge_scopes or ["default"]) if str(s).strip()][:32]
    expires_at = int(time.time()) + max(60, int(ttl_sec))
    raw = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    entry = {
        "hash": _hash_token(raw),
        "run_id": rid,
        "tenant_id": str(ctx.tenant_id),
        "actor_user_id": str(ctx.user_id) if ctx.user_id else None,
        "agent_id": agent_id or "company_main",
        "role": ctx.role,
        "tool_ids": tools,
        "knowledge_scopes": scopes,
        "expires_at": expires_at,
        "revoked": False,
    }
    blob = _nous_blob(tenant)
    tokens = dict(blob.get("run_tokens") or {})
    # prune expired
    now = int(time.time())
    tokens = {
        k: v
        for k, v in tokens.items()
        if isinstance(v, dict) and int(v.get("expires_at") or 0) > now and not v.get("revoked")
    }
    tokens[entry["hash"][:16]] = entry
    blob["run_tokens"] = tokens
    settings = _settings(tenant)
    settings["hermes_nous"] = blob
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return IssueRunTokenResult(
        token=raw,
        run_id=rid,
        expires_at=expires_at,
        tool_ids=tools,
        knowledge_scopes=scopes,
    )


def verify_run_token(db: Session, raw: str) -> dict[str, Any] | None:
    raw = (raw or "").strip()
    if not raw.startswith(TOKEN_PREFIX):
        return None
    digest = _hash_token(raw)
    key = digest[:16]
    now = int(time.time())
    for tenant in db.query(Tenant).filter(Tenant.is_active.is_(True)).all():
        blob = _nous_blob(tenant)
        tokens = blob.get("run_tokens") or {}
        entry = tokens.get(key)
        if not isinstance(entry, dict):
            continue
        if entry.get("hash") != digest:
            continue
        if entry.get("revoked"):
            return None
        if int(entry.get("expires_at") or 0) <= now:
            return None
        if str(entry.get("tenant_id")) != str(tenant.id):
            return None
        out = dict(entry)
        out["tenant"] = tenant
        return out
    return None


def revoke_run_token(db: Session, ctx: TenantContext, *, run_id: str) -> bool:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    blob = _nous_blob(tenant)
    tokens = dict(blob.get("run_tokens") or {})
    changed = False
    for key, entry in list(tokens.items()):
        if isinstance(entry, dict) and entry.get("run_id") == run_id:
            entry = dict(entry)
            entry["revoked"] = True
            tokens[key] = entry
            changed = True
    if not changed:
        return False
    blob["run_tokens"] = tokens
    settings = _settings(tenant)
    settings["hermes_nous"] = blob
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    return True


def parse_tenant_id(entry: dict[str, Any]) -> UUID:
    return UUID(str(entry["tenant_id"]))
