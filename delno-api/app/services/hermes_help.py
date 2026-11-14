"""Hermes «Помощь» — freeze chat + office state for later analysis.

Owner taps Help when stuck in onboarding or Hermes misbehaves. We snapshot
the conversation and setup facts into ``hermes.help_request`` (platform_events)
without putting secrets in the payload.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message
from app.models.platform_event import PlatformEvent
from app.models.tenant import Tenant
from app.services.audit import write_audit
from app.services.events import emit_event
from app.services.tenant_vault import looks_like_credential_paste

HELP_EVENT = "hermes.help_request"
MAX_MESSAGES = 100
MAX_BODY_CHARS = 4000
RATE_LIMIT_PER_HOUR = 8

_SECRET_LINE = re.compile(
    r"(?i)(password|passwd|пароль|sip.?pass|api.?key|token|secret)\s*[:=]\s*\S+"
)


def _redact_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if looks_like_credential_paste(raw):
        return "[секрет — через форму, не в ленте]"
    cleaned = _SECRET_LINE.sub(r"\1: [redacted]", raw)
    if len(cleaned) > MAX_BODY_CHARS:
        cleaned = cleaned[:MAX_BODY_CHARS].rstrip() + "\n…[обрезано]"
    return cleaned


def _serialize_message(row: Message) -> dict[str, Any]:
    meta = row.meta if isinstance(row.meta, dict) else {}
    safe_meta: dict[str, Any] = {}
    for key in ("modality", "attachments", "engine", "tool_calls", "suggested_actions"):
        if key in meta:
            val = meta[key]
            # Drop huge attachment binaries if any slipped into meta.
            if key == "attachments" and isinstance(val, list):
                safe_meta[key] = [
                    {
                        "filename": (i or {}).get("filename"),
                        "content_type": (i or {}).get("content_type"),
                        "kind": (i or {}).get("kind"),
                        "size": (i or {}).get("size"),
                    }
                    for i in val
                    if isinstance(i, dict)
                ][:8]
            elif key == "tool_calls" and isinstance(val, list):
                safe_meta[key] = val[:20]
            else:
                safe_meta[key] = val
    return {
        "id": str(row.id),
        "role": row.role,
        "body": _redact_text(row.body or ""),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "meta": safe_meta,
    }


def _sanitize_loop(loop: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(loop, dict):
        return {}
    out = {
        "phase": loop.get("phase"),
        "kb_ok": loop.get("kb_ok"),
        "setup_complete": (loop.get("setup") or {}).get("setup_complete")
        if isinstance(loop.get("setup"), dict)
        else loop.get("setup_complete"),
        "setup_next": loop.get("setup_next"),
        "progress": (loop.get("setup") or {}).get("progress")
        if isinstance(loop.get("setup"), dict)
        else loop.get("progress"),
    }
    draft = loop.get("kb_draft") if isinstance(loop.get("kb_draft"), dict) else None
    if draft:
        body = str(draft.get("body") or "")
        out["kb_draft"] = {
            "status": draft.get("status"),
            "title": draft.get("title"),
            "chars": len(body),
            "body_preview": body[:1500] + ("…" if len(body) > 1500 else ""),
            "source_url": draft.get("source_url"),
        }
    return out


def _sanitize_setup(setup: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(setup, dict):
        return {}
    checks_raw = setup.get("checks") if isinstance(setup.get("checks"), dict) else {}
    checks: dict[str, Any] = {}
    for key, val in checks_raw.items():
        if not isinstance(val, dict):
            continue
        detail = val.get("detail")
        # Drop credential-ish detail blobs.
        safe_detail = detail
        if isinstance(detail, dict):
            safe_detail = {
                k: v
                for k, v in detail.items()
                if k
                not in (
                    "password",
                    "login",
                    "token",
                    "api_key",
                    "secret",
                )
            }
        checks[key] = {
            "ok": bool(val.get("ok")),
            "title": val.get("title"),
            "detail": safe_detail,
        }
    return {
        "setup_complete": bool(setup.get("setup_complete")),
        "progress": setup.get("progress"),
        "message_ru": setup.get("message_ru"),
        "next_steps": (setup.get("next_steps") or [])[:6],
        "checks": checks,
    }


def _rate_limited(db: Session, tenant_id: uuid.UUID) -> bool:
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    n = (
        db.query(PlatformEvent)
        .filter(
            PlatformEvent.tenant_id == tenant_id,
            PlatformEvent.event_type == HELP_EVENT,
            PlatformEvent.created_at >= since,
        )
        .count()
    )
    return n >= RATE_LIMIT_PER_HOUR


def capture_help_request(
    db: Session,
    ctx: TenantContext,
    *,
    conversation_id: uuid.UUID | None = None,
    note: str | None = None,
    client_meta: dict[str, Any] | None = None,
    channel: str = "hermes",
) -> dict[str, Any]:
    """Freeze chat + office facts into a durable help ticket."""
    if _rate_limited(db, ctx.tenant_id):
        return {
            "ok": False,
            "error": "rate_limited",
            "message": (
                "Слишком много обращений за час. Напишите в поддержку DELNO "
                "или подождите и нажмите «Помощь» снова."
            ),
        }

    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one_or_none()
    conv: Conversation | None = None
    if conversation_id:
        conv = (
            db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.tenant_id == ctx.tenant_id,
            )
            .one_or_none()
        )
        if conv is None:
            return {
                "ok": False,
                "error": "conversation_not_found",
                "message": "Диалог не найден — откройте Hermes и нажмите «Помощь» ещё раз.",
            }
    else:
        # Latest hermes/cabinet conversation for this tenant.
        conv = (
            db.query(Conversation)
            .filter(
                Conversation.tenant_id == ctx.tenant_id,
                Conversation.channel.in_(("hermes", "cabinet", "operator", "onboarding")),
            )
            .order_by(Conversation.updated_at.desc())
            .first()
        )

    messages: list[dict[str, Any]] = []
    if conv:
        rows = (
            db.query(Message)
            .filter(
                Message.conversation_id == conv.id,
                Message.tenant_id == ctx.tenant_id,
            )
            .order_by(Message.created_at.desc())
            .limit(MAX_MESSAGES)
            .all()
        )
        messages = [_serialize_message(m) for m in reversed(rows)]

    setup: dict[str, Any] = {}
    loop: dict[str, Any] = {}
    try:
        from app.services import hermes_ops
        from app.services.hermes_nous.onboarding import get_office_loop

        setup = hermes_ops.office_setup_status(db, ctx) or {}
        loop = get_office_loop(db, ctx) or {}
    except Exception as exc:  # noqa: BLE001
        setup = {"error": type(exc).__name__}

    ticket_id = str(uuid.uuid4())
    note_clean = _redact_text((note or "").strip())[:2000]
    client = client_meta if isinstance(client_meta, dict) else {}
    # Whitelist client fields only.
    client_safe = {
        k: client.get(k)
        for k in (
            "path",
            "href",
            "user_agent",
            "viewport",
            "locale",
            "timezone",
            "compact",
            "lines_on_screen",
        )
        if client.get(k) is not None
    }

    payload = {
        "ticket_id": ticket_id,
        "status": "open",
        "note": note_clean,
        "channel": channel or (conv.channel if conv else "hermes"),
        "tenant_slug": tenant.slug if tenant else None,
        "tenant_name": tenant.name if tenant else None,
        "conversation_id": str(conv.id) if conv else None,
        "message_count": len(messages),
        "messages": messages,
        "office_loop": _sanitize_loop(loop),
        "setup": _sanitize_setup(setup),
        "client": client_safe,
        "role": ctx.role,
    }

    event = emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type=HELP_EVENT,
        category="operational",
        source="hermes.help",
        payload=payload,
    )
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="office.alert",
        category="operational",
        source="hermes.help",
        payload={
            "severity": "help",
            "title": "Клиент нажал «Помощь»",
            "message": note_clean or "Застрял в онбординге / Hermes работает не так",
            "ticket_id": ticket_id,
            "conversation_id": str(conv.id) if conv else None,
            "event_id": str(event.id),
        },
    )
    write_audit(
        db,
        ctx,
        action="hermes.help_request",
        actor=ctx.role or "tenant_owner",
        resource=ticket_id,
        new_value={
            "event_id": str(event.id),
            "conversation_id": str(conv.id) if conv else None,
            "message_count": len(messages),
        },
        detail=note_clean or None,
    )

    # Freeze marker on the conversation meta for later lookup.
    if conv:
        meta = dict(conv.meta) if isinstance(conv.meta, dict) else {}
        help_list = list(meta.get("help_tickets") or [])
        help_list.append(
            {
                "ticket_id": ticket_id,
                "event_id": str(event.id),
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        meta["help_tickets"] = help_list[-20:]
        meta["last_help_ticket_id"] = ticket_id
        conv.meta = meta
        try:
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(conv, "meta")
        except Exception:  # noqa: BLE001
            pass
        db.add(conv)
        # Visible ack in the chat transcript (also part of the frozen trail).
        db.add(
            Message(
                tenant_id=ctx.tenant_id,
                conversation_id=conv.id,
                role="assistant",
                body=(
                    "Зафиксировал переписку и состояние кабинета для команды DELNO "
                    f"(тикет `{ticket_id[:8]}`). Мы разберём, что пошло не так, "
                    "и поправим. Можете коротко дописать в чат, что ожидали."
                ),
                meta={"kind": "help_ack", "ticket_id": ticket_id, "event_id": str(event.id)},
            )
        )

    db.commit()
    return {
        "ok": True,
        "ticket_id": ticket_id,
        "event_id": str(event.id),
        "conversation_id": str(conv.id) if conv else None,
        "message_count": len(messages),
        "message": (
            "Спасибо — снимок переписки и состояния офиса сохранён. "
            f"Номер обращения: {ticket_id[:8]}. Команда DELNO разберёт и поправит."
        ),
    }


def list_help_requests(
    db: Session,
    *,
    tenant_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List help tickets (platform admin or single-tenant)."""
    q = db.query(PlatformEvent).filter(PlatformEvent.event_type == HELP_EVENT)
    if tenant_id:
        q = q.filter(PlatformEvent.tenant_id == tenant_id)
    rows = q.order_by(PlatformEvent.created_at.desc()).limit(min(limit, 200)).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        st = str(payload.get("status") or "open")
        if status and st != status:
            continue
        items.append(
            {
                "event_id": str(row.id),
                "ticket_id": payload.get("ticket_id") or str(row.id),
                "tenant_id": str(row.tenant_id) if row.tenant_id else None,
                "tenant_slug": payload.get("tenant_slug"),
                "tenant_name": payload.get("tenant_name"),
                "status": st,
                "note": payload.get("note") or "",
                "conversation_id": payload.get("conversation_id"),
                "message_count": payload.get("message_count") or 0,
                "office_loop": payload.get("office_loop") or {},
                "setup_progress": (payload.get("setup") or {}).get("progress"),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                # Full messages only when listing a single tenant (owner/admin drill-down).
                "messages": payload.get("messages") if tenant_id else None,
                "has_messages": bool(payload.get("messages")),
            }
        )
    return items


def get_help_request(
    db: Session,
    *,
    ticket_id: str,
    tenant_id: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    q = db.query(PlatformEvent).filter(PlatformEvent.event_type == HELP_EVENT)
    if tenant_id:
        q = q.filter(PlatformEvent.tenant_id == tenant_id)
    for row in q.order_by(PlatformEvent.created_at.desc()).limit(500).all():
        payload = row.payload if isinstance(row.payload, dict) else {}
        tid = str(payload.get("ticket_id") or row.id)
        if tid == ticket_id or tid.startswith(ticket_id) or str(row.id) == ticket_id:
            return {
                "event_id": str(row.id),
                "tenant_id": str(row.tenant_id) if row.tenant_id else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                **payload,
            }
    return None
