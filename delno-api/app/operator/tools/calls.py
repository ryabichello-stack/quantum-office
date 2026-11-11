"""Hermes / owner telephony tools — list, inspect, dial, setup phones."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services import phone_provision, telephony
from app.services.audit import write_audit


class CallsListTool:
    name = "calls.list"
    description = "List recent call sessions for this tenant (inbound/outbound)."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "default": 20}},
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        limit = int(params.get("limit") or 20)
        items = telephony.list_sessions(db, ctx, limit=limit)
        return ToolResult(ok=True, data={"items": items, "total": len(items)}, message=f"{len(items)} calls")


class CallsGetTool:
    name = "calls.get"
    description = "Get one call session by id (transcript/summary)."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {"session_id": {"type": "string"}},
        "required": ["session_id"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        sid = str(params.get("session_id") or "").strip()
        try:
            uid = UUID(sid)
        except ValueError:
            return ToolResult(ok=False, message="invalid session_id")
        row = telephony.get_session(db, ctx, uid)
        if not row:
            return ToolResult(ok=False, message="not_found")
        return ToolResult(ok=True, data=row, message="ok")


class CallsDialTool:
    name = "calls.dial"
    description = (
        "Queue an outbound call job (Hermes directs Dialer). "
        "Provide to_e164 and optional script for Frontline."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "to_e164": {"type": "string"},
            "script": {"type": "string"},
            "lead_id": {"type": "string"},
        },
        "required": ["to_e164"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        to_e164 = str(params.get("to_e164") or "").strip()
        script = str(params.get("script") or "").strip()
        lead_raw = str(params.get("lead_id") or "").strip()
        lead_id = None
        if lead_raw:
            try:
                lead_id = UUID(lead_raw)
            except ValueError:
                return ToolResult(ok=False, message="invalid lead_id")
        out = telephony.create_outbound_job(
            db,
            ctx,
            to_e164=to_e164,
            script=script or "Представься секретарём компании и уточни цель звонка.",
            lead_id=lead_id,
            created_by="hermes",
        )
        if not out.get("ok"):
            return ToolResult(ok=False, message=str(out.get("error") or "dial_failed"), data=out)
        write_audit(db, ctx, action="tool.calls.dial", resource="call_job", new_value=out.get("job"), actor="hermes")
        return ToolResult(ok=True, data=out, message="outbound_queued")


class CallsJobsTool:
    name = "calls.jobs"
    description = "List outbound CallJob queue for this tenant."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "limit": {"type": "integer", "default": 20},
        },
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        status = str(params.get("status") or "").strip() or None
        items = telephony.list_jobs(db, ctx, status=status, limit=int(params.get("limit") or 20))
        return ToolResult(ok=True, data={"items": items}, message=f"{len(items)} jobs")


class PhonesListTool:
    name = "phones.list"
    description = "List phone numbers (DIDs) provisioned for this tenant."
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        return ToolResult(ok=True, data=phone_provision.list_phones(db, ctx), message="ok")


class PhonesProvisionTool:
    name = "phones.provision"
    description = (
        "Attach an E.164 phone number to this tenant for inbound/outbound routing. "
        "Used by Hermes during first-time office setup."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "e164": {"type": "string"},
            "label": {"type": "string"},
            "status": {"type": "string", "default": "active"},
        },
        "required": ["e164"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        out = phone_provision.provision_phone(
            db,
            ctx,
            e164=str(params.get("e164") or ""),
            label=str(params.get("label") or "main") or "main",
            status=str(params.get("status") or "active"),
        )
        if not out.get("ok"):
            return ToolResult(ok=False, message=str(out.get("error") or "failed"), data=out)
        return ToolResult(ok=True, data=out, message="phone_provisioned")
