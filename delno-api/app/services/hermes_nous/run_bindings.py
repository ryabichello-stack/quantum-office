"""Server-side Hermes run ↔ scoped MCP token bindings.

Hermes containers must not use a long-lived company DELNO_MCP_KEY for office tools.
When the upstream MCP client cannot forward X-Delno-Run-Token, the MCP proxy
resolves the active binding by run_id (+ optional worker key) and injects scope.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.hermes_runtime import HermesRunBinding


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def bind_run_token(
    db: Session,
    *,
    tenant_id: UUID,
    profile_id: str,
    worker_id: str | None,
    run_id: str,
    session_id: str | None,
    actor_user_id: UUID | None,
    agent_id: str,
    raw_token: str,
    tool_ids: list[str],
    expires_at_unix: int,
) -> HermesRunBinding:
    existing = db.query(HermesRunBinding).filter(HermesRunBinding.run_id == run_id).one_or_none()
    exp = datetime.fromtimestamp(int(expires_at_unix), tz=timezone.utc)
    if existing:
        existing.token_hash = _hash_token(raw_token)
        existing.tool_ids = list(tool_ids or [])
        existing.expires_at = exp
        existing.revoked = False
        existing.session_id = session_id
        existing.worker_id = worker_id
        existing.profile_id = profile_id
        existing.actor_user_id = actor_user_id
        existing.agent_id = agent_id
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    row = HermesRunBinding(
        tenant_id=tenant_id,
        profile_id=profile_id,
        worker_id=worker_id,
        run_id=run_id,
        session_id=session_id,
        actor_user_id=actor_user_id,
        agent_id=agent_id or "company_main",
        token_hash=_hash_token(raw_token),
        tool_ids=list(tool_ids or []),
        expires_at=exp,
        revoked=False,
        note="issued_at_create_run",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def lookup_binding(db: Session, *, run_id: str) -> HermesRunBinding | None:
    row = db.query(HermesRunBinding).filter(HermesRunBinding.run_id == run_id).one_or_none()
    if not row or row.revoked:
        return None
    now = datetime.now(timezone.utc)
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp <= now:
        return None
    return row


def revoke_binding(db: Session, *, run_id: str) -> bool:
    row = db.query(HermesRunBinding).filter(HermesRunBinding.run_id == run_id).one_or_none()
    if not row:
        return False
    row.revoked = True
    db.add(row)
    db.commit()
    return True


def binding_to_auth_hints(row: HermesRunBinding) -> dict[str, Any]:
    return {
        "tenant_id": str(row.tenant_id),
        "profile_id": row.profile_id,
        "worker_id": row.worker_id,
        "run_id": row.run_id,
        "session_id": row.session_id,
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "agent_id": row.agent_id,
        "tool_ids": list(row.tool_ids or []),
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }
