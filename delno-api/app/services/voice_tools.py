"""In-call DELNO tool gateway: Asterisk call id → tenant → enabled tool → connector."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.principals import PRINCIPAL_VOICE_PUBLIC
from app.core.tenant import TenantContext
from app.models.call_session import CallSession
from app.models.tenant import Tenant
from app.services.connectors import list_tenant_connector_readiness
from app.services.telephony_script import get_telephony_config

_CONNECTOR = {
    "check_calendar": "calendar",
    "create_calendar_event": "calendar",
    "send_email": "mail",
    "send_welcome_email": "mail",
    "create_conference": "conference",
    "book_meeting": "calendar",
    "suggest_other_time": "calendar",
    "reschedule_meeting": "calendar",
    "confirm_meeting": "calendar",
    "cancel_meeting": "calendar",
}
_WRITES = {
    "create_calendar_event",
    "send_email",
    "send_welcome_email",
    "create_conference",
    "book_meeting",
    "reschedule_meeting",
    "confirm_meeting",
    "cancel_meeting",
}
# Same meeting verbs as messenger tools. Allowed when the line has the pieces.
_MEETING_NEEDS = {
    "book_meeting": ("check_calendar", "create_calendar_event", "send_email", "create_conference"),
    "suggest_other_time": ("check_calendar",),
    "reschedule_meeting": ("check_calendar",),
    "confirm_meeting": ("check_calendar",),
    "cancel_meeting": ("check_calendar",),
    "send_welcome_email": ("send_email",),
    "send_email": ("send_email",),
}


def dispatch(
    db: Session,
    *,
    call_id: str,
    action: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    if not call_id or len(call_id) > 120:
        return {"ok": False, "error": "invalid_call_id"}
    calls = (
        db.query(CallSession)
        .filter(CallSession.external_id == call_id, CallSession.status == "active")
        .limit(2)
        .all()
    )
    if len(calls) != 1:
        return {"ok": False, "error": "active_call_not_found"}
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == calls[0].tenant_id, Tenant.is_active.is_(True))
        .one_or_none()
    )
    if tenant is None:
        return {"ok": False, "error": "tenant_not_found"}
    ctx = TenantContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role=PRINCIPAL_VOICE_PUBLIC,
    )
    enabled = list(get_telephony_config(db, ctx)["tools"])
    for name, needs in _MEETING_NEEDS.items():
        if name not in enabled and all(n in enabled for n in needs):
            enabled.append(name)
    if action == "list_enabled_tools":
        readiness = {
            x["kind"]: x["usable"] for x in list_tenant_connector_readiness(db, ctx)
        }
        return {
            "ok": True,
            "tenant_slug": tenant.slug,
            "tools": [
                {
                    "id": name,
                    "ready": (
                        readiness.get(_CONNECTOR[name], False) if name in _CONNECTOR else True
                    ),
                }
                for name in enabled
            ],
        }
    if action not in enabled or action == "hangup_call":
        return {"ok": False, "error": "tool_not_enabled"}
    if action in _WRITES and params.get("confirmed_by_caller") is not True:
        return {
            "ok": False,
            "error": "caller_confirmation_required",
            "message_ru": "Сначала спросите, точно ли делать это, и дождитесь «да».",
        }
    kind = _CONNECTOR.get(action)
    if kind:
        readiness = list_tenant_connector_readiness(db, ctx)
        if not any(x["kind"] == kind and x.get("usable") for x in readiness):
            names = {"calendar": "календарь", "mail": "почта", "conference": "видеовстречи"}
            label = names.get(kind, kind)
            return {
                "ok": False,
                "error": "connector_not_ready",
                "connector": kind,
                "message_ru": f"Сначала подключите {label} — без этого это действие недоступно.",
            }
    if action == "get_company_knowledge":
        from app.operator.tools.builtin import GetKnowledgeTool

        query = str(params.get("query") or "").strip()[:500]
        if not query:
            return {"ok": False, "error": "query_required"}
        result = GetKnowledgeTool().run(db, ctx, query=query)
    elif action == "check_calendar":
        from app.operator.tools.office import CheckCalendarTool

        result = CheckCalendarTool().run(
            db,
            ctx,
            start=params.get("start"),
            timezone=params.get("timezone"),
            source=params.get("source"),
        )
    elif action == "create_calendar_event":
        from app.operator.tools.office import CreateCalendarEventTool

        result = CreateCalendarEventTool().run(
            db,
            ctx,
            start=params.get("start"),
            summary=params.get("summary") or params.get("title"),
            description=params.get("description"),
            attendee_email=params.get("attendee_email") or params.get("email"),
            timezone=params.get("timezone"),
            end=params.get("end"),
            source=params.get("source"),
            create_telemost=params.get("create_telemost"),
            invitees=params.get("invitees") or [],
        )
    elif action in {"send_email", "send_welcome_email", "book_meeting", "suggest_other_time", "reschedule_meeting", "confirm_meeting", "cancel_meeting"}:
        from app.services.appointments import handle as handle_appointment

        out = handle_appointment(db, ctx, action, params, channel="voice")
        return out
    elif action == "create_conference":
        from app.operator.tools.office import CreateConferenceTool

        result = CreateConferenceTool().run(
            db,
            ctx,
            title=params.get("title"),
            provider=params.get("provider"),
            invitees=params.get("invitees") or [],
            when_text=params.get("when_text"),
        )
    else:
        return {"ok": False, "error": "unknown_tool"}
    db.commit()
    return {"ok": bool(result.ok), "message": result.message, "data": result.data}
