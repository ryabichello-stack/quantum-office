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
    kb_ok = bool((setup.get("checks") or {}).get("company_knowledge", {}).get("ok"))
    connectors = setup.get("checks") or {}
    connector_ready = sum(
        1
        for k, v in connectors.items()
        if k not in ("company_knowledge",) and isinstance(v, dict) and v.get("ok")
    )
    phase = str(loop.get("phase") or "welcome")
    if kb_ok and phase in ("welcome", "company_kb"):
        phase = "connectors" if connector_ready == 0 else phase
    if kb_ok and connector_ready >= 1 and phase in ("welcome", "company_kb", "connectors"):
        # at least KB + one connector → can mark ready suggestion
        pass
    if setup.get("setup_complete"):
        phase = loop.get("phase") if loop.get("phase") == "conduct" else "ready"

    kb_draft = loop.get("kb_draft") if isinstance(loop.get("kb_draft"), dict) else None
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
            "hint": "Почта / Telegram / календарь / телефон — по шагам с формами",
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
        "kb_ok": kb_ok,
        "kb_draft": kb_draft,
        "connectors_ready_count": connector_ready,
        "setup": {
            "setup_complete": bool(setup.get("setup_complete")),
            "progress": setup.get("progress"),
            "message_ru": setup.get("message_ru"),
        },
        "ui": {
            "headline": _headline(phase, kb_ok),
            "primary_cta": _cta(phase, kb_ok),
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
    from app.operator.tools.registry import registry

    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    nous = _nous(tenant)
    loop = dict(nous.get("office_loop") or {})
    draft = loop.get("kb_draft") if isinstance(loop.get("kb_draft"), dict) else None
    if not draft or not str(draft.get("body") or "").strip():
        return {"ok": False, "error": "no_kb_draft"}

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
    return {"ok": True, "committed": True, "loop": get_office_loop(db, ctx)}


def _headline(phase: str, kb_ok: bool) -> str:
    if phase == "welcome":
        return "Давайте настроим ваш офис"
    if phase == "company_kb" or not kb_ok:
        return "Соберём базу знаний компании"
    if phase == "connectors":
        return "Подключим инструменты по шагам"
    if phase == "ready":
        return "Офис готов — можно давать поручения"
    return "Гермес дирижирует вашими инструментами"


def _cta(phase: str, kb_ok: bool) -> dict[str, str]:
    if phase == "welcome" or (phase == "company_kb" and not kb_ok):
        return {
            "title": "Сайт → знания",
            "text": "Вот ссылка на наш сайт — собери базу знаний и покажи черновик",
        }
    if phase == "connectors":
        return {
            "title": "Подключить канал",
            "text": "Что подключить следующим: почту, Telegram или календарь? Проведи меня по шагам",
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
