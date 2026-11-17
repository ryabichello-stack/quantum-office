"""Small, durable recall of completed Owner Hermes turns.

The store is separate from Hermes's profile files: it survives worker replacement
and is always filtered by both tenant and actor. It is not a source of tool grants.
"""

from __future__ import annotations

import json
import os
import re

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag
from app.models.hermes_owner_turn import HermesOwnerTurn

_SECRET = re.compile(
    r"(?i)(\b(?:password|пароль|api[_-]?key|secret|token|токен)\b\s*[:=]\s*)\S+"
    r"|\bBearer\s+\S+|\bdmcp_[A-Za-z0-9_-]+"
)


def owner_memory_enabled(db: Session, ctx: TenantContext) -> bool:
    if (os.environ.get("DELNO_OWNER_MEMORY_ENABLED") or "").strip().lower() not in ("1", "true", "yes"):
        return False
    return bool(db.scalar(
        select(FeatureFlag.enabled)
        .where(FeatureFlag.tenant_id == ctx.tenant_id,
               FeatureFlag.flag_key == "hermes_owner_memory")
    ))


def _safe_text(value: str, limit: int) -> str:
    return _SECRET.sub("[секрет скрыт]", str(value or "").strip()[:limit])


def recent_owner_context(db: Session, ctx: TenantContext, *, limit: int = 6) -> str:
    """Return bounded previous turns belonging to this actor in this company."""
    if ctx.user_id is None:
        return ""
    rows = db.scalars(
        select(HermesOwnerTurn)
        .where(HermesOwnerTurn.tenant_id == ctx.tenant_id,
               HermesOwnerTurn.user_id == ctx.user_id)
        .order_by(HermesOwnerTurn.created_at.desc(), HermesOwnerTurn.id.desc())
        .limit(min(max(limit, 1), 12))
    ).all()
    if not rows:
        return ""
    excerpts = [
        {"date": row.created_at.isoformat() if row.created_at else "",
         "question": row.request_text[:1000], "answer": row.response_text[:1600]}
        for row in reversed(rows)
    ]
    encoded = json.dumps(excerpts, ensure_ascii=False)
    while len(encoded) > 6000 and excerpts:
        excerpts.pop(0)
        encoded = json.dumps(excerpts, ensure_ascii=False)
    return encoded


def remember_owner_turn(
    db: Session, ctx: TenantContext, *, session_id: str, run_id: str,
    request_text: str, response_text: str,
) -> bool:
    """Persist a completed nonempty turn once; retries cannot duplicate it."""
    if ctx.user_id is None or not session_id.startswith(f"{ctx.tenant_slug}:") or not run_id:
        return False
    request = _safe_text(request_text, 2000)
    response = _safe_text(response_text, 4000)
    if not request or not response:
        return False
    try:
        with db.begin_nested():
            db.add(HermesOwnerTurn(
                tenant_id=ctx.tenant_id, user_id=ctx.user_id, session_id=session_id[:200],
                run_id=run_id[:120], request_text=request, response_text=response,
            ))
            db.flush()
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def list_owner_turns(db: Session, ctx: TenantContext, *, limit: int = 30) -> list[HermesOwnerTurn]:
    if ctx.user_id is None:
        return []
    return list(db.scalars(
        select(HermesOwnerTurn)
        .where(HermesOwnerTurn.tenant_id == ctx.tenant_id,
               HermesOwnerTurn.user_id == ctx.user_id)
        .order_by(HermesOwnerTurn.created_at.desc(), HermesOwnerTurn.id.desc())
        .limit(min(max(limit, 1), 50))
    ).all())


def clear_owner_turns(db: Session, ctx: TenantContext) -> int:
    if ctx.user_id is None:
        return 0
    result = db.execute(
        delete(HermesOwnerTurn)
        .where(HermesOwnerTurn.tenant_id == ctx.tenant_id,
               HermesOwnerTurn.user_id == ctx.user_id)
    )
    db.commit()
    return int(result.rowcount or 0)
