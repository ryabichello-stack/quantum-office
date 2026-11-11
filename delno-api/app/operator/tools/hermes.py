"""Hermes supervisor tools — setup checklist + health watch + alerts."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services import hermes_ops


class HermesSetupStatusTool:
    name = "hermes.setup_status"
    description = (
        "First-time office setup checklist for this tenant: KB, phone, Telegram/MAX, "
        "calendar, mail, conference. Hermes uses this to guide the owner."
    )
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        out = hermes_ops.office_setup_status(db, ctx)
        return ToolResult(ok=True, data=out, message=out.get("message_ru") or "ok")


class HermesSetupMarkTool:
    name = "hermes.setup_mark"
    description = "Mark Hermes setup progress (e.g. kb_ready=true after knowledge upload)."
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "kb_ready": {"type": "boolean"},
            "note": {"type": "string"},
        },
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        kb = params.get("kb_ready")
        out = hermes_ops.mark_setup_progress(
            db,
            ctx,
            kb_ready=bool(kb) if kb is not None else None,
            note=str(params.get("note") or "") or None,
        )
        return ToolResult(ok=True, data=out, message=out.get("message_ru") or "ok")


class HermesHealthTool:
    name = "hermes.health"
    description = (
        "Check that connected office components work (phones, channels, connectors, call queue). "
        "Returns alerts Hermes must tell the owner about."
    )
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        out = hermes_ops.office_health_report(db, ctx)
        return ToolResult(
            ok=True,
            data=out,
            message=out.get("message_ru") or ("healthy" if out.get("healthy") else "degraded"),
        )


class HermesAlertsTool:
    name = "hermes.alerts"
    description = "List recent office.alert / health events for the tenant."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "default": 20}},
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        out = hermes_ops.list_recent_office_alerts(db, ctx, limit=int(params.get("limit") or 20))
        return ToolResult(ok=True, data=out, message=f"{len(out.get('items') or [])} events")
