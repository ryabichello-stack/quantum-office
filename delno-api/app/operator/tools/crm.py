"""CRM-lite operator tools — work without Bitrix / external CRM keys."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services import crm as crm_service


class CrmFunnelTool:
    name = "crm.funnel"
    description = (
        "Mini-CRM funnel counts by lifecycle (NEW…WON/LOST) for the tenant. "
        "Uses local leads — no Bitrix required."
    )
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        data = crm_service.funnel_counts(db, ctx)
        return ToolResult(ok=True, data=data, message="ok")


class CrmLeadsTool:
    name = "crm.leads"
    description = "List tenant leads (CRM-lite). Optional status filter and text query."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 50},
            "status": {"type": "string"},
            "q": {"type": "string"},
        },
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        data = crm_service.list_leads(
            db,
            ctx,
            limit=int(params.get("limit") or 50),
            status=(str(params["status"]).strip() if params.get("status") else None),
            q=(str(params["q"]).strip() if params.get("q") else None),
        )
        return ToolResult(ok=True, data=data, message="ok")


class CrmLeadGetTool:
    name = "crm.lead_get"
    description = "Get one lead by id with party enrichment payload if present."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {"lead_id": {"type": "string"}},
        "required": ["lead_id"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        lead_id = str(params.get("lead_id") or "").strip()
        if not lead_id:
            return ToolResult(ok=False, message="lead_id is required")
        data = crm_service.get_lead(db, ctx, lead_id)
        return ToolResult(ok=bool(data.get("ok")), data=data, message=str(data.get("error") or "ok"))


class CrmCompaniesTool:
    name = "crm.companies"
    description = "Aggregate companies from tenant leads (local SoT until Bitrix sync)."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 50},
            "q": {"type": "string"},
        },
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        data = crm_service.list_companies(
            db,
            ctx,
            limit=int(params.get("limit") or 50),
            q=(str(params["q"]).strip() if params.get("q") else None),
        )
        return ToolResult(ok=True, data=data, message="ok")


class CrmCompanyUpsertTool:
    name = "crm.company_upsert"
    description = (
        "Add or update a company in CRM-lite (stored as lead). Dedups by company name. "
        "Optional phone/email/inn/website/contact_name/status."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "company": {"type": "string"},
            "phone": {"type": "string"},
            "email": {"type": "string"},
            "website": {"type": "string"},
            "inn": {"type": "string"},
            "contact_name": {"type": "string"},
            "status": {"type": "string"},
        },
        "required": ["company"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        data = crm_service.upsert_company(
            db,
            ctx,
            company=str(params.get("company") or ""),
            phone=(str(params["phone"]).strip() if params.get("phone") else None),
            email=(str(params["email"]).strip() if params.get("email") else None),
            website=(str(params["website"]).strip() if params.get("website") else None),
            inn=(str(params["inn"]).strip() if params.get("inn") else None),
            contact_name=(str(params["contact_name"]).strip() if params.get("contact_name") else None),
            status=(str(params["status"]).strip() if params.get("status") else None),
        )
        return ToolResult(ok=bool(data.get("ok")), data=data, message=str(data.get("error") or "ok"))


class CrmLifecycleSetTool:
    name = "crm.lifecycle_set"
    description = (
        "Set lead funnel stage. Values: NEW, ENRICHED, CONTACTED, IN_SEQUENCE, "
        "REPLIED, MEETING, WON, LOST, PAUSED."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "lead_id": {"type": "string"},
            "status": {"type": "string"},
        },
        "required": ["lead_id", "status"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        lead_id = str(params.get("lead_id") or "").strip()
        status = str(params.get("status") or "").strip()
        if not lead_id or not status:
            return ToolResult(ok=False, message="lead_id and status are required")
        data = crm_service.set_lifecycle(db, ctx, lead_id=lead_id, status=status)
        return ToolResult(ok=bool(data.get("ok")), data=data, message=str(data.get("error") or "ok"))


class CrmSuggestNextTool:
    name = "crm.suggest_next"
    description = "Suggest next CRM actions for a lead (deterministic, no LLM)."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {"lead_id": {"type": "string"}},
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        lead_id = str(params.get("lead_id") or "").strip() or None
        data = crm_service.suggest_next(db, ctx, lead_id=lead_id)
        return ToolResult(ok=bool(data.get("ok", True)), data=data, message=str(data.get("error") or "ok"))
