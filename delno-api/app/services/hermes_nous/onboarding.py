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
    # Auto-advance forward from facts; never clobber an explicit later phase
    # (set_phase / tests / owner skipping a step).
    phase = str(loop.get("phase") or "welcome")
    if kb_ok and phase in ("welcome", "company_kb"):
        phase = "connectors"
    if setup.get("setup_complete") and phase not in ("ready", "conduct"):
        phase = "ready"
    if setup.get("setup_complete") and loop.get("phase") == "conduct":
        phase = "conduct"

    kb_draft = loop.get("kb_draft") if isinstance(loop.get("kb_draft"), dict) else None
    # Concrete next item from hermes_ops checklist (source of truth for "что дальше").
    setup_next_raw = (setup.get("next_steps") or [None])[0]
    setup_next = None
    if isinstance(setup_next_raw, dict) and setup_next_raw.get("id"):
        setup_next = {
            "id": setup_next_raw.get("id"),
            "title": setup_next_raw.get("title") or setup_next_raw.get("id"),
            "hint": setup_next_raw.get("hint") or "",
        }
    steps = [
        {
            "id": "welcome",
            "title": "Старт",
            "done": phase != "welcome",
            "hint": "Гермес знакомится и предлагает собрать знания о компании",
        },
        {
            "id": "company_kb",
            "title": "База знаний",
            "done": kb_ok,
            "hint": "Сайт, каталог или текст → черновик KB → подтверждение",
        },
        {
            "id": "connectors",
            "title": "Инструменты",
            "done": connector_ready >= 1,
            "hint": (
                f"Сейчас по сетапу: {setup_next['title']}. {setup_next.get('hint') or ''}".strip()
                if setup_next and kb_ok
                else "Почта / Telegram / календарь / телефон — по шагам с формами"
            ),
        },
        {
            "id": "ready",
            "title": "Офис готов",
            "done": bool(setup.get("setup_complete")) or phase in ("ready", "conduct"),
            "hint": "Health зелёный, можно давать поручения",
        },
        {
            "id": "conduct",
            "title": "Дирижирование",
            "done": phase == "conduct",
            "hint": "Поручения, субагенты, cron — на живых тулах",
        },
    ]
    next_step = next((s for s in steps if not s["done"]), steps[-1])
    return {
        "ok": True,
        "engine": "nous_hermes_agent",
        "phase": phase,
        "phases": list(PHASES),
        "steps": steps,
        "next_step": next_step,
        "setup_next": setup_next,
        "kb_ok": kb_ok,
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


def _headline(phase: str, kb_ok: bool, setup_next: dict[str, Any] | None = None) -> str:
    if phase == "welcome":
        return "Давайте настроим ваш офис"
    if phase == "company_kb" or not kb_ok:
        return "Соберём базу знаний компании"
    if phase == "connectors":
        if setup_next and setup_next.get("title"):
            return f"Следующий шаг сетапа: {setup_next['title']}"
        return "Подключим инструменты по шагам"
    if phase == "ready":
        return "Офис готов — можно давать поручения"
    return "Гермес дирижирует вашими инструментами"


def _cta(phase: str, kb_ok: bool, setup_next: dict[str, Any] | None = None) -> dict[str, str]:
    if phase == "welcome" or (phase == "company_kb" and not kb_ok):
        return {
            "title": "Сайт → знания",
            # Owner must supply a real URL in chat; do not pretend one was given.
            "text": "Помоги собрать базу знаний: скажи, какую ссылку на сайт прислать, или прими текст о компании и покажи черновик",
        }
    if phase == "connectors":
        sid = str((setup_next or {}).get("id") or "")
        title = str((setup_next or {}).get("title") or "инструмент")
        hint = str((setup_next or {}).get("hint") or "")
        if sid == "phone":
            return {
                "title": f"Настроить: {title}",
                "text": (
                    "База знаний уже есть. Следующий шаг hermes_ops — телефония (DID + SIP). "
                    "Вызови hermes.setup_status, объясни что нужно, открой credentials.open_form "
                    "для mango_sip если секрета нет. Не предлагай снова импортировать KB."
                ),
            }
        if sid in {"telegram", "max", "mail", "calendar", "conference", "files"}:
            return {
                "title": f"Подключить: {title}",
                "text": (
                    f"KB готова. Следующий шаг сетапа — «{title}». {hint} "
                    "Проведи по шагам через hermes.setup_status и credentials.open_form. "
                    "Не предлагай снова собирать базу знаний."
                ),
            }
        return {
            "title": "Подключить инструмент",
            "text": (
                "KB готова. Вызови hermes.setup_status и проведи к следующему незакрытому шагу "
                "(форма секрета при необходимости). Не предлагай импорт KB заново."
            ),
        }
    if phase == "ready":
        return {
            "title": "Первое поручение",
            "text": "Ответь по базе знаний: кто мы и что предлагаем клиентам",
        }
    return {
        "title": "Задача",
        "text": "Составь план и выполни: проверь здоровье офиса и скажи, что улучшить",
    }
