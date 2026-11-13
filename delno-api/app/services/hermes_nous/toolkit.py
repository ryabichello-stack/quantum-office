"""Owner-facing toolkit inventory: connectors + AVA/telephony tools status."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools import register_builtin_tools
from app.operator.tools.registry import registry
from app.services import hermes_ops
from app.services.connectors import list_tenant_connector_readiness


AVA_TOOL_IDS = (
    "phones.list",
    "phones.provision",
    "calls.list",
    "calls.get",
    "calls.dial",
    "calls.jobs",
    "telephony.script_get",
    "telephony.script_propose",
    "telephony.script_save",
    "telephony.tools_set",
)


def get_toolkit(db: Session, ctx: TenantContext) -> dict[str, Any]:
    register_builtin_tools()
    setup = hermes_ops.office_setup_status(db, ctx)
    try:
        health = hermes_ops.office_health_report(db, ctx)
    except Exception:  # noqa: BLE001
        health = {"ok": False, "healthy": False, "message_ru": "health unavailable", "alerts": []}

    connectors_raw = list_tenant_connector_readiness(db, ctx)
    connectors = []
    for c in connectors_raw or []:
        usable = bool(c.get("usable"))
        enabled = bool(c.get("enabled"))
        connectors.append(
            {
                "kind": c.get("kind"),
                "label": c.get("label") or c.get("kind"),
                "ready": usable,
                "ok": usable,
                "configured": usable,
                "enabled": enabled,
                "detail": (
                    "подключено для этого кабинета"
                    if usable
                    else (
                        f"не usable: {c.get('reason') or 'нет кредов'}"
                        if enabled
                        else "у этого кабинета НЕ подключено"
                    )
                ),
            }
        )
    catalog = {t["name"]: t for t in registry.list_catalog()}

    ava_tools = []
    for tid in AVA_TOOL_IDS:
        meta = catalog.get(tid) or {"name": tid, "description": ""}
        ava_tools.append(
            {
                "id": tid,
                "title": tid,
                "description": meta.get("description") or "",
                "registered": tid in catalog,
                "group": "ava_telephony",
            }
        )

    media_tools = []
    for tid in (
        "generate_image",
        "web.browse",
        "office.import_website",
        "office.build_kb_draft",
        "create_conference",
    ):
        meta = catalog.get(tid)
        if meta:
            media_tools.append(
                {
                    "id": tid,
                    "title": tid,
                    "description": meta.get("description") or "",
                    "registered": True,
                    "group": "media_web",
                }
            )

    checks = setup.get("checks") if isinstance(setup, dict) else {}
    phone_check = (checks or {}).get("phone") or {}
    script_check = (checks or {}).get("telephony_script") or {}
    phone_detail = phone_check.get("detail") if isinstance(phone_check, dict) else {}
    script_ok = bool(script_check.get("ok"))
    phone_ok = bool(phone_check.get("ok"))
    ava_detail = _format_ava_detail(
        phone_detail,
        ready=phone_ok,
        script_ok=script_ok,
    )
    status_blob = dict(phone_detail) if isinstance(phone_detail, dict) else {}
    status_blob["script_ready"] = script_ok
    if isinstance(script_check.get("detail"), dict):
        status_blob["script_tools"] = (script_check.get("detail") or {}).get("tools") or []

    return {
        "ok": True,
        "engine": "hermes_cabinet",
        "setup": {
            "complete": bool(setup.get("setup_complete")),
            "message_ru": setup.get("message_ru"),
            "progress": setup.get("progress"),
        },
        "health": {
            "healthy": bool((health or {}).get("healthy")),
            "message_ru": (health or {}).get("message_ru"),
            "alerts": (health or {}).get("alerts") or [],
        },
        "connectors": connectors,
        "ava": {
            "label": "Ava · телефония",
            "ready": phone_ok,
            "script_ready": script_ok,
            "detail": ava_detail,
            "status": status_blob,
            "tools": ava_tools,
        },
        "media": {"tools": media_tools},
        "tool_count": len(catalog),
        "tools": [
            {
                "id": t["name"],
                "description": t.get("description") or "",
                "confirmation": t.get("confirmation_class") or "READ",
            }
            for t in sorted(catalog.values(), key=lambda x: x["name"])
        ],
    }


def _format_ava_detail(detail: Any, *, ready: bool, script_ok: bool = False) -> str:
    if ready and script_ok:
        return "Ava готова: DID, SIP Registered и сценарий секретаря на месте."
    if ready:
        return "Линия готова (DID+SIP). Добавьте сценарий секретаря, если ещё нет."
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    if not isinstance(detail, dict):
        return "Телефония Ava ещё не настроена — подключите SIP и номер."
    dids = detail.get("active_dids")
    sip_ok = bool(detail.get("sip_configured"))
    reg_ok = bool(detail.get("registration_ok"))
    reg_msg = str(detail.get("registration_message") or "").strip()
    parts: list[str] = []
    if dids in (0, "0", None):
        parts.append("нет активных DID")
    else:
        parts.append(f"DID: {dids}")
    parts.append("SIP в vault" if sip_ok else "SIP не сохранён")
    if reg_ok:
        parts.append("регистрация OK")
    elif reg_msg:
        parts.append(reg_msg)
    else:
        parts.append("регистрация не подтверждена")
    parts.append("сценарий готов" if script_ok else "сценарий не задан")
    return " · ".join(parts)
