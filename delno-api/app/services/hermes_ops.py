"""Hermes supervisor ops — first-time office setup + health watch + alerts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.call_job import CallJob
from app.models.call_session import CallSession
from app.models.channel_account import ChannelAccount
from app.models.phone_number import PhoneNumber
from app.models.platform_event import PlatformEvent
from app.models.tenant import Tenant
from app.services.connectors import list_tenant_connectors
from app.services.events import emit_event
from app.services.tenant_vault import list_secret_status


SETUP_STEPS: list[dict[str, str]] = [
    {"id": "kb", "title": "База знаний", "hint": "Загрузите описание бизнеса / прайс в KB"},
    {
        "id": "phone",
        "title": "Телефония",
        "hint": "Привяжите DID и сохраните SIP Mango в сейфе кабинета (безопасная форма)",
    },
    {"id": "telegram", "title": "Telegram", "hint": "Подключите branded bot token"},
    {"id": "max", "title": "MAX", "hint": "Опционально: MAX bot access token"},
    {"id": "calendar", "title": "Календарь", "hint": "Включите connector calendar + креды"},
    {"id": "mail", "title": "Почта", "hint": "Включите connector mail + SMTP"},
    {"id": "conference", "title": "ВКС", "hint": "Включите connector conference (Telemost/Meet/Jitsi)"},
    {"id": "outreach", "title": "Рассылка", "hint": "Опционально: outreach connector"},
]


def _settings(tenant: Tenant) -> dict[str, Any]:
    return dict(tenant.settings) if isinstance(tenant.settings, dict) else {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def office_setup_status(db: Session, ctx: TenantContext) -> dict[str, Any]:
    """Checklist for first-time Hermes onboarding of the office."""
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = _settings(tenant)
    hermes = settings.get("hermes") if isinstance(settings.get("hermes"), dict) else {}
    onboarding = settings.get("onboarding") if isinstance(settings.get("onboarding"), dict) else {}

    phones = (
        db.query(PhoneNumber)
        .filter(PhoneNumber.tenant_id == ctx.tenant_id, PhoneNumber.status == "active")
        .count()
    )
    tg = (
        db.query(ChannelAccount)
        .filter(
            ChannelAccount.tenant_id == ctx.tenant_id,
            ChannelAccount.type == "telegram",
            ChannelAccount.status == "active",
        )
        .count()
    )
    max_n = (
        db.query(ChannelAccount)
        .filter(
            ChannelAccount.tenant_id == ctx.tenant_id,
            ChannelAccount.type == "max",
            ChannelAccount.status == "active",
        )
        .count()
    )
    connectors = list_tenant_connectors(db, ctx)
    by_kind = {i["kind"]: i for i in connectors.get("items") or []}

    def _conn_ok(kind: str) -> bool:
        item = by_kind.get(kind) or {}
        return bool(item.get("enabled")) and bool(item.get("configured"))

    # KB: treat onboarding completed or hermes flag as done; else unknown→pending
    kb_done = bool(hermes.get("kb_ready")) or (onboarding.get("status") == "completed")

    sip_items = list_secret_status(db, ctx).get("items") or []
    sip_row = next((i for i in sip_items if i.get("kind") == "mango_sip"), None) or {}
    sip_ok = bool(sip_row.get("configured"))
    phone_ok = phones > 0 and sip_ok
    phone_detail = {
        "active_dids": phones,
        "sip_configured": sip_ok,
        "sip_login_masked": sip_row.get("login_masked") or "",
    }

    checks = {
        "kb": {"ok": kb_done, "detail": "kb_ready" if kb_done else "upload_knowledge"},
        "phone": {"ok": phone_ok, "detail": phone_detail},
        "telegram": {"ok": tg > 0, "detail": f"accounts={tg}"},
        "max": {"ok": max_n > 0, "detail": f"accounts={max_n}", "optional": True},
        "calendar": {"ok": _conn_ok("calendar"), "detail": (by_kind.get("calendar") or {}).get("status")},
        "mail": {"ok": _conn_ok("mail"), "detail": (by_kind.get("mail") or {}).get("status")},
        "conference": {
            "ok": _conn_ok("conference"),
            "detail": (by_kind.get("conference") or {}).get("status"),
        },
        "outreach": {
            "ok": _conn_ok("outreach"),
            "detail": (by_kind.get("outreach") or {}).get("status"),
            "optional": True,
        },
    }

    required = [s for s in SETUP_STEPS if not checks[s["id"]].get("optional")]
    done_req = sum(1 for s in required if checks[s["id"]]["ok"])
    next_steps = []
    for step in SETUP_STEPS:
        c = checks[step["id"]]
        if c["ok"]:
            continue
        if c.get("optional") and done_req < len(required):
            continue
        next_steps.append({**step, "status": "todo", "check": c})

    setup_complete = done_req == len(required)
    return {
        "ok": True,
        "tenant_slug": ctx.tenant_slug,
        "setup_complete": setup_complete,
        "progress": {"required_done": done_req, "required_total": len(required)},
        "checks": checks,
        "steps": SETUP_STEPS,
        "next_steps": next_steps[:3],
        "hermes": {
            "setup_started_at": hermes.get("setup_started_at"),
            "setup_completed_at": hermes.get("setup_completed_at"),
            "last_health_at": hermes.get("last_health_at"),
            "open_alerts": hermes.get("open_alerts") or [],
        },
        "message_ru": (
            "Офис готов к работе."
            if setup_complete
            else (
                "Давайте настроим офис. Следующий шаг: "
                + (next_steps[0]["title"] if next_steps else "проверить компоненты")
                + ". "
                + (next_steps[0]["hint"] if next_steps else "")
            )
        ),
    }


def mark_setup_progress(
    db: Session,
    ctx: TenantContext,
    *,
    kb_ready: bool | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = _settings(tenant)
    hermes = dict(settings.get("hermes") or {})
    if not hermes.get("setup_started_at"):
        hermes["setup_started_at"] = _now_iso()
    if kb_ready is not None:
        hermes["kb_ready"] = bool(kb_ready)
    if note:
        hermes["last_setup_note"] = note[:500]
    status = office_setup_status(db, ctx)
    # re-read after potential concurrent — apply completion on fresh checks
    if status.get("setup_complete"):
        hermes["setup_completed_at"] = hermes.get("setup_completed_at") or _now_iso()
    settings["hermes"] = hermes
    tenant.settings = settings
    emit_event(
        db,
        event_type="hermes.setup.progress",
        category="operational",
        tenant_id=ctx.tenant_id,
        source="hermes",
        payload={"kb_ready": hermes.get("kb_ready"), "setup_complete": status.get("setup_complete")},
    )
    db.commit()
    return office_setup_status(db, ctx)


def office_health_report(db: Session, ctx: TenantContext) -> dict[str, Any]:
    """Snapshot of component health for Hermes → user alerts."""
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    connectors = list_tenant_connectors(db, ctx)
    phones = (
        db.query(PhoneNumber)
        .filter(PhoneNumber.tenant_id == ctx.tenant_id)
        .order_by(PhoneNumber.created_at.desc())
        .all()
    )
    active_dids = [p.e164 for p in phones if p.status == "active"]
    queued_jobs = (
        db.query(CallJob)
        .filter(CallJob.tenant_id == ctx.tenant_id, CallJob.status == "queued")
        .count()
    )
    stuck_jobs = (
        db.query(CallJob)
        .filter(CallJob.tenant_id == ctx.tenant_id, CallJob.status.in_(("dialing", "in_progress")))
        .count()
    )
    recent_fail_calls = (
        db.query(CallSession)
        .filter(CallSession.tenant_id == ctx.tenant_id, CallSession.status == "failed")
        .order_by(CallSession.created_at.desc())
        .limit(5)
        .count()
    )
    channels = (
        db.query(ChannelAccount)
        .filter(ChannelAccount.tenant_id == ctx.tenant_id)
        .all()
    )

    alerts: list[dict[str, Any]] = []
    sip_items = list_secret_status(db, ctx).get("items") or []
    sip_row = next((i for i in sip_items if i.get("kind") == "mango_sip"), None) or {}
    sip_ok = bool(sip_row.get("configured"))
    if not active_dids:
        alerts.append(
            {
                "code": "phone.no_active_did",
                "severity": "warning",
                "message_ru": "Нет активного телефонного номера. Входящие и исходящие звонки недоступны.",
                "fix": "Привяжите DID через phones.provision или скажите Hermes номер.",
            }
        )
    if not sip_ok:
        alerts.append(
            {
                "code": "phone.sip_missing",
                "severity": "warning",
                "message_ru": "SIP Mango ещё не сохранён в сейфе кабинета — линия не зарегистрируется.",
                "fix": "Скажите «настрой телефон» и заполните безопасную форму (логин вида номер/сотрудник).",
            }
        )
    elif "/" not in str(sip_row.get("login_masked") or ""):
        alerts.append(
            {
                "code": "phone.sip_login_partial",
                "severity": "warning",
                "message_ru": "SIP-логин похож на неполный (нужен вид номер/сотрудник).",
                "fix": "Откройте форму SIP ещё раз и сохраните полный логин Mango.",
            }
        )
    for item in connectors.get("items") or []:
        if item.get("enabled") and not item.get("configured"):
            alerts.append(
                {
                    "code": f"connector.{item['kind']}.not_configured",
                    "severity": "warning",
                    "message_ru": f"Коннектор «{item['kind']}» включён, но не настроен (нет кредов/URL).",
                    "fix": f"Передайте Hermes данные для {item['kind']} или выключите connector.",
                }
            )
    for ch in channels:
        if ch.status not in ("active",):
            alerts.append(
                {
                    "code": f"channel.{ch.type}.degraded",
                    "severity": "warning",
                    "message_ru": f"Канал {ch.type} в статусе «{ch.status}».",
                    "fix": "Проверьте токен бота / переподключите канал.",
                }
            )
    if stuck_jobs >= 3:
        alerts.append(
            {
                "code": "telephony.jobs_stuck",
                "severity": "critical",
                "message_ru": f"В очереди исходящих зависло заданий: {stuck_jobs}. Dialer, возможно, не работает.",
                "fix": "Проверьте dialer worker и SIP-регистрацию Mango.",
            }
        )
    if queued_jobs >= 20:
        alerts.append(
            {
                "code": "telephony.queue_backlog",
                "severity": "warning",
                "message_ru": f"Большая очередь исходящих: {queued_jobs}.",
                "fix": "Проверьте dialer или приостановите набор.",
            }
        )

    # Persist open alerts on tenant hermes settings for next chat
    settings = _settings(tenant)
    hermes = dict(settings.get("hermes") or {})
    hermes["last_health_at"] = _now_iso()
    hermes["open_alerts"] = alerts
    settings["hermes"] = hermes
    tenant.settings = settings

    emit_event(
        db,
        event_type="hermes.health.checked",
        category="operational",
        tenant_id=ctx.tenant_id,
        source="hermes",
        payload={"alerts": len(alerts), "codes": [a["code"] for a in alerts]},
    )
    if alerts:
        emit_event(
            db,
            event_type="office.alert",
            category="operational",
            tenant_id=ctx.tenant_id,
            source="hermes",
            payload={"alerts": alerts[:10]},
        )
    db.commit()

    user_summary = (
        "Все основные компоненты в порядке."
        if not alerts
        else "Есть проблемы: " + "; ".join(a["message_ru"] for a in alerts[:3])
    )
    return {
        "ok": True,
        "healthy": len(alerts) == 0,
        "alerts": alerts,
        "telephony": {
            "active_dids": active_dids,
            "queued_jobs": queued_jobs,
            "stuck_jobs": stuck_jobs,
            "recent_failed_sessions": recent_fail_calls,
        },
        "channels": [
            {"type": c.type, "status": c.status, "id": str(c.id)} for c in channels
        ],
        "connectors": connectors.get("items") or [],
        "message_ru": user_summary,
        "checked_at": hermes["last_health_at"],
    }


def list_recent_office_alerts(db: Session, ctx: TenantContext, *, limit: int = 20) -> dict[str, Any]:
    rows = (
        db.query(PlatformEvent)
        .filter(
            PlatformEvent.tenant_id == ctx.tenant_id,
            PlatformEvent.event_type.in_(("office.alert", "hermes.health.checked", "call.inbound.unrouted")),
        )
        .order_by(PlatformEvent.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return {
        "ok": True,
        "items": [
            {
                "id": str(r.id),
                "event_type": r.event_type,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "payload": r.payload,
            }
            for r in rows
        ],
    }
