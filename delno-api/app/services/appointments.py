"""One meeting flow for the phone secretary and messenger bots.

Check free time → if busy, offer another slot → if free, book, create a video
link, email the client. Later: move, confirm, or cancel the same record.
Providers are mocked in tests; live CalDAV/SMTP/VCS go through connectors.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.connectors import get_connector
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.connectors import connector_config_for
from app.services.connector_connect import mail_delivery_access, conference_delivery_access
from app.services.tenant_broker_access import apply_access


def _calendar_config(db: Session, ctx: TenantContext, source: str | None) -> tuple[dict[str, Any] | None, str | None]:
    return apply_access(
        db,
        ctx,
        dict(connector_config_for(db, ctx, "calendar")),
        kind="calendar",
        source=source,
    )

_OPEN = {"booked", "confirmed", "rescheduled"}
current_channel: ContextVar[str] = ContextVar("delno_conduct_channel", default="messenger")
current_external_user_id: ContextVar[str | None] = ContextVar("delno_channel_user_id", default=None)
current_verified_phone: ContextVar[str | None] = ContextVar("delno_verified_caller_phone", default=None)


def _settings(tenant: Tenant) -> dict[str, Any]:
    return dict(tenant.settings) if isinstance(tenant.settings, dict) else {}


def _save(db: Session, tenant: Tenant, settings: dict[str, Any]) -> None:
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    db.refresh(tenant)


def _items(settings: dict[str, Any]) -> list[dict[str, Any]]:
    raw = settings.get("appointments")
    if not isinstance(raw, list):
        return []
    return [dict(x) for x in raw if isinstance(x, dict)]


def _find(items: list[dict[str, Any]], *, appointment_id: str | None, email: str | None, phone: str | None, verified_phone: str | None = None) -> dict[str, Any] | None:
    if verified_phone is not None and not verified_phone:
        return None
    if appointment_id:
        for item in items:
            if str(item.get("id")) == appointment_id and (verified_phone is None or item.get("phone") == verified_phone):
                return item
        return None
    email_l = (email or "").strip().lower()
    phone_s = (phone or "").strip()
    for item in reversed(items):
        if item.get("status") not in _OPEN:
            continue
        if email_l and verified_phone is None and str(item.get("email") or "").lower() == email_l:
            return item
        if phone_s and str(item.get("phone") or "") == phone_s:
            return item
    return None


def _invite_text(*, title: str, start: str, conference_url: str, company: str) -> str:
    lines = [
        "Здравствуйте!",
        "",
        f"Встреча «{title}» — {start}.",
    ]
    if conference_url:
        lines.append(f"Ссылка на видеовстречу: {conference_url}")
    lines.append("")
    lines.append("Если время не подойдёт — ответьте, подберём другое.")
    if company:
        lines.append(company)
    return "\n".join(lines)


def _free(result: Any) -> bool:
    data = getattr(result, "data", None) or {}
    if not isinstance(data, dict):
        return False
    if "free" in data:
        return bool(data["free"])
    upstream = data.get("upstream")
    if isinstance(upstream, dict) and "free" in upstream:
        return bool(upstream["free"])
    if data.get("busy") is True:
        return False
    return False


def _slots(result: Any) -> list[dict[str, Any]]:
    data = getattr(result, "data", None) or {}
    suggestions = data.get("suggestions") if isinstance(data, dict) else None
    if isinstance(suggestions, list):
        return [x for x in suggestions if isinstance(x, dict)]
    return []


def handle(
    db: Session,
    ctx: TenantContext,
    action: str,
    params: dict[str, Any] | None = None,
    *,
    channel: str | None = None,
) -> dict[str, Any]:
    params = dict(params or {})
    channel = (channel or str(params.get("channel") or "") or current_channel.get() or "messenger").strip()
    params.pop("_verified_phone", None)
    if channel == "voice":
        params["_verified_phone"] = current_verified_phone.get()
    if channel in {"telegram", "max"}:
        params["_channel_user_id"] = current_external_user_id.get()
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    action = (action or "").strip()
    if action in {"book_meeting", "meeting.book", "suggest_other_time", "meeting.suggest_time", "reschedule_meeting", "meeting.reschedule", "confirm_meeting", "meeting.confirm", "cancel_meeting", "meeting.cancel"}:
        from app.services.meeting_flow import handle as handle_meeting

        return handle_meeting(db, ctx, action, params, channel)
    if action in {"send_welcome_email", "send_email"}:
        return _send(db, ctx, tenant, params)
    return {"ok": False, "error": "unknown_action", "message_ru": "Такое действие пока не умеем."}


def _suggest(db: Session, ctx: TenantContext, params: dict[str, Any]) -> dict[str, Any]:
    start = str(params.get("start") or "").strip()
    if not start:
        return {"ok": False, "error": "start_required", "message_ru": "Назовите, на какое время смотреть."}
    calendar = get_connector("calendar")
    if calendar is None:
        return {"ok": False, "error": "no_calendar", "message_ru": "Календарь на платформе недоступен."}
    config, err = _calendar_config(db, ctx, str(params.get("source") or "") or None)
    if err or config is None:
        return {"ok": False, "error": err or "tenant_required", "message_ru": "Календарь этой компании не подключён."}
    result = calendar.suggest_slots(  # type: ignore[attr-defined]
        tenant_slug=ctx.tenant_slug,
        config=config,
        start=start,
        duration_min=int(params.get("duration_min") or 60),
        source=str(params.get("source") or "") or None,
    )
    slots = _slots(result)
    labels = [str(s.get("start") or s.get("label") or "") for s in slots if (s.get("start") or s.get("label"))]
    if not labels:
        return {
            "ok": False,
            "error": "no_slots",
            "message_ru": "Свободного времени рядом не нашлось. Назовите другой день.",
        }
    shown = ", ".join(labels[:3])
    return {
        "ok": True,
        "free": False,
        "suggestions": slots,
        "message_ru": f"Это время занято. Могу предложить: {shown}.",
    }


def _book(
    db: Session,
    ctx: TenantContext,
    tenant: Tenant,
    params: dict[str, Any],
    *,
    channel: str,
) -> dict[str, Any]:
    start = str(params.get("start") or "").strip()
    if not start:
        return {"ok": False, "error": "start_required", "message_ru": "Назовите день и время встречи."}
    calendar = get_connector("calendar")
    if calendar is None:
        return {"ok": False, "error": "no_calendar", "message_ru": "Календарь на платформе недоступен."}
    config, err = _calendar_config(db, ctx, str(params.get("source") or "") or None)
    if err or config is None:
        return {"ok": False, "error": err or "tenant_required", "message_ru": "Календарь этой компании не подключён."}
    checked = calendar.check(  # type: ignore[attr-defined]
        tenant_slug=ctx.tenant_slug,
        config=config,
        start=start,
        timezone=str(params.get("timezone") or "") or None,
        source=str(params.get("source") or "") or None,
    )
    if not getattr(checked, "ok", False):
        return {
            "ok": False,
            "error": "calendar_failed",
            "message_ru": "Не получилось заглянуть в календарь. Попробуем ещё раз чуть позже.",
        }
    if not _free(checked):
        alt = _suggest(db, ctx, params)
        alt["booked"] = False
        return alt

    title = str(params.get("title") or params.get("summary") or "Встреча").strip() or "Встреча"
    email = str(params.get("email") or params.get("attendee_email") or "").strip()
    phone = str(params.get("phone") or params.get("from_number") or "").strip()
    created = calendar.create_event(  # type: ignore[attr-defined]
        tenant_slug=ctx.tenant_slug,
        config=config,
        start=start,
        summary=title,
        description=str(params.get("description") or "") or None,
        attendee_email=email or None,
        timezone=str(params.get("timezone") or "") or None,
        end=str(params.get("end") or "") or None,
        source=str(params.get("source") or "") or None,
        create_telemost=False,
        invitees=[email] if email else None,
    )
    conference_url = ""
    conf = get_connector("conference")
    if conf is not None:
        conf_res = conf.create(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config={**connector_config_for(db, ctx, "conference"), "_conference_delivery_access": conference_delivery_access(db, ctx, str(params.get("provider") or "yandex"))},
            title=title,
            provider=str(params.get("provider") or "yandex"),
            invitees=[email] if email else [],
            when_text=start,
        )
        data = getattr(conf_res, "data", None) or {}
        conference_url = str(
            data.get("join_url") or data.get("url") or (data.get("upstream") or {}).get("join_url") or ""
        )

    mailed = None
    if email:
        mailed = _send(
            db,
            ctx,
            tenant,
            {
                "email": email,
                "subject": f"Встреча {start}",
                "body": _invite_text(
                    title=title,
                    start=start,
                    conference_url=conference_url,
                    company=tenant.name or "",
                ),
                "attachment_id": params.get("attachment_id"),
            },
            commit=False,
        )

    settings = _settings(tenant)
    items = _items(settings)
    row = {
        "id": "apt_" + uuid.uuid4().hex[:12],
        "tenant_id": str(tenant.id),
        "start": start,
        "title": title,
        "email": email,
        "phone": phone,
        "status": "booked",
        "conference_url": conference_url,
        "channel": channel,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    items.append(row)
    settings["appointments"] = items
    _save(db, tenant, settings)
    bits = [f"Встреча записана на {start}."]
    if conference_url:
        bits.append(f"Ссылка: {conference_url}.")
    if email and mailed and mailed.get("ok"):
        bits.append(f"Приглашение отправлено на {email}.")
    elif email:
        bits.append("Письмо пока не ушло — почта ещё не готова, встречу я всё равно записал.")
    return {
        "ok": True,
        "booked": True,
        "appointment": row,
        "mail": mailed,
        "message_ru": " ".join(bits),
    }


def _move(
    db: Session,
    ctx: TenantContext,
    tenant: Tenant,
    params: dict[str, Any],
    *,
    channel: str,
) -> dict[str, Any]:
    start = str(params.get("start") or "").strip()
    if not start:
        return {"ok": False, "error": "start_required", "message_ru": "На какое время переносим?"}
    calendar = get_connector("calendar")
    if calendar is not None:
        config, err = _calendar_config(db, ctx, str(params.get("source") or "") or None)
        if err or config is None:
            return {"ok": False, "error": err or "tenant_required", "message_ru": "Календарь этой компании не подключён."}
        checked = calendar.check(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            start=start,
            timezone=str(params.get("timezone") or "") or None,
            source=str(params.get("source") or "") or None,
        )
        if getattr(checked, "ok", False) and not _free(checked):
            alt = _suggest(db, ctx, params)
            alt["rescheduled"] = False
            return alt
    settings = _settings(tenant)
    items = _items(settings)
    row = _find(
        items,
        appointment_id=str(params.get("appointment_id") or "") or None,
        email=str(params.get("email") or "") or None,
        phone=str(params.get("phone") or "") or None,
        verified_phone=params.get("_verified_phone"),
    )
    if row is None:
        return {"ok": False, "error": "not_found", "message_ru": "Не нашёл встречу, которую можно перенести."}
    row["start"] = start
    row["status"] = "rescheduled"
    row["channel"] = channel
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    settings["appointments"] = items
    _save(db, tenant, settings)
    if row.get("email"):
        _send(
            db,
            ctx,
            tenant,
            {
                "email": row["email"],
                "subject": f"Встреча перенесена на {start}",
                "body": _invite_text(
                    title=str(row.get("title") or "Встреча"),
                    start=start,
                    conference_url=str(row.get("conference_url") or ""),
                    company=tenant.name or "",
                ),
            },
        )
    return {
        "ok": True,
        "rescheduled": True,
        "appointment": row,
        "message_ru": f"Встречу перенесла на {start}.",
    }


def _set_status(
    db: Session,
    tenant: Tenant,
    params: dict[str, Any],
    *,
    status: str,
    verb: str,
) -> dict[str, Any]:
    settings = _settings(tenant)
    items = _items(settings)
    row = _find(
        items,
        appointment_id=str(params.get("appointment_id") or "") or None,
        email=str(params.get("email") or "") or None,
        phone=str(params.get("phone") or "") or None,
        verified_phone=params.get("_verified_phone"),
    )
    if row is None:
        return {"ok": False, "error": "not_found", "message_ru": "Не нашёл такую встречу."}
    row["status"] = status
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    settings["appointments"] = items
    _save(db, tenant, settings)
    return {
        "ok": True,
        "appointment": row,
        "message_ru": f"Встреча {verb}: {row.get('start') or ''}.",
    }


def _send(
    db: Session,
    ctx: TenantContext,
    tenant: Tenant,
    params: dict[str, Any],
    *,
    commit: bool = True,
) -> dict[str, Any]:
    email = str(params.get("email") or params.get("to") or "").strip()
    if not email:
        return {"ok": False, "error": "email_required", "message_ru": "Нужна почта клиента, чтобы отправить письмо."}
    subject = str(params.get("subject") or "Материалы и время встречи").strip()
    body = str(params.get("body") or "").strip()
    if not body:
        body = _invite_text(
            title=str(params.get("title") or "Встреча"),
            start=str(params.get("start") or ""),
            conference_url=str(params.get("conference_url") or ""),
            company=tenant.name or "",
        )
    attachment = None
    if params.get("attachment_id"):
        from app.services.tenant_attachments import attachment_for
        try:
            attachment = attachment_for(db, ctx, str(params["attachment_id"]))
        except (ValueError, OSError):
            return {"ok": False, "error": "attachment_unavailable", "message_ru": "Выбранный файл этой компании не найден; письмо не отправлено."}
    mail = get_connector("mail")
    if mail is None:
        return {"ok": False, "error": "no_mail", "message_ru": "Почта на платформе недоступна."}
    result = mail.send_draft(  # type: ignore[attr-defined]
        tenant_slug=ctx.tenant_slug,
        config={**connector_config_for(db, ctx, "mail"), "_mail_delivery_access": mail_delivery_access(db, ctx)},
        to=email,
        subject=subject,
        body=body,
        attachment=attachment,
    )
    ok = bool(getattr(result, "ok", False))
    if commit:
        db.flush()
    return {
        "ok": ok,
        "to": email,
        "subject": subject,
        "message_ru": (
            f"Письмо для {email} отправлено."
            if ok
            else "Письмо не отправилось. Проверим почту и попробуем ещё раз."
        ),
        "data": getattr(result, "data", None) or {},
    }
