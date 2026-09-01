from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.adapters.knowledge import KnowledgeAdapter
from app.core.principals import principal_for_operator
from app.core.tenant import TenantContext
from app.models.lead import Lead
from app.operator.tools.registry import ToolResult
from app.services.audit import write_audit
from app.services.leads import notify_lead_telegram


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
        hits = data.get("matches") or data.get("results") or []
        write_audit(
            db,
            ctx,
            action="tool.get_knowledge",
            resource="knowledge",
            new_value={"query": query, "hits": len(hits), "principal": pid},
        )
        return ToolResult(ok=True, data=data, message="Knowledge search completed")


class CreateLeadTool:
    name = "create_lead"
    description = "Create a sales lead with name and phone. Optional email, company, website, source."
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "phone": {"type": "string"},
            "email": {"type": "string"},
            "company": {"type": "string"},
            "website": {"type": "string"},
            "source": {"type": "string"},
        },
        "required": ["name", "phone"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        name = str(params.get("name") or "").strip()
        phone = str(params.get("phone") or "").strip()
        if not name or not phone:
            return ToolResult(ok=False, message="name and phone are required")

        lead = Lead(
            tenant_id=ctx.tenant_id,
            source=str(params.get("source") or "operator").strip()[:120],
            name=name[:120],
            phone=phone[:60],
            email=(str(params.get("email")).strip()[:160] if params.get("email") else None),
            company=(str(params.get("company")).strip()[:160] if params.get("company") else None),
            website=(str(params.get("website")).strip()[:255] if params.get("website") else None),
        )
        db.add(lead)
        db.flush()
        notify_lead_telegram(lead)
        write_audit(
            db,
            ctx,
            action="tool.create_lead",
            resource=f"lead:{lead.id}",
            new_value={"name": lead.name, "phone": lead.phone, "source": lead.source},
        )
        return ToolResult(ok=True, data={"lead_id": str(lead.id)}, message="Lead created")
