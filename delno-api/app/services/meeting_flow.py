"""One appointment workflow for phone, messenger and cabinet agents."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.connectors import get_connector
from app.core.tenant import TenantContext
from app.models.appointment import Appointment
from app.models.tenant import Tenant
from app.services import calendar_store
from app.services.connectors import connector_config_for, list_tenant_connector_readiness
from app.services.tenant_broker_access import apply_access


def _ready(db: Session, ctx: TenantContext, kind: str) -> bool:
    return any(row["kind"] == kind and row.get("usable") for row in list_tenant_connector_readiness(db, ctx))


def _mirror(db: Session, tenant: Tenant) -> None:
    """Temporary read compatibility for existing settings consumers."""
    settings = dict(tenant.settings or {})
    rows = db.query(Appointment).filter(Appointment.tenant_id == tenant.id).order_by(Appointment.created_at).all()
    settings["appointments"] = [calendar_store.as_dict(row) for row in rows]
    tenant.settings = settings
    db.add(tenant)


def _identity(params: dict[str, Any], channel: str) -> tuple[str | None, str | None]:
    phone = str(params.get("_verified_phone") or "") or None
    external = str(params.get("_channel_user_id") or "") or None
    if channel not in {"telegram", "max"}:
        external = None
    return phone, external


def _select(db: Session, ctx: TenantContext, tenant: Tenant, params: dict[str, Any], channel: str) -> tuple[Appointment | None, dict | None]:
    phone, external = _identity(params, channel)
    ident = str(params.get("appointment_id") or "") or None
    if ctx.role in {"tenant_owner", "tenant_admin"} and ident:
        try:
            row = db.query(Appointment).filter(Appointment.id == uuid.UUID(ident), Appointment.tenant_id == tenant.id).one_or_none()
        except ValueError:
            row = None
        return row, None
    rows = calendar_store.candidates(
        db, tenant, appointment_id=ident, phone=phone,
        channel=channel if external else None, external_user_id=external,
    )
    if len(rows) > 1:
        return None, {
            "ok": False, "error": "ambiguous_appointment",
            "choices": [{"id": str(row.id), "start": row.start_at.isoformat(), "title": row.title} for row in rows[:5]],
            "message_ru": "Нашёл несколько встреч. Уточните дату нужной встречи.",
        }
    if not rows:
        return None, {"ok": False, "error": "appointment_not_found_or_unverified", "message_ru": "Не нашёл встречу для этого контакта. Попросите владельца помочь с проверкой записи."}
    return rows[0], None


def _book(db: Session, ctx: TenantContext, tenant: Tenant, params: dict[str, Any], channel: str) -> dict:
    start_text = str(params.get("start") or "")
    if not start_text:
        return {"ok": False, "error": "start_required", "message_ru": "Назовите дату и время встречи."}
    try:
        start = calendar_store.parse_time(start_text, str(params.get("timezone") or "Europe/Moscow"))
        end = calendar_store.parse_time(str(params["end"]), str(params.get("timezone") or "Europe/Moscow")) if params.get("end") else start + timedelta(minutes=int(params.get("duration_min") or 60))
    except (ValueError, TypeError) as exc:
        return {"ok": False, "error": "invalid_time", "message_ru": f"Не удалось понять время: {exc}."}
    if end <= start:
        return {"ok": False, "error": "invalid_duration", "message_ru": "Конец встречи должен быть позже начала."}
    calendar_store.import_legacy(db, tenant)
    if not calendar_store.slot_free(db, tenant, start, end):
        return {"ok": True, "booked": False, "error": "slot_busy", "message_ru": "Это время уже занято в календаре DELNO. Предложите другое."}

    # An external calendar can reject a slot, but its absence never blocks DELNO.
    external_config = None
    if _ready(db, ctx, "calendar"):
        external_config, err = apply_access(db, ctx, dict(connector_config_for(db, ctx, "calendar")), kind="calendar", source=str(params.get("source") or "") or None)
        if err or external_config is None:
            return {"ok": False, "error": "external_calendar_unavailable", "message_ru": "Подключённый календарь сейчас не отвечает. Повторите попытку позже."}
        connector = get_connector("calendar")
        checked = connector.check(tenant_slug=ctx.tenant_slug, config=external_config, start=start.isoformat(), timezone="UTC", source=str(params.get("source") or "") or None)
        data = getattr(checked, "data", None) or {}
        upstream = data.get("upstream") if isinstance(data, dict) else {}
        free = data.get("free") if isinstance(data, dict) else None
        if free is None and isinstance(upstream, dict):
            free = upstream.get("free")
        if not getattr(checked, "ok", False) or free is None:
            return {"ok": False, "error": "calendar_check_failed", "message_ru": "Не удалось проверить внешний календарь. Попробуйте позже."}
        if free is False:
            return {"ok": True, "booked": False, "error": "slot_busy", "message_ru": "Это время занято во внешнем календаре. Предложите другое."}

    phone, external_user_id = _identity(params, channel)
    phone = phone or (str(params.get("phone") or "") or None)
    email = str(params.get("email") or params.get("attendee_email") or "") or None
    try:
        row = calendar_store.create(
            db, tenant, start=start, end=end,
            title=str(params.get("title") or params.get("summary") or "Встреча"),
            phone=phone, email=email, channel=channel, external_user_id=external_user_id,
        )
    except ValueError:
        return {"ok": True, "booked": False, "error": "slot_busy", "message_ru": "Это время только что заняли. Предложите другое."}

    if external_config is not None:
        row.sync_status = "pending"
        try:
            created = get_connector("calendar").create_event(
                tenant_slug=ctx.tenant_slug, config=external_config,
                start=start.isoformat(), end=end.isoformat(), summary=row.title,
                attendee_email=email, timezone="UTC", source=str(params.get("source") or "") or None,
                create_telemost=False,
            )
            data = getattr(created, "data", None) or {}
            if getattr(created, "ok", False) and not data.get("stub"):
                row.external_event_id = str(data.get("event_id") or data.get("href") or "") or None
                row.external_provider = str(params.get("source") or external_config.get("default_source") or "") or None
                row.sync_status = "synced" if row.external_event_id else "unknown_external_id"
            else:
                row.sync_status = "sync_failed"
        except Exception:
            row.sync_status = "sync_failed"

    # Conference and mail are optional. Never treat a stub URL or unsent email as delivered.
    if _ready(db, ctx, "conference"):
        try:
            result = get_connector("conference").create(
                tenant_slug=ctx.tenant_slug, config=connector_config_for(db, ctx, "conference"),
                title=row.title, provider=str(params.get("provider") or "yandex"),
                invitees=[], when_text=start.isoformat(),
            )
            data = getattr(result, "data", None) or {}
            if getattr(result, "ok", False) and not data.get("stub"):
                row.conference_url = str(data.get("join_url") or "") or None
        except Exception:
            pass
    db.add(row)
    _mirror(db, tenant)
    db.commit()
    out = calendar_store.as_dict(row)
    message = f"Встреча записана на {start.isoformat()}."
    if row.sync_status in {"sync_failed", "unknown_external_id"}:
        message += " Во внешний календарь запись пока не подтверждена."
    if row.conference_url:
        message += f" Ссылка на видеовстречу: {row.conference_url}."
    if email and _ready(db, ctx, "mail"):
        from app.services.appointments import _invite_text, _send
        mailed = _send(db, ctx, tenant, {"email": email, "subject": f"Встреча {start.isoformat()}", "body": _invite_text(title=row.title, start=start.isoformat(), conference_url=row.conference_url or "", company=tenant.name or "")})
        message += f" Письмо {'отправлено' if mailed.get('ok') else 'не отправлено'} на {email}."
    else:
        mailed = None
        if email:
            message += " Почта не подключена, письмо не отправлено."
    return {"ok": True, "booked": True, "appointment": out, "mail": mailed, "message_ru": message}


def _change(db: Session, ctx: TenantContext, tenant: Tenant, action: str, params: dict[str, Any], channel: str) -> dict:
    row, error = _select(db, ctx, tenant, params, channel)
    if error:
        return error
    assert row is not None
    if action == "reschedule_meeting":
        try:
            start = calendar_store.parse_time(str(params.get("start") or ""), str(params.get("timezone") or "Europe/Moscow"))
            end = start + (row.end_at - row.start_at)
        except ValueError:
            return {"ok": False, "error": "invalid_time", "message_ru": "Назовите новую дату и время."}
        if not calendar_store.slot_free(db, tenant, start, end, excluding=row.id):
            return {"ok": True, "rescheduled": False, "error": "slot_busy", "message_ru": "Новое время занято. Предложите другое."}
        row.start_at, row.end_at, row.status = start, end, "rescheduled"
    elif action == "confirm_meeting":
        row.status = "confirmed"
    else:
        row.status = "cancelled"
    row.sync_version += 1
    row.sync_status = "pending" if row.external_event_id else "local_only"
    db.add(row)
    _mirror(db, tenant)
    db.commit()
    message = f"Встреча {('перенесена' if action == 'reschedule_meeting' else 'подтверждена' if action == 'confirm_meeting' else 'отменена')} в календаре DELNO."
    if row.sync_status == "pending":
        message += " Изменение во внешнем календаре ещё не подтверждено."
    return {"ok": True, "rescheduled": action == "reschedule_meeting", "appointment": calendar_store.as_dict(row), "message_ru": message}


def _suggest(db: Session, tenant: Tenant, params: dict[str, Any]) -> dict:
    try:
        start = calendar_store.parse_time(str(params.get("start") or ""), str(params.get("timezone") or "Europe/Moscow"))
        duration = timedelta(minutes=int(params.get("duration_min") or 60))
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid_time", "message_ru": "Назовите дату и время, рядом с которыми искать окно."}
    calendar_store.import_legacy(db, tenant)
    suggestions = []
    for step in range(1, 97):
        candidate = start + timedelta(minutes=30 * step)
        if calendar_store.slot_free(db, tenant, candidate, candidate + duration):
            suggestions.append({"start": candidate.isoformat(), "end": (candidate + duration).isoformat()})
        if len(suggestions) == 3:
            break
    if not suggestions:
        return {"ok": False, "error": "no_slots", "message_ru": "Рядом нет свободного времени. Предложите другой день."}
    return {"ok": True, "suggestions": suggestions, "message_ru": "Могу предложить: " + ", ".join(item["start"] for item in suggestions)}


def handle(db: Session, ctx: TenantContext, action: str, params: dict[str, Any], channel: str) -> dict:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    if action in {"book_meeting", "meeting.book"}:
        return _book(db, ctx, tenant, params, channel)
    if action in {"suggest_other_time", "meeting.suggest_time"}:
        return _suggest(db, tenant, params)
    if action in {"reschedule_meeting", "meeting.reschedule", "confirm_meeting", "meeting.confirm", "cancel_meeting", "meeting.cancel"}:
        return _change(db, ctx, tenant, action.replace("meeting.reschedule", "reschedule_meeting").replace("meeting.confirm", "confirm_meeting").replace("meeting.cancel", "cancel_meeting"), params, channel)
    raise ValueError("unsupported_meeting_action")
