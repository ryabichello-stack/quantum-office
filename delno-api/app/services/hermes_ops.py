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
from app.services.audit import write_audit
from app.services.connectors import list_tenant_connectors, list_tenant_connector_readiness
from app.services.events import emit_event
from app.services.tenant_vault import list_secret_status


_OWNER_KB_SOURCES = {
    "owner_upload",
    "hermes_dictation",
    "website_import",
    "hermes.import_website",
    "tenant.instant_demo",
    "template_upload",
    "tenant.knowledge.upload",
    "cabinet.upload",
    "onboarding.website",
    "operator.knowledge_snippet",
    "office_loop.kb_draft_confirm",
}

_SEED_KB_SOURCES = {
    "onboarding:welcome",
    "dogfood",
    "dogfood seed",
    "seed",
    "vault.seed",
    "delno-demo.seed",
}


def company_knowledge_ready(db: Session, ctx: TenantContext, *, hermes: dict[str, Any] | None = None) -> dict[str, Any]:
    """True only when the owner actually provided company facts — not dogfood seed."""
    h = hermes if isinstance(hermes, dict) else {}
    if h.get("company_profile_ready"):
        return {"ok": True, "detail": "company_profile_ready", "source": h.get("kb_source") or "company_profile"}
    if h.get("kb_ready") and (h.get("kb_source") or "") in _OWNER_KB_SOURCES:
        return {"ok": True, "detail": "kb_ready", "source": h.get("kb_source")}

    # Real owner uploads (ignore welcome/seed events)
    events = (
        db.query(PlatformEvent)
        .filter(
            PlatformEvent.tenant_id == ctx.tenant_id,
            PlatformEvent.event_type == "knowledge.document_upserted",
        )
        .order_by(PlatformEvent.created_at.desc())
        .limit(30)
        .all()
    )
    for ev in events:
        payload = ev.payload if isinstance(ev.payload, dict) else {}
        source = str(payload.get("source") or "").strip()
        title = str(payload.get("title") or "").lower()
        source_l = source.lower()
        if source_l in _SEED_KB_SOURCES or source_l.startswith("onboarding:welcome") or "seed" in source_l:
            continue
        if (
            source in _OWNER_KB_SOURCES
            or source.startswith("tenant.knowledge")
            or source.startswith("hermes.import")
            or "website" in source_l
        ):
            return {"ok": True, "detail": "knowledge_event", "source": source or title}
        # Explicit company-profile titles from owner uploads
        if any(
            k in title
            for k in (
                "профиль компании",
                "коммерческий профиль",
                "о компании",
                "company profile",
                "о нас",
                "quantum payouts",
            )
        ):
            if source_l.startswith("onboarding") and "welcome" in source_l:
                continue
            return {"ok": True, "detail": "knowledge_title", "source": title}
    return {"ok": False, "detail": "need_company_profile", "source": None}


def _setup_steps() -> list[dict[str, str]]:
    """Live catalog — new channels appear without editing this file's prompt text."""
    from app.services.instrument_catalog import setup_steps

    return setup_steps()


# Importers that bound the name at import time still see the builtin list.
# office_setup_status() always re-reads the catalog, including extras.
SETUP_STEPS: list[dict[str, str]] = _setup_steps()


def _settings(tenant: Tenant) -> dict[str, Any]:
    return dict(tenant.settings) if isinstance(tenant.settings, dict) else {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def office_setup_status(db: Session, ctx: TenantContext) -> dict[str, Any]:
    """Describe available tools and progress toward this owner's chosen goal."""
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
    readiness = {i["kind"]: i for i in list_tenant_connector_readiness(db, ctx)}

    def _conn_ok(kind: str) -> bool:
        return bool(readiness.get(kind, {}).get("usable"))

    def _conn_detail(kind: str) -> dict[str, Any]:
        """Tenant-facing connector facts — never expose bare platform ``configured``.

        Upstream Docker services report configured=true for every tenant; Hermes
        was reading that as «у вас почта/календарь уже настроены». Only
        enabled+usable means the owner opted in.
        """
        item = by_kind.get(kind) or {}
        row = readiness.get(kind) or {}
        enabled = bool(item.get("enabled") or row.get("enabled"))
        usable = bool(row.get("usable"))
        platform = bool(item.get("configured") or (item.get("status") or {}).get("configured"))
        if usable:
            summary = "подключено и usable для этого кабинета"
        elif enabled and row.get("reason") == "owner_account_required":
            summary = "НЕ подключено: флаг включён, но своего аккаунта владельца нет — спроси, какой сервис"
        elif enabled and row.get("reason") == "account_verified_upstream_pending":
            summary = "аккаунт владельца проверен, но платформа ещё не работает через него — НЕ подключено"
        elif enabled:
            summary = f"включено у тенанта, но не usable ({row.get('reason') or 'нет кредов'})"
        elif platform:
            summary = "платформа доступна; у ЭТОГО кабинета НЕ включено и НЕ настроено"
        else:
            summary = "не подключено"
        return {
            "tenant_enabled": enabled,
            "tenant_usable": usable,
            "platform_upstream": platform,
            "reason": row.get("reason"),
            "summary_ru": summary,
            # Keep ok aligned with checklist — LLMs key off nested ok hard.
            "ok": usable,
            "configured": usable,
        }

    kb_info = company_knowledge_ready(db, ctx, hermes=hermes)
    kb_done = bool(kb_info.get("ok"))

    sip_items = list_secret_status(db, ctx).get("items") or []
    sip_row = next((i for i in sip_items if i.get("kind") == "mango_sip"), None) or {}
    sip_ok = bool(sip_row.get("configured"))
    # Platform-wide Mango registration must NOT leak into a tenant without vault SIP.
    registration: dict[str, Any] = {
        "ok": False,
        "status": "not_applicable",
        "reachable": False,
        "message_ru": "SIP этого кабинета не сохранён — общая регистрация Mango не считается вашей.",
    }
    if sip_ok:
        try:
            from app.services.sip_probe import probe_registration

            # Always probe THIS tenant's registration — never a shared dogfood line.
            registration = probe_registration(ctx.tenant_slug)
        except Exception:  # noqa: BLE001
            registration = {"ok": False, "status": "unknown", "reachable": False}
    reg_ok = bool(sip_ok and registration.get("ok"))
    # Vault alone is not enough — Mango must show Registered or inbound gets «операторы заняты».
    phone_ok = phones > 0 and sip_ok and reg_ok
    phone_detail = {
        "active_dids": phones,
        "sip_configured": sip_ok,
        "sip_login_masked": sip_row.get("login_masked") or "",
        "registration_status": registration.get("status"),
        "registration_ok": reg_ok,
        "registration_message": registration.get("message_ru"),
        "summary_ru": (
            "телефония готова"
            if phone_ok
            else (
                "есть DID, но нет SIP этого кабинета"
                if phones and not sip_ok
                else (
                    "нет активного DID"
                    if not phones
                    else "SIP есть, регистрация не Registered"
                )
            )
        ),
        "telephony_provider": settings.get("telephony_provider")
        if isinstance(settings.get("telephony_provider"), (dict, str))
        else None,
    }

    telephony = settings.get("telephony") if isinstance(settings.get("telephony"), dict) else {}
    script_ok = bool(hermes.get("telephony_script_ready")) or bool((telephony.get("script") or "").strip())

    checks = {
        "kb": {"ok": kb_done, "detail": kb_info},
        "phone": {"ok": phone_ok, "detail": phone_detail},
        "telephony_script": {
            "ok": script_ok,
            "detail": {
                "configured": script_ok,
                "tools": telephony.get("tools") or [],
                "greeting": (telephony.get("greeting") or "")[:120],
            },
        },
        # Messenger bots are recommended but not blockers for office ready —
        # phone + mail/calendar/conference + KB/script already enable conduct.
        "telegram": {"ok": tg > 0, "detail": f"accounts={tg}", "optional": True},
        "max": {"ok": max_n > 0, "detail": f"accounts={max_n}", "optional": True},
        "files": {"ok": False, "detail": {}, "optional": True},
        "calendar": {"ok": _conn_ok("calendar"), "detail": _conn_detail("calendar")},
        "mail": {"ok": _conn_ok("mail"), "detail": _conn_detail("mail")},
        "conference": {
            "ok": _conn_ok("conference"),
            "detail": _conn_detail("conference"),
        },
        "outreach": {
            "ok": _conn_ok("outreach"),
            "detail": _conn_detail("outreach"),
            "optional": True,
        },
    }
    try:
        from app.services.files_cloud import cloud_status

        clouds = cloud_status(db, ctx)
        ready_count = int(clouds.get("ready_count") or 0)
        checks["files"] = {
            "ok": ready_count > 0,
            "detail": {
                "tenant_usable": ready_count > 0,
                "ready_count": ready_count,
                "ok": ready_count > 0,
                "configured": ready_count > 0,
                "summary_ru": (
                    f"подключено облаков: {ready_count}"
                    if ready_count
                    else "у этого кабинета облако НЕ подключено"
                ),
                "items": clouds.get("items") or [],
            },
            "optional": True,
        }
    except Exception:  # noqa: BLE001
        pass

    steps = _setup_steps()
    # A step added after process start must still have a check row.
    for step in steps:
        checks.setdefault(
            step["id"],
            {
                "ok": False,
                "detail": "not_checked",
                "optional": bool(step.get("optional", True)),
            },
        )
        checks[step["id"]]["optional"] = True
    goal = str(hermes.get("goal") or "").strip()
    known_ids = {s["id"] for s in steps}
    requested_raw = hermes.get("requested_instruments")
    requested = [
        str(ident) for ident in (requested_raw if isinstance(requested_raw, list) else [])
        if str(ident) in known_ids
    ]
    deferred_raw = hermes.get("deferred_instruments")
    deferred = {str(x) for x in deferred_raw} if isinstance(deferred_raw, list) else set()
    known_raw = hermes.get("known_instruments")
    new_instruments = (
        [step for step in steps if step["id"] not in set(known_raw)]
        if isinstance(known_raw, list) else []
    )
    next_steps = []
    steps_by_id = {step["id"]: step for step in steps}
    for ident in requested:
        step = steps_by_id[ident]
        c = checks[step["id"]]
        if c["ok"]:
            continue
        if step["id"] in deferred:
            continue
        next_steps.append({**step, "status": "todo", "check": c})

    done_req = sum(1 for ident in requested if checks[ident]["ok"])
    # A goal can need no external connector. Missing tools are actionable
    # suggestions, never a platform-wide gate on using the agent.
    setup_complete = bool(goal) and not next_steps
    try:
        from app.services.ava_readiness import line_status
        from app.services.instrument_catalog import inventory_from_checks

        ava = line_status(db, ctx, phone_ok=bool((checks.get("phone") or {}).get("ok")))
        instruments = inventory_from_checks(checks, deferred=deferred)
    except Exception:  # noqa: BLE001
        ava = {"test_call_allowed": False, "message_ru": ""}
        instruments = {"platform": [], "connected": [], "missing": [], "stitches": []}
    return {
        "ok": True,
        "tenant_slug": ctx.tenant_slug,
        "setup_complete": setup_complete,
        "progress": {
            "required_done": done_req,
            "required_total": len(requested),
            "connected_total": sum(1 for step in steps if checks[step["id"]]["ok"]),
            "available_total": len(steps),
        },
        "goal": goal,
        "requested_instruments": requested,
        "new_instruments": new_instruments,
        "checks": checks,
        "steps": steps,
        "next_steps": next_steps[:3],
        "deferred_instruments": sorted(deferred),
        "instruments": instruments,
        "ava": ava,
        "sip_last": settings.get("telephony_sip_last")
        if isinstance(settings.get("telephony_sip_last"), dict)
        else None,
        "hermes": {
            "setup_started_at": hermes.get("setup_started_at"),
            "setup_completed_at": hermes.get("setup_completed_at"),
            "last_health_at": hermes.get("last_health_at"),
            "open_alerts": hermes.get("open_alerts") or [],
        },
        "message_ru": (
            "Расскажите, какую задачу поручить агенту. Он предложит только нужные подключения."
            if not goal
            else (
                "Для выбранной задачи можно подключить: "
                + ", ".join(step["title"] for step in next_steps[:3])
                + ". Остальные инструменты доступны позже."
                if next_steps
                else "Агент готов выполнять выбранную задачу. Новые инструменты можно подключить позже."
            )
        ),
    }


def set_owner_goal(
    db: Session,
    ctx: TenantContext,
    *,
    goal: str,
    requested_instruments: list[str] | None = None,
) -> dict[str, Any]:
    """Save an owner's task and the tools they agreed to connect for it."""
    from app.services.instrument_catalog import get_instrument

    goal = goal.strip()
    if not goal or len(goal) > 1000:
        return {"ok": False, "error": "invalid_goal"}
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = _settings(tenant)
    hermes = dict(settings.get("hermes") or {})
    source = requested_instruments if requested_instruments is not None else hermes.get("requested_instruments") or []
    requested = list(dict.fromkeys(str(x).strip() for x in source))
    unknown = [ident for ident in requested if not get_instrument(ident)]
    if unknown:
        return {"ok": False, "error": "unknown_instrument", "ids": unknown}
    hermes["goal"] = goal
    hermes["requested_instruments"] = requested
    if not isinstance(hermes.get("known_instruments"), list):
        from app.services.instrument_catalog import all_instruments

        hermes["known_instruments"] = [item.id for item in all_instruments()]
    settings["hermes"] = hermes
    tenant.settings = settings
    db.add(tenant)
    write_audit(
        db, ctx,
        action="hermes.goal_set",
        resource="tenant:hermes_goal",
        new_value={"goal": goal, "requested_instruments": requested},
    )
    db.commit()
    return office_setup_status(db, ctx)


def acknowledge_new_instruments(db: Session, ctx: TenantContext, ids: list[str]) -> dict[str, Any]:
    """Remember that the owner has been told about newly available tools."""
    from app.services.instrument_catalog import all_instruments

    current = {item.id for item in all_instruments()}
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = _settings(tenant)
    hermes = dict(settings.get("hermes") or {})
    known = set(hermes.get("known_instruments") or current)
    known.update(ident for ident in ids if ident in current)
    hermes["known_instruments"] = sorted(known)
    settings["hermes"] = hermes
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    return office_setup_status(db, ctx)


def mark_setup_progress(
    db: Session,
    ctx: TenantContext,
    *,
    kb_ready: bool | None = None,
    note: str | None = None,
    defer_instrument: str | None = None,
    resume_instrument: str | None = None,
    resume_all: bool = False,
) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = _settings(tenant)
    hermes = dict(settings.get("hermes") or {})
    if not hermes.get("setup_started_at"):
        hermes["setup_started_at"] = _now_iso()
    if kb_ready is not None:
        hermes["kb_ready"] = bool(kb_ready)
        if kb_ready:
            hermes["company_profile_ready"] = True
            hermes["kb_source"] = hermes.get("kb_source") or "owner_upload"
        else:
            hermes["company_profile_ready"] = False
    if note:
        hermes["last_setup_note"] = note[:500]
        if note.strip().lower() in {"dogfood seed", "dogfood", "seed"}:
            # Seed must not skip the company-profile step for a real owner.
            hermes["kb_ready"] = False
            hermes["company_profile_ready"] = False
            hermes.pop("kb_source", None)
    deferred = [str(x) for x in (hermes.get("deferred_instruments") or []) if str(x).strip()]
    if resume_all:
        deferred = []
    if resume_instrument:
        deferred = [x for x in deferred if x != resume_instrument.strip()]
    if defer_instrument:
        ident = defer_instrument.strip()
        from app.services.instrument_catalog import get_instrument

        if ident and get_instrument(ident) and ident not in deferred:
            deferred.append(ident)
    hermes["deferred_instruments"] = deferred
    settings["hermes"] = hermes
    tenant.settings = settings
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
    readiness_rows = list_tenant_connector_readiness(db, ctx)
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
    hermes_settings = _settings(tenant).get("hermes") or {}
    requested_phone = "phone" in (hermes_settings.get("requested_instruments") or [])
    phone_in_use = requested_phone or bool(active_dids) or sip_ok
    if phone_in_use and not active_dids:
        alerts.append(
            {
                "code": "phone.no_active_did",
                "severity": "warning",
                "message_ru": "Нет активного телефонного номера. Входящие и исходящие звонки недоступны.",
                "fix": "Привяжите DID через phones.provision или скажите Hermes номер.",
            }
        )
    if phone_in_use and not sip_ok:
        alerts.append(
            {
                "code": "phone.sip_missing",
                "severity": "warning",
                "message_ru": "SIP Mango ещё не сохранён в сейфе кабинета — линия не регистрируется.",
                "fix": "Скажите «настрой телефон» и заполните безопасную форму (SIP-логин вида ivan@vpbx123456789.mangosip.ru).",
            }
        )
    elif phone_in_use:
        # Always probe live registration. A missing "/" in the masked login is only a
        # heuristic for incomplete vault saves — if Mango already shows Registered,
        # do not mark the office unhealthy on that heuristic alone.
        try:
            from app.services.sip_probe import probe_registration

            reg = probe_registration(ctx.tenant_slug)
        except Exception:  # noqa: BLE001
            reg = {"ok": False, "status": "unknown", "reachable": False}
        login_masked = str(sip_row.get("login_masked") or "")
        looks_partial = "/" not in login_masked
        if not reg.get("ok"):
            if looks_partial:
                alerts.append(
                    {
                        "code": "phone.sip_login_partial",
                        "severity": "warning",
                        "message_ru": "SIP-логин похож на неполный (нужен вид номер/сотрудник).",
                        "fix": "Откройте форму SIP ещё раз и сохраните полный логин Mango.",
                    }
                )
            else:
                status = str(reg.get("status") or "unknown")
                alerts.append(
                    {
                        "code": f"phone.sip_{status}",
                        "severity": "critical" if status == "rejected" else "warning",
                        "message_ru": (
                            reg.get("message_ru")
                            or "Линия SIP не Registered — входящие уйдут в «все операторы заняты»."
                        ),
                        "fix": (
                            "Откройте форму SIP и сохраните актуальный SIP-пароль сотрудника Mango "
                            "(не пароль от веб-кабинета). Затем скажите «проверь регистрацию SIP»."
                        ),
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
        if ch.status in ("active", "cancelled", "disconnected"):
            continue
        if ch.status == "pending_qr":
            alerts.append(
                {
                    "code": f"channel.{ch.type}.pending_qr",
                    "severity": "info",
                    "message_ru": (
                        f"Канал {ch.type}: QR-сессия не завершена. "
                        f"Скажите «подключи {ch.type}» и выберите бота или QR."
                    ),
                    "fix": (
                        "Рекомендуем бота (токен) — стабильнее для клиентов. "
                        "Или завершите QR, когда появится картинка."
                    ),
                }
            )
            continue
        alerts.append(
            {
                "code": f"channel.{ch.type}.degraded",
                "severity": "warning",
                "message_ru": f"Канал {ch.type} в статусе «{ch.status}».",
                "fix": f"Скажите «подключи {ch.type}» — выберем бота или QR.",
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

    blocking = [a for a in alerts if a.get("severity") in ("warning", "critical")]
    user_summary = (
        "Все основные компоненты в порядке."
        if not blocking
        else "Есть проблемы: " + "; ".join(a["message_ru"] for a in blocking[:3])
    )
    # Never hand Hermes raw platform ``configured: true`` — that looks like tenant setup.
    connectors_for_agent: list[dict[str, Any]] = []
    for row in readiness_rows:
        kind = row.get("kind")
        usable = bool(row.get("usable"))
        enabled = bool(row.get("enabled"))
        connectors_for_agent.append(
            {
                "kind": kind,
                "enabled": enabled,
                "usable": usable,
                "ready": usable,
                "configured": usable,
                "ok": usable,
                "reason": row.get("reason"),
                "summary_ru": (
                    "подключено для этого кабинета"
                    if usable
                    else (
                        f"включено, но не usable ({row.get('reason') or 'нет кредов'})"
                        if enabled
                        else "у этого кабинета НЕ подключено (платформа ≠ ваш аккаунт)"
                    )
                ),
            }
        )
    return {
        "ok": True,
        "healthy": len(blocking) == 0,
        "alerts": alerts,
        "telephony": {
            "active_dids": active_dids,
            "queued_jobs": queued_jobs,
            "stuck_jobs": stuck_jobs,
            "recent_failed_sessions": recent_fail_calls,
            "sip_configured": sip_ok,
        },
        "channels": [
            {"type": c.type, "status": c.status, "id": str(c.id)} for c in channels
        ],
        "connectors": connectors_for_agent,
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
