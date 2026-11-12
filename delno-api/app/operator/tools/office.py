"""Operator tools for office connectors — work with or without upstream creds."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.adapters.connectors import get_connector
from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services.audit import write_audit
from app.services.connectors import connector_config_for


class CheckCalendarTool:
    """AVA secretary: free/busy for one slot (universal for all tenants)."""

    name = "check_calendar"
    description = (
        "Check if a calendar slot is free (secretary tool). "
        "start as 'YYYY-MM-DD HH:MM' or ISO. Sources: mailru | yandex | google | outlook. "
        "Returns free true/false. Use before create_calendar_event."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "start": {"type": "string", "description": "Slot start YYYY-MM-DD HH:MM or ISO"},
            "timezone": {"type": "string", "default": "Europe/Moscow"},
            "source": {
                "type": "string",
                "description": "mailru | yandex | google | outlook",
                "default": "mailru",
            },
        },
        "required": ["start"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        start = str(params.get("start") or "").strip()
        if not start:
            return ToolResult(ok=False, message="start is required")
        timezone = str(params.get("timezone") or "Europe/Moscow").strip() or "Europe/Moscow"
        source = str(params.get("source") or "mailru").strip() or "mailru"
        connector = get_connector("calendar")
        assert connector is not None
        config = connector_config_for(db, ctx, "calendar")
        result = connector.check_slot(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            start=start,
            timezone=timezone,
            source=source,
        )
        write_audit(
            db,
            ctx,
            action="tool.check_calendar",
            resource="connector:calendar",
            new_value={
                "start": start,
                "free": (result.data or {}).get("free"),
                "configured": result.configured,
                "stub": bool((result.data or {}).get("stub")),
            },
        )
        free = (result.data or {}).get("free")
        msg = result.message or ("Слот свободен" if free else "Слот занят")
        if (result.data or {}).get("stub"):
            msg = f"{msg} (stub — календарь tenant ещё не подключён)"
        return ToolResult(ok=result.ok, data=result.as_dict(), message=msg)


class CreateCalendarEventTool:
    """AVA secretary: create meeting (+ optional Telemost) — universal for all tenants."""

    name = "create_calendar_event"
    description = (
        "Create a calendar meeting for the tenant (secretary tool). "
        "After check_calendar free=true. Pass confirmed attendee email. "
        "Optionally creates Yandex Telemost / conference join URL when conference broker is up. "
        "start as 'YYYY-MM-DD HH:MM' or ISO."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "start": {"type": "string"},
            "summary": {"type": "string", "default": "Созвон с клиентом"},
            "description": {"type": "string"},
            "attendee_email": {"type": "string"},
            "timezone": {"type": "string", "default": "Europe/Moscow"},
            "end": {"type": "string"},
            "source": {"type": "string", "default": "mailru"},
            "create_telemost": {"type": "boolean", "default": True},
            "invitees": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["start"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        start = str(params.get("start") or "").strip()
        if not start:
            return ToolResult(ok=False, message="start is required")
        summary = str(params.get("summary") or "Созвон с клиентом").strip() or "Созвон с клиентом"
        description = str(params.get("description") or "").strip()
        attendee_email = str(params.get("attendee_email") or "").strip() or None
        timezone = str(params.get("timezone") or "Europe/Moscow").strip() or "Europe/Moscow"
        end = str(params.get("end") or "").strip() or None
        source = str(params.get("source") or "mailru").strip() or "mailru"
        create_telemost = params.get("create_telemost")
        if create_telemost is None:
            create_telemost = True
        invitees_raw = params.get("invitees") or []
        invitees = (
            [str(x).strip() for x in invitees_raw if str(x).strip()]
            if isinstance(invitees_raw, list)
            else []
        )
        connector = get_connector("calendar")
        assert connector is not None
        config = connector_config_for(db, ctx, "calendar")
        result = connector.create_event(  # type: ignore[attr-defined]
            tenant_slug=ctx.tenant_slug,
            config=config,
            start=start,
            summary=summary,
            description=description,
            attendee_email=attendee_email,
            timezone=timezone,
            end=end,
            source=source,
            create_telemost=bool(create_telemost),
            invitees=invitees,
        )
        data = result.data or {}
        write_audit(
            db,
            ctx,
            action="tool.create_calendar_event",
            resource="connector:calendar",
            new_value={
                "start": start,
                "created": data.get("created"),
                "telemost": bool(data.get("telemost_join_url")),
                "configured": result.configured,
                "stub": bool(data.get("stub")),
            },
        )
        join = str(data.get("telemost_join_url") or "").strip()
        msg = result.message or "ok"
        if data.get("stub"):
            msg = f"{msg} (stub — подключите календарь tenant)"
        elif join:
            msg = f"{msg}. Ссылка ВКС: {join}"
        return ToolResult(ok=result.ok, data=result.as_dict(), message=msg)


class SuggestCalendarSlotsTool:
    name = "suggest_calendar_slots"
    description = (
        "Suggest free meeting slots via tenant calendar connector (secretary). "
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
                "default": "mailru",
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
        config = connector_config_for(db, ctx, "calendar")
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
        config = dict(connector_config_for(db, ctx, "files"))
        try:
            from app.services.files_cloud import credentials_for_source, normalize_source

            src = normalize_source(source) or source
            creds = credentials_for_source(db, ctx, src)
            if creds:
                config["_request_credentials"] = creds
        except Exception:  # noqa: BLE001
            pass
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
        config = connector_config_for(db, ctx, "conference")
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
