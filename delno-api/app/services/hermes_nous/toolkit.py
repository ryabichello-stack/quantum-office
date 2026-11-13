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
    connectors = [
        {
            "kind": c.get("kind"),
            "label": c.get("label") or c.get("kind"),
            "ready": bool(c.get("usable") or c.get("ready") or c.get("ok")),
            "ok": bool(c.get("usable") or c.get("ready") or c.get("ok")),
            "detail": c.get("detail") or c.get("hint") or "",
        }
        for c in (connectors_raw or [])
    ]
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
    for tid in ("generate_image", "web.browse", "office.import_website", "create_conference"):
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
    telephony_check = (checks or {}).get("telephony") or (checks or {}).get("phone") or {}

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
            "ready": bool(telephony_check.get("ok")),
            "detail": telephony_check.get("detail") or telephony_check.get("hint") or "",
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
