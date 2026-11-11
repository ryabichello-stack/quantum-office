"""Outreach staging tools — stub until OUTREACH_BASE_URL / SMTP."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.adapters.connectors import get_connector
from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services.audit import write_audit
from app.services.connectors import connector_config_for


def _outreach():
    connector = get_connector("outreach")
    assert connector is not None
    return connector


class OutreachStatusTool:
    name = "outreach.status"
    description = "Outreach connector status (stub until OUTREACH_BASE_URL)."
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        connector = _outreach()
        config = connector_config_for(db, ctx, "outreach")
        result = connector.status(tenant_slug=ctx.tenant_slug, config=config)
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")


class OutreachDashboardTool:
    name = "outreach.dashboard"
    description = "Email outreach dashboard metrics (stub zeros without upstream)."
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        connector = _outreach()
        config = connector_config_for(db, ctx, "outreach")
        result = connector.dashboard(tenant_slug=ctx.tenant_slug, config=config)  # type: ignore[attr-defined]
        write_audit(
            db,
            ctx,
            action="tool.outreach.dashboard",
            resource="connector:outreach",
            new_value={"configured": result.configured, "stub": bool(result.data.get("stub"))},
        )
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")


class OutreachPacksTool:
    name = "outreach.packs"
    description = "List outreach industry packs (local stubs until upstream)."
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        connector = _outreach()
        config = connector_config_for(db, ctx, "outreach")
        result = connector.packs(tenant_slug=ctx.tenant_slug, config=config)  # type: ignore[attr-defined]
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")


class OutreachPreviewTool:
    name = "outreach.preview"
    description = "Preview a cold/outreach email render (stub without SMTP)."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "company": {"type": "string"},
            "pack_id": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        to = str(params.get("to") or "").strip()
        if not to:
            return ToolResult(ok=False, message="to is required")
        company = str(params.get("company") or "").strip()
        connector = _outreach()
        config = connector_config_for(db, ctx, "outreach")
        result = connector.preview(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            to=to,
            company=company,
            pack_id=(str(params["pack_id"]).strip() if params.get("pack_id") else None),
            subject=(str(params["subject"]) if params.get("subject") else None),
            body=(str(params["body"]) if params.get("body") else None),
        )
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")


class OutreachStageSendTool:
    name = "outreach.stage_send"
    description = (
        "Stage one outreach email (dry-run enforced in stub mode until OUTREACH_BASE_URL). "
        "Does not send for real without upstream."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "company": {"type": "string"},
            "pack_id": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "dry_run": {"type": "boolean", "default": True},
        },
        "required": ["to"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        to = str(params.get("to") or "").strip()
        if not to:
            return ToolResult(ok=False, message="to is required")
        company = str(params.get("company") or "").strip()
        dry_run = bool(params.get("dry_run", True))
        connector = _outreach()
        config = connector_config_for(db, ctx, "outreach")
        result = connector.stage_send(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            to=to,
            company=company,
            pack_id=(str(params["pack_id"]).strip() if params.get("pack_id") else None),
            subject=(str(params["subject"]) if params.get("subject") else None),
            body=(str(params["body"]) if params.get("body") else None),
            dry_run=dry_run,
        )
        write_audit(
            db,
            ctx,
            action="tool.outreach.stage_send",
            resource="connector:outreach",
            new_value={"to": to, "configured": result.configured, "stub": bool(result.data.get("stub"))},
        )
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")


class OutreachLeadCheckTool:
    name = "outreach.lead_check"
    description = (
        "Check email/company against Bitrix/outbox dedup. "
        "Stub returns unknown / ok_to_stage until OUTREACH_BASE_URL."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "email": {"type": "string"},
            "company": {"type": "string"},
        },
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        email = str(params.get("email") or "").strip() or None
        company = str(params.get("company") or "").strip() or None
        if not email and not company:
            return ToolResult(ok=False, message="email or company is required")
        connector = _outreach()
        config = connector_config_for(db, ctx, "outreach")
        result = connector.lead_check(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            email=email,
            company=company,
        )
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")
