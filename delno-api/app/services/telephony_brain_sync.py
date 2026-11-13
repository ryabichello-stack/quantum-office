"""Sync ended CallSession → Second Brain operational memory."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.call_session import CallSession
from app.models.tenant import Tenant
from app.services.knowledge_documents import _brain_upsert


def _call_document_id(tenant_slug: str, session_id: str) -> str:
    return f"doc-{tenant_slug}-call-{session_id}"


def build_call_memory_body(session: CallSession) -> str:
    direction = "Входящий" if session.direction == "inbound" else "Исходящий"
    lines = [
        f"# {direction} звонок",
        "",
        f"- Session: `{session.id}`",
        f"- Conversation: `{session.conversation_id}`",
        f"- From: `{session.from_e164 or '—'}`",
        f"- To / DID: `{session.to_e164 or session.did_e164 or '—'}`",
        f"- Outcome: `{session.outcome or '—'}`",
        f"- Duration: `{session.duration_sec or 0}` sec",
        "",
    ]
    if session.summary:
        lines.extend(["## Summary", "", session.summary.strip(), ""])
    if session.transcript:
        lines.extend(["## Transcript", "", session.transcript.strip(), ""])
    meta = session.meta or {}
    if meta.get("recording_url"):
        lines.extend(["## Recording", "", str(meta["recording_url"]), ""])
    return "\n".join(lines).strip() + "\n"


def sync_call_session_to_brain(db: Session, session: CallSession) -> dict[str, Any]:
    """Upsert company-private call memory doc when summary or transcript exists."""
    if not (session.summary or session.transcript):
        return {"ok": False, "skipped": True, "reason": "no_content"}

    tenant = db.query(Tenant).filter(Tenant.id == session.tenant_id).one_or_none()
    if not tenant:
        return {"ok": False, "error": "tenant_missing"}

    direction = "Входящий" if session.direction == "inbound" else "Исходящий"
    peer = session.from_e164 if session.direction == "inbound" else session.to_e164
    title = f"{direction} звонок {peer or ''} → {session.did_e164 or ''}".strip()
    doc_id = _call_document_id(tenant.slug, str(session.id))
    body = build_call_memory_body(session)

    return _brain_upsert(
        db,
        tenant,
        title=title[:200],
        body=body,
        visibility="company",
        source="telephony.call",
        document_id=doc_id,
        status="published",
        index_zone="private",
        event_type="knowledge.call_memory_upserted",
    )
