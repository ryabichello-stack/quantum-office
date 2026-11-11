"""Operator tools for office connectors — work with or without upstream creds."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.adapters.connectors import get_connector
from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services.audit import write_audit
from app.services.connectors import connector_config_for


class SuggestCalendarSlotsTool:
    name = "suggest_calendar_slots"
    description = (
        "Suggest meeting slots via tenant calendar connector. "
        "Works in stub mode until CALENDAR_BASE_URL / CalDAV is wired."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "start": {"type": "string", "description": "ISO datetime preferred start"},
            "duration_min": {"type": "integer", "description": "Meeting length minutes", "default": 60},
        },
        "required": ["start"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        start = str(params.get("start") or "").strip()
        if not start:
            return ToolResult(ok=False, message="start is required")
        duration = int(params.get("duration_min") or 60)
        connector = get_connector("calendar")
        assert connector is not None
        config = connector_config_for(db, ctx, "calendar")
        result = connector.suggest_slots(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            start=start,
            duration_min=duration,
        )
        write_audit(
            db,
            ctx,
            action="tool.suggest_calendar_slots",
            resource="connector:calendar",
            new_value={"configured": result.configured, "stub": bool(result.data.get("stub"))},
        )
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")


class SendMailDraftTool:
    name = "send_mail_draft"
    description = (
        "Send or stage an email draft via mail connector. "
        "Without MAILER_BASE_URL returns stub queued=false payload."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        to = str(params.get("to") or "").strip()
        subject = str(params.get("subject") or "").strip()
        body = str(params.get("body") or "").strip()
        if not to or not subject or not body:
            return ToolResult(ok=False, message="to, subject and body are required")
        connector = get_connector("mail")
        assert connector is not None
        config = connector_config_for(db, ctx, "mail")
        result = connector.send_draft(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            to=to,
            subject=subject,
            body=body,
        )
        write_audit(
            db,
            ctx,
            action="tool.send_mail_draft",
            resource="connector:mail",
            new_value={"to": to, "configured": result.configured, "stub": bool(result.data.get("stub"))},
        )
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")


class ListFilesTool:
    name = "list_files"
    description = (
        "List files/folders via files connector. "
        "Sources: mailru | yadisk | gdrive | onedrive | local (stub until FILES_BASE_URL)."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "default": "mailru",
                "description": "mailru | yadisk | gdrive | onedrive | local",
            },
            "path": {"type": "string", "default": "/"},
        },
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        source = str(params.get("source") or "local").strip() or "local"
        path = str(params.get("path") or "/").strip() or "/"
        connector = get_connector("files")
        assert connector is not None
        config = connector_config_for(db, ctx, "files")
        result = connector.list_entries(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            source=source,
            path=path,
        )
        write_audit(
            db,
            ctx,
            action="tool.list_files",
            resource="connector:files",
            new_value={"path": path, "configured": result.configured},
        )
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")


class CreateConferenceTool:
    name = "create_conference"
    description = (
        "Create a conference (Telemost when CONFERENCE_BASE_URL set; stub join URL otherwise)."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "invitees": {"type": "array", "items": {"type": "string"}},
            "when_text": {"type": "string"},
        },
        "required": ["title"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        title = str(params.get("title") or "").strip()
        if not title:
            return ToolResult(ok=False, message="title is required")
        invitees_raw = params.get("invitees") or []
        invitees = [str(x).strip() for x in invitees_raw if str(x).strip()] if isinstance(invitees_raw, list) else []
        when_text = str(params.get("when_text") or "").strip()
        connector = get_connector("conference")
        assert connector is not None
        config = connector_config_for(db, ctx, "conference")
        result = connector.create(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            title=title,
            invitees=invitees,
            when_text=when_text,
        )
        write_audit(
            db,
            ctx,
            action="tool.create_conference",
            resource="connector:conference",
            new_value={"title": title, "configured": result.configured, "stub": bool(result.data.get("stub"))},
        )
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")
