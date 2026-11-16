"""Product loop state: onboarding → KB → connectors → ready → conduct."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services import hermes_ops


PHASES = (
    "welcome",
    "company_kb",
    "connectors",
    "ready",
    "conduct",
)


def _settings(tenant: Tenant) -> dict[str, Any]:
    return dict(tenant.settings) if isinstance(tenant.settings, dict) else {}


def _nous(tenant: Tenant) -> dict[str, Any]:
    blob = _settings(tenant).get("hermes_nous")
    return dict(blob) if isinstance(blob, dict) else {}


def _save_nous(db: Session, tenant: Tenant, nous: dict[str, Any]) -> None:
    settings = _settings(tenant)
    settings["hermes_nous"] = nous
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    db.refresh(tenant)


def get_office_loop(db: Session, ctx: TenantContext) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    nous = _nous(tenant)
    loop = dict(nous.get("office_loop") or {})
    setup = hermes_ops.office_setup_status(db, ctx)
    checks = setup.get("checks") if isinstance(setup.get("checks"), dict) else {}
    # hermes_ops uses check id "kb"; older fixtures used company_knowledge.
    kb_check = checks.get("kb") if isinstance(checks.get("kb"), dict) else {}
    if not kb_check:
        kb_check = checks.get("company_knowledge") if isinstance(checks.get("company_knowledge"), dict) else {}
    kb_ok = bool(kb_check.get("ok"))
    # Channels / tools — exclude KB + script meta from connector count.
    _not_connector = {"kb", "telephony_script", "company_knowledge"}
    connector_ready = sum(
        1 for k, v in checks.items() if k not in _not_connector and isinstance(v, dict) and v.get("ok")
    )
    goal = str(setup.get("goal") or "").strip()
    # The owner's goal drives the flow. Knowledge and channels never gate it.
    phase = str(loop.get("phase") or "welcome")
    if phase == "welcome" and goal:
        phase = "ready" if setup.get("setup_complete") else "connectors"
    elif phase in ("company_kb", "connectors") and goal and setup.get("setup_complete"):
        phase = "ready"

    kb_draft = loop.get("kb_draft") if isinstance(loop.get("kb_draft"), dict) else None
    # Concrete next item from hermes_ops checklist (source of truth for "что дальше").
    setup_next_raw = (setup.get("next_steps") or [None])[0]
    setup_next = None
    if isinstance(setup_next_raw, dict) and setup_next_raw.get("id"):
        check = setup_next_raw.get("check") if isinstance(setup_next_raw.get("check"), dict) else {}
        detail = check.get("detail") if isinstance(check.get("detail"), dict) else {}
        setup_next = {
            "id": setup_next_raw.get("id"),
            "title": setup_next_raw.get("title") or setup_next_raw.get("id"),
            "hint": setup_next_raw.get("hint") or "",
            "substep": _setup_substep(str(setup_next_raw.get("id") or ""), detail),
            "detail": detail or None,
        }
        # Prefer concrete substep hint over generic SETUP_STEPS hint.
        if setup_next["substep"] and setup_next["id"] == "phone":
            setup_next["hint"] = _phone_hint(setup_next["substep"], detail) or setup_next["hint"]
    steps = [
        {"id": "welcome", "title": "Ваша задача", "done": bool(goal),
         "hint": "Расскажите, что поручить агенту"},
        {"id": "company_kb", "title": "Знания (при необходимости)",
         "done": kb_ok, "optional": True,
         "hint": "Добавьте сведения о компании, если агент должен отвечать на вопросы о ней"},
        {"id": "connectors", "title": "Нужные инструменты",
         "done": not bool(setup_next),
         "hint": "Подключайте только то, что помогает вашей задаче"},
        {"id": "conduct", "title": "Работа",
         "done": bool(goal),
         "hint": "Агент уже может работать с доступными инструментами"},
    ]
    next_step = next((s for s in steps if not s["done"] and not s.get("optional")), steps[-1])
    return {
        "ok": True,
        "engine": "nous_hermes_agent",
        "phase": phase,
        "phases": list(PHASES),
        "steps": steps,
        "next_step": next_step,
        "setup_next": setup_next,
        "kb_ok": kb_ok,
        "goal": goal,
        "kb_draft": kb_draft,
        "connectors_ready_count": connector_ready,
        "setup": {
            "setup_complete": bool(setup.get("setup_complete")),
            "progress": setup.get("progress"),
            "message_ru": setup.get("message_ru"),
        },
        "ui": {
            "headline": _headline(phase, kb_ok, setup_next),
            "primary_cta": _cta(phase, kb_ok, setup_next),
        },
    }


def set_phase(db: Session, ctx: TenantContext, phase: str) -> dict[str, Any]:
    if phase not in PHASES:
        return {"ok": False, "error": "invalid_phase", "allowed": list(PHASES)}
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    nous = _nous(tenant)
    loop = dict(nous.get("office_loop") or {})
    loop["phase"] = phase
    loop["updated_at"] = datetime.now(timezone.utc).isoformat()
    nous["office_loop"] = loop
    _save_nous(db, tenant, nous)
    return get_office_loop(db, ctx)


def save_kb_draft(
    db: Session,
    ctx: TenantContext,
    *,
    title: str,
    body: str,
    source_url: str | None = None,
) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    nous = _nous(tenant)
    loop = dict(nous.get("office_loop") or {})
    loop["kb_draft"] = {
        "title": (title or "Профиль компании")[:200],
        "body": (body or "")[:50_000],
        "source_url": (source_url or "")[:500] or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft",
    }
    loop["phase"] = "company_kb"
    nous["office_loop"] = loop
    _save_nous(db, tenant, nous)
    return {"ok": True, "kb_draft": loop["kb_draft"], "loop": get_office_loop(db, ctx)}


def confirm_kb_draft(db: Session, ctx: TenantContext) -> dict[str, Any]:
    """Commit draft into knowledge via upload_knowledge_snippet tool path."""
    from app.operator.tools import register_builtin_tools
    from app.operator.tools.registry import registry

    register_builtin_tools()
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    nous = _nous(tenant)
    loop = dict(nous.get("office_loop") or {})
    draft = loop.get("kb_draft") if isinstance(loop.get("kb_draft"), dict) else None
    if not draft or not str(draft.get("body") or "").strip():
        return {"ok": False, "error": "no_kb_draft"}
    if str(draft.get("status") or "") == "committed":
        loop["phase"] = loop.get("phase") or "connectors"
        nous["office_loop"] = loop
        _save_nous(db, tenant, nous)
        # Idempotent: still align settings.hermes if KB step was confirmed earlier.
        hermes_ops.mark_setup_progress(
            db,
            ctx,
            kb_ready=True,
            note="office_loop.kb_draft_already_committed",
        )
        return {"ok": True, "committed": True, "already": True, "loop": get_office_loop(db, ctx)}

    title = str(draft.get("title") or "Профиль компании")
    body = str(draft.get("body") or "")
    src = draft.get("source_url")
    if src:
        body = f"Источник: {src}\n\n{body}"

    tool = registry.get("upload_knowledge_snippet")
    if not tool:
        return {"ok": False, "error": "upload_tool_missing"}
    result = registry.run(
        db,
        ctx,
        "upload_knowledge_snippet",
        title=title,
        body=body,
        visibility="company",
    )
    ok = bool(getattr(result, "ok", True)) if not isinstance(result, dict) else bool(result.get("ok", True))
    if not ok:
        return {"ok": False, "error": "upload_failed", "result": getattr(result, "data", result)}

    draft["status"] = "committed"
    draft["committed_at"] = datetime.now(timezone.utc).isoformat()
    loop["kb_draft"] = draft
    loop["phase"] = "connectors"
    nous["office_loop"] = loop
    _save_nous(db, tenant, nous)
    # Canon: readiness lives in settings.hermes (hermes_ops), NOT hermes_nous.
    hermes_ops.mark_setup_progress(
        db,
        ctx,
        kb_ready=True,
        note="office_loop.kb_draft_confirm",
    )
    return {"ok": True, "committed": True, "loop": get_office_loop(db, ctx)}


def _provider_code(detail: dict[str, Any]) -> str:
    raw = detail.get("telephony_provider")
    if isinstance(raw, dict):
        return str(raw.get("provider") or "").strip().lower()
    return str(raw or "").strip().lower()


def _setup_substep(step_id: str, detail: dict[str, Any]) -> str | None:
    """Break hermes_ops phone (and similar) into actionable micro-steps.

    Order: choose operator (Mango) → number → SIP vault → Registered.
    State for the operator lives in tenant.settings.telephony_provider.
    """
    if step_id != "phone":
        return None
    if _provider_code(detail) != "mango":
        return "need_operator"
    if int(detail.get("active_dids") or 0) <= 0:
        return "need_did"
    if not detail.get("sip_configured"):
        return "need_sip"
    if not detail.get("registration_ok"):
        return "need_reg"
    return None


def _phone_hint(substep: str, detail: dict[str, Any]) -> str:
    if substep == "need_operator":
        return (
            "Сейчас мы работаем **только с Манго Телеком (Mango Office)**. "
            "Какой у вас оператор?"
        )
    if substep == "need_did":
        return "Пришлите номер в формате **+7 987 123-45-67**"
    if substep == "need_sip":
        return (
            "DID есть — открой credentials.open_form mango_sip "
            "(логин аккаунт/сотрудник + SIP-пароль; пароль не в чат)"
        )
    if substep == "need_reg":
        status = detail.get("registration_status") or "unknown"
        msg = detail.get("registration_message") or ""
        if str(status).lower() == "rejected" or "reject" in str(msg).lower():
            return (
                f"Mango Rejected (status={status}). "
                "Сразу credentials.open_form mango_sip — проверить логин аккаунт/сотрудник и SIP-пароль. "
                f"{msg}"
            ).strip()
        return (
            f"DID и SIP в сейфе, линия не Registered (status={status}). "
            "Снова credentials.open_form mango_sip. "
            f"{msg}"
        ).strip()
    return ""


def _headline(phase: str, kb_ok: bool, setup_next: dict[str, Any] | None = None) -> str:
    if phase == "welcome":
        return "Что поручить вашему агенту?"
    if phase == "company_kb":
        return "Добавим знания, если они нужны задаче"
    if phase == "connectors":
        if setup_next and setup_next.get("title"):
            sub = setup_next.get("substep")
            if setup_next.get("id") == "phone" and sub == "need_operator":
                return "Телефон: какой у вас оператор?"
            if setup_next.get("id") == "phone" and sub == "need_did":
                return "Телефон: пришлите номер Манго"
            if setup_next.get("id") == "phone" and sub == "need_sip":
                return "Телефон: данные для подключения"
            if setup_next.get("id") == "phone" and sub == "need_reg":
                return "Телефон: ждём, пока линия заработает"
            if setup_next.get("id") == "telephony_script":
                return "Сценарий секретаря"
            return f"Для вашей задачи: {setup_next['title']}"
        return "Подключайте инструменты по мере необходимости"
    if phase == "ready":
        return "Офис готов — можно давать поручения"
    return "Гермес дирижирует вашими инструментами"


def _cta(phase: str, kb_ok: bool, setup_next: dict[str, Any] | None = None) -> dict[str, str]:
    if phase == "welcome" or (phase == "company_kb" and not kb_ok):
        return {
            "title": "Расскажите о задаче",
            "text": "Что вы хотите поручить агенту? Я предложу подходящие инструменты.",
        }
    if phase == "connectors":
        sid = str((setup_next or {}).get("id") or "")
        title = str((setup_next or {}).get("title") or "инструмент")
        hint = str((setup_next or {}).get("hint") or "")
        sub = str((setup_next or {}).get("substep") or "")
        if sid == "phone":
            if sub == "need_operator":
                return {
                    "title": "Подключить Манго",
                    "text": (
                        "Сейчас мы работаем только с Манго Телеком (Mango Office). "
                        "Спроси оператора. Манго → telephony.provider_set provider=mango. "
                        "Другой → telephony.provider_set provider=other "
                        "(заявка «скоро», шаг телефона можно отложить). Номер пока не проси."
                    ),
                }
            if sub == "need_did":
                return {
                    "title": "Подключить номер",
                    "text": (
                        "Оператор — Манго. Попроси номер в формате +7 987 123-45-67. "
                        "Только номер ЭТОГО кабинета, без чужих и демо. "
                        "phones.list → если номер назван — phones.provision. "
                        "Сразу после phones.provision открой форму доступа к линии. "
                        "Не предлагай импортировать KB."
                    ),
                }
            if sub == "need_reg":
                return {
                    "title": "Проверить регистрацию SIP",
                    "text": (
                        "SIP и DID этого кабинета есть, но линия не Registered. Вызови "
                        "hermes.setup_status / hermes.health, объясни status и next_actions. "
                        "Не предлагай импортировать KB."
                    ),
                }
            return {
                "title": f"Настроить: {title}",
                "text": (
                    "DID уже привязан. Открой credentials.open_form mango_sip — "
                    "логин вида аккаунт/сотрудник + SIP-пароль Mango (не веб). "
                    "Линия регистрируется только для ЭТОГО tenant. "
                    "Не предлагай снова импортировать KB."
                ),
            }
        if sid == "telephony_script":
            return {
                "title": "Сценарий секретаря",
                "text": (
                    "Номер уже работает. Пробный звонок рано. "
                    "Собери сценарий из базы: telephony.script_propose (не ограничивайся telephony.script_get), "
                    "покажи текст простыми словами, после «да» — telephony.script_save. "
                    "Затем telephony.voice_set voice=cedar и telephony.tools_set "
                    "с календарём, письмом и видеовстречей. "
                    "Пробный звонок только когда ava.test_call_allowed. "
                    "Не открывай форму телефона заново и не предлагай импортировать KB."
                ),
            }
        if sid == "telegram":
            return {
                "title": f"Подключить: {title}",
                "text": (
                    "Открой безопасную форму credentials.open_form для telegram_bot "
                    "(токен @BotFather). Не проси токен в чат и не предлагай импортировать KB."
                ),
            }
        if sid == "max":
            return {
                "title": f"Подключить: {title}",
                "text": (
                    "Открой безопасную форму credentials.open_form для max_bot "
                    "(access token). Не проси токен в чат и не предлагай импортировать KB."
                ),
            }
        if sid == "files":
            return {
                "title": "Подключить облако",
                "text": (
                    "Открой безопасную форму credentials.open_form для files_yadisk "
                    "(РФ по умолчанию; иначе files_mailru / files_gdrive / files_onedrive). "
                    "Не проси токен в чат и не предлагай импортировать KB."
                ),
            }
        if sid in {"mail", "calendar", "conference"}:
            return {
                "title": f"Подключить: {title}",
                "text": (
                    f"Вызови office.connector_set kind={sid} enabled=true, затем hermes.setup_status. "
                    "Говори «подключено» ТОЛЬКО если setup_status показывает ok для этого шага. "
                    "Флаг включения — это ещё не подключение: для календаря и почты нужен свой аккаунт "
                    "владельца (спроси, какой сервис, и открой credentials.open_form). "
                    f"{hint} Не предлагай снова собирать базу знаний."
                ),
            }
        return {
            "title": "Подключить инструмент",
            "text": "Подключи выбранный инструмент, если владелец согласен; остальные доступны позже.",
        }
    if phase == "ready":
        return {
            "title": "Дать поручение",
            "text": "Расскажите, что сделать сейчас. Новые подключения можно добавить по ходу работы.",
        }
    return {
        "title": "Задача",
        "text": "Составь план и выполни: проверь здоровье офиса и скажи, что улучшить",
    }
