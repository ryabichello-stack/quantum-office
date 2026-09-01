from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.adapters.knowledge import KnowledgeAdapter
from app.core.principals import principal_for_operator
from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services.audit import write_audit
from app.services.events import emit_event
from app.services.leads import create_lead_record
from app.services.party_enrichment import lookup_party_by_inn


class GetKnowledgeTool:
    name = "get_knowledge"
    description = "Search tenant knowledge base by topic or question. Never pass tenant_id."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Question or topic to search"},
        },
        "required": ["query"],
    }

    def __init__(self, adapter: KnowledgeAdapter | None = None) -> None:
        self._adapter = adapter or KnowledgeAdapter()

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        query = str(params.get("query") or "").strip()
        if not query:
            return ToolResult(ok=False, message="query is required")
        role = ctx.role or "tenant_owner"
        owner_roles = {"platform_admin", "tenant_owner", "tenant_admin"}
        pid = principal_for_operator(role=role, is_owner_context=role in owner_roles)
        data = self._adapter.search(
            query,
            tenant_slug=ctx.tenant_slug,
            principal_id=pid,
        )
        if not data.get("ok", True):
            message = str(data.get("message") or "Knowledge search failed")
            emit_event(
                db,
                tenant_id=ctx.tenant_id,
                event_type="knowledge.search_failed",
                category="operational",
                source="operator.get_knowledge",
                payload={
                    "query": query,
                    "message": message,
                    "principal": pid,
                    "tenant_slug": ctx.tenant_slug,
                },
            )
            write_audit(
                db,
                ctx,
                action="tool.get_knowledge",
                resource="knowledge",
                new_value={"query": query, "ok": False, "message": message, "principal": pid},
                result="error",
            )
            return ToolResult(ok=False, data=data, message=message)

        hits = data.get("matches") or data.get("results") or []
        write_audit(
            db,
            ctx,
            action="tool.get_knowledge",
            resource="knowledge",
            new_value={"query": query, "hits": len(hits), "principal": pid},
        )
        return ToolResult(ok=True, data=data, message="Knowledge search completed")


class LookupCompanyByInnTool:
    name = "lookup_company_by_inn"
    description = "Look up legal entity by INN (read-only). Returns company name, address, OKVED."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "inn": {"type": "string", "description": "10 or 12 digit INN"},
        },
        "required": ["inn"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        inn = str(params.get("inn") or "").strip()
        if not inn:
            return ToolResult(ok=False, message="inn is required")
        result = lookup_party_by_inn(db, inn, tenant_id=ctx.tenant_id)
        if not result.get("ok"):
            write_audit(
                db,
                ctx,
                action="tool.lookup_company_by_inn",
                resource="party",
                new_value={"inn": inn, "ok": False, "error": result.get("error")},
                result="error",
            )
            return ToolResult(ok=False, data=result, message=str(result.get("error") or "lookup failed"))
        write_audit(
            db,
            ctx,
            action="tool.lookup_company_by_inn",
            resource="party",
            new_value={"inn": result.get("inn"), "company_name": (result.get("flat") or {}).get("company_name")},
        )
        return ToolResult(ok=True, data=result, message="Party lookup completed")


class CreateLeadTool:
    name = "create_lead"
    description = "Create a sales lead with name and phone. Optional email, company, website, inn, source."
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "phone": {"type": "string"},
            "email": {"type": "string"},
            "company": {"type": "string"},
            "website": {"type": "string"},
            "inn": {"type": "string"},
            "source": {"type": "string"},
        },
        "required": ["name", "phone"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        name = str(params.get("name") or "").strip()
        phone = str(params.get("phone") or "").strip()
        if not name or not phone:
            return ToolResult(ok=False, message="name and phone are required")

        lead, meta = create_lead_record(
            db,
            ctx,
            name=name[:120],
            phone=phone[:60],
            email=(str(params.get("email")).strip()[:160] if params.get("email") else None),
            company=(str(params.get("company")).strip()[:160] if params.get("company") else None),
            website=(str(params.get("website")).strip()[:255] if params.get("website") else None),
            inn=(str(params.get("inn")).strip() if params.get("inn") else None),
            source=str(params.get("source") or "operator").strip()[:120],
            audit_action="tool.create_lead",
            event_source="operator.create_lead",
            channel="operator",
        )
        return ToolResult(
            ok=True,
            data={
                "lead_id": str(lead.id),
                "party_enriched": meta["enrichment"].get("enriched"),
                "inn": lead.inn,
            },
            message="Lead created",
        )
