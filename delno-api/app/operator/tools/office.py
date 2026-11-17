"""Operator tools for office connectors — work with or without upstream creds."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.adapters.connectors import get_connector
from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services.audit import write_audit
from app.services.connectors import connector_config_for
from app.services.tenant_broker_access import apply_access as _access_config


class CheckCalendarTool:
    name = "check_calendar"
    description = "Check whether a calendar slot is free (in-call Ava / Hermes)."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "start": {"type": "string"},
            "timezone": {"type": "string"},
            "source": {"type": "string"},
        },
        "required": ["start"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        start = str(params.get("start") or "").strip()
        if not start:
            return ToolResult(ok=False, message="start is required")
        connector = get_connector("calendar")
        assert connector is not None
        config, err = _access_config(
            db,
            ctx,
            dict(connector_config_for(db, ctx, "calendar")),
            kind="calendar",
            source=str(params.get("source") or "") or None,
        )
        if err or config is None:
            return ToolResult(ok=False, data={"error": err or "tenant_required"}, message=err or "tenant_required")
        result = connector.check(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            start=start,
            timezone=str(params.get("timezone") or "") or None,
            source=str(params.get("source") or "") or None,
        )
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")


class CreateCalendarEventTool:
    name = "create_calendar_event"
    description = "Create a calendar event (+ optional Telemost) after caller confirmation."
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "start": {"type": "string"},
            "summary": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "attendee_email": {"type": "string"},
            "email": {"type": "string"},
            "timezone": {"type": "string"},
            "end": {"type": "string"},
            "source": {"type": "string"},
            "create_telemost": {"type": "boolean"},
            "invitees": {"type": "array"},
        },
        "required": ["start"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        start = str(params.get("start") or "").strip()
        summary = str(params.get("summary") or params.get("title") or "").strip() or "Встреча"
        if not start:
            return ToolResult(ok=False, message="start is required")
        connector = get_connector("calendar")
        assert connector is not None
        config, err = _access_config(
            db,
            ctx,
            dict(connector_config_for(db, ctx, "calendar")),
            kind="calendar",
            source=str(params.get("source") or "") or None,
        )
        if err or config is None:
            return ToolResult(ok=False, data={"error": err or "tenant_required"}, message=err or "tenant_required")
        result = connector.create_event(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            start=start,
            summary=summary,
            description=str(params.get("description") or "") or None,
            attendee_email=str(params.get("attendee_email") or params.get("email") or "") or None,
            timezone=str(params.get("timezone") or "") or None,
            end=str(params.get("end") or "") or None,
            source=str(params.get("source") or "") or None,
            create_telemost=params.get("create_telemost"),
            invitees=list(params.get("invitees") or []) or None,
        )
        write_audit(
            db,
            ctx,
            action="tool.create_calendar_event",
            resource="connector:calendar",
            new_value={"start": start, "summary": summary, "configured": result.configured},
        )
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")


class SuggestCalendarSlotsTool:
    name = "suggest_calendar_slots"
    description = (
        "Suggest meeting slots via tenant calendar connector. "
        "Sources: mailru | yandex | google | outlook (stub until provider creds)."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "start": {"type": "string", "description": "ISO datetime preferred start"},
            "duration_min": {"type": "integer", "description": "Meeting length minutes", "default": 60},
            "source": {
                "type": "string",
                "description": "mailru | yandex | google | outlook",
                "default": "tenant",
            },
        },
        "required": ["start"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        start = str(params.get("start") or "").strip()
        if not start:
            return ToolResult(ok=False, message="start is required")
        duration = int(params.get("duration_min") or 60)
        source = str(params.get("source") or "mailru").strip() or "mailru"
        connector = get_connector("calendar")
        assert connector is not None
        config, err = _access_config(
            db,
            ctx,
            dict(connector_config_for(db, ctx, "calendar")),
            kind="calendar",
            source=source,
        )
        if err or config is None:
            return ToolResult(ok=False, data={"error": err or "tenant_required"}, message=err or "tenant_required")
        result = connector.suggest_slots(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            start=start,
            duration_min=duration,
            source=source,
        )
        write_audit(
            db,
            ctx,
            action="tool.suggest_calendar_slots",
            resource="connector:calendar",
            new_value={
                "configured": result.configured,
                "stub": bool(result.data.get("stub")),
                "source": source,
            },
        )
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")


class SendMailDraftTool:
    name = "send_mail_draft"
    description = (
        "Send email through this company's connected mailbox. "
        "Optional attachment_id selects one file uploaded by this company."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "attachment_id": {"type": "string", "description": "ID выбранного файла этой компании из list_files(source=tenant)"},
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
        from app.services.connector_connect import mail_delivery_access

        access = mail_delivery_access(db, ctx)
        if access is None:
            return ToolResult(
                ok=False,
                data={"error": "mail_not_connected"},
                message="Сначала подключите и проверьте почту этой компании.",
            )
        config = dict(connector_config_for(db, ctx, "mail"))
        config["_mail_delivery_access"] = access
        attachment = None
        if params.get("attachment_id"):
            from app.services.tenant_attachments import attachment_for
            try:
                attachment = attachment_for(db, ctx, str(params["attachment_id"]))
            except (ValueError, OSError):
                return ToolResult(ok=False, data={"error": "attachment_unavailable"}, message="Выбранный файл этой компании не найден; письмо не отправлено.")
        result = connector.send_draft(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            to=to,
            subject=subject,
            body=body,
            attachment=attachment,
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
        "List this company's uploaded files (source=tenant) or connected cloud files. "
        "Sources: tenant | mailru | yadisk | gdrive | onedrive."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "default": "mailru",
            "description": "tenant | mailru | yadisk | gdrive | onedrive",
            },
            "path": {"type": "string", "default": "/"},
            "limit": {"type": "integer", "default": 100},
            "offset": {"type": "integer", "default": 0},
        },
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        source = str(params.get("source") or "tenant").strip() or "tenant"
        if source == "tenant":
            from app.services.tenant_attachments import list_files
            from app.services.tenant_attachments import list_folders
            try:
                limit = max(1, min(500, int(params.get("limit") or 100)))
                offset = max(0, int(params.get("offset") or 0))
            except (TypeError, ValueError):
                return ToolResult(ok=False, data={"error": "invalid_pagination"}, message="invalid_pagination")
            rows = list_files(db, ctx, limit=limit, offset=offset)
            return ToolResult(ok=True, data={"source": "tenant", "items": rows, "folders": list_folders(db, ctx), "next_offset": offset + len(rows) if len(rows) == limit else None}, message=f"Файлов на странице: {len(rows)}")
        path = str(params.get("path") or "/").strip() or "/"
        connector = get_connector("files")
        assert connector is not None
        config, err = _access_config(
            db,
            ctx,
            dict(connector_config_for(db, ctx, "files")),
            kind="files",
            source=source,
        )
        if err or config is None:
            return ToolResult(ok=False, data={"error": err or "tenant_required"}, message=err or "tenant_required")
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
        "Create a video conference. "
        "Providers: yandex | google_meet | zoom | teams | jitsi "
        "(stub join URL until CONFERENCE_BASE_URL / provider creds)."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "provider": {
                "type": "string",
                "description": "yandex | google_meet | zoom | teams | jitsi",
                "default": "yandex",
            },
            "invitees": {"type": "array", "items": {"type": "string"}},
            "when_text": {"type": "string"},
        },
        "required": ["title"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        title = str(params.get("title") or "").strip()
        if not title:
            return ToolResult(ok=False, message="title is required")
        provider = str(params.get("provider") or "yandex").strip() or "yandex"
        invitees_raw = params.get("invitees") or []
        invitees = [str(x).strip() for x in invitees_raw if str(x).strip()] if isinstance(invitees_raw, list) else []
        when_text = str(params.get("when_text") or "").strip()
        connector = get_connector("conference")
        assert connector is not None
        from app.services.connector_connect import conference_delivery_access
        config = dict(connector_config_for(db, ctx, "conference"))
        config["_conference_delivery_access"] = conference_delivery_access(db, ctx, provider)
        result = connector.create(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            title=title,
            invitees=invitees,
            when_text=when_text,
            provider=provider,
        )
        write_audit(
            db,
            ctx,
            action="tool.create_conference",
            resource="connector:conference",
            new_value={
                "title": title,
                "provider": provider,
                "configured": result.configured,
                "stub": bool(result.data.get("stub")),
            },
        )
        return ToolResult(ok=result.ok, data=result.as_dict(), message=result.message or "ok")
