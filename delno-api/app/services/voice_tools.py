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
}
_WRITES = {
    "create_calendar_event",
    "send_email",
    "send_welcome_email",
    "create_conference",
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
    enabled = get_telephony_config(db, ctx)["tools"]
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
                        False
                        if name == "send_welcome_email"
                        else readiness.get(_CONNECTOR[name], False)
                        if name in _CONNECTOR
                        else True
                    ),
                }
                for name in enabled
            ],
        }
    if action not in enabled or action == "hangup_call":
        return {"ok": False, "error": "tool_not_enabled"}
    if action == "send_welcome_email":
        return {"ok": False, "error": "welcome_materials_not_configured"}
    if action in _WRITES and params.get("confirmed_by_caller") is not True:
        return {"ok": False, "error": "caller_confirmation_required"}
    kind = _CONNECTOR.get(action)
    if kind:
        readiness = list_tenant_connector_readiness(db, ctx)
        if not any(x["kind"] == kind and x.get("usable") for x in readiness):
            return {"ok": False, "error": "connector_not_ready", "connector": kind}
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
    elif action == "send_email":
        from app.operator.tools.office import SendMailDraftTool

        result = SendMailDraftTool().run(
            db,
            ctx,
            to=params.get("email"),
            subject=params.get("subject"),
            body=params.get("body"),
        )
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
